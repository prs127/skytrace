# Skytrace: SPHEREx motion and spectrum viewer

Team **Skytrace**, 2026 NASA Space Apps Challenge, *Planet X and SPHEREx*.

Type a sky position (RA/Dec) or a target name and Skytrace shows every NASA SPHEREx exposure of that patch,
aligned on one grid, as a blinking movie. Moving and changing objects stand out. All 102 SPHEREx
spectral channels are usable: stack by visit, compare visits at the same wavelength, play a visit
through wavelength, and get an on-the-fly spectrum and light curve of the target.

## Features
- RA/Dec input in degrees or sexagesimal, or a target name; click the image to read and copy coordinates
- Shareable links: the full view state lives in the URL (`?field=…&ra=…&dec=…&det=…&mode=…`), plus embed code
- Five view modes: visits, same channel, wavelength scan, every exposure, custom A − B
- Difference images, detector-balanced stacks, mesh-median background flattening
- 102-channel coverage strip; per-exposure forced photometry spectrum and light curve
- Overlays: target track propagated from proper motion, Gaia DR3 (ESA) and CatWISE2020 (NASA) sources moved to the frame date,
  SPHEREx data-quality flags (saturation, artefacts, masked), experimental mover finder, compass and scale bar
- Blend warning when a catalogued star overlaps the target
- **Where in the sky**: an all-sky map (RA/Dec, ecliptic, Milky Way plane); a small rocket flies to each new search and circles it
  while the archive is searched; click the map to search there
- **Aladin Lite** (CDS) view of the field on IRSA's official SPHEREx DR1 all-sky HiPS cube (102 slices), AllWISE, 2MASS or DSS2
- **Report a candidate**: a plain-text write-up of the current view (link, pinned position, nearest Gaia/CatWISE stars,
  pixel flags, exposures, visits) to copy or download
- New data releases are picked up automatically: IRSA SPHEREx collections are discovered at run time

## How it works
1. `backend/pipeline.py` finds every SPHEREx Level-2 spectral image covering the position (IRSA SIA2, all current collections).
2. It reads only the needed pixels of each 70 MB file from the public AWS mirror (`s3://nasa-irsa-spherex`) with byte-range reads,
   and, for display, subtracts the zodiacal model, masks bad pixels by their FLAGS bits (bit names read from each file's
   `MSKN` keywords) and resamples onto a north-up 6.15″ grid.
3. It measures the target in every exposure on the original detector pixels with the method of IRSA's
   *SPHEREx Source Discovery Tool* notebook: MJy/sr → µJy with the official per-pixel solid-angle map
   (`solid_angle_pixel_map`, `cal-sapm-v3-2026-191`), r = 3 px photutils aperture (sub-pixel ×5), 7–16 px annulus
   (sigma-clipped median), error from the VARIANCE extension, and `n_bad` = aperture pixels carrying the
   CONTAINS_BAD_PIXEL flags (Explanatory Supplement, Table 16). Points with `n_bad ≥ 1` are hidden by default, as in
   the notebook. Our one addition: division by the encircled energy measured from the file's own ePSF (98.6–99.6%).
   The wavelength comes from the WCS-WAVE table.
4. The browser (Bootstrap 5, plain JavaScript, Plotly) does all stacking, differencing and display live.

## Live data services (all called by the code, checked by `tests/api_check.py`)
| Service | Operator | What Skytrace gets from it |
|---|---|---|
| IRSA SIA2 (`astroquery.ipac.irsa.Irsa.query_sia`, `list_collections`) | NASA/IPAC IRSA | Every SPHEREx spectral image covering a position, in all current releases (DR1, QR3, deep fields) |
| IRSA public AWS bucket `s3://nasa-irsa-spherex` (astropy + fsspec byte-range reads) | NASA/IPAC IRSA on AWS Open Data | Image pixels, FLAGS, VARIANCE, ZODI, ePSF, WCS-WAVE; DR1 solid-angle pixel maps |
| IRSA TAP (`https://irsa.ipac.caltech.edu/TAP`, PyVO) | NASA/IPAC IRSA | Gaia DR3 (ESA) `gaia_dr3_source`, CatWISE2020 `catwise_2020`, 2MASS `fp_psc` |
| IRSA HiPS `SPHEREx/spherex_allsky_cube` | NASA/IPAC IRSA (SPHEREx Science Data Center) | 102-channel all-sky map in the Aladin tab |
| IRSA DR1 cube tile (`ibe/data/spherex/dr1/hips5_cube`) | NASA/IPAC IRSA | Official `SPECTRAL_CHANNELS` table (102 channels) |
| CDS HiPS (AllWISE, 2MASS, DSS2) via Aladin Lite | CDS Strasbourg | Context images in the Aladin tab |

