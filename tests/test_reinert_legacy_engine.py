from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.analysis.chd_reinert import CHDAnalysis
from src.core.corpus import Corpus


THEMES = {
    "saude": [
        "vacina", "hospital", "medico", "paciente", "cuidado", "enfermagem",
        "saude", "tratamento", "clinica", "remedio", "diagnostico", "consulta",
    ],
    "educacao": [
        "escola", "professor", "aluno", "aula", "ensino", "aprendizagem",
        "curriculo", "universidade", "didatica", "leitura", "prova", "curso",
    ],
    "politica": [
        "governo", "eleicao", "partido", "congresso", "prefeito", "campanha",
        "voto", "mandato", "camara", "politica", "debate", "gestao",
    ],
    "tecnologia": [
        "software", "algoritmo", "dados", "internet", "sistema", "plataforma",
        "codigo", "rede", "computador", "digital", "aplicativo", "modelo",
    ],
    "cultura": [
        "livro", "cinema", "musica", "teatro", "arte", "literatura",
        "museu", "poesia", "autor", "obra", "festival", "memoria",
    ],
}


def _make_wide_reinert_corpus() -> Corpus:
    corpus = Corpus({"ucemethod": 0, "ucesize": 80})
    for theme_name, terms in THEMES.items():
        uci = corpus.add_uci(f"**** *doc_{theme_name}")
        for idx in range(8):
            rotated = terms[idx % len(terms):] + terms[:idx % len(terms)]
            text_terms = rotated[:8] + terms[:4] + [theme_name, "pesquisa", "analise"]
            text = " ".join(text_terms)
            uce = corpus.add_uce(uci.ident, idx, text)
            for token in text.split():
                corpus.add_word(token, gram="nom", lem=token, uce_id=uce.ident)
    return corpus


def _make_noisy_raw_indexed_reinert_corpus() -> Corpus:
    """Build corpus where raw UCE text is noisy but indexed vocabulary is clean."""
    corpus = Corpus({"ucemethod": 0, "ucesize": 80})
    raw_noise = "então assim porque aqui ali ainda 36 mp3 nvoce npalestrante"
    for theme_name, terms in THEMES.items():
        uci = corpus.add_uci(f"**** *doc_{theme_name}")
        for idx in range(8):
            rotated = terms[idx % len(terms):] + terms[:idx % len(terms)]
            clean_terms = rotated[:8] + terms[:4] + [theme_name, "pesquisa", "analise"]
            raw_text = f"{raw_noise} {' '.join(clean_terms)} {raw_noise}"
            uce = corpus.add_uce(uci.ident, idx, raw_text)
            for token in clean_terms:
                corpus.add_word(token, gram="nom", lem=token, uce_id=uce.ident)
    return corpus


def _csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.reader(file))


def _csv_dict_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _semicolon_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.reader(file, delimiter=";"))


def test_ported_reinert_engine_generates_five_classes_and_dense_afc(tmp_path):
    from src.analysis.reinert import ReinertEngine, ReinertRunConfig

    corpus = _make_wide_reinert_corpus()
    result = ReinertEngine(
        corpus,
        tmp_path,
        ReinertRunConfig(
            min_docfreq=2,
            max_classes=5,
            min_child_size=3,
            max_profile_terms=80,
            max_plot_terms=120,
        ),
    ).run()

    assert result.n_classes == 5
    assert len(result.class_sizes) == 5
    assert all(size >= 3 for size in result.class_sizes.values())
    assert result.profile_afc_path is not None and result.profile_afc_path.exists()
    assert result.dendrogram_path is not None and result.dendrogram_path.exists()

    profile_rows = _csv_rows(result.term_profiles_path)
    assert len(profile_rows) > 120

    coord_rows = _csv_rows(result.profile_ca_coords_path)
    term_rows = [row for row in coord_rows[1:] if row and row[0] == "term"]
    assert len(term_rows) >= 50


def test_chd_analysis_uses_legacy_reinert_when_native_chd_is_disabled(tmp_path):
    class FailingRExecutor:
        def execute(self, *args, **kwargs):
            raise AssertionError("CHDAnalysis should not call R when native CHD is disabled")

    corpus = _make_wide_reinert_corpus()
    result = CHDAnalysis(corpus, tmp_path, r_executor=FailingRExecutor()).run(
        {
            "nb_classes": 5,
            "min_classes": 5,
            "max_classes": 5,
            "min_freq": 2,
            "classif_mode": 1,
            "typegraph": "png",
            "analysis_mode": "legacy",
            "strict_iramuteq_clone": False,
            "use_native_chd": False,
        }
    )

    assert result.n_classes == 5
    assert result.dendrogram_path is not None and result.dendrogram_path.exists()
    assert result.profile_afc_path is not None and result.profile_afc_path.exists()
    assert result.profiles
    assert result.class_sizes
    assert result.typical_segments
    assert result.colored_corpus_path is not None and result.colored_corpus_path.exists()
    assert result.class_text_paths

    matrix_path = tmp_path / "chd_profile_matrix.csv"
    assert matrix_path.exists()
    matrix_terms = [row[0] for row in _csv_rows(matrix_path)[1:] if row and row[0]]
    assert len(matrix_terms) >= 50


