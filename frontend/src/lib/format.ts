export const nf = (n: number, d = 0) => n.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d });

export function hms(sec: number): string {
  const s = Math.round(sec), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
}

/** seconds per km -> "5:12" */
export function pace(secPerKm: number): string {
  const s = Math.round(secPerKm);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export const parseDay = (iso: string) => new Date(iso + "T12:00:00");
export const fmtDay = (iso: string) => parseDay(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
export const fmtShort = (iso: string) => parseDay(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export const SPORTS: { key: string; label: string }[] = [
  { key: "run", label: "Running" }, { key: "trail", label: "Trail running" }, { key: "walk", label: "Walking" },
  { key: "tennis", label: "Tennis" }, { key: "snow", label: "Snowboarding" }, { key: "cycle", label: "Cycling" },
  { key: "sail", label: "Sailing" }, { key: "other", label: "Other" },
];
export const sportLabel = (k: string) => SPORTS.find(s => s.key === k)?.label ?? k;
