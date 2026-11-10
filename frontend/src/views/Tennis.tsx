import { useEffect, useMemo, useRef, useState } from "react";
import { api, type CourtGeometry, type TennisRow } from "../api";
import { fmtDay, nf } from "../lib/format";
import { load, save } from "../lib/storage";
import { alpha, cssVar } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";

const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

export function Tennis({ selected }: { selected: number | null }) {
  const [data, err] = useData(api.tennis);
  const years = useMemo(() => Object.keys(data?.years ?? {}).filter(y => data!.years[y].grid), [data]);
  const [year, setYear] = useState<string>(() => load("tennis-year", "all"));
  const pick = (y: string) => { setYear(y); save("tennis-year", y); };

  if (err) return <p className="empty">Could not load tennis: {err}</p>;
  if (!data) return <p className="empty">Loading tennis…</p>;
  if (!data.sessions.length) return <p className="empty">No tennis sessions yet.</p>;
  if (selected) return <SessionView id={selected} />;

  const yr = year !== "all" && data.years[year] ? year : "all";
  const shown = yr === "all" ? years : [yr];
  const grid = sumGrids(shown.map(y => data.years[y].grid!));
  const weight = (k: "net_share" | "mid_share" | "base_share" | "right_share") => {
    let num = 0, den = 0;
    for (const s of data.sessions) if ((yr === "all" || s.date.startsWith(yr)) && s[k] != null) { num += s[k]! * (s.play_min ?? 0); den += s.play_min ?? 0; }
    return den ? num / den : null;
  };
  const inYear = data.sessions.filter(s => yr === "all" || s.date.startsWith(yr));
  const withGps = inYear.filter(s => s.court_id != null);
  return (
    <section className="view">
      <div className="view-head"><h2>Tennis</h2>
        <p className="muted">Where you move on court, from the watch's GPS. Every session is folded into one half court seen from your baseline, so both ends add up. Right is your forehand side. Wrist GPS is good to a few metres, so read the zones as tendencies, not lines.</p></div>
      <div className="controls">
        <div className="seg" role="group" aria-label="Year">
          <button aria-pressed={yr === "all"} onClick={() => pick("all")}>All years</button>
          {years.map(y => <button key={y} aria-pressed={yr === y} onClick={() => pick(y)}>{y}</button>)}
        </div>
      </div>
      <div className="grid-side">
        <div className="panel">
          <div className="panel-head"><h3>Court coverage, {yr === "all" ? "all years" : yr}</h3><span className="small muted">{withGps.length} sessions with GPS</span></div>
          <CourtMap grid={grid} g={data.geometry} />
        </div>
        <div className="panel">
          <h3>Where you play</h3>
          <div className="statlist">
            <div><span>Near the net <span className="small muted">(under {data.geometry.net_zone_m} m)</span></span><span className="v">{pct(weight("net_share"))}</span></div>
            <div><span>Mid court</span><span className="v">{pct(weight("mid_share"))}</span></div>
            <div><span>Baseline <span className="small muted">(beyond {data.geometry.base_zone_m} m)</span></span><span className="v">{pct(weight("base_share"))}</span></div>
            <div><span>Forehand side</span><span className="v">{pct(weight("right_share"))}</span></div>
            <div><span>Sessions</span><span className="v">{inYear.length}</span></div>
            <div><span>Hours</span><span className="v">{nf(inYear.reduce((a, s) => a + s.minutes, 0) / 60, 0)}</span></div>
          </div>
          <p className="note">Near the net includes the changeovers at the net posts. Breaks where you stood still for more than 45 s are left out.</p>
        </div>
      </div>
      <SessionTable rows={inYear} />
    </section>
  );
}

function sumGrids(grids: number[][][]): number[][] | null {
  if (!grids.length) return null;
  return grids[0].map((row, i) => row.map((_, j) => grids.reduce((a, g) => a + g[i][j], 0)));
}

