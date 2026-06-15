"""Helpers para limpeza segura de recursos Tk/CustomTkinter."""

from __future__ import annotations

from typing import Any
import tkinter as tk


def destroy_menu_safe(menu: Any) -> None:
    """Destroi um menu Tk sem propagar excecoes de runtime."""
    if menu is None:
        return
    try:
        menu.unpost()
    except Exception:
        pass
    try:
        menu.destroy()
    except Exception:
        pass


def cleanup_widget_menus(widget: Any) -> None:
    """
    Limpa menus associados a widgets (inclui dropdowns de CTkOptionMenu).

    Isso evita acumulo de objetos `menu` no Tk que pode causar:
    "No more menus can be allocated".
    """
    if widget is None:
        return

    stack = [widget]
    visited: set[int] = set()

    while stack:
        current = stack.pop()
        current_id = id(current)
        if current_id in visited:
            continue
        visited.add(current_id)

        dropdown_menu = getattr(current, "_dropdown_menu", None)
        if dropdown_menu is not None:
            destroy_menu_safe(dropdown_menu)
            try:
                setattr(current, "_dropdown_menu", None)
            except Exception:
                pass

        context_menu = getattr(current, "_context_menu", None)
        if context_menu is not None:
            destroy_menu_safe(context_menu)
            try:
                setattr(current, "_context_menu", None)
            except Exception:
                pass

        try:
            children = current.winfo_children()
        except Exception:
            children = []
        for child in children:
            stack.append(child)


def patch_customtkinter_entry_callback() -> None:
    """
    Aplica patch defensivo no callback interno do CTkEntry.

    Evita excecoes do tipo:
    - expected integer but got ""
    - expected floating-point number but got ""
    quando o textvariable numerico fica temporariamente vazio.
    """
    try:
        import customtkinter as ctk
    except Exception:
        return

    entry_cls = getattr(ctk, "CTkEntry", None)
    if entry_cls is None:
        return
    if getattr(entry_cls, "_lexi_safe_textvar_patch", False):
        return

    original_callback = getattr(entry_cls, "_textvariable_callback", None)
    if original_callback is None:
        return

    def _safe_textvariable_callback(self, *args, **kwargs):
        try:
            return original_callback(self, *args, **kwargs)
        except tk.TclError as exc:
            msg = str(exc).lower()
            if "expected integer" in msg or "expected floating-point number" in msg:
                return None
            raise

    try:
        entry_cls._textvariable_callback = _safe_textvariable_callback
        entry_cls._lexi_safe_textvar_patch = True
    except Exception:
        return
