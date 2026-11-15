"""Measure the target again in every SPHEREx image of already-built fields, from the original files on IRSA's AWS
bucket, with the current aperture_phot() (stricter bad-pixel check, see pipeline.aperture_phot). The image stamps,
the exposure list and everything else are left as they are; flux, error, flags and n_bad are replaced.
It also reports how well the new flux reproduces the stored one (it should, the method is unchanged).
Usage: python rephot.py DATA_DIR key [key ...]"""
import json, math, sys, time
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import pipeline as P

R = 20   # pixels around the target to read (annulus outer radius is 16)


def s3_of(url):
    # https://irsa.ipac.caltech.edu/ibe/data/spherex/<release>/level2/... -> s3://nasa-irsa-spherex/<release>/level2/...
    return "s3://nasa-irsa-spherex/" + url.split("/ibe/data/spherex/", 1)[1]


def measure(e, t):
    for attempt in range(4):
        try:
            with fits.open(s3_of(e["url"]), use_fsspec=True, fsspec_kwargs={**P.S3_KW, "default_block_size": 2**16}, lazy_load_hdus=True) as h:
                hdr = h["IMAGE"].header; w = WCS(hdr); ny, nx = hdr["NAXIS2"], hdr["NAXIS1"]
                mjd = float(hdr["MJD-AVG"])
                ra, dec = P.apparent_position(t["ra"], t["dec"], t["pmra"], t["pmdec"], t.get("plx") or 0.0, t["epoch_mjd"], mjd)
                tx, ty = w.world_to_pixel(SkyCoord(float(ra), float(dec), unit="deg"))
                x0 = int(max(0, math.floor(tx) - R)); x1 = int(min(nx, math.floor(tx) + R + 1))
                y0 = int(max(0, math.floor(ty) - R)); y1 = int(min(ny, math.floor(ty) + R + 1))
                img = np.asarray(h["IMAGE"].section[y0:y1, x0:x1], dtype=np.float32)
                var = np.asarray(h["VARIANCE"].section[y0:y1, x0:x1], dtype=np.float32)
                flg = np.asarray(h["FLAGS"].section[y0:y1, x0:x1]).astype(np.int64)
                MK = P.masks_from_header(h["FLAGS"].header)
            break
        except Exception as exc:
            if attempt == 3:
                return {"error": str(exc)[:200]}
            time.sleep(2 * (attempt + 1))
    det = e["det"]
    bad = ((flg & MK["BAD"]) != 0) | ~np.isfinite(img)
    catsrc = np.zeros_like(flg, dtype=np.uint8)
    catsrc[(flg & MK["SAT"]) != 0] |= P.CAT_SAT; catsrc[bad] |= P.CAT_BAD
    catsrc[(flg & MK["ART"]) != 0] |= P.CAT_ART; catsrc[(flg & MK["SRC"]) != 0] |= P.CAT_SRC
    omap = P.sapm(det, P.release_of(e["collection"]))[y0:y1, x0:x1]
    sci = np.where(np.isfinite(img), img, np.nan).astype(np.float32)
    ph = P.aperture_phot(sci, catsrc, float(tx) - x0, float(ty) - y0, omap, var=var, nbad_map=(flg & MK["NB_BAD"]) != 0)
    ee = P.APERTURE_EE.get(str(det), 1.0)
    if ph["flux"] is not None: ph["flux"] = round(ph["flux"] / ee, 3)
    if ph["err"] is not None: ph["err"] = round(ph["err"] / ee, 3)
    return ph


def run(data, key):
    path = f"{data}/{key}.json"; m = json.load(open(path)); ex = m["exposures"]; t = m["target"]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=32) as pool:
        res = list(pool.map(lambda e: measure(e, t), ex))
    errs = [r for r in res if "error" in r]
    if errs:
        print(f"[FAIL] {key}: {len(errs)} images could not be read ({errs[0]['error']}); field left unchanged"); return False
    dflux, newly, cleared = [], [], 0
    for e, r in zip(ex, res):
        if e["flux_ujy"] is not None and r["flux"] is not None:
            dflux.append(abs(r["flux"] - e["flux_ujy"]) / max(abs(e["flux_ujy"]), 1e-9))
        was, now = bool(e["phot_flags"]), bool(r["flags"])
        if now and not was: newly.append((e["obs_id"], e["det"], e["wave"], e["flux_ujy"], r["flags"]))
        if was and not now: cleared += 1
        e["flux_ujy"], e["flux_err"], e["phot_flags"], e["n_bad"] = r["flux"], r["err"], r["flags"], r.get("n_bad", 0)
    m["photometry"] = P.PHOT_DESC
    json.dump(P.sanitize(m), open(path, "w"), separators=(",", ":"), allow_nan=False)
    dflux = np.array(dflux)
    print(f"[OK] {key}: {len(ex)} images re-measured in {time.time() - t0:.0f}s; flux reproduced to median {np.median(dflux):.1e}, "
          f"max {dflux.max():.1e} (relative); newly flagged {len(newly)}, flag cleared {cleared}", flush=True)
    for n in sorted(newly, key=lambda x: -abs(x[3] or 0))[:8]:
        print(f"      newly flagged: {n[0]} D{n[1]} {n[2]} um, stored flux {n[3]} uJy -> flags {n[4]}")
    return True


if __name__ == "__main__":
    for k in sys.argv[2:]:
        run(sys.argv[1], k)
