import asyncio, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox", "--use-gl=swiftshader", "--enable-webgl", "--ignore-gpu-blocklist"])
        pg = await b.new_page(viewport={"width": 1500, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append("PAGE " + str(e)))
        pg.on("console", lambda m: m.type == "error" and errs.append(m.text[:160]))
        await pg.goto(BASE + "?field=epsindib"); await pg.wait_for_timeout(5000)
        await pg.click('[data-bs-target="#tabAladin"]'); await pg.wait_for_timeout(8000)
        print("aladin instance:", await pg.evaluate("!!(window.SkyAladin && window.SkyAladin.instance)"))
        print("msg:", await pg.inner_text("#aladinMsg"))
        el = await pg.query_selector("#tabAladin"); await el.screenshot(path="/home/claude/scratch/aladin.png")
        print("errors:", [e for e in errs][:8])
        await b.close()
asyncio.run(main())
