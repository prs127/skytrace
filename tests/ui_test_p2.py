"""Prototype 2 browser checks: official channel labels, epoch legend, shift-and-add, all fields load."""
import asyncio, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/"
OUT = "/home/claude/skytrace/scratch/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1500, "height": 1150}); errs = []
        pg.on("pageerror", lambda e: errs.append(f"PAGEERROR {e}"))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "404" not in m.text else None)
        await pg.goto(BASE + "?field=epsindib", wait_until="networkidle")
        await pg.wait_for_function("window.__skytrace && window.__skytrace.FRAMES.length > 0", timeout=60000)
        print("detector labels:", await pg.evaluate("() => [...document.querySelectorAll('#detSel option')].map(o => o.textContent)"))
        print("field note:", await pg.inner_text("#fieldNote"))
        await pg.click("#diffToggle"); await pg.wait_for_timeout(300)
        print("legend (diff, frame 1):", await pg.inner_text("#epochLegend"))
        await pg.click("#diffToggle"); await pg.wait_for_timeout(300)
        # shift-and-add: stack all visits in custom mode, compare peak at target with and without shift
        await pg.click("label[for=m-custom]"); await pg.wait_for_timeout(300)
        n = await pg.evaluate("() => window.__skytrace.VISITS.length")
        js = """(sa) => { const s = window.__skytrace; s.S.sa = sa; s.S.A = [...Array(s.VISITS.length).keys()].join(','); s.S.B = '';
            document.getElementById('saToggle').checked = !!sa; document.getElementById('saToggle').dispatchEvent(new Event('change'));
            const fr = s.FRAMES[0], F = s.F, t = F.meta.target, n = F.np;
            const [x, y] = s.world2pix(t.ra + t.pmra * (F.meta.grid.mjd_ref - t.epoch_mjd) / 365.25 / 3.6e6 / Math.cos(t.dec * Math.PI / 180), t.dec + t.pmdec * (F.meta.grid.mjd_ref - t.epoch_mjd) / 365.25 / 3.6e6);
            let pk = -1e9, sum = 0, sum2 = 0;
            for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) { const v = fr.img[(Math.round(y) + dy) * n + Math.round(x) + dx]; if (v > pk) pk = v; }
            // second-moment size of the target blob (pixels above 20% of peak)
            let w = 0, xx = 0, yy = 0, cx = 0, cy = 0;
            for (let dy = -3; dy <= 3; dy++) for (let dx = -3; dx <= 3; dx++) { const v = fr.img[(Math.round(y) + dy) * n + Math.round(x) + dx]; if (v > 0.2 * pk) { w += v; cx += v * dx; cy += v * dy; xx += v * dx * dx; yy += v * dy * dy; } }
            cx /= w; cy /= w; return { peak: pk, size: Math.sqrt(xx / w - cx * cx + yy / w - cy * cy), legend: document.getElementById('epochLegend').textContent, frames: s.FRAMES.length }; }"""
        off = await pg.evaluate(js, 0); on = await pg.evaluate(js, 1)
        print(f"{n} visits stacked. Eps Indi B without shift: peak {off['peak']:.3f}, size {off['size']:.2f} px | with shift-and-add at its Gaia PM: peak {on['peak']:.3f}, size {on['size']:.2f} px")
        print("legend with shift-and-add:", on["legend"])
        await pg.screenshot(path=OUT + "p2_shiftadd.png")
        # every field loads and builds frames
        for key in ["wise0855", "barnard", "epsindib", "rwaur", "rdra", "m101"]:
            await pg.goto(BASE + f"?field={key}", wait_until="networkidle")
            await pg.wait_for_function("window.__skytrace && window.__skytrace.F && window.__skytrace.FRAMES.length > 0", timeout=60000)
            r = await pg.evaluate("() => { const F = window.__skytrace.F; const ch = new Set(F.meta.exposures.map(e => e.band)); return [F.meta.key, F.meta.exposures.length, window.__skytrace.VISITS.length, ch.size, F.meta.channels_source, document.getElementById('blendNote').textContent.slice(0, 60)] }")
            print("field", r)
        await pg.goto(BASE + "?field=wise0855", wait_until="networkidle"); await pg.wait_for_timeout(1500)
        await pg.screenshot(path=OUT + "p2_wise.png", full_page=True)
        print("ERRORS:", errs or "none")
        await b.close()
asyncio.run(main())
