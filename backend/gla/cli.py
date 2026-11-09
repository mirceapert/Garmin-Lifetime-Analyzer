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
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
