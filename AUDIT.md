# Skytrace: scientific audit and challenge alignment

Team Skytrace · NASA Space Apps 2026 · "Planet X and SPHEREx" · audit of 15 Nov 2026.
Every number below comes from a test in `tests/` run on real SPHEREx data. Section 1 is written the way a critical
astrophysicist would review each function; section 2 maps the challenge text line by line; section 3 covers data updates;
sections 4–5 cover judging.

## 1. Function-by-function audit (what a reviewer would check, what we found, what is still limited)

| # | What the tool shows | How it is computed | Independent check (result) | Known limit, stated in the tool |
|---|---|---|---|---|
| 1 | Which images exist | IRSA SIA2 over every SPHEREx collection found at run time (DR1, QR3, deep fields); duplicates (same `obs_id` + detector) removed, DR preferred over QR | `completeness.py`: every image IRSA lists is in every field (258/258, 358/358, 458/458, 335/335, 376/376; R Dra capped at 700 of 2,493, evenly in time); live search 290 = IRSA count | R Dra is capped for transfer time (stated) |
| 2 | Pixels | Byte-range reads of the L2 files on IRSA's AWS bucket | Raw pixels identical to IRSA's cutout service (Prototype 1) | – |
| 3 | Bad-pixel flags | Bit names read from each file's `MSKN` keywords, as the notebook does | Bits identical in DR1, DR1-deep, QR3 and QR3-deep | – |
| 4 | The blink images | IMAGE − ZODI − sky median, flagged pixels masked, resampled (normalised bilinear) onto a north-up 6.15″ TAN grid | `validate_frames.py`, 93 + 46 exposures re-processed from the raw files: browser vs `reproject_interp` median difference 0.01–0.16 × stack noise; vs the notebook's flux-conserving `reproject_exact` pixel correlation ≥ 0.991, star fluxes within 0.4–1.6% (one 4-exposure frame 4.7%) | Bilinear resampling slightly smooths noise and PSF wings: display only, all measurements use original pixels |
| 5 | Visit stacks, A − B, differences | Inverse-variance mean per detector, equal weight across detectors; difference = frame − reference | `settings_sweep.py`: membership exact; differences equal frame − reference to < 10⁻⁴ for all 3 references; custom A − B exact | A stack averages many channels: a band average, good for positions, not spectra (stated) |
| 6 | Channels and wavelengths | Wavelength at the target pixel from WCS-WAVE (`key="W"`, `sip=None`, as in the notebooks); channel from the official per-pixel CHANNEL_MAP | Our 102-channel table = official SPECTRAL_CHANNELS (0.00 nm); channel = official map in 52/52 sampled exposures (`channel_check.py`). Earlier "nearest centre" rule disagreed in 3/52 (boundary/edge pixels): replaced | The LVF changes wavelength across the field: ≤ 0.47 channel widths (0.4–1.3%) at the corners of the full 9.1′ view (stated in the help text) |
| 7 | Positions and motion | Grid WCS; target = proper motion + annual parallax from Earth's ephemeris (astropy); Gaia stars likewise | Parallax formula = astropy GCRS to 0.05 mas; Gaia stars land ≤ 0.04 px from SPHEREx peaks; target marker vs measured centroid 0.09–0.14 px for Epsilon Indi B (better than motion-only in all 4 visits) | Parallax is ≤ 0.09 px for these targets, at the level of centroid noise; WISE 0855 centroids are pulled by a G = 16.3 star 7.7″ away (blend warning shown) |
| 8 | WISE 0855 distance and motion | Fit of position, motion and parallax to 277 NEOWISE-R detections | Parallax 438 ± 36 mas vs published 438.9 ± 3.0 (Kirkpatrick et al. 2019); motion within 1.4σ of published | Our parallax is 12× less precise than Spitzer's (stated as our measurement) |
| 9 | Target brightness (spectrum) | IRSA Source Discovery Tool method on original pixels: per-pixel solid-angle map, r = 3 px subpixel aperture, 7–16 px σ-clipped annulus, VARIANCE errors, `n_bad` rule; ÷ ePSF encircled energy (our only addition, 0.4–1.4%) | `notebook_parity.py`: = notebook functions to ≤ 2×10⁻⁶ (flux and error), bad-pixel decision: every measurement the notebook flags is flagged by Skytrace too (36/36 in 3 fields re-checked 15 Nov evening; Skytrace's check is stricter, see below); official DR1 spectral cube 0.997 / 1.010; 2MASS J/H/Ks and WISE W1/W2 0.98–1.03 (`sed_check.py`); DR1 vs QR3 same-channel ratio 1.000 (M101 nucleus) and 1.006 (Eps Indi B): no calibration step between releases | Errors are statistical (VARIANCE) only, as in the notebook; saturated targets (Barnard, R Dra) withheld, as the notebook's `n_bad = 0` rule implies |
| 10 | 2MASS / WISE points | Catalogue magnitudes × published zero points; target matched at each catalogue's own epoch with its motion; CatWISE motion-fit positions (`ra_pm`, MJD 57170) | Barnard's Star found in 2MASS at 0.3″ after ~170″ of motion; ambiguous CatWISE matches refused (WISE 0855: 3 entries) | Broad bands vs narrow channels; catalogue epochs differ from SPHEREx (stated) |
| 11 | Light curve | Each clean point ÷ median of the same star in the same channel, so spectral shape cannot imitate variability | Fixed in this audit: the earlier version plotted raw flux per detector, mixing 17 channels | Needs ≥ 2 points per channel |
| 12 | Shift-and-add | Resample each exposure along a trial motion | Moving target fixed to ≤ 0.15 px per visit (Eps Indi B), drifts 0.77 px without | Trial motion is linear (no parallax), as in WiseView |
| 13 | Moving-object finder | Rebuilt after judge feedback (the old first-vs-last-visit dipole search mostly fitted noise). Sources detected in each visit stack (S/N ≥ 5 seeds, ≥ 3.5 confirmations); visits registered and position errors fitted on the field's non-moving Gaia DR3 stars (σ² = a² + b²/SNR²); straight-line linking; reported only if ≥ 3 visits and ≥ 2/3 of covering visits, line χ²/dof < 4, motion ≥ 5σ and ≥ 0.5 px, flux within ×3, no neighbour within 2 px, nothing within 4 px of saturation | (1) Known movers: WISE 0855 7.21 ± 1.39″/yr vs catalogue 8.16; Eps Indi B 4.51 ± 0.68 vs Gaia DR3 4.68; 0 reports in Barnard, RW Aur, R Dra, M101 (`movers_ref_result.txt`). (2) Injection on the real exposures, 6 fields × 2 seeds, 288 fake sources: 86/133 movers with ≥ 0.5 px shift recovered (63/74 at S/N 20–40), 0/144 still injections reported, 0 unexplained reports; quoted errors conservative (median |z| 0.21) (`movers_inject_result.txt`). (3) Independent Python implementation = browser on 12 fields, same objects and motions (`movers_parity.py`) | Needs ≥ 3 visits; saturated stars skipped (Barnard's Star); objects crossing the field within one visit (asteroids) not searched |
| 14 | Overlays | Gaia DR3 (motion + parallax), CatWISE2020 (motion), 2MASS (at its 1997–2001 position), flags | Overlay toggles verified in the sweep | – |
| 15 | Sky map, Atlas | Mollweide RA/Dec; ecliptic and Galactic plane from J2000 constants; Atlas = Aladin Lite on IRSA's SPHEREx DR1 HiPS cube, one channel map at a time | Map lines match astropy to 0.04″. `atlas_frames.py`: for all 100 non-blank channels, choosing channel k makes Aladin load cube frame k (100/100). Fixed in this audit: Aladin Lite 3.8.2's own slider maps slice numbers to frames non-linearly and in reverse, and its default slice (frame 50) is one of the two blank dichroic frames, so the old Atlas showed an empty map | The HiPS cube is an all-epoch mosaic at 12.9″ pixels: no motion there (stated) |
| 16 | Older-survey comparison (DSS2, 2MASS, AllWISE) | Colour HiPS maps hosted by NASA IRSA (`irsa.ipac.caltech.edu/data/hips/CDS/...`), drawn by Aladin Lite at the field's centre and size. Switched from CDS identifiers in this audit: CDS has been unavailable since 9 Nov 2026, so the old buttons failed | `hips_align.py`: centroids of isolated slow Gaia DR3 stars (G 11–16.5, µ < 10 mas/yr) measured in the same tiles the viewer loads, all 6 fields. Worst-field median offset: DSS2 1.32″, 2MASS 0.45″, AllWISE 0.46″ (≤ 0.21 SPHEREx pixel). Eps Indi B appears in AllWISE where its Gaia motion puts it in 2010 (visual check) | DSS2 plates are 1950s–1990s, so its astrometry is coarser (stated as decades-old photographs). Aladin's usage logging to CDS is turned off |

