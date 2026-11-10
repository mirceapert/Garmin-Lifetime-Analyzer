"""Sleep drivers and recovery lag.

Everything here is computed when you open the page, from the nightly values Garmin gives (sleep score,
sleep time, night HRV, resting heart rate) and the training load of your activities.

A night belongs to the day you wake up. "That day" for a night is the day before it: the night ending on
the morning of 10 March follows the day of 9 March.

Drivers compare nights with something (a hard training day, a late workout, a weekend) against nights
without it. The difference comes with a 95% range: if the range crosses zero, the data can't tell the
difference from chance. A driver needs at least 20 nights on each side to be shown. Each night is
measured against your typical value in the two months around it, so slow changes over the years (getting
fitter, a new watch) don't pass for drivers. These are associations in your own history, not proof of cause.

Recovery lag follows the nights after your hardest sessions (top 15% training load). Each session is
compared with your median over the 7 nights before it (a median, so one bad night doesn't move it).
Sessions followed by another hard one within 3 days are left out, so one recovery is not mixed with
the next.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Activity, DailyHealth, DerivedMetric
from . import load as ld

MIN_NIGHTS = 20
MIN_SESSIONS_YEAR = 8
HARD_QUANTILE = 0.85
LATE_WORKOUT_H = 3
RECOVERY_NIGHTS = 4

OUTCOMES = {
    "sleep_score": {"label": "Sleep score", "unit": "", "better": "higher"},
    "hrv": {"label": "Night HRV", "unit": "ms", "better": "higher"},
    "rhr": {"label": "Resting heart rate", "unit": "bpm", "better": "lower"},
    "sleep_h": {"label": "Sleep time", "unit": "h", "better": "higher"},
}


def day_frame(s: Session, tz: str, today: date) -> pd.DataFrame:
    """One row per calendar day: that day's training and the night that ends on its morning."""
    zone = ZoneInfo(tz)
    health = s.scalars(select(DailyHealth)).all()
    loads = dict(s.execute(select(DerivedMetric.activity_id, DerivedMetric.value)
                           .where(DerivedMetric.metric == "load")).all())
    acts = s.scalars(select(Activity)).all()
    days = [h.day for h in health] + [a.start_local.date() for a in acts]
    if not days:
        return pd.DataFrame()
    idx = pd.date_range(min(days), max(max(days), today), freq="D").date
    df = pd.DataFrame(index=idx)
    df["load"] = 0.0
    for col in ("tennis", "run", "snow"):
        df[col] = False
    df["last_end_utc"] = pd.NaT
    for a in acts:
        d = a.start_local.date()
        df.at[d, "load"] += loads.get(a.id, 0.0)
        if a.sport == "tennis":
            df.at[d, "tennis"] = True
        if a.sport in ("run", "trail"):
            df.at[d, "run"] = True
        if a.sport == "snow":
            df.at[d, "snow"] = True
        end = a.start_utc + timedelta(seconds=a.elapsed_s or a.timer_s or 0)
        prev = df.at[d, "last_end_utc"]
        if pd.isna(prev) or end > prev:
            df.at[d, "last_end_utc"] = end
    ends = pd.to_datetime(df["last_end_utc"]).dt.tz_localize("UTC").dt.tz_convert(zone)
    df["evening_workout"] = (ends.dt.hour >= 19).fillna(False).to_numpy()   # finished after 19:00 local
    for col in ("sleep_score", "hrv", "rhr", "sleep_h", "bed_min"):
        df[col] = np.nan
    df["sleep_start_utc"] = pd.NaT
    for h in health:
        df.at[h.day, "sleep_score"] = h.sleep_score if h.sleep_score else np.nan
        df.at[h.day, "hrv"] = h.hrv_night_ms if h.hrv_night_ms else np.nan
        df.at[h.day, "rhr"] = h.resting_hr if h.resting_hr else np.nan
        if h.sleep_s and h.sleep_s >= 3600:
            df.at[h.day, "sleep_h"] = h.sleep_s / 3600
        if h.sleep_start_utc and h.sleep_s and h.sleep_s >= 3600:
            df.at[h.day, "sleep_start_utc"] = h.sleep_start_utc
            local = h.sleep_start_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(zone)
            df.at[h.day, "bed_min"] = ((local.hour - 18) % 24) * 60 + local.minute   # minutes after 18:00
    ff = ld.fitness_fatigue(df["load"])
    df["fitness"], df["fatigue"], df["form"] = ff["fitness"].values, ff["fatigue"].values, ff["form"].values
    return df


