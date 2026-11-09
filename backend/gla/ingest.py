"""Storing what Garmin sends us, shared by the export importer and the API sync."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .db import copy_raw
from .fit_reader import FitActivity
from .geo import encode_polyline, thin_by_distance
from .models import Activity, DailyHealth, RawFile, Track
from .text import fix_text

MATCH_WINDOW = timedelta(seconds=90)
SUMMARY_FIELDS = ("elapsed_s", "timer_s", "distance_m", "ascent_m", "descent_m", "avg_hr", "max_hr",
                  "avg_speed_ms", "max_speed_ms", "calories", "start_lat", "start_lon")


def now() -> datetime:
    """Naive UTC, to the second. All stored times are UTC."""
    return datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)


def dedup_key(start_utc: datetime, sport: str) -> str:
    return f"{start_utc:%Y%m%dT%H%M%S}-{sport}"


def find_raw(s: Session, data: bytes) -> RawFile | None:
    return s.scalar(select(RawFile).where(RawFile.sha256 == hashlib.sha256(data).hexdigest()))


def store_raw(s: Session, settings: Settings, data: bytes, *, source: str, kind: str, name: str) -> RawFile:
    """Keep the file unchanged on disk, named by its checksum, and record it. Caller checks find_raw first."""
    sha = hashlib.sha256(data).hexdigest()
    stored = settings.raw_dir / kind / sha[:2] / f"{sha}.{kind}"
    copy_raw(data, stored)
    raw = RawFile(sha256=sha, source=source, kind=kind, original_name=name, stored_path=str(stored),
                  size_bytes=len(data), received_at=now())
    s.add(raw)
    s.flush()
    return raw


def match_by_time(s: Session, start: datetime, sport: str) -> Activity | None:
    cands = s.scalars(select(Activity).where(Activity.start_utc.between(start - MATCH_WINDOW, start + MATCH_WINDOW))).all()
    same = [c for c in cands if c.sport == sport] or cands
    return min(same, key=lambda c: abs((c.start_utc - start).total_seconds())) if same else None


def find_activity(s: Session, *, garmin_id: int | None, start: datetime, sport: str) -> Activity | None:
    if garmin_id is not None:
        a = s.scalar(select(Activity).where(Activity.garmin_id == garmin_id))
        if a is not None:
            return a
    a = s.scalar(select(Activity).where(Activity.dedup_key == dedup_key(start, sport)))
    return a or match_by_time(s, start, sport)


def upsert_fit_activity(s: Session, settings: Settings, f: FitActivity, raw: RawFile, *, source: str,
                        garmin_id: int | None = None, name: str | None = None) -> tuple[Activity, bool]:
    """Create or update the activity a FIT file describes. Returns (activity, created)."""
    a = find_activity(s, garmin_id=garmin_id, start=f.start_utc, sport=f.sport)
    created = a is None
    if created:
        a = Activity(dedup_key=dedup_key(f.start_utc, f.sport), sport=f.sport, start_utc=f.start_utc,
                     source=source, updated_at=now())
        s.add(a)
    a.source = source
    if garmin_id is not None and a.garmin_id is None:
        a.garmin_id = garmin_id
    a.name = a.name or fix_text(name)
    a.garmin_sport, a.garmin_sub_sport = f.garmin_sport, f.garmin_sub_sport
    a.tz_offset_min = f.tz_offset_min if f.tz_offset_min is not None else a.tz_offset_min
    for fld in ("elapsed_s", "timer_s", "distance_m", "ascent_m", "descent_m", "avg_hr", "max_hr",
                "avg_speed_ms", "max_speed_ms", "calories"):
        setattr(a, fld, getattr(f, fld))
    a.raw_file_id = raw.id
    a.updated_at = now()
    pts = f.gps_points
    a.has_gps = len(pts) > 1
    if a.has_gps:
        a.start_lat, a.start_lon = pts[0]
    s.flush()
    if len(f.streams):
        f.streams.to_parquet(settings.streams_dir / f"{a.id}.parquet", index=False, compression="zstd")
        a.has_streams = True
    if a.has_gps:
        thin = thin_by_distance(pts, 50.0)
        lats, lons = [p[0] for p in pts], [p[1] for p in pts]
        track = a.track or Track(activity_id=a.id)
        track.polyline, track.points = encode_polyline(thin), len(thin)
        track.min_lat, track.max_lat, track.min_lon, track.max_lon = min(lats), max(lats), min(lons), max(lons)
        a.track = track
    return a, created


def upsert_summary_activity(s: Session, sm: dict, *, source: str) -> tuple[Activity, bool]:
    """Activity known only from a summary (no FIT file). Never overwrites an activity that has a FIT file."""
    a = find_activity(s, garmin_id=sm.get("garmin_id"), start=sm["start_utc"], sport=sm["sport"])
    if a is not None:
        if a.garmin_id is None and sm.get("garmin_id") is not None:
            a.garmin_id = sm["garmin_id"]
        a.name = a.name or fix_text(sm.get("name"))
        if a.tz_offset_min is None:
            a.tz_offset_min = sm.get("tz_offset_min")
        return a, False
    a = Activity(dedup_key=dedup_key(sm["start_utc"], sm["sport"]), garmin_id=sm.get("garmin_id"), sport=sm["sport"],
                 garmin_sport=sm.get("garmin_sport"), name=fix_text(sm.get("name")), start_utc=sm["start_utc"],
                 tz_offset_min=sm.get("tz_offset_min"), source=source, updated_at=now(), has_gps=False)
    for fld in SUMMARY_FIELDS:
        if sm.get(fld) is not None:
            setattr(a, fld, sm[fld])
    s.add(a)
    s.flush()
    return a, True


def upsert_health(s: Session, day: date, fields: dict, *, source: str) -> bool:
    """Merge one day's health fields. Returns True if the day is new."""
    row = s.get(DailyHealth, day)
    created = row is None
    if created:
        row = DailyHealth(day=day, source=source, updated_at=now())
        s.add(row)
    for k, v in fields.items():
        setattr(row, k, v)
    row.source = source if created else row.source
    row.updated_at = now()
    return created
