"""
Tutorial guiado com spotlight interno à janela principal.

O overlay não usa janela separada. Ele é composto por regiões filhas da janela
principal, o que impede vazamento para outros aplicativos e evita disputa de
foco/z-order com o gerenciador de janelas do Windows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Literal, Optional, Tuple
import tkinter as tk

import customtkinter as ctk

from ..styles import FONTS, get_current_colors, get_themed_color

Rect = Tuple[int, int, int, int]
Placement = Literal["auto", "right", "left", "bottom", "top"]


@dataclass
class TourStep:
    """Representa uma etapa do tutorial."""

    title: str
    message: str
    target_getter: Callable[[], Optional[Rect]]
    before_enter: Optional[Callable[[], None]] = None
    preferred_placement: Placement = "auto"
    anchor_padding: int = 8
    fallback_rect: Optional[Rect] = None
    show_dont_show_option: Optional[bool] = None


class GuidedTour:
    """Renderiza walkthrough com fundo escurecido e foco no item destacado."""

    def __init__(
        self,
        master: ctk.CTk,
        steps: List[TourStep],
        on_close: Optional[Callable[[str, bool], None]] = None,
        show_dont_show_option: bool = True,
    ) -> None:
        self.master = master
        self.steps = list(steps or [])
        self.on_close = on_close
        self.show_dont_show_option = bool(show_dont_show_option)

        self._overlay: Optional[tk.Frame] = None
        self._shade_regions: List[tk.Canvas] = []
        self._spotlight_border: List[tk.Frame] = []
        self._card: Optional[ctk.CTkFrame] = None
        self._title_label: Optional[ctk.CTkLabel] = None
        self._message_scroll: Optional[ctk.CTkTextbox] = None
        self._dots_frame: Optional[ctk.CTkFrame] = None
        self._dot_labels: List[ctk.CTkLabel] = []
        self._dont_show_var: Optional[ctk.BooleanVar] = None
        self._dont_show_check: Optional[ctk.CTkCheckBox] = None
        self._buttons_frame: Optional[ctk.CTkFrame] = None
        self._back_btn: Optional[ctk.CTkButton] = None
        self._next_btn: Optional[ctk.CTkButton] = None

        self._step_index = 0
        self._active = False
        self._current_target_rect: Optional[Rect] = None
        self._current_step_show_dont_show: bool = bool(show_dont_show_option)
        self._configure_bind_id: Optional[str] = None
        self._escape_bind_id: Optional[str] = None
        self._configure_pending_id: Optional[str] = None
        self._last_card_geometry: Optional[Tuple[int, int, int, int]] = None
        self._last_message_height: Optional[int] = None

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self) -> None:
        """Inicia o tutorial."""
        if self._active or not self.steps:
            return

        self._active = True
        self.master.update_idletasks()
        self._build_overlay()
        self._bind_master_listeners()
        self._show_step(0, prepare=True)

    def bring_to_front(self, *, reset_to_first: bool = False) -> None:
        """Reposiciona o overlay interno acima da UI sem criar nova instância."""
        if not self._active:
            return
        index = 0 if reset_to_first else self._step_index
        self._show_step(index, prepare=False)
        self._lift_overlay()

    def close(self, reason: str = "closed") -> None:
        """Fecha o tutorial e limpa recursos."""
        if not self._active:
            return

        self._active = False
        self._unbind_master_listeners()
        self._cancel_configure_sync()

        for widget in [*self._shade_regions, *self._spotlight_border, self._card, self._overlay]:
            try:
                if widget is not None and widget.winfo_exists():
                    widget.destroy()
            except Exception:
                pass

        self._overlay = None
        self._shade_regions = []
        self._spotlight_border = []
        self._card = None
        self._title_label = None
        self._message_scroll = None
        self._dots_frame = None
        self._dot_labels = []
        self._dont_show_var = None
        self._dont_show_check = None
        self._buttons_frame = None
        self._back_btn = None
        self._next_btn = None
        self._current_target_rect = None
        self._last_card_geometry = None
        self._last_message_height = None

        if self.on_close:
            try:
                self.on_close(reason, self._should_not_show_again())
            except Exception:
                pass

    def _build_overlay(self) -> None:
        """Cria elementos internos do overlay sem abrir nova janela."""
        overlay = tk.Frame(self.master, borderwidth=0, highlightthickness=0)
        overlay.place(x=0, y=0, width=1, height=1)
        overlay.lower()
        self._overlay = overlay

        self._shade_regions = []
        for _ in range(4):
            canvas = tk.Canvas(
                self.master,
                highlightthickness=0,
                borderwidth=0,
                relief="flat",
                bg=get_current_colors().get("background", "#EAF0F8"),
            )
            canvas.bind("<Button-1>", lambda _event: "break")
            self._shade_regions.append(canvas)

        self._spotlight_border = []
        for _ in range(4):
            border = tk.Frame(self.master, bg=get_current_colors().get("primary", "#2F7EF7"))
            self._spotlight_border.append(border)

        self._build_card(self.master)
        self._lift_overlay()

    def _build_card(self, parent: tk.Misc) -> None:
        """Constrói o card de texto/botões dentro da janela principal."""
        card = ctk.CTkFrame(
            parent,
            fg_color=get_themed_color("surface"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=16,
            width=440,
            height=320,
        )
        card.place(x=20, y=20)
        try:
            card.pack_propagate(False)
            card.grid_propagate(False)
        except Exception:
            pass

        title = ctk.CTkLabel(
            card,
            text="",
            font=FONTS["heading"],
            anchor="w",
            justify="left",
            text_color=get_themed_color("text"),
        )
        title.pack(fill="x", padx=18, pady=(16, 8))

        dots_frame = ctk.CTkFrame(card, fg_color="transparent")
        dots_frame.pack(fill="x", padx=18, pady=(0, 10))
        dot_labels: List[ctk.CTkLabel] = []
        for _ in range(len(self.steps)):
            label = ctk.CTkLabel(
                dots_frame,
                text="●",
                font=("Segoe UI", 10),
                text_color=get_themed_color("text_secondary"),
            )
            label.pack(side="left", padx=2)
            dot_labels.append(label)

        buttons_frame = ctk.CTkFrame(card, fg_color="transparent")
        buttons_frame.pack(fill="x", padx=18, pady=(0, 10))

        message = ctk.CTkTextbox(
            card,
            font=FONTS["body"],
            activate_scrollbars=True,
            wrap="word",
            border_width=0,
            corner_radius=10,
            fg_color=get_themed_color("sheet"),
            text_color=get_themed_color("text"),
            height=150,
        )
        message.pack(fill="both", expand=True, padx=18, pady=(0, 8))
        message.configure(state="disabled")

        dont_show_var = ctk.BooleanVar(value=False)
        dont_show_check = ctk.CTkCheckBox(
            card,
            text="Não mostrar este tutorial ao iniciar",
            variable=dont_show_var,
            font=FONTS["small"],
        )
        if self.show_dont_show_option:
            dont_show_check.pack(fill="x", padx=18, pady=(0, 6))
            dont_show_check.pack_forget()

        skip_btn = self._build_action_button(buttons_frame, "Pular", lambda: self.close("skipped"))
        skip_btn.pack(side="left")

        next_btn = self._build_action_button(buttons_frame, "Próximo", self._next)
        next_btn.pack(side="right")

        back_btn = self._build_action_button(buttons_frame, "Voltar", self._back)
        back_btn.pack(side="right", padx=(8, 0))

        self._card = card
        self._title_label = title
        self._message_scroll = message
        self._dots_frame = dots_frame
        self._dot_labels = dot_labels
        self._dont_show_var = dont_show_var
        self._dont_show_check = dont_show_check
        self._buttons_frame = buttons_frame
        self._back_btn = back_btn
        self._next_btn = next_btn

    def _build_action_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
    ) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent,
            text=text,
            width=92,
            height=32,
            command=command,
            fg_color=get_themed_color("primary"),
            hover_color=get_themed_color("primary_hover"),
            text_color=("#FFFFFF", "#FFFFFF"),
            text_color_disabled=("#FFFFFF", "#FFFFFF"),
            corner_radius=16,
        )

    def _next(self) -> None:
        if self._step_index >= len(self.steps) - 1:
            self.close("completed")
            return
        self._show_step(self._step_index + 1, prepare=True)

    def _back(self) -> None:
        if self._step_index <= 0:
            return
        self._show_step(self._step_index - 1, prepare=True)

    def _show_step(self, index: int, *, prepare: bool = False) -> None:
        if not self._active or not self.steps:
            return

        self._step_index = max(0, min(index, len(self.steps) - 1))
        step = self.steps[self._step_index]

        if prepare and callable(step.before_enter):
            try:
                step.before_enter()
            except Exception:
                pass

        self.master.update_idletasks()
        rect = step.target_getter() or step.fallback_rect or self._default_rect()
        rect = self._expand_rect(rect, int(step.anchor_padding or 0))
        width, height = self._viewport_size()
        rect = self._sanitize_rect(rect, width, height)
        self._current_target_rect = rect

        if self._title_label:
            self._title_label.configure(text=step.title)
        self._set_message(step.message)
        self._current_step_show_dont_show = (
            self.show_dont_show_option
            if step.show_dont_show_option is None
            else bool(step.show_dont_show_option)
        )

        self._render_dots()
        self._render_overlay(rect)
        self._position_card(rect, preferred=step.preferred_placement)
        self._update_nav_buttons()
        self._lift_overlay()

    def _render_dots(self) -> None:
        if not self._dot_labels:
            return

        for i, label in enumerate(self._dot_labels):
            color = get_themed_color("primary") if i == self._step_index else get_themed_color("text_secondary")
            label.configure(text_color=color)

    def _render_overlay(self, rect: Rect) -> None:
        """Desenha quatro regiões de sombra ao redor do alvo."""
        if len(self._shade_regions) != 4 or len(self._spotlight_border) != 4:
            return

        width, height = self._viewport_size()
        x1, y1, x2, y2 = self._sanitize_rect(rect, width, height)

        regions = (
            (0, 0, width, y1),
            (0, y1, x1, y2 - y1),
            (x2, y1, width - x2, y2 - y1),
            (0, y2, width, height - y2),
        )
        for canvas, (x, y, w, h) in zip(self._shade_regions, regions):
            if w <= 0 or h <= 0:
                canvas.place_forget()
                continue
            canvas.place(x=x, y=y, width=w, height=h)
            canvas.delete("all")
            canvas.configure(bg=get_current_colors().get("background", "#EAF0F8"))
            canvas.create_rectangle(0, 0, w, h, fill="#000000", stipple="gray50", outline="")

        accent = get_current_colors().get("primary", "#2F7EF7")
        top, right, bottom, left = self._spotlight_border
        for border in self._spotlight_border:
            border.configure(bg=accent)
        top.place(x=x1, y=y1, width=max(1, x2 - x1), height=3)
        bottom.place(x=x1, y=y2 - 3, width=max(1, x2 - x1), height=3)
        left.place(x=x1, y=y1, width=3, height=max(1, y2 - y1))
        right.place(x=x2 - 3, y=y1, width=3, height=max(1, y2 - y1))

    def _position_card(self, rect: Rect, *, preferred: Placement = "auto") -> None:
        """Posiciona o card dentro da janela, respeitando os limites da viewport."""
        if not self._card:
            return

        width, height = self._viewport_size()
        margin = 16
        gap = 14
        card_w, card_h, message_h = self._card_dimensions(width, height)
        self._configure_card_layout(card_w, card_h, message_h)

        x1, y1, x2, y2 = self._sanitize_rect(rect, width, height)
        placements = self._resolve_placement_order(preferred, (x1, y1, x2, y2), width, height)

        chosen: Optional[Tuple[int, int]] = None
        for placement in placements:
            candidate = self._candidate_position(
                placement,
                (x1, y1, x2, y2),
                card_w,
                card_h,
                width,
                height,
                margin,
                gap,
            )
            if candidate is None:
                continue
            x, y = candidate
            if not self._rects_overlap((x, y, x + card_w, y + card_h), (x1, y1, x2, y2)):
                chosen = (x, y)
                break

        if chosen is None:
            chosen = (
                max(margin, min((width - card_w) // 2, width - card_w - margin)),
                max(margin, min(height - card_h - margin, y2 + gap)),
            )

        x, y = chosen
        geometry = (int(x), int(y), int(card_w), int(card_h))
        if geometry != self._last_card_geometry:
            self._card.configure(width=card_w, height=card_h)
            self._card.place(x=x, y=y)
            self._last_card_geometry = geometry

    def _card_dimensions(self, width: int, height: int) -> Tuple[int, int, int]:
        horizontal_margin = 24
        card_w = min(480, max(360, int(width * 0.34)))
        if width <= 1366:
            card_w = min(440, max(340, int(width * 0.36)))
        if width <= 1100:
            card_w = min(width - (horizontal_margin * 2), 420)
        if width <= 900:
            card_w = min(width - (horizontal_margin * 2), 380)
        card_w = max(300, min(card_w, width - 32))

        card_h = min(420, max(300, int(height * 0.46)))
        if height <= 768:
            card_h = min(360, max(280, int(height * 0.44)))
        card_h = max(260, min(card_h, height - 32))

        message_h = max(100, card_h - 182)
        return int(card_w), int(card_h), int(message_h)

    def _configure_card_layout(self, card_w: int, card_h: int, message_h: int) -> None:
        if self._card is None or self._message_scroll is None:
            return
        if message_h != self._last_message_height:
            self._message_scroll.configure(height=message_h)
            self._last_message_height = message_h
        self._card.configure(width=card_w, height=card_h)

    def _update_nav_buttons(self) -> None:
        if self._back_btn:
            self._back_btn.configure(state="normal" if self._step_index > 0 else "disabled")
        if self._next_btn:
            self._next_btn.configure(text="Concluir" if self._step_index == len(self.steps) - 1 else "Próximo")
        if self._dont_show_check and self._current_step_show_dont_show:
            is_last = self._step_index == len(self.steps) - 1
            if is_last and not self._dont_show_check.winfo_manager():
                self._dont_show_check.pack(fill="x", padx=18, pady=(0, 10))
            elif (not is_last) and self._dont_show_check.winfo_manager():
                self._dont_show_check.pack_forget()
        elif self._dont_show_check and self._dont_show_check.winfo_manager():
            self._dont_show_check.pack_forget()

    def _should_not_show_again(self) -> bool:
        try:
            return bool(self._dont_show_var.get()) if self._dont_show_var is not None else False
        except Exception:
            return False

    def _bind_master_listeners(self) -> None:
        if self._configure_bind_id is None:
            self._configure_bind_id = self.master.bind("<Configure>", self._on_master_configure, add="+")
        if self._escape_bind_id is None:
            self._escape_bind_id = self.master.bind("<Escape>", lambda _event: self.close("skipped"), add="+")

    def _unbind_master_listeners(self) -> None:
        if self._configure_bind_id is not None:
            try:
                self.master.unbind("<Configure>", self._configure_bind_id)
            except Exception:
                pass
            self._configure_bind_id = None
        if self._escape_bind_id is not None:
            try:
                self.master.unbind("<Escape>", self._escape_bind_id)
            except Exception:
                pass
            self._escape_bind_id = None

    def _on_master_configure(self, _event=None) -> None:
        if not self._active:
            return
        self._cancel_configure_sync()
        self._configure_pending_id = self.master.after(80, self._do_configure_sync)

    def _do_configure_sync(self) -> None:
        self._configure_pending_id = None
        if self._active:
            self._show_step(self._step_index, prepare=False)

    def _cancel_configure_sync(self) -> None:
        if self._configure_pending_id is None:
            return
        try:
            self.master.after_cancel(self._configure_pending_id)
        except Exception:
            pass
        self._configure_pending_id = None

    def _lift_overlay(self) -> None:
        for widget in [self._overlay, *self._shade_regions, *self._spotlight_border, self._card]:
            try:
                if widget is not None and widget.winfo_exists():
                    widget.lift()
            except Exception:
                pass

    def _default_rect(self) -> Rect:
        width, height = self._viewport_size()
        return (
            int(width * 0.28),
            int(height * 0.18),
            int(width * 0.72),
            int(height * 0.34),
        )

    @staticmethod
    def _sanitize_rect(rect: Rect, width: int, height: int) -> Rect:
        x1, y1, x2, y2 = [int(value) for value in rect]
        x1 = max(2, min(x1, max(2, width - 4)))
        y1 = max(2, min(y1, max(2, height - 4)))
        x2 = max(x1 + 10, min(x2, max(x1 + 10, width - 2)))
        y2 = max(y1 + 10, min(y2, max(y1 + 10, height - 2)))
        return x1, y1, x2, y2

    def _viewport_size(self) -> Tuple[int, int]:
        width = max(1, int(self.master.winfo_width()))
        height = max(1, int(self.master.winfo_height()))
        try:
            geometry = str(self.master.geometry()).split("+", 1)[0]
            if "x" in geometry:
                geo_w, geo_h = geometry.lower().split("x", 1)
                width = max(width, int(geo_w))
                height = max(height, int(geo_h))
        except Exception:
            pass
        return width, height

    def _expand_rect(self, rect: Rect, padding: int) -> Rect:
        if padding <= 0:
            return rect
        return (
            int(rect[0] - padding),
            int(rect[1] - padding),
            int(rect[2] + padding),
            int(rect[3] + padding),
        )

    @staticmethod
    def _rects_overlap(a: Rect, b: Rect) -> bool:
        return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])

    def _set_message(self, text: str) -> None:
        if self._message_scroll is None:
            return
        try:
            self._message_scroll.configure(state="normal")
            self._message_scroll.delete("1.0", "end")
            self._message_scroll.insert("1.0", str(text or ""))
            self._message_scroll.configure(state="disabled")
            self._message_scroll.yview_moveto(0.0)
        except Exception:
            pass

    def _resolve_placement_order(
        self,
        preferred: Placement,
        rect: Rect,
        width: int,
        height: int,
    ) -> List[Placement]:
        if preferred != "auto":
            ordered = [preferred]
            for candidate in ("right", "left", "bottom", "top"):
                if candidate not in ordered:
                    ordered.append(candidate)
            return ordered

        x1, y1, x2, y2 = rect
        free_space = {
            "right": max(0, width - x2),
            "left": max(0, x1),
            "bottom": max(0, height - y2),
            "top": max(0, y1),
        }
        return sorted(free_space.keys(), key=lambda key: free_space[key], reverse=True)

    @staticmethod
    def _clamp(value: int, minimum: int, maximum: int) -> int:
        if maximum < minimum:
            return minimum
        return max(minimum, min(value, maximum))

    def _candidate_position(
        self,
        placement: Placement,
        rect: Rect,
        card_w: int,
        card_h: int,
        width: int,
        height: int,
        margin: int,
        gap: int,
    ) -> Optional[Tuple[int, int]]:
        x1, y1, x2, y2 = rect
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2

        if placement == "right":
            x = x2 + gap
            y = self._clamp(center_y - (card_h // 2), margin, height - card_h - margin)
        elif placement == "left":
            x = x1 - card_w - gap
            y = self._clamp(center_y - (card_h // 2), margin, height - card_h - margin)
        elif placement == "bottom":
            x = self._clamp(center_x - (card_w // 2), margin, width - card_w - margin)
            y = y2 + gap
        elif placement == "top":
            x = self._clamp(center_x - (card_w // 2), margin, width - card_w - margin)
            y = y1 - card_h - gap
        else:
            return None

        if x < margin or y < margin:
            return None
        if x + card_w > width - margin or y + card_h > height - margin:
            return None
        return x, y
