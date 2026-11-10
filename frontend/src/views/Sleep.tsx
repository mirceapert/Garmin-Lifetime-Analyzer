import { useState } from "react";
import type { ChartConfiguration, ChartDataset } from "chart.js";
import { api, type Driver, type OutcomeKey, type Outcome, type Sleep as SleepData } from "../api";
import { fmtDay, nf, parseDay } from "../lib/format";
import { load, save } from "../lib/storage";
import { alpha, cssVar, mix } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";

const OUTCOMES: { key: OutcomeKey; col: number; label: string; digits: number }[] = [
  { key: "sleep_score", col: 1, label: "Sleep score", digits: 0 },
  { key: "hrv", col: 3, label: "Night HRV", digits: 0 },
  { key: "rhr", col: 4, label: "Resting HR", digits: 0 },
  { key: "sleep_h", col: 2, label: "Sleep time", digits: 1 },
];
const unitOf = (o: Outcome) => (o.unit === "h" ? " h" : o.unit ? ` ${o.unit}` : "");
const signed = (v: number, d: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(Math.abs(v), d)}`;

export function Sleep() {
  const [data, err] = useData(api.sleep);
  const [key, setKey] = useState<OutcomeKey>(() => load("sleep-outcome", "sleep_score"));
  const pick = (k: OutcomeKey) => { setKey(k); save("sleep-outcome", k); };
  if (err) return <p className="empty">Could not load sleep: {err}</p>;
  if (!data) return <p className="empty">Loading sleep…</p>;
  const meta = OUTCOMES.find(o => o.key === key)!;
  const o = data.drivers[key];
  return (
    <section className="view">
      <div className="view-head"><h2>Sleep &amp; recovery</h2>
        <p className="muted">What goes with your better and worse nights, and how long your body takes to settle after a hard session. A night belongs to the morning you wake up; "that day" is the day before it.</p></div>
      <div className="controls">
        <div className="seg" role="group" aria-label="Measure">
          {OUTCOMES.map(x => <button key={x.key} aria-pressed={x.key === key} onClick={() => pick(x.key)}>{x.label}</button>)}
        </div>
        {o?.since && <span className="small muted">{nf(o.nights)} nights since {fmtDay(o.since)}</span>}
      </div>
      <Trend data={data} col={meta.col} label={meta.label} digits={meta.digits} unit={o ? unitOf(o) : ""} />
      {o && <Drivers o={o} digits={meta.digits === 0 ? 1 : 2} min={data.min_nights} />}
      <Recovery data={data} />
    </section>
  );
}

function Trend({ data, col, label, digits, unit }: { data: SleepData; col: number; label: string; digits: number; unit: string }) {
  const pts = data.series.filter(r => r[col] != null).map(r => ({ x: parseDay(r[0]).getTime(), y: (r[col] as number) }));
  const ref = useChart(() => {
    if (!pts.length) return null;
    const avg = pts.map((p, i) => {
      const w = pts.slice(Math.max(0, i - 27), i + 1).filter(q => q.x >= p.x - 28 * 864e5);
      return { x: p.x, y: w.reduce((a, q) => a + q.y, 0) / w.length };
    });
    const ink = cssVar("--accent");
    return {
      type: "line",
      data: { datasets: [
        { type: "scatter", label: "Night", data: pts, backgroundColor: alpha(ink, 0.18), pointRadius: 1.6, pointHoverRadius: 4 },
        { label: "28-night average", data: avg, borderColor: ink, borderWidth: 2, pointRadius: 0 },
      ] },
      options: {
        interaction: { mode: "nearest", intersect: false, axis: "x" },
        scales: {
          x: { type: "linear", grid: { display: false },
            afterBuildTicks: ax => { const t = []; for (let y = new Date(ax.min).getFullYear() + 1; y <= new Date(ax.max).getFullYear(); y++) t.push({ value: new Date(y, 0, 1).getTime() }); ax.ticks = t; },
            ticks: { callback: v => new Date(Number(v)).getFullYear() } },
          y: { grid: { color: cssVar("--line-2") }, title: { display: !!unit.trim(), text: unit.trim() } },
        },
        plugins: { legend: { position: "top", align: "end" }, tooltip: { callbacks: {
          title: it => new Date(it[0].parsed.x ?? 0).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
          label: it => ` ${it.dataset.label}: ${nf(it.parsed.y ?? 0, digits)}${unit}`,
        } } },
      },
    };
  }, [data, col]);
  return (
    <div className="panel">
      <div className="panel-head"><h3>{label} over time</h3><span className="small muted">Each dot is a night; the line is your 28-night average</span></div>
      <div className="chart">{pts.length ? <canvas ref={ref} /> : <p className="empty">Garmin has no {label.toLowerCase()} for you yet.</p>}</div>
    </div>
  );
}

function Drivers({ o, digits, min }: { o: Outcome; digits: number; min: number }) {
  if (!o.drivers.length)
    return <div className="panel"><h3>What goes with your nights</h3><p className="empty">Not enough nights with {o.label.toLowerCase()} yet: {o.nights} so far, {min * 2} needed.</p></div>;
  const span = Math.max(...o.drivers.flatMap(d => [Math.abs(d.lo), Math.abs(d.hi)]), 0.1) * 1.08;
  const pos = (v: number) => `${50 + (v / span) * 50}%`;
  const good = (d: Driver) => (o.better === "higher" ? d.diff > 0 : d.diff < 0);
  return (
    <div className="panel">
      <div className="panel-head"><h3>What goes with your {o.label.toLowerCase()}</h3>
        <span className="small muted">Difference from nights without it, with a 95% range. Your average: {nf(o.baseline ?? 0, 1)}{unitOf(o)}</span></div>
      <div className="forest" role="table" aria-label={`Drivers of ${o.label}`}>
        {o.drivers.map(d => (
          <div key={d.key} className={`frow ${d.clear ? "" : "unclear"}`} role="row">
            <div className="flabel" role="cell">{d.label}<span className="small muted"> · {d.nights} nights</span></div>
            <div className="fplot" role="cell" aria-label={`${signed(d.diff, digits)}, range ${signed(d.lo, digits)} to ${signed(d.hi, digits)}`}>
              <span className="fzero" />
              <span className="fbar" style={{ left: pos(Math.min(d.lo, d.hi)), width: `${((d.hi - d.lo) / span) * 50}%` }} />
              <span className={`fdot ${d.clear ? (good(d) ? "good" : "bad") : ""}`} style={{ left: pos(d.diff) }} />
            </div>
            <div className="fval mono" role="cell">{signed(d.diff, digits)}{unitOf(o)}<span className="small muted"> ({signed(d.lo, digits)} to {signed(d.hi, digits)})</span></div>
          </div>
        ))}
      </div>
      <p className="note">
        A filled dot means the range stays clear of zero: <span className="legend-dot good" /> better for you, <span className="legend-dot bad" /> worse. A hollow dot means it could be chance.
        Each night is compared with your level in the two months around it, so getting fitter over the years doesn't pass for a driver. These go together in your history; they don't prove one causes the other.
        {o.hidden.length > 0 && <> Not shown (fewer than {min} nights): {o.hidden.map(h => `${h.label.toLowerCase()} (${h.nights})`).join(", ")}.</>}
      </p>
    </div>
  );
}

function Recovery({ data }: { data: SleepData }) {
  const metrics = data.recovery.metrics;
  const keys = (["hrv", "rhr"] as const).filter(k => metrics[k]?.overall.sessions);
  const [k, setK] = useState<"hrv" | "rhr">(() => load("recovery-metric", "hrv"));
  const cur = keys.includes(k) ? k : keys[0];
  const m = cur ? metrics[cur]! : null;
  const years = m ? Object.keys(m.years) : [];
  const ref = useChart(() => {
    if (!m) return null;
    const acc = cssVar("--accent"), line = cssVar("--ink-3");
    const n = m.overall.nights.filter(Boolean);
    const labels = ["Before", ...n.map(x => `Night ${x!.night}`)];
    const ds: ChartDataset<"line", (number | null)[]>[] = [
      { label: "95% range", data: [0, ...n.map(x => x!.hi)], borderWidth: 0, pointRadius: 0, backgroundColor: alpha(acc, 0.14), fill: "+1" },
      { label: "range-low", data: [0, ...n.map(x => x!.lo)], borderWidth: 0, pointRadius: 0 },
      { label: `All years (${m.overall.sessions} sessions)`, data: [0, ...n.map(x => x!.mean)], borderColor: acc, backgroundColor: acc, borderWidth: 2.5, pointRadius: 4 },
    ];
    years.forEach((y, i) => {
      const c = mix(cssVar("--surface"), cssVar("--ink"), 0.35 + (0.45 * i) / Math.max(years.length - 1, 1));
      ds.push({ label: `${y} (${m.years[y].sessions})`, data: [0, ...m.years[y].nights.map(x => x?.mean ?? null)], borderColor: c, backgroundColor: c, borderWidth: 1.5, pointRadius: 2.5, borderDash: [4, 3] });
    });
    return ({
      type: "line",
      data: { labels, datasets: ds },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: { x: { grid: { display: false } }, y: { title: { display: true, text: `change from your usual (${m.unit})` }, grid: { color: (c: { tick: { value: number } }) => (c.tick.value === 0 ? line : cssVar("--line-2")) } } },
        plugins: { legend: { position: "top", align: "end", labels: { filter: (it: { text: string }) => !it.text.startsWith("range") && it.text !== "95% range" } },
          tooltip: { filter: (it: { dataset: { label?: string } }) => !it.dataset.label?.includes("range"), callbacks: { label: (it: { dataset: { label?: string }; parsed: { y: number | null } }) => ` ${it.dataset.label}: ${signed(it.parsed.y ?? 0, 1)} ${m.unit}` } } },
      },
    }) as ChartConfiguration;
  }, [data, cur]);
  if (!m) return <div className="panel"><h3>Recovery after hard sessions</h3><p className="empty">Not enough nights with HRV or resting heart rate after hard sessions yet.</p></div>;
  const n1 = m.overall.nights[0];
  return (
    <div className="panel">
      <div className="panel-head"><h3>Recovery after hard sessions</h3>
        <div className="seg" role="group" aria-label="Recovery measure">
          {keys.map(x => <button key={x} aria-pressed={x === cur} onClick={() => { setK(x); save("recovery-metric", x); }}>{metrics[x]!.label}</button>)}
        </div></div>
      <div className="callout">
        <div><span className="eyebrow">Night after</span><b>{n1 ? `${signed(n1.mean, 1)} ${m.unit}` : "–"}</b></div>
        <div><span className="eyebrow">Back to usual</span><b>{m.overall.back_by ? `night ${m.overall.back_by}` : "not within 4 nights"}</b></div>
        <div><span className="eyebrow">Hard sessions</span><b>{m.overall.sessions}</b></div>
        <div><span className="eyebrow">Hard means load over</span><b>{nf(data.recovery.hard_load ?? 0)}</b></div>
      </div>
      <div className="chart"><canvas ref={ref} /></div>
      <p className="note">Your hardest sessions are your top 15% by training load. Each is compared with your median over the 7 nights before it. Sessions followed by another hard one within 3 days are left out. A year gets its own line from {data.min_sessions_year} sessions{cur === "hrv" && data.drivers.hrv?.since ? `; Garmin has night HRV for you since ${fmtDay(data.drivers.hrv.since)}` : ""}.</p>
    </div>
  );
}
