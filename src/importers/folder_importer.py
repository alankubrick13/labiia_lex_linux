"""
FolderImporter - Importa todos os documentos de uma pasta como coleção.
=======================================================================
Varre recursivamente uma pasta e importa todos os arquivos de texto
suportados como corpus multi-documento (um arquivo = um UCI).

Suporte a: .txt, .md, .json, .net, .pdf, .docx, .odt
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_importer import BaseImporter, ImporterError, ImportResult
from ..utils.logger import get_logger

log = get_logger(__name__)

_SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".net", ".pdf", ".docx", ".odt"}
_IGNORED_DIRS = {".git", "__pycache__", ".vscode", "node_modules"}
_MAX_FILES = 500  # Proteção contra pastas enormes


class FolderImporter(BaseImporter):
    """
    Importa todos os arquivos de texto de uma pasta (recursiva) como coleção.

    Cada arquivo vira um documento separado (UCI) no corpus IRaMuTeQ.
    Adequado para o Fluxo B (multi-documento) e CCA/Textometrica.
    """

    SUPPORTED_EXTENSIONS: List[str] = []  # Recebe pastas, não extensões

    def can_handle(self, file_path: str) -> bool:
        """Retorna True se for um diretório."""
        return Path(file_path).is_dir()

    def extract(self, file_path: str) -> ImportResult:
        """
        Importa recursivamente todos os documentos da pasta.

        Returns ImportResult onde:
          - result.text   = corpus IRaMuTeQ com N UCIs (um por arquivo)
          - result.metadata['collection_mode'] = True
          - result.metadata['documents'] = lista de {name, text, warnings}
        """
        folder = Path(file_path)
        if not folder.is_dir():
            raise ImporterError(
                what="Pasta não encontrada.",
                why=f"O caminho '{file_path}' não é uma pasta válida.",
                how="Selecione uma pasta existente no seu computador.",
            )

        self._report_progress(0.05, "Listando arquivos...")
        candidate_files = self._collect_files(folder)

        if not candidate_files:
            raise ImporterError(
                what="Nenhum arquivo suportado encontrado na pasta.",
                why=(
                    f"A pasta '{folder.name}' não contém arquivos "
                    f"{', '.join(sorted(_SUPPORTED_EXTENSIONS))}."
                ),
                how=(
                    "Coloque arquivos .txt/.md/.json/.net/.pdf/.docx/.odt "
                    "na pasta selecionada "
                    "e tente novamente."
                ),
            )

        if len(candidate_files) > _MAX_FILES:
            candidate_files = candidate_files[:_MAX_FILES]
            log.warning("FolderImporter: limitando importação a %d arquivos.", _MAX_FILES)

        documents: List[Dict[str, Any]] = []
        warnings: List[str] = []
        total = max(1, len(candidate_files))

        for idx, file_path_obj in enumerate(candidate_files):
            progress = 0.10 + 0.80 * (idx / total)
            self._report_progress(progress, f"Importando: {file_path_obj.name}")

            try:
                from . import get_importer_for_file
                importer = get_importer_for_file(str(file_path_obj))
                result = importer.extract(str(file_path_obj))
                text = result.text
                doc_warnings = list(result.warnings or [])

                if text and text.strip():
                    documents.append({
                        "name": file_path_obj.stem,
                        "filename": file_path_obj.name,
                        "path": str(file_path_obj),
                        "text": text,
                        "warnings": doc_warnings,
                    })
                    warnings.extend(doc_warnings)
                else:
                    warnings.append(f"Arquivo vazio ignorado: {file_path_obj.name}")

            except Exception as exc:
                msg = f"Falha ao importar '{file_path_obj.name}': {exc}"
                warnings.append(msg)
                log.warning(msg)

        if not documents:
            raise ImporterError(
                what="Nenhum documento pôde ser importado da pasta.",
                why="Todos os arquivos encontrados estavam vazios ou causaram erros.",
                how=(
                    "Verifique se os arquivos suportados nao estao corrompidos "
                    "e nao estao protegidos por senha (no caso de PDFs)."
                ),
            )

        self._report_progress(0.95, "Montando corpus...")
        corpus_text = self._build_iramuteq_corpus(documents)

        self._report_progress(1.0, f"{len(documents)} documento(s) importado(s).")
        log.info("FolderImporter: %d docs de '%s'", len(documents), folder.name)

        return ImportResult(
            text=corpus_text,
            source_file=str(folder),
            encoding="utf-8",
            warnings=warnings,
            metadata={
                "collection_mode": True,
                "source_type": "folder",
                "folder_name": folder.name,
                "document_count": len(documents),
                "documents": documents,
                "iramuteq_text": corpus_text,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_files(folder: Path) -> List[Path]:
        """Coleta recursivamente todos os arquivos suportados da pasta."""
        results: List[Path] = []
        for path in sorted(folder.rglob("*")):
            if not path.is_file():
                continue
            # Ignorar pastas indesejadas
            if any(part in _IGNORED_DIRS for part in path.parts):
                continue
            # Ignorar arquivos escondidos macOS e similares
            if path.name.startswith("._") or path.name.startswith("."):
                continue
            if path.suffix.lower() in _SUPPORTED_EXTENSIONS:
                results.append(path)
        return results

    @staticmethod
    def _build_iramuteq_corpus(documents: List[Dict[str, Any]]) -> str:
        """Monta corpus IRaMuTeQ com um UCI por documento."""
        import re, unicodedata
        lines: List[str] = [""]  # Linha em branco inicial obrigatória

        for doc in documents:
            raw_name = str(doc.get("name", "doc")).strip()
            normalized = unicodedata.normalize("NFD", raw_name)
            normalized = "".join(
                c for c in normalized if unicodedata.category(c) != "Mn"
            )
            safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", normalized).lower()
            safe_name = re.sub(r"_+", "_", safe_name).strip("_") or "doc"

            lines.append(f"**** *doc_{safe_name}")
            lines.append(doc.get("text", "").strip())
            lines.append("")

        return "\n".join(lines)
