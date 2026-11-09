"""Build a small fake Garmin account export for tests, shaped like the real one."""
from __future__ import annotations

import io
import json
import math
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.activity_message import ActivityMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.record_message import RecordMessage
from fit_tool.profile.messages.session_message import SessionMessage
from fit_tool.profile.profile_type import FileType, Manufacturer, Sport, SubSport

FIT_EPOCH_S = 631065600  # 1989-12-31T00:00:00Z
HOME = (45.6427, 25.5887)

# (garmin id, sport, sub sport, start UTC, minutes, km, has gps)
ACTIVITIES = [
    (1001, Sport.RUNNING, SubSport.GENERIC, datetime(2024, 5, 1, 5, 0), 40, 8.0, True),
    (1002, Sport.RUNNING, SubSport.TRAIL, datetime(2024, 5, 4, 6, 30), 90, 14.0, True),
    (1003, Sport.TENNIS, SubSport.GENERIC, datetime(2024, 5, 8, 16, 30), 75, 4.2, True),
    (1004, Sport.WALKING, SubSport.GENERIC, datetime(2024, 5, 9, 15, 0), 45, 3.5, True),
    (1005, Sport.SNOWBOARDING, SubSport.GENERIC, datetime(2024, 1, 20, 8, 0), 240, 30.0, True),
    (1006, Sport.RUNNING, SubSport.TREADMILL, datetime(2024, 2, 2, 17, 0), 30, 6.0, False),
]
SUMMARY_ONLY = (999, "running", datetime(2019, 6, 2, 6, 0), 50, 10.0)


def _ms(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def make_fit(sport, sub_sport, start: datetime, minutes: int, km: float, gps: bool, tz_hours: int = 3) -> bytes:
    b = FitFileBuilder(auto_define=True)
    fid = FileIdMessage()
    fid.type = FileType.ACTIVITY
    fid.manufacturer = Manufacturer.GARMIN.value
    fid.product = 1
    fid.serial_number = 3_000_000_000
    fid.time_created = _ms(start)
    b.add(fid)
    n = minutes * 6  # one record every 10 s keeps files small
    speed = km * 1000 / (minutes * 60)
    for i in range(n + 1):
        r = RecordMessage()
        r.timestamp = _ms(start + timedelta(seconds=10 * i))
        if gps:
            ang = 2 * math.pi * i / n
            r.position_lat = HOME[0] + 0.01 * math.sin(ang)
            r.position_long = HOME[1] + 0.014 * (1 - math.cos(ang))
        r.distance = speed * 10 * i
        r.speed = speed
        r.heart_rate = 140
        r.altitude = 600 + 20 * math.sin(i / 10)
        b.add(r)
    end = start + timedelta(minutes=minutes)
    s = SessionMessage()
    s.timestamp = _ms(end)
    s.start_time = _ms(start)
    s.sport = sport
    s.sub_sport = sub_sport
    s.total_elapsed_time = minutes * 60
    s.total_timer_time = minutes * 60
    s.total_distance = km * 1000
    s.total_ascent = 120
    s.avg_heart_rate = 140
    s.max_heart_rate = 171
    s.enhanced_max_speed = speed * 1.6
    b.add(s)
    a = ActivityMessage()
    a.timestamp = _ms(end)
    a.local_timestamp = int((end + timedelta(hours=tz_hours)).replace(tzinfo=timezone.utc).timestamp()) - FIT_EPOCH_S
    a.num_sessions = 1
    b.add(a)
    return b.build().to_bytes()


def make_settings_fit() -> bytes:
    b = FitFileBuilder(auto_define=True)
    fid = FileIdMessage()
    fid.type = FileType.SETTINGS
    fid.manufacturer = Manufacturer.GARMIN.value
    fid.product = 1
    fid.serial_number = 1
    fid.time_created = _ms(datetime(2024, 1, 1))
    b.add(fid)
    return b.build().to_bytes()


def summaries_json() -> bytes:
    rows = []
    for gid, sport, sub, start, minutes, km, _ in ACTIVITIES:
        key = "trail_running" if sub == SubSport.TRAIL else sport.name.lower()
        rows.append({"activityId": gid, "name": f"Activity {gid}", "activityType": key,
                     "startTimeGmt": _ms(start) + 4000, "startTimeLocal": _ms(start + timedelta(hours=3)),
                     "duration": minutes * 60_000, "distance": km * 100_000})
    gid, key, start, minutes, km = SUMMARY_ONLY
    rows.append({"activityId": gid, "name": "Old run without a file", "activityType": {"typeKey": key},
                 "startTimeGmt": _ms(start), "startTimeLocal": _ms(start + timedelta(hours=3)),
                 "duration": minutes * 60_000, "distance": km * 100_000, "elevationGain": 4500.0, "avgHr": 150})
    return json.dumps([{"summarizedActivitiesExport": rows}]).encode()


def sleep_json() -> bytes:
    rows = []
    for d in range(3):
        day = datetime(2024, 5, 2) + timedelta(days=d)
        start = day - timedelta(hours=3, minutes=50)   # 20:10 UTC = 23:10 local
        rows.append({"calendarDate": day.strftime("%Y-%m-%d"),
                     "sleepStartTimestampGMT": start.strftime("%Y-%m-%dT%H:%M:%S.0"),
                     "sleepEndTimestampGMT": (start + timedelta(hours=7, minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.0"),
                     "deepSleepSeconds": 5400, "lightSleepSeconds": 15000, "remSleepSeconds": 5400,
                     "awakeSleepSeconds": 1200, "avgOvernightHrv": 52.0 + d,
                     "sleepScores": {"overall": {"value": 78 + d}}})
    return json.dumps(rows).encode()


def uds_json() -> bytes:
    return json.dumps([{"calendarDate": f"2024-05-0{d}", "restingHeartRate": 50 + d, "totalSteps": 9000}
                       for d in range(2, 6)]).encode()


def build_export(dest: Path) -> Path:
    """Write <dest>/export.zip and return its path."""
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as z:
        for gid, sport, sub, start, minutes, km, gps in ACTIVITIES:
            z.writestr(f"user_{gid}.fit", make_fit(sport, sub, start, minutes, km, gps))
        z.writestr("user_settings.fit", make_settings_fit())
        z.writestr("user_9999.gpx", "<gpx/>")
    path = dest / "export.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("DI_CONNECT/DI-Connect-Uploaded-Files/UploadedFiles_0-_Part1.zip", inner.getvalue())
        z.writestr("DI_CONNECT/DI-Connect-Fitness/user_0_summarizedActivities.json", summaries_json())
        z.writestr("DI_CONNECT/DI-Connect-Wellness/2024-04-20_2024-07-29_1_sleepData.json", sleep_json())
        z.writestr("DI_CONNECT/DI-Connect-Aggregator/UDSFile_2024-04-20_2024-07-29.json", uds_json())
        z.writestr("DI_CONNECT/DI-Connect-User/user_profile.json", "{}")
    return path
