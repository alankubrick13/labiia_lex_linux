"""Verifica splitter redimensionável da janela principal."""

from __future__ import annotations

from pathlib import Path


def test_main_window_declares_resizable_paned_layout() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "ui" / "main_window.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )
    assert "ttk.PanedWindow" in source
    assert "_sidebar_min_width = 180" in source
    assert "_results_min_width = 640" in source
    assert "_save_sidebar_width_preference" in source
    assert '"sidebar_width"' in source

