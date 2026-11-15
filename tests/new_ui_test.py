"""Tests for: panel help, local search names, PNG/CSV export, image-source switcher."""
import asyncio, os, sys, csv, io, json
from playwright.async_api import async_playwright
BASE = sys.argv[1]
async def main():
    async with async_playwright() as p:
        # route external requests (IRSA HiPS tiles) through the workspace proxy; local server direct
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"], proxy={"server": os.environ.get("HTTPS_PROXY", "http://127.0.0.1:44423"), "bypass": "127.0.0.1,localhost"})
        ctx = await b.new_context(viewport={"width": 1500, "height": 1100}, accept_downloads=True, ignore_https_errors=True); pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append("PAGE " + str(e))); pg.on("console", lambda m: m.type == "error" and "api/" not in m.text and errs.append(m.text[:140]))
        await pg.goto(BASE + "?field=epsindib", wait_until="networkidle"); await pg.wait_for_timeout(2500)
        n = await pg.evaluate("document.querySelectorAll('.hud-help-btn').length"); print("help buttons:", n)
        await pg.click('#displayBtn'); await pg.wait_for_timeout(200)
        await pg.click('[data-help="display"] .hud-help-btn'); await pg.wait_for_timeout(200)
        print("display help open:", await pg.is_visible('[data-help="display"] .hud-help'), (await pg.inner_text('[data-help="display"] .hud-help'))[:90].replace("\n", " "))
        await pg.screenshot(path="/home/claude/scratch/help_open.png", clip={"x": 0, "y": 0, "width": 1500, "height": 1100})
        await pg.click('button[data-bs-target="#tabShare"]'); await pg.wait_for_timeout(300)
        async with pg.expect_download() as d: await pg.click("#saveCsvBtn")
        dl = await d.value; path = await dl.path(); txt = open(path).read()
        rows = [r for r in csv.reader(io.StringIO("\n".join(l for l in txt.splitlines() if not l.startswith("#"))))]
        meta_n = await pg.evaluate("window.__skytrace.F.meta.exposures.length")
        sx = [r for r in rows[1:] if r[0] == "SPHEREx"]; cat = [r for r in rows[1:] if r[0] != "SPHEREx"]
        print(f"CSV: {dl.suggested_filename}, header {rows[0][:6]}..., {len(sx)} SPHEREx rows (field has {meta_n}), catalogue rows {[r[0] for r in cat]}")
        e0 = await pg.evaluate("window.__skytrace.F.meta.exposures[0]"); r0 = sx[0]
        print("first row matches data:", r0[1] == e0["obs_id"] and float(r0[5]) == e0["wave"] and (r0[8] == "" if e0["flux_ujy"] is None else abs(float(r0[8]) - e0["flux_ujy"]) < 1e-6))
        async with pg.expect_download() as d: await pg.click("#saveImgBtn")
        dl = await d.value; p2 = await dl.path(); data = open(p2, "rb").read()
        print("PNG:", dl.suggested_filename, len(data), "bytes, PNG signature:", data[:8] == b"\x89PNG\r\n\x1a\n")
        open("/home/claude/scratch/export.png", "wb").write(data)
        for src in ("dss", "2mass", "wise"):
            await pg.click(f'label[for="src-{src}"]'); await pg.wait_for_timeout(7000)
            el = await pg.query_selector("#viewerWrap"); await el.screenshot(path=f"/home/claude/scratch/src_{src}.png")
            # Aladin draws into a WebGL canvas: read it back via a screenshot and count non-dark pixels
            from PIL import Image; im = Image.open(f"/home/claude/scratch/src_{src}.png").convert("L"); px = list(im.getdata())
            lit = sum(v > 40 for v in px) / len(px)
            print(f"source {src}: view visible {await pg.is_visible('#srcView')}, lit pixel fraction {lit:.2f} | note: {(await pg.inner_text('#srcNote'))[:90]}")
        print("aladin compare instance:", await pg.evaluate("!!(window.SkyAladin && window.SkyAladin.compareInstance)"))
        await pg.click('label[for="src-spherex"]'); await pg.wait_for_timeout(300)
        print("back to SPHEREx, source view hidden:", not await pg.is_visible("#srcView"))
        print("errors:", [e for e in errs if "ERR_TUNNEL" not in e and "Failed to fetch" not in e and "404" not in e] or "none")
        await b.close()
asyncio.run(main())