## Data sources (everything traceable)
| What | Source |
|---|---|
| SPHEREx images | IRSA SIA2 `spherex_dr1` + `spherex_qr3` (+ `_deep`), as the [SPHEREx archive guide](https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/) recommends; pixels read from IRSA's AWS copy via each row's `cloud_access` |
| 102 channels | Official SPHEREx DR1 `SPECTRAL_CHANNELS` table (DR1 all-sky cube) |
| Flags, zodi, wavelength | The SPHEREx file's own FLAGS, ZODI and WCS-WAVE extensions |
| Flux calibration | Official SPHEREx DR1 solid-angle pixel maps (IRSA S3, `dr1/solid_angle_pixel_map/cal-sapm-v3-2026-191`) |
| Photometry method | IRSA tutorial *SPHEREx Source Discovery Tool* (`aperture_photometry.py`) |
| Aperture correction | Measured from the SPHEREx files' own ePSF extension |
| All-sky HiPS in Aladin | IRSA `SPHEREx/spherex_allsky_cube` (SPHEREx Science Data Center); AllWISE, 2MASS, DSS2 HiPS from CDS |
| Star overlays / proper motions | Gaia DR3 (ESA) and CatWISE2020 (NASA WISE/NEOWISE; motion-fit positions `ra_pm/dec_pm` at MJD 57170), via IRSA TAP |
| Multi-mission spectrum points | 2MASS J/H/Ks (NASA/IPAC) and CatWISE2020 W1/W2, matched at each catalogue's own epoch with the target's proper motion; zero points Cohen et al. 2003 (2MASS) and Jarrett et al. 2011 (WISE) |
| WISE 0855 motion | Fit to 296 NEOWISE-R single-exposure detections (NASA), IRSA TAP |
| Target descriptions | Challenge text only |

## Validation (Prototype 5, 15 Nov 2026): full audit in `AUDIT.md`
- Displayed frames re-computed from the raw IRSA files (`validate_frames.py`): vs `reproject_interp` median difference
  0.01–0.16 × noise; vs the notebook's `reproject_exact` correlation ≥ 0.991, star fluxes within 0.4–1.6%.
- Channels from the official per-pixel CHANNEL_MAP: 52/52 sampled exposures (`channel_check.py`).
- Annual parallax modelled (formula = astropy GCRS to 0.05 mas); WISE 0855 parallax measured from NEOWISE: 438 ± 36 mas.
- Light curve divides out the spectrum (each point ÷ same-channel median).
- No flux step between releases: QR3/DR1 same-channel ratio 1.000 (M101) and 1.006 (Eps Indi B).
- Settings sweep 216/216 (3 passes); coordinate parser 6/6 formats (`parse_test.py`).

## Validation (Prototype 4, 14–15 Nov 2026)
- **Multi-mission flux check** (`tests/sed_check.py`): for 4 isolated, unsaturated stars, SPHEREx / catalogue median =
  0.995 (2MASS J), 0.999 (H), 0.980 (Ks), 0.988 (WISE W1), 1.029 (W2).
- **Cross-match**: Barnard's Star found in 2MASS at 0.3″ after ~170″ of motion; WISE 0855 is split by CatWISE2020 into
  3 entries, so its W1/W2 are reported as ambiguous instead of plotted.
- **Settings sweep** (`tests/settings_sweep.py`), 3 passes on 3 fields, 216/216 checks: visit grouping vs the gap/span
  sliders, detector filters, channel ± tolerance, λ-scan order, difference images vs frame − reference (all 3 references),
  custom A − B, display controls, overlays, frame/speed controls, share-link round trip, spectrum point counts.
- **Live services** (`tests/api_check.py`), 3 runs: SIA2, S3 pixels, solid-angle maps, TAP (Gaia/CatWISE/2MASS), HiPS,
  channel table: all OK. Live search of a new position: 290 images, same as IRSA's count.

## Validation (Prototype 3, real data, 14 Nov 2026)
- **Notebook parity** (`tests/notebook_parity.py`): on the same native pixels, Skytrace's photometry equals the IRSA
  notebook's own functions (`sa_mjy_scale_map` + `extract_photometry` + variance sum) to ≤ 2×10⁻⁶ in flux and error,
  and its bad-pixel decision matches the notebook's `extract_dqf` count in 47/47 exposures (4 targets).
