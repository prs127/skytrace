"""
Skytrace data pipeline: SPHEREx Level-2 spectral images -> aligned, flag-aware
stamps on a common sky grid, plus per-exposure forced photometry (spectra).

Data source: NASA/IPAC Infrared Science Archive (IRSA), SPHEREx collections
discovered at run time (spherex_dr1, spherex_qr3, ... ) so new releases are
picked up automatically. Pixels are read from the public AWS S3 mirror
(s3://nasa-irsa-spherex) with byte-range reads, so only the rows we need are
transferred (the ~5 MB PSF extension is never downloaded).

Portions generated with Claude (Anthropic), reviewed by team Skytrace.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS, FITSFixedWarning
import astropy.units as u
from astropy import log as _astropy_log
from scipy.ndimage import map_coordinates

_astropy_log.setLevel("WARNING")   # silence per-file SIP INFO messages from the spectral WCS

warnings.filterwarnings("ignore", category=FITSFixedWarning)
warnings.filterwarnings("ignore", message=".*datfix.*")

PIXSCALE_ARCSEC = 6.15            # SPHEREx native pixel scale (IRSA s_pixel_scale)
N_CHANNELS_PER_DET = 17           # 6 detectors x 17 = 102 spectral channels
TAP_URL = "https://irsa.ipac.caltech.edu/TAP"

# ---- FLAGS bit planes (read from the MSKNxxxx keywords of the FLAGS HDU) ----
BIT = {
    "TRANSIENT": 0, "OVERFLOW": 1, "SUR_ERROR": 2, "NONFUNC": 6, "DICHROIC": 7,
    "MISSING_DATA": 9, "HOT": 10, "COLD": 11, "FULLSAMPLE": 12, "PHANMISS": 14,
    "NONLINEAR": 15, "PERSIST": 17, "OUTLIER": 19, "CROSSTALK": 20, "SOURCE": 21,
    "GHOST": 22, "GHOST_FPA": 23, "GHOST_EXT": 24, "STREAK": 25, "BLOOM": 26,
    "HALO": 28,
}
def _m(*names): return sum(1 << BIT[n] for n in names)

# Pixels we refuse to use (they would create fake "movers"): cosmic rays,
# electronics errors, dead/hot/cold pixels, outliers, persistence ghosts.
BAD_MASK = _m("TRANSIENT", "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD",
              "OUTLIER", "PERSIST")
SAT_MASK = _m("OVERFLOW", "NONLINEAR")
ART_MASK = _m("GHOST", "GHOST_FPA", "GHOST_EXT", "STREAK", "BLOOM", "HALO", "CROSSTALK")
SRC_MASK = _m("SOURCE")
_GROUPS = {
    "BAD": ("TRANSIENT", "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "OUTLIER", "PERSIST"),
    "SAT": ("OVERFLOW", "NONLINEAR"),
    "ART": ("GHOST", "GHOST_FPA", "GHOST_EXT", "STREAK", "BLOOM", "HALO", "CROSSTALK"),
    "SRC": ("SOURCE",),
    # Flags that set the conservative CONTAINS_BAD_PIXEL warning (SPHEREx Explanatory Supplement, Table 16), exactly
    # the `bad_flags` list of the IRSA Source Discovery Tool notebook. Names absent from a file's header are skipped.
    "NB_BAD": ("TRANSIENT", "OVERFLOW", "SUR_ERROR", "NONFUNC", "DICHROIC", "MISSING_DATA", "HOT", "COLD",
               "NONLINEAR", "CROSSTALK", "GHOST", "GHOST_FPA", "GHOST_EXT", "STREAK", "PERSIST",
               "BLOOM", "SNOWBALL", "HALO", "SATELLITE_HALO"),
}


def masks_from_header(fh):
    """Build the bit masks from THIS file's FLAGS header, exactly as the IRSA Source Discovery Tool does
    (MSKNnnnn = name of bit n; QR2 used MP_<name> = n). Falls back to the DR1 table above if absent."""
    fd = {str(fh[k]).strip(): int(k[4:]) for k in fh if k.startswith("MSKN")}
    if not fd:
        fd = {k[3:]: int(fh[k]) for k in fh if k.startswith("MP_")}
    if not fd:
        fd = BIT
    return {g: sum(1 << fd[n] for n in names if n in fd) for g, names in _GROUPS.items()}
# Fraction of a point source's flux inside the r=2 px photometry aperture, per detector, measured from
# DR1 ePSFs (median of 27 PSFs per detector, spread < 1%). See tests/ee_all.py. Validated against WISE W1/W2.
try:
    APERTURE_EE = json.load(open(__import__("os").path.join(__import__("os").path.dirname(__file__), "aperture_ee.json")))
except Exception:
    APERTURE_EE = {}

# Compact per-pixel category byte shipped to the browser
CAT_SAT, CAT_BAD, CAT_ART, CAT_SRC = 1, 2, 4, 8


def flag_names(value: int) -> list[str]:
    return [n for n, b in BIT.items() if value & (1 << b)]


# --------------------------------------------------------------------------
# Archive discovery and search
# --------------------------------------------------------------------------
def discover_collections() -> list[str]:
    """Return SPHEREx image collections currently served by IRSA SIA2.

    Newest data releases first; spectral cubes excluded (they are coadds,
    not time-resolved)."""
    from astroquery.ipac.irsa import Irsa
    cols = [str(c) for c in Irsa.list_collections(servicetype="SIA", filter="spherex")["collection"]]
    cols = [c for c in cols if not c.endswith("_cube")]

    def rank(c):  # dr > qr, higher number first, wide before deep
        kind = 0 if "_dr" in c else 1
        num = int("".join(ch for ch in c.split("_")[1] if ch.isdigit()) or 0)
        return (kind, -num, "deep" in c)
    return sorted(cols, key=rank)


def query_exposures(ra: float, dec: float, collections: list[str]):
    """All SPHEREx spectral images containing (ra, dec), de-duplicated across
    releases (an exposure in both DR1 and QR3 keeps the first, i.e. newest
    processing)."""
    from astroquery.ipac.irsa import Irsa
    from astropy.table import vstack
    c = SkyCoord(ra, dec, unit="deg")
    tabs = []
    for coll in collections:
        # Retry transient network errors; if a collection still fails, stop rather than silently
        # building a field from partial data (found in verification: a dropped DR1 query left
        # Epsilon Indi B with 120 of its 458 exposures).
        for attempt in range(4):
            try:
                t = Irsa.query_sia(pos=(c, 1 * u.arcsec), collection=coll)
                break
            except Exception as exc:
                print(f"[warn] SIA {coll} attempt {attempt + 1}: {exc}")
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"IRSA SIA query for {coll} failed 4 times; not building a partial field")
        if len(t):
            t = t[[k for k in ("obs_id", "energy_bandpassname", "t_min", "t_max", "em_min",
                               "em_max", "access_url", "cloud_access", "obs_collection")]]
            for k in ("obs_id", "energy_bandpassname", "access_url", "cloud_access", "obs_collection"):
                t[k] = t[k].astype(str)
            tabs.append(t)
    if not tabs:
        return None
    t = vstack(tabs, metadata_conflicts="silent")
    seen, keep = set(), []
    for i, row in enumerate(t):
        key = (row["obs_id"], row["energy_bandpassname"])
        if key not in seen:
            seen.add(key)
            keep.append(i)
    t = t[keep]
    t.sort("t_min")
    return t


# --------------------------------------------------------------------------
# Geometry helpers
# --------------------------------------------------------------------------
def propagate(ra, dec, pmra_mas, pmdec_mas, epoch_mjd, to_mjd):
    """Linear proper-motion propagation (adequate for < 0.5 deg of motion)."""
    dt = (np.asarray(to_mjd, float) - epoch_mjd) / 365.25
    ddec = pmdec_mas * dt / 3.6e6
    dra = pmra_mas * dt / 3.6e6 / np.cos(np.radians(dec))
    return ra + dra, dec + ddec


def parallax_offset_mas(ra, dec, plx_mas, mjd):
    """Annual parallax displacement (dRA*cos(dec), dDec) in mas for an observer at the geocentre, from Earth's
    barycentric position (astropy built-in ephemeris). SPHEREx's low Earth orbit adds < 5e-5 of this."""
    if not plx_mas:
        return 0.0, 0.0
    from astropy.coordinates import get_body_barycentric
    from astropy.time import Time
    import astropy.units as u
    x, y, z = get_body_barycentric("earth", Time(mjd, format="mjd", scale="tdb")).xyz.to(u.AU).value
    a, d = math.radians(ra), math.radians(dec)
    return (plx_mas * (x * math.sin(a) - y * math.cos(a)),
            plx_mas * (x * math.cos(a) * math.sin(d) + y * math.sin(a) * math.sin(d) - z * math.cos(d)))


