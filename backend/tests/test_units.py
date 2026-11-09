from datetime import datetime

from fake_export import make_fit
from fit_tool.profile.profile_type import Sport, SubSport

from gla.fit_reader import read_fit
from gla.geo import decode_polyline, encode_polyline, thin_by_distance
from gla.sports import normalize_sport


def test_normalize_sport():
    assert normalize_sport("running") == "run"
    assert normalize_sport("running", "trail") == "trail"
    assert normalize_sport("trail_running") == "trail"
    assert normalize_sport("tennis") == "tennis"
    assert normalize_sport("snowboarding") == "snow"
    assert normalize_sport("resort_snowboarding") == "snow"
    assert normalize_sport("hiking") == "walk"
    assert normalize_sport("cycling") == "cycle"
    assert normalize_sport("cycling", "indoor_cycling") == "cycle"
    assert normalize_sport("mountain_biking") == "cycle"
    assert normalize_sport("sailing") == "sail"
    assert normalize_sport("swimming", "lap_swimming") == "other"
    assert normalize_sport(None) == "other"


def test_polyline_matches_google_reference():
    pts = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    assert encode_polyline(pts) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    assert decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@") == pts


def test_thin_keeps_ends_and_spacing():
    line = [(45.0 + i * 1e-5, 25.0) for i in range(1000)]  # ~1.1 m apart, ~1.1 km
    thin = thin_by_distance(line, 50)
    assert thin[0] == line[0] and thin[-1] == line[-1]
    assert 20 <= len(thin) <= 25


def test_read_fit_summary_and_streams():
    start = datetime(2024, 5, 4, 6, 30)
    f = read_fit(make_fit(Sport.RUNNING, SubSport.TRAIL, start, 90, 14.0, True))
    assert f.sport == "trail"
    assert f.start_utc == start
    assert f.tz_offset_min == 180
    assert abs(f.distance_m - 14000) < 1
    assert f.timer_s == 5400
    assert f.max_hr == 171
    assert f.has_gps
    assert len(f.streams) == 541
    assert f.streams["t_s"].iloc[-1] == 5400
    assert abs(f.streams["lat"].iloc[0] - 45.6427) < 1e-5


def test_read_fit_without_gps():
    f = read_fit(make_fit(Sport.RUNNING, SubSport.TREADMILL, datetime(2024, 2, 2, 17), 30, 6.0, False))
    assert f.sport == "run"
    assert not f.has_gps
    assert f.gps_points == []
