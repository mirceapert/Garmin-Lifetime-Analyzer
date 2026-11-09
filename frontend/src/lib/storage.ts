// Per-browser conveniences (remembered filters). Never required for the page to work.
export function load<T>(key: string, fallback: T): T {
  try { const v = localStorage.getItem("gla:" + key); return v ? (JSON.parse(v) as T) : fallback; } catch { return fallback; }
}
export function save(key: string, value: unknown): void {
  try { localStorage.setItem("gla:" + key, JSON.stringify(value)); } catch { /* storage unavailable: fine */ }
}
