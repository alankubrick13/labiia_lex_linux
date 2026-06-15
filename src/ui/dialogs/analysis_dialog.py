"""
Dialogos de configuracao de analises.
"""
import customtkinter as ctk
from typing import Optional, Dict, Any

from ..styles import FONTS, COLORS, get_themed_color
from ..iconography import create_help_button, label_with_icon
from ..tk_helpers import cleanup_widget_menus

SIMILARITY_LAYOUT_OPTIONS = [
    "random",
    "circle",
    "frutch",
    "kawa",
    "graphopt",
    "spirale",
    "spirale3D",
]

SIMILARITY_COEFFICIENT_OPTIONS = [
    "cooccurrence",
    "percentual de coocorrência",
    "Russel",
    "Jaccard",
    "Kulczynski1",
    "Kulczynski2",
    "Mountford",
    "Fager",
    "simple matching",
    "Hamman",
    "Faith",
    "Tanimoto",
    "Dice",
    "Phi",
    "Stiles",
    "Michael",
    "Mozley",
    "Yule",
    "Yule2",
    "Ochiai",
    "Simpson",
    "Braun-Blanquet",
    "Chi-squared",
    "Phi-squared",
    "Tschuprow",
    "Cramer",
    "Pearson",
    "binomial",
]

SIMILARITY_COMMUNITY_OPTIONS = [
    "edge_betweenness",
    "fastgreedy",
    "label_propagation",
    "leading_eigenvector",
    "multilevel",
    "louvain",
    "optimal",
    "spinglass",
    "walktrap",
]


class BaseAnalysisDialog(ctk.CTkToplevel):
    """Classe base para dialogos de analise."""
    ANALYSIS_TYPE: Optional[str] = None

    def __init__(
        self,
        parent,
        title: str,
        width: int = 450,
        height: int = 500,
        initial_params: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(True, True)
        self.minsize(400, 400)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._result: Optional[Dict[str, Any]] = None
        self._cancelled = True
        self._initial_params: Dict[str, Any] = dict(initial_params or {})
        self._is_destroying: bool = False

        self._create_base_widgets()
        self._create_params_widgets()
        self._center_on_parent(parent)
    
    def create_help_icon(self, parent, text: str):
        """Cria botão de ajuda padronizado com tooltip."""
        return create_help_button(parent, text, size=18)

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
    
    def _create_base_widgets(self):
        """Cria estrutura base."""
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Botoes (fixo no topo, sempre visivel)
        self.btn_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.btn_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            self.btn_frame,
            text="Cancelar", width=90, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._cancel
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            self.btn_frame,
            text="Executar", width=90, height=26,
            fg_color=get_themed_color("button"),
            hover_color=get_themed_color("button_hover"),
            text_color=get_themed_color("text"),
            border_width=1, border_color=get_themed_color("border"),
            corner_radius=3,
            command=self._execute
        ).pack(side="right", padx=(0, 4))

        # Container rolavel para parametros (subclasses preenchem)
        self.params_frame = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        self.params_frame.pack(fill="both", expand=True)
    
    def _create_params_widgets(self):
        """Subclasses implementam para adicionar parametros."""
        pass
    
    def _build_result(self) -> Dict[str, Any]:
        """Subclasses implementam para construir resultado."""
        return {}

    def _initial_int(self, key: str, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
        """Return integer initial value with optional bounds."""
        raw_value = self._initial_params.get(key, default)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            value = int(default)
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value

    def _initial_str(self, key: str, default: str, allowed: Optional[list] = None) -> str:
        """Return string initial value constrained to allowed set if provided."""
        value = str(self._initial_params.get(key, default) or default)
        if allowed and value not in allowed:
            return default
        return value

    def _initial_bool(self, key: str, default: bool) -> bool:
        """Return boolean initial value."""
        value = self._initial_params.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "sim"}
        return bool(value)

    def _initial_float(
        self,
        key: str,
        default: float,
        minimum: Optional[float] = None,
        maximum: Optional[float] = None,
    ) -> float:
        """Return float initial value with optional bounds."""
        raw_value = self._initial_params.get(key, default)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            value = float(default)
        if minimum is not None:
            value = max(minimum, value)
        if maximum is not None:
            value = min(maximum, value)
        return value
    
    def _execute(self):
        """Confirma execucao."""
        result = self._build_result() or {}
        analysis_type = result.get('analysis_type') or self.ANALYSIS_TYPE
        if analysis_type:
            result['analysis_type'] = analysis_type
        self._result = result
        self._cancelled = False
        self.destroy()
    
    def _cancel(self):
        """Cancela execucao."""
        self._result = None
        self._cancelled = True
        self.destroy()

    def destroy(self):
        """Destroi dialogo limpando menus internos para evitar vazamento de Tk menus."""
        if self._is_destroying:
            return
        self._is_destroying = True
        try:
            cleanup_widget_menus(self)
        except Exception:
            pass
        try:
            self.grab_release()
        except Exception:
            pass
        try:
            super().destroy()
        finally:
            self._is_destroying = False
    
    def get_result(self) -> Optional[Dict[str, Any]]:
        """Retorna resultado ou None se cancelado."""
        self.wait_window()
        return self._result


class StatisticsDialog(BaseAnalysisDialog):
    """Dialogo para estatisticas basicas."""
    ANALYSIS_TYPE = 'statistics'
    
    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Estatísticas do Corpus",
            400,
            200,
            initial_params=initial_params,
        )
    
    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=20)
        
        ctk.CTkLabel(
            title_frame,
            text="Estatísticas Básicas",
            font=FONTS['title']
        ).pack(side="left", padx=5)
        
        self.create_help_icon(title_frame, "Calcula métricas fundamentais como número de documentos, ocorrências e formas únicas.").pack(side="left")

        ctk.CTkLabel(
            self.params_frame,
            text="Calcular estatísticas descritivas do corpus:\n\n"
                 "• Número de documentos (UCIs)\n"
                 "• Número de segmentos (UCEs)\n"
                 "• Número de formas (palavras únicas)\n"
                 "• Número de ocorrências",
            font=FONTS['body'],
            justify="left"
        ).pack(pady=10)
    
    def _build_result(self) -> Dict[str, Any]:
        return {'analysis_type': 'statistics'}


