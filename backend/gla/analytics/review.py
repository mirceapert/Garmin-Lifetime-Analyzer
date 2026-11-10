"""Year in Review: one year of your history on one page.

Nothing new is measured here. Every number comes from the tables the other views use, cut to one
calendar year (local dates). Places come from the activity names Garmin gives ("Timisoara Running",
"Brus Resort Skiing/Snowboarding"): the sport words are taken off and what is left is the place.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, DailyHealth, DerivedMetric, Route, RouteMember, TennisSession, Tile
from ..sports import SPORTS
from . import load as ld
from .best_efforts import DISTANCES
from .routes import MIN_EFFORTS

# activity words Garmin puts after the place, in English and Romanian (longest first)
_SPORT_WORDS = sorted([
    "skiing/snowboarding", "snowboarding", "snowboard", "skiing", "resort", "trail running", "treadmill running",
    "running", "walking", "hiking", "cycling", "indoor cycling", "tennis", "table tennis", "sailing", "kayaking",
    "volleyball", "padel", "strength", "cardio", "swimming", "pool swim", "open water swim", "marathon",
    "repriză de mers pe jos", "mers pe jos", "alergare pe bandă", "alergare", "ciclism de interior", "ciclism",
    "înot în bazin", "înot", "drumeție", "navigație", "relaxare şi concentrare", "urcare etaje", "yoga",
], key=len, reverse=True)
_NOT_PLACES = {"base", "tempo", "threshold", "anaerobic", "benchmark run", "intervals", "recovery", "long run"}


def fold(text: str) -> str:
    """Lower case without diacritics, so "Timişoara" and "Timisoara" are one place."""
    t = unicodedata.normalize("NFKD", text.replace("ş", "s").replace("ţ", "t").replace("Ş", "S").replace("Ţ", "T"))
    return "".join(c for c in t if not unicodedata.combining(c)).lower().strip()


def place_of(name: str | None) -> str | None:
    """The place in a Garmin activity name: the words before the first activity word.
    None when the name has no place in it ("Tennis", "Treadmill Running")."""
    if not name:
        return None
    words = name.split(" - ")[0].split()                   # "Timisoara - Base" -> "Timisoara"
    folded = [fold(w) for w in words]
    phrases = [fold(w).split() for w in _SPORT_WORDS]
    cut = len(words)
    for i in range(len(words)):
        if any(folded[i:i + len(p)] == p for p in phrases):
            cut = i
            break
    kept = [w for w in words[:cut] if not re.match(r"^[\d.x/]+$", w)]
    n = " ".join(kept).strip(" -")
    if not n or fold(n) in _NOT_PLACES:
        return None
    return n


def _local_day(a: Activity) -> date:
    return (a.start_utc + timedelta(minutes=a.tz_offset_min or 0)).date()


def _hours(a: Activity) -> float:
    return (a.timer_s or a.elapsed_s or 0) / 3600


def _act(a: Activity, extra: dict | None = None) -> dict:
    return {"activity_id": a.id, "date": _local_day(a).isoformat(), "sport": a.sport, "name": a.name,
            "distance_km": round((a.distance_m or 0) / 1000, 2), "hours": round(_hours(a), 2), **(extra or {})}


def _totals(acts: list[Activity]) -> dict:
    days = {_local_day(a) for a in acts}
    streak = best = 0
    prev = None
    for d in sorted(days):
        streak = streak + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, streak)
        prev = d
    by: dict[str, dict] = {}
    for a in acts:
        b = by.setdefault(a.sport, {"sport": a.sport, "activities": 0, "distance_km": 0.0, "hours": 0.0})
        b["activities"] += 1
        b["distance_km"] += (a.distance_m or 0) / 1000
        b["hours"] += _hours(a)
    for b in by.values():
        b["distance_km"], b["hours"] = round(b["distance_km"], 1), round(b["hours"], 1)
    return {
        "activities": len(acts), "active_days": len(days), "longest_streak": best,
        "distance_km": round(sum((a.distance_m or 0) for a in acts) / 1000, 1),
        "foot_km": round(sum((a.distance_m or 0) for a in acts if a.sport in ("run", "trail", "walk")) / 1000, 1),
        "hours": round(sum(_hours(a) for a in acts), 1),
        "ascent_m": round(sum((a.ascent_m or 0) for a in acts if a.sport != "snow")),
        "by_sport": sorted(by.values(), key=lambda b: -b["hours"]),
    }


def available_years(s: Session) -> list[int]:
    return sorted({_local_day(a).year for a in s.scalars(select(Activity))})


def default_year(years: list[int], today: date) -> int | None:
    """The latest full year, or the current one when it is all there is."""
    full = [y for y in years if y < today.year]
    return full[-1] if full else (years[-1] if years else None)


def year_review(s: Session, year: int, today: date) -> dict:
    all_acts = s.scalars(select(Activity).order_by(Activity.start_utc)).all()
    acts = [a for a in all_acts if _local_day(a).year == year]
    prev = [a for a in all_acts if _local_day(a).year == year - 1]
    years = sorted({_local_day(a).year for a in all_acts})
    out: dict = {"year": year, "years": years, "partial": year == today.year,
                 "through": (min(today, date(year, 12, 31))).isoformat()}
    out["totals"] = _totals(acts)
    out["previous"] = _totals(prev) if prev else None
    if not acts:
        return out
    out["first"] = _act(acts[0])
    out["last"] = _act(acts[-1])

    # months: hours and distance per sport
    months = [{"month": m, "hours": {}, "distance_km": {}, "activities": 0} for m in range(1, 13)]
    for a in acts:
        m = months[_local_day(a).month - 1]
        m["hours"][a.sport] = round(m["hours"].get(a.sport, 0) + _hours(a), 2)
        m["distance_km"][a.sport] = round(m["distance_km"].get(a.sport, 0) + (a.distance_m or 0) / 1000, 2)
        m["activities"] += 1
    out["months"] = months

    # biggest day and week (by time moving), longest activities
    per_day: dict[date, list[Activity]] = defaultdict(list)
    for a in acts:
        per_day[_local_day(a)].append(a)
    day, day_acts = max(per_day.items(), key=lambda kv: sum(_hours(a) for a in kv[1]))
    out["biggest_day"] = {"date": day.isoformat(), "hours": round(sum(_hours(a) for a in day_acts), 2),
                          "distance_km": round(sum((a.distance_m or 0) for a in day_acts) / 1000, 1),
                          "activities": [_act(a) for a in day_acts]}
    weeks: dict[date, list[Activity]] = defaultdict(list)
    for a in acts:
        d = _local_day(a)
        weeks[d - timedelta(days=d.weekday())].append(a)
    wk, wk_acts = max(weeks.items(), key=lambda kv: sum(_hours(a) for a in kv[1]))
    out["biggest_week"] = {"monday": wk.isoformat(), "hours": round(sum(_hours(a) for a in wk_acts), 1),
                           "distance_km": round(sum((a.distance_m or 0) for a in wk_acts) / 1000, 1),
                           "activities": len(wk_acts), "sports": sorted({a.sport for a in wk_acts})}
    longest = {}
    for sp in SPORTS:
        cand = [a for a in acts if a.sport == sp and a.distance_m]
        if cand and sp != "other":
            longest[sp] = _act(max(cand, key=lambda a: a.distance_m))
    out["longest"] = longest

    out["records"] = _records(s, year)
    out["places"] = _places(all_acts, year)
    out["tiles"] = _tiles(s, year)
    out["routes"] = _routes(s, year)
    out["tennis"] = _tennis(s, acts)
    out["snow"] = _snow(s, acts)
    out["sleep"] = _sleep(s, year)
    out["fitness"] = _fitness(s, all_acts, year, today)
    return out


def _records(s: Session, year: int) -> list[dict]:
    """Per distance: the year's best, and every time that year you beat your best so far."""
    rows = s.execute(select(DerivedMetric.metric, DerivedMetric.value, Activity)
                     .join(Activity, Activity.id == DerivedMetric.activity_id)
                     .where(DerivedMetric.metric.in_(list(DISTANCES)))).all()
    out = []
    for key in DISTANCES:
        efforts = sorted(((_local_day(a), v, a) for m, v, a in rows if m == key), key=lambda e: (e[0], e[1]))
        if not efforts:
            continue
        best_so_far, prs, year_best = None, [], None
        for d, secs, a in efforts:
            if d.year == year and (year_best is None or secs < year_best[1]):
                year_best = (d, secs, a)
            if best_so_far is None or secs < best_so_far:
                if d.year == year:
                    prs.append({"date": d.isoformat(), "seconds": round(secs, 1), "activity_id": a.id, "name": a.name,
                                "improved_by": round(best_so_far - secs, 1) if best_so_far else None})
                best_so_far = secs
        all_time = min(v for _, v, _ in efforts)
        if year_best is None:
            continue
        out.append({"distance": key, "distance_m": DISTANCES[key], "seconds": round(year_best[1], 1),
                    "date": year_best[0].isoformat(), "activity_id": year_best[2].id, "name": year_best[2].name,
                    "all_time": bool(abs(year_best[1] - all_time) < 0.05), "personal_bests": prs})
    return out


