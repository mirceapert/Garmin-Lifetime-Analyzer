import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type LngLatBoundsLike, type StyleSpecification } from "maplibre-gl";
import { api, type Tiles, type TrackRow } from "../api";
import { nf, SPORTS } from "../lib/format";
import { decode } from "../lib/polyline";
import { load, save } from "../lib/storage";
import { cssVar } from "../lib/theme";
import { useChart } from "../lib/useChart";
import { useData } from "../lib/useData";

// Dark base map in both themes: the tracks glow on a night ground.
// OpenFreeMap: free vector tiles from OpenStreetMap data, no API key or account needed.
const MAP_STYLE = "https://tiles.openfreemap.org/styles/dark";
// If OpenFreeMap can't be reached, fall back to the standard OpenStreetMap tiles, darkened.
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster", tileSize: 256, maxzoom: 19,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    },
  },
  layers: [
    { id: "ground", type: "background", paint: { "background-color": "#0a1016" } },
    { id: "osm", type: "raster", source: "osm", paint: { "raster-saturation": -0.85, "raster-brightness-max": 0.32, "raster-contrast": 0.15 } },
  ],
};
const STYLE_TIMEOUT_MS = 10_000;

/** Id of the first label layer, so tracks draw above roads but under place names. */
const firstLabel = (map: maplibregl.Map) => map.getStyle().layers.find(l => l.type === "symbol")?.id;

interface Area { label: string; count: number; bounds: LngLatBoundsLike }

