"""
Dialogs Package
===============

Dialogos da interface grafica.
"""

from .import_dialog import ImportDialog
from .bigram_selection_dialog import BigramSelectionDialog
from .multiword_selection_dialog import MultiwordSelectionDialog
from .analysis_dialog import (
    CHDDialog,
    SimilarityDialog,
    WordCloudDialog,
    StatisticsDialog,
    PrototypicalDialog,
    LabbeDialog,
    KeynessExtraDialog,
    BigramNetworkExtraDialog,
    TrigramNetworkExtraDialog,
    WordTreeExtraDialog,
    WordfishExtraDialog,
    XRayExtraDialog,
    SentimentExtraDialog,
)
from .matrix_dialog import (
    MatrixFrequencyDialog,
    MatrixChi2Dialog,
    MatrixAFCDialog,
    MatrixCHDDialog,
    MatrixSimilarityDialog,
)
from .concordance_dialog import ConcordanceDialog
from .specificities_dialog import SpecificitiesDialog
from .word_selector_dialog import WordSelectorDialog
from .error_dialog import ErrorDialog
from .settings_dialog import SettingsDialog
from .fuzzy_normalizer_dialog import FuzzyNormalizerDialog
from .corpus_preparation_dialog import CorpusPreparationDialog
from .cca_dialog import CCADialog
from .cca_auto_preview_dialog import CCAAutoPreviewDialog
from .rolling_window_dialog import RollingWindowDialog
from .kwic_dialog import KWICDialog
from .keyness_dialog import KeynessDialog
from .emotions_dialog import EmotionsDialog
from .base_dialog import BaseDialogShell
from .semantic_analysis_dialogs import (
    YAKEDialog,
    LDADialog,
    AssociativeHeatmapDialog,
    ThematicMapDialog,
    ThematicCHDDialog,
)


__all__ = [
    'ImportDialog',
    'CHDDialog',
    'SimilarityDialog',
    'WordCloudDialog',
    'StatisticsDialog',
    'PrototypicalDialog',
    'LabbeDialog',
    'KeynessExtraDialog',
    'BigramNetworkExtraDialog',
    'TrigramNetworkExtraDialog',
    'WordTreeExtraDialog',
    'WordfishExtraDialog',
    'XRayExtraDialog',
    'SentimentExtraDialog',
    'ThematicMapDialog',
    'MatrixFrequencyDialog',
    'MatrixChi2Dialog',
    'MatrixAFCDialog',
    'MatrixCHDDialog',
    'MatrixSimilarityDialog',
    'ConcordanceDialog',
    'SpecificitiesDialog',
    'WordSelectorDialog',
    'ErrorDialog',
    'SettingsDialog',
    'BigramSelectionDialog',
    'MultiwordSelectionDialog',
    'FuzzyNormalizerDialog',
    'CorpusPreparationDialog',
    'CCADialog',
    'CCAAutoPreviewDialog',
    'RollingWindowDialog',
    'KWICDialog',
    'KeynessDialog',
    'EmotionsDialog',
    'BaseDialogShell',
]
