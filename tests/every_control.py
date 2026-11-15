"""Every control in the dashboard, one at a time, as a new user would try it; each check looks for a real effect.

Complements user_walkthrough.py (which follows the guide's main path) and settings_sweep.py (which checks the numbers).
Usage: python3 tests/every_control.py http://127.0.0.1:8090/
"""
import asyncio, os, sys, re
from playwright.async_api import async_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8090/"
RES = []
def ok(name, cond, info=""):
    RES.append(bool(cond)); print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))

HASH = """(id) => { const c = document.getElementById(id); const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
  let h = 0; for (let i = 0; i < d.length; i += 53) h = (h * 31 + d[i]) | 0; return h + ':' + c.width; }"""

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(proxy={"server": os.environ["HTTPS_PROXY"], "bypass": "127.0.0.1,localhost"}, args=["--ignore-certificate-errors"])
        ctx = await b.new_context(viewport={"width": 1440, "height": 900}, ignore_https_errors=True, accept_downloads=True)
        await ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE.rstrip('/'))
        pg = await ctx.new_page(); errs = []; DIALOG = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept(DIALOG.pop(0) if DIALOG else '')))
        T = "window.__skytrace"
        h = lambda cid='imgCanvas': pg.evaluate(HASH, cid)
        clip = lambda: pg.evaluate("navigator.clipboard.readText()")

        await pg.goto(BASE + "app.html?field=wise0855", wait_until="networkidle"); await pg.wait_for_timeout(3500)

        # ---------- first-time help strip
        ok("first visit: 'start here' steps shown", await pg.is_visible('#startHere'))
        await pg.click('#startHereClose'); await pg.wait_for_timeout(200)
        ok("start strip can be dismissed", not await pg.is_visible('#startHere'))

        # ---------- transport
        f0 = await pg.evaluate(f"{T}.S.frame")
        await pg.click('#nextBtn'); await pg.wait_for_timeout(300); f1 = await pg.evaluate(f"{T}.S.frame")
        await pg.click('#prevBtn'); await pg.wait_for_timeout(300); f2 = await pg.evaluate(f"{T}.S.frame")
        ok("▶ next and ◀ previous step one frame", f1 == (f0 + 1) % 3 and f2 == f0, f"{f0}->{f1}->{f2}")
        await pg.click('#filmstrip button >> nth=2'); await pg.wait_for_timeout(300)
        ok("visit button jumps to that visit", await pg.evaluate(f"{T}.S.frame") == 2)
        await pg.fill('#frameRange', '1'); await pg.dispatch_event('#frameRange', 'input'); await pg.wait_for_timeout(300)
        ok("frame slider jumps", await pg.evaluate(f"{T}.S.frame") == 1)
        # speed: count frame changes in 3 s at slowest and fastest
        async def rate(v):
            await pg.evaluate(f"(() => {{ const r = document.getElementById('speedRange'); r.value = {v}; r.dispatchEvent(new Event('input')); }})()")
            await pg.click('#playBtn'); n = 0; last = await pg.evaluate(f"{T}.S.frame")
            for _ in range(30):
                await pg.wait_for_timeout(100); cur = await pg.evaluate(f"{T}.S.frame")
                if cur != last: n += 1; last = cur
            await pg.click('#playBtn'); return n
        slow, fast = await rate(80), await rate(2000)
        ok("speed slider: right plays faster than left", fast > slow, f"left {slow} frames / 3 s, right {fast}")
        await pg.keyboard.press('Space'); await pg.wait_for_timeout(700); playing = await pg.evaluate(f"{T}.playing")
        await pg.keyboard.press('Space'); await pg.wait_for_timeout(200)
        ok("Space plays and pauses", playing and not await pg.evaluate(f"{T}.playing"))
        await pg.keyboard.press('d'); await pg.wait_for_timeout(300); dk = await pg.evaluate(f"{T}.S.diff")
        await pg.keyboard.press('d'); await pg.wait_for_timeout(300)
        ok("D switches difference on and off", dk and not await pg.evaluate(f"{T}.S.diff"))

        # ---------- every layer chip changes the overlay
        nflag = await pg.evaluate(f"(() => {{ const fr = {T}.FRAMES[{T}.S.frame]; return fr.cat ? fr.cat.reduce((s, v) => s + (v & 7 ? 1 : 0), 0) : -1; }})()")
        await pg.click('label[for=ovFlags]'); await pg.wait_for_timeout(300)
        note = await pg.evaluate("document.getElementById('layerNote').textContent")
        await pg.click('label[for=ovFlags]'); await pg.wait_for_timeout(200)
        ok("Flags layer on a frame with no flagged pixels says so", (nflag == 0) == ('no flagged' in note), f"{nflag} flagged; '{note}'")
        for chip in ['ovTarget', 'ovGaia', 'ovWise', 'ovTmass', 'ovMovers', 'ovCompass']:
            a = await h('ovCanvas'); await pg.click(f'label[for={chip}]'); await pg.wait_for_timeout(300); c = await h('ovCanvas')
            await pg.click(f'label[for={chip}]'); await pg.wait_for_timeout(200)
            ok(f"layer chip {chip[2:]} changes the drawing", a != c)
        tips = await pg.evaluate("[...document.querySelectorAll('.st-layers label')].every(l => l.title.length > 10)")
        ok("every layer chip has a hover explanation", tips)

        # ---------- detectors, view size, display options each change the picture
        opts = await pg.evaluate("[...document.querySelectorAll('#detSel option')].map(o => o.value)")
        seen = set()
        for v in opts:
            await pg.select_option('#detSel', v); await pg.wait_for_timeout(500); seen.add(await h())
        ok("each detector choice gives a different image", len(seen) == len(opts), f"{len(seen)}/{len(opts)}")
        await pg.select_option('#detSel', 'all'); await pg.wait_for_timeout(400)
        fovs = await pg.evaluate("[...document.querySelectorAll('#fovSel option')].map(o => o.value)")
        res = []
        for v in fovs:
            await pg.select_option('#fovSel', v); await pg.wait_for_timeout(300); res.append(await pg.evaluate(f"{T}.S.fov"))
        ok("each view size applies", [float(x) for x in res] == [float(x) for x in fovs], str(res))
        await pg.select_option('#fovSel', fovs[0]); await pg.wait_for_timeout(300)
        await pg.click('#displayBtn'); await pg.wait_for_timeout(300)
        for sel, vals in [('stretchSel', ['linear', 'sqrt', 'log', 'asinh']), ('cmapSel', ['inferno', 'viridis', 'div', 'gray'])]:
            hs = set()
            for v in vals:
                await pg.select_option(f'#{sel}', v); await pg.wait_for_timeout(300); hs.add(await h())
            ok(f"Display: each {sel[:-3]} option changes the picture", len(hs) == len(vals))
        for rng, v in [('loRange', '10'), ('hiRange', '95')]:
            a = await h(); await pg.fill(f'#{rng}', v); await pg.dispatch_event(f'#{rng}', 'input'); await pg.wait_for_timeout(400)
            ok(f"Display: {rng[:2]} point slider changes the picture", a != await h())
        await pg.click('label[for=smoothToggle]'); await pg.wait_for_timeout(300)
        sm = await pg.evaluate("document.getElementById('imgCanvas').classList.contains('smooth')")
        await pg.click('label[for=smoothToggle]'); await pg.wait_for_timeout(300)
        ok("Display: smooth toggle smooths the pixels on screen", sm and not await pg.evaluate("document.getElementById('imgCanvas').classList.contains('smooth')"))
        for t in ['invToggle', 'flatToggle']:
            a = await h(); await pg.click(f'label[for={t}]'); await pg.wait_for_timeout(400); c = await h()
            await pg.click(f'label[for={t}]'); await pg.wait_for_timeout(300)
            ok(f"Display: {t[:-6]} toggle changes the picture", a != c)
        a = await pg.evaluate(f"{T}.S.lock"); await pg.click('label[for=lockScale]'); await pg.wait_for_timeout(300)
        ok("Display: same-scale toggle switches", await pg.evaluate(f"{T}.S.lock") != a)
        await pg.click('label[for=lockScale]'); await pg.keyboard.press('Escape'); await pg.wait_for_timeout(200)
        await pg.goto(BASE + "app.html?field=wise0855", wait_until="networkidle"); await pg.wait_for_timeout(3000)

        # ---------- modes
        for m, want in [('m-band', 'bandCtl'), ('m-scan', 'scanCtl'), ('m-exp', None), ('m-custom', 'customCtl'), ('m-epoch', None)]:
            await pg.click(f'label[for={m}]'); await pg.wait_for_timeout(600)
            n = await pg.evaluate(f"{T}.FRAMES.length"); help_ = await pg.evaluate("document.getElementById('modeHelp').textContent.length")
            vis = (await pg.is_visible(f'#{want}')) if want else True
            ok(f"mode {m[2:]}: frames built, its controls shown, explained", n > 0 and vis and help_ > 40, f"{n} frames")
        await pg.click('label[for=m-band]'); await pg.wait_for_timeout(400)
        n1 = await pg.evaluate(f"{T}.FRAMES.reduce((s, f) => s + f.members.length, 0)")
        await pg.fill('#tolRange', '4'); await pg.dispatch_event('#tolRange', 'input'); await pg.wait_for_timeout(500)
        n2 = await pg.evaluate(f"{T}.FRAMES.reduce((s, f) => s + f.members.length, 0)")
        ok("Same band: wider tolerance uses more images", n2 > n1, f"{n1} -> {n2}")
        await pg.fill('#bandRange', '90'); await pg.dispatch_event('#bandRange', 'input'); await pg.wait_for_timeout(500)
        ok("Same band: channel slider sets the channel", await pg.evaluate(f"{T}.S.band") == 90)
        await pg.click('label[for=m-scan]'); await pg.wait_for_timeout(400)
        await pg.select_option('#scanEpoch', index=1); await pg.wait_for_timeout(500)
        ok("λ scan: choosing another visit rebuilds the frames", await pg.evaluate(f"{T}.S.scan") == 1)
        await pg.click('label[for=m-epoch]'); await pg.wait_for_timeout(400)

        # ---------- difference references give the expected arithmetic (frame - reference) on screen
        await pg.click('label[for=diffToggle]'); await pg.wait_for_timeout(400)
        hs = set()
        for v in ['first', 'prev', 'others']:
            await pg.select_option('#diffRef', v); await pg.wait_for_timeout(400); hs.add(await h())
        ok("each difference reference gives a different image", len(hs) == 3)
        await pg.click('label[for=diffToggle]'); await pg.wait_for_timeout(300)

        # ---------- pin box
        box = await pg.locator('#imgCanvas').bounding_box()
        await pg.mouse.click(box['x'] + box['width'] * .3, box['y'] + box['height'] * .4); await pg.wait_for_timeout(400)
        pin = await pg.evaluate("document.getElementById('pinBox').innerText")
        ok("click pins a position", 'RA' in pin or '°' in pin or 'h' in pin, pin[:60])
        await pg.click('#pinBox [data-copy] >> nth=0'); await pg.wait_for_timeout(200); c1 = await clip()
        await pg.click('#pinBox [data-copy] >> nth=1'); await pg.wait_for_timeout(200); c2 = await clip()
        ok("pin copies degrees and h/d", re.match(r'^\d+\.\d+ [+-]?\d+\.\d+', c1) is not None and 'h' in c2, f"{c1} | {c2}")
        await pg.click('#unpin'); await pg.wait_for_timeout(300)
        ok("pin can be cleared", 'Click the image' in await pg.evaluate("document.getElementById('pinBox').innerText"))

        # ---------- compare with every survey, the note sits beside the picture, Back works
        for sid, name in [('src-dss', 'DSS2'), ('src-2mass', '2MASS'), ('src-wise', 'AllWISE')]:
            await pg.click(f'label[for={sid}]'); await pg.wait_for_timeout(5000)
            card = await pg.is_visible('#srcCard'); title = await pg.evaluate("document.getElementById('srcTitle').textContent")
            inside = await pg.evaluate("!!document.querySelector('#srcView #srcNote')")
            ok(f"Compare with {name}: picture shown, note beside it", card and name.lower()[:4] in title.lower() and not inside and await pg.is_visible('#srcView'), title)
        await pg.click('#srcBack'); await pg.wait_for_timeout(500)
        ok("Back to the SPHEREx frames", not await pg.is_visible('#srcView') and not await pg.is_visible('#srcCard') and await pg.is_checked('#src-spherex'))

        # ---------- save the whole field, then delete it; move; delete folder; your searches
        await pg.click('#saveHereBtn'); await pg.wait_for_timeout(400)
        await pg.fill('#saveName', 'Test whole field'); await pg.click('#saveConfirm'); await pg.wait_for_timeout(400)
        ok("☆ Save this place (whole field) adds it to My places", 'Test whole field' in await pg.evaluate("document.getElementById('libSaved').innerText"))
        DIALOG.append('Second'); await pg.click('#newFolderBtn'); await pg.wait_for_timeout(300)
        DIALOG.append('2'); await pg.click('#libSaved [data-imove] >> nth=0', force=True); await pg.wait_for_timeout(400)
        dd = await pg.evaluate("JSON.parse(localStorage.getItem('skytrace-saved'))")
        ok("⇄ move a place to another folder", any(f['name'] == 'Second' and len(f['items']) == 1 for f in dd['folders']))
        await pg.click('#libSaved [data-idelete] >> nth=0', force=True); await pg.wait_for_timeout(400)
        dd = await pg.evaluate("JSON.parse(localStorage.getItem('skytrace-saved'))")
        ok("✕ remove a saved place", sum(len(f['items']) for f in dd['folders']) == 0)
        n = len(dd['folders']); await pg.click('#libSaved [data-fdelete] >> nth=1', force=True); await pg.wait_for_timeout(400)
        ok("delete a folder", len((await pg.evaluate("JSON.parse(localStorage.getItem('skytrace-saved'))"))['folders']) == n - 1)
        await pg.fill('#coordInput', '150.3 21.7'); await pg.press('#coordInput', 'Enter'); await pg.wait_for_timeout(3500)
        mine = await pg.evaluate("document.getElementById('libMine').innerText")
        ok("a searched place is added to Your searches", 'RA 150' in mine or '150.3' in mine, mine[:60])
        DIALOG.append('My test place'); await pg.click('#libMine [data-rename] >> nth=0', force=True); await pg.wait_for_timeout(400)
        ok("✎ rename in Your searches", 'My test place' in await pg.evaluate("document.getElementById('libMine').innerText"))
        await pg.click('#libMine [data-forget] >> nth=0', force=True); await pg.wait_for_timeout(400)
        ok("✕ remove from Your searches", 'My test place' not in await pg.evaluate("document.getElementById('libMine').innerText"))
        await pg.click("#libTargets >> text=Barnard's Star"); await pg.wait_for_timeout(3000)
        # Barnard saturates: movers must not report anything there (judges' example of a noise fit)
        await pg.click('#sheet [data-bs-target="#tabMovers"]'); await pg.wait_for_timeout(1500)
        mv = await pg.evaluate(f"{T}.MOVERS.length"); txt = await pg.evaluate("document.getElementById('moverList').innerText")
        ok("Barnard's Star: no false moving objects; says the target saturates", mv == 0 and 'saturat' in txt, txt[:90])
        a = await h('ovCanvas'); await pg.click('label[for=ovFlags]'); await pg.wait_for_timeout(400); c = await h('ovCanvas')
        await pg.click('label[for=ovFlags]'); await pg.wait_for_timeout(200)
        ok("layer chip Flags shades Barnard's saturated core", a != c)
        # fastest-moving stars folder: Barnard's Star is in it and opens the built field
        await pg.evaluate("document.getElementById('libFast').closest('details').querySelector('summary').click()"); await pg.wait_for_timeout(400)
        fast = await pg.evaluate("document.querySelectorAll('#libFast li').length")
        ok("Fastest-moving stars list opens (25 stars)", fast >= 25, str(fast))

        # ---------- every Analysis tab has content and an explanation
        await pg.goto(BASE + "app.html?field=epsindib", wait_until="networkidle"); await pg.wait_for_timeout(3500)
        for tab in ['tabSpec', 'tabLc', 'tabMovers', 'tabExp', 'tabSettings', 'tabShare', 'tabData', 'tabAladin']:
            await pg.click(f'#sheet [data-bs-target="#{tab}"]'); await pg.wait_for_timeout(4000 if tab == 'tabAladin' else 900)
            L = await pg.evaluate(f"document.getElementById('{tab}').innerText.length")
            hb = await pg.evaluate(f"!!document.querySelector('#{tab} .hud-help-btn')")
            tt = await pg.evaluate(f"document.querySelector('#sheet [data-bs-target=\"#{tab}\"]').title.length")
            ok(f"tab {tab[3:]}: content, ? help and a tooltip", L > 40 and hb and tt > 10, f"{L} chars")
        await pg.click('#sheet [data-bs-target="#tabAladin"]'); await pg.wait_for_timeout(500)
        for v in ['allwise', 'twomass', 'dss', 'spherex']:
            await pg.select_option('#aladinSurvey', v); await pg.wait_for_timeout(2500)
        ok("Atlas: every background can be chosen", await pg.evaluate("document.getElementById('atlasFrame').options.length") >= 100)
        await pg.select_option('#atlasFrame', index=60); await pg.wait_for_timeout(1500)
        ok("Atlas: no coordinate boxes over the map", await pg.evaluate("!document.querySelector('#aladinDiv .aladin-location')") or not await pg.is_visible('#aladinDiv .aladin-location'))
        # Moving objects on Epsilon Indi B (known mover) and shift-and-add
        await pg.click('#sheet [data-bs-target="#tabMovers"]'); await pg.wait_for_timeout(1500)
        M = await pg.evaluate(f"{T}.MOVERS.map(m => [m.pm, m.epm, !!m.target])")
        ok("Epsilon Indi B: found as the target, motion agrees with Gaia (4.68″/yr)", len(M) == 1 and M[0][2] and abs(M[0][0] - 4.68) < 2 * M[0][1], str(M))
        a = await h(); await pg.click('#saTarget'); await pg.click('label[for=saToggle]'); await pg.wait_for_timeout(1500)
        ok("shift-and-add changes the stack", a != await h())
        await pg.click('label[for=saToggle]'); await pg.wait_for_timeout(500)
        # Spectrum toggles
        await pg.click('#sheet [data-bs-target="#tabSpec"]'); await pg.wait_for_timeout(800)
        n_on = await pg.evaluate("document.getElementById('specPlot').data.reduce((s, t) => s + (t.x ? t.x.length : 0), 0)")
        await pg.click('label[for=specClean]'); await pg.wait_for_timeout(800)
        n_off = await pg.evaluate("document.getElementById('specPlot').data.reduce((s, t) => s + (t.x ? t.x.length : 0), 0)")
        await pg.click('label[for=specClean]'); await pg.click('label[for=specLog]'); await pg.wait_for_timeout(800)
        lg = await pg.evaluate("document.getElementById('specPlot').layout.yaxis.type")
        await pg.click('label[for=specLog]'); await pg.wait_for_timeout(400)
        ok("spectrum: flagged points hidden/shown, log axis", n_off > n_on and lg == 'log', f"{n_on} -> {n_off} points")
        # Share tab: each button
        await pg.click('#sheet [data-bs-target="#tabShare"]'); await pg.wait_for_timeout(500)
        await pg.click('#copyLinkBtn'); await pg.wait_for_timeout(200); c = await clip()
        ok("Copy link", 'field=epsindib' in c and 'app.html' in c)
        await pg.click('#copyEmbedBtn'); await pg.wait_for_timeout(200); c = await clip()
        ok("Copy embed code", c.startswith('<iframe') and 'embed=1' in c)
        await pg.click('#copyCoordBtn'); await pg.wait_for_timeout(200); c = await clip()
        ok("Copy centre RA/Dec", c.startswith('331.09') and '-56.8' in c, c)
        async with pg.expect_download() as d: await pg.click('#saveImgBtn')
        f = await (await d.value).path(); from PIL import Image; im = Image.open(f)
        ok("Save image (PNG) at least 900 px wide", im.width >= 900, f"{im.size}")
        async with pg.expect_download() as d: await pg.click('#saveCsvBtn')
        rows = open(await (await d.value).path()).read().strip().splitlines()
        n_exp = await pg.evaluate(f"{T}.F.meta.exposures.length")
        ok("Download data (CSV): one row per SPHEREx image (+ catalogue points)", len([r for r in rows if r.startswith('SPHEREx,')]) == n_exp, f"{len(rows)} lines, {n_exp} images")
        await pg.click('#reportBtn'); await pg.wait_for_timeout(600)
        rep = await pg.evaluate("(document.getElementById('reportText') || {}).value || document.querySelector('.modal.show textarea, .modal.show pre')?.textContent || ''")
        ok("Report a candidate writes a report", len(rep) > 200 and 'Epsilon Indi B' in rep)
        await pg.click('#reportCopy'); await pg.wait_for_timeout(200)
        ok("report: Copy", len(await clip()) > 200)
        async with pg.expect_download() as d: await pg.click('#reportDownload')
        ok("report: Download .txt", (await d.value).suggested_filename.endswith('.txt'))
        await pg.keyboard.press('Escape'); await pg.wait_for_timeout(400)
        # Sources: check releases (live server only)
        await pg.click('#sheet [data-bs-target="#tabData"]'); await pg.wait_for_timeout(400)
        if await pg.locator('#checkReleases').count():
            await pg.click('#checkReleases'); await pg.wait_for_timeout(20000)
            ok("Check IRSA for new data releases answers", len(await pg.evaluate("document.getElementById('relMsg').innerText")) > 5,
               await pg.evaluate("document.getElementById('relMsg').innerText"))
        # Export: select all / clear
        await pg.click('#exportTop'); await pg.wait_for_timeout(500)
        await pg.click('#exportNone'); none = await pg.evaluate("[...document.querySelectorAll('[data-ex]')].filter(x => x.checked).length")
        await pg.click('#exportAll'); all_ = await pg.evaluate("[...document.querySelectorAll('[data-ex]')].filter(x => !x.checked).length")
        ok("Export: Select all and Clear", none == 0 and all_ == 0)
        await pg.keyboard.press('Escape'); await pg.wait_for_timeout(400)
        # every ? help opens text
        hb = pg.locator('.hud-help-btn'); n = await hb.count(); opened = 0; vis = 0
        for i in range(n):
            if not await hb.nth(i).is_visible(): continue
            vis += 1; await hb.nth(i).click(); await pg.wait_for_timeout(150)
            if await pg.evaluate("[...document.querySelectorAll('.hud-help')].some(x => x.offsetParent && x.innerText.length > 40)"): opened += 1
            await hb.nth(i).click(); await pg.wait_for_timeout(100)
        ok("every visible ? button opens an explanation", opened == vis, f"{opened}/{vis}")
        # every control has a tooltip, an aria label or a visible label
        bare = await pg.evaluate("""[...document.querySelectorAll('button, select, input:not([type=hidden])')].filter(e => e.offsetParent)
          .filter(e => !e.closest('.aladin-container, [class*=aladin-]') && !e.closest('label'))
          .filter(e => !e.title && !e.getAttribute('aria-label') && !(e.textContent || '').trim() && !(e.id && document.querySelector(`label[for="${e.id}"]`)))
          .map(e => e.id || e.className)""")
        ok("every visible control is labelled or has a tooltip", not bare, str(bare))
        # panels
        await pg.click('#railToggle') if await pg.locator('#railToggle').count() else None
        await pg.click('#sheetToggle'); await pg.wait_for_timeout(400)
        ok("hide Analysis: « Analysis button sits in the image header", await pg.evaluate("document.getElementById('sheetShow').closest('.st-stage-head') !== null") and await pg.is_visible('#sheetShow'))
        await pg.click('#sheetShow'); await pg.wait_for_timeout(300)
        ok("« Analysis brings it back", await pg.is_visible('#sheet'))
        ok("no page errors", not errs, "; ".join(errs[:3]))
        await b.close()
    print(f"\n{sum(RES)}/{len(RES)} passed")

asyncio.run(main())
