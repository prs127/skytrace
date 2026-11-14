"""WISE 0855: fit position, proper motion AND parallax to NEOWISE-R single-exposure detections (NASA WISE, IRSA TAP).
Model per detection: RA*cos(dec) and Dec offsets = position + proper motion x time + parallax x parallax factors
(parallax factors from Earth's barycentric position, astropy; WISE is in low Earth orbit). Weighted least squares
with per-coordinate scatter estimated from the residuals; 3-sigma clipping."""
import warnings, numpy as np, pyvo, sys, json
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/claude/skytrace/backend"); import pipeline as P
tap = pyvo.dal.TAPService("https://irsa.ipac.caltech.edu/TAP")
t = tap.run_sync("""SELECT ra, dec, mjd, w2mpro, w2snr, w1mpro, w1snr FROM neowiser_p1bs_psd
WHERE CONTAINS(POINT('ICRS',ra,dec), CIRCLE('ICRS',133.775,-7.2435,0.012))=1 AND w2snr > 4""").to_table()
red = np.array([(not np.isfinite(r["w1mpro"])) or (r["w1mpro"] - r["w2mpro"] > 2.0) or (r["w1snr"] < 3) for r in t]); t = t[red]
mjd = np.array(t["mjd"], float); ra = np.array(t["ra"], float); de = np.array(t["dec"], float)
ref, ra_r, de_r = 58000.0, 133.7786805, -7.2437525          # current Skytrace track (NEOWISE PM-only fit)
x = (ra - ra_r) * np.cos(np.radians(de_r)) * 3.6e6; y = (de - de_r) * 3.6e6   # mas
pa, pd = np.array([P.parallax_offset_mas(ra_r, de_r, 1.0, m) for m in mjd]).T
dt = (mjd - ref) / 365.25
pmx = x - (-8131.0) * dt; pmy = y - 667.0 * dt
ok = np.hypot(pmx, pmy) < 6000                               # detections within 6" of the current track
for it in range(5):
    n = ok.sum(); one, zero = np.ones(n), np.zeros(n)
    A = np.vstack([np.column_stack([one, zero, dt[ok], zero, pa[ok]]), np.column_stack([zero, one, zero, dt[ok], pd[ok]])])
    b = np.concatenate([x[ok], y[ok]])
    sol, *_ = np.linalg.lstsq(A, b, rcond=None); res = b - A @ sol
    sig = 1.4826 * np.median(np.abs(res))
    rx, ry = res[:n], res[n:]; keep = np.zeros_like(ok); keep[np.where(ok)[0]] = (np.abs(rx) < 3 * sig) & (np.abs(ry) < 3 * sig)
    if (keep == ok).all(): break
    ok = keep
cov = np.linalg.inv(A.T @ A) * sig ** 2; err = np.sqrt(np.diag(cov))
x0, y0, pmra, pmdec, plx = sol
ra0 = ra_r + x0 / 3.6e6 / np.cos(np.radians(de_r)); de0 = de_r + y0 / 3.6e6
out = {"ra": ra0, "dec": de0, "pmra": pmra, "pmdec": pmdec, "plx": plx, "epoch_mjd": ref, "err": {"pmra": err[2], "pmdec": err[3], "plx": err[4], "pos_mas": float(err[0])},
       "n": int(ok.sum()), "mjd_range": [float(mjd[ok].min()), float(mjd[ok].max())], "scatter_mas": float(sig)}
print(json.dumps(out, indent=1))
