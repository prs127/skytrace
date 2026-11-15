/* Skytrace: Aladin Lite (CDS, Strasbourg) view of the current field, loaded only when its tab is opened.
   Base layer: IRSA's official SPHEREx DR1 all-sky HiPS cube (102 slices; Aladin's slider steps through them).
   Context layers: AllWISE, 2MASS and DSS2 colour HiPS, using the copies hosted by NASA IRSA (listed in
   https://irsa.ipac.caltech.edu/data/hips/list), so they keep working when the CDS servers are unavailable. Usage logging to CDS is switched off (log: false). Markers: the Skytrace target position at the
   field's reference epoch, and the Gaia DR3 / CatWISE2020 sources Skytrace already fetched from IRSA.
   Aladin Lite v3.8.2 is vendored unmodified under the LGPL-3.0 (vendor/ALADIN-LITE-LICENSE.txt). */
(function () {
  'use strict';
  const SURVEYS = {
    spherex: 'https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube',
    allwise: 'https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/RGB-W4-W2-W1',
    twomass: 'https://irsa.ipac.caltech.edu/data/hips/CDS/2MASS/Color',
    dss: 'https://irsa.ipac.caltech.edu/data/hips/CDS/DSS2/color',
  };
  const LABEL = { allwise: 'AllWISE colour', twomass: '2MASS colour', dss: 'DSS2 colour' };
  let aladin = null, loading = null, meta = null, layers = [], cube = null, frame = null;
  // The SPHEREx cube's frames, read from its own properties file: 102 frames in ascending wavelength,
  // frame index = 17*(band-1) + (channel-1); frames 50 and 51 (D3 ch17, D4 ch1, the dichroic channels) are blank
  // (obs_description in the properties). Aladin Lite 3.8.2 does not step through a cube by frame number: its
  // setSliceNumber(s) turns s into a frequency, linear in wavelength between em_min and em_max, and then loads tile
  // floor((f - f_min) / (f_max - f_min) * depth). So to show frame k we pass the s whose frequency falls in the
  // middle of tile k (checked tile by tile in tests/atlas_frames.py).
  async function loadCube() {
    if (cube) return cube;
    const txt = await (await fetch(SURVEYS.spherex + '/properties')).text();
    const prop = {}; txt.split('\n').forEach((l) => { const m = l.match(/^\s*([\w.]+)\s*=\s*(.*?)\s*$/); if (m) prop[m[1]] = m[2]; });
    const lam = (prop.data_cube_crval3_arr || '').split(/\s+/).map(Number);
    cube = { depth: +prop.hips_cube_depth, emMin: +prop.em_min, emMax: +prop.em_max, lam, blank: [50, 51] };
    if (!(cube.depth === lam.length && cube.emMin > 0 && cube.emMax > cube.emMin)) throw new Error('unexpected SPHEREx cube properties');
    return cube;
  }
  function sliceFor(k) {
    const c = 299792458, fMax = c / cube.emMin, fMin = c / cube.emMax;
    const f = fMin + (k + 0.5) / cube.depth * (fMax - fMin), lam = c / f;
    return (lam - cube.emMin) / (cube.emMax - cube.emMin) * cube.depth;
  }
  function frameLabel(k) { return `D${Math.floor(k / 17) + 1} ch${k % 17 + 1} · ${cube.lam[k].toFixed(3)} µm`; }
  function fillFrames() {
    const sel = $('atlasFrame'); if (!sel || sel.options.length) return;
    for (let k = 0; k < cube.depth; k++) if (!cube.blank.includes(k)) sel.add(new Option(frameLabel(k), String(k)));
    sel.addEventListener('change', () => showFrame(+sel.value));
  }
  function showFrame(k) {
    frame = k; const l = aladin && aladin.getBaseImageLayer && aladin.getBaseImageLayer();
    if (l && l.setSliceNumber && $('aladinSurvey').value === 'spherex') l.setSliceNumber(sliceFor(k));
    if ($('atlasFrame')) $('atlasFrame').value = String(k);
  }
  const $ = (id) => document.getElementById(id);
  const say = (t, cls) => { const m = $('aladinMsg'); if (m) { m.textContent = t; m.className = 'small ' + (cls || 'text-secondary'); } };

  function load() {
    if (loading) return loading;
    // the npm build of Aladin Lite is an ES module
    loading = import(new URL('vendor/aladin.js', document.baseURI).href)
      .then((mod) => { window.A = mod.default; return window.A.init; })
      .catch((e) => { loading = null; throw new Error('Aladin Lite could not start: ' + (e && e.message ? e.message : e)); });
    return loading;
  }

  // Check that a HiPS answers before handing it to Aladin Lite. If Aladin cannot open a survey it falls back to its
  // default (a CDS survey) and, while CDS is unavailable, keeps re-querying CDS's MocServer many times a second.
  const reachable = {};
  async function preflight(url) {
    if (reachable[url]) return;
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 12000);
    try { const r = await fetch(url + '/properties', { signal: ctl.signal, cache: 'force-cache' }); if (!r.ok) throw new Error('HTTP ' + r.status); reachable[url] = true; }
    catch (e) { throw new Error('The image server did not answer (' + url.split('/')[2] + ')'); }
    finally { clearTimeout(timer); }
  }

  async function show() {
    try {
      say('Loading Aladin Lite…');
      await load();
      await preflight(SURVEYS[$('aladinSurvey').value] || SURVEYS.spherex);
      if (!aladin) {
        aladin = window.A.aladin('#aladinDiv', {
          survey: SURVEYS[$('aladinSurvey').value] || SURVEYS.spherex, fov: 0.25, cooFrame: 'ICRS', log: false,
          showReticle: true, showCooGridControl: true, showFullscreenControl: true, showLayersControl: false,
          showSimbadPointerControl: false, showShareControl: false, showProjectionControl: false,
        });
      }
      update(meta);
      const isCube = $('aladinSurvey').value === 'spherex';
      if ($('atlasFrame')) $('atlasFrame').classList.toggle('d-none', !isCube);
      if (isCube) {
        await loadCube(); fillFrames();
        // default: 1.649 µm-ish (D3 ch1) unless a frame was chosen before; wait until the layer is ready
        const k = frame !== null ? frame : 34;
        for (let i = 0; i < 40; i++) { const l = aladin.getBaseImageLayer(); if (l && l.added && l.cubeDepth) break; await new Promise((r) => setTimeout(r, 150)); }
        showFrame(k);
      }
      say(isCube
        ? 'SPHEREx DR1 all-sky map from IRSA (12.9″ pixels, all visits combined, so it does not show motion; use the main viewer for that). Choose any of its 100 channel maps above.'
        : LABEL[$('aladinSurvey').value] + ' (HiPS hosted by NASA IRSA). Blue circles: Gaia DR3; orange squares: CatWISE2020; yellow cross: target.');
    } catch (e) { say(e.message + ' (needs internet access to the IRSA servers).', 'text-warning'); }
  }

  function update(m) {
    meta = m || meta;
    if (!aladin || !meta) return;
    const [ra, dec] = meta.grid.crval;
    aladin.gotoRaDec(ra, dec);
    aladin.setFoV(Math.max(0.12, meta.grid.npix * meta.grid.pixscale / 3600 * 1.6));
    for (const l of layers) { try { aladin.removeLayer ? aladin.removeLayer(l) : l.hide(); } catch (e) { /* ignore */ } }
    layers = [];
    const cat = (name, color, shape, size) => { const c = window.A.catalog({ name, color, shape, sourceSize: size }); aladin.addCatalog(c); layers.push(c); return c; };
    const tgt = cat('Skytrace target (reference epoch)', '#ffc107', 'cross', 18);
    tgt.addSources([window.A.source(ra, dec, { name: meta.name })]);
    const g = cat('Gaia DR3 (IRSA), epoch 2016.0', '#6ea8fe', 'circle', 6);
    g.addSources((meta.catalogs.gaia || []).map((s) => window.A.source(s.ra, s.dec, { G: s.g })));
    const w = cat('CatWISE2020 (IRSA)', '#fd7e14', 'square', 6);
    w.addSources((meta.catalogs.catwise || []).map((s) => window.A.source(s.ra, s.dec, { W2: s.w2 })));
  }

  document.addEventListener('DOMContentLoaded', () => {
    const tab = document.querySelector('[data-bs-target="#tabAladin"]');
    if (tab) tab.addEventListener('shown.bs.tab', show);
    const sel = $('aladinSurvey');
    if (sel) sel.addEventListener('change', async () => { if (!aladin) return;
      try { await preflight(SURVEYS[sel.value]); } catch (e) { say(e.message + '. Try again in a moment.'); return; }
      aladin.setBaseImageLayer(SURVEYS[sel.value]); setTimeout(show, 300); });
  });
  // ---- image-source switcher over the main viewer: the same patch in another survey, same centre and field ----
  const NOTES = {
    dss: 'Optical Digitized Sky Survey (photographic plates, 1950s–1990s). Fast-moving stars were somewhere else then: Barnard\'s Star has moved about 10′ since the 1950s.',
    twomass: '2MASS near-infrared J/H/Ks (NASA/IPAC, 1997–2001): the same kind of light as SPHEREx\'s short channels, 25 years earlier.',
    allwise: 'AllWISE mid-infrared W1/W2/W4 (NASA, 2010–2011): cold brown dwarfs such as WISE 0855 are bright here and invisible in optical light.',
  };
  let cmp = null;
  async function compare(key, m, fovDeg) {
    const view = $('srcView'), note = $('srcNote');
    if (!key || key === 'spherex' || !SURVEYS[key]) { view.classList.add('d-none'); return; }
    const survey = SURVEYS[key];
    view.classList.remove('d-none');
    note.textContent = 'Loading ' + LABEL[key] + '…';
    try {
      await load();
      await preflight(survey);
      if (!cmp) cmp = window.A.aladin('#srcAladin', { survey, fov: fovDeg, cooFrame: 'ICRS', log: false, showReticle: true, showCooGridControl: false,
        showLayersControl: false, showSimbadPointerControl: false, showShareControl: false, showProjectionControl: false, showFullscreenControl: false,
        showZoomControl: true, showFrame: false, showCooLocation: true });
      else cmp.setBaseImageLayer(survey);
      if (m) { cmp.gotoRaDec(m.grid.crval[0], m.grid.crval[1]); }
      cmp.setFoV(fovDeg);
      note.textContent = (NOTES[key] || '') + ' Image: HiPS hosted by NASA IRSA, drawn with Aladin Lite. Centre and field match the SPHEREx view; click SPHEREx to go back.';
    } catch (e) { note.textContent = e.message + '. The comparison pictures need internet access to NASA IRSA; try again in a moment.'; }
  }
  window.SkyAladin = { update: (m) => update(m), compare, showFrame, sliceFor: (k) => sliceFor(k), get cube() { return cube; }, get instance() { return aladin; }, get compareInstance() { return cmp; } };
})();
