import { useEffect, useState } from "react";

/** Load once per key; returns [data, error]. */
export function useData<T>(load: () => Promise<T>, key: unknown[] = []): [T | null, string | null] {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setError(null);
    load().then(d => live && setData(d)).catch(e => live && setError(String(e.message ?? e)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, key);
  return [data, error];
}
