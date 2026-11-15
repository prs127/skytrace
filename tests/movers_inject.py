"""Injection-recovery test for the moving-object finder, on the real SPHEREx exposures of each field.

Fake point sources (Gaussian, width measured from the field's own isolated stars) are added to every
exposure at the position a linearly moving object would have at that exposure's time. Half are given a
real motion (2-25"/yr, random direction), half are given zero motion. We then run the finder and count:
  * recovered movers (and the error of their measured motion),
  * stationary injections wrongly reported as movers (false positives on known non-movers),
  * any other reported mover (not injected, not a catalogued mover): unexplained false positives.
Writes modified copies of the field files to OUT so the browser version can be run on identical data.
"""
import gzip, json, math, os, shutil, sys
import numpy as np
sys.path.insert(0, os.path.dirname(__file__)); import movers_ref as M

def psf_sigma(m, img, cat):
    ex = m['exposures']; noises = sorted(e['noise'] for e in ex if (e['noise'] or 0) > 0); medn = noises[len(noises) // 2]
    V = M.visits(m); s, f = M.balanced(m, img, cat, V[0], medn); s = M.flatten(s); d = M.detect(s, f)
    sig = []
    yy, xx = np.mgrid[-3:4, -3:4]
    for q in d:
        if not (30 < q['snr'] < 200): continue
        ix, iy = int(round(q['x'])), int(round(q['y'])); c = np.clip(s[iy - 3:iy + 4, ix - 3:ix + 4], 0, None)
        if c.shape != (7, 7) or not np.isfinite(c).all(): continue
        tot = c.sum(); mx = (c * xx).sum() / tot; my = (c * yy).sum() / tot
        sig.append(math.sqrt(max(((c * ((xx - mx) ** 2 + (yy - my) ** 2)).sum() / tot) / 2, 0.1)))
    return float(np.median(sig)) if sig else 1.0

def inject(key, data, out, n=24, seed=1):
    rng = np.random.default_rng(seed)
    m, img, cat = M.load(data, key); img = img.copy(); ex = m['exposures']; npx = m['grid']['npix']
    sg = psf_sigma(m, img, cat)
    # noise of the smoothed visit stack (what the detector thresholds on), measured on visit 1 of this field
    from scipy.ndimage import gaussian_filter
    noises = sorted(e['noise'] for e in ex if (e['noise'] or 0) > 0); mn = noises[len(noises) // 2]
    s0, _ = M.balanced(m, img, cat, M.visits(m)[0], mn); s0 = M.flatten(s0); z = np.where(np.isfinite(s0), s0, 0)
    sm = gaussian_filter(z, 1.0, mode='constant'); vv = sm[np.isfinite(s0)]; sig_s = 1.4826 * np.median(np.abs(vv - np.median(vv)))
    gain = sg ** 2 / (sg ** 2 + 1.0)                   # peak of (Gaussian sigma sg) convolved with the sigma = 1 px smoothing
    mjd = np.array([e['mjd'] for e in ex]); tmid = 0.5 * (mjd.min() + mjd.max())
    nz = np.array([(e['noise'] or np.nan) for e in ex]); medn = np.nanmedian(nz)
    yy, xx = np.mgrid[0:npx, 0:npx]
    truth = []
    for k in range(n):
        moving = k % 2 == 0
        pm = rng.uniform(2, 25) if moving else 0.0; ang = rng.uniform(0, 2 * math.pi)
        vx, vy = pm / 6.15 / 365.25 * math.cos(ang), pm / 6.15 / 365.25 * math.sin(ang)
        for _ in range(200):                           # keep injections >= 6 px apart so they do not blend with each other
            x0, y0 = rng.uniform(12, npx - 13), rng.uniform(12, npx - 13)
            if all(math.hypot(x0 - q['x0'], y0 - q['y0']) >= 6 for q in truth): break
        snr = rng.uniform(4, 40)                       # target S/N in a visit stack, as the finder measures it
        amp = snr * sig_s / gain
        truth.append(dict(x0=x0, y0=y0, vx=vx, vy=vy, pm=pm, moving=moving, amp=amp, snr=snr))
        for i, e in enumerate(ex):
            x, y = x0 + vx * (mjd[i] - tmid), y0 + vy * (mjd[i] - tmid)
            img[i] += (amp * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sg ** 2))).astype(np.float32)
    os.makedirs(out, exist_ok=True)
    kk = key + '_inj'
    m2 = dict(m); m2['key'] = kk; m2['name'] = m['name'] + ' (injection test)'
    json.dump(m2, open(f'{out}/{kk}.json', 'w'))
    with gzip.open(f'{out}/{kk}.img.bin.gz', 'wb') as f: f.write(img.astype('<f2').tobytes())
    shutil.copy(f'{data}/{key}.cat.bin.gz', f'{out}/{kk}.cat.bin.gz')
    json.dump(dict(truth=truth, tmid=tmid, psf_sigma=sg), open(f'{out}/{kk}.truth.json', 'w'))
    return kk, truth, tmid, sg

