"""
Contrato de navegação e conteúdo para o visualizador de resultados.
"""

from __future__ import annotations

from typing import Iterable, List


class ResultViewContract:
    """Define ordem e nomes canônicos das abas de conteúdo."""

    CONTENT_TAB_ORDER = ("Estatísticas", "Tabela", "Gráfico", "Relatório")

    @classmethod
    def normalize_content_tab(cls, value: str) -> str:
        token = str(value or "").strip().lower()
        mapping = {
            "estatisticas": "Estatísticas",
            "estatísticas": "Estatísticas",
            "tabela": "Tabela",
            "grafico": "Gráfico",
            "gráfico": "Gráfico",
            "relatorio": "Relatório",
            "relatório": "Relatório",
        }
        return mapping.get(token, "Gráfico")

    @classmethod
    def ordered_existing_tabs(cls, candidates: Iterable[str]) -> List[str]:
        normalized = {cls.normalize_content_tab(item) for item in candidates}
        return [tab for tab in cls.CONTENT_TAB_ORDER if tab in normalized]

