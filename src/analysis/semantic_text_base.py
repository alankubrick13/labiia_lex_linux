"""
Backend compartilhado de preprocessamento semantico.

Consome ``Corpus`` e ``TextProcessor`` do LabiiaLex e expoe:
- tokens filtrados, lemmas, labels, datas, metadados
- matrizes documento x termo e UCE x termo (``csr_matrix``)
- vocabulario filtrado
- iteradores de sentencas

Este modulo pertence a ``src/analysis`` e NAO importa ``src/ui``.
"""

from __future__ import annotations

import logging
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse

from ..core.corpus import Corpus
from ..core.text_processor import TextProcessor
from .semantic_contracts import SemanticAnalysisError

log = logging.getLogger(__name__)

# Pontuacao para strip de tokens
_PUNCT = string.punctuation + "\u201c\u201d\u00ab\u00bb"
_TRANSCRIPT_ROLE_PATTERN = re.compile(
    r"^(?:[A-ZÀ-Ý][A-ZÀ-Ý\s\-]+)(?:\s*\((?:ENTREVISTADOR|ENTREVISTADORA|MEDIADOR|MEDIADORA|PESQUISADOR|PESQUISADORA)\))?\s+"
)
_TIMESTAMP_PATTERN = re.compile(r"^\d{2}:\d{2}:\d{2}\s+")


# ---------------------------------------------------------------------------
# Registros normalizados
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class SemanticDocument:
    """Documento normalizado para analise semantica."""

    doc_id: int
    label: str
    tokens: List[str]
    lemmas: List[str]
    date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, kw_only=True)
class SemanticSegment:
    """Segmento (UCE) normalizado para analise semantica."""

    uce_id: int
    doc_id: int
    text: str
    tokens: List[str]
    lemmas: List[str]


# ---------------------------------------------------------------------------
# Bundle de matrizes esparsas
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class SparseMatrixBundle:
    """Agrupa matrizes esparsas e vocabulario associado."""

    matrix: sparse.csr_matrix
    vocabulary: List[str]
    row_ids: List[int]
    word_to_idx: Dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.word_to_idx:
            self.word_to_idx = {w: i for i, w in enumerate(self.vocabulary)}


