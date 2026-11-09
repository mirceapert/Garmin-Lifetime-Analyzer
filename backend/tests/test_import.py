import zipfile
from datetime import date

import pandas as pd
from sqlalchemy import func, select

from gla.geo import decode_polyline
from gla.importer.export import ExportImporter
from gla.models import Activity, DailyHealth, RawFile, SyncRun


def count(sessions, model):
    with sessions() as s:
        return s.scalar(select(func.count()).select_from(model))


def test_import_full_export(settings, sessions, export_zip):
    report = ExportImporter(settings, sessions).run(export_zip)
    run = report["this_run"]
    assert run["activities_added"] == 7            # 6 FIT + 1 summary-only
    assert run["activities_summary_only"] == 1
    assert run["fit_not_activity"] == 1            # the settings file
    assert run["unsupported_by_extension"][".gpx"] == 1
    assert run.get("files_failed", 0) == 0
    assert run["summaries_matched"] == 6

    lib = report["library"]
    assert lib["by_sport"]["run"]["activities"] == 3
    assert lib["by_sport"]["trail"]["activities"] == 1
    assert lib["by_sport"]["tennis"]["activities"] == 1
    assert lib["by_sport"]["walk"]["activities"] == 1
    assert lib["by_sport"]["snow"]["activities"] == 1
    assert lib["with_gps"] == 5 and lib["with_streams"] == 6
    assert lib["first_activity_utc"].startswith("2019-06-02")

    with sessions() as s:
        trail = s.scalar(select(Activity).where(Activity.sport == "trail"))
        assert trail.garmin_id == 1002 and trail.name == "Activity 1002"
        assert trail.tz_offset_min == 180
        assert trail.start_local.hour == 9
        pts = decode_polyline(trail.track.polyline)
        assert len(pts) == trail.track.points > 10
        streams = pd.read_parquet(settings.streams_dir / f"{trail.id}.parquet")
        assert len(streams) == 541 and streams["heart_rate"].iloc[0] == 140

        old = s.scalar(select(Activity).where(Activity.garmin_id == 999))
        assert old.source == "export-summary" and old.distance_m == 10000 and old.timer_s == 3000
        assert old.ascent_m == 45 and old.avg_hr == 150 and not old.has_gps

        d = s.get(DailyHealth, date(2024, 5, 3))
        assert d.sleep_score == 79 and d.hrv_night_ms == 53 and d.resting_hr == 53
        assert d.sleep_s == 25800
        assert s.get(DailyHealth, date(2024, 5, 5)).resting_hr == 55   # RHR-only day
        run_row = s.scalar(select(SyncRun))
        assert run_row.status == "ok" and run_row.report["this_run"]["activities_added"] == 7


def test_reimport_adds_nothing_and_backs_up(settings, sessions, export_zip):
    ExportImporter(settings, sessions).run(export_zip)
    before = (count(sessions, Activity), count(sessions, RawFile), count(sessions, DailyHealth))
    report = ExportImporter(settings, sessions).run(export_zip)
    assert report["this_run"].get("activities_added", 0) == 0
    assert report["this_run"]["fit_already_imported"] == 7
    assert (count(sessions, Activity), count(sessions, RawFile), count(sessions, DailyHealth)) == before
    assert report["backup"] and list(settings.backup_dir.glob("gla-*.sqlite"))


def test_import_extracted_folder(settings, sessions, export_zip, tmp_path):
    folder = tmp_path / "extracted"
    with zipfile.ZipFile(export_zip) as z:
        z.extractall(folder)
    report = ExportImporter(settings, sessions).run(folder)
    assert report["library"]["activities"] == 7


def test_corrupt_fit_is_reported_not_fatal(settings, sessions, tmp_path):
    folder = tmp_path / "exp"
    folder.mkdir()
    (folder / "broken.fit").write_bytes(b"\x0e\x10not a fit file at all")
    report = ExportImporter(settings, sessions).run(folder)
    assert report["this_run"]["files_failed"] == 1
    assert report["failures"][0]["file"] == "broken.fit"
