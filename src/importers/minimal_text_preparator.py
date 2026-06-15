"""Minimal text preparation utilities for heterogeneous corpora."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


_CONTROL_CHARS_RE = re.compile(r"[\u0000-\u0008\u000b-\u001f\u007f]")
_ZERO_WIDTH_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_SPACE_RE = re.compile(r"[ \t\f\v]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_URL_RE = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_TOKEN_RE = re.compile(r"[\w_]+", re.UNICODE)


@dataclass(frozen=True)
class MinimalPreparationOptions:
    """Explicit options for preparation beyond the minimal default."""

    lowercase: bool = True
    remove_numbers: bool = False
    remove_accents: bool = False
    clean_web_data: bool = False


class MinimalTextPreparator:
    """Prepare text structurally without lexical filtering by default."""

    def prepare_text(
        self,
        text: str,
        options: MinimalPreparationOptions | None = None,
    ) -> str:
        cfg = options or MinimalPreparationOptions()
        prepared = unicodedata.normalize("NFKC", str(text or ""))
        prepared = prepared.replace("\r\n", "\n").replace("\r", "\n")
        prepared = _ZERO_WIDTH_RE.sub("", prepared)
        prepared = _CONTROL_CHARS_RE.sub(" ", prepared)

        if cfg.clean_web_data:
            prepared = _URL_RE.sub(" ", prepared)
            prepared = _EMAIL_RE.sub(" ", prepared)

        lines = []
        for raw_line in prepared.split("\n"):
            line = _SPACE_RE.sub(" ", raw_line).strip()
            if cfg.lowercase:
                line = line.lower()
            if cfg.remove_accents:
                line = self._strip_accents(line)
            if cfg.remove_numbers:
                line = self._drop_numeric_tokens(line)
            lines.append(line)

        prepared = "\n".join(lines)
        prepared = _BLANK_LINES_RE.sub("\n\n", prepared)
        prepared = "\n".join(line for line in prepared.split("\n") if line.strip())
        return prepared.strip()

    @staticmethod
    def _strip_accents(text: str) -> str:
        folded = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")

    @staticmethod
    def _drop_numeric_tokens(text: str) -> str:
        tokens = []
        for token in _TOKEN_RE.findall(text):
            if any(ch.isalpha() for ch in token):
                tokens.append(token)
        return " ".join(tokens)
