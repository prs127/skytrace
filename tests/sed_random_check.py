"""External check of the spectrum on any built field: SPHEREx clean values (same rules as the page: no flag, not an
outlier) against the 2MASS and WISE catalogue fluxes of the same star (independent missions). Median SPHEREx value
inside each catalogue band divided by the catalogue flux; expect ~0.85-1.15 (band average vs channel median, epochs).
Usage: python3 tests/sed_random_check.py DATA_DIR key [key ...]"""
import json, sys, math
import numpy as np
def pct50(v):
    v = sorted(v); k = (len(v) - 1) * 0.5; f = math.floor(k); c = min(f + 1, len(v) - 1); return v[f] + (v[c] - v[f]) * (k - f)
def mark_outliers(ex):   # same rule as the page (app.js markOutliers) and tests/tools_check.py
    ok = [e for e in ex if e['flux_ujy'] is not None and e['wave'] and not e.get('phot_flags')]
    for e in ex: e['_outlier'] = False
    for e in ok:
        win = [x for x in ok if abs(x['mjd'] - e['mjd']) < 15 and abs(x['wave'] - e['wave']) <= 0.04 * e['wave']]
        nb = sorted(x['flux_ujy'] for x in win if x is not e)
        if len(nb) < 4: continue
        med = pct50(nb); mad = 1.4826 * pct50(sorted(abs(v - med) for v in nb)); sig = max(mad, pct50(sorted(x['flux_err'] or 0 for x in win)))
        if abs(e['flux_ujy'] - med) > 5 * sig and abs(e['flux_ujy'] - med) > 3 * (e['flux_err'] or 0): e['_outlier'] = True
RANGES = {'2MASS J': (1.11, 1.36), '2MASS H': (1.50, 1.80), '2MASS Ks': (2.00, 2.32), 'WISE W1': (3.05, 3.80), 'WISE W2': (4.20, 5.0)}
D = sys.argv[1]
for k in sys.argv[2:]:
    m = json.load(open(f'{D}/{k}.json')); ex = m['exposures']; mark_outliers(ex)
    cl = [e for e in ex if e['flux_ujy'] is not None and not e['phot_flags'] and not e['_outlier'] and e['wave']]
    out = []
    for p in m.get('sed') or []:
        if p.get('flux_ujy') is None or p['band'] not in RANGES: continue
        lo, hi = RANGES[p['band']]; v = [e['flux_ujy'] for e in cl if lo <= e['wave'] <= hi]
        if len(v) >= 3: out.append(f"{p['band']} {np.median(v) / p['flux_ujy']:.2f} (n={len(v)})")
    print(f"{k:12s} {m['name'][:28]:28s} SPHEREx / catalogue: " + ('; '.join(out) if out else 'no catalogue star at the target, or no clean SPHEREx values in the bands'))
