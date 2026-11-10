"""Tennis court coverage from the watch's GPS.

A wrist GPS is good to a few metres, so one point says little. Over a session the shape is clear: two
clusters, one behind each baseline (you change ends), and a smaller one at the net posts (changeovers).

1. Positions are put in metres around the session's median and points more than 40 m away are dropped.
2. The court's long axis is the main direction of spread (principal axis).
3. The net is where the two ends mirror each other best: the depth profile on one side of it matches
   the other side (symmetry estimator). This holds even when you spend more time at one end.
4. Sessions whose nets land within 8 m of each other are the same court. The court's net and axis are the
   medians over its sessions, so a short or one-sided session still gets the right court.
5. Every point is folded into one half court seen from your baseline: depth = metres from the net,
   lateral = metres from the centre line, positive to your right (forehand side for a right-hander).
6. Breaks (standing still for more than 45 s) are left out of the coverage.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

METHOD = "tennis-1"
EARTH_R = 6371000.0
KEEP_M = 40.0                      # points further than this from the session median are GPS errors
SAME_COURT_M = 8.0                 # nets closer than this are one court
NEAR_COURT_M = 22.0                # a session whose own fit fails joins a court this close
BREAK_S = 45.0                     # standing still longer than this is a break
STILL_MS = 0.4
MAX_SPEED_MS = 9.0                 # faster than anyone moves on a court: GPS spike
# folded half court grid: depth 0..18 m from the net, lateral -9..9 m, 1 m cells
DEPTH_M, HALF_W_M, CELL_M = 18, 9, 1.0
NET_ZONE_M, BASE_ZONE_M = 5.0, 10.5          # net < 5 m, mid 5-10.5 m, baseline beyond 10.5 m (baseline is 11.89 m)
BASELINE_M, SINGLES_HALF_M, DOUBLES_HALF_M, SERVICE_M = 11.885, 4.115, 5.485, 6.4


@dataclass
class SessionFit:
    """One session's own estimate, before courts are pooled."""
    activity_id: int
    lat0: float
    lon0: float
    xy: np.ndarray                  # n x 2 metres east / north of (lat0, lon0)
    keep: np.ndarray                # bool per stream row: has a usable position
    centre: np.ndarray              # median position, metres
    angle: float | None             # long axis, radians from east, in [0, pi)
    net: np.ndarray | None          # net centre estimate, metres
    cost: float | None


@dataclass
class Court:
    lat: float
    lon: float
    angle: float                    # radians from east
    sessions: list[int] = field(default_factory=list)


def to_xy(lat: np.ndarray, lon: np.ndarray, lat0: float, lon0: float) -> np.ndarray:
    x = np.radians(lon - lon0) * EARTH_R * math.cos(math.radians(lat0))
    y = np.radians(lat - lat0) * EARTH_R
    return np.c_[x, y]


def to_latlon(xy: np.ndarray, lat0: float, lon0: float) -> tuple[float, float]:
    lat = lat0 + math.degrees(xy[1] / EARTH_R)
    lon = lon0 + math.degrees(xy[0] / (EARTH_R * math.cos(math.radians(lat0))))
    return lat, lon


def principal_angle(q: np.ndarray) -> tuple[float, float]:
    """Angle of the main axis (radians, 0..pi) and how elongated the cloud is (major / minor spread)."""
    w, v = np.linalg.eigh(np.cov(q.T))
    ax = v[:, 1]
    ang = math.atan2(ax[1], ax[0]) % math.pi
    return ang, float(math.sqrt(w[1] / max(w[0], 1e-9)))


def symmetric_centre(u: np.ndarray, span: float = 10.0) -> tuple[float, float] | None:
    """Where along the axis the depth profiles on both sides match best. Returns (centre, cost 0..2)."""
    bins = np.arange(0, 22, 1.0)
    best = None
    med = float(np.median(u))
    for c in np.arange(med - span, med + span + 1e-9, 0.25):
        left, right = c - u[u < c], u[u >= c] - c
        if len(left) < 0.1 * len(u) or len(right) < 0.1 * len(u):
            continue
        hl = np.histogram(left, bins)[0] / len(left)
        hr = np.histogram(right, bins)[0] / len(right)
        cost = float(np.abs(hl - hr).sum())
        if best is None or cost < best[1]:
            best = (float(c), cost)
    return best


