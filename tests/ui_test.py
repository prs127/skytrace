"""Headless browser test of the Skytrace front end (static + live modes)."""
import asyncio, json, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/"
OUT = "/home/claude/skytrace/scratch/"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1500, "height": 1100})
        errs = []
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        pg.on("pageerror", lambda e: errs.append(f"PAGEERROR: {e}"))
        await pg.goto(BASE + "?field=wise0855", wait_until="networkidle")
        await pg.wait_for_timeout(500)
        await pg.wait_for_function("window.__skytrace && window.__skytrace.FRAMES.length > 0", timeout=60000)
        info = await pg.evaluate("""() => { const s = window.__skytrace; return {
            frames: s.FRAMES.length, visits: s.VISITS.length, det: s.S.det, title: document.getElementById('fieldTitle').textContent,
            label: document.getElementById('frameLabel').textContent, share: document.getElementById('shareUrl').value,
            badge: document.getElementById('modeBadge').textContent, url: location.href,
            p2w: s.pix2world(44, 44), w2p: s.world2pix(...s.pix2world(10.3, 70.7)), g: s.F.meta.grid } }""")
        print(json.dumps(info, indent=1))
        print("blend:", await pg.inner_text("#blendNote"))
        await pg.screenshot(path=OUT + "shot_wise_visits.png", full_page=False)
        # modes
        for mode in ["band", "scan", "exp", "custom", "epoch"]:
            await pg.click(f"label[for=m-{mode}]")
            await pg.wait_for_timeout(300)
            r = await pg.evaluate("() => [window.__skytrace.FRAMES.length, document.getElementById('frameLabel').textContent, document.getElementById('frameSub').textContent]")
            print("mode", mode, r)
        # diff + rgb + overlays
        await pg.click("#diffToggle"); await pg.wait_for_timeout(300)
        for ov in ["#ovGaia", "#ovWise", "#ovFlags", "#ovMovers"]: await pg.click(ov)
        await pg.wait_for_timeout(300)
        await pg.screenshot(path=OUT + "shot_wise_diff.png")
        print("movers", await pg.evaluate("() => window.__skytrace.MOVERS.length"))
        # hover + click pin
        box = await pg.locator("#ovCanvas").bounding_box()
        await pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        await pg.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        print("hover:", (await pg.inner_text("#hoverReadout")).replace("\n", " | "))
        print("pin:", (await pg.inner_text("#pinBox")).replace("\n", " | ")[:120])
        print("url after pin:", pg.url)
        # coordinate entry: name, sexagesimal, decimal, bad
        for q in ["Barnard's Star", "17h57m48.5s +04d44m", "17 57 48.5 +04 46 07", "22:04:23.1 -56:48:02", "331.0962 -56.8005", "epsilon indi b", "R Dra", "12 34 56", "300 95", "hello"]:
            await pg.fill("#coordInput", q); await pg.press("#coordInput", "Enter"); await pg.wait_for_timeout(1500)
            print("input", repr(q), "->", await pg.inner_text("#coordMsg"), "| field:", await pg.evaluate("() => window.__skytrace.F.meta.key"))
        await pg.click("label[for=m-epoch]"); await pg.select_option("#detSel", "rgb"); await pg.wait_for_timeout(400)
        print("rdra visits:", await pg.evaluate("() => window.__skytrace.VISITS.map(v => v.idx.length)"))
        await pg.screenshot(path=OUT + "shot_rdra_rgb.png")
        # deep link round trip
        share = await pg.input_value("#shareUrl")
        print("share:", share)
        pg2 = await b.new_page(viewport={"width": 1500, "height": 1100})
        pg2.on("pageerror", lambda e: errs.append(f"PAGEERROR2: {e}"))
        await pg2.goto(share, wait_until="networkidle")
        await pg2.wait_for_function("window.__skytrace && window.__skytrace.FRAMES.length > 0", timeout=60000)
        print("deep link restored:", await pg2.evaluate("() => [window.__skytrace.F.meta.key, window.__skytrace.S.det, window.__skytrace.S.mode]"))
        # barnard default + spectrum tab
        await pg.click("#targetButtons button[data-key=barnard]"); await pg.wait_for_timeout(1500)
        await pg.click("#ovTarget"); await pg.click("#ovTarget")
        await pg.screenshot(path=OUT + "shot_barnard.png", full_page=True)
        await pg.click("button[data-bs-target='#tabLc']"); await pg.wait_for_timeout(500)
        await pg.click("#targetButtons button[data-key=epsindib]"); await pg.wait_for_timeout(1500)
        await pg.click("#diffToggle"); await pg.click("#ovMovers"); await pg.wait_for_timeout(400)
        await pg.click("button[data-bs-target='#tabMovers']"); await pg.wait_for_timeout(300)
        print("blend:", await pg.inner_text("#blendNote")); print("epsindib movers:", (await pg.inner_text("#moverList"))[:400])
        await pg.screenshot(path=OUT + "shot_epsindib.png", full_page=True)
        # play
        await pg.click("#playBtn"); await pg.wait_for_timeout(1500); f1 = await pg.evaluate("() => window.__skytrace.S.frame"); await pg.click("#playBtn")
        print("played to frame", f1)
        print("ERRORS:", errs if errs else "none")
        await b.close()
asyncio.run(main())
