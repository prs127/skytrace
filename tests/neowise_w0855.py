"""Independent check of the WISE 0855 track (used by Skytrace) with NEOWISE-R single-exposure detections (IRSA TAP)."""
import warnings, numpy as np, pyvo, time
warnings.filterwarnings("ignore")
tap = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP")
t0 = time.time()
q = """SELECT ra, dec, mjd, w2mpro, w2snr, w1mpro, w1snr, qual_frame, cc_flags
FROM neowiser_p1bs_psd
WHERE CONTAINS(POINT('ICRS',ra,dec), CIRCLE('ICRS',133.775,-7.2435,0.012))=1 AND w2snr > 4"""
t = tap.run_sync(q).to_table(); print(f"{len(t)} NEOWISE detections in {time.time()-t0:.0f}s")
# W0855 is extremely red: W1-W2 > 3. Keep detections with w1 faint or absent.
red = np.array([(not np.isfinite(r["w1mpro"])) or (r["w1mpro"] - r["w2mpro"] > 2.0) or (r["w1snr"] < 3) for r in t])
t = t[red]; print(f"{len(t)} very red detections (W1-W2>2 or no W1): WISE 0855 candidates")
mjd = np.array(t["mjd"], float); ra = np.array(t["ra"], float); de = np.array(t["dec"], float)
# Skytrace track: challenge coords at MJD 55400 + Luhman&Esplin PM
def track(m): dt = (m - 55400.0) / 365.25; return 133.795129 - 8.100 * dt / 3600 / np.cos(np.radians(-7.245147)), -7.245147 + 0.700 * dt / 3600
pr, pd = track(mjd); off = np.hypot((ra - pr) * np.cos(np.radians(de)), de - pd) * 3600
ok = off < 6; print(f"{ok.sum()} detections within 6\" of the Skytrace track; median offset {np.median(off[ok]):.2f}\"")
# fit linear motion to NEOWISE detections
ref = 58000.0; dt = (mjd[ok] - ref) / 365.25; c = np.cos(np.radians(-7.24))
A = np.vstack([np.ones(ok.sum()), dt]).T
(ra0, pmra), *_ = np.linalg.lstsq(A, ra[ok], rcond=None); (de0, pmde), *_ = np.linalg.lstsq(A, de[ok], rcond=None)
print(f"NEOWISE fit ({mjd[ok].min():.0f}-{mjd[ok].max():.0f}): pmra*cosdec = {pmra*3600*c:+.2f}\"/yr, pmdec = {pmde*3600:+.2f}\"/yr  (Skytrace uses -8.10, +0.70)")
for name, m in [("WiseView first frame 2014.3-2014.8 (mid 2014.55)", 56836.0), ("SPHEREx visit 2 (2025-11)", 60993.5)]:
    fr, fd = ra0 + pmra * (m - ref) / 365.25, de0 + pmde * (m - ref) / 365.25; sr, sd = track(m)
    print(f"{name}: NEOWISE-fit {fr:.6f} {fd:.6f} | Skytrace track {sr:.6f} {sd:.6f} | diff {np.hypot((fr-sr)*c, fd-sd)*3600:.2f}\"")
print(f"WiseView link centre: 133.786245 -7.244372 -> Skytrace track passes there at MJD", end=" ")
m = np.linspace(54000, 61000, 70001); sr, sd = track(m); i = np.argmin(np.hypot((sr - 133.786245) * c, sd + 7.244372)); print(f"{m[i]:.0f} ({2000 + (m[i]-51544.5)/365.25:.2f}), miss {np.hypot((sr[i]-133.786245)*c, sd[i]+7.244372)*3600:.2f}\"")

# ---- figure: NEOWISE detections vs Skytrace track, plus SPHEREx centroids per visit
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, json, gzip, sys
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P
from scipy.ndimage import center_of_mass
m = json.load(open("/home/claude/skytrace/frontend/data/wise0855.json")); n = m["grid"]["npix"]
img = np.frombuffer(gzip.open("/home/claude/skytrace/frontend/data/wise0855.img.bin.gz").read(), "<f2").astype(float).reshape(-1, n, n)
w = P.make_grid_wcs(*m["grid"]["crval"], n); ex = m["exposures"]; mj = np.array([e["mjd"] for e in ex])
sp = []
for lo, hi in [(60790, 60820), (60970, 61030), (61140, 61180)]:
    idx = [i for i, e in enumerate(ex) if e["wave"] and e["wave"] > 4.0 and lo <= e["mjd"] <= hi]
    a = img[idx]; fin = np.isfinite(a); co = np.where(fin, a, 0).sum(0) / np.maximum(fin.sum(0), 1)
    mm = np.mean(mj[idx]); prr, pdd = track(mm); x, y = [float(v) for v in w.world_to_pixel_values(prr, pdd)]
    xi, yi = int(round(x)), int(round(y)); sub = co[yi-2:yi+3, xi-2:xi+3] - np.median(co); sub[sub < 0] = 0
    cy, cx = center_of_mass(sub); r_, d_ = w.pixel_to_world_values(xi - 2 + cx, yi - 2 + cy); sp.append((mm, float(r_), float(d_), len(idx)))
fig, ax = plt.subplots(1, 2, figsize=(13, 4.8))
yr = lambda q: 2000 + (np.asarray(q) - 51544.5) / 365.25
tt = np.linspace(56500, 61300, 200); tr, td = track(tt)
ax[0].plot(yr(mjd[ok]), (ra[ok] - 133.79) * 3600 * c, ".", ms=3, alpha=.5, label=f"NEOWISE single exposures ({ok.sum()})")
ax[0].plot(yr(tt), (tr - 133.79) * 3600 * c, "k-", lw=1, label="Skytrace track (challenge coords + Luhman & Esplin 2016 PM)")
ax[0].plot([yr(s[0]) for s in sp], [(s[1] - 133.79) * 3600 * c for s in sp], "r*", ms=14, label="SPHEREx centroid per visit (λ > 4 µm)")
ax[0].axvspan(2014.3, 2014.8, color="orange", alpha=.25, label="your WiseView frame 2014.3–2014.8")
ax[0].set_xlabel("year"); ax[0].set_ylabel("ΔRA·cos(Dec) from 133.79° (arcsec)"); ax[0].legend(fontsize=7); ax[0].set_title("WISE 0855 east–west motion: three independent datasets", fontsize=10)
ax[1].plot(yr(mjd[ok]), (de[ok] + 7.2435) * 3600, ".", ms=3, alpha=.5); ax[1].plot(yr(tt), (td + 7.2435) * 3600, "k-", lw=1)
ax[1].plot([yr(s[0]) for s in sp], [(s[2] + 7.2435) * 3600 for s in sp], "r*", ms=14)
ax[1].set_xlabel("year"); ax[1].set_ylabel("ΔDec from −7.2435° (arcsec)"); ax[1].set_title("north–south (parallax wobble visible in NEOWISE)", fontsize=10)
plt.tight_layout(); plt.savefig("figs/w0855_track.png", dpi=85)
for s in sp:
    sr, sd = track(s[0]); print(f"SPHEREx visit MJD {s[0]:.0f} ({s[3]} exp): centroid offset from Skytrace track {np.hypot((s[1]-sr)*c, s[2]-sd)*3600:.2f}\"  ({np.hypot((s[1]-sr)*c, s[2]-sd)*3600/6.15:.2f} px)")