class CHDDialog(BaseAnalysisDialog):
    """Dialogo para analise CHD (Reinert)."""
    ANALYSIS_TYPE = 'chd'

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Classificação Hierárquica Descendente",
            500,
            580,
            initial_params=initial_params,
        )
    
    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text="CHD - Método Reinert",
            font=FONTS['title']
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Algoritmo de Classificação Hierárquica Descendente para agrupar segmentos de texto similares.").pack(side="left")

        self.strict_iramuteq_clone_var = ctk.BooleanVar(
            value=self._initial_bool("strict_iramuteq_clone", True)
        )
        strict_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        strict_frame.pack(anchor="w", padx=10, pady=(0, 8))
        
        ctk.CTkCheckBox(
            strict_frame,
            text="Modo fiel IRaMuTeQ (recomendado)",
            variable=self.strict_iramuteq_clone_var,
        ).pack(side="left")
        self.create_help_icon(strict_frame, "Tenta replicar exatamente os algoritmos e resultados do Iramuteq original.").pack(side="left", padx=5)
        
        # Numero de classes
        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row1,
            text="Número de classes:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.n_classes_var = ctk.IntVar(
            value=self._initial_int("n_classes", 5, minimum=2, maximum=10)
        )
        ctk.CTkSlider(
            row1,
            from_=2,
            to=10,
            number_of_steps=8,
            variable=self.n_classes_var,
            width=150
        ).pack(side="left", padx=10)
        
        self.n_classes_label = ctk.CTkLabel(
            row1,
            text=str(self.n_classes_var.get()),
            width=30,
        )
        self.n_classes_label.pack(side="left")
        self.n_classes_var.trace_add("write", lambda *_: self.n_classes_label.configure(text=str(self.n_classes_var.get())))

        self.create_help_icon(row1, "Quantidade desejada de grupos (classes) de vocabulário.").pack(side="left", padx=5)
        
        # Frequencia minima
        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row2,
            text="Frequência mínima:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 2, minimum=1))
        ctk.CTkEntry(
            row2,
            textvariable=self.min_freq_var,
            width=80
        ).pack(side="left", padx=10)

        self.create_help_icon(row2, "Palavras com menos ocorrências que este valor serão ignoradas na análise.").pack(side="left", padx=5)

        row2b = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2b.pack(fill="x", pady=5)

        ctk.CTkLabel(
            row2b,
            text="Mín. ST por classe:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")

        self.min_uce_var = ctk.IntVar(
            value=self._initial_int("min_uce", 0, minimum=0, maximum=99999)
        )
        ctk.CTkEntry(
            row2b,
            textvariable=self.min_uce_var,
            width=80
        ).pack(side="left", padx=10)
        ctk.CTkLabel(
            row2b,
            text="(0 = automático)",
            font=FONTS['small'],
            text_color=get_themed_color('text_secondary'),
        ).pack(side="left")
        self.create_help_icon(
            row2b,
            "Mínimo de segmentos de texto por classe terminal (IRaMuTeQ: 0 automático).",
        ).pack(side="left", padx=5)

        row_ma = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_ma.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row_ma,
            text="Máx. formas ativas:",
            font=FONTS['body'],
            width=180,
        ).pack(side="left")
        
        self.max_actives_var = ctk.IntVar(
            value=self._initial_int("max_actives", 20000, minimum=0, maximum=30000)
        )
        ctk.CTkEntry(
            row_ma,
            textvariable=self.max_actives_var,
            width=80,
        ).pack(side="left", padx=10)
        ctk.CTkLabel(
            row_ma,
            text="(0 = sem limite)",
            font=FONTS['small'],
            text_color=get_themed_color('text_secondary'),
        ).pack(side="left")

        self.create_help_icon(row_ma, "Limite de palavras analisadas para otimizar performance (0 = sem limite).").pack(side="left", padx=5)
        
        # Metodo
        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row3,
            text="Método de clustering:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.method_var = ctk.StringVar(
            value=self._initial_str(
                "method",
                "ward.D2",
                allowed=["ward.D2", "ward.D", "complete", "average"],
            )
        )
        ctk.CTkOptionMenu(
            row3,
            values=["ward.D2", "ward.D", "complete", "average"],
            variable=self.method_var,
            width=150
        ).pack(side="left", padx=10)

        self.create_help_icon(row3, "Algoritmo estatístico usado para agrupar os segmentos de texto.").pack(side="left", padx=5)

        # Modo de classificacao
        row4 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row4.pack(fill="x", pady=(10, 5))
        ctk.CTkLabel(
            row4,
            text="Modo de classificação:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.create_help_icon(row4, "Define como o corpus será dividido em segmentos (UCE vs UCI) ou método Double.").pack(side="left", padx=(0, 5))
        
        self.classif_mode_var = ctk.IntVar(
            value=self._initial_int("classif_mode", 1, minimum=0, maximum=2)
        )

        mode_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        mode_frame.pack(fill="x", pady=(0, 5))
        ctk.CTkRadioButton(
            mode_frame,
            text="Simples UCE",
            variable=self.classif_mode_var,
            value=1,
            command=self._update_double_mode_visibility,
        ).pack(anchor="w", padx=20)
        ctk.CTkRadioButton(
            mode_frame,
            text="Simples UCI",
            variable=self.classif_mode_var,
            value=2,
            command=self._update_double_mode_visibility,
        ).pack(anchor="w", padx=20)
        ctk.CTkRadioButton(
            mode_frame,
            text="Double (duas tabelas)",
            variable=self.classif_mode_var,
            value=0,
            command=self._update_double_mode_visibility,
        ).pack(anchor="w", padx=20)

        # Tamanho UCE para modo double
        self.double_size_1_row = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        ctk.CTkLabel(
            self.double_size_1_row,
            text="Taille UCE 1:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.tailleuc1_var = ctk.IntVar(
            value=self._initial_int("tailleuc1", 12, minimum=5, maximum=120)
        )
        ctk.CTkSlider(
            self.double_size_1_row,
            from_=5,
            to=120,
            number_of_steps=23,
            variable=self.tailleuc1_var,
            width=150
        ).pack(side="left", padx=10)
        
        self.create_help_icon(self.double_size_1_row, "Tamanho do primeiro segmento para classificação dupla.").pack(side="left", padx=5)
        self.tailleuc1_label = ctk.CTkLabel(
            self.double_size_1_row,
            text=str(self.tailleuc1_var.get()),
            width=30,
        )
        self.tailleuc1_label.pack(side="left")
        self.tailleuc1_var.trace_add(
            "write",
            lambda *_: self.tailleuc1_label.configure(text=str(self.tailleuc1_var.get())),
        )

        self.double_size_2_row = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        ctk.CTkLabel(
            self.double_size_2_row,
            text="Taille UCE 2:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.tailleuc2_var = ctk.IntVar(
            value=self._initial_int("tailleuc2", 14, minimum=5, maximum=160)
        )
        ctk.CTkSlider(
            self.double_size_2_row,
            from_=5,
            to=160,
            number_of_steps=31,
            variable=self.tailleuc2_var,
            width=150
        ).pack(side="left", padx=10)

        self.create_help_icon(self.double_size_2_row, "Tamanho do segundo segmento para classificação dupla.").pack(side="left", padx=5)
        self.tailleuc2_label = ctk.CTkLabel(
            self.double_size_2_row,
            text=str(self.tailleuc2_var.get()),
            width=30,
        )
        self.tailleuc2_label.pack(side="left")
        self.tailleuc2_var.trace_add(
            "write",
            lambda *_: self.tailleuc2_label.configure(text=str(self.tailleuc2_var.get())),
        )
        self._update_double_mode_visibility()

        row5 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row5.pack(fill="x", pady=(8, 5))
        ctk.CTkLabel(
            row5,
            text="Tipo de dendrograma:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.dendro_type_var = ctk.StringVar(
            value=self._initial_str(
                "dendro_type",
                "profile",
                allowed=["profile", "cloud", "pie", "barplot"],
            )
        )
        ctk.CTkOptionMenu(
            row5,
            values=["profile", "cloud", "pie", "barplot"],
            variable=self.dendro_type_var,
            width=150,
        ).pack(side="left", padx=10)

        self.create_help_icon(row5, "Formato visual da árvore hierárquica (classes).").pack(side="left", padx=5)

        row6 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row6.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row6,
            text="Direção da árvore:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.direction_var = ctk.StringVar(
            value=self._initial_str(
                "direction",
                "downwards",
                allowed=["downwards", "rightwards"],
            )
        )
        ctk.CTkOptionMenu(
            row6,
            values=["downwards", "rightwards"],
            variable=self.direction_var,
            width=150,
        ).pack(side="left", padx=10)

        self.create_help_icon(row6, "Orientação do gráfico (vertical ou horizontal).").pack(side="left", padx=5)

        bw_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        bw_frame.pack(anchor="w", padx=10, pady=(2, 2))
        self.bw_var = ctk.BooleanVar(value=self._initial_bool("bw", False))
        ctk.CTkCheckBox(
            bw_frame,
            text="Modo preto e branco",
            variable=self.bw_var,
        ).pack(side="left")
        self.create_help_icon(bw_frame, "Gera gráficos em escalas de cinza (bom para impressão).").pack(side="left", padx=5)

        row7 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row7.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row7,
            text="Rótulos (opcional):",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        initial_lab = self._initial_params.get("lab")
        if isinstance(initial_lab, list):
            lab_text = ", ".join(str(item) for item in initial_lab)
        elif initial_lab is None:
            lab_text = ""
        else:
            lab_text = str(initial_lab)
        self.lab_var = ctk.StringVar(value=lab_text)
        ctk.CTkEntry(
            row7,
            textvariable=self.lab_var,
            width=200,
            placeholder_text="classe 1, classe 2, ...",
        ).pack(side="left", padx=10)

        self.create_help_icon(row7, "Nomes personalizados para as classes geradas (separados por vírgula).").pack(side="left", padx=5)
        
        # Informacao
        ctk.CTkLabel(
            self.params_frame,
            text="Nota: A análise pode levar alguns minutos\ndependendo do tamanho do corpus.",
            font=FONTS['small'],
            text_color=get_themed_color('text_secondary')
        ).pack(pady=20)
    
    def _build_result(self) -> Dict[str, Any]:
        raw_lab = self.lab_var.get().strip() if hasattr(self, "lab_var") else ""
        labels = [item.strip() for item in raw_lab.split(",") if item.strip()] if raw_lab else None
        strict_mode = bool(self.strict_iramuteq_clone_var.get())
        parity_profile = "official_0_8a7" if strict_mode else "legacy_current"
        render_profile = "native" if strict_mode else "publication_polish"
        return {
            'analysis_type': 'chd',
            'analysis_mode': 'strict' if strict_mode else 'legacy',
            'parity_profile': parity_profile,
            'render_profile': render_profile,
            'n_classes': self.n_classes_var.get(),
            'min_freq': self.min_freq_var.get(),
            'min_uce': self.min_uce_var.get(),
            'method': self.method_var.get(),
            'classif_mode': self.classif_mode_var.get(),
            'tailleuc1': self.tailleuc1_var.get(),
            'tailleuc2': self.tailleuc2_var.get(),
            'max_actives': self.max_actives_var.get(),
            'strict_iramuteq_clone': strict_mode,
            'prefer_readable_afc_profiles': False,
            'dendro_type': self.dendro_type_var.get(),
            'bw': self.bw_var.get(),
            'lab': labels,
            'direction': self.direction_var.get(),
        }

    def _update_double_mode_visibility(self):
        """Mostra/esconde parametros extras do modo double."""
        is_double = self.classif_mode_var.get() == 0
        if is_double:
            self.double_size_1_row.pack(fill="x", pady=5)
            self.double_size_2_row.pack(fill="x", pady=5)
        else:
            self.double_size_1_row.pack_forget()
            self.double_size_2_row.pack_forget()


