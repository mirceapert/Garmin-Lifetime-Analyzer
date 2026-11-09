import { useEffect, useRef, useState } from "react";
import { api, type RouteDetail } from "../api";
import { fmtDay, hms, nf, pace, parseDay } from "../lib/format";
import { decode } from "../lib/polyline";
import { alpha, cssVar } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";

const GROUP_LABEL = { run: "Running", walk: "Walking", cycle: "Cycling" } as const;
const GROUP_COLOR = { run: "--run", walk: "--walk", cycle: "--cycle" } as const;

const routeTitle = (r: { name: string | null; length_km: number; loop: boolean; group: keyof typeof GROUP_LABEL }) =>
  r.name ?? `${nf(r.length_km, 1)} km ${GROUP_LABEL[r.group].toLowerCase()} ${r.loop ? "loop" : "route"}`;

export function Routes({ selected }: { selected: number | null }) {
  const [rows, err] = useData(api.routes);
  const [names, setNames] = useState<Record<number, string | null>>({});
  if (err) return <p className="empty">Could not load routes: {err}</p>;
  if (!rows) return <p className="empty">Loading routes…</p>;
  if (!rows.length) return <p className="empty">No route repeated three times yet.</p>;
  const list = rows.map(r => (r.id in names ? { ...r, name: names[r.id] } : r));
  const current = list.find(r => r.id === selected) ?? list[0];
  return (
    <section className="view">
      <div className="view-head"><h2>Routes you repeat</h2>
        <p className="muted">Found by comparing the shape of every GPS track. Pick one to see how you have done on it over the years, and give it a name you recognise.</p></div>
      <div className="route-cards">
        {list.map(r => (
          <button key={r.id} className="route-card" aria-pressed={r.id === current.id} onClick={() => { location.hash = `routes-${r.id}`; }}>
            <Thumb shape={r.shape} colorVar={GROUP_COLOR[r.group]} />
            <span className="rt">{routeTitle(r)}</span>
            <span className="rs"><span className="swatch" style={{ background: `var(${GROUP_COLOR[r.group]})` }} />{GROUP_LABEL[r.group]} · {r.efforts} times</span>
          </button>
        ))}
      </div>
      <RoutePanel key={current.id} id={current.id} onRenamed={(id, n) => setNames({ ...names, [id]: n })} />
    </section>
  );
}

function Thumb({ shape, colorVar }: { shape: string; colorVar: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1, W = c.clientWidth || 150, H = c.clientHeight || 86;
    c.width = W * dpr; c.height = H * dpr;
    const g = c.getContext("2d")!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const pts = decode(shape);
    const k = Math.cos((pts[0][0] * Math.PI) / 180);
    const xs = pts.map(p => p[1] * k), ys = pts.map(p => -p[0]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const s = Math.min((W - 16) / (x1 - x0 || 1), (H - 16) / (y1 - y0 || 1));
    const ox = (W - (x1 - x0) * s) / 2, oy = (H - (y1 - y0) * s) / 2;
    g.strokeStyle = cssVar(colorVar); g.lineWidth = 2; g.lineJoin = "round"; g.beginPath();
    xs.forEach((x, i) => { const px = ox + (x - x0) * s, py = oy + (ys[i] - y0) * s; if (i) g.lineTo(px, py); else g.moveTo(px, py); });
    g.stroke();
    g.fillStyle = "#fff"; g.beginPath(); g.arc(ox + (xs[0] - x0) * s, oy + (ys[0] - y0) * s, 3, 0, 7); g.fill();
  }, [shape, colorVar]);
  return <canvas ref={ref} aria-hidden="true" />;
}

