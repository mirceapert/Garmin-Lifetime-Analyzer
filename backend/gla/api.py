"""HTTP API. Milestone 1 exposes health and the library report; views arrive in milestones 4 and 5."""
from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .config import load_settings
from .db import make_engine, session_factory
from .report import last_runs, library_summary

settings = load_settings()
sessions = session_factory(make_engine(settings))
app = FastAPI(title="Garmin Lifetime Analyzer", version=__version__)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/library")
def library() -> dict:
    with sessions() as s:
        return {"library": library_summary(s), "runs": last_runs(s)}
