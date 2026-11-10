"""Read side: the numbers each view needs, as plain dicts for the API."""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Activity, DailyHealth, DerivedMetric, Route, RouteMember, TennisCourt, TennisSession, Tile, Track
from ..sports import SPORT_COLORS, SPORTS
from . import forecast as fc
from . import load as ld
from . import sleep as sl
from . import snow as sn
from . import tennis as tn
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


# ------------------------------------------------------------------ tennis (milestone 5)

def _metric(s: Session, ids: list[int], metric: str) -> dict[int, float]:
    if not ids:
        return {}
    return dict(s.execute(select(DerivedMetric.activity_id, DerivedMetric.value)
                          .where(DerivedMetric.metric == metric, DerivedMetric.activity_id.in_(ids))).all())


def _tennis_row(a: Activity, ts: TennisSession | None, load: float | None) -> dict:
    r = {"activity_id": a.id, "date": local_day(a).isoformat(), "start": a.start_local.strftime("%H:%M"), "name": a.name,
         "minutes": round((a.timer_s or a.elapsed_s or 0) / 60), "distance_km": round((a.distance_m or 0) / 1000, 2),
         "avg_hr": a.avg_hr, "max_hr": a.max_hr, "calories": a.calories, "load": round(load) if load else None,
         "has_gps": bool(a.has_gps), "court_id": None}
    if ts is not None:
        r.update({"court_id": ts.court_id, "play_min": round(ts.play_s / 60), "net_share": ts.net_share,
                  "mid_share": ts.mid_share, "base_share": ts.base_share, "right_share": ts.right_share,
                  "median_depth_m": ts.median_depth_m,
                  "top_speed_kmh": round(ts.top_speed_ms * 3.6, 1) if ts.top_speed_ms else None})
    return r


def _geometry() -> dict:
    return {"cell_m": tn.CELL_M, "depth_m": tn.DEPTH_M, "half_width_m": tn.HALF_W_M, "baseline_m": tn.BASELINE_M,
            "service_m": tn.SERVICE_M, "singles_half_m": tn.SINGLES_HALF_M, "doubles_half_m": tn.DOUBLES_HALF_M,
            "net_zone_m": tn.NET_ZONE_M, "base_zone_m": tn.BASE_ZONE_M}


def tennis(s: Session) -> dict:
    acts = s.scalars(select(Activity).where(Activity.sport == "tennis").order_by(Activity.start_utc)).all()
    sess = {t.activity_id: t for t in s.scalars(select(TennisSession))}
    loads = _metric(s, [a.id for a in acts], "load")
    rows = [_tennis_row(a, sess.get(a.id), loads.get(a.id)) for a in acts]
    years: dict[str, dict] = {}
    for a, r in zip(acts, rows):
        y = years.setdefault(r["date"][:4], {"sessions": 0, "with_gps": 0, "hours": 0.0, "grid": None, "play_s": 0.0,
                                             "net": 0.0, "mid": 0.0, "base": 0.0, "right": 0.0, "top_speed_kmh": None})
        y["sessions"] += 1
        y["hours"] += r["minutes"] / 60
        t = sess.get(a.id)
        if t is None:
            continue
        y["with_gps"] += 1
        g = t.grid
        y["grid"] = g if y["grid"] is None else [[p + q for p, q in zip(r1, r2)] for r1, r2 in zip(y["grid"], g)]
        y["play_s"] += t.play_s
        for k, v in (("net", t.net_share), ("mid", t.mid_share), ("base", t.base_share), ("right", t.right_share)):
            y[k] += v * t.play_s
        if r.get("top_speed_kmh"):
            y["top_speed_kmh"] = max(y["top_speed_kmh"] or 0, r["top_speed_kmh"])
    for y in years.values():
        w = y.pop("play_s") or 1
        for k in ("net", "mid", "base", "right"):
            v = y.pop(k)
            y[f"{k}_share"] = round(v / w, 3) if y["with_gps"] else None
        y["hours"] = round(y["hours"], 1)
        if y["grid"] is not None:
            y["grid"] = [[round(v, 1) for v in row] for row in y["grid"]]
    courts = [{"id": c.id, "lat": c.lat, "lon": c.lon, "angle_deg": c.angle_deg, "sessions": c.sessions}
              for c in s.scalars(select(TennisCourt))]
    return {"sessions": rows, "years": dict(sorted(years.items())), "courts": courts, "geometry": _geometry()}


def tennis_session(settings, s: Session, activity_id: int) -> dict | None:
    a = s.get(Activity, activity_id)
    if a is None or a.sport != "tennis":
        return None
    t = s.get(TennisSession, activity_id)
    load = _metric(s, [a.id], "load").get(a.id)
    out = _tennis_row(a, t, load)
    out["grid"] = t.grid if t else None
    out["geometry"] = _geometry()
    out["court"] = None
    if t:
        c = s.get(TennisCourt, t.court_id)
        out["court"] = {"id": c.id, "lat": c.lat, "lon": c.lon, "angle_deg": c.angle_deg, "sessions": c.sessions}
    out["per_minute"] = []
    path = settings.streams_dir / f"{a.id}.parquet"
    if a.has_streams and path.exists():
        import pandas as pd
        out["per_minute"] = tn.per_minute(pd.read_parquet(path))
    ids = [r for r in s.scalars(select(Activity.id).where(Activity.sport == "tennis").order_by(Activity.start_utc))]
    i = ids.index(a.id)
    out["prev_id"] = ids[i - 1] if i > 0 else None
    out["next_id"] = ids[i + 1] if i + 1 < len(ids) else None
    out["number"], out["of"] = i + 1, len(ids)
    return out


