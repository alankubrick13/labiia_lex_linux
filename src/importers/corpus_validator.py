"""
Validador de corpus no formato IRaMuTeQ.

Valida estrutura minima antes de processar:
- Marcadores de UCI com "****"
- Variaveis no formato "*nome_valor"
- Conteudo textual entre UCIs
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from statistics import mean
from typing import Dict, List, Optional

from ..utils.logger import get_logger


@dataclass(frozen=True)
class ValidationIssue:
    """Problema de validacao encontrado no corpus."""

    line_number: int
    what: str
    why: str
    how: str


@dataclass(frozen=True)
class ValidationReport:
    """Relatorio completo da validacao do corpus."""

    is_valid: bool
    warnings: List[str]
    errors: List[ValidationIssue]
    stats: Dict[str, float]
    suggestions: List[str]


class CorpusValidationError(Exception):
    """
    Erro amigavel de validacao de corpus.

    Segue o padrao:
    - O que aconteceu
    - Por que aconteceu
    - Como resolver
    """

    def __init__(self, issues: List[ValidationIssue]):
        self.issues = issues
        if issues:
            first = issues[0]
            extra = (
                f"\n\nForam encontrados mais {len(issues) - 1} problema(s)."
                if len(issues) > 1
                else ""
            )
            message = (
                f"O que aconteceu: Linha {first.line_number}: {first.what}\n"
                f"Por que aconteceu: {first.why}\n"
                f"Como resolver: {first.how}"
                f"{extra}"
            )
        else:
            message = (
                "O que aconteceu: O corpus e invalido.\n"
                "Por que aconteceu: Foram detectados erros de formato IRaMuTeQ.\n"
                "Como resolver: Revise a estrutura do corpus e tente novamente."
            )
        super().__init__(message)


class CorpusValidator:
    """Valida texto no formato esperado pelo IRaMuTeQ."""

    _variable_pattern = re.compile(r"^\*[A-Za-z0-9]+_[A-Za-z0-9_]+$")
    _command_marker_pattern = re.compile(r"^\*{4,}(?=\s|$)")
    _invisible_prefix_pattern = re.compile(r"^[\ufeff\u200b\u200c\u200d]+")
    _mojibake_patterns = (
        "Ã¡", "Ã£", "Ã©", "Ã§", "Ã³", "Ãª", "Ãº", "â€", "ï»¿", "�"
    )

    def __init__(self) -> None:
        self._logger = get_logger(__name__)

    def validate(self, text: str) -> ValidationReport:
        """
        Retorna relatorio de validacao completo.
        """
        issues: List[ValidationIssue] = []
        warnings: List[str] = []
        stats: Dict[str, float] = {
            "total_lines": 0,
            "total_ucis": 0,
            "empty_ucis": 0,
            "mean_block_lines": 0.0,
            "min_block_lines": 0.0,
            "max_block_lines": 0.0,
        }

        if not text or not text.strip():
            issues.append(
                ValidationIssue(
                    line_number=1,
                    what="O corpus esta vazio.",
                    why="Nenhum texto valido foi encontrado para analise.",
                    how="Importe um arquivo com conteudo textual no formato IRaMuTeQ.",
                )
            )
            return ValidationReport(
                is_valid=False,
                warnings=[],
                errors=issues,
                stats=stats,
                suggestions=[
                    "Adicione pelo menos um documento com a linha de comando '**** *variavel_valor'.",
                ],
            )

        lines = text.splitlines()
        stats["total_lines"] = float(len(lines))
        command_indices: List[int] = []
        potential_bad_markers: List[int] = []

        for idx, raw_line in enumerate(lines):
            line_no = idx + 1
            line = self._normalize_command_marker(raw_line.strip())
            if not line:
                continue

            if self._command_marker_pattern.match(line):
                command_indices.append(idx)
                if line != raw_line.strip():
                    warnings.append(
                        f"Linha {line_no}: marcador de comando normalizado para '****'."
                    )
                if len(line.split()) == 1:
                    warnings.append(
                        f"Linha {line_no}: linha de comando sem variaveis; o corpus foi mantido porque ha texto associado."
                    )
                issues.extend(self._validate_command_line(line_no, line))
            elif line.startswith("***"):
                potential_bad_markers.append(line_no)

        if any(pattern in text for pattern in self._mojibake_patterns):
            warnings.append(
                "Possível problema de encoding (mojibake) detectado. Verifique acentuação e salve em UTF-8."
            )
        if potential_bad_markers:
            warnings.append(
                "Foram encontradas linhas com '***' (três asteriscos). O marcador correto é '****'."
            )

        if not command_indices:
            issues.append(
                ValidationIssue(
                    line_number=1,
                    what="Nenhum marcador de UCI ('****') foi encontrado.",
                    why="O formato IRaMuTeQ exige uma linha de comando antes de cada documento.",
                    how="Adicione linhas como '**** *grupo_teste' antes de cada bloco de texto.",
                )
            )
            return ValidationReport(
                is_valid=False,
                warnings=warnings,
                errors=issues,
                stats=stats,
                suggestions=self._build_suggestions(issues, warnings),
            )

        block_sizes, empty_ucis, block_warnings = self._validate_text_blocks(lines, command_indices)
        issues.extend(empty_ucis)
        warnings.extend(block_warnings)

        stats["total_ucis"] = float(len(command_indices))
        stats["empty_ucis"] = float(
            sum(1 for issue in empty_ucis if issue.what == "UCI sem conteudo textual.")
        )
        if block_sizes:
            stats["mean_block_lines"] = float(mean(block_sizes))
            stats["min_block_lines"] = float(min(block_sizes))
            stats["max_block_lines"] = float(max(block_sizes))

        suggestions = self._build_suggestions(issues, warnings)
        return ValidationReport(
            is_valid=len(issues) == 0,
            warnings=warnings,
            errors=issues,
            stats=stats,
            suggestions=suggestions,
        )

    def validate_or_raise(self, text: str) -> None:
        """Valida e levanta excecao amigavel se houver problemas."""
        report = self.validate(text)
        if report.errors:
            self._logger.warning(
                "Validacao de corpus falhou com %s problema(s)", len(report.errors)
            )
            raise CorpusValidationError(report.errors)
        self._logger.debug("Validacao de corpus IRaMuTeQ concluida sem erros")

    def _validate_command_line(self, line_no: int, line: str) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        parts = line.split()
        if not parts:
            return issues

        if parts[0] != "****":
            issues.append(
                ValidationIssue(
                    line_number=line_no,
                    what="Marcador de comando invalido.",
                    why="A linha de comando deve comecar exatamente com '****'.",
                    how="Corrija o inicio da linha para o formato: **** *nome_valor",
                )
            )
            return issues

        if len(parts) == 1:
            return issues

        for token in parts[1:]:
            if not token.startswith("*"):
                issues.append(
                    ValidationIssue(
                        line_number=line_no,
                        what=f"Token '{token}' invalido na linha de comando.",
                        why="Variaveis do IRaMuTeQ precisam comecar com '*'.",
                        how="Use variaveis no formato *nome_valor.",
                    )
                )
                continue

            if "_" not in token[1:]:
                issues.append(
                    ValidationIssue(
                        line_number=line_no,
                        what=f"Variavel '{token}' sem separador '_' .",
                        why="O formato esperado e *nome_valor.",
                        how="Adicione '_' separando nome e valor, por exemplo: *sexo_f.",
                    )
                )
                continue

            if not self._variable_pattern.match(token):
                issues.append(
                    ValidationIssue(
                        line_number=line_no,
                        what=f"Variavel '{token}' com caracteres invalidos.",
                        why="Somente letras, numeros e underscore sao aceitos em *nome_valor.",
                        how="Remova acentos e simbolos especiais da variavel.",
                    )
                )

        return issues

    def _normalize_command_marker(self, line: str) -> str:
        cleaned = self._invisible_prefix_pattern.sub("", str(line or "").strip())
        if self._command_marker_pattern.match(cleaned):
            return self._command_marker_pattern.sub("****", cleaned, count=1).strip()
        return cleaned

    def _validate_text_blocks(
        self, lines: List[str], command_indices: List[int]
    ) -> tuple[List[int], List[ValidationIssue], List[str]]:
        issues: List[ValidationIssue] = []
        warnings: List[str] = []
        block_sizes: List[int] = []

        for pos, start_idx in enumerate(command_indices):
            end_idx = (
                command_indices[pos + 1]
                if pos + 1 < len(command_indices)
                else len(lines)
            )
            block_lines = lines[start_idx + 1 : end_idx]
            non_empty_lines = [line for line in block_lines if line.strip()]
            block_sizes.append(len(non_empty_lines))
            if not non_empty_lines:
                issues.append(
                    ValidationIssue(
                        line_number=start_idx + 1,
                        what="UCI sem conteudo textual.",
                        why="A linha de comando existe, mas nao ha texto associado a ela.",
                        how="Adicione ao menos uma frase apos a linha de comando.",
                    )
                )

        non_zero_blocks = [size for size in block_sizes if size > 0]
        if len(non_zero_blocks) >= 2:
            largest = max(non_zero_blocks)
            smallest = min(non_zero_blocks)
            if smallest > 0 and largest / smallest >= 10:
                warnings.append(
                    "UCIs com tamanhos muito diferentes detectadas. Isso pode afetar a estabilidade das classes."
                )

        return block_sizes, issues, warnings

    def _build_suggestions(
        self,
        issues: List[ValidationIssue],
        warnings: List[str],
    ) -> List[str]:
        suggestions: List[str] = []
        if any("marcador de UCI" in issue.what.lower() for issue in issues):
            suggestions.append("Inclua uma linha '**** *grupo_valor' antes de cada documento.")
        if any("variavel" in issue.what.lower() for issue in issues):
            suggestions.append("Use variáveis no formato *nome_valor com apenas letras, números e underscore.")
        if any("UCI sem conteudo".lower() in issue.what.lower() for issue in issues):
            suggestions.append("Garanta texto entre duas linhas '****'.")
        if any("encoding" in warning.lower() or "mojibake" in warning.lower() for warning in warnings):
            suggestions.append("Reabra o arquivo e salve em UTF-8 sem BOM para evitar caracteres corrompidos.")
        if not suggestions:
            suggestions.append("Corpus válido. Você pode prosseguir com a importação.")
        return suggestions


def validate_iramuteq_corpus(text: str, validator: Optional[CorpusValidator] = None) -> None:
    """Atalho para validar corpus IRaMuTeQ e levantar erro amigavel."""
    active_validator = validator or CorpusValidator()
    active_validator.validate_or_raise(text)
