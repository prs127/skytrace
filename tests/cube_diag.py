import warnings, json, numpy as np, sys, posixpath
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P
from astropy.io import fits; from astropy.wcs import WCS
import hpgeom as hp
stars = [("epsindib", "6412596458823395328"), ("barnard", "4472835055807757440")]
for key, gid in stars:
    m = json.load(open(f"/home/claude/skytrace/frontend/data/{key}.json"))
    g = [x for x in m["catalogs"]["gaia"] if x["id"] == gid][0]
    sep = lambda a, b: np.hypot((a["ra"] - b["ra"]) * np.cos(np.radians(a["dec"])), a["dec"] - b["dec"]) * 3600
    cw = min(m["catalogs"]["catwise"], key=lambda s: sep(s, g))
    ipix = hp.angle_to_pixel(32, g["ra"], g["dec"], nest=True, lonlat=True)
    url = posixpath.join("https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/hips5_cube/hips_20261026/Norder5", f"Dir{(ipix//10000)*10000}", f"Npix{ipix}_cube.fits")
    with fits.open(url, use_fsspec=True, lazy_load_hdus=True) as h:
        hdr = h["IMAGE"].header; w = WCS(hdr, fobj=h).celestial
        x, y = [float(v) for v in w.world_to_pixel_values(g["ra"], g["dec"])]; xi, yi = int(round(x)), int(round(y)); R = 14
        cube = np.asarray(h["IMAGE"].section[:, yi-R:yi+R+1, xi-R:xi+R+1], float)
        print(f"\n{key} Gaia {gid}: BUNIT={hdr.get('BUNIT')}, CDELT/CD: {w.proj_plane_pixel_scales()[0].to('arcsec'):.3f}")
    pix = w.proj_plane_pixel_scales()[0].to("arcsec").value; om = (pix/206264.806)**2
    yy, xx = np.mgrid[-R:R+1, -R:R+1]; rr = np.hypot(xx-(x-xi), yy-(y-yi))
    # neighbours in Gaia within 70"
    nb = sorted([(round(sep(g, o),1), o["g"]) for o in m["catalogs"]["gaia"] if o is not g and sep(g, o) < 70])
    print(f"   Gaia neighbours within 70\": {nb[:8]}")
    for k_wave in (3.35, 4.6):
        k = int(np.argmin([abs(c["wave"] - k_wave) for c in P._CHANNELS])); im = cube[k]; an = (rr > 8) & (rr < 13)
        bk = np.nanmedian(im[an]); cog = [np.nansum(im[rr <= r] - bk) * 1e12 * om for r in (1.5, 2, 2.5, 3, 4, 5)]
        zp, mag = (309.540, cw["w1"]) if k_wave < 4 else (171.787, cw["w2"])
        print(f"   channel {k+1} ({P._CHANNELS[k]['wave']} um): cube curve of growth r=1.5..5 px -> " + ", ".join(f"{c:.0f}" for c in cog) + f" uJy;  WISE {'W1' if k_wave<4 else 'W2'}={mag} -> {zp*10**(-mag/2.5)*1e6:.0f} uJy")
