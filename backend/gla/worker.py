"""Background worker: runs the Garmin sync once a day at GLA_SYNC_TIME (local time), with retries."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import SyncRun
from .sync import ApiSync, SyncBusy, SyncFailed

log = logging.getLogger(__name__)
MAX_TRIES_PER_DAY = 3
RETRY_AFTER = timedelta(minutes=30)


def is_due(settings: Settings, sessions: sessionmaker[Session], at: datetime | None = None) -> bool:
    """True when today's scheduled time has passed and today's sync has neither succeeded
    nor failed MAX_TRIES_PER_DAY times (failed runs are retried every 30 minutes)."""
    if not settings.garmin_api_key:
        return False
    tz = ZoneInfo(settings.timezone)
    at = (at or datetime.now(tz)).astimezone(tz)
    scheduled = datetime.combine(at.date(), settings.sync_time, tzinfo=tz)
    if at < scheduled:
        return False
    since_utc = scheduled.astimezone(timezone.utc).replace(tzinfo=None)
    with sessions() as s:
        runs = s.scalars(select(SyncRun).where(SyncRun.kind == "api_sync", SyncRun.started_at >= since_utc)
                         .order_by(SyncRun.started_at)).all()
    if not runs:
        return True
    if any(r.status in ("ok", "running") for r in runs) or len(runs) >= MAX_TRIES_PER_DAY:
        return False
    last_start = runs[-1].started_at.replace(tzinfo=timezone.utc)
    return at - last_start >= RETRY_AFTER


def run_forever(settings: Settings, sessions: sessionmaker[Session], poll_s: int = 60) -> None:
    log.warning("Worker started: daily sync at %s (%s)", settings.sync_time.strftime("%H:%M"), settings.timezone)
    while True:
        try:
            if is_due(settings, sessions):
                report = ApiSync(settings, sessions, progress=log.warning).run()
                log.warning("Sync finished: %s", report)
        except SyncBusy as exc:
            log.warning("%s", exc)
        except SyncFailed as exc:
            log.error("Sync failed: %s", str(exc).strip().splitlines()[-1] if str(exc).strip() else exc)
        except Exception:  # keep the worker alive whatever happens
            log.exception("Unexpected error in the worker")
        time.sleep(poll_s)
