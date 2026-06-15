"""Optional semantic/lexical resource loading for automatic CCA."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from src.importers.bigram_compounds import _fold_token

_TOKEN_RE = re.compile(r"[a-zA-Zà-öø-ÿ][a-zA-Zà-öø-ÿ0-9_-]{1,}")
_TTL_LABEL_RE = re.compile(
    r'^\s*([^\s]+)\s+[^\s]*(?:label|writtenForm)\s+"([^"]+)"@pt(?:-[a-z]+)?',
    re.IGNORECASE,
)
_SPLIT_RE = re.compile(r"[\t;,|]")


def _normalize_token(value: str, min_word_length: int) -> str:
    folded = _fold_token(value)
    if not folded:
        return ""
    match = _TOKEN_RE.search(folded)
    if not match:
        return ""
    token = match.group(0).strip("_-")
    if len(token) < int(min_word_length):
        return ""
    if not re.search(r"[a-z]", token):
        return ""
    return token


def _pair_key(left: str, right: str) -> Tuple[str, str]:
    return (left, right) if left <= right else (right, left)


@dataclass
class SemanticResourceBundle:
    """Aggregated lexical resources consumed by the CCA auto engine."""

    lemma_by_form: Dict[str, str] = field(default_factory=dict)
    semantic_pairs: Set[Tuple[str, str]] = field(default_factory=set)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


class SemanticResourceLoader:
    """
    Best-effort loader for optional external lexical resources.

    Accepted resource styles:
    - plain pair files (`word<TAB>word`)
    - MorphoBr / DELAF-like morphology lexicons (`form,lemma.POS+...`)
    - PortiLexicon-UD TSV variants (form/lemma columns)
    - OpenWordNet TTL labels grouped by synset subject
    - thesaurus rows (`word;synonym;synonym`)
    """

    SUPPORTED_SUFFIXES = {".txt", ".tsv", ".csv", ".ttl"}

    def __init__(
        self,
        min_word_length: int = 3,
        max_pairs: int = 380_000,
        max_file_bytes: int = 210 * 1024 * 1024,
        max_terms_per_synset: int = 18,
    ) -> None:
        self.min_word_length = max(2, int(min_word_length or 3))
        self.max_pairs = max(10_000, int(max_pairs or 380_000))
        self.max_file_bytes = max(1024, int(max_file_bytes or (210 * 1024 * 1024)))
        self.max_terms_per_synset = max(2, int(max_terms_per_synset or 18))

        self._lemma_by_form: Dict[str, str] = {}
        self._semantic_pairs: Set[Tuple[str, str]] = set()
        self._pairs_budget = self.max_pairs
        self._source_counter: Counter[str] = Counter()
        self._source_meta: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"files": 0, "lemma_entries": 0, "pairs": 0, "lines": 0}
        )
        self._errors: List[str] = []
        self._files_scanned = 0
        self._files_used = 0

    def load_many(self, roots: Iterable[Path]) -> SemanticResourceBundle:
        for root in roots:
            self.load(root)
        return self.bundle

    def load(self, root: Path) -> SemanticResourceBundle:
        root_path = Path(root)
        if not root_path.exists():
            return self.bundle

        for path in sorted(root_path.rglob("*")):
            if not path.is_file():
                continue
            self._files_scanned += 1
            suffix = path.suffix.lower().strip()
            if suffix not in self.SUPPORTED_SUFFIXES:
                continue
            if path.stat().st_size > self.max_file_bytes:
                self._errors.append(f"Arquivo ignorado por tamanho: {path}")
                continue
            try:
                self._parse_file(path)
                self._files_used += 1
            except Exception as exc:
                self._errors.append(f"{path}: {exc}")
        return self.bundle

    @property
    def bundle(self) -> SemanticResourceBundle:
        diagnostics = {
            "files_scanned": int(self._files_scanned),
            "files_used": int(self._files_used),
            "lemma_entries_loaded": len(self._lemma_by_form),
            "semantic_pairs_loaded": len(self._semantic_pairs),
            "source_breakdown": {k: dict(v) for k, v in self._source_meta.items()},
            "errors": list(self._errors[-30:]),
            "pair_budget_remaining": int(self._pairs_budget),
        }
        return SemanticResourceBundle(
            lemma_by_form=dict(self._lemma_by_form),
            semantic_pairs=set(self._semantic_pairs),
            diagnostics=diagnostics,
        )

    def _parse_file(self, path: Path) -> None:
        key = str(path.name).lower()
        source = "generic_pairs"
        if "morphobr" in key or "delaf" in key:
            source = "morphology"
        elif "portilexicon" in key or "ud" in key:
            source = "portilexicon_ud"
        elif "openwordnet" in key or "own-pt" in key or path.suffix.lower() == ".ttl":
            source = "openwordnet_like"
        elif "tep" in key or "sinon" in key:
            source = "thesaurus"
        self._source_counter[source] += 1
        self._source_meta[source]["files"] += 1

        if source == "openwordnet_like":
            self._parse_openwordnet_like(path, source)
            return
        if source in {"morphology", "portilexicon_ud"}:
            self._parse_morphology_like(path, source)
            return
        if source == "thesaurus":
            self._parse_thesaurus_like(path, source)
            return
        self._parse_pair_file(path, source)

    def _add_lemma(self, form: str, lemma: str, source: str) -> None:
        left = _normalize_token(form, self.min_word_length)
        right = _normalize_token(lemma, self.min_word_length)
        if not left or not right:
            return
        if left in self._lemma_by_form:
            return
        self._lemma_by_form[left] = right
        self._source_meta[source]["lemma_entries"] += 1

    def _add_pair(self, left: str, right: str, source: str) -> None:
        if self._pairs_budget <= 0:
            return
        token_a = _normalize_token(left, self.min_word_length)
        token_b = _normalize_token(right, self.min_word_length)
        if not token_a or not token_b or token_a == token_b:
            return
        pair = _pair_key(token_a, token_b)
        if pair in self._semantic_pairs:
            return
        self._semantic_pairs.add(pair)
        self._pairs_budget -= 1
        self._source_meta[source]["pairs"] += 1

    def _iter_lines(self, path: Path) -> Iterable[str]:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                yield raw.rstrip("\n")

    def _parse_pair_file(self, path: Path, source: str) -> None:
        for line in self._iter_lines(path):
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            self._source_meta[source]["lines"] += 1
            parts = [part.strip() for part in _SPLIT_RE.split(clean) if part.strip()]
            if len(parts) < 2:
                continue
            self._add_pair(parts[0], parts[1], source)

    def _parse_thesaurus_like(self, path: Path, source: str) -> None:
        for line in self._iter_lines(path):
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            self._source_meta[source]["lines"] += 1
            parts = [part.strip() for part in _SPLIT_RE.split(clean) if part.strip()]
            if len(parts) < 2:
                continue
            base = parts[0]
            terms: List[str] = []
            seen: Set[str] = set()
            for raw in parts[: self.max_terms_per_synset]:
                token = _normalize_token(raw, self.min_word_length)
                if token and token not in seen:
                    terms.append(token)
                    seen.add(token)
            if len(terms) < 2:
                continue
            for idx in range(1, len(terms)):
                self._add_pair(base, terms[idx], source)

    def _parse_morphology_like(self, path: Path, source: str) -> None:
        header_indices: Optional[Tuple[int, int]] = None
        for line in self._iter_lines(path):
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            self._source_meta[source]["lines"] += 1
            lowered = clean.lower()
            if header_indices is None and ("lemma" in lowered and "form" in lowered):
                fields = [item.strip().lower() for item in _SPLIT_RE.split(clean)]
                try:
                    form_idx = next(
                        i for i, value in enumerate(fields)
                        if value in {"form", "forma", "token", "word"}
                    )
                    lemma_idx = next(
                        i for i, value in enumerate(fields)
                        if "lemma" in value or value == "lem"
                    )
                    header_indices = (form_idx, lemma_idx)
                    continue
                except StopIteration:
                    header_indices = None

            form = ""
            lemma = ""
            parts = [item.strip() for item in _SPLIT_RE.split(clean)]
            if header_indices and len(parts) > max(header_indices):
                form = parts[header_indices[0]]
                lemma = parts[header_indices[1]]
            elif len(parts) >= 2:
                form = parts[0]
                lemma = parts[1]
            elif "," in clean:
                form, payload = clean.split(",", 1)
                lemma = self._extract_delaf_lemma(payload)
            else:
                continue
            self._add_lemma(form, lemma, source)

    def _extract_delaf_lemma(self, payload: str) -> str:
        segment = payload.strip()
        for marker in [".", "+", ":", "/", " ", "\t"]:
            if marker in segment:
                segment = segment.split(marker, 1)[0]
        token = _normalize_token(segment, self.min_word_length)
        return token or segment

    def _parse_openwordnet_like(self, path: Path, source: str) -> None:
        synset_terms: Dict[str, Set[str]] = defaultdict(set)
        for line in self._iter_lines(path):
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            self._source_meta[source]["lines"] += 1
            match = _TTL_LABEL_RE.match(clean)
            if not match:
                continue
            subject = str(match.group(1) or "").strip()
            if "synset" not in subject.lower():
                continue
            term = _normalize_token(match.group(2), self.min_word_length)
            if not term:
                continue
            terms = synset_terms[subject]
            if len(terms) < self.max_terms_per_synset:
                terms.add(term)

        for terms in synset_terms.values():
            words = sorted(terms)
            if len(words) < 2:
                continue
            for i in range(len(words)):
                for j in range(i + 1, len(words)):
                    self._add_pair(words[i], words[j], source)

