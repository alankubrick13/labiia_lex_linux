"""Execute R scripts via subprocess with Windows-friendly detection."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from ..utils.logger import get_logger
from ..utils.paths import PathManager
from ..utils.subprocess_utils import no_console_kwargs
from .version import APP_NAME
from .r_runtime import RRuntimeInfo, RRuntimeResolver, resolve_versioned_r_libs_user


@dataclass
class ExecutionResult:
    """
    Result of an R script execution.
    """

    stdout: str
    stderr: str
    return_code: int


class RNotFoundError(RuntimeError):
    """
    Raised when Rscript cannot be located.
    """


class RExecutionError(RuntimeError):
    """
    Raised when an R script fails to execute.
    """


class RTimeoutError(TimeoutError):
    """
    Raised when R execution exceeds the timeout.
    """


ProgressCallback = Callable[[int], None]


class RExecutor:
    """
    Executa scripts R via subprocess, preservando o comportamento do IRaMuTeQ.
    """

    def __init__(self, r_path: Optional[str] = None, cran_mirror: str = "https://cloud.r-project.org") -> None:
        """
        Inicializa o executor de scripts R.

        Args:
            r_path: Caminho para Rscript.exe. Se None, detecta automaticamente.
            cran_mirror: URL do CRAN mirror para instalacao de pacotes.
        """
        self._logger = get_logger(__name__)
        self._cran_mirror = cran_mirror
        self._r_runtime_info: Optional[RRuntimeInfo] = None
        self.r_path = self._resolve_r_path(r_path)
        self._r_libs_user = self._resolve_r_libs_user()

    def _resolve_r_libs_user(self) -> str:
        """
        Resolve a user-writable, R-minor-versioned library target.

        LEXIANALYST_R_LIBS_USER remains an explicit override. Plain R_LIBS_USER
        is intentionally ignored so LabiiaLex does not reuse packages compiled
        for another R minor version.
        """
        version = ""
        if self._r_runtime_info is not None:
            version = self._r_runtime_info.version_token
        return resolve_versioned_r_libs_user(version or "4.0.0", app_name=APP_NAME)

    def _build_r_env(self) -> Dict[str, str]:
        """
        Build subprocess environment for R execution.
        """
        env = os.environ.copy()
        # Compatibilidade com instâncias criadas via __new__ em testes.
        r_libs_user = str(getattr(self, "_r_libs_user", "") or "").strip()
        if r_libs_user:
            env["R_LIBS_USER"] = r_libs_user
            env["LEXIANALYST_R_LIBS_USER"] = r_libs_user
        return env

    def _resolve_r_path(self, r_path: Optional[str]) -> str:
        """
        Resolve o caminho para Rscript.exe a partir de entrada opcional.

        Args:
            r_path: Caminho fornecido pelo usuario ou None.

        Returns:
            Caminho absoluto para Rscript.exe.

        Raises:
            RNotFoundError: Se o caminho nao existir.
        """
        if r_path:
            candidate = Path(r_path)
            if candidate.is_dir():
                # Resolve nome correto do binário por plataforma
                rscript_name = "Rscript.exe" if sys.platform == "win32" else "Rscript"
                candidate = candidate / "bin" / rscript_name
            try:
                self._r_runtime_info = RRuntimeResolver().resolve(explicit_path=candidate)
                return str(self._r_runtime_info.rscript_path)
            except Exception as exc:
                raise RNotFoundError(self._build_r_not_found_message(custom_path=r_path)) from exc

        runtime = RRuntimeResolver().resolve()
        self._r_runtime_info = runtime
        return str(runtime.rscript_path)

    def detect_r_path(self) -> str:
        """
        Detecta o caminho do Rscript.exe no Windows.

        Returns:
            Caminho para Rscript.exe.

        Raises:
            RNotFoundError: Se nao encontrar o Rscript.
        """
        try:
            runtime = RRuntimeResolver().resolve()
        except Exception as exc:
            raise RNotFoundError(self._build_r_not_found_message()) from exc
        self._r_runtime_info = runtime
        return str(runtime.rscript_path)

    def check_packages(self, packages: Sequence[str]) -> Dict[str, bool]:
        """
        Verifica se pacotes R estao instalados.

        Args:
            packages: Lista de nomes de pacotes.

        Returns:
            Dict {pacote: True/False}.
        """
        if not packages:
            return {}

        quoted = ", ".join([f'"{pkg}"' for pkg in packages])
        script_lines = []
        if self._r_libs_user:
            lib_norm = self._r_libs_user.replace("\\", "/")
            script_lines.extend(
                [
                    f'libs_user <- "{lib_norm}"',
                    "dir.create(libs_user, recursive = TRUE, showWarnings = FALSE)",
                    ".libPaths(unique(c(normalizePath(libs_user, winslash = '/', mustWork = FALSE), .libPaths())))",
                    "Sys.setenv(R_LIBS_USER = libs_user)",
                ]
            )
        script_lines.extend(
            [
                f"pkgs <- c({quoted})",
                "installed <- rownames(installed.packages())",
                "status <- pkgs %in% installed",
                "names(status) <- pkgs",
                "for (p in pkgs) { cat(p, ':', status[[p]], '\\n', sep='') }",
            ]
        )
        script = "\n".join(script_lines) + "\n"

        temp_script = self._write_temp_script(script)
        try:
            result = self.execute(str(temp_script))
        finally:
            temp_script.unlink(missing_ok=True)

        status: Dict[str, bool] = {}
        for line in result.stdout.splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            status[name.strip()] = value.strip().lower() == "true"

        for pkg in packages:
            status.setdefault(pkg, False)

        return status

    def install_packages(self, packages: Sequence[str]) -> bool:
        """
        Instala pacotes R faltantes via CRAN.

        Args:
            packages: Lista de nomes de pacotes.

        Returns:
            True se instalacao bem-sucedida, False caso contrario.
        """
        if not packages:
            return True

        quoted = ", ".join([f'"{pkg}"' for pkg in packages])
        script_lines = []
        install_block = [
            "deps <- c('Depends', 'Imports', 'LinkingTo')",
            "pkg_type <- if (.Platform$OS.type == 'windows') 'binary' else 'source'",
        ]
        if self._r_libs_user:
            lib_norm = self._r_libs_user.replace("\\", "/")
            script_lines.extend(
                [
                    f'libs_user <- "{lib_norm}"',
                    "dir.create(libs_user, recursive = TRUE, showWarnings = FALSE)",
                    ".libPaths(unique(c(normalizePath(libs_user, winslash = '/', mustWork = FALSE), .libPaths())))",
                    "Sys.setenv(R_LIBS_USER = libs_user)",
                ]
            )
            script_lines.extend(install_block)
            script_lines.extend(
                [
                    "install_one <- function(pkg) {",
                    "  install.packages(pkg, repos = \"" + self._cran_mirror + "\", lib = libs_user, dependencies = deps, type = pkg_type, quiet = TRUE)",
                    "}",
                ]
            )
        else:
            script_lines.extend(
                [
                    *install_block,
                    "install_one <- function(pkg) {",
                    "  install.packages(pkg, repos = \"" + self._cran_mirror + "\", dependencies = deps, type = pkg_type, quiet = TRUE)",
                    "}",
                ]
            )
        script_lines.extend(
            [
                f"pkgs <- c({quoted})",
                "for (pkg in pkgs) { install_one(pkg) }",
            ]
        )
        script = "\n".join(script_lines) + "\n"

        temp_script = self._write_temp_script(script)
        try:
            self.execute(str(temp_script))
            return True
        except RExecutionError as exc:
            self._logger.error("Falha ao instalar pacotes R: %s", exc)
            return False
        finally:
            temp_script.unlink(missing_ok=True)

    def execute(
        self,
        script_path: str,
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        """
        Executa um script R.

        IMPORTANTE: Usa exatamente o comando:
        Rscript --vanilla --slave <script_path>

        Args:
            script_path: Caminho para o script R.
            working_dir: Diretorio de trabalho (opcional).
            timeout: Timeout em segundos (None = sem limite).
            on_progress: Callback opcional de progresso (0-100).

        Returns:
            ExecutionResult com stdout, stderr e codigo de retorno.

        Raises:
            FileNotFoundError: Se o script nao existir.
            RExecutionError: Se o script falhar.
            RTimeoutError: Se exceder o timeout.
        """
        script = Path(script_path)
        if not script.is_file():
            raise FileNotFoundError(
                "O que aconteceu: O script R nao foi encontrado.\n"
                "Por que aconteceu: O caminho informado nao existe ou foi movido.\n"
                "Como resolver: Verifique o caminho do script e tente novamente.\n"
                f"Script: {script_path}"
            )

        command = [self.r_path, "--vanilla", "--slave", str(script)]
        if on_progress:
            on_progress(0)

        try:
            process = subprocess.Popen(
                command,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_r_env(),
                **no_console_kwargs(),
            )
        except OSError as exc:
            raise RExecutionError(self._build_r_exec_error_message(str(script), str(exc))) from exc

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, stderr = process.communicate()
            raise RTimeoutError(self._build_r_timeout_message(timeout)) from exc

        result = ExecutionResult(stdout=stdout, stderr=stderr, return_code=process.returncode)

        if process.returncode != 0:
            details = self._format_process_output(
                stdout=stdout,
                stderr=stderr,
                return_code=process.returncode,
            )
            raise RExecutionError(self._build_r_exec_error_message(str(script), details))

        if on_progress:
            on_progress(100)

        return result

    def execute_with_args(
        self,
        script_path: str,
        args: Optional[Sequence[str]] = None,
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> ExecutionResult:
        """
        Execute R script with positional arguments.

        Equivalent command:
        Rscript --vanilla --slave <script_path> <arg1> <arg2> ...
        """
        script = Path(script_path)
        if not script.is_file():
            raise FileNotFoundError(
                "O que aconteceu: O script R nao foi encontrado.\n"
                "Por que aconteceu: O caminho informado nao existe ou foi movido.\n"
                "Como resolver: Verifique o caminho do script e tente novamente.\n"
                f"Script: {script_path}"
            )

        command = [self.r_path, "--vanilla", "--slave", str(script)]
        if args:
            command.extend(str(item) for item in args)

        if on_progress:
            on_progress(0)

        try:
            process = subprocess.Popen(
                command,
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=self._build_r_env(),
                **no_console_kwargs(),
            )
        except OSError as exc:
            raise RExecutionError(self._build_r_exec_error_message(str(script), str(exc))) from exc

        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            stdout, stderr = process.communicate()
            raise RTimeoutError(self._build_r_timeout_message(timeout)) from exc

        result = ExecutionResult(stdout=stdout, stderr=stderr, return_code=process.returncode)
        if process.returncode != 0:
            details = self._format_process_output(
                stdout=stdout,
                stderr=stderr,
                return_code=process.returncode,
            )
            raise RExecutionError(self._build_r_exec_error_message(str(script), details))

        if on_progress:
            on_progress(100)
        return result

    def _write_temp_script(self, content: str) -> Path:
        """
        Cria um script R temporario com o conteudo informado.

        Args:
            content: Codigo R.

        Returns:
            Path para o arquivo temporario.
        """
        temp_file = tempfile.NamedTemporaryFile(
            delete=False, suffix=".R", mode="w", encoding="utf-8"
        )
        try:
            temp_file.write(content)
        finally:
            temp_file.close()
        return Path(temp_file.name)

    def _rscript_candidates_from_home(self, r_home: Path) -> List[Path]:
        """
        Gera candidatos a partir de R_HOME.

        No Windows usa Rscript.exe (e x64/Rscript.exe para instalações antigas).
        No Linux/macOS usa Rscript (sem extensão).
        """
        if sys.platform == "win32":
            return [
                r_home / "bin" / "Rscript.exe",
                r_home / "bin" / "x64" / "Rscript.exe",
            ]
        else:
            return [
                r_home / "bin" / "Rscript",
            ]

    def _candidates_from_bundled_runtime(self) -> List[Path]:
        """
        Busca runtime R embarcado no bundle do app.

        Ordem:
        1. LEXIANALYST_BUNDLED_R_HOME / LEXIANALYST_R_HOME
        2. resources/R dentro do app congelado
        3. resources/R no projeto local
        """
        candidates: List[Path] = []

        for env_name in ("LEXIANALYST_BUNDLED_R_HOME", "LEXIANALYST_R_HOME"):
            env_home = (os.environ.get(env_name) or "").strip()
            if env_home:
                candidates.extend(self._rscript_candidates_from_home(Path(env_home)))

        try:
            project_root = PathManager.project_root()
            candidates.extend(self._rscript_candidates_from_home(project_root / "resources" / "R"))
        except Exception:
            pass

        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.extend(self._rscript_candidates_from_home(exe_dir / "resources" / "R"))
        else:
            local_root = Path(__file__).resolve().parents[2]
            candidates.extend(self._rscript_candidates_from_home(local_root / "resources" / "R"))

        return candidates

    def _candidates_from_where(self) -> List[Path]:
        """
        Descobre caminhos via shutil.which (todos os SOs) ou 'where' (Windows).

        Returns:
            Lista de caminhos encontrados no PATH.
        """
        import shutil
        candidates: List[Path] = []

        # shutil.which funciona em todos os sistemas
        for name in ("Rscript", "rscript"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
                break  # Evita duplicatas

        # Windows: tenta 'where' como complemento (cobre edge cases)
        if sys.platform == "win32" and not candidates:
            try:
                result = subprocess.run(
                    ["where", "Rscript"],
                    check=False,
                    capture_output=True,
                    text=True,
                    **no_console_kwargs(),
                )
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        if line:
                            candidates.append(Path(line))
            except OSError:
                pass

        return candidates

    def _unix_candidates(self) -> List[Path]:
        """
        Descobre Rscript em instalações típicas do Linux e macOS.

        Chamado apenas em sistemas não-Windows. Complementa _candidates_from_where()
        cobrindo instalações que não estejam no PATH.
        """
        import shutil
        candidates: List[Path] = []

        unix_r_homes = [
            Path("/usr/lib/R"),           # Debian/Ubuntu (r-base)
            Path("/usr/lib64/R"),          # Fedora/RHEL
            Path("/usr/local/lib/R"),      # Compilado do fonte
            Path("/usr/local/lib64/R"),    # Compilado 64-bit
            Path("/opt/R"),                # rig
            Path("/opt/local/lib/R"),      # MacPorts
        ]

        for home in unix_r_homes:
            rscript = home / "bin" / "Rscript"
            if rscript.exists():
                candidates.append(rscript)

        # rig: versões múltiplas em /opt/R/R-x.y.z/
        opt_r = Path("/opt/R")
        if opt_r.is_dir():
            for version_dir in sorted(opt_r.iterdir(), reverse=True):
                rscript = version_dir / "bin" / "Rscript"
                if rscript.exists():
                    candidates.append(rscript)

        # macOS: R.framework
        if sys.platform == "darwin":
            fw_rscript = Path("/Library/Frameworks/R.framework/Versions/Current/Resources/bin/Rscript")
            if fw_rscript.exists():
                candidates.append(fw_rscript)

        return candidates

    def _candidates_from_registry(self) -> List[Path]:
        """
        Busca instalacoes do R no registro do Windows.

        Returns:
            Lista de caminhos encontrados.
        """
        candidates: List[Path] = []
        try:
            import winreg
        except ImportError:
            return candidates

        key_paths = [
            r"SOFTWARE\R-core\R",
            r"SOFTWARE\R-core\R64",
            r"SOFTWARE\WOW6432Node\R-core\R",
        ]

        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key_path in key_paths:
                try:
                    with winreg.OpenKey(root, key_path) as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                        if install_path:
                            candidates.extend(
                                self._rscript_candidates_from_home(Path(install_path))
                            )
                except FileNotFoundError:
                    continue
                except OSError:
                    continue

        return candidates

    def _candidates_from_program_files(self) -> List[Path]:
        """
        Busca instalacoes em Program Files.

        Returns:
            Lista de caminhos encontrados.
        """
        candidates: List[Path] = []
        program_files = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        ]

        for base in program_files:
            base_path = Path(base) / "R"
            if not base_path.exists():
                continue
            for r_dir in base_path.glob("R-*"):
                candidates.extend(self._rscript_candidates_from_home(r_dir))

        return candidates

    def _candidates_from_local_appdata(self) -> List[Path]:
        """
        Busca instalacoes em LOCALAPPDATA (instalacao por usuario).

        Returns:
            Lista de caminhos encontrados.
        """
        candidates: List[Path] = []
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return candidates

        # Busca em LOCALAPPDATA/Programs/R (instalacao padrao por usuario)
        base_path = Path(local_appdata) / "Programs" / "R"
        if base_path.exists():
            for r_dir in base_path.glob("R-*"):
                candidates.extend(self._rscript_candidates_from_home(r_dir))

        # Busca em LOCALAPPDATA/R (instalacao alternativa)
        # R pode ser instalado diretamente em AppData/Local/R
        alt_base_path = Path(local_appdata) / "R"
        if alt_base_path.exists():
            for r_dir in alt_base_path.glob("R-*"):
                candidates.extend(self._rscript_candidates_from_home(r_dir))

        return candidates

    def _unique_candidates(self, candidates: Sequence[Path]) -> List[Path]:
        """
        Remove candidatos duplicados preservando a ordem.

        Args:
            candidates: Lista de caminhos candidatos.

        Returns:
            Lista sem duplicatas.
        """
        seen = set()
        unique: List[Path] = []
        for candidate in candidates:
            try:
                key = str(candidate.resolve()).lower()
            except OSError:
                key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def _build_r_not_found_message(self, custom_path: Optional[str] = None) -> str:
        """
        Gera mensagem amigavel para R nao encontrado.

        Args:
            custom_path: Caminho fornecido manualmente, se houver.

        Returns:
            Mensagem amigavel com orientacao.
        """
        extra = f" Caminho informado: {custom_path}." if custom_path else ""
        rscript_name = "Rscript.exe" if sys.platform == "win32" else "Rscript"
        rscript_path_hint = f"resources/R/bin/{rscript_name}"
        return (
            "O que aconteceu: O Rscript nao foi encontrado no sistema." + extra + "\n"
            "Por que aconteceu: O runtime R embarcado pode estar ausente/invalido, "
            "ou o R externo nao esta disponivel.\n"
            f"Como resolver: Verifique {rscript_path_hint} no pacote instalado "
            "ou configure o caminho do R nas configuracoes."
        )

    def _build_r_exec_error_message(self, script_path: str, details: str) -> str:
        """
        Gera mensagem amigavel para falha de execucao do R.

        Args:
            script_path: Caminho do script executado.
            details: Detalhes tecnicos (stderr).

        Returns:
            Mensagem amigavel.
        """
        return (
            "O que aconteceu: O script R falhou ao executar.\n"
            "Por que aconteceu: O R retornou um erro durante a execucao.\n"
            "Como resolver: Verifique se os pacotes R estao instalados "
            "e se o script existe e esta correto.\n"
            f"Script: {script_path}\n"
            f"Detalhes tecnicos: {details}"
        )

    def _format_process_output(self, stdout: str, stderr: str, return_code: int) -> str:
        """
        Formata saida de erro do processo priorizando stderr.

        Args:
            stdout: Saida padrao do processo.
            stderr: Saida de erro do processo.
            return_code: Codigo de retorno.

        Returns:
            Texto pronto para exibicao ao usuario.
        """
        stdout_text = (stdout or "").strip()
        stderr_text = (stderr or "").strip()

        if stderr_text and stdout_text:
            combined = (
                f"codigo_retorno={return_code}\n"
                f"stderr:\n{stderr_text}\n"
                f"stdout:\n{stdout_text}"
            )
        elif stderr_text:
            combined = f"codigo_retorno={return_code}\n{stderr_text}"
        elif stdout_text:
            combined = f"codigo_retorno={return_code}\nstdout:\n{stdout_text}"
        else:
            combined = f"codigo_retorno={return_code} (sem saida de erro)"

        limit = 6000
        if len(combined) > limit:
            return f"{combined[:limit]}\n...[saida truncada]"
        return combined

    def _build_r_timeout_message(self, timeout: Optional[int]) -> str:
        """
        Gera mensagem amigavel para timeout de execucao.

        Args:
            timeout: Timeout configurado em segundos.

        Returns:
            Mensagem amigavel.
        """
        timeout_text = f"{timeout} segundos" if timeout else "tempo limite"
        return (
            "O que aconteceu: A execucao do R excedeu o tempo limite.\n"
            "Por que aconteceu: A analise pode ser muito grande ou o sistema esta lento.\n"
            "Como resolver: Tente novamente com um corpus menor "
            "ou aumente o timeout nas configuracoes.\n"
            f"Timeout: {timeout_text}."
        )


