"""Dump what the browser displays (frame pixel values) for independent re-computation in Python."""
import asyncio, sys, json
from playwright.async_api import async_playwright
BASE, key, det, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(); await pg.goto(BASE + f"?field={key}&det={det}&flat=0", wait_until="networkidle"); await pg.wait_for_timeout(3000)
        d = await pg.evaluate("""(() => { const T = window.__skytrace, ex = T.F.meta.exposures;
            const fr = T.FRAMES.map(f => ({members: f.members.map(i => ex[i].obs_id + '|' + ex[i].det), img: Array.from(f.img).map(v => v === v ? v : null)}));
            return {S: {det: T.S.det, flat: T.S.flat, mode: T.S.mode}, grid: T.F.meta.grid, frames: fr}; })()""")
        json.dump(d, open(out, "w")); print(key, d["S"], len(d["frames"]), "frames", [len(f["members"]) for f in d["frames"]])
        await b.close()
asyncio.run(main())
