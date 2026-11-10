// Typed calls to the backend API (see backend/gla/api.py).
export type SportKey = "run" | "trail" | "walk" | "tennis" | "snow" | "cycle" | "sail" | "other";

export interface SportTotals { activities: number; distance_km: number; hours: number; ascent_m: number; descent_m: number; first: string | null; last: string | null }
export interface Lifetime {
  activities: number; first_day: string | null; active_days: number; active_share: number; foot_km: number;
  earth_share: number; hours: number; ascent_m: number; everests: number; snow_vertical_m: number;
  by_sport: Partial<Record<SportKey, SportTotals>>;
}
export interface YearOverYear { sports: string[]; years: Record<string, number[]>; latest_day: string | null }
export interface Effort { activity_id: number; date: string; seconds: number; name: string | null; activity_km: number; sport: SportKey }
export type BestEfforts = Record<"best_1k" | "best_5k" | "best_10k" | "best_hm", { distance_m: number; efforts: Effort[]; best: Effort | null }>;
export interface Tiles { zoom: number; tiles: [number, number, string, number][]; max_square: { size: number; x: number; y: number }; cluster: [number, number][]; per_year: Record<string, number> }
export interface TrackRow { id: number; sport: SportKey; date: string; polyline: string; bbox: [number, number, number, number]; name: string | null }
export interface RouteRow { id: number; name: string | null; group: "run" | "walk" | "cycle"; length_km: number; loop: boolean; efforts: number; first: string; last: string; shape: string }
export interface RouteEffort { activity_id: number; date: string; name: string | null; sport: SportKey; seconds: number; distance_km: number; pace_s_per_km: number | null; avg_hr: number | null }
export interface RouteDetail extends Omit<RouteRow, "efforts" | "first" | "last"> { efforts: RouteEffort[] }
export interface SyncStatus {
  running: boolean;
  last_run: { id: number; status: string; started_local: string; finished_local: string | null; error: string | null } | null;
  last_success: { started_local: string } | null;
  synced_through: string | null; next_scheduled_local: string;
  key: { configured: boolean; expires_on: string | null; days_left: number | null; state: string };
  warnings: { level: "info" | "warning" | "critical"; text: string }[];
}

// milestone 5
export interface CourtGeometry { cell_m: number; depth_m: number; half_width_m: number; baseline_m: number; service_m: number; singles_half_m: number; doubles_half_m: number; net_zone_m: number; base_zone_m: number }
export interface TennisRow {
  activity_id: number; date: string; start: string; name: string | null; minutes: number; distance_km: number;
  avg_hr: number | null; max_hr: number | null; calories: number | null; load: number | null; has_gps: boolean; court_id: number | null;
  play_min?: number; net_share?: number; mid_share?: number; base_share?: number; right_share?: number; median_depth_m?: number | null; top_speed_kmh?: number | null;
}
export interface TennisYear { sessions: number; with_gps: number; hours: number; grid: number[][] | null; net_share: number | null; mid_share: number | null; base_share: number | null; right_share: number | null; top_speed_kmh: number | null }
export interface Court { id: number; lat: number; lon: number; angle_deg: number; sessions: number }
export interface Tennis { sessions: TennisRow[]; years: Record<string, TennisYear>; courts: Court[]; geometry: CourtGeometry }
export interface TennisSession extends TennisRow {
  grid: number[][] | null; geometry: CourtGeometry; court: Court | null; per_minute: [number, number | null, number | null][];
  prev_id: number | null; next_id: number | null; number: number; of: number;
}
export interface SnowDay { day: string; places: string[]; activities: number[]; distance_km: number; vertical_m: number; hours: number; runs: number | null; top_speed_kmh: number | null }
export interface SnowSeason { season: string; places: string[]; days_on_snow: number; distance_km: number; vertical_m: number; hours: number; runs: number | null; runs_partial: number | null; top_speed_kmh: number | null; best_day_vertical_m: number; days: SnowDay[] }
export interface Snow { seasons: SnowSeason[]; totals: { seasons: number; days_on_snow: number; vertical_m: number; distance_km: number; top_speed_kmh: number | null } }
export type OutcomeKey = "sleep_score" | "hrv" | "rhr" | "sleep_h";
export interface Driver { key: string; label: string; nights: number; compared: number; diff: number; lo: number; hi: number; clear: boolean }
export interface Outcome { label: string; unit: string; better: "higher" | "lower"; nights: number; since?: string; baseline: number | null; drivers: Driver[]; hidden: { key: string; label: string; nights: number }[] }
export interface RecoveryNight { night: number; mean: number; lo: number; hi: number; n: number }
export interface RecoveryCurve { sessions: number; nights: (RecoveryNight | null)[]; back_by: number | null }
export interface Sleep {
  series: [string, number | null, number | null, number | null, number | null, number | null, number | null][];
  drivers: Record<OutcomeKey, Outcome>;
  recovery: { hard_load?: number; hard_sessions?: number; clean_sessions?: number; metrics: Partial<Record<"hrv" | "rhr", { label: string; unit: string; better: string; overall: RecoveryCurve; years: Record<string, RecoveryCurve> }>> };
  min_nights: number; min_sessions_year: number;
}
export interface Tonight {
  key: string; label: string; unit: string; better: string; ready: boolean; nights?: number; needed?: number;
  night_of?: string; wake_day?: string; prediction?: number; band?: number; average?: number; mae?: number; mae_baseline?: number;
  test_nights?: number; train_nights?: number; contributions?: { feature: string; label: string; value: number; effect: number }[];
  recent?: [string, number, number][];
}
export interface LoadPlan {
  ready: boolean; day: string; fitness: number; fatigue: number; form: number; load_today: number; weekday_pattern: number[];
  weekly_loads: number[]; weekly_average: number; fitness_days: number; fatigue_days: number; peak_fitness: { day: string; value: number };
}
export interface Forecast { tonight: Record<string, Tonight>; plan: LoadPlan }
export interface TrainingLoad { days: [string, number, number, number, number][]; hr_profile: { rest: number; max: number } | null }

