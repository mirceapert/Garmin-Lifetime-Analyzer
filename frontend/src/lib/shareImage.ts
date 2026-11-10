/** The Year in Review share image: 1080 × 1350 PNG, drawn in the browser. No map, nothing uploaded. */
import type { YearReview } from "../api";
import { hms, nf, parseDay, sportLabel } from "./format";

export const SHARE_W = 1080, SHARE_H = 1350;
export interface ShareOptions { theme: "night" | "day"; name: string; places: boolean }

const SPORT = { run: "#2a78d6", trail: "#eb6834", walk: "#1baf7a", tennis: "#eda100", snow: "#e87ba4", cycle: "#008300", sail: "#6250d6", other: "#8a8f98" } as Record<string, string>;
const THEMES = {
  night: { ground: "#0a1016", ink: "#eef2f5", muted: "#9fb0bf", rule: "#26323d", track: "#1a242d", bar: "#3b4a58", card: "#141c23", accent: "#9085e9" },
  day: { ground: "#f4f1ea", ink: "#15202b", muted: "#4c5966", rule: "#d6d0c4", track: "#e3ddd1", bar: "#b9b2a6", card: "#ffffff", accent: "#5848c9" },
};
const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DIST = { best_1k: "1 km", best_5k: "5 km", best_10k: "10 km", best_hm: "half marathon" } as Record<string, string>;
const MOSTLY: Record<string, string> = { sail: "mostly at sea", tennis: "mostly on court", run: "mostly running", trail: "mostly on trails",
  walk: "mostly walking", snow: "mostly on snow", cycle: "mostly on the bike", other: "mostly other sports" };