- Unit conversion: 1 MJy/sr × 1 arcsec² = 23.5044 µJy, identical to astropy units and the notebooks' formula.
- **Official DR1 spectral cube**: Skytrace / cube flux per channel, median 0.997 and 1.010 for two isolated stars
  (each detector within ±3%) (`tests/cube_check.py`).
- WISE W1/W2 for isolated stars: median SPHEREx/WISE 1.04 (8 and 7 stars; different bandpasses) (`tests/photval.py`).
- Completeness: every image IRSA lists is in each field (R Dra deliberately capped at 700 of 2,493) (`tests/completeness.py`).
- Flag bit numbers read per file: identical in DR1, DR1-deep, QR3 and QR3-deep.
- Sky map: Mollweide round trip 2×10⁻¹³°, ecliptic and Galactic plane within 0.04″ of astropy.
- Barnard's Star and R Draconis saturate SPHEREx in every exposure (OVERFLOW/SUR_ERROR/BLOOM at the core): their
  photometry is correctly withheld from clean plots; their motion and images are still shown.

## Validation (Prototype 2, real data)
- IRSA's six SPHEREx tutorial notebooks executed: 35/35 published values reproduced.
- Exposure lists identical to the SIA2 `curl` query in the SPHEREx archive guide (258/258 for WISE 0855).
- Raw pixels identical to IRSA's cutout service; wavelengths within 0.07 nm of the tutorial's.
- Spectra agree with the official SPHEREx DR1 all-sky cube channel by channel (see `tests/cube_check.py`).
- Photometry agreed with WISE W1/W2 to 2–3% (2 px aperture, superseded by the notebook method in Prototype 3).
- Shift-and-add keeps a mover fixed to ~0.1 px across visits (`tests/shift_test.py`).

## Validation (Prototype 1, real data)
- Gaia DR3 stars land within 0.04 px (median) of SPHEREx peaks in every field.
- Barnard's Star and Epsilon Indi B centroids follow their catalogue proper motion within 0.1 px per visit.
- WISE 0855 detected at S/N 26–38 per visit above 4 µm; blended with a G=16.3 background star 8.8″ away in 2025–26.
- M101 control: 84 D2 exposures, identical to IRSA's cutout tutorial.

## Run
```bash
pip install -r requirements.txt
cd backend
python build_static.py ../frontend/data          # pre-build the challenge targets (~8 min)
uvicorn server:app --port 8080                  # live mode: any RA/Dec, http://localhost:8080
# or static demo only: cd frontend && python -m http.server 8080
# public deployment (Google Cloud Run + GitHub Pages backup): see DEPLOY.md
```
Docker / Hugging Face Space: `docker build -t skytrace . && docker run -p 7860:7860 skytrace`

## Data and credits
- SPHEREx spectral images: NASA/IPAC Infrared Science Archive (IRSA), collections `spherex_dr1`, `spherex_qr3` (and deep-field variants).
- SPHEREx DR1 solid-angle pixel maps and ePSFs (SPHEREx calibration products, IRSA); SPHEREx DR1 all-sky HiPS cube (IRSA).
- Gaia DR3 (ESA) and CatWISE2020 via IRSA TAP. WISE 0855 position and proper motion: our fit to NEOWISE-R single-exposure detections (IRSA TAP).
- Photometry method from IRSA's tutorial *SPHEREx Source Discovery Tool* (Caltech/IPAC-IRSA; functions adapted from code by Zafar Rustamkulov).
- Inspired by WiseView (Backyard Worlds: Planet 9). Libraries: Astropy, Astroquery, PyVO, photutils, SciPy, FastAPI, Bootstrap 5, Plotly.js, the Rajdhani font
  (Indian Type Foundry, SIL OFL 1.1), and Aladin Lite v3.8.2 (CDS, Strasbourg; LGPL-3.0, vendored unmodified, licence in `frontend/vendor/ALADIN-LITE-LICENSE.txt`).
- This work has made use of the NASA/IPAC Infrared Science Archive, which is funded by NASA and operated by the California Institute of Technology.

## Use of SI (superintelligence) tools
Portions of the code and documentation were written with Claude (Anthropic), an SI tool, and reviewed, tested and
directed by team Skytrace; the backend source files say so in their headers. No NASA logos or mission insignia are used.
All science numbers come from the archives listed above and were checked against NASA's SPHEREx tutorial code.

## Licence
Apache-2.0
