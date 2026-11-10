import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import type { TrackRow } from "../api";
import { SPORTS } from "../lib/format";
import { decode } from "../lib/polyline";
import { load } from "../lib/storage";
import { cssVar } from "../lib/theme";
import { FALLBACK_STYLE, STYLE_TIMEOUT_MS, findAreas, firstLabel, styleUrl } from "./MapView";

/** The year's tracks on the base map you picked on the Heatmap tab, with shortcuts to the places of that year. */
export default function YearMap({ tracks }: { tracks: TrackRow[] }) {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const areas = useMemo(() => findAreas(tracks), [tracks]);
  const [area, setArea] = useState(0);
  const [ready, setReady] = useState(0);

  useEffect(() => {
    if (!box.current) return;
    const map = new maplibregl.Map({ container: box.current, style: styleUrl(load("map-base", "dark")), center: [21.23, 45.75], zoom: 10,
      attributionControl: { compact: true }, cooperativeGestures: true });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    let settled = false;
    const timer = window.setTimeout(() => { if (!settled) { settled = true; map.setStyle(FALLBACK_STYLE, { diff: false }); } }, STYLE_TIMEOUT_MS);
    map.on("style.load" as "styledata", () => { settled = true; clearTimeout(timer); setReady(r => r + 1); });
    map.on("error", e => { if (!settled && !("sourceId" in e)) { settled = true; map.setStyle(FALLBACK_STYLE, { diff: false }); } });
    mapRef.current = map;
    return () => { clearTimeout(timer); map.remove(); mapRef.current = null; };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const fc: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: tracks.map(t => ({ type: "Feature", properties: { sport: t.sport },
        geometry: { type: "LineString", coordinates: decode(t.polyline).map(([la, lo]) => [lo, la]) } })),
    };
    const src = map.getSource("year") as maplibregl.GeoJSONSource | undefined;
    if (src) src.setData(fc);
    else {
      const color = ["match", ["get", "sport"], ...SPORTS.flatMap(s => [s.key, cssVar(`--${s.key}`)]), "#999"] as unknown as maplibregl.ExpressionSpecification;
      map.addSource("year", { type: "geojson", data: fc });
      map.addLayer({ id: "year", type: "line", source: "year", layout: { "line-join": "round", "line-cap": "round" },
        paint: { "line-color": color, "line-opacity": 0.7, "line-width": ["interpolate", ["linear"], ["zoom"], 8, 1.2, 14, 2.4] } }, firstLabel(map));
    }
  }, [tracks, ready]);

  useEffect(() => { setArea(0); }, [tracks]);
  useEffect(() => {
    const a = areas[area];
    if (a && mapRef.current) mapRef.current.fitBounds(a.bounds, { padding: 30, duration: ready > 1 ? 600 : 0, maxZoom: 14 });
  }, [areas, area, ready]);

  return (
    <div className="panel">
      <div className="panel-head"><h3>Where you went</h3>
        {areas.length > 1 && <div className="areas">{areas.map((a, i) => (
          <button key={a.label} aria-pressed={i === area} onClick={() => setArea(i)}>{a.label} <span className="muted">{a.count}</span></button>))}</div>}
      </div>
      <div className="mapbox year" ref={box} role="region" aria-label="Map of this year's GPS tracks" />
      <p className="small muted">{tracks.length} tracks with GPS. Use two fingers or Ctrl and scroll to zoom.</p>
    </div>
  );
}
