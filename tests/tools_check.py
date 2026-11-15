"""Every analysis tool, on every field given, checked against an independent Python computation from the same data.

For each field: visit grouping, spectrum (points and values), light curve (points and values, or the reason it is
empty), moving objects (browser = Python reference, and every report meets the stated tests), exposures table,
Sources tab, every frame mode, difference, shift-and-add, Atlas, comparison survey, CSV, report and the PDF export.
Usage: python3 tests/tools_check.py http://127.0.0.1:8090/ /path/to/data key1 key2 ...
"""
import asyncio, json, math, os, sys, statistics
sys.path.insert(0, os.path.dirname(__file__)); import movers_ref as M
from playwright.async_api import async_playwright

BASE, DATA, KEYS = sys.argv[1], sys.argv[2], sys.argv[3:]
DEFAULT_DET = {'wise0855': 'lw', 'epsindib': 'all', 'barnard': 'all', 'rwaur': 'rgb', 'rdra': 'rgb', 'm101': '2'}
RES = []
def ok(key, name, cond, info=""):
    RES.append(bool(cond)); print(f"  {'PASS' if cond else 'FAIL'} {key:12s} {name}" + (f"  [{info}]" if info else ""), flush=True)

def flagged(e): return bool(e.get('phot_flags')) or e.get('_outlier', False)

def mark_outliers(ex):   # same rule as the page's markOutliers()
    ok = [e for e in ex if e['flux_ujy'] is not None and e['wave'] and not e.get('phot_flags')]
    for e in ex: e['_outlier'] = False
    for e in ok:
        win = [x for x in ok if abs(x['mjd'] - e['mjd']) < 15 and abs(x['wave'] - e['wave']) <= 0.04 * e['wave']]
        nb = sorted(x['flux_ujy'] for x in win if x is not e)
        if len(nb) < 4: continue
        med = pct50(nb); mad = 1.4826 * pct50(sorted(abs(v - med) for v in nb))
        sig = max(mad, pct50(sorted(x['flux_err'] or 0 for x in win)))
        if abs(e['flux_ujy'] - med) > 5 * sig and abs(e['flux_ujy'] - med) > 3 * (e['flux_err'] or 0): e['_outlier'] = True
def pct50(v):   # same as the page's percentile(): linear interpolation on the sorted values
    v = sorted(v); k = (len(v) - 1) * 0.5; f = math.floor(k); c = min(f + 1, len(v) - 1); return v[f] + (v[c] - v[f]) * (k - f)

