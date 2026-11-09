import { useMemo, useState } from "react";
import { api, type SportKey } from "../api";
import { fmtShort, nf, SPORTS } from "../lib/format";
import { load, save } from "../lib/storage";
import { cssVar, yearColor } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";

const FILTERS: Record<string, { label: string; sports: SportKey[] }> = {
  runtrail: { label: "Running + trail", sports: ["run", "trail"] },
  walk: { label: "Walking", sports: ["walk"] },
  foot: { label: "Everything on foot", sports: ["run", "trail", "walk"] },
  cycle: { label: "Cycling", sports: ["cycle"] },
};
const MONTH_STARTS = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function Lifetime() {
  const [lt, err] = useData(api.lifetime);
  if (err) return <p className="empty">Could not load your totals: {err}</p>;
  if (!lt) return <p className="empty">Loading your totals…</p>;
  if (!lt.activities) return <p className="empty">No activities yet. Import your Garmin export to fill this page.</p>;
  const by = lt.by_sport;
  const firstYear = lt.first_day?.slice(0, 4);
  const tennis = by.tennis;
  return (
    <section className="view">
      <div className="view-head"><h2>Lifetime odometer</h2><p className="muted">Everything you have recorded since {firstYear}, added up.</p></div>
      <div className="odo">
        <div><span className="eyebrow">Distance on foot</span><span className="big">{nf(lt.foot_km)}<small>km</small></span><span className="sub">{nf(lt.earth_share * 100, 1)}% of the way around the Earth</span></div>
        <div><span className="eyebrow">Time moving</span><span className="big">{nf(lt.hours)}<small>h</small></span><span className="sub">{nf(lt.hours / 24, 1)} full days across {nf(lt.activities)} activities</span></div>
        <div><span className="eyebrow">Climbed</span><span className="big">{nf(lt.ascent_m / 1000, 1)}<small>km</small></span><span className="sub">{nf(lt.everests, 1)} × Everest from sea level</span></div>
        {by.snow && <div><span className="eyebrow">Descended on a board</span><span className="big">{nf(lt.snow_vertical_m / 1000, 1)}<small>km</small></span><span className="sub">over {by.snow.activities} days on snow</span></div>}
        <div><span className="eyebrow">Active days</span><span className="big">{nf(lt.active_days)}</span><span className="sub">{nf(lt.active_share * 100)}% of days since {firstYear}</span></div>
        {tennis && <div><span className="eyebrow">Tennis on court</span><span className="big">{nf(tennis.hours)}<small>h</small></span><span className="sub">{tennis.activities} sessions, {nf(tennis.distance_km)} km of shuffling</span></div>}
      </div>
      <div className="panel">
        <div className="panel-head"><h3>By sport</h3><span className="small muted">Snowboarding counts vertical descended instead of climb</span></div>
        <div className="tablewrap">
          <table>
            <thead><tr><th>Sport</th><th className="n">Activities</th><th className="n">Distance</th><th className="n">Time</th><th className="n">Elevation</th><th>First</th><th>Last</th></tr></thead>
            <tbody>
              {SPORTS.filter(s => by[s.key as SportKey]).map(s => {
                const b = by[s.key as SportKey]!;
                return <tr key={s.key}>
                  <td><span className="swatch" style={{ background: `var(--${s.key})` }} />{s.label}</td>
                  <td className="n">{b.activities}</td><td className="n">{nf(b.distance_km)} km</td><td className="n">{nf(b.hours)} h</td>
                  <td className="n">{s.key === "snow" ? `−${nf(b.descent_m)}` : nf(b.ascent_m)} m</td>
                  <td className="mono small">{b.first}</td><td className="mono small">{b.last}</td>
                </tr>;
              })}
            </tbody>
          </table>
        </div>
      </div>
      <YearOverYear />
    </section>
  );
}

