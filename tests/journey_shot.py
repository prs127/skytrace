import asyncio, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1500, "height": 1000}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text))
        await pg.goto(BASE + "?field=barnard"); await pg.wait_for_timeout(5000)
        await pg.screenshot(path="/home/claude/scratch/j0.png")
        await pg.click("#targetButtons button[data-key=wise0855]"); await pg.wait_for_timeout(500)
        await pg.screenshot(path="/home/claude/scratch/j1_flight.png")
        await pg.wait_for_timeout(3000)
        await pg.screenshot(path="/home/claude/scratch/j2_landed.png")
        print("errors:", errs)
        await b.close()
asyncio.run(main())
