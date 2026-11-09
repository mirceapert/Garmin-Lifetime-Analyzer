# Garmin Lifetime Analyzer

A personal web app that turns your whole Garmin history into lifetime analysis: odometer, heatmap and explorer tiles, repeated routes, best efforts, tennis court coverage, snowboard seasons, sleep and recovery, forecasts and a Year in Review.

It runs on your own computer. Your data and your Garmin key never leave it, except for calls to Garmin.

**Status: milestone 4 of 6, first views.** The app imports your Garmin history, keeps itself up to date every day, and shows it in your browser: lifetime totals, the heatmap with explorer tiles, your repeated routes and your best efforts. Tennis, snowboarding, sleep and forecasts come in milestone 5.

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

## Live sync from Garmin

After the export is imported, the app keeps itself up to date from the Garmin Personal API.

1. Make your settings file from the example:

   ```powershell
   copy .env.example .env
   notepad .env
   ```

   Fill in `GARMIN_API_KEY` with your Personal API key, and `GARMIN_API_KEY_EXPIRES` with the expiry date Garmin Connect shows for it (for example `2027-11-09`). Check `TZ` and `GLA_SYNC_TIME`. Save and close.

2. Rebuild and start everything:

   ```powershell
   docker compose build
   docker compose up -d
   ```

   This starts two containers: `app` (the API) and `worker`, which syncs once a day at `GLA_SYNC_TIME`. If a sync fails, the worker tries again 30 minutes later, up to three times that day.

3. Run the first sync now instead of waiting for tomorrow:

   ```powershell
   docker compose run --rm app gla sync
   ```

   It starts the day before your newest exported activity, so nothing between the export and today is missed. Without an export it goes back 30 days; `--since 2026-10-01` picks the start yourself.

4. Check the status:

   ```powershell
   docker compose run --rm app gla status
   ```

   The same is at http://localhost:8000/api/sync/status. To sync from the browser, open http://localhost:8000/docs, pick `POST /api/sync` and press "Try it out", then "Execute". The web app's Sync now button arrives with the first views.

What a sync does:

- reads your activity list for the window and downloads the original FIT file of each activity it doesn't have yet. Activities without a FIT file, such as uploaded GPX files, are kept from their summary
- reads sleep, HRV and resting heart rate for each day, re-reading the last two days because a night's data arrives after you wake up
- reads the resting and maximum heart rate Garmin uses for your zones; training load will use them
- saves everything in one go: a sync that fails part-way changes nothing and can simply be run again

The key is used only from your computer. The app exchanges it for a 24-hour access token, cached in `data\.garmin-token.json`, and asks for a new one when needed.

Warnings appear in `gla status` (and later in the app's header) from 7 days before the key expires, when Garmin rejects the key, and when the last sync failed. To replace the key, create a new one in Garmin Connect, update both lines in `.env`, then run `docker compose up -d` again.

## Using the app

```powershell
docker compose up -d --build
```

Then open **http://localhost:8000** in your browser. The app is reachable only from this computer.

| Tab | What's on it |
| --- | --- |
| Lifetime | Odometer, totals per sport, and year over year with year toggles your browser remembers |
| Heatmap & tiles | Every GPS track on a map, sport layers, explorer tiles and your largest square, shortcuts to the places you're active |
| Routes | Routes you repeat, how your pace changed on each, and a name you choose |
| Best efforts | Fastest 1 km, 5 km, 10 km and half marathon, and how each record moved over time |

The header shows when the last sync ran and has a **Sync now** button. API key warnings appear under it from 7 days before the key expires. Every tab has its own link (for example `http://localhost:8000/#routes-25`), so you can bookmark a route.

The base map comes from CARTO, built on OpenStreetMap data, so the map tab needs an internet connection. Nothing about you is sent with those requests apart from which map squares you look at.

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

The results are in the API, ready for the views in milestone 4 (open http://localhost:8000/docs to try them):

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

## What to check (milestone 4 review)

- http://localhost:8000 opens, and still reads well when you make the browser window narrow (phone width).
- Lifetime: the totals match the earlier `gla report`, and the year toggles stay as you left them after a reload.
- Heatmap: your tracks sit on the right streets; the place shortcuts make sense; sport layers turn on and off.
- Routes: rename a route, reload the page, the name is still there.
- Best efforts: the half marathon best is the Timisoara City Marathon half.
- Sync now runs and the time in the header updates.

## What to check (milestone 3 review)

- `gla analyze` runs without errors.
- Best efforts in `/api/best-efforts` look right against races you remember. Your half marathon best should be the Timisoara City Marathon half on 25 Oct 2026.
- Your regular loops appear in `/api/routes`, and renaming one in `/docs` sticks after `gla analyze --full`.
- Fitness and fatigue in `/api/training-load` rise after your heavier weeks.

## What to check (milestone 1 review)

- The activity count and the first and last dates match Garmin Connect's activity list.
- Each sport's count looks right. Activities Garmin records as other sports are counted under Other.
- "Summary only" activities have no FIT file in the export. Open one or two in Garmin Connect and compare distance and duration with `gla report`.
- Daily health covers the days you wore the watch, with sleep score, HRV and resting heart rate.
- Anything listed as failed in the import output.

The full report is saved at `data\import-report.json`. It holds counts, dates and file names, but no GPS positions.

## What to check (milestone 2 review)

- `gla sync` finishes and `gla status` shows the key as ok with the right expiry date.
- Record a short activity, wait until it appears in Garmin Connect, run `gla sync`: it is added once. Running `gla sync` again adds nothing.
- Last night's sleep score, HRV and resting heart rate match the Garmin Connect app (`gla report` shows the day counts).
- `gla status` shows your resting and maximum heart rate from Garmin.
- The next morning, `gla status` shows the worker's scheduled sync ran.

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
4. First views: Lifetime, Heatmap and tiles, Routes, Best efforts (this one)
5. Tennis, Snowboard, Sleep and recovery, Forecasts
6. Year in Review, setup guide and hosting checklist
