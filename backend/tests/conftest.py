from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from fake_export import build_export  # noqa: E402

from gla.config import Settings  # noqa: E402
from gla.db import make_engine, session_factory  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    return Settings(data_dir=data, import_dir=tmp_path / "import", database_url=f"sqlite:///{data / 'gla.sqlite'}")


@pytest.fixture
def sessions(settings):
    return session_factory(make_engine(settings))


@pytest.fixture
def export_zip(tmp_path: Path) -> Path:
    return build_export(tmp_path)
