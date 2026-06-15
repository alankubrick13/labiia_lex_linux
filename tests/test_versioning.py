from pathlib import Path

from src.core.version import APP_VERSION


def test_app_version_matches_version_file() -> None:
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    assert version_file.exists()
    assert APP_VERSION == version_file.read_text(encoding="utf-8").strip()