def test_chd_visual_outputs_filter_noise_without_pre_cutting_afc_matrix(tmp_path):
    from src.analysis.reinert import ReinertEngine, ReinertRunConfig

    corpus = _make_wide_reinert_corpus()
    uci = corpus.add_uci("**** *doc_ruido")
    noisy_text = "mp3 36 0 nvoce npalestrante nãoterminar então assim aqui ali ainda"
    for idx in range(4):
        uce = corpus.add_uce(uci.ident, idx, noisy_text)
        for token in noisy_text.split():
            corpus.add_word(token, gram="nom", lem=token, uce_id=uce.ident)

    result = ReinertEngine(
        corpus,
        tmp_path,
        ReinertRunConfig(
            min_docfreq=2,
            max_classes=5,
            min_child_size=3,
            max_profile_terms=80,
            max_plot_terms=120,
        ),
    ).run()

    matrix_terms = {
        row[0]
        for row in _semicolon_rows(tmp_path / "chd_profile_matrix.csv")[1:]
        if row and row[0]
    }
    assert len(matrix_terms) >= 50

    layout_path = tmp_path / "chd_dendrogram_layout.json"
    assert layout_path.exists()
    layout_payload = json.loads(layout_path.read_text(encoding="utf-8"))
    visible_terms = {
        term
        for class_payload in layout_payload.get("classes", [])
        for term in class_payload.get("visible_terms", [])
    }
    for noisy in ["mp3", "36", "0", "nvoce", "npalestrante", "nãoterminar", "então", "assim", "aqui", "ali", "ainda"]:
        assert noisy not in visible_terms

    not_plotted = tmp_path / "chd_profiles_afc.png_notplotted.csv"
    if not_plotted.exists():
        hidden = not_plotted.read_text(encoding="utf-8")
        assert "mp3" not in hidden


def test_ported_reinert_prefers_clean_index_over_noisy_raw_text(tmp_path):
    from src.analysis.reinert import ReinertEngine, ReinertRunConfig

    corpus = _make_noisy_raw_indexed_reinert_corpus()
    result = ReinertEngine(
        corpus,
        tmp_path,
        ReinertRunConfig(
            min_docfreq=2,
            max_classes=5,
            min_child_size=3,
            max_profile_terms=80,
            max_plot_terms=70,
        ),
    ).run()

    assert result.n_classes == 5
    assert result.lexical_matrix.matrix.nnz > 0

    matrix_terms = {
        row[0]
        for row in _semicolon_rows(tmp_path / "chd_profile_matrix.csv")[1:]
        if row and row[0]
    }
    profile_terms = {
        row["term"]
        for row in _csv_dict_rows(tmp_path / "profiles_terms.csv")
        if row.get("term")
    }
    rejected = {
        "então",
        "entao",
        "assim",
        "porque",
        "aqui",
        "ali",
        "ainda",
        "36",
        "mp3",
        "nvoce",
        "npalestrante",
    }
    assert rejected.isdisjoint(matrix_terms)
    assert rejected.isdisjoint(profile_terms)
    assert {"vacina", "escola", "governo", "software", "livro"}.issubset(matrix_terms)


def test_profile_afc_exports_labeled_and_hidden_terms(tmp_path):
    from src.analysis.reinert import ReinertEngine, ReinertRunConfig

    corpus = _make_wide_reinert_corpus()
    result = ReinertEngine(
        corpus,
        tmp_path,
        ReinertRunConfig(
            min_docfreq=2,
            max_classes=5,
            min_child_size=3,
            max_profile_terms=80,
            max_plot_terms=45,
        ),
    ).run()

    assert result.profile_afc_path is not None and result.profile_afc_path.exists()
    labeled_path = tmp_path / "chd_profiles_afc_labeled_terms.csv"
    hidden_path = tmp_path / "chd_profiles_afc_hidden_terms.csv"
    points_path = tmp_path / "chd_profiles_afc_points.csv"
    assert labeled_path.exists()
    assert hidden_path.exists()
    assert points_path.exists()

    labeled_rows = _csv_dict_rows(labeled_path)
    hidden_rows = _csv_dict_rows(hidden_path)
    point_rows = _csv_dict_rows(points_path)
    assert len(labeled_rows) == len(point_rows)
    assert len(labeled_rows) >= 55
    assert len(hidden_rows) == 0

    labeled_terms = {row["term"] for row in labeled_rows}
    hidden_terms = {row["term"] for row in hidden_rows}
    assert labeled_terms.isdisjoint(hidden_terms)

    layout_path = tmp_path / "chd_profiles_afc_layout.json"
    assert layout_path.exists()
    layout_payload = json.loads(layout_path.read_text(encoding="utf-8"))
    assert layout_payload["class_markers_drawn"] is False
    assert layout_payload["class_labels_drawn"] is False
    assert layout_payload["term_points_drawn"] is False
    assert layout_payload["visible_label_count"] == len(labeled_rows)
    assert all(not row["term"].lower().startswith("classe ") for row in labeled_rows)
