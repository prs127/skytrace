"""Build frontend/data/explore.json: the fastest-moving stars in Gaia DR3 (ESA), queried from NASA/IPAC IRSA, as
suggested targets for live searches. Selection rule (objective): proper motion > 3"/yr, ordered by proper motion;
members of the same system (within 0.2 deg) are merged, keeping the faster one. Usage: python make_explore.py OUT"""
import json, sys, math, time, pyvo
OUT = sys.argv[1] if len(sys.argv) > 1 else "../frontend/data/explore.json"
Q = "SELECT TOP 40 source_id, ra, dec, pmra, pmdec, parallax, phot_g_mean_mag, pm FROM gaia_dr3_source WHERE pm > 3000 ORDER BY pm DESC"
rows = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP").run_sync(Q, timeout=300).to_table()
out = []
for r in rows:
    ra, de = float(r["ra"]), float(r["dec"])
    if any(math.hypot((ra - o["ra"]) * math.cos(math.radians(de)), de - o["dec"]) < 0.2 for o in out):
        continue
    plx = float(r["parallax"]) if r["parallax"] == r["parallax"] else 0.0
    out.append({"id": str(r["source_id"]), "ra": round(ra, 8), "dec": round(de, 8), "pmra": round(float(r["pmra"]), 3),
                "pmdec": round(float(r["pmdec"]), 3), "plx": round(plx, 4), "g": round(float(r["phot_g_mean_mag"]), 2),
                "pm": round(float(r["pm"]) / 1000, 2), "dist_pc": round(1000 / plx, 2) if plx > 0 else None})
json.dump({"source": "Gaia DR3 (ESA) via NASA/IPAC IRSA TAP, table gaia_dr3_source", "query": Q,
           "rule": "proper motion > 3 arcsec/yr, fastest first; systems within 0.2 deg merged", "epoch_mjd": 57388.0,
           "built": time.strftime("%Y-%m-%dT%H:%MZ", time.gmtime()), "stars": out}, open(OUT, "w"), indent=1)
print(f"{len(out)} systems written to {OUT}")
for s in out: print(s["id"], s["pm"], '"/yr', s["dist_pc"], "pc, G", s["g"])
