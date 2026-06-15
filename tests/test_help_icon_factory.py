"""Testes para a fábrica padronizada de ícones de ajuda."""

from __future__ import annotations

import pytest

try:
    import customtkinter as ctk

    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from src.ui.iconography import create_help_button, get_ui_icon, label_with_icon


def test_get_ui_icon_returns_string() -> None:
    assert isinstance(get_ui_icon("info"), str)
    assert isinstance(get_ui_icon("unknown_key"), str)


def test_label_with_icon_preserves_label_text() -> None:
    text = label_with_icon("stats", "Estatísticas")
    assert "Estatísticas" in text


@pytest.mark.skipif(not HAS_CTK, reason="CustomTkinter indisponível")
def test_create_help_button_uses_professional_info_text() -> None:
    try:
        root = ctk.CTk()
    except Exception as exc:
        pytest.skip(f"Tk indisponível no ambiente atual: {exc}")
    try:
        root.withdraw()
        button = create_help_button(root, "Ajuda de teste")
        assert button is not None
        assert button.cget("text") == ""
        assert button.cget("image") not in (None, "", "none")
    finally:
        try:
            root.destroy()
        except Exception:
            pass
