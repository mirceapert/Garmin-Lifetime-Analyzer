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
  syncStatus: () => get<SyncStatus>("/api/sync/status"),
  syncNow: async () => {
    const r = await fetch("/api/sync", { method: "POST" });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.detail ?? `Sync could not start (${r.status})`);
    return body;
  },
};
