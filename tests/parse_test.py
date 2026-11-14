"""Coordinate input parser: every accepted format must give the same position (WISE 0855 challenge coordinates)."""
import asyncio, sys
from playwright.async_api import async_playwright
CASES = ["08h55m10.831s -07d14m42.53s", "08:55:10.831 -07:14:42.53", "8 55 10.831 -7 14 42.53", "133.795129 -7.245147",
         "133.795129, -7.245147", "08h55m10.831s, -07d14m42.53s"]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]); pg = await b.new_page()
        await pg.goto(sys.argv[1], wait_until="networkidle"); await pg.wait_for_timeout(1500)
        ok = 0
        for c in CASES:
            r = await pg.evaluate(f"window.__skytrace.parseInput({c!r})")
            good = r and not r.get("error") and abs(r["ra"] - 133.795129) < 2e-5 and abs(r["dec"] + 7.245147) < 2e-5
            ok += bool(good); print(("OK  " if good else "FAIL"), repr(c), "->", r)
        r = await pg.evaluate("window.__skytrace.parseInput('Barnard')"); print("name 'Barnard' ->", r)
        for bad in ("400 10", "12h 95d", "hello world"):
            print("reject", repr(bad), "->", await pg.evaluate(f"window.__skytrace.parseInput({bad!r})"))
        print(f"{ok}/{len(CASES)} coordinate formats give the same position"); await b.close()
asyncio.run(main())
