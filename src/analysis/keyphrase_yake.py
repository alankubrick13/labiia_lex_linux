"""
Servico de extracao de palavras-chave — backend YAKE.

Usa ``yake.KeywordExtractor`` para extracao estatistica de keyphrases,
sem depender de listas de stopwords.

Pertence a ``src/analysis`` — NAO importa ``src/ui``.
"""

from __future__ import annotations

import logging
import re
from typing import List, Sequence

from src.core.stopword_policy import is_stopword_like, is_visual_content_term

from .semantic_contracts import KeyphraseCandidate, SemanticAnalysisError

log = logging.getLogger(__name__)

_CONVERSATIONAL_SINGLE_TOKEN_NOISE = {
    "acho",
    "ai",
    "aí",
    "assim",
    "daí",
    "dai",
    "entao",
    "então",
    "enfim",
    "eu",
    "gente",
    "ela",
    "ele",
    "eles",
    "elas",
    "isso",
    "isto",
    "né",
    "ne",
    "nos",
    "nós",
    "que",
    "pra",
    "pro",
    "pras",
    "pros",
    "quem",
    "tipo",
    "tudo",
    "voce",
    "você",
    "vocês",
    "voces",
}
_INTERACTION_ROLE_TOKENS = {
    "entrevistador",
    "entrevistadora",
    "entrevistado",
    "entrevistada",
    "mediador",
    "mediadora",
    "pesquisador",
    "pesquisadora",
}
_MULTIWORD_NOISE = {
    "a gente",
}


def extract_ranked_keyphrases(
    texts: Sequence[str],
    *,
    min_tokens: int = 1,
    max_tokens: int = 3,
    min_freq: int = 1,
    top_n: int = 50,
    dedup_threshold: float = 0.7,
    language: str = "pt",
) -> List[KeyphraseCandidate]:
    """Extrai keyphrases via YAKE e retorna KeyphraseCandidates ranqueados.

    Parameters
    ----------
    texts:
        Lista de textos (um por documento/UCE).
    min_tokens:
        Minimo de tokens por frase-chave.
    max_tokens:
        Maximo de tokens por frase-chave.
    min_freq:
        Frequencia minima da frase no corpus para inclusao.
    top_n:
        Numero maximo de keyphrases retornadas.
    dedup_threshold:
        Limiar de deduplicacao YAKE (0-1; menor = mais agressivo).
    language:
        Codigo de idioma para YAKE (ex: "pt", "en").

    Returns
    -------
    List[KeyphraseCandidate]
        Keyphrases ranqueadas (maior score = mais relevante).

    Raises
    ------
    SemanticAnalysisError
        Se o yake nao esta instalado ou o corpus esta vazio.
    """
    try:
        import yake
    except ImportError as exc:
        raise SemanticAnalysisError(
            "yake não encontrado.",
            "A biblioteca yake não está instalada.",
            "Execute: pip install yake",
        ) from exc

    # Concatenar todos os textos (YAKE e single-document)
    full_text = "\n".join(str(t) for t in texts if t)
    if not full_text.strip():
        raise SemanticAnalysisError(
            "Corpus vazio.",
            "Nenhum texto para extrair palavras-chave.",
            "Verifique se o corpus possui texto suficiente.",
        )

    kw = yake.KeywordExtractor(
        lan=language,
        n=min(3, max(1, int(max_tokens or 3))),
        dedupLim=dedup_threshold,
        dedupFunc="seqm",
        windowsSize=2,
        top=top_n * 3,  # extrair mais para compensar filtros pos
    )
    raw: list[tuple[str, float]] = kw.extract_keywords(full_text)

    if not raw:
        log.warning("YAKE nao extraiu nenhuma keyword do corpus.")
        return []

    # Pre-computar para contagem de frequencia
    texts_lower = [t.lower() for t in texts]
    all_lower = " ".join(texts_lower)

    candidates: List[KeyphraseCandidate] = []
    seen: set = set()

    for phrase, yake_score in raw:
        norm = phrase.lower().strip()
        if norm in seen:
            continue
        seen.add(norm)

        if _is_noise_keyphrase(norm):
            continue

        tokens = norm.split()
        if len(tokens) < min_tokens:
            continue
        if len(tokens) > 3:
            continue

        # Frequencia da frase no corpus
        freq = _count_phrase(all_lower, norm)
        if freq < min_freq:
            continue

        # Doc count
        doc_count = sum(1 for t in texts_lower if norm in t)

        # YAKE normalmente retorna score positivo menor=melhor. Em alguns
        # corpora grandes vimos valores <= 0; use magnitude para manter a
        # relevancia sempre positiva e plotavel.
        raw_score = float(yake_score)
        rank_score = abs(raw_score) if raw_score <= 0 else raw_score
        relevance = 1.0 / max(rank_score, 1e-6)

        candidates.append(KeyphraseCandidate(
            phrase=phrase,
            normalized_phrase=norm,
            score=round(relevance, 4),
            raw_yake_score=raw_score,
            frequency=freq,
            degree=0,
            doc_count=doc_count,
            mean_position=0.0,
        ))

    candidates.sort(key=lambda c: (-c.score, -c.frequency))
    return candidates[:top_n]


def _count_phrase(haystack: str, needle: str) -> int:
    """Conta ocorrencias nao-sobrepostas de needle em haystack."""
    count = 0
    start = 0
    while True:
        pos = haystack.find(needle, start)
        if pos == -1:
            break
        count += 1
        start = pos + len(needle)
    return max(count, 1)  # pelo menos 1 (foi extraido pelo YAKE)


def _is_noise_keyphrase(phrase: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(phrase or "").strip().lower())
    if not normalized:
        return True
    if normalized in _MULTIWORD_NOISE:
        return True

    tokens = [token for token in normalized.split() if token]
    if not tokens:
        return True
    if len(tokens) > 3:
        return True

    if len(tokens) == 1 and (
        tokens[0] in _CONVERSATIONAL_SINGLE_TOKEN_NOISE
        or tokens[0] in _INTERACTION_ROLE_TOKENS
    ):
        return True

    if any(token in _INTERACTION_ROLE_TOKENS for token in tokens):
        return True

    if all(token in _CONVERSATIONAL_SINGLE_TOKEN_NOISE for token in tokens):
        return True

    if any(not is_visual_content_term(token) for token in (tokens[0], tokens[-1])):
        return True

    stopword_like = sum(1 for token in tokens if is_stopword_like(token))
    if stopword_like / max(1, len(tokens)) > 0.4:
        return True

    content_tokens = [token for token in tokens if is_visual_content_term(token)]
    if len(content_tokens) < max(1, min(2, len(tokens))):
        return True

    if len(normalized) > 70:
        return True

    return False
