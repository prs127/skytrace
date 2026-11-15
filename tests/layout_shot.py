"""Screenshot the console layout at several window sizes and check that nothing overflows the window
on desktop (each pane must scroll on its own) and that the page has no console errors."""
import asyncio, sys
from playwright.async_api import async_playwright
URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8090/'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for (w, h, tag) in [(1920, 1080, 'fhd'), (1440, 900, 'laptop'), (1280, 720, 'small'), (1024, 768, 'tablet'), (420, 900, 'phone')]:
            pg = await b.new_page(viewport={"width": w, "height": h}); errs = []
            pg.on("pageerror", lambda e: errs.append("PAGE " + str(e)))
            pg.on("console", lambda m: m.type == "error" and errs.append(m.text[:160]))
            await pg.goto(URL + ("" if URL.endswith(".html") else "app.html") + "?field=wise0855"); await pg.wait_for_timeout(5000)
            await pg.screenshot(path=f"/home/claude/scratch/layout_{tag}.png")
            info = await pg.evaluate("""() => { const d = document.documentElement;
              const r = (s) => { const e = document.querySelector(s); if (!e) return null; const b = e.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height), e.scrollHeight > e.clientHeight + 2]; };
              return { docH: d.scrollHeight, winH: innerHeight, docW: d.scrollWidth, winW: innerWidth,
                rail: r('.st-acc'), stage: r('.st-stage'), data: r('.st-data-body'), viewer: r('#viewerWrap'), cmd: r('.st-cmd') }; }""")
            print(tag, info, 'errors:', errs)
            await pg.close()
        await b.close()
asyncio.run(main())
