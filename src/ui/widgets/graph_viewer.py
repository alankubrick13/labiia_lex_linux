"""
Widget para visualizacao de graficos com zoom e exportacao.
"""
import customtkinter as ctk
from pathlib import Path
from typing import Optional, Union
from PIL import Image
import logging

from ..styles import FONTS, COLORS, get_themed_color
from ..iconography import label_with_icon

log = logging.getLogger(__name__)


class GraphViewer(ctk.CTkFrame):
    """
    Widget especializado para exibicao de graficos.
    
    Funcionalidades:
    - Exibicao de imagens
    - Zoom in/out
    - Redimensionamento automatico
    - Exportacao para arquivo
    """
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        
        self._image_path: Optional[Path] = None
        self._original_image: Optional[Image.Image] = None
        self._current_zoom = 1.0
        self._current_image = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Cria widgets internos."""
        # Toolbar de zoom
        self.toolbar = ctk.CTkFrame(self, height=40)
        self.toolbar.pack(fill="x", padx=5, pady=5)
        
        self.btn_zoom_in = ctk.CTkButton(
            self.toolbar,
            text="+",
            width=40,
            command=self._zoom_in
        )
        self.btn_zoom_in.pack(side="left", padx=2)
        
        self.btn_zoom_out = ctk.CTkButton(
            self.toolbar,
            text="-",
            width=40,
            command=self._zoom_out
        )
        self.btn_zoom_out.pack(side="left", padx=2)
        
        self.btn_fit = ctk.CTkButton(
            self.toolbar,
            text="Ajustar",
            width=60,
            command=self._fit_to_window
        )
        self.btn_fit.pack(side="left", padx=2)
        
        self.zoom_label = ctk.CTkLabel(
            self.toolbar,
            text="100%",
            font=FONTS['small']
        )
        self.zoom_label.pack(side="left", padx=10)
        
        self.btn_export = ctk.CTkButton(
            self.toolbar,
            text=label_with_icon("save", "Salvar"),
            width=80,
            command=self._export_image
        )
        self.btn_export.pack(side="right", padx=5)
        
        # Area de imagem scrollavel
        self.canvas_frame = ctk.CTkScrollableFrame(self)
        self.canvas_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Label para imagem
        self.image_label = ctk.CTkLabel(
            self.canvas_frame,
            text="Nenhum gráfico carregado.",
            font=FONTS['body'],
            text_color=get_themed_color('text_secondary')
        )
        self.image_label.pack(expand=True)
    
    def load_image(self, path: Union[str, Path]) -> bool:
        """
        Carrega imagem no visualizador.
        
        Args:
            path: Caminho para arquivo de imagem
            
        Returns:
            True se carregou com sucesso
        """
        path = Path(path)
        if not path.exists():
            self.image_label.configure(
                text=f"Arquivo não encontrado:\n{path}",
                image=None
            )
            return False
        display_path = self._resolve_display_path(path)
        if display_path is None:
            self.image_label.configure(
                text=(
                    "Formato SVG sem PNG equivalente.\n"
                    "Use saída PNG para visualizar no aplicativo."
                ),
                image=None,
            )
            return False
        
        try:
            self._image_path = display_path
            self._original_image = Image.open(display_path)
            self._current_zoom = 1.0
            self._update_display()
            return True
            
        except Exception as e:
            self.image_label.configure(
                text=f"Erro ao carregar imagem:\n{e}",
                image=None
            )
            return False

    @staticmethod
    def _resolve_display_path(path: Path) -> Optional[Path]:
        """Retorna caminho renderizável (SVG usa PNG equivalente, quando existir)."""
        if path.suffix.lower() != ".svg":
            return path
        png_candidate = path.with_suffix(".png")
        return png_candidate if png_candidate.exists() else None
    
    def _update_display(self) -> None:
        """Atualiza exibicao com zoom atual."""
        if self._original_image is None:
            return
        
        # Calcula novo tamanho
        new_width = int(self._original_image.width * self._current_zoom)
        new_height = int(self._original_image.height * self._current_zoom)
        
        # Redimensiona
        resized = self._original_image.resize(
            (new_width, new_height),
            Image.Resampling.LANCZOS
        )
        
        # Converte para CTkImage
        ctk_image = ctk.CTkImage(
            light_image=resized,
            dark_image=resized,
            size=(new_width, new_height)
        )
        self._current_image = ctk_image
        
        self.image_label.configure(image=ctk_image, text="")
        self.zoom_label.configure(text=f"{int(self._current_zoom * 100)}%")
    
    def _zoom_in(self) -> None:
        """Aumenta zoom."""
        if self._current_zoom < 3.0:
            self._current_zoom *= 1.25
            self._update_display()
    
    def _zoom_out(self) -> None:
        """Diminui zoom."""
        if self._current_zoom > 0.25:
            self._current_zoom /= 1.25
            self._update_display()
    
    def _fit_to_window(self) -> None:
        """Ajusta imagem ao tamanho da janela."""
        if self._original_image is None:
            return
        
        # Calcula zoom para caber
        frame_width = self.canvas_frame.winfo_width() - 20
        frame_height = self.canvas_frame.winfo_height() - 20
        
        if frame_width <= 0 or frame_height <= 0:
            frame_width = 700
            frame_height = 500
        
        zoom_x = frame_width / self._original_image.width
        zoom_y = frame_height / self._original_image.height
        self._current_zoom = min(zoom_x, zoom_y, 1.0)
        
        self._update_display()
    
    def _export_image(self) -> None:
        """Exporta imagem para arquivo."""
        if self._original_image is None:
            return
        
        from tkinter import filedialog
        
        filepath = filedialog.asksaveasfilename(
            title="Salvar Gráfico",
            defaultextension=".png",
            initialfile=self._image_path.stem if self._image_path else "grafico",
            filetypes=[
                ("PNG", "*.png"),
                ("JPEG", "*.jpg"),
                ("PDF", "*.pdf"),
                ("Todos", "*.*")
            ]
        )
        
        if filepath:
            try:
                self._original_image.save(filepath)
            except Exception as e:
                log.exception("Falha ao exportar grafico: %s", e)
                from tkinter import messagebox
                messagebox.showerror(
                    "Erro ao exportar gráfico",
                    (
                        "O que aconteceu: Não foi possível salvar o gráfico.\n"
                        f"Por que aconteceu: {e}\n"
                        "Como resolver: Verifique permissões da pasta e tente novamente."
                    ),
                )
    
    def clear(self) -> None:
        """Limpa visualizador."""
        self._image_path = None
        self._original_image = None
        self._current_image = None
        self._current_zoom = 1.0
        
        self.image_label.configure(
            text="Nenhum gráfico carregado.",
            image=None
        )
        self.zoom_label.configure(text="100%")
