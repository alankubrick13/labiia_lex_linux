"""
Servico de modelagem de topicos (LDA).

Backend principal: R/topicmodels (VEM ou Gibbs).
Fallback de compatibilidade: pacote Python ``lda`` quando disponivel; caso
contrario usa ``sklearn.decomposition.LatentDirichletAllocation``.

Pertence a ``src/analysis`` — NAO importa ``src/ui``.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse

from ..core.r_executor import RExecutionError, RExecutor, RNotFoundError, RTimeoutError
from ..utils.paths import PathManager
from .semantic_contracts import SemanticAnalysisError

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dados de saida
# ---------------------------------------------------------------------------


@dataclass(slots=True, kw_only=True)
class TopicTerms:
    """Termos de um topico com pesos."""

    topic_id: int
    label: str
    terms: List[Tuple[str, float]]  # (term, weight)


@dataclass(slots=True, kw_only=True)
class DocTopicRow:
    """Distribuicao de topicos de um documento."""

    doc_id: int
    doc_label: str
    topic_probabilities: List[float]  # alinhado com topic_ids


@dataclass(slots=True, kw_only=True)
class LDAModelResult:
    """Resultado bruto do treino LDA."""

    topic_terms: List[TopicTerms]
    doc_topic_rows: List[DocTopicRow]
    perplexity: Optional[float]
    n_topics: int
    topic_labels: List[str]
    doc_topic_matrix: np.ndarray  # (n_docs, n_topics)
    backend: str = "python_lda_gibbs"
    method: str = "Gibbs"
    k_requested: Optional[int] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    tuning_rows: List[Dict[str, Any]] = field(default_factory=list)
    tuning_available: bool = False


# ---------------------------------------------------------------------------
# Backend R clássico (topicmodels)
# ---------------------------------------------------------------------------


def train_lda_classic(
    dtm: sparse.csr_matrix,
    vocabulary: Sequence[str],
    doc_ids: Sequence[int],
    doc_labels: Sequence[str],
    *,
    output_dir: Path,
    k: int = 10,
    method: str = "VEM",
    seed: int = 42,
    gibbs_burnin: int = 1000,
    gibbs_iter: int = 1000,
    gibbs_thin: int = 100,
    n_top_terms: int = 15,
    enable_tuning: bool = False,
    k_min: int = 2,
    k_max: int = 20,
    fallback_to_python: bool = True,
) -> LDAModelResult:
    """Treina LDA via topicmodels (R), com fallback opcional para backend Python."""

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if dtm is None or dtm.shape[0] < 2 or dtm.shape[1] < 2:
        raise SemanticAnalysisError(
            what="Corpus insuficiente para LDA.",
            why=f"DTM tem forma {dtm.shape if dtm is not None else 'None'}; "
            "sao necessarios ao menos 2 documentos e 2 termos.",
            how="Adicione mais documentos ou reduza min_freq.",
        )

    try:
        return _train_lda_with_topicmodels_r(
            dtm=dtm,
            vocabulary=vocabulary,
            doc_ids=doc_ids,
            doc_labels=doc_labels,
            output_dir=output_dir,
            k=k,
            method=method,
            seed=seed,
            gibbs_burnin=gibbs_burnin,
            gibbs_iter=gibbs_iter,
            gibbs_thin=gibbs_thin,
            n_top_terms=n_top_terms,
            enable_tuning=enable_tuning,
            k_min=k_min,
            k_max=k_max,
        )
    except SemanticAnalysisError:
        if not fallback_to_python:
            raise
        log.warning("Falha no backend LDA via R/topicmodels; usando fallback Python.", exc_info=True)
    except Exception as exc:
        if not fallback_to_python:
            raise SemanticAnalysisError(
                what="Falha inesperada no backend LDA em R.",
                why=str(exc) or exc.__class__.__name__,
                how="Verifique instalação do R/topicmodels ou use fallback Python.",
            ) from exc
        log.warning("Falha inesperada no backend R LDA; usando fallback Python.", exc_info=True)

    # Fallback robusto: backend atual Python (lda-project).
    n_terms = int(dtm.shape[1])
    k_effective = max(1, min(int(k), n_terms))
    py_result = train_lda(
        dtm=dtm,
        vocabulary=vocabulary,
        doc_ids=doc_ids,
        doc_labels=doc_labels,
        n_topics=k_effective,
        n_iter=max(50, int(gibbs_iter)),
        random_state=int(seed),
        n_top_terms=n_top_terms,
    )
    py_result.backend = "python_lda_gibbs_fallback"
    py_result.method = "Gibbs"
    py_result.k_requested = int(k)
    py_result.diagnostics = {
        "fallback_reason": "topicmodels_unavailable_or_failed",
        "tuning_requested": bool(enable_tuning),
        "tuning_available": False,
    }
    py_result.tuning_rows = []
    py_result.tuning_available = False
    return py_result


def _train_lda_with_topicmodels_r(
    *,
    dtm: sparse.csr_matrix,
    vocabulary: Sequence[str],
    doc_ids: Sequence[int],
    doc_labels: Sequence[str],
    output_dir: Path,
    k: int,
    method: str,
    seed: int,
    gibbs_burnin: int,
    gibbs_iter: int,
    gibbs_thin: int,
    n_top_terms: int,
    enable_tuning: bool,
    k_min: int,
    k_max: int,
) -> LDAModelResult:
    input_csv = output_dir / "lda_dtm_input.csv"
    args_json = output_dir / "lda_topicmodels_args.json"

    topics_csv = output_dir / "lda_topics.csv"
    doc_topic_csv = output_dir / "lda_doc_topic.csv"
    terms_beta_csv = output_dir / "lda_terms_beta.csv"
    documents_gamma_csv = output_dir / "lda_documents_gamma.csv"
    summary_json = output_dir / "lda_summary.json"
    tuning_csv = output_dir / "lda_tuning.csv"

    _write_dtm_csv(
        path=input_csv,
        dtm=dtm,
        vocabulary=vocabulary,
        doc_ids=doc_ids,
        doc_labels=doc_labels,
    )

    n_terms = int(dtm.shape[1])
    safe_k = max(1, int(k))
    method_norm = str(method or "VEM").strip().upper()
    if method_norm not in {"VEM", "GIBBS"}:
        method_norm = "VEM"

    args_payload: Dict[str, Any] = {
        "input_dtm_csv": str(input_csv),
        "output_topics_csv": str(topics_csv),
        "output_doc_topic_csv": str(doc_topic_csv),
        "output_terms_beta_csv": str(terms_beta_csv),
        "output_documents_gamma_csv": str(documents_gamma_csv),
        "output_summary_json": str(summary_json),
        "output_tuning_csv": str(tuning_csv),
        "k_requested": safe_k,
        "k_effective": min(safe_k, n_terms),
        "seed": int(seed),
        "method": method_norm,
        "gibbs_burnin": max(0, int(gibbs_burnin)),
        "gibbs_iter": max(50, int(gibbs_iter)),
        "gibbs_thin": max(1, int(gibbs_thin)),
        "n_top_terms": max(3, int(n_top_terms)),
        "enable_tuning": bool(enable_tuning),
        "k_min": max(2, int(k_min)),
        "k_max": max(2, int(k_max)),
    }
    args_json.write_text(json.dumps(args_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    script_path = PathManager.rscripts_dir() / "lda_topicmodels.R"
    if not script_path.exists():
        raise SemanticAnalysisError(
            what="Script R do LDA não encontrado.",
            why=f"O arquivo esperado não existe em {script_path}.",
            how="Restaure Rscripts/lda_topicmodels.R e execute novamente.",
        )

    try:
        executor = RExecutor()
    except RNotFoundError as exc:
        raise SemanticAnalysisError(
            what="Rscript não disponível para LDA clássico.",
            why=str(exc),
            how="Instale o R e configure o caminho em Ajustes > Caminho do R.",
        ) from exc

    required_packages = ["topicmodels", "jsonlite", "slam"]
    status = executor.check_packages(required_packages)
    missing = [pkg for pkg, ok in status.items() if not ok]
    if missing:
        raise SemanticAnalysisError(
            what="Pacotes R obrigatórios do LDA não estão disponíveis.",
            why=f"Pacotes ausentes: {', '.join(missing)}",
            how="Instale manualmente topicmodels/jsonlite/slam no R ou use fallback Python.",
        )

    try:
        executor.execute_with_args(
            script_path=str(script_path),
            args=[str(args_json)],
            working_dir=str(output_dir),
            timeout=900,
        )
    except (RExecutionError, RTimeoutError, FileNotFoundError) as exc:
        raise SemanticAnalysisError(
            what="Falha ao executar o backend R do LDA.",
            why=str(exc) or exc.__class__.__name__,
            how="Verifique topicmodels e parâmetros de execução (k/method/iter).",
        ) from exc

    return _load_r_lda_outputs(
        topics_csv=topics_csv,
        doc_topic_csv=doc_topic_csv,
        summary_json=summary_json,
        tuning_csv=tuning_csv,
    )


def _write_dtm_csv(
    *,
    path: Path,
    dtm: sparse.csr_matrix,
    vocabulary: Sequence[str],
    doc_ids: Sequence[int],
    doc_labels: Sequence[str],
) -> None:
    dense = dtm.toarray().astype(np.int64)
    vocab = [str(term) for term in vocabulary]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["Doc_ID", "Label", *vocab])
        for i in range(dense.shape[0]):
            doc_id = int(doc_ids[i]) if i < len(doc_ids) else int(i)
            doc_label = str(doc_labels[i]) if i < len(doc_labels) else f"Doc_{doc_id}"
            row = [doc_id, doc_label, *[int(x) for x in dense[i].tolist()]]
            writer.writerow(row)


def _load_r_lda_outputs(
    *,
    topics_csv: Path,
    doc_topic_csv: Path,
    summary_json: Path,
    tuning_csv: Path,
) -> LDAModelResult:
    if not topics_csv.exists() or not doc_topic_csv.exists():
        raise SemanticAnalysisError(
            what="Saídas do LDA em R estão incompletas.",
            why="Os arquivos principais (lda_topics.csv / lda_doc_topic.csv) não foram gerados.",
            how="Revise logs do Rscript e tente novamente.",
        )

    summary_payload: Dict[str, Any] = {}
    if summary_json.exists():
        try:
            summary_payload = json.loads(summary_json.read_text(encoding="utf-8"))
        except Exception:
            summary_payload = {}

    topic_terms_by_id: Dict[int, TopicTerms] = {}
    with topics_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            try:
                topic_id = int(float(row.get("Topic_ID", 0)))
            except Exception:
                continue
            topic_label = str(row.get("Topic_Label", f"T{topic_id + 1}") or f"T{topic_id + 1}")
            term = str(row.get("Term", "") or "").strip()
            if not term:
                continue
            try:
                weight = float(row.get("Weight", 0.0) or 0.0)
            except Exception:
                weight = 0.0
            if topic_id not in topic_terms_by_id:
                topic_terms_by_id[topic_id] = TopicTerms(
                    topic_id=topic_id,
                    label=topic_label,
                    terms=[],
                )
            topic_terms_by_id[topic_id].terms.append((term, float(weight)))

    topic_terms: List[TopicTerms] = []
    for topic_id in sorted(topic_terms_by_id.keys()):
        item = topic_terms_by_id[topic_id]
        item.terms.sort(key=lambda pair: pair[1], reverse=True)
        topic_terms.append(item)

    doc_topic_rows: List[DocTopicRow] = []
    matrix_rows: List[List[float]] = []
    topic_labels: List[str] = []
    n_topics = 0

    with doc_topic_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        if reader.fieldnames:
            topic_cols = [name for name in reader.fieldnames if str(name).startswith("T")]
            n_topics = len(topic_cols)
        else:
            topic_cols = []

        for idx, row in enumerate(reader):
            try:
                doc_id = int(float(row.get("Doc_ID", idx) or idx))
            except Exception:
                doc_id = idx
            doc_label = str(row.get("Label", f"Doc_{doc_id}") or f"Doc_{doc_id}")
            probs: List[float] = []
            for col in topic_cols:
                try:
                    probs.append(float(row.get(col, 0.0) or 0.0))
                except Exception:
                    probs.append(0.0)
            if probs:
                total = float(sum(probs))
                if total > 0:
                    probs = [max(0.0, p / total) for p in probs]
            doc_topic_rows.append(
                DocTopicRow(
                    doc_id=doc_id,
                    doc_label=doc_label,
                    topic_probabilities=probs,
                )
            )
            matrix_rows.append(probs)

    if n_topics <= 0:
        n_topics = int(summary_payload.get("k_effective") or summary_payload.get("n_topics") or 0)
    if n_topics <= 0 and topic_terms:
        n_topics = max(tt.topic_id for tt in topic_terms) + 1
    if n_topics <= 0:
        raise SemanticAnalysisError(
            what="Número de tópicos inválido nas saídas do LDA.",
            why="Não foi possível inferir k efetivo dos artefatos gerados.",
            how="Revise o script R e execute novamente.",
        )

    if matrix_rows:
        doc_topic_matrix = np.asarray(matrix_rows, dtype=float)
    else:
        doc_topic_matrix = np.zeros((0, n_topics), dtype=float)

    topic_labels = [f"T{i + 1}" for i in range(n_topics)]
    for tt in topic_terms:
        if 0 <= tt.topic_id < n_topics:
            topic_labels[tt.topic_id] = tt.label

    perplexity_value = summary_payload.get("perplexity")
    try:
        perplexity = float(perplexity_value) if perplexity_value is not None else None
    except Exception:
        perplexity = None

    tuning_rows: List[Dict[str, Any]] = []
    if tuning_csv.exists():
        try:
            with tuning_csv.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                for row in reader:
                    parsed: Dict[str, Any] = {}
                    for key, value in row.items():
                        key_name = str(key or "").strip()
                        raw = str(value or "").strip()
                        if not key_name:
                            continue
                        if raw == "":
                            parsed[key_name] = None
                            continue
                        if key_name == "k":
                            try:
                                parsed[key_name] = int(float(raw))
                                continue
                            except Exception:
                                pass
                        try:
                            parsed[key_name] = float(raw)
                        except Exception:
                            parsed[key_name] = raw
                    if parsed:
                        tuning_rows.append(parsed)
        except Exception:
            tuning_rows = []

    backend_name = str(summary_payload.get("backend", "r_topicmodels") or "r_topicmodels")
    method_name = str(summary_payload.get("method", "VEM") or "VEM")
    k_requested_raw = summary_payload.get("k_requested")
    try:
        k_requested = int(k_requested_raw) if k_requested_raw is not None else n_topics
    except Exception:
        k_requested = n_topics

    diagnostics = dict(summary_payload.get("diagnostics", {}) or {})
    diagnostics.setdefault("summary_path", str(summary_json) if summary_json.exists() else "")
    diagnostics.setdefault("topics_csv_path", str(topics_csv))
    diagnostics.setdefault("doc_topic_csv_path", str(doc_topic_csv))
    diagnostics.setdefault("tuning_csv_path", str(tuning_csv) if tuning_csv.exists() else "")

    return LDAModelResult(
        topic_terms=topic_terms,
        doc_topic_rows=doc_topic_rows,
        perplexity=perplexity,
        n_topics=n_topics,
        topic_labels=topic_labels,
        doc_topic_matrix=doc_topic_matrix,
        backend=backend_name,
        method=method_name,
        k_requested=k_requested,
        diagnostics=diagnostics,
        tuning_rows=tuning_rows,
        tuning_available=bool(tuning_rows),
    )


# ---------------------------------------------------------------------------
# Backend Python legado (compatibilidade/fallback)
# ---------------------------------------------------------------------------


def train_lda(
    dtm: sparse.csr_matrix,
    vocabulary: Sequence[str],
    doc_ids: Sequence[int],
    doc_labels: Sequence[str],
    *,
    n_topics: int = 6,
    n_iter: int = 200,
    random_state: int = 42,
    n_top_terms: int = 15,
) -> LDAModelResult:
    """Treina modelo LDA com backend Python de fallback."""
    try:
        import lda as lda_lib
    except ImportError:
        return _train_lda_with_sklearn(
            dtm=dtm,
            vocabulary=vocabulary,
            doc_ids=doc_ids,
            doc_labels=doc_labels,
            n_topics=n_topics,
            n_iter=n_iter,
            random_state=random_state,
            n_top_terms=n_top_terms,
        )

    if dtm is None or dtm.shape[0] < 2 or dtm.shape[1] < 2:
        raise SemanticAnalysisError(
            what="Corpus insuficiente para LDA.",
            why=f"DTM tem forma {dtm.shape if dtm is not None else 'None'}; "
            "sao necessarios ao menos 2 documentos e 2 termos.",
            how="Adicione mais documentos ou reduza min_freq.",
        )

    n_docs, n_terms = dtm.shape
    actual_topics = min(n_topics, n_terms)

    dtm_int = dtm.toarray().astype(np.int32)

    model = lda_lib.LDA(
        n_topics=actual_topics,
        n_iter=n_iter,
        random_state=random_state,
    )
    model.fit(dtm_int)
    doc_topic_matrix: np.ndarray = model.doc_topic_

    vocab_array = list(vocabulary)
    topic_terms_list: List[TopicTerms] = []
    topic_labels: List[str] = []

    for topic_idx in range(actual_topics):
        component = model.topic_word_[topic_idx]
        top_indices = component.argsort()[::-1][:n_top_terms]
        terms = [(vocab_array[idx], float(component[idx])) for idx in top_indices]
        label = " / ".join(vocab_array[top_indices[k]] for k in range(min(3, len(top_indices))))
        topic_terms_list.append(
            TopicTerms(topic_id=topic_idx, label=label, terms=terms)
        )
        topic_labels.append(label)

    doc_topic_rows: List[DocTopicRow] = []
    for doc_idx in range(n_docs):
        doc_id = int(doc_ids[doc_idx]) if doc_idx < len(doc_ids) else doc_idx
        doc_label = str(doc_labels[doc_idx]) if doc_idx < len(doc_labels) else f"Doc_{doc_id}"
        probabilities = [float(doc_topic_matrix[doc_idx, t]) for t in range(actual_topics)]
        doc_topic_rows.append(
            DocTopicRow(
                doc_id=doc_id,
                doc_label=doc_label,
                topic_probabilities=probabilities,
            )
        )

    return LDAModelResult(
        topic_terms=topic_terms_list,
        doc_topic_rows=doc_topic_rows,
        perplexity=None,
        n_topics=actual_topics,
        topic_labels=topic_labels,
        doc_topic_matrix=doc_topic_matrix,
        backend="python_lda_gibbs",
        method="Gibbs",
        k_requested=actual_topics,
    )


def _train_lda_with_sklearn(
    dtm: sparse.csr_matrix,
    vocabulary: Sequence[str],
    doc_ids: Sequence[int],
    doc_labels: Sequence[str],
    *,
    n_topics: int,
    n_iter: int,
    random_state: int,
    n_top_terms: int,
) -> LDAModelResult:
    """Fallback LDA baseado em scikit-learn para builds sem ``lda`` nativo."""
    try:
        from sklearn.decomposition import LatentDirichletAllocation
    except ImportError:
        raise SemanticAnalysisError(
            what="Backend Python de LDA nao esta instalado.",
            why="Nem o pacote lda nem scikit-learn estao disponiveis.",
            how="Instale scikit-learn ou corrija o backend R/topicmodels.",
        )

    if dtm is None or dtm.shape[0] < 2 or dtm.shape[1] < 2:
        raise SemanticAnalysisError(
            what="Corpus insuficiente para LDA.",
            why=f"DTM tem forma {dtm.shape if dtm is not None else 'None'}; "
            "sao necessarios ao menos 2 documentos e 2 termos.",
            how="Adicione mais documentos ou reduza min_freq.",
        )

    n_docs, n_terms = dtm.shape
    actual_topics = min(n_topics, n_terms)

    model = LatentDirichletAllocation(
        n_components=actual_topics,
        max_iter=max(1, int(n_iter)),
        learning_method="batch",
        random_state=random_state,
        evaluate_every=-1,
    )
    doc_topic_matrix = model.fit_transform(dtm)
    row_sums = doc_topic_matrix.sum(axis=1, keepdims=True)
    doc_topic_matrix = np.divide(
        doc_topic_matrix,
        row_sums,
        out=np.zeros_like(doc_topic_matrix, dtype=float),
        where=row_sums > 0,
    )
    topic_word = np.asarray(model.components_, dtype=float)
    topic_sums = topic_word.sum(axis=1, keepdims=True)
    topic_word = np.divide(
        topic_word,
        topic_sums,
        out=np.zeros_like(topic_word, dtype=float),
        where=topic_sums > 0,
    )

    vocab_array = list(vocabulary)
    topic_terms_list: List[TopicTerms] = []
    topic_labels: List[str] = []

    for topic_idx in range(actual_topics):
        component = topic_word[topic_idx]
        top_indices = component.argsort()[::-1][:n_top_terms]
        terms = [(vocab_array[idx], float(component[idx])) for idx in top_indices]
        label = " / ".join(vocab_array[top_indices[k]] for k in range(min(3, len(top_indices))))
        topic_terms_list.append(
            TopicTerms(topic_id=topic_idx, label=label, terms=terms)
        )
        topic_labels.append(label)

    doc_topic_rows: List[DocTopicRow] = []
    for doc_idx in range(n_docs):
        doc_id = int(doc_ids[doc_idx]) if doc_idx < len(doc_ids) else doc_idx
        doc_label = str(doc_labels[doc_idx]) if doc_idx < len(doc_labels) else f"Doc_{doc_id}"
        probabilities = [float(doc_topic_matrix[doc_idx, t]) for t in range(actual_topics)]
        doc_topic_rows.append(
            DocTopicRow(
                doc_id=doc_id,
                doc_label=doc_label,
                topic_probabilities=probabilities,
            )
        )

    return LDAModelResult(
        topic_terms=topic_terms_list,
        doc_topic_rows=doc_topic_rows,
        perplexity=float(model.perplexity(dtm)),
        n_topics=actual_topics,
        topic_labels=topic_labels,
        doc_topic_matrix=doc_topic_matrix,
        backend="python_sklearn_lda_fallback",
        method="VEM",
        k_requested=actual_topics,
        diagnostics={"fallback_backend": "sklearn"},
    )


def generate_topic_labels(
    topic_terms: List[TopicTerms],
    *,
    n_words: int = 3,
) -> List[str]:
    """Gera labels curtos para cada topico a partir dos top termos."""
    labels: List[str] = []
    for tt in topic_terms:
        top_words = [term for term, _weight in tt.terms[:n_words]]
        labels.append(" / ".join(top_words))
    return labels
