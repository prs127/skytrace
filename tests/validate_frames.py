"""Independent re-computation of the images Skytrace shows, from the raw SPHEREx L2 files, with the tools used in the
IRSA "SPHEREx Source Discovery Tool" notebook (astropy + reproject). Compares, frame by frame:
  A) reproject_interp (bilinear)   -> should equal the browser frame to float16 precision (implementation check)
  B) reproject_exact (flux-conserving, the notebook's choice for images) -> same science, slightly different kernel:
     compare star aperture fluxes and pixel correlation
  C) difference image frame1 - frame0 (notebook-style subtraction of reprojected stacks)
Usage: python validate_frames.py frames.json FIELDKEY"""
import json, sys, warnings, numpy as np
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("ERROR")
from astropy.io import fits
from astropy.wcs import WCS
from reproject import reproject_interp, reproject_exact
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P

dump = json.load(open(sys.argv[1])); key = sys.argv[2]
meta = json.load(open(f"/home/claude/skytrace/frontend/data/{key}.json"))
url = {f"{e['obs_id']}|{e['det']}": e["url"] for e in meta["exposures"]}
noise = {f"{e['obs_id']}|{e['det']}": e["noise"] for e in meta["exposures"]}
g = dump["grid"]; n = g["npix"]
gw = P.make_grid_wcs(g["crval"][0], g["crval"][1], n)
assert np.allclose(gw.wcs.crpix, g["crpix"]) and np.allclose(gw.wcs.cdelt, g["cdelt"])

def one(k):
    """Independent processing of one exposure (no Skytrace code): IMAGE - ZODI, flags by name from the file's own
    MSKN keywords, sky median of clean non-source pixels, reprojection onto the Skytrace grid."""
    ca = json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "key": url[k].split("/ibe/data/spherex/")[1]}})
    with fits.open(P._s3_path(ca), use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
        hdr = h["IMAGE"].header; w = WCS(hdr)
        yy, xx = np.mgrid[0:n, 0:n]; sx, sy = w.world_to_pixel(gw.pixel_to_world(xx.ravel(), yy.ravel()))
        x0, x1 = int(max(0, np.nanmin(sx) - 20)), int(min(2040, np.nanmax(sx) + 21)); y0, y1 = int(max(0, np.nanmin(sy) - 20)), int(min(2040, np.nanmax(sy) + 21))
        img = np.asarray(h["IMAGE"].section[y0:y1, x0:x1], float); zod = np.asarray(h["ZODI"].section[y0:y1, x0:x1], float)
        flg = np.asarray(h["FLAGS"].section[y0:y1, x0:x1]).astype(np.int64); fh = h["FLAGS"].header
    bit = {str(fh[c]).strip(): int(c[4:]) for c in fh if c.startswith("MSKN")}
    m = lambda *names: sum(1 << bit[x] for x in names if x in bit)
    bad = (flg & m("TRANSIENT", "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "OUTLIER", "PERSIST")) != 0
    sci = img - zod; sci[bad | ~np.isfinite(sci)] = np.nan
    sky_ok = np.isfinite(sci) & ((flg & m("SOURCE", "OVERFLOW", "NONLINEAR", "GHOST", "GHOST_FPA", "GHOST_EXT", "STREAK", "BLOOM", "HALO", "CROSSTALK")) == 0)
    sci -= np.median(sci[sky_ok])
    sub = w[y0:y1, x0:x1]
    a, _ = reproject_interp((sci, sub), gw, shape_out=(n, n), order="bilinear")
    b, _ = reproject_exact((sci, sub), gw, shape_out=(n, n))
    return a, b

def stack(members, which):
    dets = sorted({k.split("|")[1] for k in members}); parts = []
    for d in dets:
        ks = [k for k in members if k.split("|")[1] == d]
        num = np.zeros((n, n)); den = np.zeros((n, n))
        for k in ks:
            im = CACHE[k][which]; wgt = 1 / noise[k] ** 2; ok = np.isfinite(im)
            num[ok] += wgt * im[ok]; den[ok] += wgt
        parts.append(np.where(den > 0, num / np.where(den > 0, den, 1), np.nan))
    return np.nanmean(parts, axis=0) if len(parts) > 1 else parts[0]

CACHE = {}
for f in dump["frames"]:
    for k in f["members"]:
        if k not in CACHE: CACHE[k] = one(k)
print(f"{key}: {len(dump['frames'])} frames, {len(CACHE)} exposures re-processed from raw IRSA files (det={dump['S']['det']})")

# bright isolated Gaia stars for aperture photometry on the frames
stars = []
for s in meta["catalogs"]["gaia"]:
    if s["g"] > 15 or np.hypot(s["pmra"], s["pmdec"]) > 300: continue
    x, y = gw.world_to_pixel_values(s["ra"], s["dec"])
    if 8 < x < n - 9 and 8 < y < n - 9: stars.append((float(x), float(y)))
def ap(im, x, y, r=3, ri=7, ro=12):
    yy, xx = np.mgrid[0:n, 0:n]; rr = np.hypot(xx - x, yy - y); an = (rr >= ri) & (rr <= ro) & np.isfinite(im)
    v = im[(rr <= r) & np.isfinite(im)]; return np.sum(v - np.nanmedian(im[an]))

browser = [np.array([np.nan if v is None else v for v in f["img"]], float).reshape(n, n) for f in dump["frames"]]
for i, f in enumerate(dump["frames"]):
    A = stack(f["members"], 0); B = stack(f["members"], 1); W = browser[i]
    ok = np.isfinite(A) & np.isfinite(W) & np.isfinite(B)
    nz = np.nanmedian([noise[k] for k in f["members"]]) / np.sqrt(len(f["members"]))
    dA = (W - A)[ok]
    r = np.corrcoef(W[ok], B[ok])[0, 1]
    fr = [ap(W, x, y) / ap(B, x, y) for x, y in stars[:12] if ap(B, x, y) > 0]
    faint = ok & (np.abs(A) < 20 * nz); bright = ok & (np.abs(A) >= 20 * nz)
    df = (W - A)[faint]; rel = np.abs((W - A)[bright] / A[bright])
    nanmis = int((np.isfinite(W) != np.isfinite(A)).sum())
    print(f" frame {i+1} ({len(f['members'])} exp): browser vs reproject_interp: faint pixels ({faint.sum()}) median |diff| {np.median(np.abs(df))/nz:.3f}x noise, "
          f"99th pct {np.percentile(np.abs(df), 99)/nz:.2f}x noise; bright pixels ({bright.sum()}) median rel. diff {np.median(rel):.1e}; "
          f"pixels masked in only one: {nanmis}. vs reproject_exact: correlation {r:.4f}, star aperture flux ratio median {np.median(fr):.4f} (n={len(fr)})")
if len(browser) > 1:
    D = browser[1] - browser[0]; DI = stack(dump["frames"][1]["members"], 1) - stack(dump["frames"][0]["members"], 1)
    ok = np.isfinite(D) & np.isfinite(DI)
    print(f" difference frame2 - frame1 vs notebook-style (reproject_exact stacks subtracted): correlation {np.corrcoef(D[ok], DI[ok])[0,1]:.4f}")
