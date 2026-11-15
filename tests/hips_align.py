"""Check that the context surveys Skytrace overlays (IRSA-hosted HiPS of DSS2, 2MASS, AllWISE) are
astrometrically aligned with Gaia DR3 at each test field.

For every field: take Gaia DR3 stars already stored in the field file (fetched from IRSA TAP), keep
isolated, unsaturated, slow stars (|pm| < 10 mas/yr so epoch differences are < 0.3"), fetch the HiPS
tiles covering them at the survey's deepest order, measure a background-subtracted centroid of each
star in the tile pixels and convert it back to RA/Dec with the HiPS (HPX) WCS. Report the median and
scatter of (measured - Gaia) offsets in arcsec and in survey pixels.

JPEG tiles (the colour layers that the viewer actually shows) are read as luminance and flipped
top-to-bottom (HiPS JPEG rows run top-down, FITS rows bottom-up). The flip convention is itself
checked: for DSS2 red and AllWISE W1 both FITS and JPEG tiles exist and must give the same offsets.
"""
import io, json, sys, urllib.request, ssl, os
import numpy as np
from astropy.io import fits
from astropy.wcs.utils import proj_plane_pixel_scales
from astropy.coordinates import SkyCoord
import astropy.units as u
from PIL import Image
from reproject.hips import _dask_array as D

BASE = 'https://irsa.ipac.caltech.edu/data/hips/CDS/'
SURVEYS = [  # (label, path, tile format)
    ('DSS2 colour (shown)', 'DSS2/color', 'jpg'),
    ('2MASS colour (shown)', '2MASS/Color', 'jpg'),
    ('AllWISE colour (shown)', 'AllWISE/RGB-W4-W2-W1', 'jpg'),
    ('DSS2 red FITS', 'DSS2/red', 'fits'),
    ('DSS2 red JPEG', 'DSS2/red', 'jpg'),
    ('AllWISE W1 FITS', 'AllWISE/W1', 'fits'),
    ('AllWISE W1 JPEG', 'AllWISE/W1', 'jpg'),
]
DATA = sys.argv[1] if len(sys.argv) > 1 else 'frontend/data'
FIELDS = ['wise0855', 'barnard', 'epsindib', 'rwaur', 'rdra', 'm101']
ctx = ssl.create_default_context(cafile=os.environ.get('SSL_CERT_FILE') or os.path.expanduser('~/.ccr/ca-bundle.crt'))
_cache = {}

def fetch(url):
    if url in _cache: return _cache[url]
    try:
        with urllib.request.urlopen(url, timeout=60, context=ctx) as r: b = r.read()
    except urllib.error.HTTPError:
        b = None
    _cache[url] = b
    return b

def make_getter(fmt):
    def _get_tile(self, *, level, index):
        url = D.tile_filename(level=self._level, index=index, output_directory=self._directory_or_url, extension=fmt)
        b = fetch(url)
        if b is None: return self._nan
        if fmt == 'fits':
            return fits.getdata(io.BytesIO(b)).astype(float)
        im = np.asarray(Image.open(io.BytesIO(b)).convert('L'), dtype=float)
        return im[::-1, :]
    return _get_tile

def centroid(cut):
    bg = np.nanmedian(cut)
    c = np.clip(cut - bg, 0, None)
    n = cut.shape[0]; yy, xx = np.mgrid[0:n, 0:n]
    # iterate a 2-px-radius-weighted centre of mass around the peak
    cy, cx = np.unravel_index(np.nanargmax(c), c.shape)
    for _ in range(5):
        w = c * (((yy - cy) ** 2 + (xx - cx) ** 2) <= 2.5 ** 2)
        s = w.sum()
        if s <= 0: return None
        cy, cx = (w * yy).sum() / s, (w * xx).sum() / s
    return cy, cx

def run():
    rows = []
    for label, path, fmt in SURVEYS:
        D.HiPSArray._get_tile = make_getter(fmt)
        H = D.HiPSArray(BASE + path); wcs = H.wcs; T = H._tile_width; chunks = {}
        def window(x, y, h):
            cy, cx = y // T, x // T
            if (y - h) // T != cy or (y + h) // T != cy or (x - h) // T != cx or (x + h) // T != cx: return None
            if (cy, cx) not in chunks: chunks[(cy, cx)] = H[slice(cy * T, (cy + 1) * T), slice(cx * T, (cx + 1) * T)]
            t = chunks[(cy, cx)]
            return t[y - h - cy * T:y + h + 1 - cy * T, x - h - cx * T:x + h + 1 - cx * T]
        scale = proj_plane_pixel_scales(wcs.celestial)[0] * 3600
        for f in FIELDS:
            m = json.load(open(f'{DATA}/{f}.json'))
            g = m['catalogs']['gaia']
            ra = np.array([s['ra'] for s in g]); de = np.array([s['dec'] for s in g])
            pm = np.hypot([s.get('pmra') or 0 for s in g], [s.get('pmdec') or 0 for s in g])
            G = np.array([s.get('g') or 99 for s in g])
            sc = SkyCoord(ra * u.deg, de * u.deg)
            idx, sep, _ = sc.match_to_catalog_sky(sc, nthneighbor=2)
            ok = (pm < 10) & (G > 11) & (G < 16.5) & (sep.arcsec > 20)
            offs = []
            for i in np.where(ok)[0][:25]:
                x, y = wcs.celestial.world_to_pixel(sc[i])
                x, y = int(round(float(x))), int(round(float(y)))
                h = 7
                cut = window(x, y, h)
                if cut is None or cut.shape != (2 * h + 1, 2 * h + 1) or not np.isfinite(cut).all(): continue
                c = centroid(cut)
                if c is None: continue
                w = wcs.celestial.pixel_to_world(x - h + c[1], y - h + c[0])
                dra = (w.ra.deg - ra[i]) * np.cos(np.radians(de[i])) * 3600
                ddec = (w.dec.deg - de[i]) * 3600
                if np.hypot(dra, ddec) < 3 * scale: offs.append((dra, ddec))
            offs = np.array(offs)
            if len(offs) < 3:
                rows.append((label, f, len(offs), np.nan, np.nan, np.nan, scale)); continue
            med = np.median(offs, axis=0); r = np.hypot(*(offs - med).T)
            rows.append((label, f, len(offs), med[0], med[1], np.median(r), scale))
            print(f'{label:24s} {f:9s} N={len(offs):2d}  median dRA*cosDec={med[0]:+.2f}"  dDec={med[1]:+.2f}"  '
                  f'|median|={np.hypot(*med):.2f}" ({np.hypot(*med)/scale:.2f} px)  scatter={np.median(r):.2f}"  pix={scale:.2f}"', flush=True)
    return rows

if __name__ == '__main__':
    rows = run()
    # what matters for the viewer: the comparison image must put stars where SPHEREx does, so judge the
    # offset against the SPHEREx pixel (6.15"); also report it in survey pixels for information
    bad = [r for r in rows if '(shown)' in r[0] and not (np.isfinite(r[3]) and np.hypot(r[3], r[4]) < 0.25 * 6.15)]
    print('\nFAIL rows among the layers Skytrace shows (|median offset| >= 0.25 SPHEREx pixel = 1.54" or too few stars):', bad if bad else 'none')
    import collections
    agg = collections.defaultdict(list)
    for r in rows:
        if np.isfinite(r[3]): agg[r[0]].append(np.hypot(r[3], r[4]))
    for k, v in agg.items(): print(f'{k:24s} worst field |median offset| = {max(v):.2f}"  ({max(v)/6.15:.2f} SPHEREx px)')
