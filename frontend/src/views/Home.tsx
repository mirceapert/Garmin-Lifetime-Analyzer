import { api, type Home as HomeData } from "../api";
import { fmtDay, fmtShort, hms, nf, sportLabel } from "../lib/format";
import { useData } from "../lib/useData";

const DIST_LABEL: Record<string, string> = { best_1k: "1 km", best_5k: "5 km", best_10k: "10 km", best_hm: "half marathon" };
const formWord = (v: number) => (v > 15 ? "very fresh" : v > 5 ? "fresh" : v > -10 ? "neutral" : v > -30 ? "tired, building" : "very tired");

interface Tile { id: string; sport: string; title: string; big: string; unit: string; text: string; feature?: boolean; cta?: string }

export function Home() {
  const [h, err] = useData(api.home);
  const [sync] = useData(api.syncStatus);
  if (err) return <p className="empty">Could not load the home page: {err}</p>;
  if (!h) return <p className="empty">Loading…</p>;
  if (h.empty) return <FirstRun healthDays={h.health_days} />;
  const l = h.lifetime!;
  const tiles = buildTiles(h);
  const sleep = h.tonight?.sleep_score, hrv = h.tonight?.hrv;
  const key = sync?.key;
  return (
    <section className="view home">
      <div className="home-top">
        <div className="hero">
          <svg aria-hidden="true" className="hero-art" viewBox="0 0 600 300" preserveAspectRatio="xMaxYMid slice">
            <path d="M40 250 C120 200 140 120 220 130 S340 220 400 160 S520 60 600 90" stroke="var(--run)" />
            <path d="M0 180 C90 170 160 240 260 210 S420 110 480 140 S560 210 600 200" stroke="var(--walk)" />
            <path d="M120 300 C160 230 250 260 300 190 S380 40 470 60 S560 150 600 140" stroke="var(--trail)" />
            <path d="M200 40 C260 80 300 60 350 100 S450 220 520 230" stroke="var(--tennis)" />
          </svg>
          <div className="hero-text">
            <span className="eyebrow">Since {fmtDay(l.first_day)}</span>
            <h2>{nf(l.activities)} activities</h2>
            <p>Every run, walk, ride, rally, ride down a mountain and night of sleep your watch has recorded, in one place.</p>
          </div>
          <div className="hero-stats">
            <div><b>{nf(l.hours)}<small>h</small></b><span>moving</span></div>
            <div><b>{nf(l.foot_km)}<small>km</small></b><span>on foot</span></div>
            <div><b>{nf(l.active_days)}</b><span>active days</span></div>
            <div><b>{nf(h.health_days)}</b><span>days of health data</span></div>
          </div>
        </div>
        <div className="panel tonight">
          <div className="panel-head"><h3>Tonight</h3>{sleep?.night_of && <span className="small muted">{fmtShort(sleep.night_of)}</span>}</div>
          <div className="tonight-grid">
            {[sleep, hrv].map(t => t && (
              <div key={t.label}>
                <span className="eyebrow">{t.label}</span>
                {t.ready ? <><b>{nf(t.prediction!, 0)}{t.unit && <small> {t.unit}</small>}</b><span className="small muted">likely {nf(t.prediction! - t.band!, 0)}–{nf(t.prediction! + t.band!, 0)}</span></>
                  : <span className="small muted">Needs more nights</span>}
              </div>
            ))}
          </div>
          <div className="statlist compact">
            {h.fitness && <div><span>Fitness</span><span className="mono">{nf(h.fitness.fitness, 1)}</span></div>}
            {h.fitness && <div><span>Form</span><span className="mono">{h.fitness.form > 0 ? "+" : ""}{nf(h.fitness.form, 1)} {formWord(h.fitness.form)}</span></div>}
            {key && <div><span>Garmin key</span>
              <span className={key.state === "ok" ? "good" : key.state === "expiring" ? "warn" : "bad"}>
                {key.state === "ok" ? (key.expires_on ? `valid until ${fmtDay(key.expires_on)}` : "set") : key.state === "missing" ? "not set" : key.state === "expiring" ? `expires in ${key.days_left} days` : "expired"}
              </span></div>}
          </div>
          <a href="#forecasts">Open forecasts →</a>
        </div>
      </div>

      <section aria-labelledby="whats-here" className="whats">
        <div className="panel-head"><h3 id="whats-here">What's in here</h3><span className="small muted">Each view, with one number from your data. Click to open it.</span></div>
        <div className="home-tiles">
          {tiles.map(t => (
            <a key={t.id} href={`#${t.id}`} className={`home-tile ${t.feature ? "feature" : ""}`}>
              <span className="ht-title"><span className="ht-dot" style={{ background: `var(--${t.sport})` }} />{t.title}</span>
              <span className="ht-big">{t.big} <small>{t.unit}</small></span>
              <span className="ht-text">{t.text}{t.cta && <> <span className="ht-cta">{t.cta}</span></>}</span>
            </a>
          ))}
        </div>
      </section>

      {h.latest && h.latest.length > 0 && <div className="panel">
        <div className="panel-head"><h3>Latest activities</h3><span className="small muted">Newest first</span></div>
        <div className="tablewrap"><table>
          <thead><tr><th>Date</th><th>Activity</th><th className="n">Distance</th><th className="n">Time</th><th>Note</th></tr></thead>
          <tbody>{h.latest.map(a => (
            <tr key={a.activity_id}>
              <td>{fmtShort(a.date)}</td>
              <td><span className="swatch" style={{ background: `var(--${a.sport})` }} />{a.sport === "tennis" ? <a href={`#tennis-${a.activity_id}`}>{a.name ?? "Tennis"}</a> : a.name ?? sportLabel(a.sport)}</td>
              <td className="n">{a.distance_km >= 0.5 && a.sport !== "tennis" ? `${nf(a.distance_km, 1)} km` : "–"}</td>
              <td className="n">{hms(a.seconds)}</td>
              <td>{a.best_ever.length ? <span className="tag">Best ever {a.best_ever.map(k => DIST_LABEL[k]).join(", ")}</span>
                : a.sport === "tennis" ? <span className="muted">{a.base_share != null ? `${Math.round(a.base_share * 100)}% at the baseline` : "No court map (no GPS)"}</span> : ""}</td>
            </tr>))}</tbody>
        </table></div>
      </div>}
    </section>
  );
}

