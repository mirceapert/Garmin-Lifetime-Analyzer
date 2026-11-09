"""Settings read from the environment (see .env.example at the repository root)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, time
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    import_dir: Path
    database_url: str
    garmin_api_key: str | None = None
    garmin_api_key_expires: date | None = None   # the expiry date shown in Garmin Connect, typed by you
    timezone: str = "UTC"                        # for the daily sync time and local dates
    sync_time: time = time(6, 30)                # daily sync, local time
    first_sync_days: int = 30                    # how far back the first API sync goes when no export was imported

    @property
    def token_cache(self) -> Path:
        return self.data_dir / ".garmin-token.json"

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
    expires = os.environ.get("GARMIN_API_KEY_EXPIRES", "").strip()
    sync_time = os.environ.get("GLA_SYNC_TIME", "06:30").strip()
    hh, mm = (int(x) for x in sync_time.split(":"))
    return Settings(
        data_dir=data_dir, import_dir=import_dir, database_url=database_url,
        garmin_api_key=os.environ.get("GARMIN_API_KEY", "").strip() or None,
        garmin_api_key_expires=date.fromisoformat(expires) if expires else None,
        timezone=os.environ.get("TZ", "UTC").strip() or "UTC",
        sync_time=time(hh, mm),
        first_sync_days=int(os.environ.get("GLA_FIRST_SYNC_DAYS", "30")),
    )
