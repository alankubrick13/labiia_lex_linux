"""
Testes de integracao end-to-end.

Testa fluxos completos: importar -> processar -> analisar.
"""
import pytest
import tempfile
import os
from pathlib import Path


# Marcar testes que precisam de R
needs_r = pytest.mark.skipif(
    not os.environ.get('R_HOME'),
    reason="R nao disponivel neste ambiente"
)


class TestImportWorkflow:
    """Testa fluxo de importacao de arquivos."""
    
    def test_import_txt_file(self, tmp_path):
        """Importa arquivo TXT simples."""
        from src.importers import get_importer_for_file
        
        # Criar arquivo de teste
        test_file = tmp_path / "test.txt"
        test_file.write_text("Este e um texto de teste.", encoding='utf-8')
        
        # Importar
        importer = get_importer_for_file(str(test_file))
        result = importer.extract(str(test_file))
        
        assert result is not None
        assert "texto de teste" in result.text
    
    def test_import_iramuteq_corpus(self):
        """Importa corpus no formato IRaMuTeQ."""
        from src.importers import TXTImporter
        
        fixture_path = Path(__file__).parent / "fixtures" / "exemplo.txt"
        if not fixture_path.exists():
            pytest.skip("Arquivo de fixture nao encontrado")
        
        importer = TXTImporter()
        result = importer.extract(str(fixture_path))
        
        assert result is not None
        assert "****" in result.text
        assert "politica" in result.text.lower()
    
    def test_clean_iramuteq_corpus(self):
        """Limpa corpus para formato IRaMuTeQ."""
        from src.importers.corpus_cleaner import CorpusCleaner
        
        text = """**** *var_teste
        Essa é uma frase com caracteres "especiais" e urls http://teste.com
        """
        
        cleaner = CorpusCleaner()
        cleaned = cleaner.limpar(text)
        
        # Verifica que linhas de comando sao preservadas
        assert "****" in cleaned
        # URLs devem ser removidas
        assert "http" not in cleaned


class TestCorpusCreation:
    """Testa criacao e manipulacao de corpus."""
    
    def test_create_corpus_and_add_uci(self):
        """Cria corpus e adiciona UCIs manualmente."""
        from src.core.corpus import Corpus
        
        corpus = Corpus()
        
        # Adicionar UCIs
        uci1 = corpus.add_uci("**** *loc_cidade")
        uci2 = corpus.add_uci("**** *loc_campo")
        
        assert len(corpus.ucis) == 2
        assert uci1 is not None
        assert uci2 is not None
    
    def test_corpus_add_words(self):
        """Adiciona palavras ao corpus."""
        from src.core.corpus import Corpus
        
        corpus = Corpus()
        
        # Adicionar palavras
        corpus.add_word("palavra1")
        corpus.add_word("palavra2")
        corpus.add_word("palavra1")  # Duplicada
        
        assert "palavra1" in corpus.formes
        assert "palavra2" in corpus.formes
        assert corpus.formes["palavra1"].freq == 2
    
    def test_corpus_statistics(self):
        """Verifica estatisticas do corpus."""
        from src.core.corpus import Corpus
        
        corpus = Corpus()
        
        # Adicionar UCIs e palavras
        corpus.add_uci("**** *var1")
        corpus.add_word("palavra1")
        corpus.add_word("palavra2")
        corpus.add_word("palavra3")
        
        # Deve ter UCIs
        assert len(corpus.ucis) >= 1
        
        # Deve ter formas
        assert len(corpus.formes) >= 3