class SimilarityDialog(BaseAnalysisDialog):
    """Dialogo para analise de similaridade."""
    ANALYSIS_TYPE = 'similarity'

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Análise de Similitude",
            500,
            600,
            initial_params=initial_params,
        )
    
    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text="Análise de Similitude",
            font=FONTS['title']
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Visualiza a estrutura das relações entre palavras baseada na coocorrência.").pack(side="left")

        self.strict_iramuteq_style_var = ctk.BooleanVar(
            value=self._initial_bool("strict_iramuteq_style", True)
        )
        strict_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        strict_frame.pack(anchor="w", padx=10, pady=(0, 8))
        
        ctk.CTkCheckBox(
            strict_frame,
            text="Modo fiel IRaMuTeQ (recomendado)",
            variable=self.strict_iramuteq_style_var,
            command=self._sync_similarity_clone_mode,
        ).pack(side="left")
        self.create_help_icon(strict_frame, "Mantém a compatibilidade visual e algorítmica com o Iramuteq.").pack(side="left", padx=5)
        
        # Layout do grafo
        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row1,
            text="Layout do grafo:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.layout_var = ctk.StringVar(
            value=self._initial_str(
                "layout",
                "frutch",
                allowed=SIMILARITY_LAYOUT_OPTIONS,
            )
        )
        self.layout_menu = ctk.CTkOptionMenu(
            row1,
            values=SIMILARITY_LAYOUT_OPTIONS,
            variable=self.layout_var,
            width=150
        )
        self.layout_menu.pack(side="left", padx=10)

        self.create_help_icon(row1, "Algoritmo usado para desenhar a posição dos nós (ex: Fruchterman-Reingold).").pack(side="left", padx=5)
        
        # Frequencia minima
        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row2,
            text="Frequência mínima:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 3, minimum=1))
        ctk.CTkEntry(
            row2,
            textvariable=self.min_freq_var,
            width=80
        ).pack(side="left", padx=10)

        self.create_help_icon(row2, "Apenas palavras que aparecem pelo menos X vezes entram no grafo.").pack(side="left", padx=5)

        lemma_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        lemma_frame.pack(anchor="w", padx=10, pady=(2, 4))
        self.use_lemmas_var = ctk.BooleanVar(
            value=self._initial_bool("use_lemmas", True)
        )
        ctk.CTkCheckBox(
            lemma_frame,
            text="Agrupar singular/plural (usar lemas)",
            variable=self.use_lemmas_var,
        ).pack(side="left")
        self.create_help_icon(lemma_frame, "Analisa pelo conceito (comer) em vez da forma exata (comeu/comi).").pack(side="left", padx=5)

        row_vs = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_vs.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row_vs,
            text="Tamanho vértices:",
            font=FONTS['body'],
            width=180,
        ).pack(side="left")
        
        self.vertex_scaling_var = ctk.StringVar(
            value=self._initial_str(
                "vertex_scaling",
                "frequency",
                allowed=["frequency", "chi2", "degree"],
            )
        )
        self.vertex_scaling_menu = ctk.CTkOptionMenu(
            row_vs,
            values=["frequency", "chi2", "degree"],
            variable=self.vertex_scaling_var,
            width=150,
        )
        self.vertex_scaling_menu.pack(side="left", padx=10)

        self.create_help_icon(row_vs, "O que define o tamanho da bolinha da palavra (Frequência ou Chi2).").pack(side="left", padx=5)
        
        # Coeficiente
        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row3,
            text="Coeficiente:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        initial_coef = str(self._initial_params.get("coefficient", "cooccurrence") or "cooccurrence").strip()
        if initial_coef.lower() == "pourcentage de cooccurrence":
            initial_coef = "percentual de coocorrência"
        if initial_coef not in SIMILARITY_COEFFICIENT_OPTIONS:
            initial_coef = "cooccurrence"
        self.coef_var = ctk.StringVar(value=initial_coef)
        ctk.CTkOptionMenu(
            row3,
            values=SIMILARITY_COEFFICIENT_OPTIONS,
            variable=self.coef_var,
            width=150
        ).pack(side="left", padx=10)

        self.create_help_icon(row3, "Fórmula estatística para calcular a força da ligação entre duas palavras.").pack(side="left", padx=5)

        row_min_edge = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_min_edge.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row_min_edge,
            text="Limiar de aresta:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.min_edge_var = ctk.IntVar(
            value=self._initial_int("min_edge", 0, minimum=0, maximum=30)
        )
        ctk.CTkSlider(
            row_min_edge,
            from_=0,
            to=30,
            number_of_steps=30,
            variable=self.min_edge_var,
            width=150,
        ).pack(side="left", padx=10)

        self.create_help_icon(row_min_edge, "Remove ligações fracas (abaixo deste valor) para limpar o gráfico.").pack(side="left", padx=5)
        self.min_edge_label = ctk.CTkLabel(
            row_min_edge,
            text=str(self.min_edge_var.get()),
            width=40,
        )
        self.min_edge_label.pack(side="left")
        self.min_edge_var.trace_add(
            "write",
            lambda *_: self.min_edge_label.configure(text=str(self.min_edge_var.get())),
        )

        row_word = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_word.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row_word,
            text="Subgrafo por termo:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.graph_word_var = ctk.StringVar(value=self._initial_str("graph_word", ""))
        ctk.CTkEntry(
            row_word,
            textvariable=self.graph_word_var,
            width=150,
            placeholder_text="(opcional)",
        ).pack(side="left", padx=10)

        self.create_help_icon(row_word, "Foca a análise apenas nas conexões desta palavra específica (opcional).").pack(side="left", padx=5)

        row_gexf = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_gexf.pack(fill="x", pady=5)
        initial_gexf = self._initial_str("gexf_output", "")
        self.export_gexf_var = ctk.BooleanVar(value=bool(initial_gexf))
        
        ctk.CTkCheckBox(
            row_gexf,
            text="Exportar GEXF",
            variable=self.export_gexf_var,
            command=self._toggle_similarity_gexf_entry,
        ).pack(side="left", padx=(6, 8))
        self.create_help_icon(row_gexf, "Salva arquivo para abrir no Gephi (software avançado de grafos).").pack(side="left", padx=5)
        
        self.gexf_output_var = ctk.StringVar(value=initial_gexf if initial_gexf else "similarity.gexf")
        self.gexf_entry = ctk.CTkEntry(
            row_gexf,
            textvariable=self.gexf_output_var,
            width=220,
            placeholder_text="caminho .gexf (opcional)",
        )
        self.gexf_entry.pack(side="left", padx=4)
        self._toggle_similarity_gexf_entry()

        # Formato do grafico
        row4 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row4.pack(fill="x", pady=5)

        ctk.CTkLabel(
            row4,
            text="Formato de saída:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")

        self.typegraph_var = ctk.StringVar(
            value=self._initial_str("typegraph", "png", allowed=["png", "svg"])
        )
        ctk.CTkOptionMenu(
            row4,
            values=["png", "svg"],
            variable=self.typegraph_var,
            width=150
        ).pack(side="left", padx=10)

        # Comunidades
        row5 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row5.pack(fill="x", pady=5)

        self.detect_communities_var = ctk.BooleanVar(
            value=self._initial_bool("detect_communities", False)
        )
        self.detect_communities_checkbox = ctk.CTkCheckBox(
            row5,
            text="Detectar comunidades automaticamente",
            variable=self.detect_communities_var
        )
        self.detect_communities_checkbox.pack(side="left", padx=10)

        row6 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row6.pack(fill="x", pady=5)

        ctk.CTkLabel(
            row6,
            text="Método da comunidade:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")

        self.community_method_var = ctk.StringVar(
            value=self._initial_str(
                "community_method",
                "edge_betweenness",
                allowed=SIMILARITY_COMMUNITY_OPTIONS + ["louvain"],
            )
        )
        self.community_method_menu = ctk.CTkOptionMenu(
            row6,
            values=SIMILARITY_COMMUNITY_OPTIONS,
            variable=self.community_method_var,
            width=150
        )
        self.community_method_menu.pack(side="left", padx=10)

        self.create_help_icon(row6, "Algoritmo de detecção de grupos (clusters).").pack(side="left", padx=5)

        # Maximo de palavras para selecao interativa
        row7 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row7.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row7,
            text="Máx. palavras (seletor):",
            font=FONTS['body'],
            width=180,
        ).pack(side="left")
        self.max_words_var = ctk.IntVar(
            value=self._initial_int("max_words", 80, minimum=10, maximum=300)
        )
        ctk.CTkSlider(
            row7,
            from_=10,
            to=300,
            number_of_steps=29,
            variable=self.max_words_var,
            width=150,
        ).pack(side="left", padx=10)
        self.max_words_label = ctk.CTkLabel(
            row7,
            text=str(self.max_words_var.get()),
            width=40,
        )
        self.max_words_label.pack(side="left")
        self.max_words_var.trace_add(
            "write",
            lambda *_: self.max_words_label.configure(text=str(self.max_words_var.get())),
        )

        # Arvore maxima (arbremax)
        self.arbremax_var = ctk.BooleanVar(value=self._initial_bool("arbremax", True))
        self.arbremax_checkbox = ctk.CTkCheckBox(
            self.params_frame,
            text="Usar árvore máxima (MST)",
            variable=self.arbremax_var
        )
        self.arbremax_checkbox.pack(pady=(8, 4))

        # Halos de comunidades
        self.show_halo_var = ctk.BooleanVar(value=self._initial_bool("show_halo", False))
        self.show_halo_checkbox = ctk.CTkCheckBox(
            self.params_frame,
            text="Halos de comunidades (regiões coloridas)",
            variable=self.show_halo_var
        )
        self.show_halo_checkbox.pack(pady=4)

        # Rótulos nas arestas
        self.show_edge_labels_var = ctk.BooleanVar(value=self._initial_bool("show_edge_labels", False))
        self.show_edge_labels_checkbox = ctk.CTkCheckBox(
            self.params_frame,
            text="Mostrar valores nas arestas",
            variable=self.show_edge_labels_var
        )
        self.show_edge_labels_checkbox.pack(pady=4)

        self.cexalpha_var = ctk.BooleanVar(value=self._initial_bool("cexalpha", False))
        self.cexalpha_checkbox = ctk.CTkCheckBox(
            self.params_frame,
            text="Transparência proporcional ao tamanho do termo",
            variable=self.cexalpha_var
        )
        self.cexalpha_checkbox.pack(pady=4)
        self._sync_similarity_clone_mode()
    
    def _build_result(self) -> Dict[str, Any]:
        graph_word = self.graph_word_var.get().strip() if hasattr(self, "graph_word_var") else ""
        gexf_output = ""
        if hasattr(self, "export_gexf_var") and self.export_gexf_var.get():
            raw_gexf = self.gexf_output_var.get().strip() if hasattr(self, "gexf_output_var") else ""
            gexf_output = raw_gexf or "similarity.gexf"
        show_halo = self.show_halo_var.get()
        detect_communities = self.detect_communities_var.get() or show_halo
        strict_mode = bool(self.strict_iramuteq_style_var.get())
        parity_profile = "official_0_8a7" if strict_mode else "legacy_current"
        render_profile = "native" if strict_mode else "publication_polish"
        return {
            'analysis_type': 'similarity',
            'analysis_mode': 'strict' if strict_mode else 'legacy',
            'strict_iramuteq_style': strict_mode,
            'parity_profile': parity_profile,
            'render_profile': render_profile,
            'layout': self.layout_var.get(),
            'min_freq': self.min_freq_var.get(),
            'use_lemmas': self.use_lemmas_var.get(),
            'coefficient': self.coef_var.get(),
            'min_edge': int(self.min_edge_var.get()),
            'graph_word': graph_word if graph_word else None,
            'vertex_scaling': self.vertex_scaling_var.get(),
            'arbremax': self.arbremax_var.get(),
            'detect_communities': detect_communities,
            'community_method': self.community_method_var.get(),
            'show_halo': show_halo,
            'show_edge_labels': self.show_edge_labels_var.get(),
            'cexalpha': self.cexalpha_var.get(),
            'typegraph': self.typegraph_var.get(),
            'max_words': self.max_words_var.get(),
            'gexf_output': gexf_output,
        }

    def _toggle_similarity_gexf_entry(self):
        """Enable/disable GEXF output path according to checkbox state."""
        state = "normal" if self.export_gexf_var.get() else "disabled"
        self.gexf_entry.configure(state=state)

    def _sync_similarity_clone_mode(self):
        """When strict mode is active, lock options to IRaMuTeQ-compatible profile."""
        strict = bool(self.strict_iramuteq_style_var.get())
        if strict:
            self.layout_var.set("frutch")
            self.arbremax_var.set(True)
            self.detect_communities_var.set(False)
            self.community_method_var.set("edge_betweenness")
            self.show_halo_var.set(False)
            self.show_edge_labels_var.set(False)
            self.cexalpha_var.set(False)
            self.vertex_scaling_var.set("frequency")
        if self.show_halo_var.get():
            self.detect_communities_var.set(True)

        lock_state = "disabled" if strict else "normal"
        self.layout_menu = getattr(self, "layout_menu", None)
        if self.layout_menu is not None:
            self.layout_menu.configure(state=lock_state)
        self.arbremax_checkbox = getattr(self, "arbremax_checkbox", None)
        if self.arbremax_checkbox is not None:
            self.arbremax_checkbox.configure(state=lock_state)
        self.vertex_scaling_menu = getattr(self, "vertex_scaling_menu", None)
        if self.vertex_scaling_menu is not None:
            self.vertex_scaling_menu.configure(state=lock_state)
        self.detect_communities_checkbox = getattr(self, "detect_communities_checkbox", None)
        if self.detect_communities_checkbox is not None:
            self.detect_communities_checkbox.configure(state=lock_state)
        self.community_method_menu = getattr(self, "community_method_menu", None)
        if self.community_method_menu is not None:
            self.community_method_menu.configure(state=lock_state)
        self.show_halo_checkbox = getattr(self, "show_halo_checkbox", None)
        if self.show_halo_checkbox is not None:
            self.show_halo_checkbox.configure(state=lock_state)
        self.show_edge_labels_checkbox = getattr(self, "show_edge_labels_checkbox", None)
        if self.show_edge_labels_checkbox is not None:
            self.show_edge_labels_checkbox.configure(state=lock_state)
        self.cexalpha_checkbox = getattr(self, "cexalpha_checkbox", None)
        if self.cexalpha_checkbox is not None:
            self.cexalpha_checkbox.configure(state=lock_state)


