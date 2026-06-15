from src.ui.feedback import FeedbackService, MessageBoxBridge


def test_feedback_service_uses_custom_backend_for_show_and_ask():
    calls = []

    def _record(name):
        def _fn(*args, **kwargs):
            calls.append((name, args, kwargs))
            if name == "askquestion":
                return "yes"
            if name.startswith("ask"):
                return True
            return "ok"

        return _fn

    backend = {
        "showinfo": _record("showinfo"),
        "showwarning": _record("showwarning"),
        "showerror": _record("showerror"),
        "askyesno": _record("askyesno"),
        "askyesnocancel": _record("askyesnocancel"),
        "askokcancel": _record("askokcancel"),
        "askretrycancel": _record("askretrycancel"),
        "askquestion": _record("askquestion"),
    }

    service = FeedbackService()
    service.set_messagebox_backend(backend)

    assert service.showinfo("T", "M") == "ok"
    assert service.showwarning("T", "M") == "ok"
    assert service.showerror("T", "M") == "ok"
    assert service.askyesno("T", "M") is True
    assert service.askokcancel("T", "M") is True
    assert service.askretrycancel("T", "M") is True
    assert service.askquestion("T", "M") == "yes"
    assert len(calls) >= 7


def test_messagebox_bridge_install_and_uninstall():
    service = FeedbackService()
    bridge = MessageBoxBridge(service)

    bridge.install()
    assert bridge._installed is True
    assert callable(service.showinfo)

    bridge.uninstall()
    assert bridge._installed is False
