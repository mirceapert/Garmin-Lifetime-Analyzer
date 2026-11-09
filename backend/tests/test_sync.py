from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fake_garmin import FakeGarmin
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from gla.garmin_api import KeyRejected, LiveGarmin, fit_files_in
from gla.importer.export import ExportImporter
from gla.models import Activity, DailyHealth, RawFile, SyncRun
from gla.sync import ApiSync, SyncBusy, SyncFailed, find_hr_profile, parse_api_activity, sync_status
from gla.worker import is_due

SINCE, UNTIL = date(2026, 11, 1), date(2026, 11, 8)


@pytest.fixture
def keyed(settings):
    return replace(settings, garmin_api_key="test-key", timezone="Europe/Bucharest", sync_time=time(6, 30))


def make_sync(settings, sessions, fake):
    return ApiSync(settings, sessions, source_factory=lambda _s: fake)


def n(sessions, model, *where):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(model).where(*where))


def test_first_sync_adds_activities_health_and_profile(keyed, sessions):
    fake = FakeGarmin()
    report = make_sync(keyed, sessions, fake).run(SINCE, UNTIL)
    assert report["activities_added"] == 2
    assert report["activities_added_summary_only"] == 1
    assert report["health_days_added"] == 8
    with sessions() as s:
        run = s.scalar(select(Activity).where(Activity.garmin_id == 2001))
        assert run.sport == "run" and run.source == "api" and run.name == "API 2001"
        assert run.has_gps and run.has_streams and run.tz_offset_min == 120
        tennis = s.scalar(select(Activity).where(Activity.garmin_id == 2002))
        assert tennis.sport == "tennis" and tennis.track is not None
        walk = s.scalar(select(Activity).where(Activity.garmin_id == 2003))
        assert walk.source == "api-summary" and walk.distance_m == 2500 and walk.timer_s == 1800 and not walk.has_gps
        d = s.get(DailyHealth, date(2026, 11, 5))
        assert d.sleep_score == 80 and d.sleep_s == 24000 and d.resting_hr == 51
        assert d.hrv_night_ms == 57          # the HRV summary wins over the sleep endpoint's average
        assert d.sleep_start_utc == datetime(2026, 11, 4, 22, 0)
    st = sync_status(keyed, sessions)
    assert st["synced_through"] == "2026-11-08"
    assert st["heart_rate_profile"] == {"max": 188.0, "rest": 52.0}
    assert st["last_run"]["status"] == "ok"


def test_second_sync_downloads_nothing_new(keyed, sessions):
    fake = FakeGarmin()
    make_sync(keyed, sessions, fake).run(SINCE, UNTIL)
    before = (n(sessions, Activity), n(sessions, RawFile, RawFile.kind == "fit"))
    fake2 = FakeGarmin()
    report = make_sync(keyed, sessions, fake2).run(SINCE, UNTIL)
    assert fake2.downloads == []            # nothing is downloaded twice
    assert report.get("activities_added", 0) == 0 and report["activities_already_had"] == 3
    assert (n(sessions, Activity), n(sessions, RawFile, RawFile.kind == "fit")) == before
    assert report["health_days_updated"] == 8


def test_export_activities_are_not_downloaded_again(keyed, sessions, export_zip):
    ExportImporter(keyed, sessions).run(export_zip)
    exported = (1001, "running", datetime(2024, 5, 1, 5, 0), 40, 8.0, "fit")
    fake = FakeGarmin(activities=[exported])
    make_sync(keyed, sessions, fake).run(date(2024, 4, 30), date(2024, 5, 2))
    assert fake.downloads == []
    assert n(sessions, Activity) == 7


def test_default_window_starts_after_the_export(keyed, sessions, export_zip):
    ExportImporter(keyed, sessions).run(export_zip)
    fake = FakeGarmin(activities=[])
    report = make_sync(keyed, sessions, fake).run(until=date(2024, 5, 12))
    assert report["window"] == ["2024-05-08", "2024-05-12"]   # newest export activity was 9 May


def test_failed_sync_changes_nothing(keyed, sessions):
    fake = FakeGarmin(fail_on="get_daily_hrv")
    with pytest.raises(SyncFailed):
        make_sync(keyed, sessions, fake).run(SINCE, UNTIL)
    assert n(sessions, Activity) == 0 and n(sessions, DailyHealth) == 0
    with sessions() as s:
        run = s.scalar(select(SyncRun))
        assert run.status == "failed" and "simulated failure" in run.error
    assert sync_status(keyed, sessions)["synced_through"] is None


def test_rejected_key_shows_in_status(keyed, sessions):
    def factory(_s):
        raise KeyRejected("Garmin rejected the API key.")
    with pytest.raises(SyncFailed):
        ApiSync(keyed, sessions, source_factory=factory).run(SINCE, UNTIL)
    st = sync_status(keyed, sessions)
    assert st["key"]["state"] == "rejected"
    assert any(w["level"] == "critical" for w in st["warnings"])


def test_only_one_sync_at_a_time(keyed, sessions):
    sync = make_sync(keyed, sessions, FakeGarmin())
    sync.start_run()
    with pytest.raises(SyncBusy):
        sync.start_run()
    with sessions() as s:                       # a run stuck for 3 hours is treated as abandoned
        r = s.scalar(select(SyncRun))
        r.started_at -= timedelta(hours=3)
        s.commit()
    sync.start_run()
    with sessions() as s:
        assert s.scalar(select(SyncRun).where(SyncRun.id == 1)).status == "failed"