class TestAnalysisWorkflow:
    """Testa fluxo de analises."""
    
    def test_statistics_analysis(self):
        """Executa analise de estatisticas."""
        from src.core.corpus import Corpus
        from src.analysis import StatisticsAnalysis
        
        corpus = Corpus()
        corpus.add_uci("**** *var1")
        corpus.add_word("palavra1")
        corpus.add_word("palavra2")
        
        analysis = StatisticsAnalysis(corpus)
        stats = analysis.get_corpus_statistics()
        
        assert stats is not None
    
    @needs_r
    def test_chd_analysis_with_r(self):
        """Executa analise CHD (requer R)."""
        from src.core.corpus import Corpus
        from src.analysis import CHDAnalysis
        
        fixture_path = Path(__file__).parent / "fixtures" / "exemplo.txt"
        if not fixture_path.exists():
            pytest.skip("Arquivo de fixture nao encontrado")
        
        corpus = Corpus()
        corpus.add_uci("**** *var1")
        for word in ["politica", "publica", "educacao", "saude"]:
            corpus.add_word(word)
        
        analysis = CHDAnalysis(corpus)
        result = analysis.run(n_classes=3)
        
        assert result is not None
    
    @needs_r
    def test_similarity_analysis_with_r(self):
        """Executa analise de similaridade (requer R)."""
        from src.core.corpus import Corpus
        from src.analysis import SimilarityAnalysis
        
        corpus = Corpus()
        corpus.add_uci("**** *var1")
        for word in ["politica", "publica", "educacao", "saude"]:
            corpus.add_word(word)
        
        analysis = SimilarityAnalysis(corpus)
        result = analysis.run(min_freq=1)
        
        assert result is not None


class TestFullPipeline:
    """Testa pipeline completo."""
    
    def test_import_and_clean_pipeline(self):
        """Testa: arquivo -> importador -> cleaner."""
        from src.importers import TXTImporter
        from src.importers.corpus_cleaner import CorpusCleaner
        
        fixture_path = Path(__file__).parent / "fixtures" / "exemplo.txt"
        if not fixture_path.exists():
            pytest.skip("Arquivo de fixture nao encontrado")
        
        # 1. Importar
        importer = TXTImporter()
        result = importer.extract(str(fixture_path))
        assert result.text
        
        # 2. Limpar
        cleaner = CorpusCleaner()
        cleaned = cleaner.limpar(result.text)
        assert cleaned
        
        # Verificar estrutura
        assert "****" in cleaned
        assert "*loc_" in cleaned or "*sexo_" in cleaned
    
    def test_corpus_to_statistics_pipeline(self):
        """Testa: corpus -> analise estatisticas."""
        from src.core.corpus import Corpus
        from src.analysis import StatisticsAnalysis
        
        corpus = Corpus()
        corpus.add_uci("**** *var1")
        corpus.add_uci("**** *var2")
        
        for word in ["palavra1", "palavra2", "palavra3"]:
            corpus.add_word(word)
        
        analysis = StatisticsAnalysis(corpus)
        stats = analysis.get_corpus_statistics()
        
        assert stats is not None


class TestErrorHandling:
    """Testa tratamento de erros."""
    
    def test_import_nonexistent_file(self):
        """Importar arquivo inexistente gera erro adequado."""
        from src.importers import TXTImporter
        from src.importers.base_importer import ImporterError
        
        importer = TXTImporter()
        
        with pytest.raises((ImporterError, FileNotFoundError)):
            importer.extract("/caminho/que/nao/existe.txt")
    
    def test_import_wrong_format(self, tmp_path):
        """Importar formato errado gera erro adequado."""
        from src.importers import get_importer_for_file
        from src.importers.base_importer import ImporterError
        
        # Criar arquivo com extensao invalida
        test_file = tmp_path / "test.xyz"
        test_file.write_text("conteudo", encoding='utf-8')
        
        with pytest.raises((ImporterError, ValueError)):
            get_importer_for_file(str(test_file))
    
    def test_empty_corpus_statistics(self):
        """Corpus vazio ainda gera estatisticas."""
        from src.core.corpus import Corpus
        from src.analysis import StatisticsAnalysis
        
        corpus = Corpus()
        # Nao popular o corpus
        
        analysis = StatisticsAnalysis(corpus)
        stats = analysis.get_corpus_statistics()
        
        # Deve retornar algo, mesmo que zerado
        assert stats is not None


