"""Training load (TRIMP) per activity, and fitness, fatigue and form per day."""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

METHOD = "trimp-1"
FITNESS_DAYS, FATIGUE_DAYS = 42, 7


def trimp_from_stream(t_s: np.ndarray, hr: np.ndarray, hr_rest: float, hr_max: float, max_gap_s: float = 30) -> float | None:
    """Banister TRIMP summed second by second. Gaps longer than max_gap_s (pauses) count as max_gap_s."""
    ok = ~np.isnan(hr)
    if ok.sum() < 10:
        return None
    t, h = t_s[ok], hr[ok]
    dt = np.clip(np.diff(t, append=t[-1]), 0, max_gap_s)
    hrr = np.clip((h - hr_rest) / (hr_max - hr_rest), 0, 1.2)
    return float(np.sum(dt / 60 * hrr * 0.64 * np.exp(1.92 * hrr)))


def trimp_from_average(duration_s: float, avg_hr: float, hr_rest: float, hr_max: float) -> float:
    hrr = min(max((avg_hr - hr_rest) / (hr_max - hr_rest), 0), 1.2)
    return duration_s / 60 * hrr * 0.64 * math.exp(1.92 * hrr)


def fitness_fatigue(daily: pd.Series) -> pd.DataFrame:
    """daily: load per calendar day (no gaps). Returns fitness (42-day), fatigue (7-day) and form = fitness - fatigue
    as of the start of each day, the way coaches read it: today's form is what you bring to today's session."""
    ctl = atl = 0.0
    rows = []
    for day, load in daily.items():
        rows.append((day, ctl, atl, ctl - atl, load))
        ctl += (load - ctl) / FITNESS_DAYS
        atl += (load - atl) / FATIGUE_DAYS
    return pd.DataFrame(rows, columns=["day", "fitness", "fatigue", "form", "load"]).set_index("day")


def daily_series(loads: dict[date, float], start: date, end: date) -> pd.Series:
    days = pd.date_range(start, end, freq="D").date
    return pd.Series([loads.get(d, 0.0) for d in days], index=days, dtype=float)


def project(history: pd.DataFrame, days: int, weekly_pattern: list[float]) -> pd.DataFrame:
    """Continue fitness and fatigue for `days` days with a load per weekday (Monday first)."""
    last = history.iloc[-1]
    ctl = last.fitness + (last.load - last.fitness) / FITNESS_DAYS
    atl = last.fatigue + (last.load - last.fatigue) / FATIGUE_DAYS
    day0 = history.index[-1]
    rows = []
    for k in range(1, days + 1):
        d = day0 + timedelta(days=k)
        load = weekly_pattern[d.weekday()]
        rows.append((d, ctl, atl, ctl - atl, load))
        ctl += (load - ctl) / FITNESS_DAYS
        atl += (load - atl) / FATIGUE_DAYS
    return pd.DataFrame(rows, columns=["day", "fitness", "fatigue", "form", "load"]).set_index("day")
