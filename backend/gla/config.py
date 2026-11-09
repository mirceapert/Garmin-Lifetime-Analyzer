"""Settings read from the environment (see .env.example at the repository root)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    import_dir: Path
    database_url: str

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def streams_dir(self) -> Path:
        return self.data_dir / "streams"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def sqlite_path(self) -> Path | None:
        prefix = "sqlite:///"
        if self.database_url.startswith(prefix):
            return Path(self.database_url[len(prefix):])
        return None

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.raw_dir, self.streams_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("GLA_DATA_DIR", "data")).resolve()
    import_dir = Path(os.environ.get("GLA_IMPORT_DIR", "import")).resolve()
    database_url = os.environ.get("GLA_DATABASE_URL", f"sqlite:///{data_dir / 'gla.sqlite'}")
    return Settings(data_dir=data_dir, import_dir=import_dir, database_url=database_url)
