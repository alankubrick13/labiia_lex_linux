"""
Analise CHD (Classification Hierarchique Descendante) - Metodo Reinert/ALCESTE.
Usa os scripts R do IRaMuTeQ via RExecutor.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from collections import Counter
from typing import Dict, List, Optional, Any, Tuple

import numpy as np
from PIL import Image
from scipy import sparse
from scipy.cluster.hierarchy import linkage, to_tree

from ..core.corpus import Corpus
from ..core.text_processor import TextProcessor
from ..core.stopword_policy import is_chd_visual_content_term
from ..core.r_script_generator import RScriptGenerator
from ..core.r_executor import RExecutor, RExecutionError, RNotFoundError, RTimeoutError
from ..utils.logger import get_logger
from ..utils.paths import PathManager
from ..visualization.r_integration import RVisualizer
from .reinert import ReinertEngine, ReinertRunConfig, ReinertAnalysisResult


# Colorblind-safe publication palette (CBFriend/ColorBrewer 10-color).
PUBLICATION_PALETTE = [
    "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
    "#56B4E9", "#F0E442", "#000000", "#999999", "#44AA99",
]


@dataclass
class CHDResult:
    """Resultado da analise CHD."""

    n_classes: int
    profiles: Dict[int, List[Tuple[str, float, int, float, str]]]
    class_sizes: Dict[int, int]
    dendrogram_path: Optional[Path] = None
    contingency_table: Optional[Path] = None
    profile_afc_path: Optional[Path] = None
    afc_graph_path: Optional[Path] = None
    afc_row_coords: Optional[np.ndarray] = None
    afc_col_coords: Optional[np.ndarray] = None
    metadata_profiles_path: Optional[Path] = None
    typical_segments: Dict[int, List[Tuple[str, float]]] = field(default_factory=dict)
    antiprofiles: Dict[int, List[Tuple[str, float, int, float, str]]] = field(default_factory=dict)
    repeated_segments: Dict[int, List[Tuple[str, int, float]]] = field(default_factory=dict)
    colored_corpus_path: Optional[Path] = None
    class_text_paths: Dict[int, Path] = field(default_factory=dict)
    newick: Optional[str] = None
    # Which engine produced the classification: "native" (R/IRaMuTeQ Reinert)
    # or "ported_reinert" (pure-Python Reinert fallback). Surfaced for method
    # transparency; never "hclust" — that pseudo-CHD was removed from the flow.
    classification_engine: str = "native"


class CHDAnalysisError(Exception):
    """
    Erro amigavel para analise CHD.

    Segue o padrao: o que aconteceu, por que aconteceu, como resolver.
    """

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class CHDAnalysis:
    """
    Analise CHD/Reinert (ALCESTE).

    Classifica segmentos de texto em classes baseado no vocabulario.
    """

    DEFAULT_PARAMS = {
        "analysis_mode": "strict",
        "nb_classes": 5,
        # min_classes is a true FLOOR (degenerate guard), not the target.
        # Keeping it at the target derailed legitimate native runs that
        # emerge with fewer classes; 2 is the only genuinely degenerate bound.
        "min_classes": 2,
        "max_classes": 5,
        "min_uce": 0,
        "min_freq": 2,
        "classif_mode": 1,
        "tailleuc1": 12,
        "tailleuc2": 14,
        "method": "ward.D2",
        "use_lemmas": True,
        "active_only": True,
        "max_actives": 20000,
        "stopword_policy": "aggressive_pt",
        "strict_stopword_filter": True,
        "prefer_portuguese_br": False,
        "use_native_chd": True,
        "native_fallback_legacy": True,
        "strict_iramuteq_clone": True,
        # Phase-1 over-segmentation target (IRaMuTeQ convention is 10).
        # The final class count emerges from terminal pruning; phase 1 must
        # explore MORE classes than desired so the cut has room to work.
        "nbcl_p1": 10,
        "svd_method": "irlba",
        "auto_expand_actives": False,
        "min_actives_floor": 300,
        "mode_patate": False,
        "typegraph": "png",
        "width": 1400,
        "height": 1000,
        "prefer_readable_afc_profiles": False,
        "adaptive_label_scaling": False,
        "min_visible_words": 80,
        "nb_per_class": 80,
        "max_words": 600,
        "use_ported_reinert": True,
    }

    def __init__(self, corpus: Corpus, output_dir: Path, r_executor: Optional[RExecutor] = None):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.processor = TextProcessor(corpus)
        self.script_generator = RScriptGenerator()
        self.r_executor = r_executor or RExecutor()
        self._logger = get_logger(__name__)

        self._last_result: Optional[CHDResult] = None
        self._class_uce_map: Dict[int, List[int]] = {}
        self._last_doc_ids: List[int] = []
        self._effective_class_uce_map: Dict[int, List[int]] = {}
        self._last_listuce1_path: Optional[Path] = None
        self._last_listuce2_path: Optional[Path] = None
        # True when the result came from the ported Reinert engine because the
        # native R pipeline failed — surfaced in the manifest for transparency.
        self._fallback_via_ported: bool = False

    def _apply_adaptive_active_terms(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Increase max_actives for CHD clone mode when persisted config is too restrictive.

        This prevents sparse AFC/CHD lexical maps (e.g., max_actives=40) while
        preserving explicit user intent when value is already high or unlimited (0).
        """
        merged = dict(config or {})
        if bool(merged.get("strict_iramuteq_clone", True)):
            return merged
        if not bool(merged.get("auto_expand_actives", False)):
            return merged

        try:
            requested = int(merged.get("max_actives", self.DEFAULT_PARAMS.get("max_actives", 20000)))
        except Exception:
            requested = int(self.DEFAULT_PARAMS.get("max_actives", 20000))

        # 0 means "no explicit cap" in existing pipeline. Keep as-is.
        if requested == 0:
            return merged

        try:
            min_floor = int(merged.get("min_actives_floor", 300))
        except Exception:
            min_floor = 300
        min_floor = max(100, min(20000, min_floor))

        try:
            token_nb = int(self.corpus.gettokennb() or 0)
        except Exception:
            token_nb = 0
        try:
            uce_nb = int(self.corpus.getucenb() or 0)
        except Exception:
            uce_nb = 0

        # Conservative corpus-aware recommendation to stay near IRaMuTeQ behavior.
        by_tokens = max(400, token_nb // 18) if token_nb > 0 else 400
        by_uces = max(400, uce_nb * 3) if uce_nb > 0 else 400
        recommended = min(20000, max(min_floor, by_tokens, by_uces))

        if requested < recommended:
            merged["max_actives_requested"] = requested
            merged["max_actives"] = recommended
            self._logger.info(
                "CHD auto-expand max_actives: %s -> %s (tokens=%s, UCEs=%s)",
                requested,
                recommended,
                token_nb,
                uce_nb,
            )

        return merged

    # NOTE: _should_retry_legacy_from_strict / _build_legacy_retry_config were
    # removed. They routed strict-mode failures into a generic hclust/cutree
    # "CHD" that fabricated the requested class count and corrupted the AFC de
    # Perfis. The fallback is now the ported Reinert engine (see run()).

    def run(self, params: Optional[Dict[str, Any]] = None) -> CHDResult:
        """
        Executa analise CHD completa.

        Args:
            params: Parametros customizados (None usa defaults).

        Returns:
            CHDResult com classes e perfis.
        """
        config = {**self.DEFAULT_PARAMS, **(params or {})}
        config = self._normalize_class_targets(config)
        mode_raw = str(config.get("analysis_mode", "") or "").strip().lower()
        if mode_raw not in {"strict", "legacy"}:
            mode_raw = "strict" if bool(config.get("strict_iramuteq_clone", True)) else "legacy"
        strict_mode = mode_raw == "strict"
        # Floor guard only: defaults to 2 (degenerate bound). The user's desired
        # count lives in nb_classes/target and is treated as a soft target — a
        # native run that emerges with fewer classes is WARNED, not rejected.
        min_classes_required = max(2, int(config.get("min_classes", 2) or 2))
        target_classes = max(2, int(config.get("nb_classes", config.get("max_classes", 5)) or 5))
        config["analysis_mode"] = mode_raw
        config["strict_iramuteq_clone"] = strict_mode
        if strict_mode:
            # Strict clone must follow IRaMuTeQ pipeline without custom lexical heuristics.
            config["use_native_chd"] = True
            config["native_fallback_legacy"] = False
            config["stopword_policy"] = "aggressive_pt"
            config["strict_stopword_filter"] = True

        config = self._apply_adaptive_active_terms(config)

        try:
            classif_mode = int(config.get("classif_mode", 1))
            use_native = bool(config.get("use_native_chd", True))

            # ----------------------------------------------------------------
            # CHD fallback policy (Reinert only — NEVER a generic hclust/cutree
            # pseudo-CHD). Order:
            #   1) Native R Reinert (IRaMuTeQ scripts)   — primary path
            #   2) Ported Reinert engine (pure Python)   — true fallback
            #   3) CHDAnalysisError                       — no third fallback
            # The hclust template that used to "guarantee" the class count is no
            # longer reachable from the CHD flow; it fabricated degenerate
            # classes and corrupted the AFC de Perfis.
            # ----------------------------------------------------------------
            native_error: Optional[Exception] = None
            if use_native and classif_mode in {0, 1, 2}:
                try:
                    result = self._run_native_chd(config, classif_mode)
                    if result.n_classes < 2:
                        raise CHDAnalysisError(
                            what="CHD nativo não gerou classes válidas.",
                            why=f"Foram detectadas {result.n_classes} classe(s) (mínimo 2).",
                            how="Ajuste filtros de frequência/segmentação e execute novamente.",
                        )
                    self._warn_if_below_target(result, target_classes)
                    self._last_result = result
                    return result
                except Exception as exc:
                    # A missing lexicon makes the aggressive (strict) stopword
                    # filter fail. That is NOT a reason to abandon native Reinert:
                    # retry once with the filter relaxed (still native Reinert,
                    # never hclust) before falling back to the ported engine.
                    if self._is_relaxable_strict_failure(exc):
                        self._logger.warning(
                            "Filtro estrito de stopwords falhou; repetindo CHD nativo "
                            "com filtro relaxado: %s",
                            exc,
                        )
                        relaxed = {
                            **config,
                            "strict_stopword_filter": False,
                            "strict_iramuteq_clone": False,
                            "analysis_mode": "legacy",
                        }
                        try:
                            result = self._run_native_chd(relaxed, classif_mode)
                            if result.n_classes >= 2:
                                self._warn_if_below_target(result, target_classes)
                                self._last_result = result
                                return result
                            native_error = CHDAnalysisError(
                                what="CHD nativo não gerou classes válidas.",
                                why=f"Foram detectadas {result.n_classes} classe(s) (mínimo 2).",
                                how="Ajuste filtros de frequência/segmentação e execute novamente.",
                            )
                        except Exception as relaxed_exc:
                            native_error = relaxed_exc
                    else:
                        native_error = exc
                    if native_error is not None:
                        self._logger.warning(
                            "CHD nativo (R/IRaMuTeQ) falhou; tentando o engine Reinert "
                            "portado (Python) como fallback: %s",
                            native_error,
                        )

            # True Reinert fallback. Works in single mode; an explicit double-mode
            # request degrades to single-mode Reinert here, which is still a real
            # Reinert classification (unlike the removed hclust path).
            if self._can_use_ported_reinert(config):
                try:
                    result = self._run_legacy_reinert_pipeline(config)
                    if result.n_classes < 2:
                        raise CHDAnalysisError(
                            what="CHD (engine Reinert portado) não gerou classes válidas.",
                            why=f"Foram detectadas {result.n_classes} classe(s) (mínimo 2).",
                            how="Use um corpus com mais segmentos distintos ou reduza o número de classes.",
                        )
                    self._fallback_via_ported = native_error is not None
                    self._warn_if_below_target(result, target_classes)
                    self._last_result = result
                    return result
                except CHDAnalysisError:
                    raise
                except Exception as exc:
                    raise CHDAnalysisError(
                        what="Falha ao executar a CHD (engine Reinert portado).",
                        why=str(exc),
                        how="Verifique o corpus e os parâmetros e execute novamente.",
                    ) from exc

            # Nothing usable remained — surface the original native failure.
            if isinstance(native_error, CHDAnalysisError):
                raise native_error
            if native_error is not None:
                raise CHDAnalysisError(
                    what="Falha ao executar a analise CHD.",
                    why=str(native_error),
                    how="Verifique o corpus e os parametros fornecidos e tente novamente.",
                ) from native_error
            raise CHDAnalysisError(
                what="Nenhum pipeline CHD pôde ser executado.",
                why="O caminho nativo está desativado e o engine portado não é aplicável a este corpus.",
                how="Habilite o CHD nativo ou forneça um corpus com mais segmentos.",
            )
        except CHDAnalysisError:
            raise
        except Exception as exc:
            raise CHDAnalysisError(
                what="Falha ao executar a analise CHD.",
                why=str(exc),
                how="Verifique o corpus e os parametros fornecidos e tente novamente.",
            ) from exc

    def _warn_if_below_target(self, result: "CHDResult", target_classes: int) -> None:
        """Log a soft warning when CHD yields fewer-than-target (but valid) classes.

        The desired class count is a target, not a hard requirement. A native
        Reinert run that legitimately emerges with 2..target classes is a real,
        usable result — we surface it transparently instead of triggering an
        artificial fallback that would fabricate the missing classes.
        """
        try:
            n = int(getattr(result, "n_classes", 0) or 0)
        except (TypeError, ValueError):
            return
        target = max(0, int(target_classes or 0))
        if 2 <= n < target:
            self._logger.warning(
                "CHD retornou %d classe(s), abaixo do alvo de %d. "
                "Prosseguindo com o resultado real (sem fallback artificial).",
                n,
                target,
            )

    def _can_use_ported_reinert(self, config: Dict[str, Any]) -> bool:
        """Return True when the ported Reinert engine has enough real UCEs to run."""
        if not bool(config.get("use_ported_reinert", True)):
            return False
        try:
            uce_count = int(self.corpus.getucenb())
        except Exception:
            return False
        try:
            min_child_size = int(config.get("min_child_size", self.DEFAULT_PARAMS.get("min_uce", 0)) or 5)
        except Exception:
            min_child_size = 5
        min_child_size = max(3, min_child_size)
        return uce_count >= max(2, min_child_size * 2)

    def _run_legacy_reinert_pipeline(self, config: Dict[str, Any]) -> CHDResult:
        """Run the ported historical Python Reinert engine as CHD primary path."""
        target_classes = int(config.get("nb_classes", config.get("max_classes", 5)) or 5)
        try:
            min_docfreq = int(config.get("min_freq", self.DEFAULT_PARAMS.get("min_freq", 2)) or 2)
        except Exception:
            min_docfreq = int(self.DEFAULT_PARAMS.get("min_freq", 2))
        min_docfreq = max(1, min_docfreq)
        if bool(config.get("strict_iramuteq_clone", True)) and min_docfreq < 3:
            min_docfreq = 3
        try:
            max_profile_terms = int(config.get("nb_per_class", self.DEFAULT_PARAMS.get("nb_per_class", 80)) or 80)
        except Exception:
            max_profile_terms = 80
        max_profile_terms = max(20, min(120, max_profile_terms))
        try:
            max_plot_terms = int(config.get("afc_label_limit", 240) or 240)
        except Exception:
            max_plot_terms = 240
        max_plot_terms = max(80, min(360, max_plot_terms))
        try:
            min_child_size = int(config.get("min_child_size", self.DEFAULT_PARAMS.get("min_uce", 0)) or 5)
        except Exception:
            min_child_size = 5
        min_child_size = max(3, min_child_size)

        run_config = ReinertRunConfig(
            min_docfreq=min_docfreq,
            max_classes=max(2, min(20, target_classes)),
            min_child_size=min_child_size,
            min_characteristic_terms=1,
            max_profile_terms=max_profile_terms,
            max_plot_terms=max_plot_terms,
            max_typical_segments=10,
        )
        try:
            reinert_result = ReinertEngine(self.corpus, self.output_dir, run_config).run()
        except ValueError as exc:
            raise CHDAnalysisError(
                what="Corpus não permitiu executar a CHD.",
                why=str(exc),
                how="Use mais segmentos, reduza a frequência mínima ou diminua o número de classes.",
            ) from exc
        return self._convert_reinert_result(reinert_result)

    @staticmethod
    def _convert_reinert_result(result: ReinertAnalysisResult) -> CHDResult:
        """Convert the ported Reinert result to the public CHDResult contract."""
        profiles = {
            int(class_id): [
                (
                    row.term,
                    float(row.chi2),
                    int(row.freq),
                    float(row.pct_in_class),
                    row.sign,
                )
                for row in rows
            ]
            for class_id, rows in result.term_profiles.items()
        }
        antiprofiles = {
            int(class_id): [
                (
                    row.term,
                    float(row.chi2),
                    int(row.freq),
                    float(row.pct_in_class),
                    row.sign,
                )
                for row in rows
            ]
            for class_id, rows in result.anti_profiles.items()
        }
        repeated = {
            int(class_id): [
                (row.text, int(row.count), float(row.score))
                for row in rows
            ]
            for class_id, rows in result.repeated_segments.items()
        }
        return CHDResult(
            n_classes=int(result.n_classes),
            profiles=profiles,
            class_sizes={int(k): int(v) for k, v in result.class_sizes.items()},
            dendrogram_path=result.dendrogram_path,
            contingency_table=result.term_profiles_path,
            profile_afc_path=result.profile_afc_path,
            afc_graph_path=result.profile_afc_path,
            afc_row_coords=result.profile_ca.row_coords if result.profile_ca is not None else None,
            afc_col_coords=result.profile_ca.col_coords if result.profile_ca is not None else None,
            metadata_profiles_path=result.metadata_profiles_path,
            typical_segments={
                int(class_id): [(text, float(score)) for text, score in rows]
                for class_id, rows in result.typical_segments.items()
            },
            antiprofiles=antiprofiles,
            repeated_segments=repeated,
            colored_corpus_path=result.colored_corpus_path,
            class_text_paths=result.class_text_paths,
            newick=result.tree_newick,
            classification_engine="ported_reinert",
        )

    @staticmethod
    def _normalize_class_targets(config: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize CHD class targets so the default flow actively seeks 5 classes."""
        merged = dict(config or {})
        raw_target = merged.get("nb_classes", merged.get("n_classes", 5))
        try:
            target = int(raw_target)
        except (TypeError, ValueError):
            target = 5
        target = max(2, min(20, target))
        merged["nb_classes"] = target
        merged["n_classes"] = target

        # min_classes is a FLOOR, never raised up to the target. A native CHD
        # that legitimately emerges with fewer-than-target classes must not be
        # rejected; the floor only guards against degenerate (<2) results.
        try:
            min_classes = int(merged.get("min_classes", 2) or 2)
        except (TypeError, ValueError):
            min_classes = 2
        merged["min_classes"] = max(2, min(target, min_classes))

        try:
            max_classes = int(merged.get("max_classes", target) or target)
        except (TypeError, ValueError):
            max_classes = target
        merged["max_classes"] = max(target, min(20, max_classes))

        # Phase-1 over-segmentation is DECOUPLED from the desired final count.
        # IRaMuTeQ explores ~10 classes in phase 1 and prunes to the target;
        # coupling nbcl_p1 to the target starved the split tree (nbt too small)
        # and produced too few final classes. Default to max(10, 2*target).
        if "nbcl_p1" not in merged or merged.get("nbcl_p1") in (None, ""):
            merged["nbcl_p1"] = max(10, 2 * target)
        return merged

    def _run_single_pipeline(self, config: Dict[str, Any]) -> CHDResult:
        """Run one CHD script execution (native or legacy depending on config)."""
        # Drop any IRaMuTeQ artifacts from a previous attempt so this run's
        # freshly written n1/Contout/AFC cannot be mixed with stale files.
        self._clear_stale_iramuteq_artifacts()
        files = self._prepare_data(config)
        self._validate_native_chd_inputs(files, config)
        script_path = self._generate_script(files, config)
        self._execute_script(script_path)
        return self._parse_results(config)

    def _run_native_chd(self, config: Dict[str, Any], classif_mode: int) -> CHDResult:
        """Dispatch the native R Reinert pipeline (single or double mode)."""
        if classif_mode == 0:
            return self._run_double_mode(config)
        return self._run_single_pipeline(config)

    @staticmethod
    def _is_relaxable_strict_failure(exc: Exception) -> bool:
        """True for strict-mode failures fixable by relaxing the stopword filter.

        These are environment/lexicon issues (not a degenerate corpus), so the
        correct response is to retry NATIVE Reinert with the aggressive stopword
        filter disabled — never to switch to a generic hclust pseudo-CHD.
        """
        text = str(exc or "").strip().lower()
        if not text:
            return False
        fragments = (
            "strict_stopword_filter=true",
            "lexico nao esta carregado",
            "léxico nao esta carregado",
            "filtro agressivo de stopwords",
        )
        return any(fragment in text for fragment in fragments)

    def _run_double_mode(self, params: Dict[str, Any]) -> CHDResult:
        """
        Execute double classification mode using two R runs.

        Strategy:
        1) Build baseline DTM for profile computation.
        2) Build two truncated-context DTMs (tailleuc1 and tailleuc2).
        3) Run CHD in R for each matrix.
        4) Cross class assignments (class_a, class_b) to form final classes.
        """
        # Double mode runs R in double_a/ and double_b/ subdirs; n1/Contout are
        # rebuilt in the main output_dir. Clear stale family artifacts first.
        self._clear_stale_iramuteq_artifacts()
        strict_mode = bool(params.get("strict_iramuteq_clone", True))
        min_freq = int(params.get("min_freq", 2))
        active_only = bool(params.get("active_only", True))
        if strict_mode and active_only and min_freq < 3:
            min_freq = 3
        use_lemmas = bool(params.get("use_lemmas", True))
        max_actives = int(params.get("max_actives", self.DEFAULT_PARAMS.get("max_actives", 20000)))
        stopword_policy = str(
            params.get("stopword_policy", self.DEFAULT_PARAMS.get("stopword_policy", "aggressive_pt"))
            or self.DEFAULT_PARAMS.get("stopword_policy", "aggressive_pt")
        )
        strict_stopword_filter = bool(params.get("strict_stopword_filter", True))
        prefer_portuguese_br = bool(
            params.get("prefer_portuguese_br", self.DEFAULT_PARAMS.get("prefer_portuguese_br", False))
        )
        if strict_mode:
            stopword_policy = "aggressive_pt"
            strict_stopword_filter = True
        tailleuc1 = max(5, int(params.get("tailleuc1", 12)))
        tailleuc2 = max(5, int(params.get("tailleuc2", 14)))

        # Baseline processor (full UCE text) used for chi2 profiles.
        self.processor = TextProcessor(self.corpus)
        self.processor.build_dtm(
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
            max_actives=max_actives,
            stopword_policy=stopword_policy,
            strict_stopword_filter=strict_stopword_filter,
            strict_iramuteq_clone=strict_mode,
            prefer_portuguese_br=prefer_portuguese_br,
        )
        self._last_doc_ids = list(self.processor.doc_ids)

        processor_a = self._build_truncated_uce_processor(
            limit_words=tailleuc1,
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
            max_actives=max_actives,
            stopword_policy=stopword_policy,
            strict_stopword_filter=strict_stopword_filter,
            strict_iramuteq_clone=strict_mode,
            prefer_portuguese_br=prefer_portuguese_br,
        )
        processor_b = self._build_truncated_uce_processor(
            limit_words=tailleuc2,
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
            max_actives=max_actives,
            stopword_policy=stopword_policy,
            strict_stopword_filter=strict_stopword_filter,
            strict_iramuteq_clone=strict_mode,
            prefer_portuguese_br=prefer_portuguese_br,
        )

        run_a_dir = self.output_dir / "double_a"
        run_b_dir = self.output_dir / "double_b"
        run_a_dir.mkdir(parents=True, exist_ok=True)
        run_b_dir.mkdir(parents=True, exist_ok=True)

        self._execute_chd_for_processor(
            processor=processor_a,
            run_dir=run_a_dir,
            params=params,
            graph_name="dendrogramme_a.png",
        )
        self._execute_chd_for_processor(
            processor=processor_b,
            run_dir=run_b_dir,
            params=params,
            graph_name="dendrogramme_b.png",
        )

        assignment_a = self._read_assignment_map(
            run_dir=run_a_dir,
            doc_ids=processor_a.doc_ids,
        )
        assignment_b = self._read_assignment_map(
            run_dir=run_b_dir,
            doc_ids=processor_b.doc_ids,
        )
        merged_assignments = self._merge_double_assignments(assignment_a, assignment_b)
        self._build_class_map_from_assignments(merged_assignments)

        typegraph = str(params.get("typegraph", "png")).strip().lower()
        if typegraph not in {"png", "svg"}:
            typegraph = "png"
        graph_out = params.get(
            "graph_out",
            "dendrogramme.svg" if typegraph == "svg" else "dendrogramme.png",
        )
        preferred = run_a_dir / ("dendrogramme_a.svg" if typegraph == "svg" else "dendrogramme_a.png")
        fallback = run_b_dir / ("dendrogramme_b.svg" if typegraph == "svg" else "dendrogramme_b.png")
        final_graph = self.output_dir / graph_out
        source_graph = preferred if preferred.exists() else fallback
        if source_graph.exists():
            try:
                final_graph.write_bytes(source_graph.read_bytes())
            except OSError:
                final_graph = source_graph
        else:
            final_graph = None

        class_sizes = {
            class_id: len(uce_ids)
            for class_id, uce_ids in self._class_uce_map.items()
        }
        return self._build_result(
            class_sizes=class_sizes,
            params=params,
            dendrogram_path=final_graph if isinstance(final_graph, Path) and final_graph.exists() else None,
        )

    def _build_truncated_uce_processor(
        self,
        limit_words: int,
        min_freq: int,
        use_lemmas: bool,
        active_only: bool,
        max_actives: int,
        stopword_policy: str,
        strict_stopword_filter: bool,
        strict_iramuteq_clone: bool,
        prefer_portuguese_br: bool,
    ) -> TextProcessor:
        """Build a DTM using only the first `limit_words` of each UCE."""
        processor = TextProcessor(self.corpus)
        processor._build_vocabulary(
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
            stopword_policy=stopword_policy,
            strict_stopword_filter=bool(strict_stopword_filter),
            strict_iramuteq_clone=bool(strict_iramuteq_clone),
            prefer_portuguese_br=bool(prefer_portuguese_br),
        )
        processor._limit_vocabulary(
            max_actives=max_actives,
            use_lemmas=use_lemmas,
            strict_iramuteq_clone=bool(strict_iramuteq_clone),
        )
        if not processor.vocabulary:
            raise CHDAnalysisError(
                what="Vocabulário vazio para CHD em modo double.",
                why="Nenhuma palavra atende aos filtros de frequência.",
                how="Reduza a frequência mínima ou revise o corpus.",
            )

        uce_texts = list(self.corpus.get_uces())
        if not uce_texts:
            raise CHDAnalysisError(
                what="Corpus sem UCEs para CHD em modo double.",
                why="Não há segmentos de texto disponíveis para classificação.",
                how="Importe um corpus válido antes de executar a análise.",
            )

        rows: List[int] = []
        cols: List[int] = []
        data: List[int] = []
        doc_ids: List[int] = []

        for row_idx, (uce_id, text) in enumerate(uce_texts):
            tokens = text.split()
            if limit_words > 0:
                tokens = tokens[:limit_words]
            reduced_text = " ".join(tokens)
            counts = processor._count_words(reduced_text, use_lemmas)
            doc_ids.append(uce_id)
            for word, count in counts.items():
                word_idx = processor._word_to_idx.get(word)
                if word_idx is None or count <= 0:
                    continue
                rows.append(row_idx)
                cols.append(word_idx)
                data.append(int(count))

        processor.doc_ids = doc_ids
        processor.dtm = sparse.csr_matrix(
            (data, (rows, cols)),
            shape=(len(doc_ids), len(processor.vocabulary)),
            dtype=np.float64,
        )
        return processor

    def _execute_chd_for_processor(
        self,
        processor: TextProcessor,
        run_dir: Path,
        params: Dict[str, Any],
        graph_name: str,
    ) -> None:
        """Export one processor and execute CHD script in a dedicated folder."""
        files = processor.export_for_chd(run_dir)
        typegraph = str(params.get("typegraph", "png")).strip().lower()
        if typegraph not in {"png", "svg"}:
            typegraph = "png"
        if typegraph == "svg" and graph_name.lower().endswith(".png"):
            graph_name = graph_name[:-4] + ".svg"
        default_width = int(self.DEFAULT_PARAMS.get("width", 1400))
        default_height = int(self.DEFAULT_PARAMS.get("height", 1000))

        script_params = {
            "pathout": str(run_dir),
            "data_file": files["dtm"].name,
            "graph_out": graph_name,
            "nb_classes": params.get("nb_classes", params.get("n_classes", 0)),
            "min_classes": params.get("min_classes", params.get("nb_classes", 5)),
            "max_classes": params.get("max_classes", params.get("nb_classes", 5)),
            "min_uce": params.get("min_uce", 0),
            "classif_mode": 1,
            "method": params.get("method", "ward.D2"),
            "typegraph": typegraph,
            "width": params.get("width", default_width),
            "height": params.get("height", default_height),
        }
        script_path = self.script_generator.generate_and_save(
            "chd",
            script_params,
            run_dir / "chd_script.R",
        )
        self._execute_script(script_path)

    @staticmethod
    def _read_assignment_map(run_dir: Path, doc_ids: List[int]) -> Dict[int, int]:
        """Read clusters.csv and return mapping doc_id -> class_id."""
        mapping: Dict[int, int] = {}
        clusters_path = run_dir / "clusters.csv"
        if not clusters_path.exists():
            return mapping

        with clusters_path.open("r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader, None)
            for idx, row in enumerate(reader):
                if idx >= len(doc_ids) or not row:
                    continue
                try:
                    class_id = int(float(row[-1]))
                except ValueError:
                    continue
                if class_id <= 0:
                    continue
                mapping[int(doc_ids[idx])] = class_id
        return mapping

    @staticmethod
    def _merge_double_assignments(
        assignment_a: Dict[int, int],
        assignment_b: Dict[int, int],
    ) -> Dict[int, int]:
        """Cross two assignments and map pairs to final class ids."""
        all_doc_ids = sorted(set(assignment_a.keys()) | set(assignment_b.keys()))
        if not all_doc_ids:
            return {}

        pairs: Dict[int, Tuple[int, int]] = {
            doc_id: (assignment_a.get(doc_id, -1), assignment_b.get(doc_id, -1))
            for doc_id in all_doc_ids
        }
        pair_counter = Counter(pair for pair in pairs.values() if pair != (-1, -1))
        sorted_pairs = [pair for pair, _ in pair_counter.most_common()]
        pair_to_class = {pair: idx + 1 for idx, pair in enumerate(sorted_pairs)}

        merged: Dict[int, int] = {}
        next_class = len(pair_to_class) + 1
        for doc_id in all_doc_ids:
            pair = pairs[doc_id]
            if pair in pair_to_class:
                merged[doc_id] = pair_to_class[pair]
            else:
                # fallback for docs missing in one run
                pair_to_class[pair] = next_class
                merged[doc_id] = next_class
                next_class += 1
        return merged

    def _build_class_map_from_assignments(self, assignments: Dict[int, int]) -> None:
        """Populate class->UCE map from doc_id->class mapping."""
        self._class_uce_map = {}
        for doc_id in self._last_doc_ids:
            class_id = assignments.get(int(doc_id))
            if class_id is None:
                continue
            if int(class_id) <= 0:
                continue
            self._class_uce_map.setdefault(int(class_id), []).append(int(doc_id))

    def _prepare_data(self, params: Dict[str, Any]) -> Dict[str, Path]:
        """Prepara dados para o script R."""
        strict_mode = bool(params.get("strict_iramuteq_clone", True))
        min_freq = int(params.get("min_freq", 2))
        active_only = bool(params.get("active_only", True))
        if strict_mode and active_only and min_freq < 3:
            # make_actives_nb in IRaMuTeQ enforces freq >= 3 for active forms.
            min_freq = 3
        use_lemmas = bool(params.get("use_lemmas", True))
        max_actives = int(params.get("max_actives", self.DEFAULT_PARAMS.get("max_actives", 20000)))
        stopword_policy = str(
            params.get("stopword_policy", self.DEFAULT_PARAMS.get("stopword_policy", "aggressive_pt"))
            or self.DEFAULT_PARAMS.get("stopword_policy", "aggressive_pt")
        )
        strict_stopword_filter = bool(params.get("strict_stopword_filter", True))
        prefer_portuguese_br = bool(
            params.get("prefer_portuguese_br", self.DEFAULT_PARAMS.get("prefer_portuguese_br", False))
        )
        classif_mode = int(params.get("classif_mode", 1))
        use_native = True if strict_mode else bool(params.get("use_native_chd", True))
        if strict_mode:
            stopword_policy = "aggressive_pt"
            strict_stopword_filter = bool(getattr(self.corpus, "lexicon", None) is not None)

        self._last_listuce1_path = None
        self._last_listuce2_path = None

        if classif_mode == 2:
            return self._prepare_data_by_uci(
                min_freq=min_freq,
                use_lemmas=use_lemmas,
                active_only=active_only,
                max_actives=max_actives,
                stopword_policy=stopword_policy,
                strict_stopword_filter=strict_stopword_filter,
                use_native=use_native,
                strict_iramuteq_clone=strict_mode,
                prefer_portuguese_br=prefer_portuguese_br,
            )

        self.processor.build_dtm(
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
            max_actives=max_actives,
            stopword_policy=stopword_policy,
            strict_stopword_filter=strict_stopword_filter,
            strict_iramuteq_clone=strict_mode,
            prefer_portuguese_br=prefer_portuguese_br,
        )
        self._last_doc_ids = list(self.processor.doc_ids)
        if use_native and classif_mode in {0, 1, 2}:
            files = self.processor.export_for_chd_native(
                self.output_dir,
                tailleuc1=int(params.get("tailleuc1", 12)),
                tailleuc2=int(params.get("tailleuc2", 14)),
                classif_mode=classif_mode,
            )
            self._last_listuce1_path = files.get("listuce1")
            self._last_listuce2_path = files.get("listuce2")
            return files

        return self.processor.export_for_chd(self.output_dir)

    def _prepare_data_by_uci(
        self,
        min_freq: int,
        use_lemmas: bool,
        active_only: bool,
        max_actives: int,
        stopword_policy: str,
        strict_stopword_filter: bool,
        use_native: bool,
        strict_iramuteq_clone: bool,
        prefer_portuguese_br: bool,
    ) -> Dict[str, Path]:
        """Prepara matriz CHD por UCI (modo simples UCI)."""
        self.processor._build_vocabulary(
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
            stopword_policy=stopword_policy,
            strict_stopword_filter=bool(strict_stopword_filter),
            strict_iramuteq_clone=bool(strict_iramuteq_clone),
            prefer_portuguese_br=bool(prefer_portuguese_br),
        )
        self.processor._limit_vocabulary(
            max_actives=max_actives,
            use_lemmas=use_lemmas,
            strict_iramuteq_clone=bool(strict_iramuteq_clone),
        )
        if not self.processor.vocabulary:
            raise CHDAnalysisError(
                what="Vocabulário vazio para CHD em modo UCI.",
                why="Nenhuma palavra atende aos filtros de frequência.",
                how="Reduza a frequência mínima ou revise o corpus.",
            )

        rows: List[int] = []
        cols: List[int] = []
        data: List[int] = []
        doc_ids: List[int] = []

        for row_idx, uci in enumerate(self.corpus.ucis):
            uce_ids = [uce.ident for uce in uci.uces]
            if not uce_ids:
                continue
            uci_segments = [segment for _, segment in self.corpus.getconcorde(uce_ids)]
            merged_text = " ".join(uci_segments)
            if not merged_text.strip():
                continue

            counts = self.processor._count_words(merged_text, use_lemmas)
            if not counts:
                continue

            new_row_idx = len(doc_ids)
            doc_ids.append(uci.ident)
            for word, count in counts.items():
                word_idx = self.processor._word_to_idx.get(word)
                if word_idx is None:
                    continue
                rows.append(new_row_idx)
                cols.append(word_idx)
                data.append(int(count))

        if not doc_ids:
            raise CHDAnalysisError(
                what="Nao foi possivel montar a matriz CHD por UCI.",
                why="As UCIs do corpus nao possuem texto suficiente apos filtros.",
                how="Revise o corpus ou execute CHD no modo UCE.",
            )

        self.processor.doc_ids = doc_ids
        self._last_doc_ids = list(doc_ids)
        self.processor.dtm = sparse.csr_matrix(
            (data, (rows, cols)),
            shape=(len(doc_ids), len(self.processor.vocabulary)),
            dtype=np.float64,
        )
        if use_native:
            files = self.processor.export_for_chd_native(
                self.output_dir,
                tailleuc1=12,
                tailleuc2=14,
                classif_mode=2,
            )
            self._last_listuce1_path = files.get("listuce1")
            return files
        return self.processor.export_for_chd(self.output_dir)

    def _generate_script(self, files: Dict[str, Path], params: Dict[str, Any]) -> Path:
        """Gera script R para CHD."""
        typegraph = str(params.get("typegraph", "png")).strip().lower()
        if typegraph not in {"png", "svg"}:
            typegraph = "png"
        default_width = int(self.DEFAULT_PARAMS.get("width", 1400))
        default_height = int(self.DEFAULT_PARAMS.get("height", 1000))
        graph_default = "dendrogramme.svg" if typegraph == "svg" else "dendrogramme.png"
        graph_out = params.get("graph_out", graph_default)
        classif_mode = int(params.get("classif_mode", 1))
        strict = bool(params.get("strict_iramuteq_clone", True))
        use_native = True if strict else bool(params.get("use_native_chd", True))

        if use_native and classif_mode in {0, 1, 2}:
            rscripts_dir = PathManager.rscripts_dir()
            nbcl_p1 = int(params.get("nbcl_p1", self.DEFAULT_PARAMS.get("nbcl_p1", 5)))
            nbt_default = max(1, nbcl_p1 - 1)
            script_params = {
                "pathout": str(self.output_dir),
                "nb_classes": params.get("nb_classes", params.get("n_classes", 5)),
                "nbt": params.get("nbt", nbt_default),
                "min_uce": params.get("min_uce", 0),
                "classif_mode": classif_mode,
                "svd_method": params.get("svd_method", self.DEFAULT_PARAMS.get("svd_method", "irlba")),
                "mode_patate": params.get("mode_patate", False),
                "script_chd": str(rscripts_dir / "CHD.R"),
                "script_chdtxt": str(rscripts_dir / "chdtxt.R"),
                "script_anacor": str(rscripts_dir / "anacor.R"),
                "script_rgraph": str(rscripts_dir / "Rgraph.R"),
                "data_file": files["dtm"].name,
                "data_file2": files.get("dtm2", self.output_dir / "TableUc2.csv").name,
                "listuce1_file": files.get("listuce1", self.output_dir / "listuce1.csv").name,
                "listuce2_file": files.get("listuce2", self.output_dir / "listuce2.csv").name,
                "uce_out": "uce.csv",
                "n1_1_file": "n1-1.csv",
                "n1_file": "n1.csv",
                "clusters_file": "clusters.csv",
                "rdendro_file": "Rdendro.RData",
                "graph_out": graph_out,
                "typegraph": typegraph,
                "width": params.get("width", default_width),
                "height": params.get("height", default_height),
            }
            return self.script_generator.generate_and_save(
                "chd_native",
                script_params,
                self.output_dir / "chd_script.R",
            )

        script_params = {
            "pathout": str(self.output_dir),
            "data_file": files["dtm"].name,
            "graph_out": graph_out,
            "nb_classes": params.get("nb_classes", params.get("n_classes", 5)),
            "min_classes": params.get("min_classes", params.get("nb_classes", 5)),
            "max_classes": params.get("max_classes", params.get("nb_classes", 5)),
            "min_uce": params.get("min_uce", 0),
            "classif_mode": params.get("classif_mode", 0),
            "method": params.get("method", "ward.D2"),
            "typegraph": typegraph,
            "width": params.get("width", default_width),
            "height": params.get("height", default_height),
        }

        return self.script_generator.generate_and_save(
            "chd",
            script_params,
            self.output_dir / "chd_script.R",
        )

    def _execute_script(self, script_path: Path) -> None:
        """Executa script R de analise CHD."""
        try:
            self.r_executor.execute(
                script_path=str(script_path),
                working_dir=str(self.output_dir),
                timeout=600,
            )
        except RNotFoundError as exc:
            raise CHDAnalysisError(
                what="R nao encontrado no sistema.",
                why=str(exc),
                how="Instale o R (4.0+) e verifique se o Rscript esta disponivel no PATH.",
            ) from exc
        except RTimeoutError as exc:
            raise CHDAnalysisError(
                what="Tempo limite excedido na analise CHD.",
                why=str(exc),
                how="Tente reduzir o corpus ou aumente o tempo limite.",
            ) from exc
        except RExecutionError as exc:
            raise CHDAnalysisError(
                what="Falha na execucao do script CHD.",
                why=str(exc),
                how="Verifique se os pacotes R necessarios estao instalados.",
            ) from exc

    def _validate_native_chd_inputs(self, files: Dict[str, Path], params: Dict[str, Any]) -> None:
        """Validate native MatrixMarket inputs before running CHD.R."""
        strict_mode = bool(params.get("strict_iramuteq_clone", True))
        use_native = True if strict_mode else bool(params.get("use_native_chd", True))
        classif_mode = int(params.get("classif_mode", 1))
        if not use_native or classif_mode not in {0, 1, 2}:
            return

        matrix_roles = [("native_uc1", files.get("dtm"))]
        if classif_mode == 0:
            matrix_roles.append(("native_uc2", files.get("dtm2")))

        for role, path in matrix_roles:
            if not isinstance(path, Path):
                continue
            diagnostics = self._write_chd_matrix_diagnostics(path, role=role)
            if diagnostics.get("degenerate"):
                raise CHDAnalysisError(
                    what="Matriz CHD nativa degenerada.",
                    why=(
                        f"A matriz {role} tem {diagnostics.get('non_empty_rows', 0)} linha(s) "
                        f"e {diagnostics.get('non_empty_cols', 0)} coluna(s) nao vazias "
                        f"apos os filtros."
                    ),
                    how=(
                        "A analise sera reexecutada no caminho seguro. "
                        "Se o problema persistir, reduza filtros ou revise a segmentacao do corpus."
                    ),
                )

    def _write_chd_matrix_diagnostics(self, matrix_path: Path, *, role: str) -> Dict[str, Any]:
        """Write diagnostics for a MatrixMarket CHD input and return the role entry."""
        matrix_path = Path(matrix_path)
        diagnostics = self._matrix_market_diagnostics(matrix_path)
        diagnostics["role"] = str(role or "matrix")
        diagnostics["path"] = str(matrix_path)

        output_path = self.output_dir / "chd_matrix_diagnostics.json"
        payload: Dict[str, Any] = {"matrices": {}}
        if output_path.exists():
            try:
                existing = json.loads(output_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    payload.update(existing)
            except Exception:
                payload = {"matrices": {}}
        matrices = payload.setdefault("matrices", {})
        if not isinstance(matrices, dict):
            matrices = {}
            payload["matrices"] = matrices
        matrices[diagnostics["role"]] = diagnostics
        payload["latest"] = diagnostics
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return diagnostics

    @staticmethod
    def _matrix_market_diagnostics(matrix_path: Path) -> Dict[str, Any]:
        """Return basic shape/sparsity diagnostics for a coordinate MatrixMarket file."""
        base = {
            "exists": matrix_path.exists(),
            "rows": 0,
            "cols": 0,
            "nnz": 0,
            "non_empty_rows": 0,
            "non_empty_cols": 0,
            "empty_rows": 0,
            "empty_cols": 0,
            "degenerate": True,
        }
        if not matrix_path.exists():
            return base

        rows = cols = declared_nnz = 0
        non_empty_rows: set[int] = set()
        non_empty_cols: set[int] = set()
        saw_shape = False
        try:
            with matrix_path.open("r", encoding="utf-8") as file:
                for raw in file:
                    line = str(raw or "").strip()
                    if not line or line.startswith("%"):
                        continue
                    parts = line.split()
                    if not saw_shape:
                        if len(parts) >= 3:
                            rows = int(float(parts[0]))
                            cols = int(float(parts[1]))
                            declared_nnz = int(float(parts[2]))
                            saw_shape = True
                        continue
                    if len(parts) < 3:
                        continue
                    try:
                        row_idx = int(float(parts[0]))
                        col_idx = int(float(parts[1]))
                        value = float(parts[2])
                    except ValueError:
                        continue
                    if value == 0:
                        continue
                    non_empty_rows.add(row_idx)
                    non_empty_cols.add(col_idx)
        except Exception as exc:
            base["error"] = str(exc)
            return base

        nnz = max(declared_nnz, len(non_empty_rows), len(non_empty_cols))
        non_rows = len(non_empty_rows)
        non_cols = len(non_empty_cols)
        degenerate = rows < 2 or cols < 2 or declared_nnz <= 0 or non_rows < 2 or non_cols < 2
        return {
            "exists": True,
            "rows": rows,
            "cols": cols,
            "nnz": declared_nnz if declared_nnz > 0 else nnz,
            "non_empty_rows": non_rows,
            "non_empty_cols": non_cols,
            "empty_rows": max(0, rows - non_rows),
            "empty_cols": max(0, cols - non_cols),
            "degenerate": bool(degenerate),
        }

    def _parse_results(self, params: Dict[str, Any]) -> CHDResult:
        """Le e parseia resultados do R."""
        class_sizes: Dict[int, int] = {}
        self._class_uce_map = {}
        # Floor guard only (default 2). A valid native n1.csv with fewer-than-target
        # classes must NOT trigger the clusters.csv (hclust) fallback below.
        min_classes_required = max(2, int(params.get("min_classes", 2) or 2))
        use_native = True if bool(params.get("strict_iramuteq_clone", True)) else bool(params.get("use_native_chd", True))
        classif_mode = int(params.get("classif_mode", 1))

        if use_native and classif_mode in {0, 1, 2}:
            n1_path = self.output_dir / "n1.csv"
            assignments = self._read_assignment_rows(n1_path)
            if assignments:
                uc_map = self._read_uc_to_uces_map(self._last_listuce1_path)
                self._class_uce_map = self._map_n1_assignments_to_uces(assignments, uc_map)
                class_sizes = {
                    int(class_id): len(uce_ids)
                    for class_id, uce_ids in self._class_uce_map.items()
                    if uce_ids
                }

        # True only when the classification came from the native R n1.csv just
        # written in this output_dir; that file may then be trusted verbatim.
        from_native_n1 = bool(class_sizes)

        clusters_path = self.output_dir / "clusters.csv"
        should_try_clusters = (
            (not class_sizes)
            or (len(class_sizes) < min_classes_required)
        )
        if should_try_clusters and clusters_path.exists():
            cluster_sizes: Dict[int, int] = {}
            cluster_map: Dict[int, List[int]] = {}
            with clusters_path.open("r", encoding="utf-8") as file:
                reader = csv.reader(file)
                next(reader, None)
                for idx, row in enumerate(reader):
                    if not row:
                        continue
                    cluster_value = row[-1]
                    try:
                        class_id = int(float(cluster_value))
                    except ValueError:
                        continue
                    if class_id <= 0:
                        continue

                    cluster_sizes[class_id] = cluster_sizes.get(class_id, 0) + 1
                    if idx < len(self._last_doc_ids):
                        uce_id = int(self._last_doc_ids[idx])
                        cluster_map.setdefault(class_id, []).append(uce_id)

            # Usa clusters.csv quando ele estiver mais informativo/estável.
            if (
                len(cluster_sizes) > len(class_sizes)
                or (not class_sizes and bool(cluster_sizes))
            ):
                class_sizes = cluster_sizes
                self._class_uce_map = cluster_map
                # clusters.csv is NOT the native n1.csv classification; n1 must
                # be regenerated from this map before post-processing.
                from_native_n1 = False

        dendro_name = str(params.get("graph_out", "dendrogramme.png"))
        dendrogram_path = self.output_dir / dendro_name
        if not dendrogram_path.exists() and dendrogram_path.suffix.lower() == ".png":
            alt_svg = dendrogram_path.with_suffix(".svg")
            if alt_svg.exists():
                dendrogram_path = alt_svg
        if not dendrogram_path.exists():
            dendrogram_path = None

        return self._build_result(
            class_sizes, params, dendrogram_path, trust_existing_n1=from_native_n1
        )

    @staticmethod
    def _read_assignment_rows(path: Path) -> List[Tuple[Optional[int], int]]:
        """Read class rows from n1/clusters CSV-like outputs."""
        if not path.exists():
            return []

        assignments: List[Tuple[Optional[int], int]] = []
        with path.open("r", encoding="utf-8", newline="") as file:
            sample = file.read(2048)
            file.seek(0)
            delimiter = ";"
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
            except csv.Error:
                delimiter = ";" if ";" in sample else ","

            reader = csv.reader(file, delimiter=delimiter)
            next(reader, None)
            for row in reader:
                if not row:
                    continue
                try:
                    class_id = int(float(row[-1]))
                except (TypeError, ValueError):
                    continue
                if class_id <= 0:
                    continue

                row_id: Optional[int] = None
                if row[0] != "":
                    try:
                        row_id = int(float(row[0]))
                    except (TypeError, ValueError):
                        row_id = None

                assignments.append((row_id, class_id))
        return assignments

    @staticmethod
    def _read_uc_to_uces_map(path: Optional[Path]) -> Dict[int, List[int]]:
        """Read listuce mapping (uce;uc) into uc -> list[uce]."""
        if path is None or not path.exists():
            return {}

        mapping: Dict[int, List[int]] = {}
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.reader(file, delimiter=";")
            next(reader, None)
            for row in reader:
                if len(row) < 2:
                    continue
                try:
                    uce_id = int(float(row[0]))
                    uc_idx = int(float(row[1]))
                except ValueError:
                    continue
                mapping.setdefault(uc_idx, []).append(uce_id)
        return mapping

    def _map_n1_assignments_to_uces(
        self,
        assignments: List[Tuple[Optional[int], int]],
        uc_to_uces: Dict[int, List[int]],
    ) -> Dict[int, List[int]]:
        """Map native n1 rows to actual UCE ids."""
        class_map: Dict[int, List[int]] = {}
        known_docs = {int(doc_id) for doc_id in self._last_doc_ids}

        for row_idx, (row_id, class_id) in enumerate(assignments):
            if int(class_id) <= 0:
                continue
            targets: List[int] = []
            if row_id is not None:
                if row_id in known_docs:
                    targets = [row_id]
                elif row_id in uc_to_uces:
                    targets = list(uc_to_uces[row_id])
                elif (row_id - 1) in uc_to_uces:
                    targets = list(uc_to_uces[row_id - 1])

            if not targets and row_idx < len(self._last_doc_ids):
                targets = [int(self._last_doc_ids[row_idx])]

            if not targets:
                continue

            bucket = class_map.setdefault(int(class_id), [])
            for uce_id in targets:
                uce_id = int(uce_id)
                if uce_id not in bucket:
                    bucket.append(uce_id)

        return class_map

    def _build_result(
        self,
        class_sizes: Dict[int, int],
        params: Dict[str, Any],
        dendrogram_path: Optional[Path],
        trust_existing_n1: bool = False,
    ) -> CHDResult:
        """Build final CHD result with profiles and metadata associations.

        ``trust_existing_n1`` is True only when the native R pipeline just wrote
        a consistent n1.csv in this output_dir; every other path regenerates it
        from the current classification (see _run_reinert_post_processing).
        """
        # CHD class ids start at 1. Drop class 0 / negatives (unclassified noise).
        class_sizes = {
            int(class_id): int(count)
            for class_id, count in (class_sizes or {}).items()
            if int(class_id) > 0 and int(count) > 0
        }
        self._class_uce_map = {
            int(class_id): [int(uce_id) for uce_id in uce_ids]
            for class_id, uce_ids in (self._class_uce_map or {}).items()
            if int(class_id) > 0 and uce_ids
        }
        if not class_sizes:
            raise CHDAnalysisError(
                what="Nenhuma classe CHD válida foi gerada.",
                why="As atribuições retornaram apenas classes vazias ou não classificadas (classe 0).",
                how="Reduza filtros do corpus (freq. mínima/tamanho UCE) e execute novamente.",
            )

        sorted_class_ids = sorted(self._class_uce_map)
        classif_mode = int(params.get("classif_mode", 1))
        effective_uce_map = self._expand_class_map_to_uces(classif_mode=classif_mode)
        self._effective_class_uce_map = effective_uce_map
        ucecl = [effective_uce_map.get(class_id, []) for class_id in sorted_class_ids]
        mode_raw = str(params.get("analysis_mode", "") or "").strip().lower()
        strict_clone = bool(
            params.get("strict_iramuteq_clone", mode_raw == "strict")
        )

        # Keep metadata profile (signed chi2) for CHD table/inspection in UI.
        metadata_profiles_path = self.output_dir / "chd_metadata_profiles.csv"
        self.corpus.make_and_write_profile_et(
            ucecl,
            metadata_profiles_path,
            signed_chi2=True,
        )
        if not metadata_profiles_path.exists():
            metadata_profiles_path = None

        # Default lexical profiles from local matrix (fallback path).
        profiles = self._compute_chi2_profiles(class_sizes)

        afc_graph_path: Optional[Path] = None
        profile_afc_path: Optional[Path] = None
        alternate_profile_afc_path: Optional[Path] = None
        afc_row_coords: Optional[np.ndarray] = None
        afc_col_coords: Optional[np.ndarray] = None

        reinert_outputs: Optional[Dict[str, Path]] = None
        try:
            reinert_outputs = self._run_reinert_post_processing(
                class_sizes=class_sizes,
                ucecl=ucecl,
                params=params,
                trust_existing_n1=trust_existing_n1,
                sorted_class_ids=sorted_class_ids,
            )
        except CHDAnalysisError as exc:
            if strict_clone:
                raise CHDAnalysisError(
                    what="Falha no pós-processamento Reinert em modo strict.",
                    why=str(exc),
                    how=(
                        "No modo strict não há fallback visual/local. "
                        "Corrija os insumos CHD e execute novamente."
                    ),
                ) from exc
            self._logger.warning(
                "CHD post-processing IRaMuTeQ clone failed. Keeping native CHD classes and falling back to local AFC/profiles: %s",
                exc,
            )

        if reinert_outputs:
            chistable_path = reinert_outputs.get("chistable")
            contout_path = reinert_outputs.get("contout")
            clone_profiles = self._read_profiles_from_reinert_tables(
                class_sizes=class_sizes,
                chistable_path=chistable_path,
                contout_path=contout_path,
            )
            if clone_profiles:
                profiles = clone_profiles

            afc2dcl = reinert_outputs.get("afc2dcl")
            afc2dl = reinert_outputs.get("afc2dl")
            afc2dsl = reinert_outputs.get("afc2dsl")
            afc2del = reinert_outputs.get("afc2del")
            afc_graph_path = next(
                (
                    p
                    for p in [afc2dcl, afc2dl, afc2dsl, afc2del]
                    if isinstance(p, Path) and p.exists()
                ),
                None,
            )
            profile_afc_path = next(
                (
                    p
                    for p in [afc2dl, afc2dcl, afc2dsl, afc2del]
                    if isinstance(p, Path) and p.exists()
                ),
                afc_graph_path,
            )

            afc_row_path = reinert_outputs.get("afc_row")
            afc_col_path = reinert_outputs.get("afc_col")
            if isinstance(afc_row_path, Path):
                afc_row_coords = self._read_afc_coords(afc_row_path)
            if isinstance(afc_col_path, Path):
                afc_col_coords = self._read_afc_coords(afc_col_path)

            # Render a readability-oriented AFC profile graph only as fallback/alternative.
            # The IRaMuTeQ/R AFC2DL artifact remains the primary "AFC Perfis" output
            # whenever it exists and validates as a graph.
            fallback_graph = None
            fallback_row = None
            fallback_col = None
            prefer_readable_profiles = bool(
                params.get(
                    "prefer_readable_afc_profiles",
                    self.DEFAULT_PARAMS.get("prefer_readable_afc_profiles", False),
                )
            )
            clone_afc_graph_valid = self._is_valid_graph_file(afc_graph_path)
            clone_profile_valid = self._is_valid_graph_file(profile_afc_path)
            should_render_fallback = (
                prefer_readable_profiles
                or not clone_afc_graph_valid
                or not clone_profile_valid
                or (not strict_clone and afc_graph_path is None)
            )
            if should_render_fallback:
                try:
                    fallback_graph, fallback_row, fallback_col = self._run_post_chd_afc(profiles, params)
                except Exception as exc:
                    self._logger.warning(
                        "Falha ao gerar AFC Perfis legivel; mantendo grafico clone: %s",
                        exc,
                    )

            if not clone_profile_valid:
                profile_afc_path = None
            if not clone_afc_graph_valid:
                afc_graph_path = None

            if fallback_graph is not None and self._is_valid_graph_file(fallback_graph):
                if profile_afc_path is None:
                    profile_afc_path = fallback_graph
                else:
                    alternate_profile_afc_path = fallback_graph
                if afc_graph_path is None:
                    afc_graph_path = fallback_graph
            elif profile_afc_path is None:
                profile_afc_path = afc_graph_path

            if afc_row_coords is None:
                afc_row_coords = fallback_row
            if afc_col_coords is None:
                afc_col_coords = fallback_col
        else:
            if strict_clone:
                raise CHDAnalysisError(
                    what="Modo strict sem artefatos Reinert nativos.",
                    why="Os arquivos de perfil/AFC do fluxo IRaMuTeQ não foram gerados.",
                    how=(
                        "Revise o pipeline CHD nativo (n1/Contout/chistable) e execute novamente "
                        "sem fallback legado."
                    ),
                )
            afc_graph_path, afc_row_coords, afc_col_coords = self._run_post_chd_afc(profiles, params)
            profile_afc_path = afc_graph_path

        if not self._is_valid_graph_file(profile_afc_path):
            profile_afc_path = None
        if not self._is_valid_graph_file(afc_graph_path):
            afc_graph_path = None

        if bool(params.get("require_profile_afc_output", False)) and not self._is_valid_graph_file(profile_afc_path):
            raise CHDAnalysisError(
                what="AFC Perfis nao foi gerado corretamente.",
                why="O arquivo de saida do grafico AFC Perfis nao existe, esta vazio ou invalido.",
                how="Verifique os pacotes R obrigatorios (especialmente 'ca' e 'wordcloud') e execute a analise novamente.",
            )

        profiles = self._filter_profiles_for_visual_output(profiles)
        antiprofiles = self._compute_antiprofiles(profiles)
        typical_segments = self._compute_typical_segments(effective_uce_map, profiles, top_n=10)
        repeated_segments = self._compute_repeated_segments(effective_uce_map)
        class_text_paths = self.export_all_class_texts(
            output_dir=self.output_dir / "chd_classes",
            class_uce_map=effective_uce_map,
        )
        colored_corpus_path = self._export_colored_corpus(effective_uce_map)

        # Enhanced dendrogram is optional; always try it (strict mode keeps native as fallback).
        enhanced_dendro = self._generate_enhanced_dendrogram(
            profiles, class_sizes, params
        )
        if enhanced_dendro is not None:
            dendrogram_path = enhanced_dendro

        tree_newick = self._build_newick_from_profiles(profiles)

        result = CHDResult(
            n_classes=len(class_sizes),
            profiles=profiles,
            class_sizes=class_sizes,
            dendrogram_path=dendrogram_path,
            contingency_table=None,
            profile_afc_path=profile_afc_path,
            afc_graph_path=afc_graph_path,
            afc_row_coords=afc_row_coords,
            afc_col_coords=afc_col_coords,
            metadata_profiles_path=metadata_profiles_path,
            typical_segments=typical_segments,
            antiprofiles=antiprofiles,
            repeated_segments=repeated_segments,
            colored_corpus_path=colored_corpus_path,
            class_text_paths=class_text_paths,
            newick=tree_newick,
        )
        if reinert_outputs:
            artifact_attr_map = {
                "contout": "contout_path",
                "contsup": "contsup_path",
                "contet": "contet_path",
                "profiles": "profiles_path",
                "antiprofiles": "antiprofiles_path",
                "chistable": "chistable_path",
                "ptable": "ptable_path",
                "sbyclasse": "sbyclasse_path",
                "afc_facteur": "afc_facteur_path",
                "afc_row": "afc_row_path",
                "afc_col": "afc_col_path",
                "row_coords": "row_coords_path",
                "col_coords": "col_coords_path",
                "eigenvalues": "eigenvalues_path",
                "afc2dl_notplotted": "afc2dl_notplotted_path",
                "afc2dsl_notplotted": "afc2dsl_notplotted_path",
                "afc2del_notplotted": "afc2del_notplotted_path",
                "afc2dcl_notplotted": "afc2dcl_notplotted_path",
                "rdata": "rdata_path",
            }
            native_artifacts: Dict[str, str] = {}
            for key, attr_name in artifact_attr_map.items():
                artifact = reinert_outputs.get(key)
                if isinstance(artifact, Path) and artifact.exists():
                    setattr(result, attr_name, artifact)
                    native_artifacts[key] = str(artifact)
            if native_artifacts:
                manifest_path = self.output_dir / "manifest.json"
                try:
                    manifest_payload = {
                        "version": "1.0.9",
                        "analysis": "chd",
                        "engine": "r_native_iramuteq_profiles",
                        "profile_afc_primary": str(profile_afc_path) if profile_afc_path else None,
                        "profile_afc_alternative": str(alternate_profile_afc_path) if alternate_profile_afc_path else None,
                        "artifacts": native_artifacts,
                    }
                    manifest_path.write_text(
                        json.dumps(manifest_payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    setattr(result, "manifest_path", manifest_path)
                except Exception as exc:
                    self._logger.warning("Falha ao escrever manifest CHD nativo: %s", exc)
        if alternate_profile_afc_path is not None:
            try:
                if profile_afc_path is None or alternate_profile_afc_path.resolve() != Path(profile_afc_path).resolve():
                    setattr(result, "alternate_profile_afc_path", alternate_profile_afc_path)
            except Exception:
                setattr(result, "alternate_profile_afc_path", alternate_profile_afc_path)
        return result

    @staticmethod
    def _is_valid_graph_file(path: Optional[Path]) -> bool:
        """Validate that a graph artifact exists and is not an empty raster export."""
        if path is None:
            return False
        candidate = Path(path)
        if not candidate.exists() or not candidate.is_file():
            return False
        if candidate.suffix.lower() not in {".png", ".svg", ".jpg", ".jpeg", ".bmp", ".gif"}:
            return False
        try:
            if candidate.stat().st_size <= 0:
                return False
        except OSError:
            return False
        return not CHDAnalysis._is_blank_raster_graph(candidate)

    @staticmethod
    def _is_blank_raster_graph(path: Path) -> bool:
        """Reject near-empty raster outputs that are visually all white."""
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".gif"}:
            return False
        try:
            with Image.open(path) as image:
                rgb = image.convert("RGB")
                extrema = rgb.getextrema()
        except OSError:
            return False
        if not extrema:
            return True
        return all(channel_min >= 250 for channel_min, _channel_max in extrema)

    @staticmethod
    def _parse_numeric_cell(raw_value: Any) -> float:
        """Parse numeric CSV cells supporting comma decimal separator."""
        text = str(raw_value or "").strip().strip('"')
        if not text or text.upper() == "NA":
            return 0.0
        text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return 0.0

    @staticmethod
    def _coerce_profile_chi2(chi2: float, freq: int, total: float) -> float:
        """Map non-finite Reinert chi2 values to large finite sentinels."""
        if np.isfinite(chi2):
            return float(chi2)
        sign = -1.0 if np.signbit(chi2) else 1.0
        pct = (float(freq) / total * 100.0) if total > 0 else 0.0
        magnitude = max(100.0, float(freq) * 2.0 + pct)
        return sign * magnitude

    def _resolve_active_lemmas_for_reinert(
        self,
        min_freq: int,
        max_actives: int,
    ) -> List[str]:
        """
        Resolve active lemmas for Reinert profiles.

        Strict path mirrors IRaMuTeQ `make_actives_nb(max_actives, 1)`.
        """
        strict_terms, _lim = self.corpus.make_actives_nb(int(max_actives or 0), 1)

        # Respect caller minimum frequency if stricter than IRa's >=3.
        min_freq_i = max(1, int(min_freq or 1))
        if min_freq_i > 3:
            strict_terms = [
                term
                for term in strict_terms
                if int(getattr(self.corpus.lems.get(term), "freq", 0)) >= min_freq_i
            ]

        # Keep only lemmas that are present in current lexical matrix when available.
        if self.processor.vocabulary:
            vocab_set = {str(token) for token in self.processor.vocabulary}
            filtered = [term for term in strict_terms if term in vocab_set]
            if filtered:
                return filtered

        if strict_terms:
            return strict_terms

        # Defensive fallback (should be rare in strict clone).
        fallback: List[Tuple[str, int]] = []
        for lemma, item in self.corpus.lems.items():
            if int(getattr(item, "act", 1)) != 1:
                continue
            freq = int(getattr(item, "freq", 0))
            if freq < min_freq_i:
                continue
            fallback.append((str(lemma), freq))
        fallback.sort(key=lambda pair: pair[0], reverse=True)
        fallback.sort(key=lambda pair: pair[1], reverse=True)
        terms = [lemma for lemma, _freq in fallback]
        limit = int(max_actives or 0)
        return terms[:limit] if limit > 0 else terms

    def _resolve_supplementary_lemmas_for_reinert(
        self,
        min_freq: int,
        max_actives: int,
        active_terms: List[str],
    ) -> List[str]:
        """Resolve supplementary lemmas (act == 2) for ContSupOut.csv."""
        supp_terms, _lim = self.corpus.make_actives_nb(int(max_actives or 0), 2)
        active_set = {str(token) for token in (active_terms or [])}
        min_freq_i = max(1, int(min_freq or 1))

        filtered = [
            term
            for term in supp_terms
            if term not in active_set
            and int(getattr(self.corpus.lems.get(term), "freq", 0)) >= min_freq_i
        ]
        return filtered

    def _run_reinert_post_processing(
        self,
        class_sizes: Dict[int, int],
        ucecl: List[List[int]],
        params: Dict[str, Any],
        trust_existing_n1: bool = False,
        sorted_class_ids: Optional[List[int]] = None,
    ) -> Dict[str, Path]:
        """
        Execute IRaMuTeQ Reinert post-processing (profiles + AFC2D*).

        Mirrors textreinert.py second stage:
        - build Contout / ContSupOut / ContEtOut,
        - run ReinertTxtProf-equivalent R script.

        n1.csv MUST describe the SAME classification used to build Contout.
        - trust_existing_n1=True: the native R pipeline just wrote a consistent
          n1.csv in this output_dir (reference path) — keep it verbatim.
        - trust_existing_n1=False: any other path (double mode, ported engine,
          retry) regenerates n1.csv from the current class map so a stale n1.csv
          from an earlier attempt cannot corrupt the chi-square table (the root
          cause of the blank-AFC bug). Either way we validate consistency below.
        """
        clnb = len([cid for cid in class_sizes.keys() if int(cid) > 0])
        if clnb <= 0:
            raise CHDAnalysisError(
                what="Pós-processamento CHD IRaMuTeQ não pôde iniciar.",
                why="Nenhuma classe válida foi identificada para gerar perfis.",
                how="Execute a CHD novamente e verifique os parâmetros de classificação.",
            )

        n1_path = self.output_dir / "n1.csv"
        n1_regenerated = not trust_existing_n1 or not n1_path.exists()
        if n1_regenerated:
            # Regenerate n1 from the EXACT ucecl used to build Contout, so class
            # labels (1..clnb) line up with the Contout columns.
            if sorted_class_ids is None:
                sorted_class_ids = [cid for cid in sorted(class_sizes) if int(cid) > 0]
            self._write_n1_from_ucecl(n1_path, ucecl, sorted_class_ids)
        if not n1_path.exists():
            raise CHDAnalysisError(
                what="Arquivo base da CHD não encontrado para pós-processamento.",
                why=f"Arquivo ausente: {n1_path}",
                how="Execute a CHD novamente para regenerar os artefatos de classificação.",
            )

        # Hard consistency guard: n1 classes must be exactly {1..clnb} —
        # a mismatch means artifacts from different classifications got mixed
        # (the Inf-chi-square / blank-AFC bug). The row-count check only applies
        # to a regenerated n1: the NATIVE n1 legitimately keeps class-0 rows
        # (unclassified units), so its length differs from ucecl by design.
        self._validate_n1_consistency(
            n1_path, clnb, ucecl, check_row_count=n1_regenerated
        )

        min_freq = int(params.get("min_freq", self.DEFAULT_PARAMS.get("min_freq", 2)))
        if bool(params.get("strict_iramuteq_clone", True)) and min_freq < 3:
            min_freq = 3
        max_actives = int(params.get("max_actives", self.DEFAULT_PARAMS.get("max_actives", 20000)))
        active_terms = self._resolve_active_lemmas_for_reinert(
            min_freq=min_freq,
            max_actives=max_actives,
        )
        if not active_terms:
            raise CHDAnalysisError(
                what="Pós-processamento CHD IRaMuTeQ sem termos ativos.",
                why="Nenhum lema ativo foi encontrado após os filtros de frequência.",
                how="Reduza a frequência mínima ou desative filtros mais restritivos da CHD.",
            )
        supplementary_terms = self._resolve_supplementary_lemmas_for_reinert(
            min_freq=min_freq,
            max_actives=max_actives,
            active_terms=active_terms,
        )

        contout_path = self.output_dir / "Contout.csv"
        contsup_path = self.output_dir / "ContSupOut.csv"
        contet_path = self.output_dir / "ContEtOut.csv"
        self.corpus.make_and_write_profile(active_terms, ucecl, contout_path)
        self.corpus.make_and_write_profile(supplementary_terms, ucecl, contsup_path)
        self.corpus.make_and_write_profile_et(ucecl, contet_path, signed_chi2=False)

        typegraph = str(params.get("typegraph", "png")).strip().lower()
        if typegraph not in {"png", "svg"}:
            typegraph = "png"
        ext = "svg" if typegraph == "svg" else "png"

        rscripts_dir = PathManager.rscripts_dir()
        script_params = {
            "pathout": str(self.output_dir),
            "clnb": clnb,
            "taillecar": float(params.get("taillecar", 0.9)),
            "typegraph": typegraph,
            "script_chdfunct": str(rscripts_dir / "chdfunct.R"),
            "script_rgraph": str(rscripts_dir / "Rgraph.R"),
            "n1_file": n1_path.name,
            "contout_file": contout_path.name,
            "contsup_file": contsup_path.name,
            "contet_file": contet_path.name,
            "profiles_file": "Profiles.csv",
            "antiprofiles_file": "Antiprofile.csv",
            "chisqtable_file": "chistable.csv",
            "ptable_file": "ptable.csv",
            "sbyclasse_file": "sbyClasseOut.csv",
            "afc_facteur_file": "afc_facteur.csv",
            "afc_col_file": "afc_col.csv",
            "afc_row_file": "afc_row.csv",
            "afc2dl_out": f"AFC2DL.{ext}",
            "afc2dsl_out": f"AFC2DSL.{ext}",
            "afc2del_out": f"AFC2DEL.{ext}",
            "afc2dcl_out": f"AFC2DCL.{ext}",
            "rdata_file": "RData.RData",
        }
        script_path = self.script_generator.generate_and_save(
            "chd_reinert_profiles",
            script_params,
            self.output_dir / "chd_reinert_profiles.R",
        )
        self._execute_script(script_path)

        # The R AFC plot guards each PlotAfc2dCoul in tryCatch and, on failure,
        # leaves a BLANK PNG plus an afc2dXl_error.txt marker. Surface that as a
        # hard error instead of silently shipping an empty AFC de Perfis.
        self._raise_if_afc_plot_failed()

        outputs = {
            "contout": contout_path,
            "contsup": contsup_path,
            "contet": contet_path,
            "profiles": self.output_dir / "Profiles.csv",
            "antiprofiles": self.output_dir / "Antiprofile.csv",
            "chistable": self.output_dir / "chistable.csv",
            "ptable": self.output_dir / "ptable.csv",
            "sbyclasse": self.output_dir / "sbyClasseOut.csv",
            "afc_facteur": self.output_dir / "afc_facteur.csv",
            "afc_col": self.output_dir / "afc_col.csv",
            "afc_row": self.output_dir / "afc_row.csv",
            "row_coords": self.output_dir / "row_coords.csv",
            "col_coords": self.output_dir / "col_coords.csv",
            "eigenvalues": self.output_dir / "eigenvalues.csv",
            "afc2dl": self.output_dir / f"AFC2DL.{ext}",
            "afc2dl_notplotted": self.output_dir / f"AFC2DL.{ext}_notplotted.csv",
            "afc2dsl": self.output_dir / f"AFC2DSL.{ext}",
            "afc2dsl_notplotted": self.output_dir / f"AFC2DSL.{ext}_notplotted.csv",
            "afc2del": self.output_dir / f"AFC2DEL.{ext}",
            "afc2del_notplotted": self.output_dir / f"AFC2DEL.{ext}_notplotted.csv",
            "afc2dcl": self.output_dir / f"AFC2DCL.{ext}",
            "afc2dcl_notplotted": self.output_dir / f"AFC2DCL.{ext}_notplotted.csv",
            "rdata": self.output_dir / "RData.RData",
        }
        return outputs

    def _write_n1_from_class_map(self, output_path: Path) -> None:
        """Best-effort n1.csv writer when native CHD artifact is unavailable."""
        assignments: List[Tuple[int, int]] = []
        for class_id, uce_ids in (self._class_uce_map or {}).items():
            for uce_id in uce_ids:
                try:
                    assignments.append((int(uce_id), int(class_id)))
                except (TypeError, ValueError):
                    continue
        if not assignments:
            return
        assignments.sort(key=lambda item: item[0])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["", "x"])
            for idx, (_uce_id, class_id) in enumerate(assignments, start=1):
                writer.writerow([idx, class_id])

    def _write_n1_from_ucecl(
        self,
        output_path: Path,
        ucecl: List[List[int]],
        sorted_class_ids: List[int],
    ) -> None:
        """Write n1.csv from the SAME ucecl used to build Contout.

        Class labels are remapped to contiguous 1..clnb in the order of
        ``sorted_class_ids`` so they line up with the Contout columns (which
        are emitted in that same order). This is what keeps the chi-square
        table finite: every Contout column has a matching, non-empty n1 class.
        """
        assignments: List[Tuple[int, int]] = []
        for position, uce_ids in enumerate(ucecl, start=1):
            for uce_id in uce_ids:
                try:
                    assignments.append((int(uce_id), position))
                except (TypeError, ValueError):
                    continue
        if not assignments:
            return
        assignments.sort(key=lambda item: item[0])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["", "x"])
            for idx, (_uce_id, class_label) in enumerate(assignments, start=1):
                writer.writerow([idx, class_label])

    def _validate_n1_consistency(
        self,
        n1_path: Path,
        clnb: int,
        ucecl: List[List[int]],
        check_row_count: bool = True,
    ) -> None:
        """Fail loudly when n1.csv does not match the Contout classification.

        Guards against the blank-AFC bug: a stale n1.csv (from a previous CHD
        attempt) paired with a freshly built Contout produced empty classes,
        Inf chi-square and an aborted (blank) AFC plot. Here we refuse to run
        the R post-processing unless n1 is internally coherent.

        ``check_row_count`` must be False for the NATIVE n1.csv: that file
        legitimately keeps class-0 (unclassified) rows and, in double/UC modes,
        is indexed by classification units rather than UCEs — so its row count
        is NOT comparable to ``ucecl`` (which holds classified UCEs only). The
        class-set check below still applies to both paths and is what catches
        artifacts mixed from different classifications.
        """
        distinct: set = set()
        n_rows = 0
        try:
            with n1_path.open("r", encoding="utf-8", newline="") as file:
                reader = csv.reader(file, delimiter=";")
                next(reader, None)  # header
                for row in reader:
                    if not row:
                        continue
                    try:
                        cls = int(str(row[-1]).strip())
                    except (TypeError, ValueError):
                        continue
                    n_rows += 1
                    if cls > 0:
                        distinct.add(cls)
        except OSError as exc:
            raise CHDAnalysisError(
                what="Não foi possível ler n1.csv para validação do pós-processamento.",
                why=str(exc),
                how="Execute a CHD novamente para regenerar os artefatos de classificação.",
            ) from exc

        expected = set(range(1, int(clnb) + 1))
        if distinct != expected:
            raise CHDAnalysisError(
                what="Artefatos CHD inconsistentes para o pós-processamento.",
                why=(
                    f"n1.csv contém as classes {sorted(distinct)} mas o perfil espera "
                    f"clnb={clnb} (classes {sorted(expected)}). Os artefatos vêm de "
                    "classificações diferentes."
                ),
                how="Reexecute a CHD para regenerar n1/Contout a partir da mesma classificação.",
            )

        if check_row_count:
            expected_rows = sum(len(uces) for uces in ucecl)
            if expected_rows and n_rows != expected_rows:
                raise CHDAnalysisError(
                    what="Contagem de UCEs inconsistente entre n1.csv e Contout.",
                    why=f"n1.csv tem {n_rows} linhas mas a classificação corrente tem {expected_rows} UCEs.",
                    how="Reexecute a CHD para regenerar n1/Contout a partir da mesma classificação.",
                )

    # Output artifacts of the IRaMuTeQ CHD/AFC family. Cleared at the start of
    # each pipeline attempt so a previous run's files cannot leak into the next.
    _IRAMUTEQ_STALE_ARTIFACTS = (
        "n1.csv", "n1-1.csv", "uce.csv", "clusters.csv",
        "Contout.csv", "ContSupOut.csv", "ContEtOut.csv",
        "chistable.csv", "ptable.csv", "Profiles.csv", "Antiprofile.csv",
        "sbyClasseOut.csv", "afc_facteur.csv", "afc_col.csv", "afc_row.csv",
        "row_coords.csv", "col_coords.csv", "eigenvalues.csv", "RData.RData",
        "afc2dl_error.txt", "afc2dsl_error.txt", "afc2del_error.txt", "afc2dcl_error.txt",
    )
    _IRAMUTEQ_STALE_GLOBS = (
        "AFC2D*.png", "AFC2D*.svg", "AFC2D*_notplotted.csv",
    )

    def _clear_stale_iramuteq_artifacts(self) -> None:
        """Remove leftover IRaMuTeQ CHD/AFC output files from a prior attempt.

        Only OUTPUT artifacts are removed; CHD inputs (TableUc1.csv, listuce1.csv,
        generated R scripts) are left untouched. Missing files are ignored.
        """
        out_dir = self.output_dir
        if not out_dir or not Path(out_dir).exists():
            return
        for name in self._IRAMUTEQ_STALE_ARTIFACTS:
            try:
                (Path(out_dir) / name).unlink()
            except FileNotFoundError:
                continue
            except OSError as exc:
                self._logger.debug("Não foi possível remover artefato antigo %s: %s", name, exc)
        for pattern in self._IRAMUTEQ_STALE_GLOBS:
            for stale in Path(out_dir).glob(pattern):
                try:
                    stale.unlink()
                except OSError as exc:
                    self._logger.debug("Não foi possível remover %s: %s", stale, exc)

    def _raise_if_afc_plot_failed(self) -> None:
        """Fail when the primary AFC de Perfis plot (AFC2DL) was skipped in R.

        AFC2DL carries the active terms — it is THE AFC de Perfis. If the R plot
        aborted, an afc2dl_error.txt marker is present and the PNG is blank; we
        must not present that. Supplementary plots (SL/EL/CL) only get a warning.
        """
        out_dir = Path(self.output_dir)
        primary_marker = out_dir / "afc2dl_error.txt"
        if primary_marker.exists():
            try:
                detail = primary_marker.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                detail = ""
            raise CHDAnalysisError(
                what="Falha ao renderizar a AFC de Perfis (AFC2DL).",
                why=(
                    "O R abortou o desenho dos termos ativos da AFC"
                    + (f": {detail}" if detail else ".")
                ),
                how=(
                    "Verifique a coerência de n1/Contout/chistable e os pacotes R "
                    "(ca, wordcloud) e execute a CHD novamente."
                ),
            )
        for name in ("afc2dsl_error.txt", "afc2del_error.txt", "afc2dcl_error.txt"):
            marker = out_dir / name
            if marker.exists():
                self._logger.warning(
                    "Gráfico AFC suplementar não gerado (%s); seguindo com a AFC2DL principal.",
                    name,
                )

    def _read_profiles_from_reinert_tables(
        self,
        class_sizes: Dict[int, int],
        chistable_path: Optional[Path],
        contout_path: Optional[Path],
    ) -> Dict[int, List[Tuple[str, float, int, float, str]]]:
        """
        Build CHD profiles from IRaMuTeQ outputs (chistable + Contout).

        chistable provides signed chi2 by class; Contout provides class counts.
        """
        if chistable_path is None or not chistable_path.exists():
            return {}

        class_ids = sorted(int(cid) for cid in class_sizes.keys() if int(cid) > 0)
        if not class_ids:
            return {}

        counts_by_token: Dict[str, List[int]] = {}
        if contout_path is not None and contout_path.exists():
            with contout_path.open("r", encoding="utf-8", newline="") as file:
                reader = csv.reader(file, delimiter=";")
                for row in reader:
                    if len(row) < 2:
                        continue
                    token = str(row[0] or "").strip().strip('"')
                    if not token:
                        continue
                    values: List[int] = []
                    for raw in row[1:1 + len(class_ids)]:
                        values.append(int(round(self._parse_numeric_cell(raw))))
                    if len(values) < len(class_ids):
                        values.extend([0] * (len(class_ids) - len(values)))
                    counts_by_token[token] = values

        profiles: Dict[int, List[Tuple[str, float, int, float, str]]] = {
            int(cid): [] for cid in class_ids
        }
        with chistable_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.reader(file, delimiter=";")
            header = next(reader, None)
            if not header:
                return profiles

            for row in reader:
                if len(row) < 2:
                    continue
                token = str(row[0] or "").strip().strip('"')
                if not token or token.startswith("*"):
                    continue
                counts = counts_by_token.get(token, [0] * len(class_ids))
                total = float(sum(max(0, int(v)) for v in counts))

                for idx, class_id in enumerate(class_ids, start=1):
                    if idx >= len(row):
                        continue
                    freq = int(counts[idx - 1]) if idx - 1 < len(counts) else 0
                    pct = (float(freq) / total * 100.0) if total > 0 else 0.0
                    chi2 = self._coerce_profile_chi2(
                        float(self._parse_numeric_cell(row[idx])),
                        freq=freq,
                        total=total,
                    )
                    sign = "+" if chi2 >= 0 else "-"
                    profiles[class_id].append((token, chi2, freq, pct, sign))

        for class_id in class_ids:
            profiles[class_id].sort(key=lambda item: abs(float(item[1])), reverse=True)
        return profiles

    def _generate_enhanced_dendrogram(
        self,
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
        class_sizes: Dict[int, int],
        params: Dict[str, Any],
    ) -> Optional[Path]:
        """Generate enhanced dendrogram with word lists per class."""
        if not profiles or len(profiles) < 2:
            return None

        try:
            from .chd_visualization import render_chd_dendrogram

            typegraph = str(params.get("typegraph", "png")).strip().lower()
            if typegraph not in {"png", "svg"}:
                typegraph = "png"
            result_path = self.output_dir / f"dendrogramme_enhanced.{typegraph}"
            layout_path = self.output_dir / "chd_dendrogram_layout.json"
            render_chd_dendrogram(
                profiles=profiles,
                class_sizes=class_sizes,
                output_path=result_path,
                layout_path=layout_path,
                newick=self._build_newick_from_profiles(profiles),
                max_terms_per_class=max(8, min(30, int(params.get("nb_words", 18) or 18))),
            )
            if result_path.exists():
                self._logger.info("Enhanced dendrogram generated (python): %s", result_path)
                return result_path
        except Exception as exc:
            self._logger.warning("Failed to generate enhanced dendrogram via python renderer: %s", exc)

        # Preferred path: use the dedicated dendrogram.R script (better margins and variants).
        try:
            result_path = self._generate_enhanced_dendrogram_with_rscripts(
                profiles=profiles,
                class_sizes=class_sizes,
                params=params,
            )
            if result_path is not None and result_path.exists():
                self._logger.info("Enhanced dendrogram generated (rscripts): %s", result_path)
                return result_path
        except Exception as exc:
            self._logger.warning("Failed to generate enhanced dendrogram via rscripts: %s", exc)

        # Fallback path: legacy template generator.
        return self._generate_enhanced_dendrogram_legacy(
            profiles=profiles,
            class_sizes=class_sizes,
            params=params,
        )

    @staticmethod
    def _filter_profiles_for_visual_output(
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
    ) -> Dict[int, List[Tuple[str, float, int, float, str]]]:
        filtered: Dict[int, List[Tuple[str, float, int, float, str]]] = {}
        for class_id, rows in (profiles or {}).items():
            kept: List[Tuple[str, float, int, float, str]] = []
            seen: set[str] = set()
            for item in rows or []:
                if len(item) < 1:
                    continue
                term = str(item[0] or "").strip()
                if not term or not is_chd_visual_content_term(term):
                    continue
                key = term.lower()
                if key in seen:
                    continue
                seen.add(key)
                kept.append(item)
            filtered[int(class_id)] = kept
        return filtered

    @staticmethod
    def _build_balanced_newick(class_ids: List[int]) -> str:
        """Build balanced Newick expression from class ids."""
        labels = [str(int(cid)) for cid in class_ids]

        def _build(nodes: List[str]) -> str:
            if len(nodes) == 1:
                return nodes[0]
            mid = len(nodes) // 2
            return f"({_build(nodes[:mid])},{_build(nodes[mid:])})"

        return _build(labels)

    def _build_newick_from_profiles(
        self,
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
    ) -> Optional[str]:
        """Build Newick tree from class chi2 profiles (best-effort)."""
        class_ids = sorted(int(cid) for cid in profiles.keys())
        if len(class_ids) < 2:
            return None
        if len(class_ids) == 2:
            return f"({class_ids[0]},{class_ids[1]});"

        by_class_chi2: Dict[int, Dict[str, float]] = {}
        vocab: set[str] = set()

        for cid in class_ids:
            chi_map: Dict[str, float] = {}
            class_rows = profiles.get(cid, [])
            for item in class_rows:
                if len(item) < 2:
                    continue
                word = str(item[0]).strip()
                if not word:
                    continue
                chi = float(item[1])
                if not np.isfinite(chi):
                    continue
                chi_map[word] = chi
                vocab.add(word)
            by_class_chi2[cid] = chi_map

        if not vocab:
            return f"{self._build_balanced_newick(class_ids)};"

        vocab_list = sorted(vocab)
        class_matrix = np.zeros((len(class_ids), len(vocab_list)), dtype=np.float64)
        for row_idx, cid in enumerate(class_ids):
            chi_map = by_class_chi2.get(cid, {})
            for col_idx, word in enumerate(vocab_list):
                class_matrix[row_idx, col_idx] = float(chi_map.get(word, 0.0))

        try:
            link = linkage(class_matrix, method="ward")
            root = to_tree(link, rd=False)

            def _node_to_newick(node) -> str:
                if node.is_leaf():
                    idx = max(0, min(int(node.id), len(class_ids) - 1))
                    return str(class_ids[idx])
                left = _node_to_newick(node.get_left())
                right = _node_to_newick(node.get_right())
                return f"({left},{right})"

            return f"{_node_to_newick(root)};"
        except Exception:
            return f"{self._build_balanced_newick(class_ids)};"

    def _generate_enhanced_dendrogram_with_rscripts(
        self,
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
        class_sizes: Dict[int, int],
        params: Dict[str, Any],
    ) -> Optional[Path]:
        """Generate enhanced dendrogram through r_scripts/dendrogram.R."""
        class_ids = [
            int(cid)
            for cid in sorted(int(raw_cid) for raw_cid in profiles.keys())
            if int(cid) > 0 and int(class_sizes.get(int(cid), 0)) > 0
        ]
        if len(class_ids) < 2:
            return None

        typegraph = str(params.get("typegraph", "png")).strip().lower()
        if typegraph not in {"png", "svg"}:
            typegraph = "png"

        default_width = int(self.DEFAULT_PARAMS.get("width", 1400))
        default_height = int(self.DEFAULT_PARAMS.get("height", 1000))
        width = max(2400, int(params.get("width", default_width)))
        height = max(1700, int(params.get("height", default_height)))
        nb_words = max(10, int(params.get("nb_words", 60)))

        dendro_type = str(params.get("dendro_type", "profile")).strip().lower()
        if dendro_type not in {"profile", "cloud", "pie", "barplot"}:
            dendro_type = "profile"
        default_direction = "downwards" if dendro_type == "profile" else "rightwards"
        direction = str(params.get("direction", default_direction)).strip().lower()
        if direction not in {"downwards", "rightwards"}:
            direction = "downwards"
        type_dendro = str(params.get("type_dendro", "phylogram")).strip().lower()
        if type_dendro not in {"cladogram", "phylogram"}:
            type_dendro = "phylogram"

        raw_lab = params.get("lab")
        if isinstance(raw_lab, str):
            lab = [item.strip() for item in raw_lab.split(",") if item.strip()]
        elif isinstance(raw_lab, (list, tuple)):
            lab = [str(item).strip() for item in raw_lab if str(item).strip()]
        else:
            lab = None
        if lab and len(lab) not in {len(class_ids)}:
            lab = None

        words_rows: List[Dict[str, Any]] = []
        for cid in class_ids:
            if int(cid) <= 0:
                continue
            class_rows = profiles.get(cid, [])
            for rank, item in enumerate(class_rows, start=1):
                if len(item) < 2:
                    continue
                word = str(item[0]).strip()
                if not word:
                    continue
                chi = float(item[1])
                if not np.isfinite(chi):
                    continue
                freq = int(item[2]) if len(item) > 2 else 0
                words_rows.append(
                    {
                        "class_id": int(cid),
                        "word": word,
                        "chi2": float(chi),
                        "freq": int(freq),
                        "rank": int(rank),
                    }
                )

        if not words_rows:
            return None

        try:
            tree_newick = self._build_newick_from_profiles(profiles)
        except Exception:
            tree_newick = None
        if not tree_newick:
            tree_newick = f"{self._build_balanced_newick(class_ids)};"

        tree_file = self.output_dir / "chd_tree_enhanced.txt"
        tree_file.write_text(tree_newick, encoding="utf-8")

        classes_file = self.output_dir / "chd_classes_enhanced.csv"
        total = float(sum(max(0, int(class_sizes.get(cid, 0))) for cid in class_ids))
        if total <= 0:
            total = float(len(class_ids))
        with classes_file.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["class_id", "percentage", "n_segments"],
            )
            writer.writeheader()
            for cid in class_ids:
                count = max(0, int(class_sizes.get(cid, 0)))
                pct = (float(count) / total) * 100.0 if total > 0 else 0.0
                writer.writerow(
                    {
                        "class_id": int(cid),
                        "percentage": float(pct),
                        "n_segments": int(count),
                    }
                )

        words_file = self.output_dir / "chd_words_enhanced.csv"
        with words_file.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(
                file,
                fieldnames=["class_id", "word", "chi2", "freq", "rank"],
            )
            writer.writeheader()
            for row in words_rows:
                writer.writerow(row)

        graph_out = f"dendrogramme_enhanced.{typegraph}"
        output_file = self.output_dir / graph_out

        viz = RVisualizer()
        args = {
            "tree_file": str(tree_file),
            "classes_file": str(classes_file),
            "words_file": str(words_file),
            "output_file": str(output_file),
            "width": int(width),
            "height": int(height),
            "dpi": int(params.get("dpi", 240)),
            "nbbycl": int(nb_words),
            "type_dendro": type_dendro,
            "dendro_type": dendro_type,
            "bw": bool(params.get("bw", False)),
            "lab": lab,
            "direction": direction,
        }
        success, stdout, _ = viz.bridge.execute_script("dendrogram.R", args, timeout=240)
        if success and output_file.exists():
            return output_file

        self._logger.warning("dendrogram.R failed for enhanced CHD: %s", stdout)
        return None

    def _generate_enhanced_dendrogram_legacy(
        self,
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
        class_sizes: Dict[int, int],
        params: Dict[str, Any],
    ) -> Optional[Path]:
        """Fallback: legacy enhanced dendrogram template."""
        try:
            class_ids = [
                int(cid)
                for cid in sorted(int(raw_cid) for raw_cid in profiles.keys())
                if int(cid) > 0 and int(class_sizes.get(int(cid), 0)) > 0
            ]
            if len(class_ids) < 2:
                return None
            typegraph = str(params.get("typegraph", "png")).strip().lower()
            if typegraph not in {"png", "svg"}:
                typegraph = "png"

            # Export signed chi2 table for R (rows=words, cols=classes)
            chi2_path = self.output_dir / "chd_dendro_chi2.csv"
            vocab = set()
            by_class_chi2: Dict[int, Dict[str, float]] = {}
            for cid in class_ids:
                chi2s: Dict[str, float] = {}
                for item in profiles.get(cid, []):
                    if len(item) >= 3:
                        word = item[0]
                        chi = float(item[1])
                        if not np.isfinite(chi):
                            continue
                        vocab.add(word)
                        chi2s[word] = chi
                by_class_chi2[cid] = chi2s

            if not vocab:
                return None

            sorted_words = sorted(vocab)
            with chi2_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([""] + [str(c) for c in class_ids])
                for w in sorted_words:
                    row = [by_class_chi2[c].get(w, 0.0) for c in class_ids]
                    writer.writerow([w] + row)

            # Export class sizes for R
            sizes_path = self.output_dir / "chd_class_sizes.csv"
            with sizes_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["class_id", "count"])
                for cid in class_ids:
                    writer.writerow([cid, class_sizes.get(cid, 0)])

            default_width = int(self.DEFAULT_PARAMS.get("width", 1400))
            default_height = int(self.DEFAULT_PARAMS.get("height", 1000))
            width = int(params.get("width", default_width))
            height = int(params.get("height", default_height))
            nb_words = int(params.get("nb_words", 60))
            graph_out = f"dendrogramme_enhanced.{typegraph}"
            script_content = self.script_generator.generate_chd_enhanced_script({
                "pathout": str(self.output_dir),
                "chi2_file": chi2_path.name,
                "sizes_file": sizes_path.name,
                "graph_out": graph_out,
                "typegraph": typegraph,
                "width": width,
                "height": height,
                "nb_words": nb_words,
            })

            script_path = self.output_dir / "chd_enhanced_dendro.R"
            script_path.write_text(script_content, encoding="utf-8")
            self._execute_script(script_path)

            result_path = self.output_dir / graph_out
            if result_path.exists():
                self._logger.info("Enhanced dendrogram generated (legacy): %s", result_path)
                return result_path
        except Exception as exc:
            self._logger.warning("Legacy enhanced dendrogram failed: %s", exc)

        return None

    def _run_post_chd_afc(
        self,
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
        params: Dict[str, Any],
    ) -> Tuple[Optional[Path], Optional[np.ndarray], Optional[np.ndarray]]:
        """Executa AFC sobre matriz de perfis lemma x classe apos CHD usando RVisualizer.

        Gera visualização estilo IRaMuTeQ com stopoverlap (evita sobreposição).
        """
        if not profiles:
            return None, None, None

        profiles = self._select_profiles_for_profile_afc(profiles, params)
        if not any(profiles.values()):
            return None, None, None
            
        class_ids = sorted(profiles.keys())
        if len(class_ids) < 2:
            return None, None, None
            
        self._logger.info(f"Iniciando AFC pós-CHD para {len(class_ids)} classes...")
            
        # 1. Build Frequency Matrix (Word x Class)
        vocab = set()
        by_class_freq = {}
        by_class_chi2 = {}
        
        for cid in class_ids:
            freqs = {}
            chi2s = {}
            # profile items: (word, chi2, freq, pct, sign)
            for item in profiles.get(cid, []):
                if len(item) >= 3:
                     word = str(item[0] or "").strip()
                     if not word or not is_chd_visual_content_term(word):
                         continue
                     chi = float(item[1])
                     freq = int(item[2])
                     if freq > 0:
                         vocab.add(word)
                         freqs[word] = freq
                         chi2s[word] = chi
            by_class_freq[cid] = freqs
            by_class_chi2[cid] = chi2s
            
        if not vocab:
            return None, None, None
            
        sorted_words = sorted(list(vocab))
        
        # Write Frequency Matrix (for R analysis)
        matrix_path = self.output_dir / "chd_profile_matrix.csv"
        with matrix_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([""] + [f"class_{c}" for c in class_ids])
            for w in sorted_words:
                row = [by_class_freq[c].get(w, 0) for c in class_ids]
                writer.writerow([w] + row)

        # Write Chi2 Matrix (Critical for sizing/coloring in IRaMuTeQ style)
        chi2_path = self.output_dir / "chd_profile_chi2.csv"
        with chi2_path.open("w", encoding="utf-8", newline="") as f:
             # Standard CSV (comma) for R read.csv default
             writer = csv.writer(f) 
             writer.writerow([""] + [f"class_{c}" for c in class_ids])
             for w in sorted_words:
                 row = [by_class_chi2[c].get(w, 0.0) for c in class_ids]
                 writer.writerow([w] + row)
                 
        # 2. Run CA Analysis (Coordinates)
        row_coords_name = "chd_profiles_afc_row_coords.csv"
        col_coords_name = "chd_profiles_afc_col_coords.csv"
        inertia_name = "chd_profiles_afc_inertia.csv"
        
        # Script to run CA and save coords/inertia
        analysis_script = f"""
