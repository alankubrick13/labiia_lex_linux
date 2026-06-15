"""Audit artifacts for optional corpus preparation decisions."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .multiword_candidates import normalize_multiword_candidate

AUDIT_FIELDS = [
    "expression",
    "replacement",
    "n_tokens",
    "frequency",
    "doc_count",
    "is_score",
    "is_norm",
    "method",
    "selected",
]

CONTEXT_FIELDS = ["expression", "doc_id", "doc_label", "context"]
ENTITY_FIELDS = [
    "entity",
    "replacement",
    "entity_type",
    "frequency",
    "doc_count",
    "score",
    "selected",
]
ENTITY_CONTEXT_FIELDS = ["entity", "doc_id", "doc_label", "context"]


def _normalize_rows(items: Iterable[Dict[str, Any]], *, selected_expressions: set[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in items or []:
        normalized = normalize_multiword_candidate(dict(item or {}))
        if not normalized["expression"]:
            continue
        rows.append(
            {
                "expression": normalized["expression"],
                "replacement": normalized["replacement"],
                "n_tokens": normalized["n_tokens"],
                "frequency": normalized["frequency"],
                "doc_count": normalized.get("doc_count", 0),
                "is_score": normalized["is_score"],
                "is_norm": normalized["is_norm"],
                "method": normalized["method"],
                "selected": "true" if normalized["expression"] in selected_expressions else "false",
            }
        )
    return rows


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str] = AUDIT_FIELDS) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _multiword_context_rows(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in items or []:
        expression = str((item or {}).get("expression", "") or "").strip()
        if not expression:
            continue
        examples = (item or {}).get("context_examples", [])
        if not isinstance(examples, list):
            continue
        for example in examples:
            if not isinstance(example, dict):
                continue
            context = str(example.get("context", "") or "").strip()
            if not context:
                continue
            rows.append(
                {
                    "expression": expression,
                    "doc_id": example.get("doc_id", ""),
                    "doc_label": str(example.get("doc_label", "") or ""),
                    "context": context,
                }
            )
    return rows


def _normalize_entity_rows(items: Iterable[Dict[str, Any]], *, selected_entities: set[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in items or []:
        raw = dict(item or {})
        entity = str(raw.get("entity", "") or raw.get("expression", "") or "").strip()
        if not entity:
            continue
        replacement = str(raw.get("replacement", "") or entity.replace(" ", "_")).strip()
        rows.append(
            {
                "entity": entity,
                "replacement": replacement,
                "entity_type": str(raw.get("entity_type", "unknown") or "unknown"),
                "frequency": int(raw.get("frequency", 0) or 0),
                "doc_count": int(raw.get("doc_count", 0) or 0),
                "score": float(raw.get("score", raw.get("is_norm", 0.0)) or 0.0),
                "selected": "true" if entity in selected_entities else "false",
            }
        )
    return rows


def _entity_context_rows(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for item in items or []:
        entity = str((item or {}).get("entity", "") or "").strip()
        if not entity:
            continue
        examples = (item or {}).get("context_examples", [])
        if not isinstance(examples, list):
            continue
        for example in examples:
            if not isinstance(example, dict):
                continue
            context = str(example.get("context", "") or "").strip()
            if not context:
                continue
            rows.append(
                {
                    "entity": entity,
                    "doc_id": example.get("doc_id", ""),
                    "doc_label": str(example.get("doc_label", "") or ""),
                    "context": context,
                }
            )
    return rows


def write_corpus_preparation_audit(
    output_dir: Path,
    *,
    source_paths: Sequence[Path],
    options: Dict[str, Any],
    candidates: Sequence[Dict[str, Any]],
    selected: Sequence[Dict[str, Any]],
    diagnostics: Dict[str, Any],
    pipeline_hash: str,
    entity_candidates: Sequence[Dict[str, Any]] | None = None,
    selected_entities: Sequence[Dict[str, Any]] | None = None,
    version: str = "1.0.9",
) -> Dict[str, Path]:
    """Write CSV/JSON audit artifacts when multiword detection was used."""

    has_entities = bool((options or {}).get("detect_entities", False)) or bool(entity_candidates) or bool(selected_entities)
    if not bool((options or {}).get("detect_bigrams", False)) and not candidates and not selected and not has_entities:
        return {}

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_expressions = {
        str(item.get("expression", "") or "").strip()
        for item in selected or []
        if str(item.get("expression", "") or "").strip()
    }
    candidate_rows = _normalize_rows(candidates or [], selected_expressions=selected_expressions)
    decision_rows = _normalize_rows(selected or [], selected_expressions=selected_expressions)
    context_rows = _multiword_context_rows(candidates or [])

    candidates_path = output_dir / "multiword_candidates.csv"
    decisions_path = output_dir / "multiword_decisions.csv"
    contexts_path = output_dir / "multiword_contexts.csv"
    summary_path = output_dir / "corpus_preparation_summary.json"

    _write_csv(candidates_path, candidate_rows)
    _write_csv(decisions_path, decision_rows)
    _write_csv(contexts_path, context_rows, CONTEXT_FIELDS)

    paths: Dict[str, Path] = {
        "multiword_candidates_csv": candidates_path,
        "multiword_decisions_csv": decisions_path,
        "multiword_contexts_csv": contexts_path,
        "corpus_preparation_summary_json": summary_path,
    }

    selected_entity_names = {
        str(item.get("entity", "") or "").strip()
        for item in selected_entities or []
        if str(item.get("entity", "") or "").strip()
    }
    entity_candidate_rows = _normalize_entity_rows(entity_candidates or [], selected_entities=selected_entity_names)
    entity_decision_rows = _normalize_entity_rows(selected_entities or [], selected_entities=selected_entity_names)
    entity_context_rows = _entity_context_rows(entity_candidates or [])
    if has_entities:
        entity_candidates_path = output_dir / "entity_candidates.csv"
        entity_decisions_path = output_dir / "entity_decisions.csv"
        entity_contexts_path = output_dir / "entity_contexts.csv"
        _write_csv(entity_candidates_path, entity_candidate_rows, ENTITY_FIELDS)
        _write_csv(entity_decisions_path, entity_decision_rows, ENTITY_FIELDS)
        _write_csv(entity_contexts_path, entity_context_rows, ENTITY_CONTEXT_FIELDS)
        paths.update(
            {
                "entity_candidates_csv": entity_candidates_path,
                "entity_decisions_csv": entity_decisions_path,
                "entity_contexts_csv": entity_contexts_path,
            }
        )

    summary = {
        "version": version,
        "source_paths": [str(Path(path)) for path in source_paths or []],
        "options": dict(options or {}),
        "candidate_count": len(candidate_rows),
        "selected_count": len(decision_rows),
        "entity_candidate_count": len(entity_candidate_rows),
        "entity_selected_count": len(entity_decision_rows),
        "prepared_timestamp": datetime.now(timezone.utc).isoformat(),
        "pipeline_hash": str(pipeline_hash or ""),
        "diagnostics": dict(diagnostics or {}),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return paths
