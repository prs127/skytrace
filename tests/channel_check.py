"""Check Skytrace's channel assignment (nearest official centre wavelength at the target) against the official SPHEREx
DR1 per-pixel CHANNEL_MAP (s3://nasa-irsa-spherex/dr1/spectral_channels/cal-sch-v2-2026-229), and our 102-channel table
against its SPECTRAL_CHANNELS table."""
import warnings, json, sys, numpy as np; warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("ERROR")
from astropy.io import fits
from astropy.wcs import WCS
from astropy.coordinates import SkyCoord
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P
from targets import TARGETS
with fits.open("s3://nasa-irsa-spherex/dr1/spectral_channels/cal-sch-v2-2026-229/spectral_channels_spx_cal-sch-v2-2026-229.fits", use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
    cmap = h["CHANNEL_MAP"].data.astype(int); tab = h["SPECTRAL_CHANNELS"].data; print("CHANNEL_MAP values:", np.unique(cmap)[:20], "...")
ours = P._CHANNELS
d = max(abs(float(t["WAVELENGTH"]) - c["wave"]) for t, c in zip(tab, ours))
print(f"Our 102-channel table vs official SPECTRAL_CHANNELS: max centre difference {d*1000:.2f} nm; order identical:",
      all(int(t["DETECTOR"]) == c["det"] and int(t["SUBCHAN"]) == c["sub"] for t, c in zip(tab, ours)))
agree = tot = 0; diffs = []
for key in sys.argv[1:] or ["epsindib", "wise0855"]:
    m = json.load(open(f"/home/claude/skytrace/frontend/data/{key}.json")); T = [t for t in TARGETS if t.key == key][0]
    for e in m["exposures"][::max(1, len(m["exposures"]) // 25)]:
        ca = json.dumps({"aws": {"bucket_name": "nasa-irsa-spherex", "key": e["url"].split("/ibe/data/spherex/")[1]}})
        with fits.open(P._s3_path(ca), use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
            w = WCS(h["IMAGE"].header)
        ra, de = P.apparent_position(T.ra, T.dec, T.pmra, T.pmdec, T.plx, T.epoch_mjd, e["mjd"])
        x, y = w.world_to_pixel(SkyCoord(ra, de, unit="deg")); xi, yi = int(round(float(x))), int(round(float(y)))
        if not (0 <= xi < 2040 and 0 <= yi < 2040): continue
        sub = cmap[yi, xi]; off = (e["det"] - 1) * 17
        official = off + sub if 1 <= sub <= 17 else None          # 0 / 18: outside the detector's 17 channels
        tot += 1; agree += (official == e["band"]); diffs.append("ok" if official == e["band"] else f"{official} vs {e['band']}")
print(f"Channel at the target pixel: Skytrace = official CHANNEL_MAP in {agree}/{tot} sampled exposures; differences {sorted(set(diffs))}")
