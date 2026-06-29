"""Shared R runtime discovery and versioned library resolution."""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .version import APP_NAME
from ..utils.subprocess_utils import no_console_kwargs


MIN_R_VERSION = "4.0.0"


@dataclass(frozen=True)
class RCandidate:
    path: Path
    source: str


@dataclass(frozen=True)
class RRuntimeInfo:
    rscript_path: Path
    source: str
    version_text: str
    version_token: str
    diagnostics: Dict[str, object] = field(default_factory=dict)


VersionProbe = Callable[[Path], str]
CandidateProvider = Callable[[], Sequence[RCandidate]]


def parse_version_token(text: str) -> str:
    match = re.search(r"\d+(?:\.\d+){1,3}", str(text or ""))
    return match.group(0) if match else ""


def version_tuple(version: str) -> Tuple[int, int, int, int]:
    parts: List[int] = []
    for part in str(version or "").split("."):
        parts.append(int(part) if part.isdigit() else 0)
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])  # type: ignore[return-value]


def version_at_least(current: str, minimum: str = MIN_R_VERSION) -> bool:
    if not current:
        return False
    return version_tuple(current) >= version_tuple(minimum)


def r_minor_version(version: str) -> str:
    parts = version_tuple(version)
    return f"{parts[0]}.{parts[1]}"


def resolve_versioned_r_libs_user(
    r_version: str,
    *,
    app_name: str = APP_NAME,
    create: bool = True,
) -> str:
    """Return the LabiiaLex-managed per-R-minor library path.

    On Windows: %LOCALAPPDATA%/<app_name>/R/library/<minor>
    On Linux:   $XDG_DATA_HOME/<app_name>/R/library/<minor>
                (defaults to ~/.local/share/<app_name>/...)
    On macOS:   ~/Library/Application Support/<app_name>/R/library/<minor>
    """
    forced = (os.environ.get("LEXIANALYST_R_LIBS_USER") or "").strip()
    if forced:
        if create:
            Path(forced).mkdir(parents=True, exist_ok=True)
        return forced

    if os.name == "nt":
        local_appdata = (os.environ.get("LOCALAPPDATA") or "").strip()
        if local_appdata:
            base = Path(local_appdata) / app_name / "R" / "library"
        else:
            base = Path.home() / "AppData" / "Local" / app_name / "R" / "library"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / app_name / "R" / "library"
    else:
        # Linux — padrão XDG
        xdg_data = (os.environ.get("XDG_DATA_HOME") or "").strip()
        xdg_base = Path(xdg_data) if xdg_data else Path.home() / ".local" / "share"
        base = xdg_base / app_name / "R" / "library"

    version_dir = r_minor_version(r_version or MIN_R_VERSION)
    path = base / version_dir
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return str(path)


