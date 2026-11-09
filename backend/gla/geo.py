"""Small geometry helpers: distances, simplification and polyline encoding."""
from __future__ import annotations

import math
from collections.abc import Sequence

EARTH_R = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(h)))


def thin_by_distance(points: Sequence[tuple[float, float]], spacing_m: float = 50.0) -> list[tuple[float, float]]:
    """Keep a point roughly every `spacing_m` metres, always keeping the first and last."""
    if len(points) <= 2:
        return list(points)
    out = [points[0]]
    acc = 0.0
    for prev, cur in zip(points, points[1:]):
        acc += haversine_m(prev[0], prev[1], cur[0], cur[1])
        if acc >= spacing_m:
            out.append(cur)
            acc = 0.0
    if out[-1] != points[-1]:
        out.append(points[-1])
    return out


def encode_polyline(points: Sequence[tuple[float, float]], precision: int = 5) -> str:
    """Google encoded polyline (the format MapLibre plugins and most tools read)."""
    factor = 10 ** precision
    out: list[str] = []
    prev_lat = prev_lon = 0
    for lat, lon in points:
        ilat, ilon = round(lat * factor), round(lon * factor)
        for delta in (ilat - prev_lat, ilon - prev_lon):
            v = ~(delta << 1) if delta < 0 else delta << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        prev_lat, prev_lon = ilat, ilon
    return "".join(out)


def decode_polyline(text: str, precision: int = 5) -> list[tuple[float, float]]:
    factor = 10 ** precision
    coords: list[tuple[float, float]] = []
    i = lat = lon = 0
    while i < len(text):
        vals = []
        for _ in range(2):
            shift = result = 0
            while True:
                b = ord(text[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            vals.append(~(result >> 1) if result & 1 else result >> 1)
        lat += vals[0]
        lon += vals[1]
        coords.append((lat / factor, lon / factor))
    return coords
