import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]); pg = await b.new_page(viewport={"width": 1400, "height": 1000})
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(sys.argv[1] + "?field=epsindib&mode=custom&A=0&B=1", wait_until="networkidle"); await pg.wait_for_timeout(2500)
        box = await (await pg.query_selector("#ovCanvas")).bounding_box()
        await pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3); await pg.wait_for_timeout(300)
        print("A-B readout:", (await pg.inner_text("#hoverReadout")).replace("\n", " | "))
        await pg.goto(sys.argv[1] + "?field=epsindib", wait_until="networkidle"); await pg.wait_for_timeout(2500)
        await pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3); await pg.wait_for_timeout(300)
        print("visit readout:", (await pg.inner_text("#hoverReadout")).replace("\n", " | "))
        print("errors:", errs); await b.close()
asyncio.run(main())
