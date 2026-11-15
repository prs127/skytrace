"""Reference (Python) implementation of Skytrace's moving-object finder, written independently of the
browser code so the two can be compared field by field (tests/movers_parity.py).

Method (multi-visit linear-motion test):
 1. One stack per visit: per-detector inverse-variance mean, detectors averaged with equal weight,
    mesh-median background removed (same as the viewer's visit frames).
 2. Detect point sources in each visit stack: 3x3 local maxima of a Gaussian-smoothed (sigma = 1 px) image
    above 5 sigma (robust MAD noise of the smoothed image). Any saturated, artefact or missing pixel
    within 2 px, or the image edge within 3 px, rejects the detection.
 3. Gaussian-weighted centroid (sigma_w = 1.2 px, 7x7 window). Position error per detection
    sigma_pos = sqrt(a^2 + (b/SNR)^2), with a and b measured on the field itself from Gaia DR3 stars whose
    motion over the baseline is < 0.05 px (they should not move, so their scatter is the measurement error).
 4. Stationary sources first: a detection with matches within 3 sigma in at least two other visits, whose
    positions fit a fixed point (chi2/dof < 4), is stationary and removed.
 5. Movers: remaining detections are linked across visits by straight-line motion (any pair of visits as a
    seed, up to 30"/yr), every other visit must contain a detection near the predicted position. A track
    needs >= 3 visits; it is reported when the straight line fits (chi2/dof < 4), the motion is >= 5 sigma
    (sqrt(chi2_fixed - chi2_line)), the total shift is >= 0.5 px, and the flux changes by less than x3.
 6. Each track is compared with Gaia DR3 (positions moved to every visit date with proper motion and
    parallax): a match labels it as a known mover and gives the catalogue motion to compare with.
"""
import gzip, json, math, sys
import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter

CAT_SAT, CAT_BAD, CAT_ART = 1, 2, 4
DET_GROUPS = {'lw': [5, 6], 'sw': [1, 2, 3]}
VMAX_ARCSEC_YR, SNR_SEED, SNR_CONFIRM, MOTION_SIG, STILL_SIG, MIN_SHIFT_PX, CHI2_MAX = 30.0, 5.0, 3.5, 5.0, 3.0, 0.5, 4.0

def load(data, key):
    m = json.load(open(f'{data}/{key}.json'))
    n, npx = len(m['exposures']), m['grid']['npix']
    img = np.frombuffer(gzip.open(f'{data}/{key}.img.bin.gz').read(), dtype='<f2').astype(np.float32).reshape(n, npx, npx)
    cat = np.frombuffer(gzip.open(f'{data}/{key}.cat.bin.gz').read(), dtype=np.uint8).reshape(n, npx, npx)
    return m, img, cat

