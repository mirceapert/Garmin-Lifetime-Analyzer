# Garmin Lifetime Analyzer

A personal web app that turns your whole Garmin history into lifetime analysis: odometer, heatmap and explorer tiles, repeated routes, best efforts, tennis court coverage, snowboard seasons, sleep and recovery, forecasts and a Year in Review.

It runs on your own computer. Your data and your Garmin key never leave it, except for calls to Garmin.

**Version 1.2.** All six milestones are built, plus a Home tab, a shareable Year in Review image, and a way to run without Docker.

- **[Setup guide](docs/setup-guide.md)**: from nothing to your history in the browser, everyday use, updates, backups and troubleshooting.
- **[Hosting checklist](docs/hosting-checklist.md)**: what to do before the app is reachable from anywhere but your computer.
- **Project page**: `docs/index.html`, a one-page description of the app for other people, with no personal data. To publish it: on GitHub, Settings › Pages › Deploy from a branch › `main` and `/docs`. It appears at `https://mirceapert.github.io/Garmin-Lifetime-Analyzer/`.

## Quick start

With Docker Desktop running and your Garmin export zip in an `import` folder next to this file:

```powershell
docker compose build
docker compose run --rm app gla import --json /data/import-report.json
copy .env.example .env     # then put your Garmin Personal API key in it
docker compose up -d
docker compose run --rm app gla sync
```

Open http://localhost:8000. The [setup guide](docs/setup-guide.md) explains each step.

