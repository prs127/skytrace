import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1500, "height": 1080}); errs = []
        pg.on("pageerror", lambda e: errs.append("PAGE " + str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text[:150]))
        await pg.goto(sys.argv[1] + "?field=epsindib"); await pg.wait_for_timeout(5000)
        await pg.screenshot(path="/home/claude/scratch/hud_full.png")
        await pg.hover("#loRange"); await pg.wait_for_timeout(300)
        el = await pg.query_selector("aside"); await el.screenshot(path="/home/claude/scratch/hud_side.png")
        print("errors:", errs); await b.close()
asyncio.run(main())
