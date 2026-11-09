"""Read a Garmin FIT activity file into a summary and a per-second stream table."""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
from fitparse import FitFile

from .sports import normalize_sport

SEMICIRCLE_TO_DEG = 180.0 / 2**31
STREAM_COLUMNS = ["t_s", "timestamp", "lat", "lon", "distance_m", "speed_ms", "heart_rate", "altitude_m", "cadence"]


class NotAnActivity(ValueError):
    """The FIT file is valid but holds no activity (settings, workouts, monitoring files...)."""


@dataclass
class FitActivity:
    sport: str
    garmin_sport: str | None
    garmin_sub_sport: str | None
    start_utc: datetime
    tz_offset_min: int | None
    elapsed_s: float | None
    timer_s: float | None
    distance_m: float | None
    ascent_m: float | None
    descent_m: float | None
    avg_hr: float | None
    max_hr: float | None
    avg_speed_ms: float | None
    max_speed_ms: float | None
    calories: float | None
    streams: pd.DataFrame = field(repr=False)

    @property
    def has_gps(self) -> bool:
        return bool(self.streams["lat"].notna().any()) if len(self.streams) else False

    @property
    def gps_points(self) -> list[tuple[float, float]]:
        s = self.streams.dropna(subset=["lat", "lon"])
        return list(zip(s["lat"].tolist(), s["lon"].tolist()))


def _first(values: dict, *names):
    for n in names:
        v = values.get(n)
        if v is not None:
            return v
    return None


def _utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    # fitparse returns naive datetimes that are already UTC
    return dt.replace(tzinfo=None) if dt.tzinfo is None else dt.astimezone(timezone.utc).replace(tzinfo=None)


def read_fit(data: bytes) -> FitActivity:
    fit = FitFile(io.BytesIO(data))
    fit.parse()

    file_type = None
    for m in fit.get_messages("file_id"):
        file_type = m.get_value("type")
        break
    if file_type not in (None, "activity"):
        raise NotAnActivity(f"FIT file type is {file_type!r}")

    sessions = [{d.name: d.value for d in m} for m in fit.get_messages("session")]
    if not sessions:
        raise NotAnActivity("no session message")
    # Multisport files have several sessions; the first one names the activity, totals add up.
    s0 = sessions[0]

    def total(name: str):
        vals = [s.get(name) for s in sessions if s.get(name) is not None]
        return float(sum(vals)) if vals else None

    def peak(name: str, *alts: str):
        vals = [_first(s, name, *alts) for s in sessions]
        vals = [v for v in vals if v is not None]
        return float(max(vals)) if vals else None

    tz_offset = None
    for m in fit.get_messages("activity"):
        ts, local = m.get_value("timestamp"), m.get_value("local_timestamp")
        if isinstance(ts, datetime) and isinstance(local, datetime):
            tz_offset = round((local - ts).total_seconds() / 900) * 15  # snap to 15 minutes
        break

    rows = []
    for m in fit.get_messages("record"):
        v = {d.name: d.value for d in m}
        lat, lon = v.get("position_lat"), v.get("position_long")
        rows.append({
            "timestamp": _utc(v.get("timestamp")),
            "lat": lat * SEMICIRCLE_TO_DEG if lat is not None else None,
            "lon": lon * SEMICIRCLE_TO_DEG if lon is not None else None,
            "distance_m": v.get("distance"),
            "speed_ms": _first(v, "enhanced_speed", "speed"),
            "heart_rate": v.get("heart_rate"),
            "altitude_m": _first(v, "enhanced_altitude", "altitude"),
            "cadence": v.get("cadence"),
        })
    streams = pd.DataFrame(rows, columns=[c for c in STREAM_COLUMNS if c != "t_s"])
    start = _utc(_first(s0, "start_time")) or (streams["timestamp"].iloc[0] if len(streams) else None)
    if start is None:
        raise NotAnActivity("no start time")
    if len(streams):
        streams = streams.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        streams.insert(0, "t_s", (pd.to_datetime(streams["timestamp"]) - pd.Timestamp(start)).dt.total_seconds())
    else:
        streams = pd.DataFrame(columns=STREAM_COLUMNS)

    garmin_sport = s0.get("sport")
    garmin_sub = s0.get("sub_sport")
    return FitActivity(
        sport=normalize_sport(garmin_sport, garmin_sub),
        garmin_sport=str(garmin_sport) if garmin_sport is not None else None,
        garmin_sub_sport=str(garmin_sub) if garmin_sub is not None else None,
        start_utc=start,
        tz_offset_min=tz_offset,
        elapsed_s=total("total_elapsed_time"),
        timer_s=total("total_timer_time"),
        distance_m=total("total_distance"),
        ascent_m=total("total_ascent"),
        descent_m=total("total_descent"),
        avg_hr=float(s0["avg_heart_rate"]) if s0.get("avg_heart_rate") is not None else None,
        max_hr=peak("max_heart_rate"),
        avg_speed_ms=_first(s0, "enhanced_avg_speed", "avg_speed"),
        max_speed_ms=peak("enhanced_max_speed", "max_speed"),
        calories=total("total_calories"),
        streams=streams,
    )
