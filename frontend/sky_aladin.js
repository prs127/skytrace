/* Skytrace: Aladin Lite (CDS, Strasbourg) view of the current field, loaded only when its tab is opened.
   Base layer: IRSA's official SPHEREx DR1 all-sky HiPS cube (102 slices; Aladin's slider steps through them).
   Context layers: CDS HiPS of AllWISE, 2MASS and DSS2. Markers: the Skytrace target position at the
   field's reference epoch, and the Gaia DR3 / CatWISE2020 sources Skytrace already fetched from IRSA.
   Aladin Lite v3.8.2 is vendored unmodified under the LGPL-3.0 (vendor/ALADIN-LITE-LICENSE.txt). */
(function () {
  'use strict';
  const SURVEYS = {
    spherex: 'https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube',
    allwise: 'P/allWISE/color',
    twomass: 'P/2MASS/color',
    dss: 'P/DSS2/color',
  };
  let aladin = null, loading = null, meta = null, layers = [];
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

  async function show() {
    try {
      say('Loading Aladin Lite…');
      await load();
      if (!aladin) {
        aladin = window.A.aladin('#aladinDiv', {
          survey: SURVEYS[$('aladinSurvey').value] || SURVEYS.spherex, fov: 0.25, cooFrame: 'ICRS',
          showReticle: true, showCooGridControl: true, showFullscreenControl: true, showLayersControl: true,
          showSimbadPointerControl: false, showShareControl: false, showProjectionControl: false,
        });
      }
      update(meta);
      say($('aladinSurvey').value === 'spherex'
        ? 'SPHEREx DR1 all-sky HiPS cube from IRSA: use the slider in the view to step through its 102 slices. This is a mosaic of all epochs, so it does not show motion; use the main viewer for that.'
        : 'Context survey from CDS. Blue circles: Gaia DR3; orange squares: CatWISE2020; yellow cross: target.');
    } catch (e) { say(e.message + ' (needs internet access to the CDS and IRSA servers).', 'text-warning'); }
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
    if (sel) sel.addEventListener('change', () => { if (aladin) { aladin.setBaseImageLayer(SURVEYS[sel.value]); show(); } });
  });
  window.SkyAladin = { update: (m) => update(m), get instance() { return aladin; } };
})();
