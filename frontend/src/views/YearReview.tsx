import { lazy, Suspense, useMemo } from "react";
import { api, type YearAct, type YearReview as Review, type YearTotals } from "../api";
import { fmtDay, fmtShort, hms, nf, sportLabel } from "../lib/format";
import { cssVar } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";
import { routeTitle } from "./Routes";
import { ShareImage } from "./ShareImage";

const YearMap = lazy(() => import("./YearMap"));
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DIST_LABEL: Record<string, string> = { best_1k: "1 km", best_5k: "5 km", best_10k: "10 km", best_hm: "Half marathon" };
const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

function Delta({ now, before, unit = "", d = 0 }: { now: number; before: number | undefined; unit?: string; d?: number }) {
  if (before == null) return null;
  const diff = now - before;
  if (Math.abs(diff) < 10 ** -d / 2) return <span className="sub">same as the year before</span>;
  return <span className="sub">{diff > 0 ? "▲" : "▼"} {nf(Math.abs(diff), d)}{unit} vs the year before</span>;
}

const actLink = (a: YearAct) => `${a.name ?? sportLabel(a.sport)}, ${fmtDay(a.date)}`;

export function YearReview({ selected }: { selected: number | null }) {
  const [r, err] = useData(() => api.yearReview(selected ?? undefined), [selected]);
  const [tracks] = useData(api.tracks);
  const yearTracks = useMemo(() => (r?.year && tracks ? tracks.filter(t => t.date.startsWith(String(r.year))) : []), [r, tracks]);

  if (err) return <p className="empty">Could not load the review: {err}</p>;
  if (!r) return <p className="empty">Loading the year…</p>;
  if (!r.year) return <p className="empty">No activities yet.</p>;
  const t = r.totals, p = r.previous ?? undefined;
  return (
    <section className="view review">
      <div className="view-head">
        <span className="eyebrow">Year in review</span>
        <h2 className="review-title">{r.year}{r.partial ? " so far" : ""}</h2>
        <p className="muted">{r.partial ? `Up to ${fmtDay(r.through)}. ` : ""}{t.activities} activities on {t.active_days} days{r.first && r.last ? `, from ${fmtShort(r.first.date)} to ${fmtShort(r.last.date)}` : ""}.</p>
      </div>
      <div className="yearbar">
        <div className="seg yearpick" role="group" aria-label="Year">
          {r.years.map(y => <a key={y} href={`#year-${y}`} role="button" aria-pressed={y === r.year}>{y}</a>)}
        </div>
        {t.activities > 0 && <button className="btn" onClick={() => document.getElementById("share")?.scrollIntoView({ behavior: "smooth" })}>Share image ↓</button>}
      </div>
      {!t.activities ? <p className="empty">Nothing recorded in {r.year}.</p> : <>
        <Headline t={t} p={p} />
        <div className="grid2">
          <SportMix t={t} />
          <Months r={r} />
        </div>
        {r.records && r.records.length > 0 && <Records r={r} />}
        {yearTracks.length > 0 && <Suspense fallback={<div className="panel"><p className="empty">Loading the map…</p></div>}><YearMap tracks={yearTracks} /></Suspense>}
        <Highlights r={r} />
        <Explore r={r} />
        <Sports r={r} />
        {r.sleep && <SleepYear r={r} />}
        <ShareImage review={r} />
      </>}
    </section>
  );
}

function Headline({ t, p }: { t: YearTotals; p?: YearTotals }) {
  return (
    <div className="odo">
      <div><span className="eyebrow">Hours moving</span><span className="big">{nf(t.hours)}</span><Delta now={t.hours} before={p?.hours} unit=" h" /></div>
      <div><span className="eyebrow">Active days</span><span className="big">{t.active_days}</span><Delta now={t.active_days} before={p?.active_days} /></div>
      <div><span className="eyebrow">On foot</span><span className="big">{nf(t.foot_km)}<small>km</small></span><Delta now={t.foot_km} before={p?.foot_km} unit=" km" /></div>
      <div><span className="eyebrow">Climbed</span><span className="big">{nf(t.ascent_m)}<small>m</small></span><Delta now={t.ascent_m} before={p?.ascent_m} unit=" m" /></div>
      <div><span className="eyebrow">Longest streak</span><span className="big">{t.longest_streak}<small>days</small></span><span className="sub">active days in a row</span></div>
    </div>
  );
}

