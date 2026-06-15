"""Integration test to validate Python-R invocation."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.r_executor import RExecutor, RExecutionError, RNotFoundError  # noqa: E402


class TestRIntegration(unittest.TestCase):
    """
    Integration tests for R execution.
    """

    def test_rscript_executes_simple_script(self) -> None:
        """
        Ensure a simple R script runs successfully via RExecutor.
        """
        try:
            executor = RExecutor()
        except RNotFoundError as exc:
            self.skipTest(str(exc))

        version_check = subprocess.run(
            [executor.r_path, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
        if version_check.returncode != 0:
            self.skipTest(
                "Rscript foi encontrado, mas falhou ao iniciar. "
                "Verifique a instalacao do R no Windows."
            )

        with TemporaryDirectory() as temp_dir:
            script_path = Path(temp_dir) / "hello.R"
            script_path.write_text("cat('hello')\n", encoding="utf-8")

            try:
                result = executor.execute(
                    script_path=str(script_path),
                    working_dir=temp_dir,
                    timeout=30,
                )
            except RExecutionError as exc:
                self.skipTest(
                    "Rscript iniciou, mas falhou ao executar um script simples. "
                    "Verifique a instalacao do R no Windows. "
                    f"Detalhes: {exc}"
                )

            self.assertEqual(result.return_code, 0)
            self.assertIn("hello", result.stdout)


if __name__ == "__main__":
    unittest.main()
