"""
CCA - Connected Concept Analysis
=================================
Implementação da metodologia Textometrica (Lindgren & Lundström, 2010):

Fluxo:
  1. Extração de vocabulário filtrado (n palavras mais frequentes)
  2. Codificação temática: usuário agrupa palavras em "Conceitos"
  3. Cálculo de co-ocorrências conceito × conceito (dentro de janela de texto)
  4. Construção de grafo ponderado de conceitos
  5. Exportação para GEXF / relatório / visualização interna

Referência metodológica:
  Lindgren, S. & Lundström, R. (2010). Pirate culture and hacktivist mobilization.
  New Media & Society, 13(6), 999-1018.

Nenhum código foi copiado do Textometrica (licença aberta, mas reimplementado
do zero em Python a partir da documentação pública).
"""

from __future__ import annotations

import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, Iterator, List, Optional, Set, Tuple

import networkx as nx

from ..core.lexicon import (
    Lexicon,
    build_portuguese_stopwords_from_lexicon,
    resolve_lexicon_path,
)
from .semantic_resources import SemanticResourceBundle, SemanticResourceLoader
from ..utils.paths import PathManager
from .community_detection import detect_louvain_partition
from ..utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Tipos auxiliares
# ---------------------------------------------------------------------------

@dataclass
class WordFreq:
    """Palavra com sua frequência e possível atribuição de conceito."""
    word:     str
    freq:     int
    concept:  Optional[str] = None     # None = não atribuída

    def __hash__(self) -> int:
        return hash(self.word)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, WordFreq) and self.word == other.word


@dataclass
class ConceptEdge:
    """Aresta ponderada entre dois conceitos no grafo CCA."""
    source:    str
    target:    str
    weight:    int = 0         # # co-ocorrências na janela

    @property
    def pair(self) -> FrozenSet[str]:
        return frozenset([self.source, self.target])


@dataclass
class CCAResult:
    """Resultado completo de uma análise CCA."""
    concept_map:     Dict[str, List[str]]    # conceito → [palavras]
    word_concepts:   Dict[str, str]          # palavra → conceito
    edges:           List[ConceptEdge]       # grafo de co-ocorrências
    concept_freq:    Dict[str, int]          # freq total de cada conceito
    window_size:     int
    total_windows:   int
    segments_used:   int

    @property
    def nodes(self) -> List[str]:
        return sorted(self.concept_map.keys())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "concept_map": self.concept_map,
            "edges": [
                {"source": e.source, "target": e.target, "weight": e.weight}
                for e in self.edges
            ],
            "concept_freq": self.concept_freq,
            "params": {
                "window_size": self.window_size,
                "total_windows": self.total_windows,
                "segments_used": self.segments_used,
            },
        }


@dataclass
class AutoConceptConfig:
    """Configuração para geração automática de conceitos (CCA híbrida)."""

    top_n: int = 180
    min_freq: int = 2
    window_size: int = 5
    min_edge_weight: int = 2
    min_cluster_size: int = 3
    confidence_threshold: float = 0.80
    max_concepts: int = 15
    resolution: float = 1.0
    seed: int = 42
    adaptive_relaxation: bool = True
    relaxation_steps: int = 2
    relaxed_confidence_floor: float = 0.72
    target_min_concepts: int = 3
    target_min_assigned_words: int = 12
    lemma_bridge_weight: float = 1.0
    orthographic_bridge_weight: float = 0.45
    orthographic_similarity: float = 0.88
    max_orthographic_pairs: int = 420
    external_pair_weight: float = 0.80
    semantic_bonus_weight: float = 0.10
    early_stop_min_modularity: float = 0.18
    early_stop_max_dominance: float = 0.72


@dataclass
class AutoConceptSuggestion:
    """Conceito sugerido automaticamente."""

    name: str
    words: List[str]
    mean_confidence: float
    size: int
    diagnostics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AutoConceptResult:
    """Resultado da sugestão automática de conceitos."""

    suggestions: List[AutoConceptSuggestion]
    unassigned_words: List[str]
    diagnostics: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine principal
# ---------------------------------------------------------------------------

