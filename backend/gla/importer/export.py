"""One-time import of a Garmin account export (FR-1).

Re-running is safe: files already imported are recognised by their SHA-256 and skipped,
and activities are matched by start time and sport, so nothing is duplicated.
"""
from __future__ import annotations

import hashlib
import logging
import traceback
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db import backup_database, copy_raw
from ..fit_reader import FitActivity, NotAnActivity, read_fit
from ..geo import encode_polyline, thin_by_distance
from ..models import Activity, DailyHealth, RawFile, Setting, SyncRun, Track
from . import garmin_json
from .sources import ExportEntry, iter_export

log = logging.getLogger(__name__)
MATCH_WINDOW = timedelta(seconds=90)
COMMIT_EVERY = 50


def dedup_key(start_utc: datetime, sport: str) -> str:
    return f"{start_utc:%Y%m%dT%H%M%S}-{sport}"


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


class ExportImporter:
    def __init__(self, settings: Settings, sessions: sessionmaker[Session],
                 progress: Callable[[str], None] | None = None):
        self.settings = settings
        self.sessions = sessions
        self.progress = progress or (lambda msg: None)
        self.counts: Counter[str] = Counter()
        self.by_sport: Counter[str] = Counter()
        self.unsupported: Counter[str] = Counter()
        self.failures: list[dict] = []
        self.summaries: list[dict] = []
        self.wellness: dict = {}
        self.wellness_files: list[str] = []

    # -------------------------------------------------------------- entry point
    def run(self, path: Path) -> dict:
        backup = backup_database(self.settings)
        with self.sessions() as s:
            run = SyncRun(kind="export_import", started_at=now(), status="running")
            s.add(run)
            s.commit()
            run_id = run.id
        try:
            with self.sessions() as s:
                for i, entry in enumerate(iter_export(path), 1):
                    self._handle(s, entry)
                    if i % COMMIT_EVERY == 0:
                        s.commit()
                        self.progress(f"{i} files read, {self.counts['activities_added']} activities added")
                s.commit()
                self._apply_summaries(s)
                self._apply_wellness(s)
                self._remember_newest(s)
                s.commit()
                report = self._report(s, path, backup)
            status, error = "ok", None
        except Exception as exc:  # report the failure on the run, then re-raise
            report, status, error = None, "failed", "".join(traceback.format_exception(exc))
            raise
        finally:
            with self.sessions() as s:
                run = s.get(SyncRun, run_id)
                run.finished_at, run.status, run.error, run.report = now(), status, error, report
                s.commit()
        return report

    # -------------------------------------------------------------- per file
    def _handle(self, s: Session, e: ExportEntry) -> None:
        self.counts["files_seen"] += 1
        if e.suffix == ".fit":
            self._handle_fit(s, e)
        elif e.suffix == ".json" and garmin_json.is_summary_file(e.name):
            try:
                self.summaries.extend(garmin_json.parse_summaries(e.data))
                self.counts["summary_files"] += 1
            except Exception as exc:
                self._fail(e, exc)
        elif garmin_json.is_wellness_file(e.name):
            try:
                found = garmin_json.parse_wellness(e.data)
                if found:
                    self.wellness_files.append(e.name)
                for day, fields in found.items():
                    self.wellness.setdefault(day, {}).update(fields)
            except Exception as exc:
                self._fail(e, exc)
        else:
            self.unsupported[e.suffix or "(no extension)"] += 1

    def _fail(self, e: ExportEntry, exc: Exception) -> None:
        self.counts["files_failed"] += 1
        if len(self.failures) < 200:
            self.failures.append({"file": e.name, "error": f"{type(exc).__name__}: {exc}"})

    def _handle_fit(self, s: Session, e: ExportEntry) -> None:
        sha = hashlib.sha256(e.data).hexdigest()
        existing = s.scalar(select(RawFile).where(RawFile.sha256 == sha))
        if existing is not None:
            self.counts["fit_already_imported"] += 1
            return
        stored = self.settings.raw_dir / "fit" / sha[:2] / f"{sha}.fit"
        copy_raw(e.data, stored)
        raw = RawFile(sha256=sha, source="export", kind="fit", original_name=e.name, stored_path=str(stored),
                      size_bytes=len(e.data), received_at=now())
        s.add(raw)
        try:
            act = read_fit(e.data)
        except NotAnActivity as exc:
            raw.status, raw.note = "skipped", str(exc)
            self.counts["fit_not_activity"] += 1
            return
        except Exception as exc:
            raw.status, raw.note = "failed", f"{type(exc).__name__}: {exc}"
            self._fail(e, exc)
            return
        s.flush()
        self._upsert_from_fit(s, act, raw)

    def _upsert_from_fit(self, s: Session, f: FitActivity, raw: RawFile) -> None:
        key = dedup_key(f.start_utc, f.sport)
        a = s.scalar(select(Activity).where(Activity.dedup_key == key))
        if a is None:
            a = self._match_by_time(s, f.start_utc, f.sport)
        if a is None:
            a = Activity(dedup_key=key, sport=f.sport, start_utc=f.start_utc, source="export-fit", updated_at=now())
            s.add(a)
            self.counts["activities_added"] += 1
            self.by_sport[f.sport] += 1
        else:
            self.counts["activities_updated"] += 1
        a.source = "export-fit"
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
            out = self.settings.streams_dir / f"{a.id}.parquet"
            f.streams.to_parquet(out, index=False, compression="zstd")
            a.has_streams = True
        if a.has_gps:
            thin = thin_by_distance(pts, 50.0)
            lats, lons = [p[0] for p in pts], [p[1] for p in pts]
            track = a.track or Track(activity_id=a.id)
            track.polyline, track.points = encode_polyline(thin), len(thin)
            track.min_lat, track.max_lat, track.min_lon, track.max_lon = min(lats), max(lats), min(lons), max(lons)
            a.track = track

    def _match_by_time(self, s: Session, start: datetime, sport: str) -> Activity | None:
        cands = s.scalars(select(Activity).where(
            Activity.start_utc.between(start - MATCH_WINDOW, start + MATCH_WINDOW))).all()
        same = [c for c in cands if c.sport == sport] or cands
        return min(same, key=lambda c: abs((c.start_utc - start).total_seconds())) if same else None

    # -------------------------------------------------------------- summaries and wellness
    def _apply_summaries(self, s: Session) -> None:
        """Attach Garmin IDs and names to FIT activities; create activities that only have a summary."""
        for sm in self.summaries:
            a = None
            if sm["garmin_id"] is not None:
                a = s.scalar(select(Activity).where(Activity.garmin_id == sm["garmin_id"]))
            if a is None:
                a = self._match_by_time(s, sm["start_utc"], sm["sport"])
            if a is not None:
                if a.garmin_id is None and sm["garmin_id"] is not None:
                    a.garmin_id = sm["garmin_id"]
                a.name = a.name or sm["name"]
                if a.tz_offset_min is None:
                    a.tz_offset_min = sm["tz_offset_min"]
                self.counts["summaries_matched"] += 1
                continue
            a = Activity(dedup_key=dedup_key(sm["start_utc"], sm["sport"]), garmin_id=sm["garmin_id"],
                         sport=sm["sport"], garmin_sport=sm["garmin_sport"], name=sm["name"],
                         start_utc=sm["start_utc"], tz_offset_min=sm["tz_offset_min"], source="export-summary",
                         updated_at=now(), has_gps=False)
            for fld in ("elapsed_s", "timer_s", "distance_m", "ascent_m", "descent_m", "avg_hr", "max_hr",
                        "calories", "start_lat", "start_lon"):
                setattr(a, fld, sm[fld])
            s.add(a)
            s.flush()
            self.counts["activities_added"] += 1
            self.counts["activities_summary_only"] += 1
            self.by_sport[sm["sport"]] += 1

    def _apply_wellness(self, s: Session) -> None:
        for day, fields in self.wellness.items():
            row = s.get(DailyHealth, day)
            if row is None:
                row = DailyHealth(day=day, source="export", updated_at=now())
                s.add(row)
                self.counts["health_days_added"] += 1
            for k, v in fields.items():
                setattr(row, k, v)
            row.updated_at = now()

    def _remember_newest(self, s: Session) -> None:
        newest = s.scalar(select(Activity.start_utc).order_by(Activity.start_utc.desc()).limit(1))
        if newest is not None:
            row = s.get(Setting, "export_newest_activity_utc") or Setting(key="export_newest_activity_utc", value="")
            row.value = newest.isoformat()
            s.merge(row)

    # -------------------------------------------------------------- report
    def _report(self, s: Session, path: Path, backup: Path | None) -> dict:
        from ..report import library_summary
        return {
            "source": str(path),
            "backup": str(backup) if backup else None,
            "this_run": {**dict(self.counts), "added_by_sport": dict(self.by_sport),
                         "unsupported_by_extension": dict(self.unsupported),
                         "wellness_files_used": len(self.wellness_files)},
            "failures": self.failures,
            "library": library_summary(s),
        }
