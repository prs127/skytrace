# Skytrace: submission checklist and draft texts

Team Skytrace · NASA Space Apps Challenge 2026 · challenge "Planet X and SPHEREx".
Checked 14 Nov 2026 against the Project Submission Guide and the Judging & Awards Guide on spaceappschallenge.org,
plus the 2026 guide excerpt Pardis pasted. The public pages still show the 2025 submission guide and the 2024
judging guide text. Where 2026 differs, the 2026 rules in the Space Apps project form win.

**Deadline:** click **Submit for Judging** before **Sunday 15 November, 11:59 pm local time of your Local Event**.
Submission is final, and no edits are possible afterwards.

Legend: ✅ done in the project · ☐ Pardis to do on the website · ⚠ check

## A. Submission guide, line by line

| # | Requirement | Status |
|---|---|---|
| 1 | Every team member is registered and confirmed at a Local Event (not waitlisted) and appears on the Members tab. A team of 1 is allowed. | ☐ Check your profile. If the Universal Event needs ≥2 people (as in the 2026 text you pasted), you must be in a Local Event. |
| 2 | The project answers an official challenge, not "Create Your Own Challenge". | ☐ Select **Planet X and SPHEREx** on the team page. |
| 3 | Everything is in English (form, demo, linked pages). | ✅ Site, README and report are in English. |
| 4 | Project Name | ☐ Paste from section D. |
| 5 | High-Level Project Summary | ☐ Paste from section D. |
| 6 | **Link to Project Demo**: one 30-second video with English subtitles, **or** up to 7 slides including the title slide. It must be hosted outside the Space Apps site, use a public link, and need no login. Slides must show the team name, member names and the challenge. Going over the limit makes the project ineligible for Global Judging. | ☐ Not made yet. A storyboard is in section E. |
| 7 | **Link to Final Project**: a public website or repository with no password, permission or registration. | ☐ Deploy using DEPLOY.md (Cloud Run URL). Give the GitHub repo link in the description. |
| 8 | Detailed Project Description (what it does, how it works, benefits, tools). | ☐ Paste from section D. |
| 9 | NASA Data (required for Global Awards). | ☐ Paste from section D. |
| 10 | Space Agency Partner & Other Data: list **all** data, code, libraries and images, even open-source ones. | ☐ Paste from section D (includes ESA Gaia, CDS Aladin Lite and the libraries). |
| 11 | Use of SI (superintelligence) tools: which tools and how. | ☐ Paste from section D. |
| 12 | SI disclosure: SI-generated images or videos need a visible watermark; SI-generated code or data need acknowledgement in descriptive text **and** metadata. | ✅ Disclosed in the repository (README section and backend file headers). The website itself says nothing, by team decision. ☐ State it in the form's SI field and in the slide deck. ⚠ The rocket is drawn by code, not an image file, so we treat it as code. If a judge reads it as an SI-generated image, it would need a watermark. ⚠ Any SI-made images in the Canva deck need a visible watermark. |
| 13 | No NASA logos, flags, mission insignia or other NASA design elements in SI-generated content. | ✅ None in the tool. ⚠ Keep them out of your slides and video too. |
| 14 | Images uploaded to the project page: JPG, PNG or GIF, ≤10 MB. Videos and documents are links only. | ☐ Screenshots are about 0.3–0.6 MB each. |
| 15 | No recognisable name, voice or likeness of anyone under 18. Adults shown agree to NASA use. No personal data (address, phone, birthday). | ⚠ No faces or voices of minors in the video. Don't show your email. |
| 16 | No commercial promotion, no proprietary material, only material you have rights to. | ✅ Licences: Apache-2.0 (ours), Bootstrap MIT, Plotly MIT, Aladin Lite LGPL-3.0 (unmodified, licence included). |
| 17 | Tick the Terms & Conditions/Privacy box and the "original work, all external resources listed" box. | ☐ |
| 18 | Test every link in a private/incognito window before submitting. | ☐ Cloud Run URL, GitHub Pages URL, GitHub repo, demo link. |
| 19 | Optional: if a school or office network blocks the new site, request web-filter classification (FortiGuard). | ☐ Optional. |

## B. Judging criteria and where Skytrace shows them

