"""
Design tokens centrais da UI.

Mantem contrato semantico para temas e fornece adaptacao retrocompativel
para mapas legacy (COLORS/FONTS/SIZES) usados no codigo atual.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Mapping


ThemeName = str


@dataclass(frozen=True)
class ThemeTokenSet:
    """Conjunto de tokens de um tema."""

    colors: Mapping[str, str]


class DesignTokenRegistry:
    """Registro de tokens semanticos para UI."""

    def __init__(self) -> None:
        self._themes: Dict[ThemeName, ThemeTokenSet] = {
            "light": ThemeTokenSet(
                colors={
                    "color.bg.canvas": "#EAF0F8",
                    "color.bg.surface": "#FFFFFF",
                    "color.bg.subtle": "#F5F8FD",
                    "color.bg.rail": "#102A5C",
                    "color.bg.rail.subtle": "#17366F",
                    "color.bg.card": "#FFFFFF",
                    "color.bg.sheet": "#F7FAFF",
                    "color.fg.primary": "#17304F",
                    "color.fg.secondary": "#63748A",
                    "color.fg.disabled": "#9E9E9E",
                    "color.fg.inverse": "#F9FBFF",
                    "color.border.default": "#D9E4F2",
                    "color.border.strong": "#B7C8DE",
                    "color.border.light": "#EDF3FA",
                    "color.brand.accent": "#2D7FF9",
                    "color.brand.accent.hover": "#1D68D8",
                    "color.control.button.bg": "#FFFFFF",
                    "color.control.button.hover": "#F1F6FE",
                    "color.control.button.pressed": "#E2ECFA",
                    "color.control.menu.hover": "#E8F0FB",
                    "color.control.selection.active": "#D7E8FF",
                    "color.control.selection.inactive": "#E8EEF7",
                    "color.state.success": "#1FA968",
                    "color.state.warning": "#9D5C00",
                    "color.state.danger": "#C50F1F",
                    "color.state.info": "#2D7FF9",
                    "color.focus.ring": "#2D7FF9",
                }
            ),
            "dark": ThemeTokenSet(
                colors={
                    "color.bg.canvas": "#111A2B",
                    "color.bg.surface": "#19243A",
                    "color.bg.subtle": "#22304A",
                    "color.bg.rail": "#0B1322",
                    "color.bg.rail.subtle": "#15233A",
                    "color.bg.card": "#1A273C",
                    "color.bg.sheet": "#152033",
                    "color.fg.primary": "#F3F7FF",
                    "color.fg.secondary": "#B4C3D9",
                    "color.fg.disabled": "#808080",
                    "color.fg.inverse": "#F3F7FF",
                    "color.border.default": "#2A3C5A",
                    "color.border.strong": "#35507B",
                    "color.border.light": "#22314C",
                    "color.brand.accent": "#6BA9FF",
                    "color.brand.accent.hover": "#4E90F2",
                    "color.control.button.bg": "#22304A",
                    "color.control.button.hover": "#2D3E5E",
                    "color.control.button.pressed": "#39517A",
                    "color.control.menu.hover": "#444444",
                    "color.control.selection.active": "#294674",
                    "color.control.selection.inactive": "#22304A",
                    "color.state.success": "#72CE72",
                    "color.state.warning": "#FCE100",
                    "color.state.danger": "#FF6B6B",
                    "color.state.info": "#6BA9FF",
                    "color.focus.ring": "#6BA9FF",
                }
            ),
            "high_contrast": ThemeTokenSet(
                colors={
                    "color.bg.canvas": "#000000",
                    "color.bg.surface": "#000000",
                    "color.bg.subtle": "#000000",
                    "color.fg.primary": "#FFFFFF",
                    "color.fg.secondary": "#FFFFFF",
                    "color.fg.disabled": "#BDBDBD",
                    "color.border.default": "#FFFFFF",
                    "color.border.strong": "#FFFFFF",
                    "color.border.light": "#FFFFFF",
                    "color.brand.accent": "#00A2FF",
                    "color.brand.accent.hover": "#33B4FF",
                    "color.control.button.bg": "#000000",
                    "color.control.button.hover": "#1A1A1A",
                    "color.control.button.pressed": "#303030",
                    "color.control.menu.hover": "#1A1A1A",
                    "color.control.selection.active": "#0F4A7A",
                    "color.control.selection.inactive": "#1A1A1A",
                    "color.state.success": "#73FF73",
                    "color.state.warning": "#FFD54D",
                    "color.state.danger": "#FF8A8A",
                    "color.state.info": "#66CFFF",
                    "color.focus.ring": "#00A2FF",
                }
            ),
        }

        self.typography: Dict[str, tuple] = {
            "display": ("Segoe UI Variable", 30, "bold"),
            "h1": ("Segoe UI Variable", 23, "bold"),
            "h2": ("Segoe UI Variable", 18, "bold"),
            "body": ("Segoe UI", 13),
            "small": ("Segoe UI", 11),
            "caption": ("Segoe UI", 9),
            "menu": ("Segoe UI", 11),
            "button": ("Segoe UI Semibold", 12),
            "toolbar": ("Segoe UI", 13),
            "mono": ("Consolas", 11),
        }

        self.space: Dict[str, int] = {
            "space.1": 4,
            "space.2": 8,
            "space.3": 12,
            "space.4": 16,
            "space.5": 20,
            "space.6": 24,
            "space.7": 28,
            "space.8": 32,
        }

        self.radius: Dict[str, int] = {
            "radius.sm": 10,
            "radius.md": 14,
            "radius.lg": 18,
        }

        self.opacity: Dict[str, float] = {
            "opacity.disabled": 0.40,
        }

        # Mantem contratos antigos para compatibilidade progressiva.
        self.legacy_sizes: Dict[str, int] = {
            "button_width": 80,
            "button_height": 28,
            "button_small": 20,
            "input_width": 260,
            "input_height": 34,
            "dialog_width": 460,
            "dialog_height": 340,
            "sidebar_width": 280,
            "statusbar_height": 20,
            "toolbar_height": 32,
            "toolbar_icon": 18,
            "corner_radius": 12,
            "border_width": 1,
            "spacing_small": 4,
            "spacing_medium": 8,
            "spacing_large": 14,
            "control_height_sm": 32,
            "control_height_md": 38,
            "control_height_lg": 44,
            "table_row_compact": 28,
            "table_row_comfortable": 36,
        }

    def get_theme(self, theme: ThemeName) -> ThemeTokenSet:
        return self._themes.get(str(theme or "light").lower(), self._themes["light"])

    def get_color(self, token: str, theme: ThemeName = "light") -> str:
        colors = self.get_theme(theme).colors
        return str(colors.get(token, ""))

    def build_legacy_colors(self, theme: ThemeName = "light") -> Dict[str, str]:
        colors = self.get_theme(theme).colors
        return {
            "primary": colors["color.brand.accent"],
            "primary_hover": colors["color.brand.accent.hover"],
            "background": colors["color.bg.canvas"],
            "surface": colors["color.bg.surface"],
            "sidebar_bg": colors["color.bg.subtle"],
            "header_bg": colors["color.bg.subtle"],
            "rail_bg": colors.get("color.bg.rail", colors["color.bg.subtle"]),
            "rail_bg_subtle": colors.get("color.bg.rail.subtle", colors["color.bg.subtle"]),
            "card": colors.get("color.bg.card", colors["color.bg.surface"]),
            "sheet": colors.get("color.bg.sheet", colors["color.bg.surface"]),
            "text": colors["color.fg.primary"],
            "text_secondary": colors["color.fg.secondary"],
            "text_disabled": colors["color.fg.disabled"],
            "text_inverse": colors.get("color.fg.inverse", colors["color.fg.primary"]),
            "border": colors["color.border.default"],
            "border_strong": colors["color.border.strong"],
            "border_light": colors["color.border.light"],
            "button": colors["color.control.button.bg"],
            "button_hover": colors["color.control.button.hover"],
            "button_pressed": colors["color.control.button.pressed"],
            "success": colors["color.state.success"],
            "warning": colors["color.state.warning"],
            "danger": colors["color.state.danger"],
            "info": colors["color.state.info"],
            "menu_hover": colors["color.control.menu.hover"],
            "selection": colors["color.control.selection.active"],
            "selection_inactive": colors["color.control.selection.inactive"],
            "accent": colors["color.brand.accent"],
            "secondary": colors["color.control.selection.inactive"],
            "focus_ring": colors["color.focus.ring"],
        }

    def build_legacy_fonts(self) -> Dict[str, tuple]:
        return {
            "title": ("Segoe UI", 14, "bold"),
            "heading": ("Segoe UI", 12, "bold"),
            "body": self.typography["body"],
            "small": self.typography["small"],
            "caption": self.typography["caption"],
            "mono": self.typography["mono"],
            "toolbar": self.typography["toolbar"],
            "menu": self.typography["menu"],
            "button": self.typography["button"],
            "display": self.typography["display"],
            "h1": self.typography["h1"],
            "h2": self.typography["h2"],
        }
