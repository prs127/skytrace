"""Cross-validate the Skytrace pipeline against the IRSA cutout tutorial on M101 (SPHEREx-D2)."""
import warnings, json, gzip, numpy as np
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
from astropy.io import fits
from astropy.table import Table
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
import sys; sys.path.insert(0, "/home/claude/skytrace/backend")
import pipeline as P
from reproject import reproject_interp

mef = "spherex_cutouts_mef.fits"
summ = Table.read(mef, hdu=1)
print(f"Tutorial MEF: {len(summ)} cutouts succeeded")
tut_ids = {u.split("/")[-1].split("_spx")[0].replace("level2_", "") : r for u, r in zip(summ["access_url"], summ)}
sky = json.load(open("/home/claude/skytrace/frontend/data/fb0924aaf63.json"))
sky_d2 = {f"{e['obs_id']}D2": e for e in sky["exposures"] if e["det"] == 2}
print(f"Skytrace M101 field: {len(sky_d2)} D2 exposures")

# 1) same exposures
common = sorted(set(tut_ids) & set(sky_d2))
print(f"[1] exposures in both: {len(common)}; tutorial-only: {len(set(tut_ids)-set(sky_d2))}; skytrace-only (failed in tutorial): {len(set(sky_d2)-set(tut_ids))}")

# 2) wavelength at the target, per exposure
dl = np.array([sky_d2[k]["wave"] - float(tut_ids[k]["central_wavelength"]) for k in common])
print(f"[2] wavelength difference Skytrace - tutorial: median {np.median(dl)*1e3:+.3f} nm, max |diff| {np.max(np.abs(dl))*1e3:.3f} nm  (target 6.15\" offset ok)")
# (Skytrace measures at the grid centre 210.80208,54.34889 vs tutorial 210.80227,54.34895: 0.6" apart)

# 3) raw pixel identity and 4) resampling vs astropy reproject, for 5 exposures
with fits.open(mef) as h:
    names = [hdu.name for hdu in h]
    g = sky["grid"]; grid = P.make_grid_wcs(g["crval"][0], g["crval"][1], g["npix"])
    maxraw, rep_stats = 0.0, []
    for k in common[:6]:
        ci = int(tut_ids[k]["cutout_index"])
        im_hdu = h[f"IMAGE{ci}"]; z_hdu = h[f"ZODI{ci}"]
        cut = im_hdu.data.astype(float); hdr = im_hdu.header
        x0, y0 = int(round(-hdr["CRPIX1A"] + 1)), int(round(-hdr["CRPIX2A"] + 1))   # cutout origin on parent (0-based)
        url = sky_d2[k]["url"]; row = {"cloud_access": json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "key": url.split("/ibe/data/spherex/")[1].join(["spherex/", ""]) if False else "dr1/" + url.split("/spherex/dr1/")[1]}})}
        with fits.open(P._s3_path(row["cloud_access"]), use_fsspec=True, fsspec_kwargs={"anon": True}) as s3:
            raw = np.asarray(s3["IMAGE"].section[y0:y0 + cut.shape[0], x0:x0 + cut.shape[1]], float)
        maxraw = max(maxraw, float(np.nanmax(np.abs(raw - cut))))
        # independent resampling of the tutorial cutout (IMAGE-ZODI) with astropy reproject
        w = WCS(hdr); sci = cut - z_hdu.data
        ref, foot = reproject_interp((sci, w), grid, shape_out=(g["npix"], g["npix"]), order="bilinear")
        i_sky = [i for i, e in enumerate(sky["exposures"]) if e["det"] == 2 and f"{e['obs_id']}D2" == k][0]
        mine = np.frombuffer(gzip.open("/home/claude/skytrace/frontend/data/fb0924aaf63.img.bin.gz").read(), "<f2").reshape(-1, g["npix"], g["npix"])[i_sky].astype(float)
        mine = mine + sky["exposures"][i_sky]["sky"]          # Skytrace subtracted a constant sky; add it back
        ok = np.isfinite(ref) & np.isfinite(mine) & (foot > 0.99)
        d = mine[ok] - ref[ok]; scale = np.nanpercentile(np.abs(ref[ok]), 99)
        rep_stats.append((k, ok.sum(), np.median(np.abs(d)), np.percentile(np.abs(d), 99), scale))
print(f"[3] raw IMAGE pixels, S3 byte-range read vs IRSA cutout service: max |diff| = {maxraw:.3g} MJy/sr")
for k, n, med, p99, sc in rep_stats:
    print(f"[4] {k}: {n} px compared; Skytrace vs astropy-reproject |diff| median {med:.4f}, 99th pct {p99:.4f} MJy/sr (bright-pixel scale {sc:.2f}) -> {100*p99/sc:.2f}% of scale")

# ---- figure for the team: native cutout | astropy reproject | Skytrace | difference
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from astropy.visualization import ImageNormalize, AsinhStretch, PercentileInterval
k = common[0]; ci = int(tut_ids[k]["cutout_index"])
with fits.open(mef) as h:
    cut = h[f"IMAGE{ci}"].data - h[f"ZODI{ci}"].data; w = WCS(h[f"IMAGE{ci}"].header)
ref, _ = reproject_interp((cut, w), grid, shape_out=(g["npix"], g["npix"]), order="bilinear")
i_sky = [i for i, e in enumerate(sky["exposures"]) if e["det"] == 2 and f"{e['obs_id']}D2" == k][0]
mine = np.frombuffer(gzip.open("/home/claude/skytrace/frontend/data/fb0924aaf63.img.bin.gz").read(), "<f2").reshape(-1, g["npix"], g["npix"])[i_sky].astype(float) + sky["exposures"][i_sky]["sky"]
norm = ImageNormalize(ref, PercentileInterval(99.5), stretch=AsinhStretch())
fig, ax = plt.subplots(1, 4, figsize=(18, 4.8))
ax[0].imshow(cut, origin="lower", cmap="viridis", norm=norm); ax[0].set_title(f"Tutorial cutout (native detector pixels)\n{k}, λ={float(tut_ids[k]['central_wavelength']):.3f} µm", fontsize=9)
ax[1].imshow(ref, origin="lower", cmap="viridis", norm=norm); ax[1].set_title("Same cutout resampled north-up\nwith astropy reproject (reference)", fontsize=9)
ax[2].imshow(mine, origin="lower", cmap="viridis", norm=norm); ax[2].set_title(f"Skytrace pipeline (S3 read, own resampler)\nλ={sky_d2[k]['wave']:.3f} µm", fontsize=9)
d = mine - ref; m = np.nanpercentile(np.abs(ref), 99.5)
im = ax[3].imshow(d, origin="lower", cmap="RdBu_r", vmin=-0.05 * m, vmax=0.05 * m); ax[3].set_title("Skytrace − reference (±5% of peak)\ngrey/white = agree; masked bad pixels differ", fontsize=9)
plt.colorbar(im, ax=ax[3], fraction=0.046, label="MJy/sr")
plt.tight_layout(); plt.savefig("/home/claude/tut/figs/cutouts/xval_m101.png", dpi=85); print("figure saved")
