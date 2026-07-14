"""
Text Processor Module for LabiiaLex.

This module provides text processing capabilities including
document-term matrix (DTM) construction, co-occurrence matrices,
and data export for R analyses.

Based on: iramuteq-master/corpus.py matrix building functions
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from collections import defaultdict

import numpy as np
from scipy import sparse

from .corpus import Corpus, Word, _load_cached_english_lexicon
from .lexicon import Lexicon, build_portuguese_stopwords_from_lexicon, resolve_lexicon_path
from .stopword_layers import MANDATORY_EXTRA_STOPWORDS, expand_stopword_entry
from .stopword_policy import expand_extra_stopwords, is_content_term, is_stopword_like, is_visual_content_term

log = logging.getLogger(__name__)


class TextProcessorError(Exception):
    """
    Exception for text processing errors.
    
    Provides user-friendly error messages following the What/Why/How pattern.
    """
    
    def __init__(self, what: str, why: str, how: str):
        self.what = what
        self.why = why
        self.how = how
        super().__init__(f"{what}\n\nMotivo: {why}\n\nSolução: {how}")


class TextProcessor:
    """
    Text processing for corpus analysis.
    
    Builds document-term matrices, co-occurrence matrices, and
    exports data in formats suitable for R analyses.
    
    Attributes:
        corpus: The Corpus object to process
        dtm: Document-term matrix (sparse)
        cooc: Co-occurrence matrix (sparse)
        vocabulary: List of words (column indices for DTM)
        doc_ids: List of document IDs (row indices for DTM)
    """
    
    def __init__(self, corpus: Corpus):
        """
        Initialize TextProcessor with a corpus.
        
        Args:
            corpus: Corpus object containing UCIs, UCEs, and vocabulary
        """
        self.corpus = corpus
        self.dtm: Optional[sparse.csr_matrix] = None
        self.cooc: Optional[sparse.csr_matrix] = None
        self.vocabulary: List[str] = []
        self.doc_ids: List[int] = []
        self._word_to_idx: Dict[str, int] = {}
        self._doc_to_idx: Dict[int, int] = {}

    @staticmethod
    def _is_valid_term(word: str) -> bool:
        """Safety filter shared with the similitude engine."""
        return is_visual_content_term(word)

    # -------------------------------------------------------------------------
    # Document-Term Matrix
    # -------------------------------------------------------------------------
    
    def build_dtm(
        self,
        min_freq: int = 1,
        use_lemmas: bool = False,
        active_only: bool = True,
        max_actives: int = 0,
        stopword_policy: str = "aggressive_pt",
        strict_stopword_filter: bool = False,
        strict_iramuteq_clone: bool = False,
        prefer_portuguese_br: bool = True,
    ) -> sparse.csr_matrix:
        """
        Build document-term matrix from corpus.
        
        Creates a sparse matrix where rows are UCEs (text segments)
        and columns are words/lemmas.
        
        Args:
            min_freq: Minimum word frequency to include
            use_lemmas: Use lemmas instead of word forms
            active_only: Only include active (content) words
            max_actives: Maximum number of active terms (0 = no limit)
            stopword_policy: Stopword filtering policy ("legacy" or "aggressive_pt")
            strict_stopword_filter: Fail if aggressive policy requested without loaded lexicon
            
        Returns:
            Sparse CSR matrix of shape (n_docs, n_words)
        """
        # Get vocabulary that meets criteria
        self._build_vocabulary(
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
            stopword_policy=stopword_policy,
            strict_stopword_filter=strict_stopword_filter,
            strict_iramuteq_clone=bool(strict_iramuteq_clone),
            prefer_portuguese_br=bool(prefer_portuguese_br),
        )
        self._limit_vocabulary(
            max_actives=max_actives,
            use_lemmas=use_lemmas,
            strict_iramuteq_clone=bool(strict_iramuteq_clone),
        )
        
        if not self.vocabulary:
            raise TextProcessorError(
                what="Não foi possível construir a matriz documento-termo.",
                why=f"Nenhuma palavra atende aos critérios (freq >= {min_freq}).",
                how="Reduza o valor de min_freq ou adicione mais texto ao corpus."
            )
        
        # Get all UCE texts
        uce_texts = list(self.corpus.get_uces())
        if not uce_texts:
            raise TextProcessorError(
                what="Não foi possível construir a matriz documento-termo.",
                why="O corpus não contém segmentos de texto (UCEs).",
                how="Adicione UCEs ao corpus antes de construir a matriz."
            )
        
        # Build document index
        self.doc_ids = [uce_id for uce_id, _ in uce_texts]
        self._doc_to_idx = {doc_id: idx for idx, doc_id in enumerate(self.doc_ids)}
        use_index_counts = self._has_reliable_uce_index(self.doc_ids)
        
        # Build sparse matrix using COO format for efficiency
        rows = []
        cols = []
        data = []
        
        for doc_idx, (uce_id, text) in enumerate(uce_texts):
            word_counts = self._count_words_for_uce(
                uce_id,
                text,
                use_lemmas,
                prefer_index=use_index_counts,
            )
            for word, count in word_counts.items():
                if word in self._word_to_idx:
                    rows.append(doc_idx)
                    cols.append(self._word_to_idx[word])
                    data.append(count)
        
        n_docs = len(self.doc_ids)
        n_words = len(self.vocabulary)
        
        self.dtm = sparse.csr_matrix(
            (data, (rows, cols)),
            shape=(n_docs, n_words),
            dtype=np.float64
        )
        
        log.info(f"Built DTM: {n_docs} documents x {n_words} words, "
                 f"{self.dtm.nnz} non-zero entries")
        
        return self.dtm
    
    def _build_vocabulary(
        self,
        min_freq: int,
        use_lemmas: bool,
        active_only: bool,
        stopword_policy: str = "aggressive_pt",
        strict_stopword_filter: bool = False,
        strict_iramuteq_clone: bool = False,
        prefer_portuguese_br: bool = True,
    ) -> None:
        """Build vocabulary list meeting criteria."""
        self.vocabulary = []
        self._word_to_idx = {}
        policy = str(stopword_policy or "aggressive_pt").strip().lower()
        stopword_checker = self._resolve_stopword_checker(
            stopword_policy=policy,
            strict_stopword_filter=bool(strict_stopword_filter),
            strict_iramuteq_clone=bool(strict_iramuteq_clone),
        )
        
        if use_lemmas:
            # Use lemmas
            for lem_key, lem in self.corpus.lems.items():
                if lem.freq >= min_freq:
                    if policy == "aggressive_pt":
                        if int(getattr(lem, "act", 1)) != 1:
                            continue
                    elif active_only and int(getattr(lem, "act", 1)) != 1:
                        continue
                    if stopword_checker(lem_key):
                        continue
                    if self._is_non_portuguese_english_token(
                        token=lem_key,
                        lemma=lem_key,
                        stopword_policy=policy,
                        prefer_portuguese_br=bool(prefer_portuguese_br),
                    ):
                        continue
                    self._word_to_idx[lem_key] = len(self.vocabulary)
                    self.vocabulary.append(lem_key)
        else:
            # Use word forms
            for forme, word in self.corpus.formes.items():
                if word.freq >= min_freq:
                    if policy == "aggressive_pt":
                        if int(getattr(word, "act", 1)) != 1:
                            continue
                    elif active_only and int(getattr(word, "act", 1)) != 1:
                        continue
                    if stopword_checker(forme):
                        continue
                    if self._is_non_portuguese_english_token(
                        token=forme,
                        lemma=str(getattr(word, "lem", forme) or forme),
                        stopword_policy=policy,
                        prefer_portuguese_br=bool(prefer_portuguese_br),
                    ):
                        continue
                    self._word_to_idx[forme] = len(self.vocabulary)
                    self.vocabulary.append(forme)
        
        self.vocabulary.sort()
        self._word_to_idx = {w: i for i, w in enumerate(self.vocabulary)}

    def _is_non_portuguese_english_token(
        self,
        token: str,
        lemma: str,
        stopword_policy: str,
        prefer_portuguese_br: bool = True,
    ) -> bool:
        """
        In aggressive PT mode, drop tokens recognized as English-only.

        Keeps Portuguese terms untouched and only removes words that:
        - are unknown in PT lexicon, and
        - are recognized by the English lexicon.
        """
        if not bool(prefer_portuguese_br):
            return False

        pt_lexicon = getattr(self.corpus, "lexicon", None)
        if pt_lexicon is None:
            return False

        language_key = str(getattr(pt_lexicon, "_language_key", "") or "").lower()
        if "pt" not in language_key and "portuguese" not in language_key:
            return False

        token_norm = str(token or "").strip().lower()
        lemma_norm = str(lemma or token_norm).strip().lower()
        if not token_norm:
            return False
        if len(token_norm) < 2:
            return False
        if not token_norm.replace("-", "").isalpha():
            return False
        if not token_norm.isascii():
            return False

        # Keep Portuguese terms, except high-confidence English borrowings in "-ing".
        # This targets frequent contamination in mixed corpora (e.g., "training").
        is_ing_candidate = token_norm.endswith(("ing", "ings")) or lemma_norm.endswith(("ing", "ings"))
        if (
            pt_lexicon.lookup(token_norm) is not None
            or pt_lexicon.lookup(lemma_norm) is not None
        ) and not is_ing_candidate:
            return False

        en_lexicon = _load_cached_english_lexicon()
        if en_lexicon is None:
            return False

        return (
            en_lexicon.lookup(token_norm) is not None
            or en_lexicon.lookup(lemma_norm) is not None
        )

    def _limit_vocabulary(
        self,
        max_actives: int,
        use_lemmas: bool,
        strict_iramuteq_clone: bool = False,
    ) -> None:
        """Limit current vocabulary to top-N terms by frequency."""
        limit = int(max_actives or 0)
        scored: List[Tuple[int, str]] = []
        for token in self.vocabulary:
            if use_lemmas:
                freq = int(getattr(self.corpus.lems.get(token), "freq", 0))
            else:
                freq = int(getattr(self.corpus.formes.get(token), "freq", 0))
            scored.append((freq, token))

        if not scored:
            self.vocabulary = []
            self._word_to_idx = {}
            return

        if strict_iramuteq_clone:
            # IRaMuTeQ make_actives_nb equivalent:
            # allactives = sorted([[freq, lem], ...], reverse=True)
            # then tie-cut by frequency threshold.
            if use_lemmas:
                selected, _lim = self.corpus.make_actives_nb(limit, 1)
                if selected:
                    allowed = {str(token) for token in self.vocabulary}
                    selected = [str(token) for token in selected if str(token) in allowed]
                    if selected:
                        self.vocabulary = selected
                        self._word_to_idx = {word: idx for idx, word in enumerate(self.vocabulary)}
                        return

            scored.sort(reverse=True)

            if limit <= 0 or len(scored) <= limit:
                self.vocabulary = [token for _freq, token in scored]
                self._word_to_idx = {word: idx for idx, word in enumerate(self.vocabulary)}
                return

            effs = [freq for freq, _token in scored]
            if effs.count(effs[limit - 1]) > 1:
                lim = effs[limit - 1] + 1
                while True:
                    try:
                        stop = effs.index(lim)
                        break
                    except ValueError:
                        lim -= 1
            else:
                stop = limit - 1

            # Keep original IRaMuTeQ slicing semantics.
            self.vocabulary = [token for _freq, token in scored[:stop]]
            self._word_to_idx = {word: idx for idx, word in enumerate(self.vocabulary)}
            return

        if limit <= 0 or len(self.vocabulary) <= limit:
            return

        scored.sort(reverse=True)

        effs = [freq for freq, _token in scored]
        if effs.count(effs[limit - 1]) > 1:
            lim = effs[limit - 1] + 1
            nok = True
            while nok:
                try:
                    stop = effs.index(lim)
                    nok = False
                except ValueError:
                    lim -= 1
        else:
            stop = limit - 1

        self.vocabulary = [token for _freq, token in scored[:stop]]
        self.vocabulary.sort()
        self._word_to_idx = {word: idx for idx, word in enumerate(self.vocabulary)}
    
    def _has_reliable_uce_index(self, doc_ids: List[int]) -> bool:
        """Return True when corpus word->UCE indexes cover the current DTM rows."""
        index = getattr(self.corpus, "idformesuces", None) or {}
        if not index or not doc_ids:
            return False
        expected = {int(doc_id) for doc_id in doc_ids}
        indexed: set[int] = set()
        for uce_counts in index.values():
            for raw_uce_id, count in (uce_counts or {}).items():
                try:
                    if int(count or 0) > 0:
                        indexed.add(int(raw_uce_id))
                except Exception:
                    continue
        covered = len(expected.intersection(indexed))
        if len(expected) <= 2:
            return covered == len(expected)
        return covered / max(1, len(expected)) >= 0.8

    def _count_words_for_uce(
        self,
        uce_id: int,
        text: str,
        use_lemmas: bool,
        *,
        prefer_index: bool = True,
    ) -> Dict[str, int]:
        """Count words for a UCE using corpus indexes when available."""
        indexed_counts = self._count_indexed_words_for_uce(int(uce_id), use_lemmas) if prefer_index else {}
        if prefer_index and indexed_counts:
            return indexed_counts
        return self._count_words(text, use_lemmas)

    def _count_indexed_words_for_uce(self, uce_id: int, use_lemmas: bool) -> Dict[str, int]:
        """Count terms from corpus.idformesuces, preserving normalized vocabulary."""
        counts: Dict[str, int] = defaultdict(int)
        index = getattr(self.corpus, "idformesuces", None) or {}
        if not index:
            return {}
        idformes = self.corpus.make_idformes()
        for forme_id, uce_counts in index.items():
            try:
                count = int((uce_counts or {}).get(int(uce_id), 0) or 0)
            except Exception:
                count = 0
            if count <= 0:
                continue
            word = idformes.get(int(forme_id))
            if word is None:
                continue
            token = getattr(word, "lem", None) if use_lemmas else getattr(word, "forme", None)
            token = str(token or "").strip().lower()
            if token:
                counts[token] += count
        return dict(counts)

    def _count_words(self, text: str, use_lemmas: bool) -> Dict[str, int]:
        """Count word occurrences in text."""
        counts: Dict[str, int] = defaultdict(int)
        
        for word in text.lower().split():
            # Clean word
            word = word.strip('.,;:!?"\'()[]{}')
            if not word:
                continue
            
            if use_lemmas:
                # Find lemma for this word form
                if word in self.corpus.formes:
                    lem = self.corpus.formes[word].lem
                    if lem:
                        counts[lem] += 1
            else:
                counts[word] += 1
        
        return dict(counts)
    
    # -------------------------------------------------------------------------
    # Co-occurrence Matrix
    # -------------------------------------------------------------------------
    
    def build_cooccurrence_matrix(
        self,
        window_size: int = 5,
        min_freq: int = 3,
        active_only: bool = True,
        use_lemmas: bool = False,
        stopword_policy: str = "aggressive_pt",
        strict_stopword_filter: bool = False,
        strict_iramuteq_clone: bool = False,
        prefer_portuguese_br: bool = True,
    ) -> sparse.csr_matrix:
        """
        Build word co-occurrence matrix.
        
        Creates a symmetric sparse matrix showing how often words
        appear together within a sliding window.
        
        Args:
            window_size: Size of the context window
            min_freq: Minimum word frequency to include
            active_only: Only include active forms (active=1)
            use_lemmas: Count co-occurrences by lemma instead of raw forms
            stopword_policy: Stopword filtering policy ("legacy" or "aggressive_pt")
            strict_stopword_filter: Fail if aggressive policy requested without loaded lexicon
            
        Returns:
            Sparse CSR matrix of shape (n_words, n_words)
        """
        # Always rebuild vocabulary for deterministic policy application.
        self._build_vocabulary(
            min_freq=min_freq,
            use_lemmas=use_lemmas,
            active_only=active_only,
            stopword_policy=stopword_policy,
            strict_stopword_filter=strict_stopword_filter,
            strict_iramuteq_clone=bool(strict_iramuteq_clone),
            prefer_portuguese_br=bool(prefer_portuguese_br),
        )
        
        n_words = len(self.vocabulary)
        cooc_dict: Dict[Tuple[int, int], int] = defaultdict(int)
        
        # Process all UCE texts
        for uce_id, text in self.corpus.get_uces():
            words = text.lower().split()
            word_indices = []
            
            # Map words to indices
            for word in words:
                word = word.strip('.,;:!?"\'()[]{}')
                if not word:
                    continue
                token = word
                if use_lemmas:
                    forme = self.corpus.formes.get(word)
                    if forme is not None and getattr(forme, "lem", None):
                        token = str(forme.lem).strip().lower()
                if token in self._word_to_idx:
                    word_indices.append(self._word_to_idx[token])
            
            # Count co-occurrences within window
            for i, idx_i in enumerate(word_indices):
                for j in range(max(0, i - window_size), min(len(word_indices), i + window_size + 1)):
                    if i != j:
                        idx_j = word_indices[j]
                        # Use sorted tuple to ensure symmetry
                        key = (min(idx_i, idx_j), max(idx_i, idx_j))
                        cooc_dict[key] += 1
        
        # Build symmetric sparse matrix
        rows = []
        cols = []
        data = []
        
        for (i, j), count in cooc_dict.items():
            rows.extend([i, j])
            cols.extend([j, i])
            data.extend([count, count])
        
        self.cooc = sparse.csr_matrix(
            (data, (rows, cols)),
            shape=(n_words, n_words),
            dtype=np.float64
        )
        
        log.info(f"Built co-occurrence matrix: {n_words} x {n_words}, "
                 f"{len(cooc_dict)} unique pairs")
        
        return self.cooc

    def _resolve_stopword_checker(
        self,
        stopword_policy: str,
        strict_stopword_filter: bool,
        strict_iramuteq_clone: bool = False,
    ) -> Callable[[str], bool]:
        policy = str(stopword_policy or "aggressive_pt").strip().lower()
        extra_stopwords = self._collect_extra_stopwords()
        if policy == "legacy":
            return lambda _token: False
        if policy != "aggressive_pt":
            raise TextProcessorError(
                what="Nao foi possivel aplicar o filtro de stopwords.",
                why=f"Politica de stopword desconhecida: {stopword_policy!r}.",
                how="Use stopword_policy='legacy' ou stopword_policy='aggressive_pt'.",
            )

        lexicon = getattr(self.corpus, "lexicon", None)
        if lexicon is not None:
            if bool(strict_iramuteq_clone):
                # Strict clone follows IRaMuTeQ lexical tagging (no extra fallback lists).
                return lambda token: (
                    bool(lexicon.is_stopword(str(token or "").strip().lower()))
                    or is_stopword_like(token, extra_stopwords=extra_stopwords)
                )
            return lambda token: (
                bool(lexicon.is_stopword(str(token or "").strip().lower()))
                or is_stopword_like(token, extra_stopwords=extra_stopwords, lexicon=lexicon)
            )

        if strict_stopword_filter:
            raise TextProcessorError(
                what="Nao foi possivel aplicar o filtro agressivo de stopwords.",
                why="O lexico nao esta carregado e strict_stopword_filter=True.",
                how=(
                    "Carregue o lexico portugues antes da analise ou desative "
                    "strict_stopword_filter para usar fallback de stopwords."
                ),
            )

        return lambda token: is_stopword_like(token, extra_stopwords=extra_stopwords)

    def _collect_extra_stopwords(self) -> Set[str]:
        """Collect mandatory + corpus-configured custom stopwords."""
        merged: Set[str] = set()
        for token in MANDATORY_EXTRA_STOPWORDS:
            merged.update(expand_stopword_entry(token))
        parametres = getattr(self.corpus, "parametres", {}) or {}
        configured = parametres.get("extra_stopwords", [])
        if isinstance(configured, (list, tuple, set)):
            for value in configured:
                merged.update(expand_stopword_entry(str(value)))
        return expand_extra_stopwords(merged)
    
    # -------------------------------------------------------------------------
    # Word Frequency Analysis
    # -------------------------------------------------------------------------
    
    def get_word_frequencies(
        self,
        use_lemmas: bool = False,
        active_only: bool = False,
        exclude_stopwords: bool = False,
    ) -> List[Tuple[str, int]]:
        """
        Get word frequencies sorted by frequency.
        
        Args:
            use_lemmas: Use lemmas instead of word forms
            active_only: Restrict to active lexical forms only
            exclude_stopwords: Remove stopwords via loaded lexical dictionary
            
        Returns:
            List of (word, frequency) tuples sorted by frequency descending
        """
        lexicon = getattr(self.corpus, "lexicon", None)
        extra_stopwords = self._collect_extra_stopwords()
        if use_lemmas:
            freqs = []
            for lem in self.corpus.lems.values():
                token = str(lem.lem or "").strip()
                if not token:
                    continue
                if active_only and int(getattr(lem, "act", 1)) != 1:
                    continue
                if (exclude_stopwords or active_only) and not is_visual_content_term(
                    token,
                    extra_stopwords=extra_stopwords,
                    lexicon=lexicon,
                ):
                    continue
                freqs.append((token, int(lem.freq)))
        else:
            freqs = []
            for word in self.corpus.formes.values():
                token = str(word.forme or "").strip()
                if not token:
                    continue
                if active_only and int(getattr(word, "act", 1)) != 1:
                    continue
                if (exclude_stopwords or active_only) and not is_visual_content_term(
                    token,
                    extra_stopwords=extra_stopwords,
                    lexicon=lexicon,
                ):
                    continue
                freqs.append((token, int(word.freq)))
        
        return sorted(freqs, key=lambda x: x[1], reverse=True)
    
    def get_active_forms(self, min_freq: int = 3) -> List[str]:
        """
        Get list of active word forms meeting frequency threshold.
        
        Args:
            min_freq: Minimum frequency threshold
            
        Returns:
            List of word forms
        """
        return [
            forme for forme, word in self.corpus.formes.items()
            if word.freq >= min_freq and word.act == 1
        ]
    
    def filter_by_frequency(self, min_freq: int) -> List[str]:
        """
        Filter vocabulary by minimum frequency.
        
        Args:
            min_freq: Minimum frequency threshold
            
        Returns:
            List of words meeting threshold
        """
        return [
            forme for forme, word in self.corpus.formes.items()
            if word.freq >= min_freq
        ]
    
    # -------------------------------------------------------------------------
    # Export Methods
    # -------------------------------------------------------------------------
    
    def export_for_chd(self, path: Path) -> Dict[str, Path]:
        """
        Export data for CHD (Reinert) analysis.
        
        Creates files needed by R CHD script:
        - data.csv: Document-term matrix
        - vocab.csv: Vocabulary list
        - docs.csv: Document IDs
        
        Args:
            path: Output directory path
            
        Returns:
            Dictionary mapping file type to file path
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        # Ensure DTM is built
        if self.dtm is None:
            self.build_dtm()
        
        files = {}
        
        # Export DTM as dense matrix (R template expects rows=UCEs, cols=forms)
        dtm_path = path / "TableUc1.csv"
        row_labels = [str(doc_id) for doc_id in self.doc_ids]
        self._export_dense_matrix(
            self.dtm,
            dtm_path,
            row_labels=row_labels,
            col_labels=self.vocabulary,
        )
        files['dtm'] = dtm_path
        
        # Export vocabulary
        vocab_path = path / "formes.csv"
        self._export_vocabulary(vocab_path)
        files['vocabulary'] = vocab_path
        
        # Export document IDs
        docs_path = path / "listuce1.csv"
        with open(docs_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            for doc_id in self.doc_ids:
                writer.writerow([doc_id])
        files['docs'] = docs_path
        
        log.info(f"Exported CHD data to {path}")
        return files

    def export_for_chd_native(
        self,
        path: Path,
        tailleuc1: int = 12,
        tailleuc2: int = 14,
        classif_mode: int = 1,
    ) -> Dict[str, Path]:
        """
        Export CHD inputs following IRaMuTeQ's native Reinert pipeline.

        Files generated:
        - TableUc1.csv / TableUc2.csv: MatrixMarket sparse matrices (UC x active forms)
        - listuce1.csv / listuce2.csv: "uce;uc" mapping (UCE id -> UC index, 0-based)
        - formes.csv: vocabulary export

        Args:
            path: Output directory.
            tailleuc1: UC1 target active-token size.
            tailleuc2: UC2 target active-token size.
            classif_mode:
                0 = double CHD (UC1 + UC2),
                1 = simple UCE (UCE->UC identity, IRaMuTeQ),
                2 = simple UCI (UCI->UC identity, IRaMuTeQ).

        Returns:
            Dictionary mapping file role to output path.
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        if self.dtm is None:
            self.build_dtm()

        files: Dict[str, Path] = {}

        mode = int(classif_mode)
        if mode in {1, 2}:
            # IRaMuTeQ classif_mode=1 uses UCE rows directly (UCE->UC identity).
            uc1 = [[int(doc_id)] for doc_id in self.doc_ids]
            uc2: List[List[int]] = []
        else:
            uc1, uc2 = self._build_uc_groups(
                limit_uc1=max(1, int(tailleuc1)),
                limit_uc2=max(1, int(tailleuc2)),
            )
        if not uc1:
            raise TextProcessorError(
                what="Nao foi possivel exportar CHD nativo.",
                why="Nenhum grupo UC1 foi gerado a partir do corpus.",
                how="Verifique se o corpus possui UCEs validas e rode novamente.",
            )

        table_uc1_path = path / "TableUc1.csv"
        listuce1_path = path / "listuce1.csv"
        self._export_uc_matrix_market(uc1, table_uc1_path)
        self._export_listuce(uc1, listuce1_path, id_label="uci" if mode == 2 else "uce")
        files["dtm"] = table_uc1_path
        files["listuce1"] = listuce1_path

        if mode == 0:
            if not uc2:
                raise TextProcessorError(
                    what="Nao foi possivel exportar CHD nativo em modo duplo.",
                    why="Nenhum grupo UC2 foi gerado a partir do corpus.",
                    how="Ajuste tailleuc2 ou revise os segmentos do corpus.",
                )
            table_uc2_path = path / "TableUc2.csv"
            listuce2_path = path / "listuce2.csv"
            self._export_uc_matrix_market(uc2, table_uc2_path)
            self._export_listuce(uc2, listuce2_path)
            files["dtm2"] = table_uc2_path
            files["listuce2"] = listuce2_path

        vocab_path = path / "formes.csv"
        self._export_vocabulary(vocab_path, include_freq=True)
        files["vocabulary"] = vocab_path

        log.info(
            "Exported native CHD data to %s (uc1=%d%s)",
            path,
            len(uc1),
            f", uc2={len(uc2)}" if mode == 0 else "",
        )
        return files
    
    def export_for_afc(self, path: Path) -> Dict[str, Path]:
        """
        Export data for AFC (Correspondence Analysis).
        
        Args:
            path: Output directory path
            
        Returns:
            Dictionary mapping file type to file path
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        
        if self.dtm is None:
            self.build_dtm()
        
        files = {}
        
        # Export contingency table (integer counts, IRaMuTeQ-compatible)
        dtm_counts = self.dtm.copy()
        if dtm_counts.nnz:
            dtm_counts.data = np.rint(dtm_counts.data).astype(np.int64)
        table_path = path / "ContTable.csv"
        row_labels = [str(doc_id) for doc_id in self.doc_ids]
        self._export_dense_matrix(
            dtm_counts,
            table_path,
            row_labels=row_labels,
            col_labels=self.vocabulary,
        )
        files['table'] = table_path
        
        # Export vocabulary with frequencies
        vocab_path = path / "forme.csv"
        self._export_vocabulary(vocab_path, include_freq=True)
        files['vocabulary'] = vocab_path
        
        log.info(f"Exported AFC data to {path}")
        return files
    
    def export_for_similarity(self, path: Path) -> Dict[str, Path]:
        """
        Export data for similarity analysis.

        Args:
            path: Output directory path

        Returns:
            Dictionary mapping file type to file path
        """
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Ensure DTM exists (used for IRaMuTeQ-like coefficient calculations)
        if self.dtm is None:
            self.build_dtm()

        # Build co-occurrence if not done
        if self.cooc is None:
            self.build_cooccurrence_matrix()

        files = {}

        # Export DTM (rows=UCEs, cols=forms)
        dtm_path = path / "dtm.csv"
        row_labels = [str(doc_id) for doc_id in self.doc_ids]
        self._export_dense_matrix(
            self.dtm,
            dtm_path,
            row_labels=row_labels,
            col_labels=self.vocabulary,
        )
        files["dtm"] = dtm_path

        # Export co-occurrence matrix
        cooc_path = path / "contingency.csv"
        self._export_dense_matrix(
            self.cooc,
            cooc_path,
            row_labels=self.vocabulary,
            col_labels=self.vocabulary,
        )
        files['cooccurrence'] = cooc_path
        
        # Export vocabulary
        vocab_path = path / "words.csv"
        with open(vocab_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            for word in self.vocabulary:
                writer.writerow([word])
        files['vocabulary'] = vocab_path
        
        log.info(f"Exported similarity data to {path}")
        return files
    
    def _export_sparse_matrix(self, matrix: sparse.csr_matrix, 
                               filepath: Path) -> None:
        """Export sparse matrix as CSV triplets."""
        coo = matrix.tocoo()
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['row', 'col', 'value'])
            for i, j, v in zip(coo.row, coo.col, coo.data):
                if v != 0:
                    writer.writerow([i + 1, j + 1, v])  # 1-indexed for R

    def _build_uc_groups(self, limit_uc1: int, limit_uc2: int) -> Tuple[List[List[int]], List[List[int]]]:
        """
        Group ordered UCEs into UC1/UC2 using IRaMuTeQ's make_uc logic.

        The grouping respects paragraph boundaries and active-token sizes.
        """
        if self.dtm is None:
            raise TextProcessorError(
                what="Matriz DTM indisponivel para gerar UCs.",
                why="A DTM nao foi inicializada antes da exportacao CHD nativa.",
                how="Execute build_dtm() antes de exportar para CHD.",
            )

        # IRaMuTeQ counts UNIQUE active forms per UCE, not total frequency!
        row_sums = self.dtm.getnnz(axis=1)
        uce_act_size: Dict[int, int] = {
            int(doc_id): int(max(0, value))
            for doc_id, value in zip(self.doc_ids, row_sums)
        }
        ordered_uces = [uce for uci in self.corpus.ucis for uce in uci.uces]
        if not ordered_uces:
            return [], []

        last1 = 0
        last2 = 0
        lastpara = 0
        uc1: List[List[int]] = [[]]
        uc2: List[List[int]] = [[]]

        for uce in ordered_uces:
            uce_id = int(uce.ident)
            para_id = int(uce.para)
            count = int(uce_act_size.get(uce_id, 0))

            if para_id == lastpara:
                if last1 <= limit_uc1:
                    last1 += count
                    uc1[-1].append(uce_id)
                else:
                    uc1.append([uce_id])
                    last1 = count

                if last2 <= limit_uc2:
                    last2 += count
                    uc2[-1].append(uce_id)
                else:
                    uc2.append([uce_id])
                    last2 = count
            else:
                last1 = count
                last2 = count
                lastpara = para_id
                uc1.append([uce_id])
                uc2.append([uce_id])

        uc1 = [group for group in uc1 if group]
        uc2 = [group for group in uc2 if group]
        return uc1, uc2

    def _export_uc_matrix_market(self, uc_groups: List[List[int]], filepath: Path) -> None:
        """
        Export UC x vocabulary matrix in MatrixMarket coordinate integer format.

        Each entry is binary (presence/absence) to mirror IRaMuTeQ CHD input.
        """
        if self.dtm is None:
            raise TextProcessorError(
                what="DTM nao disponivel para exportacao MatrixMarket.",
                why="A matriz documento-termo ainda nao foi gerada.",
                how="Execute build_dtm() antes de exportar.",
            )

        doc_to_row = {int(doc_id): idx for idx, doc_id in enumerate(self.doc_ids)}
        rows: List[int] = []
        cols: List[int] = []
        data: List[int] = []

        for uc_idx, uce_ids in enumerate(uc_groups):
            row_indices = [doc_to_row[uce_id] for uce_id in uce_ids if uce_id in doc_to_row]
            if not row_indices:
                continue

            sub = self.dtm[row_indices, :]
            if sub.nnz == 0:
                continue
            active_cols = np.unique(sub.indices)
            rows.extend([uc_idx] * len(active_cols))
            cols.extend(active_cols.tolist())
            data.extend([1] * len(active_cols))

        matrix = sparse.csr_matrix(
            (data, (rows, cols)),
            shape=(len(uc_groups), len(self.vocabulary)),
            dtype=np.int32,
        )
        coo = matrix.tocoo()

        with open(filepath, "w", encoding="utf-8", newline="") as file:
            file.write("%%MatrixMarket matrix coordinate integer general\n")
            file.write(f"{matrix.shape[0]} {matrix.shape[1]} {coo.nnz}\n")
            for row, col, value in zip(coo.row, coo.col, coo.data):
                ivalue = int(value)
                if ivalue == 0:
                    continue
                file.write(f"{row + 1} {col + 1} {ivalue}\n")

    @staticmethod
    def _export_listuce(
        uc_groups: List[List[int]],
        filepath: Path,
        id_label: str = "uce",
    ) -> None:
        """Export UCE->UC mapping using IRaMuTeQ listuce format."""
        with open(filepath, "w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow([str(id_label or "uce"), "uc"])
            for uc_idx, uce_ids in enumerate(uc_groups):
                for uce_id in uce_ids:
                    writer.writerow([int(uce_id), uc_idx])
    
    def _export_dense_matrix(
        self,
        matrix: sparse.csr_matrix,
        filepath: Path,
        row_labels: Optional[List[str]] = None,
        col_labels: Optional[List[str]] = None,
    ) -> None:
        """Export matrix as dense semicolon CSV."""
        dense = matrix.toarray()
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            
            # Header row
            if col_labels:
                writer.writerow([''] + col_labels)
            
            # Data rows
            for i, row in enumerate(dense):
                row_label = row_labels[i] if row_labels and i < len(row_labels) else str(i)
                writer.writerow([row_label] + row.tolist())
    
    def _export_vocabulary(self, filepath: Path, 
                           include_freq: bool = False) -> None:
        """Export vocabulary list."""
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f, delimiter=';')
            
            if include_freq:
                writer.writerow(['word', 'freq', 'lem', 'gram'])
                for word in self.vocabulary:
                    if word in self.corpus.formes:
                        w = self.corpus.formes[word]
                        writer.writerow([word, w.freq, w.lem, w.gram])
                    elif word in self.corpus.lems:
                        l = self.corpus.lems[word]
                        writer.writerow([word, l.freq, word, l.gram])
            else:
                for word in self.vocabulary:
                    writer.writerow([word])
    
    # -------------------------------------------------------------------------
    # Statistics
    # -------------------------------------------------------------------------
    
    def get_dtm_stats(self) -> Dict[str, Any]:
        """Get statistics about the document-term matrix."""
        if self.dtm is None:
            return {}
        
        return {
            'n_documents': self.dtm.shape[0],
            'n_words': self.dtm.shape[1],
            'n_nonzero': self.dtm.nnz,
            'sparsity': 1.0 - (self.dtm.nnz / (self.dtm.shape[0] * self.dtm.shape[1])),
            'total_occurrences': self.dtm.sum(),
            'mean_doc_length': self.dtm.sum(axis=1).mean(),
            'mean_word_freq': self.dtm.sum(axis=0).mean(),
        }
