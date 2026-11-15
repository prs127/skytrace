"""IRSA serves the same catalogues through two services. Fields were first built with TAP; query_catalogs() now asks
Gator first. This compares the two on the six pre-built fields: same sources, same values.
Usage: python3 tests/catalog_services_check.py [data_dir]"""
import json, math, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend')); import pipeline as P
D = sys.argv[1] if len(sys.argv) > 1 else 'frontend/data'
bad = 0
for key in ['wise0855', 'barnard', 'epsindib', 'rwaur', 'rdra', 'm101']:
    m = json.load(open(f'{D}/{key}.json')); g = m['grid']
    radius = g['npix'] * P.PIXSCALE_ARCSEC / 3600 / math.sqrt(2) + 0.01
    new = P.query_catalogs(g['crval'][0], g['crval'][1], radius, top=int(400 * (g['npix'] / 89) ** 2)); w = new.pop('warnings')
    line = [key]
    for c in ['gaia', 'catwise', 'tmass']:
        a = {s['id']: s for s in m['catalogs'][c]}; b = {s['id']: s for s in new[c]}
        common = set(a) & set(b)
        # TAP sends binary float32 (14.895 arrives as 14.8949995), Gator sends the catalogue's printed decimals, so the
        # last stored digit can round differently: allow one unit of it (0.01 mag, 0.001 mag error, 0.001 mas/yr)
        tol = lambda f: 0.0105 if f in ('w1', 'w2', 'g') else 0.00105 if f in ('j', 'h', 'k', 'je', 'he', 'ke', 'w1e', 'w2e') else 1e-3 if f in ('pmra', 'pmdec', 'plx') else 1e-6
        worst = max(((abs(a[i][f] - b[i][f]) / tol(f), f, a[i][f], b[i][f]) for i in common for f in a[i] if isinstance(a[i][f], (int, float)) and isinstance(b[i].get(f), (int, float))), default=(0, '', 0, 0))
        maxdiff = worst[0]
        # with TOP-N cuts, sources tied with the faintest kept one may be chosen differently: allowed only at that tie
        key_f = {'gaia': 'g', 'catwise': 'w2', 'tmass': 'k'}[c]
        cut = max([s[key_f] for s in new[c] if s.get(key_f) is not None] or [0])
        odd = [s for s in list(a.values()) + list(b.values()) if s['id'] not in common]
        same = maxdiff <= 1 and all(abs((s.get(key_f) or 0) - cut) <= 0.0105 for s in odd)
        bad += not same
        line.append(f"{c}: TAP {len(a)} / Gator {len(b)} sources, {len(common)} shared{' (the rest tied at the faint cut)' if len(common) < max(len(a), len(b)) else ''}, worst difference {maxdiff:.2f} of tolerance ({worst[1]} {worst[2]} vs {worst[3]}) {'OK' if same else 'DIFFERENT'}")
    print(' | '.join(line), ('warnings: ' + '; '.join(w)) if w else '')
print('DIFFERENCES:', bad)