def apparent_position(ra, dec, pmra, pmdec, plx_mas, epoch_mjd, mjd):
    """Barycentric catalogue position moved to date `mjd` with proper motion, plus annual parallax."""
    pra, pde = propagate(ra, dec, pmra, pmdec, epoch_mjd, mjd)
    dx, dy = parallax_offset_mas(pra, pde, plx_mas, mjd)
    return pra + dx / 3.6e6 / math.cos(math.radians(pde)), pde + dy / 3.6e6


def make_grid_wcs(ra, dec, npix):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(npix + 1) / 2, (npix + 1) / 2]       # FITS 1-based centre
    s = PIXSCALE_ARCSEC / 3600.0
    w.wcs.cdelt = [-s, s]                                  # north up, east left
    return w


# Official SPHEREx DR1 channel definition: SPECTRAL_CHANNELS table of the DR1 all-sky cube
# (https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/hips5_cube/hips_20261026/, see tests/channels.py).
_CHANNELS = json.load(open(__import__("os").path.join(__import__("os").path.dirname(__file__), "spherex_channels_dr1.json")))


def band_index(det: int, wave_um: float) -> int:
    """Official SPHEREx channel number (1..102) for a pixel of detector `det` seeing wavelength
    `wave_um`: the channel of that detector whose central wavelength is nearest."""
    best = min((c for c in _CHANNELS if c["det"] == det), key=lambda c: abs(c["wave"] - wave_um))
    return best["ch"]


_CHMAP = {}
_CHMAP_LOCK = threading.RLock()   # re-entrant: a missing release falls back to dr1 inside the lock