def fit_session(activity_id: int, streams: pd.DataFrame) -> SessionFit | None:
    if "lat" not in streams or "lon" not in streams:
        return None
    ok = streams["lat"].notna() & streams["lon"].notna()
    if ok.sum() < 120:
        return None
    lat0, lon0 = float(streams.loc[ok, "lat"].median()), float(streams.loc[ok, "lon"].median())
    xy = to_xy(streams["lat"].to_numpy(float), streams["lon"].to_numpy(float), lat0, lon0)
    d = np.hypot(xy[:, 0], xy[:, 1])
    keep = ok.to_numpy() & (d < KEEP_M)
    if keep.sum() < 120:
        return None
    pts = xy[keep]
    centre = np.median(pts, axis=0)
    q = pts - centre
    angle, ratio = principal_angle(q)
    if ratio < 1.4:                                      # no clear long axis
        return SessionFit(activity_id, lat0, lon0, xy, keep, centre, None, None, None)
    ax = np.array([math.cos(angle), math.sin(angle)])
    sym = symmetric_centre(q @ ax)
    if sym is None:
        return SessionFit(activity_id, lat0, lon0, xy, keep, centre, angle, None, None)
    return SessionFit(activity_id, lat0, lon0, xy, keep, centre, angle, centre + ax * sym[0], sym[1])


def _angle_median(angles: list[float]) -> float:
    """Median of axis angles (0..pi, an axis has no direction)."""
    doubled = np.array(angles) * 2
    mean = math.atan2(np.sin(doubled).mean(), np.cos(doubled).mean())
    rel = (doubled - mean + math.pi) % (2 * math.pi) - math.pi
    return ((mean + float(np.median(rel))) / 2) % math.pi


