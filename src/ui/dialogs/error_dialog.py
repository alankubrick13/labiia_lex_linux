"""
Dialogo de erro — visual Windows 11 nativo.
"""
import customtkinter as ctk
from typing import Optional, Union

from ..styles import FONTS, COLORS, get_themed_color


class ErrorDialog(ctk.CTkToplevel):
    """
    Dialogo de erro compacto estilo Windows (MessageBox extendido).
    Layout: ícone + mensagem principal, detalhes em caixa colapsável,
    botões no rodapé.
    """

    def __init__(self, parent, error: Union[Exception, str] = None,
                 what: str = None, why: str = None, how: str = None):
        super().__init__(parent)
        self.title("Erro")
        self.geometry("520x340")
        self.minsize(460, 280)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        # Extrair informações do erro
        if error and hasattr(error, "what"):
            what = error.what
            why  = error.why
            how  = error.how
        elif error:
            what = "Ocorreu um erro"
            why  = str(error)
            how  = "Tente novamente ou consulte a documentação."

        if not how:
            how = "Verifique os detalhes acima e tente novamente."

        self._full_text = (
            f"O que aconteceu:\n{what or ''}\n\n"
            f"Por que aconteceu:\n{why or ''}\n\n"
            f"Como resolver:\n{how or ''}\n"
        )

        self._create_widgets(what or "", why or "", how or "")
        self._center_on_parent(parent)

    def _center_on_parent(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self, what: str, why: str, how: str):
        """Layout Windows MessageBox: ícone + texto, detalhes expanidos, botões no rodapé."""

        # ── Área principal ───────────────────────────────────────────────────
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        # Linha do topo: indicador + mensagem principal
        header = ctk.CTkFrame(main, fg_color="transparent")
        header.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            header, text="!",
            font=("Segoe UI", 28),
            text_color=("#9D5D00", "#FCE100"),   # amber light / dark
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            header,
            text=what or "Ocorreu um erro",
            font=FONTS["heading"],
            wraplength=380,
            justify="left",
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        # Detalhes em caixa de texto compacta (somente se houver why/how)
        details_text = ""
        if why:
            details_text += f"Detalhe: {why}"
        if how and how != "Verifique os detalhes acima e tente novamente.":
            if details_text:
                details_text += f"\n\nComo resolver: {how}"
            else:
                details_text = f"Como resolver: {how}"

        if details_text:
            ctk.CTkLabel(
                main, text="Detalhes:", font=FONTS["small"],
                text_color=get_themed_color("text_secondary"), anchor="w",
            ).pack(fill="x", pady=(0, 4))

            details_box = ctk.CTkTextbox(
                main,
                height=120,
                font=FONTS["small"],
                wrap="word",
                activate_scrollbars=True,
                fg_color=get_themed_color("background"),
                border_width=1,
                border_color=get_themed_color("border"),
                corner_radius=3,
            )
            details_box.pack(fill="both", expand=True, pady=(0, 4))
            details_box.insert("1.0", details_text)
            details_box.configure(state="disabled")

        # ── Divisória + Botões no rodapé ────────────────────────────────────
        ctk.CTkFrame(self, height=1, fg_color=get_themed_color("border")
                     ).pack(fill="x", side="bottom")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom", padx=12, pady=8)

        # "Copiar detalhes" à esquerda — ação secundária
        ctk.CTkButton(
            btn_row, text="Copiar detalhes", width=110, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=lambda: self._copy(self._full_text),
        ).pack(side="left")

        # "OK" à direita — ação primária (Windows padrão)
        ctk.CTkButton(
            btn_row, text="OK", width=80, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self.destroy,
        ).pack(side="right")

    def _copy(self, text: str):
        self.clipboard_clear()
        self.clipboard_append(text or "")
        self.update_idletasks()


def show_error(parent, error: Union[Exception, str] = None,
               what: str = None, why: str = None, how: str = None) -> None:
    """Helper para mostrar dialogo de erro."""
    dialog = ErrorDialog(parent, error=error, what=what, why=why, how=how)
    dialog.wait_window()