type SortKey = "date" | "minutes" | "avg_hr" | "load" | "top_speed_kmh" | "base_share" | "net_share";

function SessionTable({ rows }: { rows: TennisRow[] }) {
  const [sort, setSort] = useState<{ k: SortKey; desc: boolean }>({ k: "date", desc: true });
  const sorted = [...rows].sort((a, b) => {
    const va = a[sort.k] ?? -Infinity, vb = b[sort.k] ?? -Infinity;
    const c = va < vb ? -1 : va > vb ? 1 : 0;
    return sort.desc ? -c : c;
  });
  const th = (k: SortKey, label: string, n = true) => (
    <th className={n ? "n" : undefined} aria-sort={sort.k === k ? (sort.desc ? "descending" : "ascending") : "none"}>
      <button className="sortbtn" onClick={() => setSort({ k, desc: sort.k === k ? !sort.desc : true })}>{label}{sort.k === k ? (sort.desc ? " ↓" : " ↑") : ""}</button>
    </th>
  );
  const open = (id: number) => { location.hash = `tennis-${id}`; };
  return (
    <div className="panel">
      <div className="panel-head"><h3>Sessions</h3><span className="small muted">Pick one to see it on its own. Click a heading to sort.</span></div>
      <div className="tablewrap"><table>
        <thead><tr>{th("date", "Date", false)}<th>Start</th>{th("minutes", "Minutes")}{th("avg_hr", "Avg HR")}{th("load", "Load")}{th("top_speed_kmh", "Top km/h")}{th("net_share", "Net")}{th("base_share", "Baseline")}</tr></thead>
        <tbody>{sorted.map(s => (
          <tr key={s.activity_id} className="click" tabIndex={0} onClick={() => open(s.activity_id)} onKeyDown={e => e.key === "Enter" && open(s.activity_id)}>
            <td>{fmtDay(s.date)}</td><td>{s.start}</td><td className="n">{s.minutes}</td><td className="n">{s.avg_hr ?? "–"}</td>
            <td className="n">{s.load ?? "–"}</td><td className="n">{s.top_speed_kmh ? nf(s.top_speed_kmh, 1) : "–"}</td>
            <td className="n">{s.court_id ? pct(s.net_share) : <span className="muted">no GPS</span>}</td><td className="n">{s.court_id ? pct(s.base_share) : ""}</td>
          </tr>))}</tbody>
      </table></div>
    </div>
  );
}

