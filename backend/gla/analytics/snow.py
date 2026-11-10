"""Snowboard seasons: days on snow, runs, vertical and top speed.

- A season runs from July to June, so January 2019 is the 2018/19 season.
- Days on snow are calendar days, however many activities you recorded that day.
- Vertical is Garmin's descent for each activity. It stays right even when the altitude in the
  per-second data has gaps (some watches lost it for whole stretches).
- Runs are counted from altitude: a run is a descent of at least 30 m that ends where you climb
  30 m again (a lift). Pauses on the lift do not matter. Without near-complete altitude there is no count.
- Top speed is Garmin's; where Garmin left it out, a 5-sample median of the per-second speed.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

METHOD = "snow-1"
HYSTERESIS_M = 30.0
MIN_ALT_COVERAGE = 0.9
_SUFFIX = re.compile(r"\s+(resort\b.*|snowboard.*|skiing.*|ski\b.*)$", re.I)


def season(day) -> str:
    y = day.year if day.month >= 7 else day.year - 1
    return f"{y}/{str(y + 1)[-2:]}"


def place(name: str | None) -> str:
    if not name:
        return "Unknown"
    return _SUFFIX.sub("", name.strip()).strip() or name.strip()


def count_runs(altitude: pd.Series) -> int | None:
    if len(altitude) < 30 or altitude.notna().mean() < MIN_ALT_COVERAGE:
        return None
    z = altitude.interpolate(limit_direction="both").rolling(5, center=True, min_periods=1).median().to_numpy()
    runs, descending = 0, False
    hi = lo = z[0]
    for v in z:
        if descending:
            lo = min(lo, v)
            if v - lo >= HYSTERESIS_M:          # climbing again: the run is over
                runs += 1
                descending, hi = False, v
        else:
            hi = max(hi, v)
            if hi - v >= HYSTERESIS_M:
                descending, lo = True, v
    return runs + (1 if descending else 0)


def stream_top_speed(speed: pd.Series) -> float | None:
    s = speed.rolling(5, center=True, min_periods=3).median()
    return round(float(s.max()), 2) if s.notna().any() else None


def activity_metrics(streams: pd.DataFrame | None, garmin_max: float | None) -> dict[str, float]:
    out: dict[str, float] = {}
    if garmin_max and garmin_max == garmin_max:     # not NaN
        out["snow_top_speed"] = round(float(garmin_max), 2)
    elif streams is not None and "speed_ms" in streams:
        top = stream_top_speed(streams["speed_ms"])
        if top is not None:
            out["snow_top_speed"] = top
    if streams is not None and "altitude_m" in streams:
        runs = count_runs(streams["altitude_m"])
        if runs is not None:
            out["snow_runs"] = float(runs)
    return out


def _top(vals) -> float | None:
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None


def seasons(rows: list[dict]) -> dict:
    """rows: one per activity with day, name, distance_m, descent_m, hours, top_speed_ms, runs, activity_id.
    Returns seasons (newest first) with their days."""
    days: dict = {}
    for r in rows:
        d = days.setdefault(r["day"], {"day": r["day"], "places": [], "activities": [], "distance_m": 0.0,
                                        "vertical_m": 0.0, "hours": 0.0, "runs": 0, "runs_known": True, "top_speed_ms": None})
        p = place(r["name"])
        if p not in d["places"]:
            d["places"].append(p)
        d["activities"].append(r["activity_id"])
        d["distance_m"] += r["distance_m"] or 0
        d["vertical_m"] += r["descent_m"] or 0
        d["hours"] += r["hours"] or 0
        if r["runs"] is None:
            d["runs_known"] = False
        else:
            d["runs"] += r["runs"]
        d["top_speed_ms"] = _top([d["top_speed_ms"], r["top_speed_ms"]])
    out: dict[str, dict] = {}
    for day in sorted(days):
        d = days[day]
        s = out.setdefault(season(day), {"season": season(day), "days": [], "places": []})
        s["days"].append({"day": day.isoformat(), "places": d["places"], "activities": d["activities"],
                          "distance_km": round(d["distance_m"] / 1000, 1), "vertical_m": round(d["vertical_m"]),
                          "hours": round(d["hours"], 1), "runs": d["runs"] if d["runs_known"] else None,
                          "top_speed_kmh": round(d["top_speed_ms"] * 3.6, 1) if d["top_speed_ms"] else None})
        for p in d["places"]:
            if p not in s["places"]:
                s["places"].append(p)
    result = []
    for s in out.values():
        ds = s["days"]
        runs = [d["runs"] for d in ds]
        result.append({
            "season": s["season"], "places": s["places"], "days_on_snow": len(ds),
            "distance_km": round(sum(d["distance_km"] for d in ds), 1),
            "vertical_m": sum(d["vertical_m"] for d in ds),
            "hours": round(sum(d["hours"] for d in ds), 1),
            "runs": sum(runs) if all(r is not None for r in runs) else None,
            "runs_partial": sum(r for r in runs if r is not None) if any(r is None for r in runs) else None,
            "top_speed_kmh": _top([d["top_speed_kmh"] for d in ds]),
            "best_day_vertical_m": max(d["vertical_m"] for d in ds),
            "days": ds,
        })
    result.sort(key=lambda s: s["season"], reverse=True)
    return {"seasons": result,
            "totals": {"seasons": len(result), "days_on_snow": sum(s["days_on_snow"] for s in result),
                       "vertical_m": sum(s["vertical_m"] for s in result),
                       "distance_km": round(sum(s["distance_km"] for s in result), 1),
                       "top_speed_kmh": _top([s["top_speed_kmh"] for s in result])}}
