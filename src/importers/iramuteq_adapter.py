"""
Adaptação automática de texto para formato IRaMuTeQ.

Converte conteúdo bruto (TXT/PDF/DOCX/CSV/XLSX já extraído) em
blocos `**** *variavel_valor` sem exigir preparo manual do usuário.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import List


class IramuteqAutoAdapter:
    """Gera corpus IRaMuTeQ automaticamente a partir de texto livre."""

    _command_pattern = re.compile(r"^\s*\*{4}(?:\s|$)", re.MULTILINE)

    def to_iramuteq(
        self,
        text: str,
        source_file: str = "",
        source_label: str = "",
    ) -> str:
        """
        Retorna texto em formato IRaMuTeQ.

        Se o texto já contém `****`, retorna sem alterar estrutura.
        """
        raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if not raw:
            return ""
        if self._command_pattern.search(raw):
            return raw

        src_name = source_label or Path(source_file or "documento").stem or "documento"
        source_token = self._slugify(src_name, default="documento", max_len=24)
        source_ext = Path(source_file).suffix.lower().lstrip(".") if source_file else ""
        source_ext = self._slugify(source_ext, default="txt", max_len=12)

        documents = self._split_documents(raw)
        lines: List[str] = []
        for idx, doc in enumerate(documents, start=1):
            body = self._normalize_body(doc)
            if not body:
                continue
            lines.append(
                f"**** *doc_{idx} *fonte_{source_token} *tipo_{source_ext}"
            )
            lines.append(body)
            lines.append("")
        return "\n".join(lines).strip()

    def _split_documents(self, text: str) -> List[str]:
        """Heurística de segmentação em documentos para texto bruto."""
        blocks = [
            block.strip()
            for block in re.split(r"\n\s*\n+", text)
            if block and block.strip()
        ]
        if len(blocks) >= 2:
            return blocks

        return [text]

    @staticmethod
    def _normalize_body(text: str) -> str:
        """Normaliza corpo textual preservando quebras de parágrafo."""
        lines = [re.sub(r"\s+", " ", line).strip() for line in str(text).split("\n")]
        compact = [line for line in lines if line]
        return "\n".join(compact).strip()

    @staticmethod
    def _slugify(value: str, default: str, max_len: int = 32) -> str:
        """Normaliza token para padrão *nome_valor."""
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(
            char for char in normalized
            if unicodedata.category(char) != "Mn"
        )
        normalized = normalized.lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        if max_len > 0:
            normalized = normalized[:max_len].strip("_")
        return normalized or default