suppressPackageStartupMessages(library(ca))
matrix_file <- '{matrix_path.name}'
if (file.exists(matrix_file)) {{
    tab <- read.csv(matrix_file, sep=';', header=TRUE, row.names=1, check.names=FALSE)
    # Clean data similar to IRaMuTeQ
    tab[is.na(tab)] <- 0
    tab <- tab[rowSums(tab) > 0, , drop=FALSE]
    tab <- tab[, colSums(tab) > 0, drop=FALSE]
    
    if (nrow(tab) > 2 && ncol(tab) > 1) {{
        res <- ca(as.matrix(tab))
        rcoord <- res$rowcoord
        ccoord <- res$colcoord
        # Pad to 2D when only 1 AFC dimension (e.g., 2-class CHD gives nd=1)
        if (ncol(rcoord) < 2) {{
            x_span <- diff(range(rcoord[, 1], na.rm = TRUE))
            if (!is.finite(x_span) || x_span == 0) x_span <- 1.0
            y_half <- x_span * 0.4
            set.seed(42)
            nr <- nrow(rcoord)
            nc_c <- nrow(ccoord)
            rcoord <- cbind(rcoord, runif(nr, -y_half, y_half))
            ccoord <- cbind(ccoord, runif(nc_c, -y_half, y_half))
        }}
        write.csv(rcoord, '{row_coords_name}')
        write.csv(ccoord, '{col_coords_name}')
        # Save eigenvalues (inertia)
        write.csv(res$sv^2 / sum(res$sv^2), '{inertia_name}')
    }} else {{
        cat("ERROR: Matrix dimensions too small for CA\n")
    }}
}} else {{
    cat("ERROR: Matrix file not found\n")
}}
"""
        analysis_script_path = self.output_dir / "chd_profiles_afc_script.R"
        analysis_script_path.write_text(analysis_script, encoding="utf-8")
        
        self.r_executor.execute(str(analysis_script_path), str(self.output_dir))
        
        # 3. Plot using RVisualizer (IRaMuTeQ Style with stopoverlap)
        row_coords_path = self.output_dir / row_coords_name
        col_coords_path = self.output_dir / col_coords_name
        inertia_path = self.output_dir / inertia_name
        
        if not row_coords_path.exists():
            self._logger.warning("AFC output coordinates not found")
            return None, None, None

        row_coords = self._read_afc_coords(row_coords_path)
        col_coords = self._read_afc_coords(col_coords_path)
        if row_coords is None or row_coords.ndim != 2 or row_coords.shape[1] < 2:
            self._logger.info(
                "Skipping CHD AFC plot generation: insufficient AFC dimensions (%s).",
                None if row_coords is None else row_coords.shape,
            )
            return None, row_coords, col_coords
            
        # Read inertia
        inertia = []
        if inertia_path.exists():
            try:
                with inertia_path.open("r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    next(reader, None) # skip header
                    for row in reader:
                        if len(row) >= 2:
                            try:
                                inertia.append(float(row[1]))
                            except (ValueError, TypeError):
                                pass
            except Exception as e:
                self._logger.warning(f"Failed to read inertia: {e}")
        # Pad inertia to at least 2 values for 2D axis labels (2-class AFC yields nd=1)
        while len(inertia) < 2:
            inertia.append(0.0)

        # Setup RVisualizer
        typegraph = str(params.get("typegraph", "png")).strip().lower()
        if typegraph == "svg": typegraph = "svg" 
        else: typegraph = "png"
            
        output_graph_name = f"chd_profiles_afc.{typegraph}"
        output_graph_path = self.output_dir / output_graph_name
        
        try:
            viz = RVisualizer()
            
            if viz.r_available:
                # Use bridge to execute afc_plot.R directly
                args = {
                    'coords_file': str(row_coords_path),
                    'chi2_file': str(chi2_path),
                    'col_coords_file': str(col_coords_path) if col_coords_path.exists() else None,
                    'output_file': str(output_graph_path),
                    'width': max(1400, int(params.get('width', 1600))),
                    'height': max(1200, int(params.get('height', 1400))),
                    'dpi': int(params.get('dpi', 180)),
                    'axes': [1, 2],
                    'max_words': int(params.get('max_words', self.DEFAULT_PARAMS.get('max_words', 600))),
                    'nbbycl': int(params.get('nb_per_class', self.DEFAULT_PARAMS.get('nb_per_class', 80))),
                    'inertia': inertia,
                    'what': str(params.get('what', 'coord')),
                    'col': bool(params.get('col', False)),
                    'debsup': params.get('debsup', None),
                    'gexf_output': params.get('gexf_output', None),
                    'PARCEX': float(params.get('PARCEX', 1.0)),
                    'adaptive_label_scaling': bool(params.get('adaptive_label_scaling', False)),
                    'min_visible_words': int(params.get('min_visible_words', self.DEFAULT_PARAMS.get('min_visible_words', 80))),
                }
                
                success, stdout, _ = viz.bridge.execute_script('afc_plot.R', args)
                if not success:
                    self._logger.warning(f"RVisualizer AFC plot failed: {stdout}")
                else:
                    self._logger.info(f"AFC plot generated successfully at {output_graph_path}")
            else:
                 self._logger.warning("RVisualizer not available (missing R or packages)")
                 
        except Exception as e:
            self._logger.error(f"Error calling RVisualizer: {e}")
        graph_ok = self._is_valid_graph_file(output_graph_path)
        if not graph_ok:
            fallback_path = self._render_post_chd_afc_python(
                row_coords_path=row_coords_path,
                col_coords_path=col_coords_path,
                chi2_path=chi2_path,
                output_path=output_graph_path,
                params=params,
                inertia=inertia,
            )
            graph_ok = self._is_valid_graph_file(fallback_path)
            if graph_ok:
                output_graph_path = fallback_path

        if not graph_ok:
            detail = (
                "AFC Perfis nao foi gerado (arquivo ausente, vazio ou formato invalido): "
                f"{output_graph_path}"
            )
            if bool(params.get("require_profile_afc_output", False)):
                raise CHDAnalysisError(
                    what="Falha na geracao do AFC Perfis.",
                    why=detail,
                    how="Confirme os pacotes R essenciais e tente novamente.",
                )
            self._logger.warning(detail)

        return ((output_graph_path if graph_ok else None),
                row_coords, col_coords)

    def _select_profiles_for_profile_afc(
        self,
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
        params: Dict[str, Any],
    ) -> Dict[int, List[Tuple[str, float, int, float, str]]]:
        """Filter and cap CHD profiles before profile AFC matrix export."""
        filtered = self._filter_profiles_for_visual_output(profiles)
        try:
            per_class_limit = int(params.get("nb_per_class", self.DEFAULT_PARAMS.get("nb_per_class", 80)))
        except Exception:
            per_class_limit = int(self.DEFAULT_PARAMS.get("nb_per_class", 80))
        try:
            max_words = int(params.get("max_words", self.DEFAULT_PARAMS.get("max_words", 600)))
        except Exception:
            max_words = int(self.DEFAULT_PARAMS.get("max_words", 600))
        per_class_limit = max(1, min(120, per_class_limit))
        max_words = max(10, min(400, max_words))

        scored: Dict[str, Tuple[float, int, Tuple[str, float, int, float, str]]] = {}
        result: Dict[int, List[Tuple[str, float, int, float, str]]] = {}
        for class_id, rows in filtered.items():
            ordered = sorted(
                rows,
                key=lambda item: (abs(float(item[1])), int(item[2]) if len(item) > 2 else 0),
                reverse=True,
            )
            result[int(class_id)] = ordered[:per_class_limit]
            for item in result[int(class_id)]:
                word = str(item[0] or "").strip()
                score = (abs(float(item[1])), int(item[2]) if len(item) > 2 else 0)
                if word not in scored or score > scored[word][:2]:
                    scored[word] = (score[0], score[1], item)

        if len(scored) <= max_words:
            return result

        allowed = {
            word
            for word, _score in sorted(
                scored.items(),
                key=lambda entry: (entry[1][0], entry[1][1], entry[0]),
                reverse=True,
            )[:max_words]
        }
        capped: Dict[int, List[Tuple[str, float, int, float, str]]] = {}
        for class_id, rows in result.items():
            capped[int(class_id)] = [
                item for item in rows
                if str(item[0] or "").strip() in allowed
            ]
        return capped

    def _render_post_chd_afc_python(
        self,
        *,
        row_coords_path: Path,
        col_coords_path: Path,
        chi2_path: Path,
        output_path: Path,
        params: Dict[str, Any],
        inertia: List[float],
    ) -> Optional[Path]:
        """Render a readable Python fallback for CHD profile AFC coordinates."""
        rows = self._read_afc_coord_records(row_coords_path)
        if not rows:
            return None

        class_by_word, class_labels = self._read_profile_afc_class_map(chi2_path)
        cols = self._read_afc_coord_records(col_coords_path)
        class_ids = sorted({cid for cid, _score in class_by_word.values()}) or [1]
        palette = PUBLICATION_PALETTE
        try:
            from ..core.chart_theme import apply_theme, ggplot_hue

            apply_theme()
            palette = ggplot_hue(max(1, len(class_ids))) or PUBLICATION_PALETTE
        except Exception:
            pass

        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.patheffects as path_effects
        except Exception as exc:
            self._logger.warning("Matplotlib indisponivel para AFC Perfis fallback: %s", exc)
            return None

        width_px = max(1000, int(params.get("width", self.DEFAULT_PARAMS.get("width", 1400))))
        height_px = max(760, int(params.get("height", self.DEFAULT_PARAMS.get("height", 1000))))
        dpi = int(params.get("dpi", 160) or 160)
        fig, ax = plt.subplots(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)

        class_color = {
            cid: palette[idx % len(palette)]
            for idx, cid in enumerate(class_ids)
        }
        max_score = max((score for _cid, score in class_by_word.values()), default=1.0) or 1.0

        xs = [x for _label, x, _y in rows]
        ys = [y for _label, _x, y in rows]
        if xs and ys:
            x_pad = max(0.15, (max(xs) - min(xs)) * 0.15)
            y_pad = max(0.15, (max(ys) - min(ys)) * 0.15)
            ax.set_xlim(min(xs) - x_pad, max(xs) + x_pad)
            ax.set_ylim(min(ys) - y_pad, max(ys) + y_pad)

        ax.axhline(0, color="#BDBDBD", linewidth=0.8, linestyle="--", zorder=0)
        ax.axvline(0, color="#BDBDBD", linewidth=0.8, linestyle="--", zorder=0)

        try:
            max_total_labels = int(params.get("afc_label_limit", min(240, self.DEFAULT_PARAMS.get("max_words", 600))))
        except Exception:
            max_total_labels = 240
        try:
            max_labels_per_class = int(params.get("afc_labels_per_class", min(35, self.DEFAULT_PARAMS.get("nb_per_class", 80))))
        except Exception:
            max_labels_per_class = 35
        max_total_labels = max(80, min(360, max_total_labels))
        max_labels_per_class = max(10, min(90, max_labels_per_class))

        label_words: set[str] = set()
        per_class_labels: Dict[int, int] = {}
        ranked_rows = sorted(
            rows,
            key=lambda row: (
                class_by_word.get(row[0], (class_ids[0], 0.0))[1],
                row[0],
            ),
            reverse=True,
        )
        for label, _x, _y in ranked_rows:
            cid, _score = class_by_word.get(label, (class_ids[0], 0.0))
            if per_class_labels.get(cid, 0) >= max_labels_per_class:
                continue
            label_words.add(label)
            per_class_labels[cid] = per_class_labels.get(cid, 0) + 1
            if len(label_words) >= max_total_labels:
                break

        text_artists = []
        for label, x, y in rows:
            cid, score = class_by_word.get(label, (class_ids[0], 1.0))
            color = class_color.get(cid, "#2D2D2D")
            size = 34.0 + 86.0 * min(1.0, max(0.0, float(score) / max_score))
            if label not in label_words:
                continue
            text = ax.text(
                x,
                y,
                str(label),
                fontsize=6.8 if len(label_words) > 120 else 7.4,
                color=color,
                ha="center",
                va="center",
                zorder=3,
                path_effects=[path_effects.withStroke(linewidth=2.8, foreground="white")],
            )
            text_artists.append(text)

        # AFC Perfis is a dense word map. Class coordinates remain exported in
        # CSV sidecars, but the UI graph intentionally draws words only.

        try:
            from adjustText import adjust_text

            adjust_text(
                text_artists,
                ax=ax,
                expand_text=(1.1, 1.18),
                expand_points=(1.15, 1.2),
                force_text=(0.6, 0.7),
                force_points=(0.25, 0.35),
                arrowprops=dict(arrowstyle="-", color="#BDBDBD", lw=0.45, alpha=0.55),
            )
        except Exception:
            pass

        def _axis_label(axis_idx: int) -> str:
            if len(inertia) > axis_idx and np.isfinite(inertia[axis_idx]):
                return f"Eixo {axis_idx + 1} ({float(inertia[axis_idx]) * 100:.1f}%)"
            return f"Eixo {axis_idx + 1}"

        ax.set_title("AFC Perfis pós-CHD", pad=14)
        ax.set_xlabel(_axis_label(0))
        ax.set_ylabel(_axis_label(1))
        ax.grid(True, color="#E5E5E5", linewidth=0.6, alpha=0.75)

        fig.tight_layout()
        fmt = output_path.suffix.lower().lstrip(".") or "png"
        try:
            fig.savefig(output_path, format=fmt, dpi=dpi, facecolor="white", bbox_inches="tight")
        finally:
            plt.close(fig)

        if self._is_valid_graph_file(output_path):
            self._logger.info("AFC Perfis fallback Python gerado em %s", output_path)
            return output_path
        return None

    @staticmethod
    def _read_afc_coord_records(path: Path) -> List[Tuple[str, float, float]]:
        """Read AFC coordinate CSV preserving row labels."""
        if not path.exists():
            return []
        records: List[Tuple[str, float, float]] = []
        with path.open("r", encoding="utf-8", newline="") as file:
            sample = file.read(2048)
            file.seek(0)
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
            except csv.Error:
                delimiter = "," if "," in sample else ";"
            reader = csv.reader(file, delimiter=delimiter)
            next(reader, None)
            for row in reader:
                if len(row) < 3:
                    continue
                label = str(row[0] or "").strip().strip('"')
                try:
                    x = float(str(row[1] or "").strip().replace(",", "."))
                    y = float(str(row[2] or "").strip().replace(",", "."))
                except ValueError:
                    continue
                if label:
                    records.append((label, x, y))
        return records

    @staticmethod
    def _read_profile_afc_class_map(path: Path) -> Tuple[Dict[str, Tuple[int, float]], Dict[int, str]]:
        """Map each word to the class with highest chi-square score."""
        if not path.exists():
            return {}, {}
        result: Dict[str, Tuple[int, float]] = {}
        labels: Dict[int, str] = {}
        with path.open("r", encoding="utf-8", newline="") as file:
            sample = file.read(2048)
            file.seek(0)
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
            except csv.Error:
                delimiter = "," if "," in sample else ";"
            reader = csv.reader(file, delimiter=delimiter)
            header = next(reader, [])
            raw_classes = [str(item or "").strip().strip('"') for item in header[1:]]
            class_ids = [CHDAnalysis._parse_class_id(item) or (idx + 1) for idx, item in enumerate(raw_classes)]
            labels = {cid: f"classe {cid}" for cid in class_ids}
            for row in reader:
                if len(row) < 2:
                    continue
                label = str(row[0] or "").strip().strip('"')
                scores: List[Tuple[int, float]] = []
                for cid, value in zip(class_ids, row[1:]):
                    try:
                        scores.append((cid, float(str(value or "0").strip().replace(",", "."))))
                    except ValueError:
                        scores.append((cid, 0.0))
                if label and scores:
                    result[label] = max(scores, key=lambda item: item[1])
        return result, labels

    @staticmethod
    def _parse_class_id(label: Any) -> int:
        match = re.search(r"(\d+)", str(label or ""))
        return int(match.group(1)) if match else 0


    @staticmethod
    def _read_afc_coords(path: Path) -> Optional[np.ndarray]:
        """Le CSV de coordenadas AFC e converte para matriz numpy."""
        if not path.exists():
            return None

        rows: List[List[float]] = []
        with path.open("r", encoding="utf-8", newline="") as file:
            sample = file.read(2048)
            file.seek(0)
            delimiter = ";"
            try:
                delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
            except csv.Error:
                delimiter = "," if "," in sample else ";"

            reader = csv.reader(file, delimiter=delimiter)
            next(reader, None)  # header
            for row in reader:
                if len(row) <= 1:
                    continue
                numeric: List[float] = []
                for value in row[1:]:
                    try:
                        text = str(value or "").strip().strip('"').replace(",", ".")
                        if not text:
                            continue
                        numeric.append(float(text))
                    except ValueError:
                        numeric = []
                        break
                if numeric:
                    rows.append(numeric)

        if not rows:
            return None
        return np.array(rows, dtype=np.float64)

    def _expand_class_map_to_uces(self, classif_mode: int) -> Dict[int, List[int]]:
        """Expande mapa classe->documentos para classe->UCEs quando necessario."""
        if classif_mode != 2:
            return {
                int(class_id): [int(uce_id) for uce_id in uce_ids]
                for class_id, uce_ids in self._class_uce_map.items()
            }

        expanded: Dict[int, List[int]] = {}
        for class_id, uci_ids in self._class_uce_map.items():
            class_uces: List[int] = []
            for uci_id in uci_ids:
                uci = self.corpus.get_uci(int(uci_id))
                if uci is None:
                    continue
                class_uces.extend(int(uce.ident) for uce in uci.uces)
            expanded[int(class_id)] = class_uces
        return expanded

    @staticmethod
    def _compute_antiprofiles(
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
        top_n: int = 20,
    ) -> Dict[int, List[Tuple[str, float, int, float, str]]]:
        """Retorna antiperfis: palavras mais ausentes (chi2 negativo) por classe."""
        antiprofiles: Dict[int, List[Tuple[str, float, int, float, str]]] = {}
        for class_id, rows in profiles.items():
            negatives = [row for row in rows if float(row[1]) < 0]
            negatives.sort(key=lambda item: item[1])  # mais negativo primeiro
            antiprofiles[class_id] = negatives[:top_n]
        return antiprofiles

    def _compute_typical_segments(
        self,
        class_uce_map: Dict[int, List[int]],
        profiles: Dict[int, List[Tuple[str, float, int, float, str]]],
        top_n: int = 10,
    ) -> Dict[int, List[Tuple[str, float]]]:
        """Ranqueia segmentos tipicos por classe via soma de chi2 das palavras presentes."""
        typical: Dict[int, List[Tuple[str, float]]] = {}
        token_pattern = re.compile(r"\b[a-zA-ZÀ-ÿ]+\b")

        for class_id, uce_ids in class_uce_map.items():
            if not uce_ids:
                typical[class_id] = []
                continue

            weights = {
                str(word).lower(): float(chi2)
                for word, chi2, _freq, _pct, _sign in profiles.get(class_id, [])
                if float(chi2) > 0
            }
            if not weights:
                typical[class_id] = []
                continue

            scored_segments: List[Tuple[str, float]] = []
            for _uce_id, text in self.corpus.getconcorde(uce_ids):
                cleaned = str(text or "").strip()
                if not cleaned:
                    continue
                tokens = {
                    token
                    for token in token_pattern.findall(cleaned.lower())
                    if len(token) > 2
                }
                score = float(sum(weights.get(token, 0.0) for token in tokens))
                if score > 0:
                    scored_segments.append((cleaned, score))

            scored_segments.sort(key=lambda item: item[1], reverse=True)
            typical[class_id] = scored_segments[:top_n]
        return typical

    def _compute_repeated_segments(
        self,
        class_uce_map: Dict[int, List[int]],
        min_n: int = 2,
        max_n: int = 5,
        min_freq: int = 3,
        top_n: int = 20,
    ) -> Dict[int, List[Tuple[str, int, float]]]:
        """Extract repeated n-grams per class with specificity score."""
        token_pattern = re.compile(r"\b[a-zA-ZÀ-ÿ]{3,}\b")

        all_uce_ids: set[int] = set()
        for uce_ids in class_uce_map.values():
            all_uce_ids.update(int(uce_id) for uce_id in uce_ids)

        if not all_uce_ids:
            return {int(class_id): [] for class_id in class_uce_map.keys()}

        uce_texts: Dict[int, str] = {}
        for uce_id, text in self.corpus.getconcorde(sorted(all_uce_ids)):
            uce_texts[int(uce_id)] = str(text or "").strip()

        def extract_ngrams(text: str) -> List[str]:
            tokens = [token.lower() for token in token_pattern.findall(text)]
            ngrams: List[str] = []
            for n in range(min_n, max_n + 1):
                if len(tokens) < n:
                    continue
                for idx in range(len(tokens) - n + 1):
                    ngrams.append(" ".join(tokens[idx: idx + n]))
            return ngrams

        total_ngrams_global: Dict[str, int] = {}
        total_segments = 0
        for text in uce_texts.values():
            for ngram in extract_ngrams(text):
                total_ngrams_global[ngram] = total_ngrams_global.get(ngram, 0) + 1
                total_segments += 1

        result: Dict[int, List[Tuple[str, int, float]]] = {}
        for class_id, uce_ids in class_uce_map.items():
            class_ngrams: Dict[str, int] = {}
            class_total = 0

            for uce_id in uce_ids:
                text = uce_texts.get(int(uce_id), "")
                if not text:
                    continue
                for ngram in extract_ngrams(text):
                    class_ngrams[ngram] = class_ngrams.get(ngram, 0) + 1
                    class_total += 1

            scored: List[Tuple[str, int, float]] = []
            for ngram, freq_class in class_ngrams.items():
                if freq_class < min_freq:
                    continue
                freq_total = total_ngrams_global.get(ngram, freq_class)
                if total_segments > 0 and class_total > 0:
                    expected_class = freq_total * (class_total / total_segments)
                    chi2 = ((freq_class - expected_class) ** 2) / expected_class if expected_class > 0 else 0.0
                else:
                    chi2 = 0.0
                if chi2 > 0:
                    scored.append((ngram, int(freq_class), float(chi2)))

            scored.sort(key=lambda item: (item[2], item[1]), reverse=True)
            result[int(class_id)] = scored[:top_n]

        return result

    def _export_colored_corpus(self, class_uce_map: Dict[int, List[int]]) -> Optional[Path]:
        """Exporta corpus colorido por classe para HTML."""
        if not class_uce_map:
            return None
        output_path = self.output_dir / "colored_corpus.html"
        assignments: Dict[int, int] = {}
        for class_id, uce_ids in class_uce_map.items():
            for uce_id in uce_ids:
                assignments[int(uce_id)] = int(class_id)

        try:
            from .colored_corpus import ColoredCorpusExporter

            exporter = ColoredCorpusExporter()
            exporter.export_html(self.corpus, assignments, output_path)
        except Exception as exc:
            self._logger.warning("Falha ao exportar corpus colorido: %s", exc)
            return None

        return output_path if output_path.exists() else None

    def _compute_chi2_profiles(
        self,
        class_sizes: Dict[int, int],
    ) -> Dict[int, List[Tuple[str, float, int, float, str]]]:
        """Compute signed chi2 profiles lemma/form x class from DTM."""
        if self.processor.dtm is None or not self.processor.vocabulary:
            return {class_id: [] for class_id in class_sizes}

        n_docs, _ = self.processor.dtm.shape
        if n_docs == 0:
            return {class_id: [] for class_id in class_sizes}

        presence = (self.processor.dtm > 0).astype(np.int32).toarray()
        doc_to_idx = {doc_id: idx for idx, doc_id in enumerate(self.processor.doc_ids)}
        vocabulary = self.processor.vocabulary

        profiles: Dict[int, List[Tuple[str, float, int, float, str]]] = {}
        for class_id, class_doc_count in class_sizes.items():
            class_mask = np.zeros(n_docs, dtype=bool)
            for uce_id in self._class_uce_map.get(class_id, []):
                doc_idx = doc_to_idx.get(uce_id)
                if doc_idx is not None:
                    class_mask[doc_idx] = True

            class_size = int(class_mask.sum())
            outside_size = n_docs - class_size
            if class_size == 0 or outside_size <= 0:
                profiles[class_id] = []
                continue

            in_class = presence[class_mask, :]
            out_class = presence[~class_mask, :]

            obs1 = in_class.sum(axis=0).astype(np.float64)
            obs2 = out_class.sum(axis=0).astype(np.float64)
            obs3 = class_size - obs1
            obs4 = outside_size - obs2

            row_has_word = obs1 + obs2
            row_no_word = obs3 + obs4
            col_class = float(class_size)
            col_out = float(outside_size)
            total = float(n_docs)

            exp1 = (row_has_word * col_class) / total
            exp2 = (row_has_word * col_out) / total
            exp3 = (row_no_word * col_class) / total
            exp4 = (row_no_word * col_out) / total

            with np.errstate(divide="ignore", invalid="ignore"):
                chi = np.where(exp1 > 0, ((obs1 - exp1) ** 2) / exp1, 0.0)
                chi += np.where(exp2 > 0, ((obs2 - exp2) ** 2) / exp2, 0.0)
                chi += np.where(exp3 > 0, ((obs3 - exp3) ** 2) / exp3, 0.0)
                chi += np.where(exp4 > 0, ((obs4 - exp4) ** 2) / exp4, 0.0)

            sign = np.where(obs1 >= exp1, 1.0, -1.0)
            signed_chi = chi * sign
            pct = np.where(class_size > 0, (obs1 / class_size) * 100.0, 0.0)

            class_profile: List[Tuple[str, float, int, float, str]] = []
            for idx, word in enumerate(vocabulary):
                freq_in_class = int(obs1[idx])
                total_presence = int(row_has_word[idx])
                if total_presence <= 0:
                    continue
                value = float(signed_chi[idx])
                marker = "+" if value >= 0 else "-"
                class_profile.append(
                    (word, value, freq_in_class, float(pct[idx]), marker)
                )

            class_profile.sort(key=lambda item: abs(item[1]), reverse=True)
            profiles[class_id] = class_profile

        return profiles

    def get_class_profile(
        self,
        class_id: int,
        top_n: int = 20,
    ) -> List[Tuple[str, float, int, float, str]]:
        """Retorna perfil lexical de uma classe (palavras com chi2)."""
        if not self._last_result:
            return []
        profile = self._last_result.profiles.get(class_id, [])
        return profile[:top_n]

    def get_typical_segments(self, class_id: int, n: int = 10) -> List[Tuple[str, float]]:
        """Retorna segmentos tipicos de uma classe com score de representatividade."""
        if not self._last_result:
            return []
        segments = self._last_result.typical_segments.get(class_id, [])
        return segments[: max(0, int(n))]

    def get_antiprofiles(
        self,
        top_n: int = 20,
    ) -> Dict[int, List[Tuple[str, float, int, float, str]]]:
        """Retorna antiperfis (palavras com chi2 negativo) para todas as classes."""
        if not self._last_result:
            return {}
        result: Dict[int, List[Tuple[str, float, int, float, str]]] = {}
        for class_id, rows in self._last_result.antiprofiles.items():
            result[class_id] = rows[: max(0, int(top_n))]
        return result

    def get_representative_segments(self, class_id: int, n: int = 5) -> List[str]:
        """Compat: retorna apenas texto dos segmentos tipicos."""
        return [text for text, _score in self.get_typical_segments(class_id, n=n)]

    def export_class_texts(self, class_id: int, output_path: Path) -> Path:
        """Exporta todas as UCEs de uma classe para um arquivo TXT."""
        uce_ids = self._effective_class_uce_map.get(int(class_id), [])
        if not uce_ids:
            raise CHDAnalysisError(
                what=f"Classe {class_id} sem segmentos para exportacao.",
                why="Nao foram encontrados UCEs associados a esta classe.",
                how="Execute uma analise CHD valida e tente novamente.",
            )

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding="utf-8") as file:
            for idx, (_uce_id, text) in enumerate(self.corpus.getconcorde(uce_ids), start=1):
                cleaned = str(text or "").strip()
                if not cleaned:
                    continue
                file.write(f"[{idx}] {cleaned}\n")
        return output_file

    def export_all_class_texts(
        self,
        output_dir: Path,
        class_uce_map: Optional[Dict[int, List[int]]] = None,
    ) -> Dict[int, Path]:
        """Exporta todas as classes CHD em arquivos TXT separados."""
        target_map = class_uce_map if class_uce_map is not None else self._effective_class_uce_map
        exported: Dict[int, Path] = {}
        folder = Path(output_dir)
        folder.mkdir(parents=True, exist_ok=True)

        for class_id in sorted(target_map.keys()):
            uce_ids = target_map.get(class_id, [])
            if not uce_ids:
                continue
            class_path = folder / f"class_{class_id}.txt"
            with class_path.open("w", encoding="utf-8") as file:
                for idx, (_uce_id, text) in enumerate(self.corpus.getconcorde(uce_ids), start=1):
                    cleaned = str(text or "").strip()
                    if not cleaned:
                        continue
                    file.write(f"[{idx}] {cleaned}\n")
            exported[int(class_id)] = class_path
        return exported

    def run_similarity_from_class(self, class_id: int, params: Optional[Dict[str, Any]] = None):
        """Executa análise de similitude apenas com os segmentos de uma classe CHD."""
        from ..core.corpus import Corpus
        from .similarity import SimilarityAnalysis

        uce_ids = self._effective_class_uce_map.get(int(class_id), [])
        if not uce_ids:
            raise CHDAnalysisError(
                what=f"Nao foi possivel executar similitude da classe {class_id}.",
                why="A classe selecionada nao possui UCEs disponiveis.",
                how="Escolha outra classe ou rode CHD novamente.",
            )

        subset_dir = self.output_dir / f"class_{class_id}_similarity"
        subset_dir.mkdir(parents=True, exist_ok=True)
        subset_db = subset_dir / "subset_corpus.db"
        if subset_db.exists():
            subset_db.unlink()

        subset = Corpus(
            parametres=dict(self.corpus.parametres or {}),
            lexicon=self.corpus.lexicon,
        )
        subset.connect(subset_db)

        token_pattern = re.compile(r"\b[a-zA-ZÀ-ÿ]+\b")
        source_uce_map = dict(self.corpus.getconcorde(uce_ids))
        subset_uci = subset.add_uci(f"**** *class_{class_id}")
        para_counter = 0

        for uce_id in uce_ids:
            text = source_uce_map.get(uce_id, "")
            cleaned = str(text or "").strip()
            if not cleaned:
                continue
            uce = subset.add_uce(subset_uci.ident, para_counter, cleaned)
            para_counter += 1
            for token in token_pattern.findall(cleaned.lower()):
                if len(token) > 2:
                    subset.add_word(token, uce_id=uce.ident)

        if subset.getucenb() < 2:
            subset.close()
            raise CHDAnalysisError(
                what=f"Nao foi possivel executar similitude da classe {class_id}.",
                why="A classe possui menos de 2 segmentos validos para o grafo.",
                how="Escolha uma classe com mais segmentos ou ajuste filtros.",
            )

        try:
            analysis = SimilarityAnalysis(subset, subset_dir, r_executor=self.r_executor)
            return analysis.run(params or {})
        finally:
            subset.close()
