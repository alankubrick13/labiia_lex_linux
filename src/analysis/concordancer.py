"""Concordancer (KWIC) analysis for lexical search in corpus UCEs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Pattern

from ..core.corpus import Corpus


@dataclass
class ConcordanceContext:
    """One KWIC concordance hit."""

    left: str
    keyword: str
    right: str
    metadata: Dict[str, str]
    uce_id: int
    uci_id: int
    full_text: str


@dataclass
class ConcordanceResult:
    """Concordance search result set."""

    query: str
    occurrences: int
    contexts: List[ConcordanceContext] = field(default_factory=list)


class ConcordancerError(Exception):
    """Friendly error for concordance operations."""

    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class Concordancer:
    """Word/regex concordance search over corpus UCE texts."""

    def __init__(self, corpus: Corpus):
        self.corpus = corpus

    def search(self, word: str, context_size: int = 50) -> ConcordanceResult:
        """Search exact word (case-insensitive) with KWIC context."""
        query = (word or "").strip()
        if not query:
            raise ConcordancerError(
                what="Busca vazia.",
                why="Nenhuma palavra foi informada para a concordancia.",
                how="Digite uma palavra e execute a busca novamente.",
            )
        if context_size < 0:
            raise ConcordancerError(
                what="Tamanho de contexto invalido.",
                why="O numero de caracteres de contexto nao pode ser negativo.",
                how="Use um valor de contexto maior ou igual a zero.",
            )

        pattern = re.compile(rf"\b{re.escape(query)}\b", flags=re.IGNORECASE | re.UNICODE)
        return self._search_pattern(pattern, query, context_size)

    def search_regex(self, pattern: str, context_size: int = 50) -> ConcordanceResult:
        """Search regex pattern (case-insensitive) with KWIC context."""
        query = (pattern or "").strip()
        if not query:
            raise ConcordancerError(
                what="Expressao regular vazia.",
                why="Nenhum padrao foi informado para a busca.",
                how="Digite uma expressao regular valida e tente novamente.",
            )
        if context_size < 0:
            raise ConcordancerError(
                what="Tamanho de contexto invalido.",
                why="O numero de caracteres de contexto nao pode ser negativo.",
                how="Use um valor de contexto maior ou igual a zero.",
            )

        try:
            compiled = re.compile(query, flags=re.IGNORECASE | re.UNICODE)
        except re.error as exc:
            raise ConcordancerError(
                what="Expressao regular invalida.",
                why=str(exc),
                how="Corrija o padrao regex (ex.: fechar parenteses e colchetes) e tente novamente.",
            ) from exc

        return self._search_pattern(compiled, query, context_size)

    def get_word_distribution(self, word: str) -> Dict[str, int]:
        """
        Return occurrence distribution by metadata token.

        Output keys follow IRaMuTeQ metadata format without leading '*',
        for example: 'grupo_a', 'sexo_f'.
        """
        query = (word or "").strip()
        if not query:
            return {}

        pattern = re.compile(rf"\b{re.escape(query)}\b", flags=re.IGNORECASE | re.UNICODE)
        distribution: Dict[str, int] = {}

        iduces = self.corpus.make_iduces()
        for uce_id, text in self.corpus.get_uces():
            matches = list(pattern.finditer(text))
            if not matches:
                continue

            uce = iduces.get(uce_id)
            if uce is None:
                continue
            uci = self.corpus.get_uci(uce.uci)
            metadata = self._metadata_from_uci(uci.etoiles if uci else [])
            if not metadata:
                metadata = {"sem_metadata": ""}

            match_count = len(matches)
            for key, value in metadata.items():
                token = f"{key}_{value}".strip("_")
                distribution[token] = distribution.get(token, 0) + match_count

        return dict(sorted(distribution.items(), key=lambda item: item[1], reverse=True))

    def _search_pattern(
        self,
        pattern: Pattern[str],
        query_label: str,
        context_size: int,
    ) -> ConcordanceResult:
        contexts: List[ConcordanceContext] = []
        iduces = self.corpus.make_iduces()

        for uce_id, text in self.corpus.get_uces():
            if not text:
                continue

            uce = iduces.get(uce_id)
            if uce is None:
                continue
            uci_id = uce.uci
            uci = self.corpus.get_uci(uci_id)
            metadata = self._metadata_from_uci(uci.etoiles if uci else [])

            for match in pattern.finditer(text):
                start, end = match.span()
                left_raw = text[max(0, start - context_size) : start]
                right_raw = text[end : min(len(text), end + context_size)]

                left = self._normalize_context(left_raw, prefix_ellipsis=(start - context_size > 0))
                right = self._normalize_context(right_raw, suffix_ellipsis=(end + context_size < len(text)))

                contexts.append(
                    ConcordanceContext(
                        left=left,
                        keyword=match.group(0),
                        right=right,
                        metadata=metadata,
                        uce_id=uce_id,
                        uci_id=uci_id,
                        full_text=text,
                    )
                )

        return ConcordanceResult(
            query=query_label,
            occurrences=len(contexts),
            contexts=contexts,
        )

    @staticmethod
    def _normalize_context(
        text: str,
        prefix_ellipsis: bool = False,
        suffix_ellipsis: bool = False,
    ) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if prefix_ellipsis and cleaned:
            cleaned = f"... {cleaned}"
        if suffix_ellipsis and cleaned:
            cleaned = f"{cleaned} ..."
        return cleaned

    @staticmethod
    def _metadata_from_uci(tokens: List[str]) -> Dict[str, str]:
        metadata: Dict[str, str] = {}
        for token in tokens[1:]:
            raw = token.strip()
            if not raw.startswith("*"):
                continue
            raw = raw[1:]
            if "_" in raw:
                key, value = raw.split("_", 1)
            else:
                key, value = raw, ""
            metadata[key] = value
        return metadata
