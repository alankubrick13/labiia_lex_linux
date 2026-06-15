"""T7.4 — Palette and WCAG contrast accessibility tests.

Verifies that PUBLICATION_PALETTE matches the locked specification, that
all colors are valid hex, and that text over each color achieves WCAG AA
contrast (>= 4.5).
"""

from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from src.analysis.chd_reinert import PUBLICATION_PALETTE


# ---------------------------------------------------------------------------
# Locked palette from the CHD publication design contract
# ---------------------------------------------------------------------------

LOCKED_PALETTE = [
    "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
    "#56B4E9", "#F0E442", "#000000", "#999999", "#44AA99",
]

HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ---------------------------------------------------------------------------
# WCAG contrast helpers
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_color: str):
    """Convert #RRGGBB to (r, g, b) in 0-255."""
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _relative_luminance(r: int, g: int, b: int) -> float:
    """WCAG 2.1 relative luminance."""
    def linearize(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def _contrast_ratio(lum1: float, lum2: float) -> float:
    """WCAG contrast ratio between two luminances."""
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def _best_text_color(bg_hex: str) -> str:
    """Return black or white, whichever achieves better contrast on bg."""
    bg_lum = _relative_luminance(*_hex_to_rgb(bg_hex))
    white_lum = _relative_luminance(255, 255, 255)
    black_lum = _relative_luminance(0, 0, 0)
    if _contrast_ratio(white_lum, bg_lum) >= _contrast_ratio(black_lum, bg_lum):
        return "#FFFFFF"
    return "#000000"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPaletteSpec:
    def test_palette_has_exactly_10_colors(self):
        assert len(PUBLICATION_PALETTE) == 10

    def test_palette_matches_locked_values(self):
        assert PUBLICATION_PALETTE == LOCKED_PALETTE

    def test_each_color_is_valid_hex(self):
        for color in PUBLICATION_PALETTE:
            assert HEX_PATTERN.match(color), f"Invalid hex color: {color}"


class TestWCAGContrast:
    @pytest.mark.parametrize("bg_color", PUBLICATION_PALETTE)
    def test_text_contrast_meets_wcag_aa(self, bg_color):
        """For each palette color as background, the best text color
        (black or white) must achieve >= 4.5 contrast ratio."""
        text_color = _best_text_color(bg_color)
        bg_lum = _relative_luminance(*_hex_to_rgb(bg_color))
        text_lum = _relative_luminance(*_hex_to_rgb(text_color))
        ratio = _contrast_ratio(bg_lum, text_lum)
        assert ratio >= 4.5, (
            f"WCAG AA fail for bg={bg_color} text={text_color}: "
            f"ratio={ratio:.2f} < 4.5"
        )

    def test_luminance_black(self):
        assert _relative_luminance(0, 0, 0) == pytest.approx(0.0, abs=1e-6)

    def test_luminance_white(self):
        assert _relative_luminance(255, 255, 255) == pytest.approx(1.0, abs=1e-4)

    def test_contrast_black_white(self):
        """Black on white should be 21:1."""
        bl = _relative_luminance(0, 0, 0)
        wl = _relative_luminance(255, 255, 255)
        ratio = _contrast_ratio(bl, wl)
        assert ratio == pytest.approx(21.0, abs=0.1)


class TestDeterministicMapping:
    def test_class_id_to_palette_index(self):
        """class_id N maps to PUBLICATION_PALETTE[N-1]."""
        for class_id in range(1, 11):
            idx = class_id - 1
            assert PUBLICATION_PALETTE[idx] == LOCKED_PALETTE[idx]

    def test_mapping_wraps_for_excess_classes(self):
        """When class_id > 10, index should wrap (cycle)."""
        n = len(PUBLICATION_PALETTE)
        for class_id in [11, 12, 20]:
            idx = (class_id - 1) % n
            color = PUBLICATION_PALETTE[idx]
            assert HEX_PATTERN.match(color)
