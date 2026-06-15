from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_display_brand_constants_match_plan() -> None:
    from src.core.version import (
        APP_NAME,
        DISPLAY_APP_NAME,
        DISPLAY_APP_NAME_SAFE,
        DISPLAY_APP_TITLE,
    )

    assert APP_NAME == "LabiiaLex"
    assert DISPLAY_APP_NAME == "<labiia_lex>"
    assert DISPLAY_APP_NAME_SAFE == "labiia_lex"
    assert DISPLAY_APP_TITLE == "<labiia_lex> Software de Análise Textual"


def test_main_window_uses_display_branding_in_visible_shell() -> None:
    source = (PROJECT_ROOT / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")

    assert "DISPLAY_APP_NAME" in source
    assert "DISPLAY_APP_TITLE" in source
    assert 'self.title(DISPLAY_APP_TITLE)' in source


def test_general_help_and_installer_expose_new_public_branding() -> None:
    help_text = (PROJECT_ROOT / "docs" / "help" / "geral.html").read_text(encoding="utf-8")
    installer_text = (PROJECT_ROOT / "installer" / "inno" / "LabiiaLex.iss").read_text(
        encoding="utf-8"
    )

    assert "&lt;labiia_lex&gt;" in help_text
    assert "AppName=<labiia_lex>" in installer_text
    assert "DefaultGroupName=labiia_lex" in installer_text
    assert 'Name: "{autodesktop}\\labiia_lex"; Filename: "{app}\\LabiiaLex.exe"' in installer_text


def test_about_popup_text_and_installer_license_share_current_message_contract() -> None:
    main_window_text = (PROJECT_ROOT / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")
    installer_license = (PROJECT_ROOT / "license.txt").read_text(encoding="utf-8")

    expected_fragments = (
        "coordenador do <labiia_lab> (Laboratório Interdisciplinar de Inteligência Artificial para Métodos, Democracia e Sociedade).",
        "Claude Code Opus (v. 4.5, 4.6, 4.7, 4.8)",
        "Kimi (2.5 e 2.6)",
        "10) Também aproveitamos o Tall",
        "O desenvolvimento também contou com a ajuda de colaboradores do <labiia_lab>.",
        "seis meses de assinatura dos agentes de IA",
    )

    for fragment in expected_fragments:
        assert fragment in main_window_text
        assert fragment in installer_license
