"""
Metricas de associacao lexical.

Funcoes puras para coocorrencia, PPMI e ranking de pares,
operando sobre matrizes esparsas (``csr_matrix``).

Pertence a ``src/analysis`` — NAO importa ``src/ui``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Coocorrencia
# ---------------------------------------------------------------------------

def build_cooccurrence_matrix(
    dtm: sparse.csr_matrix,
) -> sparse.csr_matrix:
    """Constroi matriz de coocorrencia termo x termo a partir de DTM.

    Cada celula (i, j) conta o numero de documentos / UCEs em que
    ambos os termos i e j aparecem simultaneamente.

    Parameters
    ----------
    dtm:
        Matriz documento x termo (csr_matrix).

    Returns
    -------
    sparse.csr_matrix
        Matriz simetrica termo x termo (n_terms x n_terms).
    """
    # Binarizar: presenca/ausencia por documento
    binary = dtm.copy()
    binary.data = np.ones_like(binary.data)
    binary = binary.astype(np.float64)

    # Coocorrencia = binario^T @ binario
    cooc = (binary.T @ binary).tocsr()

    # Remover auto-coocorrencia (diagonal)
    cooc.setdiag(0)
    cooc.eliminate_zeros()

    return cooc


# ---------------------------------------------------------------------------
# PPMI
# ---------------------------------------------------------------------------

def compute_ppmi(
    cooc: sparse.csr_matrix,
    *,
    alpha: float = 0.75,
) -> sparse.csr_matrix:
    """Calcula PPMI (Positive Pointwise Mutual Information) a partir de coocorrencia.

    Parameters
    ----------
    cooc:
        Matriz de coocorrencia (simetrica, termos x termos).
    alpha:
        Expoente de suavizacao para contextos (context distribution smoothing).
        Default 0.75 (standard in word2vec literature).

    Returns
    -------
    sparse.csr_matrix
        Matriz PPMI (mesma forma).
    """
    cooc_coo = cooc.tocoo().astype(np.float64)

    total = cooc_coo.data.sum()
    if total == 0:
        return sparse.csr_matrix(cooc.shape, dtype=np.float64)

    # Frequencias marginais
    row_sums = np.array(cooc.sum(axis=1)).flatten()
    col_sums = np.array(cooc.sum(axis=0)).flatten()

    # Suavizacao de contexto
    col_smoothed = np.power(col_sums, alpha)
    col_smoothed_total = col_smoothed.sum()

    # Calcular PMI para cada par nao-nulo
    ppmi_data = np.zeros_like(cooc_coo.data)
    for idx in range(len(cooc_coo.data)):
        i = cooc_coo.row[idx]
        j = cooc_coo.col[idx]
        p_ij = cooc_coo.data[idx] / total
        p_i = row_sums[i] / total
        p_j_smooth = col_smoothed[j] / col_smoothed_total

        if p_i > 0 and p_j_smooth > 0 and p_ij > 0:
            pmi = np.log2(p_ij / (p_i * p_j_smooth))
            ppmi_data[idx] = max(0.0, pmi)

    result = sparse.csr_matrix(
        (ppmi_data, (cooc_coo.row, cooc_coo.col)),
        shape=cooc.shape,
        dtype=np.float64,
    )
    result.eliminate_zeros()
    return result


# ---------------------------------------------------------------------------
# Ranking de pares
# ---------------------------------------------------------------------------

@dataclass(slots=True, kw_only=True)
class AssociationPair:
    """Par de termos com metricas de associacao."""

    term_a: str
    term_b: str
    cooccurrence: int
    ppmi: float
    doc_count: int = 0


def rank_association_pairs(
    cooc: sparse.csr_matrix,
    ppmi: sparse.csr_matrix,
    vocabulary: Sequence[str],
    *,
    top_n: int = 200,
    min_cooc: int = 2,
) -> List[AssociationPair]:
    """Ranqueia pares de termos por peso associativo (PPMI).

    Parameters
    ----------
    cooc:
        Matriz de coocorrencia.
    ppmi:
        Matriz PPMI.
    vocabulary:
        Lista de termos (indice alinhado com colunas da matriz).
    top_n:
        Numero maximo de pares retornados.
    min_cooc:
        Coocorrencia minima para inclusao.

    Returns
    -------
    List[AssociationPair]
        Pares ordenados por PPMI decrescente. Na triangular superior apenas.
    """
    # Trabalhar apenas na triangular superior para evitar duplicatas
    ppmi_triu = sparse.triu(ppmi, k=1).tocoo()
    cooc_dense_lookup = cooc.tocsr()

    pairs: List[AssociationPair] = []
    for idx in range(len(ppmi_triu.data)):
        i = ppmi_triu.row[idx]
        j = ppmi_triu.col[idx]
        ppmi_val = float(ppmi_triu.data[idx])

        if ppmi_val <= 0:
            continue

        cooc_val = int(cooc_dense_lookup[i, j])
        if cooc_val < min_cooc:
            continue

        pairs.append(AssociationPair(
            term_a=str(vocabulary[i]),
            term_b=str(vocabulary[j]),
            cooccurrence=cooc_val,
            ppmi=ppmi_val,
            doc_count=cooc_val,  # doc_count = cooccurrence in binary DTM
        ))

    # Ordenar por PPMI decrescente
    pairs.sort(key=lambda p: (-p.ppmi, -p.cooccurrence))
    return pairs[:top_n]
