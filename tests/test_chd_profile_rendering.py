from pathlib import Path
import sys

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis.chd_reinert import CHDAnalysis


def _analysis_stub() -> CHDAnalysis:
    return CHDAnalysis.__new__(CHDAnalysis)


def test_read_profiles_from_reinert_tables_coerces_infinite_chi2(tmp_path):
    analysis = _analysis_stub()
    chistable_path = tmp_path / "chistable.csv"
    contout_path = tmp_path / "Contout.csv"

    chistable_path.write_text(
        '\n'.join(
            [
                '"";"classe 1";"classe 2"',
                '"forte";Inf;-Inf',
                '"moderado";5;-5',
            ]
        ),
        encoding="utf-8",
    )
    contout_path.write_text(
        '\n'.join(
            [
                '"forte";12;0',
                '"moderado";4;1',
            ]
        ),
        encoding="utf-8",
    )

    profiles = analysis._read_profiles_from_reinert_tables(
        class_sizes={1: 12, 2: 1},
        chistable_path=chistable_path,
        contout_path=contout_path,
    )

    top_class_1 = profiles[1][0]
    top_class_2 = profiles[2][0]

    assert top_class_1[0] == "forte"
    assert top_class_2[0] == "forte"
    assert np.isfinite(top_class_1[1])
    assert np.isfinite(top_class_2[1])
    assert top_class_1[1] > 5.0
    assert top_class_2[1] < -5.0


def test_is_valid_graph_file_rejects_blank_png(tmp_path):
    blank_path = tmp_path / "blank.png"
    non_blank_path = tmp_path / "non_blank.png"

    Image.new("RGB", (64, 64), color="white").save(blank_path)
    image = Image.new("RGB", (64, 64), color="white")
    image.putpixel((32, 32), (0, 0, 0))
    image.save(non_blank_path)

    assert not CHDAnalysis._is_valid_graph_file(blank_path)
    assert CHDAnalysis._is_valid_graph_file(non_blank_path)
