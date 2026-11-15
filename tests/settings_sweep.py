"""Settings sweep: drive every control like a user, then check the result against the data (not just 'no errors').
Run three passes on three different fields. Usage: python settings_sweep.py BASE_URL"""
import asyncio, sys, json, hashlib
from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8090/"
FIELDS = ["wise0855", "epsindib", "rwaur"]
CH = {c["ch"]: c for c in json.load(open("/home/claude/skytrace/frontend/data/channels.json"))["channels"]} \
    if isinstance(json.load(open("/home/claude/skytrace/frontend/data/channels.json")), dict) else \
    {c["ch"]: c for c in json.load(open("/home/claude/skytrace/frontend/data/channels.json"))}

JS_HELPERS = """
window.__set = (id, v) => { const e = document.getElementById(id); e.value = String(v); e.dispatchEvent(new Event('input', {bubbles: true})); e.dispatchEvent(new Event('change', {bubbles: true})); };
window.__chk = (id, on) => { const e = document.getElementById(id); if (e.checked !== !!on) e.click(); };
window.__mode = (m) => document.querySelector(`label[for="m-${m}"]`).click();
window.__hash = (id) => { const c = document.getElementById(id); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let h = 0; for (let i = 0; i < d.length; i += 97) h = (h * 31 + d[i]) >>> 0; return h; };
window.__allowed = (det) => det === 'all' || det === 'rgb' ? [1,2,3,4,5,6] : det === 'lw' ? [5,6] : det === 'sw' ? [1,2,3] : [+det];
"""

