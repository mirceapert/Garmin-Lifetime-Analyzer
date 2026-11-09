# Garmin Lifetime Analyzer

A personal web app that turns your whole Garmin history into lifetime analysis: odometer, heatmap and explorer tiles, repeated routes, best efforts, tennis court coverage, snowboard seasons, sleep and recovery, forecasts and a Year in Review.

It runs on your own computer. Your data and your Garmin key never leave it, except for calls to Garmin.

**Status: milestone 1 of 6, foundation and import.** This milestone imports your full Garmin account export into a local database and reports what it found. Live sync and the web views come in the next milestones.

## What you need

- Docker Desktop, running
- Git, or download this repository as a zip from GitHub
- Your Garmin account export (the zip Garmin emails you a link to)

## First run on Windows

Open PowerShell and run these commands one at a time.

1. Get the code and go into its folder:

   ```powershell
   git clone https://github.com/mirceapert/Garmin-Lifetime-Analyzer.git
   cd Garmin-Lifetime-Analyzer
   ```

2. Make the import folder and put your Garmin export zip in it. Leave it zipped; the importer opens it, and the zips inside it, in place.

   ```powershell
   mkdir import
   ```

   Then copy the export zip into `Garmin-Lifetime-Analyzer\import`.

3. Build the app (the first time takes a few minutes):

   ```powershell
   docker compose build
   ```

4. Import your history:

   ```powershell
   docker compose run --rm app gla import --json /data/import-report.json
   ```

   A full export can take 10 to 30 minutes. Progress is printed every 50 files. At the end you get a summary like this:

   ```text
   Activities: 1382  (2021-11-08 to 2026-11-08)
     with GPS: 1190   with per-second data: 1350   summary only: 32

     Sport            Count    Distance    Hours  First       Last
     Running            590   5904.0 km    541.0  2021-11-09  2026-11-07
     ...

   Daily health: 1827 days (2021-11-08 to 2026-11-08)
     days with sleep score: 1790, sleep time: 1800, night HRV: 1500, resting HR: 1820
   ```

   These numbers are only an example; yours will differ.

5. Start the app and check it answers:

   ```powershell
   docker compose up -d
   ```

   Open http://localhost:8000/api/library in your browser. It shows the same summary as JSON. `http://localhost:8000/docs` lists the API.

Running the import again is safe. Files already imported are recognised and skipped, so nothing is duplicated. A copy of the database is saved in `data\backups` before every import.

## What to check (milestone 1 review)

- The activity count and the first and last dates match Garmin Connect's activity list.
- Each sport's count looks right. Activities Garmin records as other sports are counted under Other.
- "Summary only" activities have no FIT file in the export. Open one or two in Garmin Connect and compare distance and duration with `gla report`.
- Daily health covers the days you wore the watch, with sleep score, HRV and resting heart rate.
- Anything listed as failed in the import output.

The full report is saved at `data\import-report.json`. It holds counts, dates and file names, but no GPS positions.

## Where things are

| Path | What |
| --- | --- |
| `data\gla.sqlite` | The database |
| `data\raw\fit` | Every FIT file, unchanged, named by its checksum |
| `data\streams` | Per-second data for each activity, one Parquet file each |
| `data\backups` | Database copies taken before each import |
| `import\` | Where you put the Garmin export |

`data\` and `import\` are excluded from Git, so your data is never committed.

## Developing

```bash
cd backend
pip install -e ".[dev]"
pytest
```

The tests build a small fake Garmin export (FIT files, activity summaries and wellness files) and import it. GitHub runs them on every push.

## Plan

The full requirements and design are in the project's design doc. Milestones:

1. Foundation and import (this one)
2. Live sync from the Garmin Personal API
3. Analytics on real data
4. First views: Lifetime, Heatmap and tiles, Routes, Best efforts
5. Tennis, Snowboard, Sleep and recovery, Forecasts
6. Year in Review, setup guide and hosting checklist
