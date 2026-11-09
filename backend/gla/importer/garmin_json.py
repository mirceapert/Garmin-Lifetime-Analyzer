"""Read the JSON parts of a Garmin export: activity summaries and daily wellness.

Garmin does not document the export format and its field names vary between export versions,
so every reader here looks for several known spellings and reports what it could not find.
Check the import report on your own export (milestone 1 review).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..sports import normalize_sport


def load_json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8-sig"))


def records(obj: Any) -> list[dict]:
    """Flatten the usual export shapes (a list, or a dict holding lists) into a list of dicts."""
    if isinstance(obj, list):
        out: list[dict] = []
        for x in obj:
            if isinstance(x, dict):
                inner = [v for v in x.values() if isinstance(v, list) and v and isinstance(v[0], dict)]
                if inner and not any(k in x for k in ("calendarDate", "activityId", "startTimeGmt")):
                    for lst in inner:
                        out.extend(records(lst))
                else:
                    out.append(x)
        return out
    if isinstance(obj, dict):
        lists = [v for v in obj.values() if isinstance(v, list)]
        if lists:
            return [r for lst in lists for r in records(lst)]
        return [obj]
    return []


def dig(d: Any, *path: str) -> Any:
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def first(d: dict, *candidates: tuple[str, ...] | str) -> Any:
    for c in candidates:
        v = dig(d, *c) if isinstance(c, tuple) else d.get(c)
        if v is not None and v != "":
            return v
    return None


def to_utc(v: Any) -> datetime | None:
    """Epoch milliseconds, epoch seconds or ISO text -> naive UTC datetime."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        secs = v / 1000 if v > 1e11 else v
        return datetime.fromtimestamp(secs, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(v, str):
        s = v.strip().replace("Z", "")
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
    return None


def to_day(v: Any) -> date | None:
    if isinstance(v, dict):
        v = v.get("date") or v.get("calendarDate")
    dt = to_utc(v)
    return dt.date() if dt else None


# ------------------------------------------------------------------ activity summaries

def is_summary_file(name: str) -> bool:
    return "summarizedactivities" in name.lower().replace("_", "")


def parse_summaries(data: bytes) -> list[dict]:
    """Return one dict per activity with the fields the importer uses (SI units)."""
    out = []
    for r in records(load_json(data)):
        start = to_utc(first(r, "startTimeGmt", "beginTimestamp", "startTimeGMT"))
        if start is None:
            continue
        atype = r.get("activityType")
        type_key = atype.get("typeKey") if isinstance(atype, dict) else atype
        out.append({
            "garmin_id": r.get("activityId"),
            "name": r.get("name") or r.get("activityName"),
            "start_utc": start,
            "tz_offset_min": _offset_minutes(r),
            "garmin_sport": type_key,
            "sport": normalize_sport(type_key),
            # Export summaries are believed to store duration in ms and distance/elevation in cm.
            # Only used for activities without a FIT file; confirm against Garmin Connect at review.
            "elapsed_s": _ms_to_s(first(r, "elapsedDuration", "duration")),
            "timer_s": _ms_to_s(first(r, "movingDuration", "duration")),
            "distance_m": _cm_to_m(r.get("distance")),
            "ascent_m": _cm_to_m(r.get("elevationGain")),
            "descent_m": _cm_to_m(r.get("elevationLoss")),
            "avg_hr": r.get("avgHr") or r.get("averageHR"),
            "max_hr": r.get("maxHr") or r.get("maxHR"),
            "calories": r.get("calories"),
            "start_lat": r.get("startLatitude"),
            "start_lon": r.get("startLongitude"),
        })
    return out


def _ms_to_s(v):
    return float(v) / 1000 if isinstance(v, (int, float)) else None


def _cm_to_m(v):
    return float(v) / 100 if isinstance(v, (int, float)) else None


def _offset_minutes(r: dict) -> int | None:
    local, gmt = to_utc(r.get("startTimeLocal")), to_utc(r.get("startTimeGmt"))
    if local and gmt:
        return round((local - gmt).total_seconds() / 900) * 15
    return None


# ------------------------------------------------------------------ daily wellness

WELLNESS_HINTS = ("sleep", "uds", "hrv", "healthstatus", "wellness", "restingheart")


def is_wellness_file(name: str) -> bool:
    n = name.lower().replace("-", "").replace("_", "")
    return n.endswith(".json") and any(h in n for h in WELLNESS_HINTS) and not is_summary_file(name)


def parse_wellness(data: bytes) -> dict[date, dict]:
    """Return {day: {field: value}} for the fields found. Fields: sleep_score, sleep_start_utc,
    sleep_end_utc, sleep_s, hrv_night_ms, resting_hr. `day` is Garmin's calendarDate (the wake-up day for sleep)."""
    days: dict[date, dict] = {}
    for r in records(load_json(data)):
        day = to_day(r.get("calendarDate"))
        if day is None:
            continue
        f: dict[str, Any] = {}
        score = first(r, ("sleepScores", "overall", "value"), ("sleepScores", "overallScore"), "overallSleepScore",
                      ("sleepScore", "value"), "sleepScore")
        if isinstance(score, (int, float)):
            f["sleep_score"] = float(score)
        start = to_utc(first(r, "sleepStartTimestampGMT", "sleepStartTimestampGmt"))
        end = to_utc(first(r, "sleepEndTimestampGMT", "sleepEndTimestampGmt"))
        if start and end and timedelta(0) < end - start < timedelta(hours=20):
            f["sleep_start_utc"], f["sleep_end_utc"] = start, end
        stages = [r.get(k) for k in ("deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds")]
        if any(isinstance(s, (int, float)) for s in stages):
            f["sleep_s"] = float(sum(s for s in stages if isinstance(s, (int, float))))
        elif "sleep_start_utc" in f:
            f["sleep_s"] = (f["sleep_end_utc"] - f["sleep_start_utc"]).total_seconds() - float(r.get("awakeSleepSeconds") or 0)
        hrv = first(r, "avgOvernightHrv", ("hrvSummary", "lastNightAvg"), "lastNightAvg")
        if hrv is None and isinstance(r.get("metrics"), list):
            for m in r["metrics"]:
                if isinstance(m, dict) and str(m.get("type", "")).upper() == "HRV":
                    hrv = m.get("value")
        if isinstance(hrv, (int, float)) and hrv > 0:
            f["hrv_night_ms"] = float(hrv)
        rhr = first(r, "restingHeartRate", "restingHeartRateValue", "currentDayRestingHeartRate")
        if isinstance(rhr, (int, float)) and 25 <= rhr <= 120:
            f["resting_hr"] = float(rhr)
        if f:
            days.setdefault(day, {}).update(f)
    return days
