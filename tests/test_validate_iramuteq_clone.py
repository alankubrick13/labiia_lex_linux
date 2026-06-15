from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.validate_iramuteq_clone import (
    SMALL_CORPUS_UCE_THRESHOLD,
    build_corpus,
    choose_chd_validation_params,
)


def test_choose_chd_validation_params_uses_small_corpus_smoke_profile(tmp_path):
    corpus = build_corpus(
        PROJECT_ROOT / "tests" / "fixtures" / "exemplo.txt",
        tmp_path / "small_validation.db",
    )
    try:
        params = choose_chd_validation_params(corpus, min_freq=1)
    finally:
        corpus.close()

    assert params["corpus_uces"] <= SMALL_CORPUS_UCE_THRESHOLD
    assert params["validation_profile"] == "native_small_corpus_smoke"
    assert params["nb_classes"] == 2
    assert params["classif_mode"] == 0
    assert params["svd_method"] == "svdR"


def test_choose_chd_validation_params_keeps_native_profile_for_larger_corpus(tmp_path):
    lines = []
    for idx in range(SMALL_CORPUS_UCE_THRESHOLD + 2):
        lines.append(f"**** *doc_{idx}")
        lines.append(f"Segmento de validacao numero {idx} com palavras suficientes para teste.")
    corpus_file = tmp_path / "large_corpus.txt"
    corpus_file.write_text("\n\n".join(lines), encoding="utf-8")

    corpus = build_corpus(corpus_file, tmp_path / "large_validation.db")
    try:
        params = choose_chd_validation_params(corpus, min_freq=2)
    finally:
        corpus.close()

    assert params["corpus_uces"] > SMALL_CORPUS_UCE_THRESHOLD
    assert params["validation_profile"] == "native"
    assert params["nb_classes"] == 4
    assert params["classif_mode"] == 1
    assert "svd_method" not in params