class WordCloudDialog(BaseAnalysisDialog):
    """Dialogo para geracao de nuvem de palavras."""
    ANALYSIS_TYPE = 'wordcloud'
    
    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Nuvem de Palavras",
            450,
            580,
            initial_params=initial_params,
        )
    
    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("wordcloud", "Nuvem de Palavras"),
            font=FONTS['title']
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Visualização clássica onde o tamanho da palavra indica sua frequência.").pack(side="left")
        
        # Maximo de palavras
        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row1,
            text="Máximo de palavras:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.max_words_var = ctk.IntVar(
            value=self._initial_int("max_words", 100, minimum=20, maximum=2000)
        )
        ctk.CTkSlider(
            row1,
            from_=20,
            to=2000,
            number_of_steps=198,
            variable=self.max_words_var,
            width=150
        ).pack(side="left", padx=10)

        self.max_words_label = ctk.CTkLabel(
            row1,
            text=str(self.max_words_var.get()),
            width=40,
        )
        self.max_words_label.pack(side="left")
        self.max_words_var.trace_add("write", lambda *_: self.max_words_label.configure(text=str(self.max_words_var.get())))

        self.create_help_icon(row1, "Limite de palavras na nuvem. Padrão: 100, máximo: 2000. Valores altos ampliam cobertura lexical, mas podem reduzir legibilidade visual.").pack(side="left", padx=5)
        
        # Frequencia minima
        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row2,
            text="Frequência mínima:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 3, minimum=1))
        ctk.CTkEntry(
            row2,
            textvariable=self.min_freq_var,
            width=80
        ).pack(side="left", padx=10)

        self.create_help_icon(row2, "Ignorar palavras que aparecem poucas vezes.").pack(side="left", padx=5)
        
        # Esquema de cores
        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        
        ctk.CTkLabel(
            row3,
            text="Esquema de cores:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        
        self.colors_var = ctk.StringVar(
            value=self._initial_str(
                "colors",
                "Dark2",
                allowed=["Dark2", "Set1", "Set2", "Paired", "Pastel1"],
            )
        )
        ctk.CTkOptionMenu(
            row3,
            values=["Dark2", "Set1", "Set2", "Paired", "Pastel1"],
            variable=self.colors_var,
            width=150
        ).pack(side="left", padx=10)

        self.create_help_icon(row3, "Paleta de cores usada para pintar as palavras.").pack(side="left", padx=5)

        # Formato da nuvem (shape)
        row3b = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3b.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row3b,
            text="Formato da nuvem:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        _SHAPE_OPTIONS = ["cardioid", "diamond", "square",
                          "triangle-forward", "triangle-upright", "pentagon", "star"]
        self.shape_var = ctk.StringVar(
            value=self._initial_str("shape", "square", allowed=_SHAPE_OPTIONS)
        )
        ctk.CTkOptionMenu(
            row3b,
            values=_SHAPE_OPTIONS,
            variable=self.shape_var,
            width=150
        ).pack(side="left", padx=10)
        self.create_help_icon(row3b, "Forma geométrica da nuvem de palavras.").pack(side="left", padx=5)

        # Modo de tamanho (sizing_mode)
        row3c = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3c.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row3c,
            text="Modo de tamanho:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        self.sizing_mode_var = ctk.StringVar(
            value="Área proporcional" if self._initial_str("sizing_mode", "area", allowed=["area", "height"]) == "area" else "Altura proporcional"
        )
        ctk.CTkOptionMenu(
            row3c,
            values=["Área proporcional", "Altura proporcional"],
            variable=self.sizing_mode_var,
            width=150
        ).pack(side="left", padx=10)
        self.create_help_icon(row3c, "Área proporcional destaca melhor a diferença entre palavras frequentes e raras.").pack(side="left", padx=5)

        # Excentricidade (eccentricity)
        row3d = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3d.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row3d,
            text="Excentricidade:",
            font=FONTS['body'],
            width=180
        ).pack(side="left")
        _ECC_OPTIONS = {"Estreita (0.35)": 0.35, "Normal (0.65)": 0.65, "Circular (1.0)": 1.0}
        _ECC_REVERSE = {v: k for k, v in _ECC_OPTIONS.items()}
        _initial_ecc = self._initial_float("eccentricity", 0.65)
        _initial_ecc_label = _ECC_REVERSE.get(_initial_ecc, "Normal (0.65)")
        self.eccentricity_var = ctk.StringVar(value=_initial_ecc_label)
        ctk.CTkOptionMenu(
            row3d,
            values=list(_ECC_OPTIONS.keys()),
            variable=self.eccentricity_var,
            width=150
        ).pack(side="left", padx=10)
        self.create_help_icon(row3d, "Controla o alongamento da forma: Estreita comprime verticalmente, Circular é uniforme.").pack(side="left", padx=5)

        row4 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row4.pack(fill="x", pady=8)
        self.active_only_var = ctk.BooleanVar(
            value=self._initial_bool("active_only", True)
        )
        ctk.CTkCheckBox(
            row4,
            text="Excluir stopwords (usar formas ativas)",
            variable=self.active_only_var,
        ).pack(side="left", padx=20)
        self.create_help_icon(row4, "Remove palavras comuns de função (o, a, de, que) deixando apenas substantivos/adjetivos.").pack(side="left", padx=5)

        row5 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row5.pack(fill="x", pady=4)
        self.use_lemmas_var = ctk.BooleanVar(
            value=self._initial_bool("use_lemmas", True)
        )
        ctk.CTkCheckBox(
            row5,
            text="Lematizar antes do teste",
            variable=self.use_lemmas_var,
        ).pack(side="left", padx=20)
        self.create_help_icon(row5, "Agrupa variações da mesma palavra pela forma lematizada (raiz).").pack(side="left", padx=5)
    
    def _build_result(self) -> Dict[str, Any]:
        _ECC_MAP = {"Estreita (0.35)": 0.35, "Normal (0.65)": 0.65, "Circular (1.0)": 1.0}
        _SIZING_MAP = {"Área proporcional": "area", "Altura proporcional": "height"}
        return {
            'analysis_type': 'wordcloud',
            'max_words':     self.max_words_var.get(),
            'min_freq':      self.min_freq_var.get(),
            'colors':        self.colors_var.get(),
            'active_only':   bool(self.active_only_var.get()),
            'use_lemmas':    bool(self.use_lemmas_var.get()),
            'shape':         self.shape_var.get(),
            'sizing_mode':   _SIZING_MAP.get(self.sizing_mode_var.get(), "area"),
            'eccentricity':  _ECC_MAP.get(self.eccentricity_var.get(), 0.65),
        }


