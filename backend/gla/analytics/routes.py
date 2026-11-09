"""Routes you repeat, found by comparing the shape of GPS tracks.

Matching is incremental: each new activity is compared with the routes already known and joins
the closest one, or starts a new route. Route IDs and the names you give them therefore stay put
when new activities arrive.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..geo import haversine_m

SIG_POINTS = 24
MAX_START_GAP_M = 400       # starts must be this close
MAX_LENGTH_DIFF = 0.12      # lengths within 12%
MAX_MEAN_GAP_M = 140        # mean distance between matching points, either direction
MIN_EFFORTS = 3             # a route is shown once you have done it this often
ROUTE_GROUPS = {"run": "run", "trail": "run", "walk": "walk", "cycle": "cycle"}


def path_length(pts: Sequence[tuple[float, float]]) -> float:
    return sum(haversine_m(*a, *b) for a, b in zip(pts, pts[1:]))


def signature(pts: Sequence[tuple[float, float]], n: int = SIG_POINTS) -> tuple[list[tuple[float, float]], float]:
    """n points evenly spaced along the track, and the track length."""
    cum = [0.0]
    for a, b in zip(pts, pts[1:]):
        cum.append(cum[-1] + haversine_m(*a, *b))
    total = cum[-1]
    out, j = [], 0
    for k in range(n):
        target = total * k / (n - 1)
        while j < len(cum) - 2 and cum[j + 1] < target:
            j += 1
        seg = (cum[j + 1] - cum[j]) or 1.0
        f = min(1.0, max(0.0, (target - cum[j]) / seg))
        out.append((pts[j][0] + (pts[j + 1][0] - pts[j][0]) * f, pts[j][1] + (pts[j + 1][1] - pts[j][1]) * f))
    return out, total


def match_distance(sig_a, len_a, sig_b, len_b) -> float | None:
    """Mean point distance between two signatures (best of both directions), or None if they can't match."""
    if len_a <= 0 or abs(len_a - len_b) / len_a > MAX_LENGTH_DIFF:
        return None
    same = haversine_m(*sig_a[0], *sig_b[0]) <= MAX_START_GAP_M
    rev = haversine_m(*sig_a[0], *sig_b[-1]) <= MAX_START_GAP_M
    cands = []
    if same:
        cands.append(sum(haversine_m(*p, *q) for p, q in zip(sig_a, sig_b)) / len(sig_a))
    if rev:
        cands.append(sum(haversine_m(*p, *q) for p, q in zip(sig_a, reversed(sig_b))) / len(sig_a))
    m = min(cands) if cands else None
    return m if m is not None and m < MAX_MEAN_GAP_M else None


def is_loop(pts: Sequence[tuple[float, float]], length: float) -> bool:
    return haversine_m(*pts[0], *pts[-1]) < max(200.0, 0.05 * length)
