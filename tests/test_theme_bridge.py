from src.ui.theme_bridge import (
    build_treeview_style_options,
    build_treeview_heading_style_options,
    build_treeview_style_map,
)


def test_treeview_style_options_compact_density():
    colors = {"surface": "#FFFFFF", "text": "#111111"}
    fonts = {"small": ("Segoe UI", 10)}
    options = build_treeview_style_options(colors, fonts, density="compact")
    assert options["rowheight"] == 22
    assert options["background"] == "#FFFFFF"
    assert options["foreground"] == "#111111"


def test_treeview_heading_style_options_fallbacks():
    colors = {"surface": "#FAFAFA", "text": "#1F1F1F"}
    fonts = {}
    options = build_treeview_heading_style_options(colors, fonts)
    assert options["background"] == "#FAFAFA"
    assert options["foreground"] == "#1F1F1F"
    assert isinstance(options["font"], tuple)


def test_treeview_style_map_uses_selection_color():
    colors = {"selection": "#CCE4F7", "text": "#242424"}
    style_map = build_treeview_style_map(colors)
    assert "background" in style_map
    assert style_map["background"][0][1] == "#CCE4F7"
    assert style_map["foreground"][0][1] == "#242424"