function YearOverYear() {
  const [filter, setFilter] = useState<string>(() => load("yoy-filter", "runtrail"));
  const [data, err] = useData(() => api.yoy(FILTERS[filter].sports), [filter]);
  const years = useMemo(() => Object.keys(data?.years ?? {}).map(Number), [data]);
  const current = years.length ? Math.max(...years) : new Date().getFullYear();
  const [on, setOn] = useState<number[] | null>(() => load<number[] | null>("yoy-years", null));
  const shown = (on ?? years).filter(y => years.includes(y));
  const setYears = (ys: number[]) => { setOn(ys); save("yoy-years", ys); };
  const pickFilter = (k: string) => { setFilter(k); save("yoy-filter", k); };

  // compare years up to today when this year has data, otherwise up to the last activity
  const todayIso = new Date().toLocaleDateString("sv-SE");
  const latest = data?.latest_day ? (data.latest_day.slice(0, 4) === todayIso.slice(0, 4) ? todayIso : data.latest_day) : null;
  const doy = latest ? dayOfYear(latest) : 0;
  const at = (y: number) => data?.years[String(y)]?.[Math.min(doy, (data?.years[String(y)]?.length ?? 1)) - 1] ?? 0;
  const cur = at(current), prev = at(current - 1);
  const pastYears = years.filter(y => y !== current);
  const best = pastYears.length ? pastYears.reduce((a, b) => (at(b) > at(a) ? b : a)) : null;
  const curLatest = latest && Number(latest.slice(0, 4)) === current;

  const ref = useChart(() => {
    if (!data || !shown.length) return null;
    return {
      type: "line",
      data: {
        datasets: shown.slice().sort().map(y => {
          const series = data.years[String(y)] ?? [];
          const last = y === current && curLatest ? doy : series.length;
          const c = yearColor(y, years, current);
          return { label: String(y), data: series.slice(0, last).map((v, i) => ({ x: i + 1, y: v })).filter((_, i) => i % 3 === 0 || i === last - 1),
            borderColor: c, backgroundColor: c, borderWidth: y === current ? 3 : 2, pointRadius: 0, tension: 0.15 };
        }),
      },
      options: {
        interaction: { mode: "nearest", axis: "x", intersect: false },
        scales: {
          x: { type: "linear", min: 1, max: 366, grid: { display: false },
            afterBuildTicks: ax => { ax.ticks = MONTH_STARTS.map(v => ({ value: v })); },
            ticks: { callback: v => MONTHS[MONTH_STARTS.indexOf(Number(v))] ?? "" } },
          y: { beginAtZero: true, title: { display: true, text: "km" }, grid: { color: cssVar("--line-2") } },
        },
        plugins: {
          legend: { display: false },
          tooltip: { itemSort: (a, b) => (b.parsed.y ?? 0) - (a.parsed.y ?? 0), callbacks: {
            title: it => new Date(2023, 0, it[0].parsed.x ?? 1).toLocaleDateString("en-GB", { day: "numeric", month: "short" }),
            label: it => ` ${it.dataset.label}: ${nf(it.parsed.y ?? 0)} km` } },
        },
      },
    };
  }, [data, shown.join(","), filter]);

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>Year over year</h3>
        <div className="seg" role="group" aria-label="Sports">
          {Object.entries(FILTERS).map(([k, f]) => <button key={k} aria-pressed={k === filter} onClick={() => pickFilter(k)}>{f.label}</button>)}
        </div>
      </div>
      {err && <p className="empty">{err}</p>}
      {data && latest && (
        <div className="callout">
          {curLatest && <div><span className="eyebrow">{current} so far</span><b>{nf(cur)} km</b></div>}
          {curLatest && years.includes(current - 1) && <div><span className="eyebrow">vs {current - 1} on {fmtShort(latest)}</span><b>{cur >= prev ? "+" : "−"}{nf(Math.abs(cur - prev))} km</b></div>}
          {best && <div><span className="eyebrow">Best year at this date</span><b>{nf(at(best))} km</b><span className="small muted">{best}</span></div>}
          {curLatest && doy > 30 && <div><span className="eyebrow">On pace for</span><b>{nf((cur / doy) * 365)} km</b></div>}
        </div>
      )}
      <div className="controls">
        <span className="eyebrow">Years</span>
        <div className="chips" role="group" aria-label="Years to show">
          {years.map(y => {
            const pressed = shown.includes(y);
            return <button key={y} className="chip" aria-pressed={pressed}
              onClick={() => setYears(pressed ? shown.filter(x => x !== y) : [...shown, y])}>
              <span className="bar" style={{ background: pressed ? yearColor(y, years, current) : undefined }} />{y}{y === current && curLatest ? <small>to date</small> : null}
            </button>;
          })}
        </div>
        <div className="seg">
          <button onClick={() => setYears(years)}>All</button>
          <button onClick={() => setYears([current, current - 1].filter(y => years.includes(y)))}>This year and last</button>
          <button onClick={() => setYears([])}>Clear</button>
        </div>
      </div>
      <div className="chart tall">
        {shown.length ? <canvas ref={ref} aria-label="Cumulative distance by day of year, one line per year" />
          : <p className="empty">Pick at least one year to draw the chart.</p>}
      </div>
      <p className="note">Your choice of years and sports is remembered in this browser.</p>
    </div>
  );
}

function dayOfYear(iso: string): number {
  const d = new Date(iso + "T12:00:00");
  return Math.floor((d.getTime() - new Date(d.getFullYear(), 0, 1).getTime()) / 864e5) + 1;
}
