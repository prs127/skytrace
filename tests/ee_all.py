"""Encircled energy inside the photometry aperture (r = R_AP native px) for each SPHEREx detector, from the
real DR1 ePSFs in the EPSF extension (median over 3 exposures x 9 zones). The aperture is evaluated with
photutils' subpixel method (subpixels=5 per native pixel = 1 per oversampled pixel... we use 'exact' on the
oversampled grid, which is what subpixel sampling approximates). Note: the ePSF stamp is 33x33 at 5x
oversampling (+/-3.3 native px), so EE is relative to the flux inside that stamp."""
import warnings, json, numpy as np, sys
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
from astropy.io import fits
from photutils.aperture import CircularAperture, aperture_photometry
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P
m = json.load(open("/home/claude/skytrace/frontend/data/epsindib.json"))
res = {}
for det in range(1, 7):
    urls = [e["url"] for e in m["exposures"] if e["det"] == det][:3]; vals = []
    for u in urls:
        ca = json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "key": u.split("/ibe/data/spherex/")[1]}})
        with fits.open(P._s3_path(ca), use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
            t = h["EPSF"].data; ov = h["EPSF"].header["OVSMPX"]
            for xc in (300, 1020, 1740):
                for yc in (300, 1020, 1740):
                    c = np.argmin(np.hypot(t["XCENTER"] - xc, t["YCENTER"] - yc)); psf = np.array(t["EPSF"][c], float)
                    n = psf.shape[0]; yy, xx = np.mgrid[0:n, 0:n]; cy, cx = [(a * psf).sum() / psf.sum() for a in (yy, xx)]
                    s = aperture_photometry(psf, CircularAperture([(cx, cy)], r=P.R_AP * ov), method="exact")["aperture_sum"][0]
                    vals.append(float(s) / psf.sum())
    res[det] = (float(np.median(vals)), float(np.min(vals)), float(np.max(vals)))
    print(f"D{det}: EE(r={P.R_AP}px) median {res[det][0]:.4f}  range {res[det][1]:.4f}-{res[det][2]:.4f}  ({len(vals)} PSFs)")
json.dump({str(k): round(v[0], 4) for k, v in res.items()}, open("/home/claude/skytrace/backend/aperture_ee.json", "w"))
