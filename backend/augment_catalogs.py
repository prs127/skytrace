"""Refresh the catalogue overlays (Gaia DR3, CatWISE2020, 2MASS) and the multi-mission SED of already-built fields,
without re-reading the SPHEREx images. Usage: python augment_catalogs.py DATA_DIR [key ...]"""
import json, math, os, sys
import pipeline as P

d = sys.argv[1] if len(sys.argv) > 1 else "../frontend/data"
idx = json.load(open(os.path.join(d, "index.json")))
keys = sys.argv[2:] or [f["key"] for f in idx["fields"]]
for k in keys:
    p = os.path.join(d, k + ".json"); m = json.load(open(p))
    g = m["grid"]; radius = g["npix"] * P.PIXSCALE_ARCSEC / 3600 / math.sqrt(2) + 0.01
    cats = P.query_catalogs(g["crval"][0], g["crval"][1], radius); cats.pop("warnings", None)
    if not cats["gaia"] or not cats["catwise"]:
        print(f"[skip] {k}: catalogue query incomplete"); continue
    m["catalogs"] = cats
    m["sed"] = P.catalog_sed(m["target"], cats)
    json.dump(P.sanitize(m) if hasattr(P, "sanitize") else m, open(p, "w"), separators=(",", ":"))
    print(f"[OK] {k}: gaia {len(cats['gaia'])}, catwise {len(cats['catwise'])}, 2mass {len(cats['tmass'])}; SED: " +
          ", ".join((f"{s['band']} {s['flux_ujy']:.4g} uJy (sep {s['sep']}\")" if 'flux_ujy' in s else s['note']) for s in m["sed"]))