def channel_map(release="dr1"):
    """Official per-pixel channel map (2040x2040; 1..17 = sub-channel of the detector, 0/18 = outside the channels),
    from s3://nasa-irsa-spherex/<release>/spectral_channels/<newest version>/, cached on disk."""
    with _CHMAP_LOCK:
        if release in _CHMAP:
            return _CHMAP[release]
        arr = None
        try:
            import s3fs
            fs = s3fs.S3FileSystem(anon=True)
            vs = sorted(p.rsplit("/", 1)[-1] for p in fs.ls(f"{SAPM_BUCKET}/{release}/spectral_channels/"))
            ver = vs[-1]
            local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sapm", f"{ver}_channel_map.npy")
            if os.path.exists(local):
                arr = np.load(local)
            else:
                with fits.open(f"s3://{SAPM_BUCKET}/{release}/spectral_channels/{ver}/spectral_channels_spx_{ver}.fits",
                               use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
                    arr = h["CHANNEL_MAP"].data.astype(np.uint8)
                os.makedirs(os.path.dirname(local), exist_ok=True); np.save(local, arr)
        except Exception as exc:
            print(f"[warn] channel map for {release}: {exc}")
            arr = channel_map("dr1") if release != "dr1" else None
        _CHMAP[release] = arr
        return arr


def official_channel(det, release, x, y, wave_um):
    """Channel 1..102 at native pixel (x, y) from the official CHANNEL_MAP; None if the pixel lies outside the
    17 channels of its detector. Falls back to the nearest channel centre only if the map is unavailable."""
    cm = channel_map(release)
    xi, yi = int(round(float(x))), int(round(float(y)))
    if cm is not None and 0 <= xi < cm.shape[1] and 0 <= yi < cm.shape[0]:
        sub = int(cm[yi, xi])
        return (int(det) - 1) * N_CHANNELS_PER_DET + sub if 1 <= sub <= N_CHANNELS_PER_DET else None
    return band_index(det, wave_um) if np.isfinite(wave_um) else None


# --------------------------------------------------------------------------
# One exposure -> aligned stamp
# --------------------------------------------------------------------------
@dataclass
class Stamp:
    meta: dict
    image: np.ndarray        # float32, background-subtracted MJy/sr, NaN = unusable
    cat: np.ndarray          # uint8 flag categories


def _s3_path(cloud_access: str) -> str:
    aws = json.loads(cloud_access)["aws"]
    return f"s3://{aws['bucket_name']}/{aws['key']}"


def fetch_stamp(row, grid_wcs: WCS, npix: int, target_track, retries: int = 3) -> Stamp | None:
    """Read only the needed pixels of one SPHEREx exposure from S3, subtract the
    zodiacal model, mask bad pixels, resample onto the common grid, and do
    forced aperture photometry at the target's predicted position."""
    det = int(str(row["energy_bandpassname"])[-1])
    last_exc = None
    for attempt in range(retries):
        try:
            with fits.open(_s3_path(row["cloud_access"]), use_fsspec=True,
                           fsspec_kwargs={"anon": True, "default_block_size": 2**18},
                           lazy_load_hdus=True) as h:
                hdr = h["IMAGE"].header
                w = WCS(hdr)
                # Footprint of the output grid in source pixels (+ margin)
                yy, xx = np.mgrid[0:npix, 0:npix]
                world = grid_wcs.pixel_to_world(xx.ravel(), yy.ravel())
                sx, sy = w.world_to_pixel(world)
                if not (np.isfinite(sx).any()):
                    return None
                ny, nx = hdr["NAXIS2"], hdr["NAXIS1"]
                x0 = int(max(0, np.floor(np.nanmin(sx)) - 18)); x1 = int(min(nx, np.ceil(np.nanmax(sx)) + 19))
                y0 = int(max(0, np.floor(np.nanmin(sy)) - 18)); y1 = int(min(ny, np.ceil(np.nanmax(sy)) + 19))
                if x1 - x0 < 4 or y1 - y0 < 4:
                    return None
                img = np.asarray(h["IMAGE"].section[y0:y1, x0:x1], dtype=np.float32)
                zod = np.asarray(h["ZODI"].section[y0:y1, x0:x1], dtype=np.float32)
                var = np.asarray(h["VARIANCE"].section[y0:y1, x0:x1], dtype=np.float32)
                flg = np.asarray(h["FLAGS"].section[y0:y1, x0:x1]).astype(np.int64)
                MK = masks_from_header(h["FLAGS"].header)
                # Wavelength at the target (per-pixel LVF lookup table, WCS key 'W')
                tra, tdec = target_track(float(hdr["MJD-AVG"]))
                tx, ty = w.world_to_pixel(SkyCoord(tra, tdec, unit="deg"))
                wave_um = bw_um = float("nan")
                try:
                    ww = WCS(hdr, fobj=h, key="W")
                    ww.sip = None
                    txc = float(np.clip(tx, 0, nx - 1)); tyc = float(np.clip(ty, 0, ny - 1))
                    lam, bw = ww.pixel_to_world(txc, tyc)
                    wave_um = float(getattr(lam, "value", lam)); bw_um = float(getattr(bw, "value", bw))
                except Exception as exc:
                    print(f"[warn] spectral WCS {row['obs_id']}: {exc}")
                mjd = float(hdr["MJD-AVG"])
                l2dqa = str(hdr.get("L2DQAFLG", "")).strip()
            break
        except Exception as exc:
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    else:
        print(f"[error] {row['obs_id']} D{det}: {last_exc}")
        return None

    # --- clean, background-subtract -----------------------------------
    sci = img - zod
    bad = ((flg & MK["BAD"]) != 0) | ~np.isfinite(sci)
    good_sky = ~bad & ((flg & (MK["SRC"] | MK["SAT"] | MK["ART"])) == 0)
    if good_sky.sum() > 20:
        sky = np.median(sci[good_sky])
        mad = np.median(np.abs(sci[good_sky] - sky)) * 1.4826
    else:
        sky = np.nanmedian(sci[~bad]) if (~bad).any() else 0.0
        mad = np.nan
    sci = sci - sky

    # --- resample (normalised bilinear so masked pixels don't bleed) ----
    lx, ly = sx - x0, sy - y0
    data0 = np.where(bad, 0.0, sci).astype(np.float64)
    wgt = (~bad).astype(np.float64)
    coords = np.vstack([ly, lx])
    num = map_coordinates(data0, coords, order=1, mode="constant", cval=0.0)
    den = map_coordinates(wgt, coords, order=1, mode="constant", cval=0.0)
    out = np.full(npix * npix, np.nan, dtype=np.float32)
    ok = den > 0.5
    out[ok] = (num[ok] / den[ok]).astype(np.float32)
    out = out.reshape(npix, npix)

    catsrc = np.zeros_like(flg, dtype=np.uint8)
    catsrc[(flg & MK["SAT"]) != 0] |= CAT_SAT
    catsrc[bad] |= CAT_BAD
    catsrc[(flg & MK["ART"]) != 0] |= CAT_ART
    catsrc[(flg & MK["SRC"]) != 0] |= CAT_SRC
    ix = np.clip(np.rint(lx).astype(int), 0, catsrc.shape[1] - 1)
    iy = np.clip(np.rint(ly).astype(int), 0, catsrc.shape[0] - 1)
    cat = catsrc[iy, ix].reshape(npix, npix)
    outside = ~((lx >= -0.5) & (lx <= catsrc.shape[1] - 0.5) & (ly >= -0.5) & (ly <= catsrc.shape[0] - 0.5)).reshape(npix, npix)
    cat[outside] = CAT_BAD
    out[outside] = np.nan

    # --- forced aperture photometry on the ORIGINAL detector pixels ----------
    # (no resampling, so the result does not depend on where the display grid falls)
    # notebook: photometry uses every finite pixel; flagged pixels are counted (n_bad), not removed
    # (raw IMAGE, as in the notebook: the local annulus removes zodiacal light and sky, so ZODI is not subtracted here)
    sci_nat = np.where(np.isfinite(img), img, np.nan).astype(np.float32)
    nbad_map = (flg & MK["NB_BAD"]) != 0
    omap = sapm(det, release_of(row['obs_collection']))[y0:y1, x0:x1]
    _ix = int(np.clip(round(float(tx)) - x0, 0, omap.shape[1] - 1)); _iy = int(np.clip(round(float(ty)) - y0, 0, omap.shape[0] - 1))
    omega = float(omap[_iy, _ix])                 # solid angle of the target pixel, arcsec^2 (provenance)
    phot = aperture_phot(sci_nat, catsrc, float(tx) - x0, float(ty) - y0, omap, var=var, nbad_map=nbad_map)
    ee = APERTURE_EE.get(str(det), 1.0)          # aperture correction from the real SPHEREx ePSF
    if phot["flux"] is not None: phot["flux"] = round(phot["flux"] / ee, 3)
    if phot["err"] is not None: phot["err"] = round(phot["err"] / ee, 3)
    # flags in a 3x3 box around the target on the native image
    ixt, iyt = int(round(float(tx))) - x0, int(round(float(ty))) - y0
    tflag = 0
    if 0 <= ixt < flg.shape[1] and 0 <= iyt < flg.shape[0]:
        box = flg[max(0, iyt - 1):iyt + 2, max(0, ixt - 1):ixt + 2]
        tflag = int(np.bitwise_or.reduce(box.ravel()))

    em_min = float(row["em_min"]) * 1e6
    em_max = float(row["em_max"]) * 1e6
    meta = {
        "obs_id": str(row["obs_id"]), "det": det, "mjd": round(mjd, 5),
        "date": Time(mjd, format="mjd").isot[:16],
        "wave": round(wave_um, 4), "bw": round(bw_um, 4),
        "band": official_channel(det, release_of(row["obs_collection"]), tx, ty, wave_um),
        "sky": round(float(sky), 4), "noise": round(float(mad), 5) if np.isfinite(mad) else None,
        "flux_ujy": phot["flux"], "flux_err": phot["err"], "phot_flags": phot["flags"], "n_bad": phot.get("n_bad", 0),
        "target_flags": flag_names(tflag), "target_flagbits": tflag,
        "frac_bad": round(float(np.mean(cat & CAT_BAD > 0)), 3),
        "collection": str(row["obs_collection"]), "url": str(row["access_url"]),
        "dqa": l2dqa, "omega": round(omega, 3),
        # predicted target position at this exposure (proper motion + parallax), and Earth's barycentric position
        # (AU, ICRS) so the browser can apply parallax to any catalogue star exactly
        "tra": round(float(tra), 7), "tdec": round(float(tdec), 7), "earth": earth_au(mjd),
    }
    return Stamp(meta=meta, image=out, cat=cat)


def earth_au(mjd):
    from astropy.coordinates import get_body_barycentric
    from astropy.time import Time
    import astropy.units as u
    return [round(float(v), 6) for v in get_body_barycentric("earth", Time(mjd, format="mjd", scale="tdb")).xyz.to(u.AU).value]


R_AP, R_IN, R_OUT = 3.0, 7.0, 16.0     # pixels; smallest notebook radius and the notebook annulus
PHOT_DESC = ("IRSA SPHEREx Source Discovery Tool method on native detector pixels: per-pixel solid-angle map "
             f"(release-matched, currently cal-sapm-v3-2026-191), r={R_AP:g} px aperture (photutils subpixel x5), {R_IN:g}-{R_OUT:g} px annulus "
             "(sigma-clipped median), error from VARIANCE, n_bad = aperture pixels with CONTAINS_BAD_PIXEL flags; then divided by the ePSF encircled energy")
UJY_PER_MJYSR_ARCSEC2 = 1e12 * (math.pi / 180 / 3600) ** 2   # = 23.5044 uJy per (MJy/sr x arcsec^2)


# Official SPHEREx solid-angle pixel maps (calibration product, as used in the IRSA "SPHEREx Source Discovery Tool"
# notebook). Each release directory of the public bucket carries its own copy:
#   s3://nasa-irsa-spherex/<release>/solid_angle_pixel_map/<version>/<det>/solid_angle_pixel_map_D<det>_spx_<version>.fits
# The release is taken from the image's collection (spherex_dr1_deep -> dr1, spherex_qr3 -> qr3, a future
# spherex_dr2 -> dr2) and the newest version in that directory is used, so new releases need no code change.
# DR1 and QR3 currently both ship cal-sapm-v3-2026-191 (identical maps, checked pixel by pixel).
SAPM_BUCKET = "nasa-irsa-spherex"
_SAPM = {}
_SAPM_VERSION = {}
_SAPM_LOCK = threading.Lock()


def release_of(collection):
    """spherex_dr1_deep -> dr1, spherex_qr3 -> qr3."""
    parts = str(collection).split("_")
    return parts[1] if len(parts) > 1 else "dr1"


def sapm_version(release="dr1"):
    if release not in _SAPM_VERSION:
        try:
            import s3fs
            vs = sorted(p.rsplit("/", 1)[-1] for p in s3fs.S3FileSystem(anon=True).ls(f"{SAPM_BUCKET}/{release}/solid_angle_pixel_map/"))
            _SAPM_VERSION[release] = vs[-1] if vs else None
        except Exception:
            _SAPM_VERSION[release] = None
        if _SAPM_VERSION[release] is None and release != "dr1":
            _SAPM_VERSION[release] = sapm_version("dr1")          # fall back to the DR1 map
    return _SAPM_VERSION[release]


def sapm(det, release="dr1"):
    """Per-pixel solid angle (arcsec^2) for detector det, 2040x2040; cached on disk after the first download."""
    det = int(det)
    rel = release if sapm_version(release) else "dr1"
    ver = sapm_version(rel)
    key = (ver, det)
    with _SAPM_LOCK:
        if key in _SAPM:
            return _SAPM[key]
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sapm", f"{ver}_D{det}.npy")
        legacy = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sapm", f"D{det}.npy")
        if os.path.exists(local):
            arr = np.load(local)
        elif ver == "cal-sapm-v3-2026-191" and os.path.exists(legacy):
            arr = np.load(legacy)
        else:
            p = f"s3://{SAPM_BUCKET}/{rel}/solid_angle_pixel_map/{ver}/{det}/solid_angle_pixel_map_D{det}_spx_{ver}.fits"
            with fits.open(p, use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
                assert h["IMAGE"].header["BUNIT"].strip() == "arcsec2"
                arr = h["IMAGE"].data.astype(np.float32)
            try:
                os.makedirs(os.path.dirname(local), exist_ok=True); np.save(local, arr)
            except OSError:
                pass
        _SAPM[key] = arr
        return arr


def aperture_phot(img, cat, x, y, omega_arcsec2, var=None, nbad_map=None, r_ap=R_AP, r_in=R_IN, r_out=R_OUT):
    """Forced aperture photometry in micro-Jansky, following the IRSA "SPHEREx Source Discovery Tool"
    (spherex_source_discovery_tool/aperture_photometry.py: sa_mjy_scale_map + extract_photometry):
      1. IMAGE [MJy/sr] -> uJy/pixel with the official per-pixel solid-angle map:
             scale = Omega_pix[arcsec^2] x 23.5044   (variance scaled by scale^2)
      2. background = sigma_clipped_stats(annulus, sigma=3, maxiters=5) median, annulus 'center' mask
      3. flux = photutils aperture_photometry(method='subpixel', subpixels=5, mask=bad) - median x area
      4. error = sqrt( aperture sum of scaled VARIANCE )   (same subpixel aperture)
    Only non-finite pixels are excluded, exactly as in the notebook. As in the notebook (grab_star /
    plot_spectrum), n_bad = number of aperture pixels ('center' method) carrying any CONTAINS_BAD_PIXEL flag;
    a measurement with n_bad >= 1 gets the 'bad_pixels' flag and is hidden by default in the UI."""
    from astropy.stats import sigma_clipped_stats
    from photutils.aperture import CircularAperture, CircularAnnulus, aperture_photometry as _ap
    scale = np.asarray(omega_arcsec2, dtype=np.float64) * UJY_PER_MJYSR_ARCSEC2
    img = np.asarray(img, dtype=np.float64) * scale
    ny, nx = img.shape
    flags = []
    if x < r_ap or y < r_ap or x > nx - 1 - r_ap or y > ny - 1 - r_ap:
        return {"flux": None, "err": None, "flags": ["off_grid"]}
    bad = ~np.isfinite(img)
    pos = [(float(x), float(y))]
    ap = CircularAperture(pos, r=r_ap)
    apm = ap.to_mask(method="center")[0]
    inside = apm.to_image((ny, nx))
    inside = inside > 0 if inside is not None else np.zeros((ny, nx), bool)
    n_bad = int((nbad_map & inside).sum()) if nbad_map is not None else 0
    if n_bad:
        flags.append("bad_pixels")
    if (bad & inside).any():
        flags.append("masked")
    if (bad & inside).all():
        return {"flux": None, "err": None, "flags": flags + ["no_data"], "n_bad": n_bad}
    if ((cat & CAT_SAT) != 0)[inside].any():
        flags.append("saturated")
    if ((cat & CAT_ART) != 0)[inside].any():
        flags.append("artifact")
    ann = CircularAnnulus(pos, r_in=r_in, r_out=r_out).to_mask(method="center")[0]
    cut = ann.multiply(img)
    vals = cut[ann.data > 0] if cut is not None else np.array([])
    vals = vals[np.isfinite(vals)]
    if vals.size < 8:
        return {"flux": None, "err": None, "flags": flags + ["no_background"], "n_bad": n_bad}
    _, med, _ = sigma_clipped_stats(vals, sigma=3, maxiters=5)
    t = _ap(np.where(bad, 0.0, img), ap, mask=bad, method="subpixel", subpixels=5)
    flux = float(t["aperture_sum"][0]) - float(med) * ap.area
    err = None
    if var is not None:
        v = np.asarray(var, dtype=np.float64) * scale ** 2
        vbad = ~np.isfinite(v) | bad
        tv = _ap(np.where(vbad, 0.0, v), ap, mask=vbad, method="subpixel", subpixels=5)
        vs = float(tv["aperture_sum"][0])
        err = math.sqrt(vs) if vs > 0 else None
    return {"flux": round(flux, 3), "err": round(err, 3) if err is not None else None, "flags": flags, "n_bad": n_bad}


# --------------------------------------------------------------------------
# Catalog overlays (Gaia DR3 + CatWISE2020 via IRSA TAP)
# --------------------------------------------------------------------------
def query_catalogs(ra, dec, radius_deg, gmax=20.0, w2max=16.5, kmax=16.0):
    import pyvo
    tap = pyvo.dal.TAPService(TAP_URL)
    out = {"gaia": [], "catwise": [], "tmass": []}
    try:
        q = (f"SELECT TOP 400 source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag "
             f"FROM gaia_dr3_source WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
             f"CIRCLE('ICRS',{ra},{dec},{radius_deg})) AND phot_g_mean_mag < {gmax} "
             f"ORDER BY phot_g_mean_mag")
        for r in tap.run_sync(q).to_table():
            out["gaia"].append({
                "id": str(r["source_id"]), "ra": float(r["ra"]), "dec": float(r["dec"]),
                "pmra": float(r["pmra"]) if np.isfinite(r["pmra"]) else 0.0,
                "pmdec": float(r["pmdec"]) if np.isfinite(r["pmdec"]) else 0.0,
                "plx": float(r["parallax"]) if np.isfinite(r["parallax"]) else None,
                "g": round(float(r["phot_g_mean_mag"]), 2)})
    except Exception as exc:
        print("[warn] gaia:", exc)
    try:
        q = (f"SELECT TOP 400 source_name, ra, dec, ra_pm, dec_pm, pmra, pmdec, w1mpro, w2mpro, w1sigmpro, w2sigmpro, meanobsmjd "
             f"FROM catwise_2020 WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
             f"CIRCLE('ICRS',{ra},{dec},{radius_deg})) AND w2mpro < {w2max} ORDER BY w2mpro")
        for r in tap.run_sync(q).to_table():
            out["catwise"].append({
                # ra_pm/dec_pm: position from the motion fit at the CatWISE2020 epoch MJD 57170 (IRSA column docs);
                # plain ra/dec is the stationary fit and is wrong for fast movers
                "id": str(r["source_name"]),
                "ra": float(r["ra_pm"]) if _fin(r["ra_pm"], 9) is not None else float(r["ra"]),
                "dec": float(r["dec_pm"]) if _fin(r["dec_pm"], 9) is not None else float(r["dec"]),
                "epoch": CATWISE_EPOCH_MJD,
                "pmra": float(r["pmra"]) * 1000 if np.isfinite(r["pmra"]) else 0.0,
                "pmdec": float(r["pmdec"]) * 1000 if np.isfinite(r["pmdec"]) else 0.0,
                "w1": round(float(r["w1mpro"]), 2) if np.isfinite(r["w1mpro"]) else None,
                "w2": round(float(r["w2mpro"]), 2),
                "w1e": _fin(r["w1sigmpro"]), "w2e": _fin(r["w2sigmpro"]), "mjd": _fin(r["meanobsmjd"], 2)})
    except Exception as exc:
        print("[warn] catwise:", exc)
    try:   # 2MASS Point Source Catalog (NASA/IPAC), no proper motions; each source has its own observation date
        q = (f"SELECT TOP 400 designation, ra, dec, j_m, j_msigcom, h_m, h_msigcom, k_m, k_msigcom, jdate, ph_qual, cc_flg "
             f"FROM fp_psc WHERE 1=CONTAINS(POINT('ICRS',ra,dec),"
             f"CIRCLE('ICRS',{ra},{dec},{radius_deg})) AND k_m < {kmax} ORDER BY k_m")
        for r in tap.run_sync(q).to_table():
            out["tmass"].append({
                "id": str(r["designation"]), "ra": float(r["ra"]), "dec": float(r["dec"]),
                "j": _fin(r["j_m"]), "je": _fin(r["j_msigcom"]), "h": _fin(r["h_m"]), "he": _fin(r["h_msigcom"]),
                "k": _fin(r["k_m"]), "ke": _fin(r["k_msigcom"]), "mjd": round(float(r["jdate"]) - 2400000.5, 4),
                "q": str(r["ph_qual"]), "cc": str(r["cc_flg"])})
    except Exception as exc:
        print("[warn] 2mass:", exc)
    return out


def _fin(v, nd=3):
    if np.ma.is_masked(v):
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if np.isfinite(v) else None


# Zero-magnitude flux densities (Vega system)
#  2MASS: Cohen, Wheaton & Megeath (2003), AJ 126, 1090, as adopted in the 2MASS Explanatory Supplement (Sec. VI.4a)
#  WISE:  Jarrett et al. (2011), ApJ 735, 112, as adopted in the WISE All-Sky Explanatory Supplement (Sec. IV.4.h)
ZERO_POINTS = {
    "2MASS J": (1.235, 1594.0), "2MASS H": (1.662, 1024.0), "2MASS Ks": (2.159, 666.7),
    "WISE W1": (3.3526, 309.540), "WISE W2": (4.6028, 171.787),
}
CATWISE_EPOCH_MJD = 57170.0      # CatWISE2020 positions are given at epoch 2015.4 (Marocco et al. 2021)


def _mag_to_ujy(band, m, sig):
    wave, f0 = ZERO_POINTS[band]
    f = f0 * 1e6 * 10 ** (-0.4 * m)
    return wave, round(f, 3), (round(f * math.log(10) / 2.5 * sig, 3) if sig is not None else None)


def catalog_sed(target, cats, r_2mass=2.5, r_wise=3.0):
    """Cross-match the target with 2MASS and CatWISE2020, moving the target to each catalogue's own epoch
    with its proper motion, and convert the catalogue magnitudes to flux density (uJy)."""
    out = []
    t = target
    best = None
    for s in cats.get("tmass", []):
        tra, tde = propagate(t["ra"], t["dec"], t["pmra"], t["pmdec"], t["epoch_mjd"], s["mjd"])
        d = SkyCoord(tra, tde, unit="deg").separation(SkyCoord(s["ra"], s["dec"], unit="deg")).arcsec
        if d < r_2mass and (best is None or d < best[0]):
            best = (d, s)
    if best:
        d, s = best
        for band, key, ekey, qi in (("2MASS J", "j", "je", 0), ("2MASS H", "h", "he", 1), ("2MASS Ks", "k", "ke", 2)):
            if s[key] is None:
                continue
            w, f, e = _mag_to_ujy(band, s[key], s[ekey])
            out.append({"band": band, "wave": w, "flux_ujy": f, "err": e, "mjd": s["mjd"], "id": s["id"],
                        "sep": round(d, 2), "qual": s["q"][qi] if len(s["q"]) > qi else "", "cc": s["cc"][qi] if len(s["cc"]) > qi else ""})
    tra, tde = propagate(t["ra"], t["dec"], t["pmra"], t["pmdec"], t["epoch_mjd"], CATWISE_EPOCH_MJD)
    tpm = math.hypot(t["pmra"], t["pmdec"])
    cands = []
    for s in cats.get("catwise", []):
        d = SkyCoord(tra, tde, unit="deg").separation(SkyCoord(s["ra"], s["dec"], unit="deg")).arcsec
        if d >= r_wise:
            continue
        if tpm > 200 and math.hypot(s["pmra"] - t["pmra"], s["pmdec"] - t["pmdec"]) > 0.3 * tpm:
            continue                          # a fast mover must match a catalogue source moving the same way
        cands.append((d, s))
    cands.sort(key=lambda c: c[0])
    if len(cands) > 1 and tpm > 200:
        out.append({"band": "WISE", "note": f"CatWISE2020 splits this moving object into {len(cands)} entries "
                    f"({', '.join(c[1]['id'] for c in cands)}); their W1/W2 are not plotted."})
        cands = []
    if cands:
        d, s = cands[0]
        for band, key, ekey in (("WISE W1", "w1", "w1e"), ("WISE W2", "w2", "w2e")):
            if s.get(key) is None:
                continue
            w, f, e = _mag_to_ujy(band, s[key], s.get(ekey))
            out.append({"band": band, "wave": w, "flux_ujy": f, "err": e, "mjd": s.get("mjd"), "id": s["id"], "sep": round(d, 2)})
    return out


# --------------------------------------------------------------------------
# Whole field
# --------------------------------------------------------------------------
@dataclass
class Target:
    key: str
    name: str
    ra: float                 # deg at epoch_mjd
    dec: float
    pmra: float = 0.0         # mas/yr (mu_alpha * cos dec)
    pmdec: float = 0.0
    epoch_mjd: float = 57388.0   # Gaia DR3 reference epoch J2016.0
    note: str = ""
    plx: float = 0.0          # parallax, mas (0 = not modelled)
    source: str = ""
    extra: dict = field(default_factory=dict)


def build_field(t: Target, npix: int = 89, workers: int = 16, max_exposures: int | None = None,
                collections: list[str] | None = None, progress=print) -> dict:
    t0 = time.time()
    collections = collections or discover_collections()
    progress(f"[{t.key}] collections: {collections}")
    # Search at the target's position in mid-2025 (SPHEREx era)
    sra, sdec = propagate(t.ra, t.dec, t.pmra, t.pmdec, t.epoch_mjd, 61000.0)
    rows = query_exposures(float(sra), float(sdec), collections)
    if rows is None or len(rows) == 0:
        raise RuntimeError("No SPHEREx exposures cover this position yet")
    n_found = len(rows)
    if max_exposures and len(rows) > max_exposures:
        # keep an even sampling in time rather than truncating the newest data
        idx = np.unique(np.linspace(0, len(rows) - 1, max_exposures).round().astype(int))
        rows = rows[idx]
    mjd_mid = float(np.median(np.asarray(rows["t_min"], float)))
    cra, cdec = propagate(t.ra, t.dec, t.pmra, t.pmdec, t.epoch_mjd, mjd_mid)
    grid = make_grid_wcs(float(cra), float(cdec), npix)
    track = lambda mjd: tuple(float(v) for v in apparent_position(t.ra, t.dec, t.pmra, t.pmdec, t.plx, t.epoch_mjd, mjd))
    progress(f"[{t.key}] {len(rows)} exposures; grid centre {cra:.5f} {cdec:.5f}")

    stamps: list[Stamp] = []
    radius = npix * PIXSCALE_ARCSEC / 3600 / math.sqrt(2) + 0.01
    with ThreadPoolExecutor(max_workers=workers + 1) as ex:
        cat_future = ex.submit(query_catalogs, float(cra), float(cdec), radius)   # runs alongside downloads
        futs = [ex.submit(fetch_stamp, row, grid, npix, track) for row in rows]
        for i, f in enumerate(as_completed(futs), 1):
            s = f.result()
            if s is not None:
                stamps.append(s)
            if i % 25 == 0:
                progress(f"[{t.key}] {i}/{len(futs)} read ({time.time() - t0:.0f}s)")
        cats = cat_future.result()
    stamps.sort(key=lambda s: (s.meta["mjd"], s.meta["det"]))
    det_ranges = {}
    for row in rows:
        d = int(str(row["energy_bandpassname"])[-1])
        det_ranges[d] = [round(float(row["em_min"]) * 1e6, 4), round(float(row["em_max"]) * 1e6, 4)]
    hdr = grid.to_header()
    meta = {
        "key": t.key, "name": t.name, "note": t.note, "source": t.source,
        "target": {"ra": t.ra, "dec": t.dec, "pmra": t.pmra, "pmdec": t.pmdec, "plx": t.plx, "epoch_mjd": t.epoch_mjd, **t.extra},
        "grid": {"npix": npix, "crval": [float(cra), float(cdec)], "crpix": [float(hdr["CRPIX1"]), float(hdr["CRPIX2"])],
                 "cdelt": [float(hdr["CDELT1"]), float(hdr["CDELT2"])], "pixscale": PIXSCALE_ARCSEC, "mjd_ref": mjd_mid},
        "completeness": {"found_in_archive": n_found, "requested": len(rows), "read": len(stamps)},
        "collections": collections, "detectors": det_ranges, "channels_source": "SPHEREx DR1 SPECTRAL_CHANNELS",
        "photometry": PHOT_DESC,
        "built": Time.now().isot[:19] + "Z", "build_seconds": round(time.time() - t0, 1),
        "exposures": [s.meta for s in stamps], "catalogs": cats,
        "sed": catalog_sed({"ra": t.ra, "dec": t.dec, "pmra": t.pmra, "pmdec": t.pmdec, "epoch_mjd": t.epoch_mjd}, cats),
        "encoding": {"image": "float16 little-endian, N x npix x npix, row 0 = south", "cat": "uint8 bitmask SAT=1 BAD=2 ART=4 SRC=8"},
    }
    imgs = np.stack([s.image for s in stamps]).astype("<f2") if stamps else np.zeros((0, npix, npix), "<f2")
    cats_arr = np.stack([s.cat for s in stamps]).astype(np.uint8) if stamps else np.zeros((0, npix, npix), np.uint8)
    return {"meta": meta, "images": imgs, "cats": cats_arr}


def write_package(pkg: dict, outdir: str):
    import os
    os.makedirs(outdir, exist_ok=True)
    key = pkg["meta"]["key"]
    with gzip.open(os.path.join(outdir, f"{key}.img.bin.gz"), "wb", compresslevel=6) as f:
        f.write(pkg["images"].tobytes())
    with gzip.open(os.path.join(outdir, f"{key}.cat.bin.gz"), "wb", compresslevel=9) as f:
        f.write(pkg["cats"].tobytes())
    with open(os.path.join(outdir, f"{key}.json"), "w") as f:
        json.dump(sanitize(pkg["meta"]), f, separators=(",", ":"), allow_nan=False, default=_json_default)


def sanitize(o):
    """Replace NaN/inf by None recursively so the JSON is strict."""
    if isinstance(o, dict):
        return {k: sanitize(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [sanitize(v) for v in o]
    if isinstance(o, (float, np.floating)):
        return float(o) if np.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    return o


def _json_default(o):
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    raise TypeError(type(o))
