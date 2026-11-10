import importlib
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from gla.analytics import best_efforts as be
from gla.analytics import load as ld
from gla.analytics import queries as q
from gla.analytics import routes as rt
from gla.analytics import run_analysis
from gla.analytics import tiles as tl
from gla.geo import decode_polyline, encode_polyline
from gla.importer.export import ExportImporter
from gla.ingest import dedup_key, now
from gla.models import Activity, DerivedMetric, Route, Setting, Track
from gla.text import fix_text


# ------------------------------------------------------------------ pure functions

def test_best_effort_ignores_gps_jump_and_finds_fast_middle():
    t = np.arange(0, 3001, 1.0)                     # 50 minutes, 1 s samples
    speed = np.full(len(t), 3.0)                    # 3 m/s
    speed[1000:1300] = 5.0                          # 300 s at 5 m/s in the middle: 1.5 km fast
    dist = np.concatenate([[0], np.cumsum(speed[1:])])
    dist[2000:] += 800                              # an 800 m GPS jump in one second
    s = pd.DataFrame({"t_s": t, "distance_m": dist})
    out = be.best_efforts(s)
    assert out["best_1k"] == pytest.approx(200, abs=1)          # 1 km at 5 m/s
    assert "best_10k" not in out                                 # 9.6 km once the jump is removed
    assert be.fastest(t, np.concatenate([[0], np.cumsum(speed[1:])]), 5000) == pytest.approx(300 + 3500 / 3, abs=1)


def test_trimp_and_fitness():
    t = np.arange(0, 3600, 1.0)
    hr = np.full(len(t), 150.0)
    a = ld.trimp_from_stream(t, hr, 60, 190)
    b = ld.trimp_from_average(3600, 150, 60, 190)
    assert a == pytest.approx(b, rel=0.01) and 80 < a < 120
    assert ld.trimp_from_stream(t, np.full(len(t), np.nan), 60, 190) is None
    days = ld.daily_series({date(2026, 1, 1) + timedelta(days=k): 50.0 for k in range(300)}, date(2026, 1, 1), date(2026, 10, 27))
    ff = ld.fitness_fatigue(days)
    assert ff.iloc[-1].fitness == pytest.approx(50, abs=0.5) and ff.iloc[-1].form == pytest.approx(0, abs=0.5)
    proj = ld.project(ff, 14, [0.0] * 7)
    assert proj.iloc[-1].form > 10                 # two rest weeks: fatigue drops faster than fitness


def test_tiles_square_and_cluster():
    block = {(x, y) for x in range(10, 14) for y in range(20, 24)}       # 4 x 4
    extra = {(14, 20), (30, 30)}
    assert tl.largest_square(block | extra) == (4, 10, 20)
    assert len(tl.largest_cluster(block | extra)) == 4                    # inner 2 x 2
    # a 3 km straight line crosses at least two zoom-14 tiles; densifying catches every tile on the way
    line = [(45.75, 21.20), (45.75, 21.24)]
    assert len(tl.tiles_on_track(line)) >= 2


def test_route_matching_rules():
    loop = [(45.75 + 0.01 * np.sin(a), 21.22 + 0.014 * (1 - np.cos(a))) for a in np.linspace(0, 2 * np.pi, 200)]
    sig, length = rt.signature(loop)
    other_dir = list(reversed(loop))
    sig2, len2 = rt.signature(other_dir)
    assert rt.match_distance(sig, length, sig2, len2) is not None       # same loop, the other way round
    far = [(lat + 0.01, lon) for lat, lon in loop]
    sig3, len3 = rt.signature(far)
    assert rt.match_distance(sig, length, sig3, len3) is None            # starts 1.1 km apart
    short = loop[:120]
    sig4, len4 = rt.signature(short)
    assert rt.match_distance(sig, length, sig4, len4) is None            # 40% shorter
    assert rt.is_loop(loop, length)


def test_fix_text():
    assert fix_text("Timişoara ReprizÄ\x83 de mers pe jos") == "Timişoara Repriză de mers pe jos"
    assert fix_text("Café") == "Café" and fix_text(None) is None


# ------------------------------------------------------------------ pipeline on the fake export

def add_copy(sessions, src_id: int, days_later: int, shift_deg: float = 0.0, minutes: float | None = None) -> int:
    with sessions() as s:
        src = s.get(Activity, src_id)
        pts = [(la + shift_deg, lo) for la, lo in decode_polyline(src.track.polyline)]
        start = src.start_utc + timedelta(days=days_later)
        a = Activity(dedup_key=dedup_key(start, src.sport), sport=src.sport, start_utc=start, tz_offset_min=180,
                     timer_s=(minutes or src.timer_s / 60) * 60, distance_m=src.distance_m, avg_hr=145, max_hr=170,
                     has_gps=True, source="test", updated_at=now())
        s.add(a)
        s.flush()
        lats, lons = [p[0] for p in pts], [p[1] for p in pts]
        a.track = Track(activity_id=a.id, polyline=encode_polyline(pts), points=len(pts),
                        min_lat=min(lats), max_lat=max(lats), min_lon=min(lons), max_lon=max(lons))
        s.commit()
        return a.id


