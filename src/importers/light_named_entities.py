"""Conservative named-entity candidates for optional corpus preparation."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Sequence, Tuple

BRIDGE_WORDS = {"da", "de", "do", "das", "dos", "e"}
COMMON_SENTENCE_STARTS = {
    "a",
    "as",
    "o",
    "os",
    "um",
    "uma",
    "hoje",
    "ontem",
    "amanha",
    "quando",
    "como",
    "porque",
    "para",
    "sobre",
    "este",
    "esta",
    "isso",
    "mas",
}
TOKEN_RE = re.compile(r"\b[\wÀ-ÿ][\wÀ-ÿ.-]*\b", re.UNICODE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _iter_document_lines(text: str) -> Iterable[Tuple[int, str, str]]:
    doc_id = 0
    doc_label = "Documento 1"
    saw_marker = False
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("****"):
            saw_marker = True
            doc_id += 1
            marker = line.lstrip("*").strip()
            doc_label = marker or f"Documento {doc_id}"
            continue
        if not saw_marker and doc_id == 0:
            doc_id = 1
        yield doc_id or 1, doc_label, line


def _is_acronym(token: str) -> bool:
    cleaned = re.sub(r"[^A-Za-zÀ-ÿ]", "", str(token or ""))
    return len(cleaned) >= 2 and cleaned.isupper()


def _is_mixed_case_name(token: str) -> bool:
    value = str(token or "")
    letters = [ch for ch in value if ch.isalpha()]
    return len(letters) >= 3 and any(ch.islower() for ch in letters) and any(ch.isupper() for ch in letters[1:])


def _is_capitalized(token: str) -> bool:
    value = str(token or "")
    return len(value) >= 2 and value[0].isupper() and any(ch.islower() for ch in value[1:])


def _entity_type(entity: str) -> str:
    parts = [p for p in str(entity or "").split() if p.lower() not in BRIDGE_WORDS]
    if len(parts) == 1:
        token = parts[0]
        if _is_acronym(token):
            return "acronym"
        if _is_mixed_case_name(token):
            return "mixed_case_name"
        return "proper_name"
    institution_markers = {
        "Tribunal",
        "Federal",
        "Ministerio",
        "Ministério",
        "Universidade",
        "Instituto",
        "Secretaria",
        "Fundacao",
        "Fundação",
        "Banco",
        "Congresso",
    }
    if any(part in institution_markers for part in parts):
        return "institution_or_group"
    return "proper_name"


def _candidate_sequences(sentence: str, max_tokens: int) -> Iterable[str]:
    tokens = [(m.group(0), m.start()) for m in TOKEN_RE.finditer(str(sentence or ""))]
    i = 0
    while i < len(tokens):
        token, start = tokens[i]
        lower = token.lower()
        valid_single = _is_acronym(token) or _is_mixed_case_name(token) or _is_capitalized(token)
        if not valid_single or (start == 0 and lower in COMMON_SENTENCE_STARTS):
            i += 1
            continue

        parts = [token]
        j = i + 1
        while j < len(tokens) and len(parts) < max_tokens:
            next_token = tokens[j][0]
            next_lower = next_token.lower()
            if next_lower in BRIDGE_WORDS:
                if j + 1 < len(tokens):
                    lookahead = tokens[j + 1][0]
                    if _is_capitalized(lookahead) or _is_acronym(lookahead) or _is_mixed_case_name(lookahead):
                        parts.append(next_token)
                        j += 1
                        continue
                break
            if _is_capitalized(next_token) or _is_acronym(next_token) or _is_mixed_case_name(next_token):
                parts.append(next_token)
                j += 1
                continue
            break

        while parts and parts[-1].lower() in BRIDGE_WORDS:
            parts.pop()
        if parts:
            yield " ".join(parts)
            if len(parts) > 1:
                i = j
                continue
        i += 1


def _context(text: str, entities: Sequence[str], max_examples: int) -> Dict[str, Dict[str, Any]]:
    doc_ids: Dict[str, set[int]] = defaultdict(set)
    examples: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    lowered = {entity: entity.lower() for entity in entities}
    for doc_id, doc_label, line in _iter_document_lines(text):
        line_lower = line.lower()
        for entity, entity_lower in lowered.items():
            if entity_lower not in line_lower:
                continue
            doc_ids[entity].add(int(doc_id))
            if len(examples[entity]) < max_examples:
                examples[entity].append(
                    {
                        "doc_id": int(doc_id),
                        "doc_label": str(doc_label or f"Documento {doc_id}"),
                        "context": re.sub(r"\s+", " ", line).strip()[:180],
                    }
                )
    return {
        entity: {"doc_count": len(doc_ids.get(entity, set())), "context_examples": list(examples.get(entity, []))}
        for entity in entities
    }


def extract_light_named_entities(
    text: str,
    *,
    top_n: int = 50,
    min_freq: int = 2,
    max_tokens: int = 6,
    max_examples: int = 3,
) -> List[Dict[str, Any]]:
    """Detect light named entities without external NLP dependencies."""

    top_n = max(1, int(top_n or 50))
    min_freq = max(1, int(min_freq or 2))
    max_tokens = min(6, max(1, int(max_tokens or 6)))
    counts: Counter[str] = Counter()
    canonical: Dict[str, str] = {}

    for _doc_id, _doc_label, line in _iter_document_lines(text):
        for sentence in SENTENCE_SPLIT_RE.split(line):
            for candidate in _candidate_sequences(sentence.strip(), max_tokens=max_tokens):
                if not any(ch.isalpha() for ch in candidate):
                    continue
                key = candidate.lower()
                counts[key] += 1
                canonical.setdefault(key, candidate)

    rows: List[Dict[str, Any]] = []
    for key, frequency in counts.items():
        if frequency < min_freq:
            continue
        entity = canonical[key]
        rows.append(
            {
                "entity": entity,
                "replacement": entity.replace(" ", "_"),
                "entity_type": _entity_type(entity),
                "frequency": int(frequency),
                "doc_count": 0,
                "score": float(frequency),
                "selected_default": len(entity.split()) >= 2 or _is_acronym(entity) or _is_mixed_case_name(entity),
                "context_examples": [],
            }
        )

    rows.sort(key=lambda item: (-int(item["frequency"]), -len(str(item["entity"]).split()), str(item["entity"]).lower()))
    rows = rows[:top_n]
    context_by_entity = _context(text, [str(item["entity"]) for item in rows], max_examples=max_examples)
    max_freq = max((int(item["frequency"]) for item in rows), default=1)
    for row in rows:
        context = context_by_entity.get(str(row["entity"]), {})
        row["doc_count"] = int(context.get("doc_count", 0) or 0)
        row["context_examples"] = list(context.get("context_examples", []) or [])
        row["score"] = round(float(row["frequency"]) / max(1.0, float(max_freq)), 6)
    return rows


def selected_entities_to_multiword_payload(selected: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return selected multi-token entities as payload accepted by the R merge pass."""
    payload: List[Dict[str, Any]] = []
    for item in selected or []:
        entity = str((item or {}).get("entity", "") or "").strip()
        parts = [part for part in entity.split() if part]
        if len(parts) < 2:
            continue
        payload.append(
            {
                "expression": entity,
                "replacement": str((item or {}).get("replacement", "") or entity.replace(" ", "_")).strip(),
                "frequency": int((item or {}).get("frequency", 0) or 0),
                "doc_count": int((item or {}).get("doc_count", 0) or 0),
                "method": "light_named_entity",
            }
        )
    return payload
