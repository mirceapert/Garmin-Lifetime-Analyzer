"""Explorer tiles: zoom-14 map squares you have visited, your largest fully covered square and cluster."""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

from ..geo import haversine_m

ZOOM = 14
STEP_M = 40.0          # densify tracks so a fast stretch can't jump over a tile


def tile_of(lat: float, lon: float, z: int = ZOOM) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lr = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lr) + 1.0 / math.cos(lr)) / math.pi) / 2.0 * n)
    return x, y


def tiles_on_track(points: Sequence[tuple[float, float]], z: int = ZOOM) -> set[tuple[int, int]]:
    out: set[tuple[int, int]] = set()
    if not points:
        return out
    out.add(tile_of(*points[0], z))
    for (la1, lo1), (la2, lo2) in zip(points, points[1:]):
        steps = max(1, int(haversine_m(la1, lo1, la2, lo2) // STEP_M))
        for k in range(1, steps + 1):
            f = k / steps
            out.add(tile_of(la1 + (la2 - la1) * f, lo1 + (lo2 - lo1) * f, z))
    return out


def largest_square(tiles: Iterable[tuple[int, int]]) -> tuple[int, int, int]:
    """(size, x, y) of the largest fully visited square; x, y = its top-left tile."""
    vis = set(tiles)
    sq: dict[tuple[int, int], int] = {}
    best = (0, 0, 0)
    for x, y in sorted(vis):
        v = 1 + min(sq.get((x - 1, y), 0), sq.get((x, y - 1), 0), sq.get((x - 1, y - 1), 0))
        sq[(x, y)] = v
        if v > best[0]:
            best = (v, x - v + 1, y - v + 1)
    return best


def largest_cluster(tiles: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    """Largest connected group of tiles whose four neighbours are all visited."""
    vis = set(tiles)
    nb = lambda t: ((t[0] + 1, t[1]), (t[0] - 1, t[1]), (t[0], t[1] + 1), (t[0], t[1] - 1))  # noqa: E731
    inner = {t for t in vis if all(n in vis for n in nb(t))}
    seen: set = set()
    best: list = []
    for t in inner:
        if t in seen:
            continue
        comp, stack = [], [t]
        seen.add(t)
        while stack:
            c = stack.pop()
            comp.append(c)
            for n in nb(c):
                if n in inner and n not in seen:
                    seen.add(n)
                    stack.append(n)
        if len(comp) > len(best):
            best = comp
    return sorted(best)
