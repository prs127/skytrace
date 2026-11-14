"""Live check of every external data service Skytrace uses (run before a demo).
Each check fetches real data and tests it against a known expectation."""
import sys, time, json, warnings
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("ERROR")
sys.path.insert(0, "/home/claude/skytrace/backend")
import pipeline as P
from astropy.io import fits
import urllib.request

def check(name, fn):
    t = time.time()
    try:
        info = fn(); print(f"  OK   {name:58s} {time.time()-t:5.1f}s  {info}")
        return True
    except Exception as exc:
        print(f"  FAIL {name:58s} {time.time()-t:5.1f}s  {type(exc).__name__}: {str(exc)[:120]}"); return False

def sia():
    cols = P.discover_collections()
    assert {"spherex_dr1", "spherex_qr3"} <= set(cols), cols
    rows = P.query_exposures(133.76002, -7.24223, cols)
    assert len(rows) >= 258, len(rows)
    return f"collections {cols}; WISE 0855 position: {len(rows)} images (>= 258 expected)"

def s3():
    rows = P.query_exposures(269.44622, 4.76880, ["spherex_dr1"])
    with fits.open(P._s3_path(rows[0]["cloud_access"]), use_fsspec=True, fsspec_kwargs={"anon": True}) as h:
        hd = h["IMAGE"].header; sec = h["IMAGE"].section[1000:1004, 1000:1004]
        assert hd["BUNIT"].strip() == "MJy / sr" and sec.shape == (4, 4)
        return f"{rows[0]['obs_id']}: BUNIT {hd['BUNIT']}, MJD-AVG {hd['MJD-AVG']:.3f}, 4x4 byte-range read"

def sapm():
    a = P.sapm(3); m = float(abs(a).mean())
    assert a.shape == (2040, 2040) and 37 < m < 39, m
    return f"D3 map 2040x2040, mean {m:.3f} arcsec^2/pixel"

def tap():
    c = P.query_catalogs(269.44850, 4.73942, 0.08)   # 2MASS saw Barnard 170" away (1998-2000)
    g = [s for s in c["gaia"] if s["id"] == "4472832130942575872"]
    assert g and abs(g[0]["pmdec"] - 10362.394) < 0.01, "Barnard's Star not returned with its Gaia PM"
    assert c["catwise"] and "epoch" in c["catwise"][0]
    sed = P.catalog_sed({"ra": 269.44850252544, "dec": 4.73942005111, "pmra": -801.551, "pmdec": 10362.394, "epoch_mjd": 57388.0}, c)
    j = [s for s in sed if s.get("band") == "2MASS J"]
    assert j and j[0]["sep"] < 1.0, sed
    return f"Gaia DR3 {len(c['gaia'])}, CatWISE2020 {len(c['catwise'])}, 2MASS {len(c['tmass'])}; Barnard's Star 2MASS match at {j[0]['sep']}\" after 16 yr of motion"

def hips():
    with urllib.request.urlopen("https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube/properties", timeout=60) as r:
        t = r.read().decode()
    assert "hips_cube_depth      = 102" in t
    return "IRSA SPHEREx DR1 all-sky HiPS cube: 102 slices"

def channels():
    with urllib.request.urlopen("https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/hips5_cube/hips_20261026/Norder5/Dir0/Npix445_cube.fits", timeout=120) as r:
        open("/tmp/ch.fits", "wb").write(r.read())
    with fits.open("/tmp/ch.fits") as h:
        t = h["SPECTRAL_CHANNELS"].data
    ours = json.load(open("/home/claude/skytrace/backend/spherex_channels_dr1.json"))
    ours = ours["channels"] if isinstance(ours, dict) else ours
    assert len(t) == 102 == len(ours)
    return f"official SPECTRAL_CHANNELS table: 102 rows, same as the app's table"

print(time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()))
res = [check("IRSA SIA2 SPHEREx image search (all releases)", sia),
       check("IRSA AWS S3 bucket nasa-irsa-spherex (pixels)", s3),
       check("SPHEREx DR1 solid-angle pixel maps (S3 calibration)", sapm),
       check("IRSA TAP: Gaia DR3, CatWISE2020, 2MASS + cross-match", tap),
       check("IRSA HiPS: SPHEREx DR1 all-sky cube (Aladin layer)", hips),
       check("IRSA DR1 cube SPECTRAL_CHANNELS table", channels)]
print(f"{sum(res)}/{len(res)} services OK")
