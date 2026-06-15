"""
Unit tests for the Analysis modules.

Tests TextProcessor, RScriptGenerator, and AnalysisExecutor.
"""

import pytest
import tempfile
from pathlib import Path
import sys
import csv
import re
import json
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.corpus import Corpus
from src.core.text_processor import TextProcessor, TextProcessorError
from src.core.lexicon import Lexicon, resolve_lexicon_path
from src.core.r_script_generator import RScriptGenerator, RScriptGeneratorError
from src.core.analysis_executor import (
    AnalysisExecutor, AnalysisTask, AnalysisType, TaskStatus
)
from src.analysis.statistics import StatisticsAnalysis
from src.analysis.similarity import SimilarityAnalysis
from src.analysis.chd_reinert import CHDAnalysis, CHDResult
from src.analysis.emotions import EmotionsAnalysis


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_corpus():
    """Create a sample corpus for testing."""
    corpus = Corpus({'ucemethod': 0, 'ucesize': 100})
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        corpus.connect(db_path)
        
        # Add UCIs
        corpus.add_uci("**** *doc_1 *type_a")
        corpus.add_uci("**** *doc_2 *type_b")
        
        # Add UCEs with text
        corpus.add_uce(0, 0, "análise texto qualitativa pesquisa dados")
        corpus.add_uce(0, 0, "pesquisa qualitativa estudo caso metodologia")
        corpus.add_uce(1, 0, "análise quantitativa estatística dados números")
        corpus.add_uce(1, 0, "estatística análise dados quantitativa resultados")
        
        # Add words
        for word in ["análise", "texto", "qualitativa", "pesquisa", "dados",
                     "estudo", "caso", "metodologia", "quantitativa", 
                     "estatística", "números", "resultados"]:
            corpus.add_word(word, gram="noun", lem=word)
        
        yield corpus
        corpus.close()


@pytest.fixture
def empty_corpus():
    """Create an empty corpus for testing edge cases."""
    return Corpus()


# =============================================================================
# TextProcessor Tests
# =============================================================================

