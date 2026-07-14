#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
R Bridge - Manages R executable detection and script execution

This module provides the foundation for R integration, handling:
- R installation detection on Windows (including Registry)
- R package verification and installation
- Script execution with proper error handling
"""

import os
import sys
import subprocess
import json
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

from ...utils.logger import get_logger
from ...utils.subprocess_utils import no_console_kwargs
from ...core.version import APP_NAME
from ...core.r_runtime import RRuntimeInfo, RRuntimeResolver, resolve_versioned_r_libs_user

logger = get_logger('r_bridge')


def _default_r_lib_candidates() -> List[Path]:
    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    candidates: List[Path] = []
    if local_appdata:
        # Windows: locais padrão de instalação por usuário
        candidates.append(Path(local_appdata) / APP_NAME / "R" / "library")
        candidates.append(Path(local_appdata) / "LabiiaLex" / "R" / "library")
    # Windows: instalação compartilhada legada
    candidates.append(Path(fr"C:\ProgramData\{APP_NAME}\R\library"))
    candidates.append(Path(r"C:\ProgramData\LabiiaLex\R\library"))
    # Linux/macOS: caminho XDG
    if sys.platform != "win32":
        xdg_data = (os.environ.get("XDG_DATA_HOME") or "").strip()
        xdg_base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
        candidates.append(xdg_base / APP_NAME / "R" / "library")
        if sys.platform == "darwin":
            candidates.append(Path.home() / "Library" / "Application Support" / APP_NAME / "R" / "library")
    return candidates


INSTALLER_R_LIBS_CANDIDATES = _default_r_lib_candidates()

# Required R packages for IRaMuTeQ-style visualizations
REQUIRED_PACKAGES = [
    "XML",
    "Rmpfr",
    "MASS",
    "ade4",
    "ape",
    "ca",
    "Matrix",
    "cluster",
    "colorspace",
    "dplyr",
    "fmsb",
    "ggplot2",
    "ggraph",
    "ggwordcloud",
    "igraph",
    "intergraph",
    "irlba",
    "jsonlite",
    "ldatuning",
    "network",
    "png",
    "proxy",
    "quanteda",
    "quanteda.textstats",
    "quanteda.textplots",
    "RColorBrewer",
    "rgexf",
    "rgl",
    "reshape2",
    "scales",
    "scatterplot3d",
    "servr",
    "slam",
    "sna",
    "stopwords",
    "stringi",
    "syuzhet",
    "textometry",
    "tidyr",
    "topicmodels",
    "wordcloud",
    "wordcloud2",
]

# Optional base/runtime helpers that are not ordinary CRAN dependencies.
OPTIONAL_PACKAGES = ["tcltk"]


class RBridge:
    """
    Manages R executable detection and script execution.

    Provides methods to:
    - Find R installation on the system
    - Check and install required packages
    - Execute R scripts with arguments
    """

    def __init__(self):
        self._r_executable: Optional[str] = None
        self._r_available: Optional[bool] = None
        self._r_version: Optional[str] = None
        self._r_runtime_info: Optional[RRuntimeInfo] = None
        self._packages_status: Dict[str, bool] = {}
        self._scripts_dir = Path(__file__).parent / 'r_scripts'

    @property
    def r_available(self) -> bool:
        """Check if R is available on the system."""
        if self._r_available is None:
            self._r_executable = self.find_r_executable()
            self._r_available = self._r_executable is not None
        return self._r_available

    @property
    def r_executable(self) -> Optional[str]:
        """Get the path to the R executable."""
        if self._r_executable is None:
            self._r_executable = self.find_r_executable()
        return self._r_executable

    @property
    def scripts_dir(self) -> Path:
        """Get the directory containing R scripts."""
        return self._scripts_dir

    def _build_r_env(self, extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Build subprocess environment for R execution.

        Uses installer-managed library when available, so runtime remains deterministic.
        """
        env = os.environ.copy()

        forced_lib = env.get("LEXIANALYST_R_LIBS_USER", "").strip()
        if not forced_lib:
            version = ""
            if self._r_runtime_info is not None:
                version = self._r_runtime_info.version_token
            elif self._r_executable is None:
                self._r_executable = self.find_r_executable()
                if self._r_executable is None:
                    version = "4.0.0"
            if not version and self._r_runtime_info is not None:
                version = self._r_runtime_info.version_token
            forced_lib = resolve_versioned_r_libs_user(version or "4.0.0", app_name=APP_NAME)

        if forced_lib:
            try:
                Path(forced_lib).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            env["R_LIBS_USER"] = forced_lib
            env["LEXIANALYST_R_LIBS_USER"] = forced_lib

        if extra_env:
            env.update(extra_env)
        return env

    def _find_r_in_registry(self) -> Optional[str]:
        """Search Windows Registry for R installation path."""
        if sys.platform != 'win32':
            return None

        try:
            import winreg

            # Check both HKLM and HKCU
            for hkey in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for subkey in [r'SOFTWARE\R-core\R', r'SOFTWARE\R-core\R64']:
                    try:
                        with winreg.OpenKey(hkey, subkey) as key:
                            install_path, _ = winreg.QueryValueEx(key, 'InstallPath')
                            rscript = os.path.join(install_path, 'bin', 'Rscript.exe')
                            if os.path.exists(rscript):
                                logger.info(f"R found in registry: {rscript}")
                                return rscript
                    except (FileNotFoundError, OSError):
                        continue
        except ImportError:
            logger.debug("winreg not available")
        except Exception as e:
            logger.debug(f"Registry search error: {e}")

        return None

    def _find_bundled_r(self) -> Optional[str]:
        """Prefer bundled R runtime shipped with the app when available."""
        candidates: List[str] = []

        for env_name in ("LEXIANALYST_BUNDLED_R_HOME", "LEXIANALYST_R_HOME"):
            env_home = (os.environ.get(env_name) or "").strip()
            if env_home:
                # Adiciona candidatos para ambas as plataformas conforme SO
                if sys.platform == "win32":
                    candidates.extend(
                        [
                            os.path.join(env_home, "bin", "Rscript.exe"),
                            os.path.join(env_home, "bin", "x64", "Rscript.exe"),
                        ]
                    )
                else:
                    candidates.append(os.path.join(env_home, "bin", "Rscript"))

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            if sys.platform == "win32":
                candidates.extend(
                    [
                        str(exe_dir / "resources" / "R" / "bin" / "Rscript.exe"),
                        str(exe_dir / "_internal" / "resources" / "R" / "bin" / "Rscript.exe"),
                    ]
                )
            else:
                candidates.extend(
                    [
                        str(exe_dir / "resources" / "R" / "bin" / "Rscript"),
                        str(exe_dir / "_internal" / "resources" / "R" / "bin" / "Rscript"),
                    ]
                )
        else:
            project_root = Path(__file__).resolve().parents[3]
            if sys.platform == "win32":
                candidates.append(str(project_root / "resources" / "R" / "bin" / "Rscript.exe"))
            else:
                candidates.append(str(project_root / "resources" / "R" / "bin" / "Rscript"))

        for candidate in candidates:
            if os.path.exists(candidate) and self._test_rscript(candidate):
                logger.info(f"Bundled R runtime found: {candidate}")
                return candidate
        return None

    def _test_rscript(self, path: str) -> bool:
        """Test if Rscript executable works."""
        try:
            result = subprocess.run(
                [path, '--version'],
                capture_output=True,
                timeout=10,
                env=self._build_r_env(),
                **no_console_kwargs(),
            )
            return result.returncode == 0
        except Exception:
            return False

    def find_r_executable(self) -> Optional[str]:
        """
        Find Rscript executable on the system.

        Searches in:
        1. Windows Registry (Windows only)
        2. Common Windows installation locations
        3. PATH environment variable
        4. Common Unix locations

        Returns:
            Path to Rscript executable, or None if not found
        """
        try:
            runtime = RRuntimeResolver().resolve()
        except Exception as exc:
            logger.warning("R not found on system: %s", exc)
            return None

        self._r_runtime_info = runtime
        logger.info("R found at: %s (%s)", runtime.rscript_path, runtime.version_token)
        return str(runtime.rscript_path)

    def _parse_version(self, path: str) -> tuple:
        """Parse R version from path like 'R-4.3.1' for sorting."""
        import re
        match = re.search(r'R-(\d+)\.(\d+)\.?(\d*)', os.path.basename(path))
        if match:
            major, minor, patch = match.groups()
            return (int(major), int(minor), int(patch) if patch else 0)
        return (0, 0, 0)

    def _run_r_code(self, r_code: str, timeout: int = 60) -> Tuple[bool, str, str]:
        """
        Execute R code using a temp file (Windows compatible).

        Returns:
            Tuple of (success, stdout, stderr)
        """
        if not self.r_available:
            return False, "", "R not available"

        # Write R code to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.R', delete=False,
                                         encoding='utf-8') as f:
            f.write(r_code)
            temp_script = f.name

        try:
            result = subprocess.run(
                [self.r_executable, '--vanilla', '--slave', temp_script],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._build_r_env(),
                **no_console_kwargs(),
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", f"Timeout after {timeout}s"
        except Exception as e:
            return False, "", str(e)
        finally:
            try:
                os.unlink(temp_script)
            except OSError:
                pass

    def check_packages(self, packages: Optional[List[str]] = None) -> Dict[str, bool]:
        """
        Check if required R packages are installed.

        Args:
            packages: List of package names to check (default: REQUIRED_PACKAGES)

        Returns:
            Dictionary mapping package name to installed status
        """
        if not self.r_available:
            return {pkg: False for pkg in (packages or REQUIRED_PACKAGES)}

        packages = packages or REQUIRED_PACKAGES

        # R code to check packages (without jsonlite dependency)
        r_code = '''
packages <- c({pkgs})
results <- sapply(packages, function(pkg) {{
    requireNamespace(pkg, quietly = TRUE)
}})
# Output as simple format: pkg1=TRUE,pkg2=FALSE
cat(paste(names(results), as.character(results), sep="=", collapse=","))
'''.format(pkgs=', '.join(f'"{p}"' for p in packages))

        success, stdout, stderr = self._run_r_code(r_code, timeout=30)

        if success and stdout.strip():
            # Parse simple format: pkg1=TRUE,pkg2=FALSE
            result = {}
            for pair in stdout.strip().split(','):
                if '=' in pair:
                    name, value = pair.split('=', 1)
                    result[name.strip()] = value.strip().upper() == 'TRUE'

            if result:
                self._packages_status = result
                return result
        else:
            logger.warning(f"Package check failed: {stderr}")

        return {pkg: False for pkg in packages}

    def get_package_build_mismatches(
        self,
        packages: Optional[List[str]] = None,
    ) -> List[Dict[str, str]]:
        """Return compiled R packages built for a different R minor version."""
        if not self.r_available:
            return []

        packages = packages or REQUIRED_PACKAGES
        r_code = r'''
packages <- c({pkgs})
minor_token <- function(version) {{
  parts <- strsplit(as.character(version), ".", fixed = TRUE)[[1]]
  if (length(parts) < 2) {{
    return(as.character(version))
  }}
  paste(parts[[1]], parts[[2]], sep = ".")
}}
current_minor <- minor_token(as.character(getRversion()))
for (pkg in packages) {{
  if (!requireNamespace(pkg, quietly = TRUE)) {{
    next
  }}
  desc <- tryCatch(packageDescription(pkg), error = function(e) NULL)
  if (is.null(desc)) {{
    next
  }}
  needs <- tolower(as.character(if (is.null(desc$NeedsCompilation)) "no" else desc$NeedsCompilation))
  if (!identical(needs, "yes")) {{
    next
  }}
  built <- as.character(if (is.null(desc$Built)) "" else desc$Built)
  match <- regexpr("R [0-9]+\\.[0-9]+(?:\\.[0-9]+)?", built, perl = TRUE)
  if (match[1] < 0) {{
    next
  }}
  built_version <- sub("^R ", "", regmatches(built, match))
  if (!identical(minor_token(built_version), current_minor)) {{
    cat(paste(pkg, built, current_minor, sep = "\t"), "\n", sep = "")
  }}
}}
'''.format(pkgs=', '.join(f'"{p}"' for p in packages))

        success, stdout, stderr = self._run_r_code(r_code, timeout=30)
        if not success:
            logger.warning("R package build mismatch check failed: %s", stderr)
            return []

        mismatches: List[Dict[str, str]] = []
        for line in stdout.splitlines():
            parts = line.strip().split("\t")
            if len(parts) != 3:
                continue
            mismatches.append(
                {"package": parts[0], "built": parts[1], "current_minor": parts[2]}
            )
        return mismatches

    def install_packages(self, packages: Optional[List[str]] = None) -> bool:
        """
        Install missing R packages.

        Args:
            packages: List of package names to install (default: missing packages)

        Returns:
            True if all packages installed successfully
        """
        if not self.r_available:
            logger.error("Cannot install packages: R not available")
            return False

        if packages is None:
            # Install missing required + optional packages by default
            required_status = self.check_packages(REQUIRED_PACKAGES)
            optional_status = self.check_packages(OPTIONAL_PACKAGES)
            packages = [
                pkg for pkg, installed in {**required_status, **optional_status}.items()
                if not installed
            ]

        if not packages:
            logger.info("All required packages already installed")
            return True

        logger.info(f"Installing R packages: {packages}")

        # R code to install packages (using temp file for Windows compatibility)
        r_code = '''
options(repos = c(CRAN = "https://cloud.r-project.org"))
packages <- c({pkgs})
deps <- c("Depends", "Imports", "LinkingTo")
pkg_type <- if (.Platform$OS.type == "windows") "binary" else "source"
libs_user <- Sys.getenv("LEXIANALYST_R_LIBS_USER", unset = Sys.getenv("R_LIBS_USER", unset = ""))
if (nzchar(libs_user)) {{
    dir.create(libs_user, recursive = TRUE, showWarnings = FALSE)
    .libPaths(unique(c(normalizePath(libs_user, winslash = "/", mustWork = FALSE), .libPaths())))
    Sys.setenv(R_LIBS_USER = libs_user)
}}

for (pkg in packages) {{
    if (!requireNamespace(pkg, quietly = TRUE)) {{
        cat(paste("Installing", pkg, "...\\n"))
        tryCatch({{
            if (nzchar(libs_user)) {{
                install.packages(pkg, quiet = TRUE, lib = libs_user, dependencies = deps, type = pkg_type)
            }} else {{
                install.packages(pkg, quiet = TRUE, dependencies = deps, type = pkg_type)
            }}
            if (requireNamespace(pkg, quietly = TRUE)) {{
                cat(paste("[OK]", pkg, "\\n"))
            }} else {{
                cat(paste("[FAIL]", pkg, "\\n"))
            }}
        }}, error = function(e) {{
            cat(paste("[ERROR]", pkg, "-", e$message, "\\n"))
        }})
    }} else {{
        cat(paste("[SKIP]", pkg, "already installed\\n"))
    }}
}}
'''.format(pkgs=', '.join(f'"{p}"' for p in packages))

        success, stdout, stderr = self._run_r_code(r_code, timeout=600)  # 10 min for install

        if stdout:
            logger.info(f"Install output: {stdout}")
        if stderr:
            logger.warning(f"Install warnings: {stderr}")

        # Verify installation
        status = self.check_packages(packages)
        all_installed = all(status.values())

        if all_installed:
            logger.info("All packages installed successfully")
        else:
            failed = [p for p, s in status.items() if not s]
            logger.error(f"Failed to install: {failed}")

        return all_installed

    def execute_script(self, script_name: str, args: Dict[str, Any],
                       timeout: int = 120) -> Tuple[bool, str, bytes]:
        """
        Execute an R script with arguments.

        Args:
            script_name: Name of the script in r_scripts directory
            args: Dictionary of arguments to pass to the script
            timeout: Timeout in seconds (default: 120)

        Returns:
            Tuple of (success, stdout, output_bytes)
            - success: True if script executed successfully
            - stdout: Standard output from R
            - output_bytes: Binary content of output file if generated
        """
        if not self.r_available:
            return False, "R not available", b''

        script_path = self.scripts_dir / script_name
        if not script_path.exists():
            return False, f"Script not found: {script_name}", b''

        # Create args JSON file with proper encoding
        args_file = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json',
                                             delete=False, encoding='utf-8') as f:
                json.dump(args, f, ensure_ascii=False)
                args_file = f.name

            # Execute R script
            result = subprocess.run(
                [self.r_executable, '--vanilla', str(script_path), args_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=self._build_r_env(),
                **no_console_kwargs(),
            )

            success = result.returncode == 0
            stdout = result.stdout + result.stderr

            # Read output file if specified and exists
            output_bytes = b''
            output_file = args.get('output_file')
            if output_file and os.path.exists(output_file):
                try:
                    with open(output_file, 'rb') as f:
                        output_bytes = f.read()
                except Exception as e:
                    logger.warning(f"Could not read output file: {e}")

            if not success:
                logger.error(f"R script error: {stdout}")
            else:
                logger.debug(f"R script completed: {script_name}")

            return success, stdout, output_bytes

        except subprocess.TimeoutExpired:
            logger.error(f"R script timed out after {timeout}s")
            return False, f"Timeout after {timeout}s", b''
        except Exception as e:
            logger.error(f"Error executing R script: {e}")
            return False, str(e), b''
        finally:
            # Cleanup args file
            if args_file:
                try:
                    os.unlink(args_file)
                except OSError:
                    pass

    def get_r_version(self) -> Optional[str]:
        """Get R version string."""
        if not self.r_available:
            return None

        if self._r_version:
            return self._r_version

        # Use simple R code to get version
        r_code = 'cat(paste(R.version$major, R.version$minor, sep="."))'
        success, stdout, _ = self._run_r_code(r_code, timeout=10)

        if success and stdout.strip():
            self._r_version = f"R {stdout.strip()}"
            return self._r_version

        return None

    def get_status_summary(self) -> Dict[str, Any]:
        """
        Get a summary of R integration status.

        Returns:
            Dictionary with status information
        """
        return {
            'r_available': self.r_available,
            'r_executable': self.r_executable,
            'r_version': self.get_r_version() if self.r_available else None,
            'packages': self.check_packages() if self.r_available else {},
            'optional_packages': self.check_packages(OPTIONAL_PACKAGES) if self.r_available else {},
            'r_libs_user': self._build_r_env().get("R_LIBS_USER", ""),
            'scripts_dir': str(self.scripts_dir),
        }

    def get_package_diagnostics(
        self,
        required: Optional[List[str]] = None,
        optional: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Return structured package diagnostics for installers/self-tests."""
        required_list = required or REQUIRED_PACKAGES
        optional_list = optional or OPTIONAL_PACKAGES
        required_status = self.check_packages(required_list) if self.r_available else {}
        optional_status = self.check_packages(optional_list) if self.r_available else {}
        missing_required = sorted([pkg for pkg, ok in required_status.items() if not ok])
        missing_optional = sorted([pkg for pkg, ok in optional_status.items() if not ok])
        return {
            "r_available": self.r_available,
            "r_executable": self.r_executable,
            "r_version": self.get_r_version() if self.r_available else None,
            "required_status": required_status,
            "optional_status": optional_status,
            "missing_required": missing_required,
            "missing_optional": missing_optional,
            "r_libs_user": self._build_r_env().get("R_LIBS_USER", ""),
        }

    def ensure_packages(self) -> bool:
        """
        Ensure all required packages are installed.

        Returns:
            True if all packages are available
        """
        status = self.check_packages()
        if all(status.values()):
            return True
        return self.install_packages()