def find_courts(fits: list[SessionFit]) -> tuple[list[Court], dict[int, int]]:
    """Group sessions into courts. Returns the courts and, per activity, the index of its court."""
    # nets in one shared frame: the first session's origin
    if not fits:
        return [], {}
    lat0, lon0 = fits[0].lat0, fits[0].lon0

    def shared(f: SessionFit, p: np.ndarray) -> np.ndarray:
        lat, lon = to_latlon(p, f.lat0, f.lon0)
        return to_xy(np.array([lat]), np.array([lon]), lat0, lon0)[0]

    good = [(f, shared(f, f.net)) for f in fits if f.net is not None and f.cost is not None and f.cost < 0.7]
    # single-linkage clusters of the nets, then clusters whose centres are close are merged
    parent = list(range(len(good)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(good)):
        for j in range(i):
            if np.linalg.norm(good[i][1] - good[j][1]) < SAME_COURT_M * 0.75:
                parent[root(i)] = root(j)
    by_root: dict[int, list] = {}
    for i, g in enumerate(good):
        by_root.setdefault(root(i), []).append(g)
    groups = sorted(by_root.values(), key=len, reverse=True)
    cores: list[list] = []
    for g in groups:                                    # biggest first
        p = np.median([q for _, q in g], axis=0)
        for m in cores:
            # courts sit side by side (or end to end, a full court length and run-off apart), so two "nets"
            # less than a court length apart along the axis and close across it are one court whose net
            # was misplaced in the smaller group
            ang = _angle_median([f.angle for f, _ in m])
            ax = np.array([math.cos(ang), math.sin(ang)])
            d = np.median([q for _, q in m], axis=0) - p
            along, across = abs(d @ ax), abs(d @ np.array([-ax[1], ax[0]]))
            if along < 2 * BASELINE_M and across < SAME_COURT_M:
                break
        else:
            cores.append(g)
    # sessions left out of a core (misplaced net, unclear axis) join the nearest court below
    courts, centres, member = [], [], {}
    for g in cores:
        p = np.median([q for _, q in g], axis=0)
        # a lone session is trusted only if its own fit looks clean
        if len(g) == 1 and g[0][0].cost > 0.45:
            continue
        lat, lon = to_latlon(p, lat0, lon0)
        courts.append(Court(lat, lon, _angle_median([f.angle for f, _ in g])))
        centres.append(p)
    for f in fits:
        own = shared(f, f.net) if f.net is not None else None
        here = shared(f, f.centre)
        best = None
        for i, c in enumerate(centres):
            d_own = np.linalg.norm(c - own) if own is not None else math.inf
            d_here = np.linalg.norm(c - here)
            if d_own < SAME_COURT_M or d_here < NEAR_COURT_M:
                score = min(d_own, d_here)
                if best is None or score < best[0]:
                    best = (score, i)
        if best is not None:
            member[f.activity_id] = best[1]
            courts[best[1]].sessions.append(f.activity_id)
    return courts, member


def _breaks(t: np.ndarray, speed: np.ndarray) -> np.ndarray:
    """True where you stood still for more than BREAK_S in a row."""
    still = np.nan_to_num(speed, nan=0.0) < STILL_MS
    out = np.zeros(len(t), bool)
    i = 0
    while i < len(t):
        if still[i]:
            j = i
            while j + 1 < len(t) and still[j + 1]:
                j += 1
            if t[j] - t[i] > BREAK_S:
                out[i:j + 1] = True
            i = j + 1
        else:
            i += 1
    return out


def fold(f: SessionFit, court: Court) -> tuple[np.ndarray, np.ndarray]:
    """Depth from the net and lateral offset (+ = your right) for every row with a usable position."""
    net = to_xy(np.array([court.lat]), np.array([court.lon]), f.lat0, f.lon0)[0]
    ax = np.array([math.cos(court.angle), math.sin(court.angle)])
    left = np.array([-ax[1], ax[0]])                    # 90 degrees anticlockwise of the axis
    q = f.xy - net
    u, v = q @ ax, q @ left
    side = np.sign(u)
    side[side == 0] = 1
    # facing the net from the u < 0 end you look along +axis, so your right is -left; from the other end, +left
    return np.abs(u), v * side


def top_speed(speed: np.ndarray, garmin_max: float | None = None) -> float | None:
    """Garmin's own top speed when it is believable; otherwise one that survives GPS spikes
    (spikes above 9 m/s go, then a 3-sample median, then the 99.5th percentile)."""
    if garmin_max and 0 < garmin_max <= MAX_SPEED_MS:
        return round(float(garmin_max), 2)
    s = pd.Series(np.where(speed > MAX_SPEED_MS, np.nan, speed)).rolling(3, center=True, min_periods=2).median().dropna()
    return round(float(np.percentile(s, 99.5)), 2) if len(s) else None


def coverage(f: SessionFit, court: Court, streams: pd.DataFrame, garmin_max: float | None = None) -> dict:
    """Folded grid (seconds per 1 m cell), zone shares, forehand-side share and top speed."""
    t = streams["t_s"].to_numpy(float)
    speed = streams["speed_ms"].to_numpy(float) if "speed_ms" in streams else np.full(len(t), np.nan)
    depth, lat = fold(f, court)
    dt = np.clip(np.diff(t, append=t[-1]), 0, 5)
    use = f.keep & ~_breaks(t, speed) & (depth <= DEPTH_M)
    rows, cols = int(DEPTH_M / CELL_M), int(2 * HALF_W_M / CELL_M)
    grid = np.zeros((rows, cols))
    di = np.clip((depth[use] / CELL_M).astype(int), 0, rows - 1)
    li = np.clip(((lat[use] + HALF_W_M) / CELL_M).astype(int), 0, cols - 1)
    np.add.at(grid, (di, li), dt[use])
    total = float(dt[use].sum()) or 1.0
    d, w = depth[use], dt[use]
    return {
        "grid": np.round(grid, 1).tolist(),
        "play_s": round(float(dt[use].sum())),
        "net_share": round(float(w[d < NET_ZONE_M].sum() / total), 3),
        "mid_share": round(float(w[(d >= NET_ZONE_M) & (d < BASE_ZONE_M)].sum() / total), 3),
        "base_share": round(float(w[d >= BASE_ZONE_M].sum() / total), 3),
        "right_share": round(float(w[lat[use] > 0].sum() / total), 3),
        "median_depth_m": round(float(np.median(d)), 1) if len(d) else None,
        "top_speed_ms": top_speed(speed, garmin_max),
    }


def per_minute(streams: pd.DataFrame) -> list[list]:
    """[minute, mean HR, mean speed m/s] per minute of the session."""
    t = streams["t_s"].to_numpy(float)
    m = (t // 60).astype(int)
    df = pd.DataFrame({"m": m})
    df["hr"] = streams["heart_rate"].to_numpy(float) if "heart_rate" in streams else np.nan
    sp = streams["speed_ms"].to_numpy(float) if "speed_ms" in streams else np.full(len(t), np.nan)
    df["sp"] = np.where(sp > MAX_SPEED_MS, np.nan, sp)
    g = df.groupby("m").mean()
    return [[int(k), None if pd.isna(r.hr) else round(float(r.hr)), None if pd.isna(r.sp) else round(float(r.sp), 2)]
            for k, r in g.iterrows()]