Still open (said openly): 2026 ED138 is not detected (V ≈ 19.8, crowded field); CSA NEOSSat data is not integrated
(its archive was unreachable from the build environment, so it could not be verified); IRSA's Level-3
`l3_flux_corrections` product is not applied (the notebook does not apply it either).

## 2. Challenge text, line by line

| Challenge says | Skytrace does | Measure |
|---|---|---|
| "public-facing web tool to display images of the sky from SPHEREx" | Browser tool, no install or login; Cloud Run live site plus GitHub Pages backup | Public URLs |
| "making it easy for anyone to quickly see how they change over time" | One-click blink of visits, play/speed controls, difference images | Pre-built fields open in about 1 s; new positions in about 1.5 min |
| "Users will enter the coordinates (Right Ascension and declination)" | Decimal or sexagesimal input, target names, click-the-sky map | `parse_test.py`: 6 formats give the same position; out-of-range and nonsense input rejected with a message |
| "display a series of images of that patch like a little video" | Visits, Same band, λ scan, Every exposure, A − B | Sweep: frame membership exact |
| "Comets, asteroids, stars, brown dwarfs … reveal themselves by shifting position" | Shift-and-add, mover finder, catalogue overlays moved to each date, 2MASS-era positions | Eps Indi B fixed to ≤ 0.15 px; movers flagged at 145σ |
| "The Earth orbits the Sun too, causing objects near us to change their apparent positions … measure the distances" | Annual parallax modelled for every target; WISE 0855 distance measured from NEOWISE | 438 ± 36 mas vs 438.9 ± 3.0 published |
| "uniquely sensitive to … hydrogen, water, carbon dioxide, carbon monoxide" | Per-exposure spectrum over 0.75–5 µm with 102-channel coverage; λ-scan movie | Cube agreement ≈ 1% |
| "objects which often overlap or vary in brightness" | Blend warnings (Gaia neighbours); same-channel light curve | Light curve free of spectral shape |
| "Test your tool on Barnard's Star, Epsilon Indi B, WISE 0855, RW Aurigae, R Draconis" | All five pre-built and checked, plus M101 control | Completeness 100% |
| Easy to update with new releases | See section 3 | Run-time discovery |
| Display 102 bands creatively; per-detector stacks; spectra on the fly | Detector stacks and RGB, λ scan, channel strip, live spectrum | – |
| Add or subtract images taken at different times | Difference (3 references) and custom A − B | Exact to 10⁻⁴ |
| Let users choose the field of view | New searches download 9′, 15′ or 20′ fields; view size 2.5′ up to the full field; Aladin for wider context | 15′ build checked (147 px, 0 movers in COSMOS) |
| Overlay Gaia or WISE | Gaia DR3, CatWISE2020, plus 2MASS | Cross-match tests |
| Coordinates in the URL, embeddable | Full view state in the URL; embed code | Share-link round trip in the sweep |
| Display metadata such as contamination flags | Flag overlay, per-exposure flags table, `n_bad` | – |
| Use Astropy and Aladin | Astropy, astroquery, PyVO, photutils, reproject (tests); Aladin Lite | – |

