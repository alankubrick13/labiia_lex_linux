"""Voyant-inspired lexical suite (TermsBerry, Trends, Document Terms, Contexts, Bubblelines, Co-occurrences)."""

from __future__ import annotations

import csv
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from ..core.corpus import Corpus
from ..core.lexicon import build_portuguese_stopwords_from_lexicon
from ..utils.logger import get_logger
from ._extras_common import UciRecord, build_uci_records, tokenize_text


QUERY_TOKEN_PATTERN = re.compile(r"\b[a-zA-ZÀ-ÿ]{3,}\b")
DEFAULT_COLORS = [
    "#1F77B4",
    "#E377C2",
    "#2CA02C",
    "#FF7F0E",
    "#6F42C1",
    "#17BECF",
    "#D62728",
    "#8C564B",
]
ENGLISH_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was", "were",
    "have", "has", "had", "into", "onto", "than", "then", "their", "there",
    "them", "your", "yours", "you", "will", "would", "shall", "should", "can",
    "could", "what", "when", "where", "which", "who", "whom", "why", "how",
}

VOYANT_PANEL_ORDER: List[str] = [
    "termsberry",
    "trends",
    "document_terms",
    "bubblelines",
    "cooccurrences",
]
VOYANT_PANEL_TITLES_PT: Dict[str, str] = {
    "termsberry": "TermsBerry",
    "trends": "Tendências",
    "document_terms": "Termos do documento",
    "bubblelines": "Gráfico de bolhas",
    "cooccurrences": "Co-ocorrências",
}
VOYANT_GRAPH_LABEL_BY_PANEL: Dict[str, str] = {
    "termsberry": "TermsBerry",
    "trends": "Tendências",
    "document_terms": "Termos do documento",
    "bubblelines": "Gráfico de bolhas",
    "cooccurrences": "Co-ocorrências",
}
VOYANT_TABLE_LABEL_BY_PANEL: Dict[str, str] = {
    "termsberry": "TermsBerry (Nós)",
    "trends": "Tendências",
    "document_terms": "Termos do documento",
    "bubblelines": "Gráfico de bolhas (Pontos)",
    "cooccurrences": "Co-ocorrências",
}


@dataclass
class VoyantSuiteResult:
    """Result payload for the Voyant-inspired suite."""

    graph_path: Optional[Path] = None
    table_path: Optional[Path] = None

    termsberry_graph_path: Optional[Path] = None
    trends_graph_path: Optional[Path] = None
    document_terms_chart_path: Optional[Path] = None
    bubblelines_graph_path: Optional[Path] = None
    cooccurrences_graph_path: Optional[Path] = None

    termsberry_nodes_csv_path: Optional[Path] = None
    termsberry_edges_csv_path: Optional[Path] = None
    trends_csv_path: Optional[Path] = None
    document_terms_csv_path: Optional[Path] = None
    contexts_csv_path: Optional[Path] = None
    bubblelines_points_csv_path: Optional[Path] = None
    cooccurrences_csv_path: Optional[Path] = None
    summary_json_path: Optional[Path] = None

    graph_gallery: Dict[str, Path] = field(default_factory=dict)
    table_gallery: Dict[str, Path] = field(default_factory=dict)
    voyant_suite_payload_v1: Dict[str, Any] = field(default_factory=dict)
    selected_terms: List[str] = field(default_factory=list)
    query_terms: List[str] = field(default_factory=list)

    n_documents: int = 0
    n_segments: int = 0
    n_contexts: int = 0