function SportMix({ t }: { t: YearTotals }) {
  const max = Math.max(...t.by_sport.map(b => b.hours), 0.1);
  return (
    <div className="panel">
      <div className="panel-head"><h3>Your year by sport</h3><span className="small muted">hours</span></div>
      <div className="mix">
        {t.by_sport.map(b => (
          <div key={b.sport} className="mixrow">
            <span>{sportLabel(b.sport)}</span>
            <span className="mixbar"><span style={{ width: `${(b.hours / max) * 100}%`, background: `var(--${b.sport})` }} /></span>
            <span className="mono">{nf(b.hours, 1)} h</span>
            <span className="small muted">{b.activities}× {b.distance_km >= 1 && b.sport !== "tennis" ? `· ${nf(b.distance_km)} km` : ""}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Months({ r }: { r: Review }) {
  const sports = r.totals.by_sport.map(b => b.sport);
  const ref = useChart(() => ({
    type: "bar",
    data: {
      labels: MONTHS,
      datasets: sports.map(sp => ({
        label: sportLabel(sp), data: r.months!.map(m => m.hours[sp] ?? 0), backgroundColor: cssVar(`--${sp}`),
        borderColor: cssVar("--surface"), borderWidth: { top: 2 }, borderSkipped: false, maxBarThickness: 34,
      })),
    },
    options: {
      interaction: { mode: "index", intersect: false },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, title: { display: true, text: "hours" }, grid: { color: cssVar("--line-2") } } },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 10, boxHeight: 10 } },
        tooltip: { filter: it => (it.parsed.y ?? 0) > 0, callbacks: { title: it => MONTH_NAMES[it[0].dataIndex], label: it => ` ${it.dataset.label}: ${nf(it.parsed.y ?? 0, 1)} h` } } },
    },
  }), [r]);
  return (
    <div className="panel">
      <div className="panel-head"><h3>Month by month</h3><span className="small muted">hours per sport</span></div>
      <div className="chart"><canvas ref={ref} /></div>
    </div>
  );
}

const gain = (pbs: { improved_by: number | null }[]) => pbs.reduce((a, b) => a + (b.improved_by ?? 0), 0);

