"""
Unit tests for the Corpus module.

Tests Word, Lem, Uci, Uce classes and Corpus functionality
including SQLite persistence and text segmentation.
"""

import pytest
import tempfile
import threading
from pathlib import Path

from src.core.corpus import (
    Word, Lem, Uci, Uce, Corpus, CorpusError,
    decouperlist, decoupercharact,
    testetoile as check_etoile,
    testint as check_int
)


# =============================================================================
# Word Tests
# =============================================================================

class TestWord:
    """Tests for the Word dataclass."""
    
    def test_word_creation(self):
        """Test basic word creation."""
        word = Word(forme="texto", gram="noun", ident=0)
        assert word.forme == "texto"
        assert word.gram == "noun"
        assert word.ident == 0
        assert word.freq == 1
        assert word.act == 1
    
    def test_word_with_lemma(self):
        """Test word with explicit lemma."""
        word = Word(forme="textos", gram="noun", ident=1, lem="texto")
        assert word.forme == "textos"
        assert word.lem == "texto"
    
    def test_word_default_lemma(self):
        """Test word defaults lemma to forme."""
        word = Word(forme="análise", gram="noun", ident=2)
        assert word.lem == "análise"
    
    def test_word_frequency(self):
        """Test word with explicit frequency."""
        word = Word(forme="e", gram="conj", ident=3, freq=100)
        assert word.freq == 100


# =============================================================================
# Lem Tests
# =============================================================================

class TestLem:
    """Tests for the Lem class."""
    
    def test_lem_creation(self):
        """Test lemma creation."""
        lem = Lem(lem="texto", gram="noun")
        assert lem.lem == "texto"
        assert lem.gram == "noun"
        assert lem.freq == 0
        assert len(lem.formes) == 0
    
    def test_lem_add_forme(self):
        """Test adding word forms to lemma."""
        lem = Lem(lem="texto", gram="noun")
        word1 = Word(forme="texto", gram="noun", ident=0, freq=5)
        word2 = Word(forme="textos", gram="noun", ident=1, freq=3)
        
        lem.add_forme(word1)
        assert lem.freq == 5
        assert 0 in lem.formes
        
        lem.add_forme(word2)
        assert lem.freq == 8
        assert 1 in lem.formes


# =============================================================================
# Uci/Uce Tests
# =============================================================================

class TestUci:
    """Tests for the Uci class."""
    
    def test_uci_from_line(self):
        """Test UCI creation from metadata line."""
        uci = Uci.from_line(0, "**** *var1_val1 *var2_val2")
        assert uci.ident == 0
        assert len(uci.etoiles) == 3
        assert "*var1_val1" in uci.etoiles
        assert "*var2_val2" in uci.etoiles
    
    def test_uci_with_paras(self):
        """Test UCI with paragraph tags."""
        uci = Uci.from_line(1, "**** *tema_educacao", "-*theme_1")
        assert uci.ident == 1
        assert "-*theme_1" in uci.paras
    
    def test_uci_empty_uces(self):
        """Test UCI starts with empty UCE list."""
        uci = Uci.from_line(0, "**** *test")
        assert len(uci.uces) == 0


class TestUce:
    """Tests for the Uce class."""
    
    def test_uce_creation(self):
        """Test UCE creation."""
        uce = Uce(ident=0, para=0, uci=0)
        assert uce.ident == 0
        assert uce.para == 0
        assert uce.uci == 0


# =============================================================================
# Segmentation Tests
# =============================================================================

class TestSegmentation:
    """Tests for text segmentation functions."""
    
    def test_check_etoile_true(self):
        """Test UCI marker detection - positive."""
        assert check_etoile("**** *var1_val1") is True
    
    def test_check_etoile_false(self):
        """Test UCI marker detection - negative."""
        assert check_etoile("This is regular text") is False
        assert check_etoile("*** not enough") is False
    
    def test_check_int_true(self):
        """Test numbered line detection - positive."""
        assert check_int("0001 *text") is True
    
    def test_check_int_false(self):
        """Test numbered line detection - negative."""
        assert check_int("text *marker") is False
    
    def test_decoupercharact_basic(self):
        """Test character-based segmentation."""
        text = "This is a test sentence. This is another sentence."
        found, segment, remainder = decoupercharact(text + '$', 30, 20)
        assert found is True
        assert len(segment) <= 31
    
    def test_decouperlist_basic(self):
        """Test word list-based segmentation."""
        words = ["This", "is", "a", "test", "sentence.", "This", "is", "another", "sentence.", "$"]
        found, segment, remainder = decouperlist(words, 7, 5)
        assert found is True
        assert len(segment) <= 8


# =============================================================================
# Corpus Tests
# =============================================================================