## 3. Can it be updated with new data? Yes. How, and what still needs a person

1. **New SPHEREx releases appear automatically.** At every search the server asks IRSA for all SPHEREx collections
   (`Irsa.list_collections(servicetype='SIA', filter='spherex')`), so a future `spherex_qr4` or `spherex_dr2` is searched
   with no code change. When the same exposure is in two releases, the data release (DR) is preferred over the quick
   release (QR), and the newer DR over the older.
2. **Calibration follows the image's release.** Solid-angle maps and the official channel map are looked up in
   `s3://nasa-irsa-spherex/<release>/…/<newest version>/` for the release each image belongs to (DR1 and QR3 currently
   ship identical maps, checked pixel by pixel). If a new release has no map yet, DR1's is used and a warning is logged.
3. **Users see when a field is out of date.** "Check IRSA for new data releases" compares the collections a field was built from
   with what IRSA has now and offers a one-click rebuild.
4. **What needs a person:** the six pre-built demo fields are snapshots (`python build_static.py` refreshes them in about
   15 minutes), and the ePSF encircled-energy table (`tests/ee_all.py`, 2 minutes). Both are scripted.

## 4. Award categories: where Skytrace fits (honest ranking)
1. **Best Use of Data** (strongest fit): it makes SPHEREx, a NASA mission with data released since 2025, searchable by
   anyone in a browser, and combines it with WISE/NEOWISE, 2MASS and ESA Gaia, all through NASA/IPAC IRSA.
