"""Windows-friendly path utilities for LabiiaLex."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Union

from ..core.version import APP_NAME as PRODUCT_NAME


class PathManager:
    """
    Centralizes project path resolution to keep Windows paths consistent.
    """

    APP_NAME = PRODUCT_NAME

    @staticmethod
    def is_frozen() -> bool:
        """Return True when running from a frozen executable bundle."""
        return bool(getattr(sys, "frozen", False))

    @staticmethod
    def project_root() -> Path:
        """
        Return the LabiiaLex project root directory.

        Returns:
            Path to the repository/project root.
        """
        if PathManager.is_frozen():
            exe_dir = Path(sys.executable).resolve().parent
            internal_dir = exe_dir / "_internal"
            if internal_dir.exists():
                return internal_dir
            return exe_dir
        return Path(__file__).resolve().parents[2]

    @staticmethod
    def user_data_dir() -> Path:
        """
        Return writable per-user data directory for LabiiaLex.

        On Windows, uses LOCALAPPDATA/LabiiaLex.
        """
        if os.name == "nt":
            base = (
                os.environ.get("LOCALAPPDATA")
                or os.environ.get("APPDATA")
                or str(Path.home() / "AppData" / "Local")
            )
        elif sys.platform == "darwin":
            base = str(Path.home() / "Library" / "Application Support")
        else:
            base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")

        target = Path(base) / PathManager.APP_NAME
        target.mkdir(parents=True, exist_ok=True)
        return target

    @staticmethod
    def src_dir() -> Path:
        """
        Return the src/ directory path.

        Returns:
            Path to src/.
        """
        return PathManager.project_root() / "src"

    @staticmethod
    def rscripts_dir() -> Path:
        """
        Return the Rscripts/ directory path.

        Returns:
            Path to Rscripts/.
        """
        return PathManager.project_root() / "Rscripts"

    @staticmethod
    def iramuteq_vendor_dir() -> Path:
        """
        Return vendored IRaMuTeQ 0.8a7 snapshot root when present.

        Returns:
            Path to vendor/iramuteq_0_8a7.
        """
        return PathManager.project_root() / "vendor" / "iramuteq_0_8a7"

    @staticmethod
    def official_rscripts_dir() -> Path:
        """
        Return the official IRaMuTeQ Rscripts snapshot if vendored.

        Falls back to project Rscripts/ so callers can opt in safely before
        the snapshot exists in every environment.
        """
        candidate = PathManager.iramuteq_vendor_dir() / "Rscripts"
        if candidate.exists():
            return candidate
        return PathManager.rscripts_dir()

    @staticmethod
    def official_configuration_dir() -> Path:
        """
        Return the official IRaMuTeQ configuration snapshot if vendored.

        Falls back to the installed IRaMuTeQ configuration folder when
        available on Windows, otherwise to the project root configuration.
        """
        vendor_candidate = PathManager.iramuteq_vendor_dir() / "configuration"
        if vendor_candidate.exists():
            return vendor_candidate

        installed_candidate = Path(r"C:\Program Files\IRaMuTeQ-0.8a7\configuration")
        if installed_candidate.exists():
            return installed_candidate

        return PathManager.project_root() / "configuration"

    @staticmethod
    def dictionaries_dir() -> Path:
        """
        Return the dictionaries/ directory path.

        Returns:
            Path to dictionaries/.
        """
        return PathManager.project_root() / "dictionaries"

    @staticmethod
    def resources_dir() -> Path:
        """
        Return the resources/ directory path.

        Returns:
            Path to resources/.
        """
        return PathManager.project_root() / "resources"

    @staticmethod
    def templates_dir() -> Path:
        """
        Return the resources/templates/ directory path.

        Returns:
            Path to resources/templates/.
        """
        return PathManager.resources_dir() / "templates"

    @staticmethod
    def tests_dir() -> Path:
        """
        Return the tests/ directory path.

        Returns:
            Path to tests/.
        """
        return PathManager.project_root() / "tests"

    @staticmethod
    def resolve(path: Union[str, Path]) -> Path:
        """
        Normalize a path to an absolute Path instance.

        Args:
            path: Path string or Path object.

        Returns:
            Absolute Path with user expansion applied.
        """
        return Path(path).expanduser().resolve()

    @staticmethod
    def ensure_dir(path: Union[str, Path]) -> Path:
        """
        Ensure a directory exists and return it as a Path.

        Args:
            path: Directory path.

        Returns:
            Path to the ensured directory.
        """
        resolved = Path(path)
        resolved.mkdir(parents=True, exist_ok=True)
        return resolved
