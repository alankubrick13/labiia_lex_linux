"""Tests for tableau (matrix) data structure."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.tableau import Tableau, TableauError


def test_tableau_from_csv_semicolon_and_numeric_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "matrix.csv"
        path.write_text(
            "categoria;sexo;idade\n"
            "A;F;20\n"
            "B;M;30\n"
            "B;F;x\n",
            encoding="utf-8",
        )

        tableau = Tableau.from_csv(path, sep=";", header=True, rownames=False)

        assert tableau.shape == (3, 3)
        assert tableau.col_names == ["categoria", "sexo", "idade"]
        numeric = tableau.numeric_data()
        assert float(numeric["idade"].iloc[0]) == 20.0
        assert float(numeric["idade"].iloc[2]) == 0.0


def test_tableau_from_csv_autodetect_comma():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "matrix_comma.csv"
        path.write_text(
            "grupo,valor\nA,10\nB,20\n",
            encoding="utf-8",
        )

        tableau = Tableau.from_csv(path, sep=None, header=True, rownames=False)
        assert tableau.shape == (2, 2)
        assert tableau.col_names == ["grupo", "valor"]


def test_tableau_from_xlsx_and_to_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        xlsx_path = Path(tmpdir) / "matrix.xlsx"
        pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_excel(xlsx_path, index=False)

        tableau = Tableau.from_xlsx(xlsx_path, sheet=0, header=True, rownames=False)
        assert tableau.shape == (2, 2)

        out_path = Path(tmpdir) / "export.csv"
        saved = tableau.to_csv(out_path, sep=";")
        assert saved.exists()
        content = saved.read_text(encoding="utf-8")
        assert "a;b" in content


def test_tableau_missing_file_raises_friendly_error():
    with pytest.raises(TableauError):
        Tableau.from_csv("arquivo_inexistente.csv")