2. **Best Use of Science** (strong): every displayed quantity is checked against the official SPHEREx tutorial code, the
   official DR1 cube, other missions and published astrometry; limits are stated in the tool; the audit fixed its own errors.
3. **Art & Technology** (possible): the starship-console interface, all-sky journey map and λ-scan "spectrum movie" on a
   rigorous back end.
- Weaker fits: Most Inspirational and Best Storytelling depend on the demo; Galactic Impact, Global Connection and Local
  Impact are not what the tool is built for; Best Mission Concept does not apply (we built software, not a mission).

## 5. The five judging criteria
- **Impact:** the challenge text notes that volunteers found most known brown dwarfs and comets by comparing images.
  Skytrace gives anyone that ability for SPHEREx's 102-band survey, with no software to install, plus a shareable report.
  Gap: not yet tested with real volunteers.
- **Creativity:** channel-locked blinking (comparing visits at the same wavelength, so SPHEREx's changing filters cannot
  imitate motion); a λ-scan "spectrum movie"; light curves with the spectrum divided out; multi-mission points on the
  spectrum; parallax made visible; a console-style interface.
- **Validity:** see section 1. Every computation is reproduced by independent code, and limits are stated in the tool.
- **Relevance:** see section 2. SPHEREx data is the core; every objective and consideration is addressed.
- **Presentation:** depends on the demo. Suggested story: Pluto was found by blinking two images (challenge text), and
  Skytrace lets anyone blink SPHEREx. Show WISE 0855 moving, the parallax and distance, Epsilon Indi B with shift-and-add,
  then the spectrum checked against NASA's own tools.

## 6. Where each control comes from: SPHEREx tutorials, WiseView, the challenge, or new

IRSA tutorials (`caltech-ipac.github.io/irsa-tutorials`): **Intro** = Introduction to SPHEREx Spectral Images ·
**Cutouts** = Download a collection of SPHEREx Spectral Image cutouts · **PSF** = Understanding and Extracting the ePSF
Extension · **HiPS** = Using SPHEREx HiPS All-Sky Mosaic Cubes · **Mosaic** = Understanding and Analyzing SPHEREx Mosaic
Cubes · **SDT** = SPHEREx Source Discovery Tool demo.