class TestTextProcessor:
    """Tests for the TextProcessor class."""
    
    def test_processor_creation(self, sample_corpus):
        """Test TextProcessor initialization."""
        processor = TextProcessor(sample_corpus)
        assert processor.corpus is sample_corpus
        assert processor.dtm is None
        assert processor.cooc is None
    
    def test_build_vocabulary(self, sample_corpus):
        """Test vocabulary building."""
        processor = TextProcessor(sample_corpus)
        processor._build_vocabulary(min_freq=1, use_lemmas=False, active_only=True)
        
        assert len(processor.vocabulary) > 0
        assert "análise" in processor.vocabulary
    
    def test_build_dtm(self, sample_corpus):
        """Test document-term matrix construction."""
        processor = TextProcessor(sample_corpus)
        dtm = processor.build_dtm(min_freq=1)
        
        assert dtm is not None
        assert dtm.shape[0] == 4  # 4 UCEs
        assert dtm.shape[1] > 0  # Some words
        assert dtm.nnz > 0  # Non-empty

    def test_build_dtm_uses_internal_form_indices_when_text_differs_from_vocabulary(self):
        """DTM must use corpus word indexes, not only raw text splitting."""
        corpus = Corpus({'ucemethod': 0, 'ucesize': 100})
        corpus.add_uci("**** *doc_1")
        uce = corpus.add_uce(0, 0, "Análise QUALITATIVA apareceu no corpus.")
        corpus.add_word("analise", gram="noun", lem="analise", uce_id=uce.ident)
        corpus.add_word("qualitativa", gram="noun", lem="qualitativa", uce_id=uce.ident)

        processor = TextProcessor(corpus)
        dtm = processor.build_dtm(min_freq=1, use_lemmas=True, active_only=True)

        assert processor.vocabulary == ["analise", "qualitativa"]
        assert dtm.shape == (1, 2)
        assert dtm.nnz == 2
    
    def test_dtm_sparsity(self, sample_corpus):
        """Test DTM is truly sparse."""
        processor = TextProcessor(sample_corpus)
        dtm = processor.build_dtm(min_freq=1)
        
        # Calculate density
        density = dtm.nnz / (dtm.shape[0] * dtm.shape[1])
        assert density < 0.5  # Matrix should be relatively sparse
    
    def test_build_cooccurrence(self, sample_corpus):
        """Test co-occurrence matrix construction."""
        processor = TextProcessor(sample_corpus)
        processor.build_dtm(min_freq=1)
        cooc = processor.build_cooccurrence_matrix(window_size=2, min_freq=1)
        
        assert cooc is not None
        assert cooc.shape[0] == cooc.shape[1]  # Square matrix
    
    def test_word_frequencies(self, sample_corpus):
        """Test word frequency retrieval."""
        processor = TextProcessor(sample_corpus)
        freqs = processor.get_word_frequencies()
        
        assert len(freqs) > 0
        # Should be sorted by frequency descending
        if len(freqs) > 1:
            assert freqs[0][1] >= freqs[-1][1]

    def test_active_only_excludes_portuguese_stopwords(self):
        """Active vocabulary should demote stopwords based on IRaMuTeQ lexicon."""
        lexicon = Lexicon()
        loaded = lexicon.load(resolve_lexicon_path("portuguese"))
        assert loaded > 0

        corpus = Corpus({"ucemethod": 1, "ucesize": 40}, lexicon=lexicon)
        corpus.add_uci("**** *doc_1")
        uce = corpus.add_uce(0, 0, "que analise")
        corpus.add_word("que", uce_id=uce.ident)
        corpus.add_word("analise", uce_id=uce.ident)

        processor = TextProcessor(corpus)
        freqs = dict(processor.get_word_frequencies(active_only=True))

        assert corpus.formes["que"].act == 2
        assert corpus.formes["analise"].act == 1
        assert "que" not in freqs
        assert "analise" in freqs
    
    def test_export_for_chd(self, sample_corpus):
        """Test CHD data export."""
        processor = TextProcessor(sample_corpus)
        processor.build_dtm(min_freq=1)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            files = processor.export_for_chd(Path(tmpdir))
            
            assert 'dtm' in files
            assert files['dtm'].exists()
            assert 'vocabulary' in files
            assert files['vocabulary'].exists()

            with files['dtm'].open("r", encoding="utf-8", newline="") as file:
                reader = csv.reader(file, delimiter=';')
                header = next(reader)
                first_data_row = next(reader)
            assert header[0] == ""
            assert first_data_row[0] == str(processor.doc_ids[0])

    def test_export_for_chd_native(self, sample_corpus):
        """Native CHD export writes MatrixMarket + listuce mappings."""
        processor = TextProcessor(sample_corpus)
        processor.build_dtm(min_freq=1, use_lemmas=False, active_only=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            files = processor.export_for_chd_native(
                Path(tmpdir),
                tailleuc1=3,
                tailleuc2=5,
                classif_mode=0,
            )

            assert files["dtm"].exists()
            assert files["dtm2"].exists()
            assert files["listuce1"].exists()
            assert files["listuce2"].exists()

            with files["dtm"].open("r", encoding="utf-8") as file:
                first_line = file.readline().strip()
                second_line = file.readline().strip()
            assert first_line == "%%MatrixMarket matrix coordinate integer general"
            assert len(second_line.split()) == 3

            with files["listuce1"].open("r", encoding="utf-8", newline="") as file:
                reader = csv.reader(file, delimiter=";")
                header = next(reader)
                first = next(reader)
            assert header == ["uce", "uc"]
            assert len(first) == 2

            files_mode1 = processor.export_for_chd_native(
                Path(tmpdir) / "mode1",
                tailleuc1=3,
                tailleuc2=5,
                classif_mode=1,
            )
            assert files_mode1["dtm"].exists()
            assert files_mode1["listuce1"].exists()
            assert "dtm2" not in files_mode1
            assert "listuce2" not in files_mode1

            with files_mode1["dtm"].open("r", encoding="utf-8") as file:
                _mm_header = file.readline().strip()
                matrix_shape = file.readline().strip().split()
            assert int(matrix_shape[0]) == sample_corpus.getucenb()

            with files_mode1["listuce1"].open("r", encoding="utf-8", newline="") as file:
                reader = csv.reader(file, delimiter=";")
                next(reader, None)
                rows = [(int(r[0]), int(r[1])) for r in reader if len(r) >= 2]
            assert len(rows) == sample_corpus.getucenb()
            assert [uc for _uce, uc in rows] == list(range(sample_corpus.getucenb()))
    
    def test_export_for_similarity(self, sample_corpus):
        """Test similarity data export."""
        processor = TextProcessor(sample_corpus)
        processor.build_dtm(min_freq=1)
        processor.build_cooccurrence_matrix()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            files = processor.export_for_similarity(Path(tmpdir))
            
            assert 'cooccurrence' in files
            assert files['cooccurrence'].exists()
    
    def test_dtm_stats(self, sample_corpus):
        """Test DTM statistics."""
        processor = TextProcessor(sample_corpus)
        processor.build_dtm(min_freq=1)
        
        stats = processor.get_dtm_stats()
        
        assert 'n_documents' in stats
        assert 'n_words' in stats
        assert 'sparsity' in stats
        assert 0 <= stats['sparsity'] <= 1


class TestTextProcessorErrors:
    """Tests for TextProcessor error handling."""
    
    def test_empty_corpus_dtm(self, empty_corpus):
        """Test DTM building with empty corpus raises error."""
        processor = TextProcessor(empty_corpus)
        
        with pytest.raises(TextProcessorError):
            processor.build_dtm()


# =============================================================================
# RScriptGenerator Tests
# =============================================================================

class TestRScriptGenerator:
    """Tests for the RScriptGenerator class."""
    
    def test_generator_creation(self):
        """Test RScriptGenerator initialization."""
        generator = RScriptGenerator()
        assert generator.templates_dir is None
    
    def test_generate_chd_script(self):
        """Test CHD script generation."""
        generator = RScriptGenerator()
        params = {
            'pathout': '/tmp/test',
            'nb_classes': 5,
            'data_file': 'data.csv',
        }
        
        script = generator.generate_chd_script(params)
        
        assert 'CHD' in script
        assert 'hclust' in script
        assert '/tmp/test' in script or 'C:/tmp/test' in script.replace('\\', '/')

    def test_generate_chd_native_script(self):
        """Test native CHD script generation (IRaMuTeQ pipeline)."""
        generator = RScriptGenerator()
        script = generator.generate_chd_native_script(
            {
                "pathout": "/tmp/test",
                "nb_classes": 5,
                "classif_mode": 1,
                "script_chd": "/tmp/CHD.R",
                "script_chdtxt": "/tmp/chdtxt.R",
                "script_anacor": "/tmp/anacor.R",
                "script_rgraph": "/tmp/Rgraph.R",
            }
        )

        assert "readMM" in script
        assert "Rchdtxt(" in script
        assert '/tmp/CHD.R' in script or 'C:/tmp/CHD.R' in script.replace('\\', '/')
    
    def test_generate_similarity_script(self):
        """Test similarity script generation."""
        generator = RScriptGenerator()
        params = {
            'pathout': '/tmp/test',
            'layout': 'kamada',
            'grayscale': True,
            'gexf_output': '/tmp/test/similarity.gexf',
        }
        
        script = generator.generate_similarity_script(params)
        
        assert 'Similarity' in script or 'igraph' in script
        assert 'kamada' in script
        assert 'TRUE' in script  # grayscale
        assert 'edge_widths' in script or 'E(g)$weight' in script  # Edge width calculation
        assert 'igraph' in script  # Uses igraph package
        assert 'similarity.gexf' in script
        assert 'id = node_ids' in script
        assert 'label = node_names' in script

    def test_generate_similarity_script_with_advanced_options(self):
        """Test similarity script includes MST and communities logic."""
        generator = RScriptGenerator()
        params = {
            'pathout': '/tmp/test',
            'strict_iramuteq_style': False,
            'layout': 'fruchterman',
            'arbremax': True,
            'detect_communities': True,
            'community_method': 'walktrap',
            'typegraph': 'svg',
        }

        script = generator.generate_similarity_script(params)

        assert 'mst(' in script
        assert 'cluster_walktrap' in script
        assert 'similarity_communities.csv' in script or 'community' in script
        assert 'similarity_centrality.csv' in script or 'centrality' in script
        assert 'svg(' in script

    def test_generate_similarity_script_preserves_halo_controls_in_custom_mode(self):
        """Halo controls remain parameter-driven when strict IRaMuTeQ mode is disabled."""
        generator = RScriptGenerator()
        params = {
            'pathout': '/tmp/test',
            'strict_iramuteq_style': False,
            'detect_communities': False,
            'community_method': 'multilevel',
            'show_halo': True,
            'show_edge_labels': False,
        }

        script = generator.generate_similarity_script(params)

        assert 'show_halo <- TRUE' in script
        assert 'halo = show_halo' in script
        assert 'if (show_halo && is.null(community_idx))' not in script
        assert 'community_idx <- as.integer(4)' not in script
        assert 'show_halo <- FALSE' not in script

    def test_generate_similarity_script_forces_iramuteq_clone_baseline(self):
        """Strict IRaMuTeQ mode suppresses Lexi-only visual extras."""
        generator = RScriptGenerator()
        params = {
            'pathout': '/tmp/test',
            'arbremax': False,
            'show_edge_labels': True,
            'show_halo': True,
            'detect_communities': True,
        }

        script = generator.generate_similarity_script(params)

        assert 'arbremax <- TRUE' in script
        assert 'show_edge_labels <- FALSE' in script
        assert 'show_halo <- FALSE' in script
        assert 'detect_communities <- FALSE' in script

    def test_generate_similarity_script_uses_official_native_render_controls(self):
        """Official/native parity must disable LabiiaLex-only repel tweaks."""
        generator = RScriptGenerator()
        script = generator.generate_similarity_script(
            {
                "pathout": "/tmp/test",
                "parity_profile": "official_0_8a7",
                "render_profile": "native",
            }
        )

        assert ".lexi_enable_repel <- FALSE" in script
        assert "edge.curved = FALSE" in script
        assert "width <- 1000" in script
        assert "height <- 1000" in script

    def test_generate_chd_and_wordcloud_support_svg(self):
        """CHD and word cloud templates support SVG output device."""
        generator = RScriptGenerator()

        chd_script = generator.generate_chd_script({
            'pathout': '/tmp/test',
            'typegraph': 'svg',
        })
        wc_script = generator.generate_wordcloud_script({
            'pathout': '/tmp/test',
            'typegraph': 'svg',
        })

        assert 'if (typegraph == "svg")' in chd_script
        assert 'svg(' in chd_script
        assert 'if (typegraph == "svg")' in wc_script
        assert 'ggsave(' in wc_script

    def test_generate_wordcloud_script_uses_ranked_color_bins_and_safe_defaults(self):
        """Wordcloud script should default to readable visual settings."""
        generator = RScriptGenerator()
        script = generator.generate_wordcloud_script({'pathout': '/tmp/test'})

        assert 'colors_palette      <- "Dark2"' in script
        assert 'sizing_mode         <- "area"' in script
        assert 'eccentricity        <- 0.65' in script
        assert 'rank(-words_df$freq, ties.method = "first")' in script
        assert 'max_steps           <- 60' in script
        assert 'grid_size           <- 4' in script

    def test_generate_wordcloud_script_adapts_dimensions_for_density(self):
        """Adaptive dimensions should grow with denser/complex clouds."""
        generator = RScriptGenerator()
        script_small = generator.generate_wordcloud_script(
            {'pathout': '/tmp/test', 'max_words': 40, 'shape': 'square', 'sizing_mode': 'area'}
        )
        script_dense = generator.generate_wordcloud_script(
            {
                'pathout': '/tmp/test',
                'max_words': 220,
                'shape': 'triangle-forward',
                'sizing_mode': 'height',
                'eccentricity': 0.35,
            }
        )

        width_small = int(re.search(r"width\s*<-\s*(\d+)", script_small).group(1))
        width_dense = int(re.search(r"width\s*<-\s*(\d+)", script_dense).group(1))
        assert 980 <= width_small <= 1900
        assert width_dense <= 1900
        assert width_dense > width_small

    def test_generate_wordcloud_script_includes_shape_diagnostics(self):
        """Wordcloud template includes explicit shape diagnostics metadata."""
        generator = RScriptGenerator()
        script = generator.generate_wordcloud_script(
            {"pathout": "/tmp/test", "shape": "cardioid", "shape_requested": "cardioid"}
        )

        assert 'shape_requested     <- "cardioid"' in script
        assert "allowed_shapes <- c(" in script
        assert "shape_effective = shape" in script
        assert 'meta_file           <- "wordcloud_render_meta.json"' in script
        assert "geom_fn <- geom_text_wordcloud_area" in script

    def test_generate_wordcloud_script_includes_render_metadata_fields(self):
        """Wordcloud script should emit render diagnostics used by installer self-test."""
        generator = RScriptGenerator()
        script = generator.generate_wordcloud_script({"pathout": "/tmp/test"})

        assert 'render_engine = "ggwordcloud"' in script
        assert "ggwordcloud_version = ggwordcloud_version" in script
        assert "geom_used = geom_used" in script
        assert "shape_strategy = shape_strategy" in script
        assert "shape_validation_ok = identical(shape_requested, shape)" in script

    def test_generate_wordcloud_script_keeps_area_geom_baseline(self):
        """Regression guard: supported formats must keep area geom baseline."""
        generator = RScriptGenerator()
        script = generator.generate_wordcloud_script(
            {"pathout": "/tmp/test", "shape": "star", "shape_requested": "star"}
        )
        assert "geom_fn <- geom_text_wordcloud_area" in script

    def test_generate_emotions_script_uses_frequency_weighted_vocabulary(self):
        """Emotions template must classify unique normalized words for performance."""
        generator = RScriptGenerator()
        script = generator.generate_emotions_script({"pathout": "/tmp/test"})

        assert "words_freq <- sort(table(token_df$palavra), decreasing = TRUE)" in script
        assert "unique_words <- names(words_freq)" in script
        assert "word_nrc <- get_nrc_sentiment(unique_words, language = \"portuguese\")" in script
        assert "frequencia_token" in script
        assert "lookup_idx <- match(token_df$palavra, word_lookup$palavra)" in script
        assert "token_scores <- word_lookup[lookup_idx, export_cols, drop = FALSE]" in script

    def test_generate_emotions_script_preserves_label_space_and_radar_percentages(self):
        """Emotions template should avoid clipped labels and keep radar values as percentages."""
        generator = RScriptGenerator()
        script = generator.generate_emotions_script({"pathout": "/tmp/test"})

        assert "bar_ylim_max <- max(bar_vals) * 1.28 + 2" in script
        assert "ylim      = c(0, bar_ylim_max)" in script
        assert "xpd = NA" in script
        assert "radar_pct_vals <- emotion_pct[emotion_cols]" in script
        assert "paste0(formatC(radar_pct_vals[i], format = \"f\", digits = 2), \"%\")" in script
        assert "axistype  = 0" in script
        assert "vlabels   = rep(\"\", length(emotion_cols))" in script
        assert "x = axis_x * 1.34" in script
        assert "tangent_x <- -sin(angles[i])" in script
        assert "pct_offset <- if (abs(axis_x) > 0.75) 0.22 else if (abs(axis_y) > 0.75) 0.08 else 0.14" in script
        assert "pct_cex <- if (abs(axis_x) > 0.75) 0.78 else 0.82" in script
        assert "x = axis_x * 1.10 + tangent_x * pct_offset" in script

    def test_generate_emotions_script_exports_token_level_matches(self):
        """Emotions export should be reproducible from token-level assignments."""
        generator = RScriptGenerator()
        script = generator.generate_emotions_script({"pathout": "/tmp/test"})

        assert "raw_tokens <- unlist(strsplit(raw_text, \"\\\\s+\"))" in script
        assert "token_id = seq_along(valid_idx)" in script
        assert "palavra_original = raw_tokens[valid_idx]" in script
        assert "palavra = norm_tokens[valid_idx]" in script
        assert "tipo = if (emo_col %in% c(\"positive\", \"negative\")) \"sentimento\" else \"emocao\"" in script
        assert "classified_rows <- lapply(export_cols, function(emo_col) {" in script
        assert "words_long_df <- words_long_df[order(words_long_df$token_id, words_long_df$emocao), ]" in script
        assert "write.csv(words_long_df, file = words_out, row.names = FALSE, fileEncoding = \"UTF-8\")" in script

    def test_generate_emotions_script_exports_grouped_word_lists(self):
        """Emotions export should also include grouped word lists per class for direct audit."""
        generator = RScriptGenerator()
        script = generator.generate_emotions_script({"pathout": "/tmp/test"})

        assert 'words_summary_out <- "emotions_words_summary.csv"' in script
        assert "words_summary_rows <- lapply(export_cols, function(emo_col) {" in script
        assert "palavras_tokens = paste(matched_words, collapse = \" | \")" in script
        assert "palavras_unicas_lista = paste(matched_words_unique, collapse = \" | \")" in script
        assert "write.csv(words_summary_df, file = words_summary_out, row.names = FALSE, fileEncoding = \"UTF-8\")" in script

    def test_generate_emotions_script_aligns_stats_with_exported_token_scores(self):
        """Emotions stats must come from the same token scores used by the export CSV."""
        generator = RScriptGenerator()
        script = generator.generate_emotions_script({"pathout": "/tmp/test"})

        assert "totals <- colSums(token_scores[, emotion_cols, drop = FALSE])" in script
        assert "polarities <- colSums(token_scores[, c(\"positive\", \"negative\"), drop = FALSE])" in script
        assert "total_polarity <- sum(polarities)" in script
        assert "polarity_pct <- if (total_polarity > 0) round(polarities / total_polarity * 100, 2) else rep(0, 2)" in script
        assert "porcentagem = c(emotion_pct, as.numeric(polarity_pct[c(\"positive\", \"negative\")]))" in script

    def test_generate_emotions_script_creates_separate_polarity_graph(self):
        """Polarity should render to its own graph artifact for a dedicated UI tab."""
        generator = RScriptGenerator()
        script = generator.generate_emotions_script({"pathout": "/tmp/test"})

        assert 'polarity_out <- "emotions_polarity.png"' in script
        assert 'main      = "Polaridade — Léxico NRC"' in script
        assert 'png(polarity_out,' in script

    def test_emotions_analysis_clamps_small_plot_dimensions_before_r_script(self):
        """Small persisted UI dimensions must not create R 'figure margins too large' plots."""
        width, height = EmotionsAnalysis._safe_plot_dimensions({"width": 500, "height": 300})

        assert width >= 900
        assert height >= 650


# =============================================================================
# Analysis Modules Tests
# =============================================================================


class TestStatisticsAnalysis:
    """Tests for StatisticsAnalysis."""

    def test_basic_statistics(self, sample_corpus):
        """Test corpus statistics calculation."""
        analysis = StatisticsAnalysis(sample_corpus)
        stats = analysis.get_corpus_statistics()

        assert stats.total_ucis == 2
        assert stats.total_uces == 4
        assert stats.total_formes == 12
        assert stats.total_occurrences == 12
        assert stats.total_hapax == 12
        assert stats.mean_words_per_uce == pytest.approx(3.0)
        assert stats.vocabulary_richness == pytest.approx(1.0)

    def test_frequency_distribution(self, sample_corpus):
        """Test frequency distribution."""
        analysis = StatisticsAnalysis(sample_corpus)
        dist = analysis.get_frequency_distribution()
        assert dist[1] == 12

    def test_word_frequencies_limit(self, sample_corpus):
        """Test word frequency top_n limit."""
        analysis = StatisticsAnalysis(sample_corpus)
        freqs = analysis.get_word_frequencies(top_n=5)
        assert len(freqs) == 5

    def test_generate_statistics_graphs(self, sample_corpus):
        """Statistics graphs are generated from R script outputs."""

        class DummyRExecutor:
            def execute(self, script_path, working_dir, timeout=600):
                script = Path(script_path).read_text(encoding="utf-8")
                run_dir = Path(working_dir)
                for graph_name in re.findall(r"(?:png|svg)\(['\"]([^'\"]+)['\"]", script):
                    (run_dir / graph_name).write_text("img", encoding="utf-8")
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = StatisticsAnalysis(sample_corpus, r_executor=DummyRExecutor())
            graphs = analysis.generate_graphs(Path(tmpdir), typegraph="png")
            assert "zipf" in graphs
            assert graphs["zipf"].exists()
            assert "uce_size_distribution" in graphs
            assert graphs["uce_size_distribution"].exists()


class TestExtraAnalyses:
    """Tests for extra analyses integrated from external scripts."""

    def test_keyness_extra_runs(self, sample_corpus, tmp_path):
        from src.analysis.keyness_extra import KeynessExtraAnalysis

        class DummyKeynessRunner:
            def run_script(self, script_name, args, timeout=240):
                assert script_name == "keyness_quanteda.R"
                Path(args["output_csv"]).write_text(
                    (
                        "term;keyness_score;p_value;target_count;reference_count;norm_a;norm_b;direction\n"
                        "analise;15.500000;0.0001;12;3;3200.0;800.0;A\n"
                        "dados;-9.200000;0.0040;2;11;530.0;2900.0;B\n"
                    ),
                    encoding="utf-8",
                )
                Path(args["output_plot"]).write_bytes(b"PNG")
                Path(args["output_summary"]).write_text(
                    json.dumps({"tokens_a": 300, "tokens_b": 320, "rows": 2}),
                    encoding="utf-8",
                )
                return "ok"

        analysis = KeynessExtraAnalysis(
            sample_corpus,
            tmp_path / "keyness_extra",
            runner=DummyKeynessRunner(),
        )
        result = analysis.run(
            {
                "variable": "type",
                "target_value": "a",
                "min_freq": 1,
                "top_n": 8,
            }
        )

        assert result.variable == "type"
        assert result.target_value == "a"
        assert result.table_path is not None and result.table_path.exists()
        assert result.graph_path is not None and result.graph_path.exists()
        assert len(result.top_terms) > 0

    def test_bigram_network_extra_runs(self, sample_corpus, tmp_path):
        from src.analysis.bigram_network_extra import BigramNetworkExtraAnalysis

        analysis = BigramNetworkExtraAnalysis(sample_corpus, tmp_path / "bigram_extra")
        result = analysis.run({"min_bigram_freq": 1, "top_edges": 40})

        assert result.edges_path is not None and result.edges_path.exists()
        assert result.graph_path is not None and result.graph_path.exists()
        assert result.n_nodes > 0
        assert result.n_edges > 0

    def test_trigram_network_extra_runs(self, sample_corpus, tmp_path):
        from src.analysis.trigram_network_extra import TrigramNetworkExtraAnalysis

        analysis = TrigramNetworkExtraAnalysis(sample_corpus, tmp_path / "trigram_extra")
        result = analysis.run({"min_trigram_freq": 1, "top_edges": 40})

        assert result.edges_path is not None and result.edges_path.exists()
        assert result.graph_path is not None and result.graph_path.exists()
        assert result.combined_path is not None and result.combined_path.exists()
        assert result.n_nodes > 0
        assert result.n_edges > 0

    def test_wordfish_extra_runs(self, sample_corpus, tmp_path):
        from src.analysis.wordfish_extra import WordfishExtraAnalysis

        analysis = WordfishExtraAnalysis(sample_corpus, tmp_path / "wordfish_extra")
        result = analysis.run({"min_freq": 1, "max_features": 200})

        assert result.graph_path is not None and result.graph_path.exists()
        assert result.scores_path is not None and result.scores_path.exists()
        assert result.n_documents >= 2
        assert result.n_terms > 0

    def test_xray_extra_runs(self, sample_corpus, tmp_path):
        from src.analysis.xray_extra import XRayExtraAnalysis

        analysis = XRayExtraAnalysis(sample_corpus, tmp_path / "xray_extra")
        result = analysis.run({"patterns": "análise,dados", "max_docs": 50})

        assert result.graph_path is not None and result.graph_path.exists()
        assert result.points_path is not None and result.points_path.exists()
        assert result.n_points > 0

    def test_sentiment_extra_runs(self, tmp_path):
        from src.analysis.sentiment_extra import SentimentExtraAnalysis

        corpus = Corpus({'ucemethod': 0, 'ucesize': 100})
        db_path = tmp_path / "sentiment_extra.db"
        corpus.connect(db_path)
        try:
            uci = corpus.add_uci("**** *doc_1 *data_2025-08-01")
            corpus.add_uce(uci.ident, 0, "serviço ótimo feliz sucesso")
            corpus.add_uce(uci.ident, 1, "resultado péssimo ruim problema")

            analysis = SentimentExtraAnalysis(corpus, tmp_path / "sentiment_extra")
            result = analysis.run({"with_timeline": True, "top_words": 10})

            assert result.distribution_graph_path is not None and result.distribution_graph_path.exists()
            assert result.distribution_csv_path is not None and result.distribution_csv_path.exists()
            assert result.word_sentiment_csv_path is not None and result.word_sentiment_csv_path.exists()
            assert result.total_matched_tokens > 0
        finally:
            corpus.close()


class TestSimilarityAnalysis:
    """Tests for SimilarityAnalysis metadata helpers."""

    def test_available_coefficients_and_layouts(self, sample_corpus):
        """Test coefficient and layout availability."""
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = SimilarityAnalysis(sample_corpus, Path(tmpdir))
            coeffs = analysis.get_available_coefficients()
            layouts = analysis.get_available_layouts()

            assert 0 in coeffs
            assert 'fruchterman' in layouts

    def test_run_parses_communities_and_centrality(self, sample_corpus):
        """Similarity run parses community and centrality files generated by R."""
        class DummyRExecutor:
            def execute(self, script_path, working_dir, timeout=600):
                working = Path(working_dir)
                (working / "similarity.svg").write_text("<svg/>", encoding="utf-8")
                (working / "similarity_communities.csv").write_text(
                    "term,community\nanálise,1\nestatística,2\n",
                    encoding="utf-8",
                )
                (working / "similarity_centrality.csv").write_text(
                    "term,degree,weighted_degree\nanálise,3,4.5\nestatística,2,2.0\n",
                    encoding="utf-8",
                )
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = SimilarityAnalysis(
                sample_corpus,
                Path(tmpdir),
                r_executor=DummyRExecutor(),
            )
            result = analysis.run(
                {
                    "min_freq": 1,
                    "typegraph": "svg",
                    "graph_out": "similarity.svg",
                    "detect_communities": True,
                    "community_method": "louvain",
                }
            )

            assert result.graph_path.suffix == ".svg"
            assert result.graph_path.exists()
            assert result.communities is not None
            assert result.communities.get("análise") == 1
            assert result.centrality is not None
            assert result.centrality.get("análise") == pytest.approx(4.5)

    def test_run_filters_selected_words_in_export(self, sample_corpus):
        """Similarity respects selected_words and exports only selected vocabulary."""

        class DummyRExecutor:
            def execute(self, script_path, working_dir, timeout=600):
                working = Path(working_dir)
                (working / "similarity.png").write_text("img", encoding="utf-8")
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = SimilarityAnalysis(
                sample_corpus,
                Path(tmpdir),
                r_executor=DummyRExecutor(),
            )
            result = analysis.run(
                {
                    "min_freq": 1,
                    "selected_words": ["análise", "estatística", "nao_existe"],
                }
            )

            assert result.graph_path.exists()
            contingency_path = Path(tmpdir) / "contingency.csv"
            with contingency_path.open("r", encoding="utf-8") as file:
                header = next(csv.reader(file, delimiter=";"))
            selected_header = set(header[1:])
            assert selected_header == {"análise", "estatística"}

    def test_sanitize_params_enforces_strict_profile_by_default(self):
        config = SimilarityAnalysis.sanitize_params(
            {
                "detect_communities": True,
                "show_halo": True,
                "show_edge_labels": True,
                "cexalpha": True,
                "arbremax": False,
                "layout": "kamada",
                "renderer_backend": "python",
            }
        )
        assert config["strict_iramuteq_style"] is True
        assert config["analysis_mode"] == "strict"
        assert config["parity_profile"] == "official_0_8a7"
        assert config["render_profile"] == "native"
        assert config["detect_communities"] is False
        assert config["show_halo"] is False
        assert config["show_edge_labels"] is False
        assert config["cexalpha"] is False
        assert config["arbremax"] is True
        assert config["layout"] == "frutch"
        assert config["renderer_backend"] == "iramuteq_r"

    def test_sanitize_params_keeps_custom_mode(self):
        config = SimilarityAnalysis.sanitize_params(
            {
                "strict_iramuteq_style": False,
                "detect_communities": True,
                "show_halo": True,
                "show_edge_labels": True,
                "cexalpha": True,
                "arbremax": False,
                "community_method": "walktrap",
            }
        )
        assert config["strict_iramuteq_style"] is False
        assert config["detect_communities"] is True
        assert config["show_halo"] is True
        assert config["show_edge_labels"] is True
        assert config["cexalpha"] is True
        assert config["arbremax"] is False
        assert config["community_method"] == "walktrap"

    def test_sanitize_params_applies_official_native_dimensions(self):
        config = SimilarityAnalysis.sanitize_params(
            {
                "parity_profile": "official_0_8a7",
                "render_profile": "native",
            }
        )
        assert config["width"] == 1000
        assert config["height"] == 1000

    def test_sanitize_params_treats_runtime_selected_words_as_explicit(self):
        config = SimilarityAnalysis.sanitize_params(
            {
                "selected_words": ["análise", "estatística"],
            }
        )
        assert config["selected_words"] == ["análise", "estatística"]
        assert config["selected_words_explicit"] is True

        confirmed = SimilarityAnalysis.sanitize_params(
            {
                "selected_words": ["análise", "estatística"],
                "selected_words_explicit": True,
            }
        )
        assert confirmed["selected_words"] == ["análise", "estatística"]
        assert confirmed["selected_words_explicit"] is True

    def test_sanitize_params_keeps_edge_threshold_disabled_in_strict_mode(self):
        config = SimilarityAnalysis.sanitize_params(
            {
                "analysis_mode": "strict",
                "min_edge": 4,
            }
        )
        assert config["edge_threshold_enabled"] is False
        assert config["min_edge"] == 4.0

    def test_sanitize_params_enables_edge_threshold_by_default_only_in_legacy_mode(self):
        config = SimilarityAnalysis.sanitize_params(
            {
                "analysis_mode": "legacy",
                "strict_iramuteq_style": False,
                "min_edge": 4,
            }
        )
        assert config["edge_threshold_enabled"] is True


class TestCHDProfiles:
    """Tests for CHD chi2 profile computation."""

    def test_compute_chi2_profiles_returns_ranked_terms(self, sample_corpus):
        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = CHDAnalysis(sample_corpus, Path(tmpdir))
            analysis.processor.build_dtm(min_freq=1, use_lemmas=False, active_only=False)

            # Two classes with two UCEs each
            doc_ids = analysis.processor.doc_ids
            analysis._class_uce_map = {
                1: doc_ids[:2],
                2: doc_ids[2:4],
            }
            class_sizes = {1: 2, 2: 2}

            profiles = analysis._compute_chi2_profiles(class_sizes)

            assert 1 in profiles
            assert 2 in profiles
            assert len(profiles[1]) > 0
            word, chi2, freq, pct, sign = profiles[1][0]
            assert isinstance(word, str)
            assert isinstance(chi2, float)
            assert isinstance(freq, int)
            assert isinstance(pct, float)
            assert sign in {"+", "-"}

    def test_run_double_mode_merges_two_clusterings(self, sample_corpus):
        """Double mode crosses two CHD assignments and creates merged classes."""

        class DummyRExecutor:
            def execute(self, script_path, working_dir, timeout=600):
                script_dir = Path(script_path).parent
                if script_dir.name == "double_a":
                    (script_dir / "clusters.csv").write_text(
                        '"","x"\n"1",1\n"2",1\n"3",2\n"4",2\n',
                        encoding="utf-8",
                    )
                    (script_dir / "dendrogramme_a.png").write_text("img", encoding="utf-8")
                elif script_dir.name == "double_b":
                    (script_dir / "clusters.csv").write_text(
                        '"","x"\n"1",1\n"2",2\n"3",1\n"4",2\n',
                        encoding="utf-8",
                    )
                    (script_dir / "dendrogramme_b.png").write_text("img", encoding="utf-8")
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = CHDAnalysis(
                sample_corpus,
                Path(tmpdir),
                r_executor=DummyRExecutor(),
            )
            result = analysis.run(
                {
                    "classif_mode": 0,
                    "nb_classes": 2,
                    "min_freq": 1,
                    "use_lemmas": False,
                    "active_only": False,
                    "tailleuc1": 3,
                    "tailleuc2": 5,
                }
            )

            assert result.n_classes == 4
            assert sorted(result.class_sizes.values()) == [1, 1, 1, 1]
            assert sum(result.class_sizes.values()) == sample_corpus.getucenb()
            assert result.dendrogram_path is not None
            assert result.dendrogram_path.exists()

    def test_build_result_contains_post_processing_outputs(self, sample_corpus):
        """CHD result includes AFC coords, antiprofiles, typical segments and exports."""

        class DummyRExecutor:
            def execute(self, script_path, working_dir, timeout=600):
                script = Path(script_path).name
                working = Path(working_dir)
                if script == "chd_profiles_afc_script.R":
                    (working / "chd_profiles_afc.png").write_text("img", encoding="utf-8")
                    (working / "chd_profiles_afc_row_coords.csv").write_text(
                        '"","Dim1","Dim2"\n"análise",0.25,-0.10\n"dados",-0.40,0.15\n',
                        encoding="utf-8",
                    )
                    (working / "chd_profiles_afc_col_coords.csv").write_text(
                        '"","Dim1","Dim2"\n"class_1",0.55,0.01\n"class_2",-0.55,-0.01\n',
                        encoding="utf-8",
                    )
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = CHDAnalysis(
                sample_corpus,
                Path(tmpdir),
                r_executor=DummyRExecutor(),
            )
            analysis.processor.build_dtm(min_freq=1, use_lemmas=False, active_only=False)
            doc_ids = analysis.processor.doc_ids
            analysis._class_uce_map = {1: doc_ids[:2], 2: doc_ids[2:4]}

            result = analysis._build_result(
                class_sizes={1: 2, 2: 2},
                params={"classif_mode": 1, "typegraph": "png"},
                dendrogram_path=None,
            )

            assert result.afc_graph_path is not None
            assert result.afc_graph_path.exists()
            assert result.afc_row_coords is not None
            assert result.afc_col_coords is not None
            assert result.afc_row_coords.shape[1] >= 2
            assert result.afc_col_coords.shape[1] >= 2
            assert result.typical_segments.get(1)

    def test_post_chd_afc_renders_python_fallback_when_r_visualizer_does_not_plot(self, sample_corpus, monkeypatch):
        """AFC Perfis still gets an XY word plot when CA coords exist but R plotting fails."""

        class DummyRExecutor:
            def execute(self, script_path, working_dir, timeout=600):
                working = Path(working_dir)
                (working / "chd_profiles_afc_row_coords.csv").write_text(
                    '"","Dim1","Dim2"\n"vacina",0.25,-0.10\n"governo",-0.40,0.15\n',
                    encoding="utf-8",
                )
                (working / "chd_profiles_afc_col_coords.csv").write_text(
                    '"","Dim1","Dim2"\n"class_1",0.55,0.01\n"class_2",-0.55,-0.01\n',
                    encoding="utf-8",
                )
                (working / "chd_profiles_afc_inertia.csv").write_text(
                    '"","x"\n"1",0.7\n"2",0.3\n',
                    encoding="utf-8",
                )
                return None

        class UnavailableRVisualizer:
            r_available = False

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("src.analysis.chd_reinert.RVisualizer", UnavailableRVisualizer)
            analysis = CHDAnalysis(
                sample_corpus,
                Path(tmpdir),
                r_executor=DummyRExecutor(),
            )

            graph_path, row_coords, col_coords = analysis._run_post_chd_afc(
                {
                    1: [("vacina", 8.0, 5, 70.0, "+")],
                    2: [("governo", 7.0, 4, 65.0, "+")],
                },
                {"typegraph": "png", "width": 900, "height": 700},
            )

            assert graph_path is not None
            assert graph_path.exists()
            assert graph_path.name == "chd_profiles_afc.png"
            assert row_coords is not None and row_coords.shape[1] >= 2
            assert col_coords is not None and col_coords.shape[1] >= 2

    def test_post_chd_afc_filters_visual_noise_before_matrix_export(self, sample_corpus, monkeypatch):
        """AFC profile matrix should not contain numbers, stopwords or fused n-artifacts."""

        class DummyRExecutor:
            def execute(self, script_path, working_dir, timeout=600):
                working = Path(working_dir)
                (working / "chd_profiles_afc_row_coords.csv").write_text(
                    '"","Dim1","Dim2"\n"vacina",0.25,-0.10\n"governo",-0.40,0.15\n',
                    encoding="utf-8",
                )
                (working / "chd_profiles_afc_col_coords.csv").write_text(
                    '"","Dim1","Dim2"\n"class_1",0.55,0.01\n"class_2",-0.55,-0.01\n',
                    encoding="utf-8",
                )
                return None

        class UnavailableRVisualizer:
            r_available = False

        with tempfile.TemporaryDirectory() as tmpdir:
            monkeypatch.setattr("src.analysis.chd_reinert.RVisualizer", UnavailableRVisualizer)
            output_dir = Path(tmpdir)
            analysis = CHDAnalysis(sample_corpus, output_dir, r_executor=DummyRExecutor())
            profiles = {
                1: [
                    ("vacina", 8.0, 5, 70.0, "+"),
                    ("mp3", 7.0, 5, 65.0, "+"),
                    ("nvoce", 6.0, 4, 60.0, "+"),
                    ("então", 5.0, 4, 55.0, "+"),
                ],
                2: [
                    ("governo", 7.0, 4, 65.0, "+"),
                    ("ntranscrever", 6.0, 4, 60.0, "+"),
                    ("0", 5.0, 4, 55.0, "+"),
                    ("ainda", 4.0, 3, 50.0, "+"),
                ],
            }

            graph_path, _row_coords, _col_coords = analysis._run_post_chd_afc(
                profiles,
                {"typegraph": "png", "width": 900, "height": 700},
            )

            assert graph_path is not None
            matrix_rows = {
                row[0]
                for row in csv.reader((output_dir / "chd_profile_matrix.csv").open(encoding="utf-8"), delimiter=";")
                if row and row[0]
            }
            chi2_rows = {
                row[0]
                for row in csv.reader((output_dir / "chd_profile_chi2.csv").open(encoding="utf-8"))
                if row and row[0]
            }
            assert "vacina" in matrix_rows
            assert "governo" in matrix_rows
            for noisy in ["mp3", "nvoce", "ntranscrever", "então", "0", "ainda"]:
                assert noisy not in matrix_rows
                assert noisy not in chi2_rows

    def test_native_chd_matrix_preflight_writes_diagnostics_and_detects_empty_rows(self, sample_corpus):
        """Degenerate native CHD matrix should be detected before R gets called."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            matrix = output_dir / "TableUc1.csv"
            matrix.write_text(
                "%%MatrixMarket matrix coordinate integer general\n"
                "3 4 1\n"
                "2 1 1\n",
                encoding="utf-8",
            )
            analysis = CHDAnalysis(sample_corpus, output_dir)

            diagnostics = analysis._write_chd_matrix_diagnostics(matrix, role="native_uc1")

            assert diagnostics["rows"] == 3
            assert diagnostics["cols"] == 4
            assert diagnostics["nnz"] == 1
            assert diagnostics["non_empty_rows"] == 1
            assert diagnostics["degenerate"] is True
            assert (output_dir / "chd_matrix_diagnostics.json").exists()

    def test_strict_chd_falls_back_to_ported_reinert_when_native_fails(self, sample_corpus, monkeypatch):
        """Native R 'Too many dimensions!' is recoverable via the PORTED Reinert
        engine — never via a generic hclust pseudo-CHD."""
        from src.analysis.chd_reinert import CHDAnalysisError, CHDResult

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = CHDAnalysis(sample_corpus, Path(tmpdir))
            native_calls = {"count": 0}
            ported_calls = {"count": 0}

            def fake_single(config):
                native_calls["count"] += 1
                raise CHDAnalysisError(
                    what="Falha na execucao do script CHD.",
                    why="Error in boostana(...): Too many dimensions!",
                    how="Verifique os pacotes R necessarios.",
                )

            def fake_ported(config):
                ported_calls["count"] += 1
                return CHDResult(
                    n_classes=5,
                    profiles={cid: [("termo", 4.0, 6, 30.0, "+")] for cid in range(1, 6)},
                    class_sizes={cid: 2 for cid in range(1, 6)},
                    classification_engine="ported_reinert",
                )

            monkeypatch.setattr(analysis, "_run_single_pipeline", fake_single)
            monkeypatch.setattr(analysis, "_can_use_ported_reinert", lambda config: True)
            monkeypatch.setattr(analysis, "_run_legacy_reinert_pipeline", fake_ported)

            result = analysis.run(
                {
                    "analysis_mode": "strict",
                    "strict_iramuteq_clone": True,
                    "use_native_chd": True,
                    "classif_mode": 1,
                    "nb_classes": 5,
                }
            )

            assert result.n_classes == 5
            # Native attempted once (no hclust retry), then the ported engine ran.
            assert native_calls["count"] == 1
            assert ported_calls["count"] == 1
            assert result.classification_engine == "ported_reinert"
            assert analysis._fallback_via_ported is True

    def test_build_result_keeps_native_artifacts_and_exposes_phylogram_in_official_profile(self, sample_corpus, monkeypatch):
        """Official/native CHD keeps the native dendrogram primary and exposes the readable phylogram separately."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            analysis = CHDAnalysis(sample_corpus, output_dir)
            analysis.processor.build_dtm(min_freq=1, use_lemmas=False, active_only=False)
            doc_ids = analysis.processor.doc_ids
            analysis._class_uce_map = {1: doc_ids[:2], 2: doc_ids[2:4]}

            native_dendro = output_dir / "dendrogramme.png"
            native_dendro.write_text("native", encoding="utf-8")
            native_profile = output_dir / "AFC2DL.png"
            native_profile.write_text("native-afc", encoding="utf-8")
            polished_dendro = output_dir / "dendrogramme_polished.png"
            polished_dendro.write_text("polished", encoding="utf-8")
            polished_profile = output_dir / "chd_profiles_afc.png"
            polished_profile.write_text("polished-afc", encoding="utf-8")
            chistable = output_dir / "chistable.csv"
            chistable.write_text("term;1;2\nanalise;5;1\n", encoding="utf-8")
            contout = output_dir / "Contout.csv"
            contout.write_text("term;1;2\nanalise;3;1\n", encoding="utf-8")
            afc_row = output_dir / "afc_row.csv"
            afc_row.write_text("label,Dim1,Dim2\nanalise,0.2,-0.1\n", encoding="utf-8")
            afc_col = output_dir / "afc_col.csv"
            afc_col.write_text("label,Dim1,Dim2\nclass_1,0.5,0.1\nclass_2,-0.5,-0.1\n", encoding="utf-8")

            monkeypatch.setattr(
                analysis,
                "_run_reinert_post_processing",
                lambda class_sizes, ucecl, params, **kwargs: {
                    "chistable": chistable,
                    "contout": contout,
                    "afc2dl": native_profile,
                    "afc_row": afc_row,
                    "afc_col": afc_col,
                },
            )
            monkeypatch.setattr(
                analysis,
                "_read_profiles_from_reinert_tables",
                lambda class_sizes, chistable_path, contout_path: {
                    1: [("analise", 5.0, 3, 60.0, "+")],
                    2: [("dados", 4.0, 2, 40.0, "+")],
                },
            )
            monkeypatch.setattr(
                analysis,
                "_run_post_chd_afc",
                lambda profiles, params: (polished_profile, np.array([[0.1, 0.2]]), np.array([[0.3, 0.4]])),
            )
            monkeypatch.setattr(
                analysis,
                "_generate_enhanced_dendrogram",
                lambda profiles, class_sizes, params: polished_dendro,
            )
            monkeypatch.setattr(analysis, "_compute_antiprofiles", lambda profiles: {})
            monkeypatch.setattr(analysis, "_compute_typical_segments", lambda effective_uce_map, profiles, top_n=10: {})
            monkeypatch.setattr(analysis, "_compute_repeated_segments", lambda effective_uce_map: {})
            monkeypatch.setattr(analysis, "export_all_class_texts", lambda output_dir, class_uce_map: {})
            monkeypatch.setattr(analysis, "_export_colored_corpus", lambda effective_uce_map: None)
            monkeypatch.setattr(analysis, "_build_newick_from_profiles", lambda profiles: "(1,2);")

            result = analysis._build_result(
                class_sizes={1: 2, 2: 2},
                params={
                    "classif_mode": 1,
                    "typegraph": "png",
                    "analysis_mode": "strict",
                    "strict_iramuteq_clone": True,
                    "parity_profile": "official_0_8a7",
                    "render_profile": "native",
                    "prefer_readable_afc_profiles": True,
                },
                dendrogram_path=native_dendro,
            )

            assert result.dendrogram_path == polished_dendro
            assert result.profile_afc_path == native_profile
            assert getattr(result, "alternate_profile_afc_path", None) == polished_profile
            assert result.antiprofiles == {}
            assert result.colored_corpus_path is None
            assert result.class_text_paths == {}

    def test_strict_native_chd_runs_r_pipeline_before_ported_reinert(self, sample_corpus, tmp_path, monkeypatch):
        """Strict/native CHD must prefer the R/IRaMuTeQ path over the ported Python engine."""
        analysis = CHDAnalysis(sample_corpus, tmp_path)
        calls = []

        def fake_single(config):
            calls.append("native")
            return CHDResult(
                n_classes=5,
                profiles={cid: [("termo", 4.0, 6, 30.0, "+")] for cid in range(1, 6)},
                class_sizes={cid: 2 for cid in range(1, 6)},
            )

        def fake_ported(config):
            calls.append("ported")
            raise AssertionError("Ported Reinert should not run before native R CHD")

        monkeypatch.setattr(analysis, "_can_use_ported_reinert", lambda config: True)
        monkeypatch.setattr(analysis, "_run_single_pipeline", fake_single)
        monkeypatch.setattr(analysis, "_run_legacy_reinert_pipeline", fake_ported)

        result = analysis.run(
            {
                "analysis_mode": "strict",
                "strict_iramuteq_clone": True,
                "use_native_chd": True,
                "classif_mode": 1,
                "nb_classes": 5,
                "min_classes": 5,
            }
        )

        assert result.n_classes == 5
        assert calls == ["native"]

    def test_run_similarity_from_class_uses_class_subset(self, sample_corpus):
        """CHD can run similarity only for one selected class."""

        class DummyRExecutor:
            def execute(self, script_path, working_dir, timeout=600):
                script = Path(script_path).name
                working = Path(working_dir)
                if script == "similarity_script.R":
                    (working / "similarity.png").write_text("img", encoding="utf-8")
                return None

        with tempfile.TemporaryDirectory() as tmpdir:
            analysis = CHDAnalysis(
                sample_corpus,
                Path(tmpdir),
                r_executor=DummyRExecutor(),
            )
            # Reuse two UCEs as one class
            uce_ids = [uce.ident for uce in sample_corpus.ucis[0].uces]
            analysis._effective_class_uce_map = {1: uce_ids}

            similarity_result = analysis.run_similarity_from_class(
                1,
                {"min_freq": 1, "graph_out": "similarity.png"},
            )
            assert similarity_result.graph_path.exists()


class TestWordCloudAnalysisHelpers:
    """Helpers for wordcloud shape normalization and metadata."""

    def test_wordcloud_shape_alias_normalization(self):
        from src.analysis.wordcloud import WordCloudAnalysis

        assert WordCloudAnalysis._normalize_shape("circular") == "square"
        assert WordCloudAnalysis._normalize_shape("HEART") == "cardioid"
        assert WordCloudAnalysis._normalize_shape("triangle-upright") == "triangle-upright"
        assert WordCloudAnalysis._normalize_shape("shape_invalido") == "square"

    def test_wordcloud_render_metadata_file(self, tmp_path):
        from src.analysis.wordcloud import WordCloudAnalysis

        corpus = Corpus({"ucemethod": 0, "ucesize": 80})
        analysis = WordCloudAnalysis(corpus, tmp_path / "wc")
        out_dir = tmp_path / "wc_meta"
        out_dir.mkdir(parents=True, exist_ok=True)

        meta_path = analysis._write_render_metadata(
            output_dir=out_dir,
            shape_requested="cardioid",
            shape_effective="cardioid",
            sizing_mode="area",
            eccentricity=0.65,
            output_file="wordcloud.png",
            ok=True,
            error=None,
        )

        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        assert payload["shape_requested"] == "cardioid"
        assert payload["shape_effective"] == "cardioid"
        assert payload["sizing_mode"] == "area"
        assert payload["ok"] is True

    def test_generate_wordcloud_script(self):
        """Test word cloud script generation."""
        generator = RScriptGenerator()
        params = {
            'pathout': '/tmp/test',
            'max_words': 100,
        }
        
        script = generator.generate_wordcloud_script(params)
        
        assert 'wordcloud' in script.lower()
        assert '100' in script
    
    def test_generate_and_save(self):
        """Test script generation and save."""
        generator = RScriptGenerator()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            params = {'pathout': tmpdir}
            script_path = generator.generate_and_save('chd', params)
            
            assert script_path.exists()
            content = script_path.read_text()
            assert 'CHD' in content
    
    def test_invalid_analysis_type(self):
        """Test error for invalid analysis type."""
        generator = RScriptGenerator()
        
        with pytest.raises(RScriptGeneratorError):
            generator.generate_and_save('invalid_type', {})


# =============================================================================
# AnalysisExecutor Tests
# =============================================================================

class TestAnalysisTask:
    """Tests for the AnalysisTask class."""
    
    def test_task_creation(self):
        """Test task creation."""
        task = AnalysisTask.create(AnalysisType.CHD, {'min_freq': 5})
        
        assert task.task_id is not None
        assert task.analysis_type == AnalysisType.CHD
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0
    
    def test_task_from_string(self):
        """Test task creation from string type."""
        task = AnalysisTask.create('similarity', {})
        
        assert task.analysis_type == AnalysisType.SIMILARITY
    
    def test_task_to_dict(self):
        """Test task serialization."""
        task = AnalysisTask.create(AnalysisType.SIMILARITY, {})
        
        data = task.to_dict()
        
        assert data['task_id'] == task.task_id
        assert data['analysis_type'] == 'similarity'
        assert data['status'] == 'pending'


class TestAnalysisExecutor:
    """Tests for the AnalysisExecutor class."""
    
    def test_executor_creation(self, sample_corpus):
        """Test executor initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = AnalysisExecutor(sample_corpus, Path(tmpdir))
            
            assert executor.corpus is sample_corpus
            assert executor.output_dir.exists()
    
    def test_queue_analysis(self, sample_corpus):
        """Test queueing an analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = AnalysisExecutor(sample_corpus, Path(tmpdir))
            
            task = executor.queue_analysis(AnalysisType.CHD, {'min_freq': 1})
            
            assert task.status == TaskStatus.PENDING
            assert task.task_id in [t.task_id for t in executor.get_all_tasks()]
    
    def test_get_status(self, sample_corpus):
        """Test getting task status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = AnalysisExecutor(sample_corpus, Path(tmpdir))
            task = executor.queue_analysis(AnalysisType.SIMILARITY)
            
            status = executor.get_status(task.task_id)
            
            assert status is not None
            assert status.task_id == task.task_id
    
    def test_cancel_analysis(self, sample_corpus):
        """Test cancelling an analysis."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = AnalysisExecutor(sample_corpus, Path(tmpdir))
            task = executor.queue_analysis(AnalysisType.SIMILARITY)
            
            result = executor.cancel_analysis(task.task_id)
            
            assert result is True
            assert executor.get_status(task.task_id).status == TaskStatus.CANCELLED
    
    def test_cancel_nonexistent_task(self, sample_corpus):
        """Test cancelling nonexistent task returns False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = AnalysisExecutor(sample_corpus, Path(tmpdir))
            
            result = executor.cancel_analysis("fake-id")
            
            assert result is False
    
    def test_progress_callback(self, sample_corpus):
        """Test progress callback is called."""
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = AnalysisExecutor(sample_corpus, Path(tmpdir))
            
            progress_updates = []
            
            def callback(task_id, progress, message):
                progress_updates.append((task_id, progress, message))
            
            executor.set_progress_callback(callback)
            executor._update_progress("test-id", 50, "Halfway")
            
            assert len(progress_updates) == 1
            assert progress_updates[0][1] == 50


class TestAnalysisExecutorTypes:
    """Tests for different analysis type values."""
    
    def test_analysis_type_values(self):
        """Test AnalysisType enum values."""
        assert AnalysisType.CHD.value == "chd"
        assert AnalysisType.SIMILARITY.value == "similarity"
        assert AnalysisType.WORDCLOUD.value == "wordcloud"
    
    def test_task_status_values(self):
        """Test TaskStatus enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"
