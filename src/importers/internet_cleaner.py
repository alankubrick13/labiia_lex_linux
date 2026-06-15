"""
Internet artifact cleaner for imported corpus text.

Uses the `clean-text` package when available and falls back to robust regexes.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from ..utils.logger import get_logger

log = get_logger(__name__)

_CLEAN_TEXT_FN: Optional[Callable[..., str]] = None
_CLEAN_TEXT_PROBED = False

_URL_RE = re.compile(r"(?i)\b(?:https?://|ftp://|www\.)\S+\b")
_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().\-]{7,}\d)(?!\w)")
_MENTION_RE = re.compile(r"(?<![\w])@[a-z0-9_]{2,}\b", re.IGNORECASE)


def _resolve_clean_text() -> Optional[Callable[..., str]]:
    global _CLEAN_TEXT_FN, _CLEAN_TEXT_PROBED
    if _CLEAN_TEXT_PROBED:
        return _CLEAN_TEXT_FN
    _CLEAN_TEXT_PROBED = True
    try:
        from cleantext import clean as clean_text

        _CLEAN_TEXT_FN = clean_text
        log.info("Pacote clean-text detectado para limpeza de dados da internet.")
    except Exception:
        _CLEAN_TEXT_FN = None
        log.warning(
            "Pacote clean-text indisponivel; usando fallback regex para limpeza web."
        )
    return _CLEAN_TEXT_FN


def _clean_line_with_package(text: str, clean_text_fn: Callable[..., str]) -> str:
    base_kwargs = {
        "fix_unicode": False,
        "to_ascii": False,
        "lower": False,
        "normalize_whitespace": True,
        "no_line_breaks": False,
        "strip_lines": False,
        "no_urls": True,
        "no_emails": True,
        "no_phone_numbers": True,
        "no_ip_addresses": True,
        "no_file_paths": True,
        "replace_with_url": "",
        "replace_with_email": "",
        "replace_with_phone_number": "",
        "replace_with_ip_address": "",
        "replace_with_file_path": "",
    }
    try:
        cleaned = clean_text_fn(text, **base_kwargs)
    except TypeError:
        # Backward-compat for older clean-text signatures.
        cleaned = clean_text_fn(
            text,
            no_urls=True,
            no_emails=True,
            no_phone_numbers=True,
            replace_with_url="",
            replace_with_email="",
            replace_with_phone_number="",
            lower=False,
            to_ascii=False,
            fix_unicode=False,
        )
    if not isinstance(cleaned, str):
        cleaned = str(cleaned or "")
    # Defensive cleanup in case replacement tokens are still present.
    cleaned = (
        cleaned.replace("<URL>", "")
        .replace("<EMAIL>", "")
        .replace("<PHONE>", "")
        .replace("<IP>", "")
        .replace("<FILE_PATH>", "")
    )
    return cleaned


def _clean_line_with_regex(text: str) -> str:
    cleaned = _URL_RE.sub("", text)
    cleaned = _EMAIL_RE.sub("", cleaned)
    cleaned = _IP_RE.sub("", cleaned)
    cleaned = _PHONE_RE.sub("", cleaned)
    cleaned = _MENTION_RE.sub("", cleaned)
    return cleaned


def clean_internet_artifacts(
    text: str,
    preserve_command_lines: bool = True,
) -> str:
    """
    Remove URLs, emails, phones, IPs and web-like artifacts from text.

    Args:
        text: Input corpus text.
        preserve_command_lines: Keep IRaMuTeQ command lines (`**** ...`) untouched.
    """
    raw = str(text or "")
    if not raw:
        return raw

    clean_text_fn = _resolve_clean_text()
    output_lines = []
    for line in raw.split("\n"):
        line_raw = str(line or "")
        if preserve_command_lines and line_raw.strip().startswith("****"):
            output_lines.append(line_raw)
            continue
        if preserve_command_lines and (
            "LINHA_CMD_INICIO" in line_raw or "QUATRO_AST_MARCADOR" in line_raw
        ):
            output_lines.append(line_raw)
            continue

        cleaned = (
            _clean_line_with_package(line_raw, clean_text_fn)
            if clean_text_fn is not None
            else _clean_line_with_regex(line_raw)
        )
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        output_lines.append(cleaned)

    return "\n".join(output_lines)

