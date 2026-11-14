"""Dump text outputs, errors and figures from an executed notebook."""
import json, sys, base64, os, re
nb = json.load(open(sys.argv[1])); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
fig = 0
for ci, c in enumerate(nb["cells"]):
    if c["cell_type"] != "code": continue
    src = "".join(c["source"]).strip().splitlines()
    head = src[0][:90] if src else ""
    for o in c.get("outputs", []):
        if o["output_type"] == "error":
            print(f"[cell {ci}] ERROR {o['ename']}: {o['evalue'][:300]}  <- {head}")
        elif o["output_type"] == "stream":
            t = "".join(o["text"]).strip()
            if t: print(f"[cell {ci}] {head}\n    " + t[:900].replace("\n", "\n    "))
        elif o["output_type"] in ("execute_result", "display_data"):
            d = o["data"]
            if "image/png" in d:
                fig += 1; p = f"{out}/fig{fig:02d}_cell{ci}.png"; open(p, "wb").write(base64.b64decode(d["image/png"])); print(f"[cell {ci}] FIGURE -> {p}   <- {head}")
            elif "text/plain" in d:
                t = "".join(d["text/plain"]).strip(); print(f"[cell {ci}] {head}\n    = " + t[:700].replace("\n", "\n      "))
