"""Fastest stretch of each distance inside a run, found in the per-second stream."""
from __future__ import annotations

import numpy as np
import pandas as pd

METHOD = "best-1"
DISTANCES = {"best_1k": 1000.0, "best_5k": 5000.0, "best_10k": 10000.0, "best_hm": 21097.5}
GLITCH_SPEED = 10.0     # m/s (36 km/h): faster steps in a run are GPS jumps and are dropped


def clean_distance(t_s: np.ndarray, distance_m: np.ndarray) -> np.ndarray:
    """Cumulative distance with GPS jumps (and any step backwards) removed."""
    d = pd.Series(distance_m, dtype=float).ffill().fillna(0).to_numpy()
    dt, dd = np.diff(t_s), np.diff(d)
    with np.errstate(divide="ignore", invalid="ignore"):
        speed = np.where(dt > 0, dd / dt, np.inf)
    bad = (dd < 0) | ((dd > 0) & (speed > GLITCH_SPEED))
    return np.concatenate([[0.0], np.cumsum(np.where(bad, 0.0, dd))])


def fastest(t_s: np.ndarray, dist: np.ndarray, target_m: float) -> float | None:
    """Shortest elapsed time covering target_m, interpolating inside the end sample."""
    if len(dist) < 2 or dist[-1] < target_m:
        return None
    j = np.searchsorted(dist, dist + target_m)
    ok = j < len(dist)
    i, j = np.nonzero(ok)[0], j[ok]
    span = np.maximum(dist[j] - dist[j - 1], 1e-9)
    frac = (dist[i] + target_m - dist[j - 1]) / span
    t_end = t_s[j - 1] + frac * (t_s[j] - t_s[j - 1])
    times = t_end - t_s[i]
    return float(times.min()) if len(times) else None


def best_efforts(streams: pd.DataFrame) -> dict[str, float]:
    if streams.empty or "distance_m" not in streams:
        return {}
    t = streams["t_s"].to_numpy(dtype=float)
    dist = clean_distance(t, streams["distance_m"].to_numpy(dtype=float))
    out = {}
    for name, target in DISTANCES.items():
        v = fastest(t, dist, target)
        if v is not None and v > 0:
            out[name] = round(v, 1)
    return out
