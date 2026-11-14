import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]); pg = await b.new_page()
        for key in ["epsindib", "barnard"]:
            await pg.goto(f"{sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8080/'}?field={key}&det=all", wait_until="networkidle")
            await pg.wait_for_function("window.__skytrace && window.__skytrace.FRAMES.length > 0", timeout=60000)
            js = """(sa) => { const s = window.__skytrace; document.getElementById('saToggle').checked = !!sa; document.getElementById('saToggle').dispatchEvent(new Event('change'));
              const F = s.F, t = F.meta.target, n = F.np, ref = F.meta.grid.mjd_ref;
              const [x0, y0] = s.world2pix(t.ra + t.pmra * (ref - t.epoch_mjd) / 365.25 / 3.6e6 / Math.cos(t.dec * Math.PI / 180), t.dec + t.pmdec * (ref - t.epoch_mjd) / 365.25 / 3.6e6);
              return s.FRAMES.map(fr => { let w = 0, cx = 0, cy = 0; const X = Math.round(x0), Y = Math.round(y0);
                for (let dy = -2; dy <= 2; dy++) for (let dx = -2; dx <= 2; dx++) { const v = fr.img[(Y + dy) * n + X + dx]; if (v > 0) { w += v; cx += v * (X + dx); cy += v * (Y + dy); } }
                return [ (cx / w - x0).toFixed(2), (cy / w - y0).toFixed(2), Math.round(fr.mjd) ]; }); }"""
            off = await pg.evaluate(js, 0); on = await pg.evaluate(js, 1)
            print(f"{key}: target centroid offset from its reference position, per visit (dx, dy px, MJD)")
            print("   shift OFF:", off); print("   shift ON :", on)
        await b.close()
asyncio.run(main())
