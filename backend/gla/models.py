"""Database tables.

Raw Garmin files are kept unchanged on disk (data/raw) and referenced from `raw_files`.
Everything else can be rebuilt from them. Per-second streams live in Parquet files
(data/streams/<activity id>.parquet), not in the database.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RawFile(Base):
    __tablename__ = "raw_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(16))          # "export" or "api"
    kind: Mapped[str] = mapped_column(String(16))            # "fit", "json"
    original_name: Mapped[str] = mapped_column(Text)
    stored_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok, failed, skipped
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("dedup_key", name="uq_activity_dedup"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    garmin_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True, index=True)
    dedup_key: Mapped[str] = mapped_column(String(64))       # start time (UTC, to the second) + sport
    sport: Mapped[str] = mapped_column(String(16), index=True)  # run, trail, walk, tennis, snow, other
    garmin_sport: Mapped[str | None] = mapped_column(String(48), nullable=True)
    garmin_sub_sport: Mapped[str | None] = mapped_column(String(48), nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_utc: Mapped[datetime] = mapped_column(DateTime, index=True)
    tz_offset_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elapsed_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    timer_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    ascent_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    descent_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    calories: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_gps: Mapped[bool] = mapped_column(Boolean, default=False)
    start_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    start_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    has_streams: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_file_id: Mapped[int | None] = mapped_column(ForeignKey("raw_files.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(16))           # export-fit, export-summary, api
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    track: Mapped["Track | None"] = relationship(back_populates="activity", uselist=False, cascade="all, delete-orphan")

    @property
    def start_local(self) -> datetime:
        from datetime import timedelta
        return self.start_utc + timedelta(minutes=self.tz_offset_min or 0)


class Track(Base):
    """Simplified GPS line for maps (about one point per 50 m), Google polyline encoded."""
    __tablename__ = "tracks"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    polyline: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer)
    min_lat: Mapped[float] = mapped_column(Float)
    min_lon: Mapped[float] = mapped_column(Float)
    max_lat: Mapped[float] = mapped_column(Float)
    max_lon: Mapped[float] = mapped_column(Float)

    activity: Mapped[Activity] = relationship(back_populates="track")


class DailyHealth(Base):
    __tablename__ = "daily_health"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    sleep_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_start_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sleep_end_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sleep_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    hrv_night_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    resting_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))             # export_import, api_sync
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")  # running, ok, failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class DerivedMetric(Base):
    """A number computed from an activity (training load, best efforts). Rebuildable from raw data."""
    __tablename__ = "derived_metrics"
    __table_args__ = (UniqueConstraint("activity_id", "metric", name="uq_metric"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), index=True)
    metric: Mapped[str] = mapped_column(String(32), index=True)    # load, best_1k, best_5k, best_10k, best_hm
    value: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(16))                # version of the method that produced it


class Route(Base):
    """A route you repeat. Detected automatically; the name is yours to change and survives re-analysis."""
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    group: Mapped[str] = mapped_column(String(16))                # run (incl. trail), walk, cycle
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    length_m: Mapped[float] = mapped_column(Float)
    loop: Mapped[bool] = mapped_column(Boolean)
    signature: Mapped[list] = mapped_column(JSON)                 # 24 points along the first effort
    shape: Mapped[str] = mapped_column(Text)                      # encoded polyline of the first effort
    created_at: Mapped[datetime] = mapped_column(DateTime)


class RouteMember(Base):
    __tablename__ = "route_members"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)
    match_m: Mapped[float] = mapped_column(Float)                 # mean distance to the route signature


class Tile(Base):
    """A zoom-14 map tile you have been in, with the first visit."""
    __tablename__ = "tiles"

    x: Mapped[int] = mapped_column(Integer, primary_key=True)
    y: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_day: Mapped[date] = mapped_column(Date)
    first_activity_id: Mapped[int] = mapped_column(Integer)
    visits: Mapped[int] = mapped_column(Integer)


class TennisCourt(Base):
    """A court you have played on, found from the GPS of your sessions. Rebuilt on every analysis."""
    __tablename__ = "tennis_courts"

    id: Mapped[int] = mapped_column(primary_key=True)
    lat: Mapped[float] = mapped_column(Float)                     # centre of the net
    lon: Mapped[float] = mapped_column(Float)
    angle_deg: Mapped[float] = mapped_column(Float)               # long axis, degrees anticlockwise from east
    sessions: Mapped[int] = mapped_column(Integer)


class TennisSession(Base):
    """Court coverage of one tennis session, folded into one half court (see analytics/tennis.py)."""
    __tablename__ = "tennis_sessions"

    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("tennis_courts.id"))
    grid: Mapped[list] = mapped_column(JSON)                      # seconds per 1 m cell, depth rows x lateral columns
    play_s: Mapped[float] = mapped_column(Float)
    net_share: Mapped[float] = mapped_column(Float)
    mid_share: Mapped[float] = mapped_column(Float)
    base_share: Mapped[float] = mapped_column(Float)
    right_share: Mapped[float] = mapped_column(Float)
    median_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str] = mapped_column(String(16))
