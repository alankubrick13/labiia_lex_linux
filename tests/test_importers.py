"""
Testes para os importadores de documentos.
==========================================
Testa funcionalidades básicas de cada importador e limpador.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.importers.base_importer import BaseImporter, ImportResult, ImporterError
from src.importers.txt_importer import TXTImporter
from src.importers.corpus_cleaner import CorpusCleaner
from src.importers.bigram_compounds import (
    apply_selected_bigrams_to_text,
    extract_bigram_candidates,
    selected_bigrams_to_expressions,
)
from src.importers.general_cleaner import GeneralCleaner
from src.importers.iramuteq_adapter import IramuteqAutoAdapter
from src.importers.text_cleaning import (
    extrair_variaveis_do_nome_arquivo,
    limpar_texto,
)
from src.core.lexicon import build_portuguese_stopwords_from_lexicon


class TestBaseImporter(unittest.TestCase):
    """Testes para a classe BaseImporter."""
    
    def test_import_result_dataclass(self) -> None:
        """Verifica que ImportResult armazena dados corretamente."""
        result = ImportResult(
            text="Texto de teste",
            source_file="/caminho/arquivo.txt",
            encoding="utf-8",
            warnings=["Aviso 1"],
            metadata={"key": "value"}
        )
        
        self.assertEqual(result.text, "Texto de teste")
        self.assertEqual(result.source_file, "/caminho/arquivo.txt")
        self.assertEqual(result.encoding, "utf-8")
        self.assertEqual(len(result.warnings), 1)
        self.assertEqual(result.metadata["key"], "value")
    
    def test_importer_error_message(self) -> None:
        """Verifica que ImporterError formata mensagem corretamente."""
        error = ImporterError(
            what="Arquivo não encontrado",
            why="O caminho está incorreto",
            how="Verifique o caminho"
        )
        
        msg = str(error)
        self.assertIn("O que aconteceu:", msg)
        self.assertIn("Por que aconteceu:", msg)
        self.assertIn("Como resolver:", msg)


class TestTXTImporter(unittest.TestCase):
    """Testes para TXTImporter."""
    
    def setUp(self) -> None:
        self.importer = TXTImporter()
    
    def test_can_handle_txt(self) -> None:
        """Verifica detecção de arquivos TXT."""
        self.assertTrue(self.importer.can_handle("arquivo.txt"))
        self.assertTrue(self.importer.can_handle("arquivo.TXT"))
        self.assertTrue(self.importer.can_handle("arquivo.corpus"))
        self.assertTrue(self.importer.can_handle("arquivo.md"))
        self.assertTrue(self.importer.can_handle("arquivo.json"))
        self.assertTrue(self.importer.can_handle("arquivo.net"))
        self.assertFalse(self.importer.can_handle("arquivo.pdf"))
    
    def test_extract_utf8(self) -> None:
        """Testa extração de arquivo UTF-8."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', delete=False, encoding='utf-8'
        ) as f:
            f.write("Texto de teste com acentuação: é, á, ã, ç")
            temp_path = f.name
        
        try:
            result = self.importer.extract(temp_path)
            self.assertIn("acentuação", result.text)
            self.assertEqual(result.encoding, "utf-8")
        finally:
            Path(temp_path).unlink()
    
    def test_extract_latin1(self) -> None:
        """Testa extração de arquivo Latin-1."""
        with tempfile.NamedTemporaryFile(
            mode='wb', suffix='.txt', delete=False
        ) as f:
            f.write("Texto com acentuação".encode('latin-1'))
            temp_path = f.name
        
        try:
            result = self.importer.extract(temp_path)
            self.assertIn("acentua", result.text)
        finally:
            Path(temp_path).unlink()
    
    def test_file_not_found(self) -> None:
        """Testa erro para arquivo inexistente."""
        with self.assertRaises(ImporterError) as ctx:
            self.importer.extract("/caminho/inexistente.txt")
        
        self.assertIn("não encontrado", str(ctx.exception))

    def test_extract_valid_json_values(self) -> None:
        """Extrai apenas valores textuais de JSON válido."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            f.write('{"titulo": "Relatorio", "itens": ["alpha", "beta"], "meta": {"descricao": "Texto interno"}}')
            temp_path = f.name

        try:
            result = self.importer.extract(temp_path)
            self.assertIn("Relatorio", result.text)
            self.assertIn("alpha", result.text)
            self.assertIn("Texto interno", result.text)
            self.assertNotIn('"titulo"', result.text)
            self.assertEqual(result.metadata.get("source_extension"), ".json")
            self.assertGreater(result.metadata.get("json_values_extracted", 0), 0)
        finally:
            Path(temp_path).unlink()

    def test_extract_invalid_json_fallback_to_raw_text(self) -> None:
        """Se JSON estiver inválido, mantém conteúdo bruto com aviso."""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            f.write('{"quebrado": true,,}')
            temp_path = f.name

        try:
            result = self.importer.extract(temp_path)
            self.assertIn('{"quebrado": true,,}', result.text)
            self.assertTrue(any("JSON invalido" in warning for warning in result.warnings))
        finally:
            Path(temp_path).unlink()


class TestCorpusCleaner(unittest.TestCase):
    """Testes para CorpusCleaner."""
    
    def setUp(self) -> None:
        self.cleaner = CorpusCleaner()
    
    def test_remove_forbidden_chars(self) -> None:
        """Testa remoção de caracteres proibidos."""
        texto = 'Texto com "aspas" e & comercial'
        limpo = self.cleaner.limpar(texto)
        
        self.assertNotIn('"', limpo)
        self.assertIn(' e ', limpo)  # & substituído por ' e '
    
    def test_preserve_command_lines(self) -> None:
        """Testa preservação de linhas de comando."""
        texto = "**** *var1_valor *var2_valor\nTexto do documento."
        limpo = self.cleaner.limpar(texto)
        
        self.assertIn("****", limpo)
        self.assertIn("*var1_valor", limpo)
    
    def test_remove_urls(self) -> None:
        """Testa remoção de URLs."""
        texto = "Visite https://example.com para mais info."
        limpo = self.cleaner.limpar(texto)
        
        self.assertNotIn("https://", limpo)
        self.assertNotIn("example.com", limpo)

    def test_clean_internet_data_option_can_be_disabled(self) -> None:
        """Quando desabilitado, mantém URLs/e-mails no texto."""
        cleaner = CorpusCleaner(limpar_dados_internet=False)
        texto = "Contato: teste@example.com e site https://example.com"
        limpo = cleaner.limpar(texto)

        # O cleaner ainda normaliza caracteres gerais; validamos que os artefatos
        # web não foram removidos por regra dedicada.
        self.assertIn("testeexample.com", limpo)
        self.assertIn("https:", limpo)
        self.assertIn("example.com", limpo)

    def test_clean_internet_data_option_removes_www_and_email(self) -> None:
        """Remove artefatos web quando a opção está ativa."""
        cleaner = CorpusCleaner(limpar_dados_internet=True)
        texto = "Acesse www.exemplo.com ou escreva para joao@exemplo.com"
        limpo = cleaner.limpar(texto)

        self.assertNotIn("www.exemplo.com", limpo)
        self.assertNotIn("joao@exemplo.com", limpo)
    
    def test_compound_expressions(self) -> None:
        """Testa substituição de expressões compostas."""
        texto = "A inteligência artificial está transformando."
        limpo = self.cleaner.limpar(texto)
        
        self.assertIn("inteligencia_artificial", limpo)

    def test_custom_compound_expression(self) -> None:
        """Aplica expressão customizada selecionada pelo usuário."""
        cleaner = CorpusCleaner(
            expressoes_customizadas=[("dilma rousseff", "dilma_rousseff")]
        )
        texto = "**** *doc_1\nDilma Rousseff apareceu no corpus."
        limpo = cleaner.limpar(texto)

        self.assertIn("dilma_rousseff", limpo.lower())

    def test_remove_accents_option(self) -> None:
        """Remove acentos do texto quando opcao estiver ativa."""
        cleaner = CorpusCleaner(remover_acentos=True)
        texto = "**** *cidade_são_paulo\nAção pública e educação."
        limpo = cleaner.limpar(texto)

        self.assertIn("*cidade_sao_paulo", limpo)
        self.assertIn("Acao publica e educacao.", limpo)

    def test_custom_expression_still_applies_with_remove_accents(self) -> None:
        """
        Expressões customizadas sem acento devem funcionar quando o texto original tem acentos
        e a opção "remover acentos" está ativa.
        """
        cleaner = CorpusCleaner(
            remover_acentos=True,
            expressoes_customizadas=[("educacao superior", "educacao_superior")],
        )
        texto = "**** *doc_1\nEducação superior melhora a educação superior."
        limpo = cleaner.limpar(texto)

        self.assertIn("educacao_superior", limpo.lower())

    def test_custom_expression_matches_variable_whitespace(self) -> None:
        """Expressão customizada deve casar mesmo com múltiplos espaços/quebras de linha."""
        cleaner = CorpusCleaner(
            expressoes_customizadas=[("sistema wayfinding", "sistema_wayfinding")]
        )
        texto = "**** *doc_1\nsistema   wayfinding\nsistema wayfinding"
        limpo = cleaner.limpar(texto)

        self.assertGreaterEqual(limpo.lower().count("sistema_wayfinding"), 2)

    def test_remove_numbers_keeps_command_tokens_valid(self) -> None:
        """Nao deve remover digitos das variaveis de linha de comando."""
        cleaner = CorpusCleaner(remover_numeros=True)
        texto = (
            "**** *doc_1 *id_123 *grupo_a\n"
            "Texto 2024 com numeros 45."
        )
        limpo = cleaner.limpar(texto)

        self.assertIn("*doc_1", limpo)
        self.assertIn("*id_123", limpo)
        self.assertNotIn("2024", limpo)

    def test_statistics(self) -> None:
        """Testa geração de estatísticas."""
        original = "Texto original com algumas palavras extras."
        limpo = self.cleaner.limpar(original)
        stats = self.cleaner.get_estatisticas(original, limpo)
        
        self.assertIn('caracteres_original', stats)
        self.assertIn('caracteres_limpo', stats)
        self.assertIn('palavras_original', stats)

    def test_remove_empty_ucis_after_cleaning(self) -> None:
        """Remove UCI que ficou sem texto após limpeza."""
        cleaner = CorpusCleaner(remover_numeros=True)
        texto = (
            "**** *doc_1 *grupo_a\n"
            "12345 67890\n\n"
            "**** *doc_2 *grupo_b\n"
            "Texto válido"
        )
        limpo = cleaner.limpar(texto)

        self.assertEqual(limpo.count("**** "), 1)
        self.assertIn("*doc_2", limpo)
        self.assertNotIn("*doc_1", limpo)


class TestIramuteqAutoAdapter(unittest.TestCase):
    """Testes para adaptacao automatica para formato IRaMuTeQ."""

    def setUp(self) -> None:
        self.adapter = IramuteqAutoAdapter()

    def test_preserves_existing_iramuteq_format(self) -> None:
        text = "**** *doc_1 *fonte_teste\nTexto já formatado."
        adapted = self.adapter.to_iramuteq(text, source_file="arquivo.txt")
        self.assertEqual(adapted, text)

    def test_converts_plain_text_to_iramuteq(self) -> None:
        text = "Primeiro documento.\n\nSegundo documento."
        adapted = self.adapter.to_iramuteq(text, source_file="entrevistas.txt")

        self.assertEqual(adapted.count("**** "), 2)
        self.assertIn("*fonte_entrevistas", adapted)
        self.assertIn("*tipo_txt", adapted)
        self.assertIn("Primeiro documento.", adapted)
        self.assertIn("Segundo documento.", adapted)


class TestBigramCompounds(unittest.TestCase):
    """Testes para sugestões de união de bigramas na importação."""

    def test_extract_bigram_candidates_basic(self) -> None:
        text = (
            "**** *doc_1\n"
            "inteligencia artificial avanca\n"
            "inteligencia artificial cresce\n"
            "dilma rousseff participa\n"
        )

        candidates = extract_bigram_candidates(text, top_n=20, min_freq=2)
        expressions = {item["expression"] for item in candidates}

        self.assertIn("inteligencia artificial", expressions)
        self.assertNotIn("doc 1", expressions)

    def test_selected_bigrams_to_expressions(self) -> None:
        selected = [
            {"expression": "dilma rousseff", "replacement": "dilma_rousseff", "frequency": 3},
            {"expression": "dilma rousseff", "replacement": "dilma_rousseff", "frequency": 3},
            {"expression": "invalido", "replacement": "invalido", "frequency": 1},
        ]

        normalized = selected_bigrams_to_expressions(selected)
        self.assertEqual(normalized, [("dilma rousseff", "dilma_rousseff")])

    def test_apply_selected_bigrams_to_text_handles_hyphen(self) -> None:
        text = "**** *doc_1\nsistema-wayfinding e design."
        merged, count = apply_selected_bigrams_to_text(
            text,
            [("sistema wayfinding", "sistema_wayfinding")],
        )

        self.assertIn("sistema_wayfinding", merged)
        self.assertGreaterEqual(count, 1)

    def test_apply_selected_bigrams_to_text_handles_stopword_bridge(self) -> None:
        text = "**** *doc_1\nsistemas de wayfinding ajudam."
        merged, count = apply_selected_bigrams_to_text(
            text,
            [("sistemas wayfinding", "sistemas_wayfinding")],
            allow_stopword_bridge=True,
        )

        self.assertIn("sistemas_wayfinding", merged)
        self.assertGreaterEqual(count, 1)

    def test_apply_selected_bigrams_to_text_preserves_command_lines(self) -> None:
        text = "**** *doc_1 *fonte_teste\nsistema wayfinding."
        merged, _ = apply_selected_bigrams_to_text(
            text,
            [("sistema wayfinding", "sistema_wayfinding")],
        )

        self.assertIn("**** *doc_1 *fonte_teste", merged)


class TestGeneralCleaner(unittest.TestCase):
    """Testes para GeneralCleaner."""
    
    def setUp(self) -> None:
        self.cleaner = GeneralCleaner(idioma='pt')
    
    def test_tokenization(self) -> None:
        """Testa tokenização básica."""
        texto = "Palavra1, palavra2 e palavra3!"
        tokens = self.cleaner.tokenizar(texto)
        
        self.assertEqual(len(tokens), 4)  # palavra1, palavra2, e, palavra3
    
    def test_remove_stopwords(self) -> None:
        """Testa remoção de stopwords."""
        texto = "O gato está em cima da mesa."
        limpo = self.cleaner.limpar(texto)
        
        # 'o', 'está', 'em', 'da' são stopwords
        self.assertNotIn(' o ', ' ' + limpo + ' ')
        self.assertIn('gato', limpo)
        self.assertIn('mesa', limpo)
    
    def test_lowercase(self) -> None:
        """Testa conversão para minúsculas."""
        cleaner = GeneralCleaner(minusculas=True)
        texto = "TEXTO EM MAIÚSCULAS"
        limpo = cleaner.limpar(texto)
        
        self.assertEqual(limpo, limpo.lower())
    
    def test_statistics(self) -> None:
        """Testa geração de estatísticas."""
        original = "O gato está em cima da mesa."
        limpo = self.cleaner.limpar(original)
        stats = self.cleaner.get_estatisticas(original, limpo)
        
        self.assertIn('tokens_original', stats)
        self.assertIn('tokens_limpo', stats)
        self.assertIn('reducao_percentual', stats)

    def test_iramuteq_pt_stopwords_are_loaded(self) -> None:
        """Stopwords PT ampliadas incluem itens comuns do IRaMuTeQ."""
        stopwords = build_portuguese_stopwords_from_lexicon()
        for token in ("que", "uma", "por", "pela", "com", "de", "nao", "não", "et", "al", "off", "the"):
            self.assertIn(token, stopwords)


class TestPDFImporter(unittest.TestCase):
    """Testes para PDFImporter (sem arquivo real)."""
    
    def test_can_handle(self) -> None:
        """Verifica detecção de arquivos PDF."""
        from src.importers.pdf_importer import PDFImporter
        importer = PDFImporter()
        
        self.assertTrue(importer.can_handle("arquivo.pdf"))
        self.assertTrue(importer.can_handle("arquivo.PDF"))
        self.assertFalse(importer.can_handle("arquivo.txt"))

    def test_clean_page_text_removes_page_artifacts(self) -> None:
        """Remove hifenizacao e numero de pagina do texto extraido."""
        from src.importers.pdf_importer import PDFImporter
        importer = PDFImporter()

        raw_text = "Relato de pesqui-\nsa aplicada\n\nPágina 12\n"
        cleaned = importer._clean_page_text(raw_text)

        self.assertIn("pesquisa", cleaned)
        self.assertNotIn("pesqui-\nsa", cleaned)
        self.assertNotIn("Página 12", cleaned)

    def test_remove_repeated_page_markers(self) -> None:
        """Remove cabecalho/rodape repetido em varias paginas."""
        from src.importers.pdf_importer import PDFImporter
        importer = PDFImporter()

        pages = [
            "REVISTA XYZ\nConteudo da pagina um\n1",
            "REVISTA XYZ\nConteudo da pagina dois\n2",
            "REVISTA XYZ\nConteudo da pagina tres\n3",
        ]

        cleaned_pages = importer._remove_repeated_page_markers(pages)

        self.assertNotIn("REVISTA XYZ", "\n".join(cleaned_pages))
        self.assertIn("Conteudo da pagina dois", "\n".join(cleaned_pages))

    def test_build_iramuteq_text_uses_filename_variables(self) -> None:
        """Gera linha **** com variaveis simples extraidas do nome do arquivo."""
        from src.importers.pdf_importer import PDFImporter

        importer = PDFImporter()
        text = "Conteudo completo do documento para analise."
        block = importer._build_iramuteq_text("reuniao_5_ano_2023.pdf", text)

        self.assertIn("****", block)
        self.assertIn("*doc_reuniao_5_ano_2023", block)
        self.assertIn("*reuniao_5", block)
        self.assertIn("*ano_2023", block)
        self.assertTrue(block.endswith(text))


class TestTextCleaning(unittest.TestCase):
    """Testes do pipeline de limpeza textual compartilhado."""

    def test_limpar_texto_aplica_pipeline_ordenado(self) -> None:
        bruto = (
            "Cabecalho curto\n"
            "governa-\n"
            "mento em transfor-\n"
            "macao digital\n\n"
            "Rodape 12\n"
            "Este paragrafo tem tamanho suficiente para permanecer apos a limpeza.\n"
            "Outro trecho robusto para manter o contexto do corpus.\n"
        )
        limpo = limpar_texto(bruto, min_line_chars=20)

        self.assertIn("governamento", limpo)
        self.assertIn("transformacao", limpo)
        self.assertIn("Este paragrafo tem tamanho suficiente", limpo)
        self.assertNotIn("Cabecalho curto", limpo)
        self.assertNotIn("Rodape 12", limpo)
        self.assertNotIn("\n\n\n", limpo)

    def test_limpar_texto_preserva_paragrafos_vazios_intencionais(self) -> None:
        bruto = (
            "Primeira linha longa o bastante para manter no texto final consolidado.\n"
            "\n"
            "Segunda linha longa o bastante para compor o proximo paragrafo.\n"
        )
        limpo = limpar_texto(bruto, min_line_chars=20)
        self.assertIn("\n\n", limpo)

    def test_extrair_variaveis_do_nome_arquivo(self) -> None:
        vars_map = extrair_variaveis_do_nome_arquivo("relatorio_reuniao_5_ano_2024.pdf")
        self.assertEqual(vars_map.get("reuniao"), "5")
        self.assertEqual(vars_map.get("ano"), "2024")


class TestDOCXImporter(unittest.TestCase):
    """Testes para DOCXImporter (sem arquivo real)."""
    
    def test_can_handle(self) -> None:
        """Verifica detecção de arquivos DOCX."""
        from src.importers.docx_importer import DOCXImporter
        importer = DOCXImporter()
        
        self.assertTrue(importer.can_handle("arquivo.docx"))
        self.assertTrue(importer.can_handle("arquivo.DOCX"))
        self.assertFalse(importer.can_handle("arquivo.doc"))


class TestODTImporter(unittest.TestCase):
    """Testes para ODTImporter."""

    def test_can_handle(self) -> None:
        """Verifica detecção de arquivos ODT."""
        from src.importers.odt_importer import ODTImporter
        importer = ODTImporter()

        self.assertTrue(importer.can_handle("arquivo.odt"))
        self.assertTrue(importer.can_handle("arquivo.ODT"))
        self.assertFalse(importer.can_handle("arquivo.docx"))

    def test_extract_minimal_odt(self) -> None:
        """Extrai texto de um ODT mínimo com content.xml."""
        from src.importers.odt_importer import ODTImporter

        content_xml = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content
  xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
  xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">
  <office:body>
    <office:text>
      <text:p>Primeira linha do ODT.</text:p>
      <text:p>Segunda linha.</text:p>
    </office:text>
  </office:body>
</office:document-content>
"""

        with tempfile.NamedTemporaryFile(suffix=".odt", delete=False) as f:
            temp_path = f.name

        try:
            with zipfile.ZipFile(temp_path, "w") as zf:
                zf.writestr("content.xml", content_xml)

            importer = ODTImporter()
            result = importer.extract(temp_path)

            self.assertIn("Primeira linha do ODT.", result.text)
            self.assertIn("Segunda linha.", result.text)
            self.assertEqual(result.metadata.get("source_extension"), ".odt")
        finally:
            Path(temp_path).unlink(missing_ok=True)


