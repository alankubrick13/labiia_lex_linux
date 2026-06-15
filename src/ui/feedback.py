"""
Canal de feedback UI padronizado.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
import logging
from tkinter import messagebox as tk_messagebox


StatusCallback = Callable[[str, float], None]


@dataclass
class FeedbackService:
    """
    Centraliza comunicacao de status e dialogs de mensagem.

    Mantem comportamento atual (messagebox) com API unica.
    """

    status_callback: Optional[StatusCallback] = None
    logger: Optional[logging.Logger] = None
    _messagebox_backend: Optional[Dict[str, Callable[..., Any]]] = None

    def __post_init__(self) -> None:
        if self._messagebox_backend is None:
            self._messagebox_backend = self._capture_default_backend()

    @staticmethod
    def _capture_default_backend() -> Dict[str, Callable[..., Any]]:
        names = (
            "showinfo",
            "showwarning",
            "showerror",
            "askyesno",
            "askyesnocancel",
            "askokcancel",
            "askretrycancel",
            "askquestion",
        )
        backend: Dict[str, Callable[..., Any]] = {}
        for name in names:
            fn = getattr(tk_messagebox, name, None)
            if callable(fn):
                backend[name] = fn
        return backend

    def set_messagebox_backend(self, backend: Dict[str, Callable[..., Any]]) -> None:
        self._messagebox_backend = dict(backend or {})

    def reset_messagebox_backend(self) -> None:
        self._messagebox_backend = self._capture_default_backend()

    def _call_backend(self, method: str, *args, **kwargs) -> Any:
        fn = None
        if isinstance(self._messagebox_backend, dict):
            fn = self._messagebox_backend.get(method)
        if not callable(fn):
            fn = getattr(tk_messagebox, method, None)
        if not callable(fn):
            raise AttributeError(f"messagebox backend '{method}' indisponível")
        return fn(*args, **kwargs)

    @staticmethod
    def _extract_message(args: tuple, kwargs: Dict[str, Any]) -> str:
        if len(args) >= 2 and args[1] is not None:
            return str(args[1])
        if "message" in kwargs and kwargs["message"] is not None:
            return str(kwargs["message"])
        return ""

    def status(self, message: str, progress: float = 0.0) -> None:
        if self.status_callback:
            self.status_callback(str(message), float(progress))

    def info(self, title: str, message: str, *, progress: Optional[float] = None) -> None:
        if progress is not None:
            self.status(message, progress)
        self.showinfo(title, message)

    def warning(self, title: str, message: str, *, progress: Optional[float] = None) -> None:
        if progress is not None:
            self.status(message, progress)
        self.showwarning(title, message)

    def error(self, title: str, message: str, *, progress: Optional[float] = None) -> None:
        if progress is not None:
            self.status(message, progress)
        self.showerror(title, message)

    # --- API compatível com tkinter.messagebox ---
    def showinfo(self, *args, **kwargs) -> Any:
        self.status(self._extract_message(args, kwargs), 0.0)
        return self._call_backend("showinfo", *args, **kwargs)

    def showwarning(self, *args, **kwargs) -> Any:
        self.status(self._extract_message(args, kwargs), 0.0)
        return self._call_backend("showwarning", *args, **kwargs)

    def showerror(self, *args, **kwargs) -> Any:
        self.status(self._extract_message(args, kwargs), 0.0)
        return self._call_backend("showerror", *args, **kwargs)

    def askyesno(self, *args, **kwargs) -> bool:
        self.status(self._extract_message(args, kwargs), 0.0)
        return bool(self._call_backend("askyesno", *args, **kwargs))

    def askyesnocancel(self, *args, **kwargs) -> Optional[bool]:
        self.status(self._extract_message(args, kwargs), 0.0)
        return self._call_backend("askyesnocancel", *args, **kwargs)

    def askokcancel(self, *args, **kwargs) -> bool:
        self.status(self._extract_message(args, kwargs), 0.0)
        return bool(self._call_backend("askokcancel", *args, **kwargs))

    def askretrycancel(self, *args, **kwargs) -> bool:
        self.status(self._extract_message(args, kwargs), 0.0)
        return bool(self._call_backend("askretrycancel", *args, **kwargs))

    def askquestion(self, *args, **kwargs) -> str:
        self.status(self._extract_message(args, kwargs), 0.0)
        return str(self._call_backend("askquestion", *args, **kwargs))

    def exception(
        self,
        title: str,
        exc: Exception,
        *,
        user_message: Optional[str] = None,
        progress: Optional[float] = None,
    ) -> None:
        details = user_message or str(exc) or "Erro inesperado."
        if self.logger:
            self.logger.exception("%s: %s", title, details)
        self.error(title, details, progress=progress)


class MessageBoxBridge:
    """Patch global opcional para redirecionar tkinter.messagebox ao FeedbackService."""

    def __init__(self, feedback: FeedbackService) -> None:
        self.feedback = feedback
        self._installed = False
        self._originals: Dict[str, Callable[..., Any]] = {}

    def install(self) -> None:
        if self._installed:
            return
        names = (
            "showinfo",
            "showwarning",
            "showerror",
            "askyesno",
            "askyesnocancel",
            "askokcancel",
            "askretrycancel",
            "askquestion",
        )
        for name in names:
            fn = getattr(tk_messagebox, name, None)
            if callable(fn):
                self._originals[name] = fn
        self.feedback.set_messagebox_backend(self._originals)

        tk_messagebox.showinfo = self.feedback.showinfo
        tk_messagebox.showwarning = self.feedback.showwarning
        tk_messagebox.showerror = self.feedback.showerror
        tk_messagebox.askyesno = self.feedback.askyesno
        tk_messagebox.askyesnocancel = self.feedback.askyesnocancel
        tk_messagebox.askokcancel = self.feedback.askokcancel
        tk_messagebox.askretrycancel = self.feedback.askretrycancel
        tk_messagebox.askquestion = self.feedback.askquestion

        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        for name, fn in self._originals.items():
            setattr(tk_messagebox, name, fn)
        self.feedback.reset_messagebox_backend()
        self._installed = False