class VoyantSuiteDialog(BaseAnalysisDialog):
    """Dialogo para pacote lexical inspirado no Voyant."""

    ANALYSIS_TYPE = "voyant_suite"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Pacote Voyant (inspirado)",
            820,
            820,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            title_frame,
            text="Voyant Suite",
            font=FONTS["title"],
        ).pack(side="left", padx=5)
        self.create_help_icon(
            title_frame,
            "Gera TermsBerry, Tendencias, Contextos, Bubblelines e Co-ocorrencias em uma unica execucao.",
        ).pack(side="left")

        row_query = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_query.pack(fill="x", pady=4)
        ctk.CTkLabel(row_query, text="Consulta inicial:", font=FONTS["body"], width=200).pack(side="left")
        self.query_var = ctk.StringVar(value=self._initial_str("query", ""))
        ctk.CTkEntry(
            row_query,
            textvariable=self.query_var,
            width=320,
            placeholder_text="termos separados por espaco ou virgula (opcional)",
        ).pack(side="left", padx=10)
        self.create_help_icon(
            row_query,
            "Termos para focar a analise. Se vazio, usa os mais frequentes automaticamente.",
        ).pack(side="left")

        row_mode = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_mode.pack(fill="x", pady=4)
        ctk.CTkLabel(row_mode, text="Estrategia de termos:", font=FONTS["body"], width=200).pack(side="left")
        self._mode_label_to_value = {
            "Top frequentes": "top",
            "Mista (consulta + top)": "mixed",
            "Apenas consulta": "query",
        }
        self._mode_value_to_label = {value: label for label, value in self._mode_label_to_value.items()}
        default_mode = self._initial_str("mode", "top", allowed=["top", "mixed", "query"])
        self.mode_var = ctk.StringVar(value=self._mode_value_to_label.get(default_mode, "Top frequentes"))
        ctk.CTkOptionMenu(
            row_mode,
            values=list(self._mode_label_to_value.keys()),
            variable=self.mode_var,
            width=220,
        ).pack(side="left", padx=10)
        self.create_help_icon(
            row_mode,
            "Define se o foco vem da consulta, dos mais frequentes ou dos dois.",
        ).pack(side="left")

        row_terms = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_terms.pack(fill="x", pady=4)
        ctk.CTkLabel(row_terms, text="Numero inicial de termos:", font=FONTS["body"], width=200).pack(side="left")
        self.num_initial_terms_var = ctk.IntVar(
            value=self._initial_int("num_initial_terms", 20, minimum=5, maximum=80)
        )
        ctk.CTkSlider(
            row_terms,
            from_=5,
            to=80,
            number_of_steps=75,
            variable=self.num_initial_terms_var,
            width=220,
        ).pack(side="left", padx=10)
        self.num_initial_terms_label = ctk.CTkLabel(
            row_terms,
            text=str(self.num_initial_terms_var.get()),
            width=40,
        )
        self.num_initial_terms_label.pack(side="left")
        self.num_initial_terms_var.trace_add(
            "write",
            lambda *_: self.num_initial_terms_label.configure(text=str(self.num_initial_terms_var.get())),
        )
        self.create_help_icon(
            row_terms,
            "Quantidade inicial de termos candidatos. Valores maiores ampliam cobertura, mas podem trazer mais ruído.",
        ).pack(side="left", padx=(6, 0))

        row_context = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_context.pack(fill="x", pady=4)
        ctk.CTkLabel(row_context, text="Janela de contexto:", font=FONTS["body"], width=200).pack(side="left")
        self.context_var = ctk.IntVar(value=self._initial_int("context", 5, minimum=2, maximum=20))
        ctk.CTkSlider(
            row_context,
            from_=2,
            to=20,
            number_of_steps=18,
            variable=self.context_var,
            width=220,
        ).pack(side="left", padx=10)
        self.context_label = ctk.CTkLabel(row_context, text=str(self.context_var.get()), width=40)
        self.context_label.pack(side="left")
        self.context_var.trace_add(
            "write",
            lambda *_: self.context_label.configure(text=str(self.context_var.get())),
        )
        self.create_help_icon(
            row_context,
            "Define quantos termos ao redor entram na janela de co-ocorrência e contextos KWIC.",
        ).pack(side="left", padx=(6, 0))

        row_bins = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_bins.pack(fill="x", pady=4)
        ctk.CTkLabel(row_bins, text="Segmentos (bins):", font=FONTS["body"], width=200).pack(side="left")
        self.bins_var = ctk.IntVar(value=self._initial_int("bins", 10, minimum=4, maximum=30))
        ctk.CTkSlider(
            row_bins,
            from_=4,
            to=30,
            number_of_steps=26,
            variable=self.bins_var,
            width=220,
        ).pack(side="left", padx=10)
        self.bins_label = ctk.CTkLabel(row_bins, text=str(self.bins_var.get()), width=40)
        self.bins_label.pack(side="left")
        self.bins_var.trace_add(
            "write",
            lambda *_: self.bins_label.configure(text=str(self.bins_var.get())),
        )
        self.create_help_icon(
            row_bins,
            "Número de segmentos usados para distribuir ocorrências no corpus (ex.: Bubblelines/Tendências).",
        ).pack(side="left", padx=(6, 0))

        row_docs = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_docs.pack(fill="x", pady=4)
        ctk.CTkLabel(row_docs, text="Max. documentos (bolhas):", font=FONTS["body"], width=200).pack(side="left")
        self.max_docs_var = ctk.IntVar(value=self._initial_int("max_docs", 50, minimum=5, maximum=300))
        ctk.CTkSlider(
            row_docs,
            from_=5,
            to=300,
            number_of_steps=59,
            variable=self.max_docs_var,
            width=220,
        ).pack(side="left", padx=10)
        self.max_docs_label = ctk.CTkLabel(row_docs, text=str(self.max_docs_var.get()), width=40)
        self.max_docs_label.pack(side="left")
        self.max_docs_var.trace_add(
            "write",
            lambda *_: self.max_docs_label.configure(text=str(self.max_docs_var.get())),
        )
        self.create_help_icon(
            row_docs,
            "Limita a quantidade de documentos incluídos nos painéis de bolhas para manter legibilidade.",
        ).pack(side="left", padx=(6, 0))

        row_min = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_min.pack(fill="x", pady=4)
        ctk.CTkLabel(row_min, text="Frequencia minima:", font=FONTS["body"], width=200).pack(side="left")
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 2, minimum=1, maximum=100))
        ctk.CTkEntry(row_min, textvariable=self.min_freq_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(
            row_min,
            "Frequência mínima para um termo entrar na análise. Aumente para reduzir termos raros.",
        ).pack(side="left", padx=(6, 0))

        row_ctx_rows = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_ctx_rows.pack(fill="x", pady=4)
        ctk.CTkLabel(row_ctx_rows, text="Limite de linhas KWIC:", font=FONTS["body"], width=200).pack(side="left")
        self.max_context_rows_var = ctk.IntVar(
            value=self._initial_int("max_context_rows", 800, minimum=50, maximum=5000)
        )
        ctk.CTkEntry(row_ctx_rows, textvariable=self.max_context_rows_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(
            row_ctx_rows,
            "Máximo de linhas de contexto KWIC armazenadas/exibidas no resultado.",
        ).pack(side="left", padx=(6, 0))

        row_lemma = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_lemma.pack(fill="x", pady=(10, 4))
        self.use_lemmas_var = ctk.BooleanVar(value=self._initial_bool("use_lemmas", True))
        ctk.CTkCheckBox(
            row_lemma,
            text="Agrupar singular/plural (usar lemas)",
            variable=self.use_lemmas_var,
        ).pack(side="left", padx=10)
        self.create_help_icon(
            row_lemma,
            "Une variações morfológicas (ex.: aluno/alunos) para fortalecer frequências por conceito.",
        ).pack(side="left", padx=(6, 0))

        row_active = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_active.pack(fill="x", pady=4)
        self.active_only_var = ctk.BooleanVar(value=self._initial_bool("active_only", True))
        ctk.CTkCheckBox(
            row_active,
            text="Usar apenas formas ativas",
            variable=self.active_only_var,
        ).pack(side="left", padx=10)
        self.create_help_icon(
            row_active,
            "Mantém apenas classes lexicais de conteúdo (substantivos, verbos, adjetivos etc.).",
        ).pack(side="left", padx=(6, 0))

        row_stop = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row_stop.pack(fill="x", pady=4)
        self.remove_stopwords_var = ctk.BooleanVar(value=self._initial_bool("remove_stopwords", True))
        ctk.CTkCheckBox(
            row_stop,
            text="Remover stopwords",
            variable=self.remove_stopwords_var,
        ).pack(side="left", padx=10)
        self.create_help_icon(
            row_stop,
            "Remove palavras muito frequentes e pouco informativas (de, a, o, que...).",
        ).pack(side="left", padx=(6, 0))

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "voyant_suite",
            "query": self.query_var.get().strip(),
            "mode": self._mode_label_to_value.get(self.mode_var.get().strip(), "top"),
            "num_initial_terms": int(self.num_initial_terms_var.get()),
            "context": int(self.context_var.get()),
            "bins": int(self.bins_var.get()),
            "max_docs": int(self.max_docs_var.get()),
            "min_freq": int(self.min_freq_var.get()),
            "max_context_rows": int(self.max_context_rows_var.get()),
            "use_lemmas": bool(self.use_lemmas_var.get()),
            "active_only": bool(self.active_only_var.get()),
            "remove_stopwords": bool(self.remove_stopwords_var.get()),
        }


class PrototypicalDialog(BaseAnalysisDialog):
    """Dialogo para analise prototipica."""

    ANALYSIS_TYPE = 'prototypical'

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Análise Prototípica",
            450,
            300,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("prototypical", "Análise Prototípica"),
            font=FONTS['title']
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Cruza frequência e ordem de evocação para identificar o núcleo central de uma representação.").pack(side="left")

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row1,
            text="Frequência limiar:",
            font=FONTS['body'],
            width=180,
        ).pack(side="left")
        
        self.freq_threshold_var = ctk.IntVar(
            value=self._initial_int("freq_threshold", 5, minimum=1, maximum=50)
        )
        ctk.CTkSlider(
            row1,
            from_=1,
            to=50,
            number_of_steps=49,
            variable=self.freq_threshold_var,
            width=150,
        ).pack(side="left", padx=10)
        self.freq_label = ctk.CTkLabel(row1, text=str(self.freq_threshold_var.get()), width=35)
        self.freq_label.pack(side="left")
        self.freq_threshold_var.trace_add(
            "write",
            lambda *_: self.freq_label.configure(text=str(self.freq_threshold_var.get())),
        )

        self.create_help_icon(row1, "Ponto de corte para considerar uma palavra frequente.").pack(side="left", padx=5)

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row2,
            text="Rank limiar:",
            font=FONTS['body'],
            width=180,
        ).pack(side="left")
        
        self.rank_threshold_var = ctk.DoubleVar(
            value=self._initial_float("rank_threshold", 2.5, minimum=0.5, maximum=10.0)
        )
        ctk.CTkSlider(
            row2,
            from_=0.5,
            to=10.0,
            number_of_steps=95,
            variable=self.rank_threshold_var,
            width=150,
        ).pack(side="left", padx=10)
        self.rank_label = ctk.CTkLabel(row2, text=f"{self.rank_threshold_var.get():.1f}", width=40)
        self.rank_label.pack(side="left")
        self.rank_threshold_var.trace_add(
            "write",
            lambda *_: self.rank_label.configure(text=f"{self.rank_threshold_var.get():.1f}"),
        )

        self.create_help_icon(row2, "Ordem média de evocação para separar núcleo central da periferia.").pack(side="left", padx=5)

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "prototypical",
            "freq_threshold": int(self.freq_threshold_var.get()),
            "rank_threshold": float(self.rank_threshold_var.get()),
        }


