import { useEffect, useRef } from "react";
import { Chart, registerables, type ChartConfiguration } from "chart.js";
import { cssVar } from "./theme";

Chart.register(...registerables);

function applyDefaults() {
  Chart.defaults.font.family = cssVar("--f-body").replace(/"/g, "");
  Chart.defaults.font.size = 12;
  Chart.defaults.color = cssVar("--ink-2");
  Chart.defaults.borderColor = cssVar("--line-2");
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.animation = false;
  const tt = Chart.defaults.plugins.tooltip;
  tt.backgroundColor = cssVar("--ink"); tt.titleColor = cssVar("--surface"); tt.bodyColor = cssVar("--surface");
  tt.padding = 9; tt.cornerRadius = 6;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
}

/** Draw a Chart.js chart into the returned canvas ref; rebuilt whenever `deps` change. */
export function useChart(build: () => ChartConfiguration | null, deps: unknown[]) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    applyDefaults();
    const cfg = build();
    if (!cfg) return;
    const chart = new Chart(ref.current, cfg);
    return () => chart.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}
