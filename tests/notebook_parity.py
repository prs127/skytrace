"""Parity: Skytrace aperture_phot vs the IRSA notebook's own functions (sa_mjy_scale_map + extract_photometry
+ variance sum), on identical native SPHEREx pixels, same aperture (r=3), annulus (7-16), solid-angle maps."""
import warnings, json, sys, numpy as np
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
from photutils.aperture import CircularAperture, aperture_photometry
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P
sys.path.insert(0, "/home/claude/tut/irsa-tutorials/tutorials/spherex/spherex_source_discovery")
from spherex_source_discovery_tool import aperture_photometry as NB
tgt = sys.argv[1] if len(sys.argv) > 1 else "rdra"
import os
m = json.load(open(os.path.join(os.environ.get("SKYTRACE_DATA", "/home/claude/skytrace/frontend/data"), f"{tgt}.json")))
ex = m["exposures"]; sel = [ex[i] for i in np.linspace(0, len(ex) - 1, 12).astype(int)]
import targets
T = [t for t in targets.TARGETS if t.key == tgt][0]
rows = []; zrat = []; agree = []
for e in sel:
    ca = json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "key": e["url"].split("/ibe/data/spherex/")[1]}})
    with fits.open(P._s3_path(ca), use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
        hdr = h["IMAGE"].header; w = WCS(hdr)
        ra, dec = P.propagate(T.ra, T.dec, T.pmra, T.pmdec, T.epoch_mjd, float(hdr["MJD-AVG"]))
        tx, ty = w.world_to_pixel(SkyCoord(ra, dec, unit="deg"))
        x0, y0 = int(tx) - 25, int(ty) - 25
        if x0 < 0 or y0 < 0 or x0 + 51 > 2040 or y0 + 51 > 2040: continue
        img = np.asarray(h["IMAGE"].section[y0:y0+51, x0:x0+51], float)
        var = np.asarray(h["VARIANCE"].section[y0:y0+51, x0:x0+51], float)
        zod = np.asarray(h["ZODI"].section[y0:y0+51, x0:x0+51], float)
        flg = np.asarray(h["FLAGS"].section[y0:y0+51, x0:x0+51]).astype(np.int64)
        fh = h["FLAGS"].header
        det = int(hdr["DETECTOR"])
    sa = P.sapm(det)[y0:y0+51, x0:x0+51]
    pos = [(float(tx) - x0, float(ty) - y0)]
    # --- notebook path (its own code) ---
    scale = sa * NB.ARCSEC2_TO_SR * 1e6 * 1e3                # mJy/pix per MJy/sr  (sa_mjy_scale_map formula)
    tab = NB.extract_photometry(img * scale, pos, [3.0], annulus_rad_in=7, annulus_rad_out=16)
    nb_flux = float(tab["aper_sum_bkgsub_r3.0"][0]) * 1e3    # mJy -> uJy
    v = var * scale ** 2
    nb_err = float(np.sqrt(aperture_photometry(v, CircularAperture(pos, r=3.0), mask=~np.isfinite(v), method="subpixel", subpixels=5)["aperture_sum"][0])) * 1e3
    # notebook n_bad: sum over bad_flags of extract_dqf counts (center method)
    fd = {fh[k]: int(k[4:]) for k in fh if k.startswith("MSKN")}
    nb_bad = sum(float(NB.extract_dqf((flg & (1 << fd[f])) > 0, pos, [3.0])["aperture_sum_r3.0"][0]) for f in P._GROUPS["NB_BAD"] if f in fd)
    # --- Skytrace (raw IMAGE, as the notebook) ---
    MK = P.masks_from_header(fh)
    r = P.aperture_phot(img, np.zeros(img.shape, np.uint8), pos[0][0], pos[0][1], sa, var=var, nbad_map=(flg & MK["NB_BAD"]) != 0)
    # --- Skytrace as run in the pipeline (zodi model subtracted first) ---
    rz = P.aperture_phot(img - zod, np.zeros(img.shape, np.uint8), pos[0][0], pos[0][1], sa, var=var)
    zrat.append(rz["flux"] / r["flux"] if r["flux"] else np.nan)
    agree.append((nb_bad >= 1) == (r["n_bad"] >= 1))
    if r["flux"] is None:
        print(f"{e['obs_id']:>28} D{det} notebook {nb_flux:12.3f}  skytrace -- withheld, flags {r['flags']} (NaN pixels: {int((~np.isfinite(img)).sum())})"); continue
    rows.append((e["obs_id"], det, nb_flux, r["flux"], nb_err, r["err"]))
    print(f"{e['obs_id']:>28} D{det} notebook {nb_flux:12.3f} ± {nb_err:8.3f}  skytrace {r['flux']:12.3f} ± {r['err']:8.3f}  ratio {r['flux']/nb_flux:.6f}")
rat = np.array([r[3] / r[2] for r in rows]); erat = np.array([r[5] / r[4] for r in rows])
print(f"{tgt}: bad-pixel decision (n_bad>=1) agrees with notebook extract_dqf in {sum(agree)}/{len(agree)}; zodi pre-subtraction changes flux by max {np.nanmax(np.abs(np.array(zrat)-1)):.2e}")
print(f"\n{tgt}: n={len(rows)}  flux ratio max|1-r| = {np.max(np.abs(1-rat)):.2e}   err ratio max|1-r| = {np.max(np.abs(1-erat)):.2e}")
