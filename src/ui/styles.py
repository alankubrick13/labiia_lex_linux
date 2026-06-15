"""
Estilos visuais para a interface do aplicativo.
Baseado no Windows 11 Fluent Design System + DWM API para barra de titulo nativa.
"""
from typing import Any, Dict

import customtkinter as ctk
from .design_tokens import DesignTokenRegistry

# Tema padrao
APPEARANCE_MODE = "light"   # "dark", "light" ou "system"
COLOR_THEME = "blue"

_TOKEN_REGISTRY = DesignTokenRegistry()

# Escalas semanticas (passo base 4px) para novas implementacoes.
SPACE_SCALE: Dict[str, int] = dict(_TOKEN_REGISTRY.space)
RADIUS_SCALE: Dict[str, int] = dict(_TOKEN_REGISTRY.radius)
OPACITY_SCALE: Dict[str, float] = dict(_TOKEN_REGISTRY.opacity)

# Dicionarios legacy permanecem mutaveis e estaveis em memoria.
COLORS: Dict[str, str] = {}
DARK_COLORS: Dict[str, str] = {}
FONTS: Dict[str, tuple] = {}
SIZES: Dict[str, int] = {}


def _sync_legacy_maps_from_tokens() -> None:
    """Sincroniza mapas legacy sem quebrar referencias existentes."""
    COLORS.clear()
    COLORS.update(_TOKEN_REGISTRY.build_legacy_colors("light"))

    DARK_COLORS.clear()
    DARK_COLORS.update(_TOKEN_REGISTRY.build_legacy_colors("dark"))

    FONTS.clear()
    FONTS.update(_TOKEN_REGISTRY.build_legacy_fonts())

    SIZES.clear()
    SIZES.update(dict(_TOKEN_REGISTRY.legacy_sizes))


_sync_legacy_maps_from_tokens()


# ---------------------------------------------------------------------------
# DWM API — barra de título nativa do Windows que muda com o tema
# ---------------------------------------------------------------------------

def _apply_dwm_titlebar(hwnd: int, dark: bool) -> None:
    """
    Usa a API DWM do Windows para:
    - Ativar/desativar dark mode na barra de título (DWMWA_USE_IMMERSIVE_DARK_MODE=20)
    - Definir a cor de fundo da barra de título (DWMWA_CAPTION_COLOR=35)
    para que combine perfeitamente com o fundo do aplicativo.
    """
    try:
        import ctypes
        dwmapi = ctypes.windll.dwmapi

        # 1. Dark mode na barra de título
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value)
        )

        # 2. Cor da barra de título = cor de fundo do app (efeito Mica integrado)
        DWMWA_CAPTION_COLOR = 35
        # Cor: dark=#202020  light=#F3F3F3  — em formato COLORREF 0x00BBGGRR
        if dark:
            r, g, b = 0x20, 0x20, 0x20   # #202020
        else:
            r, g, b = 0xF3, 0xF3, 0xF3   # #F3F3F3
        colorref = ctypes.c_int(b << 16 | g << 8 | r)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR,
            ctypes.byref(colorref), ctypes.sizeof(colorref)
        )

        # 3. Cor do texto do título (DWMWA_TEXT_COLOR = 36)
        #    Branco no dark, quase preto no light
        DWMWA_TEXT_COLOR = 36
        if dark:
            tr, tg, tb = 0xFF, 0xFF, 0xFF
        else:
            tr, tg, tb = 0x1A, 0x1A, 0x1A
        text_colorref = ctypes.c_int(tb << 16 | tg << 8 | tr)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_TEXT_COLOR,
            ctypes.byref(text_colorref), ctypes.sizeof(text_colorref)
        )

        # 4. Bordas da janela arredondadas (DWMWA_WINDOW_CORNER_PREFERENCE = 33)
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = ctypes.c_int(2)   # 2 = DWMWCP_ROUND (Windows 11)
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(DWMWCP_ROUND), ctypes.sizeof(DWMWCP_ROUND)
        )

    except Exception:
        pass  # Não suportado em versões mais antigas do Windows — falha silenciosa


def apply_dwm_to_widget(widget) -> None:
    """
    Aplica estilo DWM à janela que contém o widget.
    Chame após o widget ter um HWND (após .update_idletasks() ou .winfo_id()).
    """
    try:
        dark = ctk.get_appearance_mode().lower() == "dark"
        hwnd = widget.winfo_id()
        _apply_dwm_titlebar(hwnd, dark)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Overrides internos do CustomTkinter para parecer com Windows
# ---------------------------------------------------------------------------

def _set_theme_values(widget: str, values: Dict[str, Any]) -> None:
    """Atualiza chaves do tema do widget se ele existir no CTk ThemeManager."""
    section = ctk.ThemeManager.theme.get(widget)
    if not isinstance(section, dict):
        return
    section.update(values)


