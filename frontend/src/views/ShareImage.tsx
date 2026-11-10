import { useEffect, useRef, useState } from "react";
import type { YearReview } from "../api";
import { drawShare, fontsReady, type ShareOptions } from "../lib/shareImage";
import { load, save } from "../lib/storage";

/** Preview and download of the year's share image. Drawn in this browser; nothing is uploaded. */
export function ShareImage({ review }: { review: YearReview }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const [opts, setOpts] = useState<ShareOptions>(() => ({ theme: "night", name: "", places: true, ...load<Partial<ShareOptions>>("share-image", {}) }));
  const [ready, setReady] = useState(false);
  const set = (p: Partial<ShareOptions>) => { const n = { ...opts, ...p }; setOpts(n); save("share-image", n); };

  useEffect(() => { let live = true; fontsReady().then(() => live && setReady(true)); return () => { live = false; }; }, []);
  useEffect(() => { if (ready && ref.current) drawShare(ref.current, review, opts); }, [ready, review, opts]);

  const download = () => {
    const c = ref.current;
    if (!c) return;
    c.toBlob(b => {
      if (!b) return;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `year-in-review-${review.year}${opts.theme === "day" ? "-day" : ""}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    }, "image/png");
  };

  return (
    <div className="panel share" id="share">
      <div className="share-preview"><canvas ref={ref} width={1080} height={1350} role="img" aria-label={`Share image for ${review.year}`} /></div>
      <div className="share-controls">
        <h3>Share {review.year}</h3>
        <p className="small muted">A 1080 × 1350 image for Instagram, WhatsApp or Strava. It's drawn here in your browser and holds no map, so it doesn't show where you live.</p>
        <div className="seg" role="group" aria-label="Look">
          <button aria-pressed={opts.theme === "night"} onClick={() => set({ theme: "night" })}>Night</button>
          <button aria-pressed={opts.theme === "day"} onClick={() => set({ theme: "day" })}>Day</button>
        </div>
        <label className="field">Name on the image <span className="small muted">(optional)</span>
          <input type="text" value={opts.name} maxLength={24} placeholder="Your name" onChange={e => set({ name: e.target.value })} />
        </label>
        <label className="ck"><input type="checkbox" checked={opts.places} onChange={e => set({ places: e.target.checked })} /> Show place names</label>
        <button className="btn primary big" onClick={download} disabled={!ready}>Download image</button>
      </div>
    </div>
  );
}
