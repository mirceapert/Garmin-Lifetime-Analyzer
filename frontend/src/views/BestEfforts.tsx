import { useState } from "react";
import { api, type BestEfforts as BE } from "../api";
import { fmtDay, hms, nf, pace, parseDay } from "../lib/format";
import { load, save } from "../lib/storage";
import { alpha, cssVar } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";

const DIST: { key: keyof BE; label: string }[] = [
  { key: "best_1k", label: "1 km" }, { key: "best_5k", label: "5 km" },
  { key: "best_10k", label: "10 km" }, { key: "best_hm", label: "Half marathon" },
];

export function BestEfforts() {
  const [data, err] = useData(api.bestEfforts);
  const [sel, setSel] = useState<keyof BE>(() => load("be-distance", "best_5k"));
  const pick = (k: keyof BE) => { setSel(k); save("be-distance", k); };
  const d = data?.[sel];

  const ref = useChart(() => {
    if (!d || !d.efforts.length) return null;
    // best effort per month, and the record as it stood at each point
    const monthly = new Map<string, (typeof d.efforts)[number]>();
    for (const e of d.efforts) {
      const m = e.date.slice(0, 7), cur = monthly.get(m);
      if (!cur || e.seconds < cur.seconds) monthly.set(m, e);
    }
    const pts = [...monthly.values()].sort((a, b) => a.date.localeCompare(b.date));
    let rec = Infinity;
    const recLine = pts.map(p => { rec = Math.min(rec, p.seconds); return { x: parseDay(p.date).getTime(), y: rec }; });
    recLine.push({ x: Date.now(), y: rec });
    const run = cssVar("--run");
    return {
      type: "scatter",
      data: { datasets: [
        { label: "Best of the month", data: pts.map(p => ({ x: parseDay(p.date).getTime(), y: p.seconds, e: p })), backgroundColor: alpha(run, 0.65), pointRadius: 4, pointHoverRadius: 6 },
        { type: "line", label: "Record at the time", data: recLine, stepped: "before", borderColor: cssVar("--accent"), borderWidth: 2, pointRadius: 0 },
      ] },
      options: {
        scales: {
          x: { type: "linear", grid: { display: false },
            afterBuildTicks: ax => { const t = []; for (let y = new Date(ax.min).getFullYear() + 1; y <= new Date(ax.max).getFullYear(); y++) t.push({ value: new Date(y, 0, 1).getTime() }); ax.ticks = t; },
            ticks: { callback: v => new Date(Number(v)).getFullYear() } },
          y: { reverse: true, title: { display: true, text: "time (faster is higher)" }, ticks: { callback: v => hms(Number(v)) }, grid: { color: cssVar("--line-2") } },
        },
        plugins: { legend: { position: "top", align: "end" }, tooltip: { callbacks: { label: it => {
          const e = (it.raw as { e?: (typeof d.efforts)[number] }).e;
          return e ? ` ${fmtDay(e.date)}: ${hms(e.seconds)} in ${e.name ?? "a run"} (${nf(e.activity_km, 1)} km)` : ` Record: ${hms(it.parsed.y ?? 0)}`;
        } } } },
      },
    };
  }, [d]);

  if (err) return <p className="empty">Could not load best efforts: {err}</p>;
  if (!data) return <p className="empty">Loading best efforts…</p>;
  return (
    <section className="view">
      <div className="view-head"><h2>Best efforts</h2>
        <p className="muted">Your fastest stretch of each distance inside any outdoor run, not only whole activities. A 5 km best can come from the middle of a 10 km run. Treadmill runs are left out.</p></div>
      <div className="panel">
        <div className="panel-head"><h3>All-time bests</h3><span className="small muted">Pick a distance to chart it</span></div>
        <div className="tablewrap"><table>
          <thead><tr><th>Distance</th><th className="n">Best</th><th className="n">Pace</th><th>Date</th><th>Found in</th><th className="n">Runs long enough</th></tr></thead>
          <tbody>{DIST.map(x => { const b = data[x.key].best; return (
            <tr key={x.key} className={`click ${x.key === sel ? "sel" : ""}`} tabIndex={0} onClick={() => pick(x.key)} onKeyDown={e => e.key === "Enter" && pick(x.key)}>
              <td>{x.label}</td>
              <td className="n">{b ? hms(b.seconds) : "–"}</td>
              <td className="n">{b ? `${pace(b.seconds / (data[x.key].distance_m / 1000))} /km` : "–"}</td>
              <td>{b ? fmtDay(b.date) : ""}</td><td>{b ? `${b.name ?? "Run"}, ${nf(b.activity_km, 1)} km` : "No run this long yet"}</td>
              <td className="n">{data[x.key].efforts.length}</td>
            </tr>); })}</tbody>
        </table></div>
      </div>
      <div className="panel">
        <div className="panel-head"><h3>{DIST.find(x => x.key === sel)!.label} best effort over time</h3><span className="small muted">Each dot is your best for that month; the line is your record at the time</span></div>
        <div className="chart tall">{d?.efforts.length ? <canvas ref={ref} /> : <p className="empty">No runs long enough yet.</p>}</div>
      </div>
    </section>
  );
}
