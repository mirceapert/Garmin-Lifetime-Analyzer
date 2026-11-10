/** Google encoded polyline -> [lat, lon][] */
export function decode(text: string, precision = 5): [number, number][] {
  const f = 10 ** precision, out: [number, number][] = [];
  let i = 0, lat = 0, lon = 0;
  while (i < text.length) {
    for (let k = 0; k < 2; k++) {
      let shift = 0, result = 0, b: number;
      do { b = text.charCodeAt(i++) - 63; result |= (b & 0x1f) << shift; shift += 5; } while (b >= 0x20);
      const d = result & 1 ? ~(result >> 1) : result >> 1;
      if (k === 0) lat += d; else lon += d;
    }
    out.push([lat / f, lon / f]);
  }
  return out;
}