class TestConfigManager:
    """Testa gerenciador de configuracoes."""
    
    def test_config_manager_creates_file(self, tmp_path):
        """ConfigManager cria arquivo de configuracao."""
        from src.core.config_manager import ConfigManager
        
        config_file = tmp_path / "config.json"
        config = ConfigManager(str(config_file))
        
        config.set("test_key", "test_value")
        config.save()
        
        assert config_file.exists()
    
    def test_config_manager_reads_values(self, tmp_path):
        """ConfigManager le valores salvos."""
        from src.core.config_manager import ConfigManager
        
        config_file = tmp_path / "config.json"
        
        # Salvar
        config1 = ConfigManager(str(config_file))
        config1.set("my_key", "my_value")
        config1.save()
        
        # Ler novamente
        config2 = ConfigManager(str(config_file))
        value = config2.get("my_key")
        
        assert value == "my_value"

    def test_config_manager_persists_last_analysis_params(self, tmp_path):
        """ConfigManager persiste ultimos parametros por tipo de analise."""
        from src.core.config_manager import ConfigManager

        config_file = tmp_path / "config.json"

        config1 = ConfigManager(str(config_file))
        config1.set_last_analysis_params(
            "chd",
            {"n_classes": 7, "min_freq": 4, "method": "average"},
        )
        config1.save()

        config2 = ConfigManager(str(config_file))
        params = config2.get_last_analysis_params("chd")

        assert params["n_classes"] == 7
        assert params["min_freq"] == 4
        assert params["method"] == "average"

    def test_config_manager_includes_analysis_defaults(self, tmp_path):
        """ConfigManager expõe defaults de análise mesmo sem customização."""
        from src.core.config_manager import ConfigManager

        config = ConfigManager(str(tmp_path / "config.json"))
        defaults = config.get_analysis_defaults("matrix_afc")

        assert defaults["n_dim"] == 2
        assert defaults["typegraph"] == "png"


class TestRExecutor:
    """Testa executor de scripts R."""
    
    def test_r_executor_detects_r(self):
        """RExecutor tenta detectar R."""
        from src.core.r_executor import RExecutor
        
        executor = RExecutor()
        
        # Deve ter um caminho (pode ser None se R nao instalado)
        # Mas nao deve dar erro
        assert hasattr(executor, 'r_path')
    
    def test_r_executor_has_execute_method(self):
        """RExecutor tem metodo execute."""
        from src.core.r_executor import RExecutor
        
        executor = RExecutor()
        assert hasattr(executor, 'execute')
        assert callable(executor.execute)

    def test_execute_uses_rscript_positional_script_argument(self, monkeypatch, tmp_path):
        """RExecutor deve chamar Rscript sem usar '-f' (argumento posicional)."""
        from src.core.r_executor import RExecutor
        from src.core import r_executor as r_executor_module

        script_path = tmp_path / "script.R"
        script_path.write_text("cat('ok')\n", encoding="utf-8")

        captured = {}

        class DummyProcess:
            returncode = 0

            def communicate(self, timeout=None):
                return ("ok\n", "")

        def fake_popen(command, **kwargs):
            captured["command"] = list(command)
            return DummyProcess()

        monkeypatch.setattr(r_executor_module.subprocess, "Popen", fake_popen)

        executor = RExecutor.__new__(RExecutor)
        executor._logger = None
        executor._cran_mirror = "https://cloud.r-project.org"
        executor.r_path = "Rscript.exe"

        result = executor.execute(
            script_path=str(script_path),
            working_dir=str(tmp_path),
            timeout=30,
        )

        assert result.return_code == 0
        assert captured["command"][:3] == ["Rscript.exe", "--vanilla", "--slave"]
        assert "-f" not in captured["command"]
        assert captured["command"][-1] == str(script_path)