| Criterion | Evidence a judge can check in 2 minutes |
|---|---|
| **Impact** (big problem? helps many?) | Anyone can blink any patch of the SPHEREx sky in a browser, with no Python and no 70 MB downloads. It keeps the Backyard Worlds-style hunt for moving objects going with new 0.75–5 µm data across 102 colours. "Report a candidate" turns a sighting into a shareable, checkable write-up. Embed codes let classrooms and planetaria put a live view on their own pages. |
| **Creativity** | The 102 channels are made usable: per-detector stacks, a λ-scan "movie through colour", false-colour detector RGB and same-channel visit comparisons. A rocket flies to each new position on a true all-sky map. Shift-and-add along a trial motion makes a mover sharpen into a point. |
| **Validity** (scientifically valid? works?) | Photometry equals the IRSA SPHEREx Source Discovery Tool notebook's own functions to ≤2×10⁻⁶ on the same pixels. It agrees with the official DR1 spectral cube to 0.997–1.010 (median). Every image IRSA lists is used. Gaia stars land within 0.04 px. Movers stay fixed to about 0.1 px under shift-and-add. Saturated targets are flagged, not hidden behind numbers. |
| **Relevance** (responds to the challenge, complete, usable) | Covers every item in the challenge: RA/Dec input, blinking, all five test targets, FOV choice, add/subtract any epochs, 102 bands, Gaia/WISE overlays, URL coordinates and embed, contamination flags, Astropy and Aladin, and automatic pickup of new releases. Live public URL. |
| **Presentation** | 30 s video or 7 slides (section E). The About box and README explain the method in plain language. |

## C. The challenge's "potential considerations"

| Consideration | Skytrace |
|---|---|
| Easy updates for new releases | IRSA SPHEREx collections are discovered at run time. A "check for new releases" button offers a rebuild. |
| Creative display of 102 bands | Visits, Same band, λ scan, Exposures and A−B modes; detector and RGB stacks; a 102-channel coverage strip; an on-the-fly spectrum. |
| Add/subtract images at different times | Difference images and a custom A − B visit selector, with an epoch legend (+ − ·). |
| User-chosen field of view | 9.1′ / 6′ / 4′ / 2.5′ in the viewer, plus the Aladin view for wide context. |
| Gaia/WISE overlays | Gaia DR3 and CatWISE2020 (via IRSA), each moved to the frame's date with its proper motion. |
| Coordinates in the URL, embeddable | The whole view state is in the URL; "Copy embed code" gives an iframe. |
| Metadata such as contamination flags | Per-pixel SPHEREx flags (bit names from each file), per-exposure flags in the table, and n_bad on the photometry. |
| Astropy and Aladin | Astropy, astroquery, pyvo and photutils on the server; Aladin Lite (CDS) in the browser on IRSA's SPHEREx HiPS cube. |
| Mentor hint: 2026 ED138 | IRSA MOST returns 365 SPHEREx images on its predicted track (V≈19.8, 0.016–0.024″/min). No detection yet with simple methods: it is faint and in a crowded field. Template subtraction is the next step. Present this honestly as work in progress. |

## D. Draft texts for the project form (edit freely)

**Project name:** Skytrace: blink the SPHEREx sky

**High-level summary:**
Skytrace is a free web tool that turns NASA SPHEREx's infrared survey into a flip-book of the sky. Type any coordinates and it finds every SPHEREx image of that spot in the NASA/IPAC archive, lines them up, and plays them like a video, so nearby brown dwarfs and other moving or changing objects jump out. You can compare any dates, step through all 102 SPHEREx colours, see the object's spectrum and light curve, overlay Gaia and WISE stars, and share or embed the exact view with a link. It brings the Backyard Worlds style of discovery to SPHEREx data for anyone with a browser, and every number is checked against NASA's own SPHEREx tutorials.

