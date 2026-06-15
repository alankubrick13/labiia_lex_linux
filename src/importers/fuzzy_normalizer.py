"""
FuzzyNormalizer - Normaliza variações ortográficas no corpus.
=============================================================
Implementa os 3 algoritmos de clustering do OpenRefine:

  1. Fingerprint       — normaliza e ordena tokens, agrupa idênticos
  2. N-gram Fingerprint — usa n-gramas de caracteres para fuzzy matching
  3. Levenshtein       — agrupa palavras com distância de edição <= N

Nenhum código foi copiado do OpenRefine (Apache 2.0); apenas os
algoritmos foram reimplementados em Python a partir da documentação
pública: https://openrefine.org/docs/manual/cellediting#cluster-and-edit

Uso típico:
    normalizer = FuzzyNormalizer(corpus_text)
    clusters = normalizer.cluster_fingerprint()
    # clusters = [FuzzyCluster(canonical='democracia', variants=['Democracia','democrácia',...]), ...]
    corpus_corrigido = normalizer.apply_clusters(clusters, corpus_text)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from ..utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FuzzyCluster:
    """
    Um grupo de formas que provavelmente representam a mesma palavra.

    Attributes:
        canonical:  Forma escolhida como referência (mais frequente por padrão).
        variants:   Todas as formas encontradas no corpus (incluindo canonical).
        frequency:  Frequência total somada de todas as variantes.
        source:     Algoritmo que gerou o cluster ('fingerprint'|'ngram'|'levenshtein').
    """
    canonical: str
    variants: List[str]
    frequency: int = 0
    source: str = "fingerprint"

    def __post_init__(self) -> None:
        if self.canonical not in self.variants:
            self.variants = [self.canonical] + list(self.variants)

    @property
    def size(self) -> int:
        return len(self.variants)


@dataclass
class NormalizationResult:
    """Resultado de uma normalização aplicada ao corpus."""
    original_text: str
    normalized_text: str
    clusters_applied: List[FuzzyCluster] = field(default_factory=list)
    replacements: int = 0
    tokens_before: int = 0
    tokens_after: int = 0

    @property
    def reduction_pct(self) -> float:
        if self.tokens_before == 0:
            return 0.0
        return round((1 - self.tokens_after / self.tokens_before) * 100, 2)


# ---------------------------------------------------------------------------
# Funções utilitárias (puras, sem side-effects)
# ---------------------------------------------------------------------------

def _fold(text: str) -> str:
    """
    Remove acentos e converte para minúsculas.
    Equivalente ao 'accent folding' do OpenRefine.
    """
    nfd = unicodedata.normalize("NFD", str(text or ""))
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()


def fingerprint(word: str) -> str:
    """
    Cria fingerprint para agrupamento, estilo OpenRefine Fingerprint:
      1. Strip + lowercase + remover acentos
      2. Remover pontuação e caracteres não-alfanuméricos
      3. Dividir por espaço
      4. Ordenar tokens únicos
      5. Re-juntar com espaço

    >>> fingerprint("Política Pública") == fingerprint("politica publica")
    True
    """
    folded = _fold(word)
    cleaned = re.sub(r"[^a-z0-9\s]", " ", folded)
    tokens = sorted(set(cleaned.split()))
    return " ".join(tokens)


def ngram_fingerprint(word: str, n: int = 2) -> str:
    """
    Cria n-gram fingerprint, estilo OpenRefine:
      1. Fingerprint simples (sem espaços)
      2. Gera todos os n-gramas de caracteres
      3. Ordena e une sem separador

    >>> ngram_fingerprint("democracia") != ngram_fingerprint("democrático")
    True
    """
    base = fingerprint(word).replace(" ", "")
    if len(base) < n:
        return base
    grams = sorted(set(base[i:i + n] for i in range(len(base) - n + 1)))
    return "".join(grams)


def levenshtein_distance(a: str, b: str) -> int:
    """
    Distância de Levenshtein entre duas strings.
    Implementação DP O(m*n), sem dependências externas.
    """
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    m, n = len(a), len(b)
    # Apenas 2 linhas necessárias (otimização de memória)
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,       # delete
                curr[j - 1] + 1,   # insert
                prev[j - 1] + cost # replace
            )
        prev, curr = curr, [0] * (n + 1)

    return prev[n]


# ---------------------------------------------------------------------------
# Classe principal
# ---------------------------------------------------------------------------

class FuzzyNormalizer:
    """
    Normaliza variações ortográficas num corpus de texto.

    Implementa os algoritmos de clustering do OpenRefine em Python puro,
    adaptados para corpora IRaMuTeQ (preserva linhas de comando ****).

    Parâmetros:
        min_word_length: Palavras menores que isso são ignoradas (default=4).
        min_frequency:   Palavras com freq < isso são ignoradas (default=2).
        max_vocab_size:  Limita o vocabulário para performance (default=50000).
    """

    _COMMAND_LINE_PATTERN = re.compile(r"^\*{4}", re.MULTILINE)
    _WORD_PATTERN = re.compile(r"\b[a-záéíóúàâêôãõüçñ][a-záéíóúàâêôãõüçñ_-]{2,}\b",
                               re.IGNORECASE | re.UNICODE)

    def __init__(
        self,
        text: str,
        min_word_length: int = 4,
        min_frequency: int = 2,
        max_vocab_size: int = 50_000,
    ) -> None:
        self._text = text
        self.min_word_length = max(2, min_word_length)
        self.min_frequency = max(1, min_frequency)
        self.max_vocab_size = max(100, max_vocab_size)

        self._vocab: Dict[str, int] = {}   # word → frequency
        self._build_vocab()

    # ------------------------------------------------------------------
    # Construcción do vocabulário
    # ------------------------------------------------------------------

    def _is_command_line(self, line: str) -> bool:
        return line.strip().startswith("****")

    def _build_vocab(self) -> None:
        """Extrai vocabulário ignorando linhas de comando IRaMuTeQ."""
        freq: Dict[str, int] = {}
        for line in self._text.splitlines():
            if self._is_command_line(line):
                continue
            for match in self._WORD_PATTERN.finditer(line):
                word = match.group(0)
                if len(word) >= self.min_word_length:
                    freq[word] = freq.get(word, 0) + 1

        # Filtrar por frequência mínima e limitar tamanho
        filtered = {
            w: f for w, f in freq.items()
            if f >= self.min_frequency
        }
        # Ordenar por frequência decrescente e limitar
        sorted_items = sorted(filtered.items(), key=lambda x: -x[1])
        self._vocab = dict(sorted_items[:self.max_vocab_size])
        log.debug("FuzzyNormalizer: vocabulário com %d formas", len(self._vocab))

    # ------------------------------------------------------------------
    # Algoritmo 1: Fingerprint Clustering
    # ------------------------------------------------------------------

    def cluster_fingerprint(self) -> List[FuzzyCluster]:
        """
        Agrupa palavras com o mesmo fingerprint (estilo OpenRefine Fingerprint).

        Muito rápido — O(n). Captura:
          - Maiúsculas/minúsculas: Democracia / democracia
          - Variações de acentuação: democrácia / democracia
          - Anagramas de tokens: "pública política" / "política pública"
        """
        groups: Dict[str, List[str]] = {}
        for word in self._vocab:
            fp = fingerprint(word)
            if fp:
                groups.setdefault(fp, []).append(word)

        return self._build_clusters(groups, source="fingerprint")

    # ------------------------------------------------------------------
    # Algoritmo 2: N-gram Fingerprint Clustering
    # ------------------------------------------------------------------

    def cluster_ngram(self, n: int = 2) -> List[FuzzyCluster]:
        """
        Agrupa palavras com o mesmo n-gram fingerprint (estilo OpenRefine N-gram).

        Mais tolerante a erros de digitação internos que o fingerprint simples.
        Captura:
          - Erros de digitação: demcracia / democracia
          - Variações internas: democrasy / democracia (n=2 bigramas)

        Args:
            n: Tamanho dos n-gramas de caracteres (default=2).
        """
        groups: Dict[str, List[str]] = {}
        for word in self._vocab:
            fp = ngram_fingerprint(word, n=n)
            if fp:
                groups.setdefault(fp, []).append(word)

        return self._build_clusters(groups, source=f"ngram{n}")

    # ------------------------------------------------------------------
    # Algoritmo 3: Levenshtein Clustering
    # ------------------------------------------------------------------

    def cluster_levenshtein(
        self,
        threshold: int = 1,
        block_size: int = 3,
    ) -> List[FuzzyCluster]:
        """
        Agrupa palavras com distância de edição <= threshold (estilo OpenRefine PPM/Levenshtein).

        Mais lento — O(n²) — mas captura erros de digitação arbitrários.
        Usa blocking por prefixo para melhor performance.

        Args:
            threshold:  Distância máxima de Levenshtein (default=1).
            block_size: Tamanho do prefixo para blocking (default=3).
        """
        words = list(self._vocab.keys())

        # Blocking: agrupa por prefixo folded para limitar comparações
        blocks: Dict[str, List[str]] = {}
        for word in words:
            prefix = _fold(word)[:block_size]
            blocks.setdefault(prefix, []).append(word)

        visited: Set[str] = set()
        clusters: List[FuzzyCluster] = []

        for block_words in blocks.values():
            if len(block_words) < 2:
                continue
            for i, w1 in enumerate(block_words):
                if w1 in visited:
                    continue
                group = [w1]
                for w2 in block_words[i + 1:]:
                    if w2 in visited:
                        continue
                    dist = levenshtein_distance(_fold(w1), _fold(w2))
                    if dist <= threshold:
                        group.append(w2)
                        visited.add(w2)

                if len(group) > 1:
                    visited.add(w1)
                    canonical = max(group, key=lambda w: self._vocab.get(w, 0))
                    total_freq = sum(self._vocab.get(w, 0) for w in group)
                    clusters.append(FuzzyCluster(
                        canonical=canonical,
                        variants=group,
                        frequency=total_freq,
                        source=f"levenshtein{threshold}",
                    ))

        clusters.sort(key=lambda c: -c.frequency)
        log.info("cluster_levenshtein(threshold=%d): %d clusters", threshold, len(clusters))
        return clusters

    # ------------------------------------------------------------------
    # Aplicação dos clusters ao corpus
    # ------------------------------------------------------------------

    def apply_clusters(
        self,
        clusters: List[FuzzyCluster],
        text: Optional[str] = None,
    ) -> NormalizationResult:
        """
        Aplica os clusters ao corpus, substituindo variantes pela forma canônica.

        Preserva linhas de comando IRaMuTeQ (**** *var_xxx).

        Args:
            clusters: Lista de clusters a aplicar.
            text:     Texto a normalizar (default=texto passado no __init__).

        Returns:
            NormalizationResult com o texto normalizado e estatísticas.
        """
        source = text if text is not None else self._text
        if not clusters:
            return NormalizationResult(
                original_text=source,
                normalized_text=source,
            )

        # Constrói mapa: variante → canônica (case-insensitive)
        replacement_map: Dict[str, str] = {}
        clusters_applied: List[FuzzyCluster] = []

        for cluster in clusters:
            canonical = cluster.canonical
            changed = False
            for variant in cluster.variants:
                if variant != canonical:
                    replacement_map[variant] = canonical
                    # Também mapa com folded key para matching case-insensitive
                    replacement_map[variant.lower()] = canonical
                    changed = True
            if changed:
                clusters_applied.append(cluster)

        if not replacement_map:
            return NormalizationResult(
                original_text=source,
                normalized_text=source,
            )

        tokens_before = len(re.findall(r"\b\w+\b", source))
        result_lines: List[str] = []
        total_replacements = 0

        for line in source.splitlines():
            if self._is_command_line(line):
                result_lines.append(line)  # Preserva **** intacto
                continue

            new_line, count = self._replace_in_line(line, replacement_map)
            result_lines.append(new_line)
            total_replacements += count

        normalized = "\n".join(result_lines)
        tokens_after = len(re.findall(r"\b\w+\b", normalized))

        log.info(
            "FuzzyNormalizer.apply_clusters: %d substituições, %d clusters aplicados",
            total_replacements,
            len(clusters_applied),
        )

        return NormalizationResult(
            original_text=source,
            normalized_text=normalized,
            clusters_applied=clusters_applied,
            replacements=total_replacements,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
        )

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _build_clusters(
        self,
        groups: Dict[str, List[str]],
        source: str,
    ) -> List[FuzzyCluster]:
        """Constrói lista de FuzzyCluster a partir de grupos por chave."""
        clusters: List[FuzzyCluster] = []
        for _key, variants in groups.items():
            if len(variants) < 2:
                continue  # Nenhuma variação → não é um cluster
            canonical = max(variants, key=lambda w: self._vocab.get(w, 0))
            total_freq = sum(self._vocab.get(w, 0) for w in variants)
            clusters.append(FuzzyCluster(
                canonical=canonical,
                variants=variants,
                frequency=total_freq,
                source=source,
            ))
        clusters.sort(key=lambda c: -c.frequency)
        log.info("cluster_%s: %d clusters de variações", source, len(clusters))
        return clusters

    @staticmethod
    def _replace_in_line(line: str, repl_map: Dict[str, str]) -> Tuple[str, int]:
        """
        Substitui variantes na linha usando fronteiras de palavra.
        Preserva o case da forma canônica.
        """
        count = 0

        def _sub(m: re.Match) -> str:
            nonlocal count
            word = m.group(0)
            canonical = repl_map.get(word) or repl_map.get(word.lower())
            if canonical and canonical != word:
                count += 1
                return canonical
            return word

        return re.sub(r"\b\w[\w_-]*\b", _sub, line), count

    # ------------------------------------------------------------------
    # Utilitários públicos estáticos (para uso em testes ou UI)
    # ------------------------------------------------------------------

    @staticmethod
    def fingerprint(word: str) -> str:
        """API pública para o fingerprint de uma palavra."""
        return fingerprint(word)

    @staticmethod
    def ngram_fingerprint(word: str, n: int = 2) -> str:
        """API pública para o n-gram fingerprint."""
        return ngram_fingerprint(word, n)

    @staticmethod
    def levenshtein_distance(a: str, b: str) -> int:
        """API pública para a distância de Levenshtein."""
        return levenshtein_distance(a, b)

    def get_vocab(self) -> Dict[str, int]:
        """Retorna o vocabulário extraído do corpus."""
        return dict(self._vocab)

    def get_stats(self) -> Dict[str, int]:
        """Retorna estatísticas básicas do vocabulário."""
        return {
            "vocab_size": len(self._vocab),
            "min_frequency": self.min_frequency,
            "min_word_length": self.min_word_length,
            "total_tokens": sum(self._vocab.values()),
        }
