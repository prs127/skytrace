/* Skytrace in-panel help: a "?" button on every panel opens a short plain-language guide to the controls inside it. */
(function () {
  'use strict';
  const HELP = {
    search: `<b>Find a patch of sky.</b>
      <ul><li>Type a <b>target name</b> (e.g. <code>WISE 0855</code>, <code>Barnard</code>) or <b>coordinates</b>: degrees (<code>133.795 -7.245</code>)
      or hours/degrees (<code>08h55m10.8s -07d14m42s</code>, <code>08:55:10.8 -07:14:42</code>). Press <b>Search</b> or Enter.</li>
      <li><b>Field size</b> (9′, 15′, 20′) is used for new archive searches: a bigger field can follow faster-moving objects but takes longer to download.</li>
      <li>A new place is fetched live from NASA's IRSA archive: about 1–2 minutes for 300–400 SPHEREx images at 9′, longer for bigger fields.
      It then appears in <b>Your searches</b> in the Library.</li></ul>`,
    sky: `<b>Where you are on the whole sky.</b>
      <ul><li>The oval is the entire sky (RA across, Dec up). The yellow ring is your current target.</li>
      <li><b>Dashed line</b>: the ecliptic, the plane of the planets; asteroids and comets are found near it.
      <b>Grey band</b>: the Milky Way, where stars crowd together.</li>
      <li><b>Click anywhere</b> to search that spot. Blue diamonds are the challenge targets; grey ones are places already searched.</li></ul>`,
    view: `<b>Choose which SPHEREx images make up each frame of the movie.</b>
      <ul><li><b>Visits</b>: SPHEREx sees each spot about every 6 months. One frame per visit, made by averaging all its images.
      Best for spotting things that move between visits (nearby stars, brown dwarfs).</li>
      <li><b>Same band</b>: compare visits at one colour (channel). SPHEREx's filter changes across the detector, so this
      stops colour changes from looking like motion. Pick the channel on the slider or the strip under the viewer.</li>
      <li><b>λ scan</b>: play one visit through its colours, short to long wavelength: a "spectrum movie" showing which sources are bright where.</li>
      <li><b>Exposures</b>: every single image in time order. Each image is a different colour, so stars flicker; fast asteroids and comets can jump between images taken hours apart.</li>
      <li><b>Add / subtract</b>: tick visits to add together (A) and to subtract (B). Anything that changed or moved shows as a bright/dark pair.</li>
      <li><b>Detectors</b>: use all six (0.75–5 µm), one, the short or the long ones, or false colour (blue = short, red = long wavelengths). Cold brown dwarfs such as WISE 0855 are brightest in D5+D6.</li>
      <li><b>Difference</b>: subtract a reference (first frame, previous frame, or the mean of the others) from every frame, so only changes remain.</li>
      <li><b>View size</b>: show the whole downloaded field or zoom in. To download a bigger field, choose 15′ or 20′ next to the search box.</li>
      <li><b>Display</b>: brightness stretch, colours and background options (they change only the picture).</li></ul>`,
    display: `<b>How the picture is drawn (it does not change the data).</b>
      <ul><li><b>Stretch</b>: maps brightness to grey levels. asinh shows faint and bright things together; linear is literal; log boosts faint detail.</li>
      <li><b>Colour map</b>: grey, or false colours that make faint differences easier to see.</li>
      <li><b>Low % / High %</b>: the darkest and brightest pixels clipped to black and white. Raise High % to see faint objects.</li>
      <li><b>Field of view</b>: zoom between the full 9.1′ view and 2.5′. One pixel is 6.15″.</li>
      <li><b>Invert</b>: dark stars on a light sky, like old photographic plates. <b>Smooth pixels</b>: blends the square pixels.</li>
      <li><b>Flatten background</b>: removes slow brightness gradients (scattered light) so faint sources stand out.</li>
      <li><b>Same brightness scale</b>: keeps one scale for every frame, so real brightness changes are visible while blinking.</li></ul>`,
    overlays: `<b>Layers drawn on top of the image.</b> Click a chip to switch a layer on (✓) or off. None of them changes the data.
      <ul><li><b>Target</b> (yellow crosshair): where the target should be on that frame's date, from its catalogue proper motion and parallax.</li>
      <li><b>Gaia DR3</b> (blue circles) and <b>CatWISE</b> (orange squares): known stars and infrared sources, moved to each frame's date. A dot with no marker is not in these catalogues.</li>
      <li><b>2MASS</b> (white diamonds): where sources were in 1997–2001. A fast-moving star has left its diamond.</li>
      <li><b>Flags</b>: SPHEREx's own pixel warnings: red saturated, yellow artefact (ghost, halo, streak…), grey masked. Don't trust anything inside them.</li>
      <li><b>Movers</b> (pink): tracks found by the motion test in the <i>Moving objects</i> tab. <b>Compass</b>: north and east arrows and a 1′ bar.</li></ul>`,
    viewer: `<b>The SPHEREx sky movie.</b> North is up and east is left. Each frame is a stack of SPHEREx images; the caption under the image says which.
      <ul><li><b>Compare with</b>: show the same place in older surveys: DSS2 optical photographs (1950s–1990s), 2MASS (1997–2001), AllWISE (2010–2011). A fast star sits somewhere else in each.</li>
      <li>Move the mouse over the image to read RA, Dec and brightness; <b>click</b> to pin a position (it goes into links and reports).</li></ul>`,
    channels: `<b>SPHEREx's 102 colours.</b> SPHEREx splits 0.75–5 µm infrared light into 102 channels on six detectors (D1–D6).
      Each bar is one channel; its height is the number of images of your target in that channel. Click a bar to view that channel in "Same band" mode.`,
    share: `<b>Keep and share what you see.</b>
      <ul><li><b>Copy link</b>: the link reopens this exact view (target, frame, settings).</li>
      <li><b>Copy embed code</b>: a snippet to put this view inside another web page.</li>
      <li><b>Save image</b>: a PNG of the current frame with its markers and a caption (target, date, wavelengths).</li>
      <li><b>Download data</b>: a CSV of every SPHEREx measurement of the target (date, wavelength, channel, brightness, error, quality flags), plus 2MASS/WISE points.</li>
      <li><b>Report a candidate</b>: a ready-to-send text write-up of a spot you pinned: position, nearby catalogued stars, flags, images and your notes.</li></ul>`,
    spectrum: `<b>The target's brightness at every wavelength SPHEREx measured</b>, made on the original SPHEREx pixels.
      <ul><li>Each dot is one image (µJy against µm); colours are visits. White diamonds and orange squares are the same object in 2MASS and WISE.</li>
      <li>Points with bad pixels are hidden unless you switch them on; switch on the log axis for very red or very faint objects.</li></ul>`,
    lightcurve: `<b>Brightness over time with the colour taken out</b>: each point is divided by the target's usual brightness in that channel.
      A steady star stays at 1; variable stars such as R Draconis and RW Aurigae move away from 1.`,
    movers: `<b>How the moving-object search works.</b>
      <ul><li>Sources are found in each visit separately, and their positions are compared across visits.</li>
      <li>An object is reported only if it moves along a <b>straight line through at least three visits</b>, the motion is at least <b>5σ</b>
      and at least 0.5 pixel, it is seen in at least 2/3 of the visits that cover its path, its brightness changes by less than ×3, and no other source is within 2 pixels.</li>
      <li>Position errors are measured in the same field from Gaia DR3 stars that do not move.</li>
      <li>Each result says whether it is the target, a known Gaia DR3 star, or <b>not in Gaia</b> (then check it by eye: blink it, try shift-and-add with its motion).</li>
      <li>Saturated stars are skipped. Fast solar-system objects that cross the field within one visit are not searched.</li></ul>`,
    aladin: `<b>An interactive atlas of the same place</b>: zoom and pan, switch to other surveys, or pick any of SPHEREx's 100 all-sky channel maps from the list (2 of the 102 channels are blank by design).
      The all-sky SPHEREx map combines every visit, so it cannot show motion; use the main viewer for that.`,
    exposures: `<b>The SPHEREx images in the current frame.</b> Date, detector (D), wavelength at the target (λ), channel (Ch), the quality flags
      at the target's pixel, and a link to the original FITS file at NASA's IRSA archive.`,
    data: `<b>Where the data came from.</b> Archive collections, how many images were found and used, the photometry method and catalogues, so anyone can check the result.`,
  };
  const EXTRA = {
    library: `<b>Your library of places.</b>
      <ul><li><b>Challenge targets</b>: the five test objects from the challenge plus a control field (M101). They open instantly.</li>
      <li><b>Fastest-moving stars</b>: the 25 stars with the largest motion measured by Gaia DR3. Ones not downloaded yet are searched live.</li>
      <li><b>Your searches</b>: every place you search. ✎ renames it (the name stays in your browser), ✕ removes it from your list.</li>
      <li>« hides the library to give the image more room.</li></ul>`,
    timeline: `<b>Play the frames like a flip-book.</b>
      <ul><li>◀ ▶ step one frame (keyboard: ← →); <b>Play</b> loops (space bar). The long slider jumps to any frame.</li>
      <li><b>Speed</b>: slide right for faster playback.</li>
      <li>The visit buttons below jump to a visit; the legend shows which visits are in the frame (+ added, − subtracted, · unused).</li></ul>`,
    export: `<b>Download a PDF report for this place.</b> Tick what to include: images (the frame on screen, one per visit, a difference image), plots and tables (spectrum, light curve, visits, exposures, flags), moving-object results, your pinned spot and notes, settings with a link back, and data credits. One place per PDF keeps reports readable.`,
    settings: `<b>How exposures are grouped into visits.</b> A new visit starts after a gap longer than the first slider; a visit longer than the second slider is split into equal parts (fields near the ecliptic poles are watched almost continuously).`,
  };
  Object.assign(HELP, EXTRA);
  function add(card, key) {
    const html = HELP[key]; if (!html) return;
    card.style.position = 'relative';
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'hud-help-btn'; btn.textContent = '?';
    btn.setAttribute('aria-label', 'Explain this panel'); btn.title = 'What do these controls do?';
    const GUIDE = { search: 'search', sky: 'skymap', library: 'library', viewer: 'reading', overlays: 'layers', timeline: 'play', view: 'modes', display: 'display',
      channels: 'channels', spectrum: 'spectrum', lightcurve: 'lightcurve', movers: 'movers', exposures: 'exposures', aladin: 'atlas', settings: 'visits', share: 'share', data: 'sources', export: 'export' };
    const box = document.createElement('div'); box.className = 'hud-help small d-none';
    box.innerHTML = html + (GUIDE[key] ? ` <a href="guide.html#${GUIDE[key]}" target="_blank" rel="noopener">More in How to use</a>` : '');
    // where the explanation opens: inside a collapsible section, under a pane's heading, or at the top of a tab
    const acc = card.querySelector('.accordion-body');
    const head = card.querySelector(':scope > .st-stage-head, :scope > .st-strip-head');
    if (acc) acc.insertBefore(box, acc.firstChild);
    else if (head) head.after(box);
    else if (card.matches('.st-cmd, .st-search, .st-transport, .st-toolbar, .st-layers, .st-stage-head')) card.appendChild(box);
    else if (card.querySelector(':scope > .card-body')) { const b = card.querySelector(':scope > .card-body'); b.parentNode.insertBefore(box, b); }
    else card.insertBefore(box, card.firstChild);
    // opening the explanation also opens a collapsed section
    if (acc) btn.addEventListener('click', () => { const c = card.querySelector('.accordion-collapse'); if (c && !c.classList.contains('show') && window.bootstrap) bootstrap.Collapse.getOrCreateInstance(c).show(); });
    btn.onclick = () => { const open = box.classList.toggle('d-none'); btn.classList.toggle('active', !open); btn.setAttribute('aria-expanded', String(!open)); };
    card.appendChild(btn);
  }
  document.addEventListener('DOMContentLoaded', () => document.querySelectorAll('[data-help]').forEach((c) => add(c, c.dataset.help)));
  window.SkytraceHelp = HELP;
})();
