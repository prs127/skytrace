"""Pre-build the challenge test fields for the static prototype.
Usage: python build_static.py OUTDIR [key ...]
Written with Claude (Anthropic, AI assistant) and reviewed by team Skytrace."""
import json, os, sys, time
from pipeline import build_field, write_package, discover_collections
from targets import TARGETS

out = sys.argv[1] if len(sys.argv) > 1 else "../frontend/data"
keys = sys.argv[2:] or [t.key for t in TARGETS]
os.makedirs(out, exist_ok=True)
cols = discover_collections()
index_path = os.path.join(out, "index.json")
index = json.load(open(index_path)) if os.path.exists(index_path) else {"fields": []}
for t in TARGETS:
    if t.key not in keys:
        continue
    t0 = time.time()
    try:
        pkg = build_field(t, npix=89, workers=32, max_exposures=700, collections=cols)
    except Exception as exc:
        print(f"[FAIL] {t.key}: {exc}"); continue
    write_package(pkg, out)
    m = pkg["meta"]
    entry = {"key": t.key, "name": t.name, "ra": m["grid"]["crval"][0], "dec": m["grid"]["crval"][1],
             "n": len(m["exposures"]), "built": m["built"]}
    index["fields"] = [f for f in index["fields"] if f["key"] != t.key] + [entry]
    index["collections"] = cols
    json.dump(index, open(index_path, "w"), indent=1)
    c = m["completeness"]
    print(f"[OK] {t.key}: {len(m['exposures'])} exposures in {time.time()-t0:.0f}s  (archive listed {c['found_in_archive']}, requested {c['requested']}, read {c['read']})", flush=True)
