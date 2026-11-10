import { useMemo, useState } from "react";
import { api, type LoadPlan, type Tonight } from "../api";
import { fmtDay, fmtShort, nf, parseDay } from "../lib/format";
import { load, save } from "../lib/storage";
import { alpha, cssVar } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";

const signed = (v: number, d = 1) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(Math.abs(v), d)}`;
const addDays = (iso: string, n: number) => { const d = parseDay(iso); d.setDate(d.getDate() + n); return d.toISOString().slice(0, 10); };

export function Forecasts() {
  const [f, err] = useData(api.forecast);
  const [tl] = useData(api.trainingLoad);
  if (err) return <p className="empty">Could not load forecasts: {err}</p>;
  if (!f) return <p className="empty">Loading forecasts…</p>;
  return (
    <section className="view">
      <div className="view-head"><h2>Forecasts</h2>
        <p className="muted">Tonight's sleep and HRV from what you did today, and where your fitness and form will be on a day you pick. Today's training counts once it is synced: press Sync now after an evening session.</p></div>
      <div className="grid2">
        {Object.values(f.tonight).map(t => <TonightCard key={t.key} t={t} />)}
      </div>
      {f.plan.ready && <Planner plan={f.plan} history={tl?.days ?? null} />}
    </section>
  );
}

function TonightCard({ t }: { t: Tonight }) {
  const unit = t.unit ? ` ${t.unit}` : "";
  const ref = useChart(() => {
    if (!t.ready || !t.recent?.length) return null;
    const acc = cssVar("--accent"), ink = cssVar("--ink-3");
    return {
      type: "line",
      data: { labels: t.recent.map(r => fmtShort(r[0])), datasets: [
        { label: "Forecast", data: t.recent.map(r => r[2]), borderColor: acc, borderWidth: 2, pointRadius: 0 },
        { label: "What happened", data: t.recent.map(r => r[1]), borderColor: ink, backgroundColor: ink, showLine: false, pointRadius: 2.5 },
      ] },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6 } }, y: { grid: { color: cssVar("--line-2") } } },
        plugins: { legend: { position: "top", align: "end" }, tooltip: { callbacks: { label: it => ` ${it.dataset.label}: ${nf(it.parsed.y ?? 0, 0)}${unit}` } } },
      },
    };
  }, [t]);
  if (!t.ready)
    return <div className="panel"><h3>{t.label} tonight</h3><p className="empty">Not enough nights to learn from yet: {t.nights ?? 0} of {t.needed} needed.</p></div>;
  const better = (t.mae_baseline! - t.mae!) / t.mae_baseline!;
  return (
    <div className="panel">
      <div className="panel-head"><h3>{t.label} tonight</h3><span className="small muted">Night of {fmtDay(t.night_of!)}</span></div>
      <div className="callout">
        <div><span className="eyebrow">Forecast</span><b>{nf(t.prediction!, 0)}{unit}</b></div>
        <div><span className="eyebrow">Likely range</span><b>{nf(t.prediction! - t.band!, 0)}–{nf(t.prediction! + t.band!, 0)}</b></div>
        <div><span className="eyebrow">7-night average</span><b>{nf(t.average!, 0)}{unit}</b></div>
      </div>
      <div className="statlist">
        {t.contributions!.slice(0, 4).map(c => (
          <div key={c.feature}><span>{c.label}</span><span className="mono">{signed(c.effect)}{unit}</span></div>
        ))}
      </div>
      <div className="chart short"><canvas ref={ref} /></div>
      <p className="note">
        Off by {nf(t.mae!, 1)}{unit} on a typical night, against {nf(t.mae_baseline!, 1)}{unit} for simply guessing your 7-night average
        ({better > 0 ? `${Math.round(better * 100)}% better` : "no better"}), tested on your newest {t.test_nights} nights. The range covers 4 nights in 5.
        Sleep has a lot that no watch sees, so treat this as a nudge, not a promise. Effects above are against your average night.
      </p>
    </div>
  );
}

function Planner({ plan, history }: { plan: LoadPlan; history: [string, number, number, number, number][] | null }) {
  const [target, setTarget] = useState<string>(() => { const v = load<string | null>("plan-target", null); return v && v > plan.day ? v : addDays(plan.day, 28); });
  const [level, setLevel] = useState<number>(() => load("plan-level", 100));
  const [taper, setTaper] = useState<number>(() => load("plan-taper", 7));
  const set = <T,>(k: string, f: (v: T) => void) => (v: T) => { f(v); save(k, v); };

  const proj = useMemo(() => project(plan, target, level, taper), [plan, target, level, taper]);
  const end = proj.at(-1);
  const ref = useChart(() => {
    const hist = (history ?? []).filter(d => d[0] >= addDays(plan.day, -90) && d[0] <= plan.day);
    const labels = [...hist.map(d => d[0]), ...proj.map(p => p.day)];
    const pad = <T,>(a: T[], before: number, after: number) => [...Array(before).fill(null), ...a, ...Array(after).fill(null)];
    const fit = cssVar("--run"), fat = cssVar("--trail"), form = cssVar("--accent");
    const hFit = hist.map(d => d[2]), hFat = hist.map(d => d[3]), hForm = hist.map(d => d[4]);
    // projections start from the last history point so the lines join
    const join = <T,>(h: T[], p: T[]) => pad([h.at(-1) ?? null, ...p], Math.max(hist.length - 1, 0), 0);
    return {
      type: "line",
      data: { labels, datasets: [
        { label: "Fitness", data: pad(hFit, 0, proj.length), borderColor: fit, borderWidth: 2, pointRadius: 0 },
        { label: "Fatigue", data: pad(hFat, 0, proj.length), borderColor: fat, borderWidth: 2, pointRadius: 0 },
        { label: "Form", data: pad(hForm, 0, proj.length), borderColor: form, backgroundColor: alpha(form, 0.1), borderWidth: 2, pointRadius: 0, fill: "origin" },
        { label: "Fitness, planned", data: join(hFit, proj.map(p => p.fitness)), borderColor: fit, borderWidth: 2, borderDash: [5, 4], pointRadius: 0 },
        { label: "Fatigue, planned", data: join(hFat, proj.map(p => p.fatigue)), borderColor: fat, borderWidth: 2, borderDash: [5, 4], pointRadius: 0 },
        { label: "Form, planned", data: join(hForm, proj.map(p => p.form)), borderColor: form, borderWidth: 2, borderDash: [5, 4], pointRadius: 0 },
      ] },
      options: {
        interaction: { mode: "index", intersect: false },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8, callback: function (v) { return fmtShort(labels[Number(v)]); } } },
          y: { title: { display: true, text: "training load units" }, grid: { color: cssVar("--line-2") } } },
        plugins: { legend: { position: "top", align: "end", labels: { filter: it => !it.text.includes("planned") } },
          tooltip: { callbacks: { title: it => fmtDay(labels[it[0].dataIndex]), label: it => it.parsed.y == null ? "" : ` ${it.dataset.label}: ${nf(it.parsed.y, 1)}` } } },
      },
    };
  }, [history, proj]);
  const formWord = (v: number) => (v > 15 ? "very fresh, fitness may start to slip" : v > 5 ? "fresh, ready to perform" : v > -10 ? "neutral" : v > -30 ? "tired, building" : "very tired, overreaching");
  return (
    <div className="panel">
      <div className="panel-head"><h3>Fitness and form planner</h3><span className="small muted">Fitness is your 42-day load, fatigue your 7-day load, form the gap between them</span></div>
      <div className="controls planner">
        <label>Target day <input type="date" value={target} min={addDays(plan.day, 1)} max={addDays(plan.day, 180)} onChange={e => e.target.value && set("plan-target", setTarget)(e.target.value)} /></label>
        <label>Training until then <input type="range" min={0} max={200} step={10} value={level} onChange={e => set("plan-level", setLevel)(Number(e.target.value))} />
          <span className="mono">{level}%</span><span className="small muted">of your last 4 weeks ({nf(plan.weekly_average * level / 100)} a week)</span></label>
        <label>Easier final days <input type="range" min={0} max={14} value={taper} onChange={e => set("plan-taper", setTaper)(Number(e.target.value))} /><span className="mono">{taper}</span><span className="small muted">at half the load</span></label>
      </div>
      {end && <div className="callout">
        <div><span className="eyebrow">Form on {fmtShort(target)}</span><b>{signed(end.form)}</b><span className="small muted">{formWord(end.form)}</span></div>
        <div><span className="eyebrow">Fitness then</span><b>{nf(end.fitness, 1)}</b><span className="small muted">today {nf(plan.fitness, 1)}</span></div>
        <div><span className="eyebrow">Best form on the way</span><b>{signed(Math.max(...proj.map(p => p.form)))}</b><span className="small muted">{fmtShort(proj.reduce((a, b) => (b.form > a.form ? b : a)).day)}</span></div>
        <div><span className="eyebrow">Your fittest</span><b>{nf(plan.peak_fitness.value, 1)}</b><span className="small muted">{fmtDay(plan.peak_fitness.day)}</span></div>
      </div>}
      <div className="chart tall"><canvas ref={ref} /></div>
      <p className="note">The plan repeats your usual week (the average load of each weekday over the last 8 weeks), scaled to the level you set, with the last days at half the load. Dashed lines are the plan; the shaded line is form. Most people race best with form between +5 and +15.</p>
    </div>
  );
}

function project(plan: LoadPlan, target: string, level: number, taper: number) {
  const days = Math.max(1, Math.round((parseDay(target).getTime() - parseDay(plan.day).getTime()) / 864e5));
  const sum = plan.weekday_pattern.reduce((a, b) => a + b, 0);
  const week = sum > 0 ? plan.weekday_pattern.map(v => (v / sum) * plan.weekly_average) : Array(7).fill(plan.weekly_average / 7);
  let ctl = plan.fitness, atl = plan.fatigue;
  const out: { day: string; fitness: number; fatigue: number; form: number }[] = [];
  for (let k = 1; k <= days; k++) {
    const day = addDays(plan.day, k);
    const wd = (parseDay(day).getDay() + 6) % 7;                     // Monday = 0, as in the backend
    let l = week[wd] * level / 100;
    if (days - k < taper) l *= 0.5;
    out.push({ day, fitness: ctl, fatigue: atl, form: ctl - atl });   // values at the start of the day
    ctl += (l - ctl) / plan.fitness_days;
    atl += (l - atl) / plan.fatigue_days;
  }
  return out;
}
