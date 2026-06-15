"""Fix C — robustez do plot R + detecção de AFC em branco.

Cobre (sem R):
- _is_valid_graph_file rejeita PNG em branco e aceita PNG com conteúdo;
- _raise_if_afc_plot_failed levanta erro quando afc2dl_error.txt existe e
  apenas avisa para os marcadores suplementares;
- o template R chd_reinert_profiles sanitiza chistabletot e grava marcadores.

Ver planejamentofable.md, Fase 3.
"""

import logging
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw

from src.analysis.chd_reinert import CHDAnalysis, CHDAnalysisError


class _StubCHD(CHDAnalysis):
    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self._logger = logging.getLogger("test_chd_blank_guard")


def _white_png(path, size=(200, 200)):
    Image.new("RGB", size, (255, 255, 255)).save(path)


def _content_png(path, size=(200, 200)):
    img = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "ricardo", fill=(200, 0, 0))
    draw.line((0, 0, size[0], size[1]), fill=(0, 0, 255), width=3)
    img.save(path)


def test_blank_png_is_invalid(tmp_path):
    p = tmp_path / "AFC2DL.png"
    _white_png(p)
    assert CHDAnalysis._is_valid_graph_file(p) is False


def test_content_png_is_valid(tmp_path):
    p = tmp_path / "AFC2DL.png"
    _content_png(p)
    assert CHDAnalysis._is_valid_graph_file(p) is True


def test_missing_file_is_invalid(tmp_path):
    assert CHDAnalysis._is_valid_graph_file(tmp_path / "nope.png") is False


def test_raise_when_afc2dl_error_marker_present(tmp_path):
    chd = _StubCHD(tmp_path)
    (tmp_path / "afc2dl_error.txt").write_text("could not plot terms", encoding="utf-8")
    with pytest.raises(CHDAnalysisError) as exc:
        chd._raise_if_afc_plot_failed()
    assert "AFC2DL" in (exc.value.what or "")
    assert "could not plot terms" in (exc.value.why or "")


def test_no_raise_when_no_marker(tmp_path):
    chd = _StubCHD(tmp_path)
    chd._raise_if_afc_plot_failed()  # must not raise


def test_supplementary_marker_only_warns(tmp_path, caplog):
    chd = _StubCHD(tmp_path)
    (tmp_path / "afc2dcl_error.txt").write_text("supp failed", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        chd._raise_if_afc_plot_failed()  # must not raise
    assert any("suplementar" in r.getMessage().lower() for r in caplog.records)


def test_template_sanitizes_chistabletot_and_writes_markers():
    """The generated R template must neutralize non-finite chi-square and
    persist an error marker when a PlotAfc2dCoul call fails."""
    src = (ROOT / "src" / "core" / "r_script_generator.py").read_text(encoding="utf-8")
    assert "chistabletot[!is.finite(as.matrix(chistabletot))] <- 0" in src
    assert 'writeLines(as.character(e$message), "afc2dl_error.txt")' in src
    for name in ("afc2dsl_error.txt", "afc2del_error.txt", "afc2dcl_error.txt"):
        assert name in src


def test_templates_use_product_palette_for_class_colors():
    """A paleta de classes dos gráficos R (AFC2D* e dendrograma nativo) deve ser
    a mesma ggplot_hue (Lab, C=100, L=65) usada por YAKE/LDA/heatmap — injetada
    como override de rainbow() nos scripts gerados, sem alterar Rgraph.R."""
    src = (ROOT / "src" / "core" / "r_script_generator.py").read_text(encoding="utf-8")
    assert src.count('grDevices::convertColor(lab, from = "Lab", to = "sRGB", clip = TRUE)') == 2, (
        "override de rainbow() deve existir nos templates de perfis E do CHD nativo"
    )
    # O clone validado Rgraph.R permanece intocado (regra do planejamento).
    rgraph = (ROOT / "Rscripts" / "Rgraph.R").read_text(encoding="utf-8", errors="replace")
    assert "convertColor" not in rgraph
