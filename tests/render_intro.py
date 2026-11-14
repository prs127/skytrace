import warnings; warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
import numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from astropy.io import fits; from astropy.wcs import WCS
from astropy.visualization import ImageNormalize, AsinhStretch, PercentileInterval
url = "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/level2/2025W18_1B/l2b-v27-2026-196/1/level2_2025W18_1B_0074_2D1_spx_l2b-v27-2026-196.fits"
h = fits.open(url, cache=True)
img, flg, var, zod = (h[k].data for k in ("IMAGE", "FLAGS", "VARIANCE", "ZODI"))
ww = WCS(h["IMAGE"].header, fobj=h, key="W"); ww.sip = None
yy, xx = np.mgrid[0:2040:8, 0:2040:8]; lam, bw = ww.pixel_to_world(xx, yy)
fig, ax = plt.subplots(2, 3, figsize=(15, 9.5))
def show(a, data, title, cmap="gray", norm=None, cb=""):
    im = a.imshow(data, origin="lower", cmap=cmap, norm=norm); a.set_title(title, fontsize=10); fig.colorbar(im, ax=a, fraction=0.046, label=cb)
show(ax[0,0], img, "IMAGE (MJy/sr), asinh 99.5%", norm=ImageNormalize(img, PercentileInterval(99.5), stretch=AsinhStretch()), cb="MJy/sr")
show(ax[0,1], img - zod, "IMAGE − ZODI", norm=ImageNormalize(img - zod, PercentileInterval(99.5), stretch=AsinhStretch()), cb="MJy/sr")
show(ax[0,2], zod, "ZODI model (MJy/sr)", cmap="viridis", cb="MJy/sr")
show(ax[1,0], np.log10(var), "log10 VARIANCE", cmap="magma", norm=ImageNormalize(np.log10(var), PercentileInterval(99)), cb="log (MJy/sr)²")
bad = (flg & sum(1 << b for b in (0, 2, 6, 9, 10, 11, 17, 19))) != 0
show(ax[1,1], np.where(bad, 2, np.where(flg & (1 << 21), 1, 0)), "FLAGS: 0 clean, 1 SOURCE, 2 bad", cmap="cividis")
im = ax[1,2].imshow(np.asarray(lam.value if hasattr(lam, "value") else lam), origin="lower", cmap="turbo", extent=[0, 2040, 0, 2040]); ax[1,2].set_title("WCS-WAVE central wavelength (µm)\nlinear variable filter gradient", fontsize=10); fig.colorbar(im, ax=ax[1,2], fraction=0.046, label="µm")
fig.suptitle("Notebook 1 replication: level2_2025W18_1B_0074_2D1 (SPHEREx DR1, detector 1)", fontsize=12)
plt.tight_layout(); plt.savefig("figs/intro/intro_extensions.png", dpi=80)
lv = np.asarray(lam.value if hasattr(lam,'value') else lam)
print("wavelength range on D1: %.3f - %.3f um (nominal 0.75-1.09)" % (lv.min(), lv.max()))
print("median ZODI %.3f MJy/sr; median IMAGE %.3f; frac bad %.3f; frac SOURCE %.3f" % (np.nanmedian(zod), np.nanmedian(img), bad.mean(), ((flg & (1<<21))!=0).mean()))
print("N_SOURCE check: header", h["IMAGE"].header["L2 N_SOURCE"], "counted", int(((flg & (1<<21))!=0).sum()))
