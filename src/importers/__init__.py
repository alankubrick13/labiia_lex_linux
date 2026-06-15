"""
LabiiaLex - Importadores de Documentos
=========================================
Este módulo contém os importadores para diferentes formatos de arquivo
e os limpadores de corpus para análise textual.

Importadores disponíveis:
- TXTImporter:    Arquivos textuais (.txt, .md, .json, .net)
- PDFImporter:    Arquivos PDF (.pdf)
- DOCXImporter:   Arquivos Word (.docx)
- ODTImporter:    Arquivos OpenDocument (.odt)
- XLSXImporter:   Arquivos Excel (.xlsx) e CSV (.csv)
- ZipImporter:    Coleção de documentos em ZIP (multi-documento)
- FolderImporter: Coleção de documentos de uma pasta (multi-documento)

Limpadores disponíveis:
- CorpusCleaner: Limpeza para formato IRaMuTeQ
- GeneralCleaner: Limpeza para análises textuais tradicionais
"""

from .base_importer import BaseImporter, ImportResult, ImporterError
from .txt_importer import TXTImporter
from .pdf_importer import PDFImporter
from .docx_importer import DOCXImporter
from .odt_importer import ODTImporter
from .xlsx_importer import XLSXImporter
from .zip_importer import ZipImporter
from .folder_importer import FolderImporter
from .corpus_cleaner import CorpusCleaner
from .text_cleaning import limpar_texto, extrair_variaveis_do_nome_arquivo
from .bigram_compounds import (
    apply_selected_bigrams_to_text,
    extract_bigram_candidates,
    selected_bigrams_to_expressions,
)
from .general_cleaner import GeneralCleaner
from .iramuteq_adapter import IramuteqAutoAdapter
from .fuzzy_normalizer import FuzzyNormalizer, FuzzyCluster, NormalizationResult
from .corpus_validator import (
    ValidationIssue,
    ValidationReport,
    CorpusValidationError,
    CorpusValidator,
    validate_iramuteq_corpus,
)

__all__ = [
    # Base
    "BaseImporter",
    "ImportResult",
    "ImporterError",
    # Importadores — arquivo único
    "TXTImporter",
    "PDFImporter",
    "DOCXImporter",
    "ODTImporter",
    "XLSXImporter",
    # Importadores — coleção multi-documento
    "ZipImporter",
    "FolderImporter",
    # Limpadores e normalizadores
    "CorpusCleaner",
    "limpar_texto",
    "extrair_variaveis_do_nome_arquivo",
    "apply_selected_bigrams_to_text",
    "extract_bigram_candidates",
    "selected_bigrams_to_expressions",
    "GeneralCleaner",
    "IramuteqAutoAdapter",
    "FuzzyNormalizer",
    "FuzzyCluster",
    "NormalizationResult",
    # Validacao de corpus
    "ValidationIssue",
    "ValidationReport",
    "CorpusValidationError",
    "CorpusValidator",
    "validate_iramuteq_corpus",
]


def get_importer_for_file(file_path: str) -> BaseImporter:
    """
    Retorna o importador apropriado para o arquivo ou pasta.

    Inclui suporte a:
      - Arquivos individuais: .txt, .md, .json, .net, .pdf, .docx, .odt, .xlsx, .csv
      - Coleções: .zip (ZipImporter)
      - Pastas: qualquer diretório (FolderImporter)

    Args:
        file_path: Caminho do arquivo ou pasta.

    Returns:
        Instância do importador apropriado.

    Raises:
        ImporterError: Se não houver importador para o tipo.
    """
    from pathlib import Path
    path = Path(file_path)

    # Pasta → FolderImporter
    if path.is_dir():
        return FolderImporter()

    importers = [
        ZipImporter(),   # ZIP antes do TXT para prioridade correta
        TXTImporter(),
        PDFImporter(),
        DOCXImporter(),
        ODTImporter(),
        XLSXImporter(),
    ]

    for importer in importers:
        if importer.can_handle(str(file_path)):
            return importer

    ext = path.suffix.lower()
    supported = ".txt, .md, .json, .net, .pdf, .docx, .odt, .xlsx, .csv, .zip"
    raise ImporterError(
        what=f"Tipo de arquivo '{ext}' não é suportado.",
        why=f"Não há importador disponível para arquivos '{ext}'.",
        how=f"Converta o arquivo para um dos formatos suportados: {supported}",
    )