def nights(df: pd.DataFrame) -> pd.DataFrame:
    """One row per wake day with the features of the day before."""
    prev = df.shift(1)
    n = pd.DataFrame(index=df.index)
    for k in OUTCOMES:
        n[k] = df[k]
    n["load"] = prev["load"]
    n["tennis"] = prev["tennis"].fillna(False).astype(bool)
    n["run"] = prev["run"].fillna(False).astype(bool)
    n["form"] = prev["form"]
    # form after that day's training: what the body carries into the night
    n["form_after"] = df["form"]
    wd = pd.Series([d.weekday() for d in df.index], index=df.index)
    n["weekend"] = ((wd - 1) % 7).isin([4, 5])                 # the day before was Friday or Saturday
    gap_h = (pd.to_datetime(df["sleep_start_utc"]) - pd.to_datetime(prev["last_end_utc"])).dt.total_seconds() / 3600
    n["late_workout"] = (gap_h >= 0) & (gap_h <= LATE_WORKOUT_H)
    usual_bed = df["bed_min"].rolling(28, min_periods=10).median().shift(1)
    n["late_bed"] = (df["bed_min"] - usual_bed) >= 60
    n["short_prev"] = prev["sleep_h"] < 6
    n["has_bed"] = df["bed_min"].notna()
    return n


def driver_masks(n: pd.DataFrame) -> dict[str, tuple[str, pd.Series, pd.Series]]:
    """key -> (label, nights with it, nights it is compared with)."""
    trained = n["load"] > 0
    hard_cut = n.loc[trained, "load"].quantile(HARD_QUANTILE) if trained.any() else math.inf
    everyone = pd.Series(True, index=n.index)
    return {
        "hard_day": ("Hard training day (your top 15% load)", n["load"] >= hard_cut, n["load"] < hard_cut),
        "rest_day": ("Rest day (no recorded activity)", ~trained, trained),
        "late_workout": (f"Workout ending under {LATE_WORKOUT_H} h before bed", n["late_workout"] & n["has_bed"],
                         ~n["late_workout"] & n["has_bed"]),
        "tennis": ("Tennis that day", n["tennis"], ~n["tennis"]),
        "run": ("Run that day", n["run"], ~n["run"]),
        "weekend": ("Friday or Saturday night", n["weekend"], ~n["weekend"]),
        "late_bed": ("Bed 1 h or more later than usual", n["late_bed"], ~n["late_bed"] & n["has_bed"]),
        "short_prev": ("Short night before (under 6 h)", n["short_prev"], n["short_prev"].eq(False) & everyone),
        "fatigued": ("Fatigue well above fitness (form under -10)", n["form_after"] < -10, n["form_after"] >= -10),
    }


def _diff(a: pd.Series, b: pd.Series) -> tuple[float, float, float]:
    """Mean difference a - b with a 95% range (Welch)."""
    d = a.mean() - b.mean()
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return d, d - 1.96 * se, d + 1.96 * se


def drivers(n: pd.DataFrame) -> dict:
    masks = driver_masks(n)
    out: dict[str, dict] = {}
    for key, meta in OUTCOMES.items():
        have = n[key].notna()
        if have.sum() < 2 * MIN_NIGHTS:
            out[key] = {**meta, "nights": int(have.sum()), "baseline": None, "drivers": [], "hidden": []}
            continue
        y = n.loc[have, key]
        # compare against your level at the time, not against your whole history: slow changes
        # (getting fitter, a new watch, a new job) would otherwise pass for a driver
        resid = (n[key] - n[key].rolling(61, center=True, min_periods=15).median())[have]
        items, hidden = [], []
        for dk, (label, with_, without) in masks.items():
            a = resid[with_[have].fillna(False).astype(bool)].dropna()
            b = resid[without[have].fillna(False).astype(bool)].dropna()
            if len(a) < MIN_NIGHTS or len(b) < MIN_NIGHTS:
                hidden.append({"key": dk, "label": label, "nights": int(len(a))})
                continue
            d, lo, hi = _diff(a, b)
            items.append({"key": dk, "label": label, "nights": int(len(a)), "compared": int(len(b)),
                          "diff": round(d, 2), "lo": round(lo, 2), "hi": round(hi, 2),
                          "clear": bool(lo > 0 or hi < 0)})
        items.sort(key=lambda r: -abs(r["diff"]) / (y.std() or 1))
        first = n.index[have.to_numpy()][0]
        out[key] = {**meta, "nights": int(have.sum()), "since": first.isoformat(), "baseline": round(float(y.mean()), 1),
                    "drivers": items, "hidden": hidden}
    return out