def _apply_windows_overrides() -> None:
    """Ajusta tema do CustomTkinter para visual Windows 11 nativo."""
    L = COLORS
    D = DARK_COLORS

    # Janela principal
    _set_theme_values("CTk", {
        "fg_color": [L["background"], D["background"]],
    })
    _set_theme_values("CTkToplevel", {
        "fg_color": [L["background"], D["background"]],
    })

    # Frame (painel) — sem arredondamento excessivo
    _set_theme_values("CTkFrame", {
        "corner_radius": 4,
        "border_width": 0,
        "fg_color":      [L["surface"],  D["surface"]],
        "top_fg_color":  [L["surface"],  D["surface"]],
        "border_color":  [L["border"],   D["border"]],
    })

    # Labels
    _set_theme_values("CTkLabel", {
        "text_color": [L["text"], D["text"]],
        "fg_color": "transparent",
    })

    # Botões — estilo Windows: fundo claro, borda sutil, texto escuro
    _set_theme_values("CTkButton", {
        "corner_radius":         3,
        "border_width":          1,
        "fg_color":              [L["button"],       D["button"]],
        "hover_color":           [L["button_hover"], D["button_hover"]],
        "border_color":          [L["border_strong"], D["border_strong"]],
        "text_color":            [L["text"],         D["text"]],
        "text_color_disabled":   [L["text_secondary"], D["text_secondary"]],
    })

    # Entrada de texto — branco puro, borda azul ao focar (handled by CTk)
    _set_theme_values("CTkEntry", {
        "corner_radius":          3,
        "border_width":           1,
        "fg_color":               ["#FFFFFF", "#2B2B2B"],
        "border_color":           [L["border"], D["border"]],
        "text_color":             [L["text"],   D["text"]],
        "placeholder_text_color": [L["text_secondary"], D["text_secondary"]],
    })

    # Caixa de texto multilinha
    _set_theme_values("CTkTextbox", {
        "corner_radius":               3,
        "border_width":                1,
        "fg_color":                    ["#FFFFFF", "#2B2B2B"],
        "border_color":                [L["border"], D["border"]],
        "text_color":                  [L["text"],   D["text"]],
        "scrollbar_button_color":      ["#C8C8C8", "#505050"],
        "scrollbar_button_hover_color":["#ABABAB", "#636363"],
    })

    # OptionMenu / ComboBox — estilo combobox Windows
    _set_theme_values("CTkOptionMenu", {
        "corner_radius":         3,
        "fg_color":              ["#FFFFFF",          "#2B2B2B"],
        "button_color":          [L["border"],        D["border_strong"]],
        "button_hover_color":    [L["button_hover"],  D["button_hover"]],
        "text_color":            [L["text"],          D["text"]],
        "text_color_disabled":   [L["text_secondary"], D["text_secondary"]],
    })
    _set_theme_values("CTkComboBox", {
        "corner_radius":         3,
        "border_width":          1,
        "fg_color":              ["#FFFFFF",          "#2B2B2B"],
        "border_color":          [L["border"],        D["border"]],
        "button_color":          [L["border"],        D["border_strong"]],
        "button_hover_color":    [L["button_hover"],  D["button_hover"]],
        "text_color":            [L["text"],          D["text"]],
        "text_color_disabled":   [L["text_secondary"], D["text_secondary"]],
    })

    # Barra de progresso — Windows usa azul fino, sem borda
    _set_theme_values("CTkProgressBar", {
        "corner_radius":  2,
        "border_width":   0,
        "fg_color":       ["#E5E5E5",  "#3A3A3A"],
        "progress_color": [L["primary"], D["primary"]],
        "border_color":   [L["border"], D["border"]],
    })

    # Scrollbar — fina e discreta como no Windows 11
    _set_theme_values("CTkScrollbar", {
        "corner_radius":     2,
        "border_spacing":    2,
        "fg_color":          "transparent",
        "button_color":      ["#C4C4C4", "#505050"],
        "button_hover_color":["#9E9E9E", "#686868"],
    })

    # Checkbox — quadrado, sem radius (Windows style)
    _set_theme_values("CTkCheckBox", {
        "corner_radius":         0,
        "border_width":          1,
        "fg_color":              [L["primary"],     D["primary"]],
        "border_color":          [L["border_strong"], D["border_strong"]],
        "hover_color":           [L["menu_hover"],  D["menu_hover"]],
        "checkmark_color":       ["#FFFFFF",        "#FFFFFF"],
        "text_color":            [L["text"],        D["text"]],
        "text_color_disabled":   [L["text_secondary"], D["text_secondary"]],
    })

    # RadioButton — círculo Windows
    _set_theme_values("CTkRadioButton", {
        "border_width_checked":   5,
        "border_width_unchecked": 2,
        "fg_color":        [L["primary"],       D["primary"]],
        "border_color":    [L["border_strong"], D["border_strong"]],
        "hover_color":     [L["menu_hover"],    D["menu_hover"]],
        "text_color":      [L["text"],          D["text"]],
        "text_color_disabled": [L["text_secondary"], D["text_secondary"]],
    })

    # Slider — estilo Windows (barra fina, thumb redondo)
    _set_theme_values("CTkSlider", {
        "corner_radius":        0,
        "button_corner_radius": 10,
        "border_width":         4,
        "button_length":        0,
        "fg_color":             ["#D0D0D0",   "#444444"],
        "progress_color":       [L["primary"], D["primary"]],
        "button_color":         [L["primary"], D["primary"]],
        "button_hover_color":   ["#004EA6",   "#3BC5FF"],
    })

    # Switch — Windows toggle switch
    _set_theme_values("CTkSwitch", {
        "border_width":   3,
        "button_length":  0,
        "fg_color":       ["#C0C0C0",   "#4A4A4A"],
        "progress_color": [L["primary"], D["primary"]],
        "button_color":   ["#FFFFFF",   "#E8E8E8"],
        "button_hover_color": ["#F0F0F0", "#F5F5F5"],
        "text_color":         [L["text"], D["text"]],
        "text_color_disabled":[L["text_secondary"], D["text_secondary"]],
    })

    # SegmentedButton
    _set_theme_values("CTkSegmentedButton", {
        "corner_radius":          3,
        "border_width":           1,
        "fg_color":               [L["surface"],    D["surface"]],
        "selected_color":         [L["primary"],    D["primary"]],
        "selected_hover_color":   [L["primary_hover"], D["primary_hover"]],
        "unselected_color":       [L["button"],     D["button"]],
        "unselected_hover_color": [L["button_hover"], D["button_hover"]],
        "text_color":             [L["text"],       D["text"]],
        "text_color_disabled":    [L["text_secondary"], D["text_secondary"]],
    })

    # ScrollableFrame
    _set_theme_values("CTkScrollableFrame", {
        "label_fg_color": [L["surface"], D["surface"]],
    })

    # Dropdown (CTkOptionMenu popup)
    _set_theme_values("DropdownMenu", {
        "fg_color":    [L["surface"],    D["surface"]],
        "hover_color": [L["menu_hover"], D["menu_hover"]],
        "text_color":  [L["text"],       D["text"]],
    })


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def apply_theme(mode: str = None):
    """Aplica tema global.

    Args:
        mode: "dark", "light" ou "system". Se None, usa APPEARANCE_MODE padrão.
    """
    global APPEARANCE_MODE
    if mode and str(mode).lower() in ("dark", "light", "system"):
        APPEARANCE_MODE = str(mode).lower()
    _sync_legacy_maps_from_tokens()
    ctk.set_appearance_mode(APPEARANCE_MODE)
    ctk.set_default_color_theme(COLOR_THEME)
    _apply_windows_overrides()