function SessionView({ id }: { id: number }) {
  const [s, err] = useData(() => api.tennisSession(id), [id]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (!s || (e.target as HTMLElement).closest("input,textarea")) return;
      if (e.key === "ArrowLeft" && s.prev_id) location.hash = `tennis-${s.prev_id}`;
      if (e.key === "ArrowRight" && s.next_id) location.hash = `tennis-${s.next_id}`;
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [s]);
  const pm = s?.per_minute ?? [];
  const hrRef = useChart(() => pm.some(p => p[1] != null) ? lineCfg(pm.map(p => p[0]), pm.map(p => p[1]), "Heart rate", "bpm", cssVar("--accent")) : null, [s]);
  const spRef = useChart(() => pm.some(p => p[2] != null) ? lineCfg(pm.map(p => p[0]), pm.map(p => p[2] == null ? null : p[2] * 3.6), "Speed", "km/h", cssVar("--tennis")) : null, [s]);
  if (err) return <p className="empty">Could not load the session: {err}</p>;
  if (!s) return <p className="empty">Loading the session…</p>;
  return (
    <section className="view">
      <div className="controls">
        <a className="btn" href="#tennis">← All sessions</a>
        <a className="btn" href={s.prev_id ? `#tennis-${s.prev_id}` : undefined} aria-disabled={!s.prev_id}>Previous</a>
        <a className="btn" href={s.next_id ? `#tennis-${s.next_id}` : undefined} aria-disabled={!s.next_id}>Next</a>
        <span className="small muted">Session {s.number} of {s.of}. Arrow keys move too.</span>
      </div>
      <div className="view-head"><h2>{s.name ?? "Tennis"}, {fmtDay(s.date)}</h2>
        <p className="muted">Started {s.start}, {s.minutes} minutes{s.court ? `, on a court played ${s.court.sessions} times` : ""}.</p></div>
      <div className="callout">
        <div><span className="eyebrow">Avg heart rate</span><b>{s.avg_hr ?? "–"}</b></div>
        <div><span className="eyebrow">Max heart rate</span><b>{s.max_hr ?? "–"}</b></div>
        <div><span className="eyebrow">Training load</span><b>{s.load ?? "–"}</b></div>
        <div><span className="eyebrow">Distance</span><b>{nf(s.distance_km, 2)} km</b></div>
        <div><span className="eyebrow">Top speed</span><b>{s.top_speed_kmh ? `${nf(s.top_speed_kmh, 1)} km/h` : "–"}</b></div>
        <div><span className="eyebrow">Calories</span><b>{s.calories ?? "–"}</b></div>
      </div>
      <div className="grid-side">
        <div className="panel">
          <div className="panel-head"><h3>Court coverage</h3>{s.play_min != null && <span className="small muted">{s.play_min} minutes of play, breaks left out</span>}</div>
          {s.grid ? <CourtMap grid={s.grid} g={s.geometry} /> : <p className="empty">No GPS for this session (indoor, or GPS was off), so no court map.</p>}
        </div>
        <div className="panel">
          <h3>Zones</h3>
          <div className="statlist">
            <div><span>Near the net</span><span className="v">{pct(s.net_share)}</span></div>
            <div><span>Mid court</span><span className="v">{pct(s.mid_share)}</span></div>
            <div><span>Baseline</span><span className="v">{pct(s.base_share)}</span></div>
            <div><span>Forehand side</span><span className="v">{pct(s.right_share)}</span></div>
            <div><span>Typical distance from the net</span><span className="v">{s.median_depth_m != null ? `${nf(s.median_depth_m, 1)} m` : "–"}</span></div>
          </div>
        </div>
      </div>
      <div className="grid2">
        <div className="panel"><h3>Heart rate per minute</h3><div className="chart short">{pm.some(p => p[1] != null) ? <canvas ref={hrRef} /> : <p className="empty">No heart rate recorded.</p>}</div></div>
        <div className="panel"><h3>Speed per minute</h3><div className="chart short">{pm.some(p => p[2] != null) ? <canvas ref={spRef} /> : <p className="empty">No speed recorded.</p>}</div></div>
      </div>
    </section>
  );
}

function lineCfg(xs: number[], ys: (number | null)[], label: string, unit: string, color: string) {
  return {
    type: "line" as const,
    data: { labels: xs, datasets: [{ label, data: ys, borderColor: color, backgroundColor: alpha(color, 0.12), fill: true, borderWidth: 2, pointRadius: 0, tension: 0.25, spanGaps: true }] },
    options: {
      interaction: { mode: "index" as const, intersect: false },
      scales: { x: { grid: { display: false }, title: { display: true, text: "minute" }, ticks: { maxTicksLimit: 8 } },
        y: { title: { display: true, text: unit }, grid: { color: cssVar("--line-2") } } },
      plugins: { legend: { display: false }, tooltip: { callbacks: { title: (it: { label: string }[]) => `Minute ${it[0].label}`, label: (it: { parsed: { y: number | null } }) => ` ${nf(it.parsed.y ?? 0, unit === "km/h" ? 1 : 0)} ${unit}` } } },
    },
  };
}

