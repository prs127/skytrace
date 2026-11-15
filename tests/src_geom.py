import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]); pg = await b.new_page(viewport={"width": 1500, "height": 1100})
        for fov in ("9.1", "4"):
            await pg.goto(sys.argv[1] + f"?field=wise0855&fov={fov}", wait_until="networkidle"); await pg.wait_for_timeout(2500)
            await pg.click('label[for="src-2mass"]'); await pg.wait_for_timeout(4000)
            r = await pg.evaluate("(() => { const c = window.SkyAladin.compareInstance, g = window.__skytrace.F.meta.grid; return {aladin: c.getRaDec(), fov: c.getFov(), grid: g.crval, S_fov: window.__skytrace.S.fov}; })()")
            print(f"FOV {fov}': Aladin centre {r['aladin'][0]:.5f} {r['aladin'][1]:.5f} vs grid {r['grid'][0]:.5f} {r['grid'][1]:.5f}; Aladin field {r['fov'][0]*60:.2f}' x {r['fov'][1]*60:.2f}' (SPHEREx view {r['S_fov']}')")
        await b.close()
asyncio.run(main())
