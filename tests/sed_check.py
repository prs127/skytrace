"""Multi-mission check: SPHEREx (Skytrace, clean points only) vs 2MASS J/H/Ks and WISE W1/W2 catalogue fluxes for
isolated, unsaturated, non-moving stars. Each catalogue band is compared with the median SPHEREx flux of the channels
inside that band's wavelength range. Expect agreement at the ~5-15% level (band average vs channel median, different
epochs, catalogue zero points); a gross mismatch would reveal a units or cross-match error."""
import warnings, json, numpy as np, sys
warnings.filterwarnings("ignore")
from astropy import log; log.setLevel("WARNING")
sys.path.insert(0, "/home/claude/skytrace/backend")
import pipeline as P
RANGES = {"2MASS J": (1.11, 1.36), "2MASS H": (1.51, 1.79), "2MASS Ks": (2.00, 2.31), "WISE W1": (3.0, 3.75), "WISE W2": (4.1, 5.0)}
def sep(a, b): return np.hypot((a["ra"] - b["ra"]) * np.cos(np.radians(a["dec"])), a["dec"] - b["dec"]) * 3600
STARS = []
for key in ["wise0855", "epsindib", "rwaur", "barnard", "m101"]:
    m = json.load(open(f"/home/claude/skytrace/frontend/data/{key}.json"))
    cw, ga, tm = m["catalogs"]["catwise"], m["catalogs"]["gaia"], m["catalogs"]["tmass"]
    for s in cw:
        if s["w1"] is None or not (9.0 < s["w1"] < 11.5) or abs(s["pmra"]) + abs(s["pmdec"]) > 100: continue
        if any(sep(s, o) < 25 for o in cw if o is not s): continue
        g = [x for x in ga if sep(s, x) < 3]
        if len(g) != 1 or any(sep(g[0], x) < 15 and x["g"] < g[0]["g"] + 3 for x in ga if x is not g[0]): continue
        t2 = [x for x in tm if sep(s, x) < 3]
        if len(t2) != 1 or t2[0]["q"] != "AAA" or t2[0]["cc"] != "000": continue
        STARS.append((key, g[0]))
print(f"{len(STARS)} isolated stars with clean 2MASS (AAA, cc=000) and CatWISE; using 4")
rat = {b: [] for b in RANGES}
for key, g in STARS[:4]:
    t = P.Target("star", "check", g["ra"], g["dec"], g["pmra"], g["pmdec"], 57388.0)
    pkg = P.build_field(t, npix=41, workers=16, collections=["spherex_dr1", "spherex_qr3"], progress=lambda x: None)
    m = pkg["meta"]; ex = [e for e in m["exposures"] if e["flux_ujy"] is not None and not e["phot_flags"] and e["wave"]]
    line = []
    for s in m["sed"]:
        if "flux_ujy" not in s: continue
        lo, hi = RANGES[s["band"]]; v = [e["flux_ujy"] for e in ex if lo <= e["wave"] <= hi]
        if len(v) < 3: continue
        r = np.median(v) / s["flux_ujy"]; rat[s["band"]].append(r); line.append(f"{s['band']} {r:.3f} (n={len(v)}, sep {s['sep']}\")")
    print(f"Gaia DR3 {g['id']} G={g['g']} ({key} field): " + "; ".join(line))
print("\nSPHEREx / catalogue, median over stars:")
for b, v in rat.items():
    if v: print(f"  {b}: {np.median(v):.3f}  (range {min(v):.3f}-{max(v):.3f}, {len(v)} stars)")
