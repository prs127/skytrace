"""Explore menu: pick the 2nd-fastest Gaia DR3 star, run the live search, check the target marker lands on the star."""
import asyncio, sys, time
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]); pg = await b.new_page(viewport={"width": 1500, "height": 1100}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(sys.argv[1], wait_until="networkidle"); await pg.wait_for_timeout(2500)
        n = await pg.evaluate("document.querySelectorAll('#libFast [data-fast]').length"); print("library fast-star entries:", n)
        print("first entries:", await pg.evaluate("Array.from(document.querySelectorAll('#libFast [data-fast]')).slice(0,2).map(o=>o.textContent)"))
        await pg.click('details:has(#libFast) > summary')
        t0 = time.time(); await pg.click('[data-fast="1"]')
        await pg.wait_for_function("window.__skytrace.F && /Fast star|RA /.test(document.getElementById('fieldTitle').textContent) && document.getElementById('loadingVeil').classList.contains('d-none')", timeout=400000)
        await pg.wait_for_timeout(1500)
        r = await pg.evaluate("""(() => { const T = window.__skytrace, F = T.F, ex = F.meta.exposures, n = F.np, out = [];
          T.FRAMES.forEach((fr) => { const m = fr.members, tra = m.reduce((s, i) => s + ex[i].tra, 0) / m.length, tde = m.reduce((s, i) => s + ex[i].tdec, 0) / m.length;
            const [px, py] = T.world2pix(tra, tde); let cx = px, cy = py;
            for (let it = 0; it < 5; it++) { let sw = 0, sx = 0, sy = 0; const v = [];
              for (let y = Math.floor(cy) - 6; y <= Math.ceil(cy) + 6; y++) for (let x = Math.floor(cx) - 6; x <= Math.ceil(cx) + 6; x++) { const r = Math.hypot(x - cx, y - cy); if (r > 4 && r < 6) { const q = fr.img[y * n + x]; if (q === q) v.push(q); } }
              v.sort((a, b) => a - b); const bg = v[Math.floor(v.length / 2)] || 0;
              for (let y = Math.floor(cy) - 3; y <= Math.ceil(cy) + 3; y++) for (let x = Math.floor(cx) - 3; x <= Math.ceil(cx) + 3; x++) { if (Math.hypot(x - cx, y - cy) > 2.5) continue; const q = fr.img[y * n + x] - bg; if (q === q && q > 0) { sw += q; sx += q * x; sy += q * y; } }
              if (sw > 0) { cx = sx / sw; cy = sy / sw; } }
            out.push(+Math.hypot(cx - px, cy - py).toFixed(2)); });
          return {title: document.getElementById('fieldTitle').textContent, n: ex.length, plx: F.meta.target.plx, pm: [F.meta.target.pmra, F.meta.target.pmdec], off: out}; })()""")
        print(f"built in {time.time()-t0:.0f}s:", r)
        await pg.fill("#coordInput", await pg.evaluate("window.__skytrace.F.meta.grid.crval.map(v => v.toFixed(4)).join(' ')")); await pg.press("#coordInput", "Enter"); await pg.wait_for_timeout(2500)
        print("a coordinate search inside a user field is listed in Your searches:", await pg.evaluate("document.querySelectorAll('#libMine [data-key]').length"))
        print("errors:", errs or "none"); await b.close()
asyncio.run(main())