def _places(all_acts: list[Activity], year: int) -> dict:
    labels: dict[str, Counter] = defaultdict(Counter)
    count: Counter = Counter()
    first_year: dict[str, int] = {}
    for a in all_acts:
        p = place_of(a.name)
        if not p:
            continue
        k = fold(p)
        y = _local_day(a).year
        first_year[k] = min(first_year.get(k, y), y)
        if y == year:
            count[k] += 1
            labels[k][p] += 1
    top = [{"place": labels[k].most_common(1)[0][0], "activities": n, "new": first_year[k] == year}
           for k, n in count.most_common()]
    return {"count": len(top), "new": sum(1 for p in top if p["new"]), "top": top[:8],
            "new_places": [p["place"] for p in top if p["new"]][:12]}


def _tiles(s: Session, year: int) -> dict:
    rows = s.scalars(select(Tile)).all()
    new = sum(1 for t in rows if t.first_day.year == year)
    total = sum(1 for t in rows if t.first_day.year <= year)
    return {"new": new, "total_at_year_end": total}


def _routes(s: Session, year: int) -> dict:
    members = s.execute(select(RouteMember.route_id, Activity).join(Activity, Activity.id == RouteMember.activity_id)).all()
    by: dict[int, list[Activity]] = defaultdict(list)
    for rid, a in members:
        by[rid].append(a)
    info = {r.id: r for r in s.scalars(select(Route))}
    shown = {rid: acts for rid, acts in by.items() if len(acts) >= MIN_EFFORTS}
    in_year = {rid: [a for a in acts if _local_day(a).year == year] for rid, acts in shown.items()}
    new = [rid for rid, acts in shown.items() if min(_local_day(a) for a in acts).year == year]
    top = sorted(((rid, len(v)) for rid, v in in_year.items() if len(v) >= 2), key=lambda kv: -kv[1])[:5]
    return {"new": len(new), "top": [{"route_id": rid, "name": info[rid].name, "group": info[rid].group,
                                      "length_km": round(info[rid].length_m / 1000, 2), "loop": info[rid].loop, "times": n} for rid, n in top]}


