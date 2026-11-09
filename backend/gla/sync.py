"""Daily sync from the Garmin Personal API (FR-2, FR-3).

A run reads the activity list and daily health for a short window, downloads the FIT file of
every activity we don't have yet, and saves everything in one transaction: a run that fails
leaves the database as it was (NFR-4) and can simply be repeated.
"""
from __future__ import annotations

import json
import logging
import traceback
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .fit_reader import NotAnActivity, read_fit
from .garmin_api import GarminSource, KeyMissing, KeyRejected, fit_files_in
from .importer.garmin_json import first, to_utc, wellness_from_obj
from .ingest import find_raw, now, store_raw, upsert_fit_activity, upsert_health, upsert_summary_activity
from .models import Activity, Setting, SyncRun
from .sports import normalize_sport, regroup_activities

log = logging.getLogger(__name__)
PAGE = 100
OVERLAP_DAYS = 2          # re-read the last days: sleep and HRV for a night arrive after waking
STALE_RUN = timedelta(hours=2)
SUMMARY_CHUNK_DAYS = 28


class SyncBusy(RuntimeError):
    """Another sync is running."""


# ------------------------------------------------------------------ settings helpers

def get_setting(s: Session, key: str) -> str | None:
    row = s.get(Setting, key)
    return row.value if row else None


def set_setting(s: Session, key: str, value: str) -> None:
    row = s.get(Setting, key)
    if row is None:
        s.add(Setting(key=key, value=value))
    else:
        row.value = value


def local_today(settings: Settings) -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


# ------------------------------------------------------------------ parsing API responses

def parse_api_activity(r: dict) -> dict | None:
    """Activity list entry (Garmin Connect API units: metres, seconds, m/s)."""
    start = to_utc(first(r, "startTimeGMT", "startTimeGmt", "beginTimestamp"))
    if start is None or r.get("activityId") is None:
        return None
    atype = r.get("activityType")
    type_key = atype.get("typeKey") if isinstance(atype, dict) else atype
    local = to_utc(r.get("startTimeLocal"))
    num = lambda k: float(r[k]) if isinstance(r.get(k), (int, float)) else None  # noqa: E731
    return {
        "garmin_id": int(r["activityId"]), "name": r.get("activityName") or r.get("name"),
        "start_utc": start, "tz_offset_min": round((local - start).total_seconds() / 900) * 15 if local else None,
        "garmin_sport": type_key, "sport": normalize_sport(type_key),
        "elapsed_s": num("elapsedDuration") or num("duration"), "timer_s": num("movingDuration") or num("duration"),
        "distance_m": num("distance"), "ascent_m": num("elevationGain"), "descent_m": num("elevationLoss"),
        "avg_hr": num("averageHR"), "max_hr": num("maxHR"), "avg_speed_ms": num("averageSpeed"),
        "max_speed_ms": num("maxSpeed"), "calories": num("calories"),
        "start_lat": num("startLatitude"), "start_lon": num("startLongitude"),
    }


def find_hr_profile(obj: Any) -> dict:
    """Resting and maximum heart rate Garmin uses for zones (prefers the DEFAULT sport entry)."""
    found: list[dict] = []

    def walk(o):
        if isinstance(o, dict):
            if any(k in o for k in ("maxHeartRateUsed", "restingHeartRateUsed")):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)
    walk(obj)
    found.sort(key=lambda d: 0 if str(d.get("sport", "DEFAULT")).upper() == "DEFAULT" else 1)
    for d in found:
        mx, rest = d.get("maxHeartRateUsed"), d.get("restingHeartRateUsed")
        if isinstance(mx, (int, float)) and 120 <= mx <= 230:
            return {"hr_max": float(mx), "hr_rest": float(rest) if isinstance(rest, (int, float)) and 25 <= rest <= 100 else None}
    return {}


# ------------------------------------------------------------------ the sync

