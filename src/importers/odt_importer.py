"""
ODTImporter - Importador para arquivos OpenDocument Text (.odt).
================================================================
Extrai texto do arquivo content.xml interno do pacote ODT.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import List

from .base_importer import BaseImporter, ImportResult, ImporterError
from ..utils.logger import get_logger


_OFFICE_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
_TEXT_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


class ODTImporter(BaseImporter):
    """Importador para documentos OpenDocument Text (.odt)."""

    SUPPORTED_EXTENSIONS: List[str] = [".odt"]

    def __init__(self) -> None:
        super().__init__()
        self._logger = get_logger(__name__)

    def can_handle(self, file_path: str) -> bool:
        ext = self._get_file_extension(file_path)
        return ext in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: str) -> ImportResult:
        path = self._validate_file_exists(file_path)
        warnings: List[str] = []

        if not zipfile.is_zipfile(path):
            raise ImporterError(
                what="Arquivo .odt invalido.",
                why=f"O arquivo '{path.name}' nao possui estrutura ZIP esperada do formato ODT.",
                how="Verifique se o arquivo e um .odt valido e tente novamente.",
            )

        try:
            with zipfile.ZipFile(path, "r") as zf:
                try:
                    content_xml = zf.read("content.xml")
                except KeyError:
                    raise ImporterError(
                        what="Arquivo ODT sem content.xml.",
                        why="A estrutura interna do ODT esta incompleta ou corrompida.",
                        how="Abra e salve novamente o arquivo no LibreOffice/Word para recriar a estrutura.",
                    )
        except ImporterError:
            raise
        except Exception as exc:
            raise ImporterError(
                what="Falha ao abrir o arquivo ODT.",
                why=str(exc),
                how="Verifique se o arquivo nao esta corrompido ou bloqueado por outro programa.",
            )

        text = self._extract_text_from_content_xml(content_xml)
        if not text.strip():
            warnings.append("O documento .odt nao contem texto extraivel.")

        words = text.split()
        metadata = {
            "line_count": len(text.splitlines()),
            "word_count": len(words),
            "char_count": len(text),
            "source_extension": ".odt",
            "file_size": self._get_file_size(file_path),
            "file_size_formatted": self._format_file_size(self._get_file_size(file_path)),
        }

        self._logger.info(
            "ODT importado: %s palavras, %s linhas",
            metadata["word_count"],
            metadata["line_count"],
        )

        return ImportResult(
            text=text,
            source_file=str(path),
            encoding="utf-8",
            warnings=warnings,
            metadata=metadata,
        )

    def _extract_text_from_content_xml(self, xml_bytes: bytes) -> str:
        """Extrai texto de paragrafos e titulos do content.xml."""
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            raise ImporterError(
                what="Nao foi possivel interpretar o XML interno do ODT.",
                why=str(exc),
                how="Verifique se o documento nao esta corrompido.",
            )

        office_text = root.find(f".//{{{_OFFICE_NS}}}text")
        if office_text is None:
            return ""

        paragraph_tags = {
            f"{{{_TEXT_NS}}}p",
            f"{{{_TEXT_NS}}}h",
            f"{{{_TEXT_NS}}}list-item",
        }
        blocks: List[str] = []
        for node in office_text.iter():
            if node.tag not in paragraph_tags:
                continue
            block = " ".join(part.strip() for part in node.itertext() if part and part.strip())
            block = re.sub(r"\s+", " ", block).strip()
            if block:
                blocks.append(block)

        return "\n\n".join(blocks).strip()
