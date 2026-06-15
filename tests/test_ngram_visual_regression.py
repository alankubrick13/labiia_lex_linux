from __future__ import annotations

import csv
import json
from unittest.mock import MagicMock

from src.core.corpus import Corpus


def _corpus_from_texts(texts: list[str]) -> MagicMock:
    corpus = MagicMock(spec=Corpus)
    corpus.ucis = []
    uces = []
    for idx, text in enumerate(texts):
        uce = MagicMock()
        uce.ident = idx
        uci = MagicMock()
        uci.ident = idx
        uci.etoiles = []
        uci.paras = {}
        uci.uces = [uce]
        corpus.ucis.append(uci)
        uces.append((idx, text))
    corpus.get_uces = MagicMock(return_value=uces)
    corpus.lexicon = None
    corpus.parametres = {}
    return corpus


def _read_terms_from_edges(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        terms = set()
        for row in reader:
            for key in ("word_1", "word_2", "word_3"):
                value = str(row.get(key, "") or "").strip()
                if value:
                    terms.add(value)
        return terms


def test_bigram_network_filters_visual_noise_before_edges(tmp_path) -> None:
    from src.analysis.bigram_network_extra import BigramNetworkExtraAnalysis

    corpus = _corpus_from_texts(
        [
            "né gente vacina publica vacina publica 36 aa si",
            "então gente vacina publica vacina publica 10 ainda",
        ]
    )
    analysis = BigramNetworkExtraAnalysis(corpus, tmp_path)
    analysis._plot_network = lambda path, graph, params: path.write_text("plot skipped", encoding="utf-8")

    result = analysis.run({"min_bigram_freq": 2, "top_edges": 20})
    terms = _read_terms_from_edges(result.edges_path)

    assert {"vacina", "publica"}.issubset(terms)
    assert {"né", "gente", "então", "36", "10", "aa", "si", "ainda"}.isdisjoint(terms)


def test_trigram_network_filters_visual_noise_before_edges(tmp_path) -> None:
    from src.analysis.trigram_network_extra import TrigramNetworkExtraAnalysis

    corpus = _corpus_from_texts(
        [
            "acho inteligencia artificial generativa inteligencia artificial generativa 0",
            "assim inteligencia artificial generativa inteligencia artificial generativa aa",
        ]
    )
    analysis = TrigramNetworkExtraAnalysis(corpus, tmp_path)
    analysis._plot_network = lambda path, graph, params: path.write_text("plot skipped", encoding="utf-8")

    result = analysis.run({"min_trigram_freq": 2, "top_edges": 20})
    terms = _read_terms_from_edges(result.edges_path)

    assert {"inteligencia", "artificial", "generativa"}.issubset(terms)
    assert {"acho", "assim", "0", "aa"}.isdisjoint(terms)


def test_readable_network_renderer_uses_repelled_label_layout(tmp_path) -> None:
    import networkx as nx

    from src.analysis.readable_network_plot import write_readable_network_plot

    graph = nx.Graph()
    center_terms = [
        "oesterreich",
        "santos",
        "eliezer",
        "arruda",
        "camila",
        "falar",
        "entendeu",
        "curitiba",
        "governo",
        "concordo",
        "votaram",
        "familia",
    ]
    for idx, term in enumerate(center_terms):
        graph.add_edge("bolsonaro", term, weight=6 + idx)
        graph.add_edge(term, center_terms[(idx + 1) % len(center_terms)], weight=3)

    output = tmp_path / "network.png"
    write_readable_network_plot(graph, output, title="Rede teste", max_labels=40)

    meta = json.loads(output.with_name("network_render_meta.json").read_text(encoding="utf-8"))
    assert meta["layout"] == "component_spring_readable_repelled"
    assert meta["label_layout"] == "repelled_labels"
    assert meta["label_collision_passes"] >= 1
    assert meta["label_anchor_lines"] is True
