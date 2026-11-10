#!/usr/bin/env sh
# Garmin Lifetime Analyzer without Docker (macOS and Linux).
#   ./start.sh            set up what is missing, then start the app and the daily sync
#   ./start.sh --update   get the newest version first (git pull), then start
#   ./start.sh --no-sync  start the app without the daily sync
# Settings come from .env in this folder. PORT=8010 ./start.sh uses another port.
set -e
cd "$(dirname "$0")"
UPDATE=0; SYNC=1
for a in "$@"; do case "$a" in --update) UPDATE=1 ;; --no-sync) SYNC=0 ;; *) echo "Unknown option $a"; exit 1 ;; esac; done
PORT="${PORT:-8000}"

if [ "$UPDATE" = 1 ]; then echo "== Getting the newest version"; git pull; fi

if [ ! -x .venv/bin/python ]; then
  command -v python3 >/dev/null || { echo "Python not found. Install Python 3.12 or newer."; exit 1; }
  echo "== Creating the Python environment (.venv)"; python3 -m venv .venv
fi
.venv/bin/python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" \
  || { echo "Python 3.12 or newer is needed. Install it, delete .venv and run this again."; exit 1; }
if [ "$UPDATE" = 1 ] || [ ! -f .venv/.gla-installed ] || [ backend/pyproject.toml -nt .venv/.gla-installed ]; then
  echo "== Installing the app into .venv"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e ./backend
  touch .venv/.gla-installed
fi

if [ "$UPDATE" = 1 ] || [ ! -f frontend/dist/index.html ]; then
  command -v npm >/dev/null || { echo "Node.js not found. Install Node.js 20 or newer (needed once, to build the web page)."; exit 1; }
  echo "== Building the web page"; (cd frontend && npm install --no-audit --no-fund && npm run build)
fi

[ -f .env ] || echo "No .env file yet: copy .env.example to .env and fill in your Garmin key for the daily sync."
[ "$UPDATE" = 1 ] && { echo "== Analyzing with the new version"; .venv/bin/gla analyze --full; }

if [ "$SYNC" = 1 ]; then
  mkdir -p data
  .venv/bin/gla worker > data/worker.log 2>&1 &
  WORKER=$!
  trap 'kill $WORKER 2>/dev/null' EXIT INT TERM
  echo "Daily sync running in the background (log: data/worker.log)."
fi
.venv/bin/gla serve --port "$PORT"
