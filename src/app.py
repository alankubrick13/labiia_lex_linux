"""Aplicacao principal do LabiiaLex (esqueleto)."""

from __future__ import annotations

from .core.config_manager import ConfigManager
from .utils.logger import get_logger


class LabiiaLexApp:
    """
    Esqueleto da aplicacao principal do LabiiaLex.
    """

    def __init__(self, config_path: str | None = None) -> None:
        """
        Inicializa a aplicacao.

        Args:
            config_path: Caminho opcional para o arquivo de configuracao.
        """
        self.logger = get_logger(__name__)
        self.config = ConfigManager(config_path=config_path)

    def run(self) -> None:
        """
        Inicia a aplicacao (placeholder).
        """
        self.logger.info("LabiiaLex iniciado. UI ainda nao implementada.")
