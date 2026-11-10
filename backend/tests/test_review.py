"""Year in Review."""
import importlib
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from gla.analytics import review as rv
from gla.models import Activity, DerivedMetric


@pytest.mark.parametrize("name,place", [
    ("Timisoara Walking", "Timisoara"),
    ("Timişoara Repriză de mers pe jos", "Timişoara"),
    ("Timisoara - Base", "Timisoara"),
    ("Brus Resort Skiing/Snowboarding", "Brus"),
    ("Sânmihaiu Român Ciclism", "Sânmihaiu Român"),
    ("Arad Running stafeta 3x7.5", "Arad"),
    ("Baile Herculane - Hercules Semi 2025", "Baile Herculane"),
    ("Sant Josep de sa Talaia Mers pe jos", "Sant Josep de sa Talaia"),
    ("Tennis", None), ("Treadmill Running", None), ("Alergare pe bandă", None), ("Înot în bazin", None), (None, None),
])
def test_place_from_activity_name(name, place):
    assert rv.place_of(name) == place


def test_same_place_with_and_without_diacritics():
    assert rv.fold("Timişoara") == rv.fold("Timisoara") == "timisoara"
    assert rv.fold("Țarcu") == "tarcu"


def test_default_year_is_the_latest_full_year():
    assert rv.default_year([2023, 2024, 2025, 2026], date(2026, 11, 10)) == 2025
    assert rv.default_year([2026], date(2026, 11, 10)) == 2026
    assert rv.default_year([], date(2026, 11, 10)) is None


def _run(s, i, day, secs5k):
    a = Activity(id=i, dedup_key=f"k{i}", sport="run", name=f"Timisoara Running {i}", start_utc=datetime(day.year, day.month, day.day, 6),
                 tz_offset_min=120, elapsed_s=1800, timer_s=1800, distance_m=6000, has_gps=True, has_streams=True, source="test",
                 updated_at=datetime(2026, 1, 1))
    s.add(a)
    s.add(DerivedMetric(activity_id=i, metric="best_5k", value=secs5k, method="t"))


def test_records_count_personal_bests_set_that_year(sessions):
    with sessions() as s:
        _run(s, 1, date(2024, 3, 1), 1500)
        _run(s, 2, date(2025, 3, 1), 1490)       # personal best
        _run(s, 3, date(2025, 6, 1), 1495)       # not
        _run(s, 4, date(2025, 9, 1), 1450)       # personal best again
        _run(s, 5, date(2026, 4, 1), 1420)       # the best ever, a year later
        s.commit()
        rec = {r["distance"]: r for r in rv._records(s, 2025)}["best_5k"]
    assert rec["seconds"] == 1450 and rec["date"] == "2025-09-01" and not rec["all_time"]
    assert [p["improved_by"] for p in rec["personal_bests"]] == [10, 40]


def test_year_review_endpoint(analyzed, monkeypatch):
    settings, _ = analyzed
    monkeypatch.setenv("GLA_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("GLA_DATABASE_URL", settings.database_url)
    import gla.api
    api = importlib.reload(gla.api)
    c = TestClient(api.app)
    r = c.get("/api/year-review").json()                  # the export ends in 2024: that is the latest full year
    assert r["year"] == 2024 and r["years"] == [2019, 2024]
    t = r["totals"]
    assert t["activities"] == 6 and t["active_days"] == 6
    assert {b["sport"] for b in t["by_sport"]} == {"run", "trail", "tennis", "walk", "snow"}
    assert sum(m["activities"] for m in r["months"]) == 6
    assert r["biggest_day"]["date"] == "2024-01-20"         # four hours of snowboarding
    assert r["previous"] is None and r["tennis"]["sessions"] == 1 and r["snow"]["days"] == 1
    assert r["tiles"]["new"] > 0 and r["first"]["date"] == "2024-01-20"
    assert c.get("/api/year-review?year=2019").json()["totals"]["activities"] == 1
    assert c.get("/api/year-review?year=2001").status_code == 404


def test_home_endpoint(analyzed, monkeypatch):
    settings, _ = analyzed
    monkeypatch.setenv("GLA_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("GLA_DATABASE_URL", settings.database_url)
    import gla.api
    api = importlib.reload(gla.api)
    h = TestClient(api.app).get("/api/home").json()
    assert h["empty"] is False and h["lifetime"]["activities"] == 7
    assert h["tiles"]["visited"] > 0 and h["tennis"]["sessions"] == 1 and h["snow"]["days_on_snow"] == 1
    assert h["year"]["year"] == 2024 and len(h["latest"]) == 5
    assert h["latest"][0]["date"] >= h["latest"][-1]["date"]
    assert set(h["tonight"]) == {"sleep_score", "hrv"} and h["tonight"]["sleep_score"]["ready"] is False


def test_home_before_any_import(settings, monkeypatch):
    monkeypatch.setenv("GLA_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("GLA_DATABASE_URL", settings.database_url)
    import gla.api
    api = importlib.reload(gla.api)
    assert TestClient(api.app).get("/api/home").json() == {"empty": True, "health_days": 0}