**Detailed description:** (shorten if the form limits length)
What it does: you enter RA/Dec or a target name. Skytrace queries IRSA's SIA2 service for every SPHEREx spectral image covering that point, in every current release (DR1, QR3 and their deep variants, found automatically, so new releases appear without code changes). It reads only the pixels it needs from NASA's public AWS copy and aligns them on one 6.15″ grid. In the browser you can blink visits; difference any two dates or groups of dates; shift-and-add along a trial proper motion; scan a visit through wavelength; view detector or false-colour stacks; and read RA/Dec, brightness and data-quality flags under the cursor. The target is measured in every exposure with exactly the method of IRSA's SPHEREx Source Discovery Tool tutorial: the official per-pixel solid-angle maps, a 3-pixel aperture, a 7–16 pixel annulus, errors from the VARIANCE extension, and the n_bad bad-pixel rule. This builds a spectrum and light curve. Gaia DR3 and CatWISE2020 stars are drawn at each frame's date. An all-sky map shows where you are, and a rocket flies to each new search. An Aladin Lite tab shows IRSA's SPHEREx all-sky cube. "Report a candidate" writes up what you found.
How we checked it: our photometry equals the tutorial's own code to 2 parts in a million. It matches the official SPHEREx DR1 spectral cube to about 1% (median). Every image the archive lists is used. Catalogue stars land within 0.04 pixels.
Tools: Python (Astropy, astroquery, PyVO, photutils, SciPy, FastAPI), JavaScript (Bootstrap 5, Plotly.js, Aladin Lite), Google Cloud Run, GitHub.
Benefits: it lowers the barrier to doing real discovery with NASA infrared data, for students, citizen scientists and researchers alike.

**NASA data:**
NASA SPHEREx spectral images (Level 2: IMAGE, FLAGS, VARIANCE, ZODI, EPSF and WCS-WAVE extensions) from releases DR1 and QR3, via the NASA/IPAC Infrared Science Archive (IRSA) SIA2 service and IRSA's public AWS bucket. Also used: SPHEREx DR1 solid-angle pixel maps (calibration product); the SPHEREx DR1 SPECTRAL_CHANNELS table (102 channels); the SPHEREx DR1 all-sky HiPS cube; CatWISE2020 and NEOWISE-R single-exposure data (NASA WISE mission) and the 2MASS Point Source Catalog (NASA/IPAC) via IRSA TAP; IRSA's Moving Object Search Tool (MOST); and IRSA's SPHEREx tutorial notebooks, whose methods we follow and reproduce.

**Space agency partner and other data / resources:**
ESA Gaia DR3 (via IRSA TAP). CSA NEOSSat tutorial reviewed (data via CADC; not integrated: see notes). CDS Strasbourg: Aladin Lite v3.8.2 (LGPL-3.0) and the AllWISE, 2MASS and DSS2 HiPS. Software: Astropy, astroquery, PyVO, photutils, NumPy, SciPy, s3fs/fsspec, FastAPI, Uvicorn, Bootstrap 5 (MIT), Plotly.js (MIT). Font: Rajdhani (Indian Type Foundry, SIL OFL 1.1). Inspired by WiseView (Backyard Worlds: Planet 9). Hosting: Google Cloud Run (Space Apps Global Offer), GitHub Pages.

**Use of SI (superintelligence) tools:**
We used Claude (Anthropic) as an SI coding assistant to write and review most of the Python and JavaScript code, the documentation and the code-drawn rocket/sky-map animation. The repository README and source headers record this. All science data come from NASA/IPAC IRSA and the other archives listed; no number comes from the SI tool. Every calculation was checked against NASA's SPHEREx tutorial code and official data products (tests are in the repository).

## E. 30-second demo storyboard (subtitles on every shot)

1. (0–4 s) The rocket flies across the all-sky map. *"SPHEREx photographs the whole sky in 102 infrared colours. Skytrace lets anyone search it."*
2. (4–10 s) Type `08h55m10.8s -07d14m42s` and Go; WISE 0855 blinks. *"Blink any patch of sky: this cold brown dwarf moves 8 arcseconds a year."*
3. (10–16 s) Epsilon Indi B: difference image, then shift-and-add sharpening. *"Subtract dates, or follow a motion until the mover snaps into focus."*
4. (16–22 s) λ-scan and the spectrum panel. *"Step through all 102 colours and get a spectrum, checked against NASA's own tools."*
5. (22–27 s) Pin, then Report a candidate, then Copy link. *"Pin what you find, report it, share the exact view."*
6. (27–30 s) Title card: Skytrace · team Skytrace · Pardis · Planet X and SPHEREx · public URL. (No NASA logo.)

## F. Honest limits (say them before a judge finds them)

- SPHEREx pixels are 6.15″, so only fast movers (≳1″/yr over the ~1.5-year baseline) shift visibly. Slow objects need shift-and-add.
- Very bright stars (Barnard's Star, R Draconis) saturate SPHEREx. Their photometry is withheld; their images and motion are still shown.
- The automatic mover finder is experimental. 2026 ED138 is not yet detected (faint, crowded field).
- The live search takes about 1–2 minutes for a new position. The six challenge fields are pre-built and instant.
