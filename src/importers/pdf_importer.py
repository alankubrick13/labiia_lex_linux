"""
PDFImporter - Importador para arquivos PDF.
=============================================
Usa pdfplumber para extrair texto de documentos PDF.
Detecta PDFs escaneados (apenas imagens) e orienta o usuário.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from typing import List, Optional

from .base_importer import BaseImporter, ImportResult, ImporterError
from .text_cleaning import extrair_variaveis_do_nome_arquivo, limpar_texto
from ..utils.logger import get_logger


class PDFImporter(BaseImporter):
    """
    Importador para arquivos PDF.
    
    Características:
    - Extrai texto de PDFs com texto selecionável
    - Detecta PDFs escaneados (sem texto extraível)
    - Fornece estatísticas por página
    """
    
    SUPPORTED_EXTENSIONS: List[str] = ['.pdf']
    
    # Limiar mínimo de caracteres por página para considerar como tendo texto
    MIN_CHARS_PER_PAGE = 50
    
    def __init__(self) -> None:
        super().__init__()
        self._logger = get_logger(__name__)
        self._pdfplumber = None
    
    def _ensure_pdfplumber(self) -> None:
        """Importa pdfplumber sob demanda."""
        if self._pdfplumber is None:
            try:
                import pdfplumber
                self._pdfplumber = pdfplumber
            except ImportError:
                raise ImporterError(
                    what="Biblioteca pdfplumber não encontrada.",
                    why="O pdfplumber é necessário para ler arquivos PDF.",
                    how="Instale com: pip install pdfplumber"
                )
    
    def can_handle(self, file_path: str) -> bool:
        """
        Verifica se o arquivo é um PDF.
        
        Args:
            file_path: Caminho do arquivo.
            
        Returns:
            True se for um PDF.
        """
        ext = self._get_file_extension(file_path)
        return ext in self.SUPPORTED_EXTENSIONS
    
    def extract(self, file_path: str) -> ImportResult:
        """
        Extrai texto de um arquivo PDF.
        
        Args:
            file_path: Caminho do arquivo PDF.
            
        Returns:
            ImportResult com o texto e metadados.
            
        Raises:
            ImporterError: Se houver erro na extração.
        """
        self._ensure_pdfplumber()
        path = self._validate_file_exists(file_path)
        warnings: List[str] = []
        self._report_progress(0.02, "Abrindo PDF...")
        
        pages_text: List[str] = []
        pages_without_text: List[int] = []
        total_chars = 0
        
        try:
            with self._pdfplumber.open(path) as pdf:
                total_pages = len(pdf.pages)
                self._report_progress(0.05, f"PDF carregado ({total_pages} páginas)")
                
                self._logger.info(f"Processando PDF com {total_pages} páginas")
                
                for i, page in enumerate(pdf.pages, start=1):
                    page_text = self._clean_page_text(page.extract_text() or "")
                    pages_text.append(page_text)
                    
                    char_count = len(page_text.strip())
                    total_chars += char_count
                    
                    if char_count < self.MIN_CHARS_PER_PAGE:
                        pages_without_text.append(i)
                    
                    self._logger.debug(
                        f"Página {i}/{total_pages}: {char_count} caracteres"
                    )
                    progress = 0.05 + (i / max(1, total_pages)) * 0.80
                    self._report_progress(
                        progress,
                        f"Extraindo página {i}/{total_pages}...",
                    )

                self._report_progress(0.90, "Limpando texto extraído...")
                pages_text = self._remove_repeated_page_markers(pages_text)
                text = limpar_texto("\n\n".join(page for page in pages_text if page.strip()))
                total_chars = len(text)
        
        except Exception as e:
            error_msg = str(e).lower()
            
            if "encrypted" in error_msg or "password" in error_msg:
                raise ImporterError(
                    what="O PDF está protegido por senha.",
                    why="Não é possível extrair texto de documentos criptografados.",
                    how="Abra o PDF no leitor de sua preferência, remova a proteção e tente novamente."
                )
            
            if "corrupt" in error_msg or "invalid" in error_msg:
                raise ImporterError(
                    what="O arquivo PDF parece estar corrompido.",
                    why="O conteúdo do arquivo não é um PDF válido.",
                    how="Tente abrir o arquivo em um leitor de PDF para verificar se está corrompido."
                )
            
            self._logger.error(f"Erro ao processar PDF: {e}")
            raise ImporterError(
                what="Erro ao extrair texto do PDF.",
                why=str(e),
                how="Verifique se o arquivo é um PDF válido e não está corrompido."
            )
        
        # Verifica se é um PDF escaneado
        
        if not text.strip() or total_chars < (total_pages * self.MIN_CHARS_PER_PAGE // 2):
            raise ImporterError(
                what="Este PDF parece ser escaneado (apenas imagens).",
                why="PDFs escaneados contêm imagens das páginas em vez de texto selecionável. "
                    "O software não consegue extrair texto de imagens.",
                how="Opções para resolver:\n"
                    "1. Use um software de OCR (como Adobe Acrobat Pro ou Tesseract) para "
                    "converter as imagens em texto.\n"
                    "2. Se possível, obtenha uma versão digital do documento com texto selecionável.\n"
                    "3. Transcreva o documento manualmente."
            )
        
        # Avisos sobre páginas sem texto
        if pages_without_text:
            if len(pages_without_text) <= 5:
                pages_list = ", ".join(map(str, pages_without_text))
            else:
                pages_list = f"{len(pages_without_text)} páginas"
            warnings.append(
                f"Algumas páginas parecem não ter texto extraível: {pages_list}"
            )
        
        # Metadados
        words = text.split()
        metadata = {
            'page_count': total_pages,
            'word_count': len(words),
            'char_count': len(text),
            'pages_without_text': pages_without_text,
            'file_size': self._get_file_size(file_path),
            'file_size_formatted': self._format_file_size(self._get_file_size(file_path)),
            'iramuteq_text': self._build_iramuteq_text(file_path=file_path, text=text),
        }
        
        self._logger.info(
            f"PDF importado: {metadata['word_count']} palavras, "
            f"{total_pages} páginas"
        )
        self._report_progress(1.0, "PDF importado com sucesso.")
        
        return ImportResult(
            text=text,
            source_file=str(path),
            encoding="utf-8",  # pdfplumber retorna UTF-8
            warnings=warnings,
            metadata=metadata,
        )

    def _clean_page_text(self, text: str) -> str:
        """Limpa artefatos comuns de texto extraído de PDF."""
        if not text:
            return ""
        return limpar_texto(text, min_line_chars=20)

    def _remove_repeated_page_markers(self, pages_text: List[str]) -> List[str]:
        """Remove cabeçalhos/rodapés repetidos em muitas páginas."""
        if len(pages_text) < 2:
            return pages_text

        first_lines = []
        last_lines = []
        for page_text in pages_text:
            lines = [line.strip() for line in page_text.split('\n') if line.strip()]
            if lines:
                first_lines.append(self._normalize_marker_line(lines[0]))
                last_lines.append(self._normalize_marker_line(lines[-1]))

        threshold = max(2, int(len(pages_text) * 0.6))
        first_counter = Counter(line for line in first_lines if line)
        last_counter = Counter(line for line in last_lines if line)
        repeated_markers = {
            line for line, count in first_counter.items()
            if count >= threshold and len(line) >= 4
        } | {
            line for line, count in last_counter.items()
            if count >= threshold and len(line) >= 4
        }

        if not repeated_markers:
            return pages_text

        self._logger.info(
            "Removendo %s marcador(es) repetido(s) de cabecalho/rodape no PDF",
            len(repeated_markers),
        )

        cleaned_pages: List[str] = []
        for page_text in pages_text:
            page_lines = []
            for line in page_text.split('\n'):
                normalized = self._normalize_marker_line(line)
                if normalized in repeated_markers:
                    continue
                page_lines.append(line)
            cleaned_pages.append('\n'.join(page_lines).strip())

        return cleaned_pages

    def _normalize_marker_line(self, line: str) -> str:
        """Normaliza linha para comparar marcadores repetidos."""
        normalized = (line or "").strip().lower()
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized

    def _build_iramuteq_text(self, file_path: str, text: str) -> str:
        """Monta bloco IRaMuTeQ com metadados simples derivados do nome do arquivo."""
        body = str(text or "").strip()
        if not body:
            return ""

        safe_doc = re.sub(r"[^a-zA-Z0-9_]+", "_", Path(file_path).stem).strip("_").lower()
        if not safe_doc:
            safe_doc = "doc_pdf"

        tokens = [f"*doc_{safe_doc}"]
        for name, value in extrair_variaveis_do_nome_arquivo(file_path).items():
            safe_name = re.sub(r"[^a-z0-9_]+", "_", str(name).lower()).strip("_")
            safe_value = re.sub(r"[^a-z0-9_]+", "_", str(value).lower()).strip("_")
            if not safe_name or not safe_value:
                continue
            tokens.append(f"*{safe_name}_{safe_value}")

        return f"**** {' '.join(tokens)}\n{body}"