def visits(m, win=30, span=60):
    ex = m['exposures']; order = sorted(range(len(ex)), key=lambda i: ex[i]['mjd'])
    clusters, last = [], -1e9
    for i in order:
        if ex[i]['mjd'] - last > win: clusters.append([])
        clusters[-1].append(i); last = ex[i]['mjd']
    out = []
    for c in clusters:
        t0 = ex[c[0]]['mjd']; ln = ex[c[-1]]['mjd'] - t0; nch = max(1, math.ceil(ln / span - 1e-9))
        parts = [[] for _ in range(nch)]
        for i in c: parts[min(nch - 1, int((ex[i]['mjd'] - t0) // (ln / nch or 1)))].append(i)
        out += [p for p in parts if p]
    return out

def det_ok(m, i, det):
    d = m['exposures'][i]['det']
    if det in ('all', 'rgb'): return True
    return d in DET_GROUPS[det] if det in DET_GROUPS else d == int(det)

def coadd(m, img, cat, members, medn):
    s = np.zeros(img.shape[1:]); ws = np.zeros_like(s); cov = np.zeros_like(s); nsat = np.zeros_like(s); nart = np.zeros_like(s)
    for i in members:
        nz = m['exposures'][i]['noise'] or 0; w = 1 / (nz if nz > 0 else medn) ** 2
        c = cat[i]; bad = (c & CAT_BAD) > 0; sat = (c & CAT_SAT) > 0
        cov += np.where(bad, sat, 1); nsat += sat; nart += np.where(bad, 0, (c & CAT_ART) > 0)
        v = img[i]; ok = ~bad & np.isfinite(v)
        s += np.where(ok, w * v, 0); ws += np.where(ok, w, 0)
    out = np.where(ws > 0, s / np.where(ws > 0, ws, 1), np.nan)
    fl = np.where(ws > 0, 0, CAT_BAD) | np.where((cov > 0) & (nsat * 2 >= cov), CAT_SAT, 0) | np.where((cov > 0) & (nart * 2 >= cov), CAT_ART, 0)
    return out, fl.astype(np.uint8)

def balanced(m, img, cat, members, medn):
    dets = sorted({m['exposures'][i]['det'] for i in members})
    if len(dets) < 2: return coadd(m, img, cat, members, medn)
    parts = [coadd(m, img, cat, [i for i in members if m['exposures'][i]['det'] == d], medn) for d in dets]
    stack = np.array([p[0] for p in parts]); k = np.isfinite(stack).sum(0)
    out = np.where(k > 0, np.nansum(stack, 0) / np.maximum(k, 1), np.nan)
    sat = sum(((p[1] & CAT_SAT) > 0).astype(int) for p in parts); art = sum(((p[1] & CAT_ART) > 0).astype(int) for p in parts)
    fl = np.where(k > 0, 0, CAT_BAD) | np.where(sat * 2 >= len(parts), CAT_SAT, 0) | np.where(art * 2 >= len(parts), CAT_ART, 0)
    return out, fl.astype(np.uint8)

def flatten(a, B=15):
    n = a.shape[0]; nb = math.ceil(n / B); mesh = np.full((nb, nb), np.nan)
    for by in range(nb):
        for bx in range(nb):
            v = a[by * B:(by + 1) * B, bx * B:(bx + 1) * B].ravel(); v = np.sort(v[np.isfinite(v)])
            if len(v) < 20: continue
            med = np.percentile(v, 50); sig = 1.4826 * np.percentile(np.sort(np.abs(v - med)), 50)
            kept = v[np.abs(v - med) < 3 * sig]; mesh[by, bx] = np.percentile(kept, 50) if len(kept) > 10 else med
    g = np.nanmedian(mesh) if np.isfinite(mesh).any() else 0; mesh[~np.isfinite(mesh)] = g
    y = np.clip((np.arange(n) + .5) / B - .5, 0, nb - 1); y0 = np.floor(y).astype(int); y1 = np.minimum(nb - 1, y0 + 1); ty = y - y0
    x0, x1, tx = y0, y1, ty
    bg = ((mesh[y0][:, x0] * (1 - tx) + mesh[y0][:, x1] * tx) * (1 - ty)[:, None] + (mesh[y1][:, x0] * (1 - tx) + mesh[y1][:, x1] * tx) * ty[:, None])
    return a - bg

def detect(stack, fl):
    n = stack.shape[0]; z = np.where(np.isfinite(stack), stack, 0.0)
    sm = gaussian_filter(z, 1.0, mode='constant'); v = sm[np.isfinite(stack)]
    med = np.median(v); sig = 1.4826 * np.median(np.abs(v - med))
    noise = np.where(np.isfinite(stack), stack, np.nan); nmed = np.nanmedian(noise); nsig = 1.4826 * np.nanmedian(np.abs(noise - nmed))
    peak = (sm == maximum_filter(sm, size=3)) & ((sm - med) / sig >= SNR_CONFIRM)
    badzone = maximum_filter(((fl & (CAT_SAT | CAT_ART | CAT_BAD)) > 0).astype(np.uint8), size=5) > 0
    # the wings, ghosts and diffraction features of a saturated star change with the spacecraft roll between
    # visits and can mimic motion: nothing within 4 px of a saturated pixel is used
    satzone = maximum_filter(((fl & CAT_SAT) > 0).astype(np.uint8), size=9) > 0
    out = []
    yy, xx = np.mgrid[-3:4, -3:4]
    for y, x in zip(*np.nonzero(peak)):
        if x < 3 or y < 3 or x > n - 4 or y > n - 4 or badzone[y, x] or satzone[y, x]: continue
        cx, cy = float(x), float(y)
        for _ in range(4):
            ix, iy = int(round(cx)), int(round(cy))
            if ix < 3 or iy < 3 or ix > n - 4 or iy > n - 4: break
            w = z[iy - 3:iy + 4, ix - 3:ix + 4] * np.exp(-((xx + ix - cx) ** 2 + (yy + iy - cy) ** 2) / (2 * 1.2 ** 2))
            w = np.clip(w, 0, None); s = w.sum()
            if s <= 0: break
            cx, cy = (w * (xx + ix)).sum() / s, (w * (yy + iy)).sum() / s
        r2 = (np.mgrid[0:n, 0:n][1] - cx) ** 2 + (np.mgrid[0:n, 0:n][0] - cy) ** 2
        flux = float(z[r2 <= 4].sum())
        out.append(dict(x=cx, y=cy, snr=float((sm[y, x] - med) / sig), flux=flux))
    return out

def run(data, key, det='all', verbose=True):
    m, img, cat = load(data, key)
    ex = m['exposures']; noises = sorted(e['noise'] for e in ex if (e['noise'] or 0) > 0); medn = noises[len(noises) // 2] if noises else 1.0   # as the page
    V = [[i for i in v if det_ok(m, i, det)] for v in visits(m)]; V = [v for v in V if v]
    t = np.array([np.mean([ex[i]['mjd'] for i in v]) for v in V])
    stacks = []
    for v in V:
        s, f = balanced(m, img, cat, v, medn); stacks.append((flatten(s), f))
    D = [detect(s, f) for s, f in stacks]
    g = m['grid']
    from astropy.wcs import WCS
    w = WCS(naxis=2); w.wcs.ctype = ['RA---TAN', 'DEC--TAN']; w.wcs.crval = g['crval']; w.wcs.crpix = g['crpix']; w.wcs.cdelt = g['cdelt']
    sys.path.insert(0, '/home/claude/skytrace/backend'); from pipeline import apparent_position
    def gaia_xy(s, mjd):
        ra, de = apparent_position(s['ra'], s['dec'], s.get('pmra') or 0, s.get('pmdec') or 0, s.get('plx') or 0, 57388.0, mjd)
        x, y = w.world_to_pixel_values(ra, de); return float(x) - 0, float(y) - 0
    # pixel convention: crpix is 1-based in FITS; the viewer uses 0-based (crpix-1). world_to_pixel_values is 0-based.
    gaia = m['catalogs']['gaia']
    base = (t[-1] - t[0]) / 365.25 if len(t) > 1 else 0
    # 3. relative astrometry and position errors, measured on this field from Gaia DR3 stars that do not move
    #    measurably over the baseline (< 0.05 px): (a) remove each visit's median offset (registration),
    #    (b) fit sigma_pos^2 = a^2 + b^2/SNR^2 to robust (MAD) scatter in SNR bins.
    still = [s for s in gaia if math.hypot(s.get('pmra') or 0, s.get('pmdec') or 0) / 1000 * max(base, 0.1) / 6.15 < 0.05 and (s.get('plx') or 0) < 20]
    match = []
    for s in still:
        for k, dk in enumerate(D):
            gx, gy = gaia_xy(s, t[k])
            best = min(dk, key=lambda d: (d['x'] - gx) ** 2 + (d['y'] - gy) ** 2, default=None)
            if best and best['snr'] >= SNR_SEED and math.hypot(best['x'] - gx, best['y'] - gy) < 1.0: match.append((k, best['x'] - gx, best['y'] - gy, best['snr']))
    off = np.zeros((len(D), 2))
    for k in range(len(D)):
        r = np.array([(dx, dy) for kk, dx, dy, sn in match if kk == k and sn >= 15])
        if len(r) >= 5: off[k] = np.median(r, 0)
    for k, dk in enumerate(D):
        for d in dk: d['x'] -= off[k][0]; d['y'] -= off[k][1]
    a_, b_ = 0.10, 1.0
    if len(match) >= 30:
        r = np.array([(dx - off[k][0], dy - off[k][1], sn) for k, dx, dy, sn in match])
        edges = np.unique(np.percentile(r[:, 2], np.linspace(0, 100, 6)))
        xs, ys = [], []
        for lo, hi in zip(edges[:-1], edges[1:]):
            q = r[(r[:, 2] >= lo) & (r[:, 2] <= hi)]
            if len(q) < 6: continue
            sig = 1.4826 * np.median(np.abs(np.concatenate([q[:, 0], q[:, 1]]) - 0))
            xs.append(1 / np.median(q[:, 2]) ** 2); ys.append(sig ** 2)
        if len(xs) >= 3:
            coef = np.polyfit(xs, ys, 1)
            a_ = math.sqrt(max(coef[1], 0.03 ** 2)); b_ = math.sqrt(max(coef[0], 0.3 ** 2))
    res = match
    sp = lambda d: math.hypot(a_, b_ / d['snr'])
    for k, dk in enumerate(D):
        for d in dk: d['k'] = k; d['s'] = sp(d)
    # 4-5. link detections across visits with straight-line motion (a still star is the case v = 0), then
    #      classify each track by comparing a fixed-point fit with a straight-line fit.
    vmax = VMAX_ARCSEC_YR / 6.15 / 365.25  # px/day
    npx = stacks[0][0].shape[0]
    def fitline(P, tt, W):
        tm = tt.mean(); A = np.vstack([np.ones_like(tt), tt - tm]).T * np.sqrt(W)[:, None]
        cx_, *_ = np.linalg.lstsq(A, np.array([p['x'] for p in P]) * np.sqrt(W), rcond=None)
        cy_, *_ = np.linalg.lstsq(A, np.array([p['y'] for p in P]) * np.sqrt(W), rcond=None)
        chil = float(sum(((p['x'] - cx_[0] - cx_[1] * (tt[q] - tm)) ** 2 + (p['y'] - cy_[0] - cy_[1] * (tt[q] - tm)) ** 2) / p['s'] ** 2 for q, p in enumerate(P)))
        mx, my = np.average([p['x'] for p in P], weights=W), np.average([p['y'] for p in P], weights=W)
        chi0 = float(sum(((p['x'] - mx) ** 2 + (p['y'] - my) ** 2) / p['s'] ** 2 for p in P))
        return cx_, cy_, chil, chi0, tm
    tracks = []
    for i in range(len(D)):
        for j in range(i + 1, len(D)):
            dt = t[j] - t[i]
            for ja, a in enumerate(D[i]):
                if a['snr'] < SNR_SEED: continue
                for jb, b in enumerate(D[j]):
                    if b['snr'] < SNR_SEED: continue
                    if math.hypot(b['x'] - a['x'], b['y'] - a['y']) > vmax * dt + 3 * math.hypot(a['s'], b['s']): continue
                    if max(a['flux'], b['flux']) > 3 * max(min(a['flux'], b['flux']), 1e-9): continue
                    vx, vy = (b['x'] - a['x']) / dt, (b['y'] - a['y']) / dt
                    pts = [(i, ja, a), (j, jb, b)]; covered = 2
                    for k in range(len(D)):
                        if k in (i, j): continue
                        px, py = a['x'] + vx * (t[k] - t[i]), a['y'] + vy * (t[k] - t[i])
                        if not (3 <= px <= npx - 4 and 3 <= py <= npx - 4): continue
                        covered += 1
                        c = [(math.hypot(e['x'] - px, e['y'] - py), jj, e) for jj, e in enumerate(D[k])]
                        c = [q for q in c if q[0] < 3 * math.hypot(q[2]['s'], a['s'], b['s'])]
                        if c: q = min(c, key=lambda z: z[0]); pts.append((k, q[1], q[2]))
                    if len(pts) < 3: continue
                    P = [p[2] for p in pts]; tt = np.array([t[p[0]] for p in pts]); W = np.array([1 / p['s'] ** 2 for p in P])
                    cx_, cy_, chil, chi0, tm = fitline(P, tt, W)
                    dof = 2 * len(P) - 4; shift = math.hypot(cx_[1], cy_[1]) * (tt.max() - tt.min())
                    fl = [p['flux'] for p in P]
                    sv = 1 / math.sqrt(float((W * (tt - tm) ** 2).sum()))   # 1-sigma error of each velocity component, px/day
                    tracks.append(dict(sv=sv, pts=[(p[0], p[1]) for p in pts], n=len(P), covered=covered, sig=math.sqrt(max(chi0 - chil, 0)), chi=chil / max(dof, 1),
                                       vx=cx_[1], vy=cy_[1], x=cx_[0], y=cy_[0], tm=tm, shift=shift, snr=min(p['snr'] for p in P),
                                       fluxok=max(fl) <= 3 * max(min(fl), 1e-9)))
    # best explanation first: more visits, then better straight-line fit
    tracks.sort(key=lambda z: (-z['n'], z['chi']))
    used = set(); chosen = []
    for tr in tracks:
        if any(p in used for p in tr['pts']): continue
        if tr['chi'] >= CHI2_MAX: continue
        used.update(tr['pts']); chosen.append(tr)
    stationary = [tr for tr in chosen if tr['sig'] < STILL_SIG]
    # blends: a neighbour within 2 px in the same visit pulls the centroid differently from visit to visit
    # (different wavelength mixes), which can fake motion; such tracks are not reported
    def blended(tr):
        for k, j in tr['pts']:
            d = D[k][j]
            if any(jj != j and math.hypot(e['x'] - d['x'], e['y'] - d['y']) < 2.0 for jj, e in enumerate(D[k])): return True
        return False
    for tr in chosen: tr['blend'] = blended(tr)
    # a real object is seen in (almost) every visit that covers its path: at least 2/3 of them
    tracks = [tr for tr in chosen if tr['sig'] >= MOTION_SIG and tr['shift'] >= MIN_SHIFT_PX and tr['fluxok'] and tr['n'] >= math.ceil(2 * tr['covered'] / 3) and not tr['blend']]
    out = []
    for tr in tracks:
        ra0, de0 = w.pixel_to_world_values(tr['x'], tr['y']); ra1, de1 = w.pixel_to_world_values(tr['x'] + tr['vx'] * 365.25, tr['y'] + tr['vy'] * 365.25)
        pmra = (ra1 - ra0) * math.cos(math.radians(de0)) * 3.6e6; pmdec = (de1 - de0) * 3.6e6
        known = None
        for s in gaia:
            if all(math.hypot(*(np.array(gaia_xy(s, t[p[0]])) - np.array([D[p[0]][p[1]]['x'], D[p[0]][p[1]]['y']]))) < 1.5 for p in tr['pts']):
                known = s; break
        T = m['target']; tgt = None
        tx = [w.world_to_pixel_values(*apparent_position(T['ra'], T['dec'], T.get('pmra') or 0, T.get('pmdec') or 0, T.get('plx') or 0, T.get('epoch_mjd', 57388.0), t[p[0]])) for p in tr['pts']]
        if all(math.hypot(float(x) - D[p[0]][p[1]]['x'], float(y) - D[p[0]][p[1]]['y']) < 1.5 for (x, y), p in zip(tx, tr['pts'])): tgt = T
        epm = tr['sv'] * 365.25 * 6.15   # arcsec/yr
        out.append(dict(covered=tr['covered'], epm=epm, target=(T.get('name') or m['name']) if tgt else None, target_pm=(math.hypot(T.get('pmra') or 0, T.get('pmdec') or 0) / 1000 if tgt else None),
                        ra=float(ra0), dec=float(de0), pmra=pmra, pmdec=pmdec, pm=math.hypot(pmra, pmdec) / 1000, n=tr['n'], sig=tr['sig'], chi=tr['chi'],
                        shift=tr['shift'], snr=tr['snr'], gaia=(known['id'] if known else None),
                        gaia_pm=(math.hypot(known.get('pmra') or 0, known.get('pmdec') or 0) / 1000 if known else None)))
    if verbose:
        print(f'{key:9s} det={det:4s} visits={len(V)} dets/visit={[len(d) for d in D]} still tracks={len(stationary)} chosen={len(chosen)} a={a_:.3f}px b={b_:.2f} calib={len(res)} movers={len(out)}')
        for o in out:
            print(f"   {o['ra']:.5f} {o['dec']:+.5f}  pm={o['pm']:.2f}±{o['epm']:.2f}\"/yr ({o['pmra']:+.0f},{o['pmdec']:+.0f} mas/yr) n={o['n']}/{o['covered']} {o['sig']:.1f}sig chi2/dof={o['chi']:.2f} shift={o['shift']:.2f}px snr>={o['snr']:.1f} "
                  + (f"Gaia {o['gaia']} pm {o['gaia_pm']:.2f}\"/yr" if o['gaia'] else 'no Gaia match') + (f" | target {o['target']} catalogue pm {o['target_pm']:.2f}\"/yr" if o['target'] else ''))
    return out, dict(a=a_, b=b_, ncal=len(res), visits=len(V))

if __name__ == '__main__':
    data = sys.argv[1] if len(sys.argv) > 1 else 'frontend/data'
    for key, det in [('wise0855', 'lw'), ('wise0855', 'all'), ('epsindib', 'all'), ('barnard', 'all'), ('rwaur', 'all'), ('rdra', 'all'), ('m101', 'all'), ('m101', '2')]:
        run(data, key, det)
