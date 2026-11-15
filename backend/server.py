"""
Skytrace live server (FastAPI).

Serves the Bootstrap front end and lets users search ANY RA/Dec: the field is
built on demand from the IRSA SPHEREx archive and cached on disk, so the next
visitor gets it instantly. Collections are discovered at query time, so a new
SPHEREx release appears without a code change.

Run:  uvicorn server:app --host 0.0.0.0 --port 8080   (from backend/; Cloud Run sets $PORT)
Portions generated with Claude (Anthropic), reviewed by team Skytrace.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline import Target, build_field, discover_collections, write_package

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DATA = Path(os.environ.get("SKYTRACE_DATA", FRONTEND / "data"))
DATA.mkdir(parents=True, exist_ok=True)
INDEX = DATA / "index.json"
MAX_JOBS = int(os.environ.get("SKYTRACE_MAX_JOBS", "2"))
MAX_EXPOSURES = int(os.environ.get("SKYTRACE_MAX_EXPOSURES", "700"))

app = FastAPI(title="Skytrace", version="0.1.0")
JOBS: dict[str, dict] = {}
_lock = threading.Lock()
_releases_cache: dict = {"t": 0.0, "collections": []}


def _index() -> dict:
    try:
        return json.loads(INDEX.read_text())
    except Exception:
        return {"fields": []}


def _add_to_index(meta: dict):
    with _lock:
        idx = _index()
        entry = {"key": meta["key"], "name": meta["name"], "ra": meta["grid"]["crval"][0],
                 "dec": meta["grid"]["crval"][1], "n": len(meta["exposures"]), "built": meta["built"]}
        idx["fields"] = [f for f in idx.get("fields", []) if f["key"] != meta["key"]] + [entry]
        idx["collections"] = meta.get("collections", [])
        tmp = INDEX.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, indent=1))
        tmp.replace(INDEX)


# Field sizes users can choose (arcmin -> grid pixels of 6.15"). Larger fields catch faster movers but take longer
# to fetch: the archive reads scale with the number of image rows (about x1.6 for 15', x2.2 for 20').
FIELD_SIZES = {9: 89, 15: 147, 20: 195}


def field_key(ra: float, dec: float, pmra: float, pmdec: float, size: int = 9) -> str:
    # ~4 arcsec rounding so repeated searches of the same spot hit the cache (size 9 keeps the original keys)
    extra = "" if size == 9 else f",{size}"
    h = hashlib.sha1(f"{ra:.3f},{dec:.3f},{pmra:.0f},{pmdec:.0f}{extra}".encode()).hexdigest()[:10]
    return f"f{h}"


@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version, "fields": len(_index().get("fields", []))}


@app.get("/api/releases")
def releases():
    """SPHEREx collections IRSA serves right now (cached 10 minutes)."""
    if time.time() - _releases_cache["t"] > 600:
        import pipeline
        _releases_cache["collections"] = discover_collections()
        # only remember a list IRSA actually returned (not the built-in fallback used during an IRSA outage)
        _releases_cache["t"] = time.time() if pipeline._COLLECTIONS_CACHE else 0
    return {"collections": _releases_cache["collections"], "checked": _releases_cache["t"]}


def _missing_catalogs(key: str) -> bool:
    """A field saved while an IRSA catalogue query failed is rebuilt on the next request instead of being reused."""
    try:
        return bool(json.loads((DATA / f"{key}.json").read_text()).get("catalog_warnings"))
    except Exception:
        return False


@app.post("/api/field")
def start_field(ra: float = Query(..., ge=0, lt=360), dec: float = Query(..., ge=-90, le=90),
                pmra: float = 0.0, pmdec: float = 0.0, epoch_mjd: float = 57388.0, plx: float = 0.0,
                name: str | None = None, force: int = 0, size: int = 9):
    if size not in FIELD_SIZES:
        raise HTTPException(400, f"size must be one of {sorted(FIELD_SIZES)} arcmin")
    key = field_key(ra, dec, pmra, pmdec, size)
    if not force and (DATA / f"{key}.json").exists() and not _missing_catalogs(key):
        return {"id": None, "status": "done", "key": key, "message": "cached"}
    running = [j for j in JOBS.values() if j["status"] == "running"]
    for j in running:
        if j["key"] == key:
            return j
    if len(running) >= MAX_JOBS:
        raise HTTPException(429, "Server busy building other fields, try again in a minute.")
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "status": "running", "key": key, "message": "Queued", "started": time.time()}
    JOBS[jid] = job
    # Shared, public list: only the Explore menu's own label format is accepted; visitors' personal names stay in their browser.
    ok_name = name and re.fullmatch(r"Fast star \d{1,2}\.\d{2}″/yr \(Gaia DR3 \d{6,20}\)", name)
    label = name if ok_name else f"RA {ra:.4f} Dec {dec:+.4f}"
    tgt = Target(key, label, ra, dec, pmra, pmdec, epoch_mjd, note="User search.", source="Coordinates entered by user", plx=plx)

    def run():
        try:
            pkg = build_field(tgt, npix=FIELD_SIZES[size], max_exposures=MAX_EXPOSURES, progress=lambda m: job.update(message=m))
            write_package(pkg, str(DATA))
            _add_to_index(pkg["meta"])
            job.update(status="done", message=f"Done: {len(pkg['meta']['exposures'])} exposures")
        except Exception as exc:
            job.update(status="error", message=str(exc))
    threading.Thread(target=run, daemon=True).start()
    return job


@app.get("/api/job/{jid}")
def job_status(jid: str):
    if jid not in JOBS:
        raise HTTPException(404, "Unknown job")
    return JOBS[jid]


# Data first (user-built fields may live outside the front-end folder), then the page.
app.mount("/data", StaticFiles(directory=str(DATA)), name="data")
app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