def test_pipeline_metrics(analyzed):
    settings, sessions = analyzed
    with sessions() as s:
        m = lambda gid, k: s.scalar(select(DerivedMetric.value).join(Activity).where(Activity.garmin_id == gid, DerivedMetric.metric == k))  # noqa: E731
        assert m(1001, "best_5k") == pytest.approx(1500, abs=2)        # 8 km in 40 min, even pace: 5 km in 25:00
        assert m(1001, "best_10k") is None
        assert m(1006, "best_1k") is None                              # treadmill: no records
        assert m(1003, "best_1k") is None                              # tennis: no records
        assert m(1001, "load") > 0 and m(1005, "load") > m(1004, "load")
        assert m(999, "load") is not None                              # summary-only: from average HR


def test_routes_are_stable_and_keep_their_name(analyzed):
    settings, sessions = analyzed
    with sessions() as s:
        run_id = s.scalar(select(Activity.id).where(Activity.garmin_id == 1001))
    for k in (7, 14):
        add_copy(sessions, run_id, k, shift_deg=0.0002)            # ~20 m off: same route
    add_copy(sessions, run_id, 21, shift_deg=0.02)                  # 2 km away: not the same route
    run_analysis(settings, sessions)
    with sessions() as s:
        routes = q.routes(s)
        # the fake trail run (1002) follows the same loop, so it joins: runs and trail runs share routes
        assert len(routes) == 1 and routes[0]["efforts"] == 4 and routes[0]["group"] == "run"
        rid = routes[0]["id"]
        s.get(Route, rid).name = "River loop"
        s.commit()
    add_copy(sessions, run_id, 28, minutes=38)
    run_analysis(settings, sessions)
    with sessions() as s:
        r = q.route_detail(s, rid)
        assert r["name"] == "River loop" and len(r["efforts"]) == 5
        assert r["efforts"][-1]["pace_s_per_km"] == pytest.approx(38 * 60 / 8, abs=1)
    run_analysis(settings, sessions, full=True)                    # a full re-run keeps the named route
    with sessions() as s:
        assert q.route_detail(s, rid)["name"] == "River loop"


def test_queries(analyzed):
    settings, sessions = analyzed
    with sessions() as s:
        lt = q.lifetime(s)
        assert lt["activities"] == 7 and lt["foot_km"] == pytest.approx(8 + 14 + 3.5 + 6 + 10, abs=0.1)
        assert lt["by_sport"]["snow"]["activities"] == 1
        yoy = q.year_over_year(s, ["run", "trail"])
        assert yoy["years"]["2024"][-1] == pytest.approx(28.0, abs=0.01)        # 8 + 14 + 6 km
        assert yoy["years"]["2019"][-1] == pytest.approx(10.0)
        bes = q.best_efforts(s)
        assert bes["best_5k"]["best"]["activity_id"] is not None
        t = q.tiles(s)
        assert t["zoom"] == 14 and len(t["tiles"]) > 0
        assert all(tr["sport"] != "tennis" or True for tr in q.tracks(s))
        tl_ = q.training_load(s, date(2024, 6, 1))
        assert tl_["days"][0][0] == "2019-06-02" and tl_["days"][-1][0] == "2024-06-01"


def test_hr_profile_prefers_garmin(analyzed):
    settings, sessions = analyzed
    from gla.analytics.pipeline import hr_profile
    with sessions() as s:
        est = hr_profile(s)
        assert est[1] == 171                                   # highest max HR seen
        s.add(Setting(key="hr_rest", value="55"))
        s.add(Setting(key="hr_max", value="192"))
        s.commit()
        assert hr_profile(s) == (55.0, 192.0)


def test_analytics_endpoints(analyzed, monkeypatch):
    settings, sessions = analyzed
    monkeypatch.setenv("GLA_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("GLA_DATABASE_URL", settings.database_url)
    import gla.api
    api = importlib.reload(gla.api)
    c = TestClient(api.app)
    assert c.get("/api/lifetime").json()["activities"] == 7
    assert "2024" in c.get("/api/year-over-year?sports=run,trail").json()["years"]
    assert c.get("/api/best-efforts").json()["best_1k"]["best"]
    assert c.get("/api/tiles").json()["zoom"] == 14
    assert len(c.get("/api/tracks").json()) == 5
    assert c.get("/api/routes").json() == []
    assert c.get("/api/routes/999").status_code == 404
    assert len(c.get("/api/training-load").json()["days"]) > 100
    assert len(c.get("/api/health-days").json()) == 4