class LabbeDialog(BaseAnalysisDialog):
    """Dialogo para distancia de Labbe."""

    ANALYSIS_TYPE = 'labbe'

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Distância de Labbé",
            450,
            260,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("labbe", "Distância de Labbé"),
            font=FONTS['title']
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Mede a distância vocabular entre dois textos ou grupos (0 = iguais, 1 = diferentes).").pack(side="left")

        row = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row,
            text="Frequência mínima:",
            font=FONTS['body'],
            width=180,
        ).pack(side="left")
        
        self.min_freq_var = ctk.IntVar(
            value=self._initial_int("min_freq", 3, minimum=1, maximum=50)
        )
        ctk.CTkSlider(
            row,
            from_=1,
            to=50,
            number_of_steps=49,
            variable=self.min_freq_var,
            width=150,
        ).pack(side="left", padx=10)
        self.min_freq_label = ctk.CTkLabel(row, text=str(self.min_freq_var.get()), width=35)
        self.min_freq_label.pack(side="left")
        self.min_freq_var.trace_add(
            "write",
            lambda *_: self.min_freq_label.configure(text=str(self.min_freq_var.get())),
        )

        self.create_help_icon(row, "Ignora palavras muito raras no cálculo da distância.").pack(side="left", padx=5)

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "labbe",
            "min_freq": int(self.min_freq_var.get()),
        }


