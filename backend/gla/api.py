"""HTTP API. Milestones 1 and 2: health, library report, sync status and Sync now. Views arrive in milestones 4 and 5."""
from __future__ import annotations

import threading

from fastapi import FastAPI, HTTPException

from . import __version__
from .config import load_settings
from .db import make_engine, session_factory
from .report import last_runs, library_summary
from .sync import ApiSync, SyncBusy, SyncFailed, sync_status

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


@app.get("/api/sync/status")
def get_sync_status() -> dict:
    """Last sync, next scheduled sync and API key warnings, for the header strip."""
    return sync_status(settings, sessions)


@app.post("/api/sync", status_code=202)
def sync_now() -> dict:
    """Start a sync in the background. Poll /api/sync/status to see it finish."""
    if not settings.garmin_api_key:
        raise HTTPException(400, "No Garmin API key. Add GARMIN_API_KEY to the .env file and restart.")
    sync = ApiSync(settings, sessions)
    try:
        run_id = sync.start_run()
    except SyncBusy as exc:
        raise HTTPException(409, str(exc)) from exc

    def work():
        try:
            sync.execute(run_id)
        except SyncFailed:
            pass  # recorded on the run; status shows it

    threading.Thread(target=work, name=f"sync-{run_id}", daemon=True).start()
    return {"run_id": run_id, "status": "started"}