class CCAAnalyzer:
    """
    Engine de Connected Concept Analysis.

    Uso:
        analyzer = CCAAnalyzer(raw_text)
        vocab = analyzer.get_top_words(n=100)
        # usuário codifica palavras em conceitos → concept_map
        result = analyzer.run(concept_map, window_size=10)
    """

    _COMMAND_LINE = re.compile(r"^\s*\*{4}", re.MULTILINE)
    _WORD_RE = re.compile(
        r"\b[a-zA-ZàáâãäéêëíîïóôõöúûüçñÀÁÂÃÄÉÊËÍÎÏÓÔÕÖÚÛÜÇÑ][a-zA-ZàáâãäéêëíîïóôõöúûüçñÀÁÂÃÄÉÊËÍÎÏÓÔÕÖÚÛÜÇÑ_-]{1,}\b"
    )

    # Stopwords mínimas em Português (ampliável)
    _STOPWORDS_PT = frozenset(
        "a de do da dos das e em o os as um uma uns umas para por"
        " com sem que se na no nas nos ou ao à aos às lhe lhes"
        " mais muito como mas também ainda já seu sua seus suas"
        " quando onde porque pois até mesmo bem ser esta este"
        " isso aquilo esse essa isto meu minha nosso nossa eu"
        " ele ela eles elas você voce nós nos me te si entre"
        " desta deste nesta neste essa ser estar foi era".split()
    )
    # Ruído frequente em textos acadêmicos (afiliação, editoração, rodapé).
    _ACADEMIC_NOISE_TOKENS = frozenset(
        {
            "universidade",
            "federal",
            "estadual",
            "santa",
            "catarina",
            "florianopolis",
            "ufsc",
            "usp",
            "ufmg",
            "ufrj",
            "instituto",
            "departamento",
            "faculdade",
            "programa",
            "campus",
            "centro",
            "laboratorio",
            "laboratório",
            "pesquisador",
            "pesquisadora",
            "resumo",
            "abstract",
            "palavraschave",
            "palavraschave",
            "keywords",
            "revista",
            "periodico",
            "periódico",
            "editora",
            "edicao",
            "edição",
            "volume",
            "numero",
            "número",
            "suplemento",
            "issn",
            "doi",
            "orcid",
            "email",
            "http",
            "https",
            "www",
            "com",
            "org",
            "br",
            "jan",
            "fev",
            "mar",
            "abr",
            "mai",
            "jun",
            "jul",
            "ago",
            "set",
            "out",
            "nov",
            "dez",
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        }
    )
    _HARD_NOISE_TOKENS = frozenset(
        {
            "doi",
            "issn",
            "orcid",
            "http",
            "https",
            "www",
            "email",
        }
    )

    def __init__(
        self,
        raw_text: str,
        remove_stopwords: bool = True,
        min_word_length: int = 3,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> None:
        self._raw_text = raw_text
        self._remove_stopwords = remove_stopwords
        self._min_word_length = max(1, min_word_length)
        self._progress_callback = progress_callback
        self._tokens: List[str] = []          # corpus inteiro tokenizado
        self._segments: List[List[str]] = []  # dividido por UCI (****)
        self._freq: Counter = Counter()
        self._capitalized_tokens: Counter[str] = Counter()
        self._auto_stopwords_cache: Optional[Set[str]] = None
        self._auto_lexicon: Optional[Lexicon] = None
        self._auto_lexicon_loaded = False
        self._auto_lexicon_en: Optional[Lexicon] = None
        self._auto_lexicon_en_loaded = False
        self._auto_lemma_cache: Dict[str, str] = {}
        self._auto_external_pairs_cache: Optional[Set[Tuple[str, str]]] = None
        self._auto_semantic_bundle: Optional[SemanticResourceBundle] = None
        self._auto_semantic_loaded = False

        self._tokenize()

    def _emit_progress(self, pct: int, message: str) -> None:
        """Emite progresso do pré-processamento do vocabulário (best effort)."""
        if not self._progress_callback:
            return
        try:
            self._progress_callback(int(max(0, min(100, pct))), str(message or ""))
        except Exception:
            # Progresso nunca pode interromper a análise.
            pass

    # ------------------------------------------------------------------
    # Tokenização
    # ------------------------------------------------------------------

    @staticmethod
    def _fold(text: str) -> str:
        """Lowercase + remove acentos."""
        nfd = unicodedata.normalize("NFD", text)
        return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()

    def _tokenize(self) -> None:
        """Divide o corpus em tokens e segmentos (UCIs)."""
        lines = self._raw_text.splitlines()
        total_lines = max(1, len(lines))
        total_chars = max(1, len(self._raw_text))
        consumed_chars = 0
        last_emit = time.perf_counter()
        self._emit_progress(5, "Inicializando leitura do corpus")
        current_seg: List[str] = []
        for line_idx, line in enumerate(lines, start=1):
            if self._COMMAND_LINE.match(line):
                if current_seg:
                    self._segments.append(current_seg)
                    current_seg = []
                consumed_chars += len(line) + 1
                continue
            for m in self._WORD_RE.finditer(line):
                original_token = m.group(0)
                word = self._fold(original_token)
                if len(word) < self._min_word_length:
                    continue
                if self._remove_stopwords and word in self._STOPWORDS_PT:
                    continue
                current_seg.append(word)
                self._tokens.append(word)
                if str(original_token[:1]).isupper():
                    self._capitalized_tokens[word] += 1
                now = time.perf_counter()
                if now - last_emit >= 0.20:
                    approx_consumed = consumed_chars + int(m.end())
                    ratio = min(1.0, max(0.0, approx_consumed / total_chars))
                    pct = int(5 + (ratio * 85))
                    self._emit_progress(pct, f"Processando corpus ({line_idx}/{total_lines} linhas)")
                    last_emit = now

            consumed_chars += len(line) + 1
            if line_idx % 250 == 0 or line_idx == total_lines:
                ratio = min(1.0, max(0.0, consumed_chars / total_chars))
                pct = int(5 + (ratio * 85))
                self._emit_progress(pct, f"Processando corpus ({line_idx}/{total_lines} linhas)")

        if current_seg:
            self._segments.append(current_seg)

        self._emit_progress(94, "Consolidando frequências do vocabulário")
        self._freq = Counter(self._tokens)
        self._emit_progress(100, "Vocabulário carregado")
        log.debug("CCAAnalyzer: %d tokens, %d segmentos, %d formas únicas",
                  len(self._tokens), len(self._segments), len(self._freq))

    # ------------------------------------------------------------------
    # Vocabulário
    # ------------------------------------------------------------------

    def get_top_words(self, n: int = 120, min_freq: int = 2) -> List[WordFreq]:
        """
        Retorna as N palavras mais frequentes que atendem à freq mínima.

        Args:
            n:        Número máximo de palavras.
            min_freq: Frequência mínima para incluir.

        Returns:
            Lista de WordFreq ordenada por frequência descendente.
        """
        result = [
            WordFreq(word=w, freq=f)
            for w, f in self._freq.most_common()
            if f >= min_freq
        ]
        return result[:n]

    def get_vocab_size(self) -> int:
        return len(self._freq)

    def get_vocab(self) -> Dict[str, int]:
        """Retorna o dicionário completo palavra → frequência."""
        return dict(self._freq)

    # ------------------------------------------------------------------
    # Sugestão automática de conceitos (CCA híbrida)
    # ------------------------------------------------------------------

    def _get_auto_stopwords(self) -> Set[str]:
        """
        Retorna stopwords robustas para auto-conceitos.

        Combina lista mínima local + stopwords derivadas do léxico PT,
        com fallback silencioso para manter robustez em qualquer ambiente.
        """
        if self._auto_stopwords_cache is not None:
            return set(self._auto_stopwords_cache)

        stopwords = set(self._STOPWORDS_PT)
        try:
            lexicon_path = resolve_lexicon_path("portuguese")
            lexicon_stopwords = build_portuguese_stopwords_from_lexicon(str(lexicon_path))
            stopwords.update(lexicon_stopwords)
        except Exception as exc:
            log.warning("Falha ao carregar stopwords do léxico PT para CCA auto: %s", exc)

        self._auto_stopwords_cache = set(stopwords)
        return stopwords

    @staticmethod
    def _sanitize_auto_config(config: AutoConceptConfig) -> AutoConceptConfig:
        """Normaliza limites para evitar parâmetros inválidos."""
        return AutoConceptConfig(
            top_n=max(20, int(config.top_n or 180)),
            min_freq=max(1, int(config.min_freq or 2)),
            window_size=max(2, int(config.window_size or 5)),
            min_edge_weight=max(1, int(config.min_edge_weight or 2)),
            min_cluster_size=max(2, int(config.min_cluster_size or 3)),
            confidence_threshold=min(0.99, max(0.10, float(config.confidence_threshold or 0.80))),
            max_concepts=max(1, int(config.max_concepts or 15)),
            resolution=max(0.1, float(config.resolution or 1.0)),
            seed=int(config.seed or 42),
            adaptive_relaxation=bool(config.adaptive_relaxation),
            relaxation_steps=max(0, min(4, int(config.relaxation_steps or 0))),
            relaxed_confidence_floor=min(
                0.95,
                max(0.55, float(config.relaxed_confidence_floor or 0.72)),
            ),
            target_min_concepts=max(1, int(config.target_min_concepts or 3)),
            target_min_assigned_words=max(2, int(config.target_min_assigned_words or 12)),
            lemma_bridge_weight=max(0.0, float(config.lemma_bridge_weight or 0.0)),
            orthographic_bridge_weight=max(0.0, float(config.orthographic_bridge_weight or 0.0)),
            orthographic_similarity=min(0.99, max(0.60, float(config.orthographic_similarity or 0.88))),
            max_orthographic_pairs=max(0, int(config.max_orthographic_pairs or 0)),
            external_pair_weight=max(0.0, float(config.external_pair_weight or 0.0)),
            semantic_bonus_weight=min(0.40, max(0.0, float(config.semantic_bonus_weight or 0.0))),
            early_stop_min_modularity=min(
                0.95,
                max(-0.20, float(config.early_stop_min_modularity or 0.18)),
            ),
            early_stop_max_dominance=min(
                1.0,
                max(0.25, float(config.early_stop_max_dominance or 0.72)),
            ),
        )

    def _load_auto_lexicon(self) -> Optional[Lexicon]:
        """Carrega léxico PT local (uma vez) para lematização leve."""
        if self._auto_lexicon_loaded:
            return self._auto_lexicon

        self._auto_lexicon_loaded = True
        try:
            path = resolve_lexicon_path("portuguese")
            if not path.exists():
                return None
            lexicon = Lexicon()
            loaded = int(lexicon.load(path))
            if loaded <= 0:
                return None
            self._auto_lexicon = lexicon
            return lexicon
        except Exception as exc:
            log.warning("Falha ao carregar léxico PT para CCA auto: %s", exc)
            return None

    def _load_auto_lexicon_en(self) -> Optional[Lexicon]:
        """Carrega léxico EN local (uma vez) para reduzir ruído em corpus PT."""
        if self._auto_lexicon_en_loaded:
            return self._auto_lexicon_en

        self._auto_lexicon_en_loaded = True
        try:
            path = resolve_lexicon_path("english")
            if not path.exists():
                return None
            lexicon = Lexicon()
            loaded = int(lexicon.load(path))
            if loaded <= 0:
                return None
            self._auto_lexicon_en = lexicon
            return lexicon
        except Exception as exc:
            log.warning("Falha ao carregar léxico EN para CCA auto: %s", exc)
            return None

    def _is_english_dominant_token(self, token: str) -> bool:
        """
        Detecta termo inglês quando ausente no léxico PT e presente no EN.
        """
        candidate = self._fold(str(token or ""))
        if not candidate:
            return False
        lex_pt = self._load_auto_lexicon()
        lex_en = self._load_auto_lexicon_en()
        if lex_pt is None or lex_en is None:
            return False
        if lex_pt.lookup(candidate) is not None:
            return False
        return lex_en.lookup(candidate) is not None

    @staticmethod
    def _pair_key(word_a: str, word_b: str) -> Tuple[str, str]:
        """Garante chave ordenada e estável para pares não direcionados."""
        return (word_a, word_b) if word_a <= word_b else (word_b, word_a)

    @staticmethod
    def _word_similarity(word_a: str, word_b: str) -> float:
        """Similaridade ortográfica simples (leve e sem dependências extras)."""
        if not word_a or not word_b:
            return 0.0
        return float(SequenceMatcher(None, word_a, word_b).ratio())

    def _lemma_for_auto_word(self, word: str) -> str:
        """Retorna lema normalizado para uma palavra candidata."""
        token = self._fold(str(word or ""))
        if not token:
            return ""
        if token in self._auto_lemma_cache:
            return self._auto_lemma_cache[token]

        lemma = token
        lexicon = self._load_auto_lexicon()
        if lexicon is not None:
            try:
                looked = lexicon.lookup(token)
                if looked and looked[0]:
                    lemma = self._fold(str(looked[0]))
            except Exception:
                pass

        if lemma == token:
            semantic_bundle = self._load_auto_semantic_bundle()
            external_lemma = semantic_bundle.lemma_by_form.get(token, "")
            if external_lemma:
                lemma = self._fold(external_lemma)

        self._auto_lemma_cache[token] = lemma
        return lemma

    def _load_auto_semantic_bundle(self) -> SemanticResourceBundle:
        """Carrega recursos semânticos opcionais locais para o CCA automático."""
        if self._auto_semantic_loaded and self._auto_semantic_bundle is not None:
            return self._auto_semantic_bundle

        self._auto_semantic_loaded = True
        bundle = SemanticResourceBundle()
        try:
            roots = [
                PathManager.resources_dir() / "semantic",
                PathManager.resources_dir() / "semantic_sources",
                PathManager.dictionaries_dir() / "semantic",
            ]
            loader = SemanticResourceLoader(min_word_length=self._min_word_length)
            bundle = loader.load_many(roots)
        except Exception as exc:
            log.warning("Falha ao carregar recursos semânticos opcionais do CCA auto: %s", exc)

        self._auto_semantic_bundle = bundle
        return bundle

    def _load_external_semantic_pairs(self) -> Set[Tuple[str, str]]:
        """
        Retorna pares semânticos opcionais (cache) para reforço de arestas.
        """
        if self._auto_external_pairs_cache is not None:
            return set(self._auto_external_pairs_cache)

        semantic_bundle = self._load_auto_semantic_bundle()
        pairs = set(semantic_bundle.semantic_pairs)
        self._auto_external_pairs_cache = set(pairs)
        return pairs

    def _build_relaxed_config(self, base_cfg: AutoConceptConfig, step: int) -> AutoConceptConfig:
        """Cria configuração mais permissiva para cobrir corpora heterogêneos."""
        idx = max(1, int(step))
        return replace(
            base_cfg,
            top_n=min(420, int(base_cfg.top_n + (35 * idx))),
            window_size=min(16, int(base_cfg.window_size + idx)),
            min_edge_weight=max(1, int(base_cfg.min_edge_weight - idx)),
            min_cluster_size=max(2, int(base_cfg.min_cluster_size - 1)),
            resolution=min(2.4, float(base_cfg.resolution + (0.18 * idx))),
            confidence_threshold=max(
                float(base_cfg.relaxed_confidence_floor),
                float(base_cfg.confidence_threshold - (0.06 * idx)),
            ),
            external_pair_weight=min(1.45, float(base_cfg.external_pair_weight + (0.08 * idx))),
            semantic_bonus_weight=min(0.32, float(base_cfg.semantic_bonus_weight + (0.03 * idx))),
        )

    def _build_candidate_distribution_stats(
        self,
        words: Set[str],
    ) -> Dict[str, Dict[str, float]]:
        """Mede dispersão e concentração por segmento para candidatos."""
        if not words:
            return {}

        segment_hits: Dict[str, int] = defaultdict(int)
        max_segment_freq: Dict[str, int] = defaultdict(int)
        total_segments = max(1, len(self._segments))

        for seg in self._segments:
            local = Counter(token for token in seg if token in words)
            if not local:
                continue
            for token, count in local.items():
                segment_hits[token] += 1
                if int(count) > int(max_segment_freq.get(token, 0)):
                    max_segment_freq[token] = int(count)

        stats: Dict[str, Dict[str, float]] = {}
        for token in words:
            freq = max(1, int(self._freq.get(token, 0)))
            hit_count = int(segment_hits.get(token, 0))
            dominance = min(1.0, float(max_segment_freq.get(token, 0)) / float(freq))
            dispersion = min(1.0, float(hit_count) / float(total_segments))
            cap_ratio = min(1.0, float(self._capitalized_tokens.get(token, 0)) / float(freq))
            stats[token] = {
                "dispersion": float(dispersion),
                "dominance": float(dominance),
                "capitalized_ratio": float(cap_ratio),
                "segment_hits": float(hit_count),
            }
        return stats

    def _candidate_noise_score(
        self,
        token: str,
        freq: int,
        dispersion: float,
        dominance: float,
        capitalized_ratio: float,
    ) -> float:
        """Pontua ruído lexical comum em corpus acadêmico."""
        noise = 0.0
        if token in self._ACADEMIC_NOISE_TOKENS:
            noise += 0.42
        if len(token) <= 3:
            noise += 0.10
        if "_" in token or "-" in token:
            noise += 0.06
        if float(dispersion) < 0.12:
            noise += 0.14
        if float(dominance) > 0.80:
            noise += min(0.28, (float(dominance) - 0.80) * 1.2)
        if int(freq) >= 2 and float(capitalized_ratio) >= 0.88:
            noise += 0.50
        if int(freq) >= 3 and float(capitalized_ratio) >= 0.95 and float(dispersion) >= 0.35:
            noise += 0.20
        if self._is_english_dominant_token(token):
            noise += 0.28
        return min(0.88, max(0.0, noise))

    def _rank_auto_candidates(
        self,
        candidates: List[WordFreq],
        cfg: AutoConceptConfig,
    ) -> Tuple[List[WordFreq], Dict[str, Dict[str, float]], Dict[str, Any]]:
        """
        Rankeia candidatos por informatividade (freq + dispersão) e remove ruído.
        """
        if not candidates:
            return [], {}, {"reason": "empty_candidates"}

        words = {wf.word for wf in candidates}
        stats = self._build_candidate_distribution_stats(words)
        ranked_rows: List[Tuple[float, int, str]] = []
        word_quality: Dict[str, Dict[str, float]] = {}
        noisy_candidates = 0

        for wf in candidates:
            token = str(wf.word)
            if token in self._HARD_NOISE_TOKENS:
                continue
            freq = int(wf.freq)
            st = stats.get(token, {})
            dispersion = float(st.get("dispersion", 0.0))
            dominance = float(st.get("dominance", 0.0))
            cap_ratio = float(st.get("capitalized_ratio", 0.0))
            noise = self._candidate_noise_score(
                token=token,
                freq=freq,
                dispersion=dispersion,
                dominance=dominance,
                capitalized_ratio=cap_ratio,
            )
            if noise >= 0.55:
                noisy_candidates += 1

            informative = (0.42 + (0.90 * dispersion) + (0.18 * (1.0 - dominance)))
            score = max(0.0, float(freq) * max(0.10, informative) * max(0.05, 1.0 - noise))
            ranked_rows.append((float(score), int(freq), token))
            word_quality[token] = {
                "dispersion": dispersion,
                "dominance": dominance,
                "capitalized_ratio": cap_ratio,
                "noise_score": noise,
                "candidate_score": score,
            }

        ranked_rows.sort(key=lambda item: (-float(item[0]), -int(item[1]), str(item[2])))
        selected_words = [token for _, _, token in ranked_rows[: int(cfg.top_n)]]
        if not selected_words:
            # Fallback de segurança: mantém cobertura mínima.
            selected_words = [wf.word for wf in candidates[: int(cfg.top_n)]]
            selected_words = list(dict.fromkeys(selected_words))

        selected_set = set(selected_words)
        selected = [wf for wf in candidates if wf.word in selected_set]
        selected.sort(key=lambda wf: -int(wf.freq))

        diagnostics = {
            "candidate_pool_size": int(len(candidates)),
            "candidate_selected_size": int(len(selected)),
            "candidate_noisy_estimate": int(noisy_candidates),
            "candidate_top_examples": [
                {
                    "word": token,
                    "score": round(float(score), 4),
                    "freq": int(freq),
                    "noise": round(float(word_quality.get(token, {}).get("noise_score", 0.0)), 4),
                    "dispersion": round(float(word_quality.get(token, {}).get("dispersion", 0.0)), 4),
                    "dominance": round(float(word_quality.get(token, {}).get("dominance", 0.0)), 4),
                }
                for score, freq, token in ranked_rows[: min(18, len(ranked_rows))]
            ],
        }
        return selected, word_quality, diagnostics

    def _supplement_suggestions_from_seeds(
        self,
        graph: nx.Graph,
        freq_by_word: Dict[str, int],
        word_quality: Dict[str, Dict[str, float]],
        cfg: AutoConceptConfig,
        used_names: Set[str],
        assigned_words: Set[str],
        remaining_slots: int,
    ) -> Tuple[List[AutoConceptSuggestion], Set[str], Dict[str, Any]]:
        """
        Fallback para corpora muito esparsos: cria conceitos por expansão local
        a partir de sementes centrais ainda não atribuídas.
        """
        if remaining_slots <= 0 or graph.number_of_nodes() == 0:
            return [], set(), {"reason": "no_remaining_slots_or_empty_graph"}

        created: List[AutoConceptSuggestion] = []
        newly_assigned: Set[str] = set()
        min_weight = max(0.8, float(cfg.min_edge_weight) * 0.55)
        seed_rows: List[Tuple[float, str]] = []

        for word in graph.nodes():
            if word in assigned_words:
                continue
            quality = word_quality.get(word, {})
            noise = float(quality.get("noise_score", 0.0))
            if noise >= 0.50:
                continue
            degree_w = float(graph.degree(word, weight="weight"))
            score = (
                (0.55 * float(freq_by_word.get(word, 0)))
                + (0.45 * degree_w)
            )
            score *= max(0.20, 1.0 - noise)
            score *= (0.55 + (0.75 * float(quality.get("dispersion", 0.0))))
            if score <= 0.0:
                continue
            seed_rows.append((float(score), str(word)))

        seed_rows.sort(key=lambda item: (-float(item[0]), str(item[1])))
        for _seed_score, seed in seed_rows:
            if len(created) >= int(remaining_slots):
                break
            if seed in assigned_words or seed in newly_assigned:
                continue

            neighbors: List[Tuple[str, float]] = []
            for neighbor, attrs in graph[seed].items():
                if neighbor in assigned_words or neighbor in newly_assigned:
                    continue
                weight = float(attrs.get("weight", 0.0))
                if weight < min_weight:
                    continue
                quality = word_quality.get(str(neighbor), {})
                if float(quality.get("noise_score", 0.0)) >= 0.50:
                    continue
                neighbors.append((str(neighbor), weight))

            if not neighbors:
                continue

            neighbors.sort(
                key=lambda item: (
                    -float(item[1]),
                    -int(freq_by_word.get(item[0], 0)),
                    item[0],
                )
            )
            concept_words: List[str] = [seed]
            for neighbor, _weight in neighbors:
                if neighbor not in concept_words:
                    concept_words.append(neighbor)
                if len(concept_words) >= 6:
                    break

            min_seed_size = max(2, int(cfg.min_cluster_size) - 1)
            if len(concept_words) < min_seed_size:
                continue

            quality_words = [
                word for word in concept_words
                if float(word_quality.get(word, {}).get("noise_score", 0.0)) < 0.45
            ]
            if len(quality_words) < min_seed_size:
                continue
            mean_noise = float(
                sum(float(word_quality.get(word, {}).get("noise_score", 0.0)) for word in concept_words)
                / max(len(concept_words), 1)
            )
            if mean_noise >= 0.50:
                continue

            seed_edges = [float(graph[seed][nbr].get("weight", 0.0)) for nbr in concept_words if nbr != seed]
            max_seed_weight = max(seed_edges, default=1.0)
            word_confidences: List[float] = []
            for word in concept_words:
                quality = word_quality.get(word, {})
                dispersion = min(1.0, float(quality.get("dispersion", 0.0)) / 0.55)
                noise = float(quality.get("noise_score", 0.0))
                link_strength = 1.0
                if word != seed:
                    link_strength = float(graph[seed][word].get("weight", 0.0)) / float(max_seed_weight or 1.0)
                conf = 0.56 + (0.20 * min(1.0, link_strength)) + (0.12 * dispersion) - (0.14 * noise)
                word_confidences.append(max(0.45, min(0.93, conf)))

            mean_conf = float(sum(word_confidences) / max(len(word_confidences), 1))
            if mean_conf < max(0.55, float(cfg.relaxed_confidence_floor) - 0.08):
                continue

            naming_candidates = sorted(
                concept_words,
                key=lambda token: (
                    float(word_quality.get(token, {}).get("noise_score", 0.0)),
                    -int(freq_by_word.get(token, 0)),
                    token,
                ),
            )
            concept_name = self._make_unique_suggestion_name(
                base_name=naming_candidates[0],
                used_names=used_names,
            )
            created.append(
                AutoConceptSuggestion(
                    name=concept_name,
                    words=list(concept_words),
                    mean_confidence=round(mean_conf, 4),
                    size=len(concept_words),
                    diagnostics={
                        "source": "seed_expansion",
                        "seed": seed,
                        "min_seed_edge_weight": round(float(min_weight), 4),
                        "mean_noise": round(float(mean_noise), 4),
                    },
                )
            )
            newly_assigned.update(concept_words)

        return created, newly_assigned, {
            "seed_candidates": int(len(seed_rows)),
            "seed_suggestions_created": int(len(created)),
            "seed_words_assigned": int(len(newly_assigned)),
        }

    def _build_word_graph_for_auto(
        self,
        candidate_words: Set[str],
        cfg: AutoConceptConfig,
    ) -> Tuple[nx.Graph, int, Dict[str, Any]]:
        """
        Constrói grafo de co-ocorrência entre palavras candidatas.

        Retorna:
          - grafo ponderado palavra × palavra
          - total de janelas efetivamente analisadas
          - diagnósticos de enriquecimento lexical
        """
        graph = nx.Graph()
        for word in candidate_words:
            graph.add_node(word, freq=int(self._freq.get(word, 0)))

        pair_weights: Dict[Tuple[str, str], float] = defaultdict(float)
        total_windows = 0
        diagnostics: Dict[str, Any] = {
            "lexicon_loaded": bool(self._load_auto_lexicon() is not None),
            "lemma_bridge_pairs": 0,
            "orthographic_bridge_pairs": 0,
            "external_bridge_pairs": 0,
            "external_bridge_files_dir": str(PathManager.resources_dir() / "semantic"),
        }
        semantic_bundle = self._load_auto_semantic_bundle()
        diagnostics["external_pairs_available"] = len(semantic_bundle.semantic_pairs)
        diagnostics["external_lemma_entries_available"] = len(semantic_bundle.lemma_by_form)
        diagnostics["semantic_sources"] = dict(
            (semantic_bundle.diagnostics or {}).get("source_breakdown", {})
        )

        for seg in self._segments:
            seg_words = [w for w in seg if w in candidate_words]
            if len(seg_words) < 2:
                continue

            if len(seg_words) <= cfg.window_size:
                windows = [seg_words]
            else:
                windows = [
                    seg_words[i : i + cfg.window_size]
                    for i in range(len(seg_words) - cfg.window_size + 1)
                ]

            for window in windows:
                unique_words = sorted(set(window))
                if len(unique_words) < 2:
                    continue
                total_windows += 1
                for i in range(len(unique_words)):
                    for j in range(i + 1, len(unique_words)):
                        pair = self._pair_key(unique_words[i], unique_words[j])
                        pair_weights[pair] += 1.0

        # Ponte morfológica por lema (dicionário PT local).
        if float(cfg.lemma_bridge_weight) > 0.0:
            lemma_groups: Dict[str, List[str]] = defaultdict(list)
            for word in sorted(candidate_words):
                lemma = self._lemma_for_auto_word(word)
                if lemma:
                    lemma_groups[lemma].append(word)

            for words in lemma_groups.values():
                if len(words) < 2:
                    continue
                for i in range(len(words)):
                    for j in range(i + 1, len(words)):
                        pair = self._pair_key(words[i], words[j])
                        pair_weights[pair] += float(cfg.lemma_bridge_weight)
                        diagnostics["lemma_bridge_pairs"] += 1

        # Ponte ortográfica (útil para variantes não cobertas pelo léxico).
        if float(cfg.orthographic_bridge_weight) > 0.0 and int(cfg.max_orthographic_pairs) > 0:
            words_sorted = sorted(candidate_words, key=lambda w: (-int(self._freq.get(w, 0)), w))
            bridged = 0
            for i in range(len(words_sorted)):
                if bridged >= int(cfg.max_orthographic_pairs):
                    break
                word_a = words_sorted[i]
                # Janela local reduz custo quadrático em corpora grandes.
                for j in range(i + 1, min(i + 28, len(words_sorted))):
                    if bridged >= int(cfg.max_orthographic_pairs):
                        break
                    word_b = words_sorted[j]
                    if abs(len(word_a) - len(word_b)) > 3:
                        continue
                    if len(word_a) >= 5 and len(word_b) >= 5 and word_a[:3] != word_b[:3]:
                        continue
                    similarity = self._word_similarity(word_a, word_b)
                    if similarity < float(cfg.orthographic_similarity):
                        continue
                    pair = self._pair_key(word_a, word_b)
                    pair_weights[pair] += float(cfg.orthographic_bridge_weight)
                    diagnostics["orthographic_bridge_pairs"] += 1
                    bridged += 1

        # Ponte semântica opcional por arquivos locais.
        external_pairs = self._load_external_semantic_pairs()
        if external_pairs and float(cfg.external_pair_weight) > 0.0:
            for pair in external_pairs:
                left, right = pair
                if left in candidate_words and right in candidate_words:
                    pair_weights[pair] += float(cfg.external_pair_weight)
                    diagnostics["external_bridge_pairs"] += 1

        for (word_a, word_b), weight in pair_weights.items():
            if float(weight) >= float(cfg.min_edge_weight):
                graph.add_edge(word_a, word_b, weight=float(weight))

        return graph, total_windows, diagnostics

    @staticmethod
    def _make_unique_suggestion_name(base_name: str, used_names: Set[str]) -> str:
        """Garante nome único dentro da lista de sugestões."""
        name = str(base_name or "").strip() or "conceito"
        if name not in used_names:
            used_names.add(name)
            return name

        idx = 2
        while True:
            candidate = f"{name} {idx}"
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate
            idx += 1

    def _split_large_community(
        self,
        graph: nx.Graph,
        cluster_words: List[str],
        cfg: AutoConceptConfig,
    ) -> List[List[str]]:
        """
        Tenta subdividir comunidades muito grandes em subgrupos semânticos.

        Isso melhora cobertura em corpora homogêneos, onde uma única comunidade
        ampla pode esconder subtemas com arestas suficientemente coesas.
        """
        if len(cluster_words) < max(8, cfg.min_cluster_size * 3):
            return [list(cluster_words)]

        subgraph = graph.subgraph(cluster_words).copy()
        if subgraph.number_of_edges() < max(4, cfg.min_cluster_size):
            return [list(cluster_words)]

        split_payload = detect_louvain_partition(
            subgraph,
            resolution=min(2.8, float(cfg.resolution + 0.45)),
            seed=cfg.seed,
        )
        split_partition = dict(split_payload.get("partition", {}) or {})
        split_groups: Dict[int, List[str]] = defaultdict(list)
        for word in cluster_words:
            split_groups[int(split_partition.get(word, -1))].append(word)

        valid_groups = [
            sorted(group)
            for group in split_groups.values()
            if len(group) >= cfg.min_cluster_size
        ]
        if len(valid_groups) < 2:
            return [list(cluster_words)]

        largest_ratio = max(len(group) for group in valid_groups) / float(len(cluster_words))
        if largest_ratio > 0.82:
            return [list(cluster_words)]

        valid_groups.sort(
            key=lambda group: sum(int(self._freq.get(word, 0)) for word in group),
            reverse=True,
        )
        return valid_groups

    def _suggest_from_graph_pass(
        self,
        graph: nx.Graph,
        freq_by_word: Dict[str, int],
        word_quality: Dict[str, Dict[str, float]],
        cfg: AutoConceptConfig,
        used_names: Set[str],
        blocked_words: Set[str],
    ) -> Tuple[List[AutoConceptSuggestion], Set[str], Dict[str, Any]]:
        """Extrai sugestões de uma passada de grafo com threshold específico."""
        if graph.number_of_nodes() == 0:
            return [], set(), {"reason": "empty_graph"}

        partition_payload = detect_louvain_partition(
            graph,
            resolution=cfg.resolution,
            seed=cfg.seed,
        )
        partition = dict(partition_payload.get("partition", {}) or {})

        # Garante cobertura completa mesmo se o detector retornar parcial.
        next_cluster_id = max(partition.values(), default=-1) + 1
        for node in graph.nodes():
            if node not in partition:
                partition[node] = next_cluster_id
                next_cluster_id += 1

        communities: Dict[int, List[str]] = defaultdict(list)
        for word in graph.nodes():
            communities[int(partition[word])].append(word)

        expanded_communities: List[Tuple[str, List[str]]] = []
        split_events = 0
        for cluster_id, cluster_words in communities.items():
            splits = self._split_large_community(
                graph=graph,
                cluster_words=cluster_words,
                cfg=cfg,
            )
            if len(splits) == 1:
                expanded_communities.append((str(cluster_id), list(cluster_words)))
                continue
            split_events += 1
            for split_idx, split_words in enumerate(splits, start=1):
                expanded_communities.append((f"{cluster_id}.{split_idx}", split_words))

        ranked_communities = sorted(
            expanded_communities,
            key=lambda item: sum(freq_by_word.get(w, 0) for w in item[1]),
            reverse=True,
        )

        global_strength = {node: float(val) for node, val in graph.degree(weight="weight")}
        external_pairs = self._load_external_semantic_pairs()
        suggestions: List[AutoConceptSuggestion] = []
        assigned_words: Set[str] = set()
        communities_diagnostics: List[Dict[str, Any]] = []

        for cluster_id, cluster_words in ranked_communities:
            if len(cluster_words) < cfg.min_cluster_size:
                communities_diagnostics.append(
                    {
                        "cluster_id": cluster_id,
                        "raw_size": len(cluster_words),
                        "status": "discarded_small_cluster",
                    }
                )
                continue

            subgraph = graph.subgraph(cluster_words)
            cluster_strength = {
                node: float(subgraph.degree(node, weight="weight"))
                for node in cluster_words
            }
            max_cluster_strength = max(cluster_strength.values(), default=0.0)
            max_cluster_freq = max((freq_by_word.get(node, 0) for node in cluster_words), default=0)
            lemma_values: List[str] = []
            for cluster_word in cluster_words:
                lemma_value = self._lemma_for_auto_word(cluster_word)
                if lemma_value:
                    lemma_values.append(lemma_value)
            lemma_counter: Counter[str] = Counter(lemma_values)

            scored_rows: List[Dict[str, Any]] = []
            for word in sorted(cluster_words):
                total_strength = float(global_strength.get(word, 0.0))
                intra_strength = float(cluster_strength.get(word, 0.0))
                purity = (intra_strength / total_strength) if total_strength > 0 else 0.0
                centrality = (intra_strength / max_cluster_strength) if max_cluster_strength > 0 else 0.0
                freq_score = (
                    float(freq_by_word.get(word, 0)) / float(max_cluster_freq)
                    if max_cluster_freq > 0
                    else 0.0
                )
                quality = word_quality.get(word, {})
                dispersion = float(quality.get("dispersion", 0.0))
                dominance = float(quality.get("dominance", 0.0))
                noise_score = float(quality.get("noise_score", 0.0))
                dispersion_bonus = min(1.0, dispersion / 0.55)
                dominance_penalty = min(1.0, max(0.0, dominance - 0.68) / 0.32)
                lemma = self._lemma_for_auto_word(word)
                lemma_bonus = 1.0 if lemma and int(lemma_counter.get(lemma, 0)) >= 2 else 0.0
                semantic_links = 0
                if external_pairs:
                    for other in cluster_words:
                        if other == word:
                            continue
                        if self._pair_key(word, other) in external_pairs:
                            semantic_links += 1
                semantic_bonus = min(1.0, float(semantic_links) / 3.0)
                lexical_bonus = max(float(lemma_bonus), float(semantic_bonus))
                confidence = max(
                    0.0,
                    min(
                        1.0,
                        (0.42 * purity)
                        + (0.27 * centrality)
                        + (0.15 * freq_score)
                        + (0.09 * dispersion_bonus)
                        - (0.08 * dominance_penalty)
                        - (0.10 * noise_score)
                        + (float(cfg.semantic_bonus_weight) * lexical_bonus),
                    ),
                )
                scored_rows.append(
                    {
                        "word": word,
                        "confidence": confidence,
                        "purity": purity,
                        "centrality": centrality,
                        "freq_score": freq_score,
                        "lexical_bonus": lexical_bonus,
                        "semantic_links": semantic_links,
                        "lemma": lemma,
                        "freq": int(freq_by_word.get(word, 0)),
                        "dispersion": dispersion,
                        "dominance": dominance,
                        "dispersion_bonus": dispersion_bonus,
                        "dominance_penalty": dominance_penalty,
                        "noise_score": noise_score,
                        "candidate_score": float(quality.get("candidate_score", 0.0)),
                    }
                )

            assigned_rows = [
                row for row in scored_rows
                if float(row["confidence"]) >= float(cfg.confidence_threshold)
            ]
            fallback_mode = False
            if len(assigned_rows) < 2 and float(cfg.confidence_threshold) <= 0.76:
                relaxed_threshold = max(
                    0.55,
                    float(cfg.relaxed_confidence_floor) - 0.08,
                    float(cfg.confidence_threshold) - 0.16,
                )
                fallback_rows = [
                    row
                    for row in scored_rows
                    if float(row["confidence"]) >= float(relaxed_threshold)
                ]
                fallback_rows.sort(
                    key=lambda row: (
                        -float(row["confidence"]),
                        -int(row["freq"]),
                        str(row["word"]),
                    )
                )
                if len(fallback_rows) >= 2:
                    cap = min(8, max(2, int(cfg.min_cluster_size + 3)))
                    assigned_rows = fallback_rows[:cap]
                    fallback_mode = True
            if len(assigned_rows) < 2:
                communities_diagnostics.append(
                    {
                        "cluster_id": cluster_id,
                        "raw_size": len(cluster_words),
                        "assigned_size": len(assigned_rows),
                        "status": "discarded_low_confidence",
                    }
                )
                continue

            assigned_rows.sort(
                key=lambda row: (
                    -float(row["confidence"]),
                    -int(row["freq"]),
                    str(row["word"]),
                )
            )
            concept_words = [
                str(row["word"])
                for row in assigned_rows
                if (
                    str(row["word"]) not in blocked_words
                    and str(row["word"]) not in assigned_words
                    and float(row.get("noise_score", 0.0)) <= 0.45
                )
            ]
            if len(concept_words) < 2:
                communities_diagnostics.append(
                    {
                        "cluster_id": cluster_id,
                        "raw_size": len(cluster_words),
                        "status": "discarded_overlap_with_previous_pass",
                    }
                )
                continue

            concept_noises = [
                float(word_quality.get(word, {}).get("noise_score", 0.0))
                for word in concept_words
            ]
            mean_noise = float(sum(concept_noises) / max(len(concept_noises), 1))
            low_noise_words = [
                word for word in concept_words
                if float(word_quality.get(word, {}).get("noise_score", 0.0)) < 0.45
            ]
            if mean_noise >= 0.48 and len(low_noise_words) < 2:
                communities_diagnostics.append(
                    {
                        "cluster_id": cluster_id,
                        "raw_size": len(cluster_words),
                        "assigned_size": len(concept_words),
                        "mean_noise": round(mean_noise, 4),
                        "status": "discarded_noisy_cluster",
                    }
                )
                continue
            if len(concept_words) == 2:
                cap_ratios = [
                    float(word_quality.get(word, {}).get("capitalized_ratio", 0.0))
                    for word in concept_words
                ]
                if min(cap_ratios, default=0.0) >= 0.80 and mean_noise >= 0.30:
                    communities_diagnostics.append(
                        {
                            "cluster_id": cluster_id,
                            "raw_size": len(cluster_words),
                            "assigned_size": len(concept_words),
                            "mean_noise": round(mean_noise, 4),
                            "status": "discarded_name_like_pair",
                        }
                    )
                    continue

            naming_rows = [
                row for row in assigned_rows if str(row["word"]) in concept_words
            ]
            naming_rows.sort(
                key=lambda row: (
                    -(
                        float(row["confidence"])
                        + (0.10 * float(row.get("dispersion_bonus", 0.0)))
                        - (0.16 * float(row.get("noise_score", 0.0)))
                    ),
                    -int(row["freq"]),
                    str(row["word"]),
                )
            )
            concept_name = self._make_unique_suggestion_name(
                base_name=str((naming_rows[0] if naming_rows else assigned_rows[0])["word"]),
                used_names=used_names,
            )
            mean_confidence = float(
                sum(float(row["confidence"]) for row in assigned_rows if str(row["word"]) in concept_words)
                / max(len(concept_words), 1)
            )

            suggestions.append(
                AutoConceptSuggestion(
                    name=concept_name,
                    words=concept_words,
                    mean_confidence=round(mean_confidence, 4),
                    size=len(concept_words),
                    diagnostics={
                        "cluster_id": cluster_id,
                        "raw_size": len(cluster_words),
                        "assigned_size": len(concept_words),
                        "mean_noise": round(mean_noise, 4),
                        "fallback_mode": bool(fallback_mode),
                        "mean_purity": round(
                            sum(
                                float(row["purity"])
                                for row in assigned_rows
                                if str(row["word"]) in concept_words
                            )
                            / max(len(concept_words), 1),
                            4,
                        ),
                        "word_scores": [
                            {
                                "word": row["word"],
                                "confidence": round(float(row["confidence"]), 4),
                                "purity": round(float(row["purity"]), 4),
                                "centrality": round(float(row["centrality"]), 4),
                                "freq_score": round(float(row["freq_score"]), 4),
                                "lexical_bonus": round(float(row["lexical_bonus"]), 4),
                                "semantic_links": int(row["semantic_links"]),
                                "lemma": str(row["lemma"] or ""),
                                "freq": int(row["freq"]),
                                "dispersion": round(float(row.get("dispersion", 0.0)), 4),
                                "dominance": round(float(row.get("dominance", 0.0)), 4),
                                "noise_score": round(float(row.get("noise_score", 0.0)), 4),
                                "candidate_score": round(float(row.get("candidate_score", 0.0)), 4),
                            }
                            for row in assigned_rows
                            if str(row["word"]) in concept_words
                        ],
                    },
                )
            )
            assigned_words.update(concept_words)
            communities_diagnostics.append(
                {
                    "cluster_id": cluster_id,
                    "raw_size": len(cluster_words),
                    "assigned_size": len(concept_words),
                    "fallback_mode": bool(fallback_mode),
                    "status": "accepted",
                }
            )
            if len(suggestions) >= cfg.max_concepts:
                break

        return suggestions, assigned_words, {
            "communities_detected": int(partition_payload.get("n_communities", 0) or 0),
            "modularity": float(partition_payload.get("modularity", 0.0) or 0.0),
            "community_split_events": int(split_events),
            "communities": communities_diagnostics,
        }

    def suggest_concepts_hybrid(
        self,
        config: Optional[AutoConceptConfig] = None,
    ) -> AutoConceptResult:
        """
        Sugere conceitos automaticamente via híbrido CCA + rede.

        Faz uma passada estrita e, quando necessário, ativa passadas adaptativas
        mais permissivas para ampliar cobertura em corpora heterogêneos.
        """
        cfg = self._sanitize_auto_config(config or AutoConceptConfig())
        sampling_min_freq = max(1, int(cfg.min_freq))
        # Em corpora pequenos, permitir termos com frequência 1 aumenta cobertura.
        if len(self._segments) <= 4:
            sampling_min_freq = 1
        top_words = self.get_top_words(
            n=max(int(cfg.top_n * 3), int(cfg.top_n + 180)),
            min_freq=sampling_min_freq,
        )

        if not top_words:
            return AutoConceptResult(
                suggestions=[],
                unassigned_words=[],
                diagnostics={"reason": "empty_vocab_after_frequency_filter"},
            )

        auto_stopwords = self._get_auto_stopwords()
        candidates = [wf for wf in top_words if wf.word not in auto_stopwords]
        if not candidates:
            return AutoConceptResult(
                suggestions=[],
                unassigned_words=[wf.word for wf in top_words],
                diagnostics={"reason": "all_top_words_filtered_as_stopwords"},
            )

        ranked_candidates, word_quality, candidate_diag = self._rank_auto_candidates(
            candidates=candidates,
            cfg=cfg,
        )
        if not ranked_candidates:
            ranked_candidates = candidates[: int(cfg.top_n)]
            word_quality = {
                wf.word: {
                    "dispersion": 0.0,
                    "dominance": 0.0,
                    "capitalized_ratio": 0.0,
                    "noise_score": 0.0,
                    "candidate_score": float(wf.freq),
                }
                for wf in ranked_candidates
            }

        candidate_words = {wf.word for wf in ranked_candidates}
        freq_by_word = {wf.word: int(wf.freq) for wf in ranked_candidates}

        pass_configs: List[AutoConceptConfig] = [cfg]
        if cfg.adaptive_relaxation:
            for step in range(1, cfg.relaxation_steps + 1):
                pass_configs.append(self._build_relaxed_config(cfg, step))

        all_suggestions: List[AutoConceptSuggestion] = []
        used_names: Set[str] = set()
        assigned_words: Set[str] = set()
        pass_diagnostics: List[Dict[str, Any]] = []
        adaptive_used = False
        last_graph = None

        for pass_index, pass_cfg in enumerate(pass_configs, start=1):
            graph, total_windows, bridge_diag = self._build_word_graph_for_auto(
                candidate_words=candidate_words,
                cfg=pass_cfg,
            )
            last_graph = graph
            pass_suggestions, pass_assigned, pass_diag = self._suggest_from_graph_pass(
                graph=graph,
                freq_by_word=freq_by_word,
                word_quality=word_quality,
                cfg=pass_cfg,
                used_names=used_names,
                blocked_words=assigned_words,
            )
            if pass_index > 1:
                adaptive_used = True

            all_suggestions.extend(pass_suggestions)
            assigned_words.update(pass_assigned)

            modularity = float(pass_diag.get("modularity", 0.0) or 0.0)
            concept_sizes = [
                int(suggestion.size or len(suggestion.words or []))
                for suggestion in all_suggestions
            ]
            total_assigned_so_far = int(sum(size for size in concept_sizes if size > 0))
            largest_concept = int(max(concept_sizes, default=0) or 0)
            dominance_ratio = (
                float(largest_concept / total_assigned_so_far)
                if total_assigned_so_far > 0
                else 1.0
            )
            coverage_ratio = float(len(assigned_words) / max(len(candidate_words), 1))
            reached_minimum_targets = bool(
                len(all_suggestions) >= cfg.target_min_concepts
                and len(assigned_words) >= cfg.target_min_assigned_words
            )
            quality_gate_ok = bool(
                modularity >= float(pass_cfg.early_stop_min_modularity)
                and dominance_ratio <= float(pass_cfg.early_stop_max_dominance)
            )

            pass_diagnostics.append(
                {
                    "pass": pass_index,
                    "config": {
                        "top_n": pass_cfg.top_n,
                        "min_freq": pass_cfg.min_freq,
                        "window_size": pass_cfg.window_size,
                        "min_edge_weight": pass_cfg.min_edge_weight,
                        "min_cluster_size": pass_cfg.min_cluster_size,
                        "confidence_threshold": pass_cfg.confidence_threshold,
                        "resolution": pass_cfg.resolution,
                    },
                    "graph_nodes": graph.number_of_nodes(),
                    "graph_edges": graph.number_of_edges(),
                    "windows_analyzed": total_windows,
                    "added_concepts": len(pass_suggestions),
                    "added_words": len(pass_assigned),
                    "coverage_ratio": round(coverage_ratio, 4),
                    "dominance_ratio": round(dominance_ratio, 4),
                    "quality_gate_ok": bool(quality_gate_ok),
                    "reached_minimum_targets": bool(reached_minimum_targets),
                    "community_metrics": pass_diag,
                    "lexical_bridges": bridge_diag,
                }
            )

            if len(all_suggestions) >= cfg.max_concepts:
                break
            if reached_minimum_targets and (not cfg.adaptive_relaxation or quality_gate_ok):
                break
            if pass_index > 1 and len(pass_suggestions) == 0 and (
                coverage_ratio >= 0.35 or reached_minimum_targets
            ):
                # Evita iterações adaptativas sem ganho significativo.
                break

        if (
            bool(cfg.adaptive_relaxation)
            and (
            len(all_suggestions) < int(cfg.target_min_concepts)
            and last_graph is not None
            and int(cfg.max_concepts) > len(all_suggestions)
            )
        ):
            seed_suggestions, seed_assigned, seed_diag = self._supplement_suggestions_from_seeds(
                graph=last_graph,
                freq_by_word=freq_by_word,
                word_quality=word_quality,
                cfg=cfg,
                used_names=used_names,
                assigned_words=assigned_words,
                remaining_slots=int(cfg.max_concepts) - len(all_suggestions),
            )
            if seed_suggestions:
                all_suggestions.extend(seed_suggestions)
                assigned_words.update(seed_assigned)
                pass_diagnostics.append(
                    {
                        "pass": "seed_expansion",
                        "added_concepts": len(seed_suggestions),
                        "added_words": len(seed_assigned),
                        "details": seed_diag,
                    }
                )

        final_suggestions = all_suggestions[: cfg.max_concepts]
        final_assigned_words = {
            word
            for suggestion in final_suggestions
            for word in suggestion.words
        }
        unassigned_words = [
            wf.word for wf in candidates if wf.word not in final_assigned_words
        ]

        diagnostics = {
            "method": "hybrid_cca_network",
            "candidate_words": len(candidates),
            "candidate_ranked_words": len(ranked_candidates),
            "assigned_words": len(final_assigned_words),
            "adaptive_relaxation_enabled": bool(cfg.adaptive_relaxation),
            "adaptive_relaxation_used": bool(adaptive_used),
            "passes": pass_diagnostics,
            "external_pairs_loaded": len(self._load_external_semantic_pairs()),
            "semantic_resources": dict(self._load_auto_semantic_bundle().diagnostics or {}),
            "confidence_threshold": cfg.confidence_threshold,
            "candidate_ranking": candidate_diag,
        }

        return AutoConceptResult(
            suggestions=final_suggestions,
            unassigned_words=unassigned_words,
            diagnostics=diagnostics,
        )

    # ------------------------------------------------------------------
    # Cálculo de co-ocorrências
    # ------------------------------------------------------------------

    def _cooccurrence_windows(
        self,
        word_to_concept: Dict[str, str],
        window_size: int,
    ) -> Iterator[List[str]]:
        """
        Gera janelas deslizantes sobre cada segmento, retornando os
        conceitos presentes em cada janela (sem duplicatas).
        """
        for seg in self._segments:
            # Mapear tokens do segmento para conceitos
            concepts_in_seg = [word_to_concept.get(t) for t in seg]
            # Janela deslizante
            for i in range(len(seg) - window_size + 1):
                window = concepts_in_seg[i: i + window_size]
                present = sorted(set(c for c in window if c is not None))
                if len(present) >= 2:
                    yield present

    def run(
        self,
        concept_map: Dict[str, List[str]],
        window_size: int = 10,
    ) -> CCAResult:
        """
        Executa a análise CCA com o mapa de conceitos definido pelo usuário.

        Args:
            concept_map:  Dicionário {nome_conceito: [palavras]}.
            window_size:  Tamanho da janela de co-ocorrência (em tokens).

        Returns:
            CCAResult com o grafo de conceitos e co-ocorrências.
        """
        if not concept_map:
            raise ValueError("concept_map vazio — defina ao menos um conceito com palavras.")

        # Inverter mapa: palavra → conceito
        word_to_concept: Dict[str, str] = {}
        for concept, words in concept_map.items():
            for w in words:
                w_folded = self._fold(w)
                word_to_concept[w_folded] = concept

        # Frequência por conceito
        concept_freq: Dict[str, int] = defaultdict(int)
        for token in self._tokens:
            c = word_to_concept.get(token)
            if c:
                concept_freq[c] += 1

        # Co-ocorrências: pares de conceito → peso
        pair_weights: Dict[FrozenSet, int] = defaultdict(int)
        total_windows = 0

        for window_concepts in self._cooccurrence_windows(word_to_concept, window_size):
            total_windows += 1
            # Todos os pares (não-ordenados) dentro da janela
            for i in range(len(window_concepts)):
                for j in range(i + 1, len(window_concepts)):
                    pair = frozenset([window_concepts[i], window_concepts[j]])
                    pair_weights[pair] += 1

        # Construir arestas
        edges: List[ConceptEdge] = []
        for pair, weight in pair_weights.items():
            concepts = sorted(pair)
            if len(concepts) == 2:
                edges.append(ConceptEdge(
                    source=concepts[0],
                    target=concepts[1],
                    weight=weight,
                ))
        edges.sort(key=lambda e: -e.weight)

        log.info(
            "CCA: %d conceitos, %d arestas, %d janelas, %d segmentos",
            len(concept_map),
            len(edges),
            total_windows,
            len(self._segments),
        )

        return CCAResult(
            concept_map=dict(concept_map),
            word_concepts=word_to_concept,
            edges=edges,
            concept_freq=dict(concept_freq),
            window_size=window_size,
            total_windows=total_windows,
            segments_used=len(self._segments),
        )

    # ------------------------------------------------------------------
    # Exportação GEXF
    # ------------------------------------------------------------------

    @staticmethod
    def export_gexf(result: CCAResult, path: str | Path) -> Path:
        """
        Exporta o grafo CCA para GEXF (compatível com Gephi).

        Args:
            result: CCAResult da análise.
            path:   Caminho de saída (.gexf).

        Returns:
            Path do arquivo criado.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<gexf xmlns="http://gexf.net/1.3"'
            ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
            ' xsi:schemaLocation="http://gexf.net/1.3 http://gexf.net/1.3/gexf.xsd"'
            ' version="1.3">',
            '  <meta>',
            '    <creator>LabiiaLex CCA</creator>',
            '    <description>Connected Concept Analysis</description>',
            '  </meta>',
            '  <graph defaultedgetype="undirected">',
            '    <attributes class="node">',
            '      <attribute id="freq" title="Frequency" type="integer"/>',
            '      <attribute id="words" title="Words" type="string"/>',
            '    </attributes>',
            '    <nodes>',
        ]

        for node_id, concept in enumerate(result.nodes):
            freq = result.concept_freq.get(concept, 0)
            words = ", ".join(result.concept_map.get(concept, []))
            safe_concept = concept.replace("&", "&amp;").replace('"', "&quot;")
            safe_words = words.replace("&", "&amp;").replace('"', "&quot;")
            lines.append(
                f'      <node id="{node_id}" label="{safe_concept}">'
            )
            lines.append(
                f'        <attvalues>'
                f'<attvalue for="freq" value="{freq}"/>'
                f'<attvalue for="words" value="{safe_words}"/>'
                f'</attvalues>'
            )
            lines.append('      </node>')

        lines.append('    </nodes>')
        lines.append('    <edges>')

        node_index = {c: i for i, c in enumerate(result.nodes)}
        for edge_id, edge in enumerate(result.edges):
            src = node_index.get(edge.source, 0)
            tgt = node_index.get(edge.target, 0)
            lines.append(
                f'      <edge id="{edge_id}" source="{src}" target="{tgt}"'
                f' weight="{edge.weight}"/>'
            )

        lines.append('    </edges>')
        lines.append('  </graph>')
        lines.append('</gexf>')

        path.write_text("\n".join(lines), encoding="utf-8")
        log.info("GEXF exportado para %s", path)
        return path

    # ------------------------------------------------------------------
    # Relatório CSV simples
    # ------------------------------------------------------------------

    @staticmethod
    def export_csv(result: CCAResult, path: str | Path) -> Path:
        """Exporta a tabela de co-ocorrências em CSV."""
        import csv
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Conceito A", "Conceito B", "Co-ocorrências"])
            for edge in result.edges:
                writer.writerow([edge.source, edge.target, edge.weight])

        log.info("CSV CCA exportado para %s", path)
        return path
