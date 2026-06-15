"""
Dialogo de importacao de arquivos — visual Windows 11 nativo.
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
import threading
from typing import Optional, Dict, Any, List
import re
import unicodedata

from ..styles import FONTS, COLORS, get_themed_color, get_current_colors
from ..iconography import create_help_button, label_with_icon
from ..modern_components import (
    create_option_card,
    create_section_title,
    create_sheet_footer,
    create_surface,
    set_option_card_state,
    style_flat_button,
)
from ...utils.logger import get_logger
from ...core.stopword_layers import parse_stopwords_file, parse_stopwords_text

log = get_logger(__name__)


class ImportDialog(ctk.CTkToplevel):
    """
    Dialogo para importar e configurar corpus.

    Modos de importacao:
      A. Arquivo único  — .txt, .md, .json, .net, .pdf, .docx, .odt, .xlsx, .csv
      B. Pasta (coleção) — todos os .txt/.md/.json/.net/.pdf/.docx/.odt de um diretório
      C. ZIP (coleção) — todos os formatos suportados dentro de um .zip

    Fluxo:
    1. Escolher modo de origem (arquivo / pasta / ZIP)
    2. Selecionar origem
    3. Escolher modo de corpus (IRaMuTeQ ou tradicional)
    4. Configurar segmentação
    5. Preview do resultado
    6. Confirmar importação
    """

    def __init__(self, parent, default_uce_size: int = 40):
        super().__init__(parent)
        self.title("Importar")
        self._set_initial_geometry(parent)
        self.minsize(860, 620)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._result: Optional[Dict[str, Any]] = None
        self._file_path: Optional[Path] = None
        self._file_paths: List[Path] = []
        self._extracted_text: str = ""
        self._import_metadata: Dict[str, Any] = {}
        self._default_uce_size = max(20, min(200, int(default_uce_size or 40)))
        self._preview_running = False
        self._bigram_candidates: List[Dict[str, Any]] = []
        self._global_stopwords: List[str] = list(
            getattr(parent, "get_global_custom_stopwords", lambda: [])()
        )
        self._project_stopwords: List[str] = list(
            getattr(parent, "get_project_custom_stopwords", lambda: [])()
        )
        self._session_stopwords: List[str] = []
        self.lowercase_var = ctk.BooleanVar(value=False)
        self.remove_numbers_var = ctk.BooleanVar(value=False)
        self.remove_accents_var = ctk.BooleanVar(value=False)
        self.clean_web_data_var = ctk.BooleanVar(value=False)
        # Modo de origem: 'file' | 'folder' | 'zip'
        self._source_mode: str = "file"

        self._create_widgets()
        self._center_on_parent(parent)
        self.wait_window()

    def _set_initial_geometry(self, parent) -> None:
        """
        Define tamanho inicial amplo para exibir todas as seções ao abrir.

        Usa proporção da tela com limites para manter compatibilidade em
        monitores menores e abrir "grande" por padrão.
        """
        try:
            screen_w = max(1024, int(self.winfo_screenwidth()))
            screen_h = max(700, int(self.winfo_screenheight()))
        except Exception:
            self.geometry("1120x860")
            return

        target_w = min(1280, max(980, int(screen_w * 0.78)))
        target_h = min(940, max(760, int(screen_h * 0.86)))
        target_w = min(target_w, screen_w - 60)
        target_h = min(target_h, screen_h - 80)

        # Evita abrir menor que o pai quando a janela principal já está ampla.
        try:
            parent_w = int(parent.winfo_width() or 0)
            parent_h = int(parent.winfo_height() or 0)
            if parent_w > 980:
                target_w = min(screen_w - 60, max(target_w, int(parent_w * 0.90)))
            if parent_h > 700:
                target_h = min(screen_h - 80, max(target_h, int(parent_h * 0.90)))
        except Exception:
            pass

        self.geometry(f"{target_w}x{target_h}")

    def _center_on_parent(self, parent):
        """Centraliza na janela pai."""
        self.update_idletasks()
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        dialog_w = self.winfo_width()
        dialog_h = self.winfo_height()
        x = parent_x + (parent_w - dialog_w) // 2
        y = parent_y + (parent_h - dialog_h) // 2
        self.geometry(f"+{x}+{y}")

    def _create_help_icon(self, parent, text: str) -> ctk.CTkButton:
        """Cria ícone de ajuda padronizado com tooltip."""
        return create_help_button(parent, text, size=18)

    def _create_widgets(self):
        """Cria widgets — layout Windows (conteudo rolavel + botoes no rodape)."""
        self.configure(fg_color=get_themed_color("background"))
        self.advanced_section_expanded_var = ctk.BooleanVar(value=False)
        self.source_card_buttons: Dict[str, ctk.CTkButton] = {}

        # === Conteudo rolavel (occupa tudo acima do rodape) ===
        main_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=16, pady=(12, 0))

        # === Seção 1: Tipo de origem ===
        source_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        source_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            source_frame,
            text="1. O que você quer importar?",
            font=FONTS['heading']
        ).pack(anchor="w")

        source_btn_row = ctk.CTkFrame(source_frame, fg_color="transparent")
        source_btn_row.pack(fill="x", pady=(4, 2), padx=16)

        # Botão: Arquivo único
        self.btn_src_file = ctk.CTkButton(
            source_btn_row,
            text=label_with_icon("documents", "Arquivo único"),
            width=184, height=52,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=16,
            command=lambda: self._set_source_mode("file"),
        )
        self.btn_src_file.pack(side="left", padx=(0, 10))
        self._create_help_icon(source_btn_row, "Selecione um único arquivo texto, PDF, Word, Excel, CSV etc. para analisar.").pack(side="left", padx=(4, 16))

        # Botão: Pasta (coleção)
        self.btn_src_folder = ctk.CTkButton(
            source_btn_row,
            text=label_with_icon("corpus", "Pasta (coleção)"),
            width=184, height=52,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=16,
            command=lambda: self._set_source_mode("folder"),
        )
        self.btn_src_folder.pack(side="left", padx=(0, 10))
        self._create_help_icon(source_btn_row, "Selecione uma pasta contendo vários arquivos para analisá-los juntos.").pack(side="left", padx=(4, 16))

        # Botão: ZIP (coleção)
        self.btn_src_zip = ctk.CTkButton(
            source_btn_row,
            text=label_with_icon("import", "ZIP (coleção)"),
            width=184, height=52,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=16,
            command=lambda: self._set_source_mode("zip"),
        )
        self.btn_src_zip.pack(side="left", padx=(0, 10))
        self._create_help_icon(source_btn_row, "Importe um arquivo compactado ZIP contendo textos para análise.").pack(side="left", padx=(4, 0))
        self.source_card_buttons = {
            "file": self.btn_src_file,
            "folder": self.btn_src_folder,
            "zip": self.btn_src_zip,
        }

        # Descrição dinâmica do modo de origem
        self.source_desc_label = ctk.CTkLabel(
            source_frame,
            text="Selecione um ou mais arquivos suportados (.txt, .md, .json, .net, .pdf, .docx, .odt, .xlsx, .csv).",
            font=FONTS['small'],
            text_color=get_themed_color("text_secondary"),
            anchor="w",
        )
        self.source_desc_label.pack(fill="x", padx=16, pady=(2, 0))

        # === Seção 2: Selecao de origem ===
        file_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        file_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            file_frame,
            text="2. Selecione a origem:",
            font=FONTS['heading']
        ).pack(anchor="w")

        file_row = ctk.CTkFrame(file_frame, fg_color="transparent")
        file_row.pack(fill="x", pady=4)

        self.file_entry = ctk.CTkEntry(
            file_row,
            placeholder_text="Nenhuma origem selecionada",
        )
        self.file_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.file_entry.configure(state="disabled")

        self.btn_browse = ctk.CTkButton(
            file_row,
            text="Procurar...",
            width=90, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._browse_file,
        )
        self.btn_browse.pack(side="left")

        # === Seção 3: Opções avançadas ===
        self.advanced_section_frame = ctk.CTkFrame(
            main_frame,
            fg_color=get_themed_color("surface"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=16,
        )
        self.advanced_section_frame.pack(fill="x", pady=(0, 8))

        advanced_header = ctk.CTkFrame(self.advanced_section_frame, fg_color="transparent")
        advanced_header.pack(fill="x", padx=16, pady=(14, 10))
        ctk.CTkLabel(
            advanced_header,
            text="3. Opções avançadas",
            font=FONTS["heading"],
        ).pack(side="left")
        self.advanced_toggle_button = ctk.CTkButton(
            advanced_header,
            text="Mostrar opções avançadas",
            width=190,
            height=30,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=14,
            command=self._toggle_advanced_section,
        )
        self.advanced_toggle_button.pack(side="right")

        self.advanced_section_body = ctk.CTkFrame(self.advanced_section_frame, fg_color="transparent")

        mode_frame = ctk.CTkFrame(self.advanced_section_body, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            mode_frame,
            text="3. Modo de corpus:",
            font=FONTS['heading']
        ).pack(anchor="w")

        self.mode_var = ctk.StringVar(value="traditional")

        modes_row = ctk.CTkFrame(mode_frame, fg_color="transparent")
        modes_row.pack(fill="x", pady=4)

        trad_row = ctk.CTkFrame(modes_row, fg_color="transparent")
        trad_row.pack(anchor="w", padx=16, pady=2)
        ctk.CTkRadioButton(
            trad_row,
            text="Análise tradicional (texto livre)",
            variable=self.mode_var,
            value="traditional"
        ).pack(side="left")
        self._create_help_icon(
            trad_row, 
            "O texto será tratado de forma contínua, sem variáveis explícitas. Bom para importar material da web."
        ).pack(side="left", padx=(6, 0))

        iramuteq_row = ctk.CTkFrame(modes_row, fg_color="transparent")
        iramuteq_row.pack(anchor="w", padx=16, pady=2)
        ctk.CTkRadioButton(
            iramuteq_row,
            text="Formato IRaMuTeQ (com variáveis ****)",
            variable=self.mode_var,
            value="iramuteq"
        ).pack(side="left")
        self._create_help_icon(
            iramuteq_row, 
            "O formato clássico onde cada texto começa com '****' e pode incluir metadados/variáveis (ex: *sexo_f)."
        ).pack(side="left", padx=(6, 0))

        # === Seção 4: Segmentação ===
        options_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        options_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            options_frame,
            text="4. Segmentação:",
            font=FONTS['heading']
        ).pack(anchor="w")

        options_row = ctk.CTkFrame(options_frame, fg_color="transparent")
        options_row.pack(fill="x", pady=4)

        uce_row = ctk.CTkFrame(options_row, fg_color="transparent")
        uce_row.pack(fill="x", pady=(8, 2))
        ctk.CTkLabel(
            uce_row,
            text="Tamanho do segmento (UCE):",
            font=FONTS['body'],
        ).pack(side="left", padx=(16, 6))

        self._create_help_icon(
            uce_row, 
            "Tamanho em palavras (tokens) de cada segmento analisado. O padrão recomendado é 40."
        ).pack(side="left", padx=(0, 16))
        self.uce_size_var = ctk.IntVar(value=self._default_uce_size)
        ctk.CTkSlider(
            uce_row,
            from_=20,
            to=120,
            number_of_steps=20,
            variable=self.uce_size_var,
            width=160,
        ).pack(side="left", padx=(0, 8))
        self.uce_size_label = ctk.CTkLabel(
            uce_row,
            text=str(self.uce_size_var.get()),
            font=FONTS['body'],
            width=32,
        )
        self.uce_size_label.pack(side="left")
        self.uce_size_var.trace_add(
            "write",
            lambda *_: self.uce_size_label.configure(text=str(self.uce_size_var.get())),
        )

        # === Seção 5: Preview ===
        preview_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        preview_frame.pack(fill="both", expand=True, pady=(0, 8))

        ctk.CTkLabel(
            preview_frame,
            text="5. Preview:",
            font=FONTS['heading']
        ).pack(anchor="w")

        self.preview_text = ctk.CTkTextbox(
            preview_frame,
            height=110,
            font=FONTS['mono'],
            fg_color=get_themed_color("background"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
        )
        self.preview_text.pack(fill="both", expand=True, pady=(4, 4))
        self.preview_text.insert("1.0", "Selecione um arquivo para ver o preview...")
        self.preview_text.configure(state="disabled")

        self.preview_status_label = ctk.CTkLabel(
            preview_frame,
            text="Aguardando arquivo...",
            font=FONTS['small'],
            text_color=get_themed_color("text_secondary"),
            anchor="w",
        )
        self.preview_status_label.pack(fill="x", pady=(0, 2))

        self.preview_progress = ctk.CTkProgressBar(
            preview_frame, height=4, corner_radius=2,
        )
        self.preview_progress.pack(fill="x", pady=(0, 4))
        self.preview_progress.set(0)

        # === Seção 6: União de bigramas (fase posterior) ===
        bigram_frame = ctk.CTkFrame(self.advanced_section_body, fg_color="transparent")
        bigram_frame.pack(fill="x", pady=(0, 4))

        bigram_title_row = ctk.CTkFrame(bigram_frame, fg_color="transparent")
        bigram_title_row.pack(anchor="w")
        ctk.CTkLabel(
            bigram_title_row,
            text="6. Expressões compostas (após importar):",
            font=FONTS['heading']
        ).pack(side="left")
        self._create_help_icon(
            bigram_title_row, 
            "Esta etapa foi movida para Preparar corpus, depois que a importação limpa inicial terminar."
        ).pack(side="left", padx=(6, 0))

        self._selected_bigrams_cache: List[Dict[str, Any]] = []
        self._bigram_dialog_open = False

        bigram_btn_row = ctk.CTkFrame(bigram_frame, fg_color="transparent")
        bigram_btn_row.pack(fill="x", padx=(16, 0), pady=(4, 2))

        self.btn_open_bigram_dialog = ctk.CTkButton(
            bigram_btn_row,
            text="Selecionar expressoes para unir...",
            width=240, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._open_bigram_selection_dialog,
            state="disabled",
        )
        self.btn_open_bigram_dialog.pack(side="left")

        self.bigram_status_label = ctk.CTkLabel(
            bigram_btn_row,
            text="Disponível após a importação.",
            font=FONTS['small'],
            text_color=COLORS['text_secondary'],
            anchor="w",
        )
        self.bigram_status_label.pack(side="left", padx=(10, 0))

        # === Secao 7: Stopwords customizadas ===
        stopword_frame = ctk.CTkFrame(self.advanced_section_body, fg_color="transparent")
        stopword_frame.pack(fill="x", pady=(0, 6))

        stopword_title_row = ctk.CTkFrame(stopword_frame, fg_color="transparent")
        stopword_title_row.pack(anchor="w")
        ctk.CTkLabel(
            stopword_title_row,
            text="7. Stopwords customizadas (opcional):",
            font=FONTS["heading"],
        ).pack(side="left")
        self._create_help_icon(
            stopword_title_row,
            "Inclua palavras por dicionario (.txt/.csv) ou manualmente. "
            "Camadas aplicadas: base + global + projeto + sessao.",
        ).pack(side="left", padx=(6, 0))

        stopword_row = ctk.CTkFrame(stopword_frame, fg_color="transparent")
        stopword_row.pack(fill="x", padx=(16, 0), pady=(4, 2))

        self.btn_stopwords_file = ctk.CTkButton(
            stopword_row,
            text="Importar dicionario...",
            width=150,
            height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._import_stopword_dictionary,
        )
        self.btn_stopwords_file.pack(side="left")

        self.stopwords_manual_var = ctk.StringVar(value="")
        self.stopwords_manual_entry = ctk.CTkEntry(
            stopword_row,
            textvariable=self.stopwords_manual_var,
            width=280,
            placeholder_text="Adicionar manualmente: termo1, termo2, et al",
        )
        self.stopwords_manual_entry.pack(side="left", padx=(8, 8))

        self.btn_stopwords_add = ctk.CTkButton(
            stopword_row,
            text="Adicionar",
            width=88,
            height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._add_manual_stopwords,
        )
        self.btn_stopwords_add.pack(side="left")

        self.btn_stopwords_clear = ctk.CTkButton(
            stopword_row,
            text="Limpar sessao",
            width=110,
            height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1,
            border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._clear_session_stopwords,
        )
        self.btn_stopwords_clear.pack(side="left", padx=(8, 0))

        stopword_flags_row = ctk.CTkFrame(stopword_frame, fg_color="transparent")
        stopword_flags_row.pack(fill="x", padx=(16, 0), pady=(2, 2))
        self.persist_project_stopwords_var = ctk.BooleanVar(value=True)
        self.persist_global_stopwords_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            stopword_flags_row,
            text="Salvar no projeto",
            variable=self.persist_project_stopwords_var,
        ).pack(side="left")
        ctk.CTkCheckBox(
            stopword_flags_row,
            text="Salvar globalmente",
            variable=self.persist_global_stopwords_var,
        ).pack(side="left", padx=(12, 0))

        self.stopwords_status_label = ctk.CTkLabel(
            stopword_frame,
            text="",
            font=FONTS["small"],
            text_color=get_themed_color("text_secondary"),
            anchor="w",
        )
        self.stopwords_status_label.pack(fill="x", padx=(16, 0), pady=(0, 2))
        self._refresh_stopword_status()

        # === Divisoria + Botoes no rodape (padrao Windows) ===
        ctk.CTkFrame(self, height=1, fg_color=get_themed_color("border")
                     ).pack(fill="x", side="bottom")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", side="bottom", padx=12, pady=8)

        # Cancelar (secundario, direita — antes do primario)
        self.btn_cancel = ctk.CTkButton(
            btn_row, text="Cancelar", width=90, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._cancel,
        )
        self.btn_cancel.pack(side="right", padx=(4, 0))

        # Importar (primario = azul accent)
        self.btn_import = ctk.CTkButton(
            btn_row, text="Importar", width=90, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._import,
            state="disabled",
        )
        self.btn_import.pack(side="right", padx=(0, 4))

        # Atualizar Preview (acao auxiliar, esquerda dos principais)
        self.btn_preview = ctk.CTkButton(
            btn_row, text="Atualizar Preview", width=130, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._update_preview,
            state="disabled",
        )
        self.btn_preview.pack(side="right", padx=(0, 8))
        self._toggle_advanced_section(force=False)
        self._set_source_mode("file")

    def _toggle_advanced_section(self, force: Optional[bool] = None) -> None:
        """Mostra ou oculta opções avançadas sem alterar o fluxo legado."""
        expanded = bool(self.advanced_section_expanded_var.get())
        if force is not None:
            expanded = bool(force)
        else:
            expanded = not expanded

        self.advanced_section_expanded_var.set(expanded)
        if expanded:
            self.advanced_section_body.pack(fill="x", padx=0, pady=(0, 12))
            self.advanced_toggle_button.configure(text="Ocultar opções avançadas")
        else:
            self.advanced_section_body.pack_forget()
            self.advanced_toggle_button.configure(text="Mostrar opções avançadas")

    def _refresh_stopword_status(self) -> None:
        total = len(set(self._global_stopwords + self._project_stopwords + self._session_stopwords))
        self.stopwords_status_label.configure(
            text=(
                f"Base fixa + global({len(self._global_stopwords)}) + "
                f"projeto({len(self._project_stopwords)}) + "
                f"sessao({len(self._session_stopwords)}) = {total} termo(s) customizado(s)"
            )
        )

    def _add_manual_stopwords(self) -> None:
        raw = str(self.stopwords_manual_var.get() or "")
        terms = parse_stopwords_text(raw)
        if not terms:
            return
        merged = sorted(set(self._session_stopwords).union(terms))
        self._session_stopwords = merged
        self.stopwords_manual_var.set("")
        self._refresh_stopword_status()
        if self._file_path or self._file_paths:
            self._update_preview()

    def _clear_session_stopwords(self) -> None:
        self._session_stopwords = []
        self.stopwords_manual_var.set("")
        self._refresh_stopword_status()
        if self._file_path or self._file_paths:
            self._update_preview()

    def _import_stopword_dictionary(self) -> None:
        selected = filedialog.askopenfilename(
            title="Selecionar dicionario de stopwords",
            filetypes=[("Texto/CSV", "*.txt *.csv"), ("Todos", "*.*")],
        )
        if not selected:
            return
        try:
            loaded = parse_stopwords_file(Path(selected))
        except Exception as exc:
            self.stopwords_status_label.configure(text=f"Falha ao ler dicionario: {exc}")
            return
        if not loaded:
            return
        merged = sorted(set(self._session_stopwords).union(loaded))
        self._session_stopwords = merged
        self._refresh_stopword_status()
        if self._file_path or self._file_paths:
            self._update_preview()

    def _get_stopword_layers(self) -> Dict[str, List[str]]:
        return {
            "global": list(self._global_stopwords),
            "project": list(self._project_stopwords),
            "session": list(self._session_stopwords),
        }

    # ------------------------------------------------------------------
    # Source mode
    # ------------------------------------------------------------------

    _SOURCE_LABELS = {
        "file":   "Selecione um ou mais arquivos suportados (.txt, .md, .json, .net, .pdf, .docx, .odt, .xlsx, .csv).",
        "folder": "Selecione uma pasta. Todos os formatos suportados serao importados como documentos separados.",
        "zip":    "Selecione um arquivo .zip com formatos suportados dentro. Cada arquivo = um documento.",
    }

    @staticmethod
    def _lighten_hex_color(color: str, factor: float = 0.22) -> str:
        """Clareia cor hexadecimal misturando com branco."""
        raw = str(color or "").strip()
        if not raw.startswith("#") or len(raw) != 7:
            return "#2B88D8"
        try:
            r = int(raw[1:3], 16)
            g = int(raw[3:5], 16)
            b = int(raw[5:7], 16)
            k = max(0.0, min(1.0, float(factor)))
            lr = int(round(r + (255 - r) * k))
            lg = int(round(g + (255 - g) * k))
            lb = int(round(b + (255 - b) * k))
            return f"#{lr:02X}{lg:02X}{lb:02X}"
        except Exception:
            return "#2B88D8"

    def _format_selected_source(self) -> str:
        """Texto amigável para exibir a origem selecionada."""
        if self._source_mode == "file":
            if not self._file_paths:
                return ""
            if len(self._file_paths) == 1:
                return str(self._file_paths[0])
            first = self._file_paths[0]
            return f"{len(self._file_paths)} arquivos selecionados  •  primeiro: {first.name}"
        return str(self._file_path or "")

    @staticmethod
    def _sanitize_doc_name(raw_name: str) -> str:
        """Normaliza nome para token de variável IRaMuTeQ."""
        normalized = unicodedata.normalize("NFD", str(raw_name or "").strip())
        normalized = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", normalized).lower()
        safe = re.sub(r"_+", "_", safe).strip("_")
        return safe or "doc"

    def _build_multi_file_collection(
        self,
        file_paths: List[Path],
        progress_callback,
    ) -> tuple[str, Dict[str, Any], List[str]]:
        """
        Importa múltiplos arquivos e monta uma coleção interna compatível com o fluxo atual.

        Retorna:
          extracted_text: texto concatenado (modo tradicional)
          import_metadata: metadados de coleção (inclui iramuteq_text)
          warnings: avisos acumulados dos importadores
        """
        from ...importers import get_importer_for_file
        from ...importers.text_cleaning import limpar_texto

        documents: List[Dict[str, Any]] = []
        warnings: List[str] = []
        iramuteq_blocks: List[str] = []
        raw_parts: List[str] = []

        total = max(1, len(file_paths))
        for idx, path in enumerate(file_paths):
            progress_callback(0.10 + 0.70 * (idx / total), f"Importando {path.name} ({idx + 1}/{len(file_paths)})...")
            importer = get_importer_for_file(str(path))
            result = importer.extract(str(path))
            file_warnings = list(result.warnings or [])
            warnings.extend(file_warnings)
            metadata = dict(result.metadata or {})
            extracted = str(result.text or "").strip()
            if extracted:
                extracted = limpar_texto(extracted, min_line_chars=20)

            if extracted:
                raw_parts.append(f"===== {path.name} =====\n{extracted}")

            iramuteq_chunk = str(metadata.get("iramuteq_text") or "").strip()
            if "****" in iramuteq_chunk:
                iramuteq_blocks.append(iramuteq_chunk)
            elif extracted:
                safe_name = self._sanitize_doc_name(path.stem)
                iramuteq_blocks.append(f"**** *doc_{safe_name}\n{extracted}")

            documents.append(
                {
                    "name": path.stem,
                    "filename": path.name,
                    "path": str(path),
                    "text": extracted,
                    "warnings": file_warnings,
                }
            )

        progress_callback(0.86, "Montando coleção...")
        lines: List[str] = [""]
        for chunk in iramuteq_blocks:
            lines.append(chunk.strip())
            lines.append("")
        iramuteq_text = "\n".join(lines)
        extracted_text = "\n\n".join(raw_parts).strip()

        import_metadata: Dict[str, Any] = {
            "collection_mode": True,
            "source_type": "multi_file",
            "document_count": len(documents),
            "documents": documents,
            "iramuteq_text": iramuteq_text,
            "selected_files": [str(p) for p in file_paths],
        }
        return extracted_text, import_metadata, warnings

    @staticmethod
    def _build_traditional_collection_text(text: str, metadata: Optional[Dict[str, Any]]) -> str:
        """Reconstrói coleção em texto com marcadores de documento para modo tradicional."""
        if not isinstance(metadata, dict) or not metadata.get("collection_mode"):
            body = str(text or "").strip()
            return f"**** *doc_1\n{body}" if body else ""

        documents = metadata.get("documents", [])
        if not isinstance(documents, list) or not documents:
            body = str(text or "").strip()
            return f"**** *doc_1\n{body}" if body else ""

        blocks: List[str] = []
        for idx, item in enumerate(documents, start=1):
            if not isinstance(item, dict):
                continue
            body = str(item.get("text") or "").strip()
            if not body:
                continue
            raw_name = str(item.get("name") or item.get("filename") or f"doc_{idx}")
            folded = unicodedata.normalize("NFD", raw_name)
            folded = "".join(c for c in folded if unicodedata.category(c) != "Mn")
            token = re.sub(r"[^a-zA-Z0-9_]+", "_", folded).lower()
            token = re.sub(r"_+", "_", token).strip("_")
            if not token:
                token = f"doc_{idx}"
            blocks.append(f"**** *doc_{token}\n{body}")

        if blocks:
            return "\n\n".join(blocks).strip()
        body = str(text or "").strip()
        return f"**** *doc_1\n{body}" if body else ""

    def _set_source_mode(self, mode: str) -> None:
        """Alterna modo de origem: file | folder | zip."""
        self._source_mode = mode
        self._file_path = None
        self._file_paths = []
        self.file_entry.configure(state="normal")
        self.file_entry.delete(0, "end")
        self.file_entry.configure(state="disabled")
        self.btn_preview.configure(state="disabled")
        self.btn_import.configure(state="disabled")
        self.btn_open_bigram_dialog.configure(state="disabled")

        # Feedback visual dos botões de modo
        selected_bg = get_themed_color("primary")
        selected_hover = get_themed_color("primary_hover")
        normal = get_themed_color("button")
        normal_hover = get_themed_color("button_hover")

        for button, key in (
            (self.btn_src_file, "file"),
            (self.btn_src_folder, "folder"),
            (self.btn_src_zip, "zip"),
        ):
            selected = key == mode
            button.configure(
                fg_color=selected_bg if selected else normal,
                hover_color=selected_hover if selected else normal_hover,
                text_color=("#FFFFFF", "#FFFFFF") if selected else get_themed_color("text"),
            )

        self.source_desc_label.configure(text=self._SOURCE_LABELS.get(mode, ""))

    def _browse_file(self):
        """Abre diálogo de seleção de acordo com o modo de origem."""
        if self._source_mode == "folder":
            chosen = filedialog.askdirectory(
                title="Selecionar pasta com documentos",
            )
            if chosen:
                self._file_path = Path(chosen)
        elif self._source_mode == "zip":
            chosen = filedialog.askopenfilename(
                title="Selecionar arquivo ZIP",
                filetypes=[("ZIP", "*.zip")],
            )
            if chosen:
                self._file_path = Path(chosen)
        else:  # file
            filetypes = [
                ("Todos suportados", "*.txt *.md *.json *.net *.pdf *.docx *.odt *.xlsx *.csv"),
                ("Texto", "*.txt"),
                ("Markdown", "*.md"),
                ("JSON", "*.json"),
                ("NET", "*.net"),
                ("PDF", "*.pdf"),
                ("Word/OpenDocument", "*.docx *.odt"),
                ("Excel", "*.xlsx *.csv"),
            ]
            chosen = filedialog.askopenfilenames(
                title="Selecionar arquivos",
                filetypes=filetypes,
            )
            if chosen:
                self._file_paths = [Path(item) for item in chosen]
                self._file_path = self._file_paths[0]

        has_selection = bool(self._file_paths) if self._source_mode == "file" else bool(self._file_path)
        if has_selection:
            self.file_entry.configure(state="normal")
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, self._format_selected_source())
            self.file_entry.configure(state="disabled")
            self.btn_preview.configure(state="normal")
            self._update_preview()

    def _update_preview(self):
        """Atualiza preview do texto sem bloquear a UI."""
        has_source = bool(self._file_paths) if self._source_mode == "file" else bool(self._file_path)
        if not has_source or self._preview_running:
            return

        self._preview_running = True
        self.btn_import.configure(state="disabled")
        self.btn_preview.configure(state="disabled")
        self.btn_open_bigram_dialog.configure(state="disabled")
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", "Processando arquivo...\n")
        self.preview_text.configure(state="disabled")
        self._set_preview_progress(0.01, "Iniciando importacao...")

        worker = threading.Thread(target=self._preview_worker, daemon=True)
        worker.start()

    def _preview_worker(self) -> None:
        """Executa extracao/limpeza em thread de fundo para manter UI responsiva."""
        if self._source_mode == "file" and not self._file_paths:
            self._finish_preview_error("Arquivo nao selecionado.")
            return
        if self._source_mode != "file" and not self._file_path:
            self._finish_preview_error("Arquivo nao selecionado.")
            return

        try:
            from ...importers import get_importer_for_file
            from ...importers.corpus_validator import CorpusValidator
            from ...importers.iramuteq_adapter import IramuteqAutoAdapter
            from ...core.stopword_layers import merge_stopword_layers
            from ...core.import_processing_cache import ImportProcessingCache
            from ...core.r_text_pipeline import RTextPipeline

            log.info("Atualizando preview para: %s (modo=%s)", self._file_path, self._source_mode)

            def _progress_callback(progress: float, message: str = "") -> None:
                self._safe_after(lambda: self._set_preview_progress(progress, message))

            selected_mode = str(self.mode_var.get() or "traditional")
            stopword_layers = self._get_stopword_layers()
            extra_stopwords = merge_stopword_layers(
                global_words=stopword_layers["global"],
                project_words=stopword_layers["project"],
                session_words=stopword_layers["session"],
            )
            source_paths = self._file_paths if self._source_mode == "file" and self._file_paths else [self._file_path]
            source_paths = [Path(path) for path in source_paths if path is not None]
            pipeline = RTextPipeline()
            cache = ImportProcessingCache()
            phase1_options = {
                "lowercase": False,
                "remove_numbers": False,
                "remove_accents": False,
                "clean_web_data": False,
                "detect_bigrams": False,
                "aggressive_noise_filter": True,
            }
            cache_key = cache.build_key(
                source_paths=source_paths,
                mode=selected_mode,
                options=phase1_options,
                stopwords=extra_stopwords,
                pipeline_hash=(
                    pipeline.script_hash()
                    if hasattr(pipeline, "script_hash")
                    else pipeline.__class__.__name__
                ),
            )
            cached_payload = cache.get(cache_key)

            if cached_payload is not None:
                _progress_callback(0.80, "Carregando importação do cache...")
                extracted_text = str(cached_payload.get("extracted_text", "") or "")
                source_text = str(cached_payload.get("source_text", "") or "")
                cleaned_text = str(cached_payload.get("prepared_text", "") or "")
                preview_full = str(cached_payload.get("preview_text", "") or cleaned_text)
                bigram_candidates = []
                import_metadata = dict(cached_payload.get("metadata", {}) or {})
                import_metadata["cache_hit"] = True
            else:
                if self._source_mode == "file" and len(self._file_paths) > 1:
                    extracted_text, import_metadata, multi_warnings = self._build_multi_file_collection(
                        self._file_paths,
                        _progress_callback,
                    )
                    if multi_warnings:
                        import_metadata["warnings"] = multi_warnings
                else:
                    importer = get_importer_for_file(str(self._file_path))
                    if hasattr(importer, "set_progress_callback"):
                        importer.set_progress_callback(_progress_callback)
                    else:
                        _progress_callback(0.15, "Lendo arquivo...")
                    result = importer.extract(str(self._file_path))
                    extracted_text = result.text
                    import_metadata = dict(result.metadata or {})

                _progress_callback(0.82, "Aplicando limpeza estrutural...")
                is_collection = bool(import_metadata.get("collection_mode", False))

                if selected_mode == "iramuteq":
                    if is_collection:
                        source_text = import_metadata.get("iramuteq_text") or extracted_text
                    else:
                        adapter = IramuteqAutoAdapter()
                        source_text = import_metadata.get("iramuteq_text") or extracted_text
                        source_text = adapter.to_iramuteq(
                            source_text,
                            source_file=str(self._file_path),
                            source_label=self._file_path.stem,
                        )
                else:
                    source_text = self._build_traditional_collection_text(extracted_text, import_metadata)

                _progress_callback(0.93, "Executando pipeline textual em R...")
                pipeline_result = pipeline.run(
                    text=source_text,
                    mode=selected_mode,
                    lowercase=False,
                    remove_numbers=False,
                    remove_accents=False,
                    clean_web_data=False,
                    detect_bigrams=False,
                    selected_bigrams=[],
                    extra_stopwords=extra_stopwords,
                    bigram_top_n=20,
                    bigram_min_freq=2,
                    aggressive_noise_filter=True,
                )
                cleaned_text = pipeline_result.prepared_text
                preview_full = pipeline_result.preview_text or cleaned_text
                bigram_candidates = []
                import_metadata["cache_hit"] = False
                cache.put(
                    cache_key,
                    {
                        "extracted_text": extracted_text,
                        "source_text": source_text,
                        "prepared_text": cleaned_text,
                        "preview_text": preview_full,
                        "metadata": import_metadata,
                    },
                )

            import_metadata["r_pipeline_source_text"] = source_text
            import_metadata["r_pipeline_prepared_text"] = cleaned_text
            import_metadata.setdefault("r_pipeline_diagnostics", {})
            import_metadata["custom_stopwords_session"] = list(self._session_stopwords)
            import_metadata["custom_stopwords_project"] = list(self._project_stopwords)
            import_metadata["custom_stopwords_global"] = list(self._global_stopwords)
            if selected_mode == "iramuteq":
                import_metadata["iramuteq_text"] = cleaned_text
                _progress_callback(0.97, "Validando corpus...")
                report = CorpusValidator().validate(cleaned_text)
                if report.errors:
                    error_lines = "\n".join(
                        f"- Linha {issue.line_number}: {issue.what}"
                        for issue in report.errors[:5]
                    )
                    preview_full += (
                        "\n\n[ALERTA]\n"
                        "Ainda ha inconsistencias de metadados:\n"
                        f"{error_lines}"
                    )
                if report.warnings:
                    warning_lines = "\n".join(f"- {warning}" for warning in report.warnings[:5])
                    preview_full += f"\n\n[AVISOS]\n{warning_lines}"
            else:
                import_metadata["traditional_text_prepared"] = cleaned_text
            extracted_text = cleaned_text

            is_collection = bool(import_metadata.get("collection_mode", False))
            if is_collection:
                docs = import_metadata.get("documents", [])
                doc_count = import_metadata.get("document_count", len(docs))
                source_type = import_metadata.get("source_type", "collection")
                source_label = (
                    import_metadata.get("zip_name")
                    or import_metadata.get("folder_name")
                    or f"{doc_count} arquivo(s)"
                    or str(self._file_path.name)
                )
                doc_list = "\n".join(
                    f"  [{i+1}] {d.get('filename', d.get('name', '?'))}"
                    for i, d in enumerate(docs[:15])
                )
                extra = f"\n  ... e mais {doc_count - 15} documento(s)" if doc_count > 15 else ""
                collection_summary = (
                    f"=== COLECAO IMPORTADA ({source_type.upper()}) ===\n"
                    f"Origem: {source_label}\n"
                    f"Documentos importados: {doc_count}\n"
                    f"{doc_list}{extra}\n"
                    f"{'='*40}\n\n"
                )
                preview_full = collection_summary + preview_full

            preview = preview_full[:2000]
            if len(preview_full) > 2000:
                preview += "\n\n[... texto truncado para preview ...]"

            self._safe_after(
                lambda: self._finish_preview_success(
                    preview=preview,
                    extracted_text=extracted_text,
                    import_metadata=import_metadata,
                    mode=selected_mode,
                    bigram_candidates=bigram_candidates,
                )
            )
        except Exception as exc:
            log.exception("Falha ao atualizar preview de importacao")
            self._safe_after(lambda err=exc: self._finish_preview_error(str(err)))

    def _safe_after(self, callback) -> None:
        """Executa callback na UI thread se dialogo ainda existir."""
        try:
            if self.winfo_exists():
                self.after(0, callback)
        except Exception:
            pass

    def _open_bigram_selection_dialog(self) -> None:
        """Abre dialogo de selecao de bigramas."""
        if self._bigram_dialog_open or not self._bigram_candidates:
            return

        self._bigram_dialog_open = True

        def on_confirm(selected: List[Dict[str, Any]]) -> None:
            self._selected_bigrams_cache = selected
            self._update_bigram_status_label()
            self._bigram_dialog_open = False

        def on_close() -> None:
            self._bigram_dialog_open = False

        from .bigram_selection_dialog import BigramSelectionDialog
        BigramSelectionDialog(
            parent=self,
            candidates=self._bigram_candidates,
            on_confirm=on_confirm,
        )

        self._bigram_dialog_open = False
        self._update_bigram_status_label()

    def _update_bigram_status_label(self) -> None:
        """Atualiza label de status dos bigramas."""
        count = len(self._selected_bigrams_cache)
        total = len(self._bigram_candidates)

        if total == 0:
            self.bigram_status_label.configure(text="Nenhuma sugestao disponivel")
        elif count == 0:
            self.bigram_status_label.configure(text=f"{total} sugeridos, nenhum selecionado")
        elif count == 1:
            self.bigram_status_label.configure(text="1 expressao selecionada")
        else:
            self.bigram_status_label.configure(text=f"{count} expressoes selecionadas")

    def _set_bigram_candidates(self, mode: str, candidates: Optional[List[Dict[str, Any]]]) -> None:
        """Preenche lista de candidatos de bigramas detectados no preview."""
        normalized = []
        for item in candidates or []:
            if not isinstance(item, dict):
                continue
            expression  = str(item.get("expression", "")).strip()
            replacement = str(item.get("replacement", "")).strip()
            frequency   = int(item.get("frequency", 0) or 0)
            if not expression or not replacement or frequency <= 0:
                continue
            normalized.append({"expression": expression, "replacement": replacement, "frequency": frequency})

        self._bigram_candidates = normalized
        self._selected_bigrams_cache = []

        if not self._bigram_candidates:
            self.bigram_status_label.configure(text="Nenhuma expressao frequente encontrada")
            self.btn_open_bigram_dialog.configure(state="disabled")
        else:
            count = len(self._bigram_candidates)
            self.bigram_status_label.configure(text=f"{count} sugerida(s), nenhuma selecionada")
            self.btn_open_bigram_dialog.configure(state="normal")

    def _collect_selected_bigrams(self) -> List[Dict[str, Any]]:
        """Retorna payload de bigramas selecionados para aplicar na importacao."""
        return self._selected_bigrams_cache

    def _set_preview_progress(self, progress: float, message: str = "") -> None:
        """Atualiza barra de progresso e mensagem do preview."""
        value = max(0.0, min(1.0, float(progress or 0.0)))
        self.preview_progress.set(value)
        if message:
            self.preview_status_label.configure(text=message)

    def _finish_preview_success(
        self,
        preview: str,
        extracted_text: str,
        import_metadata: Dict[str, Any],
        mode: str,
        bigram_candidates: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Finaliza preview com sucesso."""
        self._extracted_text = extracted_text
        self._import_metadata = import_metadata
        self._set_bigram_candidates(mode=mode, candidates=bigram_candidates)
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", preview)
        self.preview_text.configure(state="disabled")
        self.btn_import.configure(state="normal")
        self.btn_preview.configure(state="normal")
        self._set_preview_progress(1.0, "Preview atualizado.")
        self._preview_running = False

    def _finish_preview_error(self, error_message: str) -> None:
        """Finaliza preview com erro."""
        self._import_metadata = {}
        self._set_bigram_candidates(mode=str(self.mode_var.get() or "traditional"), candidates=[])
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", f"ERRO ao carregar arquivo:\n\n{error_message}")
        self.preview_text.configure(state="disabled")
        self.btn_import.configure(state="disabled")
        self.btn_preview.configure(state="normal")
        self._set_preview_progress(0.0, "Falha ao processar arquivo.")
        self._preview_running = False

    def _import(self):
        """Confirma importacao."""
        selected_bigrams = self._collect_selected_bigrams()
        self._result = {
            'file_path': self._file_path,
            'text':      self._extracted_text,
            'metadata':  self._import_metadata,
            'mode':      self.mode_var.get(),
            'options': {
                'lowercase':           self.lowercase_var.get(),
                'remove_numbers':      self.remove_numbers_var.get(),
                'remove_accents':      self.remove_accents_var.get(),
                'clean_web_data':      self.clean_web_data_var.get(),
                'uce_size':            int(self.uce_size_var.get()),
                'enable_bigram_merge': len(selected_bigrams) > 0,
                'selected_bigrams':    selected_bigrams,
                'session_stopwords':   list(self._session_stopwords),
                'persist_project_stopwords': bool(self.persist_project_stopwords_var.get()),
                'persist_global_stopwords':  bool(self.persist_global_stopwords_var.get()),
            }
        }
        self.destroy()

    def _cancel(self):
        """Cancela importacao."""
        self._result = None
        self.destroy()

    def get_result(self) -> Optional[Dict[str, Any]]:
        """Retorna resultado da importacao."""
        return self._result