class KeynessExtraDialog(BaseAnalysisDialog):
    """Dialogo para keyness por variável de metadado."""

    ANALYSIS_TYPE = "keyness_extra"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Keyness (Extras)",
            480,
            330,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("keyness", "Keyness por Metadado"),
            font=FONTS["title"],
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Encontra palavras estatisticamente mais frequentes em um grupo específico.").pack(side="left")

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Variável:", font=FONTS["body"], width=180).pack(side="left")
        self.variable_var = ctk.StringVar(value=self._initial_str("variable", ""))
        ctk.CTkEntry(row1, textvariable=self.variable_var, width=200, placeholder_text="vazio = automático").pack(side="left", padx=10)
        self.create_help_icon(row1, "Nome da variável de metadado (ex: genero). Deixe vazio para listar todas.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Valor alvo:", font=FONTS["body"], width=180).pack(side="left")
        self.target_value_var = ctk.StringVar(value=self._initial_str("target_value", ""))
        ctk.CTkEntry(row2, textvariable=self.target_value_var, width=200, placeholder_text="vazio = automático").pack(side="left", padx=10)
        self.create_help_icon(row2, "Valor específico da variável (ex: feminino). Deixe vazio para escolher depois.").pack(side="left", padx=(0, 5))

        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        ctk.CTkLabel(row3, text="Frequência mínima:", font=FONTS["body"], width=180).pack(side="left")
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 3, minimum=1, maximum=50))
        ctk.CTkEntry(row3, textvariable=self.min_freq_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row3, "Ignora palavras com poucas ocorrências globalmente.").pack(side="left", padx=(0, 5))

        row4 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row4.pack(fill="x", pady=5)
        ctk.CTkLabel(row4, text="Top termos:", font=FONTS["body"], width=180).pack(side="left")
        self.top_n_var = ctk.IntVar(value=self._initial_int("top_n", 20, minimum=5, maximum=100))
        ctk.CTkEntry(row4, textvariable=self.top_n_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row4, "Número de palavras chave para mostrar no gráfico.").pack(side="left", padx=(0, 5))

        row5 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row5.pack(fill="x", pady=5)
        ctk.CTkLabel(row5, text="Métrica R:", font=FONTS["body"], width=180).pack(side="left")
        initial_measure = self._initial_str("measure", "lr")
        measure_values = ["Log-Likelihood (lr)", "Qui-quadrado (chi2)"]
        mapped_initial = "Log-Likelihood (lr)" if str(initial_measure).strip().lower() != "chi2" else "Qui-quadrado (chi2)"
        self.measure_var = ctk.StringVar(value=mapped_initial)
        ctk.CTkOptionMenu(row5, values=measure_values, variable=self.measure_var, width=200).pack(side="left", padx=10)
        self.create_help_icon(row5, "Define a estatística do keyness no quanteda.").pack(side="left", padx=(0, 5))

        row6 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row6.pack(fill="x", pady=5)
        self.remove_stopwords_var = ctk.BooleanVar(value=self._initial_bool("remove_stopwords", True))
        ctk.CTkCheckBox(
            row6,
            text="Remover stopwords (PT)",
            variable=self.remove_stopwords_var,
            font=FONTS["body"],
        ).pack(side="left", padx=(180, 0))
        self.create_help_icon(row6, "Aplica remoção de stopwords antes do cálculo.").pack(side="left", padx=(8, 5))

    def _build_result(self) -> Dict[str, Any]:
        measure_label = str(self.measure_var.get() or "").strip().lower()
        measure = "chi2" if "chi2" in measure_label else "lr"
        return {
            "analysis_type": "keyness_extra",
            "variable": self.variable_var.get().strip(),
            "target_value": self.target_value_var.get().strip(),
            "min_freq": int(self.min_freq_var.get()),
            "top_n": int(self.top_n_var.get()),
            "measure": measure,
            "remove_stopwords": bool(self.remove_stopwords_var.get()),
        }


class BigramNetworkExtraDialog(BaseAnalysisDialog):
    """Dialogo para rede de coocorrência por bigramas."""

    ANALYSIS_TYPE = "bigram_network_extra"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Rede de Bigramas (Extras)",
            480,
            280,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("bigram", "Rede por Bigramas"),
            font=FONTS["title"],
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Grafo de conexões entre palavras vizinhas imediatas (n-grams).").pack(side="left")

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Freq. mínima bigrama:", font=FONTS["body"], width=180).pack(side="left")
        self.min_bigram_freq_var = ctk.IntVar(value=self._initial_int("min_bigram_freq", 2, minimum=1, maximum=20))
        ctk.CTkEntry(row1, textvariable=self.min_bigram_freq_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row1, "Mínimo de vezes que o par de palavras deve aparecer junto.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Máx. arestas:", font=FONTS["body"], width=180).pack(side="left")
        self.top_edges_var = ctk.IntVar(value=self._initial_int("top_edges", 120, minimum=20, maximum=500))
        ctk.CTkEntry(row2, textvariable=self.top_edges_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row2, "Limite de conexões exibidas no grafo.").pack(side="left", padx=(0, 5))

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "bigram_network_extra",
            "min_bigram_freq": int(self.min_bigram_freq_var.get()),
            "top_edges": int(self.top_edges_var.get()),
        }


class TrigramNetworkExtraDialog(BaseAnalysisDialog):
    """Dialogo para rede de coocorrência por trigramas."""

    ANALYSIS_TYPE = "trigram_network_extra"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Rede de Trigramas (Extras)",
            480,
            280,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("bigram", "Rede por Trigramas"),
            font=FONTS["title"],
        ).pack(side="left", padx=5)
        self.create_help_icon(
            title_frame,
            "Grafo de conexões entre palavras em sequências de três (trigramas).",
        ).pack(side="left")

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row1, text="Freq. mínima trigrama:", font=FONTS["body"], width=180
        ).pack(side="left")
        self.min_trigram_freq_var = ctk.IntVar(
            value=self._initial_int("min_trigram_freq", 2, minimum=1, maximum=20)
        )
        ctk.CTkEntry(row1, textvariable=self.min_trigram_freq_var, width=90).pack(
            side="left", padx=10
        )
        self.create_help_icon(
            row1, "Mínimo de vezes que a sequência de três palavras deve aparecer."
        ).pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(
            row2, text="Máx. arestas:", font=FONTS["body"], width=180
        ).pack(side="left")
        self.top_edges_var = ctk.IntVar(
            value=self._initial_int("top_edges", 120, minimum=20, maximum=500)
        )
        ctk.CTkEntry(row2, textvariable=self.top_edges_var, width=90).pack(
            side="left", padx=10
        )
        self.create_help_icon(
            row2, "Limite de conexões exibidas no grafo."
        ).pack(side="left", padx=(0, 5))

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "trigram_network_extra",
            "min_trigram_freq": int(self.min_trigram_freq_var.get()),
            "top_edges": int(self.top_edges_var.get()),
        }


