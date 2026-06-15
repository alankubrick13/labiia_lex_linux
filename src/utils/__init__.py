"""
Widget de Tooltip para CustomTkinter.
Mostra uma pequena janela flutuante com texto explicativo ao passar o mouse.
"""
import customtkinter as ctk
import tkinter as tk
from typing import Optional

class CTkTooltip:
    """
    Cria um tooltip para um widget específico.
    
    Uso:
        btn = ctk.CTkButton(...)
        tooltip = CTkTooltip(btn, message="Clique para salvar")
    """
    def __init__(
        self,
        widget,
        message: str = "Info",
        delay: int = 350,
        text_color: Optional[str] = None,
        bg_color: Optional[str] = None,
        width: int = 400
    ):
        self.widget = widget
        self.message = message
        self.delay = delay
        self.width = width
        
        # Cores padrão estilo "light tooltip"
        self.bg_color = bg_color or "#FAFAFA"  # Branco quase puro
        self.text_color = text_color or "#333333" # Texto cinza escuro
        self.border_color = "#CCCCCC" # Borda cinza suave
        
        self.tooltip_window: Optional[tk.Toplevel] = None
        self.id_after: Optional[str] = None
        
        # Eventos
        self.widget.bind("<Enter>", self.schedule)
        self.widget.bind("<Leave>", self.unschedule)
        self.widget.bind("<ButtonPress>", self.unschedule)

    def schedule(self, _event=None):
        self.unschedule()
        self.id_after = self.widget.after(self.delay, self.show)

    def unschedule(self, _event=None):
        id_after = self.id_after
        self.id_after = None
        if id_after:
            self.widget.after_cancel(id_after)
        self.hide()

    def show(self):
        if self.tooltip_window:
            return
            
        try:
            if not self.widget.winfo_exists():
                return
        except Exception:
            return

        # Calcular posição
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        except Exception:
            return
        
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        self.tooltip_window.attributes("-topmost", True) # Sempre no topo
        
        # Frame container com borda
        frame = ctk.CTkFrame(
            self.tooltip_window,
            fg_color=self.bg_color,
            corner_radius=6,
            border_width=1,
            border_color=self.border_color
        )
        frame.pack()
        
        # Label com texto
        label = ctk.CTkLabel(
            frame,
            text=self.message,
            text_color=self.text_color,
            bg_color="transparent",
            fg_color="transparent",
            font=("Segoe UI", 11),
            padx=8,
            pady=4,
            justify="left",
            wraplength=self.width
        )
        label.pack()

    def hide(self):
        tw = self.tooltip_window
        self.tooltip_window = None
        if tw:
            tw.destroy()
