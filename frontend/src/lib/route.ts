import { useEffect, useState } from "react";

/** Plain #name routing: "#routes-25" -> ["routes", "25"]. */
export function useHash(): [string, string | null] {
  const read = () => {
    const h = location.hash.slice(1);
    const m = /^([a-z-]+?)(?:-(\d+))?$/.exec(h);
    return m ? [m[1], m[2] ?? null] as [string, string | null] : ["", null] as [string, string | null];
  };
  const [state, setState] = useState(read);
  useEffect(() => {
    const on = () => setState(read());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return state;
}
