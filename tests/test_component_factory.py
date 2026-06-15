from src.ui.component_factory import style_button


class _FakeButton:
    def __init__(self):
        self.calls = []

    def configure(self, **kwargs):
        self.calls.append(kwargs)


def test_style_button_ghost_configures_once_without_conflict():
    button = _FakeButton()
    style_button(button, variant="ghost", size="md")
    assert len(button.calls) == 1
    cfg = button.calls[0]
    assert cfg["corner_radius"] == 0
    assert cfg["fg_color"] == "transparent"


def test_style_button_secondary_keeps_border_defaults():
    button = _FakeButton()
    style_button(button, variant="secondary", size="sm")
    assert len(button.calls) == 1
    cfg = button.calls[0]
    assert cfg["border_width"] == 1
    assert "border_color" in cfg
