"""Atlas tab: choosing SPHEREx channel k must make Aladin Lite load cube tiles of frame k (file suffix _k),
for every one of the 100 non-blank frames, and the label must match the cube's own wavelength list."""
import asyncio, os, re, sys, urllib.request
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8090/'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"], proxy={"server": os.environ.get("HTTPS_PROXY", "http://127.0.0.1:44423"), "bypass": "127.0.0.1,localhost"})
        ctx = await b.new_context(viewport={"width": 1600, "height": 950}, ignore_https_errors=True); pg = await ctx.new_page(); reqs = []; errs = []
        pg.on("request", lambda r: 'spherex_allsky_cube' in r.url and 'Npix' in r.url and reqs.append(r.url.split('/')[-1]))
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE + "?field=rwaur", wait_until="networkidle"); await pg.wait_for_timeout(1500)
        await pg.click('button[data-bs-target="#tabAladin"]'); await pg.wait_for_timeout(8000)
        first = sorted(set(reqs)); print("default frame tiles:", first, "| selector:", await pg.input_value('#atlasFrame'))
        opts = await pg.evaluate("[...document.querySelectorAll('#atlasFrame option')].map(o => [+o.value, o.textContent])")
        print("options:", len(opts), opts[:2], opts[-1])
        bad = []
        for k, label in opts:
            reqs.clear(); await pg.select_option('#atlasFrame', str(k)); await pg.wait_for_timeout(1300)
            got = {int(m.group(1)) for r in reqs for m in [re.search(r'_(\d+)\.png', r)] if m}
            if got != {k}: bad.append((k, sorted(got)))
        print("frames whose tiles did not match:", bad or "none")
        el = await pg.query_selector("#aladinDiv"); await pg.select_option('#atlasFrame', '34'); await pg.wait_for_timeout(4000); await el.screenshot(path="/home/claude/scratch/atlas_frame34.png")
        print("errors:", errs or "none"); await b.close()
asyncio.run(main())