class WordTreeExtraDialog(BaseAnalysisDialog):
    """Dialogo para árvore de palavras contextual."""

    ANALYSIS_TYPE = "word_tree_extra"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Árvore de Palavras (Extras)",
            540,
            430,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("word_tree", "Árvore de Palavras"),
            font=FONTS["title"],
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Visualiza as frases onde uma palavra específica aparece (concordância visual).").pack(side="left")

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Termo central:", font=FONTS["body"], width=190).pack(side="left")
        self.keyword_var = ctk.StringVar(value=self._initial_str("keyword", ""))
        ctk.CTkEntry(
            row1,
            textvariable=self.keyword_var,
            width=240,
            placeholder_text="vazio = termo mais frequente",
        ).pack(side="left", padx=10)
        self.create_help_icon(row1, "Palavra raiz da árvore. Deixe vazio para usar a mais frequente.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Frequência mínima:", font=FONTS["body"], width=190).pack(side="left")
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 3, minimum=1, maximum=30))
        ctk.CTkEntry(row2, textvariable=self.min_freq_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row2, "Mínimo de ocorrências para um ramo aparecer.").pack(side="left", padx=(0, 5))

        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        ctk.CTkLabel(row3, text="Profundidade máxima:", font=FONTS["body"], width=190).pack(side="left")
        self.max_depth_var = ctk.IntVar(value=self._initial_int("max_depth", 4, minimum=1, maximum=8))
        ctk.CTkEntry(row3, textvariable=self.max_depth_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row3, "Quantas palavras seguintes analisar.").pack(side="left", padx=(0, 5))

        row4 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row4.pack(fill="x", pady=5)
        ctk.CTkLabel(row4, text="Mín. freq. de ramo:", font=FONTS["body"], width=190).pack(side="left")
        self.min_branch_freq_var = ctk.IntVar(value=self._initial_int("min_branch_freq", 2, minimum=1, maximum=50))
        ctk.CTkEntry(row4, textvariable=self.min_branch_freq_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row4, "Mínimo de ocorrências para um ramo secundário aparecer.").pack(side="left", padx=(0, 5))

        row5 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row5.pack(fill="x", pady=5)
        ctk.CTkLabel(row5, text="Máx. ramos no gráfico:", font=FONTS["body"], width=190).pack(side="left")
        self.top_branches_var = ctk.IntVar(value=self._initial_int("top_branches", 120, minimum=20, maximum=500))
        ctk.CTkEntry(row5, textvariable=self.top_branches_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row5, "Limite de ramos exibidos para manter a legibilidade.").pack(side="left", padx=(0, 5))

        row6 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row6.pack(fill="x", pady=(10, 4))
        self.use_lemmas_var = ctk.BooleanVar(value=self._initial_bool("use_lemmas", True))
        ctk.CTkCheckBox(
            row6,
            text="Agrupar singular/plural (usar lemas)",
            variable=self.use_lemmas_var,
        ).pack(side="left", padx=12)
        self.create_help_icon(row6, "Trata 'casa' e 'casas' como a mesma palavra.").pack(side="left", padx=5)

        row7 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row7.pack(fill="x", pady=4)
        self.active_only_var = ctk.BooleanVar(value=self._initial_bool("active_only", True))
        ctk.CTkCheckBox(
            row7,
            text="Excluir stopwords (formas ativas)",
            variable=self.active_only_var,
        ).pack(side="left", padx=12)
        self.create_help_icon(row7, "Remove palavras comuns de função (o, a, de, que).").pack(side="left", padx=5)

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "word_tree_extra",
            "keyword": self.keyword_var.get().strip(),
            "min_freq": int(self.min_freq_var.get()),
            "max_depth": int(self.max_depth_var.get()),
            "min_branch_freq": int(self.min_branch_freq_var.get()),
            "top_branches": int(self.top_branches_var.get()),
            "use_lemmas": bool(self.use_lemmas_var.get()),
            "active_only": bool(self.active_only_var.get()),
        }


class WordfishExtraDialog(BaseAnalysisDialog):
    """Dialogo para escalonamento 1D (estilo Wordfish)."""

    ANALYSIS_TYPE = "wordfish_extra"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Escalonamento 1D (Extras)",
            500,
            320,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("wordfish", "Escalonamento 1D (Wordfish)"),
            font=FONTS["title"],
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Posiciona textos em uma única dimensão (ex: espectro ideológico).").pack(side="left")

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Variável de grupo:", font=FONTS["body"], width=180).pack(side="left")
        self.group_variable_var = ctk.StringVar(value=self._initial_str("group_variable", ""))
        ctk.CTkEntry(row1, textvariable=self.group_variable_var, width=220, placeholder_text="vazio = automático").pack(side="left", padx=10)
        self.create_help_icon(row1, "Metadado que define os grupos a comparar.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=5)
        ctk.CTkLabel(row2, text="Frequência mínima:", font=FONTS["body"], width=180).pack(side="left")
        self.min_freq_var = ctk.IntVar(value=self._initial_int("min_freq", 3, minimum=1, maximum=40))
        ctk.CTkEntry(row2, textvariable=self.min_freq_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row2, "Mínimo de ocorrências para inclusão.").pack(side="left", padx=(0, 5))

        row3 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row3.pack(fill="x", pady=5)
        ctk.CTkLabel(row3, text="Máx. termos:", font=FONTS["body"], width=180).pack(side="left")
        self.max_features_var = ctk.IntVar(value=self._initial_int("max_features", 1200, minimum=100, maximum=5000))
        ctk.CTkEntry(row3, textvariable=self.max_features_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row3, "Limite de palavras analisadas.").pack(side="left", padx=(0, 5))

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "wordfish_extra",
            "group_variable": self.group_variable_var.get().strip(),
            "min_freq": int(self.min_freq_var.get()),
            "max_features": int(self.max_features_var.get()),
        }


class XRayExtraDialog(BaseAnalysisDialog):
    """Dialogo para dispersão de termos (x-ray)."""

    ANALYSIS_TYPE = "xray_extra"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Dispersão de Termos (X-Ray)",
            500,
            240,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("dispersion", "Dispersão Lexical"),
            font=FONTS["title"],
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Mostra onde palavras específicas aparecem ao longo do texto.").pack(side="left")

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Termos:", font=FONTS["body"], width=180).pack(side="left")
        self.terms_var = ctk.StringVar(value=self._initial_str("terms", ""))
        ctk.CTkEntry(
            row1,
            textvariable=self.terms_var,
            width=250,
            placeholder_text="ex: amor, ódio, paz",
        ).pack(side="left", padx=10)
        self.create_help_icon(row1, "Palavras a pesquisar, separadas por vírgula.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=(10, 4))
        self.active_only_var = ctk.BooleanVar(value=self._initial_bool("active_only", False))
        ctk.CTkCheckBox(
            row2,
            text="Buscar apenas em formas ativas (excluir stopwords)",
            variable=self.active_only_var,
        ).pack(side="left", padx=12)
        self.create_help_icon(row2, "Remove palavras comuns de função (o, a, de, que) antes da busca.").pack(side="left", padx=5)

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "xray_extra",
            "terms": self.terms_var.get().strip(),
            "active_only": bool(self.active_only_var.get()),
        }


class SentimentExtraDialog(BaseAnalysisDialog):
    ANALYSIS_TYPE = "sentiment_extra"

    def __init__(self, parent, initial_params: Optional[Dict[str, Any]] = None):
        super().__init__(
            parent,
            "Sentimentos (Extras)",
            480,
            300,
            initial_params=initial_params,
        )

    def _create_params_widgets(self):
        title_frame = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        title_frame.pack(pady=(0, 15))
        ctk.CTkLabel(
            title_frame,
            text=label_with_icon("sentiment", "Análise de Sentimentos"),
            font=FONTS["title"],
        ).pack(side="left", padx=5)
        self.create_help_icon(title_frame, "Classifica o texto em positivo/negativo usando dicionários léxicos.").pack(side="left")

        row1 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row1.pack(fill="x", pady=5)
        ctk.CTkLabel(row1, text="Top palavras:", font=FONTS["body"], width=180).pack(side="left")
        self.top_words_var = ctk.IntVar(value=self._initial_int("top_words", 25, minimum=10, maximum=300))
        ctk.CTkEntry(row1, textvariable=self.top_words_var, width=90).pack(side="left", padx=10)
        self.create_help_icon(row1, "Número de palavras polarizadas para exibir no gráfico.").pack(side="left", padx=(0, 5))

        row2 = ctk.CTkFrame(self.params_frame, fg_color="transparent")
        row2.pack(fill="x", pady=8)
        self.with_timeline_var = ctk.BooleanVar(value=self._initial_bool("with_timeline", True))
        ctk.CTkCheckBox(
            row2,
            text="Gerar gráfico de sentimentos ao longo do tempo (se houver datas)",
            variable=self.with_timeline_var,
        ).pack(side="left", padx=10)
        self.create_help_icon(row2, "Requer que o corpus tenha metadados cronológicos.").pack(side="left", padx=5)

    def _build_result(self) -> Dict[str, Any]:
        return {
            "analysis_type": "sentiment_extra",
            "top_words": int(self.top_words_var.get()),
            "with_timeline": bool(self.with_timeline_var.get()),
        }