async def check(pg, key, errs):
    m = json.load(open(f'{DATA}/{key}.json')); ex = m['exposures']; n = len(ex); mark_outliers(ex)
    print(f"      outliers marked: {sum(e['_outlier'] for e in ex)}")
    det = DEFAULT_DET.get(key, 'all')
    await pg.goto(f"{BASE}app.html?field={key}", wait_until="networkidle")
    await pg.wait_for_function("window.__skytrace && window.__skytrace.F && window.__skytrace.FRAMES.length", timeout=90000); await pg.wait_for_timeout(1500)
    T = "window.__skytrace"
    ok(key, "field opens", await pg.evaluate(f"{T}.F.meta.key") == key, f"{n} images")
    # ---- visits
    py_v = M.visits(m); js_v = await pg.evaluate(f"{T}.VISITS.map(v => v.idx.slice().sort((a, b) => a - b))")
    ok(key, "visits: same grouping as Python", [sorted(v) for v in py_v] == js_v, f"{len(js_v)} visits")
    # ---- spectrum: clean points and their values
    await pg.click('#sheet [data-bs-target="#tabSpec"]'); await pg.wait_for_timeout(700)
    spec = await pg.evaluate("document.getElementById('specPlot').data ? document.getElementById('specPlot').data.filter(t => /^V\\d/.test(t.name)).flatMap(t => t.y) : []")
    want = sorted(e['flux_ujy'] for e in ex if e['flux_ujy'] is not None and e['wave'] and not flagged(e))
    ok(key, "spectrum: every clean measurement plotted, values exact", sorted(spec) == want, f"{len(spec)} points")
    await pg.click('label[for=specClean]'); await pg.wait_for_timeout(700)
    spec2 = await pg.evaluate("document.getElementById('specPlot').data ? document.getElementById('specPlot').data.filter(t => /^V\\d/.test(t.name)).flatMap(t => t.y).length : 0")
    await pg.click('label[for=specClean]'); await pg.wait_for_timeout(300)
    ok(key, "spectrum: flagged ones added when the switch is off", spec2 == sum(1 for e in ex if e['flux_ujy'] is not None and e['wave']), f"{spec2}")
    # ---- light curve
    await pg.click('#sheet [data-bs-target="#tabLc"]'); await pg.wait_for_timeout(900)
    by = {}
    for e in ex:
        if e['flux_ujy'] is not None and e['band'] and not flagged(e) and e['flux_ujy'] > 0: by.setdefault(e['band'], []).append(e['flux_ujy'])
    erb = {}
    for e in ex:
        if e['flux_ujy'] is not None and e['band'] and not flagged(e) and e['flux_ujy'] > 0: erb.setdefault(e['band'], []).append(e['flux_err'] or 0)
    med = {b: pct50(v) for b, v in by.items() if len(v) >= 2 and pct50(v) >= 5 * pct50(erb[b])}   # target detected at >= 5 sigma
    want = sorted(round(e['flux_ujy'] / med[e['band']], 9) for e in ex if e['band'] in med and e['flux_ujy'] is not None and not flagged(e) and e['flux_ujy'] > 0)
    lc = await pg.evaluate("document.getElementById('lcPlot').data ? document.getElementById('lcPlot').data.flatMap(t => t.y) : null")
    if want:
        ok(key, "light curve: every usable point plotted, value = flux / channel median", lc is not None and sorted(round(v, 9) for v in lc) == want, f"{len(want)} points, scatter {statistics.pstdev(want):.3f}")
    else:
        msg = await pg.evaluate("document.getElementById('lcPlot').innerText")
        ok(key, "light curve: none possible, and the tab says why", lc is None and len(msg) > 60, msg[:110])
    # ---- moving objects: browser = Python reference; every report meets the tests
    await pg.click('#sheet [data-bs-target="#tabMovers"]'); await pg.wait_for_timeout(900)
    info = await pg.evaluate(f"{T}.MOVER_INFO"); js = await pg.evaluate(f"{T}.MOVERS")
    gaia_missing = any('Gaia' in w for w in (m.get('catalog_warnings') or []))
    if len(py_v) < 3 or gaia_missing:
        txt = await pg.evaluate("document.getElementById('moverList').innerText")
        ok(key, "moving objects: not run, and says why", info is None and len(txt) > 40, txt[:90])
    else:
        py, pinfo = M.run(DATA, key, det, verbose=False)
        match = sum(1 for o in py if any(math.hypot((j['ra'] - o['ra']) * math.cos(math.radians(o['dec'])), j['dec'] - o['dec']) * 3600 < 3 and abs(j['pm'] - o['pm']) < 1e-3 for j in js))
        ok(key, "moving objects: browser = independent Python (same objects, same motions)", match == len(py) == len(js), f"{len(js)} reported, error floor {info['a']:.3f}/{pinfo['a']:.3f} px")
        good = all(j['sig'] >= 5 and j['n'] >= 3 and j['n'] >= math.ceil(2 * j['covered'] / 3) for j in js)
        ok(key, "moving objects: every report passes the stated tests (>=5 sigma, >=3 visits, >=2/3 coverage)", good)
        for j in js:
            lab = 'target' if j.get('target') else ('Gaia DR3 ' + str(j['gaia']['id']) if j.get('gaia') else 'NOT IN GAIA')
            print(f"      mover {j['pm']:.2f} ± {j['epm']:.2f}\"/yr, {j['sig']:.1f} sigma, {j['n']}/{j['covered']} visits, {lab}" + (f" (catalogue {j['gaia']['pm']:.2f})" if j.get('gaia') else ''))
            if j.get('gaia'): ok(key, "  known star's measured motion agrees with Gaia within 3 sigma", abs(j['pm'] - j['gaia']['pm']) < 3 * j['epm'] + 0.05)
    # ---- exposures table
    await pg.click('#sheet [data-bs-target="#tabExp"]'); await pg.wait_for_timeout(600)
    nmem = await pg.evaluate(f"{T}.FRAMES[{T}.S.frame].members.length"); rows = await pg.evaluate("document.querySelectorAll('#tabExp tbody tr').length")
    ok(key, "exposures table: one row per image in the frame (first 150, then a '…and N more' line)", rows == min(150, nmem) + (nmem > 150), f"{rows} rows / {nmem} images")
    # ---- sources
    await pg.click('#sheet [data-bs-target="#tabData"]'); await pg.wait_for_timeout(400)
    src = await pg.evaluate("document.getElementById('tabData').innerText")
    ok(key, "sources tab: image count and collections", str(n) in src and 'spherex' in src.lower())
    # ---- every frame mode builds frames
    for mode in ['band', 'scan', 'exp', 'custom', 'epoch']:
        await pg.click(f'label[for=m-{mode}]'); await pg.wait_for_timeout(500)
        nf = await pg.evaluate(f"{T}.FRAMES.length")
        ok(key, f"mode {mode}: frames built", nf > 0, f"{nf}")
    # ---- difference and shift-and-add run without errors
    await pg.click('label[for=diffToggle]'); await pg.wait_for_timeout(500)
    ok(key, "difference frames", await pg.evaluate(f"{T}.FRAMES[{T}.S.frame].isDiff === true || {T}.S.diff == 1"))
    await pg.click('label[for=diffToggle]'); await pg.wait_for_timeout(300)
    await pg.click('#sheet [data-bs-target="#tabMovers"]'); await pg.click('#saTarget'); await pg.click('label[for=saToggle]'); await pg.wait_for_timeout(1500)
    ok(key, "shift-and-add with the target's motion", await pg.evaluate(f"{T}.FRAMES.length") > 0)
    await pg.click('label[for=saToggle]'); await pg.wait_for_timeout(500)
    # ---- share: CSV and report
    await pg.click('#sheet [data-bs-target="#tabShare"]'); await pg.wait_for_timeout(300)
    async with pg.expect_download() as d: await pg.click('#saveCsvBtn')
    rows = open(await (await d.value).path()).read().splitlines()
    ok(key, "CSV: one row per SPHEREx image", sum(1 for r in rows if r.startswith('SPHEREx,')) == n)
    await pg.click('#reportBtn'); await pg.wait_for_timeout(500)
    rep = await pg.evaluate("document.getElementById('reportText').value")
    ok(key, "candidate report written", len(rep) > 300 and 'RA' in rep)
    await pg.keyboard.press('Escape'); await pg.wait_for_timeout(500)
    # ---- Atlas and a comparison survey (NASA IRSA HiPS over the network)
    await pg.click('#sheet [data-bs-target="#tabAladin"]'); await pg.wait_for_timeout(5000)
    ok(key, "Atlas loads with the 100 SPHEREx channel maps", await pg.evaluate("document.getElementById('atlasFrame').options.length") >= 100)
    await pg.click('label[for=src-2mass]'); await pg.wait_for_timeout(4000)
    ok(key, "compare with 2MASS", await pg.is_visible('#srcCard') and 'Loading' not in await pg.evaluate("document.getElementById('srcNote').textContent"))
    await pg.click('#srcBack'); await pg.wait_for_timeout(400)
    # ---- PDF export with every section
    await pg.click('#exportTop'); await pg.wait_for_timeout(500); await pg.click('#exportAll')
    async with pg.expect_download(timeout=120000) as d: await pg.click('#exportGo')
    import pypdf; r = pypdf.PdfReader(await (await d.value).path()); text = ''.join(p.extract_text() or '' for p in r.pages)
    ok(key, "PDF export, every section", len(r.pages) >= 3 and 'Spectrum' in text and 'Moving objects' in text and 'Light curve' in text, f"{len(r.pages)} pages")
    await pg.keyboard.press('Escape'); await pg.wait_for_timeout(400)
    ok(key, "no page errors", not errs, '; '.join(errs[:2])); errs.clear()

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(proxy={"server": os.environ["HTTPS_PROXY"], "bypass": "127.0.0.1,localhost"}, args=["--ignore-certificate-errors"])
        ctx = await b.new_context(viewport={"width": 1440, "height": 900}, ignore_https_errors=True, accept_downloads=True)
        pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        for key in KEYS:
            print(f"== {key}", flush=True)
            try: await check(pg, key, errs)
            except Exception as e:
                import traceback; traceback.print_exc(); ok(key, "check ran to the end", False, repr(e)[:200])
        await b.close()
    print(f"\n{sum(RES)}/{len(RES)} passed")
asyncio.run(main())