function Records({ r }: { r: Review }) {
  return (
    <div className="panel">
      <div className="panel-head"><h3>Best efforts this year</h3><span className="small muted">From outdoor runs and trail runs</span></div>
      <div className="records">
        {r.records!.map(e => (
          <div key={e.distance} className={`record ${e.personal_bests.length ? "pb" : ""}`}>
            <span className="eyebrow">{DIST_LABEL[e.distance] ?? e.distance}</span>
            <b>{hms(e.seconds)}</b>
            <span className="small muted">{fmtShort(e.date)} · {e.name ?? "Run"}</span>
            {e.all_time ? <span className="tag">Your best ever</span>
              : e.personal_bests.length ? <span className="tag">New best at the time</span> : <span className="small muted">Not a personal best</span>}
            {e.personal_bests.length > 0 && <span className="small muted">
              {e.personal_bests.length === 1 ? "Personal best" : `${e.personal_bests.length} personal bests`} this year
              {gain(e.personal_bests) > 0 ? `, ${hms(gain(e.personal_bests))} faster in total` : ", the first time you ran it"}
            </span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function Highlights({ r }: { r: Review }) {
  const d = r.biggest_day!, w = r.biggest_week!;
  const sunday = new Date(w.monday + "T12:00:00"); sunday.setDate(sunday.getDate() + 6);
  return (
    <div className="grid2">
      <div className="panel">
        <h3>Biggest day and week</h3>
        <div className="statlist">
          <div><span>Biggest day: {fmtDay(d.date)}<br /><span className="small muted">{d.activities.map(a => a.name ?? sportLabel(a.sport)).join(", ")}</span></span>
            <span className="v">{hms(d.hours * 3600)}</span></div>
          <div><span>Biggest week: {fmtShort(w.monday)} to {fmtShort(sunday.toISOString().slice(0, 10))}<br /><span className="small muted">{w.activities} activities: {w.sports.map(sportLabel).join(", ").toLowerCase()}</span></span>
            <span className="v">{nf(w.hours, 1)} h</span></div>
          {r.first && <div><span>First of the year<br /><span className="small muted">{actLink(r.first)}</span></span><span className="v">{fmtShort(r.first.date)}</span></div>}
          {r.last && <div><span>{r.partial ? "Latest" : "Last of the year"}<br /><span className="small muted">{actLink(r.last)}</span></span><span className="v">{fmtShort(r.last.date)}</span></div>}
        </div>
      </div>
      <div className="panel">
        <h3>Longest of each</h3>
        <div className="statlist">
          {Object.entries(r.longest ?? {}).map(([sp, a]) => (
            <div key={sp}><span><span className="swatch" style={{ background: `var(--${sp})` }} />{sportLabel(sp)}<br /><span className="small muted">{actLink(a)}</span></span>
              <span className="v">{nf(a.distance_km, a.distance_km < 100 ? 1 : 0)} km</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Explore({ r }: { r: Review }) {
  const pl = r.places!, ti = r.tiles!, ro = r.routes!;
  return (
    <div className="grid2">
      <div className="panel">
        <div className="panel-head"><h3>Places</h3><span className="small muted">{pl.count} places, {pl.new} new this year</span></div>
        <div className="statlist">
          {pl.top.map(x => <div key={x.place}><span>{x.place}{x.new && <span className="tag">new</span>}</span><span className="v">{x.activities}</span></div>)}
        </div>
        {pl.new_places.length > pl.top.filter(x => x.new).length && <p className="small muted">Also new: {pl.new_places.filter(n => !pl.top.some(x => x.place === n)).join(", ")}.</p>}
        <p className="note">Places come from the names Garmin gives your activities.</p>
      </div>
      <div className="panel">
        <h3>Exploring</h3>
        <div className="callout">
          <div><span className="eyebrow">New explorer tiles</span><b>{nf(ti.new)}</b><span className="small muted">{nf(ti.total_at_year_end)} by the end of the year</span></div>
          <div><span className="eyebrow">New routes</span><b>{ro.new}</b><span className="small muted">done 3 times or more</span></div>
        </div>
        {ro.top.length > 0 && <>
          <span className="eyebrow">Routes you repeated most</span>
          <div className="statlist">
            {ro.top.map(x => <div key={x.route_id}><a href={`#routes-${x.route_id}`}>{routeTitle(x)}</a><span className="v">{x.times}×</span></div>)}
          </div>
        </>}
      </div>
    </div>
  );
}

function Sports({ r }: { r: Review }) {
  const tn = r.tennis, sn = r.snow, f = r.fitness;
  const fitRef = useChart(() => f ? {
    type: "line",
    data: { labels: f.weekly.map((_, i) => i), datasets: [{ label: "Fitness", data: f.weekly, borderColor: cssVar("--run"), borderWidth: 2, pointRadius: 0, tension: 0.3 }] },
    options: { scales: { x: { display: false }, y: { display: false, beginAtZero: true } }, plugins: { legend: { display: false }, tooltip: { enabled: false } } },
  } : null, [r]);
  if (!tn && !sn && !f) return null;
  return (
    <div className="grid3">
      {f && <div className="panel">
        <h3>Fitness</h3>
        <div className="callout">
          <div><span className="eyebrow">Peak</span><b>{nf(f.peak_fitness, 1)}</b><span className="small muted">{fmtShort(f.peak_day)}</span></div>
          <div><span className="eyebrow">Start → end</span><b>{nf(f.start_fitness)} → {nf(f.end_fitness)}</b></div>
          <div><span className="eyebrow">Training load</span><b>{nf(f.total_load)}</b></div>
        </div>
        <div className="chart tiny"><canvas ref={fitRef} role="img" aria-label="Fitness through the year" /></div>
      </div>}
      {tn && <div className="panel">
        <h3><a href="#tennis">Tennis</a></h3>
        <div className="statlist">
          <div><span>Sessions</span><span className="v">{tn.sessions}</span></div>
          <div><span>Hours on court</span><span className="v">{nf(tn.hours, 1)}</span></div>
          <div><span>At the baseline</span><span className="v">{pct(tn.base_share)}</span></div>
          <div><span>Near the net</span><span className="v">{pct(tn.net_share)}</span></div>
          <div><span>Top speed</span><span className="v">{tn.top_speed_kmh ? `${nf(tn.top_speed_kmh, 1)} km/h` : "–"}</span></div>
        </div>
      </div>}
      {sn && <div className="panel">
        <h3><a href="#snow">Snowboard</a></h3>
        <div className="statlist">
          <div><span>Days on snow</span><span className="v">{sn.days}</span></div>
          <div><span>Vertical down</span><span className="v">{nf(sn.vertical_m)} m</span></div>
          <div><span>Top speed</span><span className="v">{sn.top_speed_kmh ? `${nf(sn.top_speed_kmh, 1)} km/h` : "–"}</span></div>
          <div><span>Where</span><span>{sn.places.join(", ")}</span></div>
        </div>
      </div>}
    </div>
  );
}

function SleepYear({ r }: { r: Review }) {
  const s = r.sleep!, p = s.previous;
  const row = (label: string, v: number | null, pv: number | null | undefined, unit: string, d = 0, lowerBetter = false) => v == null ? null : (
    <div><span>{label}{pv != null && <><br /><span className="small muted">{nf(pv, d)}{unit} the year before{Math.abs(v - pv) >= 10 ** -d ? ((v > pv) !== lowerBetter ? ", better" : ", worse") : ""}</span></>}</span>
      <span className="v">{nf(v, d)}{unit}</span></div>
  );
  return (
    <div className="panel">
      <div className="panel-head"><h3><a href="#sleep">Sleep</a></h3><span className="small muted">{s.nights} nights recorded</span></div>
      <div className="grid2 tight">
        <div className="statlist">
          {row("Average sleep score", s.score, p?.score, "")}
          {row("Average sleep", s.hours, p?.hours, " h", 1)}
        </div>
        <div className="statlist">
          {row("Resting heart rate", s.rhr, p?.rhr, " bpm", 0, true)}
          {row("Night HRV", s.hrv, p?.hrv, " ms")}
          {s.best_month && s.worst_month && <div><span>Best and worst month<br /><span className="small muted">by average sleep score</span></span>
            <span className="v">{MONTHS[s.best_month.month - 1]} {s.best_month.score} · {MONTHS[s.worst_month.month - 1]} {s.worst_month.score}</span></div>}
        </div>
      </div>
    </div>
  );
}