/** Group tracks by where they start (0.25° cells) and name each place after the word its activities share most. */
function findAreas(tracks: TrackRow[]): Area[] {
  const cells = new Map<string, TrackRow[]>();
  for (const t of tracks) {
    const k = `${Math.round(t.bbox[0] * 4)},${Math.round(t.bbox[1] * 4)}`;
    (cells.get(k) ?? cells.set(k, []).get(k)!).push(t);
  }
  return [...cells.values()].sort((a, b) => b.length - a.length).slice(0, 7).map((ts, i) => {
    const words = new Map<string, number>();
    for (const t of ts) {
      const w = (t.name ?? "").split(/[\s\-–,]+/)[0];
      if (w && w.length > 2 && /^\p{Lu}/u.test(w)) words.set(w, (words.get(w) ?? 0) + 1);
    }
    const label = [...words.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? `Area ${i + 1}`;
    // fit to the middle 90% of tracks so one long ride doesn't zoom the map out
    const lats = ts.flatMap(t => [t.bbox[0], t.bbox[2]]).sort((a, b) => a - b);
    const lons = ts.flatMap(t => [t.bbox[1], t.bbox[3]]).sort((a, b) => a - b);
    const q = (arr: number[], p: number) => arr[Math.min(arr.length - 1, Math.max(0, Math.round(p * (arr.length - 1))))];
    return { label, count: ts.length, bounds: [[q(lons, 0.05), q(lats, 0.05)], [q(lons, 0.95), q(lats, 0.95)]] as LngLatBoundsLike };
  }).filter((a, i, all) => all.findIndex(b => b.label === a.label) === i);
}

function tilePolygon(x: number, y: number, z: number, size = 1): number[][][] {
  const n = 2 ** z;
  const lon = (tx: number) => (tx / n) * 360 - 180;
  const lat = (ty: number) => (Math.atan(Math.sinh(Math.PI * (1 - (2 * ty) / n))) * 180) / Math.PI;
  return [[[lon(x), lat(y)], [lon(x + size), lat(y)], [lon(x + size), lat(y + size)], [lon(x), lat(y + size)], [lon(x), lat(y)]]];
}

export function MapView({ scheme }: { scheme: string }) {
  const [tracks, tErr] = useData(api.tracks);
  const [tiles, tiErr] = useData(api.tiles);
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false);
  const [sports, setSports] = useState<Record<string, boolean>>(() => load("map-sports", {}));
  const [showTiles, setShowTiles] = useState<boolean>(() => load("map-tiles", true));
  const [area, setArea] = useState<number>(0);

  const areas = useMemo(() => (tracks ? findAreas(tracks) : []), [tracks]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const t of tracks ?? []) c[t.sport] = (c[t.sport] ?? 0) + 1;
    return c;
  }, [tracks]);
  const visible = (k: string) => sports[k] !== false;

  // create the map once
  useEffect(() => {
    if (!box.current) return;
    const map = new maplibregl.Map({ container: box.current, style: MAP_STYLE, center: [21.23, 45.75], zoom: 11, attributionControl: { compact: true } });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    let settled = false;
    const fallback = () => {
      if (settled) return;
      settled = true;
      map.setStyle(FALLBACK_STYLE);
      map.once("styledata", () => setReady(true));
    };
    map.on("load", () => { settled = true; setReady(true); });
    // the style itself failed (not a single tile): use the fallback map
    map.on("error", e => { if (!settled && !("sourceId" in e)) fallback(); });
    const timer = setTimeout(fallback, STYLE_TIMEOUT_MS);
    mapRef.current = map;
    return () => { clearTimeout(timer); map.remove(); mapRef.current = null; };
  }, []);

  // tracks layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !tracks) return;
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: tracks.map(t => ({ type: "Feature", properties: { sport: t.sport, id: t.id },
        geometry: { type: "LineString", coordinates: decode(t.polyline).map(([la, lo]) => [lo, la]) } })),
    };
    const color: maplibregl.ExpressionSpecification = ["match", ["get", "sport"], ...SPORTS.flatMap(s => [s.key, cssVar(`--${s.key}`)]), "#999"] as unknown as maplibregl.ExpressionSpecification;
    if (map.getSource("tracks")) (map.getSource("tracks") as maplibregl.GeoJSONSource).setData(fc);
    else {
      map.addSource("tracks", { type: "geojson", data: fc });
      map.addLayer({ id: "tracks", type: "line", source: "tracks", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": color, "line-opacity": ["interpolate", ["linear"], ["zoom"], 8, 0.55, 14, 0.4],
          "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1, 12, 1.6, 16, 3] } }, firstLabel(map));
    }
    if (areas[0]) map.fitBounds(areas[0].bounds, { padding: 30, duration: 0 });
  }, [ready, tracks, areas, scheme]);

  // tiles layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !tiles) return;
    const cluster = new Set(tiles.cluster.map(([x, y]) => `${x},${y}`));
    const fc: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: tiles.tiles.map(([x, y, first]) => ({
      type: "Feature", properties: { cluster: cluster.has(`${x},${y}`), first }, geometry: { type: "Polygon", coordinates: tilePolygon(x, y, tiles.zoom) } })) };
    const sq = tiles.max_square;
    const square: GeoJSON.Feature = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: tilePolygon(sq.x, sq.y, tiles.zoom, sq.size) } };
    if (!map.getSource("tiles")) {
      map.addSource("tiles", { type: "geojson", data: fc });
      map.addSource("square", { type: "geojson", data: square });
      const below = map.getLayer("tracks") ? "tracks" : firstLabel(map);
      map.addLayer({ id: "tiles-fill", type: "fill", source: "tiles", paint: { "fill-color": "#9085e9", "fill-opacity": ["case", ["get", "cluster"], 0.28, 0.12] } }, below);
      map.addLayer({ id: "tiles-line", type: "line", source: "tiles", paint: { "line-color": "#9085e9", "line-opacity": 0.35, "line-width": 0.6 } }, below);
      map.addLayer({ id: "square", type: "line", source: "square", paint: { "line-color": "#c9c2ff", "line-width": 2, "line-dasharray": [3, 2] } }, firstLabel(map));
    }
  }, [ready, tiles]);

  // visibility
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (map.getLayer("tracks")) map.setFilter("tracks", ["in", ["get", "sport"], ["literal", SPORTS.map(s => s.key).filter(visible)]]);
    for (const id of ["tiles-fill", "tiles-line", "square"]) if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", showTiles ? "visible" : "none");
  }, [ready, sports, showTiles, tracks, tiles]);

  const goArea = (i: number) => { setArea(i); mapRef.current?.fitBounds(areas[i].bounds, { padding: 30 }); };
  const fitAll = () => {
    if (!tracks?.length) return;
    const b = tracks.reduce((acc, t) => [Math.min(acc[0], t.bbox[1]), Math.min(acc[1], t.bbox[0]), Math.max(acc[2], t.bbox[3]), Math.max(acc[3], t.bbox[2])], [180, 90, -180, -90]);
    setArea(-1); mapRef.current?.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 30 });
  };
  const toggleSport = (k: string) => { const n = { ...sports, [k]: !visible(k) }; setSports(n); save("map-sports", n); };
  const toggleTiles = () => { setShowTiles(!showTiles); save("map-tiles", !showTiles); };

  return (
    <section className="view">
      <div className="view-head"><h2>Lifetime heatmap</h2>
        <p className="muted">Every GPS track you have recorded. Brighter lines are paths you return to. Drag to pan, scroll or pinch to zoom.</p></div>
      {(tErr || tiErr) && <p className="empty">Could not load the map data: {tErr ?? tiErr}</p>}
      <div className="areas" role="group" aria-label="Places">
        {areas.map((a, i) => <button key={a.label} aria-pressed={i === area} onClick={() => goArea(i)}>{a.label} <span className="mono small">{a.count}</span></button>)}
        <button aria-pressed={area === -1} onClick={fitAll}>Everything</button>
      </div>
      <div className="grid-side">
        <div className="mapbox"><div ref={box} style={{ position: "absolute", inset: 0 }} /></div>
        <div className="panel">
          <h3>Layers</h3>
          <div style={{ display: "grid", gap: 8 }}>
            {SPORTS.filter(s => counts[s.key]).map(s => (
              <label className="ck" key={s.key}><input type="checkbox" checked={visible(s.key)} onChange={() => toggleSport(s.key)} />
                <span className="swatch" style={{ background: `var(--${s.key})`, marginRight: 0 }} />{s.label} <span className="mono small">{counts[s.key]}</span></label>))}
            <label className="ck"><input type="checkbox" checked={showTiles} onChange={toggleTiles} /> Explorer tiles and largest square</label>
          </div>
          {tiles && <TileStats tiles={tiles} />}
        </div>
      </div>
    </section>
  );
}

