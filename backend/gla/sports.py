"""Map Garmin sport names onto the app's sport groups."""
from __future__ import annotations

SPORTS = ("run", "trail", "walk", "tennis", "snow", "other")

# FIT names (fitparse) and Garmin Connect activity type keys, lower case.
_DIRECT = {
    "running": "run",
    "street_running": "run",
    "track_running": "run",
    "treadmill_running": "run",
    "indoor_running": "run",
    "virtual_run": "run",
    "trail_running": "trail",
    "trail": "trail",
    "walking": "walk",
    "casual_walking": "walk",
    "speed_walking": "walk",
    "hiking": "walk",
    "tennis": "tennis",
    "snowboarding": "snow",
    "resort_snowboarding": "snow",
    "backcountry_snowboarding": "snow",
}


def normalize_sport(sport: str | None, sub_sport: str | None = None) -> str:
    """Return one of SPORTS. Sub-sport wins where it is more specific (running + trail = trail)."""
    s = (str(sport) if sport is not None else "").lower()
    sub = (str(sub_sport) if sub_sport is not None else "").lower()
    if s == "running" and sub == "trail":
        return "trail"
    if sub in _DIRECT and _DIRECT[sub] in ("trail", "snow"):
        return _DIRECT[sub]
    return _DIRECT.get(s, "other")
