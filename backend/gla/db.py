"""Engine, sessions and backups."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import Base


def make_engine(settings: Settings) -> Engine:
    settings.ensure_dirs()
    engine = create_engine(settings.database_url, future=True)
    if settings.database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _pragmas(conn, _record):  # pragma: no cover - trivial
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()
    Base.metadata.create_all(engine)
    return engine


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)


def backup_database(settings: Settings, keep: int = 10) -> Path | None:
    """Copy the SQLite database before an import (NFR-4). Returns the backup path, or None if nothing to back up."""
    src = settings.sqlite_path
    if src is None or not src.exists():
        return None
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.backup_dir / f"gla-{datetime.now():%Y%m%d-%H%M%S}.sqlite"
    # use SQLite's online backup so a WAL database is copied consistently
    with sqlite3.connect(src) as s, sqlite3.connect(dest) as d:
        s.backup(d)
    backups = sorted(settings.backup_dir.glob("gla-*.sqlite"))
    for old in backups[:-keep]:
        old.unlink(missing_ok=True)
    return dest


def copy_raw(src_bytes: bytes, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(src_bytes)
        shutil.move(tmp, dest)
