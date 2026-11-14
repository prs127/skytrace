"""Completeness check: for every field, query IRSA SIA2 directly over HTTP (the same request as the
`curl` example in the SPHEREx archive guide) and confirm the field contains every image IRSA lists.
Usage: python tests/completeness.py [DATA_DIR]"""
import io, json, sys, time, warnings
import requests
from astropy.io.votable import parse_single_table
warnings.filterwarnings("ignore")
D = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/skytrace/frontend/data"
COLLS = ["spherex_dr1", "spherex_dr1_deep", "spherex_qr3", "spherex_qr3_deep"]
idx = json.load(open(f"{D}/index.json"))
all_ok = True
for f in idx["fields"]:
    m = json.load(open(f"{D}/{f['key']}.json")); t = m["target"]
    # search position used by the pipeline: target propagated to MJD 61000
    dt = (61000.0 - t["epoch_mjd"]) / 365.25
    import math
    ra = t["ra"] + t["pmra"] * dt / 3.6e6 / math.cos(math.radians(t["dec"])); dec = t["dec"] + t["pmdec"] * dt / 3.6e6
    listed = set()
    for c in COLLS:
        for attempt in range(4):
            try:
                r = requests.get("https://irsa.ipac.caltech.edu/SIA", params={"COLLECTION": c, "POS": f"circle {ra} {dec} {1/3600}", "RESPONSEFORMAT": "VOTABLE"}, timeout=120)
                r.raise_for_status(); tab = parse_single_table(io.BytesIO(r.content)).to_table(use_names_over_ids=True); break
            except Exception as exc:
                time.sleep(3 * (attempt + 1)); tab = None
        if tab is None: print(f"  {f['key']}: {c} query failed"); all_ok = False; continue
        if len(tab): listed |= {(str(x["obs_id"]), int(str(x["energy_bandpassname"])[-1])) for x in tab}
    have = {(e["obs_id"], e["det"]) for e in m["exposures"]}
    cap = m.get("completeness", {})
    missing = listed - have
    capped = cap.get("requested", len(listed)) < cap.get("found_in_archive", len(listed))
    ok = (not missing) or capped
    all_ok &= ok
    print(f"{f['key']:9s}: IRSA lists {len(listed)} images; field has {len(have)}; missing {len(missing)}"
          + (f" (field deliberately capped at {cap['requested']} of {cap['found_in_archive']}, evenly in time)" if capped else "")
          + f"  -> {'OK' if ok else 'INCOMPLETE'}")
print("ALL COMPLETE" if all_ok else "PROBLEMS FOUND")