# ------------------------------------------------------------------ snowboard (milestone 5)

def snow(s: Session) -> dict:
    acts = s.scalars(select(Activity).where(Activity.sport == "snow").order_by(Activity.start_utc)).all()
    ids = [a.id for a in acts]
    top, runs = _metric(s, ids, "snow_top_speed"), _metric(s, ids, "snow_runs")
    rows = [{"activity_id": a.id, "day": local_day(a), "name": a.name, "distance_m": a.distance_m,
             "descent_m": a.descent_m, "hours": (a.elapsed_s or a.timer_s or 0) / 3600,   # lifts included
             "top_speed_ms": top.get(a.id), "runs": int(runs[a.id]) if a.id in runs else None} for a in acts]
    return sn.seasons(rows)


# ------------------------------------------------------------------ sleep, recovery, forecasts (milestone 5)

def sleep(s: Session, tz: str, today: date) -> dict:
    df = sl.day_frame(s, tz, today)
    if df.empty:
        return {"series": [], "drivers": {}, "recovery": {"metrics": {}}}
    return {"series": sl.daily_series(df), "drivers": sl.drivers(sl.nights(df)),
            "recovery": sl.recovery(df, sl.activity_loads(s)), "min_nights": sl.MIN_NIGHTS,
            "min_sessions_year": sl.MIN_SESSIONS_YEAR}


def forecast(s: Session, tz: str, today: date) -> dict:
    df = sl.day_frame(s, tz, today)
    if df.empty:
        return {"tonight": {}, "plan": {"ready": False}}
    return {"tonight": {k: fc.tonight(df, k, today) for k in fc.TARGETS}, "plan": fc.load_plan(df, today)}


# ------------------------------------------------------------------ home (front page)

def home(s: Session, tz: str, today: date) -> dict:
    """One number per view for the Home tab. Everything here is also on the view it links to."""
    from . import review as rv
    life = lifetime(s)
    if not life["activities"]:
        return {"empty": True, "health_days": s.scalar(select(func.count()).select_from(DailyHealth)) or 0}
    life.pop("colors", None)
    out: dict = {"empty": False, "lifetime": {k: life[k] for k in ("activities", "first_day", "active_days", "foot_km",
                                                                  "earth_share", "hours", "ascent_m")}}
    out["health_days"] = s.scalar(select(func.count()).select_from(DailyHealth)) or 0
    t = tiles(s)
    out["tiles"] = {"visited": len(t["tiles"]), "largest_square": t["max_square"]["size"]}
    out["routes"] = len(routes(s))
    be = best_efforts(s)
    # the longest distance you have a best for is the headline
    best = next((dict(v["best"], distance=k) for k in reversed(list(DISTANCES)) if (v := be.get(k)) and v.get("best")), None)
    out["best_effort"] = best
    tn_rows = s.scalars(select(Activity).where(Activity.sport == "tennis")).all()
    with_court = s.scalar(select(func.count()).select_from(TennisSession)) or 0
    out["tennis"] = {"sessions": len(tn_rows), "hours": round(sum((a.timer_s or a.elapsed_s or 0) for a in tn_rows) / 3600, 1),
                     "with_court": with_court} if tn_rows else None
    sn_tot = snow(s)["totals"]
    out["snow"] = sn_tot if sn_tot["days_on_snow"] else None
    df = sl.day_frame(s, tz, today)
    rec = sl.recovery(df, sl.activity_loads(s)) if not df.empty else {"metrics": {}}
    hrv = rec["metrics"].get("hrv", {}).get("overall") if rec.get("metrics") else None
    rhr = rec["metrics"].get("rhr", {}).get("overall") if rec.get("metrics") else None
    pick = hrv if hrv and hrv.get("sessions") else rhr
    out["recovery"] = {"metric": "hrv" if pick is hrv else "rhr", "back_by": pick.get("back_by"), "sessions": pick["sessions"],
                       "night1": pick["nights"][0]["mean"] if pick["nights"] and pick["nights"][0] else None} if pick and pick.get("sessions") else None
    out["tonight"] = {k: {kk: v.get(kk) for kk in ("ready", "label", "unit", "prediction", "band", "night_of")}
                      for k, v in ((k, fc.tonight(df, k, today)) for k in fc.TARGETS)} if not df.empty else {}
    plan = fc.load_plan(df, today) if not df.empty else {"ready": False}
    out["fitness"] = {k: plan.get(k) for k in ("fitness", "fatigue", "form", "peak_fitness")} if plan.get("ready") else None
    years = rv.available_years(s)
    y = rv.default_year(years, today)
    if y is not None:
        acts = [a for a in s.scalars(select(Activity)) if local_day(a).year == y]
        tot = rv._totals(acts)
        out["year"] = {"year": y, "hours": tot["hours"], "active_days": tot["active_days"], "activities": tot["activities"]}
    latest = s.scalars(select(Activity).order_by(Activity.start_utc.desc()).limit(5)).all()
    ids = [a.id for a in latest]
    sess = {x.activity_id: x for x in s.scalars(select(TennisSession).where(TennisSession.activity_id.in_(ids)))}
    best_ids = {}
    for k, v in be.items():
        if v.get("best"):
            best_ids.setdefault(v["best"]["activity_id"], []).append(k)
    out["latest"] = [{"activity_id": a.id, "date": local_day(a).isoformat(), "sport": a.sport, "name": a.name,
                      "distance_km": round((a.distance_m or 0) / 1000, 2), "seconds": a.timer_s or a.elapsed_s,
                      "has_gps": bool(a.has_gps), "base_share": sess[a.id].base_share if a.id in sess else None,
                      "best_ever": best_ids.get(a.id, [])} for a in latest]
    return out
