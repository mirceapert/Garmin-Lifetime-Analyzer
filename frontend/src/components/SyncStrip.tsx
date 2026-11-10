import { useCallback, useEffect, useState } from "react";
import { api, type SyncStatus } from "../api";

const when = (iso: string) => {
  const d = new Date(iso);
  const today = new Date().toDateString() === d.toDateString();
  return today ? `today ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`
    : d.toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
};

/** Last sync, Sync now, and API key warnings (FR-3). Polls every minute, every 3 s while a sync runs. */
export function SyncStrip({ onSynced }: { onSynced: () => void }) {
  const [st, setSt] = useState<SyncStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const refresh = useCallback(() => api.syncStatus().then(s => { setSt(s); setErr(null); return s; }).catch(e => { setErr(String(e.message)); return null; }), []);

  useEffect(() => { refresh(); const t = setInterval(refresh, 60_000); return () => clearInterval(t); }, [refresh]);
  useEffect(() => {
    if (!st?.running) return;
    const t = setInterval(async () => {
      const s = await refresh();
      if (s && !s.running) { clearInterval(t); if (s.last_run?.status === "ok") onSynced(); }
    }, 3000);
    return () => clearInterval(t);
  }, [st?.running, refresh, onSynced]);

  const start = async () => {
    try { await api.syncNow(); await refresh(); } catch (e) { setErr(String((e as Error).message)); }
  };

  const last = st?.last_run;
  const level = !st ? "" : st.warnings.some(w => w.level === "critical") ? "bad" : st.warnings.some(w => w.level === "warning") ? "warn" : "";
  return (
    <>
      <div className="sync" aria-live="polite">
        {st && (
          <span><span className={`dot ${level}`} />
            {st.running ? "Syncing with Garmin…" : last ? `Last sync ${when(last.started_local)}${last.status === "failed" ? " (failed)" : ""}` : "Not synced yet"}
          </span>
        )}
        <button className="btn" onClick={start} disabled={!st || st.running || !st.key.configured}>
          {st?.running ? "Syncing…" : "Sync now"}
        </button>
      </div>
      {(st?.warnings ?? []).filter(w => w.level !== "info").map(w => (
        <div key={w.text} className={`banner ${w.level}`} role="status" style={{ flexBasis: "100%" }}>
          <strong>{w.level === "critical" ? "Action needed" : "Heads up"}</strong><span>{w.text}</span>
        </div>
      ))}
      {err && <div className="banner warning" style={{ flexBasis: "100%" }}><strong>Sync</strong><span>{err}</span></div>}
    </>
  );
}