def _tennis(s: Session, acts: list[Activity]) -> dict | None:
    t = [a for a in acts if a.sport == "tennis"]
    if not t:
        return None
    sess = {x.activity_id: x for x in s.scalars(select(TennisSession).where(TennisSession.activity_id.in_([a.id for a in t])))}
    w = sum(x.play_s for x in sess.values())
    share = (lambda k: round(sum(getattr(x, k) * x.play_s for x in sess.values()) / w, 3)) if w else (lambda k: None)
    tops = [x.top_speed_ms for x in sess.values() if x.top_speed_ms]
    return {"sessions": len(t), "hours": round(sum(_hours(a) for a in t), 1), "with_gps": len(sess),
            "net_share": share("net_share"), "base_share": share("base_share"), "right_share": share("right_share"),
            "top_speed_kmh": round(max(tops) * 3.6, 1) if tops else None,
            "longest": _act(max(t, key=_hours))}


def _snow(s: Session, acts: list[Activity]) -> dict | None:
    sn = [a for a in acts if a.sport == "snow"]
    if not sn:
        return None
    top = dict(s.execute(select(DerivedMetric.activity_id, DerivedMetric.value)
                         .where(DerivedMetric.metric == "snow_top_speed",
                                DerivedMetric.activity_id.in_([a.id for a in sn]))).all())
    from .snow import place
    places = []
    for a in sn:
        p = place(a.name)
        if p not in places:
            places.append(p)
    return {"days": len({_local_day(a) for a in sn}), "vertical_m": round(sum(a.descent_m or 0 for a in sn)),
            "distance_km": round(sum(a.distance_m or 0 for a in sn) / 1000, 1), "places": places,
            "top_speed_kmh": round(max(top.values()) * 3.6, 1) if top else None}