# ---------------------------------------------------------------------------
# SemanticTextBundle — ponto central de preprocessamento
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class SemanticTextBundle:
    """Bundle de preprocessamento semantico.

    Construido a partir de ``Corpus`` + ``TextProcessor`` via
    ``from_corpus(...)``.  Expoe documentos, segmentos, matrizes
    esparsas e iteradores para consumo pelos servicos semanticos.
    """

    documents: List[SemanticDocument]
    segments: List[SemanticSegment]
    vocabulary: List[str]
    doc_term_matrix: Optional[SparseMatrixBundle] = None
    uce_term_matrix: Optional[SparseMatrixBundle] = None
    doc_id_to_label: Dict[int, str] = field(default_factory=dict)
    detected_speaker_tokens: List[str] = field(default_factory=list)

    # ----- factory principal -------------------------------------------------

    @classmethod
    def from_corpus(
        cls,
        corpus: Corpus,
        *,
        min_freq: int = 2,
        use_lemmas: bool = True,
        max_features: int = 2000,
    ) -> "SemanticTextBundle":
        """Constroi bundle a partir de um Corpus do LabiiaLex.

        Parameters
        ----------
        corpus:
            Corpus ja importado e processado.
        min_freq:
            Frequencia minima para inclusao no vocabulario.
        use_lemmas:
            Usar lemas em vez de formas brutas.
        max_features:
            Maximo de features no vocabulario (0 = ilimitado).

        Returns
        -------
        SemanticTextBundle
            Bundle pronto para consumo por LDA, YAKE, Heatmap etc.

        Raises
        ------
        SemanticAnalysisError
            Se o corpus nao tiver dados suficientes.
        """
        if corpus is None:
            raise SemanticAnalysisError(
                what="Corpus nulo.",
                why="Nenhum corpus foi fornecido para preprocessamento.",
                how="Importe um corpus antes de executar a analise.",
            )

        processor = TextProcessor(corpus)

        # Construir DTM no nivel de UCE
        try:
            processor.build_dtm(
                min_freq=min_freq,
                use_lemmas=use_lemmas,
                active_only=True,
                max_actives=max_features,
            )
        except Exception as exc:
            raise SemanticAnalysisError(
                what="Falha ao construir a matriz documento-termo.",
                why=str(exc),
                how="Verifique se o corpus tem texto suficiente e reduza min_freq se necessario.",
            ) from exc

        vocabulary = list(processor.vocabulary)
        word_to_idx = dict(processor._word_to_idx)

        # Montar documentos normalizados
        documents: List[SemanticDocument] = []
        doc_id_to_label: Dict[int, str] = {}

        for uci in corpus.ucis:
            doc_id = int(uci.ident)
            # Extrair label a partir de metadados
            paras = getattr(uci, "paras", {}) or {}
            label = str(
                paras.get("title", "")
                or paras.get("name", "")
                or paras.get("label", "")
                or f"Doc_{doc_id}"
            )
            date = str(paras.get("date", "") or "")
            metadata = {str(k): v for k, v in paras.items()} if paras else {}

            # Coletar tokens de todas UCEs deste UCI
            uce_ids = [int(uce.ident) for uce in uci.uces]
            doc_tokens: List[str] = []
            doc_lemmas: List[str] = []
            for _uce_id, text in corpus.getconcorde(uce_ids):
                clean_text = _strip_transcript_artifacts(str(text or ""))
                for word in clean_text.lower().split():
                    clean = word.strip(_PUNCT)
                    if not clean:
                        continue
                    doc_tokens.append(clean)
                    # Tentar resolver lema
                    forme = corpus.formes.get(clean)
                    if forme is not None and getattr(forme, "lem", None):
                        doc_lemmas.append(str(forme.lem))
                    else:
                        doc_lemmas.append(clean)

            documents.append(SemanticDocument(
                doc_id=doc_id,
                label=label,
                tokens=doc_tokens,
                lemmas=doc_lemmas,
                date=date if date else None,
                metadata=metadata,
            ))
            doc_id_to_label[doc_id] = label

        # Mapa de UCE -> UCI para otimização O(N) em vez de O(N^2)
        uce_id_to_uci_id: Dict[int, int] = {}
        for uci in corpus.ucis:
            uci_id = int(uci.ident)
            for uce in uci.uces:
                uce_id_to_uci_id[int(uce.ident)] = uci_id

        # Montar segmentos normalizados
        segments: List[SemanticSegment] = []
        detected_speaker_tokens: set[str] = set()
        for uce_text_tuple in corpus.get_uces():
            uce_id, text = uce_text_tuple
            uce_id_int = int(uce_id)
            # Encontrar doc_id pai via mapa O(1)
            parent_doc_id = uce_id_to_uci_id.get(uce_id_int, 0)
            raw_text = str(text or "")
            detected_speaker_tokens.update(_extract_transcript_speaker_tokens(raw_text))
            clean_text = _strip_transcript_artifacts(raw_text)
            seg_tokens: List[str] = []
            seg_lemmas: List[str] = []
            for word in clean_text.lower().split():
                clean = word.strip(_PUNCT)
                if not clean:
                    continue
                seg_tokens.append(clean)
                forme = corpus.formes.get(clean)
                if forme is not None and getattr(forme, "lem", None):
                    seg_lemmas.append(str(forme.lem))
                else:
                    seg_lemmas.append(clean)

            segments.append(SemanticSegment(
                uce_id=int(uce_id),
                doc_id=parent_doc_id,
                text=clean_text,
                tokens=seg_tokens,
                lemmas=seg_lemmas,
            ))

        # Montar SparseMatrixBundle para UCE x termo (ja produzido pelo processor)
        uce_matrix_bundle = SparseMatrixBundle(
            matrix=processor.dtm,
            vocabulary=vocabulary,
            row_ids=list(processor.doc_ids),
            word_to_idx=word_to_idx,
        )

        # Montar SparseMatrixBundle para documento (UCI) x termo
        doc_matrix_bundle = _build_document_term_matrix(
            corpus=corpus,
            vocabulary=vocabulary,
            word_to_idx=word_to_idx,
            use_lemmas=use_lemmas,
        )

        return cls(
            documents=documents,
            segments=segments,
            vocabulary=vocabulary,
            doc_term_matrix=doc_matrix_bundle,
            uce_term_matrix=uce_matrix_bundle,
            doc_id_to_label=doc_id_to_label,
            detected_speaker_tokens=sorted(detected_speaker_tokens),
        )

    # ----- utilidades --------------------------------------------------------

    def iter_sentences(self) -> Iterator[Tuple[int, str]]:
        """Itera (uce_id, texto) sobre todos os segmentos."""
        for seg in self.segments:
            yield seg.uce_id, seg.text

    def get_document_tokens(self, use_lemmas: bool = True) -> List[List[str]]:
        """Retorna tokens por documento (para CountVectorizer etc)."""
        if use_lemmas:
            return [doc.lemmas for doc in self.documents]
        return [doc.tokens for doc in self.documents]

    def get_segment_tokens(self, use_lemmas: bool = True) -> List[List[str]]:
        """Retorna tokens por segmento (UCE)."""
        if use_lemmas:
            return [seg.lemmas for seg in self.segments]
        return [seg.tokens for seg in self.segments]

    @property
    def n_documents(self) -> int:
        return len(self.documents)

    @property
    def n_segments(self) -> int:
        return len(self.segments)

    @property
    def n_features(self) -> int:
        return len(self.vocabulary)

    def has_temporal_data(self) -> bool:
        """Verifica se ao menos 3 documentos tem data valida."""
        count = sum(1 for doc in self.documents if doc.date)
        return count >= 3


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _find_parent_doc_id(corpus, uce_id: int) -> int:
    """Return parent UCI doc_id for a UCE index; 0 if not found."""
    for uci in corpus.ucis:
        for uce in uci.uces:
            if int(uce.ident) == uce_id:
                return int(uci.ident)
    return 0


