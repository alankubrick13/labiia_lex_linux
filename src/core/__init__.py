"""
Core Module for LabiiaLex.

This package provides the core functionality for corpus management,
text processing, R script generation, and analysis execution.

Modules:
    corpus: Data structures for UCIs, UCEs, words, and lemmas
    text_processor: Document-term and co-occurrence matrices
    r_script_generator: Template-based R script generation
    r_executor: R script execution via subprocess
    analysis_executor: Analysis task management and execution
    config_manager: Configuration management
"""

from .corpus import (
    Word,
    Lem,
    Uci,
    Uce,
    Corpus,
    CorpusError,
    decouperlist,
    decoupercharact,
    testetoile,
    testint,
)

from .text_processor import (
    TextProcessor,
    TextProcessorError,
)

from .r_script_generator import (
    RScriptGenerator,
    RScriptGeneratorError,
)

from .r_executor import (
    RExecutor,
    RNotFoundError,
    RExecutionError,
    RTimeoutError,
    ExecutionResult,
)

from .analysis_executor import (
    AnalysisExecutor,
    AnalysisExecutorError,
    AnalysisTask,
    AnalysisType,
    TaskStatus,
)
from .lexicon import (
    Lexicon,
    resolve_lexicon_path,
    ACTIVE_GRAM_TYPES,
)
from .history import (
    AnalysisHistory,
    HistoryEntry,
    HistoryError,
)
from .project import (
    Project,
    ProjectManager,
    ProjectError,
)
from .tableau import (
    Tableau,
    TableauError,
)
from .report_generator import (
    ReportGenerator,
    ReportGeneratorError,
)
from .version import (
    APP_NAME,
    APP_VERSION,
)

__all__ = [
    # Corpus
    'Word',
    'Lem',
    'Uci',
    'Uce',
    'Corpus',
    'CorpusError',
    'decouperlist',
    'decoupercharact',
    'testetoile',
    'testint',
    # Text Processor
    'TextProcessor',
    'TextProcessorError',
    # R Script Generator
    'RScriptGenerator',
    'RScriptGeneratorError',
    # R Executor
    'RExecutor',
    'RNotFoundError',
    'RExecutionError',
    'RTimeoutError',
    'ExecutionResult',
    # Analysis Executor
    'AnalysisExecutor',
    'AnalysisExecutorError',
    'AnalysisTask',
    'AnalysisType',
    'TaskStatus',
    # Lexicon
    'Lexicon',
    'resolve_lexicon_path',
    'ACTIVE_GRAM_TYPES',
    # History
    'AnalysisHistory',
    'HistoryEntry',
    'HistoryError',
    # Project
    'Project',
    'ProjectManager',
    'ProjectError',
    # Tableau
    'Tableau',
    'TableauError',
    # Reports
    'ReportGenerator',
    'ReportGeneratorError',
    # Version
    'APP_NAME',
    'APP_VERSION',
]