def _sleep(s: Session, year: int) -> dict | None:
    def stats(y: int) -> dict | None:
        rows = s.scalars(select(DailyHealth).where(DailyHealth.day >= date(y, 1, 1), DailyHealth.day <= date(y, 12, 31))).all()
        if not rows:
            return None

        def mean(vals, nd=1):
            vals = [v for v in vals if v]
            return round(float(np.mean(vals)), nd) if vals else None
        return {"nights": sum(1 for r in rows if r.sleep_s and r.sleep_s >= 3600),
                "score": mean([r.sleep_score for r in rows], 0),
                "hours": mean([r.sleep_s / 3600 for r in rows if r.sleep_s and r.sleep_s >= 3600], 2),
                "hrv": mean([r.hrv_night_ms for r in rows], 0), "rhr": mean([r.resting_hr for r in rows], 0),
                "_rows": rows}
    cur = stats(year)
    if cur is None:
        return None
    rows = cur.pop("_rows")
    prev = stats(year - 1)
    if prev:
        prev.pop("_rows")
    by_month: dict[int, list[int]] = defaultdict(list)
    for r in rows:
        if r.sleep_score:
            by_month[r.day.month].append(r.sleep_score)
    good = {m: float(np.mean(v)) for m, v in by_month.items() if len(v) >= 10}
    best = max(good.items(), key=lambda kv: kv[1]) if good else None
    worst = min(good.items(), key=lambda kv: kv[1]) if good else None
    return {**cur, "previous": prev,
            "best_month": {"month": best[0], "score": round(best[1])} if best else None,
            "worst_month": {"month": worst[0], "score": round(worst[1])} if worst else None}


def _fitness(s: Session, all_acts: list[Activity], year: int, today: date) -> dict | None:
    loads = dict(s.execute(select(DerivedMetric.activity_id, DerivedMetric.value).where(DerivedMetric.metric == "load")).all())
    per_day: dict[date, float] = defaultdict(float)
    for a in all_acts:
        if a.id in loads:
            per_day[_local_day(a)] += loads[a.id]
    if not per_day:
        return None
    end = min(date(year, 12, 31), today)
    if min(per_day) > end:
        return None
    ff = ld.fitness_fatigue(ld.daily_series(per_day, min(per_day), end))
    yr = ff[[d.year == year for d in ff.index]]
    if yr.empty:
        return None
    peak = yr["fitness"].idxmax()
    return {"total_load": round(float(yr["load"].sum())), "peak_fitness": round(float(yr["fitness"].max()), 1),
            "peak_day": peak.isoformat(), "start_fitness": round(float(yr["fitness"].iloc[0]), 1),
            "end_fitness": round(float(yr["fitness"].iloc[-1]), 1),
            "weekly": [round(float(yr["fitness"].iloc[i]), 1) for i in range(0, len(yr), 7)]}