def recovery(df: pd.DataFrame, activity_loads: list[tuple[date, float]]) -> dict:
    """How HRV and resting heart rate move in the nights after your hardest sessions."""
    if not activity_loads:
        return {"metrics": {}, "sessions": 0}
    vals = np.array([v for _, v in activity_loads])
    cut = float(np.quantile(vals, HARD_QUANTILE))
    hard_days = sorted({d for d, v in activity_loads if v >= cut})
    hard_set = set(hard_days)
    clean = [d for d in hard_days if not any(d + timedelta(days=k) in hard_set for k in (1, 2, 3))]
    out: dict[str, dict] = {}
    for key in ("hrv", "rhr"):
        series = df[key]
        rows = []
        for d in clean:
            base_days = [d - timedelta(days=k) for k in range(0, 7)]
            base = series.reindex(base_days).dropna()
            if len(base) < 4:
                continue
            after = [series.get(d + timedelta(days=k), np.nan) for k in range(1, RECOVERY_NIGHTS + 1)]
            if np.isnan(after[0]):
                continue
            rows.append((d, [a - base.median() if not np.isnan(a) else np.nan for a in after]))
        out[key] = {**OUTCOMES[key], "overall": _curve([r[1] for r in rows]), "years": {}}
        by_year = defaultdict(list)
        for d, dev in rows:
            by_year[d.year].append(dev)
        for y, devs in sorted(by_year.items()):
            if len(devs) >= MIN_SESSIONS_YEAR:
                out[key]["years"][str(y)] = _curve(devs)
    return {"hard_load": round(cut, 1), "hard_sessions": len(hard_days), "clean_sessions": len(clean), "metrics": out}


def _curve(devs: list[list[float]]) -> dict:
    """Mean change per night after the session with a 95% range, and the first night back to normal."""
    if not devs:
        return {"sessions": 0, "nights": [], "back_by": None}
    arr = np.array(devs, dtype=float)
    nights_ = []
    back = None
    for k in range(arr.shape[1]):
        col = arr[:, k][~np.isnan(arr[:, k])]
        if len(col) < 3:
            nights_.append(None)
            continue
        m = float(col.mean())
        se = float(col.std(ddof=1) / math.sqrt(len(col)))
        lo, hi = m - 1.96 * se, m + 1.96 * se
        nights_.append({"night": k + 1, "mean": round(m, 2), "lo": round(lo, 2), "hi": round(hi, 2), "n": int(len(col))})
        first = nights_[0]["mean"] if nights_[0] else None
        # back to normal: indistinguishable from your baseline, or within a quarter of the first night's change
        if back is None and k > 0 and (lo <= 0 <= hi or (first and abs(m) <= abs(first) / 4)):
            back = k + 1
        elif back is None and k == 0 and lo <= 0 <= hi:
            back = 1
    return {"sessions": int(arr.shape[0]), "nights": nights_, "back_by": back}


def activity_loads(s: Session) -> list[tuple[date, float]]:
    rows = s.execute(select(Activity, DerivedMetric.value).join(DerivedMetric, DerivedMetric.activity_id == Activity.id)
                     .where(DerivedMetric.metric == "load")).all()
    return [(a.start_local.date(), v) for a, v in rows]


def daily_series(df: pd.DataFrame) -> list[list]:
    """[day, sleep score, sleep hours, HRV, resting HR, bedtime minutes after 18:00, load] for the charts."""
    def f(v, nd=1):
        return None if pd.isna(v) else round(float(v), nd)
    return [[d.isoformat(), f(r.sleep_score, 0), f(r.sleep_h, 2), f(r.hrv, 0), f(r.rhr, 0), f(r.bed_min, 0), f(r.load, 0)]
            for d, r in df.iterrows()]
