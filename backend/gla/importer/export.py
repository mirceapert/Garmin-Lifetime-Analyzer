"""One-time import of a Garmin account export (FR-1).

Re-running is safe: files already imported are recognised by their SHA-256 and skipped,
and activities are matched by start time and sport, so nothing is duplicated.
"""
from __future__ import annotations

import logging
import traceback
from collections import Counter
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db import backup_database
from ..fit_reader import NotAnActivity, read_fit
from ..ingest import find_raw, now, store_raw, upsert_fit_activity, upsert_health, upsert_summary_activity
from ..models import Activity, Setting, SyncRun
from . import garmin_json
from .sources import ExportEntry, iter_export

log = logging.getLogger(__name__)
COMMIT_EVERY = 50


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
        if find_raw(s, e.data) is not None:
            self.counts["fit_already_imported"] += 1
            return
        raw = store_raw(s, self.settings, e.data, source="export", kind="fit", name=e.name)
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
        a, created = upsert_fit_activity(s, self.settings, act, raw, source="export-fit")
        if created:
            self.counts["activities_added"] += 1
            self.by_sport[a.sport] += 1
        else:
            self.counts["activities_updated"] += 1

    # -------------------------------------------------------------- summaries and wellness
    def _apply_summaries(self, s: Session) -> None:
        """Attach Garmin IDs and names to FIT activities; create activities that only have a summary."""
        for sm in self.summaries:
            a, created = upsert_summary_activity(s, sm, source="export-summary")
            if created:
                self.counts["activities_added"] += 1
                self.counts["activities_summary_only"] += 1
                self.by_sport[a.sport] += 1
            else:
                self.counts["summaries_matched"] += 1

    def _apply_wellness(self, s: Session) -> None:
        for day, fields in self.wellness.items():
            if upsert_health(s, day, fields, source="export"):
                self.counts["health_days_added"] += 1

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
