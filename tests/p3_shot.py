import asyncio, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1500, "height": 1150}); errs = []
        pg.on("pageerror", lambda e: errs.append("PAGE " + str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text[:150]))
        await pg.goto(BASE + "?field=wise0855"); await pg.wait_for_timeout(6000)
        print("specNote wise0855:", await pg.inner_text("#specNote"))
        await pg.screenshot(path="/home/claude/scratch/p3_wise.png")
        await pg.click("#libTargets .st-item[data-key=barnard]"); await pg.wait_for_timeout(4000)
        print("specNote barnard:", await pg.inner_text("#specNote"))
        await pg.click('[data-bs-target="#tabLc"]'); await pg.wait_for_timeout(800)
        print("lc barnard:", (await pg.inner_text("#lcPlot"))[:120])
        await pg.click("#libTargets .st-item[data-key=epsindib]"); await pg.wait_for_timeout(4000)
        await pg.click('[data-bs-target="#tabLc"]'); await pg.wait_for_timeout(800)
        print("lc epsindib has plot:", await pg.evaluate("!!document.querySelector('#lcPlot .main-svg')"))
        # pin + report
        box = await pg.query_selector("#ovCanvas"); bb = await box.bounding_box()
        await pg.mouse.click(bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2); await pg.wait_for_timeout(400)
        await pg.click("#reportBtn"); await pg.wait_for_timeout(800)
        await pg.fill("#reportNotes", "Test note: dot moves between visits"); await pg.wait_for_timeout(300)
        rep = await pg.input_value("#reportText"); print("REPORT:\n" + "\n".join(rep.splitlines()[:16]))
        await pg.screenshot(path="/home/claude/scratch/p3_report.png")
        print("errors:", errs)
        await b.close()
asyncio.run(main())
