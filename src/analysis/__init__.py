"""
LabiiaLex - Modulos de Analise
===============================
"""

from .statistics import StatisticsAnalysis, CorpusStatistics
from .chd_reinert import CHDAnalysis, CHDResult
from .similarity import SimilarityAnalysis, SimilarityResult, SIMILARITY_COEFFICIENTS
from .wordcloud import WordCloudAnalysis, WordCloudResult
from .prototypical import PrototypicalAnalysis, PrototypicalResult
from .labbe import LabbeAnalysis, LabbeResult
from .concordancer import (
    Concordancer,
    ConcordanceContext,
    ConcordanceResult,
    ConcordancerError,
)
from .specificities import (
    SpecificitiesAnalysis,
    SpecificitiesResult,
    SpecificityEntry,
    SpecificitiesAnalysisError,
)
from .colored_corpus import ColoredCorpusExporter
from .frequency import (
    FrequencyAnalysis,
    FrequencyAnalysisError,
    FrequencyEntry,
    FrequencyResult,
)
from .chi2_matrix import (
    Chi2MatrixAnalysis,
    Chi2MatrixAnalysisError,
    Chi2Result,
)
from .matrix_adapter import (
    MatrixAnalysisAdapter,
    MatrixAnalysisAdapterError,
    MatrixAFCResult,
    MatrixCHDResult,
    MatrixSimilarityResult,
)
from .keyness_extra import (
    KeynessExtraAnalysis,
    KeynessExtraAnalysisError,
    KeynessExtraResult,
)
from .keyness_r import (
    KeynessRAnalysis,
    KeynessRAnalysisError,
    KeynessRResult,
    KeynessRRow,
)
from .bigram_network_extra import (
    BigramNetworkExtraAnalysis,
    BigramNetworkExtraAnalysisError,
    BigramNetworkExtraResult,
)
from .trigram_network_extra import (
    TrigramNetworkExtraAnalysis,
    TrigramNetworkExtraAnalysisError,
    TrigramNetworkExtraResult,
)
from .wordfish_extra import (
    WordfishExtraAnalysis,
    WordfishExtraAnalysisError,
    WordfishExtraResult,
)
from .xray_extra import (
    XRayExtraAnalysis,
    XRayExtraAnalysisError,
    XRayExtraResult,
)
from .sentiment_extra import (
    SentimentExtraAnalysis,
    SentimentExtraAnalysisError,
    SentimentExtraResult,
)
from .word_tree_extra import (
    WordTreeExtraAnalysis,
    WordTreeExtraAnalysisError,
    WordTreeExtraResult,
)
from .network_text_analysis import (
    NetworkTextAnalysis,
    NetworkTextAnalysisError,
    NetworkTextAnalysisResult,
)
from .voyant_suite import (
    VoyantSuiteAnalysis,
    VoyantSuiteAnalysisError,
    VoyantSuiteResult,
)
from .emotions import (
    EmotionsAnalysis,
    EmotionsAnalysisError,
    EmotionsResult,
)
from .semantic_contracts import (
    SemanticAnalysisError,
    ArtifactManifest,
    BaseSemanticParams,
    BaseSemanticResult,
    KeyphraseCandidate,
)
from .semantic_text_base import (
    SemanticTextBundle,
    SparseMatrixBundle,
    SemanticDocument,
    SemanticSegment,
)
from .association_metrics import (
    build_cooccurrence_matrix,
    compute_ppmi,
    rank_association_pairs,
    AssociationPair,
)
from .topic_modeling import (
    train_lda,
    generate_topic_labels,
    LDAModelResult,
    TopicTerms,
    DocTopicRow,
)
from .keyphrase_yake import extract_ranked_keyphrases
from .semantic_graph_exports import (
    GraphNode,
    GraphEdge,
    write_nodes_csv,
    write_edges_csv,
    write_summary_json,
    write_diagnostics_json,
)

__all__ = [
    "StatisticsAnalysis",
    "CorpusStatistics",
    "CHDAnalysis",
    "CHDResult",
    "SimilarityAnalysis",
    "SimilarityResult",
    "SIMILARITY_COEFFICIENTS",
    "WordCloudAnalysis",
    "WordCloudResult",
    "PrototypicalAnalysis",
    "PrototypicalResult",
    "LabbeAnalysis",
    "LabbeResult",
    "Concordancer",
    "ConcordanceContext",
    "ConcordanceResult",
    "ConcordancerError",
    "SpecificitiesAnalysis",
    "SpecificitiesResult",
    "SpecificityEntry",
    "SpecificitiesAnalysisError",
    "ColoredCorpusExporter",
    "FrequencyAnalysis",
    "FrequencyAnalysisError",
    "FrequencyEntry",
    "FrequencyResult",
    "Chi2MatrixAnalysis",
    "Chi2MatrixAnalysisError",
    "Chi2Result",
    "MatrixAnalysisAdapter",
    "MatrixAnalysisAdapterError",
    "MatrixAFCResult",
    "MatrixCHDResult",
    "MatrixSimilarityResult",
    "KeynessExtraAnalysis",
    "KeynessExtraAnalysisError",
    "KeynessExtraResult",
    "KeynessRAnalysis",
    "KeynessRAnalysisError",
    "KeynessRResult",
    "KeynessRRow",
    "BigramNetworkExtraAnalysis",
    "BigramNetworkExtraAnalysisError",
    "BigramNetworkExtraResult",
    "TrigramNetworkExtraAnalysis",
    "TrigramNetworkExtraAnalysisError",
    "TrigramNetworkExtraResult",
    "WordfishExtraAnalysis",
    "WordfishExtraAnalysisError",
    "WordfishExtraResult",
    "XRayExtraAnalysis",
    "XRayExtraAnalysisError",
    "XRayExtraResult",
    "SentimentExtraAnalysis",
    "SentimentExtraAnalysisError",
    "SentimentExtraResult",
    "WordTreeExtraAnalysis",
    "WordTreeExtraAnalysisError",
    "WordTreeExtraResult",
    "NetworkTextAnalysis",
    "NetworkTextAnalysisError",
    "NetworkTextAnalysisResult",
    "VoyantSuiteAnalysis",
    "VoyantSuiteAnalysisError",
    "VoyantSuiteResult",
    "EmotionsAnalysis",
    "EmotionsAnalysisError",
    "EmotionsResult",
    "SemanticAnalysisError",
    "ArtifactManifest",
    "BaseSemanticParams",
    "BaseSemanticResult",
    "KeyphraseCandidate",
    "SemanticTextBundle",
    "SparseMatrixBundle",
    "SemanticDocument",
    "SemanticSegment",
]
