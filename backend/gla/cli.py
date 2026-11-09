"""Command line: `gla import <path>`, `gla report`."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from pathlib import Path

from .config import load_settings
from .db import make_engine, session_factory
from .importer.export import ExportImporter
from .report import format_summary, last_runs, library_summary
from .sync import ApiSync, SyncBusy, SyncFailed, sync_status


def _cmd_import(args) -> int:
    settings = load_settings()
    sessions = session_factory(make_engine(settings))
    path = Path(args.path) if args.path else settings.import_dir
    if not path.exists():
        print(f"Nothing to import: {path} does not exist. Put your Garmin export .zip in the import folder.", file=sys.stderr)
        return 2
    print(f"Importing {path} ... (a full export can take 10 to 30 minutes)")
    report = ExportImporter(settings, sessions, progress=print).run(path)
    run = report["this_run"]
    print()
    print(f"This run: {run.get('files_seen', 0)} files read, {run.get('activities_added', 0)} activities added, "
          f"{run.get('activities_updated', 0)} updated, {run.get('fit_already_imported', 0)} FIT files already imported, "
          f"{run.get('fit_not_activity', 0)} FIT files without an activity, {run.get('files_failed', 0)} failed, "
          f"{run.get('health_days_added', 0)} health days added.")
    if run.get("unsupported_by_extension"):
        print("Not read (not needed yet): " + ", ".join(f"{k} {v}" for k, v in sorted(run["unsupported_by_extension"].items())))
    for f in report["failures"][:10]:
        print(f"  failed: {f['file']}: {f['error']}")
    print()
    print(format_summary(report["library"]))
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=2, default=str))
        print(f"\nFull report written to {args.json}")
    return 0


def _cmd_report(args) -> int:
    settings = load_settings()
    sessions = session_factory(make_engine(settings))
    with sessions() as s:
        lib = library_summary(s)
        if args.json:
            print(json.dumps({"library": lib, "runs": last_runs(s)}, indent=2))
        else:
            print(format_summary(lib))
            print("\nRecent runs:")
            for r in last_runs(s):
                print(f"  #{r['id']} {r['kind']} {r['status']} {r['started_at']}" + (f"  {r['error']}" if r["error"] else ""))
    return 0


def _cmd_sync(args) -> int:
    from datetime import date
    settings = load_settings()
    sessions = session_factory(make_engine(settings))
    since = date.fromisoformat(args.since) if args.since else None
    try:
        report = ApiSync(settings, sessions, progress=print).run(since=since)
    except SyncBusy as exc:
        print(exc, file=sys.stderr)
        return 3
    except SyncFailed as exc:
        print("Sync failed: " + (str(exc).strip().splitlines() or ["unknown error"])[-1], file=sys.stderr)
        return 1
    print(f"Synced {report['window'][0]} to {report['window'][1]}: "
          f"{report.get('activities_added', 0)} activities added, "
          f"{report.get('activities_added_summary_only', 0)} added without a file, "
          f"{report.get('activities_already_had', 0)} already here, "
          f"{report.get('health_days_added', 0)} health days added, {report.get('health_days_updated', 0)} updated.")
    return 0


def _cmd_status(args) -> int:
    settings = load_settings()
    st = sync_status(settings, session_factory(make_engine(settings)))
    if args.json:
        print(json.dumps(st, indent=2))
        return 0
    last = st["last_run"]
    print(f"Last sync: {last['status'] + ' at ' + last['started_local'] if last else 'never'}")
    print(f"Synced through: {st['synced_through'] or '-'}   next scheduled: {st['next_scheduled_local']}")
    k = st["key"]
    print(f"API key: {k['state']}" + (f", expires {k['expires_on']} ({k['days_left']} days)" if k["expires_on"] else ""))
    for w in st["warnings"]:
        print(f"  [{w['level']}] {w['text']}")
    return 0


def _cmd_worker(args) -> int:
    from .worker import run_forever
    logging.getLogger().setLevel(logging.WARNING)
    settings = load_settings()
    run_forever(settings, session_factory(make_engine(settings)))
    return 0


def _cmd_regroup(args) -> int:
    from .sports import regroup_activities
    settings = load_settings()
    sessions = session_factory(make_engine(settings))
    with sessions() as s:
        moved = regroup_activities(s)
        s.commit()
        print(f"{moved} activities moved to a different sport group.\n")
        print(format_summary(library_summary(s)))
    return 0


def _cmd_analyze(args) -> int:
    from .analytics import run_analysis
    settings = load_settings()
    sessions = session_factory(make_engine(settings))
    print("Analyzing" + (" everything again" if args.full else " new activities") + " ...")
    rep = run_analysis(settings, sessions, full=args.full)
    print(f"{rep.get('activities_analyzed', 0)} activities analyzed, {rep.get('routes_created', 0)} new routes, "
          f"{rep.get('tiles', 0)} explorer tiles, {rep.get('names_fixed', 0)} names fixed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="fitparse")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="gla", description="Garmin Lifetime Analyzer")
    sub = p.add_subparsers(dest="cmd", required=True)
    pi = sub.add_parser("import", help="import a Garmin account export (.zip or extracted folder)")
    pi.add_argument("path", nargs="?", help="export zip or folder (default: the import folder)")
    pi.add_argument("--json", help="also write the full report to this file")
    pi.set_defaults(func=_cmd_import)
    pr = sub.add_parser("report", help="show what is in the library")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=_cmd_report)
    ps = sub.add_parser("sync", help="sync new activities and daily health from the Garmin Personal API")
    ps.add_argument("--since", help="start date YYYY-MM-DD (default: from the last sync)")
    ps.set_defaults(func=_cmd_sync)
    pst = sub.add_parser("status", help="last sync, next sync and API key warnings")
    pst.add_argument("--json", action="store_true")
    pst.set_defaults(func=_cmd_status)
    pw = sub.add_parser("worker", help="run the daily sync schedule (used by the worker container)")
    pw.set_defaults(func=_cmd_worker)
    prg = sub.add_parser("regroup", help="re-apply the sport groups to all stored activities")
    prg.set_defaults(func=_cmd_regroup)
    pa = sub.add_parser("analyze", help="compute training load, best efforts, routes and tiles")
    pa.add_argument("--full", action="store_true", help="recompute everything, not only new activities")
    pa.set_defaults(func=_cmd_analyze)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
