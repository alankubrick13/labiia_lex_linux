"""Version and display branding helpers."""

from __future__ import annotations

from pathlib import Path
import sys

APP_NAME = "LabiiaLex"
DISPLAY_APP_NAME = "<labiia_lex>"
DISPLAY_APP_NAME_SAFE = "labiia_lex"
DISPLAY_APP_TITLE = "<labiia_lex> Software de Análise Textual"
FALLBACK_VERSION = "1.0.9"


def _candidate_roots() -> list[Path]:
    here = Path(__file__).resolve()
    roots: list[Path] = [here.parents[2]]
    if len(here.parents) > 3:
        roots.append(here.parents[3])

    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            roots.append(Path(meipass))
        roots.append(Path(sys.executable).resolve().parent)

    roots.append(Path.cwd())

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _read_version_file() -> str:
    for root in _candidate_roots():
        version_file = root / "VERSION"
        if not version_file.exists():
            continue
        try:
            value = version_file.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value
    return FALLBACK_VERSION


APP_VERSION = _read_version_file()
