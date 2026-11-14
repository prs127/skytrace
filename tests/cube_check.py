"""Independent check of Skytrace spectra + official channel assignment against the SPHEREx DR1 all-sky
cube (spherex_dr1_cube HiPS tiles, the product used in IRSA's HiPS notebook)."""
import warnings, json, numpy as np, sys, pyvo
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
sys.path.insert(0, "/home/claude/skytrace/backend")
import pipeline as P
from astropy.io import fits
from astropy.wcs import WCS
from astropy.table import Table
import hpgeom as hp, posixpath

# 1) pick isolated, unsaturated Gaia stars with a CatWISE counterpart in the rebuilt fields
def sep(a, b): return np.hypot((a["ra"] - b["ra"]) * np.cos(np.radians(a["dec"])), a["dec"] - b["dec"]) * 3600
STARS = []
for key in ["wise0855", "epsindib", "rwaur", "barnard"]:
    try: m = json.load(open(f"/home/claude/skytrace/frontend/data/{key}.json"))
    except FileNotFoundError: continue
    cw = m["catalogs"]["catwise"]; ga = m["catalogs"]["gaia"]
    for s in cw:
        if s["w1"] is None or not (9.0 < s["w1"] < 11.5): continue
        if any(sep(s, o) < 25 for o in cw if o is not s): continue
        g = [x for x in ga if sep(s, x) < 3]
        if len(g) != 1: continue
        if any(sep(g[0], x) < 15 and x["g"] < g[0]["g"] + 3 for x in ga if x is not g[0]): continue
        STARS.append((key, s, g[0]))
print(f"{len(STARS)} candidate stars:", [(k, gg['id'], gg['g']) for k, _, gg in STARS[:4]])
for n, (key, s, g) in enumerate(STARS[:2]):
    print(f"\n=== star {n+1}: {key} field, Gaia DR3 {g['id']} G={g['g']}, W1={s['w1']}")
    # 2) Skytrace pipeline on this star (native-pixel photometry, official channels)
    t = P.Target("star", "check star", g["ra"], g["dec"], g["pmra"], g["pmdec"], 57388.0)
    pkg = P.build_field(t, npix=31, workers=16, collections=["spherex_dr1", "spherex_qr3"], progress=lambda x: None)
    ex = [e for e in pkg["meta"]["exposures"] if e["flux_ujy"] is not None and not e["phot_flags"]]
    print(f"Skytrace: {len(ex)} clean exposures")
    by = {}
    for e in ex: by.setdefault(e["band"], []).append(e["flux_ujy"])
    sky = {b: np.median(v) for b, v in by.items()}

    # 3) official DR1 all-sky cube photometry at the same position
    Norder = 5; nside = 2 ** Norder
    ipix = hp.angle_to_pixel(nside, g["ra"], g["dec"], nest=True, lonlat=True); dirid = (ipix // 10000) * 10000
    url = posixpath.join("https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/hips5_cube/hips_20261026", f"Norder{Norder}", f"Dir{dirid}", f"Npix{ipix}_cube.fits")
    with fits.open(url, use_fsspec=True, lazy_load_hdus=True) as h:
        w = WCS(h["IMAGE"].header, fobj=h).celestial
        x, y = [float(v) for v in w.world_to_pixel_values(g["ra"], g["dec"])]
        xi, yi = int(round(x)), int(round(y)); R = 12
        cube = np.asarray(h["IMAGE"].section[:, yi - R:yi + R + 1, xi - R:xi + R + 1], float)
        ch = Table(h["SPECTRAL_CHANNELS"].data)
        # True sky area of a HEALPix order-14 pixel (tile order 5 + 9). NOTE: the HPX projection-plane area
        # (CDELT^2) is 3*pi/8 = 1.178x larger and must NOT be used for flux (found during verification).
        pix = np.sqrt(4 * np.pi / (12 * 4 ** 14)) * 206264.806
    print(f"DR1 cube tile {url.split('/')[-1]}, pixel scale {pix:.2f}\"")
    yy, xx = np.mgrid[-R:R + 1, -R:R + 1]; rr = np.hypot(xx - (x - xi), yy - (y - yi))
    omega = (pix / 206264.806) ** 2
    def cube_phot(r_ap):
        out = []
        for k in range(cube.shape[0]):
            im = cube[k]; an = (rr > 6) & (rr < 10) & np.isfinite(im)
            out.append((np.nansum(im[rr <= r_ap] - np.nanmedian(im[an]))) * 1e12 * omega)
        return np.array(out)
    f3, f4 = cube_phot(3.0), cube_phot(4.0)
    print(f"cube curve of growth r=3 vs r=4 cube px: median ratio {np.nanmedian(f3/f4):.3f} (1.0 = aperture contains ~all light)")
    ratios = [(b, sky[b] / f4[b - 1]) for b in sorted(sky) if f4[b - 1] > 0]
    r = np.array([q for _, q in ratios])
    print(f"Skytrace / DR1 cube, per official channel ({len(r)} channels): median {np.median(r):.3f}, robust scatter {1.4826*np.median(np.abs(r-np.median(r))):.3f}")
    for d in range(1, 7):
        rd = [q for b, q in ratios if P._CHANNELS[b - 1]["det"] == d]
        if rd: print(f"   D{d}: {len(rd):2d} channels, median ratio {np.median(rd):.3f}")
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    wl = np.array([c["wave"] for c in P._CHANNELS])
    fig, ax = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax[0].plot(wl, f4, "k-", lw=1, label="SPHEREx DR1 all-sky cube (official, 102 channels)")
    ax[0].plot([e["wave"] for e in ex], [e["flux_ujy"] for e in ex], ".", ms=3, alpha=.35, color="tab:blue", label="Skytrace, every exposure (native pixels)")
    ax[0].plot([wl[b - 1] for b in sorted(sky)], [sky[b] for b in sorted(sky)], "o", ms=4, color="tab:red", label="Skytrace, median per official channel")
    ax[0].set_ylabel("flux (µJy)"); ax[0].legend(fontsize=8); ax[0].set_title(f"Gaia DR3 {g['id']} (G={g['g']}): Skytrace vs official SPHEREx DR1 cube", fontsize=10)
    ax[1].plot([wl[b - 1] for b, _ in ratios], r, "o", ms=3, color="tab:red"); ax[1].axhline(1, color="k", lw=.8)
    ax[1].set_ylim(0.7, 1.3); ax[1].set_ylabel("ratio"); ax[1].set_xlabel("wavelength (µm)")
    plt.tight_layout(); plt.savefig(f"/home/claude/skytrace/report/figs/cube_check_{n}.png", dpi=85); print("figure saved")
