"""
TXTImporter - Importador para arquivos de texto simples.
=========================================================
Suporta arquivos de texto com deteccao automatica de encoding.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List

from .base_importer import BaseImporter, ImportResult, ImporterError
from ..utils.logger import get_logger


class TXTImporter(BaseImporter):
    """
    Importador para arquivos baseados em texto.
    
    Suporta:
    - texto simples: .txt, .text, .corpus, .md, .net
    - JSON: .json (extrai valores textuais quando valido)
    """
    
    SUPPORTED_EXTENSIONS: List[str] = ['.txt', '.text', '.corpus', '.md', '.json', '.net']
    
    def __init__(self) -> None:
        super().__init__()
        self._logger = get_logger(__name__)
    
    def can_handle(self, file_path: str) -> bool:
        """
        Verifica se o arquivo é um texto simples.
        
        Args:
            file_path: Caminho do arquivo.
            
        Returns:
            True se for um arquivo de texto suportado.
        """
        ext = self._get_file_extension(file_path)
        return ext in self.SUPPORTED_EXTENSIONS
    
    def extract(self, file_path: str) -> ImportResult:
        """
        Extrai texto de um arquivo textual.
        
        Args:
            file_path: Caminho do arquivo TXT.
            
        Returns:
            ImportResult com o texto e metadados.
            
        Raises:
            ImporterError: Se houver erro na leitura.
        """
        path = self._validate_file_exists(file_path)
        warnings: List[str] = []
        ext = path.suffix.lower()
        
        # Detectar encoding
        encoding = self.detect_encoding(file_path)
        self._logger.info(f"Lendo arquivo textual com encoding: {encoding}")
        
        # Tentar ler com o encoding detectado
        try:
            raw_text = self._read_with_encoding(path, encoding)
        except UnicodeDecodeError:
            # Se falhar, tentar encodings alternativos
            self._logger.warning(
                f"Falha ao ler com {encoding}, tentando encodings alternativos"
            )
            raw_text, encoding = self._try_alternative_encodings(path)
            warnings.append(
                f"Encoding original não funcionou. Usando: {encoding}"
            )

        text = raw_text
        json_values_extracted = 0
        if ext == '.json':
            text, json_values_extracted = self._extract_json_text(raw_text, warnings)
        elif ext == '.net':
            warnings.append(
                "Arquivo .net tratado como texto simples. "
                "Se for um arquivo de rede (ex.: Pajek), o conteudo sera preservado como texto bruto."
            )
        
        # Verificar se o arquivo está vazio
        if not text.strip():
            warnings.append("O arquivo está vazio ou contém apenas espaços em branco.")
        
        # Coletar metadados
        lines = text.split('\n')
        words = text.split()
        
        metadata = {
            'line_count': len(lines),
            'word_count': len(words),
            'char_count': len(text),
            'source_extension': ext or '',
            'file_size': self._get_file_size(file_path),
            'file_size_formatted': self._format_file_size(self._get_file_size(file_path)),
        }
        if ext == '.json':
            metadata['json_values_extracted'] = json_values_extracted
        
        self._logger.info(
            f"Arquivo textual importado: {metadata['word_count']} palavras, "
            f"{metadata['line_count']} linhas"
        )
        
        return ImportResult(
            text=text,
            source_file=str(path),
            encoding=encoding,
            warnings=warnings,
            metadata=metadata,
        )
    
    def _read_with_encoding(self, path: Path, encoding: str) -> str:
        """
        Lê arquivo com encoding especificado.
        
        Args:
            path: Path do arquivo.
            encoding: Encoding a usar.
            
        Returns:
            Conteúdo do arquivo.
            
        Raises:
            UnicodeDecodeError: Se o encoding não funcionar.
            ImporterError: Para outros erros de leitura.
        """
        try:
            with open(path, 'r', encoding=encoding, errors='strict') as f:
                return f.read()
        except PermissionError:
            raise ImporterError(
                what="Sem permissão para ler o arquivo.",
                why="O sistema operacional bloqueou o acesso.",
                how="Verifique as permissões do arquivo ou feche programas que estejam usando-o."
            )
        except OSError as e:
            raise ImporterError(
                what="Erro ao ler o arquivo de texto.",
                why=str(e),
                how="Verifique se o arquivo está acessível e não está corrompido."
            )
    
    def _try_alternative_encodings(self, path: Path) -> tuple:
        """
        Tenta ler o arquivo com encodings alternativos.
        
        Args:
            path: Path do arquivo.
            
        Returns:
            Tupla (texto, encoding_usado).
            
        Raises:
            ImporterError: Se nenhum encoding funcionar.
        """
        alternative_encodings = [
            'utf-8',
            'latin-1',
            'cp1252',
            'iso-8859-1',
            'utf-16',
            'utf-8-sig',  # UTF-8 com BOM
        ]
        
        for encoding in alternative_encodings:
            try:
                with open(path, 'r', encoding=encoding, errors='strict') as f:
                    text = f.read()
                self._logger.info(f"Sucesso ao ler com encoding: {encoding}")
                return text, encoding
            except UnicodeDecodeError:
                continue
        
        # Se nenhum funcionar, usar latin-1 (aceita qualquer byte)
        with open(path, 'r', encoding='latin-1', errors='replace') as f:
            text = f.read()
        self._logger.warning("Usando latin-1 com substituição de caracteres inválidos")
        return text, 'latin-1'

    def _extract_json_text(self, raw_text: str, warnings: List[str]) -> tuple[str, int]:
        """
        Extrai texto de valores JSON para reduzir ruido estrutural.

        Se o arquivo nao for JSON valido, retorna o texto bruto.
        """
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            warnings.append(
                "JSON invalido; arquivo importado como texto bruto "
                f"(linha {exc.lineno}, coluna {exc.colno})."
            )
            return raw_text, 0

        values: List[str] = []
        self._collect_json_strings(payload, values)
        normalized = [
            re.sub(r"\s+", " ", value).strip()
            for value in values
            if str(value).strip()
        ]
        normalized = [value for value in normalized if value]

        if not normalized:
            warnings.append(
                "JSON sem valores textuais extraiveis; arquivo importado como texto bruto."
            )
            return raw_text, 0

        extracted = "\n".join(normalized)
        return extracted, len(normalized)

    @classmethod
    def _collect_json_strings(cls, payload, output: List[str]) -> None:
        """Percorre JSON recursivamente coletando valores textuais."""
        if isinstance(payload, dict):
            for value in payload.values():
                cls._collect_json_strings(value, output)
            return
        if isinstance(payload, list):
            for item in payload:
                cls._collect_json_strings(item, output)
            return
        if isinstance(payload, str):
            output.append(payload)
