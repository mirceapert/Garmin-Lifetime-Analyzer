import { useState } from "react";
import { api } from "../api";
import { fmtDay, nf } from "../lib/format";
import { alpha, cssVar } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";

export function Snow() {
  const [data, err] = useData(api.snow);
  const [open, setOpen] = useState<string | null>(null);
  const seasons = data?.seasons ?? [];
  const asc = [...seasons].reverse();
  const ref = useChart(() => {
    if (!asc.length) return null;
    const c = cssVar("--snow");
    return {
      type: "bar",
      data: { labels: asc.map(s => s.season), datasets: [{ label: "Vertical", data: asc.map(s => s.vertical_m), backgroundColor: c, borderRadius: 4, maxBarThickness: 46 }] },
      options: {
        scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "metres descended" }, grid: { color: cssVar("--line-2") }, ticks: { callback: v => nf(Number(v)) } } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => {
          const s = asc[it.dataIndex];
          return [` ${nf(s.vertical_m)} m down in ${s.days_on_snow} days`, ` ${s.places.join(", ")}`];
        } } } },
      },
    };
  }, [data]);
  const spRef = useChart(() => {
    if (!asc.length) return null;
    const c = cssVar("--snow");
    return {
      type: "line",
      data: { labels: asc.map(s => s.season), datasets: [{ label: "Top speed", data: asc.map(s => s.top_speed_kmh), borderColor: c, backgroundColor: alpha(c, 0.9), borderWidth: 2, pointRadius: 5, pointHoverRadius: 7 }] },
      options: {
        scales: { x: { grid: { display: false } }, y: { title: { display: true, text: "km/h" }, grid: { color: cssVar("--line-2") } } },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: it => ` ${nf(it.parsed.y ?? 0, 1)} km/h` } } },
      },
    };
  }, [data]);

  if (err) return <p className="empty">Could not load snowboarding: {err}</p>;
  if (!data) return <p className="empty">Loading snowboarding…</p>;
  if (!seasons.length) return <p className="empty">No snowboarding yet.</p>;
  const t = data.totals;
  return (
    <section className="view">
      <div className="view-head"><h2>Snowboard seasons</h2>
        <p className="muted">A season runs from July to June, so January 2019 belongs to 2018/19. Several recordings on one day count as one day on snow. Vertical is the descent Garmin measured; runs are counted from altitude, and only where the altitude was recorded almost without gaps.</p></div>
      <div className="odo">
        <div><span className="eyebrow">Seasons</span><span className="big">{t.seasons}</span></div>
        <div><span className="eyebrow">Days on snow</span><span className="big">{t.days_on_snow}</span></div>
        <div><span className="eyebrow">Vertical down</span><span className="big">{nf(t.vertical_m / 1000, 1)}<small>km</small></span><span className="sub">{nf(t.vertical_m / 8849, 1)} times Everest</span></div>
        <div><span className="eyebrow">Distance</span><span className="big">{nf(t.distance_km)}<small>km</small></span></div>
        <div><span className="eyebrow">Top speed</span><span className="big">{t.top_speed_kmh ? nf(t.top_speed_kmh, 1) : "–"}<small>km/h</small></span></div>
      </div>
      <div className="grid2">
        <div className="panel"><h3>Vertical per season</h3><div className="chart short"><canvas ref={ref} /></div></div>
        <div className="panel"><h3>Top speed per season</h3><div className="chart short"><canvas ref={spRef} /></div></div>
      </div>
      <div className="panel">
        <div className="panel-head"><h3>Seasons</h3><span className="small muted">Pick a season to see its days</span></div>
        <div className="tablewrap"><table>
          <thead><tr><th>Season</th><th>Where</th><th className="n">Days</th><th className="n">Runs</th><th className="n">Vertical</th><th className="n">Best day</th><th className="n">Distance</th><th className="n">Hours</th><th className="n">Top km/h</th></tr></thead>
          <tbody>{seasons.map(s => [
            <tr key={s.season} className={`click ${open === s.season ? "sel" : ""}`} tabIndex={0} aria-expanded={open === s.season}
              onClick={() => setOpen(open === s.season ? null : s.season)} onKeyDown={e => e.key === "Enter" && setOpen(open === s.season ? null : s.season)}>
              <td><b>{s.season}</b></td><td>{s.places.join(", ")}</td><td className="n">{s.days_on_snow}</td>
              <td className="n">{s.runs ?? (s.runs_partial ? `${s.runs_partial}+` : "–")}</td>
              <td className="n">{nf(s.vertical_m)} m</td><td className="n">{nf(s.best_day_vertical_m)} m</td>
              <td className="n">{nf(s.distance_km, 1)} km</td><td className="n">{nf(s.hours, 1)}</td><td className="n">{s.top_speed_kmh ? nf(s.top_speed_kmh, 1) : "–"}</td>
            </tr>,
            ...(open === s.season ? s.days.map(d => (
              <tr key={d.day} className="sub-row">
                <td>{fmtDay(d.day)}</td><td>{d.places.join(", ")}</td><td className="n">{d.activities.length > 1 ? `${d.activities.length} recordings` : ""}</td>
                <td className="n">{d.runs ?? "–"}</td><td className="n">{nf(d.vertical_m)} m</td><td></td>
                <td className="n">{nf(d.distance_km, 1)} km</td><td className="n">{nf(d.hours, 1)}</td><td className="n">{d.top_speed_kmh ? nf(d.top_speed_kmh, 1) : "–"}</td>
              </tr>)) : []),
          ])}</tbody>
        </table></div>
        <p className="note">"–" for runs: the watch lost the altitude for long stretches that season, so runs can't be counted; vertical still comes from Garmin's own descent. Where Garmin left out the top speed, it comes from the per-second speed smoothed over 5 seconds, so it may read a little low. Hours include time on the lifts.</p>
      </div>
    </section>
  );
}
