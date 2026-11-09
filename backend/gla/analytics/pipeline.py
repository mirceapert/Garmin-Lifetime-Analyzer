"""Run the analytics over the library: after every import and sync, or in full with `gla analyze --full`.

Each step only writes derived tables, so it can be re-run at any time without touching your raw data.
"""
from __future__ import annotations

import logging
import statistics
from collections import Counter
from datetime import datetime

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..geo import decode_polyline, encode_polyline
from ..ingest import now
from ..text import fix_text
from ..models import Activity, DailyHealth, DerivedMetric, Route, RouteMember, Setting, Tile, Track
from . import best_efforts as be
from . import load as ld
from . import routes as rt
from . import tiles as tl

log = logging.getLogger(__name__)
ANALYSIS_VERSION = f"{ld.METHOD}+{be.METHOD}"
BEST_EFFORT_SPORTS = ("run", "trail")
NO_TILE_SPORTS = ("tennis",)          # a court is not exploring


def hr_profile(s: Session) -> tuple[float, float] | None:
    """Resting and maximum heart rate from Garmin (synced), else estimated from your own data."""
    get = lambda k: s.get(Setting, k)  # noqa: E731
    rest = float(get("hr_rest").value) if get("hr_rest") else None
    mx = float(get("hr_max").value) if get("hr_max") else None
    if rest is None:
        vals = s.scalars(select(DailyHealth.resting_hr).where(DailyHealth.resting_hr.is_not(None))).all()
        rest = statistics.median(vals) if vals else None
    if mx is None:
        mx = s.scalar(select(func.max(Activity.max_hr)))
        mx = min(mx, 220) if mx else None
    if rest is None or mx is None or mx - rest < 40:
        return None
    return rest, mx


def analyze(settings: Settings, s: Session, full: bool = False) -> dict:
    counts: Counter[str] = Counter()
    for a in s.scalars(select(Activity)):
        fixed = fix_text(a.name)
        if fixed != a.name:
            a.name = fixed
            counts["names_fixed"] += 1
    _activity_metrics(settings, s, full, counts)
    _routes(s, full, counts)
    _tiles(s, counts)
    s.flush()
    return dict(counts)


# ------------------------------------------------------------------ per-activity metrics

def _activity_metrics(settings: Settings, s: Session, full: bool, counts: Counter) -> None:
    prof = hr_profile(s)
    done = set() if full else set(s.scalars(select(DerivedMetric.activity_id).where(
        DerivedMetric.metric == "analyzed", DerivedMetric.method == ANALYSIS_VERSION)))
    for a in s.scalars(select(Activity).order_by(Activity.start_utc)):
        if a.id in done:
            continue
        s.execute(delete(DerivedMetric).where(DerivedMetric.activity_id == a.id))
        streams = None
        if a.has_streams:
            path = settings.streams_dir / f"{a.id}.parquet"
            if path.exists():
                streams = pd.read_parquet(path)
        metrics: dict[str, tuple[float, str]] = {"analyzed": (1.0, ANALYSIS_VERSION)}
        if prof:
            rest, mx = prof
            load = None
            if streams is not None and "heart_rate" in streams:
                load = ld.trimp_from_stream(streams["t_s"].to_numpy(float), streams["heart_rate"].to_numpy(float), rest, mx)
            if load is None and a.avg_hr and (a.timer_s or a.elapsed_s):
                load = ld.trimp_from_average(a.timer_s or a.elapsed_s, a.avg_hr, rest, mx)
            if load is not None:
                metrics["load"] = (round(load, 1), ld.METHOD)
        if a.sport in BEST_EFFORT_SPORTS and a.has_gps and streams is not None:
            # GPS only: treadmill distance comes from wrist motion and makes impossible records
            for k, v in be.best_efforts(streams).items():
                metrics[k] = (v, be.METHOD)
        for k, (v, method) in metrics.items():
            s.add(DerivedMetric(activity_id=a.id, metric=k, value=v, method=method))
        counts["activities_analyzed"] += 1


# ------------------------------------------------------------------ routes

def _routes(s: Session, full: bool, counts: Counter) -> None:
    if full:
        s.execute(delete(RouteMember))
    known = {m for m in s.scalars(select(RouteMember.activity_id))}
    routes = list(s.scalars(select(Route)))
    cache = {r.id: ([tuple(p) for p in r.signature], r.length_m) for r in routes}
    rows = s.execute(select(Activity, Track).join(Track, Track.activity_id == Activity.id)
                     .where(Activity.sport.in_(list(rt.ROUTE_GROUPS))).order_by(Activity.start_utc)).all()
    for a, t in rows:
        if a.id in known:
            continue
        pts = decode_polyline(t.polyline)
        if len(pts) < 5:
            continue
        sig, length = rt.signature(pts)
        if length < 500:
            continue
        group = rt.ROUTE_GROUPS[a.sport]
        best = None
        for r in routes:
            if r.group != group:
                continue
            d = rt.match_distance(*cache[r.id], sig, length)
            if d is not None and (best is None or d < best[0]):
                best = (d, r)
        if best is None:
            r = Route(group=group, length_m=round(length), loop=rt.is_loop(pts, length),
                      signature=[[round(p[0], 6), round(p[1], 6)] for p in sig], shape=t.polyline, created_at=now())
            s.add(r)
            s.flush()
            routes.append(r)
            cache[r.id] = (sig, length)
            s.add(RouteMember(activity_id=a.id, route_id=r.id, match_m=0.0))
            counts["routes_created"] += 1
        else:
            s.add(RouteMember(activity_id=a.id, route_id=best[1].id, match_m=round(best[0], 1)))
        counts["route_members_added"] += 1
    s.flush()
    # a route nobody belongs to any more (after --full) goes, unless you named it
    used = set(s.scalars(select(RouteMember.route_id)))
    for r in routes:
        if r.id not in used and not r.name:
            s.delete(r)


# ------------------------------------------------------------------ tiles

def _tiles(s: Session, counts: Counter) -> None:
    first: dict[tuple[int, int], tuple] = {}
    visits: Counter = Counter()
    rows = s.execute(select(Activity.id, Activity.start_utc, Activity.tz_offset_min, Track.polyline)
                     .join(Track, Track.activity_id == Activity.id)
                     .where(Activity.sport.not_in(NO_TILE_SPORTS)).order_by(Activity.start_utc)).all()
    for aid, start, tz, poly in rows:
        day = (start + pd.Timedelta(minutes=tz or 0)).date()
        for t in tl.tiles_on_track(decode_polyline(poly)):
            visits[t] += 1
            if t not in first:
                first[t] = (day, aid)
    s.execute(delete(Tile))
    for (x, y), (day, aid) in first.items():
        s.add(Tile(x=x, y=y, first_day=day, first_activity_id=aid, visits=visits[(x, y)]))
    counts["tiles"] = len(first)
