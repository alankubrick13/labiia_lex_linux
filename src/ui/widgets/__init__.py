"""
Widgets Package
===============

Widgets customizados da interface.
"""

from .corpus_tree import CorpusTree
from .results_viewer import ResultsViewer
from .graph_viewer import GraphViewer
from .corpus_navigator import CorpusNavigator
from .guided_tour import GuidedTour, TourStep
from .analysis_catalog import AnalysisCatalogView
from .analysis_ribbon import AnalysisRibbonView

__all__ = [
    'CorpusTree',
    'ResultsViewer',
    'GraphViewer',
    'CorpusNavigator',
    'AnalysisCatalogView',
    'AnalysisRibbonView',
    'GuidedTour',
    'TourStep',
]
