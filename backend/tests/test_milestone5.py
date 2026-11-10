"""Tennis courts, snowboard seasons, sleep drivers, recovery and forecasts."""
import importlib
import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from gla.analytics import forecast as fc
from gla.analytics import sleep as sl
from gla.analytics import snow as sn
from gla.analytics import tennis as tn
from gla.sports import normalize_sport

COURT = (45.7486, 21.2322)


# ------------------------------------------------------------------ sports

def test_table_tennis_is_not_tennis():
    assert normalize_sport("tennis", "97") == "other"
    assert normalize_sport("tennis", "table_tennis") == "other"
    assert normalize_sport("racket", "padel") == "other"
    assert normalize_sport("tennis", "generic") == "tennis"
    assert normalize_sport("tennis", None) == "tennis"


# ------------------------------------------------------------------ tennis

def fake_session(seed: int, net_shift=(0.0, 0.0), minutes=60, one_end_share=0.5, gps_spike=False,
                 right_m=0.0) -> pd.DataFrame:
    """A player on a court whose long axis points north: at the south end (facing north) the right is
    east, at the north end (facing south) it is west. He stays right_m to his right of the centre line,
    alternates ends, and walks to the net posts at changeovers."""
    rng = np.random.default_rng(seed)
    n = minutes * 30                                             # one point every 2 s
    t = np.arange(n) * 2.0
    end = np.where((t // 600) % 2 == 0, -1, 1)                   # change ends every 10 minutes
    if one_end_share != 0.5:
        end = np.where(rng.random(n) < one_end_share, -1, 1)
    depth = rng.normal(12.5, 1.5, n)
    north = end * depth                                          # metres north of the net
    east = -end * right_m + rng.normal(0, 2.0, n)                # his right: east at the south end, west at the north
    change = (t % 600) < 40                                      # changeover at the net post
    north[change] = rng.normal(0, 1.0, change.sum())
    east[change] = 6.5 + rng.normal(0, 0.5, change.sum())
    north += rng.normal(0, 1.5, n) + net_shift[1]
    east += net_shift[0]
    if gps_spike:
        north[100:103] += 2000
    lat = COURT[0] + np.degrees(north / tn.EARTH_R)
    lon = COURT[1] + np.degrees(east / (tn.EARTH_R * math.cos(math.radians(COURT[0]))))
    speed = np.abs(np.r_[0, np.diff(north)]) / 2.0
    return pd.DataFrame({"t_s": t, "lat": lat, "lon": lon, "speed_ms": speed,
                         "heart_rate": 120 + 20 * np.sin(t / 300)})


def test_court_found_from_sessions():
    streams = {i: fake_session(i) for i in range(1, 6)}
    streams[6] = fake_session(6, one_end_share=0.92)             # nearly all at one end: own fit is unreliable
    streams[7] = fake_session(7, gps_spike=True)
    streams[8] = fake_session(8, net_shift=(45.0, 0.0))          # the court next door but one
    streams[9] = fake_session(9, net_shift=(45.0, 0.0))
    fits = [tn.fit_session(i, s) for i, s in streams.items()]
    courts, member = tn.find_courts([f for f in fits if f])
    assert len(courts) == 2
    main = courts[member[1]]
    assert abs(main.lat - COURT[0]) * 111_000 < 1.5 and abs(main.lon - COURT[1]) * 78_000 < 1.5
    assert abs(math.degrees(main.angle) - 90) < 5
    assert member[6] == member[7] == member[1] and member[8] == member[9] != member[1]
    cov = tn.coverage(fits[0], main, streams[1])
    assert cov["base_share"] > 0.75 and 11 < cov["median_depth_m"] < 14
    assert 0.4 < cov["right_share"] < 0.6
    # the session mostly at one end still lands on the right net
    assert tn.coverage(fits[5], main, streams[6])["base_share"] > 0.7


def test_fold_puts_your_right_on_the_right_at_both_ends():
    court = tn.Court(COURT[0], COURT[1], math.pi / 2)
    s = fake_session(1, right_m=3.0)
    cov = tn.coverage(tn.fit_session(1, s), court, s)
    assert cov["right_share"] > 0.85
    grid = np.array(cov["grid"])
    assert grid.shape == (tn.DEPTH_M, 2 * tn.HALF_W_M)
    assert grid[11:14, tn.HALF_W_M:].sum() > grid[11:14, :tn.HALF_W_M].sum() * 3


def test_tennis_top_speed_ignores_spikes():
    sp = np.r_[np.full(500, 2.0), [40.0], np.full(500, 3.0)]
    assert tn.top_speed(sp) == pytest.approx(3.0)
    assert tn.top_speed(sp, garmin_max=4.2) == 4.2
    assert tn.top_speed(sp, garmin_max=26.0) == pytest.approx(3.0)    # Garmin's own spike


def test_tennis_per_minute():
    s = fake_session(3, minutes=5)
    pm = tn.per_minute(s)
    assert len(pm) == 5 and pm[0][0] == 0 and 100 < pm[0][1] < 150


# ------------------------------------------------------------------ snowboard

def lift_day(runs: int, drop=300.0, gaps=False) -> pd.Series:
    alt = []
    for _ in range(runs):
        alt += list(np.linspace(1500, 1500 + drop, 120))           # lift up
        alt += list(np.linspace(1500 + drop, 1500, 200))           # ride down
    s = pd.Series(alt) + np.random.default_rng(1).normal(0, 2, len(alt))
    if gaps:
        s[::3] = np.nan
    return s


def test_snow_runs_and_seasons():
    assert sn.count_runs(lift_day(4)) == 4
    assert sn.count_runs(lift_day(4, gaps=True)) is None             # altitude too patchy to count
    assert sn.season(date(2019, 1, 20)) == "2018/19" and sn.season(date(2024, 12, 2)) == "2024/25"
    assert sn.place("Saint-Gervais-les-Bains Resort Skiing/Snowboarding") == "Saint-Gervais-les-Bains"
    rows = [
        {"activity_id": 1, "day": date(2019, 1, 20), "name": "Saint-Gervais Resort Skiing", "distance_m": 30000,
         "descent_m": 4000, "hours": 4, "top_speed_ms": 15.0, "runs": 10},
        {"activity_id": 2, "day": date(2019, 1, 20), "name": "Saint-Gervais Resort Skiing", "distance_m": 5000,
         "descent_m": 800, "hours": 1, "top_speed_ms": 17.0, "runs": 2},
        {"activity_id": 3, "day": date(2019, 1, 21), "name": "Hauteluce Snowboard", "distance_m": 9000,
         "descent_m": 1500, "hours": 2, "top_speed_ms": None, "runs": None},
        {"activity_id": 4, "day": date(2020, 1, 23), "name": "Raska Resort", "distance_m": 9000,
         "descent_m": 1100, "hours": 3, "top_speed_ms": 14.0, "runs": 5},
    ]
    out = sn.seasons(rows)
    assert [s["season"] for s in out["seasons"]] == ["2019/20", "2018/19"]
    s18 = out["seasons"][1]
    assert s18["days_on_snow"] == 2 and s18["vertical_m"] == 6300 and s18["runs"] is None and s18["runs_partial"] == 12
    assert s18["days"][0]["runs"] == 12 and s18["top_speed_kmh"] == pytest.approx(61.2)
    assert s18["places"] == ["Saint-Gervais", "Hauteluce"]
    assert out["totals"]["days_on_snow"] == 3


def test_snow_activity_metrics_fall_back_to_streams():
    st = pd.DataFrame({"speed_ms": np.r_[np.full(50, 8.0), [60.0], np.full(50, 12.0)], "altitude_m": np.nan})
    m = sn.activity_metrics(st, float("nan"))
    assert m["snow_top_speed"] == pytest.approx(12.0) and "snow_runs" not in m
    assert sn.activity_metrics(st, 14.5)["snow_top_speed"] == 14.5


# ------------------------------------------------------------------ sleep, recovery, forecasts

def synthetic_days(n_days=400, seed=0) -> pd.DataFrame:
    """Tennis every Wednesday costs 10 points of sleep score and 8 ms of HRV the following night."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n_days, freq="D").date
    df = pd.DataFrame(index=idx)
    df["tennis"] = [d.weekday() == 2 for d in idx]
    df["run"] = [d.weekday() == 5 for d in idx]
    df["snow"] = False
    df["load"] = np.where(df["tennis"], 90.0, np.where(df["run"], 60.0, 0.0))
    df["evening_workout"] = df["tennis"]
    df["last_end_utc"] = [pd.Timestamp(d) + pd.Timedelta(hours=19) if t else pd.NaT for d, t in zip(idx, df["tennis"])]
    after_tennis = df["tennis"].shift(1, fill_value=False).to_numpy()
    df["sleep_score"] = 75 - 10 * after_tennis + rng.normal(0, 4, n_days)
    df["hrv"] = 50 - 8 * after_tennis + rng.normal(0, 3, n_days)
    df["rhr"] = 55 + 2 * after_tennis + rng.normal(0, 1, n_days)
    df["sleep_h"] = 7 + rng.normal(0, 0.5, n_days)
    df["bed_min"] = 300 + rng.normal(0, 20, n_days)
    df["sleep_start_utc"] = [pd.Timestamp(d) - pd.Timedelta(hours=1) for d in idx]
    from gla.analytics import load as ld
    ff = ld.fitness_fatigue(df["load"])
    df["fitness"], df["fatigue"], df["form"] = ff["fitness"].values, ff["fatigue"].values, ff["form"].values
    return df


def test_sleep_drivers_find_tennis_and_hide_rare_ones():
    df = synthetic_days()
    d = sl.drivers(sl.nights(df))
    score = {r["key"]: r for r in d["sleep_score"]["drivers"]}
    assert score["tennis"]["clear"] and score["tennis"]["diff"] == pytest.approx(-10, abs=2)
    assert score["tennis"]["hi"] < 0
    assert abs(score["weekend"]["diff"]) < 3
    assert "late_bed" in {h["key"] for h in d["sleep_score"]["hidden"]}    # fewer than 20 such nights
    assert {r["key"]: r for r in d["hrv"]["drivers"]}["tennis"]["diff"] == pytest.approx(-8, abs=1.5)


def test_recovery_curve_after_hard_sessions():
    df = synthetic_days()
    loads = [(d, 90.0) for d in df.index if d.weekday() == 2] + [(d, 20.0) for d in df.index if d.weekday() == 5]
    rec = sl.recovery(df, loads)
    hrv = rec["metrics"]["hrv"]["overall"]
    assert hrv["sessions"] > 40
    assert hrv["nights"][0]["mean"] == pytest.approx(-8, abs=2) and hrv["nights"][0]["hi"] < 0
    assert hrv["back_by"] == 2
    assert "2025" in rec["metrics"]["hrv"]["years"]


def test_ridge_and_tonight_forecast():
    x = np.random.default_rng(2).normal(size=(300, 3))
    y = 3 * x[:, 0] - 2 * x[:, 2] + 10
    m = fc.Ridge(lam=0.01).fit(x, y)
    assert np.allclose(m.predict(x), y, atol=0.05)
    df = synthetic_days()
    today = df.index[-1]
    while today.weekday() != 2:                                  # a tennis Wednesday
        today -= timedelta(days=1)
    r = fc.tonight(df.loc[:today], "sleep_score", today)
    assert r["ready"] and r["mae"] < r["mae_baseline"]
    assert r["prediction"] < 70                                  # tennis tonight: worse sleep expected
    assert {c["feature"] for c in r["contributions"]} == set(fc.FEATURES)
    plan = fc.load_plan(df, today)
    assert plan["ready"] and len(plan["weekday_pattern"]) == 7 and plan["weekday_pattern"][2] == pytest.approx(90)
    short = fc.tonight(df.iloc[:30], "sleep_score", df.index[29])
    assert not short["ready"]


# ------------------------------------------------------------------ API on the fake export

def test_milestone5_endpoints(analyzed, monkeypatch):
    settings, sessions = analyzed
    monkeypatch.setenv("GLA_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("GLA_DATABASE_URL", settings.database_url)
    import gla.api
    api = importlib.reload(gla.api)
    c = TestClient(api.app)
    t = c.get("/api/tennis").json()
    assert len(t["sessions"]) == 1 and t["geometry"]["baseline_m"] == pytest.approx(11.885)
    sid = t["sessions"][0]["activity_id"]
    d = c.get(f"/api/tennis/{sid}").json()
    assert d["number"] == 1 and d["prev_id"] is None and len(d["per_minute"]) > 60
    assert c.get("/api/tennis/999999").status_code == 404
    snow = c.get("/api/snow").json()
    assert snow["seasons"][0]["season"] == "2023/24" and snow["totals"]["days_on_snow"] == 1
    sleep = c.get("/api/sleep").json()
    assert set(sleep["drivers"]) == set(sl.OUTCOMES) and sleep["series"]
    f = c.get("/api/forecast").json()
    assert f["plan"]["ready"] and f["tonight"]["sleep_score"]["ready"] is False   # four nights are not enough