class VoyantSuiteAnalysisError(Exception):
    """Friendly error for Voyant suite analysis."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class VoyantSuiteAnalysis:
    """Generate Voyant-like outputs from a loaded corpus."""

    DEFAULT_PARAMS = {
        "query": "",
        "num_initial_terms": 20,
        "context": 5,
        "bins": 10,
        "max_docs": 50,
        "min_freq": 2,
        "use_lemmas": True,
        "active_only": True,
        "remove_stopwords": True,
        "max_context_rows": 800,
        "width": 1400,
        "height": 900,
        "mode": "top",  # top | mixed | query
        "termsberry_per_term_limit": 8,
        "termsberry_max_nodes": 120,
    }

    def __init__(self, corpus: Corpus, output_dir: Path):
        self.corpus = corpus
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._logger = get_logger(__name__)
        self._fallback_stopwords = {
            str(token).strip().lower()
            for token in build_portuguese_stopwords_from_lexicon()
        }
        self._fallback_stopwords.update(ENGLISH_STOPWORDS)

    def run(self, params: Optional[Dict[str, Any]] = None) -> VoyantSuiteResult:
        """Execute Voyant-inspired suite and export charts/tables."""
        config = self._sanitize_params(params)
        query_terms = self._parse_query_terms(config.get("query"))

        uci_records = build_uci_records(self.corpus)
        if not uci_records:
            raise VoyantSuiteAnalysisError(
                what="Nao foi possivel executar o pacote Voyant.",
                why="O corpus nao possui documentos (UCIs) carregados.",
                how="Importe um corpus e execute novamente.",
            )

        doc_streams = self._build_document_streams(
            records=uci_records,
            use_lemmas=bool(config["use_lemmas"]),
            active_only=bool(config["active_only"]),
            remove_stopwords=bool(config["remove_stopwords"]),
        )
        if not doc_streams:
            raise VoyantSuiteAnalysisError(
                what="Nao foi possivel executar o pacote Voyant.",
                why="Os documentos ficaram sem tokens apos filtros lexicais.",
                how="Reduza filtros (stopwords/ativos) ou use outro corpus.",
            )

        uce_streams = self._build_uce_streams(
            doc_streams=doc_streams,
            use_lemmas=bool(config["use_lemmas"]),
            active_only=bool(config["active_only"]),
            remove_stopwords=bool(config["remove_stopwords"]),
        )
        if not uce_streams:
            raise VoyantSuiteAnalysisError(
                what="Nao foi possivel gerar segmentacao para tendencias.",
                why="Nao ha UCEs com tokens validos para construir segmentos.",
                how="Importe um corpus com mais texto ou reduza filtros lexicais.",
            )

        global_counter: Counter[str] = Counter()
        for item in doc_streams:
            global_counter.update(item["tokens"])

        min_freq = int(config["min_freq"])
        selected_terms = self._select_terms(
            global_counter=global_counter,
            query_terms=query_terms,
            num_initial_terms=int(config["num_initial_terms"]),
            min_freq=min_freq,
            mode=str(config["mode"]),
        )
        if not selected_terms:
            raise VoyantSuiteAnalysisError(
                what="Nao ha termos suficientes para a suite Voyant.",
                why="Nenhum termo atingiu a frequencia minima apos filtros.",
                how="Diminua a frequencia minima e execute novamente.",
            )

        context_window = int(config["context"])
        bins = int(config["bins"])
        max_docs = int(config["max_docs"])
        max_context_rows = int(config["max_context_rows"])

        trends_terms = selected_terms[: min(8, len(selected_terms))]
        bubble_terms = selected_terms[: min(6, len(selected_terms))]
        context_terms = selected_terms[: min(8, len(selected_terms))]

        trends_rows, trends_series, n_segments = self._build_trends_data(
            uce_streams=uce_streams,
            terms=trends_terms,
            bins=bins,
        )
        trends_csv_path = self.output_dir / "voyant_trends.csv"
        self._write_csv(
            trends_csv_path,
            ["segment", "term", "count", "relative"],
            trends_rows,
        )
        trends_graph_path = self.output_dir / "voyant_trends.png"
        self._plot_trends(
            path=trends_graph_path,
            series=trends_series,
            bins=n_segments,
            width=int(config["width"]),
            height=int(config["height"]),
        )

        primary_doc = self._pick_primary_document(doc_streams)
        document_terms_rows, document_terms_series = self._build_document_terms_data(
            doc_tokens=primary_doc["tokens"],
            terms=selected_terms,
            bins=bins,
            min_freq=min_freq,
        )
        document_terms_csv_path = self.output_dir / "voyant_document_terms.csv"
        self._write_csv(
            document_terms_csv_path,
            ["rank", "term", "count", "relative_percent", "trend"],
            document_terms_rows,
        )
        document_terms_chart_path = self.output_dir / "voyant_document_terms.png"
        self._plot_document_terms(
            path=document_terms_chart_path,
            rows=document_terms_rows,
            series=document_terms_series,
            bins=bins,
            width=int(config["width"]),
            height=int(config["height"]),
            title=f"Termos do documento ({primary_doc['title']})",
        )

        contexts_rows = self._build_contexts_data(
            uce_streams=uce_streams,
            terms=context_terms,
            context_window=context_window,
            row_limit=max_context_rows,
        )
        contexts_csv_path = self.output_dir / "voyant_contexts.csv"
        self._write_csv(
            contexts_csv_path,
            ["document", "left", "term", "right", "uce_id", "uci_id"],
            contexts_rows,
        )

        termsberry_nodes, termsberry_edges = self._build_termsberry_data(
            uce_streams=uce_streams,
            selected_terms=selected_terms,
            global_counter=global_counter,
            context_window=context_window,
            per_term_limit=int(config["termsberry_per_term_limit"]),
            max_nodes=int(config["termsberry_max_nodes"]),
        )
        termsberry_nodes_csv_path = self.output_dir / "voyant_termsberry_nodes.csv"
        termsberry_edges_csv_path = self.output_dir / "voyant_termsberry_edges.csv"
        self._write_csv(
            termsberry_nodes_csv_path,
            ["node", "frequency", "kind"],
            termsberry_nodes,
        )
        self._write_csv(
            termsberry_edges_csv_path,
            ["source", "target", "weight"],
            termsberry_edges,
        )
        termsberry_graph_path = self.output_dir / "voyant_termsberry.png"
        self._plot_termsberry(
            path=termsberry_graph_path,
            nodes=termsberry_nodes,
            edges=termsberry_edges,
            selected_terms=selected_terms,
            width=int(config["width"]),
            height=int(config["height"]),
        )

        bubble_points, bubble_doc_titles, bubble_bins = self._build_bubblelines_data(
            doc_streams=doc_streams,
            terms=bubble_terms,
            bins=bins,
            max_docs=max_docs,
        )
        bubblelines_points_csv_path = self.output_dir / "voyant_bubblelines_points.csv"
        self._write_csv(
            bubblelines_points_csv_path,
            ["doc_index", "doc_title", "term", "segment", "count", "relative"],
            bubble_points,
        )
        bubblelines_graph_path = self.output_dir / "voyant_bubblelines.png"
        self._plot_bubblelines(
            path=bubblelines_graph_path,
            points=bubble_points,
            doc_titles=bubble_doc_titles,
            terms=bubble_terms,
            bins=bubble_bins,
            width=int(config["width"]),
            height=int(config["height"]),
        )

        cooccurrence_rows = self._build_cooccurrences_data(
            uce_streams=uce_streams,
            selected_terms=selected_terms,
            context_window=context_window,
        )
        cooccurrences_csv_path = self.output_dir / "voyant_cooccurrences.csv"
        self._write_csv(
            cooccurrences_csv_path,
            ["term_left", "term_right", "count"],
            cooccurrence_rows,
        )
        cooccurrences_graph_path = self.output_dir / "voyant_cooccurrences.png"
        self._plot_cooccurrences(
            path=cooccurrences_graph_path,
            edges=cooccurrence_rows,
            selected_terms=selected_terms,
            width=int(config["width"]),
            height=int(config["height"]),
        )

        graph_gallery = {
            VOYANT_GRAPH_LABEL_BY_PANEL["termsberry"]: termsberry_graph_path,
            VOYANT_GRAPH_LABEL_BY_PANEL["trends"]: trends_graph_path,
            VOYANT_GRAPH_LABEL_BY_PANEL["document_terms"]: document_terms_chart_path,
            VOYANT_GRAPH_LABEL_BY_PANEL["bubblelines"]: bubblelines_graph_path,
            VOYANT_GRAPH_LABEL_BY_PANEL["cooccurrences"]: cooccurrences_graph_path,
        }
        graph_gallery = {
            label: path
            for label, path in graph_gallery.items()
            if path.exists()
        }
        # Compatibilidade retroativa com labels sem acentuação.
        if "Tendências" in graph_gallery:
            graph_gallery["Tendencias"] = graph_gallery["Tendências"]
        if "Gráfico de bolhas" in graph_gallery:
            graph_gallery["Grafico de bolhas"] = graph_gallery["Gráfico de bolhas"]
        if "Co-ocorrências" in graph_gallery:
            graph_gallery["Co-ocorrencias"] = graph_gallery["Co-ocorrências"]

        table_gallery = {
            VOYANT_TABLE_LABEL_BY_PANEL["document_terms"]: document_terms_csv_path,
            "Contextos": contexts_csv_path,
            VOYANT_TABLE_LABEL_BY_PANEL["cooccurrences"]: cooccurrences_csv_path,
            VOYANT_TABLE_LABEL_BY_PANEL["trends"]: trends_csv_path,
            "Nos TermsBerry": termsberry_nodes_csv_path,
            "Arestas TermsBerry": termsberry_edges_csv_path,
            VOYANT_TABLE_LABEL_BY_PANEL["bubblelines"]: bubblelines_points_csv_path,
        }
        table_gallery = {
            label: path
            for label, path in table_gallery.items()
            if path.exists()
        }
        # Compatibilidade retroativa com labels sem acentuação.
        if "Tendências" in table_gallery:
            table_gallery["Tendencias"] = table_gallery["Tendências"]
        if "Co-ocorrências" in table_gallery:
            table_gallery["Co-ocorrencias"] = table_gallery["Co-ocorrências"]

        graph_path_by_panel: Dict[str, Optional[Path]] = {
            "termsberry": termsberry_graph_path if termsberry_graph_path.exists() else None,
            "trends": trends_graph_path if trends_graph_path.exists() else None,
            "document_terms": document_terms_chart_path if document_terms_chart_path.exists() else None,
            "bubblelines": bubblelines_graph_path if bubblelines_graph_path.exists() else None,
            "cooccurrences": cooccurrences_graph_path if cooccurrences_graph_path.exists() else None,
        }
        table_path_by_panel: Dict[str, Optional[Path]] = {
            "termsberry": termsberry_nodes_csv_path if termsberry_nodes_csv_path.exists() else None,
            "trends": trends_csv_path if trends_csv_path.exists() else None,
            "document_terms": document_terms_csv_path if document_terms_csv_path.exists() else None,
            "bubblelines": bubblelines_points_csv_path if bubblelines_points_csv_path.exists() else None,
            "cooccurrences": cooccurrences_csv_path if cooccurrences_csv_path.exists() else None,
        }

        summary_payload = {
            "selected_terms": selected_terms,
            "query_terms": query_terms,
            "documents": len(doc_streams),
            "segments": n_segments,
            "contexts": len(contexts_rows),
            "context_window": context_window,
            "bins": bins,
            "max_docs": max_docs,
            "mode": config["mode"],
        }
        graphs_payload: Dict[str, Dict[str, Any]] = {}
        tables_payload: Dict[str, Dict[str, Any]] = {}
        graph_tabs: List[str] = []
        total_tokens = sum(len(doc.get("tokens", [])) for doc in doc_streams)
        for panel_id in VOYANT_PANEL_ORDER:
            panel_title = VOYANT_PANEL_TITLES_PT.get(panel_id, panel_id)
            panel_graph = graph_path_by_panel.get(panel_id)
            panel_table = table_path_by_panel.get(panel_id)
            if panel_graph is not None and panel_graph.exists():
                graph_tabs.append(panel_id)
            graphs_payload[panel_id] = {
                "id": panel_id,
                "title_pt": panel_title,
                "image_path": str(panel_graph) if panel_graph and panel_graph.exists() else "",
                "stats": {},
            }
            tables_payload[panel_id] = {
                "id": panel_id,
                "title_pt": panel_title,
                "csv_path": str(panel_table) if panel_table and panel_table.exists() else "",
                "row_count": self._count_csv_data_rows(panel_table),
            }

        graphs_payload["termsberry"]["stats"] = {
            "nodes": len(termsberry_nodes),
            "edges": len(termsberry_edges),
            "selected_terms": len(selected_terms),
        }
        graphs_payload["trends"]["stats"] = {
            "segments": int(n_segments),
            "tracked_terms": len(trends_terms),
        }
        graphs_payload["document_terms"]["stats"] = {
            "ranked_terms": len(document_terms_rows),
            "document": str(primary_doc.get("title", "Documento")),
        }
        graphs_payload["bubblelines"]["stats"] = {
            "documents": len(bubble_doc_titles),
            "segments": int(bubble_bins),
            "terms": len(bubble_terms),
        }
        graphs_payload["cooccurrences"]["stats"] = {
            "pairs": len(cooccurrence_rows),
            "selected_terms": len(selected_terms),
        }
        tables_payload["termsberry"]["extra_csv"] = [
            {
                "id": "termsberry_edges",
                "title_pt": "TermsBerry (Arestas)",
                "csv_path": str(termsberry_edges_csv_path) if termsberry_edges_csv_path.exists() else "",
                "row_count": self._count_csv_data_rows(termsberry_edges_csv_path),
            }
        ]
        tables_payload["document_terms"]["extra_csv"] = [
            {
                "id": "contexts",
                "title_pt": "Contextos",
                "csv_path": str(contexts_csv_path) if contexts_csv_path.exists() else "",
                "row_count": self._count_csv_data_rows(contexts_csv_path),
            }
        ]
        voyant_suite_payload_v1: Dict[str, Any] = {
            "version": "voyant_suite_payload_v1",
            "graph_tabs": list(VOYANT_PANEL_ORDER),
            "graphs": graphs_payload,
            "tables": tables_payload,
            "report": {
                "html_path": "",
                "txt_summary": (
                    f"{len(doc_streams)} documentos, {n_segments} segmentos, "
                    f"{len(selected_terms)} termos selecionados."
                ),
            },
            "meta": {
                "corpus_name": str(primary_doc.get("title", "Corpus")),
                "doc_count": len(doc_streams),
                "tokens": int(total_tokens),
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "selected_terms": list(selected_terms),
                "query_terms": list(query_terms),
                "context_window": int(context_window),
                "bins": int(bins),
                "max_docs": int(max_docs),
                "mode": str(config.get("mode", "top")),
            },
        }
        summary_payload["voyant_suite_payload_v1"] = voyant_suite_payload_v1
        summary_payload["graph_gallery"] = {
            label: str(path)
            for label, path in graph_gallery.items()
        }
        summary_payload["table_gallery"] = {
            label: str(path)
            for label, path in table_gallery.items()
        }
        summary_json_path = self.output_dir / "voyant_suite_summary.json"
        summary_json_path.write_text(
            json.dumps(summary_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return VoyantSuiteResult(
            graph_path=graph_path_by_panel.get("termsberry"),
            table_path=table_path_by_panel.get("document_terms"),
            termsberry_graph_path=graph_path_by_panel.get("termsberry"),
            trends_graph_path=graph_path_by_panel.get("trends"),
            document_terms_chart_path=graph_path_by_panel.get("document_terms"),
            bubblelines_graph_path=graph_path_by_panel.get("bubblelines"),
            cooccurrences_graph_path=graph_path_by_panel.get("cooccurrences"),
            termsberry_nodes_csv_path=table_path_by_panel.get("termsberry"),
            termsberry_edges_csv_path=termsberry_edges_csv_path if termsberry_edges_csv_path.exists() else None,
            trends_csv_path=table_path_by_panel.get("trends"),
            document_terms_csv_path=table_path_by_panel.get("document_terms"),
            contexts_csv_path=contexts_csv_path if contexts_csv_path.exists() else None,
            bubblelines_points_csv_path=table_path_by_panel.get("bubblelines"),
            cooccurrences_csv_path=table_path_by_panel.get("cooccurrences"),
            summary_json_path=summary_json_path if summary_json_path.exists() else None,
            graph_gallery=graph_gallery,
            table_gallery=table_gallery,
            voyant_suite_payload_v1=voyant_suite_payload_v1,
            selected_terms=selected_terms,
            query_terms=query_terms,
            n_documents=len(doc_streams),
            n_segments=n_segments,
            n_contexts=len(contexts_rows),
        )

    def _sanitize_params(self, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        config = {**self.DEFAULT_PARAMS, **(params or {})}
        config["query"] = str(config.get("query", "") or "").strip()
        config["num_initial_terms"] = self._clamp_int(config.get("num_initial_terms"), 20, 5, 80)
        config["context"] = self._clamp_int(config.get("context"), 5, 2, 20)
        config["bins"] = self._clamp_int(config.get("bins"), 10, 4, 30)
        config["max_docs"] = self._clamp_int(config.get("max_docs"), 50, 5, 300)
        config["max_context_rows"] = self._clamp_int(config.get("max_context_rows"), 800, 50, 5000)
        config["min_freq"] = self._clamp_int(config.get("min_freq"), 2, 1, 100)
        config["termsberry_per_term_limit"] = self._clamp_int(
            config.get("termsberry_per_term_limit"), 8, 4, 20
        )
        config["termsberry_max_nodes"] = self._clamp_int(
            config.get("termsberry_max_nodes"), 120, 40, 220
        )
        config["width"] = self._clamp_int(config.get("width"), 1400, 700, 3200)
        config["height"] = self._clamp_int(config.get("height"), 900, 500, 2200)
        config["use_lemmas"] = bool(config.get("use_lemmas", True))
        config["active_only"] = bool(config.get("active_only", True))
        config["remove_stopwords"] = bool(config.get("remove_stopwords", True))
        mode = str(config.get("mode", "top") or "top").strip().lower()
        if mode not in {"top", "mixed", "query"}:
            mode = "top"
        config["mode"] = mode
        return config

    @staticmethod
    def _clamp_int(value: Any, default: int, min_value: int, max_value: int) -> int:
        try:
            normalized = int(value)
        except Exception:
            normalized = int(default)
        return max(min_value, min(max_value, normalized))

    def _parse_query_terms(self, query: Any) -> List[str]:
        raw = str(query or "").strip().lower()
        if not raw:
            return []
        seen: set[str] = set()
        terms: List[str] = []
        for token in QUERY_TOKEN_PATTERN.findall(raw):
            clean = token.strip().lower()
            if clean and clean not in seen:
                terms.append(clean)
                seen.add(clean)
        return terms

    def _build_document_streams(
        self,
        *,
        records: List[UciRecord],
        use_lemmas: bool,
        active_only: bool,
        remove_stopwords: bool,
    ) -> List[Dict[str, Any]]:
        streams: List[Dict[str, Any]] = []
        for idx, record in enumerate(records):
            tokens = self._tokenize_and_normalize(
                record.text,
                use_lemmas=use_lemmas,
                active_only=active_only,
                remove_stopwords=remove_stopwords,
            )
            if not tokens:
                continue
            streams.append(
                {
                    "uci_id": int(record.uci_id),
                    "uci_index": int(record.uci_index),
                    "title": self._document_title(record, idx),
                    "tokens": tokens,
                }
            )
        return streams

    def _build_uce_streams(
        self,
        *,
        doc_streams: List[Dict[str, Any]],
        use_lemmas: bool,
        active_only: bool,
        remove_stopwords: bool,
    ) -> List[Dict[str, Any]]:
        title_by_uci_id: Dict[int, str] = {}
        title_by_uci_index: Dict[int, str] = {}
        for doc in doc_streams:
            title = str(doc.get("title", "Documento")).strip() or "Documento"
            title_by_uci_id[int(doc.get("uci_id", -1))] = title
            title_by_uci_index[int(doc.get("uci_index", -1))] = title

        iduces = self.corpus.make_iduces()
        uce_streams: List[Dict[str, Any]] = []
        for uce_id, text in self.corpus.get_uces():
            tokens = self._tokenize_and_normalize(
                str(text or ""),
                use_lemmas=use_lemmas,
                active_only=active_only,
                remove_stopwords=remove_stopwords,
            )
            if not tokens:
                continue
            uce = iduces.get(int(uce_id))
            uci_ref = int(getattr(uce, "uci", -1)) if uce is not None else -1
            title = (
                title_by_uci_id.get(uci_ref)
                or title_by_uci_index.get(uci_ref)
                or f"Documento {max(1, uci_ref + 1)}"
            )
            uce_streams.append(
                {
                    "uce_id": int(uce_id),
                    "uci_id": int(uci_ref),
                    "title": title,
                    "tokens": tokens,
                }
            )
        return uce_streams

    @staticmethod
    def _document_title(record: UciRecord, fallback_index: int) -> str:
        preferred_keys = (
            "title",
            "titulo",
            "document",
            "documento",
            "doc",
            "nome",
            "name",
            "arquivo",
            "file",
        )
        for key in preferred_keys:
            value = str(record.metadata.get(key, "") or "").strip()
            if value:
                return value
        if record.metadata:
            first_key = sorted(record.metadata.keys())[0]
            value = str(record.metadata.get(first_key, "") or "").strip()
            if value:
                return value
        return f"Documento {fallback_index + 1}"

    def _tokenize_and_normalize(
        self,
        text: str,
        *,
        use_lemmas: bool,
        active_only: bool,
        remove_stopwords: bool,
    ) -> List[str]:
        tokens = tokenize_text(str(text or ""), remove_stopwords=False)
        normalized: List[str] = []
        for token in tokens:
            clean = self._normalize_token(
                token,
                use_lemmas=use_lemmas,
                active_only=active_only,
            )
            if not clean:
                continue
            if remove_stopwords and clean in self._fallback_stopwords:
                continue
            normalized.append(clean)
        return normalized

    def _normalize_token(self, token: str, *, use_lemmas: bool, active_only: bool) -> str:
        clean = str(token or "").strip().lower()
        if len(clean) < 3:
            return ""

        if use_lemmas:
            forme = self.corpus.formes.get(clean)
            if forme is not None and getattr(forme, "lem", None):
                clean = str(forme.lem).strip().lower()
            lemma = self.corpus.lems.get(clean)
            if active_only and lemma is not None and int(getattr(lemma, "act", 1)) != 1:
                return ""
        else:
            forme = self.corpus.formes.get(clean)
            if active_only and forme is not None and int(getattr(forme, "act", 1)) != 1:
                return ""
        return clean

    def _select_terms(
        self,
        *,
        global_counter: Counter[str],
        query_terms: List[str],
        num_initial_terms: int,
        min_freq: int,
        mode: str,
    ) -> List[str]:
        candidates = [
            term
            for term, freq in sorted(global_counter.items(), key=lambda item: (-item[1], item[0]))
            if int(freq) >= int(min_freq)
        ]
        if not candidates:
            return []

        query_present = [term for term in query_terms if int(global_counter.get(term, 0)) > 0]

        if mode == "query":
            if query_present:
                return query_present[:num_initial_terms]
            return candidates[:num_initial_terms]

        if mode == "mixed":
            merged: List[str] = []
            seen: set[str] = set()
            for term in query_present + candidates:
                if term not in seen:
                    merged.append(term)
                    seen.add(term)
                if len(merged) >= num_initial_terms:
                    break
            return merged

        return candidates[:num_initial_terms]

    def _build_trends_data(
        self,
        *,
        uce_streams: List[Dict[str, Any]],
        terms: List[str],
        bins: int,
    ) -> Tuple[List[Tuple[int, str, int, float]], Dict[str, List[float]], int]:
        if not uce_streams or not terms:
            return [], {}, 0

        total_uces = len(uce_streams)
        n_segments = max(1, min(int(bins), total_uces))
        segment_totals = [0 for _ in range(n_segments)]
        term_counts: Dict[str, List[int]] = {term: [0 for _ in range(n_segments)] for term in terms}

        for idx, item in enumerate(uce_streams):
            tokens = item.get("tokens", [])
            if not isinstance(tokens, list):
                continue
            segment = min(n_segments - 1, int((idx * n_segments) / total_uces))
            segment_totals[segment] += len(tokens)
            counter = Counter(tokens)
            for term in terms:
                term_counts[term][segment] += int(counter.get(term, 0))

        rows: List[Tuple[int, str, int, float]] = []
        series: Dict[str, List[float]] = {}
        for term in terms:
            term_series: List[float] = []
            for segment in range(n_segments):
                count = int(term_counts[term][segment])
                total = int(segment_totals[segment])
                relative = (float(count) / float(total)) if total > 0 else 0.0
                rows.append((segment + 1, term, count, relative))
                term_series.append(relative)
            series[term] = term_series

        return rows, series, n_segments

    def _build_document_terms_data(
        self,
        *,
        doc_tokens: List[str],
        terms: List[str],
        bins: int,
        min_freq: int,
    ) -> Tuple[List[Tuple[int, str, int, float, str]], Dict[str, List[float]]]:
        if not doc_tokens:
            return [], {}

        counts = Counter(doc_tokens)
        selected = [term for term in terms if int(counts.get(term, 0)) >= int(min_freq)]
        if not selected:
            selected = [term for term, _ in counts.most_common(min(20, max(5, len(terms))))]

        selected = sorted(selected, key=lambda term: (-int(counts.get(term, 0)), term))
        selected = selected[: min(len(selected), 25)]

        n_bins = max(1, min(int(bins), len(doc_tokens)))
        segment_totals = [0 for _ in range(n_bins)]
        term_segment_counts: Dict[str, List[int]] = {term: [0 for _ in range(n_bins)] for term in selected}

        total_tokens = len(doc_tokens)
        for idx, token in enumerate(doc_tokens):
            segment = min(n_bins - 1, int((idx * n_bins) / total_tokens))
            segment_totals[segment] += 1
            if token in term_segment_counts:
                term_segment_counts[token][segment] += 1

        series: Dict[str, List[float]] = {}
        rows: List[Tuple[int, str, int, float, str]] = []
        for rank, term in enumerate(selected, start=1):
            count = int(counts.get(term, 0))
            relative_percent = (100.0 * float(count) / float(total_tokens)) if total_tokens > 0 else 0.0
            rel_series: List[float] = []
            for segment in range(n_bins):
                seg_total = int(segment_totals[segment])
                rel = (float(term_segment_counts[term][segment]) / float(seg_total)) if seg_total > 0 else 0.0
                rel_series.append(rel)
            series[term] = rel_series
            trend_code = self._encode_trend_series(rel_series)
            rows.append((rank, term, count, relative_percent, trend_code))

        return rows, series

    @staticmethod
    def _encode_trend_series(values: List[float]) -> str:
        if not values:
            return ""
        peak = max(float(value) for value in values)
        if peak <= 0:
            return "0" * len(values)
        return "".join(
            str(min(9, max(0, int(round((float(value) / peak) * 9.0)))))
            for value in values
        )

    def _build_contexts_data(
        self,
        *,
        uce_streams: List[Dict[str, Any]],
        terms: List[str],
        context_window: int,
        row_limit: int,
    ) -> List[Tuple[str, str, str, str, int, int]]:
        if not terms:
            return []
        terms_set = set(terms)
        contexts: List[Tuple[str, str, str, str, int, int]] = []

        for item in uce_streams:
            tokens = item.get("tokens", [])
            if not isinstance(tokens, list) or not tokens:
                continue
            for idx, token in enumerate(tokens):
                if token not in terms_set:
                    continue
                left = " ".join(tokens[max(0, idx - context_window):idx]).strip()
                right = " ".join(tokens[idx + 1: idx + 1 + context_window]).strip()
                contexts.append(
                    (
                        str(item.get("title", "Documento")),
                        left,
                        token,
                        right,
                        int(item.get("uce_id", -1)),
                        int(item.get("uci_id", -1)),
                    )
                )
                if len(contexts) >= row_limit:
                    return contexts
        return contexts

    def _build_termsberry_data(
        self,
        *,
        uce_streams: List[Dict[str, Any]],
        selected_terms: List[str],
        global_counter: Counter[str],
        context_window: int,
        per_term_limit: int,
        max_nodes: int,
    ) -> Tuple[List[Tuple[str, int, str]], List[Tuple[str, str, int]]]:
        selected_set = set(selected_terms)
        neighbor_by_term: Dict[str, Counter[str]] = {term: Counter() for term in selected_terms}

        for item in uce_streams:
            tokens = item.get("tokens", [])
            if not isinstance(tokens, list) or not tokens:
                continue
            for idx, token in enumerate(tokens):
                if token not in selected_set:
                    continue
                start = max(0, idx - context_window)
                end = min(len(tokens), idx + context_window + 1)
                for j in range(start, end):
                    if j == idx:
                        continue
                    other = str(tokens[j]).strip().lower()
                    if not other or other == token or len(other) < 3:
                        continue
                    neighbor_by_term[token][other] += 1

        edge_counter: Counter[Tuple[str, str]] = Counter()
        for term in selected_terms:
            top_neighbors = neighbor_by_term[term].most_common(per_term_limit)
            for other, weight in top_neighbors:
                pair = tuple(sorted((term, other)))
                edge_counter[pair] += int(weight)

        if not edge_counter:
            nodes = [
                (term, int(global_counter.get(term, 0)), "term")
                for term in selected_terms
            ]
            return nodes, []

        max_edges = max(80, min(180, int(max_nodes * 1.4)))
        ranked_edges = edge_counter.most_common(max_edges)
        trimmed_edges = [
            (pair, int(weight))
            for pair, weight in ranked_edges
            if int(weight) >= 2
        ]
        if not trimmed_edges:
            trimmed_edges = [(pair, int(weight)) for pair, weight in ranked_edges[: max(1, max_edges // 2)]]
        used_nodes: set[str] = set()
        for (left, right), _weight in trimmed_edges:
            used_nodes.add(left)
            used_nodes.add(right)

        sorted_used_nodes = sorted(
            used_nodes,
            key=lambda item: (-int(global_counter.get(item, 0)), item),
        )
        selected_set = set(selected_terms)
        capped_nodes: List[str] = [node for node in sorted_used_nodes if node in selected_set]
        for node in sorted_used_nodes:
            if node in capped_nodes:
                continue
            if len(capped_nodes) >= int(max_nodes):
                break
            capped_nodes.append(node)
        if not capped_nodes:
            capped_nodes = sorted_used_nodes[: max(1, int(max_nodes))]
        kept_nodes = set(capped_nodes)

        node_rows: List[Tuple[str, int, str]] = []
        for node in capped_nodes:
            kind = "term" if node in selected_set else "collocate"
            freq = int(global_counter.get(node, 0))
            if freq <= 0:
                freq = 1
            node_rows.append((node, freq, kind))

        edge_rows = [
            (left, right, int(weight))
            for (left, right), weight in trimmed_edges
            if int(weight) > 0 and left in kept_nodes and right in kept_nodes
        ]
        return node_rows, edge_rows

    def _build_bubblelines_data(
        self,
        *,
        doc_streams: List[Dict[str, Any]],
        terms: List[str],
        bins: int,
        max_docs: int,
    ) -> Tuple[List[Tuple[int, str, str, int, int, float]], List[str], int]:
        if not doc_streams or not terms:
            return [], [], 0

        docs = doc_streams[: max(1, int(max_docs))]
        n_bins = max(1, int(bins))
        points: List[Tuple[int, str, str, int, int, float]] = []
        doc_titles: List[str] = []

        for doc_idx, doc in enumerate(docs):
            title = str(doc.get("title", f"Documento {doc_idx + 1}"))
            tokens = doc.get("tokens", [])
            if not isinstance(tokens, list) or not tokens:
                continue
            doc_titles.append(title)
            n_tokens = len(tokens)
            segment_totals = [0 for _ in range(n_bins)]
            term_segment_counts: Dict[str, List[int]] = {term: [0 for _ in range(n_bins)] for term in terms}

            for idx, token in enumerate(tokens):
                segment = min(n_bins - 1, int((idx * n_bins) / n_tokens))
                segment_totals[segment] += 1
                if token in term_segment_counts:
                    term_segment_counts[token][segment] += 1

            for term in terms:
                for segment in range(n_bins):
                    count = int(term_segment_counts[term][segment])
                    total = int(segment_totals[segment])
                    relative = (float(count) / float(total)) if total > 0 else 0.0
                    points.append((doc_idx, title, term, segment + 1, count, relative))

        return points, doc_titles, n_bins

    def _build_cooccurrences_data(
        self,
        *,
        uce_streams: List[Dict[str, Any]],
        selected_terms: List[str],
        context_window: int,
    ) -> List[Tuple[str, str, int]]:
        selected_set = set(selected_terms)
        pair_counter: Counter[Tuple[str, str]] = Counter()

        for item in uce_streams:
            tokens = item.get("tokens", [])
            if not isinstance(tokens, list) or not tokens:
                continue
            selected_positions = [
                (idx, str(token))
                for idx, token in enumerate(tokens)
                if token in selected_set
            ]
            for left_idx in range(len(selected_positions)):
                pos_left, term_left = selected_positions[left_idx]
                for right_idx in range(left_idx + 1, len(selected_positions)):
                    pos_right, term_right = selected_positions[right_idx]
                    if (pos_right - pos_left) > int(context_window):
                        break
                    if term_left == term_right:
                        continue
                    pair = tuple(sorted((term_left, term_right)))
                    pair_counter[pair] += 1

        rows = [
            (left, right, int(weight))
            for (left, right), weight in pair_counter.most_common(200)
            if int(weight) > 0
        ]
        return rows

    @staticmethod
    def _pick_primary_document(doc_streams: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not doc_streams:
            return {"title": "Documento", "tokens": []}
        return max(
            doc_streams,
            key=lambda item: len(item.get("tokens", [])),
        )

    @staticmethod
    def _write_csv(path: Path, headers: Sequence[str], rows: Iterable[Iterable[Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(list(headers))
            for row in rows:
                writer.writerow(list(row))

    @staticmethod
    def _count_csv_data_rows(path: Optional[Path]) -> int:
        if path is None or not path.exists() or not path.is_file():
            return 0
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                # Primeiro cabeçalho, demais linhas = dados.
                count = sum(1 for _ in handle)
            return max(0, count - 1)
        except OSError:
            return 0

    @staticmethod
    def _figure_size(width_px: int, height_px: int) -> Tuple[float, float]:
        width_in = max(7.0, min(24.0, float(width_px) / 110.0))
        height_in = max(4.5, min(16.0, float(height_px) / 110.0))
        return width_in, height_in

    @staticmethod
    def _truncate_label(label: str, max_chars: int = 28) -> str:
        clean = str(label or "").strip()
        if len(clean) <= max_chars:
            return clean
        return clean[: max_chars - 1].rstrip() + "..."

    def _plot_trends(
        self,
        *,
        path: Path,
        series: Dict[str, List[float]],
        bins: int,
        width: int,
        height: int,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=self._figure_size(width, height))
        if not series:
            ax.text(0.5, 0.5, "Sem dados para Tendências", ha="center", va="center")
            ax.axis("off")
            fig.savefig(path, dpi=140, bbox_inches="tight")
            plt.close(fig)
            return

        x_values = list(range(1, int(bins) + 1))
        for idx, (term, values) in enumerate(series.items()):
            color = DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
            ax.plot(
                x_values,
                values,
                marker="o",
                linewidth=1.6,
                markersize=4.6,
                color=color,
                label=term,
            )
        ax.set_title("Tendências lexicais")
        ax.set_xlabel("Segmentos do corpus")
        ax.set_ylabel("Frequencia relativa")
        ax.grid(alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)

    def _plot_document_terms(
        self,
        *,
        path: Path,
        rows: List[Tuple[int, str, int, float, str]],
        series: Dict[str, List[float]],
        bins: int,
        width: int,
        height: int,
        title: str,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=self._figure_size(width, height))
        if not rows or not series:
            ax.text(0.5, 0.5, "Sem dados para Termos do documento", ha="center", va="center")
            ax.axis("off")
            fig.savefig(path, dpi=140, bbox_inches="tight")
            plt.close(fig)
            return

        top_rows = rows[: min(15, len(rows))]
        terms = [str(row[1]) for row in top_rows]
        counts = [int(row[2]) for row in top_rows]
        max_count = max(counts) if counts else 1

        y_pos = list(range(len(top_rows)))
        ax.barh(y_pos, counts, color="#2563EB", alpha=0.78, edgecolor="#1D4ED8")
        ax.set_yticks(y_pos)
        ax.set_yticklabels([self._truncate_label(term, max_chars=24) for term in terms], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, max_count * 1.55)
        ax.set_xlabel("Contagem no documento")
        ax.set_ylabel("Termos")
        ax.set_title(title)
        ax.grid(axis="x", alpha=0.25)

        for idx, row in enumerate(top_rows):
            relative_percent = float(row[3])
            trend_code = str(row[4])
            count = int(row[2])
            ax.text(
                count + max_count * 0.03,
                idx,
                f"{relative_percent:.2f}%  {trend_code}",
                va="center",
                ha="left",
                fontsize=7.5,
                color="#334155",
            )
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)

    def _plot_termsberry(
        self,
        *,
        path: Path,
        nodes: List[Tuple[str, int, str]],
        edges: List[Tuple[str, str, int]],
        selected_terms: List[str],
        width: int,
        height: int,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=self._figure_size(width, height))
        if not nodes:
            ax.text(0.5, 0.5, "Sem dados para TermsBerry", ha="center", va="center")
            ax.axis("off")
            fig.savefig(path, dpi=140, bbox_inches="tight")
            plt.close(fig)
            return

        selected_set = set(selected_terms)
        sorted_nodes = sorted(
            nodes,
            key=lambda item: (-int(item[1]), str(item[0])),
        )
        # Aproxima comportamento do Voyant: poucas dezenas de termos com maior frequência.
        sorted_nodes = sorted_nodes[:75]
        frequencies = [max(1, int(freq)) for _term, freq, _kind in sorted_nodes]
        max_freq = max(frequencies) if frequencies else 1

        # Raios em unidades de layout (não pixels).
        radii: List[float] = []
        for _term, freq, _kind in sorted_nodes:
            rel = math.sqrt(float(max(1, int(freq))) / float(max_freq))
            radii.append(0.06 + 0.24 * rel)

        # Empacotamento simples por espiral para evitar sobreposição central excessiva.
        placed: List[Tuple[float, float, float]] = []
        pad = 0.015
        for idx, radius in enumerate(radii):
            if idx == 0:
                placed.append((0.0, 0.0, radius))
                continue
            theta = 0.0
            found = False
            while theta < 5000.0:
                spiral_r = 0.02 * theta
                x_coord = spiral_r * math.cos(theta)
                y_coord = spiral_r * math.sin(theta)
                ok = True
                for px, py, pr in placed:
                    dist = math.hypot(x_coord - px, y_coord - py)
                    if dist < (radius + pr + pad):
                        ok = False
                        break
                if ok:
                    placed.append((x_coord, y_coord, radius))
                    found = True
                    break
                theta += 0.20
            if not found:
                # Fallback muito raro: posiciona no anel mais externo.
                angle = idx * 0.7
                outer = 2.2 + (0.03 * idx)
                placed.append((outer * math.cos(angle), outer * math.sin(angle), radius))

        min_x = min(x - r for (x, _y, r) in placed)
        max_x = max(x + r for (x, _y, r) in placed)
        min_y = min(y - r for (_x, y, r) in placed)
        max_y = max(y + r for (_x, y, r) in placed)
        span_x = max(1e-6, max_x - min_x)
        span_y = max(1e-6, max_y - min_y)
        scale = 0.9 / max(span_x, span_y)

        # Heurística inspirada no Voyant TermsBerry:
        # calcula fonte mínima pelo espaço global disponível por termo.
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        ax_bbox = ax.get_window_extent(renderer=renderer)
        layout_radius_px = max(1.0, min(float(ax_bbox.width), float(ax_bbox.height)) / 2.0)
        layout_area_px = math.pi * (layout_radius_px * layout_radius_px)
        total_terms = max(1, len(sorted_nodes))
        term_area_px = layout_area_px / float(total_terms)
        term_radius_px = math.sqrt(term_area_px / math.pi)
        min_font_px = max(5.5, term_radius_px / 3.0)
        max_font_px = min_font_px * 2.25
        min_freq = min(frequencies) if frequencies else 1

        def _text_size_px(raw_freq: int) -> float:
            if max_freq <= min_freq:
                return min_font_px * 1.35
            ratio = (float(raw_freq) - float(min_freq)) / float(max_freq - min_freq)
            ratio = max(0.0, min(1.0, ratio))
            return min_font_px + ((max_font_px - min_font_px) * ratio)

        normalized_positions: List[Tuple[float, float, float]] = []
        for x_raw, y_raw, radius_raw in placed:
            normalized_positions.append(
                (
                    (x_raw - (min_x + max_x) / 2.0) * scale,
                    (y_raw - (min_y + max_y) / 2.0) * scale,
                    radius_raw * scale,
                )
            )

        for (node, freq, _kind), (x_coord, y_coord, radius) in zip(sorted_nodes, normalized_positions):
            is_selected = node in selected_set
            face = "#3B82F6" if is_selected else "#E5E7EB"
            edge = "#1D4ED8" if is_selected else "#64748B"
            circ = plt.Circle(
                (x_coord, y_coord),
                radius,
                facecolor=face,
                edgecolor=edge,
                linewidth=0.9,
                alpha=0.95,
            )
            ax.add_patch(circ)

            node_freq = int(max(1, int(freq)))
            p_center = ax.transData.transform((x_coord, y_coord))
            p_right = ax.transData.transform((x_coord + radius, y_coord))
            radius_px = max(1.0, abs(float(p_right[0]) - float(p_center[0])))
            diameter_px = max(2.0, 2.0 * radius_px)
            if diameter_px < 12.0:
                continue

            label_text = str(node).strip()
            if not label_text:
                continue

            target_font_px = _text_size_px(node_freq)
            font_px = max(4.8, min(target_font_px, diameter_px * 0.42))
            font_pt = max(3.5, float(font_px) * 72.0 / float(max(1.0, fig.dpi)))
            text_artist = ax.text(
                x_coord,
                y_coord,
                label_text,
                ha="center",
                va="center",
                fontsize=font_pt,
                fontweight=("bold" if is_selected else "normal"),
                color=("#FFFFFF" if is_selected else "#0F172A"),
                zorder=8,
            )
            # Ajuste iterativo para garantir que o rótulo caiba dentro da bolha.
            max_text_width = diameter_px * 0.80
            max_text_height = diameter_px * 0.56
            for _ in range(10):
                bbox = text_artist.get_window_extent(renderer=renderer)
                bw = max(1.0, float(bbox.width))
                bh = max(1.0, float(bbox.height))
                if bw <= max_text_width and bh <= max_text_height:
                    break

                scale_factor = min(max_text_width / bw, max_text_height / bh) * 0.94
                new_size = float(text_artist.get_fontsize()) * scale_factor
                if new_size >= 4.6:
                    text_artist.set_fontsize(new_size)
                    continue

                current_label = str(text_artist.get_text() or "")
                if len(current_label) <= 3:
                    break
                shortened = current_label[:-2].strip()
                if not shortened:
                    break
                text_artist.set_text(f"{shortened}…")
                text_artist.set_fontsize(max(4.8, font_pt * 0.78))

        ax.set_title("TermsBerry")
        limit = max(
            max(abs(x) + r for x, _y, r in normalized_positions),
            max(abs(y) + r for _x, y, r in normalized_positions),
        )
        bound = max(0.52, float(limit) + 0.05)
        ax.set_xlim(-bound, bound)
        ax.set_ylim(-bound, bound)
        ax.set_aspect("equal", adjustable="box")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=180)
        plt.close(fig)

    def _plot_bubblelines(
        self,
        *,
        path: Path,
        points: List[Tuple[int, str, str, int, int, float]],
        doc_titles: List[str],
        terms: List[str],
        bins: int,
        width: int,
        height: int,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig_w, fig_h = self._figure_size(width, height)
        fig_h = max(fig_h, min(15.0, 0.52 * max(6, len(doc_titles))))
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))

        if not points:
            ax.text(0.5, 0.5, "Sem dados para Bubblelines", ha="center", va="center")
            ax.axis("off")
            fig.savefig(path, dpi=140, bbox_inches="tight")
            plt.close(fig)
            return

        color_by_term = {
            term: DEFAULT_COLORS[idx % len(DEFAULT_COLORS)]
            for idx, term in enumerate(terms)
        }

        for term in terms:
            term_points = [row for row in points if row[2] == term and int(row[4]) > 0]
            if not term_points:
                continue
            x = [int(row[3]) for row in term_points]
            y = [int(row[0]) for row in term_points]
            sizes = [
                18.0 + (900.0 * min(1.0, float(row[5]) * 8.0))
                for row in term_points
            ]
            ax.scatter(
                x,
                y,
                s=sizes,
                alpha=0.62,
                color=color_by_term.get(term, "#1F77B4"),
                edgecolors="none",
                label="_nolegend_",
            )

        ax.set_xlim(0.5, int(bins) + 0.5)
        ax.set_xticks(list(range(1, int(bins) + 1)))
        ax.set_xlabel("Segmentos")
        ax.set_ylabel("Documentos")
        ax.grid(axis="x", alpha=0.25)

        if doc_titles:
            y_ticks = list(range(len(doc_titles)))
            y_labels = [self._truncate_label(title, max_chars=36) for title in doc_titles]
            ax.set_yticks(y_ticks)
            ax.set_yticklabels(y_labels, fontsize=8)
            ax.invert_yaxis()

        legend_terms = [term for term in terms if any(row[2] == term and int(row[4]) > 0 for row in points)]
        legend_rows = 0
        title_artist = fig.suptitle("Gráfico de bolhas (Bubblelines)", y=0.985)
        legend_artist = None
        if legend_terms:
            from matplotlib.lines import Line2D

            handles = [
                Line2D(
                    [0],
                    [0],
                    marker="o",
                    linestyle="",
                    markersize=7,
                    markerfacecolor=color_by_term.get(term, "#1F77B4"),
                    markeredgecolor="none",
                    alpha=0.9,
                    label=term,
                )
                for term in legend_terms
            ]
            legend_cols = max(1, min(4, len(handles)))
            legend_rows = int(math.ceil(float(len(handles)) / float(legend_cols)))
            legend_artist = fig.legend(
                handles=handles,
                loc="upper center",
                bbox_to_anchor=(0.5, 0.952),
                ncol=legend_cols,
                fontsize=8,
                frameon=True,
                borderaxespad=0.2,
                handletextpad=0.4,
                columnspacing=0.9,
            )

        # Mede título/legenda e reserva área superior para evitar qualquer sobreposição.
        try:
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            top_lower_bound = 1.0
            if title_artist is not None:
                title_bbox = title_artist.get_window_extent(renderer=renderer).transformed(fig.transFigure.inverted())
                top_lower_bound = min(top_lower_bound, float(title_bbox.y0))
            if legend_artist is not None:
                legend_bbox = legend_artist.get_window_extent(renderer=renderer).transformed(fig.transFigure.inverted())
                top_lower_bound = min(top_lower_bound, float(legend_bbox.y0))
            top_margin = max(0.52, min(0.88, top_lower_bound - 0.02))
        except Exception:
            top_margin = 0.82 if legend_rows else 0.90

        fig.subplots_adjust(left=0.12, right=0.98, bottom=0.14, top=top_margin)
        fig.savefig(path, dpi=140)
        plt.close(fig)

    def _plot_cooccurrences(
        self,
        *,
        path: Path,
        edges: List[Tuple[str, str, int]],
        selected_terms: List[str],
        width: int,
        height: int,
    ) -> None:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx

        fig, ax = plt.subplots(figsize=self._figure_size(width, height))
        if not selected_terms:
            ax.text(0.5, 0.5, "Sem termos para co-ocorrencias", ha="center", va="center")
            ax.axis("off")
            fig.savefig(path, dpi=140, bbox_inches="tight")
            plt.close(fig)
            return

        graph = nx.Graph()
        for term in selected_terms:
            graph.add_node(term)
        for left, right, weight in edges:
            if left == right:
                continue
            graph.add_edge(left, right, weight=max(1, int(weight)))

        if graph.number_of_edges() == 0 and graph.number_of_nodes() > 1:
            nodes = list(graph.nodes)
            for idx in range(len(nodes) - 1):
                graph.add_edge(nodes[idx], nodes[idx + 1], weight=1)

        layout = nx.spring_layout(
            graph,
            seed=17,
            k=1.4 / math.sqrt(max(2, graph.number_of_nodes())),
            iterations=220,
            weight="weight",
        )

        degrees = dict(graph.degree())
        max_degree = max(degrees.values()) if degrees else 1
        node_sizes = [
            420.0 + 1800.0 * (float(max(1, degrees.get(node, 1))) / float(max_degree))
            for node in graph.nodes
        ]

        edge_weights = [float(graph.edges[edge].get("weight", 1.0)) for edge in graph.edges]
        max_weight = max(edge_weights) if edge_weights else 1.0
        edge_widths = [0.6 + 3.2 * (weight / max_weight) for weight in edge_weights]

        nx.draw_networkx_edges(
            graph,
            layout,
            ax=ax,
            width=edge_widths,
            edge_color="#64748B",
            alpha=0.62,
        )
        nx.draw_networkx_nodes(
            graph,
            layout,
            ax=ax,
            node_size=node_sizes,
            node_color="#93C5FD",
            edgecolors="#2563EB",
            linewidths=0.8,
            alpha=0.95,
        )
        nx.draw_networkx_labels(
            graph,
            layout,
            labels={node: node for node in graph.nodes},
            font_size=9,
            font_family="sans-serif",
            ax=ax,
        )

        ax.set_title("Co-ocorrências")
        ax.axis("off")
        fig.tight_layout()
        fig.savefig(path, dpi=140)
        plt.close(fig)
