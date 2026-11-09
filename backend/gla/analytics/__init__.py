"""Analytics over the library (milestone 3): training load, best efforts, explorer tiles, routes, totals."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings

log = logging.getLogger(__name__)


def run_analysis(settings: Settings, sessions: sessionmaker[Session], full: bool = False) -> dict:
    """Analyze in its own transaction. Raises on error; see analyze_quietly for the after-sync hook."""
    from .pipeline import analyze
    with sessions() as s:
        report = analyze(settings, s, full=full)
        s.commit()
        return report


def analyze_quietly(settings: Settings, sessions: sessionmaker[Session]) -> dict | None:
    """After an import or sync: a failure here must not undo the data that just arrived."""
    try:
        return run_analysis(settings, sessions)
    except Exception:
        log.exception("Analysis after import or sync failed; run `gla analyze` to retry")
        return None
