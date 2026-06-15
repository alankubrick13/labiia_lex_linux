"""Helpers para execução de subprocessos no Windows sem janela de console."""

from __future__ import annotations

import os
import subprocess
from typing import Any, Dict


def no_console_kwargs() -> Dict[str, Any]:
    """
    Retorna kwargs para ocultar janela de console em subprocessos no Windows.

    Em outros sistemas retorna dict vazio.
    """
    if os.name != "nt":
        return {}

    kwargs: Dict[str, Any] = {}

    create_no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0)
    if create_no_window:
        kwargs["creationflags"] = create_no_window

    startup_cls = getattr(subprocess, "STARTUPINFO", None)
    if startup_cls is not None:
        startup = startup_cls()
        startup.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0) or 0)
        startup.wShowWindow = 0
        kwargs["startupinfo"] = startup

    return kwargs

