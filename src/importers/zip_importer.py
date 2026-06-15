"""
ZipImporter - Importa coleções de documentos de um arquivo ZIP.
================================================================
Extrai todos os arquivos de texto suportados de um ZIP e combina
como corpus multi-documento (um arquivo = um UCI no corpus IRaMuTeQ).

Suporte a:
  - .txt/.md/.json/.net — texto
  - .pdf  — extrai texto via PDFImporter
  - .docx — extrai texto via DOCXImporter
  - .odt  — extrai texto via ODTImporter
  Arquivos macOS ._xxx ignorados automaticamente.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .base_importer import BaseImporter, ImporterError, ImportResult
from ..utils.logger import get_logger

log = get_logger(__name__)

_SUPPORTED_EXTENSIONS = {".txt", ".md", ".json", ".net", ".pdf", ".docx", ".odt"}
_MACOS_PREFIX = "._"
_IGNORED_DIRS = {"__MACOSX", ".git"}


class ZipImporter(BaseImporter):
    """
    Importa todos os documentos de texto de um arquivo ZIP como coleção.

    Cada arquivo dentro do ZIP vira um documento separado (UCI) no corpus.
    Adequado para o Fluxo B (multi-documento) e CCA/Textometrica.
    """

    SUPPORTED_EXTENSIONS: List[str] = [".zip"]

    def can_handle(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() == ".zip"

    def extract(self, file_path: str) -> ImportResult:
        """
        Extrai todos os documentos do ZIP como corpus multi-documento.

        Retorna ImportResult onde:
          - result.text   = corpus IRaMuTeQ com N UCIs (um por arquivo)
          - result.metadata['collection_mode'] = True
          - result.metadata['documents'] = lista de {name, text, warnings}
        """
        path = self._validate_file_exists(file_path)

        if not zipfile.is_zipfile(str(path)):
            raise ImporterError(
                what="Arquivo ZIP inválido.",
                why=f"O arquivo '{path.name}' não é um ZIP válido ou está corrompido.",
                how="Verifique se o arquivo ZIP está completo e não corrompido.",
            )

        self._report_progress(0.05, "Abrindo arquivo ZIP...")

        documents: List[Dict[str, Any]] = []
        warnings: List[str] = []

        with zipfile.ZipFile(str(path), "r") as zf:
            entries = [e for e in zf.infolist() if not e.is_dir()]
            total = max(1, len(entries))

            for idx, entry in enumerate(entries):
                name = entry.filename
                entry_path = Path(name)

                # Ignorar macOS e diretórios indesejados
                if entry_path.name.startswith(_MACOS_PREFIX):
                    continue
                if any(part in _IGNORED_DIRS for part in entry_path.parts):
                    continue

                ext = entry_path.suffix.lower()
                if ext not in _SUPPORTED_EXTENSIONS:
                    continue

                progress = 0.1 + 0.8 * (idx / total)
                self._report_progress(progress, f"Extraindo: {entry_path.name}")

                try:
                    text, doc_warnings = self._extract_entry(zf, entry, ext)
                    if text and text.strip():
                        documents.append({
                            "name": entry_path.stem,
                            "filename": entry_path.name,
                            "text": text,
                            "warnings": doc_warnings,
                        })
                        warnings.extend(doc_warnings)
                        log.debug("Extraído: %s (%d chars)", entry_path.name, len(text))
                    else:
                        warnings.append(f"Arquivo vazio ignorado: {entry_path.name}")
                except Exception as exc:
                    msg = f"Falha ao extrair '{entry_path.name}': {exc}"
                    warnings.append(msg)
                    log.warning(msg)

        if not documents:
            raise ImporterError(
                what="Nenhum documento encontrado no ZIP.",
                why=(
                    "O arquivo ZIP não contém arquivos de texto suportados "
                    f"({', '.join(sorted(_SUPPORTED_EXTENSIONS))})."
                ),
                how=(
                    "Certifique-se de que o ZIP contem arquivos suportados "
                    "(.txt/.md/.json/.net/.pdf/.docx/.odt). "
                    "Arquivos de subpastas também são incluídos automaticamente."
                ),
            )

        self._report_progress(0.95, "Montando corpus...")
        corpus_text = self._build_iramuteq_corpus(documents)

        self._report_progress(1.0, f"ZIP importado: {len(documents)} documento(s).")
        log.info("ZipImporter: %d documentos extraídos de %s", len(documents), path.name)

        return ImportResult(
            text=corpus_text,
            source_file=str(path),
            encoding="utf-8",
            warnings=warnings,
            metadata={
                "collection_mode": True,
                "source_type": "zip",
                "zip_name": path.name,
                "document_count": len(documents),
                "documents": documents,
                "iramuteq_text": corpus_text,
            },
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_entry(
        self,
        zf: zipfile.ZipFile,
        entry: zipfile.ZipInfo,
        ext: str,
    ) -> tuple[str, List[str]]:
        """Extrai texto de um membro do ZIP de acordo com seu formato."""
        import tempfile, os

        raw_bytes = zf.read(entry.filename)

        if ext in {".txt", ".md"}:
            text = self._decode_bytes(raw_bytes)
            return text, []

        # Para formatos com parser proprio, salvar temporariamente
        # e delegar para o importador correspondente.
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, dir=tempfile.gettempdir()
        ) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        doc_warnings: List[str] = []
        try:
            importer = self._get_sub_importer(ext)
            result = importer.extract(tmp_path)
            text = result.text
            doc_warnings = result.warnings or []
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return text, doc_warnings

    @staticmethod
    def _decode_bytes(raw: bytes) -> str:
        """Tenta decodificar bytes de texto com fallback robusto."""
        for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")

    @staticmethod
    def _get_sub_importer(ext: str) -> BaseImporter:
        """Retorna importador adequado para uma extensão."""
        if ext == ".pdf":
            from .pdf_importer import PDFImporter
            return PDFImporter()
        if ext == ".docx":
            from .docx_importer import DOCXImporter
            return DOCXImporter()
        if ext == ".odt":
            from .odt_importer import ODTImporter
            return ODTImporter()
        if ext in {".json", ".net", ".md", ".txt"}:
            from .txt_importer import TXTImporter
            return TXTImporter()
        raise ImporterError(
            what=f"Sem importador para '{ext}'.",
            why="Formato não suportado dentro do ZIP.",
            how="Use apenas formatos suportados dentro do ZIP "
                "(.txt/.md/.json/.net/.pdf/.docx/.odt).",
        )

    @staticmethod
    def _build_iramuteq_corpus(documents: List[Dict[str, Any]]) -> str:
        """
        Monta corpus no formato IRaMuTeQ com um UCI por documento.

        Formato:
          **** *doc_nome_do_arquivo
          Texto do documento...

          **** *doc_outro_arquivo
          ...
        """
        lines: List[str] = [""]  # Linha em branco inicial obrigatória

        for doc in documents:
            # Sanitiza o nome do documento para variável IRaMuTeQ
            import re, unicodedata
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