function TileStats({ tiles }: { tiles: Tiles }) {
  const years = Object.keys(tiles.per_year);
  const ref = useChart(() => ({
    type: "bar",
    data: { labels: years, datasets: [{ data: years.map(y => tiles.per_year[y]), backgroundColor: cssVar("--accent"), borderRadius: 4, maxBarThickness: 24 }] },
    options: { plugins: { legend: { display: false }, tooltip: { callbacks: { title: it => years[it[0].dataIndex], label: it => ` ${it.parsed.y} new tiles` } } },
      scales: { x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: false, callback: (_v, i) => `'${years[i].slice(2)}` } },
        y: { beginAtZero: true, ticks: { maxTicksLimit: 4 }, grid: { color: cssVar("--line-2") } } } },
  }), [tiles]);
  return (
    <>
      <div className="statlist">
        <div><span className="muted">Tiles visited</span><span className="v">{nf(tiles.tiles.length)}</span></div>
        <div><span className="muted">Largest square</span><span className="v">{tiles.max_square.size} × {tiles.max_square.size}</span></div>
        <div><span className="muted">Largest cluster</span><span className="v">{nf(tiles.cluster.length)}</span></div>
      </div>
      <div><div className="eyebrow" style={{ marginBottom: 6 }}>New tiles per year</div><div className="chart tiny"><canvas ref={ref} /></div></div>
      <p className="note">A tile is a zoom-14 map square, about 1.7 km wide here. The largest square is the biggest block of tiles you have fully covered; a tile joins your cluster when all four neighbours are visited too.</p>
    </>
  );
}