def get_current_colors() -> Dict[str, str]:
    """Retorna a paleta de cores ativa (útil para widgets nativos tk)."""
    if ctk.get_appearance_mode().lower() == "dark":
        return dict(DARK_COLORS)
    return dict(COLORS)


def style_native_menu(menu) -> None:
    """Aplica cores dark/light a um tk.Menu nativo."""
    c = get_current_colors()
    try:
        menu.configure(
            bg=c.get("surface", "#FFFFFF"),
            fg=c.get("text", "#1A1A1A"),
            activebackground=c.get("menu_hover", "#E5F0FB"),
            activeforeground=c.get("text", "#1A1A1A"),
            selectcolor=c.get("primary", "#0067C0"),
            relief="flat",
            borderwidth=0,
        )
    except Exception:
        pass


def get_font(name: str) -> tuple:
    """Retorna tupla de fonte pelo nome."""
    return FONTS.get(name, FONTS["body"])


def get_color(name: str) -> str:
    """Retorna cor pelo nome (modo claro/padrão)."""
    return COLORS.get(name, COLORS["text"])


def get_themed_color(name: str) -> tuple:
    """Retorna tupla (cor_clara, cor_escura) para widgets CTk."""
    light = COLORS.get(name, "#FF00FF")
    dark  = DARK_COLORS.get(name, light)
    return (light, dark)


def get_token(token: str, theme: str = None) -> str:
    """Retorna valor de token semantico (ex.: color.bg.canvas)."""
    theme_name = str(theme or ctk.get_appearance_mode() or "light").lower()
    if theme_name == "system":
        # Mantem previsibilidade, pois modo do OS pode variar por runtime.
        theme_name = APPEARANCE_MODE if APPEARANCE_MODE != "system" else "light"
    return _TOKEN_REGISTRY.get_color(token, theme=theme_name)
