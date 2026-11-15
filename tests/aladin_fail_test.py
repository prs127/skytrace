"""If NASA IRSA's HiPS server does not answer, the comparison view must show a message and must NOT fall back to
Aladin Lite's default CDS survey (which, while CDS is down, re-queries CDS many times a second)."""
import asyncio, os, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8090/app.html'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"], proxy={"server": os.environ.get("HTTPS_PROXY", ""), "bypass": "127.0.0.1,localhost"})
        ctx = await b.new_context(viewport={"width": 1500, "height": 950}, ignore_https_errors=True); pg = await ctx.new_page()
        cds = []; await pg.route("**/irsa.ipac.caltech.edu/data/hips/**", lambda r: r.abort())
        pg.on("request", lambda r: 'unistra.fr' in r.url and cds.append(r.url))
        await pg.goto(BASE + "?field=epsindib", wait_until="networkidle"); await pg.wait_for_timeout(1500)
        await pg.click('label[for="src-dss"]'); await pg.wait_for_timeout(6000)
        print("IRSA blocked: requests to CDS in 6 s:", len(cds), "| note:", (await pg.inner_text('#srcNote'))[:120])
        await pg.click('button[data-bs-target="#tabAladin"]'); await pg.wait_for_timeout(5000)
        print("atlas with IRSA blocked: requests to CDS:", len(cds), "| message:", (await pg.inner_text('#aladinMsg'))[:120])
        print("PASS" if len(cds) == 0 else "FAIL"); await b.close()
asyncio.run(main())
