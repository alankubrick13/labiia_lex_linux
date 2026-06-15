"""
BaseImporter - Classe base para todos os importadores de documentos.
=====================================================================
Define a interface comum e fornece funcionalidades compartilhadas
como detecção de encoding.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import chardet

from ..utils.logger import get_logger


@dataclass
class ImportResult:
    """
    Resultado de uma importação de documento.
    
    Attributes:
        text: Texto extraído do documento.
        source_file: Caminho do arquivo de origem.
        encoding: Encoding detectado ou utilizado.
        warnings: Lista de avisos gerados durante a importação.
        metadata: Metadados adicionais (páginas, parágrafos, etc).
    """
    text: str
    source_file: str
    encoding: str = "utf-8"
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class ImporterError(Exception):
    """
    Exceção amigável para erros de importação.
    
    Segue o padrão:
    - O que aconteceu
    - Por que aconteceu
    - Como resolver
    """
    
    def __init__(self, what: str, why: str, how: str, original_error: Optional[Exception] = None):
        self.what = what
        self.why = why
        self.how = how
        self.original_error = original_error
        message = f"O que aconteceu: {what}\nPor que aconteceu: {why}\nComo resolver: {how}"
        super().__init__(message)


class BaseImporter(ABC):
    """
    Classe base abstrata para importadores de documentos.
    
    Todos os importadores devem herdar desta classe e implementar:
    - can_handle(file_path): Verifica se pode processar o arquivo
    - extract(file_path): Extrai texto do arquivo
    """
    
    # Extensões suportadas (sobrescrever nas subclasses)
    SUPPORTED_EXTENSIONS: List[str] = []
    
    def __init__(self) -> None:
        self._logger = get_logger(__name__)
        self._progress_callback: Optional[Callable[[float, str], None]] = None

    def set_progress_callback(
        self,
        callback: Optional[Callable[[float, str], None]],
    ) -> None:
        """Registra callback opcional para progresso (0.0-1.0, mensagem)."""
        self._progress_callback = callback

    def _report_progress(self, progress: float, message: str = "") -> None:
        """Notifica progresso de importação, se callback estiver configurado."""
        if self._progress_callback is None:
            return
        try:
            value = float(progress)
        except (TypeError, ValueError):
            value = 0.0
        value = max(0.0, min(1.0, value))
        try:
            self._progress_callback(value, str(message or ""))
        except Exception:
            # Progresso nunca deve interromper a importação.
            self._logger.debug("Falha ao reportar progresso de importacao", exc_info=True)
    
    @abstractmethod
    def can_handle(self, file_path: str) -> bool:
        """
        Verifica se este importador pode processar o arquivo.
        
        Args:
            file_path: Caminho do arquivo a verificar.
            
        Returns:
            True se o importador pode processar o arquivo.
        """
        pass
    
    @abstractmethod
    def extract(self, file_path: str) -> ImportResult:
        """
        Extrai texto do arquivo.
        
        Args:
            file_path: Caminho do arquivo a processar.
            
        Returns:
            ImportResult com o texto extraído e metadados.
            
        Raises:
            ImporterError: Se houver erro na extração.
        """
        pass
    
    def detect_encoding(self, file_path: str, sample_size: int = 65536) -> str:
        """
        Detecta o encoding de um arquivo de texto.
        
        Args:
            file_path: Caminho do arquivo.
            sample_size: Quantidade de bytes para analisar (default: 64KB).
            
        Returns:
            Nome do encoding detectado (ex: 'utf-8', 'latin-1').
        """
        path = Path(file_path)
        
        if not path.is_file():
            raise ImporterError(
                what="Arquivo não encontrado.",
                why=f"O arquivo '{path.name}' não existe ou foi movido.",
                how="Verifique se o caminho está correto e se o arquivo existe."
            )
        
        try:
            with open(path, 'rb') as f:
                raw_data = f.read(sample_size)
        except PermissionError:
            raise ImporterError(
                what="Sem permissão para ler o arquivo.",
                why="O sistema operacional bloqueou o acesso ao arquivo.",
                how="Verifique as permissões do arquivo ou feche outros programas que estejam usando-o."
            )
        except OSError as e:
            raise ImporterError(
                what="Erro ao ler o arquivo.",
                why=str(e),
                how="Tente abrir o arquivo em outro programa para verificar se está corrompido."
            )
        
        if not raw_data:
            return 'utf-8'  # Arquivo vazio, assume UTF-8
        
        result = chardet.detect(raw_data)
        encoding = result.get('encoding', 'utf-8')
        confidence = result.get('confidence', 0)
        
        self._logger.debug(
            f"Encoding detectado: {encoding} (confiança: {confidence:.2%})"
        )
        
        # Mapeia encodings comuns para nomes padronizados
        encoding_map = {
            'ascii': 'utf-8',  # ASCII é subconjunto de UTF-8
            'ISO-8859-1': 'latin-1',
            'iso-8859-1': 'latin-1',
            'windows-1252': 'cp1252',
            'Windows-1252': 'cp1252',
        }
        
        return encoding_map.get(encoding, encoding) if encoding else 'utf-8'
    
    def _validate_file_exists(self, file_path: str) -> Path:
        """
        Valida que o arquivo existe e retorna o Path.
        
        Args:
            file_path: Caminho do arquivo.
            
        Returns:
            Path do arquivo validado.
            
        Raises:
            ImporterError: Se o arquivo não existir.
        """
        path = Path(file_path)
        
        if not path.exists():
            raise ImporterError(
                what="Arquivo não encontrado.",
                why=f"O arquivo '{path.name}' não existe no caminho especificado.",
                how=f"Verifique se o caminho está correto: {file_path}"
            )
        
        if not path.is_file():
            raise ImporterError(
                what="O caminho não é um arquivo.",
                why=f"'{path.name}' é um diretório ou outro tipo de item.",
                how="Selecione um arquivo válido para importar."
            )
        
        return path
    
    def _get_file_extension(self, file_path: str) -> str:
        """
        Obtém a extensão do arquivo em minúsculas.
        
        Args:
            file_path: Caminho do arquivo.
            
        Returns:
            Extensão do arquivo (ex: '.txt', '.pdf').
        """
        return Path(file_path).suffix.lower()
    
    def _get_file_size(self, file_path: str) -> int:
        """
        Obtém o tamanho do arquivo em bytes.
        
        Args:
            file_path: Caminho do arquivo.
            
        Returns:
            Tamanho em bytes.
        """
        return os.path.getsize(file_path)
    
    def _format_file_size(self, size_bytes: int) -> str:
        """
        Formata tamanho de arquivo para exibição amigável.
        
        Args:
            size_bytes: Tamanho em bytes.
            
        Returns:
            String formatada (ex: '1.5 MB').
        """
        for unit in ['bytes', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
