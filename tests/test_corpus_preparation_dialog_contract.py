from __future__ import annotations


class _Var:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def test_corpus_preparation_dialog_defaults_match_109_contract() -> None:
    from src.ui.dialogs.corpus_preparation_dialog import CorpusPreparationDialog

    dialog = CorpusPreparationDialog.__new__(CorpusPreparationDialog)
    dialog.lowercase_var = _Var(False)
    dialog.remove_numbers_var = _Var(False)
    dialog.remove_accents_var = _Var(False)
    dialog.clean_web_data_var = _Var(False)
    dialog.detect_bigrams_var = _Var(True)
    dialog.bigram_top_n_var = _Var(30)
    dialog.bigram_min_freq_var = _Var(3)
    dialog.ngram_max_var = _Var(3)
    dialog.min_is_norm_var = _Var(0.35)
    dialog.detect_entities_var = _Var(False)
    dialog.entity_top_n_var = _Var(50)
    dialog.entity_min_freq_var = _Var(2)
    dialog.entity_max_tokens_var = _Var(6)
    dialog.destroy = lambda: None

    CorpusPreparationDialog._confirm(dialog)

    assert dialog.get_result() == {
        "lowercase": False,
        "remove_numbers": False,
        "remove_accents": False,
        "clean_web_data": False,
        "detect_bigrams": True,
        "bigram_top_n": 30,
        "bigram_min_freq": 3,
        "ngram_max": 3,
        "min_is_norm": 0.35,
        "selected_bigrams": [],
        "detect_entities": False,
        "entity_top_n": 50,
        "entity_min_freq": 2,
        "entity_max_tokens": 6,
        "selected_entities": [],
    }


def test_multiword_selection_dialog_imports_and_accepts_legacy_wrapper() -> None:
    from src.ui.dialogs.bigram_selection_dialog import BigramSelectionDialog
    from src.ui.dialogs.multiword_selection_dialog import MultiwordSelectionDialog

    assert issubclass(BigramSelectionDialog, MultiwordSelectionDialog)
