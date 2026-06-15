"""
Analise de Similaridade (grafo de co-ocorrencia).
Usa os scripts R: simi.R, simied.R, Rgraph.R (via gerador de scripts).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..core.corpus import Corpus
from ..core.text_processor import TextProcessor
from ..core.stopword_policy import is_visual_content_term
from ..core.r_script_generator import RScriptGenerator
from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..core.network_renderer import render_similarity_network
from ..utils.logger import get_logger


IRAMUTEQ_SIMILARITY_INDICES = [
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
SIMILARITY_COEFFICIENTS = {
    idx: name for idx, name in enumerate(IRAMUTEQ_SIMILARITY_INDICES)
}

GRAPH_LAYOUTS = [
    "random",
    "circle",
    "frutch",
    "kawa",
    "graphopt",
    "spirale",
    "spirale3D",
    "fruchterman",
    "kamada",
    "circular",
]

LAYOUT_ALIASES = {
    "fruchterman": "frutch",
    "fr": "frutch",
    "frutch": "frutch",
    "kamada": "kawa",
    "kk": "kawa",
    "kawa": "kawa",
    "circular": "circle",
    "circle": "circle",
    "random": "random",
    "graphopt": "graphopt",
    "spirale": "spirale",
    "spirale3d": "spirale3D",
    "spirale3D": "spirale3D",
}

COMMUNITY_METHOD_ALIASES = {
    "edge_betweenness": "edge_betweenness",
    "betweenness": "edge_betweenness",
    "fastgreedy": "fastgreedy",
    "label_propagation": "label_propagation",
    "leading_eigenvector": "leading_eigenvector",
    "multilevel": "multilevel",
    "louvain": "multilevel",
    "optimal": "optimal",
    "spinglass": "spinglass",
    "walktrap": "walktrap",
}

STRICT_IRAMUTEQ_OVERRIDES = {
    "layout": "frutch",
    "arbremax": True,
    "community_method": "edge_betweenness",
    "detect_communities": False,
    "show_halo": False,
    "show_edge_labels": False,
    "cexalpha": False,
    "renderer_backend": "iramuteq_r",
    "vertex_scaling": "frequency",
}

LEGACY_COMMUNITY_METHOD_BY_INDEX = {
    0: "edge_betweenness",
    1: "fastgreedy",
    2: "label_propagation",
    3: "leading_eigenvector",
    4: "multilevel",
    5: "optimal",
    6: "spinglass",
    7: "walktrap",
}


@dataclass
class SimilarityResult:
    """Resultado da analise de similaridade."""

    graph_path: Path
    adjacency_matrix: Optional[Path] = None
    communities: Optional[Dict[str, int]] = None
    centrality: Optional[Dict[str, float]] = None
    backend_used: str = "unknown"
    strict_mode_used: bool = True
    fallback_used: bool = False
    dropped_token_count: int = 0
    r_session_info: Optional[Dict[str, Any]] = None
    community_sensitivity_report: Optional[Dict[str, Any]] = None
    raw_graph_path: Optional[Path] = None
    verified_output: bool = False
    render_metrics: Optional[Dict[str, Any]] = None
    manifest_path: Optional[Path] = None
    warnings: Optional[List[str]] = None


class SimilarityAnalysisError(Exception):
    """
    Erro amigavel para analise de similaridade.

    Segue o padrao: o que aconteceu, por que aconteceu, como resolver.
    """

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class SimilarityAnalysis:
    """Analise de Similaridade / Grafo de co-ocorrencia."""

    DEFAULT_PARAMS = {
        "coefficient": 0,
        "layout": "frutch",
        "min_freq": 3,
        "window_size": 5,
        "use_lemmas": True,
        "active_only": True,
        "min_edge": 0,
        "vertex_size_min": 5,
        "vertex_size_max": 30,
        "vertex_scaling": "frequency",
        "arbremax": True,
        "detect_communities": False,
        "community_method": "edge_betweenness",
        "show_halo": False,
        "show_edge_labels": False,
        "cexalpha": False,
        "grayscale": False,
        "strict_iramuteq_style": True,
        "graph_word": "",
        "gexf_output": "",
        "typegraph": "png",
        "renderer_backend": "iramuteq_r",
        "stopword_policy": "aggressive_pt",
        "width": 1000,
        "height": 1000,
        "use_new_engine": True,
    }

    def __init__(self, corpus: Corpus, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.processor = TextProcessor(corpus)
        self.script_generator = RScriptGenerator()
        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)
        self._last_result: Optional[SimilarityResult] = None

    def run(self, params: Optional[Dict[str, Any]] = None) -> SimilarityResult:
        """Executa analise de similaridade."""
        config = self.sanitize_params(params)

        # --- New engine bridge ---
        use_new = config.get("use_new_engine", True)
        # Honor injected r_executor: fall back to legacy path when the executor
        # was explicitly provided and use_new_engine was not explicitly requested.
        if self.r_executor is not None and (params is None or "use_new_engine" not in (params or {})):
            use_new = False
        if use_new:
            try:
                return self._run_new_engine(config)
            except Exception as exc:
                if config.get("strict_iramuteq_style", True):
                    raise SimilarityAnalysisError(
                        what="Falha no backend estrito de similitude.",
                        why=str(exc),
                        how=(
                            "Verifique o Rscript e os pacotes R obrigatorios "
                            "ou desative o modo fiel IRaMuTeQ para usar a trilha experimental."
                        ),
                    ) from exc
                self._logger.warning(
                    f"New similitude engine failed, falling back to legacy: {exc}",
                    exc_info=True,
                )

        try:
            coefficient = int(config.get("coefficient", 0))
            layout = str(config.get("layout", "frutch"))
            community_method = str(config.get("community_method", "edge_betweenness"))
            min_freq = int(config.get("min_freq", 3))
            window_size = int(config.get("window_size", 5))
            use_lemmas = bool(config.get("use_lemmas", True))
            active_only = bool(config.get("active_only", True))
            renderer_backend = str(config.get("renderer_backend", "iramuteq_r")).strip().lower()
            selected_words_raw = config.get("selected_words") or []
            selected_words = {
                str(word).strip().lower()
                for word in selected_words_raw
                if str(word).strip()
            }
            if selected_words and use_lemmas:
                selected_words = self._normalize_selected_lemmas(selected_words)
            typegraph = str(config.get("typegraph", "png")).strip().lower()

            graph_default = "similarity.svg" if typegraph == "svg" else "similarity.png"
            graph_out = str(config.get("graph_out") or graph_default)
            if Path(graph_out).suffix.lower() not in {".png", ".svg"}:
                graph_out = f"{graph_out}.{typegraph}"

            self.processor.build_dtm(
                min_freq=min_freq,
                use_lemmas=use_lemmas,
                active_only=active_only,
            )
            self.processor.build_cooccurrence_matrix(
                window_size=window_size,
                min_freq=min_freq,
                active_only=active_only,
                use_lemmas=use_lemmas,
            )

            if selected_words:
                selected_indices = [
                    idx for idx, word in enumerate(self.processor.vocabulary)
                    if word.lower() in selected_words
                ]
                if len(selected_indices) < 2:
                    raise SimilarityAnalysisError(
                        what="Selecao de palavras insuficiente para similitude.",
                        why="Menos de duas palavras selecionadas existem no vocabulario filtrado.",
                        how="Selecione mais palavras ou reduza a frequencia minima.",
                    )

                self.processor.cooc = self.processor.cooc[selected_indices, :][:, selected_indices]
                if self.processor.dtm is not None:
                    self.processor.dtm = self.processor.dtm[:, selected_indices]
                self.processor.vocabulary = [
                    self.processor.vocabulary[idx] for idx in selected_indices
                ]
                self.processor._word_to_idx = {
                    word: idx for idx, word in enumerate(self.processor.vocabulary)
                }

            files = self.processor.export_for_similarity(self.output_dir)

            script_params = {
                **config,
                "coefficient": coefficient,
                "layout": layout,
                "community_method": community_method,
                "typegraph": typegraph,
                "pathout": str(self.output_dir),
                "data_file": files["cooccurrence"].name,
                "dtm_file": files["dtm"].name,
                "graph_out": graph_out,
                "communities_out": "similarity_communities.csv",
                "centrality_out": "similarity_centrality.csv",
            }

            script_path = self.script_generator.generate_and_save(
                "similarity",
                script_params,
                self.output_dir / "similarity_script.R",
            )

            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )

            graph_path = self.output_dir / script_params["graph_out"]
            communities_path = self.output_dir / script_params["communities_out"]
            centrality_path = self.output_dir / script_params["centrality_out"]

            if renderer_backend == "python":
                py_graph = render_similarity_network(
                    cooc_matrix_path=files["cooccurrence"],
                    output_path=graph_path,
                    communities_path=communities_path,
                    centrality_path=centrality_path,
                    width=int(config.get("width", 1200)),
                    height=int(config.get("height", 1200)),
                    use_mst=config.get("arbremax", True),
                    min_edge=float(config.get("min_edge", 0)),
                    show_halo=config.get("show_halo", False),
                    grayscale=config.get("grayscale", False),
                    typegraph=typegraph,
                )
                if py_graph is not None:
                    graph_path = py_graph

            # Verificar se o arquivo de imagem foi realmente criado
            if not graph_path.exists():
                raise SimilarityAnalysisError(
                    what="O grafico de similaridade nao foi gerado.",
                    why=f"O arquivo de saida nao foi encontrado: {graph_path}",
                    how="Verifique se o R e os pacotes necessarios (igraph) estao instalados corretamente.",
                )

            result = self._parse_results(
                graph_path=graph_path,
                adjacency_matrix=files.get("cooccurrence"),
                communities_path=communities_path,
                centrality_path=centrality_path,
            )
            self._last_result = result
            return result

        except RNotFoundError as exc:
            raise SimilarityAnalysisError(
                what="R nao encontrado no sistema.",
                why=str(exc),
                how="Instale o R (4.0+) e verifique se o Rscript esta disponivel no PATH.",
            ) from exc
        except RTimeoutError as exc:
            raise SimilarityAnalysisError(
                what="Tempo limite excedido na analise de similaridade.",
                why=str(exc),
                how="Tente reduzir o corpus ou aumente o tempo limite.",
            ) from exc
        except RExecutionError as exc:
            raise SimilarityAnalysisError(
                what="Falha na execucao do script de similaridade.",
                why=str(exc),
                how="Verifique se os pacotes R necessarios estao instalados.",
            ) from exc
        except Exception as exc:
            raise SimilarityAnalysisError(
                what="Falha ao executar a analise de similaridade.",
                why=str(exc),
                how="Verifique os dados exportados e tente novamente.",
            ) from exc

    def _run_new_engine(self, config: Dict[str, Any]) -> SimilarityResult:
        """Run analysis using the new Python-native similitude engine."""
        from .similitude import SimilitudeAnalysis

        # Map legacy coefficient index to name
        coefficient = config.get("coefficient", 0)
        if isinstance(coefficient, (int, float)):
            idx = int(coefficient)
            coeff_name = SIMILARITY_COEFFICIENTS.get(idx, "cooccurrence")
        else:
            coeff_name = str(coefficient)

        strict_mode = bool(config.get("strict_iramuteq_style", True))
        layout = str(config.get("layout", "frutch"))
        renderer_backend = str(config.get("renderer_backend", "iramuteq_r")).strip().lower()

        # Build new-engine params — defaults aligned with IRaMuTeQ simitxt.cfg
        new_params = {
            "coefficient": coeff_name,
            "layout": layout,
            "min_freq": int(config.get("min_freq", 3)),
            "use_lemmas": bool(config.get("use_lemmas", True)),
            "active_only": bool(config.get("active_only", True)),
            "min_edge": float(config.get("min_edge", 0)),
            "arbremax": bool(config.get("arbremax", True)),
            "detect_communities": bool(config.get("detect_communities", True))
                or bool(config.get("show_halo", True)),
            "community_method": str(config.get("community_method", "edge_betweenness")),
            "show_halo": bool(config.get("show_halo", True))
                or bool(config.get("detect_communities", True)),
            "show_edge_labels": bool(config.get("show_edge_labels", False)),
            "vertex_scaling": str(config.get("vertex_scaling", "frequency")),
            "grayscale": bool(config.get("grayscale", False)),
            "typegraph": str(config.get("typegraph", "png")),
            "width": int(config.get("width", 1000)),
            "height": int(config.get("height", 1000)),
            "renderer_backend": renderer_backend,
            "stopword_policy": str(config.get("stopword_policy", "aggressive_pt")),
            "selected_words": list(config.get("selected_words", [])) or None,
            "strict_iramuteq_style": strict_mode,
            "keep_punctuation": bool(config.get("keep_punctuation", False)),
            "graph_word": str(config.get("graph_word", "") or "").strip(),
        }

        if strict_mode:
            new_params.update(
                {
                    "layout": "frutch",
                    "arbremax": True,
                    "community_method": "edge_betweenness",
                    "show_edge_labels": False,
                    "vertex_scaling": "frequency",
                    "renderer_backend": "iramuteq_r",
                    "keep_punctuation": False,
                }
            )

        analysis = SimilitudeAnalysis(self.corpus, self.output_dir)
        result = analysis.run(new_params)

        # Convert to legacy SimilarityResult format
        return SimilarityResult(
            graph_path=result.graph_path,
            adjacency_matrix=result.adjacency_matrix,
            communities=result.communities,
            centrality=result.centrality,
            backend_used=getattr(result, "backend_used", renderer_backend),
            strict_mode_used=getattr(result, "strict_mode_used", strict_mode),
            fallback_used=getattr(result, "fallback_used", False),
            dropped_token_count=getattr(result, "dropped_token_count", 0),
            r_session_info=getattr(result, "r_session_info", None),
            community_sensitivity_report=getattr(
                result,
                "community_sensitivity_report",
                None,
            ),
            raw_graph_path=getattr(result, "raw_graph_path", None),
            verified_output=getattr(result, "verified_output", False),
            render_metrics=getattr(result, "render_metrics", None),
            manifest_path=getattr(result, "manifest_path", None),
            warnings=getattr(result, "warnings", None),
        )

    def get_available_coefficients(self) -> Dict[int, str]:
        """Retorna coeficientes de similaridade disponiveis."""
        return SIMILARITY_COEFFICIENTS

    def get_available_layouts(self) -> List[str]:
        """Retorna layouts de grafo disponiveis."""
        return GRAPH_LAYOUTS

    @classmethod
    def sanitize_params(cls, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Normalize/sanitize params and apply strict IRaMuTeQ profile by default."""
        incoming = dict(params or {})

        if "halo" in incoming and "show_halo" not in incoming:
            incoming["show_halo"] = incoming.get("halo")
        if "label_e" in incoming and "show_edge_labels" not in incoming:
            incoming["show_edge_labels"] = incoming.get("label_e")
        if "com" in incoming and "detect_communities" not in incoming:
            incoming["detect_communities"] = incoming.get("com")
        if "communities" in incoming and "community_method" not in incoming:
            try:
                idx = int(incoming.get("communities"))
            except (TypeError, ValueError):
                idx = -1
            incoming["community_method"] = LEGACY_COMMUNITY_METHOD_BY_INDEX.get(idx, "edge_betweenness")

        config = {**cls.DEFAULT_PARAMS, **incoming}
        config["coefficient"] = cls._normalize_coefficient(config.get("coefficient", 0))
        config["layout"] = cls._normalize_layout(config.get("layout", "frutch"))
        config["community_method"] = cls._normalize_community_method(
            config.get("community_method", "edge_betweenness")
        )
        config["min_freq"] = max(1, cls._coerce_int(config.get("min_freq"), 3))
        config["window_size"] = max(1, cls._coerce_int(config.get("window_size"), 5))
        config["min_edge"] = max(0.0, cls._coerce_float(config.get("min_edge"), 0.0))
        config["width"] = max(300, cls._coerce_int(config.get("width"), 1000))
        config["height"] = max(300, cls._coerce_int(config.get("height"), 1000))
        config["use_lemmas"] = cls._coerce_bool(config.get("use_lemmas"), True)
        config["active_only"] = cls._coerce_bool(config.get("active_only"), True)
        config["arbremax"] = cls._coerce_bool(config.get("arbremax"), True)
        config["detect_communities"] = cls._coerce_bool(config.get("detect_communities"), True)
        config["show_halo"] = cls._coerce_bool(config.get("show_halo"), True)
        config["show_edge_labels"] = cls._coerce_bool(config.get("show_edge_labels"), False)
        config["cexalpha"] = cls._coerce_bool(config.get("cexalpha"), False)
        config["grayscale"] = cls._coerce_bool(config.get("grayscale"), False)
        config["strict_iramuteq_style"] = cls._coerce_bool(
            config.get("strict_iramuteq_style"),
            True,
        )

        renderer_backend = str(
            config.get(
                "renderer_backend",
                "python" if config.get("use_python_renderer", False) else "iramuteq_r",
            )
        ).strip().lower()
        if renderer_backend not in {"iramuteq_r", "python"}:
            renderer_backend = "iramuteq_r"
        config["renderer_backend"] = renderer_backend

        vertex_scaling = str(config.get("vertex_scaling", "frequency")).strip().lower()
        if vertex_scaling not in {"frequency", "chi2", "degree"}:
            vertex_scaling = "frequency"
        config["vertex_scaling"] = vertex_scaling

        graph_word = str(config.get("graph_word", "") or "").strip()
        config["graph_word"] = graph_word

        typegraph = str(config.get("typegraph", "png")).strip().lower()
        config["typegraph"] = typegraph if typegraph in {"png", "svg"} else "png"

        if config["strict_iramuteq_style"]:
            config.update(STRICT_IRAMUTEQ_OVERRIDES)

        stopword_policy = str(config.get("stopword_policy", "aggressive_pt")).strip().lower()
        if stopword_policy not in {"legacy", "aggressive_pt"}:
            stopword_policy = "aggressive_pt"
        config["stopword_policy"] = stopword_policy

        if config.get("show_halo", False):
            config["detect_communities"] = True
        if not config.get("detect_communities", False):
            config["show_halo"] = False

        # Computed semantic keys for UI and testing.
        strict = config.get("strict_iramuteq_style", True)
        config.setdefault("analysis_mode", "strict" if strict else "legacy")
        config.setdefault("parity_profile", "official_0_8a7" if strict else "default")
        config.setdefault("render_profile", "native")
        selected_words = cls._sanitize_selected_words(config.get("selected_words"))
        config["selected_words"] = selected_words
        config["selected_words_explicit"] = bool(selected_words)
        effective_mode = config.get("analysis_mode", "strict")
        config.setdefault("edge_threshold_enabled", effective_mode != "strict")

        return config

    @staticmethod
    def _coerce_bool(value: Any, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "sim"}
        return bool(value)

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _normalize_coefficient(value: Any) -> int:
        """Normaliza coeficiente para índice IRaMuTeQ [0..27]."""
        if isinstance(value, bool):
            return 0

        if isinstance(value, (int, float)):
            idx = int(value)
            return idx if idx in SIMILARITY_COEFFICIENTS else 0

        raw = str(value or "").strip()
        if not raw:
            return 0

        if raw.isdigit():
            idx = int(raw)
            return idx if idx in SIMILARITY_COEFFICIENTS else 0

        lower_raw = raw.lower()
        for idx, name in SIMILARITY_COEFFICIENTS.items():
            if lower_raw == str(name).lower():
                return idx

        alias_map = {
            "jaccard": 3,
            "cooc": 0,
            "cooccurrence": 0,
            "percentual de coocorrência": 1,
            "pourcentage de cooccurrence": 1,
            "binomial": 27,
            "dice": 12,
            "phi": 13,
            "pearson": 26,
        }
        return alias_map.get(lower_raw, 0)

    @staticmethod
    def _normalize_layout(value: Any) -> str:
        """Normaliza layout para nomes equivalentes aos usados em simi.R."""
        layout = str(value or "frutch").strip()
        return LAYOUT_ALIASES.get(layout, LAYOUT_ALIASES.get(layout.lower(), "frutch"))

    @staticmethod
    def _normalize_community_method(value: Any) -> str:
        """Normaliza método de comunidade para nomes canônicos."""
        method = str(value or "edge_betweenness").strip()
        return COMMUNITY_METHOD_ALIASES.get(
            method,
            COMMUNITY_METHOD_ALIASES.get(method.lower(), "edge_betweenness"),
        )

    @staticmethod
    def _sanitize_selected_words(value: Any) -> List[str]:
        """Keep only displayable content terms from manual similitude selection."""
        if isinstance(value, (str, bytes)):
            raw_items = [value]
        elif isinstance(value, (list, tuple, set)):
            raw_items = list(value)
        else:
            raw_items = []

        selected: List[str] = []
        seen: set[str] = set()
        for item in raw_items:
            token = str(item or "").strip().lower()
            if not token or token in seen:
                continue
            if not is_visual_content_term(token):
                continue
            seen.add(token)
            selected.append(token)
        return selected

    def _normalize_selected_lemmas(self, selected_words: set[str]) -> set[str]:
        """Map selected forms to lemmas when lemma mode is enabled."""
        normalized: set[str] = set()
        for token in selected_words:
            candidate = str(token or "").strip().lower()
            if not candidate:
                continue
            forme = self.corpus.formes.get(candidate)
            if forme is not None and getattr(forme, "lem", None):
                normalized.add(str(forme.lem).strip().lower())
            else:
                normalized.add(candidate)
        return normalized

    def _parse_results(
        self,
        graph_path: Path,
        adjacency_matrix: Optional[Path],
        communities_path: Path,
        centrality_path: Path,
    ) -> SimilarityResult:
        """Parse output files generated by the R similarity script."""
        communities = self._read_communities(communities_path)
        centrality = self._read_centrality(centrality_path)

        return SimilarityResult(
            graph_path=graph_path,
            adjacency_matrix=adjacency_matrix,
            communities=communities,
            centrality=centrality,
        )

    def _read_communities(self, file_path: Path) -> Optional[Dict[str, int]]:
        """Read term -> community mapping from CSV."""
        rows = self._read_csv_rows(file_path)
        if not rows:
            return None

        result: Dict[str, int] = {}
        for row in rows:
            term = str(row.get("node", row.get("term", ""))).strip()
            community_raw = row.get("community")
            if not term or community_raw in (None, ""):
                continue
            try:
                result[term] = int(float(str(community_raw)))
            except (TypeError, ValueError):
                continue
        return result or None

    def _read_centrality(self, file_path: Path) -> Optional[Dict[str, float]]:
        """
        Read term centrality from CSV.

        Prefers weighted degree when available, then degree.
        """
        rows = self._read_csv_rows(file_path)
        if not rows:
            return None

        result: Dict[str, float] = {}
        for row in rows:
            term = str(row.get("node", row.get("term", ""))).strip()
            if not term:
                continue
            value = row.get("weighted_degree", row.get("degree", ""))
            try:
                result[term] = float(str(value))
            except (TypeError, ValueError):
                continue
        return result or None

    @staticmethod
    def _read_csv_rows(file_path: Path) -> List[Dict[str, str]]:
        """Read CSV rows supporting comma/semicolon delimiters."""
        if not file_path.exists():
            return []

        with file_path.open("r", encoding="utf-8", newline="") as file:
            sample = file.read(2048)
            file.seek(0)
            delimiter = ","
            try:
                sniffed = csv.Sniffer().sniff(sample, delimiters=",;")
                delimiter = sniffed.delimiter
            except csv.Error:
                delimiter = ";" if ";" in sample else ","

            reader = csv.DictReader(file, delimiter=delimiter)
            return [dict(row) for row in reader if row]