function buildTiles(h: HomeData): Tile[] {
  const l = h.lifetime!, out: Tile[] = [];
  out.push({ id: "lifetime", sport: "run", title: "Lifetime", big: `${nf(l.earth_share * 100, 1)}%`, unit: "of the way round the Earth",
    text: "Your odometer, totals per sport, and every year side by side." });
  if (h.tiles) out.push({ id: "map", sport: "walk", title: "Heatmap & tiles", big: nf(h.tiles.visited), unit: "map squares explored",
    text: `Every GPS track on one map. Your largest fully explored square is ${h.tiles.largest_square}×${h.tiles.largest_square}.` });
  out.push({ id: "routes", sport: "run", title: "Routes", big: nf(h.routes ?? 0), unit: "routes you repeat",
    text: "Found on their own. See how your pace changed on each, and name them." });
  const b = h.best_effort;
  out.push({ id: "best-efforts", sport: "accent", title: "Best efforts", big: b ? hms(b.seconds) : "–", unit: b ? DIST_LABEL[b.distance] : "no outdoor runs yet",
    text: b ? `${b.name ?? "Run"}, ${fmtDay(b.date)}. Plus your other distances.` : "Your fastest 1 km, 5 km, 10 km and half marathon." });
  if (h.tennis) out.push({ id: "tennis", sport: "tennis", title: "Tennis", big: nf(h.tennis.sessions), unit: `sessions, ${nf(h.tennis.hours)} h on court`,
    text: "Where you move on court, folded into one half court. Every session on its own." });
  if (h.snow) out.push({ id: "snow", sport: "snow", title: "Snowboard", big: `${nf(h.snow.vertical_m / 1000, 1)} km`, unit: `down, in ${h.snow.days_on_snow} days`,
    text: `${h.snow.seasons} season${h.snow.seasons > 1 ? "s" : ""}: runs, vertical and top speed per trip.` });
  const r = h.recovery;
  out.push({ id: "sleep", sport: "accent", title: "Sleep & recovery",
    big: r?.back_by ? `Night ${r.back_by}` : "–", unit: r?.back_by ? `back to usual ${r.metric === "hrv" ? "HRV" : "resting HR"}` : "needs more nights",
    text: "After a hard session. And what goes with your better and worse nights." });
  if (h.fitness) out.push({ id: "forecasts", sport: "accent", title: "Forecasts", big: `${h.fitness.form > 0 ? "+" : ""}${nf(h.fitness.form, 1)}`, unit: `form today, ${formWord(h.fitness.form)}`,
    text: "Plan your weeks to a race and see where fitness and form will be." });
  if (h.year) out.push({ id: `year-${h.year.year}`, sport: "accent", title: "Year in review", big: String(h.year.year), unit: `${nf(h.year.hours)} hours, ${h.year.active_days} active days`,
    text: "One year on one page, and an image to share.", cta: `Make the ${h.year.year} image →`, feature: true });
  return out;
}

function FirstRun({ healthDays }: { healthDays: number }) {
  return (
    <section className="view">
      <div className="view-head"><h2>Welcome</h2>
        <p className="muted">No activities yet{healthDays ? ` (${nf(healthDays)} days of health data are in)` : ""}. Three steps and your whole Garmin history is here. The setup guide in the repository's <code>docs</code> folder explains each one.</p></div>
      <ol className="steps">
        <li><b>Ask Garmin for your data export.</b> In your Garmin account's Data Management page, choose Export Your Data. Garmin emails you a link to a zip.</li>
        <li><b>Import it.</b> Put the zip, still zipped, in the <code>import</code> folder and run <code>docker compose run --rm app gla import</code>.</li>
        <li><b>Connect the daily sync.</b> Put your Garmin Personal API key in <code>.env</code>, run <code>docker compose up -d</code>, then <code>docker compose run --rm app gla sync</code>.</li>
      </ol>
      <p className="note">Reload this page when the import has finished.</p>
    </section>
  );
}