| Control / panel | Origin | What Skytrace adds | Verified by |
|---|---|---|---|
| Archive search by RA/Dec (SIA2, all collections) | Intro, Cutouts, SPHEREx archive guide | Run-time discovery of new releases; DR preferred over QR | completeness.py, api_check.py |
| Reading pixels from IRSA's AWS bucket | Intro (cloud access) | Exact byte-range reads plus a larger connection pool (bit-identical output; ~27% fewer bytes; 3.4 → 5.4 exposures/s in the build environment) | identical-output test |
| IMAGE / FLAGS / VARIANCE / ZODI / EPSF / WCS-WAVE use | Intro | – | notebook parity |
| Flag names from `MSKN` keywords | Intro, SDT | Flag overlay; per-exposure flag table | per-release bit check |
| Wavelength per pixel (WCS key "W", `sip=None`) | Intro, Cutouts | Target-pixel wavelength in every exposure | 0.07 nm vs tutorial |
| 102 channels (SPECTRAL_CHANNELS) | HiPS | Official per-pixel CHANNEL_MAP for each exposure | channel_check.py 52/52 |
| ePSF | PSF | Aperture correction (encircled energy) | ee_all.py |
| Photometry, solid-angle maps, `n_bad` rule | SDT | – (identical method) | notebook_parity.py ≤ 2×10⁻⁶ |
| Reprojecting onto a common grid and subtracting | SDT (reproject + difference image) | Done live in the browser for any visits | validate_frames.py |
| Spectral cube comparison | HiPS, Mosaic | – | cube_check.py 0.997 / 1.010 |
| Blinking frames, visit windows, difference images, epoch legend (+ − ·), shift-and-add, stretch percentiles, FOV choice | WiseView (challenge resource) | Applied to SPHEREx's 102 channels | settings_sweep.py |
| Detector stacks, spectra on the fly, add/subtract, FOV, Gaia/WISE overlays, URL/embed, flags, Astropy + Aladin, release updates | Challenge "Potential considerations" | – | AUDIT §2 |
| Same-band blinking and λ-scan (channel-locked so the changing filter cannot fake motion) | **New** | – | sweep |
| Visit-grouping sliders (gap and maximum length) | **New** | – | sweep |
| Detector-balanced stacks, mesh-median background flattening | **New** | – | validate_frames.py |
| 102-channel coverage strip | **New** | – | – |
| Light curve with the spectrum divided out | **New** | – | sweep |
| 2MASS overlay, 2MASS/WISE points on the spectrum (epoch-matched) | **New** | – | sed_check.py 0.98–1.03 |
| Annual parallax; WISE 0855 parallax from NEOWISE | **New** (challenge background mentions parallax) | – | astropy GCRS 0.05 mas; 438 ± 36 mas |
| Blend warning, mover finder (experimental), candidate report | **New** | – | ui_test.py |
| All-sky "where in the sky" map, console interface, live server | **New** | – | map geometry test |
| "?" help on every panel; quick start and glossary | **New** | – | new_ui_test.py |
| Image-source switcher (DSS2 optical, 2MASS, AllWISE) | **New** (Aladin, a challenge consideration) | Same centre and field as the SPHEREx view; NASA IRSA's HiPS copies, so it works while CDS is down | src_geom.py: centre identical, field 9.10′ / 4.00′; hips_align.py: Gaia stars ≤ 1.32″ (DSS2), ≤ 0.46″ (2MASS, AllWISE) |
| Console layout: control rail, image, tabbed data pane | **New** (WiseView-style image-first layout, modernised) | Panes fit the window and scroll on their own; controls can be hidden | layout_shot.py (5 window sizes), layout_ui_test.py |
| Explore: 25 fastest-moving Gaia DR3 stars | **New** | Objective rule (pm > 3″/yr), Gaia motion and parallax | explore_test.py: marker within 0.04–0.23 px of the star |
| Save image (PNG), download measurements (CSV) | **New** | – | new_ui_test.py: CSV = data (458/458 rows) |
| Pages: one-off animated Welcome, Home, Dashboard, How to use | **New** (Material 3 drawer + side sheet; Worldview-style timeline) | Library on the left, analysis on the right, both collapsible; field notes and blend warning behind small i / ! buttons; long texts collapsible | layout_ui_test.py, user_walkthrough.py |
| Saved places (named folders, rename, move, delete, notes, shareable folder link) | **New** (like map bookmarks) | Stored in the browser; the shared link carries the list, no server or accounts | user_walkthrough.py: folder opened in a fresh browser profile |
| Export PDF, one place per file, tick-box sections | **New** | Images, spectrum plot and table, light curve, movers and method, visits, exposures, flags, pinned spot, notes, settings, credits (jsPDF 4.2.1, MIT) | user_walkthrough.py: PDF holds only the ticked sections |

### User walkthrough (15 Nov 2026)
`tests/user_walkthrough.py` follows the How-to-use guide as a first-time user and as an astronomer: 70/70 checks.
It found three real bugs, all fixed: the dashboard collapsed after the spectrum's log-axis switch (Plotly's measuring box
and the export panel entered the page layout); the page jumped to the bottom on load (the visit strip scrolled the
page, not itself); the share link pointed at the welcome page instead of the dashboard. Reruns after the fixes:
settings_sweep 72/72 × 3 targets, ui_test, new_ui_test, layout_ui_test, movers_parity 0 mismatches.

### NASA IRSA outage, 15 Nov 2026 afternoon
IRSA's front end returned "502 Proxy Error" for about half of all requests (SIA image search and TAP catalogues).
Skytrace now retries every IRSA call with growing waits, never builds a field from a partial image list, rebuilds a
field whose catalogue lookup failed the next time it is requested, and the moving-object check refuses to run if
Gaia DR3 is missing (it needs Gaia stars to line up the visits and to label known stars). Pre-built targets do not
depend on IRSA.

