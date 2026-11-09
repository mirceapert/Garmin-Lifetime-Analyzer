"""Thin wrapper over Garmin's official Personal API client (garmin-connect-personal-api-python).

Adds what a daily sync needs: a token cache in the data folder, a short pause between calls,
retries on rate limits and server errors, and clear errors for a missing or rejected key.
"""
from __future__ import annotations

import io
import logging
import time
import zipfile
from datetime import date
from typing import Any, Callable, Protocol

from garmin_personal_api import GarminPersonalApiClient, HttpError, PersonalApiAuthenticator

from .config import Settings

log = logging.getLogger(__name__)
FIT_MAGIC = b".FIT"


class KeyMissing(RuntimeError):
    """No GARMIN_API_KEY in the .env file."""


class KeyRejected(RuntimeError):
    """Garmin refused the key: expired, deleted or mistyped."""


class GarminSource(Protocol):
    """The calls the sync uses. The live client and the test fake both provide them."""

    def search_activities(self, *, start: int, limit: int, start_date: date, end_date: date) -> Any: ...
    def download_activity(self, activity_id: int) -> bytes: ...
    def get_daily_sleep(self, day: date) -> Any: ...
    def get_daily_hrv(self, day: date) -> Any: ...
    def get_daily_summaries(self, start_date: date, end_date: date) -> Any: ...
    def get_heart_rate_zones(self) -> Any: ...


class LiveGarmin:
    def __init__(self, settings: Settings, *, pause_s: float = 0.3, retries: int = 3,
                 sleep: Callable[[float], None] = time.sleep):
        if not settings.garmin_api_key:
            raise KeyMissing("Add GARMIN_API_KEY to the .env file next to docker-compose.yml.")
        self._key = settings.garmin_api_key
        self._auth = PersonalApiAuthenticator(bearer_token_cache_file=settings.token_cache)
        self._pause, self._retries, self._sleep = pause_s, retries, sleep
        self._client = GarminPersonalApiClient(self._token(force=False))

    def _token(self, force: bool) -> str:
        try:
            return self._auth.obtain_token(self._key, force_refresh=force).access_token
        except HttpError as exc:
            if exc.status_code in (400, 401, 403):
                raise KeyRejected("Garmin rejected the API key. It may have expired or been deleted; "
                                  "create a new one in Garmin Connect and update .env.") from exc
            raise

    def _call(self, fn: Callable, *args, **kwargs):
        refreshed = False
        for attempt in range(self._retries + 1):
            self._sleep(self._pause)
            try:
                return fn(*args, **kwargs)
            except HttpError as exc:
                if exc.status_code == 404:
                    return None                       # no data for that day
                if exc.status_code == 401 and not refreshed:
                    self._client.update_bearer_token(self._token(force=True))
                    refreshed = True
                    continue
                if exc.status_code in (401, 403):
                    raise KeyRejected("Garmin refused the request with this API key.") from exc
                if (exc.status_code == 429 or exc.status_code >= 500) and attempt < self._retries:
                    wait = (5, 20, 60)[min(attempt, 2)]
                    log.warning("Garmin answered %s; waiting %s s", exc.status_code, wait)
                    self._sleep(wait)
                    continue
                raise
        raise RuntimeError("unreachable")

    def search_activities(self, *, start, limit, start_date, end_date):
        return self._call(self._client.search_activities, start=start, limit=limit, start_date=start_date, end_date=end_date)

    def download_activity(self, activity_id):
        return self._call(self._client.download_activity, activity_id)

    def get_daily_sleep(self, day):
        return self._call(self._client.get_daily_sleep, day)

    def get_daily_hrv(self, day):
        return self._call(self._client.get_daily_hrv, day)

    def get_daily_summaries(self, start_date, end_date):
        return self._call(self._client.get_daily_summaries, start_date, end_date)

    def get_heart_rate_zones(self):
        return self._call(self._client.get_heart_rate_zones)

    def close(self) -> None:
        self._client.close()
        self._auth.close()


def fit_files_in(download: bytes) -> list[tuple[str, bytes]]:
    """The original-file download is a ZIP (Garmin's client says so); a bare FIT file is accepted too."""
    if len(download) > 12 and download[8:12] == FIT_MAGIC:
        return [("activity.fit", download)]
    try:
        with zipfile.ZipFile(io.BytesIO(download)) as z:
            return [(n, z.read(n)) for n in z.namelist() if n.lower().endswith(".fit")]
    except zipfile.BadZipFile:
        return []
