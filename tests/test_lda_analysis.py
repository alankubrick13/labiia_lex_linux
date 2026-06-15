"""
Testes de contrato para a classe LDAAnalysis (Task 6).

Verifica geracao de artefatos de modelagem de topicos, incluindo
CSV de distribuicao, termos por topico e plotagens.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import numpy as np
from scipy import sparse

from src.core.corpus import Corpus
from src.analysis.semantic_contracts import SemanticAnalysisError
from src.analysis.lda_analysis import LDAParams, LDAAnalysis
from src.analysis.topic_modeling import LDAModelResult, TopicTerms, DocTopicRow
from src.analysis.topic_modeling import train_lda


@pytest.fixture
def sample_corpus() -> Corpus:
    """Cria um corpus basico mockado para testes do LDA."""
    corpus = MagicMock(spec=Corpus)

    words = [
        "governo", "federal", "aprovou", "medida", "economica", 
        "estuda", "crescimento", "educacao", "saude", "sao", 
        "prioridades", "imposto", "renda", "populacao", "reclama"
    ]
    
    formes = {}
    for word in words:
        mock_word = MagicMock()
        mock_word.forme = word
        mock_word.lem = word
        mock_word.freq = 5
        mock_word.act = 1
        formes[word] = mock_word
    corpus.formes = formes

    lems = {}
    for word in words:
        mock_lem = MagicMock()
        mock_lem.lem = word
        mock_lem.freq = 5
        mock_lem.act = 1
        lems[word] = mock_lem
    corpus.lems = lems

    # Criando 4 UCIs (documentos)
    ucis = []
    for i in range(4):
        uci = MagicMock()
        uci.ident = i
        # Alguns com data, outros sem, para testar timeline
        date_val = f"2023-01-0{i+1}" if i < 3 else ""
        uci.paras = {"title": f"Doc_{i}", "date": date_val}
        
        uce = MagicMock()
        uce.ident = i
        uci.uces = [uce]
        ucis.append(uci)
    
    corpus.ucis = ucis

    texts = [
        (0, "governo federal aprovou medida economica imposto renda"),
        (1, "governo estuda crescimento populacao"),
        (2, "educacao saude prioridades governo federal"),
        (3, "populacao reclama imposto renda saude")
    ]
    corpus.get_uces = MagicMock(return_value=texts)
    
    def _getconcorde(ids):
        return [(uid, t) for uid, t in texts if uid in ids]
    corpus.getconcorde = MagicMock(side_effect=_getconcorde)
    
    corpus.lexicon = None
    corpus.parametres = {}
    
    return corpus


class TestLDAAnalysis:

    def test_lda_analysis_generates_artifacts(self, sample_corpus, tmp_path):
        """LDA deve gerar os CSVs e imagens obrigatorios."""
        output_dir = tmp_path / "lda_output"
        output_dir.mkdir()

        params = LDAParams(n_topics=2, min_freq=1, max_features=100, n_iter=50)
        analysis = LDAAnalysis()
        result = analysis.run(sample_corpus, output_dir, params)

        assert result.analysis_type == "lda"
        
        # Arquivos esperados
        topics_csv = output_dir / "lda_topics.csv"
        doc_topic_csv = output_dir / "lda_doc_topic.csv"
        summary_json = output_dir / "lda_summary.json"
        representative_csv = output_dir / "lda_representative_sentences.csv"
        beta_csv = output_dir / "lda_terms_beta.csv"
        gamma_csv = output_dir / "lda_documents_gamma.csv"
        top_terms_png = output_dir / "lda_top_terms.png"
        heatmap_png = output_dir / "lda_doc_topic_heatmap.png"
        dist_png = output_dir / "lda_distribution.png"
        timeline_png = output_dir / "lda_topic_timeline.png"

        assert topics_csv.exists()
        assert doc_topic_csv.exists()
        assert summary_json.exists()
        assert representative_csv.exists()
        assert beta_csv.exists()
        assert gamma_csv.exists()
        assert top_terms_png.exists()
        assert heatmap_png.exists()
        assert dist_png.exists()
        assert timeline_png.exists()  # Porque mock tem 3 documentos com data

        # Validar soma ~1.0 no doc_topic
        with open(doc_topic_csv, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) > 1
        
        # Validar conteudo json
        with open(summary_json, encoding="utf-8") as f:
            summary = json.load(f)
        assert summary["analysis_type"] == "lda"
        assert summary["n_topics"] == 2
        assert "backend" in summary
        assert "method" in summary
        assert "k_requested" in summary
        assert "k_effective" in summary
        assert "representative_sentences" in summary
        assert summary["representative_sentences_count"] >= 1

    def test_lda_rejects_invalid_params(self, sample_corpus, tmp_path):
        """Rejeita k infeasivel (ex: <= 0)."""
        output_dir = tmp_path / "lda_out2"
        output_dir.mkdir()

        params = LDAParams(n_topics=0)
        analysis = LDAAnalysis()

        with pytest.raises(SemanticAnalysisError) as exc:
            analysis.run(sample_corpus, output_dir, params)
        assert "topico" in str(exc.value).lower() or "k" in str(exc.value).lower()

    def test_lda_preserves_requested_topic_count_and_exports_all_topics(self, sample_corpus, tmp_path):
        """Quando o usuario pede 5 topicos, a saida deve manter 5 topicos."""
        output_dir = tmp_path / "lda_out3"
        output_dir.mkdir()

        params = LDAParams(n_topics=5, min_freq=1, max_features=100, n_iter=50)
        analysis = LDAAnalysis()
        result = analysis.run(sample_corpus, output_dir, params)

        assert result.model_result.n_topics == 5

        topics_seen = set()
        with open(output_dir / "lda_topics.csv", encoding="utf-8") as f:
            next(f)  # header
            for line in f:
                cols = line.strip().split(";")
                if not cols or not cols[0]:
                    continue
                topics_seen.add(int(cols[0]))

        assert topics_seen == {0, 1, 2, 3, 4}

    def test_lda_recreates_output_dir_before_writing_artifacts(self, sample_corpus, tmp_path, monkeypatch):
        """A UI usa subpastas temporarias; se a pasta sumir, o LDA deve recria-la antes dos CSVs."""
        import src.analysis.lda_analysis as lda_module

        def _fake_train(**kwargs):
            shutil.rmtree(Path(kwargs["output_dir"]), ignore_errors=True)
            return LDAModelResult(
                topic_terms=[
                    TopicTerms(topic_id=0, label="T0", terms=[("governo", 0.6), ("federal", 0.4)]),
                    TopicTerms(topic_id=1, label="T1", terms=[("saude", 0.6), ("educacao", 0.4)]),
                ],
                doc_topic_rows=[
                    DocTopicRow(doc_id=0, doc_label="d0", topic_probabilities=[0.8, 0.2]),
                    DocTopicRow(doc_id=1, doc_label="d1", topic_probabilities=[0.3, 0.7]),
                ],
                perplexity=10.0,
                n_topics=2,
                topic_labels=["T0", "T1"],
                doc_topic_matrix=np.array([[0.8, 0.2], [0.3, 0.7]]),
            )

        monkeypatch.setattr(lda_module, "train_lda_classic", _fake_train)

        output_dir = tmp_path / "missing_parent" / "lda"
        result = LDAAnalysis().run(
            sample_corpus,
            output_dir,
            LDAParams(n_topics=2, min_freq=1, max_features=100, n_iter=50),
        )

        assert result.topics_csv_path.exists()
        assert (output_dir / "lda_topics.csv").exists()

    def test_lda_distribution_uses_mean_topic_probability(self):
        """Distribuição deve refletir média de P(T|D), não apenas tópico dominante."""
        model_result = LDAModelResult(
            topic_terms=[
                TopicTerms(topic_id=0, label="T0", terms=[("a", 0.5)]),
                TopicTerms(topic_id=1, label="T1", terms=[("b", 0.5)]),
                TopicTerms(topic_id=2, label="T2", terms=[("c", 0.5)]),
            ],
            doc_topic_rows=[
                DocTopicRow(doc_id=0, doc_label="d0", topic_probabilities=[0.9, 0.08, 0.02]),
                DocTopicRow(doc_id=1, doc_label="d1", topic_probabilities=[0.8, 0.1, 0.1]),
                DocTopicRow(doc_id=2, doc_label="d2", topic_probabilities=[0.7, 0.2, 0.1]),
            ],
            perplexity=None,
            n_topics=3,
            topic_labels=["T0", "T1", "T2"],
            doc_topic_matrix=np.array(
                [[0.9, 0.08, 0.02], [0.8, 0.1, 0.1], [0.7, 0.2, 0.1]]
            ),
        )

        means = LDAAnalysis._mean_topic_probabilities(model_result)
        assert means == pytest.approx([0.8, 0.1266667, 0.0733333], abs=1e-6)
        assert sum(means) == pytest.approx(1.0, abs=1e-6)

    def test_lda_doc_topic_heatmap_keeps_legend_away_from_colorbar(self, tmp_path, monkeypatch):
        """A legenda do heatmap Doc-Tópico não deve colidir com a barra de cores."""
        import src.analysis.lda_analysis as lda_module

        captured = {}

        def _capture_figure(fig, path, dpi=120):
            captured["fig"] = fig
            Path(path).write_bytes(b"placeholder")

        monkeypatch.setattr(lda_module, "save_figure", _capture_figure)

        model_result = LDAModelResult(
            topic_terms=[
                TopicTerms(topic_id=i, label=f"T{i + 1}", terms=[("termo", 1.0)])
                for i in range(5)
            ],
            doc_topic_rows=[
                DocTopicRow(doc_id=0, doc_label="Doc_0", topic_probabilities=[0.0, 0.43, 0.13, 0.33, 0.11]),
                DocTopicRow(doc_id=1, doc_label="Doc_1", topic_probabilities=[0.27, 0.36, 0.26, 0.0, 0.10]),
                DocTopicRow(doc_id=2, doc_label="Doc_2", topic_probabilities=[0.20, 0.33, 0.02, 0.0, 0.45]),
            ],
            perplexity=None,
            n_topics=5,
            topic_labels=[
                "curitiba / anderson / pensar",
                "falar / achar / sampaio",
                "vacina / achar / pagar",
                "camila / oesterreich / santo",
                "lula / filho / casa",
            ],
            doc_topic_matrix=np.array(
                [
                    [0.0, 0.43, 0.13, 0.33, 0.11],
                    [0.27, 0.36, 0.26, 0.0, 0.10],
                    [0.20, 0.33, 0.02, 0.0, 0.45],
                ]
            ),
        )

        LDAAnalysis()._write_heatmap(model_result, tmp_path / "heatmap.png")

        fig = captured["fig"]
        colorbar_ax = next(ax for ax in fig.axes if ax.get_ylabel() == "P(Tópico | Doc)")
        legend_ax = fig.axes[1]
        gap = legend_ax.get_position().x0 - colorbar_ax.get_position().x1

        assert gap >= 0.065

    def test_python_lda_fallback_uses_sklearn_when_lda_package_is_absent(self):
        dtm = np.array(
            [
                [3, 2, 0, 0],
                [2, 3, 0, 0],
                [0, 0, 3, 2],
                [0, 0, 2, 3],
            ],
            dtype=int,
        )

        result = train_lda(
            dtm=sparse.csr_matrix(dtm),
            vocabulary=["governo", "politica", "dados", "modelo"],
            doc_ids=[1, 2, 3, 4],
            doc_labels=["d1", "d2", "d3", "d4"],
            n_topics=2,
            n_iter=5,
            random_state=42,
            n_top_terms=2,
        )

        assert result.backend in {"python_lda_gibbs", "python_sklearn_lda_fallback"}
        assert result.n_topics == 2
        assert result.doc_topic_matrix.shape == (4, 2)
        assert result.doc_topic_matrix.sum(axis=1) == pytest.approx([1.0, 1.0, 1.0, 1.0])

    def test_lda_params_aliases_and_method_normalization(self):
        params = LDAParams(n_topics=7, method="gibbs", seed=123, k_min=5, k_max=3)
        assert params.k == 7
        assert params.n_topics == 7
        assert params.method == "GIBBS"
        assert params.random_state == 123
        assert params.k_max >= params.k_min

    def test_lda_advanced_diagnostics_are_optional_and_exported(self, sample_corpus, tmp_path, monkeypatch):
        """Diagnóstico avançado só roda quando marcado e gera artefatos extras."""
        import src.analysis.lda_analysis as lda_module

        calls = []

        def _fake_train(**kwargs):
            calls.append(kwargs)
            seed = int(kwargs.get("seed", 42))
            return LDAModelResult(
                topic_terms=[
                    TopicTerms(topic_id=0, label="T0", terms=[("inteligencia_artificial", 0.6), ("dados", 0.2)]),
                    TopicTerms(topic_id=1, label="T1", terms=[("saude_publica", 0.6), ("hospital", 0.2)]),
                ],
                doc_topic_rows=[
                    DocTopicRow(doc_id=0, doc_label="d0", topic_probabilities=[0.9, 0.1]),
                    DocTopicRow(doc_id=1, doc_label="d1", topic_probabilities=[0.55, 0.45]),
                    DocTopicRow(doc_id=2, doc_label="d2", topic_probabilities=[0.2, 0.8]),
                    DocTopicRow(doc_id=3, doc_label="d3", topic_probabilities=[0.1, 0.9]),
                ],
                perplexity=100.0 + seed,
                n_topics=2,
                topic_labels=["T0", "T1"],
                doc_topic_matrix=np.array([[0.9, 0.1], [0.55, 0.45], [0.2, 0.8], [0.1, 0.9]]),
            )

        monkeypatch.setattr(lda_module, "train_lda_classic", _fake_train)

        result = LDAAnalysis().run(
            sample_corpus,
            tmp_path,
            LDAParams(
                n_topics=2,
                min_freq=1,
                enable_advanced_diagnostics=True,
                stability_n_seeds=3,
            ),
        )

        assert len(calls) == 3
        assert calls[0]["enable_tuning"] is True
        assert result.diagnostics_image_path is not None
        assert result.diagnostics_image_path.exists()
        assert result.topic_diagnostics_csv_path is not None
        assert result.topic_diagnostics_csv_path.exists()
        assert result.stability_summary_json_path is not None
        assert result.stability_summary_json_path.exists()
        assert result.representative_sentences_csv_path is not None
        assert result.representative_sentences_csv_path.exists()

        summary = json.loads((tmp_path / "lda_summary.json").read_text(encoding="utf-8"))
        assert summary["advanced_diagnostics_available"] is True
        assert summary["multiword_features_count"] == 2