class TestCorpus:
    """Tests for the Corpus class."""
    
    def test_corpus_creation(self):
        """Test corpus initialization."""
        corpus = Corpus()
        assert len(corpus.ucis) == 0
        assert len(corpus.formes) == 0
    
    def test_corpus_with_params(self):
        """Test corpus with parameters."""
        params = {'ucesize': 50, 'ucemethod': 1}
        corpus = Corpus(params)
        assert corpus.parametres['ucesize'] == 50
    
    def test_add_word(self):
        """Test adding words to corpus."""
        corpus = Corpus()
        word = corpus.add_word("texto", gram="noun", lem="texto")
        
        assert word.forme == "texto"
        assert "texto" in corpus.formes
        assert corpus.formes["texto"].freq == 1
    
    def test_add_word_increment_frequency(self):
        """Test word frequency increments on duplicate."""
        corpus = Corpus()
        corpus.add_word("texto")
        corpus.add_word("texto")
        
        assert corpus.formes["texto"].freq == 2
    
    def test_add_uci(self):
        """Test adding UCI to corpus."""
        corpus = Corpus()
        uci = corpus.add_uci("**** *var1_val1 *var2_val2")
        
        assert len(corpus.ucis) == 1
        assert uci.ident == 0
        assert "*var1_val1" in uci.etoiles
    
    def test_add_multiple_ucis(self):
        """Test adding multiple UCIs."""
        corpus = Corpus()
        uci1 = corpus.add_uci("**** *doc_1")
        uci2 = corpus.add_uci("**** *doc_2")
        
        assert len(corpus.ucis) == 2
        assert uci1.ident == 0
        assert uci2.ident == 1
    
    def test_segment_text_character(self):
        """Test text segmentation with character method."""
        corpus = Corpus({'ucemethod': 0, 'ucesize': 50})
        text = "Este é um texto de teste para segmentação. " * 5
        segments = corpus.segment_text(text)
        
        assert len(segments) > 0
        for seg in segments:
            assert len(seg) > 0
    
    def test_segment_text_word_list(self):
        """Test text segmentation with word list method."""
        corpus = Corpus({'ucemethod': 1, 'ucesize': 10})
        text = "Este é um texto de teste para segmentação. " * 5
        segments = corpus.segment_text(text)
        
        assert len(segments) > 0
    
    def test_statistics(self):
        """Test corpus statistics methods."""
        corpus = Corpus()
        corpus.add_uci("**** *doc_1")
        corpus.add_word("texto")
        corpus.add_word("análise")
        corpus.add_word("texto")  # Duplicate
        
        assert corpus.getucinb() == 1
        assert corpus.getwordnb() == 2
        assert corpus.gettokennb() == 3
    
    def test_make_lexique(self):
        """Test vocabulary dictionary creation."""
        corpus = Corpus()
        corpus.add_word("texto", gram="noun")
        corpus.add_word("análise", gram="noun")
        
        lexique = corpus.make_lexique()
        assert "texto" in lexique
        assert "análise" in lexique
        assert lexique["texto"][0] == 1  # frequency
    
    def test_get_hapaxes(self):
        """Test hapax detection."""
        corpus = Corpus()
        corpus.add_word("texto")
        corpus.add_word("texto")  # freq=2
        corpus.add_word("único")  # freq=1 (hapax)
        
        hapaxes = corpus.get_hapaxes()
        assert "único" in hapaxes
        assert "texto" not in hapaxes
    
    def test_make_etoiles(self):
        """Test metadata tag extraction."""
        corpus = Corpus()
        corpus.add_uci("**** *var1_a *var2_b")
        corpus.add_uci("**** *var1_c *var2_d")
        
        etoiles = corpus.make_etoiles()
        assert "*var1_a" in etoiles
        assert "*var2_d" in etoiles


# =============================================================================
# SQLite Persistence Tests
# =============================================================================

class TestCorpusPersistence:
    """Tests for SQLite persistence."""
    
    def test_connect_and_create_tables(self):
        """Test database connection and table creation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_corpus.db"
            corpus = Corpus()
            corpus.connect(db_path)
            
            assert db_path.exists()
            corpus.close()
    
    def test_save_and_load_corpus(self):
        """Test round-trip save/load of corpus."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_corpus.db"
            
            # Create and save corpus
            corpus1 = Corpus()
            corpus1.connect(db_path)
            corpus1.add_word("texto", gram="noun", lem="texto")
            corpus1.add_word("análise", gram="noun", lem="análise")
            corpus1.add_word("texto")  # Increment frequency
            corpus1.save_corpus()
            corpus1.close()
            
            # Load corpus
            corpus2 = Corpus()
            corpus2.load_corpus(db_path)
            
            assert len(corpus2.formes) == 2
            assert corpus2.formes["texto"].freq == 2
            assert corpus2.formes["análise"].freq == 1
            corpus2.close()
    
    def test_add_uce_with_database(self):
        """Test adding UCE with database connection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_corpus.db"
            
            corpus = Corpus()
            corpus.connect(db_path)
            corpus.add_uci("**** *doc_1")
            corpus.add_uce(0, 0, "Este é o texto do segmento.")
            
            # Verify stored
            uces = list(corpus.get_uces())
            assert len(uces) == 1
            assert uces[0][1] == "Este é o texto do segmento."
            corpus.close()
    
    def test_corpus_context_manager(self):
        """Test corpus as context manager."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_corpus.db"
            
            with Corpus() as corpus:
                corpus.connect(db_path)
                corpus.add_word("teste")
                corpus.save_corpus()
            
            # Connection should be closed
            assert corpus._conn is None

    def test_cross_thread_read_with_single_connection(self):
        """Permite leitura em thread diferente (usado por análises assíncronas)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_corpus.db"

            corpus = Corpus()
            corpus.connect(db_path)
            corpus.add_uci("**** *doc_1")
            corpus.add_uce(0, 0, "Segmento em thread")

            output = {}

            def worker():
                output["uces"] = list(corpus.get_uces())

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=5)

            assert "uces" in output
            assert len(output["uces"]) == 1
            assert output["uces"][0][1] == "Segmento em thread"
            corpus.close()


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestCorpusErrors:
    """Tests for error handling."""
    
    def test_save_without_connection(self):
        """Test save fails without database connection."""
        corpus = Corpus()
        corpus.add_word("texto")
        
        with pytest.raises(CorpusError) as exc_info:
            corpus.save_corpus()
        
        assert "banco de dados" in str(exc_info.value).lower()
    
    def test_corpus_error_format(self):
        """Test CorpusError message format."""
        error = CorpusError(
            what="Erro de teste",
            why="Razão de teste",
            how="Solução de teste"
        )
        
        message = str(error)
        assert "Erro de teste" in message
        assert "Motivo:" in message
        assert "Solução:" in message