function RoutePanel({ id, onRenamed }: { id: number; onRenamed: (id: number, name: string | null) => void }) {
  const [r, err] = useData(() => api.route(id), [id]);
  const [draft, setDraft] = useState<string>("");
  const [saved, setSaved] = useState<string | null>(null);
  useEffect(() => { if (r) setDraft(r.name ?? ""); }, [r]);

  const efforts = (r?.efforts ?? []).filter(e => e.pace_s_per_km);
  const byYear = new Map<number, typeof efforts>();
  for (const e of efforts) { const y = Number(e.date.slice(0, 4)); (byYear.get(y) ?? byYear.set(y, []).get(y)!).push(e); }
  const years = [...byYear.keys()].sort();
  const med = (a: number[]) => { const s = [...a].sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
  const fastest = efforts.length ? efforts.reduce((a, b) => (b.seconds < a.seconds ? b : a)) : null;
  const solid = years.filter(y => byYear.get(y)!.length >= 3);
  const firstY = solid[0] ?? years[0], lastY = solid.at(-1) ?? years.at(-1);
  const m0 = firstY !== undefined ? med(byYear.get(firstY)!.map(e => e.pace_s_per_km!)) : 0;
  const m1 = lastY !== undefined ? med(byYear.get(lastY)!.map(e => e.pace_s_per_km!)) : 0;

  const ref = useChart(() => {
    if (!r || !efforts.length) return null;
    const col = cssVar(GROUP_COLOR[r.group]);
    return {
      type: "scatter",
      data: { datasets: [
        { label: "Each time", data: efforts.map(e => ({ x: parseDay(e.date).getTime(), y: e.pace_s_per_km!, e })), backgroundColor: alpha(col, 0.6), pointRadius: 4, pointHoverRadius: 6 },
        { type: "line", label: "Yearly median", data: years.map(y => ({ x: new Date(y, 6, 1).getTime(), y: med(byYear.get(y)!.map(e => e.pace_s_per_km!)) })),
          borderColor: cssVar("--ink"), backgroundColor: cssVar("--ink"), borderWidth: 2, pointRadius: 4, tension: 0.2 },
      ] },
      options: {
        scales: {
          x: { type: "linear", grid: { display: false },
            afterBuildTicks: ax => { const t = []; for (let y = new Date(ax.min).getFullYear() + 1; y <= new Date(ax.max).getFullYear(); y++) t.push({ value: new Date(y, 0, 1).getTime() }); ax.ticks = t; },
            ticks: { callback: v => new Date(Number(v)).getFullYear() } },
          y: { reverse: true, title: { display: true, text: "pace, min/km (faster is higher)" }, ticks: { callback: v => pace(Number(v)) }, grid: { color: cssVar("--line-2") } },
        },
        plugins: { legend: { position: "top", align: "end" }, tooltip: { callbacks: { label: it => {
          const e = (it.raw as { e?: RouteDetail["efforts"][number] }).e;
          return e ? ` ${fmtDay(e.date)}: ${hms(e.seconds)} (${pace(e.pace_s_per_km!)} /km)` : ` median: ${pace(it.parsed.y ?? 0)} /km`;
        } } } },
      },
    };
  }, [r]);

  const rename = async () => {
    const n = draft.trim();
    const res = await api.renameRoute(id, n);
    onRenamed(id, res.name); setSaved(res.name ? "Saved" : "Name cleared");
  };

  if (err) return <p className="empty">{err}</p>;
  if (!r) return <div className="panel"><p className="muted">Loading…</p></div>;
  const change = m0 && m1 ? (m1 / m0 - 1) * 100 : 0;
  return (
    <div className="panel">
      <div className="panel-head">
        <form className="rename" onSubmit={e => { e.preventDefault(); rename(); }}>
          <label className="eyebrow" htmlFor="route-name" style={{ flexBasis: "100%" }}>Route name</label>
          <input id="route-name" value={draft} placeholder={routeTitle({ ...r, name: null })} onChange={e => { setDraft(e.target.value); setSaved(null); }} maxLength={80} />
          <button className="btn" type="submit" disabled={draft.trim() === (r.name ?? "")}>Save name</button>
          {saved && <span className="small muted" role="status">{saved}</span>}
        </form>
        <span className="small muted">{GROUP_LABEL[r.group]} · {nf(r.length_km, 1)} km · {r.efforts.length} times · {fmtDay(r.efforts[0].date)} to {fmtDay(r.efforts.at(-1)!.date)}</span>
      </div>
      {fastest && (
        <div className="callout">
          <div><span className="eyebrow">Fastest</span><b>{hms(fastest.seconds)}</b><span className="small muted">{fmtDay(fastest.date)}</span></div>
          {firstY !== undefined && <div><span className="eyebrow">Typical pace {firstY}</span><b>{pace(m0)} /km</b></div>}
          {lastY !== undefined && lastY !== firstY && <div><span className="eyebrow">Typical pace {lastY}</span><b>{pace(m1)} /km</b></div>}
          {lastY !== firstY && <div><span className="eyebrow">Change</span><b>{change <= 0 ? "" : "+"}{nf(change, 1)}%</b><span className="small muted">{change < 0 ? "faster" : "slower"} per km</span></div>}
        </div>
      )}
      <div className="chart"><canvas ref={ref} /></div>
      <div className="tablewrap"><table>
        <thead><tr><th>Year</th><th className="n">Times</th><th className="n">Median pace</th><th className="n">Best time</th><th className="n">Avg heart rate</th></tr></thead>
        <tbody>{years.map(y => { const a = byYear.get(y)!; const b = a.reduce((m, e) => (e.seconds < m.seconds ? e : m)); const hr = a.filter(e => e.avg_hr);
          return <tr key={y}><td>{y}</td><td className="n">{a.length}</td><td className="n">{pace(med(a.map(e => e.pace_s_per_km!)))} /km</td><td className="n">{hms(b.seconds)}</td>
            <td className="n">{hr.length ? `${nf(hr.reduce((s, e) => s + e.avg_hr!, 0) / hr.length)} bpm` : "–"}</td></tr>; })}</tbody>
      </table></div>
    </div>
  );
}
