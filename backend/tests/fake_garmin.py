"""A stand-in for the Garmin Personal API, answering in the shapes the real API uses."""
from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta, timezone

from fake_export import make_fit
from fit_tool.profile.profile_type import Sport, SubSport

# (activity id, type key, start UTC, minutes, km, file kind)
API_ACTIVITIES = [
    (2001, "running", datetime(2026, 11, 2, 5, 0), 45, 9.0, "fit"),
    (2002, "tennis", datetime(2026, 11, 4, 17, 30), 80, 4.5, "fit"),
    (2003, "walking", datetime(2026, 11, 6, 15, 0), 30, 2.5, "gpx"),   # uploaded GPX: no FIT inside
]
SPORTS = {"running": (Sport.RUNNING, SubSport.GENERIC), "tennis": (Sport.TENNIS, SubSport.GENERIC)}


def _ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


class FakeGarmin:
    def __init__(self, activities=API_ACTIVITIES, fail_on: str | None = None, extra: list | None = None):
        self.activities = list(activities) + list(extra or [])
        self.fail_on = fail_on
        self.downloads: list[int] = []
        self.calls: list[str] = []

    def _maybe_fail(self, name):
        self.calls.append(name)
        if self.fail_on == name:
            raise ConnectionError(f"simulated failure in {name}")

    def search_activities(self, *, start, limit, start_date, end_date):
        self._maybe_fail("search_activities")
        rows = []
        for gid, key, st, minutes, km, _ in self.activities:
            if start_date <= st.date() <= end_date:
                rows.append({"activityId": gid, "activityName": f"API {gid}", "activityType": {"typeKey": key},
                             "startTimeGMT": st.strftime("%Y-%m-%d %H:%M:%S"),
                             "startTimeLocal": (st + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
                             "distance": km * 1000, "duration": minutes * 60.0, "movingDuration": minutes * 60.0,
                             "averageHR": 130.0, "maxHR": 160.0})
        rows.sort(key=lambda r: r["startTimeGMT"], reverse=True)
        return rows[start:start + limit]

    def download_activity(self, activity_id):
        self._maybe_fail("download_activity")
        self.downloads.append(activity_id)
        gid, key, st, minutes, km, kind = next(a for a in self.activities if a[0] == activity_id)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            if kind == "fit":
                sport, sub = SPORTS[key]
                z.writestr(f"{gid}_ACTIVITY.fit", make_fit(sport, sub, st, minutes, km, True, tz_hours=2))
            else:
                z.writestr(f"{gid}.gpx", "<gpx/>")
        return buf.getvalue()

    def get_daily_sleep(self, day: date):
        self._maybe_fail("get_daily_sleep")
        start = datetime.combine(day, datetime.min.time()) - timedelta(hours=2)   # 22:00 UTC the evening before
        return {"dailySleepDTO": {"calendarDate": day.isoformat(), "sleepStartTimestampGMT": _ms(start),
                                  "sleepEndTimestampGMT": _ms(start + timedelta(hours=7)),
                                  "deepSleepSeconds": 5000, "lightSleepSeconds": 14000, "remSleepSeconds": 5000,
                                  "sleepScores": {"overall": {"value": 80, "qualifierKey": "GOOD"}}},
                "avgOvernightHrv": 55.0, "sleepMovement": [{"startGMT": "x", "activityLevel": 1.0}]}

    def get_daily_hrv(self, day: date):
        self._maybe_fail("get_daily_hrv")
        return {"hrvSummary": {"calendarDate": day.isoformat(), "lastNightAvg": 57, "weeklyAvg": 54},
                "hrvReadings": [{"hrvValue": 60}]}

    def get_daily_summaries(self, start_date, end_date):
        self._maybe_fail("get_daily_summaries")
        out, d = [], start_date
        while d <= end_date:
            out.append({"calendarDate": d.isoformat(), "restingHeartRate": 51, "totalSteps": 8000})
            d += timedelta(days=1)
        return {"data": out}

    def get_heart_rate_zones(self):
        self._maybe_fail("get_heart_rate_zones")
        return [{"sport": "RUNNING", "maxHeartRateUsed": 190, "restingHeartRateUsed": 50},
                {"sport": "DEFAULT", "maxHeartRateUsed": 188, "restingHeartRateUsed": 52}]
