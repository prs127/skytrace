"""Track 2026 ED138 through SPHEREx with IRSA's Moving Object Search Tool (MOST) ephemeris:
forced photometry at the predicted position in every exposure, co-moving stacks, and a control
track offset by 90 arcsec (must show nothing). Portions generated with Claude (Anthropic)."""
import json, sys, warnings, numpy as np
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
from astropy.table import Table
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P
t = Table.read("/home/claude/skytrace/scratch/ed138/most_ed138.ecsv"); t.sort("mjd_start")
OFF = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0     # control: offset in Dec (arcsec)
NP = 31
def job(r):
    key = str(r["uri"]).split("ibe/data/spherex/")[1]; det = int(key.split("_spx")[0][-1])
    row = {"cloud_access": json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "key": key}}), "energy_bandpassname": f"SPHEREx-D{det}",
           "em_min": 0.7e-6, "em_max": 5.1e-6, "obs_id": str(r["observationid"]), "access_url": "https://irsa.ipac.caltech.edu/" + str(r["uri"]), "obs_collection": key.split("/")[0]}
    ra, de = float(r["ra_obj"]), float(r["dec_obj"]) + OFF / 3600
    grid = P.make_grid_wcs(ra, de, NP)                       # co-moving grid: object at the centre
    s = P.fetch_stamp(row, grid, NP, lambda mjd: (ra, de))
    return s
with ThreadPoolExecutor(16) as ex: stamps = [s for s in ex.map(job, t) if s is not None]
print(f"offset {OFF}\": {len(stamps)} exposures read")
m = [s.meta for s in stamps]
ok = [i for i, e in enumerate(m) if e["flux_ujy"] is not None and e["flux_err"] and not set(e["phot_flags"]) & {"saturated", "masked", "no_data"}]
f = np.array([m[i]["flux_ujy"] for i in ok]); e = np.array([m[i]["flux_err"] for i in ok]); w = np.array([m[i]["wave"] for i in ok]); mj = np.array([m[i]["mjd"] for i in ok])
# robust combination: clip >4 sigma outliers (stars crossing the aperture), then weighted mean
res = {}
for lab, sel in [("all", w > 0), ("0.75-1.6 um", w < 1.6), ("1.6-2.5 um", (w >= 1.6) & (w < 2.5)), ("2.5-3.8 um", (w >= 2.5) & (w < 3.8)), ("3.8-5.0 um", w >= 3.8)]:
    ff, ee = f[sel], e[sel]
    for _ in range(3):
        mu = np.sum(ff / ee**2) / np.sum(1 / ee**2); keep = np.abs(ff - mu) / ee < 4
        if keep.all(): break
        ff, ee = ff[keep], ee[keep]
    mu = np.sum(ff / ee**2) / np.sum(1 / ee**2); err = np.sum(1 / ee**2) ** -0.5; chi = np.sum(((ff - mu) / ee) ** 2) / max(len(ff) - 1, 1)
    res[lab] = (mu, err, len(ff), sel.sum(), chi)
    print(f"  {lab:12s}: {mu:7.1f} ± {err:5.1f} uJy  (S/N {mu/err:5.1f}; {len(ff)}/{sel.sum()} exposures kept; reduced chi2 {chi:.2f})")
imgs = np.stack([s.image for s in stamps]); med = np.nanmedian(imgs, 0)
c = NP // 2; ring = med[np.hypot(*np.mgrid[-c:c+1, -c:c+1]) > 6]; sig = 1.4826 * np.nanmedian(np.abs(ring - np.nanmedian(ring)))
print(f"  co-moving median stack: centre 3x3 mean {np.nanmean(med[c-1:c+2, c-1:c+2]) - np.nanmedian(ring):.4f} MJy/sr = {(np.nanmean(med[c-1:c+2, c-1:c+2]) - np.nanmedian(ring))/sig:.1f} x pixel noise")
np.save(f"/home/claude/skytrace/scratch/ed138/stack_off{int(OFF)}.npy", med)
json.dump({"offset": OFF, "res": {k: [float(x) for x in v] for k, v in res.items()}, "phot": [[float(a), float(b), float(c_), float(d)] for a, b, c_, d in zip(w, f, e, mj)]}, open(f"/home/claude/skytrace/scratch/ed138/phot_off{int(OFF)}.json", "w"))