/** Half court seen from behind your baseline: the net at the top, your right on the right. */
function CourtMap({ grid, g }: { grid: number[][] | null; g: CourtGeometry }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [tip, setTip] = useState<string | null>(null);
  const total = useMemo(() => (grid ? grid.flat().reduce((a, b) => a + b, 0) : 0), [grid]);
  const geo = useMemo(() => {
    const pad = 22, mW = g.half_width_m * 2, mH = g.depth_m;
    return { pad, mW, mH };
  }, [g]);
  useEffect(() => {
    const c = ref.current;
    if (!c || !grid) return;
    const dpr = window.devicePixelRatio || 1;
    const W = c.clientWidth, s = (W - 2 * geo.pad) / geo.mW, H = geo.mH * s + 2 * geo.pad;
    c.style.height = `${H}px`;
    c.width = W * dpr; c.height = H * dpr;
    const x = c.getContext("2d")!;
    x.setTransform(dpr, 0, 0, dpr, 0, 0);
    const X = (lat: number) => geo.pad + (lat + g.half_width_m) * s, Y = (d: number) => geo.pad + d * s;
    x.fillStyle = cssVar("--night"); x.fillRect(0, 0, W, H);
    const max = Math.max(...grid.flat(), 1);
    const hue = cssVar("--tennis");
    grid.forEach((row, i) => row.forEach((v, j) => {
      if (v < max * 0.03) return;                                    // a few stray GPS seconds
      x.fillStyle = alpha(hue, 0.12 + 0.88 * Math.pow(v / max, 0.75));
      x.fillRect(X(j * g.cell_m - g.half_width_m) + 1, Y(i * g.cell_m) + 1, g.cell_m * s - 2, g.cell_m * s - 2);
    }));
    // court lines
    x.strokeStyle = "rgba(255,255,255,.75)"; x.lineWidth = 1.5;
    const ln = (a: number, b: number, cc: number, d: number) => { x.beginPath(); x.moveTo(X(a), Y(b)); x.lineTo(X(cc), Y(d)); x.stroke(); };
    ln(-g.doubles_half_m, g.baseline_m, g.doubles_half_m, g.baseline_m);
    ln(-g.singles_half_m, g.service_m, g.singles_half_m, g.service_m);
    for (const w of [g.singles_half_m, g.doubles_half_m]) { ln(-w, 0, -w, g.baseline_m); ln(w, 0, w, g.baseline_m); }
    ln(0, 0, 0, g.service_m);
    x.lineWidth = 3; ln(-g.doubles_half_m - 0.9, 0, g.doubles_half_m + 0.9, 0);
    x.fillStyle = "rgba(255,255,255,.8)"; x.font = `600 11px ${cssVar("--f-body")}`;
    x.textAlign = "center"; x.fillText("NET", X(0), geo.pad - 7);
    x.textAlign = "left"; x.fillText("Backhand side", geo.pad, H - 7);
    x.textAlign = "right"; x.fillText("Forehand side", W - geo.pad, H - 7);
  }, [grid, g, geo]);
  if (!grid || !total) return <p className="empty">No court coverage for this selection.</p>;
  const move = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const c = ref.current!, r = c.getBoundingClientRect(), s = (r.width - 2 * geo.pad) / geo.mW;
    const lat = (e.clientX - r.left - geo.pad) / s - g.half_width_m, d = (e.clientY - r.top - geo.pad) / s;
    const i = Math.floor(d / g.cell_m), j = Math.floor((lat + g.half_width_m) / g.cell_m);
    const v = grid[i]?.[j];
    setTip(v == null ? null : `${nf(Math.max(d, 0), 0)}–${nf(d + 1, 0)} m from the net, ${lat >= 0 ? "right" : "left"} ${nf(Math.abs(lat), 0)} m: ${nf(v / 60, 1)} min (${nf((100 * v) / total, 1)}%)`);
  };
  return (
    <div className="court">
      <canvas ref={ref} onMouseMove={move} onMouseLeave={() => setTip(null)} role="img" aria-label="Heatmap of time spent on each square metre of a half tennis court" />
      <p className="small muted court-tip">{tip ?? "Brighter squares: more time spent. Hover a square for the minutes."}</p>
    </div>
  );
}
