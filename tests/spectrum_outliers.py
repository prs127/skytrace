"""Scan every measurement shown as clean for values that disagree with the same visit's measurements at nearly the
same wavelength (a spectrum is smooth over a few channels, and one visit lasts days, so the star cannot change).
Reports clean points more than 5 robust sigma (and more than 3 x their own error bar) from the local median.
Usage: python3 tests/spectrum_outliers.py DATA_DIR key [key ...]"""
import json, sys, numpy as np
sys.path.insert(0, 'tests'); import movers_ref as M
D, keys = sys.argv[1], sys.argv[2:]; total = 0
for k in keys:
    m = json.load(open(f'{D}/{k}.json')); ex = m['exposures']; out = []
    for v in M.visits(m):
        c = [ex[i] for i in v if ex[i]['flux_ujy'] is not None and not ex[i]['phot_flags'] and ex[i]['wave']]
        for e in c:
            nb = [x['flux_ujy'] for x in c if x is not e and abs(x['wave'] - e['wave']) <= 0.04 * e['wave']]
            if len(nb) < 4: continue
            med = np.median(nb); mad = 1.4826 * np.median(np.abs(np.array(nb) - med))
            sig = max(mad, np.median([x['flux_err'] or 0 for x in c if abs(x['wave'] - e['wave']) <= 0.04 * e['wave']]))
            if abs(e['flux_ujy'] - med) > 5 * sig and abs(e['flux_ujy'] - med) > 3 * (e['flux_err'] or 0):
                out.append((e['obs_id'], e['det'], e['wave'], e['flux_ujy'], round(med, 1), round(sig, 1)))
    total += len(out)
    print(f"{k:12s} clean {sum(1 for e in ex if e['flux_ujy'] is not None and not e['phot_flags'])}, outliers {len(out)}", *[f"\n    {o}" for o in out[:5]])
print('TOTAL', total)
