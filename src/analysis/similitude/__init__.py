"""
Similitude Analysis Module.

Reconstructed from scratch with:
  - UCE-based co-presence (not sliding window)
  - Full contingency table (a, b, c, d)
  - 25+ association indices computed in Python
  - NetworkX graph construction with MST
  - IRaMuTeQ-style visualization
  - Full traceability: corpus -> matrix -> graph -> image

Compatible with the existing SimilarityAnalysis interface.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ...core.corpus import Corpus
from .models import SimilitudeConfig, SimilitudeResult
from .matrix import build_similitude_matrix
from .graph import build_graph
from .visualization import render_similitude
from .validation import (
    validate_binary_matrix,
    validate_contingency,
    validate_association_matrix,
)

import logging

log = logging.getLogger(__name__)

_STRICT_VERIFIED_RENDER_ARTIFACTS = (
    "render_stdout",
    "render_stderr",
    "similitude_env",
    "community_sensitivity",
    "raw_graph",
    "layout_raw",
)


class SimilitudeAnalysis:
    """
    Similitude analysis engine.

    Three-layer pipeline:
      1. Matrix: binary UCE×term -> contingency -> association
      2. Graph: association matrix -> NetworkX graph -> MST -> communities
      3. Visualization: graph -> IRaMuTeQ-style PNG/SVG

    Usage:
        analysis = SimilitudeAnalysis(corpus, output_dir)
        result = analysis.run(params)
    """

    # Default params matching the existing SimilarityAnalysis interface
    DEFAULT_PARAMS = {
        "coefficient": "cooccurrence",
        "layout": "frutch",
        "min_freq": 3,
        "use_lemmas": True,
        "active_only": True,
        "min_edge": 0,
        "arbremax": True,
        "detect_communities": True,
        "community_method": "edge_betweenness",
        "show_halo": True,
        "show_edge_labels": False,
        "vertex_scaling": "frequency",
        "grayscale": False,
        "typegraph": "png",
        "width": 1000,
        "height": 1000,
        "renderer_backend": "iramuteq_r",
        "stopword_policy": "aggressive_pt",
        "font_family": "sans-serif",
        "strict_iramuteq_style": True,
        "keep_punctuation": False,
        "graph_word": "",
    }

    def __init__(
        self,
        corpus: Corpus,
        output_dir: Path,
    ):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, params: Optional[Dict[str, Any]] = None) -> SimilitudeResult:
        """
        Execute the full similitude analysis pipeline.

        Args:
            params: Analysis parameters (merged with defaults).

        Returns:
            SimilitudeResult with graph image path and all artifacts.
        """
        config = self._build_config(params)

        log.info(
            f"Starting similitude analysis: coefficient={config.coefficient}, "
            f"min_freq={config.min_freq}, arbremax={config.arbremax}"
        )

        # ===== Layer 1: Matrix =====
        log.info("Layer 1: Building association matrix...")
        matrix = build_similitude_matrix(
            corpus=self.corpus,
            min_freq=config.min_freq,
            active_only=config.active_only,
            use_lemmas=config.use_lemmas,
            coefficient=config.coefficient,
            stopword_policy=config.stopword_policy,
            selected_words=config.selected_words,
            max_terms=config.max_terms,
        )

        # Validate
        v1 = validate_binary_matrix(matrix.binary_matrix, matrix.n_terms)
        v2 = validate_contingency(
            matrix.contingency.a, matrix.contingency.b,
            matrix.contingency.c, matrix.contingency.d,
            matrix.n_uces,
        )
        v3 = validate_association_matrix(matrix.association)

        for v in [v1, v2, v3]:
            if not v.is_valid:
                for err in v.errors:
                    log.error(f"Validation error: {err}")
                raise ValueError(
                    f"Matrix validation failed: {'; '.join(v.errors)}"
                )
            for w in v.warnings:
                log.warning(f"Validation warning: {w}")

        log.info(
            f"Matrix built: {matrix.n_uces} UCEs x {matrix.n_terms} terms, "
            f"coefficient={matrix.coefficient_name}"
        )

        # ===== Layer 2: Graph =====
        log.info("Layer 2: Building graph...")
        graph = build_graph(matrix, config)
        log.info(
            f"Graph built: {graph.graph.number_of_nodes()} nodes, "
            f"{graph.n_edges} edges, "
            f"{len(set(graph.communities.values()))} communities"
        )

        # ===== Layer 3: Visualization =====
        log.info("Layer 3: Rendering visualization...")
        graph_filename = f"similitude.{config.typegraph}"
        graph_path = self.output_dir / graph_filename
        graph_path = render_similitude(graph, graph_path, config, matrix=matrix)

        # ===== Export artifacts =====
        artifacts = self._export_artifacts(matrix, graph)
        artifacts.update(self._collect_render_sidecars(graph_path))
        community_sensitivity_report = self._load_json_artifact(
            artifacts.get("community_sensitivity")
        )
        display_communities = self._extract_display_partition(
            community_sensitivity_report
        )
        if display_communities:
            graph.communities = display_communities
            self._rewrite_communities_csv(artifacts.get("communities"), display_communities)

        warnings: List[str] = []
        if graph.graph.number_of_nodes() > config.readability_warning_threshold:
            warnings.append(
                "Graph exceeds the recommended readability threshold; "
                "use selected_words, graph_word, min_freq, min_edge, or corpus subsetting."
            )

        backend_used = self._resolve_backend_used(config, artifacts)
        verified_output = self._is_verified_output(config, backend_used, artifacts)
        render_metrics = self._build_render_metrics(artifacts)
        manifest_path = self._write_manifest(
            graph_path=graph_path,
            artifacts=artifacts,
            backend_used=backend_used,
            strict_mode_used=bool(config.strict_iramuteq_style),
            verified_output=verified_output,
            render_metrics=render_metrics,
            warnings=warnings,
        )
        artifacts["manifest"] = manifest_path

        # ===== Build result =====
        centrality = {
            term: metrics.get("weighted_degree", 0.0)
            for term, metrics in graph.metrics.items()
        }

        result = SimilitudeResult(
            graph_path=graph_path,
            adjacency_matrix=artifacts.get("association_matrix"),
            communities=display_communities or graph.communities,
            centrality=centrality,
            association_matrix_path=artifacts.get("association_matrix"),
            vocabulary_path=artifacts.get("vocabulary"),
            communities_path=artifacts.get("communities"),
            centrality_path=artifacts.get("centrality"),
            graph_data=graph,
            matrix_data=matrix,
            config=config,
            artifacts=artifacts,
            backend_used=backend_used,
            strict_mode_used=bool(config.strict_iramuteq_style),
            fallback_used=False,
            dropped_token_count=len(matrix.dropped_tokens),
            r_session_info=self._load_json_artifact(artifacts.get("similitude_env")),
            community_sensitivity_report=community_sensitivity_report,
            raw_graph_path=artifacts.get("raw_graph"),
            verified_output=verified_output,
            render_metrics=render_metrics,
            manifest_path=manifest_path,
            warnings=warnings,
        )

        log.info(f"Similitude analysis complete: {graph_path}")
        return result

    def _build_config(self, params: Optional[Dict[str, Any]] = None) -> SimilitudeConfig:
        """Merge user params with defaults and build config."""
        merged = {**self.DEFAULT_PARAMS, **(params or {})}

        # Handle legacy param names
        if "halo" in merged and "show_halo" not in (params or {}):
            merged["show_halo"] = merged["halo"]
        if "label_e" in merged and "show_edge_labels" not in (params or {}):
            merged["show_edge_labels"] = merged["label_e"]
        if "com" in merged and "detect_communities" not in (params or {}):
            merged["detect_communities"] = merged["com"]

        # Coerce types
        selected_words = merged.get("selected_words")
        if isinstance(selected_words, (list, tuple, set)):
            selected_words = [str(w).strip() for w in selected_words if str(w).strip()]
        else:
            selected_words = None

        config = SimilitudeConfig(
            min_freq=max(1, int(merged.get("min_freq", 3))),
            active_only=bool(merged.get("active_only", True)),
            use_lemmas=bool(merged.get("use_lemmas", True)),
            stopword_policy=str(merged.get("stopword_policy", "aggressive_pt")),
            coefficient=str(merged.get("coefficient", "cooccurrence")),
            arbremax=bool(merged.get("arbremax", True)),
            min_edge=max(0.0, float(merged.get("min_edge", 0))),
            max_terms=max(0, int(merged.get("max_terms", 0))),
            selected_words=selected_words or None,
            graph_word=str(merged.get("graph_word", "") or "").strip(),
            keep_punctuation=bool(merged.get("keep_punctuation", False)),
            strict_iramuteq_style=bool(merged.get("strict_iramuteq_style", True)),
            readability_warning_threshold=max(
                10,
                int(merged.get("readability_warning_threshold", 200)),
            ),
            detect_communities=bool(merged.get("detect_communities", True)),
            community_method=str(merged.get("community_method", "edge_betweenness")),
            show_halo=bool(merged.get("show_halo", True)),
            layout=str(merged.get("layout", "frutch")),
            width=max(300, int(merged.get("width", 1200))),
            height=max(300, int(merged.get("height", 1000))),
            typegraph=str(merged.get("typegraph", "png")),
            show_edge_labels=bool(merged.get("show_edge_labels", False)),
            vertex_scaling=str(merged.get("vertex_scaling", "frequency")),
            grayscale=bool(merged.get("grayscale", False)),
            font_family=str(merged.get("font_family", "sans-serif")),
            edge_curved=bool(merged.get("edge_curved", True)),
            renderer_backend=str(merged.get("renderer_backend", "iramuteq_r")),
        )

        if config.strict_iramuteq_style:
            config.layout = "frutch"
            config.arbremax = True
            config.community_method = "edge_betweenness"
            config.show_edge_labels = False
            config.vertex_scaling = "frequency"
            config.renderer_backend = "iramuteq_r"
            config.keep_punctuation = False
            # LabiiaLex keeps the IRaMuTeQ-style renderer/graph profile here,
            # but still honors the cleaned corpus policy and manual word list.
            # Otherwise normalized corpora leak stopwords back into similitude.
            if config.stopword_policy not in {"legacy", "aggressive_pt"}:
                config.stopword_policy = "aggressive_pt"
            config.max_terms = 200
            config.grayscale = True

        return config

    def _export_artifacts(
        self,
        matrix,
        graph,
    ) -> Dict[str, Path]:
        """Export analysis artifacts as CSV files."""
        artifacts: Dict[str, Path] = {}

        # Association matrix
        assoc_path = self.output_dir / "similitude_association.csv"
        self._write_square_matrix_csv(
            assoc_path, matrix.association, matrix.vocabulary,
        )
        artifacts["association_matrix"] = assoc_path

        # Vocabulary with frequencies
        vocab_path = self.output_dir / "similitude_vocabulary.csv"
        with open(vocab_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["term", "frequency"])
            for i, term in enumerate(matrix.vocabulary):
                writer.writerow([term, int(matrix.term_frequencies[i])])
        artifacts["vocabulary"] = vocab_path

        # Communities
        comm_path = self.output_dir / "similitude_communities.csv"
        with open(comm_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["node", "community"])
            for term, cid in sorted(graph.communities.items()):
                writer.writerow([term, cid])
        artifacts["communities"] = comm_path

        # Centrality/metrics
        cent_path = self.output_dir / "similitude_centrality.csv"
        with open(cent_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["node", "degree", "weighted_degree", "betweenness", "closeness"])
            for term, m in sorted(graph.metrics.items()):
                writer.writerow([
                    term,
                    int(m.get("degree", 0)),
                    f"{m.get('weighted_degree', 0.0):.4f}",
                    f"{m.get('betweenness', 0.0):.6f}",
                    f"{m.get('closeness', 0.0):.6f}",
                ])
        artifacts["centrality"] = cent_path

        dropped_path = self.output_dir / "dropped_tokens.csv"
        with open(dropped_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["term", "reason", "frequency"])
            for item in matrix.dropped_tokens:
                writer.writerow([
                    str(item.get("term", "")),
                    str(item.get("reason", "")),
                    int(item.get("frequency", 0) or 0),
                ])
        artifacts["dropped_tokens"] = dropped_path

        log.info(f"Exported {len(artifacts)} artifacts to {self.output_dir}")
        return artifacts

    @staticmethod
    def _load_json_artifact(path: Optional[Path]) -> Optional[Dict[str, Any]]:
        """Load a JSON artifact if present and valid."""
        if path is None or not Path(path).exists():
            return None
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return None

    @staticmethod
    def _collect_render_sidecars(graph_path: Path) -> Dict[str, Path]:
        """Collect known renderer sidecar files next to the graph output."""
        parent = Path(graph_path).parent
        candidates = {
            "render_stdout": parent / "render_stdout.log",
            "render_stderr": parent / "render_stderr.log",
            "similitude_env": parent / "similitude_env.json",
            "community_sensitivity": parent / "community_sensitivity.json",
            "raw_graph": parent / "similitude_raw_iramuteq.png",
            "layout_raw": parent / "layout_raw.json",
            "label_adjustments": parent / "label_adjustments.json",
        }
        return {
            key: path for key, path in candidates.items()
            if path.exists()
        }

    @staticmethod
    def _resolve_backend_used(
        config: SimilitudeConfig,
        artifacts: Dict[str, Path],
    ) -> str:
        """Resolve the backend actually used for the final output."""
        if artifacts.get("raw_graph") and artifacts.get("layout_raw"):
            return "iramuteq_r"
        return str(config.renderer_backend)

    @staticmethod
    def _is_verified_output(
        config: SimilitudeConfig,
        backend_used: str,
        artifacts: Dict[str, Path],
    ) -> bool:
        """A strict run is verifiable only when all required render artifacts exist."""
        if not config.strict_iramuteq_style:
            return False
        if backend_used != "iramuteq_r":
            return False
        return all(artifacts.get(name) and Path(artifacts[name]).exists() for name in _STRICT_VERIFIED_RENDER_ARTIFACTS)

    @staticmethod
    def _build_render_metrics(artifacts: Dict[str, Path]) -> Dict[str, Any]:
        """Build render metrics from layout and label adjustment sidecars."""
        layout_data = SimilitudeAnalysis._load_json_artifact(artifacts.get("layout_raw")) or {}
        adjustments = SimilitudeAnalysis._load_json_artifact(artifacts.get("label_adjustments")) or {}
        nodes = layout_data.get("nodes") if isinstance(layout_data, dict) else None
        device = layout_data.get("device") if isinstance(layout_data, dict) else None
        if not isinstance(nodes, list):
            nodes = []
        if not isinstance(device, dict):
            device = {}
        if isinstance(adjustments, dict) and isinstance(adjustments.get("__metrics__"), dict):
            metrics = dict(adjustments["__metrics__"])
            metrics["label_count"] = int(metrics.get("label_count", len(nodes)) or len(nodes))
            metrics["device"] = device
            return metrics

        dpi = float(device.get("dpi", 96) or 96)
        pointsize = float(device.get("pointsize", 8) or 8)
        px_per_pt = dpi / 72.0

        label_heights: List[float] = []
        central_area = 0.0
        total_area = 0.0
        width = float(device.get("width", 0) or 0)
        height = float(device.get("height", 0) or 0)
        center_x0 = width * 0.35
        center_x1 = width * 0.65
        center_y0 = height * 0.35
        center_y1 = height * 0.65

        for node in nodes:
            if not isinstance(node, dict):
                continue
            cex = float(node.get("label_cex", 1.0) or 1.0)
            label = str(node.get("term", ""))
            label_height = pointsize * cex * px_per_pt
            label_width = max(label_height * 0.6 * max(len(label), 1), label_height)
            label_heights.append(label_height)
            total_area += label_width * label_height

            adj = adjustments.get(label, {}) if isinstance(adjustments, dict) else {}
            x = float(node.get("x_px", node.get("x", 0.0)) or 0.0) + float(adj.get("dx", 0.0) or 0.0)
            y = float(node.get("y_px", node.get("y", 0.0)) or 0.0) + float(adj.get("dy", 0.0) or 0.0)
            box_x0 = x - (label_width / 2.0)
            box_x1 = x + (label_width / 2.0)
            box_y0 = y - (label_height / 2.0)
            box_y1 = y + (label_height / 2.0)
            overlap_w = max(0.0, min(box_x1, center_x1) - max(box_x0, center_x0))
            overlap_h = max(0.0, min(box_y1, center_y1) - max(box_y0, center_y0))
            central_area += overlap_w * overlap_h

        metrics: Dict[str, Any] = {
            "label_count": len(nodes),
            "device": device,
        }
        if label_heights:
            arr = np.asarray(label_heights, dtype=float)
            metrics["max_label_height_px"] = float(np.max(arr))
            metrics["label_height_ratio_p95_p50"] = float(np.percentile(arr, 95) / max(np.percentile(arr, 50), 1e-6))
        else:
            metrics["max_label_height_px"] = 0.0
            metrics["label_height_ratio_p95_p50"] = 0.0
        metrics["central_label_area_share"] = float(central_area / total_area) if total_area > 0 else 0.0
        metrics["overlap_area_ratio"] = None
        return metrics

    def _write_manifest(
        self,
        graph_path: Path,
        artifacts: Dict[str, Path],
        backend_used: str,
        strict_mode_used: bool,
        verified_output: bool,
        render_metrics: Dict[str, Any],
        warnings: List[str],
    ) -> Path:
        """Write the canonical similitude manifest for the run."""
        manifest_path = self.output_dir / "similitude_manifest.json"
        payload = {
            "graph_path": str(graph_path),
            "backend_used": backend_used,
            "strict_mode_used": strict_mode_used,
            "verified_output": verified_output,
            "render_metrics": render_metrics,
            "warnings": list(warnings),
            "artifacts": {
                key: str(path) for key, path in sorted(artifacts.items())
            },
        }
        manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    @staticmethod
    def _extract_display_partition(
        report: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, int]]:
        """Extract the renderer display partition as term -> community_id."""
        if not isinstance(report, dict):
            return None
        partition = report.get("display_partition")
        if not isinstance(partition, dict):
            return None

        normalized: Dict[str, int] = {}
        for node, value in partition.items():
            try:
                normalized[str(node)] = int(value)
            except (TypeError, ValueError):
                continue
        return normalized or None

    @staticmethod
    def _rewrite_communities_csv(
        path: Optional[Path],
        communities: Dict[str, int],
    ) -> None:
        """Rewrite the exported communities CSV when the R renderer provides the display partition."""
        if path is None:
            return
        with Path(path).open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["node", "community"])
            for term, cid in sorted(communities.items()):
                writer.writerow([term, cid])

    @staticmethod
    def _write_square_matrix_csv(
        path: Path,
        matrix: np.ndarray,
        labels: List[str],
    ) -> None:
        """Write a square matrix as CSV with row/column headers."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow([""] + labels)
            for i, label in enumerate(labels):
                row = [label] + [f"{matrix[i, j]:.6f}" for j in range(matrix.shape[1])]
                writer.writerow(row)
