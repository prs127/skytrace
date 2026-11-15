"""Walk through Skytrace as a first-time user following guide.html, and as an astronomer checking each control.
Every step prints PASS/FAIL with what was observed. External requests (IRSA HiPS) go through the workspace proxy.
Usage: python tests/user_walkthrough.py http://127.0.0.1:8090/"""
import asyncio, os, re, sys, json
from playwright.async_api import async_playwright
BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8090/'
results = []
def ok(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (f'  [{detail}]' if detail else ''), flush=True)

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"],
                                    proxy={"server": os.environ.get("HTTPS_PROXY", ""), "bypass": "127.0.0.1,localhost"})
        ctx = await b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True, ignore_https_errors=True)
        await ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE.rstrip('/'))
        pg = await ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept(DIALOG.pop(0) if DIALOG else '')))
        T = "window.__skytrace"

        # ---- welcome -> home -> dashboard
        await pg.goto(BASE); await pg.wait_for_timeout(6000)
        ok("welcome: Next appears after the animation", await pg.is_visible('#next') and await pg.evaluate("getComputedStyle(document.getElementById('next')).opacity") == '1')
        await pg.click('#next'); await pg.wait_for_load_state(); ok("welcome: Next opens Home", pg.url.endswith('home.html'), pg.url)
        ok("home: one primary button", await pg.locator('.st-hero .btn-info').count() == 1)
        ok("home: example links", await pg.locator('#homeTargets a').count() == 6)
        await pg.click('text=How to use Skytrace'); await pg.wait_for_load_state()
        anchors = await pg.evaluate("[...document.querySelectorAll('.st-toc a')].map(a => a.getAttribute('href').slice(1))")
        missing = await pg.evaluate(f"{json.dumps(anchors)}.filter(id => !document.getElementById(id))")
        ok("guide: every contents link has a section", not missing, f"{len(anchors)} links, missing {missing}")

        # ---- guide section 2, step 1: open WISE 0855 from the library
        await pg.goto(BASE + 'app.html'); await pg.wait_for_function(f"{T} && {T}.F && document.getElementById('loadingVeil').classList.contains('d-none')", timeout=60000)
        await pg.click('#libTargets .st-item[data-key=wise0855]'); await pg.wait_for_function(f"{T}.F.meta.key === 'wise0855' && document.getElementById('loadingVeil').classList.contains('d-none')", timeout=60000)
        await pg.wait_for_timeout(800)
        ok("library: WISE 0855 opens and is highlighted", await pg.locator('#libTargets .st-item.active').inner_text() != '')
        ok("field name and i note", 'WISE' in await pg.inner_text('#fieldTitle') and await pg.is_visible('#noteBtn'))
        await pg.click('#noteBtn'); ok("i opens the field note", await pg.is_visible('#fieldNote'), (await pg.inner_text('#fieldNote'))[:60])
        await pg.mouse.click(5, 880); ok("clicking elsewhere closes it", not await pg.is_visible('#fieldNote'))
        ok("blend ! shown for WISE 0855 (Gaia star 7.7\" away)", await pg.is_visible('#blendBtn'))
        await pg.click('#blendBtn'); ok("! opens the blend warning", 'Blend' in await pg.inner_text('#blendNote')); await pg.mouse.click(5, 880)
        # step 2: play
        f0 = await pg.evaluate(f"{T}.S.frame"); await pg.click('#playBtn'); await pg.wait_for_timeout(1500); await pg.click('#playBtn')
        ok("play advances frames", await pg.evaluate(f"{T}.S.frame") != f0 or await pg.evaluate(f"{T}.FRAMES.length") == 1)
        # speed slider: right = faster
        await pg.evaluate("(() => { const r = document.getElementById('speedRange'); r.value = r.max; r.dispatchEvent(new Event('input')); })()")
        fast = await pg.evaluate(f"{T}.S.speed")
        await pg.evaluate("(() => { const r = document.getElementById('speedRange'); r.value = r.min; r.dispatchEvent(new Event('input')); })()")
        slow = await pg.evaluate(f"{T}.S.speed"); ok("speed: slider right = fewer ms per frame (faster)", fast < slow, f"right {fast} ms, left {slow} ms")
        # step 3: Gaia layer
        await pg.click('label[for=ovGaia]'); ok("Gaia DR3 chip toggles the layer", await pg.evaluate(f"{T}.S.ov.includes('gaia')"))
        # step 4: moving objects
        await pg.click('button[data-bs-target="#tabMovers"]'); await pg.wait_for_timeout(300)
        mv = await pg.evaluate(f"{T}.MOVERS.map(m => [m.pm.toFixed(2), !!m.target])")
        ok("moving objects: WISE 0855 found and labelled as the target", any(t for _, t in mv), str(mv))
        await pg.click('#moverList .mover-row'); ok("clicking a result pins it", 'Pinned' in await pg.inner_text('#pinBox'))
        await pg.click('label[for=ovMovers]'); ok("Movers layer on", await pg.evaluate(f"{T}.S.ov.includes('movers')"))
        await pg.click('#tabMovers details.st-about summary'); ok("'How these were checked' expands", 'Gaia' in await pg.inner_text('#tabMovers details.st-about'))
        # step 5: difference
        await pg.click('#diffToggle'); await pg.wait_for_timeout(300)
        ok("Difference: frames become differences", await pg.evaluate(f"{T}.FRAMES.some(f => f.isDiff)"))
        for ref in ['prev', 'others', 'first']:
            await pg.select_option('#diffRef', ref); await pg.wait_for_timeout(200)
        ok("difference references selectable", await pg.evaluate(f"{T}.S.dref") == 'first')
        await pg.click('#diffToggle')
        # step 6: spectrum
        await pg.click('button[data-bs-target="#tabSpec"]'); await pg.wait_for_timeout(400)
        ok("spectrum plot drawn", await pg.evaluate("!!document.getElementById('specPlot').data && document.getElementById('specPlot').data.length > 0"))
        await pg.click('label[for=specLog]'); await pg.click('label[for=specClean]'); await pg.wait_for_timeout(300)
        ok("spectrum toggles (log axis, flagged points)", await pg.evaluate("document.getElementById('specPlot').layout.yaxis.type") == 'log')
        await pg.click('label[for=specLog]'); await pg.click('label[for=specClean]')

        # ---- search box: name, coordinates, bad input
        await pg.fill('#coordInput', 'Epsilon Indi B'); await pg.press('#coordInput', 'Enter')
        await pg.wait_for_function(f"{T}.F.meta.key === 'epsindib' && document.getElementById('loadingVeil').classList.contains('d-none')", timeout=60000)
        ok("search by name opens Epsilon Indi B", True)
        await pg.fill('#coordInput', '22h04m23s -56d48m00s'); await pg.press('#coordInput', 'Enter'); await pg.wait_for_timeout(1200)
        ok("coordinates inside the field: pinned, no new download", 'Pinned' in await pg.inner_text('#pinBox'), await pg.inner_text('#coordMsg'))
        await pg.fill('#coordInput', 'hello world'); await pg.press('#coordInput', 'Enter'); await pg.wait_for_timeout(300)
        ok("unreadable input gets a message", 'Could not read' in await pg.inner_text('#coordMsg'))
        ok("field size menu offers 9, 15, 20 arcmin", await pg.evaluate("[...document.querySelectorAll('#sizeSel option')].map(o => o.value).join()") == '9,15,20')

        # ---- reading the image: hover, pin box buttons
        await pg.evaluate("document.querySelector('.st-stage').scrollTop = 0; document.body.scrollTop = 0; document.documentElement.scrollTop = 0; document.getElementById('console').scrollTop = 0")
        box = await pg.locator('#ovCanvas').bounding_box()
        await pg.mouse.move(box['x'] + box['width'] * .3, box['y'] + box['height'] * .4, steps=3); await pg.wait_for_timeout(300)
        ro = await pg.inner_text('#hoverReadout'); ok("hover read-out shows RA, Dec and MJy/sr", 'RA' in ro and 'MJy/sr' in ro, ro[:70])
        await pg.mouse.click(box['x'] + box['width'] * .3, box['y'] + box['height'] * .4)
        await pg.click('#pinToInput'); ok("'use as input' fills the search box", re.search(r'\d+h', await pg.input_value('#coordInput')) is not None)

        # ---- modes
        for mode in ['band', 'scan', 'exp', 'custom', 'epoch']:
            await pg.click(f'label[for=m-{mode}]'); await pg.wait_for_timeout(300)
            ok(f"mode {mode}: frames built", await pg.evaluate(f"{T}.S.mode") == mode and await pg.evaluate(f"{T}.FRAMES.length") > 0, f"{await pg.evaluate(f'{T}.FRAMES.length')} frames")
            if mode == 'band':
                ok("same band: channel slider visible", await pg.is_visible('#bandRange'))
            if mode == 'scan': ok("lambda scan: visit menu visible", await pg.is_visible('#scanEpoch'))
            if mode == 'custom':
                await pg.click('#customList input[data-set=B][data-k="1"]'); await pg.wait_for_timeout(300)
                ok("add/subtract: ticking B subtracts", await pg.evaluate(f"{T}.FRAMES[0].minus.size") > 0)
        await pg.click('details:has(#modeHelp) summary'); ok("'About this mode' explains the mode", len(await pg.inner_text('#modeHelp')) > 40)
        # channel strip click -> same band
        await pg.locator('#bandStrip').scroll_into_view_if_needed(); sb = await pg.locator('#bandStrip').bounding_box(); await pg.mouse.click(sb['x'] + sb['width'] * .5, sb['y'] + sb['height'] * .5); await pg.wait_for_timeout(300)
        ok("channel strip click switches to Same band at that channel", await pg.evaluate(f"{T}.S.mode") == 'band', f"channel {await pg.evaluate(f'{T}.S.band')}")
        await pg.click('label[for=m-epoch]')
        # detectors
        for det in ['rgb', 'lw', '3', 'all']:
            await pg.select_option('#detSel', det); await pg.wait_for_timeout(250)
        ok("detector menu works", await pg.evaluate(f"{T}.S.det") == 'all')
        # view size
        await pg.select_option('#fovSel', '4'); await pg.wait_for_timeout(200); ok("view size zooms (4')", await pg.evaluate(f"{T}.S.fov") == 4)
        await pg.select_option('#fovSel', '9.1')
        # display menu
        await pg.click('#displayBtn'); await pg.wait_for_timeout(200)
        ok("Display menu opens", await pg.is_visible('#stretchSel'))
        for sel, v in [('#stretchSel', 'log'), ('#cmapSel', 'inferno')]: await pg.select_option(sel, v)
        for cid in ['invToggle', 'smoothToggle', 'flatToggle', 'lockScale']: await pg.click(f'label[for={cid}]'); await pg.click(f'label[for={cid}]')
        ok("Display options change settings", await pg.evaluate(f"{T}.S.stretch") == 'log' and await pg.evaluate(f"{T}.S.cmap") == 'inferno')
        await pg.select_option('#stretchSel', 'asinh'); await pg.select_option('#cmapSel', 'gray'); await pg.keyboard.press('Escape')
        # layers
        for lid in ['ovWise', 'ovTmass', 'ovFlags', 'ovCompass', 'ovTarget']:
            before = await pg.evaluate(f"{T}.S.ov"); await pg.click(f'label[for={lid}]'); after = await pg.evaluate(f"{T}.S.ov")
            ok(f"layer chip {lid} toggles", before != after)
        # compare with older surveys
        await pg.click('label[for=src-2mass]'); await pg.wait_for_timeout(6000)
        ok("Compare with 2MASS shows the picture", await pg.is_visible('#srcView') and 'did not answer' not in await pg.inner_text('#srcNote'), (await pg.inner_text('#srcNote'))[:60])
        await pg.click('label[for=src-spherex]'); await pg.wait_for_timeout(300)
        # light curve, exposures, atlas, visits, sources
        await pg.click('button[data-bs-target="#tabLc"]'); await pg.wait_for_timeout(400); ok("light curve tab shows a plot or a reason", await pg.evaluate("!!document.getElementById('lcPlot').data || document.getElementById('lcPlot').textContent.length > 20"))
        await pg.click('button[data-bs-target="#tabExp"]'); ok("exposures table rows", await pg.locator('#expTable tr').count() > 0)
        await pg.click('button[data-bs-target="#tabAladin"]'); await pg.wait_for_timeout(7000); ok("atlas loads the SPHEREx map with a channel list", await pg.locator('#atlasFrame option').count() == 100, (await pg.inner_text('#aladinMsg'))[:60])
        await pg.click('button[data-bs-target="#tabSettings"]')
        await pg.evaluate("(() => { const r = document.getElementById('winRange'); r.value = 10; r.dispatchEvent(new Event('input')); })()"); await pg.wait_for_timeout(300)
        ok("visit grouping slider changes visits", await pg.evaluate(f"{T}.VISITS.length") >= 4, f"{await pg.evaluate(f'{T}.VISITS.length')} visits")
        await pg.evaluate("(() => { const r = document.getElementById('winRange'); r.value = 30; r.dispatchEvent(new Event('input')); })()")
        await pg.click('button[data-bs-target="#tabData"]'); ok("sources tab lists the data", 'SPHEREx exposures' in await pg.inner_text('#provenance'))
        # shift-and-add
        await pg.click('button[data-bs-target="#tabMovers"]'); await pg.click('#saTarget'); await pg.click('label[for=saToggle]'); await pg.wait_for_timeout(500)
        ok("shift-and-add on with the target's motion", await pg.evaluate(f"{T}.S.sa") == 1 and abs(await pg.evaluate(f"{T}.S.sapmra") - 3982) < 2)
        await pg.click('label[for=saToggle]')

        # ---- saved places
        box = await pg.locator('#ovCanvas').bounding_box()
        await pg.mouse.click(box['x'] + box['width'] * .5, box['y'] + box['height'] * .5)
        await pg.click('#saveHereBtn'); await pg.wait_for_timeout(500)
        await pg.fill('#saveName', 'Eps Indi B spot'); await pg.select_option('#saveFolderSel', '__new'); await pg.fill('#saveNewFolder', 'Brown dwarfs'); await pg.fill('#saveNote', 'moving pair')
        await pg.click('#saveConfirm'); await pg.wait_for_timeout(600)
        ok("save a pinned spot into a new folder", 'Brown dwarfs' in await pg.inner_text('#libSaved') and 'Eps Indi B spot' in await pg.inner_text('#libSaved'))
        link = await pg.evaluate("(() => { const d = JSON.parse(localStorage.getItem('skytrace-saved')); return d.folders.find(f => f.name === 'Brown dwarfs').id; })()")
        await pg.hover(f'[data-folder="{link}"] > summary'); await pg.click(f'[data-fshare="{link}"]'); await pg.wait_for_timeout(300)
        shared = await pg.evaluate("navigator.clipboard.readText()")
        ok("share folder copies a link", 'folder=' in shared, shared[:80])
        DIALOG.append('Renamed spot')
        item = await pg.locator(f'[data-folder="{link}"] [data-irename]').first.get_attribute('data-irename')
        await pg.hover(f'[data-folder="{link}"] li'); await pg.click(f'[data-irename="{item}"]'); await pg.wait_for_timeout(300)
        ok("rename a saved place", 'Renamed spot' in await pg.inner_text('#libSaved'))
        await pg.click('#libTargets .st-item[data-key=wise0855]'); await pg.wait_for_timeout(2500)
        await pg.click(f'[data-open="{item}"]'); await pg.wait_for_timeout(3000)
        ok("opening a saved spot reopens its field and pin", await pg.evaluate(f"{T}.F.meta.key") == 'epsindib' and 'Pinned' in await pg.inner_text('#pinBox'))
        # import the shared folder in a fresh browser profile
        ctx2 = await b.new_context(viewport={"width": 1440, "height": 900}); pg2 = await ctx2.new_page()
        await pg2.goto(shared); await pg2.wait_for_function(f"{T} && {T}.F", timeout=60000); await pg2.wait_for_timeout(800)
        ok("a shared folder link adds the folder for someone else", 'Brown dwarfs (shared)' in await pg2.inner_text('#libSaved'))
        await ctx2.close()

        # ---- export PDF
        await pg.click('#exportTop'); await pg.wait_for_timeout(500)
        ok("Export panel opens with checkboxes", await pg.locator('#exportPanel [data-ex]').count() >= 15, await pg.inner_text('#exportWhat'))
        await pg.click('#exportNone'); await pg.click('#exportPanel [data-ex=summary]'); await pg.click('#exportPanel [data-ex=movers]'); await pg.click('#exportPanel [data-ex=current]')
        async with pg.expect_download(timeout=90000) as d: await pg.click('#exportGo')
        path = '/home/claude/scratch/walk_report.pdf'; await (await d.value).save_as(path)
        import subprocess; txt = subprocess.run(['pdftotext', path, '-'], capture_output=True, text=True).stdout
        ok("PDF contains only the ticked sections", 'Target and field' in txt and 'Moving objects' in txt and 'Spectrum values' not in txt and 'Light curve' not in txt)
        await pg.click('#exportPanel .btn-close'); await pg.wait_for_timeout(400)

        # ---- share, help, panels, keyboard, URL
        await pg.click('#shareTop'); await pg.wait_for_timeout(300); ok("Share button opens the Share tab", await pg.is_visible('#shareUrl'))
        url = await pg.input_value('#shareUrl'); ok("share link carries coordinates", 'ra=' in url and 'dec=' in url, url[:90])
        helps = await pg.locator('.hud-help-btn:visible').count(); ok("help buttons present", helps >= 8, f"{helps} visible")
        await pg.click('[data-help="overlays"] > .hud-help-btn'); ok("layers help explains and links to the guide", 'guide.html#layers' in await pg.inner_html('[data-help="overlays"] .hud-help'))
        await pg.click('#railToggle'); await pg.click('#sheetToggle'); await pg.wait_for_timeout(400)
        w = await pg.evaluate("document.getElementById('viewerWrap').getBoundingClientRect().width")
        await pg.click('#railShow'); await pg.click('#sheetShow'); await pg.wait_for_timeout(400)
        w2 = await pg.evaluate("document.getElementById('viewerWrap').getBoundingClientRect().width")
        ok("hiding both side panels gives the image more room", w >= w2, f"{w:.0f}px vs {w2:.0f}px")
        await pg.click('#viewerWrap'); f0 = await pg.evaluate(f"{T}.S.frame"); await pg.keyboard.press('ArrowRight')
        ok("keyboard arrow steps a frame", await pg.evaluate(f"{T}.S.frame") != f0)
        await pg.goto(BASE + 'app.html?field=wise0855&det=lw&diff=1&ov=target,gaia'); await pg.wait_for_function(f"{T} && {T}.F", timeout=60000); await pg.wait_for_timeout(800)
        ok("URL settings applied", await pg.evaluate(f"[{T}.S.det, {T}.S.diff, {T}.S.ov].join('|')") == 'lw|1|target,gaia')
        await pg.goto(BASE + '?field=rwaur'); await pg.wait_for_timeout(2500); ok("old /?field= link goes to the dashboard", 'app.html' in pg.url)
        ok("no page errors", not errs, '; '.join(errs)[:200])
        print(f"\n{sum(r for _, r in results)}/{len(results)} passed")
        await b.close()
DIALOG = []
asyncio.run(main())
