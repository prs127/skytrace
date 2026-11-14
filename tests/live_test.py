import sys
import asyncio, time
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1500, "height": 1100}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        await pg.goto((sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/"), wait_until="networkidle")
        await pg.wait_for_function("window.__skytrace && window.__skytrace.FRAMES.length > 0", timeout=60000)
        print("badge:", await pg.inner_text("#modeBadge"))
        t0 = time.time()
        await pg.fill("#coordInput", "10h03m07.63s +03d21m00.8s"); await pg.press("#coordInput", "Enter")
        await pg.wait_for_function("window.__skytrace.F && window.__skytrace.F.meta.key.startsWith('f')", timeout=400000)
        await pg.wait_for_timeout(800)
        m = await pg.evaluate("() => { const F = window.__skytrace.F; return [F.meta.key, F.meta.name, F.meta.exposures.length, window.__skytrace.VISITS.length, F.meta.catalogs.gaia.length, F.meta.exposures.filter(e => e.det === 2).length] }")
        print(f"live build {time.time()-t0:.0f}s ->", m, "| url:", pg.url)
        await pg.select_option("#detSel", "sw"); await pg.wait_for_timeout(500)
        await pg.screenshot(path="/home/claude/skytrace/scratch/shot_live_m101.png")
        await pg.click("#checkReleases"); await pg.wait_for_timeout(3000)
        print("releases:", await pg.inner_text("#relMsg"))
        # second request for same position must hit the cache
        t0 = time.time(); await pg.reload(wait_until="networkidle")
        await pg.wait_for_function("window.__skytrace && window.__skytrace.F && window.__skytrace.F.meta.key.startsWith('f')", timeout=60000)
        print(f"reload from URL restored live field in {time.time()-t0:.1f}s")
        print("ERRORS:", errs or "none")
        await b.close()
asyncio.run(main())
