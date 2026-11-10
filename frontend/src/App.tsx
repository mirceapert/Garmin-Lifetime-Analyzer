import { lazy, Suspense, useCallback, useState } from "react";
import { SyncStrip } from "./components/SyncStrip";
import { useHash } from "./lib/route";
import { Lifetime } from "./views/Lifetime";
import { Routes } from "./views/Routes";
import { BestEfforts } from "./views/BestEfforts";
import { useColorScheme } from "./lib/theme";

// the map library is large: load it only when the map tab opens
const MapView = lazy(() => import("./views/MapView").then(m => ({ default: m.MapView })));

const TABS = [
  { id: "lifetime", label: "Lifetime" },
  { id: "map", label: "Heatmap & tiles" },
  { id: "routes", label: "Routes" },
  { id: "best-efforts", label: "Best efforts" },
];

export function App() {
  const [view, param] = useHash();
  const scheme = useColorScheme();
  const [version, setVersion] = useState(0);              // bumps after a sync, so views reload their data
  const synced = useCallback(() => setVersion(v => v + 1), []);
  const current = TABS.some(t => t.id === view) ? view : "lifetime";
  const key = `${scheme}-${version}`;

  return (
    <div className="wrap">
      <header className="top">
        <div className="brand">
          <span className="eyebrow">Your Garmin history, lifetime view</span>
          <h1>Garmin Data Analyzer</h1>
        </div>
        <SyncStrip onSynced={synced} />
      </header>
      <nav className="tabs" aria-label="Views">
        {TABS.map(t => <a key={t.id} href={`#${t.id}`} aria-current={t.id === current ? "page" : undefined}>{t.label}</a>)}
      </nav>
      <main>
        {current === "lifetime" && <Lifetime key={key} />}
        {current === "map" && <Suspense fallback={<p className="empty">Loading the map…</p>}><MapView key={key} scheme={scheme} /></Suspense>}
        {current === "routes" && <Routes key={key} selected={param ? Number(param) : null} />}
        {current === "best-efforts" && <BestEfforts key={key} />}
      </main>
      <footer>Data from your Garmin account, stored on this computer. Map: OpenFreeMap © OpenMapTiles, data © OpenStreetMap contributors.</footer>
    </div>
  );
}