### Full re-check, 15 Nov 2026 evening (all analysis tools on 15 fields)
`tests/tools_check.py` checks every analysis tool against an independent Python computation from the same data, on the
6 challenge fields and 9 random positions (8 drawn uniformly over the sky, plus the Galactic centre): visit grouping,
spectrum points and values, light-curve points and values, moving objects (browser = Python reference, every report
meets the stated tests), exposures table, Sources tab, every frame mode, difference, shift-and-add, CSV, report, Atlas,
comparison survey and the full PDF. `tests/every_control.py` clicks every control (80 checks). Found and fixed:
- **Light curve at an empty position** drew noise divided by its own median (scatter 23×). Now a channel is used only
  if the target is detected at ≥ 5σ there; otherwise the tab says no source is detected.
- **Light curve of saturated stars** (Barnard's Star, R Draconis: every measurement saturated; RW Aurigae: 8 usable
  points) is withheld and the tab says why; the guide no longer claims a light curve for R Draconis.
- **Catalogue queries could block for ever**: IRSA's TAP service stopped answering; requests had no time limit, so after
  a few the worker threads were all stuck and every later catalogue query failed. All requests now have time limits, and
  the catalogues are asked first from IRSA's Gator service (answered in ~1 s while TAP was down); TAP is the fallback.
  Gator and TAP give the same sources and values on all 6 challenge fields (`tests/catalog_services_check.py`; values
  differ only in the last printed digit because TAP sends binary float32).
- **Fields built without catalogues** can fetch them again in seconds (images kept), from the Moving objects and
  Sources tabs or automatically on the next request.
- **IRSA image search**: the four SPHEREx collections are queried at the same time with a 90 s limit per try (a single
  random field now builds in about 90 s instead of several minutes when IRSA is slow).
- **Crowded fields** (Galactic centre): almost every pixel is flagged SOURCE, so no image had a noise estimate; noise is
  now estimated from all unmasked pixels there.
- **Saved places**: a new user could not save into the starter folder (it got a new id every time it was read).
Results: tools_check 15 fields, every_control 80/80, user_walkthrough 70/70, settings_sweep 3 × 72/72, movers_parity 0
mismatches on 12 fields, catalog_services_check 0 differences.

### New-user test with random sky-map clicks, 15 Nov 2026 night
Following the guide as a first-time user on random positions found three more problems, all fixed:
- **An unflagged value 225 times too bright.** At a random position (RA 338.1192, Dec +22.8893) one D5 measurement read
  204,732 µJy against a median of 912 µJy, with no flag. Cause: a cosmic-ray pixel (TRANSIENT, 574 MJy/sr) centred 3.07 px
  from the target. The notebook's bad-pixel count (and ours, copied from it) only checks pixels whose centre is inside
  r = 3 px, but the flux sum (subpixel method) takes part of that pixel. Skytrace now checks every pixel that adds to the
  sum. All 22 fields were re-measured from the original files (`backend/rephot.py`): every flux reproduced exactly
  (difference 0), and 4-9 % of values per field are now flagged and hidden by default.
- **Unflagged outliers.** A value far from the same visit's other values at nearly the same wavelength (> 5× local
  scatter and > 3× its error, within 4 % and 15 days) is marked *outlier* and hidden like a flagged one: 6 of ~3,000 clean
  values in 16 fields, all in D5/D6. The PDF table lists every value with its flags.
- **Random clicks measured empty sky.** A sky-map click now centres the field on the nearest Gaia DR3 star (G < 18,
  within 90″), measures that star, and says so in the field name and note. Typed coordinates are measured exactly.
- During this test NASA IRSA's image search (SIA) and TAP returned 502 for every request; new searches could not be
  built until IRSA recovers. Already-built fields and the six challenge targets work.

## 7. Ideas considered and not built (and why)
- **Community database of candidates, ratings and favourites:** left out for this deadline (needs accounts, moderation
  and a persistent server; Cloud Run storage is temporary). Saved places and shared folder links cover personal use.
- **"Your sky tonight" (planetarium for the user's location and time):** rejected. It uses no SPHEREx data, duplicates
  free tools such as Stellarium, and would pull judges' attention away from the challenge objective (seeing SPHEREx images
  change over time). The location-free all-sky map already shows where a target is.
- **Server-side cutouts of other surveys (CDS hips2fits):** the service returned "Page unavailable" during development
  (CDS has been unavailable since 9 Nov 2026), so the comparison views draw NASA IRSA's copies of the same HiPS maps
  with Aladin Lite instead, and their alignment is checked in Python on the same tiles (`hips_align.py`).
