import { useEffect, useState } from "react";

export const cssVar = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** Re-render when the system switches between light and dark. */
export function useColorScheme(): "light" | "dark" {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const [dark, setDark] = useState(mq.matches);
  useEffect(() => {
    const on = (e: MediaQueryListEvent) => setDark(e.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [mq]);
  return dark ? "dark" : "light";
}

/** Older years recede toward the surface colour; the current year carries the accent. */
export function yearColor(year: number, years: number[], current: number): string {
  if (year === current) return cssVar("--accent");
  const older = years.filter(y => y !== current);
  const i = older.indexOf(year), t = older.length > 1 ? i / (older.length - 1) : 1;
  return mix(cssVar("--surface"), cssVar("--ink"), 0.22 + 0.5 * t);
}

export function mix(a: string, b: string, t: number): string {
  const p = (h: string) => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const A = p(a), B = p(b);
  return `rgb(${A.map((v, i) => Math.round(v + (B[i] - v) * t)).join(", ")})`;
}

export function alpha(hex: string, a: number): string {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16));
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}
