"""
KWIC — Keyword-in-Context / Concordancer
==========================================
Inspirado no AntConc e no Sketch Engine Concordancer.

Funcionalidades:
  - Busca literal ou por regex (com flag case-insensitive opcional)
  - Contexto configurável (N tokens à esquerda / direita)
  - Ordenação: por contexto à esquerda, direita, ou posição no corpus
  - Metadados IRaMuTeQ por ocorrência (qual UCI, quais variáveis)
  - Estatísticas: frequência, dispersão (Juilland D)
  - Export CSV e TXT

Nenhum código foi copiado do AntConc ou Sketch Engine;
reimplementação a partir da documentação pública do método.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..utils.logger import get_logger

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Tipos
# ---------------------------------------------------------------------------

@dataclass
class KWICLine:
    """Uma linha de concordância (ocorrência)."""
    left_tokens:  List[str]   # tokens à esquerda (em ordem, mais próximo por último)
    keyword:      str         # forma como aparece no texto
    right_tokens: List[str]   # tokens à direita
    uci_index:    int         # índice da UCI onde ocorre
    uci_id:       str         # id da UCI (valor de *doc_X)
    uci_vars:     Dict[str, str]    # variáveis da UCI
    token_pos:    int         # posição absoluta no corpus (em tokens)
    sentence:     str         # sentença completa (para context preview)

    @property
    def left_str(self) -> str:
        return " ".join(self.left_tokens)

    @property
    def right_str(self) -> str:
        return " ".join(self.right_tokens)

    @property
    def sort_key_left(self) -> str:
        """Contexto esquerdo invertido — para ordenar por colócato imediato."""
        return " ".join(reversed(self.left_tokens))

    @property
    def sort_key_right(self) -> str:
        return " ".join(self.right_tokens)


@dataclass
class KWICResult:
    """Resultado completo de uma busca KWIC."""
    query:           str
    lines:           List[KWICLine]
    total_tokens:    int
    total_ucis:      int
    frequency:       int          # n.º total de ocorrências
    dispersion_d:    float        # Juilland D (0–1)
    ucis_with_hits:  int          # n.º de UCIs com ao menos 1 hit
    context_size:    int
    is_regex:        bool

    @property
    def relative_freq(self) -> float:
        """Frequência relativa por 1000 tokens."""
        if self.total_tokens == 0:
            return 0.0
        return self.frequency / self.total_tokens * 1000

    def sorted_by(self, key: str) -> List[KWICLine]:
        """
        Ordena as linhas.

        Args:
            key: "pos" | "left1" | "right1" | "uci"
        """
        if key == "left1":
            return sorted(self.lines, key=lambda l: l.sort_key_left)
        elif key == "right1":
            return sorted(self.lines, key=lambda l: l.sort_key_right)
        elif key == "uci":
            return sorted(self.lines, key=lambda l: (l.uci_index, l.token_pos))
        else:
            return list(self.lines)  # natural (pos)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_CMD_RE  = re.compile(r"^\s*\*{4}(.*)$", re.MULTILINE)
_VAR_RE  = re.compile(r"\*([a-zA-ZÀ-ÿ0-9][a-zA-ZÀ-ÿ0-9_-]*)_([a-zA-ZÀ-ÿ0-9_.+\-]+)")
_WORD_RE = re.compile(
    r"\b[a-zA-ZàáâãäéêëíîïóôõöúûüçñÀÁÂÃÄÉÊËÍÎÏÓÔÕÖÚÛÜÇÑ][a-zA-ZàáâãäéêëíîïóôõöúûüçñÀÁÂÃÄÉÊËÍÎÏÓÔÕÖÚÛÜÇÑ_-]*\b"
)


@dataclass
class _UCIRecord:
    index:   int
    uci_id:  str
    vars:    Dict[str, str]
    tokens:  List[str]         # forma original de cada token
    starts:  List[int]         # posição global do token no corpus


class KWICEngine:
    """
    Engine KWIC para corpus IRaMuTeQ.

    Uso::
        engine = KWICEngine(raw_text)
        result = engine.search("democracia", context=5)
        for line in result.sorted_by("left1"):
            print(line.left_str, ">>>", line.keyword, "<<<", line.right_str)
    """

    def __init__(self, raw_text: str) -> None:
        self._raw_text = raw_text
        self._ucis: List[_UCIRecord] = []
        self._all_tokens: List[str] = []        # tokens globais (forma original)
        self._token_to_uci: List[int] = []      # token_idx → uci_idx
        self._parse()

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse(self) -> None:
        lines  = self._raw_text.splitlines(keepends=True)
        current_vars:   Dict[str, str] = {}
        current_tokens: List[str]      = []
        current_starts: List[int]      = []
        uci_header:     Optional[str]  = None
        uci_idx = 0

        def _flush():
            nonlocal uci_idx
            if uci_header is None:
                return
            uci_id = current_vars.get("doc", str(uci_idx))
            self._ucis.append(_UCIRecord(
                index=uci_idx,
                uci_id=uci_id,
                vars=dict(current_vars),
                tokens=list(current_tokens),
                starts=list(current_starts),
            ))
            uci_idx += 1
            current_tokens.clear()
            current_starts.clear()

        for line in lines:
            if _CMD_RE.match(line):
                _flush()
                uci_header   = line.rstrip("\r\n")
                current_vars = {n: v for n, v in _VAR_RE.findall(line)}
            else:
                if uci_header is not None:
                    for m in _WORD_RE.finditer(line):
                        global_pos = len(self._all_tokens)
                        word = m.group(0)
                        self._all_tokens.append(word)
                        current_tokens.append(word)
                        current_starts.append(global_pos)

        _flush()

        # Construir índice token → UCI
        self._token_to_uci = [0] * len(self._all_tokens)
        for uci in self._ucis:
            for gpos in uci.starts:
                self._token_to_uci[gpos] = uci.index

        log.debug("KWIC: %d tokens, %d UCIs", len(self._all_tokens), len(self._ucis))

    # ------------------------------------------------------------------
    # Busca
    # ------------------------------------------------------------------

    @staticmethod
    def _fold(text: str) -> str:
        nfd = unicodedata.normalize("NFD", text)
        return "".join(c for c in nfd if unicodedata.category(c) != "Mn").lower()

    def search(
        self,
        query: str,
        context: int = 5,
        case_sensitive: bool = False,
        use_regex: bool = False,
        max_hits: int = 5000,
    ) -> KWICResult:
        """
        Busca uma palavra-chave ou padrão no corpus.

        Args:
            query:           Termo ou regex a buscar.
            context:         N.º de tokens de contexto (esq. e dir.).
            case_sensitive:  Se True, respeita maiúsculas.
            use_regex:       Se True, trata query como regex.
            max_hits:        Limite de linhas retornadas.

        Returns:
            KWICResult.
        """
        tokens = self._all_tokens
        n = len(tokens)
        if n == 0:
            return self._empty_result(query, use_regex)

        context = max(1, context)

        # Construir lista de tokens normalizados para matching
        if case_sensitive:
            norm_tokens = tokens
        else:
            norm_tokens = [self._fold(t) for t in tokens]

        # Padrão de match
        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                pattern = re.compile(r"^(?:" + query + r")$", flags)
            except re.error as exc:
                raise ValueError(f"Regex inválida: {exc}") from exc
            match_fn = lambda t: bool(pattern.match(t))
        else:
            q = query if case_sensitive else self._fold(query)
            match_fn = lambda t: t == q

        # Varrer tokens
        lines: List[KWICLine] = []
        uci_hits: Dict[int, int] = {}   # uci_idx → contagem

        for i, tok in enumerate(norm_tokens):
            if not match_fn(tok):
                continue

            uci_idx  = self._token_to_uci[i]
            uci      = self._ucis[uci_idx]
            uci_hits[uci_idx] = uci_hits.get(uci_idx, 0) + 1

            # Contextos (tokens originais)
            left_start  = max(0, i - context)
            right_end   = min(n, i + context + 1)
            left_toks   = tokens[left_start:i]
            right_toks  = tokens[i + 1:right_end]

            # Sentença de contexto para preview (usa tokens originais)
            sentence = " ".join(tokens[left_start:right_end])

            lines.append(KWICLine(
                left_tokens  = left_toks,
                keyword      = tokens[i],
                right_tokens = right_toks,
                uci_index    = uci_idx,
                uci_id       = uci.uci_id,
                uci_vars     = uci.vars,
                token_pos    = i,
                sentence     = sentence,
            ))

            if len(lines) >= max_hits:
                log.warning("KWIC: limite de %d hits atingido", max_hits)
                break

        freq       = len(uci_hits) and sum(uci_hits.values()) or 0
        disp_d     = self._juilland_d(uci_hits, len(self._ucis))

        return KWICResult(
            query          = query,
            lines          = lines,
            total_tokens   = n,
            total_ucis     = len(self._ucis),
            frequency      = sum(uci_hits.values()),
            dispersion_d   = disp_d,
            ucis_with_hits = len(uci_hits),
            context_size   = context,
            is_regex       = use_regex,
        )

    def _empty_result(self, query, is_regex) -> KWICResult:
        return KWICResult(
            query=query, lines=[], total_tokens=0, total_ucis=0,
            frequency=0, dispersion_d=0.0, ucis_with_hits=0,
            context_size=5, is_regex=is_regex,
        )

    # ------------------------------------------------------------------
    # Métricas
    # ------------------------------------------------------------------

    @staticmethod
    def _juilland_d(uci_hits: Dict[int, int], n_ucis: int) -> float:
        """
        Juilland D — medida de dispersão entre 0 e 1.
        D = 1 - (CV / sqrt(n_ucis - 1))   onde CV = desvio/média.
        D próximo de 1 = distribuído uniformemente.
        """
        if n_ucis < 2 or not uci_hits:
            return 0.0
        freqs = list(uci_hits.values())
        # Completar UCIs sem hits
        all_freqs = freqs + [0] * (n_ucis - len(freqs))
        mean = sum(all_freqs) / n_ucis
        if mean == 0:
            return 0.0
        variance = sum((f - mean) ** 2 for f in all_freqs) / n_ucis
        std = math.sqrt(variance)
        cv  = std / mean
        d   = max(0.0, 1.0 - cv / math.sqrt(n_ucis - 1))
        return round(d, 4)

    # ------------------------------------------------------------------
    # Múltiplas buscas simultâneas
    # ------------------------------------------------------------------

    def search_multiple(
        self,
        queries: List[str],
        context: int = 5,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> List[KWICResult]:
        return [
            self.search(q, context=context,
                        case_sensitive=case_sensitive, use_regex=use_regex)
            for q in queries
        ]

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    @staticmethod
    def export_csv(result: KWICResult, path, sort_key: str = "pos") -> None:
        import csv
        from pathlib import Path
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = result.sorted_by(sort_key)
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["#", "UCI", "Contexto Esq.", "KEYWORD", "Contexto Dir.", "Variáveis"])
            for i, line in enumerate(lines, 1):
                vars_str = "  ".join(f"{k}={v}" for k, v in sorted(line.uci_vars.items()))
                w.writerow([i, line.uci_id, line.left_str, line.keyword, line.right_str, vars_str])
        log.info("KWIC CSV exportado: %s", path)

    @staticmethod
    def export_txt(result: KWICResult, path, sort_key: str = "pos") -> None:
        from pathlib import Path
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        lines = result.sorted_by(sort_key)
        ctx   = result.context_size
        kw_w  = max(len(result.query) + 4, 20)
        col_w = ctx * 12

        with path.open("w", encoding="utf-8") as f:
            f.write(f"KWIC — '{result.query}'\n")
            f.write(f"Freq: {result.frequency}  DispD: {result.dispersion_d:.3f}  "
                    f"RelFreq: {result.relative_freq:.2f}/1k\n")
            f.write("─" * (col_w * 2 + kw_w + 10) + "\n")
            for ln in lines:
                left  = ln.left_str.rjust(col_w)[:col_w]
                kw    = f"[{ln.keyword}]"
                right = ln.right_str.ljust(col_w)[:col_w]
                f.write(f"{left}  {kw:{kw_w}}  {right}  [{ln.uci_id}]\n")
        log.info("KWIC TXT exportado: %s", path)