// milestone 6
export interface YearTotals { activities: number; active_days: number; longest_streak: number; distance_km: number; foot_km: number; hours: number; ascent_m: number; by_sport: { sport: string; activities: number; distance_km: number; hours: number }[] }
export interface YearAct { activity_id: number; date: string; sport: string; name: string | null; distance_km: number; hours: number }
export interface YearReview {
  year: number | null; years: number[]; partial: boolean; through: string;
  totals: YearTotals; previous: YearTotals | null; first?: YearAct; last?: YearAct;
  months?: { month: number; hours: Record<string, number>; distance_km: Record<string, number>; activities: number }[];
  biggest_day?: { date: string; hours: number; distance_km: number; activities: YearAct[] };
  biggest_week?: { monday: string; hours: number; distance_km: number; activities: number; sports: string[] };
  longest?: Record<string, YearAct>;
  records?: { distance: string; distance_m: number; seconds: number; date: string; activity_id: number; name: string | null; all_time: boolean;
    personal_bests: { date: string; seconds: number; activity_id: number; name: string | null; improved_by: number | null }[] }[];
  places?: { count: number; new: number; top: { place: string; activities: number; new: boolean }[]; new_places: string[] };
  tiles?: { new: number; total_at_year_end: number };
  routes?: { new: number; top: { route_id: number; name: string | null; group: "run" | "walk" | "cycle"; length_km: number; loop: boolean; times: number }[] };
  tennis?: { sessions: number; hours: number; with_gps: number; net_share: number | null; base_share: number | null; right_share: number | null; top_speed_kmh: number | null; longest: YearAct } | null;
  snow?: { days: number; vertical_m: number; distance_km: number; places: string[]; top_speed_kmh: number | null } | null;
  sleep?: { nights: number; score: number | null; hours: number | null; hrv: number | null; rhr: number | null;
    previous: { nights: number; score: number | null; hours: number | null; hrv: number | null; rhr: number | null } | null;
    best_month: { month: number; score: number } | null; worst_month: { month: number; score: number } | null } | null;
  fitness?: { total_load: number; peak_fitness: number; peak_day: string; start_fitness: number; end_fitness: number; weekly: number[] } | null;
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const api = {
  lifetime: () => get<Lifetime>("/api/lifetime"),
  yoy: (sports: string[]) => get<YearOverYear>(`/api/year-over-year?sports=${sports.join(",")}`),
  bestEfforts: () => get<BestEfforts>("/api/best-efforts"),
  tiles: () => get<Tiles>("/api/tiles"),
  tracks: () => get<TrackRow[]>("/api/tracks"),
  routes: () => get<RouteRow[]>("/api/routes"),
  route: (id: number) => get<RouteDetail>(`/api/routes/${id}`),
  renameRoute: async (id: number, name: string) => {
    const r = await fetch(`/api/routes/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name }) });
    if (!r.ok) throw new Error(await r.text());
    return r.json() as Promise<{ id: number; name: string | null }>;
  },
  tennis: () => get<Tennis>("/api/tennis"),
  tennisSession: (id: number) => get<TennisSession>(`/api/tennis/${id}`),
  snow: () => get<Snow>("/api/snow"),
  sleep: () => get<Sleep>("/api/sleep"),
  forecast: () => get<Forecast>("/api/forecast"),
  trainingLoad: () => get<TrainingLoad>("/api/training-load"),
  yearReview: (year?: number) => get<YearReview>(year ? `/api/year-review?year=${year}` : "/api/year-review"),
  syncStatus: () => get<SyncStatus>("/api/sync/status"),
  syncNow: async () => {
    const r = await fetch("/api/sync", { method: "POST" });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail ?? `Sync could not start (${r.status})`);
    return body;
  },
};
