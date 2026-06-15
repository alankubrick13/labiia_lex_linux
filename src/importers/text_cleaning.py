"""
Utilitarios de limpeza textual para importacao.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, List


def limpar_texto(texto_bruto: str, min_line_chars: int = 20) -> str:
    """
    Limpa e normaliza texto bruto para analise lexicometrica.

    Ordem do pipeline:
    1) Remove hifenizacao de fim de linha.
    2) Normaliza espacos e quebras de linha.
    3) Filtra linhas estruturais curtas (cabecalho/rodape provavel),
       preservando linhas vazias intencionais.
    4) Reconstroi paragrafos com quebra dupla entre blocos.
    """
    text = str(texto_bruto or "")
    if not text:
        return ""

    # 1) Hifenizacao: "governa-\nmento" -> "governamento"
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)

    # 2) Espacamento de base por linha
    normalized_lines: List[str] = []
    for raw_line in text.split("\n"):
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        normalized_lines.append(line)

    # 3) Filtro estrutural
    filtered_lines: List[str] = []
    for line in normalized_lines:
        if not line:
            filtered_lines.append("")
            continue
        if _is_structural_noise(line, min_line_chars=min_line_chars):
            continue
        filtered_lines.append(line)

    # 4) Reconstrucao de paragrafos
    paragraphs: List[str] = []
    current: List[str] = []
    for line in filtered_lines:
        if not line:
            if current:
                paragraphs.append(" ".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append(" ".join(current).strip())

    cleaned = "\n\n".join(p for p in paragraphs if p)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def extrair_variaveis_do_nome_arquivo(file_path: str) -> Dict[str, str]:
    """
    Extrai variaveis simples para metadados IRaMuTeQ a partir do nome do arquivo.

    Exemplo:
      "reuniao_5_ano_2023.pdf" -> {"reuniao": "5", "ano": "2023"}
    """
    stem = Path(str(file_path or "")).stem
    if not stem:
        return {}

    folded = unicodedata.normalize("NFD", stem)
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    folded = re.sub(r"[^a-zA-Z0-9_]+", "_", folded).lower()
    folded = re.sub(r"_+", "_", folded).strip("_")
    if not folded:
        return {}

    parts = [part for part in folded.split("_") if part]
    pairs: Dict[str, str] = {}

    i = 0
    while i < len(parts) - 1:
        left = parts[i]
        right = parts[i + 1]
        if not left or not right:
            i += 1
            continue
        if left in pairs:
            i += 1
            continue
        if _looks_like_value(right):
            pairs[left] = right
            i += 2
            continue
        i += 1

    return pairs


def _is_structural_noise(line: str, min_line_chars: int) -> bool:
    stripped = str(line or "").strip()
    if not stripped:
        return False

    # Numeracao de pagina isolada.
    if re.fullmatch(r"(?:p[aá]gina\s*)?\d+", stripped, flags=re.IGNORECASE):
        return True

    # Linhas curtas tendem a ser cabecalho/rodape em PDFs academicos.
    threshold = max(0, int(min_line_chars or 0))
    if threshold > 0 and len(stripped) < threshold:
        return True

    return False


def _looks_like_value(value: str) -> bool:
    v = str(value or "").strip().lower()
    if not v:
        return False
    if re.fullmatch(r"\d{1,4}", v):
        return True
    if len(v) <= 3:
        return True
    return False
