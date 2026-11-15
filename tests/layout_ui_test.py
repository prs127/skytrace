"""Console layout checks: rail hide/show (and the overlay canvas follows the new image size), every data tab
opens and shows content, the Atlas tab loads the SPHEREx cube and the IRSA-hosted surveys, help buttons work
inside sections and tabs, keyboard play still works. External requests go through the workspace proxy."""
import asyncio, os, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8090/'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"], proxy={"server": os.environ.get("HTTPS_PROXY", "http://127.0.0.1:44423"), "bypass": "127.0.0.1,localhost"})
        ctx = await b.new_context(viewport={"width": 1600, "height": 950}, ignore_https_errors=True); pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append("PAGE " + str(e))); pg.on("console", lambda m: m.type == "error" and errs.append(m.text[:160]))
        await pg.goto(BASE + "?field=barnard", wait_until="networkidle"); await pg.wait_for_timeout(2500)
        size = lambda: pg.evaluate("() => { const v = document.getElementById('viewerWrap').getBoundingClientRect(), o = document.getElementById('ovCanvas'); return [Math.round(v.width), o.width]; }")
        before = await size()
        await pg.click('#railToggle'); await pg.wait_for_timeout(600)
        after = await size()
        print("rail hidden:", await pg.evaluate("document.getElementById('console').classList.contains('rail-hidden')"), "| viewer px before/after", before, after,
              "| overlay canvas follows (within 2%):", abs(after[1] - after[0]) <= 0.02 * after[0])
        await pg.screenshot(path="/home/claude/scratch/layout_railhidden.png")
        await pg.click('#railShow'); await pg.wait_for_timeout(400)
        print("rail shown again:", not await pg.evaluate("document.getElementById('console').classList.contains('rail-hidden')"))
        for tab in ["tabLc", "tabExp", "tabMovers", "tabShare", "tabData", "tabSpec"]:
            await pg.click(f'button[data-bs-target="#{tab}"]'); await pg.wait_for_timeout(500)
            vis = await pg.is_visible(f"#{tab}"); txt = (await pg.inner_text(f"#{tab}"))[:70].replace("\n", " ")
            print(f"{tab}: visible {vis} | {txt}")
        print("exposure rows:", await pg.evaluate("document.querySelectorAll('#expTable tr').length"), "| tab count label:", await pg.inner_text("#expCount"))
        await pg.click('button[data-bs-target="#tabAladin"]'); await pg.wait_for_timeout(9000)
        print("atlas msg:", (await pg.inner_text("#aladinMsg"))[:110])
        await pg.screenshot(path="/home/claude/scratch/layout_atlas.png")
        await pg.select_option("#aladinSurvey", "allwise"); await pg.wait_for_timeout(7000)
        print("atlas msg (AllWISE):", (await pg.inner_text("#aladinMsg"))[:110])
        el = await pg.query_selector("#aladinDiv"); await el.screenshot(path="/home/claude/scratch/atlas_allwise.png")
        await pg.click('button[data-bs-target="#tabSpec"]'); await pg.wait_for_timeout(400)
        await pg.click('[data-help="spectrum"] > .hud-help-btn'); await pg.wait_for_timeout(200)
        print("spectrum help visible:", await pg.is_visible('[data-help="spectrum"] > .hud-help'))
        await pg.click('#displayBtn'); await pg.wait_for_timeout(300)
        await pg.click('[data-help="display"] > .hud-help-btn'); await pg.wait_for_timeout(300)
        print("display menu opens and its help shows:", await pg.is_visible('#stretchSel'), await pg.is_visible('[data-help="display"] .hud-help'))
        await pg.keyboard.press("Escape")
        f0 = await pg.evaluate("window.__skytrace.S.frame"); await pg.click("#viewerWrap"); await pg.keyboard.press("ArrowRight"); await pg.wait_for_timeout(300)
        print("arrow key steps frame:", f0, "->", await pg.evaluate("window.__skytrace.S.frame"))
        print("errors:", [e for e in errs if "Failed to load resource" not in e] or "none")
        await b.close()
asyncio.run(main())