class ApiSync:
    def __init__(self, settings: Settings, sessions: sessionmaker[Session],
                 source_factory: Callable[[Settings], GarminSource] | None = None,
                 progress: Callable[[str], None] | None = None):
        self.settings = settings
        self.sessions = sessions
        self.source_factory = source_factory or _live_source
        self.progress = progress or (lambda m: None)

    # -- locking: a run row in status "running" is the lock
    def start_run(self) -> int:
        with self.sessions() as s:
            running = s.scalars(select(SyncRun).where(SyncRun.kind == "api_sync", SyncRun.status == "running")).all()
            for r in running:
                if now() - r.started_at < STALE_RUN:
                    raise SyncBusy(f"A sync started at {r.started_at:%H:%M} UTC is still running.")
                r.status, r.finished_at, r.error = "failed", now(), "Abandoned: the process stopped mid-run."
            run = SyncRun(kind="api_sync", started_at=now(), status="running")
            s.add(run)
            s.commit()
            return run.id

    def run(self, since: date | None = None, until: date | None = None) -> dict:
        return self.execute(self.start_run(), since, until)

    def execute(self, run_id: int, since: date | None = None, until: date | None = None) -> dict:
        counts: Counter[str] = Counter()
        status, error, report, source = "ok", None, None, None
        try:
            source = self.source_factory(self.settings)
            with self.sessions() as s:
                try:
                    until = until or local_today(self.settings)
                    since = since or self._default_since(s, until)
                    self.progress(f"Syncing {since} to {until}")
                    self._activities(s, source, since, until, counts)
                    self._health(s, source, since, until, counts)
                    self._hr_profile(s, source, counts)
                    set_setting(s, "api_synced_through", until.isoformat())
                    counts["activities_regrouped"] += regroup_activities(s)
                    report = {"window": [since.isoformat(), until.isoformat()], **dict(counts)}
                    s.commit()
                except Exception:
                    s.rollback()
                    raise
        except (KeyMissing, KeyRejected) as exc:
            status, error = "failed", f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            status, error = "failed", "".join(traceback.format_exception(exc))
        finally:
            with self.sessions() as s:
                run = s.get(SyncRun, run_id)
                run.finished_at, run.status, run.error, run.report = now(), status, error, report
                s.commit()
            close = getattr(source, "close", None)
            if callable(close):
                close()
        if status != "ok":
            raise SyncFailed(error)
        from .analytics import analyze_quietly
        report["analysis"] = analyze_quietly(self.settings, self.sessions)
        return report

    def _default_since(self, s: Session, until: date) -> date:
        synced = get_setting(s, "api_synced_through")
        if synced:
            return date.fromisoformat(synced) - timedelta(days=OVERLAP_DAYS)
        newest = get_setting(s, "export_newest_activity_utc")
        if newest:
            return datetime.fromisoformat(newest).date() - timedelta(days=1)
        return until - timedelta(days=self.settings.first_sync_days)

    # -- activities
    def _activities(self, s: Session, src: GarminSource, since: date, until: date, counts: Counter) -> None:
        start = 0
        while True:
            page = src.search_activities(start=start, limit=PAGE, start_date=since, end_date=until) or []
            if isinstance(page, dict):
                page = next((v for v in page.values() if isinstance(v, list)), [])
            for r in page:
                self._one_activity(s, src, r, counts)
            if len(page) < PAGE:
                break
            start += PAGE

    def _one_activity(self, s: Session, src: GarminSource, r: dict, counts: Counter) -> None:
        sm = parse_api_activity(r)
        if sm is None:
            counts["activities_unreadable"] += 1
            return
        counts["activities_listed"] += 1
        existing = s.scalar(select(Activity).where(Activity.garmin_id == sm["garmin_id"]))
        if existing is not None and (existing.raw_file_id is not None or existing.source == "api-summary"):
            counts["activities_already_had"] += 1      # have its FIT file, or already know it has none
            return
        download = src.download_activity(sm["garmin_id"])
        fits = fit_files_in(download or b"")
        for name, data in fits:
            if find_raw(s, data) is not None:
                counts["activities_already_had"] += 1
                return
            raw = store_raw(s, self.settings, data, source="api", kind="fit", name=f"{sm['garmin_id']}/{name}")
            try:
                fit = read_fit(data)
            except NotAnActivity as exc:
                raw.status, raw.note = "skipped", str(exc)
                continue
            except Exception as exc:
                raw.status, raw.note = "failed", f"{type(exc).__name__}: {exc}"
                counts["fit_failed"] += 1
                continue
            a, created = upsert_fit_activity(s, self.settings, fit, raw, source="api",
                                             garmin_id=sm["garmin_id"], name=sm["name"])
            counts["activities_added" if created else "activities_updated"] += 1
            return
        # no usable FIT file (manual entries, GPX/TCX uploads): keep the summary
        a, created = upsert_summary_activity(s, sm, source="api-summary")
        counts["activities_added_summary_only" if created else "activities_already_had"] += 1

    # -- daily health
    def _health(self, s: Session, src: GarminSource, since: date, until: date, counts: Counter) -> None:
        days: dict[date, dict] = {}

        def merge(obj, label):
            if obj is None:
                return
            self._keep_json(s, obj, label)
            for d, fields in wellness_from_obj(obj).items():
                if since <= d <= until:
                    days.setdefault(d, {}).update(fields)

        d = since
        while d <= until:
            merge(src.get_daily_sleep(d), f"sleep/{d}")
            merge(src.get_daily_hrv(d), f"hrv/{d}")
            d += timedelta(days=1)
        chunk = since
        while chunk <= until:
            end = min(until, chunk + timedelta(days=SUMMARY_CHUNK_DAYS - 1))
            merge(src.get_daily_summaries(chunk, end), f"dailysummaries/{chunk}_{end}")
            chunk = end + timedelta(days=1)
        for day, fields in days.items():
            created = upsert_health(s, day, fields, source="api")
            counts["health_days_added" if created else "health_days_updated"] += 1

    def _hr_profile(self, s: Session, src: GarminSource, counts: Counter) -> None:
        obj = src.get_heart_rate_zones()
        if obj is None:
            return
        self._keep_json(s, obj, "heart-rate-zones")
        prof = find_hr_profile(obj)
        for k, v in prof.items():
            if v is not None:
                set_setting(s, k, str(v))
                counts[f"{k}_set"] = 1

    def _keep_json(self, s: Session, obj: Any, label: str) -> None:
        data = json.dumps(obj, sort_keys=True).encode()
        if find_raw(s, data) is None:
            store_raw(s, self.settings, data, source="api", kind="json", name=label)