const UNDER: Record<string, string> = { sail: "under sail", cycle: "on the bike" };
const DISPLAY = "'Barlow Condensed', 'Arial Narrow', sans-serif", SANS = "'IBM Plex Sans', 'Segoe UI', sans-serif", MONO = "'IBM Plex Mono', monospace";
const longDay = (iso: string) => parseDay(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long" });

export async function fontsReady(): Promise<void> {
  try {
    await Promise.all([`600 64px ${DISPLAY}`, `500 30px ${DISPLAY}`, `400 20px ${SANS}`, `600 20px ${SANS}`, `400 20px ${MONO}`]
      .map(f => document.fonts.load(f)));
  } catch { /* draw with fallbacks */ }
}

interface Stat { value: string; unit: string; label: string }
interface Card { label: string; big: string; sub: string }

export function contentFor(r: YearReview, o: ShareOptions) {
  const t = r.totals, by = Object.fromEntries(t.by_sport.map(b => [b.sport, b]));
  // three totals: on foot first, then the two biggest of sailing, cycling and snowboarding, then climbing
  const stats: Stat[] = [];
  if (t.foot_km >= 1) stats.push({ value: nf(t.foot_km), unit: "km", label: "on foot" });
  const extra: (Stat & { h: number })[] = [];
  for (const sp of ["sail", "cycle"]) if (by[sp]?.distance_km >= 1) extra.push({ value: nf(by[sp].distance_km), unit: "km", label: UNDER[sp], h: by[sp].hours });
  if (r.snow?.vertical_m) extra.push({ value: nf(r.snow.vertical_m), unit: "m", label: "down the mountain", h: by.snow?.hours ?? 0 });
  stats.push(...extra.sort((a, b) => b.h - a.h));
  if (t.ascent_m >= 50) stats.push({ value: nf(t.ascent_m), unit: "m", label: "climbed" });
  stats.push({ value: nf(t.activities), unit: "", label: "activities" }, { value: nf(t.longest_streak), unit: "days", label: "longest streak" });

  const sports = t.by_sport.slice(0, t.by_sport.length > 6 ? 5 : 6).map(b => ({ label: sportLabel(b.sport), color: SPORT[b.sport] ?? SPORT.other, hours: b.hours }));
  if (t.by_sport.length > 6) sports.push({ label: "Everything else", color: SPORT.other, hours: t.by_sport.slice(5).reduce((a, b) => a + b.hours, 0) });

  const months = (r.months ?? []).map(m => Object.values(m.hours).reduce((a, b) => a + b, 0));
  const top = months.indexOf(Math.max(...months));
  let caption = "";
  if (r.months && months[top] > 0) {
    const hrs = r.months[top].hours, [sp, h] = Object.entries(hrs).sort((a, b) => b[1] - a[1])[0];
    caption = `${MONTHS[top]}: ${nf(months[top], 1)} h, ${h / months[top] >= 0.5 ? MOSTLY[sp] ?? "your busiest month" : "your busiest month"}`;
  }

  const cards: Card[] = [];
  // a best you improved on beats one recorded for the first time; then the longer distance
  const gainOf = (e: { personal_bests: { improved_by: number | null }[] }) => e.personal_bests.reduce((a, b) => a + (b.improved_by ?? 0), 0);
  const recs = (r.records ?? []).filter(e => e.personal_bests.length)
    .sort((a, b) => Number(gainOf(b) > 0) - Number(gainOf(a) > 0) || b.distance_m - a.distance_m);
  if (recs[0]) {
    const e = recs[0], last = e.personal_bests[e.personal_bests.length - 1];
    const gain = gainOf(e);
    cards.push({ label: `New ${DIST[e.distance] ?? e.distance} best`, big: hms(last.seconds),
      sub: `${longDay(last.date)}, ${gain > 0 ? `${hms(gain)} faster than before` : "your first one recorded"}` });
  }
  if (r.biggest_day) {
    const d = r.biggest_day, mins = Math.round(d.hours * 60);
    const what = [...new Set(d.activities.map(a => sportLabel(a.sport).toLowerCase()))].join(" and ");
    cards.push({ label: "Biggest day", big: d.distance_km >= 1 ? `${nf(d.distance_km, 1)} km` : `${Math.floor(mins / 60)} h ${mins % 60} min`,
      sub: `${what}, ${longDay(d.date)}${d.distance_km >= 1 ? `, ${Math.floor(mins / 60)} h ${mins % 60} min` : ""}` });
  }
  if (r.tennis) cards.push({ label: "On court", big: `${r.tennis.sessions} session${r.tennis.sessions > 1 ? "s" : ""}`,
    sub: `${nf(r.tennis.hours)} hours${r.tennis.base_share != null ? `, ${Math.round(r.tennis.base_share * 100)}% at the baseline` : ""}` });
  if (r.snow) cards.push({ label: "On snow", big: `${r.snow.days} day${r.snow.days > 1 ? "s" : ""}`, sub: o.places ? r.snow.places.join(", ") : `${nf(r.snow.distance_km)} km on the mountain` });
  if (o.places && r.places && r.places.new > 0) cards.push({ label: "New places", big: `${r.places.new} of ${r.places.count}`, sub: r.places.new_places.slice(0, 4).join(", ") });
  const runL = r.longest?.run ?? r.longest?.trail;
  if (runL) cards.push({ label: "Longest run", big: `${nf(runL.distance_km, 1)} km`, sub: longDay(runL.date) });
  if (r.tiles?.new) cards.push({ label: "Explored", big: `${nf(r.tiles.new)} squares`, sub: "new on the map" });
  if (r.sleep?.score) cards.push({ label: "Sleep", big: `${r.sleep.score} score`, sub: `average over ${r.sleep.nights} nights` });

  const shown = cards.slice(0, 4);
  const footer = shown.some(c => c.label === "Explored") || !r.tiles?.new ? `${nf(t.activities)} activities` : `${nf(r.tiles.new)} new map squares explored`;
  return { stats: stats.slice(0, 3), sports, months, top, caption, cards: shown, footer };
}

export function drawShare(canvas: HTMLCanvasElement, r: YearReview, o: ShareOptions): void {
  canvas.width = SHARE_W; canvas.height = SHARE_H;
  const x = canvas.getContext("2d")!;
  const c = THEMES[o.theme], d = contentFor(r, o);
  const L = 76, R = SHARE_W - 76, W = R - L;
  const spacing = (px: number) => { (x as unknown as { letterSpacing: string }).letterSpacing = `${px}px`; };
  const text = (s: string, px: number, y: number, opt: { font?: string; weight?: number; color?: string; align?: CanvasTextAlign; at?: number; max?: number; track?: number } = {}) => {
    let size = px;
    spacing(opt.track ?? 0);
    const set = () => { x.font = `${opt.weight ?? 400} ${size}px ${opt.font ?? SANS}`; };
    set();
    while (opt.max && x.measureText(s).width > opt.max && size > 10) { size -= 1; set(); }
    x.fillStyle = opt.color ?? c.ink; x.textAlign = opt.align ?? "left";
    x.fillText(s, opt.at ?? L, y);
    const w = x.measureText(s).width;
    spacing(0);
    return w;
  };
  const withUnit = (value: string, unit: string, px: number, y: number, at: number, align: "left" | "right" = "left") => {
    x.font = `600 ${px}px ${DISPLAY}`; const vw = x.measureText(value).width;
    x.font = `500 ${Math.round(px * 0.42)}px ${DISPLAY}`; const uw = unit ? x.measureText(unit).width + 8 : 0;
    const start = align === "left" ? at : at - vw - uw;
    text(value, px, y, { font: DISPLAY, weight: 600, at: start });
    if (unit) text(unit, Math.round(px * 0.42), y, { font: DISPLAY, weight: 500, color: c.muted, at: start + vw + 8 });
  };
  const round = (rx: number, ry: number, w: number, h: number, rad: [number, number, number, number], fill: string) => {
    x.beginPath(); x.roundRect(rx, ry, w, h, rad); x.fillStyle = fill; x.fill();
  };

  x.fillStyle = c.ground; x.fillRect(0, 0, SHARE_W, SHARE_H);
  x.textBaseline = "alphabetic";

  // title
  const who = o.name.trim() ? `${o.name.trim()}'s year in review` : "Year in review";
  text(who.toUpperCase(), 22, 96, { weight: 600, color: c.muted, track: 3, max: 560 });
  text(String(r.year), 236, 300, { font: DISPLAY, weight: 600, track: -4 });
  withUnit(nf(r.totals.hours), "hours", 64, 150, R, "right");
  text(`moving, on ${r.totals.active_days} day${r.totals.active_days === 1 ? "" : "s"}`, 22, 186, { color: c.muted, align: "right", at: R });

  // three totals
  x.fillStyle = c.rule; x.fillRect(L, 340, W, 2); x.fillRect(L, 488, W, 2);
  const colW = W / 3;
  d.stats.forEach((s, i) => {
    const cx = L + i * colW + (i ? 30 : 0);
    if (i) { x.fillStyle = c.rule; x.fillRect(L + i * colW, 342, 2, 146); }
    withUnit(s.value, s.unit, 72, 428, cx);
    text(s.label, 22, 464, { color: c.muted, at: cx, max: colW - 40 });
  });

  // hours by sport
  text("HOURS BY SPORT", 18, 556, { weight: 600, color: c.muted, track: 2 });
  const maxH = Math.max(...d.sports.map(s => s.hours), 0.1);
  const barL = 250, barR = 572;
  d.sports.forEach((s, i) => {
    const y = 600 + i * 40;
    text(s.label, 22, y + 8, { at: L, max: barL - L - 14 });
    round(barL, y - 6, barR - barL, 16, [0, 6, 6, 0], c.track);
    round(barL, y - 6, Math.max(4, (barR - barL) * (s.hours / maxH)), 16, [0, 6, 6, 0], s.color);
    text(nf(s.hours, 1), 20, y + 8, { font: MONO, align: "right", at: 648 });
  });

  // month by month
  const mL = 704, mW = R - mL;
  text("MONTH BY MONTH", 18, 556, { weight: 600, color: c.muted, track: 2, at: mL });
  const maxM = Math.max(...d.months, 0.1), bw = (mW - 11 * 6) / 12, base = 790;
  d.months.forEach((v, i) => {
    const h = Math.max(2, 200 * (v / maxM)), bx = mL + i * (bw + 6);
    round(bx, base - h, bw, h, [4, 4, 0, 0], i === d.top && v > 0 ? c.accent : c.bar);
    text("JFMAMJJASOND"[i], 15, base + 26, { color: c.muted, align: "center", at: bx + bw / 2 });
  });
  if (d.caption) text(d.caption, 19, 852, { color: c.muted, at: mL, max: mW });

  // highlight cards
  const cw = (W - 18) / 2, ch = 150;
  d.cards.forEach((card, i) => {
    const cx = L + (i % 2) * (cw + 18), cy = 900 + Math.floor(i / 2) * (ch + 18);
    round(cx, cy, cw, ch, [14, 14, 14, 14], c.card);
    text(card.label.toUpperCase(), 17, cy + 44, { weight: 600, color: c.accent, track: 2, at: cx + 26, max: cw - 52 });
    text(card.big, 58, cy + 102, { font: DISPLAY, weight: 600, at: cx + 26, max: cw - 52 });
    text(card.sub, 20, cy + 132, { color: c.muted, at: cx + 26, max: cw - 52 });
  });

  // footer
  text(d.footer, 18, 1292, { color: c.muted });
  text("GARMIN DATA ANALYZER", 22, 1292, { font: DISPLAY, weight: 600, color: c.muted, align: "right", at: R, track: 1 });
}