@pytest.mark.parametrize("days_left,state,level", [(30, "ok", None), (5, "expiring", "warning"), (-1, "expired", "critical")])
def test_key_expiry_warnings(keyed, sessions, days_left, state, level):
    today = datetime.now(ZoneInfo("Europe/Bucharest")).date()
    st = sync_status(replace(keyed, garmin_api_key_expires=today + timedelta(days=days_left)), sessions)
    assert st["key"]["state"] == state and st["key"]["days_left"] == days_left
    levels = [w["level"] for w in st["warnings"]]
    assert (level in levels) if level else levels == []


def test_missing_key_warning(settings, sessions):
    st = sync_status(settings, sessions)
    assert st["key"]["state"] == "missing" and st["warnings"][0]["level"] == "critical"


def test_worker_schedule(keyed, sessions):
    tz = ZoneInfo("Europe/Bucharest")
    day = datetime.now(tz).date()
    at = lambda h, m: datetime.combine(day, time(h, m), tzinfo=tz)  # noqa: E731
    assert not is_due(keyed, sessions, at(6, 0))
    assert is_due(keyed, sessions, at(6, 31))

    def add_run(local_h, local_m, status):
        with sessions() as s:
            started = at(local_h, local_m).astimezone(timezone.utc).replace(tzinfo=None)
            s.add(SyncRun(kind="api_sync", started_at=started, finished_at=started, status=status))
            s.commit()
    add_run(6, 31, "failed")
    assert not is_due(keyed, sessions, at(6, 45))     # wait 30 minutes before retrying
    assert is_due(keyed, sessions, at(7, 2))
    add_run(7, 2, "failed")
    add_run(7, 33, "failed")
    assert not is_due(keyed, sessions, at(9, 0))      # three failures: give up until tomorrow
    assert not is_due(replace(keyed, garmin_api_key=None), sessions, at(6, 31))


def test_worker_not_due_after_success(keyed, sessions):
    tz = ZoneInfo("Europe/Bucharest")
    day = datetime.now(tz).date()
    started = datetime.combine(day, time(6, 31), tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
    with sessions() as s:
        s.add(SyncRun(kind="api_sync", started_at=started, finished_at=started, status="ok"))
        s.commit()
    assert not is_due(keyed, sessions, datetime.combine(day, time(12, 0), tzinfo=tz))


def test_parse_helpers():
    a = parse_api_activity({"activityId": 5, "activityName": "Trail", "activityType": {"typeKey": "trail_running"},
                            "startTimeGMT": "2026-05-01 05:00:00", "startTimeLocal": "2026-05-01 08:00:00",
                            "distance": 12000.0, "duration": 4000.0, "elevationGain": 600.0})
    assert a["sport"] == "trail" and a["tz_offset_min"] == 180 and a["distance_m"] == 12000 and a["ascent_m"] == 600
    assert parse_api_activity({"activityName": "no id"}) is None
    assert find_hr_profile({"zones": [{"sport": "DEFAULT", "maxHeartRateUsed": 186, "restingHeartRateUsed": 48}]}) == {"hr_max": 186.0, "hr_rest": 48.0}
    assert find_hr_profile({}) == {}


def test_fit_files_in():
    import io
    import zipfile
    from fake_export import make_fit
    from fit_tool.profile.profile_type import Sport, SubSport
    fit = make_fit(Sport.RUNNING, SubSport.GENERIC, datetime(2026, 1, 1, 8), 10, 2.0, True)
    assert fit_files_in(fit) == [("activity.fit", fit)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("123_ACTIVITY.fit", fit)
        z.writestr("readme.txt", "x")
    assert fit_files_in(buf.getvalue()) == [("123_ACTIVITY.fit", fit)]
    assert fit_files_in(b"not a zip") == []


class _Err(Exception):
    pass


def test_live_client_retries_and_refreshes():
    from garmin_personal_api import HttpError
    live = LiveGarmin.__new__(LiveGarmin)
    live._pause, live._retries, live._sleep = 0, 3, lambda s: None
    tokens = []
    live._token = lambda force: tokens.append(force) or "t2"

    class Client:
        def __init__(self):
            self.n = 0
            self.token = None

        def update_bearer_token(self, t):
            self.token = t

        def flaky(self):
            self.n += 1
            if self.n == 1:
                raise HttpError(status_code=429, method="GET", url="u", response_text="slow down")
            if self.n == 2:
                raise HttpError(status_code=401, method="GET", url="u", response_text="expired token")
            return "ok"

        def missing(self):
            raise HttpError(status_code=404, method="GET", url="u", response_text="")

        def forbidden(self):
            raise HttpError(status_code=403, method="GET", url="u", response_text="")

    live._client = Client()
    assert live._call(live._client.flaky) == "ok"
    assert tokens == [True] and live._client.token == "t2"
    assert live._call(live._client.missing) is None
    with pytest.raises(KeyRejected):
        live._call(live._client.forbidden)


def test_api_sync_endpoints(settings, sessions, monkeypatch):
    import importlib
    monkeypatch.setenv("GLA_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("GLA_DATABASE_URL", settings.database_url)
    monkeypatch.delenv("GARMIN_API_KEY", raising=False)
    import gla.api
    api = importlib.reload(gla.api)
    client = TestClient(api.app)
    assert client.post("/api/sync").status_code == 400
    st = client.get("/api/sync/status").json()
    assert st["key"]["state"] == "missing" and st["last_run"] is None and "next_scheduled_local" in st
