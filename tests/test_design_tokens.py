from src.ui.design_tokens import DesignTokenRegistry


def test_design_token_registry_supports_expected_themes():
    registry = DesignTokenRegistry()
    for theme in ("light", "dark", "high_contrast"):
        token_set = registry.get_theme(theme)
        assert token_set is not None
        assert "color.bg.canvas" in token_set.colors
        assert "color.brand.accent" in token_set.colors


def test_legacy_color_contract_is_backward_compatible():
    registry = DesignTokenRegistry()
    legacy = registry.build_legacy_colors("light")
    for key in (
        "primary",
        "background",
        "surface",
        "text",
        "border",
        "button",
        "menu_hover",
    ):
        assert key in legacy
        assert isinstance(legacy[key], str)
        assert legacy[key]


def test_legacy_sizes_keep_required_keys():
    registry = DesignTokenRegistry()
    sizes = registry.legacy_sizes
    for key in (
        "button_width",
        "button_height",
        "input_height",
        "dialog_width",
        "sidebar_width",
        "spacing_small",
        "spacing_medium",
        "spacing_large",
    ):
        assert key in sizes
        assert isinstance(sizes[key], int)
        assert sizes[key] > 0

