"""HTTP API: library, sync, analytics for every view, and the web app itself."""
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


# ------------------------------------------------------------------ analytics (milestone 3)
from datetime import datetime as _dt  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from pydantic import BaseModel  # noqa: E402

from .analytics import queries as q  # noqa: E402
from .models import Route  # noqa: E402

FOOT_SPORTS = ["run", "trail", "walk"]


@app.get("/api/lifetime")
def get_lifetime() -> dict:
    """Odometer and totals per sport."""
    with sessions() as s:
        return q.lifetime(s)


@app.get("/api/year-over-year")
def get_yoy(sports: str = "run,trail") -> dict:
    """Cumulative distance by day of year, one series per year. `sports` is a comma-separated list."""
    with sessions() as s:
        return q.year_over_year(s, [x for x in sports.split(",") if x])


@app.get("/api/best-efforts")
def get_best_efforts() -> dict:
    with sessions() as s:
        return q.best_efforts(s)


@app.get("/api/tiles")
def get_tiles() -> dict:
    with sessions() as s:
        return q.tiles(s)


@app.get("/api/tracks")
def get_tracks() -> list[dict]:
    """Every GPS track (simplified, encoded polyline) for the heatmap."""
    with sessions() as s:
        return q.tracks(s)


@app.get("/api/routes")
def get_routes(min_efforts: int = 3) -> list[dict]:
    with sessions() as s:
        return q.routes(s, min_efforts)


@app.get("/api/routes/{route_id}")
def get_route(route_id: int) -> dict:
    with sessions() as s:
        r = q.route_detail(s, route_id)
    if r is None:
        raise HTTPException(404, "No such route")
    return r


class RouteName(BaseModel):
    name: str | None


@app.patch("/api/routes/{route_id}")
def rename_route(route_id: int, body: RouteName) -> dict:
    with sessions() as s:
        r = s.get(Route, route_id)
        if r is None:
            raise HTTPException(404, "No such route")
        r.name = (body.name or "").strip()[:80] or None
        s.commit()
        return {"id": r.id, "name": r.name}


@app.get("/api/training-load")
def get_training_load() -> dict:
    with sessions() as s:
        return q.training_load(s, _dt.now(ZoneInfo(settings.timezone)).date())


@app.get("/api/health-days")
def get_health_days() -> list[list]:
    """[day, sleep score, sleep seconds, night HRV, resting HR] per day."""
    with sessions() as s:
        return q.health_days(s)


# ------------------------------------------------------------------ milestone 5
def _today():
    return _dt.now(ZoneInfo(settings.timezone)).date()


@app.get("/api/tennis")
def get_tennis() -> dict:
    """Every tennis session with its court coverage, coverage per year, and the courts found."""
    with sessions() as s:
        return q.tennis(s)


@app.get("/api/tennis/{activity_id}")
def get_tennis_session(activity_id: int) -> dict:
    """One session: folded court grid, zones, heart rate and speed per minute, previous and next session."""
    with sessions() as s:
        r = q.tennis_session(settings, s, activity_id)
    if r is None:
        raise HTTPException(404, "No such tennis session")
    return r


@app.get("/api/snow")
def get_snow() -> dict:
    """Snowboard seasons with days on snow, runs, vertical and top speed."""
    with sessions() as s:
        return q.snow(s)


@app.get("/api/sleep")
def get_sleep() -> dict:
    """Nightly series, sleep drivers and recovery after hard sessions."""
    with sessions() as s:
        return q.sleep(s, settings.timezone, _today())


@app.get("/api/forecast")
def get_forecast() -> dict:
    """Tonight's sleep score and HRV forecast, and the starting point for the fitness planner."""
    with sessions() as s:
        return q.forecast(s, settings.timezone, _today())


# ------------------------------------------------------------------ the web app (milestone 4)
import os as _os  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402

WEB_DIR = _Path(_os.environ.get("GLA_WEB_DIR", _Path(__file__).resolve().parents[2] / "frontend" / "dist"))
if (WEB_DIR / "index.html").exists():
    # mounted last, so every /api route above wins
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
