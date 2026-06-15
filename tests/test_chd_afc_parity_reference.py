"""Fase 6.3 — paridade end-to-end da AFC de Perfis com a referência ideal.

Roda a CHD completa (nativa, R) sobre o corpus de referência e compara com os
valores canônicos da execução instalada (tests/data/reference_chd_afc/).

Requisitos (senão o teste é SKIP):
- R disponível (Rscript) com os pacotes ca/wordcloud/irlba/Matrix/ape;
- corpus de referência apontado por env LABIIA_CHD_PARITY_CORPUS (.txt).

Ver planejamentofable.md, Fase 6.3, e tests/data/reference_chd_afc/README.md.
"""

import csv
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REF_DIR = ROOT / "tests" / "data" / "reference_chd_afc"


def _r_available() -> bool:
    try:
        from src.core.r_runtime import RRuntimeResolver

        return RRuntimeResolver().resolve() is not None
    except Exception:
        return False


def _reference_class_distribution():
    n1 = REF_DIR / "n1.csv"
    counts = {}
    with n1.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader, None)
        for row in reader:
            if not row:
                continue
            try:
                cls = int(row[-1])
            except ValueError:
                continue
            counts[cls] = counts.get(cls, 0) + 1
    return counts


def test_reference_fixtures_present_and_canonical():
    """Cheap guard (always runs): the reference fixtures hold the 5-class baseline."""
    assert (REF_DIR / "n1.csv").exists()
    assert (REF_DIR / "afc_facteur.csv").exists()
    counts = _reference_class_distribution()
    positive = {k: v for k, v in counts.items() if k > 0}
    assert len(positive) == 5, f"esperado 5 classes na referência, obtido {sorted(positive)}"
    # Distribuição canônica {1:43,2:43,3:35,4:45,5:44} (ver README).
    assert sorted(positive.values()) == [35, 43, 43, 44, 45]


@pytest.mark.skipif(not _r_available(), reason="R/Rscript indisponível para paridade end-to-end")
@pytest.mark.skipif(
    not os.environ.get("LABIIA_CHD_PARITY_CORPUS"),
    reason="defina LABIIA_CHD_PARITY_CORPUS com o corpus de referência (.txt)",
)
def test_chd_afc_parity_with_reference(tmp_path):
    """End-to-end: a CHD nativa deve reproduzir a AFC de Perfis densa de referência."""
    from src.core.corpus import Corpus
    from src.analysis.chd_reinert import CHDAnalysis

    corpus_path = Path(os.environ["LABIIA_CHD_PARITY_CORPUS"])
    assert corpus_path.exists(), f"corpus não encontrado: {corpus_path}"

    corpus = Corpus.from_text_file(corpus_path) if hasattr(Corpus, "from_text_file") else Corpus(corpus_path)

    analysis = CHDAnalysis(corpus, tmp_path)
    result = analysis.run(
        {
            "analysis_mode": "strict",
            "nb_classes": 5,
            "classif_mode": 1,
            "min_freq": 2,
            "max_actives": 20000,
            "svd_method": "irlba",
        }
    )

    # 1) Número de classes próximo do alvo/ referência.
    assert result.n_classes == 5, f"esperado 5 classes, obtido {result.n_classes}"

    # 2) chistable sem valores não-finitos.
    chistable = tmp_path / "chistable.csv"
    if chistable.exists():
        text = chistable.read_text(encoding="utf-8", errors="replace")
        assert "Inf" not in text and "NaN" not in text, "chistable contém valores não-finitos"

    # 3) AFC2DL existe, é válido (não-branco) e denso.
    afc2dl = tmp_path / "AFC2DL.png"
    assert afc2dl.exists(), "AFC2DL.png não foi gerado"
    assert CHDAnalysis._is_valid_graph_file(afc2dl), "AFC2DL.png está em branco/ inválido"
    assert afc2dl.stat().st_size > 150_000, "AFC2DL.png pequeno demais (esparso?)"

    # 4) profile_afc_path do resultado aponta para o AFC2DL denso.
    assert result.profile_afc_path is not None
    assert Path(result.profile_afc_path).name.startswith("AFC2DL")

    # 5) Variâncias dos 2 primeiros fatores ~ 32.74 / 26.27 (tolerância ±1.5 pp).
    eig = tmp_path / "eigenvalues.csv"
    if eig.exists():
        with eig.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            variances = [float(r["variance"]) for r in reader]
        assert abs(variances[0] - 32.74) <= 1.5, f"fator 1 = {variances[0]:.2f}"
        assert abs(variances[1] - 26.27) <= 1.5, f"fator 2 = {variances[1]:.2f}"
