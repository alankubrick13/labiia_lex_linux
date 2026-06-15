"""Bloqueia regressão de emojis na camada de UI."""

from __future__ import annotations

import re
from pathlib import Path


EMOJI_PATTERN = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")


def test_ui_source_has_no_emoji_characters() -> None:
    ui_dir = Path(__file__).resolve().parents[1] / "src" / "ui"
    offenders: list[str] = []
    for path in ui_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if EMOJI_PATTERN.search(text):
            offenders.append(str(path.relative_to(ui_dir.parent)))
    assert not offenders, f"Arquivos UI com emoji detectado: {offenders}"