class TestImporterRegistry(unittest.TestCase):
    """Testes para seleção automática de importadores por extensão."""

    def test_get_importer_for_new_extensions(self) -> None:
        """Roteia .odt para ODTImporter e .json/.md/.net para TXTImporter."""
        from src.importers import get_importer_for_file
        from src.importers.odt_importer import ODTImporter
        from src.importers.txt_importer import TXTImporter

        self.assertIsInstance(get_importer_for_file("arquivo.odt"), ODTImporter)
        self.assertIsInstance(get_importer_for_file("arquivo.json"), TXTImporter)
        self.assertIsInstance(get_importer_for_file("arquivo.md"), TXTImporter)
        self.assertIsInstance(get_importer_for_file("arquivo.net"), TXTImporter)


class TestXLSXImporter(unittest.TestCase):
    """Testes para XLSXImporter."""
    
    def test_can_handle(self) -> None:
        """Verifica detecção de arquivos Excel/CSV."""
        from src.importers.xlsx_importer import XLSXImporter
        importer = XLSXImporter()
        
        self.assertTrue(importer.can_handle("arquivo.xlsx"))
        self.assertTrue(importer.can_handle("arquivo.csv"))
        self.assertTrue(importer.can_handle("arquivo.tsv"))
        self.assertFalse(importer.can_handle("arquivo.txt"))
    
    def test_extract_csv(self) -> None:
        """Testa extração de arquivo CSV."""
        from src.importers.xlsx_importer import XLSXImporter
        importer = XLSXImporter()
        
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False, encoding='utf-8'
        ) as f:
            f.write("col1,col2,col3\n")
            f.write("valor1,valor2,valor3\n")
            f.write("texto,mais texto,final\n")
            temp_path = f.name
        
        try:
            result = importer.extract(temp_path)
            self.assertIn("valor1", result.text)
            self.assertIn("texto", result.text)
            self.assertIn("iramuteq_text", result.metadata)
        finally:
            Path(temp_path).unlink()

    def test_extract_csv_builds_iramuteq_docs_per_row(self) -> None:
        """Cada linha de dados da planilha vira um documento IRaMuTeQ."""
        from src.importers.xlsx_importer import XLSXImporter
        importer = XLSXImporter()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False, encoding='utf-8'
        ) as f:
            f.write("Texto,Grupo,Ano\n")
            f.write("Primeiro depoimento,A,2024\n")
            f.write("Segundo depoimento,B,2025\n")
            temp_path = f.name

        try:
            result = importer.extract(temp_path)
            iramuteq_text = result.metadata.get("iramuteq_text", "")

            self.assertEqual(iramuteq_text.count("**** "), 2)
            self.assertIn("*grupo_a", iramuteq_text)
            self.assertIn("*grupo_b", iramuteq_text)
            self.assertIn("Primeiro depoimento", iramuteq_text)
            self.assertIn("Segundo depoimento", iramuteq_text)
        finally:
            Path(temp_path).unlink()

    def test_extract_csv_without_header_keeps_first_row_as_document(self) -> None:
        """CSV sem cabecalho nao deve perder a primeira linha de dados."""
        from src.importers.xlsx_importer import XLSXImporter
        importer = XLSXImporter()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False, encoding='utf-8'
        ) as f:
            f.write("Primeiro depoimento livre,grupo_a\n")
            f.write("Segundo depoimento livre,grupo_b\n")
            temp_path = f.name

        try:
            result = importer.extract(temp_path)
            iramuteq_text = result.metadata.get("iramuteq_text", "")

            self.assertEqual(iramuteq_text.count("**** "), 2)
            self.assertIn("Primeiro depoimento livre", iramuteq_text)
            self.assertIn("Segundo depoimento livre", iramuteq_text)
        finally:
            Path(temp_path).unlink()

    def test_extract_csv_ignores_id_like_column_as_variable(self) -> None:
        """Coluna identificadora de alta cardinalidade nao vira variavel lexical."""
        from src.importers.xlsx_importer import XLSXImporter
        importer = XLSXImporter()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.csv', delete=False, encoding='utf-8'
        ) as f:
            f.write("id,texto,grupo\n")
            f.write("1001,Depoimento um,A\n")
            f.write("1002,Depoimento dois,B\n")
            f.write("1003,Depoimento tres,A\n")
            temp_path = f.name

        try:
            result = importer.extract(temp_path)
            iramuteq_text = result.metadata.get("iramuteq_text", "")

            self.assertIn("*grupo_a", iramuteq_text)
            self.assertIn("*grupo_b", iramuteq_text)
            self.assertNotIn("*id_1001", iramuteq_text)
            self.assertNotIn("*id_1002", iramuteq_text)
        finally:
            Path(temp_path).unlink()


if __name__ == "__main__":
    unittest.main()
