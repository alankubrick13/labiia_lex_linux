from __future__ import annotations

from src.importers.corpus_validator import CorpusValidator
from src.importers.fuzzy_normalizer import FuzzyCluster, FuzzyNormalizer


def test_validator_accepts_repairable_extra_asterisk_command_marker() -> None:
    text = "***** *doc_1\nTexto valido do corpus."

    report = CorpusValidator().validate(text)

    assert report.is_valid is True
    assert any("corrigido" in warning.lower() or "normalizado" in warning.lower() for warning in report.warnings)


def test_validator_accepts_bom_before_command_marker() -> None:
    text = "\ufeff**** *doc_1\nTexto valido do corpus."

    report = CorpusValidator().validate(text)

    assert report.is_valid is True
    assert report.stats["total_ucis"] == 1


def test_command_line_without_variables_is_warning_not_traceback() -> None:
    text = "****\nTexto valido do corpus."

    report = CorpusValidator().validate(text)

    assert report.is_valid is True
    assert report.errors == []
    assert any("sem variaveis" in warning.lower() for warning in report.warnings)


def test_fuzzy_normalizer_preserves_command_lines_with_extra_asterisks() -> None:
    text = "***** *doc_1\nDemocrácia democracia democracia."
    normalizer = FuzzyNormalizer(text, min_word_length=4, min_frequency=1)
    result = normalizer.apply_clusters(
        [
            FuzzyCluster(
                canonical="democracia",
                variants=["democracia", "Democrácia"],
                frequency=3,
            )
        ]
    )

    assert result.normalized_text.splitlines()[0] == "***** *doc_1"
