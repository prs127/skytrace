"""Photometric validation of Skytrace against WISE (CatWISE2020 W1/W2) for isolated stars."""
import warnings, json, gzip, numpy as np, sys
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
from astropy.io import fits
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P
D = "/home/claude/skytrace/frontend/data/"

def encircled(det_url, r_native=2.0):
    """Fraction of ePSF flux within r native pixels, from the real SPHEREx ePSF of one exposure (centre zone)."""
    row = {"cloud_access": json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "key": det_url.split("/ibe/data/spherex/")[1]}})}
    with fits.open(P._s3_path(row["cloud_access"]), use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
        t = h["EPSF"].data; ov = h["EPSF"].header["OVSMPX"]
        c = np.argmin(np.hypot(t["XCENTER"] - 1020, t["YCENTER"] - 1020)); psf = np.array(t["EPSF"][c], float)
    n = psf.shape[0]; yy, xx = np.mgrid[0:n, 0:n]; cy, cx = [(a * psf).sum() / psf.sum() for a in (yy, xx)]
    return psf[np.hypot(xx - cx, yy - cy) <= r_native * ov].sum() / psf.sum()

def load(k):
    m = json.load(open(D + k + ".json")); n = m["grid"]["npix"]; N = len(m["exposures"])
    return m, np.frombuffer(gzip.open(D + k + ".img.bin.gz").read(), "<f2").astype(float).reshape(N, n, n)

GRID_OMEGA = 6.15 ** 2   # resampled grid pixels are 6.15" x 6.15" on the tangent plane (grid cdelt)
def phot(img, x, y, det):
    """Same aperture/annulus/subpixel method as the pipeline, on the resampled grid, ePSF-corrected."""
    f = P.aperture_phot(img.astype(np.float32), np.zeros(img.shape, np.uint8), x, y, GRID_OMEGA)["flux"]
    return None if f is None else f / P.APERTURE_EE[str(det)]

ZP = {"w1": (309.540, (3.25, 3.50)), "w2": (171.787, (4.45, 4.75))}
rows = []
for k in ["epsindib", "rwaur", "barnard", "wise0855", "m101"]:
    m, img = load(k); g = m["grid"]; w = P.make_grid_wcs(g["crval"][0], g["crval"][1], g["npix"])
    cw = m["catalogs"]["catwise"]
    for band, (zp, (l0, l1)) in ZP.items():
        sel = [i for i, e in enumerate(m["exposures"]) if e["wave"] and l0 <= e["wave"] <= l1]
        for s in cw:
            mag = s[band]
            if mag is None or not (8.5 < mag < 12.5) or np.hypot(s["pmra"], s["pmdec"]) > 100: continue
            near = [o for o in cw if o is not s and np.hypot((o["ra"] - s["ra"]) * np.cos(np.radians(s["dec"])), o["dec"] - s["dec"]) * 3600 < 25]
            if near: continue                       # isolated: no other CatWISE source within 25"
            x, y = [float(v) for v in w.world_to_pixel_values(s["ra"], s["dec"])]
            if not (17 < x < g["npix"] - 18 and 17 < y < g["npix"] - 18): continue
            f = [phot(img[i], x, y, m["exposures"][i]["det"]) for i in sel]
            f = [v for v in f if v is not None]
            if len(f) < 3: continue
            rows.append((k, band, mag, np.median(f), zp * 10 ** (-mag / 2.5) * 1e6, len(f)))
ee4 = ee6 = 1.0   # aperture correction already applied per exposure (APERTURE_EE, r=3 px)
print("Aperture correction (r=3 px) per detector:", P.APERTURE_EE)
for band, ee in (("w1", ee4), ("w2", ee6)):
    r = np.array([x[3] / x[4] for x in rows if x[1] == band])
    if not len(r): continue
    print(f"{band.upper()}: {len(r)} isolated stars; SPHEREx/WISE flux ratio (aperture-corrected) median {np.median(r):.3f}, scatter {1.4826*np.median(np.abs(r-np.median(r))):.3f}")
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(11, 4.6))
for a, band, ee, lab in ((ax[0], "w1", ee4, "WISE W1 3.4 µm vs SPHEREx 3.25–3.50 µm"), (ax[1], "w2", ee6, "WISE W2 4.6 µm vs SPHEREx 4.45–4.75 µm")):
    xs = np.array([x[4] for x in rows if x[1] == band]); ys = np.array([x[3] / ee for x in rows if x[1] == band])
    a.loglog(xs, ys, "o", ms=4, alpha=.7); lim = [min(xs.min(), ys.min()) * .7, max(xs.max(), ys.max()) * 1.4]
    a.plot(lim, lim, "k--", lw=1, label="1:1"); a.set_xlim(lim); a.set_ylim(lim)
    a.set_xlabel("WISE catalogue flux (µJy)"); a.set_ylabel("Skytrace SPHEREx flux, aperture-corrected (µJy)")
    a.set_title(f"{lab}\n{len(xs)} isolated stars, median ratio {np.median(ys/xs):.3f}", fontsize=9); a.legend()
plt.tight_layout(); plt.savefig("/home/claude/skytrace/report/figs/photval_wise.png", dpi=85)
