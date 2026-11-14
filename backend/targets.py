"""Challenge test targets ("Planet X and SPHEREx", NASA Space Apps 2026).

Descriptions use only the challenge's own wording. Positions and proper motions come from
catalogues served by NASA/IPAC IRSA:
  - Gaia DR3 (ESA, via IRSA TAP table gaia_dr3_source), reference epoch J2016.0 = MJD 57388.0
  - Parallaxes: Gaia DR3 (via IRSA TAP) for the four Gaia targets.
  - WISE 0855 is not in Gaia DR3: position, proper motion and parallax fitted to 277 NEOWISE-R single-exposure
    detections (NASA WISE mission, IRSA TAP table neowiser_p1bs_psd, MJD 56782-60419), see
    tests/neowise_w0855_plx.py. Parallax 438 ± 36 mas, consistent with the published 438.9 ± 3.0 mas
    (Kirkpatrick et al. 2019).
Portions generated with Claude (Anthropic), reviewed by team Skytrace.
"""
from pipeline import Target

TARGETS = [
    Target("wise0855", "WISE 0855-0714", 133.77868405, -7.24373332, -8128.7, 663.9, 58000.0,
           note="Challenge target: a fast-moving brown dwarf (challenge coordinates 08h55m10.831s −07d14m42.53s).",
           source="NEOWISE-R single-exposure fit with parallax (277 detections 2014–2024, tests/neowise_w0855_plx.py): "
                  "PM −8.129 ± 0.011, +0.664 ± 0.011 ″/yr, parallax 438 ± 36 mas",
           plx=438.1),
    Target("barnard", "Barnard's Star", 269.44850252544, 4.73942005111, -801.551, 10362.394, 57388.0,
           note="Challenge target. Gaia DR3 proper motion 10.39″/yr.",
           source="Gaia DR3 4472832130942575872", plx=546.9759),
    Target("epsindib", "Epsilon Indi B", 331.07645259656, -56.79381206688, 3981.977, -2466.832, 57388.0,
           note="Challenge target: a pair of brown dwarfs orbiting a star. Gaia DR3 proper motion 4.68″/yr.",
           source="Gaia DR3 6412596012146801152", plx=270.658),
    Target("rwaur", "RW Aurigae", 76.95608119553, 30.40120458910, 2.641, -27.398, 57388.0,
           note="Challenge target: variable star.",
           source="Gaia DR3 156430822114424576", plx=6.4062),
    Target("rdra", "R Draconis", 248.16737836729, 66.75500674547, -20.643, 6.149, 57388.0,
           note="Challenge target: variable star.",
           source="Gaia DR3 1648328016354496384", plx=1.2509),
    Target("m101", "M101 (control field)", 210.80227, 54.34895, 0.0, 0.0, 57388.0,
           note="Validation field: the position used in IRSA's SPHEREx cutout tutorial (84 SPHEREx-D2 images there).",
           source="IRSA tutorial 'spherex-cutouts' position"),
]
