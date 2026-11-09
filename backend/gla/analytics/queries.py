"""Read side: the numbers each view needs, as plain dicts for the API."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Activity, DailyHealth, DerivedMetric, Route, RouteMember, Tile, Track
from ..sports import SPORT_COLORS, SPORTS
from . import load as ld
from . import tiles as tl
from .best_efforts import DISTANCES
from .pipeline import hr_profile
from .routes import MIN_EFFORTS

FOOT = ("run", "trail", "walk")
EARTH_KM = 40075.0
EVEREST_M = 8849.0


def local_day(a: Activity) -> date:
    return (a.start_utc + timedelta(minutes=a.tz_offset_min or 0)).date()


def lifetime(s: Session) -> dict:
    acts = s.scalars(select(Activity)).all()
    by = {k: {"activities": 0, "distance_km": 0.0, "hours": 0.0, "ascent_m": 0.0, "descent_m": 0.0,
              "first": None, "last": None} for k in SPORTS}
    days = set()
    for a in acts:
        b = by[a.sport]
        b["activities"] += 1
        b["distance_km"] += (a.distance_m or 0) / 1000
        b["hours"] += (a.timer_s or a.elapsed_s or 0) / 3600
        b["ascent_m"] += a.ascent_m or 0
        b["descent_m"] += a.descent_m or 0
        d = local_day(a)
        days.add(d)
        b["first"] = min(b["first"], d) if b["first"] else d
        b["last"] = max(b["last"], d) if b["last"] else d
    for b in by.values():
        for k in ("distance_km", "hours"):
            b[k] = round(b[k], 1)
        b["ascent_m"], b["descent_m"] = round(b["ascent_m"]), round(b["descent_m"])
        b["first"] = b["first"].isoformat() if b["first"] else None
        b["last"] = b["last"].isoformat() if b["last"] else None
    foot_km = sum(by[k]["distance_km"] for k in FOOT)
    ascent = sum(b["ascent_m"] for k, b in by.items() if k != "snow")
    first = min((local_day(a) for a in acts), default=None)
    span_days = ((max(days) - first).days + 1) if days else 0
    return {
        "activities": len(acts),
        "first_day": first.isoformat() if first else None,
        "active_days": len(days),
        "active_share": round(len(days) / span_days, 3) if span_days else 0,
        "foot_km": round(foot_km, 1),
        "earth_share": round(foot_km / EARTH_KM, 4),
        "hours": round(sum(b["hours"] for b in by.values()), 1),
        "ascent_m": ascent,
        "everests": round(ascent / EVEREST_M, 2),
        "snow_vertical_m": by["snow"]["descent_m"],
        "by_sport": {k: v for k, v in by.items() if v["activities"]},
        "colors": SPORT_COLORS,
    }


def year_over_year(s: Session, sports: list[str]) -> dict:
    """Cumulative distance by day of year, one series per year."""
    daily: dict[int, list[float]] = defaultdict(lambda: [0.0] * 367)
    last_day = None
    for a in s.scalars(select(Activity).where(Activity.sport.in_(sports))):
        d = local_day(a)
        daily[d.year][d.timetuple().tm_yday] += (a.distance_m or 0) / 1000
        last_day = max(last_day, d) if last_day else d
    out = {}
    for y, vals in sorted(daily.items()):
        c, series = 0.0, []
        n = 366 if (date(y, 12, 31).timetuple().tm_yday == 366) else 365
        for i in range(1, n + 1):
            c += vals[i]
            series.append(round(c, 2))
        out[str(y)] = series
    return {"sports": sports, "years": out, "latest_day": last_day.isoformat() if last_day else None}


def best_efforts(s: Session) -> dict:
    rows = s.execute(select(DerivedMetric.metric, DerivedMetric.value, Activity)
                     .join(Activity, Activity.id == DerivedMetric.activity_id)
                     .where(DerivedMetric.metric.in_(list(DISTANCES)))).all()
    out = {k: {"distance_m": v, "efforts": [], "best": None} for k, v in DISTANCES.items()}
    for metric, secs, a in rows:
        e = {"activity_id": a.id, "date": local_day(a).isoformat(), "seconds": secs, "name": a.name,
             "activity_km": round((a.distance_m or 0) / 1000, 2), "sport": a.sport}
        out[metric]["efforts"].append(e)
    for v in out.values():
        v["efforts"].sort(key=lambda e: e["date"])
        v["best"] = min(v["efforts"], key=lambda e: e["seconds"]) if v["efforts"] else None
    return out


def tiles(s: Session) -> dict:
    rows = s.scalars(select(Tile)).all()
    coords = [(t.x, t.y) for t in rows]
    size, x, y = tl.largest_square(coords)
    cluster = tl.largest_cluster(coords)
    per_year: dict[str, int] = defaultdict(int)
    for t in rows:
        per_year[str(t.first_day.year)] += 1
    return {"zoom": tl.ZOOM, "tiles": [[t.x, t.y, t.first_day.isoformat(), t.visits] for t in rows],
            "max_square": {"size": size, "x": x, "y": y}, "cluster": [list(c) for c in cluster],
            "per_year": dict(sorted(per_year.items()))}


def routes(s: Session, min_efforts: int = MIN_EFFORTS) -> list[dict]:
    counts = dict(s.execute(select(RouteMember.route_id, func.count()).group_by(RouteMember.route_id)).all())
    out = []
    for r in s.scalars(select(Route)):
        n = counts.get(r.id, 0)
        if n < min_efforts:
            continue
        span = s.execute(select(func.min(Activity.start_utc), func.max(Activity.start_utc))
                         .join(RouteMember, RouteMember.activity_id == Activity.id)
                         .where(RouteMember.route_id == r.id)).one()
        out.append({"id": r.id, "name": r.name, "group": r.group, "length_km": round(r.length_m / 1000, 2),
                    "loop": r.loop, "efforts": n, "first": span[0].date().isoformat(), "last": span[1].date().isoformat(),
                    "shape": r.shape})
    out.sort(key=lambda r: -r["efforts"])
    return out


def route_detail(s: Session, route_id: int) -> dict | None:
    r = s.get(Route, route_id)
    if r is None:
        return None
    acts = s.scalars(select(Activity).join(RouteMember, RouteMember.activity_id == Activity.id)
                     .where(RouteMember.route_id == route_id).order_by(Activity.start_utc)).all()
    efforts = [{"activity_id": a.id, "date": local_day(a).isoformat(), "name": a.name, "sport": a.sport,
                "seconds": a.timer_s or a.elapsed_s, "distance_km": round((a.distance_m or 0) / 1000, 2),
                "pace_s_per_km": round((a.timer_s or a.elapsed_s) / (a.distance_m / 1000), 1) if a.distance_m else None,
                "avg_hr": a.avg_hr} for a in acts]
    return {"id": r.id, "name": r.name, "group": r.group, "length_km": round(r.length_m / 1000, 2), "loop": r.loop,
            "shape": r.shape, "efforts": efforts}


def training_load(s: Session, today: date) -> dict:
    rows = s.execute(select(Activity, DerivedMetric.value).join(DerivedMetric, DerivedMetric.activity_id == Activity.id)
                     .where(DerivedMetric.metric == "load")).all()
    per_day: dict[date, float] = defaultdict(float)
    for a, v in rows:
        per_day[local_day(a)] += v
    prof = hr_profile(s)
    if not per_day:
        return {"days": [], "hr_profile": prof}
    series = ld.daily_series(per_day, min(per_day), today)
    ff = ld.fitness_fatigue(series)
    return {"hr_profile": {"rest": prof[0], "max": prof[1]} if prof else None, "method": ld.METHOD,
            "days": [[d.isoformat(), round(r.load, 1), round(r.fitness, 1), round(r.fatigue, 1), round(r.form, 1)]
                     for d, r in ff.iterrows()]}


def tracks(s: Session) -> list[dict]:
    rows = s.execute(select(Activity.id, Activity.sport, Activity.start_utc, Activity.tz_offset_min, Track.polyline,
                            Track.min_lat, Track.min_lon, Track.max_lat, Track.max_lon, Activity.name)
                     .join(Track, Track.activity_id == Activity.id).order_by(Activity.start_utc)).all()
    return [{"id": r[0], "sport": r[1], "date": (r[2] + timedelta(minutes=r[3] or 0)).date().isoformat(),
             "polyline": r[4], "bbox": [r[5], r[6], r[7], r[8]], "name": r[9]} for r in rows]


def health_days(s: Session) -> list[list]:
    return [[d.day.isoformat(), d.sleep_score, d.sleep_s, d.hrv_night_ms, d.resting_hr]
            for d in s.scalars(select(DailyHealth).order_by(DailyHealth.day))]
