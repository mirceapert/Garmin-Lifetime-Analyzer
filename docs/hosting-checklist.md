# Hosting checklist

What to do before this app is reachable from anywhere but your own computer. Today it listens only on `127.0.0.1` and has **no login**, on purpose: anyone who can reach port 8000 can read your whole history, rename routes and start a sync with your Garmin key.

Work through the sections in order. The first one is the only one you need if the goal is "open it from my phone".

## 0. Choose how far you go

| Goal | Simplest way | Sections |
| --- | --- | --- |
| Use it from your own phone and laptop, nobody else | A private network (Tailscale or similar): the app stays off the public internet | 1 |
| Reach it from any browser, only you | A small server or home machine, behind a reverse proxy with HTTPS and a login | 2 to 6 |
| Share it with other people | Not supported: one database, one Garmin key, no accounts | – |

## 1. Private network (recommended)

- [ ] Install Tailscale (or WireGuard, ZeroTier) on the computer running the app and on your phone.
- [ ] In `docker-compose.yml`, keep the port bound to `127.0.0.1` and expose the app on the private network only, for example with `tailscale serve 8000`, which also adds HTTPS.
- [ ] Open the app from your phone on its private address. Nothing is open to the internet, so sections 2 to 6 aren't needed.

## 2. Server and data

- [ ] A Linux machine or small VPS with Docker: 1 vCPU and 1 to 2 GB of RAM are enough; disk = the size of your `data` folder times 3, for backups and growth.
- [ ] Copy `data/` and `.env` across (see the setup guide, "Your data and backups"). The import folder isn't needed after the first import.
- [ ] Set `TZ` in `.env` to *your* time zone, not the server's: it decides which day an activity and a night belong to.
- [ ] Keep the API key only in `.env` on the server, readable by its owner only (`chmod 600 .env`). Don't put it in the image, the repository or CI.

## 3. HTTPS and a login in front of the app

The app itself has no accounts, so the login lives in the reverse proxy in front of it.

- [ ] Keep `127.0.0.1:8000:8000` in `docker-compose.yml`, so only the proxy reaches the app. Never publish port 8000 on `0.0.0.0`.
- [ ] Put a reverse proxy in front with automatic HTTPS. Caddy is the least work; a minimal `Caddyfile`:

  ```
  garmin.example.com {
      basic_auth {
          mircea <bcrypt hash from `caddy hash-password`>
      }
      reverse_proxy 127.0.0.1:8000
  }
  ```

- [ ] Or use a single-sign-on gate instead of a password (Cloudflare Access, oauth2-proxy with your Google or GitHub account).
- [ ] Check the login covers everything, including `/api/*` and `/docs`: open both in a private window and expect a login prompt.
- [ ] Hide the API docs page if you don't use it: `GLA_API_DOCS=false` in `.env`.
- [ ] Rate-limit `POST /api/sync` in the proxy (one call a minute is plenty), so a stuck page can't hammer Garmin.

## 4. Database

SQLite is fine for one person on one server; keep it unless you have a reason to move.

- [ ] Staying on SQLite: keep `data/` on a local disk (not a network share), and back it up (section 5).
- [ ] Moving to PostgreSQL (optional): add the `psycopg[binary]` package to `backend/pyproject.toml`, set `GLA_DATABASE_URL=postgresql+psycopg://user:password@host/gla`, start once so the tables are created, then copy the rows across (a small script, or `pgloader` from the SQLite file). Run `gla analyze --full` afterwards. The pre-import backup only copies SQLite, so use `pg_dump` for PostgreSQL backups.

## 5. Backups and updates

- [ ] Nightly copy of `data/` and `.env` to another machine or object storage, with a few weeks of history. For SQLite, copy `data/backups/` or use `sqlite3 gla.sqlite ".backup out.sqlite"` rather than copying the live file.
- [ ] Test a restore once: a fresh machine, the backup, `docker compose up -d --build`, and the app shows your history.
- [ ] Update with `git pull`, `docker compose up -d --build`, `gla analyze --full`. Rebuild monthly even without code changes, for security fixes in the base images.

## 6. Watching it

- [ ] An uptime check on the login page (UptimeRobot, Healthchecks.io).
- [ ] Notice failed syncs: the header banner shows them, and `GET /api/sync/status` returns them for a monitor.
- [ ] Renew the Garmin key before it expires; the app warns 7 days ahead.
- [ ] Logs: `docker compose logs --since 24h`. Docker keeps them on disk; cap their size in Docker's daemon settings.

## 7. Terms and third parties

- [ ] The Garmin Personal API is for your own data and your own use. Hosting it for yourself fits that; opening it to others doesn't.
- [ ] The base map comes from OpenFreeMap, which asks nothing for normal use. The fallback uses OpenStreetMap's own tile servers, whose usage policy allows light use like this; for heavier use, point the map at a tile provider you have an account with.
- [ ] Your GPS tracks show where you live and train. Keep the login on, and think twice before sharing screenshots of the heatmap.

## What is not built yet

These would be needed for more than one user, and are out of scope for version 1:

- accounts and a login inside the app (rather than in the proxy)
- one Garmin key and one data folder per user
- background jobs in a queue instead of one worker container