def _strip_transcript_artifacts(text: str) -> str:
    """Remove timestamps e rótulos de falante no início do segmento."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    cleaned = _TIMESTAMP_PATTERN.sub("", cleaned)
    cleaned = _TRANSCRIPT_ROLE_PATTERN.sub("", cleaned)
    return cleaned.strip()


def _extract_transcript_speaker_tokens(text: str) -> List[str]:
    """Extrai tokens de falante a partir do prefixo de transcrição, se houver."""
    cleaned = str(text or "").strip()
    if not cleaned:
        return []
    without_ts = _TIMESTAMP_PATTERN.sub("", cleaned)
    match = _TRANSCRIPT_ROLE_PATTERN.match(without_ts)
    if not match:
        return []
    speaker_label = match.group(0).strip()
    speaker_label = re.sub(r"\(.*?\)", " ", speaker_label)
    tokens = [
        token.lower()
        for token in re.findall(r"[A-ZÀ-Ý][A-ZÀ-Ý\-]+", speaker_label)
        if len(token) > 1
    ]
    return tokens


def _build_document_term_matrix(
    corpus: Corpus,
    vocabulary: List[str],
    word_to_idx: Dict[str, int],
    use_lemmas: bool,
) -> SparseMatrixBundle:
    """Constroi matriz documento (UCI) x termo a partir do vocabulario dado."""
    rows: List[int] = []
    cols: List[int] = []
    data: List[int] = []
    doc_ids: List[int] = []

    for row_idx, uci in enumerate(corpus.ucis):
        doc_id = int(uci.ident)
        doc_ids.append(doc_id)

        uce_ids_local = [int(uce.ident) for uce in uci.uces]
        if not uce_ids_local:
            continue

        word_counts: Dict[str, int] = {}
        for _uce_id, text in corpus.getconcorde(uce_ids_local):
            clean_text = _strip_transcript_artifacts(str(text or ""))
            for word in clean_text.lower().split():
                clean = word.strip(_PUNCT)
                if not clean:
                    continue
                token = clean
                if use_lemmas:
                    forme = corpus.formes.get(clean)
                    if forme is not None and getattr(forme, "lem", None):
                        token = str(forme.lem)
                if token in word_to_idx:
                    word_counts[token] = word_counts.get(token, 0) + 1

        for token, count in word_counts.items():
            rows.append(row_idx)
            cols.append(word_to_idx[token])
            data.append(count)

    n_docs = len(doc_ids)
    n_words = len(vocabulary)

    matrix = sparse.csr_matrix(
        (data, (rows, cols)),
        shape=(n_docs, n_words),
        dtype=np.float64,
    )

    return SparseMatrixBundle(
        matrix=matrix,
        vocabulary=vocabulary,
        row_ids=doc_ids,
        word_to_idx=word_to_idx,
    )
