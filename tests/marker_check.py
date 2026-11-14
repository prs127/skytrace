"""Does the target marker (pipeline prediction: proper motion + parallax) sit on the target's measured centroid in
each visit stack? Compared with the motion-only prediction. Centroid: flux-weighted, 2.5 px radius, sky-subtracted."""
import asyncio, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]); pg = await b.new_page()
        for key, det in (("epsindib", "all"), ("wise0855", "lw"), ("barnard", "all")):
            await pg.goto(BASE + f"?field={key}&det={det}&flat=0", wait_until="networkidle"); await pg.wait_for_timeout(2500)
            r = await pg.evaluate("""(() => { const T = window.__skytrace, F = T.F, ex = F.meta.exposures, t = F.meta.target, n = F.np, out = [];
              T.FRAMES.forEach((fr) => {
                const m = fr.members, tra = m.reduce((s, i) => s + ex[i].tra, 0) / m.length, tde = m.reduce((s, i) => s + ex[i].tdec, 0) / m.length;
                const dt = (fr.mjd - t.epoch_mjd) / 365.25, lra = t.ra + t.pmra * dt / 3.6e6 / Math.cos(t.dec * Math.PI / 180), lde = t.dec + t.pmdec * dt / 3.6e6;
                const [px, py] = T.world2pix(tra, tde), [lx, ly] = T.world2pix(lra, lde);
                let cx = px, cy = py;
                for (let it = 0; it < 5; it++) { let sw = 0, sx = 0, sy = 0; const vals = [];
                  for (let y = Math.floor(cy) - 6; y <= Math.ceil(cy) + 6; y++) for (let x = Math.floor(cx) - 6; x <= Math.ceil(cx) + 6; x++) { const r = Math.hypot(x - cx, y - cy); if (r > 4 && r < 6) { const v = fr.img[y * n + x]; if (v === v) vals.push(v); } }
                  vals.sort((a, b) => a - b); const bg = vals[Math.floor(vals.length / 2)] || 0;
                  for (let y = Math.floor(cy) - 3; y <= Math.ceil(cy) + 3; y++) for (let x = Math.floor(cx) - 3; x <= Math.ceil(cx) + 3; x++) { if (Math.hypot(x - cx, y - cy) > 2.5) continue; const v = fr.img[y * n + x] - bg; if (v === v && v > 0) { sw += v; sx += v * x; sy += v * y; } }
                  if (sw > 0) { cx = sx / sw; cy = sy / sw; } }
                out.push({ m: m.length, full: Math.hypot(cx - px, cy - py), lin: Math.hypot(cx - lx, cy - ly), plxshift: Math.hypot(px - lx, py - ly) });
              }); return out; })()""")
            fmt = lambda a: "[" + ", ".join(f"{v:.2f}" for v in a) + "]"
            print(f"{key:9s} per-visit |centroid - prediction| px: motion+parallax {fmt([x['full'] for x in r])}  motion only {fmt([x['lin'] for x in r])}  (parallax term {fmt([x['plxshift'] for x in r])} px)")
        await b.close()
asyncio.run(main())
