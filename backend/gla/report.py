"""What is in the library: used by the import report, the CLI and the API."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Activity, DailyHealth, SyncRun
from .sports import SPORTS


def library_summary(s: Session) -> dict:
    rows = s.execute(select(Activity.sport, func.count(), func.sum(Activity.distance_m), func.sum(Activity.timer_s),
                            func.min(Activity.start_utc), func.max(Activity.start_utc))
                     .group_by(Activity.sport)).all()
    by_sport = {sport: {"activities": n, "distance_km": round((dist or 0) / 1000, 1), "hours": round((secs or 0) / 3600, 1),
                        "first": first.isoformat() if first else None, "last": last.isoformat() if last else None}
                for sport, n, dist, secs, first, last in rows}
    total = sum(v["activities"] for v in by_sport.values())
    first_last = s.execute(select(func.min(Activity.start_utc), func.max(Activity.start_utc))).one()
    count = lambda *cond: s.scalar(select(func.count()).select_from(Activity).where(*cond)) or 0
    h_first, h_last, h_days = s.execute(select(func.min(DailyHealth.day), func.max(DailyHealth.day), func.count())
                                        .select_from(DailyHealth)).one()
    coverage = {}
    for col in ("sleep_score", "sleep_s", "hrv_night_ms", "resting_hr"):
        coverage[col] = s.scalar(select(func.count()).select_from(DailyHealth).where(getattr(DailyHealth, col).is_not(None))) or 0
    return {
        "activities": total,
        "first_activity_utc": first_last[0].isoformat() if first_last[0] else None,
        "last_activity_utc": first_last[1].isoformat() if first_last[1] else None,
        "with_gps": count(Activity.has_gps.is_(True)),
        "with_streams": count(Activity.has_streams.is_(True)),
        "summary_only": count(Activity.source == "export-summary"),
        "by_sport": {k: by_sport[k] for k in SPORTS if k in by_sport},
        "health": {"days": h_days, "first_day": h_first.isoformat() if h_first else None,
                   "last_day": h_last.isoformat() if h_last else None, "days_with": coverage},
    }


def last_runs(s: Session, limit: int = 5) -> list[dict]:
    runs = s.scalars(select(SyncRun).order_by(SyncRun.id.desc()).limit(limit)).all()
    return [{"id": r.id, "kind": r.kind, "status": r.status, "started_at": r.started_at.isoformat(),
             "finished_at": r.finished_at.isoformat() if r.finished_at else None,
             "error": (r.error or "").splitlines()[-1] if r.error else None} for r in runs]


SPORT_LABELS = {"run": "Running", "trail": "Trail running", "walk": "Walking", "tennis": "Tennis",
                "snow": "Snowboarding", "other": "Other"}


HEALTH_LABELS = {"sleep_score": "sleep score", "sleep_s": "sleep time", "hrv_night_ms": "night HRV", "resting_hr": "resting HR"}


def format_summary(lib: dict) -> str:
    lines = [f"Activities: {lib['activities']}  ({(lib['first_activity_utc'] or '-')[:10]} to {(lib['last_activity_utc'] or '-')[:10]})",
             f"  with GPS: {lib['with_gps']}   with per-second data: {lib['with_streams']}   summary only: {lib['summary_only']}",
             "", f"  {'Sport':<15}{'Count':>7}{'Distance':>12}{'Hours':>9}  First       Last"]
    for k, v in lib["by_sport"].items():
        lines.append(f"  {SPORT_LABELS[k]:<15}{v['activities']:>7}{v['distance_km']:>9.1f} km{v['hours']:>9.1f}  "
                     f"{(v['first'] or '')[:10]}  {(v['last'] or '')[:10]}")
    h = lib["health"]
    lines += ["", f"Daily health: {h['days']} days ({h['first_day'] or '-'} to {h['last_day'] or '-'})",
              "  days with " + ", ".join(f"{HEALTH_LABELS[k]}: {v}" for k, v in h["days_with"].items())]
    return "\n".join(lines)