async def run_pass(pg, key, res):
    def ok(name, cond, info=""):
        res.append((key, name, bool(cond), info))
    await pg.goto(BASE + f"?field={key}", wait_until="networkidle"); await pg.wait_for_timeout(2500)
    await pg.evaluate(JS_HELPERS)
    sk = "window.__skytrace"

    # --- 1. visits partition the exposures; gaps and spans respect the sliders
    for win, span in ((30, 60), (10, 30), (90, 120)):
        await pg.evaluate(f"__set('winRange', {win}); __set('spanRange', {span});"); await pg.wait_for_timeout(300)
        r = await pg.evaluate(f"""(() => {{ const T = {sk}, ex = T.F.meta.exposures, V = T.VISITS;
            const all = V.flatMap(v => v.idx), uniq = new Set(all);
            let maxGapIn = 0, maxSpan = 0, minGapBetween = 1e9;
            V.forEach((v, k) => {{ const m = v.idx.map(i => ex[i].mjd).sort((a,b)=>a-b);
               for (let j = 1; j < m.length; j++) maxGapIn = Math.max(maxGapIn, m[j]-m[j-1]);
               maxSpan = Math.max(maxSpan, m[m.length-1]-m[0]);
               if (k) {{ const p = V[k-1].idx.map(i => ex[i].mjd); minGapBetween = Math.min(minGapBetween, m[0] - Math.max(...p)); }} }});
            return {{n: ex.length, all: all.length, uniq: uniq.size, maxGapIn, maxSpan, minGapBetween, nv: V.length, win: T.S.win, span: T.S.span}}; }})()""")
        ok(f"visits partition (win {win}, span {span})", r["all"] == r["n"] == r["uniq"], f"{r['nv']} visits")
        ok(f"gap inside visit <= win {win}", r["maxGapIn"] <= win + 1e-6, f"max {r['maxGapIn']:.2f} d")
        ok(f"visit length <= span {span}", r["maxSpan"] <= span + 1e-6, f"max {r['maxSpan']:.2f} d")
    await pg.evaluate("__set('winRange', 30); __set('spanRange', 60);"); await pg.wait_for_timeout(200)

    # --- 2. Visits mode + every detector choice
    await pg.evaluate("__mode('epoch')"); await pg.wait_for_timeout(200)
    for det in ["all", "rgb", "lw", "sw", "1", "2", "3", "4", "5", "6"]:
        await pg.evaluate(f"__set('detSel', '{det}')"); await pg.wait_for_timeout(250)
        r = await pg.evaluate(f"""(() => {{ const T = {sk}, ex = T.F.meta.exposures, al = __allowed('{det}');
            const bad = T.FRAMES.flatMap(f => f.members).filter(i => !al.includes(ex[i].det)).length;
            const expect = T.VISITS.filter(v => v.idx.some(i => al.includes(ex[i].det))).length;
            const want = T.VISITS.reduce((s, v) => s + v.idx.filter(i => al.includes(ex[i].det)).length, 0);
            const got = T.FRAMES.reduce((s, f) => s + f.members.length, 0);
            return {{bad, frames: T.FRAMES.length, expect, want, got}}; }})()""")
        ok(f"visits/det={det}: only allowed detectors", r["bad"] == 0, f"{r['frames']} frames")
        ok(f"visits/det={det}: frame count and members", r["frames"] == r["expect"] and r["got"] == r["want"], f"{r['got']}/{r['want']} exposures")
    await pg.evaluate("__set('detSel', 'all')"); await pg.wait_for_timeout(200)

    # --- 3. Same-band mode: channel and tolerance
    await pg.evaluate("__mode('band')"); await pg.wait_for_timeout(200)
    for band, tol in ((5, 0), (40, 2), (92, 1), (102, 0)):
        await pg.evaluate(f"__set('bandRange', {band}); __set('tolRange', {tol});"); await pg.wait_for_timeout(300)
        r = await pg.evaluate(f"""(() => {{ const T = {sk}, ex = T.F.meta.exposures;
            const bad = T.FRAMES.flatMap(f => f.members).filter(i => Math.abs(ex[i].band - {band}) > {tol}).length;
            const want = ex.filter(e => e.band && Math.abs(e.band - {band}) <= {tol}).length;
            const got = T.FRAMES.reduce((s, f) => s + f.members.length, 0);
            return {{bad, want, got, label: document.getElementById('bandLabel').textContent}}; }})()""")
        c = CH.get(band)
        ok(f"band {band}±{tol}: members in channel range", r["bad"] == 0 and r["got"] == r["want"], f"{r['got']} exposures")
        ok(f"band {band}: label shows official wavelength", c is not None and f"{c['wave']:.3f}" in r["label"], r["label"])

    # --- 4. Wavelength scan: ordered channels, one visit, members match channel
    await pg.evaluate("__mode('scan')"); await pg.wait_for_timeout(200)
    for k in (0, 1):
        await pg.evaluate(f"__set('scanEpoch', {k})"); await pg.wait_for_timeout(300)
        r = await pg.evaluate(f"""(() => {{ const T = {sk}, ex = T.F.meta.exposures, v = T.VISITS[{k}];
            const bands = T.FRAMES.map(f => f.band); const asc = bands.every((b, i) => !i || b > bands[i-1]);
            const wrongBand = T.FRAMES.filter(f => f.members.some(i => ex[i].band !== f.band)).length;
            const outside = T.FRAMES.flatMap(f => f.members).filter(i => !v.idx.includes(i)).length;
            const waves = T.FRAMES.map(f => f.members.map(i => ex[i].wave)).map(a => a.reduce((s,x)=>s+x,0)/a.length);
            const waveAsc = waves.every((w, i) => !i || w >= waves[i-1] - 0.02);
            return {{n: T.FRAMES.length, asc, wrongBand, outside, waveAsc}}; }})()""")
        ok(f"λ scan visit {k+1}: channels ascending, correct members", r["asc"] and r["wrongBand"] == 0 and r["outside"] == 0, f"{r['n']} channels")
        ok(f"λ scan visit {k+1}: measured wavelength increases", r["waveAsc"])

    # --- 5. Every-exposure mode: one exposure per frame, time order
    await pg.evaluate("__mode('exp')"); await pg.wait_for_timeout(400)
    r = await pg.evaluate(f"""(() => {{ const T = {sk}, ex = T.F.meta.exposures; const t = T.FRAMES.map(f => ex[f.members[0]].mjd);
        return {{n: T.FRAMES.length, total: ex.length, single: T.FRAMES.every(f => f.members.length === 1), sorted: t.every((x, i) => !i || x >= t[i-1])}}; }})()""")
    ok("exposures mode: 1 per frame, time-ordered, all present", r["single"] and r["sorted"] and r["n"] == r["total"], f"{r['n']} frames")

    # --- 6. Difference images equal frame minus reference (all three references)
    await pg.evaluate("__mode('epoch'); __set('detSel', 'lw');"); await pg.wait_for_timeout(300)
    await pg.evaluate("__chk('diffToggle', false)"); await pg.wait_for_timeout(300)
    await pg.evaluate(f"window.__raw = {sk}.FRAMES.map(f => Array.from(f.img))")
    for ref in ("first", "prev", "others"):
        await pg.evaluate(f"__set('diffRef', '{ref}'); __chk('diffToggle', true);"); await pg.wait_for_timeout(400)
        r = await pg.evaluate(f"""(() => {{ const T = {sk}, R = window.__raw, n = R.length; let worst = 0, cnt = 0;
            T.FRAMES.forEach((f, k) => {{ let ref;
              if ('{ref}' === 'first') ref = R[k === 0 ? 1 : 0];
              else if ('{ref}' === 'prev') ref = R[k === 0 ? 1 : k - 1];
              else {{ ref = R[0].map((_, p) => {{ let s = 0, c = 0; R.forEach((a, j) => {{ if (j !== k && a[p] === a[p]) {{ s += a[p]; c++; }} }}); return c ? s / c : NaN; }}); }}
              for (let p = 0; p < f.img.length; p++) {{ const want = R[k][p] - ref[p]; if (want === want && f.img[p] === f.img[p]) {{ worst = Math.max(worst, Math.abs(f.img[p] - want)); cnt++; }} }} }});
            return {{worst, cnt, n}}; }})()""")
        ok(f"difference (minus {ref}) = frame − reference", r["worst"] < 1e-4 and r["cnt"] > 0, f"max error {r['worst']:.1e} over {r['cnt']} px")
        await pg.evaluate("__chk('diffToggle', false)"); await pg.wait_for_timeout(200)

    # --- 7. Custom A − B equals visit 1 − visit 2 (same detectors)
    await pg.evaluate(f"window.__v = {sk}.FRAMES.map(f => Array.from(f.img))")
    await pg.evaluate("__mode('custom')"); await pg.wait_for_timeout(300)
    await pg.evaluate(f"(() => {{ const T = {sk}; T.S.A = '0'; T.S.B = '1'; }})()")
    await pg.evaluate("__set('detSel', 'lw')"); await pg.wait_for_timeout(400)
    r = await pg.evaluate(f"""(() => {{ const T = {sk}, f = T.FRAMES[0], a = window.__v[0], b = window.__v[1]; let worst = 0, c = 0;
        for (let p = 0; p < f.img.length; p++) {{ const w = a[p] - b[p]; if (w === w && f.img[p] === f.img[p]) {{ worst = Math.max(worst, Math.abs(f.img[p] - w)); c++; }} }}
        return {{worst, c, label: f.label}}; }})()""")
    ok("custom A−B = visit 1 − visit 2", r["worst"] < 1e-4 and r["c"] > 0, f"{r['label']}: max error {r['worst']:.1e}")
    await pg.evaluate("__mode('epoch'); __set('detSel', 'all');"); await pg.wait_for_timeout(300)

    # --- 8. Display settings change the picture and the shareable URL, and undo cleanly
    base = await pg.evaluate("__hash('imgCanvas')")
    for ctl, val, back, url_key in (("stretchSel", "linear", "asinh", "stretch"), ("cmapSel", "inferno", "gray", "cmap"),
                                    ("loRange", 10, 1, "lo"), ("hiRange", 95, 99.5, "hi"), ("fovSel", "4", "9.1", "fov")):
        await pg.evaluate(f"__set('{ctl}', '{val}')"); await pg.wait_for_timeout(300)
        h = await pg.evaluate("__hash('imgCanvas')"); url = await pg.input_value("#shareUrl")
        ok(f"display {ctl}={val} changes image and URL", h != base and f"{url_key}=" in url)
        await pg.evaluate(f"__set('{ctl}', '{back}')"); await pg.wait_for_timeout(300)
        ok(f"display {ctl} back to {back} restores image", await pg.evaluate("__hash('imgCanvas')") == base)
    for tog in ("invToggle", "flatToggle", "lockScale"):
        st0 = await pg.evaluate(f"document.getElementById('{tog}').checked")
        await pg.evaluate(f"__chk('{tog}', {str(not st0).lower()})"); await pg.wait_for_timeout(300)
        h = await pg.evaluate("__hash('imgCanvas')")
        await pg.evaluate(f"__chk('{tog}', {str(st0).lower()})"); await pg.wait_for_timeout(300)
        ok(f"toggle {tog} changes image and restores", h != base and await pg.evaluate("__hash('imgCanvas')") == base)
    await pg.evaluate("__chk('smoothToggle', true)"); sm = await pg.evaluate("document.getElementById('imgCanvas').classList.contains('smooth')")
    await pg.evaluate("__chk('smoothToggle', false)"); ok("smooth pixels toggles smoothing", sm)

    # --- 9. Overlays each draw something
    # flags: test on the single exposure with the most flagged pixels (visit stacks use a majority rule)
    await pg.evaluate("__mode('exp')"); await pg.wait_for_timeout(400)
    kf = await pg.evaluate(f"""(() => {{ const T = {sk}; let best = 0, bn = -1; T.FRAMES.forEach((f, k) => {{ let n = 0; for (const c of f.cat) if (c & 7) n++; if (n > bn) {{ bn = n; best = k; }} }}); return [best, bn]; }})()""")
    await pg.evaluate(f"__set('frameRange', {kf[0]})"); await pg.wait_for_timeout(300)
    h0 = await pg.evaluate("__hash('ovCanvas')"); await pg.evaluate("__chk('ovFlags', true)"); await pg.wait_for_timeout(250)
    h1 = await pg.evaluate("__hash('ovCanvas')"); await pg.evaluate("__chk('ovFlags', false)"); await pg.wait_for_timeout(250)
    ok("overlay ovFlags draws flagged pixels", (h1 != h0) == (kf[1] > 0) and await pg.evaluate("__hash('ovCanvas')") == h0, f"{kf[1]} flagged px in that exposure")
    await pg.evaluate("__mode('epoch')"); await pg.wait_for_timeout(400)
    ov0 = await pg.evaluate("__hash('ovCanvas')")
    for o in ("ovGaia", "ovWise", "ovTmass", "ovCompass", "ovTarget"):
        st0 = await pg.evaluate(f"document.getElementById('{o}').checked")
        await pg.evaluate(f"__chk('{o}', {str(not st0).lower()})"); await pg.wait_for_timeout(250)
        h = await pg.evaluate("__hash('ovCanvas')")
        await pg.evaluate(f"__chk('{o}', {str(st0).lower()})"); await pg.wait_for_timeout(250)
        ok(f"overlay {o} toggles drawing", h != ov0 and await pg.evaluate("__hash('ovCanvas')") == ov0)

    # --- 10. Frame slider, step buttons and play speed
    n = await pg.evaluate(f"{sk}.FRAMES.length")
    await pg.evaluate(f"__set('frameRange', {n - 1})"); await pg.wait_for_timeout(200)
    ok("frame slider selects the frame", await pg.evaluate(f"{sk}.S.frame") == n - 1)
    await pg.click("#nextBtn"); await pg.wait_for_timeout(150)
    ok("next button wraps to first frame", await pg.evaluate(f"{sk}.S.frame") == 0)
    await pg.evaluate("__mode('exp')"); await pg.wait_for_timeout(400)
    await pg.evaluate("__set('speedRange', 2080 - 200)"); await pg.wait_for_timeout(100)
    f0 = await pg.evaluate(f"{sk}.S.frame"); await pg.click("#playBtn"); await pg.wait_for_timeout(2100); await pg.click("#playBtn")
    f1 = await pg.evaluate(f"{sk}.S.frame"); adv = (f1 - f0) % await pg.evaluate(f"{sk}.FRAMES.length")
    ok("play at 200 ms/frame advances ~10 frames in 2.1 s", 8 <= adv <= 11, f"advanced {adv}")

    # --- 11. Share link restores the exact view
    await pg.evaluate("__mode('band'); __set('detSel', 'all'); __set('bandRange', 77); __set('tolRange', 1); __set('cmapSel', 'inferno'); __set('fovSel', '6');"); await pg.wait_for_timeout(400)
    url = await pg.input_value("#shareUrl"); want = await pg.evaluate(f"JSON.stringify({sk}.S)")
    url = url.replace(url.split('?')[0], pg.url.split('?')[0])   # same link, served by the local test server
    p2 = await pg.context.new_page(); await p2.goto(url, wait_until="networkidle"); await p2.wait_for_timeout(2500)
    got = await p2.evaluate(f"JSON.stringify({sk}.S)"); await p2.close()
    w, g = json.loads(want), json.loads(got)
    diff = {k: (w[k], g.get(k)) for k in ("mode", "band", "tol", "cmap", "fov", "det", "win", "span", "stretch") if str(w[k]) != str(g.get(k))}
    ok("share link restores mode/channel/display", not diff, str(diff) if diff else url.split('?')[1][:90])

    # --- 12. Spectrum points equal the clean measurements in the data
    await pg.click('[data-bs-target="#tabSpec"]'); await pg.wait_for_timeout(300)
    r = await pg.evaluate(f"""(() => {{ const T = {sk}, ex = T.F.meta.exposures, d = document.getElementById('specPlot').data;
        const plotted = d.filter(t => /^V\\d/.test(t.name)).reduce((s, t) => s + t.x.length, 0);
        const clean = ex.filter(e => e.flux_ujy !== null && e.wave && !(e.phot_flags && e.phot_flags.length)).length;
        const cat = d.filter(t => /2MASS|WISE/.test(t.name)).reduce((s, t) => s + t.x.length, 0);
        const sed = (T.F.meta.sed || []).filter(p => p.flux_ujy != null).length;
        return {{plotted, clean, cat, sed}}; }})()""")
    ok("spectrum plots every clean SPHEREx point", r["plotted"] == r["clean"], f"{r['plotted']}/{r['clean']}")
    ok("spectrum plots every matched 2MASS/WISE point", r["cat"] == r["sed"], f"{r['cat']}/{r['sed']}")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        ctx = await b.new_context(viewport={"width": 1500, "height": 1100}); pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append("PAGE " + str(e)))
        pg.on("console", lambda m: m.type == "error" and "api/" not in m.text and errs.append(m.text[:140]))
        res = []
        for k in FIELDS:
            await run_pass(pg, k, res)
        bad = [r for r in res if not r[2]]
        for k in FIELDS:
            rr = [r for r in res if r[0] == k]
            print(f"PASS {FIELDS.index(k)+1} ({k}): {sum(r[2] for r in rr)}/{len(rr)} checks passed")
        for r in bad: print("  FAIL", r)
        print("sample:", [f"{r[1]} [{r[3]}]" for r in res if r[0] == FIELDS[0]][:4])
        print("ERRORS:", errs or "none")
        await b.close()
asyncio.run(main())