class RRuntimeResolver:
    """Find the best external Rscript runtime for LabiiaLex."""

    def __init__(
        self,
        *,
        min_version: str = MIN_R_VERSION,
        candidate_provider: Optional[CandidateProvider] = None,
        version_probe: Optional[VersionProbe] = None,
    ) -> None:
        self.min_version = min_version
        self._candidate_provider = candidate_provider or self.discover_candidates
        self._version_probe = version_probe or self._probe_version

    def resolve(self, explicit_path: Optional[os.PathLike[str] | str] = None) -> RRuntimeInfo:
        if explicit_path:
            candidate = RCandidate(Path(explicit_path), "explicit")
            return self._resolve_explicit(candidate)

        accepted: List[RRuntimeInfo] = []
        rejected: List[Dict[str, str]] = []

        for candidate in self._unique_candidates(self._candidate_provider()):
            info = self._probe_candidate(candidate, rejected)
            if info is not None:
                accepted.append(info)

        if not accepted:
            raise FileNotFoundError("Rscript nao encontrado ou versao R incompativel.")

        accepted.sort(key=lambda item: version_tuple(item.version_token), reverse=True)
        selected = accepted[0]
        diagnostics = {
            "accepted": [self._diag_entry(item) for item in accepted],
            "rejected": rejected,
            "selected": self._diag_entry(selected),
        }
        return RRuntimeInfo(
            rscript_path=selected.rscript_path,
            source=selected.source,
            version_text=selected.version_text,
            version_token=selected.version_token,
            diagnostics=diagnostics,
        )

    def _resolve_explicit(self, candidate: RCandidate) -> RRuntimeInfo:
        rejected: List[Dict[str, str]] = []
        info = self._probe_candidate(candidate, rejected)
        if info is None:
            reason = rejected[0]["reason"] if rejected else "invalid explicit R runtime"
            raise FileNotFoundError(f"Rscript explicito invalido: {candidate.path} ({reason})")
        diagnostics = {
            "accepted": [self._diag_entry(info)],
            "rejected": rejected,
            "selected": self._diag_entry(info),
            "override": True,
        }
        return RRuntimeInfo(
            rscript_path=info.rscript_path,
            source=info.source,
            version_text=info.version_text,
            version_token=info.version_token,
            diagnostics=diagnostics,
        )

    def _probe_candidate(
        self,
        candidate: RCandidate,
        rejected: List[Dict[str, str]],
    ) -> Optional[RRuntimeInfo]:
        try:
            version_text = self._version_probe(candidate.path)
        except Exception as exc:  # noqa: BLE001 - diagnostic boundary
            rejected.append(self._reject_entry(candidate, str(exc)))
            return None

        token = parse_version_token(version_text)
        if not version_at_least(token, self.min_version):
            rejected.append(self._reject_entry(candidate, f"R {token or '?'} < {self.min_version}"))
            return None

        return RRuntimeInfo(
            rscript_path=candidate.path,
            source=candidate.source,
            version_text=str(version_text or ""),
            version_token=token,
        )

    def discover_candidates(self) -> Sequence[RCandidate]:
        candidates: List[RCandidate] = []

        env_rscript = os.environ.get("LEXIANALYST_RSCRIPT_PATH") or os.environ.get("RSCRIPT_PATH")
        if env_rscript:
            candidates.append(RCandidate(Path(env_rscript), "env:RSCRIPT_PATH"))

        env_r_home = os.environ.get("R_HOME")
        if env_r_home:
            candidates.extend(self._rscript_candidates_from_home(Path(env_r_home), "env:R_HOME"))

        # Linux/macOS: prioridade para candidatos Unix antes das buscas Windows
        if sys.platform != "win32":
            candidates.extend(self._unix_candidates())

        # Windows: registro e locais padrão
        candidates.extend(self._registry_candidates())
        candidates.extend(self._root_candidates(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "R", "programfiles"))
        candidates.extend(self._root_candidates(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "R", "programfilesx86"))

        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            candidates.extend(self._root_candidates(Path(local_appdata) / "Programs" / "R", "localappdata_programs"))
            candidates.extend(self._root_candidates(Path(local_appdata) / "R", "localappdata_r"))

        candidates.extend(self._root_candidates(Path(r"C:\R"), "c_root"))
        candidates.extend(self._root_candidates(Path(r"C:\tools\R"), "chocolatey"))
        # shutil.which como fallback universal (funciona em todos os SOs)
        candidates.extend(self._where_candidates())
        return candidates

    def _probe_version(self, path: Path) -> str:
        result = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            **no_console_kwargs(),
        )
        if result.returncode != 0:
            raise OSError((result.stderr or result.stdout or "").strip() or f"exit {result.returncode}")
        return (result.stdout or result.stderr or "").strip()

    def _rscript_candidates_from_home(self, home: Path, source: str) -> List[RCandidate]:
        """Retorna candidatos Rscript a partir de um R_HOME.

        No Windows usa Rscript.exe (e x64/Rscript.exe para instalações antigas).
        No Linux/macOS usa Rscript (sem extensão).
        """
        if sys.platform == "win32":
            return [
                RCandidate(home / "bin" / "Rscript.exe", source),
                RCandidate(home / "bin" / "x64" / "Rscript.exe", source),
            ]
        else:
            return [
                RCandidate(home / "bin" / "Rscript", source),
            ]

    def _registry_candidates(self) -> List[RCandidate]:
        if sys.platform != "win32":
            return []
        try:
            import winreg
        except ImportError:
            return []

        candidates: List[RCandidate] = []
        key_paths = [
            r"SOFTWARE\R-core\R",
            r"SOFTWARE\R-core\R64",
            r"SOFTWARE\WOW6432Node\R-core\R",
        ]
        for root, root_name in (
            (winreg.HKEY_LOCAL_MACHINE, "HKLM"),
            (winreg.HKEY_CURRENT_USER, "HKCU"),
        ):
            for key_path in key_paths:
                try:
                    with winreg.OpenKey(root, key_path) as key:
                        install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                except OSError:
                    continue
                if install_path:
                    candidates.extend(
                        self._rscript_candidates_from_home(
                            Path(install_path),
                            f"registry:{root_name}\\{key_path}",
                        )
                    )
        return candidates

    def _root_candidates(self, root: Path, source_prefix: str) -> List[RCandidate]:
        candidates: List[RCandidate] = []
        for dirname in glob.glob(str(root / "R-*")):
            home = Path(dirname)
            candidates.extend(self._rscript_candidates_from_home(home, f"{source_prefix}:{home.name}"))
        return candidates

    def _where_candidates(self) -> List[RCandidate]:
        """Busca Rscript via shutil.which (funciona em todos os SOs)."""
        found: List[RCandidate] = []
        # Tenta variações de nome; no Windows 'Rscript' resolve para Rscript.exe
        for name in ("Rscript", "rscript"):
            path = shutil.which(name)
            if path:
                found.append(RCandidate(Path(path), f"path:which:{name}"))
                break  # Evita duplicatas
        return found

    def _unix_candidates(self) -> List[RCandidate]:
        """Descobre Rscript em instalações típicas do Linux e macOS.

        Chamado apenas em sistemas não-Windows. Complementa _where_candidates()
        cobrindo instalações R que não estejam no PATH.
        """
        candidates: List[RCandidate] = []

        # Locais padrão de instalação no Linux (apt/deb, dnf/rpm, pacman, brew)
        unix_r_homes = [
            Path("/usr/lib/R"),           # Debian/Ubuntu (r-base)
            Path("/usr/lib64/R"),          # Fedora/RHEL (r-base)
            Path("/usr/local/lib/R"),      # Compilado do fonte
            Path("/usr/local/lib64/R"),    # Compilado 64-bit
            Path("/opt/R"),                # rig (R Installation Manager)
            Path("/opt/local/lib/R"),      # MacPorts no macOS
        ]

        # Locais por usuário
        xdg_data = (os.environ.get("XDG_DATA_HOME") or "").strip()
        if xdg_data:
            unix_r_homes.append(Path(xdg_data) / "R")
        unix_r_homes.append(Path.home() / ".local" / "lib" / "R")
        unix_r_homes.append(Path.home() / ".local" / "share" / "rig" / "R")

        for home in unix_r_homes:
            rscript = home / "bin" / "Rscript"
            if rscript.exists():
                candidates.append(RCandidate(rscript, f"unix_home:{home}"))

        # rig: versões múltiplas em /opt/R/R-x.y.z/
        opt_r = Path("/opt/R")
        if opt_r.is_dir():
            for version_dir in sorted(opt_r.iterdir(), reverse=True):
                rscript = version_dir / "bin" / "Rscript"
                if rscript.exists():
                    candidates.append(RCandidate(rscript, f"rig:{version_dir.name}"))

        # macOS: R.app instala em /Library/Frameworks/R.framework
        if sys.platform == "darwin":
            for fw_path in (
                Path("/Library/Frameworks/R.framework/Versions/Current/Resources"),
                Path("/usr/local/Cellar"),  # Homebrew prefix
            ):
                rscript = fw_path / "bin" / "Rscript"
                if rscript.exists():
                    candidates.append(RCandidate(rscript, f"darwin:{fw_path}"))

        return candidates

    def _unique_candidates(self, candidates: Iterable[RCandidate]) -> List[RCandidate]:
        seen = set()
        unique: List[RCandidate] = []
        for candidate in candidates:
            key = str(candidate.path).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique

    def _diag_entry(self, info: RRuntimeInfo) -> Dict[str, str]:
        return {
            "rscript_path": str(info.rscript_path),
            "source": info.source,
            "version": info.version_text,
            "version_token": info.version_token,
        }

    def _reject_entry(self, candidate: RCandidate, reason: str) -> Dict[str, str]:
        return {
            "rscript_path": str(candidate.path),
            "source": candidate.source,
            "reason": reason,
        }