class SyncFailed(RuntimeError):
    pass


def _live_source(settings: Settings) -> GarminSource:
    from .garmin_api import LiveGarmin
    return LiveGarmin(settings)


# ------------------------------------------------------------------ status (FR-3)

def sync_status(settings: Settings, sessions: sessionmaker[Session]) -> dict:
    tz = ZoneInfo(settings.timezone)
    today = local_today(settings)
    with sessions() as s:
        runs = s.scalars(select(SyncRun).where(SyncRun.kind == "api_sync").order_by(SyncRun.id.desc()).limit(20)).all()
        synced_through = get_setting(s, "api_synced_through")
        hr_max, hr_rest = get_setting(s, "hr_max"), get_setting(s, "hr_rest")
    last = runs[0] if runs else None
    last_ok = next((r for r in runs if r.status == "ok"), None)
    running = last is not None and last.status == "running" and now() - last.started_at < STALE_RUN

    warnings: list[dict] = []
    key = {"configured": bool(settings.garmin_api_key),
           "expires_on": settings.garmin_api_key_expires.isoformat() if settings.garmin_api_key_expires else None,
           "days_left": None, "state": "ok"}
    if not settings.garmin_api_key:
        key["state"] = "missing"
        warnings.append({"level": "critical", "text": "No Garmin API key. Add GARMIN_API_KEY to the .env file and restart."})
    else:
        if settings.garmin_api_key_expires:
            left = (settings.garmin_api_key_expires - today).days
            key["days_left"] = left
            if left < 0:
                key["state"] = "expired"
                warnings.append({"level": "critical", "text": "Your Garmin API key has expired. Create a new key in Garmin Connect and update .env."})
            elif left <= 7:
                key["state"] = "expiring"
                warnings.append({"level": "warning", "text": f"Your Garmin API key expires in {left} day{'s' if left != 1 else ''}, on "
                                 f"{settings.garmin_api_key_expires:%d %b}. Create a new key in Garmin Connect and update .env."})
        else:
            warnings.append({"level": "info", "text": "Add GARMIN_API_KEY_EXPIRES to .env to get a reminder before the key expires."})
        if last is not None and last.status == "failed" and last.error and last.error.startswith("KeyRejected"):
            key["state"] = "rejected"
            warnings.append({"level": "critical", "text": "Garmin rejected the API key on the last sync. Create a new key and update .env."})
    if last is not None and last.status == "failed" and key["state"] != "rejected":
        warnings.append({"level": "warning", "text": f"The last sync failed at {_local(last.started_at, tz):%d %b %H:%M}: {_short(last.error)}"})

    return {
        "running": running,
        "last_run": _run_dict(last, tz),
        "last_success": _run_dict(last_ok, tz),
        "synced_through": synced_through,
        "next_scheduled_local": next_scheduled(settings).isoformat(timespec="minutes"),
        "key": key,
        "heart_rate_profile": {"max": float(hr_max) if hr_max else None, "rest": float(hr_rest) if hr_rest else None},
        "warnings": warnings,
    }


def next_scheduled(settings: Settings, at: datetime | None = None) -> datetime:
    tz = ZoneInfo(settings.timezone)
    at = at or datetime.now(tz)
    cand = datetime.combine(at.date(), settings.sync_time, tzinfo=tz)
    return cand if cand > at else cand + timedelta(days=1)


def _local(utc_naive: datetime, tz: ZoneInfo) -> datetime:
    from datetime import timezone
    return utc_naive.replace(tzinfo=timezone.utc).astimezone(tz)


def _short(error: str | None) -> str:
    if not error:
        return "unknown error"
    line = error.strip().splitlines()[-1]
    return line[:200]


def _run_dict(r: SyncRun | None, tz: ZoneInfo) -> dict | None:
    if r is None:
        return None
    return {"id": r.id, "status": r.status, "started_local": _local(r.started_at, tz).isoformat(timespec="minutes"),
            "finished_local": _local(r.finished_at, tz).isoformat(timespec="minutes") if r.finished_at else None,
            "report": r.report, "error": _short(r.error) if r.error else None}
