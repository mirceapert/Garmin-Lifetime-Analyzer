"""Map Garmin sport names onto the app's sport groups."""
from __future__ import annotations

SPORTS = ("run", "trail", "walk", "tennis", "snow", "cycle", "sail", "other")

# One fixed colour per sport group, used by every view (light theme, dark theme).
SPORT_COLORS = {
    "run": ("#2a78d6", "#3987e5"), "trail": ("#eb6834", "#d95926"), "walk": ("#1baf7a", "#199e70"),
    "tennis": ("#eda100", "#c98500"), "snow": ("#e87ba4", "#d55181"), "cycle": ("#008300", "#008300"),
    "sail": ("#6250d6", "#9085e9"), "other": ("#8a8f98", "#7f8b96"),
}

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
    "cycling": "cycle",
    "road_biking": "cycle",
    "mountain_biking": "cycle",
    "gravel_cycling": "cycle",
    "cyclocross": "cycle",
    "indoor_cycling": "cycle",
    "virtual_ride": "cycle",
    "e_bike_fitness": "cycle",
    "e_bike_mountain": "cycle",
    "e_biking": "cycle",
    "bmx": "cycle",
    "sailing": "sail",
    "sail_race": "sail",
    "sail_expedition": "sail",
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


def regroup_activities(s) -> int:
    """Re-apply the sport groups to every stored activity (after the groups change). Returns how many moved."""
    from sqlalchemy import select
    from .models import Activity
    moved = 0
    for a in s.scalars(select(Activity)):
        new = normalize_sport(a.garmin_sport, a.garmin_sub_sport)
        if new != a.sport and not (new == "other" and a.garmin_sport is None):
            a.sport = new
            moved += 1
    return moved