def score(found, truth, m, tmid):
    from astropy.wcs import WCS
    g = m['grid']; w = WCS(naxis=2); w.wcs.ctype = ['RA---TAN', 'DEC--TAN']; w.wcs.crval = g['crval']; w.wcs.crpix = g['crpix']; w.wcs.cdelt = g['cdelt']
    rec, fp_still, other = [], 0, 0
    for o in found:
        x, y = w.world_to_pixel_values(o['ra'], o['dec'])
        # compare with every injection at the track's reference time (position at tmid +- motion*dt)
        best = None
        for tr in truth:
            if math.hypot(tr['x0'] - x, tr['y0'] - y) < 2.5 + tr['pm'] / 6.15 * 1.5: best = tr if best is None or math.hypot(tr['x0'] - x, tr['y0'] - y) < math.hypot(best['x0'] - x, best['y0'] - y) else best
        if best is None: other += (0 if o.get('gaia') or o.get('target') else 1); continue
        if not best['moving']: fp_still += 1; continue
        rec.append((best['pm'], o['pm'], o['epm'], best['snr']))
    return rec, fp_still, other

if __name__ == '__main__':
    data, out = 'frontend/data', sys.argv[1] if len(sys.argv) > 1 else '/home/claude/scratch/injdata'
    tot_m = tot_rec = tot_fp = tot_other = 0; errs = []; allrec = []; alltruth = []
    for key, det in [('wise0855', 'lw'), ('epsindib', 'all'), ('barnard', 'all'), ('rwaur', 'all'), ('rdra', 'all'), ('m101', 'all')]:
        for seed in (1, 2):
            kk, truth, tmid, sg = inject(key, data, out, seed=seed)
            found, info = M.run(out, kk, det, verbose=False)
            m = json.load(open(f'{out}/{kk}.json'))
            rec, fp, other = score(found, truth, m, tmid)
            nm = sum(t['moving'] for t in truth)
            # only movers whose shift over the baseline is >= 0.5 px can be found by design
            base = (max(e['mjd'] for e in m['exposures']) - min(e['mjd'] for e in m['exposures'])) / 365.25
            nm_detectable = sum(t['moving'] and t['pm'] * base / 6.15 >= 0.5 for t in truth)
            tot_m += nm_detectable; tot_rec += len(rec); tot_fp += fp; tot_other += other
            errs += [(f - tpm) / max(e, 1e-6) for tpm, f, e, _ in rec]; allrec.extend(rec); alltruth.extend([dict(t, base=base) for t in truth])
            print(f"{key:9s} seed {seed}: psf sigma {sg:.2f}px  injected movers {nm} (shift >= 0.5 px: {nm_detectable})  recovered {len(rec)}  "
                  f"stationary injections reported as movers {fp}  other unexplained movers {other}  |pm error| median "
                  f"{np.median([abs(f - tpm) for tpm, f, e, _ in rec]) if rec else float('nan'):.2f}\"/yr", flush=True)
    print(f"\nTOTAL: recovered {tot_rec}/{tot_m} detectable movers; false positives: {tot_fp} stationary injections, {tot_other} unexplained")
    if errs: print(f"pm error / quoted 1-sigma: median |z| {np.median(np.abs(errs)):.2f} (0.67 expected for honest errors), 95th pct {np.percentile(np.abs(errs), 95):.2f}")
    # recovery fraction by injected S/N, for movers that shift >= 1 px over the baseline
    for lo, hi in [(4, 7), (7, 12), (12, 20), (20, 40)]:
        inj = [t for t in alltruth if t['moving'] and lo <= t['snr'] < hi and t['pm'] * t['base'] / 6.15 >= 1.0]
        got = [r for r in allrec if lo <= r[3] < hi and r[0] * 1 >= 0]
        print(f"S/N {lo:>2}-{hi:<2}: recovered {len(got)} of {len(inj)} injected movers with >= 1 px shift (rough: recovered ones include smaller shifts)")
