"""The browser's moving-object finder must give the same answer as the Python reference (tests/movers_ref.py)
on the same data: the 6 real fields and the 6 injection-test fields (tests/movers_inject.py output).
Usage: python tests/movers_parity.py http://127.0.0.1:8091/ /path/to/data"""
import asyncio, json, math, sys, os
sys.path.insert(0, os.path.dirname(__file__)); import movers_ref as M
from playwright.async_api import async_playwright
BASE, DATA = sys.argv[1], sys.argv[2]
CASES = [('wise0855', 'lw'), ('epsindib', 'all'), ('barnard', 'all'), ('rwaur', 'all'), ('rdra', 'all'), ('m101', 'all')]
CASES += [(k + '_inj', d) for k, d in CASES]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 1500, "height": 950}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        bad = 0
        for key, det in CASES:
            await pg.goto(f"{BASE}?field={key}&det={det}"); await pg.wait_for_function("window.__skytrace && window.__skytrace.MOVER_INFO", timeout=60000)
            js = await pg.evaluate("window.__skytrace.MOVERS.map(m => ({ra: m.ra, dec: m.dec, pm: m.pm, epm: m.epm, sig: m.sig, n: m.n}))")
            info = await pg.evaluate("window.__skytrace.MOVER_INFO")
            py, pinfo = M.run(DATA, key, det, verbose=False)
            # pair them by position
            matched = 0; dpm = []
            for o in py:
                c = [j for j in js if math.hypot((j['ra'] - o['ra']) * math.cos(math.radians(o['dec'])), j['dec'] - o['dec']) * 3600 < 3]
                if c: matched += 1; dpm.append(abs(c[0]['pm'] - o['pm']))
            ok = matched == len(py) == len(js)
            bad += not ok
            print(f"{key:13s} det={det:3s} python {len(py)} movers, browser {len(js)}, matched {matched}, max |pm diff| {max(dpm) if dpm else 0:.3f}\"/yr | "
                  f"error floor a: py {pinfo['a']:.3f} js {info['a']:.3f} | {'OK' if ok else 'MISMATCH'}", flush=True)
        print('page errors:', errs or 'none'); print('MISMATCHES:', bad)
        await b.close()
asyncio.run(main())
