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
| 9 | Target brightness (spectrum) | IRSA Source Discovery Tool method on original pixels: per-pixel solid-angle map, r = 3 px subpixel aperture, 7–16 px σ-clipped annulus, VARIANCE errors, `n_bad` rule; ÷ ePSF encircled energy (our only addition, 0.4–1.4%) | `notebook_parity.py`: = notebook functions to ≤ 2×10⁻⁶ (flux and error), bad-pixel decision 47/47; official DR1 spectral cube 0.997 / 1.010; 2MASS J/H/Ks and WISE W1/W2 0.98–1.03 (`sed_check.py`); DR1 vs QR3 same-channel ratio 1.000 (M101 nucleus) and 1.006 (Eps Indi B): no calibration step between releases | Errors are statistical (VARIANCE) only, as in the notebook; saturated targets (Barnard, R Dra) withheld, as the notebook's `n_bad = 0` rule implies |
| 10 | 2MASS / WISE points | Catalogue magnitudes × published zero points; target matched at each catalogue's own epoch with its motion; CatWISE motion-fit positions (`ra_pm`, MJD 57170) | Barnard's Star found in 2MASS at 0.3″ after ~170″ of motion; ambiguous CatWISE matches refused (WISE 0855: 3 entries) | Broad bands vs narrow channels; catalogue epochs differ from SPHEREx (stated) |
| 11 | Light curve | Each clean point ÷ median of the same star in the same channel, so spectral shape cannot imitate variability | Fixed in this audit: the earlier version plotted raw flux per detector, mixing 17 channels | Needs ≥ 2 points per channel |
| 12 | Shift-and-add | Resample each exposure along a trial motion | Moving target fixed to ≤ 0.15 px per visit (Eps Indi B), drifts 0.77 px without | Trial motion is linear (no parallax), as in WiseView |
| 13 | Mover finder | 6σ positive/negative dipoles between first and last visit, catalogued static stars rejected | Finds Eps Indi B at 145σ | Not calibrated for completeness or false positives: labelled experimental |
| 14 | Overlays | Gaia DR3 (motion + parallax), CatWISE2020 (motion), 2MASS (at its 1997–2001 position), flags | Overlay toggles verified in the sweep | – |
| 15 | Sky map, Aladin | Mollweide RA/Dec; ecliptic and Galactic plane from J2000 constants; Aladin on IRSA's SPHEREx HiPS cube | Map lines match astropy to 0.04″ | The HiPS cube is an all-epoch mosaic: no motion there (stated) |

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
| Let users choose the field of view | 9.1′ / 6′ / 4′ / 2.5′; Aladin for wider context | – |
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
