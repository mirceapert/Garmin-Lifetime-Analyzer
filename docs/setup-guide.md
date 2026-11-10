# Setup guide

From nothing to your whole Garmin history in the browser. Written for Windows; the macOS and Linux commands are the same in a terminal, except where noted.

Docker is the recommended way. On a computer without Docker, see [Without Docker](#without-docker) at the end.

Plan on about an hour of your time, plus the wait for Garmin's export.

## 1. What you need

- **Docker Desktop**, installed and running. Download it from docker.com. On Windows it asks for a restart the first time.
- **About 10 GB free** on the drive that holds Docker's data, plus room for your export. Docker misbehaves when its drive fills up (see [Troubleshooting](#troubleshooting)).
- **Git** (git-scm.com), or download this repository as a zip from GitHub instead.
- **A Garmin Connect account** with your history in it.

## 2. Ask Garmin for your data export

The export carries your whole history: every activity's original FIT file, plus sleep, HRV and resting heart rate.

1. Sign in at garmin.com and open your account's **Data Management** page.
2. Choose **Export Your Data** and confirm.
3. Garmin emails you a download link when the archive is ready. It can take from a few hours to several days.
4. Download the zip. Don't unzip it.

You can carry on with steps 3 and 5 while you wait.

## 3. Get the code

In PowerShell, pick a folder you like (for example `F:\Git`) and run:

```powershell
git clone https://github.com/mirceapert/Garmin-Lifetime-Analyzer.git
cd Garmin-Lifetime-Analyzer
mkdir import
```

Every command from here on runs in this `Garmin-Lifetime-Analyzer` folder.

## 4. Import your history

1. Copy the export zip into the `import` folder. Leave it zipped.
2. Build the app. The first build takes a few minutes:

   ```powershell
   docker compose build
   ```

3. Import:

   ```powershell
   docker compose run --rm app gla import --json /data/import-report.json
   ```

   A full export takes 10 to 30 minutes. Progress shows every 50 files. At the end you get a summary of activities per sport and of the days with sleep and HRV. The analysis (training load, best efforts, tiles, routes, tennis courts, snowboard runs) runs on its own at the end.

4. Compare the summary with Garmin Connect: the number of activities and the first and last dates should match.

Running the import again is safe. Files already imported are skipped, and the database is copied to `data\backups` first.

## 5. Connect the Garmin Personal API (daily sync)

The export is a snapshot. The Personal API keeps the app up to date afterwards.

1. In Garmin Connect on the web, open **Settings**, then **Personal API Key**, and create a key. Garmin shows it once; copy it straight away. Pick how long it lasts (up to a year).
2. Make your settings file:

   ```powershell
   copy .env.example .env
   notepad .env
   ```

3. Fill in:
   - `GARMIN_API_KEY`: the key. Treat it like a password: it stays in this file on your computer and is never committed to Git.
   - `GARMIN_API_KEY_EXPIRES`: the expiry date Garmin shows, as `2027-11-09`.
   - `TZ`: your time zone, for example `Europe/Bucharest`.
   - `GLA_SYNC_TIME`: when the daily sync runs, for example `06:30`.

4. Start everything and run the first sync now:

   ```powershell
   docker compose up -d --build
   docker compose run --rm app gla sync
   docker compose run --rm app gla status
   ```

   `gla status` shows the last sync, the key's expiry, and the resting and maximum heart rate Garmin uses for you.

From now on the `worker` container syncs every day at `GLA_SYNC_TIME` and retries a failed run up to three times, 30 minutes apart. The app warns you in its header from 7 days before the key expires. To replace the key, create a new one, update both lines in `.env`, and run `docker compose up -d`.

## 6. Open the app

Open **http://localhost:8000**. It is reachable only from this computer.

| Tab | What's on it |
| --- | --- |
| Lifetime | Odometer, totals per sport, year over year with year toggles |
| Heatmap & tiles | Every GPS track on a map, explorer tiles, largest square |
| Routes | Routes you repeat, your pace on each, names you choose |
| Best efforts | Fastest 1 km, 5 km, 10 km and half marathon over time |
| Tennis | Court coverage folded into one half court, every session on its own |
| Snowboard | Seasons, days on snow, runs, vertical, top speed |
| Sleep & recovery | What goes with your better and worse nights; recovery after hard sessions |
| Forecasts | Tonight's sleep and HRV; a fitness and form planner |
| Year in review | One year on one page |

Every tab and every tennis session has its own address, so bookmarks work. **Sync now** in the header syncs straight away, for example after an evening session.

## 7. Everyday use

| To | Run |
| --- | --- |
| Start the app after a restart of your computer | Nothing: Docker Desktop starts it. Otherwise `docker compose up -d` |
| Stop it | `docker compose down` |
| See what it's doing | `docker compose logs -f --tail 50` |
| Check sync and key | `docker compose run --rm app gla status` |
| Re-run the analysis | `docker compose run --rm app gla analyze` |

## 8. Updating to a new version

```powershell
git checkout main
git pull
docker compose up -d --build
docker compose run --rm app gla analyze --full
```

`analyze --full` recomputes everything with the new methods. Your route names are kept.

If `git checkout` or `git pull` refuses because files have changed and you didn't change them, Windows has only switched their line endings. Discard that with `git checkout -- .` and try again.

## 9. Your data and backups

| Path | What |
| --- | --- |
| `data\gla.sqlite` | The database |
| `data\raw` | Every FIT file and Garmin response, unchanged |
| `data\streams` | Per-second data, one file per activity |
| `data\backups` | Database copies from before each import (the last 10) |
| `.env` | Your API key and settings |

Back up the whole `data` folder and `.env` (for example to an external drive). Everything the app shows can be rebuilt from `data\raw` with `gla analyze --full`; route names live in the database.

To move to another computer: install Docker, clone the repository, copy `data` and `.env` across, and run `docker compose up -d --build`.

## Without Docker

The app also runs straight on Windows, macOS or Linux, for example on a second computer. You need:

- **Python 3.12 or newer** (python.org; on Windows tick "Add python.exe to PATH" in the installer)
- **Node.js 20 or newer** (nodejs.org), used once to build the web page
- **Git** (git-scm.com)

1. Get the code:

   ```powershell
   git clone https://github.com/mirceapert/Garmin-Lifetime-Analyzer.git
   cd Garmin-Lifetime-Analyzer
   ```

2. Bring your data. Either copy the `data` folder and `.env` from the computer that already has them into this folder (stop the app there first, `docker compose down`, so the database is copied whole), or start fresh: `copy .env.example .env`, fill in the key as in step 5, and put the export zip in an `import` folder.

3. Start it. On Windows double-click **`start.cmd`** (or run `.\start.cmd` in PowerShell); on macOS and Linux run `./start.sh`.

   The first start creates a Python environment in `.venv`, installs the app and builds the web page, which takes a few minutes. Later starts take seconds. Then open http://localhost:8000. The daily sync runs alongside in a small minimized window; closing the app (Ctrl+C) stops both.

4. Starting fresh? Import once the app is set up, in a second window in the same folder:

   ```powershell
   .\.venv\Scripts\gla import
   .\.venv\Scripts\gla sync
   ```

   On macOS and Linux it's `.venv/bin/gla`.

The `gla` commands are the same as with Docker, without `docker compose run --rm app` in front: `.\.venv\Scripts\gla status`, `gla analyze --full` and so on. Run them from the `Garmin-Lifetime-Analyzer` folder: the app finds `.env`, `data` and `import` in the folder you start it from.

| To | Run |
| --- | --- |
| Start | `start.cmd` (Windows) or `./start.sh` |
| Start without the daily sync | `start.cmd -NoSync` or `./start.sh --no-sync` |
| Use another port | `start.cmd -Port 8010` or `PORT=8010 ./start.sh` |
| Update to a new version | `start.cmd -Update` or `./start.sh --update` (pulls, reinstalls, rebuilds, re-analyzes) |

Good to know:

- The sync runs only while the app runs. If the computer was off at `GLA_SYNC_TIME`, the sync runs as soon as you start the app that day. **Sync now** works as always.
- Two computers each keep their own copy and sync on their own; nothing is shared between them. The same Garmin key works on both.
- If PowerShell says running scripts is disabled, use `start.cmd`, which starts `start.ps1` for this one run without changing any settings.

## Troubleshooting

**"This site can't be reached" at localhost:8000.** Check the containers run: `docker compose ps`. If `app` keeps restarting, `docker compose logs app` says why.

**"read-only file system" or strange import errors in the logs.** The drive with Docker's data is full. Free space, run `docker system prune`, then on Windows `wsl --shutdown` and start Docker Desktop again. If an image was damaged, rebuild it from scratch: `docker compose build --no-cache`. Docker Desktop can keep its data on another drive (Settings, Resources, Disk image location).

**The page looks like the old version after an update.** Make sure you are on `main` with `git status`, rebuild with `docker compose up -d --build`, then reload the page with Ctrl+F5.

**The map is empty or grey.** The base map needs internet. If OpenFreeMap can't be reached, the app falls back to OpenStreetMap's own tiles after 10 seconds.

**`gla sync` says the key was rejected.** It expired or was revoked. Create a new key in Garmin Connect and update `.env`.

**Port 8000 is taken by another program.** Change the left number in `docker-compose.yml` (`"127.0.0.1:8010:8000"`) and open http://localhost:8010.
