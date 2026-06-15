"""
Testes de contrato para a classe ThematicCHDAnalysis (Task 11).

Garante que a pipeline consegue unir os agrupamentos lexicais do CHD
aos topicos latentes do LDA.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import numpy as np

from src.core.corpus import Corpus
from src.analysis.thematic_chd_analysis import ThematicCHDParams, ThematicCHDAnalysis
from src.analysis.chd_reinert import CHDResult

@pytest.fixture
def mock_chd_result(tmp_path) -> CHDResult:
    """Mock de um lixo de CHDAnalysis."""
    class_1 = tmp_path / "class_1.txt"
    class_1.write_text("governo politica governo\npolitica leis", encoding="utf-8")
    
    class_2 = tmp_path / "class_2.txt"
    class_2.write_text("economia juros mercado\ncrise inflacao", encoding="utf-8")
    
    return CHDResult(
        n_classes=2,
        profiles={
            1: [("governo", 1.0, 2, 0.5, "noun"), ("politica", 1.0, 2, 0.5, "noun")],
            2: [("economia", 1.0, 2, 0.5, "noun"), ("juros", 1.0, 1, 0.5, "noun")]
        },
        class_sizes={1: 2, 2: 2},
        class_text_paths={1: class_1, 2: class_2},
        dendrogram_path=tmp_path / "dendrogram.png" # artefato preservado
    )


class TestThematicCHDAnalysis:

    @patch("src.analysis.thematic_chd_analysis.CHDAnalysis")
    def test_thematic_chd_pipeline(self, mock_chd_class, mock_chd_result, tmp_path):
        """Pipeline deve cruzar CHD mockado com LDA das classes."""
        
        # O mock da classe CHDAnalysis deve retornar o mock_chd_result no run
        mock_instance = MagicMock()
        mock_instance.run.return_value = mock_chd_result
        mock_chd_class.return_value = mock_instance
        
        output_dir = tmp_path / "thematic_chd"
        output_dir.mkdir()

        params = ThematicCHDParams(n_topics=2, min_freq=1)
        analysis = ThematicCHDAnalysis()
        
        corpus = MagicMock(spec=Corpus)
        result = analysis.run(corpus, output_dir, params)
        
        assert result.analysis_type == "thematic_chd"
        assert result.chd_result == mock_chd_result
        
        # Artefatos esperados
        heatmap_png = output_dir / "thematic_chd_class_topic_heatmap.png"
        mix_csv = output_dir / "class_topic_mix.csv"
        labels_json = output_dir / "class_labels.json"
        
        assert heatmap_png.exists()
        assert mix_csv.exists()
        assert labels_json.exists()
        
        # Conteudo de mix (2 classes)
        with open(mix_csv, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 3 # cabecalho + classe 1 + classe 2
        
        # Labels tematicos
        with open(labels_json, encoding="utf-8") as f:
            labels = json.load(f)
        
        assert "1" in labels
        assert "2" in labels
        assert "theme" in labels["1"]