**Without Docker** (Python 3.12+ and Node.js 20+): put your `.env` (and a copied `data` folder, if you have one) here, then double-click `start.cmd` on Windows or run `./start.sh` on macOS and Linux. It sets itself up on the first run and starts the app and the daily sync. See [Without Docker](docs/setup-guide.md#without-docker).

## Using the app

```powershell
docker compose up -d --build
```

Then open **http://localhost:8000** in your browser. The app is reachable only from this computer.

| Tab | What's on it |
| --- | --- |
| Home | Your lifetime at a glance, tonight's forecast, one number from each view with a link to it, and your latest activities. Before the first import it shows the setup steps |
| Lifetime | Odometer, totals per sport, and year over year with year toggles your browser remembers |
| Heatmap & tiles | Every GPS track on a map, sport layers, explorer tiles and your largest square, shortcuts to the places you're active |
| Routes | Routes you repeat, how your pace changed on each, and a name you choose |
| Best efforts | Fastest 1 km, 5 km, 10 km and half marathon, and how each record moved over time |
| Tennis | Court coverage per year folded into one half court, zones, a sortable session list, and each session on its own (`#tennis-260`) with heart rate and speed per minute |
| Snowboard | Seasons with days on snow, runs, vertical, top speed, and the days of each season |
| Sleep & recovery | Sleep score, HRV, resting heart rate and sleep time over the years, what goes with your better and worse nights, and how many nights you need after a hard session |
| Forecasts | Tonight's sleep score and HRV, and a planner for your fitness and form on a day you pick |
| Year in review | One year on one page: totals against the year before, month by month, best efforts and personal bests, the year's map, biggest day and week, longest of each sport, places, new tiles and routes, tennis, snowboard, fitness and sleep. Opens on the latest full year; `#year-2024` opens 2024. At the bottom, **Share image** makes a 1080 × 1350 PNG of the year (Night or Day, your name if you want it, place names on or off). It's drawn in your browser and has no map, so it doesn't show where you live |

The header shows when the last sync ran and has a **Sync now** button. API key warnings appear under it from 7 days before the key expires. Every tab has its own link (for example `http://localhost:8000/#routes-25`), so you can bookmark a route.

The base map comes from [OpenFreeMap](https://openfreemap.org), which serves OpenStreetMap data for free with no API key or account. The Layers panel switches between three base maps: Dark (the default, so tracks stand out), Light and Streets. Your choice is remembered. If it can't be reached, the map falls back to the standard OpenStreetMap tiles, darkened. Either way the map tab needs an internet connection, and nothing about you is sent with those requests apart from which map squares you look at.

## Analytics

After every import and sync the app analyzes new activities on its own. To run it by hand:

```powershell
docker compose run --rm app gla analyze          # only activities not analyzed yet
docker compose run --rm app gla analyze --full   # everything again, after a method changes
```

What it computes:

- **Training load** for every activity with heart rate (TRIMP, second by second when the per-second data has heart rate), using the resting and maximum heart rate from your Garmin profile. From it, fitness (42-day), fatigue (7-day) and form per day.
- **Best efforts**: your fastest 1 km, 5 km, 10 km and half marathon inside any outdoor run or trail run. GPS jumps faster than 36 km/h are dropped first. Treadmill runs are left out because their distance comes from wrist motion.
- **Explorer tiles**: every zoom-14 map square your GPS tracks crossed (tennis excluded), your largest fully covered square and largest cluster.
- **Repeated routes**: tracks of the same kind (runs with trail runs, walks, rides) that start within 400 m, are within 12% in length and stay within 140 m on average become one route. A route shows once you have done it 3 times. Routes keep their ID and the name you give them when new activities arrive.
- **Names**: activity names that arrived garbled from Garmin ("ReprizÄ") are repaired.
- **Sport groups**: table tennis, padel, squash and the other racket sports Garmin files under tennis move to Other.
- **Tennis courts**: the courts you play on are found from the GPS of all your sessions together (the net is where both ends mirror each other), then every session is folded into one half court seen from your baseline, right side = forehand. Zones: near the net (under 5 m), mid court, baseline (beyond 10.5 m). Breaks of more than 45 s standing still are left out. Wrist GPS is good to a few metres, so the zones are tendencies.
- **Snowboard**: a season runs July to June; several recordings on one day are one day on snow. Vertical is Garmin's descent. Runs are counted from altitude (a descent of 30 m or more that ends at a lift), only where the altitude has almost no gaps. Top speed is Garmin's, or the per-second speed smoothed over 5 s where Garmin left it out.
- **Sleep drivers** (computed when you open the tab): nights after a hard day, a rest day, a late workout, tennis, a run, a weekend, a late bedtime, a short night or high fatigue, compared with the nights without, each against your level in the two months around it. Shown with a 95% range, and only with 20 nights or more on each side.
- **Recovery**: night HRV and resting heart rate in the 4 nights after your hardest sessions (top 15% load), against your median of the 7 nights before. Per year from 8 sessions.
- **Tonight's forecast**: a small linear model trained on your own nights each time you open the tab, with its accuracy against simply guessing your 7-night average.
- **Year in Review** (computed when you open the tab): nothing new is measured; the numbers above are cut to one calendar year. A personal best counts when an effort beat every earlier one at the time. Places come from the names Garmin gives activities ("Timisoara Running" is Timisoara; "Treadmill Running" has no place).

The results are in the API (open http://localhost:8000/docs to try them):

| Endpoint | What |
| --- | --- |
| `GET /api/lifetime` | Odometer and totals per sport |
| `GET /api/year-over-year?sports=run,trail` | Cumulative distance by day of year, per year |
| `GET /api/best-efforts` | Every best effort per distance and the all-time best |
| `GET /api/tiles` | Visited tiles, largest square and cluster, new tiles per year |
| `GET /api/tracks` | All GPS tracks for the heatmap |
| `GET /api/routes`, `GET /api/routes/{id}` | Repeated routes and every effort on one |
| `PATCH /api/routes/{id}` | Rename a route, body `{"name": "Bega loop"}` |
| `GET /api/training-load` | Daily load, fitness, fatigue and form |
| `GET /api/health-days` | Sleep score, sleep time, night HRV and resting heart rate per day |
| `GET /api/tennis`, `GET /api/tennis/{id}` | Tennis sessions, coverage per year, courts; one session in detail |
| `GET /api/snow` | Snowboard seasons and their days |
| `GET /api/sleep` | Nightly series, sleep drivers, recovery after hard sessions |
| `GET /api/forecast` | Tonight's sleep score and HRV, and the starting point of the fitness planner |
| `GET /api/home` | One number per view for the Home tab, tonight's forecast, the latest activities |
| `GET /api/year-review?year=2025` | One year on one page; without `year`, the latest full year |

## What to check (without Docker)

On the second PC, with Python 3.12+, Node.js 20+ and Git installed:

```powershell
git clone https://github.com/mirceapert/Garmin-Lifetime-Analyzer.git
cd Garmin-Lifetime-Analyzer
git checkout run-without-docker
```

- Copy `data` and `.env` from the first PC into this folder (stop it there first with `docker compose down`).
- Double-click `start.cmd`. The first run sets up `.venv` and builds the web page, then says to open http://localhost:8000. Your history is there.
- A minimized "gla" window runs the daily sync; Ctrl+C in the main window closes both.
- In a second PowerShell window in the folder: `.\.venv\Scripts\gla status` shows the key as ok, so `.env` was read.
- On the first PC, Docker still works as before: `docker compose up -d --build`.

## Where things are

| Path | What |
| --- | --- |
| `data\gla.sqlite` | The database |
| `data\raw\fit` | Every FIT file, unchanged, named by its checksum |
| `data\streams` | Per-second data for each activity, one Parquet file each |
| `data\backups` | Database copies taken before each import |
| `data\raw\json` | Every Garmin API response, unchanged |
| `.env` | Your API key and settings (never committed) |
| `import\` | Where you put the Garmin export |

`data\` and `import\` are excluded from Git, so your data is never committed.

## Developing

```bash
cd backend
pip install -e ".[dev]"
pytest

cd ../frontend
npm install
npm run dev      # http://localhost:5173, with /api sent to the app on :8000
```

The tests build a small fake Garmin export (FIT files, activity summaries and wellness files) and a fake Personal API that answers in the real API's shapes. GitHub runs them on every push.

## Plan

The full requirements and design are in the project's design doc. Milestones:

1. Foundation and import
2. Live sync from the Garmin Personal API
3. Analytics on real data
4. First views: Lifetime, Heatmap and tiles, Routes, Best efforts
5. Tennis, Snowboard, Sleep and recovery, Forecasts
6. Year in Review, setup guide and hosting checklist

After version 1: a Home tab, a shareable Year in Review image and a project page (version 1.1, this one).
