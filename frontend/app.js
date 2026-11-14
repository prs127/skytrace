/* Skytrace front end: blink, difference and spectral views of SPHEREx data.
 * Works in two modes:
 *   - static: pre-built fields from data/index.json (demo / offline)
 *   - live:   Skytrace server present (api/health answers) -> any RA/Dec is
 *             searched in the IRSA archive on demand.
 */
'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const D2R = Math.PI / 180;
  const PIX = 6.15;                       // arcsec per SPHEREx pixel
  const CAT_SAT = 1, CAT_BAD = 2, CAT_ART = 4, CAT_SRC = 8;
  // Official SPHEREx DR1 channel table (data/channels.json, from the DR1 cube's SPECTRAL_CHANNELS HDU)
  let CHANNELS = [];
  const DET_RANGE = {};
  function setChannels(ch) {
    CHANNELS = ch;
    for (let d = 1; d <= 6; d++) { const c = ch.filter((x) => x.det === d); DET_RANGE[d] = [Math.min(...c.map((x) => x.wmin)), Math.max(...c.map((x) => x.wmax))]; }
  }

  const DEFAULTS = { mode: 'epoch', det: 'all', band: 92, tol: 1, win: 30, span: 60, stretch: 'asinh', cmap: 'gray', lo: 1, hi: 99.5,
    fov: 9.1, inv: 0, smooth: 0, lock: 1, flat: 1, sa: 0, sapmra: 0, sapmdec: 0, diff: 0, dref: 'first', speed: 600, ov: 'target,compass', scan: 0, A: '0', B: '', frame: 0 };
  const FIELD_DEFAULTS = { wise0855: { det: 'lw' }, epsindib: { det: 'all' }, barnard: { det: 'all' }, rwaur: { det: 'rgb' }, rdra: { det: 'rgb' }, m101: { det: '2' } };
  const ALIASES = {
    wise0855: ['wise0855', 'w0855', 'wisej0855', 'wise08550714', 'wisej085510'],
    barnard: ['barnard', 'barnardsstar', 'barnardstar', 'gj699', 'gl699'],
    epsindib: ['epsindib', 'epsilonindib', 'epsind', 'epsilonindi', 'epsiloninds', 'epsiloninb'],
    rwaur: ['rwaur', 'rwaurigae'],
    rdra: ['rdra', 'rdraconis'],
    m101: ['m101', 'ngc5457', 'pinwheel'],
  };
  const MODE_HELP = {
    epoch: 'One stacked frame per visit (exposures grouped in time). Best for seeing motion between visits. A stack averages many channels, so its brightness is a band average, good for positions, not for spectra.',
    band: 'Compares visits at the same wavelength channel, so colour changes cannot fake motion. The channel is exact at the target; SPHEREx filters vary across the detector, so at the corners of the full 9.1′ view the wavelength differs by up to half a channel (0.4–1.3%). Click a channel in the strip below.',
    scan: 'Plays one visit through the official SPHEREx channels, one by one: a spectrum movie showing at which wavelengths each source is bright. Channel wavelengths are exact at the target and drift by up to half a channel at the field corners.',
    exp: 'Every exposure in time order. Wavelength changes frame to frame, so stars flicker; fast asteroids and comets still stand out.',
    custom: 'Build your own comparison: average of visits in A minus average of visits in B.',
  };

  // ---------------------------------------------------------------- state
  const S = { ...DEFAULTS, specClean: true };   // hide n_bad>=1 points by default, as the IRSA notebook's plot does
  let INDEX = { fields: [] };
  let LIVE = false;
  let F = null;                 // loaded field {meta, img, cat, np, n}
  let VISITS = [];
  let FRAMES = [];
  let LIMITS = null;            // display limits cache
  let RENDER_CACHE = new Map();
  let PIN = null;               // {ra, dec, label}
  let MOVERS = [];
  let playTimer = null;
  let suppressUrl = false;
  const LIVE_URL = (window.SKYTRACE_LIVE_URL || '').trim();
  let PUBLIC_BASE = (window.SKYTRACE_PUBLIC_URL || LIVE_URL || '').trim();

  // ---------------------------------------------------------------- utils
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const fmt = (v, d = 2) => (v === null || v === undefined || !isFinite(v)) ? '–' : Number(v).toFixed(d);
  function mjdToIso(mjd) { return new Date((mjd - 40587) * 86400000).toISOString().slice(0, 16).replace('T', ' '); }
  function mjdToDate(mjd) { return new Date((mjd - 40587) * 86400000).toISOString().slice(0, 10); }
  function raToHms(ra) {
    let h = ((ra % 360) + 360) % 360 / 15; const hh = Math.floor(h); let m = (h - hh) * 60; const mm = Math.floor(m); let s = (m - mm) * 60;
    let sStr = s.toFixed(2); if (sStr === '60.00') { return raToHms(ra + 0.000001); }
    return `${String(hh).padStart(2, '0')}h${String(mm).padStart(2, '0')}m${sStr.padStart(5, '0')}s`;
  }
  function decToDms(dec) {
    const sg = dec < 0 ? '-' : '+'; let a = Math.abs(dec); const dd = Math.floor(a); let m = (a - dd) * 60; const mm = Math.floor(m); const s = (m - mm) * 60;
    let sStr = s.toFixed(1); if (sStr === '60.0') return decToDms(dec + (dec < 0 ? -1e-7 : 1e-7));
    return `${sg}${String(dd).padStart(2, '0')}d${String(mm).padStart(2, '0')}m${sStr.padStart(4, '0')}s`;
  }
  function angSepDeg(ra1, de1, ra2, de2) {
    const a = Math.sin((de2 - de1) * D2R / 2) ** 2 + Math.cos(de1 * D2R) * Math.cos(de2 * D2R) * Math.sin((ra2 - ra1) * D2R / 2) ** 2;
    return 2 * Math.asin(Math.min(1, Math.sqrt(a))) / D2R;
  }
  function percentile(sorted, p) {
    if (!sorted.length) return 0;
    const i = clamp((p / 100) * (sorted.length - 1), 0, sorted.length - 1); const lo = Math.floor(i), hi = Math.ceil(i);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
  }
  function normName(s) { return s.toLowerCase().replace(/[^a-z0-9]/g, ''); }
  function setMsg(el, text, kind = 'secondary') { el.className = `form-text small text-${kind}`; el.textContent = text; }

  // float16 -> float32 lookup table
  const F16 = (() => {
    const t = new Float32Array(65536);
    for (let h = 0; h < 65536; h++) {
      const s = (h & 0x8000) ? -1 : 1, e = (h >> 10) & 0x1f, f = h & 0x3ff;
      t[h] = e === 0 ? s * 6.103515625e-05 * (f / 1024) : e === 31 ? (f ? NaN : s * Infinity) : s * Math.pow(2, e - 15) * (1 + f / 1024);
    }
    return t;
  })();

  async function fetchBytes(url) {
    const r = await fetch(url, { cache: 'no-cache' });
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return gunzipIfNeeded(new Uint8Array(await r.arrayBuffer()));
  }
  // Same bytes, wrapped as base64 JSON, for static hosts that refuse .gz files (e.g. the artifact demo)
  const DATA_FORMAT = (document.querySelector('meta[name=skytrace-data]') || {}).content || 'gz';
  async function fetchBlob(base) {
    try { if (DATA_FORMAT === 'b64') throw new Error('skip'); return await fetchBytes(base + '.bin.gz'); }
    catch (e) {
      const j = await fetchJson(base + '.b64.json', { cache: 'no-cache' });
      const bin = atob(j.b64), u = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
      return gunzipIfNeeded(u);
    }
  }
  async function gunzipIfNeeded(buf) {
    if (buf.length > 2 && buf[0] === 0x1f && buf[1] === 0x8b) {
      if (!('DecompressionStream' in window)) throw new Error('This browser cannot decompress gzip data; please use a current Chrome, Edge, Firefox or Safari.');
      const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));
      return new Uint8Array(await new Response(stream).arrayBuffer());
    }
    return buf;
  }
  async function fetchJson(url, opts) { const r = await fetch(url, opts); if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`); return r.json(); }

  // ---------------------------------------------------------------- WCS (gnomonic, matches astropy RA---TAN/DEC--TAN)
  function world2pix(ra, dec) {
    const g = F.meta.grid, a0 = g.crval[0] * D2R, d0 = g.crval[1] * D2R, a = ra * D2R, d = dec * D2R;
    const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a - a0);
    const xi = Math.cos(d) * Math.sin(a - a0) / cosc;
    const eta = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a - a0)) / cosc;
    return [xi / D2R / g.cdelt[0] + g.crpix[0] - 1, eta / D2R / g.cdelt[1] + g.crpix[1] - 1];
  }
  function pix2world(x, y) {
    const g = F.meta.grid, a0 = g.crval[0] * D2R, d0 = g.crval[1] * D2R;
    const xi = (x + 1 - g.crpix[0]) * g.cdelt[0] * D2R, eta = (y + 1 - g.crpix[1]) * g.cdelt[1] * D2R;
    const den = Math.cos(d0) - eta * Math.sin(d0);
    const ra = (a0 + Math.atan2(xi, den)) / D2R, dec = Math.atan2(Math.sin(d0) + eta * Math.cos(d0), Math.hypot(xi, den)) / D2R;
    return [(ra % 360 + 360) % 360, dec];
  }
  function propagate(ra, dec, pmra, pmdec, epochMjd, toMjd) {
    const dt = (toMjd - epochMjd) / 365.25;
    return [ra + pmra * dt / 3.6e6 / Math.cos(dec * D2R), dec + pmdec * dt / 3.6e6];
  }
  // Proper motion plus annual parallax. E = Earth's barycentric position (AU, ICRS), stored by the pipeline for every
  // exposure (astropy ephemeris); the same formula is checked against astropy's GCRS transform in the backend.
  function apparent(ra, dec, pmra, pmdec, plx, epochMjd, toMjd, E) {
    const [pra, pde] = propagate(ra, dec, pmra || 0, pmdec || 0, epochMjd, toMjd);
    if (!plx || !E) return [pra, pde];
    const a = pra * D2R, d = pde * D2R;
    const dx = plx * (E[0] * Math.sin(a) - E[1] * Math.cos(a));
    const dy = plx * (E[0] * Math.cos(a) * Math.sin(d) + E[1] * Math.sin(a) * Math.sin(d) - E[2] * Math.cos(d));
    return [pra + dx / 3.6e6 / Math.cos(d), pde + dy / 3.6e6];
  }
  function meanEarth(members) {
    const ex = F.meta.exposures, v = members.map((i) => ex[i].earth).filter(Boolean);
    if (!v.length) return null;
    return [0, 1, 2].map((k) => v.reduce((s, e) => s + e[k], 0) / v.length);
  }
  // Target position for a set of exposures: mean of the pipeline's per-exposure predictions (motion + parallax).
  function targetAt(members, mjd) {
    const ex = F.meta.exposures, t = F.meta.target, p = members.filter((i) => ex[i].tra !== undefined);
    if (p.length) return [p.reduce((s, i) => s + ex[i].tra, 0) / p.length, p.reduce((s, i) => s + ex[i].tdec, 0) / p.length];
    return apparent(t.ra, t.dec, t.pmra, t.pmdec, t.plx, t.epoch_mjd, mjd, meanEarth(members));
  }

  // ---------------------------------------------------------------- URL state
  const URL_KEYS = ['mode', 'det', 'band', 'tol', 'win', 'span', 'stretch', 'cmap', 'lo', 'hi', 'fov', 'inv', 'smooth', 'lock', 'flat', 'sa', 'sapmra', 'sapmdec', 'diff', 'dref', 'speed', 'ov', 'scan', 'A', 'B', 'frame'];
  function readUrl() {
    const p = new URLSearchParams(location.search);
    const h = decodeURIComponent(location.hash.replace(/^#/, ''));
    if (h.includes('=')) for (const [k, v] of new URLSearchParams(h)) p.set(k, v);
    else if (h) p.set('field', h);
    return p;
  }
  function applyParams(p) {
    for (const k of URL_KEYS) {
      if (!p.has(k)) continue;
      const v = p.get(k), d = DEFAULTS[k];
      S[k] = typeof d === 'number' ? (isFinite(+v) ? +v : d) : v;
    }
    S.lo = clamp(S.lo, 0, 20); S.hi = clamp(S.hi, 90, 100); S.band = clamp(Math.round(S.band), 1, 102);
    S.tol = clamp(Math.round(S.tol), 0, 8); S.win = clamp(S.win, 2, 120); S.speed = clamp(S.speed, 80, 2000);
    if (!['epoch', 'band', 'scan', 'exp', 'custom'].includes(S.mode)) S.mode = 'epoch';
    if (!['all', 'rgb', 'lw', 'sw', '1', '2', '3', '4', '5', '6'].includes(String(S.det))) S.det = 'all';
    S.span = clamp(S.span, 5, 400);
    S.det = String(S.det);
  }
  function stateParams() {
    const p = new URLSearchParams();
    if (F) {
      p.set('field', F.meta.key);
      const [cra, cdec] = F.meta.grid.crval; p.set('ra', cra.toFixed(5)); p.set('dec', cdec.toFixed(5));
    }
    if (PIN) { p.set('pra', PIN.ra.toFixed(5)); p.set('pdec', PIN.dec.toFixed(5)); }
    // compare with this field's own defaults (e.g. WISE 0855 opens on D5+D6), so every non-default choice is kept
    const base = { ...DEFAULTS, ...((F && FIELD_DEFAULTS[F.meta.key]) || {}) };
    for (const k of URL_KEYS) if (String(S[k]) !== String(base[k])) p.set(k, S[k]);
    return p;
  }
  function shareUrl() {
    let base = PUBLIC_BASE;
    if (!base) base = (location.origin && location.origin !== 'null') ? location.origin + location.pathname : '';
    return base + '?' + stateParams().toString();
  }
  function writeUrl() {
    if (suppressUrl) return;
    const qs = stateParams().toString();
    try { history.replaceState(null, '', '?' + qs); } catch (e) {
      try { if (F && location.hash !== '#' + F.meta.key) history.replaceState(null, '', '#' + F.meta.key); } catch (e2) { /* sandboxed */ }
    }
    $('shareUrl').value = shareUrl();
  }

  // ---------------------------------------------------------------- coordinate parsing
  function parseInput(str) {
    const s = (str || '').trim();
    if (!s) return null;
    const n = normName(s);
    for (const f of INDEX.fields) {
      const al = [normName(f.key), normName(f.name), ...(ALIASES[f.key] || [])];
      if (al.some((a) => a && (n === a || (n.length >= 4 && (a.startsWith(n) || n.startsWith(a)))))) return { field: f.key, name: f.name };
    }
    const hasH = /[hH]/.test(s) || /\d+:\d+/.test(s);
    const tokens = s.replace(/[hHdDmMsS:°'′"″,]/g, ' ').trim().split(/\s+/);
    if (!tokens.every((t) => /^[+-]?\d+(\.\d*)?$|^[+-]?\.\d+$/.test(t))) return { error: 'Could not read that. Try "133.795 -7.245" or "08h55m10.8s -07d14m42s" or a target name.' };
    let ra, dec;
    if (tokens.length === 2) {
      ra = +tokens[0] * (hasH ? 15 : 1); dec = +tokens[1];
    } else if (tokens.length >= 3 && tokens.length <= 6) {
      // RA = h [m [s]], Dec = d [m [s]]; split at an explicit +/- sign if present, otherwise evenly
      let k = tokens.findIndex((t, j) => j > 0 && /^[+-]/.test(t));
      if (k < 0) { if (tokens.length === 3) return { error: 'Ambiguous: give the Dec sign (e.g. "12 34 +56") or use 6 numbers.' }; k = Math.ceil(tokens.length / 2); }
      const raT = tokens.slice(0, k), deT = tokens.slice(k);
      if (raT.length > 3 || deT.length > 3 || !deT.length) return { error: 'Expected h m s and d m s.' };
      const sexa = (arr) => arr.reduce((acc, v, j) => acc + Math.abs(+v) / Math.pow(60, j), 0);
      ra = sexa(raT) * 15; dec = (deT[0].startsWith('-') ? -1 : 1) * sexa(deT);
    } else return { error: 'Expected 2 numbers (degrees) or up to 6 numbers (h m s  d m s).' };
    if (!(ra >= 0 && ra < 360 && dec >= -90 && dec <= 90)) return { error: 'Out of range: RA must be 0–360° (0–24h), Dec −90° to +90°.' };
    return { ra, dec };
  }

  // ---------------------------------------------------------------- data loading
  async function loadIndex() {
    try { setChannels(await fetchJson('data/channels.json', { cache: 'no-cache' })); } catch (e) { console.error('channels.json missing', e); }
    // detector labels from the official channel table
    const dl = { lw: [5, 6], sw: [1, 2, 3] };
    document.querySelectorAll('#detSel option').forEach((o) => {
      const v = o.value, r = (a, b) => `${DET_RANGE[a][0].toFixed(2)}–${DET_RANGE[b][1].toFixed(2)} µm`;
      if (!DET_RANGE[1]) return;
      if (/^[1-6]$/.test(v)) o.textContent = `D${v} ${r(+v, +v)}`;
      else if (v === 'all') o.textContent = `All 6 detectors (${r(1, 6)})`;
      else if (dl[v]) o.textContent = `D${dl[v].join('+D')} ${r(dl[v][0], dl[v][dl[v].length - 1])}`;
    });
    try { INDEX = await fetchJson('data/index.json', { cache: 'no-cache' }); }
    catch (e) { INDEX = { fields: [] }; }
    try {
      const h = await fetchJson('api/health');
      LIVE = !!(h && h.ok);
    } catch (e) { LIVE = false; }
    $('modeBadge').textContent = LIVE ? 'Live IRSA archive' : 'Pre-built demo fields';
    $('modeBadge').className = 'badge ' + (LIVE ? 'text-bg-success' : 'text-bg-secondary');
    if (!LIVE && LIVE_URL) { const l = $('liveLink'); l.href = LIVE_URL; l.classList.remove('d-none'); }
    if (window.SkyJourney) SkyJourney.setFields(INDEX.fields);
    const hint = $('skyClickHint'); if (hint) hint.textContent = LIVE ? 'Click the map to search there.' : 'Click the map to pick coordinates (searching new positions needs the live server).';
    const box = $('targetButtons'); box.innerHTML = '';
    for (const f of INDEX.fields) {
      const b = document.createElement('button');
      b.className = 'btn btn-sm btn-outline-secondary'; b.textContent = f.name; b.dataset.key = f.key;
      b.title = `${f.n} SPHEREx exposures`;
      b.onclick = () => openField(f.key, true);
      box.appendChild(b);
    }
  }

  function veil(on, text) { $('loadingVeil').classList.toggle('d-none', !on); if (text) $('loadingText').textContent = text;} 

  async function openField(key, resetView) {
    stopPlay();
    veil(true, 'Loading SPHEREx data…');
    const fi = INDEX.fields.find((f) => f.key === key);
    if (fi && window.SkyJourney) SkyJourney.travel(fi.ra, fi.dec, true);
    try {
      const base = 'data/' + encodeURIComponent(key);
      const [meta, imgBytes, catBytes] = await Promise.all([fetchJson(base + '.json', { cache: 'no-cache' }), fetchBlob(base + '.img'), fetchBlob(base + '.cat')]);
      const np = meta.grid.npix, n = meta.exposures.length, len = n * np * np;
      if (imgBytes.length !== len * 2 || catBytes.length !== len) throw new Error(`Corrupt field data (${imgBytes.length} / ${len * 2} bytes)`);
      const u16 = new Uint16Array(imgBytes.buffer, imgBytes.byteOffset, len);
      const img = new Float32Array(len); for (let i = 0; i < len; i++) img[i] = F16[u16[i]];
      F = { meta, img, cat: catBytes, np, n };
      const noises = meta.exposures.map((e) => e.noise).filter((v) => v > 0).sort((a, b) => a - b);
      F.medNoise = noises.length ? noises[Math.floor(noises.length / 2)] : 1;
      if (resetView) {
        const keep = { speed: S.speed, stretch: S.stretch, cmap: S.cmap === 'div' ? 'gray' : S.cmap };
        Object.assign(S, DEFAULTS, keep, FIELD_DEFAULTS[key] || {});
        S.sapmra = Math.round(meta.target.pmra || 0); S.sapmdec = Math.round(meta.target.pmdec || 0);
        clearPin();
      }
      $('hoverReadout').textContent = 'Move over the image to read RA, Dec and brightness.';
      document.querySelectorAll('#targetButtons button').forEach((b) => b.classList.toggle('active', b.dataset.key === key));
      $('fieldTitle').textContent = meta.name;
      if ($('hudTarget')) { $('hudTarget').textContent = meta.name; $('hudCoord').textContent = `${meta.grid.crval[0].toFixed(3)} ${meta.grid.crval[1] >= 0 ? '+' : ''}${meta.grid.crval[1].toFixed(3)}`; }
      $('fieldNote').textContent = meta.note || '';
      renderBlendNote();
      groupVisits(); syncControls(); rebuild(); renderProvenance(); drawSpectrum(); drawLightCurve();
      if (window.SkyAladin) SkyAladin.update(meta);
      let landed = Promise.resolve();
      if (window.SkyJourney) { landed = SkyJourney.travel(meta.grid.crval[0], meta.grid.crval[1], false); SkyJourney.arrive(); }
      if ($('skyHere')) $('skyHere').textContent = `${raToHms(meta.grid.crval[0]).slice(0, 8)} ${decToDms(meta.grid.crval[1]).slice(0, 9)}`;
      await Promise.race([landed, new Promise((r) => setTimeout(r, 1900))]);
      veil(false);
    } catch (err) {
      console.error(err);
      veil(true, 'Could not load this field: ' + err.message);
    }
  }

  // ---------------------------------------------------------------- visits / frames
  function groupVisits() {
    const ex = F.meta.exposures;
    const order = ex.map((_, i) => i).sort((a, b) => ex[a].mjd - ex[b].mjd);
    // 1) split on gaps longer than S.win days; 2) split any cluster longer than S.span days into
    //    equal chunks (fields near the ecliptic poles are observed almost continuously).
    const clusters = []; let cur = null, last = -1e9;
    for (const i of order) {
      if (ex[i].mjd - last > S.win) { cur = []; clusters.push(cur); }
      cur.push(i); last = ex[i].mjd;
    }
    VISITS = [];
    for (const c of clusters) {
      const t0 = ex[c[0]].mjd, len = ex[c[c.length - 1]].mjd - t0, nchunk = Math.max(1, Math.ceil(len / S.span - 1e-9));
      const parts = Array.from({ length: nchunk }, () => []);
      for (const i of c) parts[Math.min(nchunk - 1, Math.floor((ex[i].mjd - t0) / (len / nchunk || 1)))].push(i);
      for (const part of parts) if (part.length) VISITS.push({ idx: part, mjd0: ex[part[0]].mjd, mjd1: ex[part[part.length - 1]].mjd });
    }
    VISITS.forEach((v, k) => { v.k = k; v.label = `Visit ${k + 1}`; v.range = `${mjdToDate(v.mjd0)} → ${mjdToDate(v.mjd1)}`; });
    if (S.scan >= VISITS.length) S.scan = 0;
    renderCustomList();
  }
  const DET_GROUPS = { lw: [5, 6], sw: [1, 2, 3] };
  function detFilter(i) {
    if (S.det === 'all' || S.det === 'rgb') return true;
    const d = F.meta.exposures[i].det;
    return DET_GROUPS[S.det] ? DET_GROUPS[S.det].includes(d) : d === +S.det;
  }
  function weightOf(i) { const nz = F.meta.exposures[i].noise; const s = nz > 0 ? nz : F.medNoise; return 1 / (s * s); }
  // Shift-and-add (as in WiseView): offset, in grid pixels, of an object moving with the chosen proper
  // motion, between the field reference date and date `mjd`. Sampling each exposure at (x+dx, y+dy)
  // keeps such an object fixed, so its signal adds up while everything else smears.
  function shiftAt(mjd) {
    if (!S.sa || !F) return [0, 0];
    const [ra0, de0] = F.meta.grid.crval, ref = F.meta.grid.mjd_ref;
    const [x0, y0] = world2pix(ra0, de0), [x1, y1] = world2pix(...propagate(ra0, de0, +S.sapmra, +S.sapmdec, ref, mjd));
    return [x1 - x0, y1 - y0];
  }
  function sampleShifted(off, n, x, y) {
    const x0 = Math.floor(x), y0 = Math.floor(y), fx = x - x0, fy = y - y0; let s = 0, w = 0;
    for (const [ix, iy, wt] of [[x0, y0, (1 - fx) * (1 - fy)], [x0 + 1, y0, fx * (1 - fy)], [x0, y0 + 1, (1 - fx) * fy], [x0 + 1, y0 + 1, fx * fy]]) {
      if (ix < 0 || iy < 0 || ix >= n || iy >= n || wt <= 0) continue;
      const v = F.img[off + iy * n + ix]; if (v === v) { s += wt * v; w += wt; }
    }
    return w > 0.5 ? s / w : NaN;
  }
  function coadd(members) {
    // Inverse-variance weighted mean. A pixel is marked saturated/artefact in the stack only if
    // that flag is set in at least half of the exposures covering it (majority rule).
    const n = F.np * F.np, sum = new Float64Array(n), ws = new Float64Array(n), cat = new Uint8Array(n);
    const cov = new Uint16Array(n), nsat = new Uint16Array(n), nart = new Uint16Array(n);
    for (const i of members) {
      const w = weightOf(i), off = i * n;
      const [dx, dy] = shiftAt(F.meta.exposures[i].mjd), shifted = S.sa && (Math.abs(dx) > 1e-3 || Math.abs(dy) > 1e-3);
      for (let p = 0; p < n; p++) {
        let v, c;
        if (shifted) {
          const x = (p % F.np) + dx, y = Math.floor(p / F.np) + dy, xi = Math.round(x), yi = Math.round(y);
          c = (xi >= 0 && yi >= 0 && xi < F.np && yi < F.np) ? F.cat[off + yi * F.np + xi] : CAT_BAD;
          v = sampleShifted(off, F.np, x, y);
        } else { v = F.img[off + p]; c = F.cat[off + p]; }
        if (c & CAT_BAD) { if (c & CAT_SAT) { nsat[p]++; cov[p]++; } continue; }
        cov[p]++; if (c & CAT_SAT) nsat[p]++; if (c & CAT_ART) nart[p]++;
        if (v === v) { sum[p] += w * v; ws[p] += w; }
      }
    }
    const out = new Float32Array(n);
    for (let p = 0; p < n; p++) {
      if (ws[p] > 0) out[p] = sum[p] / ws[p]; else { out[p] = NaN; cat[p] |= CAT_BAD; }
      if (cov[p] && nsat[p] * 2 >= cov[p]) cat[p] |= CAT_SAT;
      if (cov[p] && nart[p] * 2 >= cov[p]) cat[p] |= CAT_ART;
    }
    return { img: out, cat };
  }
  function meanMjd(members) { if (!members.length) return F.meta.grid.mjd_ref; let s = 0; for (const i of members) s += F.meta.exposures[i].mjd; return s / members.length; }
  function waveRange(members) {
    let lo = Infinity, hi = -Infinity;
    for (const i of members) { const w = F.meta.exposures[i].wave; if (w) { lo = Math.min(lo, w); hi = Math.max(hi, w); } }
    return isFinite(lo) ? (hi - lo < 0.005 ? `${lo.toFixed(3)} µm` : `${lo.toFixed(2)}–${hi.toFixed(2)} µm`) : '';
  }
  // Remove smooth background structure (zodiacal / scattered-light residuals) with a mesh-median
  // background, as in SExtractor: sigma-clipped median in 15x15-pixel blocks, bilinearly interpolated.
  // Point sources (stars, movers) are only a few pixels across and do not bias the block medians.
  function flattenPlane(img) {
    const n = F.np, B = 15, nb = Math.ceil(n / B), mesh = new Float32Array(nb * nb);
    for (let by = 0; by < nb; by++) for (let bx = 0; bx < nb; bx++) {
      const v = [];
      for (let y = by * B; y < Math.min(n, (by + 1) * B); y++) for (let x = bx * B; x < Math.min(n, (bx + 1) * B); x++) { const q = img[y * n + x]; if (q === q) v.push(q); }
      if (v.length < 20) { mesh[by * nb + bx] = NaN; continue; }
      v.sort((a, b) => a - b); const med = percentile(v, 50), sig = 1.4826 * percentile(v.map((q) => Math.abs(q - med)).sort((a, b) => a - b), 50);
      const kept = v.filter((q) => Math.abs(q - med) < 3 * sig); mesh[by * nb + bx] = kept.length > 10 ? percentile(kept, 50) : med;
    }
    // fill empty blocks with the mean of valid neighbours (or global median)
    const valid = Array.from(mesh).filter((q) => q === q).sort((a, b) => a - b); const gmed = valid.length ? percentile(valid, 50) : 0;
    for (let k = 0; k < mesh.length; k++) if (mesh[k] !== mesh[k]) mesh[k] = gmed;
    for (let y = 0; y < n; y++) {
      const fy = clamp((y + 0.5) / B - 0.5, 0, nb - 1), y0 = Math.floor(fy), y1 = Math.min(nb - 1, y0 + 1), ty = fy - y0;
      for (let x = 0; x < n; x++) {
        const fx = clamp((x + 0.5) / B - 0.5, 0, nb - 1), x0 = Math.floor(fx), x1 = Math.min(nb - 1, x0 + 1), tx = fx - x0;
        const bg = (mesh[y0 * nb + x0] * (1 - tx) + mesh[y0 * nb + x1] * tx) * (1 - ty) + (mesh[y1 * nb + x0] * (1 - tx) + mesh[y1 * nb + x1] * tx) * ty;
        img[y * n + x] -= bg;
      }
    }
  }
  function visitsOf(members) { const s = new Set(); for (const i of members) { const k = VISITS.findIndex((v) => v.idx.includes(i)); if (k >= 0) s.add(k); } return s; }
  function makeFrame(members, label, sub) {
    const fr = { members, label, sub, mjd: meanMjd(members), earth: meanEarth(members), plus: visitsOf(members), minus: new Set() };
    if (S.det === 'rgb' && S.mode === 'epoch') {
      const groups = [[5, 6], [3, 4], [1, 2]];   // R, G, B
      fr.rgb = groups.map((g) => coadd(members.filter((i) => g.includes(F.meta.exposures[i].det))));
      fr.cat = new Uint8Array(F.np * F.np);
      for (const c of fr.rgb) for (let p = 0; p < fr.cat.length; p++) fr.cat[p] |= c.cat[p] & (CAT_SAT | CAT_ART);
      for (let p = 0; p < fr.cat.length; p++) if (fr.rgb.every((c) => c.img[p] !== c.img[p])) fr.cat[p] |= CAT_BAD;
    } else {
      const c = balancedCoadd(members); fr.img = c.img; fr.cat = c.cat;
    }
    if (S.flat) { if (fr.rgb) fr.rgb.forEach((c) => flattenPlane(c.img)); else flattenPlane(fr.img); }
    return fr;
  }
  // Stack each detector separately, then average the detector stacks with equal weight. Every visit
  // then samples the same spectral mix, so a star's colour cannot leave a residual in difference images.
  function balancedCoadd(members) {
    const ex = F.meta.exposures, dets = [...new Set(members.map((i) => ex[i].det))];
    if (dets.length < 2) return coadd(members);
    const parts = dets.map((d) => coadd(members.filter((i) => ex[i].det === d)));
    const n = F.np * F.np, img = new Float32Array(n), cat = new Uint8Array(n);
    for (let p = 0; p < n; p++) {
      let s = 0, k = 0, sat = 0, art = 0;
      for (const c of parts) { const v = c.img[p]; if (v === v) { s += v; k++; } if (c.cat[p] & CAT_SAT) sat++; if (c.cat[p] & CAT_ART) art++; }
      img[p] = k ? s / k : NaN;
      cat[p] = (k ? 0 : CAT_BAD) | (sat * 2 >= parts.length ? CAT_SAT : 0) | (art * 2 >= parts.length ? CAT_ART : 0);
    }
    return { img, cat };
  }
  function rebuild() {
    if (!F) return;
    stopPlay();
    const ex = F.meta.exposures;
    FRAMES = [];
    if (S.mode === 'epoch') {
      for (const v of VISITS) {
        const m = v.idx.filter(detFilter); if (!m.length) continue;
        FRAMES.push(makeFrame(m, v.label, `${v.range} · ${m.length} exposures · ${waveRange(m)}`));
      }
    } else if (S.mode === 'band') {
      for (const v of VISITS) {
        const m = v.idx.filter((i) => ex[i].band && Math.abs(ex[i].band - S.band) <= S.tol); if (!m.length) continue;
        FRAMES.push(makeFrame(m, `${v.label} · channel ${S.band}${S.tol ? ' ±' + S.tol : ''}`, `${v.range} · ${m.length} exposures · ${waveRange(m)}`));
      }
    } else if (S.mode === 'scan') {
      const v = VISITS[S.scan] || VISITS[0];
      if (v) for (let b = 1; b <= 102; b++) {
        const m = v.idx.filter((i) => ex[i].band === b && detFilter(i)); if (!m.length) continue;
        const fr = makeFrame(m, `Channel ${b} (D${bandDet(b)}, ${bandCenter(b).toFixed(3)} µm)`, `${v.label} · ${waveRange(m)} · ${m.length} exposure${m.length > 1 ? 's' : ''}`);
        fr.band = b; FRAMES.push(fr);
      }
    } else if (S.mode === 'exp') {
      const ord = ex.map((_, i) => i).filter(detFilter).sort((a, b) => ex[a].mjd - ex[b].mjd);
      for (const i of ord) FRAMES.push(makeFrame([i], `D${ex[i].det} · ${mjdToIso(ex[i].mjd)}`, `λ ${fmt(ex[i].wave, 3)} µm · channel ${ex[i].band ?? '–'} · ${ex[i].obs_id}`));
    } else if (S.mode === 'custom') {
      const A = parseSet(S.A), B = parseSet(S.B);
      const mA = VISITS.filter((v) => A.has(v.k)).flatMap((v) => v.idx).filter(detFilter);
      const mB = VISITS.filter((v) => B.has(v.k)).flatMap((v) => v.idx).filter(detFilter);
      if (mA.length) {
        const fa = makeFrame(mA, `A: ${[...A].map((k) => 'V' + (k + 1)).join('+')}`, '');
        if (mB.length) {
          const fb = makeFrame(mB, '', '');
 subtractInto(fa, fb); fa.minus = fb.plus;
          fa.label += ` − B: ${[...B].map((k) => 'V' + (k + 1)).join('+')}`; fa.isDiff = true;
        }
        fa.sub = `${mA.length}${mB.length ? ' − ' + mB.length : ''} exposures`;
        FRAMES.push(fa);
      }
    }
    if (S.diff && S.mode !== 'custom' && FRAMES.length > 1) applyDiff();
    LIMITS = null; RENDER_CACHE.clear();
    S.frame = clamp(S.frame, 0, Math.max(0, FRAMES.length - 1));
    $('frameRange').max = Math.max(0, FRAMES.length - 1);
    renderFilmstrip(); computeMovers(); drawBandStrip(); renderFrame(); writeUrl();
  }
  function parseSet(s) { return new Set(String(s || '').split(/[,\s]+/).filter((x) => x !== '').map(Number).filter((x) => x >= 0 && x < VISITS.length)); }
  function subtractInto(fa, fb) {
    const sub = (a, b) => { for (let p = 0; p < a.img.length; p++) a.img[p] = a.img[p] - b.img[p]; for (let p = 0; p < a.cat.length; p++) a.cat[p] |= b.cat[p]; };
    if (fa.rgb && fb.rgb) for (let c = 0; c < 3; c++) sub(fa.rgb[c], fb.rgb[c]); else sub(fa, fb);
  }
  function applyDiff() {
    const orig = FRAMES.map((f) => ({ plus: f.plus, img: f.img ? f.img.slice() : null, rgb: f.rgb ? f.rgb.map((c) => ({ img: c.img.slice(), cat: c.cat })) : null, cat: f.cat }));
    const meanOthers = (k) => {
      const others = orig.filter((_, j) => j !== k);
      const avg = (get) => { const n = get(others[0]).length, out = new Float32Array(n), cnt = new Uint16Array(n);
        for (const o of others) { const a = get(o); for (let p = 0; p < n; p++) if (a[p] === a[p]) { out[p] += a[p]; cnt[p]++; } }
        for (let p = 0; p < n; p++) out[p] = cnt[p] ? out[p] / cnt[p] : NaN; return out; };
      return orig[k].rgb ? { rgb: [0, 1, 2].map((c) => ({ img: avg((o) => o.rgb[c].img), cat: new Uint8Array(n0()) })), cat: new Uint8Array(n0()) } : { img: avg((o) => o.img), cat: new Uint8Array(n0()) };
    };
    const n0 = () => F.np * F.np;
    FRAMES.forEach((fr, k) => {
      let ref;
      if (S.dref === 'first') ref = k === 0 ? orig[1] : orig[0];
      else if (S.dref === 'prev') ref = k === 0 ? orig[1] : orig[k - 1];
      else ref = meanOthers(k);
      subtractInto(fr, ref);
      fr.minus = S.dref === 'others' ? new Set([...Array(VISITS.length).keys()].filter((j) => FRAMES.some((f, m) => m !== k && f.plus.has(j)))) : (ref.plus || new Set());
      fr.isDiff = true;
      const refLabel = S.dref === 'others' ? 'mean of others' : (S.dref === 'first' ? (k === 0 ? 'frame 2' : 'frame 1') : (k === 0 ? 'frame 2' : `frame ${k}`));
      fr.sub = `${fr.sub} · minus ${refLabel}`;
    });
  }

  // ---------------------------------------------------------------- rendering
  const CMAPS = {
    gray: [[0, 0, 0], [255, 255, 255]],
    inferno: [[0, 0, 4], [40, 11, 84], [101, 21, 110], [159, 42, 99], [212, 72, 66], [245, 125, 21], [250, 193, 39], [252, 255, 164]],
    viridis: [[68, 1, 84], [72, 40, 120], [62, 74, 137], [49, 104, 142], [38, 130, 142], [31, 158, 137], [53, 183, 121], [109, 205, 89], [180, 222, 44], [253, 231, 37]],
    div: [[33, 102, 172], [103, 169, 207], [209, 229, 240], [247, 247, 247], [253, 219, 199], [239, 138, 98], [178, 24, 43]],
  };
  const LUTS = {};
  function lut(name) {
    if (LUTS[name]) return LUTS[name];
    const pts = CMAPS[name] || CMAPS.gray, out = new Uint8ClampedArray(256 * 3);
    for (let i = 0; i < 256; i++) {
      const t = i / 255 * (pts.length - 1), k = Math.min(pts.length - 2, Math.floor(t)), f = t - k;
      for (let c = 0; c < 3; c++) out[i * 3 + c] = pts[k][c] + (pts[k + 1][c] - pts[k][c]) * f;
    }
    return (LUTS[name] = out);
  }
  function cropInfo() {
    const want = Math.round(S.fov * 60 / PIX); let npc = Math.min(F.np, want % 2 ? want : want + 1);
    return { npc, off: Math.floor((F.np - npc) / 2) };
  }
  function stretchFn(t) {
    switch (S.stretch) {
      case 'linear': return t;
      case 'sqrt': return Math.sqrt(t);
      case 'log': return Math.log10(1 + 1000 * t) / 3;
      default: return Math.asinh(10 * t) / Math.asinh(10);
    }
  }
  function frameChannels(fr) { return fr.rgb ? fr.rgb.map((c) => c.img) : [fr.img]; }
  function limitsFor(arrs, isDiff) {
    const { npc, off } = cropInfo(), np = F.np, vals = [];
    const total = arrs.length * npc * npc, step = Math.max(1, Math.floor(total / 250000));
    let c = 0;
    for (const a of arrs) for (let y = off; y < off + npc; y++) for (let x = off; x < off + npc; x++) {
      if ((c++ % step) !== 0) continue; const v = a[y * np + x]; if (v === v) vals.push(isDiff ? Math.abs(v) : v);
    }
    vals.sort((a, b) => a - b);
    if (!vals.length) return [0, 1];
    if (isDiff) { const m = percentile(vals, S.hi) || 1e-6; return [-m, m]; }
    let lo = percentile(vals, S.lo), hi = percentile(vals, S.hi); if (hi <= lo) hi = lo + 1e-6;
    return [lo, hi];
  }
  function getLimits(fr) {
    const nch = fr.rgb ? 3 : 1;
    if (!S.lock) return Array.from({ length: nch }, (_, c) => limitsFor([frameChannels(fr)[c]], !!fr.isDiff));
    if (!LIMITS) LIMITS = Array.from({ length: nch }, (_, c) => limitsFor(FRAMES.map((f) => frameChannels(f)[c]).filter(Boolean), !!fr.isDiff));
    return LIMITS;
  }
  function renderImageData(k) {
    if (RENDER_CACHE.has(k)) return RENDER_CACHE.get(k);
    const fr = FRAMES[k], { npc, off } = cropInfo(), np = F.np, lim = getLimits(fr);
    const id = new ImageData(npc, npc), d = id.data;
    const cmapName = fr.isDiff && S.cmap === 'gray' ? 'gray' : S.cmap;
    const L = lut(cmapName), chans = frameChannels(fr);
    for (let r = 0; r < npc; r++) {
      const y = off + (npc - 1 - r);
      for (let x = 0; x < npc; x++) {
        const p = y * np + off + x, o = (r * npc + x) * 4;
        if (fr.rgb) {
          let nan = 0;
          for (let c = 0; c < 3; c++) {
            const v = chans[c][p];
            if (v !== v) { nan++; d[o + c] = 0; continue; }
            let t = clamp((v - lim[c][0]) / (lim[c][1] - lim[c][0]), 0, 1);
            t = fr.isDiff ? 0.5 + 0.5 * Math.sign(t * 2 - 1) * stretchFn(Math.abs(t * 2 - 1)) : stretchFn(t);
            d[o + c] = (S.inv ? 1 - t : t) * 255;
          }
          if (nan === 3) { d[o] = 30; d[o + 1] = 30; d[o + 2] = 42; }
        } else {
          const v = chans[0][p];
          if (v !== v) { d[o] = 30; d[o + 1] = 30; d[o + 2] = 42; }
          else {
            let t = clamp((v - lim[0][0]) / (lim[0][1] - lim[0][0]), 0, 1);
            t = fr.isDiff ? 0.5 + 0.5 * Math.sign(t * 2 - 1) * stretchFn(Math.abs(t * 2 - 1)) : stretchFn(t);
            if (S.inv) t = 1 - t;
            const li = Math.round(t * 255) * 3; d[o] = L[li]; d[o + 1] = L[li + 1]; d[o + 2] = L[li + 2];
          }
        }
        d[o + 3] = 255;
      }
    }
    RENDER_CACHE.set(k, id);
    return id;
  }
  function renderFrame() {
    const c = $('imgCanvas'), ov = $('ovCanvas');
    if (!F || !FRAMES.length) {
      const ctx = c.getContext('2d'); c.width = c.height = 10; ctx.clearRect(0, 0, 10, 10);
      ov.getContext('2d').clearRect(0, 0, ov.width, ov.height);
      $('frameLabel').textContent = 'No frames for this selection';
      $('frameSub').textContent = S.mode === 'band' ? 'No exposures in this channel; pick another channel in the strip below.' : 'Try another detector or mode.';
      $('expTable').innerHTML = ''; $('expCount').textContent = '';
      return;
    }
    const k = clamp(S.frame, 0, FRAMES.length - 1), fr = FRAMES[k], { npc } = cropInfo();
    const id = renderImageData(k);
    if (c.width !== npc) { c.width = npc; c.height = npc; }
    c.getContext('2d').putImageData(id, 0, 0);
    c.classList.toggle('smooth', !!S.smooth);
    $('frameLabel').textContent = `${fr.label}  (${k + 1}/${FRAMES.length})`;
    $('frameSub').textContent = fr.sub;
    $('frameRange').value = k;
    document.querySelectorAll('#filmstrip button').forEach((b, i) => b.classList.toggle('active', i === k));
    const act = document.querySelector('#filmstrip button.active'); if (act && act.scrollIntoView) act.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    renderLegend(fr); drawOverlay(); renderExposureTable(fr); highlightSpectrum(fr);
    if (S.mode === 'scan') drawBandStrip();
  }
  // WiseView-style legend: which visits this frame adds (+), subtracts (−) or leaves out (·)
  function renderLegend(fr) {
    const el = $('epochLegend'); if (!el) return;
    el.innerHTML = 'Visits used: ' + VISITS.map((v, k) => {
      const plus = fr.plus && fr.plus.has(k), minus = fr.minus && fr.minus.has(k);
      const ch = plus && minus ? '±' : plus ? '+' : minus ? '−' : '·', cls = plus ? 'text-success' : minus ? 'text-danger' : 'text-secondary';
      return `<span class="${cls} fw-bold" title="${v.label}: ${v.range} (${v.idx.length} exposures)">${ch}</span>`;
    }).join(' ') + (S.sa ? ` <span class="badge text-bg-warning ms-2">shift-and-add ${(+S.sapmra / 1000).toFixed(2)}, ${(+S.sapmdec / 1000).toFixed(2)} ″/yr</span>` : '');
  }
  function renderFilmstrip() {
    const box = $('filmstrip'); box.innerHTML = '';
    if (FRAMES.length > 150) { box.innerHTML = `<span class="small text-secondary">${FRAMES.length} frames: use the slider.</span>`; return; }
    FRAMES.forEach((fr, i) => {
      const b = document.createElement('button');
      b.textContent = S.mode === 'scan' ? `ch ${fr.band}` : (S.mode === 'exp' ? mjdToDate(fr.mjd).slice(2) : fr.label.split(' · ')[0]);
      b.title = fr.sub; b.onclick = () => { stopPlay(); S.frame = i; renderFrame(); writeUrl(); };
      box.appendChild(b);
    });
  }

  // ---------------------------------------------------------------- overlays
  function ovGeom() {
    const ov = $('ovCanvas'), rect = ov.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    const W = Math.max(10, Math.round(rect.width * dpr));
    if (ov.width !== W) { ov.width = W; ov.height = W; }
    const { npc, off } = cropInfo();
    const s = W / npc;
    const toScreen = (gx, gy) => [(gx - off + 0.5) * s, (npc - (gy - off) - 0.5) * s];
    return { ov, ctx: ov.getContext('2d'), W, s, npc, off, dpr, toScreen };
  }
  const ovOn = (k) => String(S.ov).split(',').includes(k);
  function drawOverlay() {
    if (!F || !FRAMES.length) return;
    const g0 = ovGeom(), ctx = g0.ctx, fr = FRAMES[clamp(S.frame, 0, FRAMES.length - 1)];
    const [sdx, sdy] = shiftAt(fr.mjd);             // in shift-and-add mode, draw everything in the co-moving frame
    const g = { ...g0, toScreen: (gx, gy) => g0.toScreen(gx - sdx, gy - sdy) };
    ctx.clearRect(0, 0, g.W, g.W);
    ctx.lineWidth = Math.max(1, g.dpr);
    // flags
    if (ovOn('flags') && fr.cat) {
      const id = new ImageData(g.npc, g.npc), d = id.data;
      for (let r = 0; r < g.npc; r++) { const y = g.off + (g.npc - 1 - r); for (let x = 0; x < g.npc; x++) {
        const cv = fr.cat[y * F.np + g.off + x], o = (r * g.npc + x) * 4;
        if (cv & CAT_SAT) { d[o] = 255; d[o + 1] = 40; d[o + 2] = 40; d[o + 3] = 120; }
        else if (cv & CAT_ART) { d[o] = 255; d[o + 1] = 200; d[o + 2] = 0; d[o + 3] = 90; }
        else if (cv & CAT_BAD) { d[o] = 120; d[o + 1] = 120; d[o + 2] = 140; d[o + 3] = 110; }
      } }
      const tmp = document.createElement('canvas'); tmp.width = tmp.height = g.npc; tmp.getContext('2d').putImageData(id, 0, 0);
      ctx.imageSmoothingEnabled = false; ctx.drawImage(tmp, 0, 0, g.W, g.W);
    }
    const t = F.meta.target;
    // catalogs
    if (ovOn('gaia')) {
      for (const st of F.meta.catalogs.gaia) {
        const [ra, dec] = apparent(st.ra, st.dec, st.pmra, st.pmdec, st.plx, 57388.0, fr.mjd, fr.earth);
        const [x, y] = g.toScreen(...world2pix(ra, dec)); if (x < -10 || y < -10 || x > g.W + 10 || y > g.W + 10) continue;
        const pm = Math.hypot(st.pmra, st.pmdec), fast = pm > 200;
        const r = clamp(10 - 0.45 * (st.g - 8), 2.5, 12) * g.dpr;
        ctx.strokeStyle = fast ? 'rgba(0,230,255,0.95)' : 'rgba(110,168,254,0.75)';
        ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.stroke();
        if (fast) { // arrow: motion over 5 years
          const [ra2, dec2] = propagate(st.ra, st.dec, st.pmra, st.pmdec, 57388.0, fr.mjd + 5 * 365.25);
          const [x2, y2] = g.toScreen(...world2pix(ra2, dec2)); arrow(ctx, x, y, x2, y2, 'rgba(0,230,255,0.95)', g.dpr);
        }
      }
    }
    if (ovOn('wise')) {
      ctx.strokeStyle = 'rgba(255,159,64,0.8)';
      for (const st of F.meta.catalogs.catwise) {   // CatWISE2020 motion-fit positions (epoch MJD 57170) moved to this frame's date
        const [cra, cde] = propagate(st.ra, st.dec, st.pmra || 0, st.pmdec || 0, st.epoch || 57170.0, fr.mjd);
        const [x, y] = g.toScreen(...world2pix(cra, cde)); if (x < -10 || y < -10 || x > g.W + 10 || y > g.W + 10) continue;
        const r = 4 * g.dpr; ctx.beginPath(); ctx.moveTo(x, y - r); ctx.lineTo(x + r, y); ctx.lineTo(x, y + r); ctx.lineTo(x - r, y); ctx.closePath(); ctx.stroke();
      }
    }
    if (ovOn('tmass') && F.meta.catalogs.tmass) {      // 2MASS: no proper motions; drawn at the catalogue position
      ctx.strokeStyle = 'rgba(255,255,255,0.75)';
      for (const st of F.meta.catalogs.tmass) {
        const [x, y] = g.toScreen(...world2pix(st.ra, st.dec)); if (x < -10 || y < -10 || x > g.W + 10 || y > g.W + 10) continue;
        ctx.beginPath(); ctx.arc(x, y, 5 * g.dpr, 0, 2 * Math.PI); ctx.stroke();
      }
    }
    // target track + predicted position
    if (ovOn('target')) {
      ctx.fillStyle = 'rgba(255,193,7,0.85)';
      const track = VISITS.map((v) => targetAt(v.idx, (v.mjd0 + v.mjd1) / 2));
      track.forEach(([ra, dec]) => { const [x, y] = g.toScreen(...world2pix(ra, dec)); ctx.beginPath(); ctx.arc(x, y, 1.6 * g.dpr, 0, 2 * Math.PI); ctx.fill(); });
      const [ra, dec] = targetAt(fr.members || [], fr.mjd);
      const [x, y] = g.toScreen(...world2pix(ra, dec));
      ctx.strokeStyle = 'rgba(255,193,7,0.95)'; ctx.lineWidth = 1.5 * g.dpr;
      const r = Math.max(3.5 * g.s, 9 * g.dpr);
      ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x - r * 1.6, y); ctx.lineTo(x - r * 1.15, y); ctx.moveTo(x + r * 1.15, y); ctx.lineTo(x + r * 1.6, y);
      ctx.moveTo(x, y - r * 1.6); ctx.lineTo(x, y - r * 1.15); ctx.moveTo(x, y + r * 1.15); ctx.lineTo(x, y + r * 1.6); ctx.stroke();
      ctx.lineWidth = Math.max(1, g.dpr);
    }
    if (ovOn('movers')) {
      MOVERS.forEach((m, i) => {
        const [x1, y1] = g.toScreen(m.px, m.py), [x2, y2] = g.toScreen(m.nx, m.ny);
        arrow(ctx, x1, y1, x2, y2, 'rgba(255,99,255,0.95)', g.dpr);
        ctx.fillStyle = 'rgba(255,99,255,0.95)'; ctx.font = `${11 * g.dpr}px system-ui`; ctx.fillText(`M${i + 1}`, x2 + 5 * g.dpr, y2 - 5 * g.dpr);
      });
    }
    if (PIN) {
      const [x, y] = g.toScreen(...world2pix(PIN.ra, PIN.dec)); const r = 7 * g.dpr;
      ctx.strokeStyle = '#ff6b6b'; ctx.lineWidth = 1.5 * g.dpr;
      ctx.beginPath(); ctx.moveTo(x - r, y - r); ctx.lineTo(x + r, y + r); ctx.moveTo(x + r, y - r); ctx.lineTo(x - r, y + r); ctx.stroke();
      ctx.lineWidth = Math.max(1, g.dpr);
    }
    if (ovOn('compass')) {
      const pad = 14 * g.dpr, L = 26 * g.dpr, x0 = g.W - pad - L * 0.2, y0 = g.W - pad;
      ctx.strokeStyle = ctx.fillStyle = 'rgba(230,230,230,0.9)'; ctx.font = `${11 * g.dpr}px system-ui`;
      arrow(ctx, x0, y0, x0, y0 - L, 'rgba(230,230,230,0.9)', g.dpr); ctx.fillText('N', x0 - 4 * g.dpr, y0 - L - 4 * g.dpr);
      arrow(ctx, x0, y0, x0 - L, y0, 'rgba(230,230,230,0.9)', g.dpr); ctx.fillText('E', x0 - L - 12 * g.dpr, y0 + 4 * g.dpr);
      const bar = 60 / PIX * g.s, bx = pad, by = g.W - pad;
      ctx.lineWidth = 2 * g.dpr; ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx + bar, by); ctx.stroke();
      ctx.fillText('1′', bx + bar / 2 - 4 * g.dpr, by - 5 * g.dpr); ctx.lineWidth = Math.max(1, g.dpr);
    }
  }
  function arrow(ctx, x1, y1, x2, y2, col, dpr) {
    const a = Math.atan2(y2 - y1, x2 - x1), h = 6 * dpr;
    ctx.strokeStyle = col; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
    ctx.lineTo(x2 - h * Math.cos(a - 0.45), y2 - h * Math.sin(a - 0.45)); ctx.moveTo(x2, y2);
    ctx.lineTo(x2 - h * Math.cos(a + 0.45), y2 - h * Math.sin(a + 0.45)); ctx.stroke();
  }

  // ---------------------------------------------------------------- hover / click
  function eventToGrid(ev) {
    const g = ovGeom(), rect = g.ov.getBoundingClientRect();
    const sx = (ev.clientX - rect.left) * g.dpr, sy = (ev.clientY - rect.top) * g.dpr;
    const gx = sx / g.s - 0.5 + g.off, gy = (g.npc - sy / g.s - 0.5) + g.off;
    return { gx, gy, g };
  }
  function onHover(ev) {
    if (!F || !FRAMES.length) return;
    const { gx, gy } = eventToGrid(ev), fr = FRAMES[S.frame];
    const ix = Math.round(gx), iy = Math.round(gy);
    if (ix < 0 || iy < 0 || ix >= F.np || iy >= F.np) return;
    const [ra, dec] = pix2world(gx, gy), p = iy * F.np + ix;
    let val;
    if (fr.rgb) val = `R ${fmt(fr.rgb[0].img[p], 3)}  G ${fmt(fr.rgb[1].img[p], 3)}  B ${fmt(fr.rgb[2].img[p], 3)}`;
    else val = fmt(fr.img[p], 4);
    const c = fr.cat[p], flags = [c & CAT_SAT ? 'saturated' : '', c & CAT_ART ? 'artefact' : '', c & CAT_BAD ? 'masked' : ''].filter(Boolean).join(', ');
    let near = '';
    let best = 2.2;
    for (const st of F.meta.catalogs.gaia) {
      const [sra, sde] = apparent(st.ra, st.dec, st.pmra, st.pmdec, st.plx, 57388.0, fr.mjd, fr.earth); const [x, y] = world2pix(sra, sde);
      const dd = Math.hypot(x - gx, y - gy); if (dd < best) { best = dd; near = `Gaia DR3 ${st.id}  G=${st.g}  PM ${fmt(Math.hypot(st.pmra, st.pmdec) / 1000, 2)}″/yr`; }
    }
    $('hoverReadout').innerHTML = `RA ${ra.toFixed(5)}°  Dec ${dec.toFixed(5)}°<br>${raToHms(ra)} ${decToDms(dec)}<br>${fr.isDiff ? 'Δ ' : ''}${val} MJy/sr ${fr.isDiff ? 'difference' : 'above local sky'}${fr.members && fr.members.length > 1 ? ` (mean of ${fr.members.length} exposures, ${waveRange(fr.members)})` : ''}${flags ? ' · ' + flags : ''}${near ? '<br><span class="text-info">' + near + '</span>' : ''}`;
  }
  function onClick(ev) {
    if (!F) return;
    const { gx, gy } = eventToGrid(ev); const [ra, dec] = pix2world(gx, gy);
    setPin(ra, dec);
  }
  function setPin(ra, dec) {
    PIN = { ra, dec };
    const deg = `${ra.toFixed(5)} ${dec.toFixed(5)}`, sex = `${raToHms(ra)} ${decToDms(dec)}`;
    $('pinBox').innerHTML = `<div class="d-flex justify-content-between"><b>Pinned</b><a href="#" id="unpin" class="small">clear</a></div>
      <div class="font-monospace">${deg}</div><div class="font-monospace">${sex}</div>
      <div class="mt-1 d-flex gap-1 flex-wrap"><button class="btn btn-xs btn-sm py-0 btn-outline-info" data-copy="${deg}">copy deg</button>
      <button class="btn btn-sm py-0 btn-outline-info" data-copy="${sex}">copy hms/dms</button>
      <button class="btn btn-sm py-0 btn-outline-secondary" id="pinToInput">use as input</button></div>`;
    $('pinBox').querySelectorAll('[data-copy]').forEach((b) => b.onclick = () => copyText(b.dataset.copy, $('shareMsg'), 'Coordinates copied.'));
    $('unpin').onclick = (e) => { e.preventDefault(); clearPin(); drawOverlay(); writeUrl(); };
    $('pinToInput').onclick = () => { $('coordInput').value = sex; };
    drawOverlay(); writeUrl();
  }
  function clearPin() { PIN = null; $('pinBox').textContent = 'Click the image to pin a position.'; }
  async function copyText(text, msgEl, ok) {
    try { await navigator.clipboard.writeText(text); setMsg(msgEl, ok, 'success'); }
    catch (e) { const inp = $('shareUrl'); const prev = inp.value; inp.value = text; inp.select(); setMsg(msgEl, 'Copy blocked by the browser: the text is selected in the box above, press Ctrl/Cmd+C.', 'warning'); setTimeout(() => { inp.value = prev; }, 8000); }
  }

  // ---------------------------------------------------------------- band strip (102 channels)
  function bandCenter(b) { const c = CHANNELS[b - 1]; return c ? c.wave : NaN; }
  function bandDet(b) { const c = CHANNELS[b - 1]; return c ? c.det : Math.ceil(b / 17); }
  function waveColor(w) { // 0.75..5 um -> blue..red (turbo-like)
    const t = clamp(Math.log(w / 0.75) / Math.log(5 / 0.75), 0, 1);
    const r = Math.round(255 * clamp(1.5 - Math.abs(4 * t - 3), 0, 1)), g = Math.round(255 * clamp(1.5 - Math.abs(4 * t - 2), 0, 1)), b = Math.round(255 * clamp(1.5 - Math.abs(4 * t - 1), 0, 1));
    return `rgb(${Math.max(r, 40)},${Math.max(g, 40)},${Math.max(b, 60)})`;
  }
  function drawBandStrip() {
    const cv = $('bandStrip'); if (!F) return;
    const dpr = window.devicePixelRatio || 1, W = Math.round(cv.clientWidth * dpr), H = Math.round(64 * dpr);
    if (cv.width !== W) cv.width = W; if (cv.height !== H) cv.height = H;
    const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, W, H);
    const counts = new Array(103).fill(0); for (const e of F.meta.exposures) if (e.band) counts[e.band]++;
    const maxC = Math.max(1, ...counts), cw = W / 102;
    let observed = 0;
    for (let b = 1; b <= 102; b++) {
      const x = (b - 1) * cw, c = counts[b]; if (c) observed++;
      const h = c ? (0.25 + 0.75 * c / maxC) * (H - 6 * dpr) : 2 * dpr;
      ctx.fillStyle = c ? waveColor(bandCenter(b)) : '#334155';
      ctx.fillRect(x + 0.5, H - h, Math.max(1, cw - 1), h);
      if ((b - 1) % 17 === 0 && b > 1) { ctx.fillStyle = '#64748b'; ctx.fillRect(x - 0.5, 0, 1, H); }
    }
    const sel = [];
    if (S.mode === 'band') for (let b = S.band - S.tol; b <= S.band + S.tol; b++) sel.push(b);
    if (S.mode === 'scan' && FRAMES[S.frame]) sel.push(FRAMES[S.frame].band);
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5 * dpr;
    for (const b of sel) if (b >= 1 && b <= 102) ctx.strokeRect((b - 1) * cw + 0.5, 1, cw - 1, H - 2);
    $('bandStripInfo').textContent = `${observed}/102 channels observed · ${F.meta.exposures.length} exposures`;
  }
  function onBandClick(ev) {
    if (!F) return;
    const rect = $('bandStrip').getBoundingClientRect(); const b = clamp(Math.floor((ev.clientX - rect.left) / rect.width * 102) + 1, 1, 102);
    S.band = b; S.mode = 'band'; S.frame = 0; syncControls(); rebuild();
  }
  function onBandHover(ev) {
    if (!F) return;
    const rect = $('bandStrip').getBoundingClientRect(); const b = clamp(Math.floor((ev.clientX - rect.left) / rect.width * 102) + 1, 1, 102);
    const n = F.meta.exposures.filter((e) => e.band === b).length;
    const cc = CHANNELS[b - 1];
    $('bandStrip').title = `Channel ${b} (D${cc.det} sub-channel ${cc.sub}): ${cc.wmin.toFixed(3)}–${cc.wmax.toFixed(3)} µm, R=${cc.R}. ${n} exposures here. Click to compare visits at this wavelength.`;
  }

  // ---------------------------------------------------------------- spectrum & light curve (Plotly)
  const PLOT_LAYOUT = { paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', font: { color: '#cbd5e1', size: 11 }, margin: { l: 52, r: 10, t: 8, b: 38 }, legend: { orientation: 'h', y: 1.12, font: { size: 10 } } };
  const VISIT_COLORS = ['#4dabf7', '#ffd43b', '#ff6b6b', '#69db7c', '#da77f2', '#ffa94d', '#20c997', '#f783ac'];
  function exposureVisit(i) { return VISITS.findIndex((v) => v.idx.includes(i)); }
  function isFlagged(e) { return e.phot_flags && e.phot_flags.length > 0; }
  function drawSpectrum() {
    if (!window.Plotly || !F) { $('specPlot').innerHTML = '<div class="small text-secondary p-2">Plot library unavailable.</div>'; return; }
    const ex = F.meta.exposures, traces = [];
    VISITS.forEach((v, k) => {
      const pts = v.idx.filter((i) => ex[i].flux_ujy !== null && ex[i].wave && !(S.specClean && isFlagged(ex[i])));
      traces.push({ x: pts.map((i) => ex[i].wave), y: pts.map((i) => ex[i].flux_ujy), error_y: { type: 'data', array: pts.map((i) => ex[i].flux_err || 0), thickness: 0.8, width: 0, color: VISIT_COLORS[k % 8] },
        mode: 'markers', type: 'scatter', name: `V${k + 1} ${mjdToDate(v.mjd0).slice(0, 7)}`,
        marker: { size: 5, color: VISIT_COLORS[k % 8], symbol: pts.map((i) => isFlagged(ex[i]) ? 'circle-open' : 'circle') },
        text: pts.map((i) => `${ex[i].obs_id} D${ex[i].det}<br>${mjdToIso(ex[i].mjd)}${isFlagged(ex[i]) ? '<br>flags: ' + ex[i].phot_flags.join(', ') : ''}`), hovertemplate: '%{x:.3f} µm<br>%{y:.1f} µJy<br>%{text}<extra></extra>' });
    });
    const yr = (mjd) => (2000 + (mjd - 51544.5) / 365.25).toFixed(0);
    for (const [survey, sym, col, label] of [['2MASS', 'diamond', '#ffffff', '2MASS J/H/Ks'], ['WISE', 'square', '#ff9f43', 'WISE W1/W2 (CatWISE2020)']]) {
      const pts = (F.meta.sed || []).filter((p) => p.flux_ujy != null && p.band.startsWith(survey));
      if (!pts.length) continue;
      const when = survey === '2MASS' ? ` ${yr(pts[0].mjd)}` : ' 2010–18';
      traces.push({ x: pts.map((p) => p.wave), y: pts.map((p) => p.flux_ujy), error_y: { type: 'data', array: pts.map((p) => p.err || 0), thickness: 1, width: 3, color: col },
        mode: 'markers', type: 'scatter', name: label + when, marker: { size: 10, symbol: sym, color: 'rgba(0,0,0,0)', line: { color: col, width: 2 } },
        text: pts.map((p) => `${p.band} · ${p.id} · matched ${p.sep}″ at the catalogue epoch`), hovertemplate: '%{x:.3f} µm<br>%{y:.4g} µJy<br>%{text}<extra></extra>' });
    }
    traces.push({ x: [], y: [], mode: 'markers', type: 'scatter', name: 'this frame', marker: { size: 11, color: 'rgba(0,0,0,0)', line: { color: '#fff', width: 1.5 } }, hoverinfo: 'skip' });
    const layout = { ...PLOT_LAYOUT, xaxis: { title: 'wavelength (µm)', range: [0.7, 5.1], gridcolor: '#1f2937' }, yaxis: { title: 'flux (µJy)', type: S.specLog ? 'log' : 'linear', gridcolor: '#1f2937' } };
    Plotly.react('specPlot', traces, layout, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] });
    if (FRAMES.length) highlightSpectrum(FRAMES[S.frame]);
    const n = ex.filter((e) => e.flux_ujy !== null).length, nf = ex.filter((e) => e.flux_ujy !== null && isFlagged(e)).length, nw = ex.filter((e) => e.flux_ujy === null).length;
    $('specNote').textContent = `${n - nf} clean measurements` + (nf ? `, ${nf} with flagged pixels in the aperture${S.specClean ? ' (hidden)' : ' (hollow)'}` : '') + (nw ? `, ${nw} not measurable (off the detector or no background)` : '') + '.'
      + (n && nf === n ? ' Every measurement has flagged pixels: this target is bright enough to saturate SPHEREx, so its photometry is not reliable.' : '')
      + (F.meta.sed || []).filter((p) => p.note).map((p) => ' ' + p.note).join('');
  }
  function highlightSpectrum(fr) {
    if (!window.Plotly || !F || !$('specPlot').data) return;
    const ex = F.meta.exposures, m = (fr ? fr.members : []).filter((i) => ex[i].flux_ujy !== null && ex[i].wave && !(S.specClean && isFlagged(ex[i]))).slice(0, 400);
    const idx = $('specPlot').data.length - 1;
    try { Plotly.restyle('specPlot', { x: [m.map((i) => ex[i].wave)], y: [m.map((i) => ex[i].flux_ujy)] }, [idx]); } catch (e) { /* plot hidden */ }
  }
  function drawLightCurve() {
    // Variability free of spectral shape: SPHEREx sees the target at a different wavelength in every exposure, so each
    // clean measurement is divided by the median of all clean measurements of the same star in the same channel.
    // A constant star gives 1 at every date; a variable star departs from 1. Channels with fewer than 2 points are skipped.
    if (!window.Plotly || !F) return;
    const ex = F.meta.exposures, byBand = {};
    ex.forEach((e, i) => { if (e.flux_ujy !== null && e.band && !isFlagged(e) && e.flux_ujy > 0) (byBand[e.band] = byBand[e.band] || []).push(i); });
    const med = {};
    for (const [b, idx] of Object.entries(byBand)) if (idx.length >= 2) { const v = idx.map((i) => ex[i].flux_ujy).sort((p, q) => p - q); med[b] = percentile(v, 50); }
    const traces = [];
    for (let d = 1; d <= 6; d++) {
      const pts = ex.map((e, i) => i).filter((i) => ex[i].det === d && med[ex[i].band] && ex[i].flux_ujy !== null && !isFlagged(ex[i]) && ex[i].flux_ujy > 0);
      if (!pts.length) continue;
      traces.push({ x: pts.map((i) => mjdToIso(ex[i].mjd)), y: pts.map((i) => ex[i].flux_ujy / med[ex[i].band]),
        error_y: { type: 'data', array: pts.map((i) => (ex[i].flux_err || 0) / med[ex[i].band]), thickness: 0.6, width: 0 },
        mode: 'markers', type: 'scatter', name: `D${d}`, marker: { size: 5, color: waveColor(DET_RANGE[d] ? (DET_RANGE[d][0] + DET_RANGE[d][1]) / 2 : 1) },
        text: pts.map((i) => `channel ${ex[i].band}, ${fmt(ex[i].wave, 3)} µm, ${fmt(ex[i].flux_ujy, 4)} µJy`), hovertemplate: '%{x}<br>%{y:.3f} × channel median<br>%{text}<extra>D' + d + '</extra>' });
    }
    if (!traces.length) { try { Plotly.purge('lcPlot'); } catch (e) { /* none */ } $('lcPlot').innerHTML = '<div class="small text-secondary p-3">No channel has two or more clean measurements of the target (flagged pixels in the aperture, or the target saturates SPHEREx).</div>'; return; }
    if (!$('lcPlot').data) $('lcPlot').innerHTML = '';
    Plotly.react('lcPlot', traces, { ...PLOT_LAYOUT, xaxis: { type: 'date', gridcolor: '#1f2937' }, yaxis: { title: 'flux ÷ median in same channel', gridcolor: '#1f2937', zeroline: false },
      shapes: [{ type: 'line', xref: 'paper', x0: 0, x1: 1, y0: 1, y1: 1, line: { color: '#64748b', width: 1, dash: 'dot' } }] }, { displaylogo: false, responsive: true });
  }


  // ---------------------------------------------------------------- movers (experimental)
  const MOVER_SIGMA = 6;
  function lobeCentroid(D, n, x, y, sign, med) {
    let sx = 0, sy = 0, sw = 0;
    for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) {
      const v = sign * (D[(y + dy) * n + x + dx] - med); if (v > 0) { sx += v * (x + dx); sy += v * (y + dy); sw += v; }
    }
    return sw > 0 ? [sx / sw, sy / sw] : [x, y];
  }
  function computeMovers() {
    MOVERS = [];
    const box = $('moverList');
    if (!F || VISITS.length < 2) { box.innerHTML = '<div class="text-secondary">Needs at least two visits.</div>'; return; }
    const pick = (v) => v.idx.filter(S.det === 'rgb' ? () => true : detFilter);
    const vis = VISITS.filter((v) => pick(v).length);
    if (vis.length < 2) { box.innerHTML = '<div class="text-secondary">Needs at least two visits with data.</div>'; return; }
    const A = balancedCoadd(pick(vis[0])), B = balancedCoadd(pick(vis[vis.length - 1])), n = F.np, D = new Float32Array(n * n), dt = (meanMjd(pick(vis[vis.length - 1])) - meanMjd(pick(vis[0]))) / 365.25;
    const vals = [];
    for (let p = 0; p < n * n; p++) { D[p] = A.img[p] - B.img[p]; if (D[p] === D[p]) vals.push(D[p]); }
    vals.sort((a, b) => a - b); const med = percentile(vals, 50);
    const mad = vals.map((v) => Math.abs(v - med)).sort((a, b) => a - b); const sig = 1.4826 * percentile(mad, 50) || 1e-9;
    const peaks = [];
    for (let y = 2; y < n - 2; y++) for (let x = 2; x < n - 2; x++) {
      const p = y * n + x, v = D[p]; if (!(Math.abs(v - med) > MOVER_SIGMA * sig)) continue;
      if ((A.cat[p] | B.cat[p]) & CAT_SAT) continue;
      let ext = true;
      for (let dy = -1; dy <= 1 && ext; dy++) for (let dx = -1; dx <= 1; dx++) { if (!dx && !dy) continue; const q = D[p + dy * n + dx]; if (q === q && (v > 0 ? q > v : q < v)) { ext = false; break; } }
      if (ext) peaks.push({ x, y, v, snr: (v - med) / sig });
    }
    const pos = peaks.filter((q) => q.snr > 0), neg = peaks.filter((q) => q.snr < 0);
    const stationary = F.meta.catalogs.gaia.filter((s) => Math.hypot(s.pmra, s.pmdec) < 100).map((s) => world2pix(...propagate(s.ra, s.dec, s.pmra, s.pmdec, 57388.0, F.meta.grid.mjd_ref)));
    const nearStatic = (x, y) => stationary.some(([sx, sy]) => Math.hypot(sx - x, sy - y) < 1.6);
    const used = new Set();
    for (const a of pos.sort((p, q) => q.snr - p.snr)) {
      let best = null, bd = 6.5;
      neg.forEach((b, j) => { if (used.has(j)) return; const d = Math.hypot(a.x - b.x, a.y - b.y); if (d >= 0.7 && d < bd) { bd = d; best = j; } });
      if (best === null) continue;
      const b = neg[best], ratio = a.snr / -b.snr;
      if (ratio < 0.33 || ratio > 3) continue;           // a moving point source leaves a roughly symmetric +/- pair
      if (nearStatic(a.x, a.y) && nearStatic(b.x, b.y)) continue;
      used.add(best);
      const [ax, ay] = lobeCentroid(D, n, a.x, a.y, 1, med), [bx, by] = lobeCentroid(D, n, b.x, b.y, -1, med);
      const [ra1, de1] = pix2world(ax, ay), [ra2, de2] = pix2world(bx, by);
      const pm = angSepDeg(ra1, de1, ra2, de2) * 3600 / Math.max(dt, 1e-3);
      MOVERS.push({ px: ax, py: ay, nx: bx, ny: by, snr: Math.min(a.snr, -b.snr), ra: ra2, dec: de2, pm });
      if (MOVERS.length >= 10) break;
    }
    if (!MOVERS.length) { box.innerHTML = `<div class="text-secondary">No dipole above ${MOVER_SIGMA}σ between ${vis[0].label} and ${vis[vis.length - 1].label} for this detector choice.</div>`; }
    else {
      box.innerHTML = MOVERS.map((m, i) => `<div class="mover-row p-1 border-bottom border-secondary-subtle" data-i="${i}"><b>M${i + 1}</b> ${m.ra.toFixed(4)} ${m.dec.toFixed(4)} · ${m.snr.toFixed(1)}σ · ~${m.pm.toFixed(1)}″/yr (rough)</div>`).join('')
        + `<div class="text-secondary mt-1">Baseline ${dt.toFixed(2)} yr. Click a row to pin it.</div>`;
      box.querySelectorAll('.mover-row').forEach((r) => r.onclick = () => { const m = MOVERS[+r.dataset.i]; setPin(m.ra, m.dec); });
    }
    if (ovOn('movers')) drawOverlay();
  }

  // ---------------------------------------------------------------- tables / provenance
  function flagPills(names) {
    if (!names || !names.length) return '<span class="text-secondary">none</span>';
    const sat = ['OVERFLOW', 'NONLINEAR'], art = ['GHOST', 'GHOST_FPA', 'GHOST_EXT', 'STREAK', 'BLOOM', 'HALO', 'CROSSTALK'], bad = ['TRANSIENT', 'SUR_ERROR', 'NONFUNC', 'MISSING_DATA', 'HOT', 'COLD', 'OUTLIER', 'PERSIST'];
    return names.filter((n) => n !== 'FULLSAMPLE').map((n) => `<span class="st-flagpill ${sat.includes(n) ? 'sat' : art.includes(n) ? 'art' : bad.includes(n) ? 'bad' : ''}">${n}</span>`).join('');
  }
  function renderExposureTable(fr) {
    const ex = F.meta.exposures, m = fr.members.slice().sort((a, b) => ex[a].mjd - ex[b].mjd);
    $('expCount').textContent = `${m.length}`;
    $('expTable').innerHTML = m.slice(0, 150).map((i) => { const e = ex[i];
      return `<tr><td class="text-nowrap">${mjdToIso(e.mjd)}</td><td>${e.det}</td><td>${fmt(e.wave, 3)}</td><td>${e.band ?? '–'}</td><td>${flagPills(e.target_flags)}</td><td><a href="${e.url}" target="_blank" rel="noopener" title="Full SPHEREx FITS file at IRSA (~70 MB)">FITS</a></td></tr>`; }).join('')
      + (m.length > 150 ? `<tr><td colspan="6" class="text-secondary">…and ${m.length - 150} more</td></tr>` : '');
  }
  function renderProvenance() {
    const m = F.meta, ex = m.exposures, t = m.target;
    const mj = ex.map((e) => e.mjd); const sat = ex.filter((e) => (e.target_flags || []).some((f) => f === 'OVERFLOW' || f === 'NONLINEAR')).length;
    $('provenance').innerHTML = `
      <div><b>${ex.length}</b> SPHEREx exposures, <b>${VISITS.length}</b> visits, ${mjdToDate(Math.min(...mj))} → ${mjdToDate(Math.max(...mj))}</div>
      <div>Grid ${m.grid.npix}×${m.grid.npix} px at ${m.grid.pixscale}″ (${(m.grid.npix * m.grid.pixscale / 60).toFixed(1)}′), centre ${m.grid.crval[0].toFixed(5)} ${m.grid.crval[1].toFixed(5)}</div>
      <div>Target PM ${fmt(t.pmra / 1000, 3)}, ${fmt(t.pmdec / 1000, 3)} ″/yr · ${m.source || ''}</div>
      <div>Saturation flags at target in ${sat}/${ex.length} exposures</div>
      <div>Collections: ${(m.collections || []).map((c) => `<code>${c}</code>`).join(' ')}</div>
      <div>Overlays (all via NASA/IPAC IRSA): ${m.catalogs.gaia.length} Gaia DR3 (ESA), ${m.catalogs.catwise.length} CatWISE2020 (NASA WISE/NEOWISE), ${(m.catalogs.tmass || []).length} 2MASS (NASA/IPAC) sources</div>
      <div class="text-secondary">Built ${m.built} in ${m.build_seconds}s · <a href="https://irsa.ipac.caltech.edu/Missions/spherex.html" target="_blank" rel="noopener">IRSA SPHEREx</a></div>
      ${LIVE ? '<button class="btn btn-sm btn-outline-success mt-2" id="checkReleases">Check IRSA for new data releases</button><div id="relMsg" class="form-text small"></div>' : ''}`;
    if (LIVE) $('checkReleases').onclick = checkReleases;
  }

  function renderBlendNote() {
    // Warn when a catalogued star sits within ~2.5 SPHEREx pixels of the target during the SPHEREx era
    const t = F.meta.target, mjd = F.meta.grid.mjd_ref, [tra, tde] = propagate(t.ra, t.dec, t.pmra, t.pmdec, t.epoch_mjd, mjd);
    const near = F.meta.catalogs.gaia.map((s) => { const [ra, de] = propagate(s.ra, s.dec, s.pmra, s.pmdec, 57388.0, mjd); return { s, d: angSepDeg(tra, tde, ra, de) * 3600 }; })
      .filter((o) => o.d > 1.5 && o.d < 2.5 * PIX).sort((a, b) => a.d - b.d).slice(0, 3);
    const el = $('blendNote');
    el.classList.toggle('d-none', !near.length);
    el.textContent = near.length ? `Blend warning: ${near.map((o) => `Gaia DR3 ${o.s.id} (G=${o.s.g}) is ${o.d.toFixed(1)}″ away`).join('; ')} in ${mjdToDate(mjd).slice(0, 7)}. SPHEREx pixels are ${PIX}″, so their light overlaps; check the spectrum.` : '';
  }

  // ---------------------------------------------------------------- live server (optional)
  async function checkReleases() {
    const msg = $('relMsg'); setMsg(msg, 'Asking IRSA…');
    try {
      const r = await fetchJson('api/releases');
      const have = new Set(F.meta.collections || []), fresh = r.collections.filter((c) => !have.has(c));
      if (fresh.length) {
        msg.innerHTML = `New: ${fresh.map((c) => `<code>${c}</code>`).join(' ')} <button class="btn btn-sm py-0 btn-success" id="rebuildBtn">Rebuild this field</button>`;
        $('rebuildBtn').onclick = () => liveBuild({ ra: F.meta.target.ra, dec: F.meta.target.dec, pmra: F.meta.target.pmra, pmdec: F.meta.target.pmdec, epoch_mjd: F.meta.target.epoch_mjd, name: F.meta.name, force: 1 });
      } else setMsg(msg, `Up to date (${r.collections.join(', ')}).`, 'success');
    } catch (e) { setMsg(msg, 'Could not reach IRSA: ' + e.message, 'danger'); }
  }
  async function liveBuild(q) {
    veil(true, 'Searching the IRSA SPHEREx archive…');
    if (window.SkyJourney && isFinite(q.ra) && isFinite(q.dec)) SkyJourney.travel(+q.ra, +q.dec, true);
    try {
      const params = new URLSearchParams(Object.entries(q).filter(([, v]) => v !== undefined && v !== null));
      const job = await fetchJson('api/field?' + params.toString(), { method: 'POST' });
      let st = job;
      while (st.status !== 'done' && st.status !== 'error') {
        await new Promise((r) => setTimeout(r, 1500));
        st = await fetchJson('api/job/' + job.id);
        veil(true, st.message || 'Working…');
      }
      if (st.status === 'error') throw new Error(st.message);
      await loadIndex(); await openField(st.key, true);
    } catch (e) { if (window.SkyJourney) SkyJourney.arrive(); veil(true, 'Archive search failed: ' + e.message); setTimeout(() => veil(false), 6000); }
  }

  // ---------------------------------------------------------------- go / input
  async function onGo() {
    const msg = $('coordMsg'); const r = parseInput($('coordInput').value);
    if (!r) return setMsg(msg, 'Type coordinates or a name.', 'warning');
    if (r.error) return setMsg(msg, r.error, 'danger');
    if (r.field) { setMsg(msg, `Opening ${r.name}.`, 'success'); return openField(r.field, true); }
    // coordinates: inside a pre-built field?
    let best = null, bd = Infinity;
    for (const f of INDEX.fields) { const d = angSepDeg(r.ra, r.dec, f.ra, f.dec); if (d < bd) { bd = d; best = f; } }
    const half = 9.1 / 60 / 2 * 0.95;
    if (best && bd < half) {
      setMsg(msg, `Inside the ${best.name} field (${(bd * 60).toFixed(1)}′ from centre). Pinned.`, 'success');
      if (!F || F.meta.key !== best.key) await openField(best.key, true);
      setPin(r.ra, r.dec); return;
    }
    if (LIVE) { setMsg(msg, `Searching IRSA at ${r.ra.toFixed(4)} ${r.dec.toFixed(4)}…`, 'info'); return liveBuild({ ra: r.ra, dec: r.dec }); }
    if (LIVE_URL) {
      const u = new URL(LIVE_URL); u.searchParams.set('ra', r.ra.toFixed(5)); u.searchParams.set('dec', r.dec.toFixed(5));
      msg.className = 'form-text small text-warning';
      msg.innerHTML = `${r.ra.toFixed(4)} ${r.dec.toFixed(4)} is outside the pre-built fields. <a href="${u.toString()}" target="_blank" rel="noopener">Search it on the live site</a>.`;
      return;
    }
    setMsg(msg, `${r.ra.toFixed(4)} ${r.dec.toFixed(4)} is outside the pre-built fields. This demo is not connected to the Skytrace server, which runs live IRSA searches for any position.`, 'warning');
  }

  // ---------------------------------------------------------------- controls
  function renderCustomList() {
    const A = parseSet(S.A), B = parseSet(S.B);
    $('customList').innerHTML = VISITS.map((v) => `<div class="d-flex align-items-center gap-2"><span class="flex-grow-1">${v.label} <span class="text-secondary">${v.range} (${v.idx.length})</span></span>
      <label><input type="checkbox" data-set="A" data-k="${v.k}" ${A.has(v.k) ? 'checked' : ''}> A</label>
      <label><input type="checkbox" data-set="B" data-k="${v.k}" ${B.has(v.k) ? 'checked' : ''}> B</label></div>`).join('');
    $('customList').querySelectorAll('input').forEach((cb) => cb.onchange = () => {
      const set = parseSet(S[cb.dataset.set]); const k = +cb.dataset.k; cb.checked ? set.add(k) : set.delete(k);
      S[cb.dataset.set] = [...set].sort().join(','); rebuild();
    });
    $('scanEpoch').innerHTML = VISITS.map((v) => `<option value="${v.k}">${v.label}: ${v.range}</option>`).join('');
    $('scanEpoch').value = String(S.scan);
  }
  function syncControls() {
    suppressUrl = true;
    document.querySelectorAll('input[name=mode]').forEach((r) => r.checked = r.value === S.mode);
    $('modeHelp').textContent = MODE_HELP[S.mode];
    $('detSel').value = S.det; $('bandRange').value = S.band; $('tolRange').value = S.tol; $('winRange').value = S.win; $('spanRange').value = S.span;
    $('stretchSel').value = S.stretch; $('cmapSel').value = S.cmap; $('loRange').value = S.lo; $('hiRange').value = S.hi;
    $('fovSel').value = String(S.fov); if ($('fovSel').value !== String(S.fov)) { S.fov = 9.1; $('fovSel').value = '9.1'; }
    $('saToggle').checked = !!S.sa; $('saPmra').value = S.sapmra; $('saPmdec').value = S.sapmdec;
    $('flatToggle').checked = !!S.flat; $('invToggle').checked = !!S.inv; $('smoothToggle').checked = !!S.smooth; $('lockScale').checked = !!S.lock;
    $('diffToggle').checked = !!S.diff; $('diffRef').value = S.dref; $('diffRef').disabled = !S.diff; $('speedRange').value = S.speed;
    for (const [id, k] of [['ovTarget', 'target'], ['ovGaia', 'gaia'], ['ovWise', 'wise'], ['ovTmass', 'tmass'], ['ovFlags', 'flags'], ['ovMovers', 'movers'], ['ovCompass', 'compass']]) $(id).checked = ovOn(k);
    $('bandCtl').classList.toggle('d-none', S.mode !== 'band'); $('scanCtl').classList.toggle('d-none', S.mode !== 'scan'); $('customCtl').classList.toggle('d-none', S.mode !== 'custom');
    $('diffToggle').disabled = S.mode === 'custom';
    updateLabels();
    if (VISITS.length) { $('scanEpoch').value = String(S.scan); renderCustomList(); }
    suppressUrl = false;
  }
  function updateLabels() {
    const cc = CHANNELS[S.band - 1];
    $('bandLabel').textContent = cc ? `${S.band} (D${cc.det}, ${cc.wave.toFixed(3)} µm, R=${cc.R})` : String(S.band);
    $('tolLabel').textContent = S.tol; $('winLabel').textContent = S.win; $('spanLabel').textContent = S.span; $('loLabel').textContent = S.lo; $('hiLabel').textContent = S.hi;
  }
  function bind() {
    const rebuildOn = (id, key, conv = (v) => v, extra) => $(id).addEventListener('input', (e) => { S[key] = conv(e.target.value); if (extra) extra(); updateLabels(); rebuild(); });
    const rerenderOn = (id, key, conv = (v) => v) => $(id).addEventListener('input', (e) => { S[key] = conv(e.target.value); updateLabels(); LIMITS = null; RENDER_CACHE.clear(); renderFrame(); writeUrl(); });
    document.querySelectorAll('input[name=mode]').forEach((r) => r.addEventListener('change', () => { S.mode = r.value; S.frame = 0; if (S.mode === 'custom' && !S.A) S.A = '0'; syncControls(); rebuild(); }));
    rebuildOn('detSel', 'det'); rebuildOn('bandRange', 'band', Number); rebuildOn('tolRange', 'tol', Number);
    rebuildOn('winRange', 'win', Number, () => { groupVisits(); drawSpectrum(); renderProvenance(); });
    rebuildOn('spanRange', 'span', Number, () => { groupVisits(); drawSpectrum(); renderProvenance(); });
    $('scanEpoch').addEventListener('change', (e) => { S.scan = +e.target.value; S.frame = 0; rebuild(); });
    $('diffToggle').addEventListener('change', (e) => {
      S.diff = e.target.checked ? 1 : 0; $('diffRef').disabled = !S.diff;
      if (S.diff && S.cmap === 'gray') S.cmap = 'div'; else if (!S.diff && S.cmap === 'div') S.cmap = 'gray';
      $('cmapSel').value = S.cmap; rebuild();
    });
    $('diffRef').addEventListener('change', (e) => { S.dref = e.target.value; rebuild(); });
    rerenderOn('stretchSel', 'stretch'); rerenderOn('cmapSel', 'cmap'); rerenderOn('loRange', 'lo', Number); rerenderOn('hiRange', 'hi', Number);
    rerenderOn('fovSel', 'fov', Number);
    $('flatToggle').addEventListener('change', (e) => { S.flat = e.target.checked ? 1 : 0; rebuild(); });
    $('saToggle').addEventListener('change', (e) => { S.sa = e.target.checked ? 1 : 0; rebuild(); });
    for (const [id, k] of [['saPmra', 'sapmra'], ['saPmdec', 'sapmdec']]) $(id).addEventListener('change', (e) => { const v = parseFloat(e.target.value); S[k] = isFinite(v) ? v : 0; if (S.sa) rebuild(); else writeUrl(); });
    $('saTarget').onclick = () => { if (!F) return; S.sapmra = Math.round(F.meta.target.pmra || 0); S.sapmdec = Math.round(F.meta.target.pmdec || 0); $('saPmra').value = S.sapmra; $('saPmdec').value = S.sapmdec; if (S.sa) rebuild(); };
    $('invToggle').addEventListener('change', (e) => { S.inv = e.target.checked ? 1 : 0; RENDER_CACHE.clear(); renderFrame(); writeUrl(); });
    $('smoothToggle').addEventListener('change', (e) => { S.smooth = e.target.checked ? 1 : 0; renderFrame(); writeUrl(); });
    $('lockScale').addEventListener('change', (e) => { S.lock = e.target.checked ? 1 : 0; LIMITS = null; RENDER_CACHE.clear(); renderFrame(); writeUrl(); });
    for (const [id, k] of [['ovTarget', 'target'], ['ovGaia', 'gaia'], ['ovWise', 'wise'], ['ovTmass', 'tmass'], ['ovFlags', 'flags'], ['ovMovers', 'movers'], ['ovCompass', 'compass']]) {
      $(id).addEventListener('change', (e) => { const set = new Set(String(S.ov).split(',').filter(Boolean)); e.target.checked ? set.add(k) : set.delete(k); S.ov = [...set].join(','); drawOverlay(); writeUrl(); });
    }
    $('frameRange').addEventListener('input', (e) => { stopPlay(); S.frame = +e.target.value; renderFrame(); writeUrl(); });
    $('speedRange').addEventListener('input', (e) => { S.speed = +e.target.value; writeUrl(); });
    $('playBtn').onclick = () => (playTimer ? stopPlay() : startPlay());
    $('prevBtn').onclick = () => step(-1); $('nextBtn').onclick = () => step(1);
    $('goBtn').onclick = onGo; $('coordInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') onGo(); });
    $('ovCanvas').addEventListener('mousemove', onHover); $('ovCanvas').addEventListener('click', onClick);
    $('bandStrip').addEventListener('click', onBandClick); $('bandStrip').addEventListener('mousemove', onBandHover);
    $('copyLinkBtn').onclick = () => copyText(shareUrl(), $('shareMsg'), 'Link copied. Anyone opening it sees this exact view.');
    $('copyEmbedBtn').onclick = () => { const u = new URL(shareUrl(), location.href); u.searchParams.set('embed', '1'); copyText(`<iframe src="${u.toString()}" width="660" height="760" style="border:0" title="Skytrace SPHEREx viewer"></iframe>`, $('shareMsg'), 'Embed code copied.'); };
    $('copyCoordBtn').onclick = () => { if (!F) return; const [ra, dec] = F.meta.grid.crval; copyText(`${ra.toFixed(5)} ${dec.toFixed(5)}  (${raToHms(ra)} ${decToDms(dec)})`, $('shareMsg'), 'Centre coordinates copied.'); };
    $('specLog').addEventListener('change', (e) => { S.specLog = e.target.checked; drawSpectrum(); });
    $('specClean').addEventListener('change', (e) => { S.specClean = e.target.checked; drawSpectrum(); });
    document.querySelectorAll('button[data-bs-toggle="tab"]').forEach((b) => b.addEventListener('shown.bs.tab', () => { if (window.Plotly) { Plotly.Plots.resize('specPlot'); Plotly.Plots.resize('lcPlot'); } }));
    window.addEventListener('resize', () => { drawOverlay(); drawBandStrip(); });
    document.addEventListener('keydown', (e) => {
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement.tagName) && document.activeElement.type !== 'range') return;
      if (e.key === ' ') { e.preventDefault(); playTimer ? stopPlay() : startPlay(); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); step(1); } else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1); }
      else if (e.key === 'd' || e.key === 'D') { $('diffToggle').click(); }
    });
  }
  function step(d) { if (!FRAMES.length) return; stopPlay(); S.frame = (S.frame + d + FRAMES.length) % FRAMES.length; renderFrame(); writeUrl(); }
  function startPlay() {
    if (FRAMES.length < 2) return;
    $('playBtn').textContent = '❚❚ Pause';
    const tick = () => { S.frame = (S.frame + 1) % FRAMES.length; renderFrame(); playTimer = setTimeout(tick, S.speed); };
    playTimer = setTimeout(tick, S.speed);
  }
  function stopPlay() { if (playTimer) { clearTimeout(playTimer); playTimer = null; writeUrl(); } $('playBtn').textContent = '▶ Play'; }


  // ---------------------------------------------------------------- candidate report (plain text, only data already on screen)
  function nearestIn(list, ra, dec, mjd, epochOf, E) {
    let best = null;
    for (const st of list) {
      const [sra, sde] = apparent(st.ra, st.dec, st.pmra || 0, st.pmdec || 0, st.plx, epochOf, mjd, E);
      const d = angSepDeg(ra, dec, sra, sde) * 3600; if (!best || d < best.d) best = { st, d };
    }
    return best;
  }
  function buildReport() {
    if (!F || !FRAMES.length) return 'Open a field first.';
    const m = F.meta, fr = FRAMES[S.frame], ex = m.exposures, L = [];
    const [cra, cdec] = m.grid.crval;
    L.push('SKYTRACE CANDIDATE REPORT');
    L.push(`Generated: ${new Date().toISOString().slice(0, 19)}Z`);
    L.push(`View link: ${shareUrl()}`);
    L.push(`Field: ${m.name}  centre ${cra.toFixed(5)} ${cdec.toFixed(5)}  (${raToHms(cra)} ${decToDms(cdec)})`);
    if (PIN) {
      L.push(`Candidate position (pinned): ${PIN.ra.toFixed(5)} ${PIN.dec.toFixed(5)}  (${raToHms(PIN.ra)} ${decToDms(PIN.dec)})`);
      const [gx, gy] = world2pix(PIN.ra, PIN.dec), ix = Math.round(gx), iy = Math.round(gy);
      if (ix >= 0 && iy >= 0 && ix < F.np && iy < F.np) {
        const c = fr.cat[iy * F.np + ix];
        const fl = [c & CAT_SAT ? 'saturated' : '', c & CAT_ART ? 'artefact (ghost/streak/halo/crosstalk)' : '', c & CAT_BAD ? 'masked' : '', c & CAT_SRC ? 'SPHEREx SOURCE flag (a detected source is here)' : ''].filter(Boolean);
        L.push(`  Flags at that pixel in this frame: ${fl.length ? fl.join('; ') : 'none'}`);
      }
      const g = nearestIn(m.catalogs.gaia, PIN.ra, PIN.dec, fr.mjd, 57388.0, fr.earth);
      if (g) L.push(`  Nearest Gaia DR3: ${g.st.id}  ${g.d.toFixed(1)}" away  G=${g.st.g}  proper motion ${(Math.hypot(g.st.pmra, g.st.pmdec) / 1000).toFixed(3)}"/yr`);
      const w = nearestIn(m.catalogs.catwise, PIN.ra, PIN.dec, fr.mjd, 57170.0);
      if (w) L.push(`  Nearest CatWISE2020: ${w.st.id}  ${w.d.toFixed(1)}" away  W1=${w.st.w1} W2=${w.st.w2}  proper motion ${(Math.hypot(w.st.pmra, w.st.pmdec) / 1000).toFixed(3)}"/yr`);
      L.push('  (catalogue positions moved to this frame\'s date with their catalogued proper motion; SPHEREx pixels are 6.15")');
    } else L.push('Candidate position: none pinned. Click the image on the candidate, then reopen this report.');
    L.push('');
    L.push(`Frame shown: ${fr.label}  ${fr.sub || ''}`);
    L.push(`View: mode=${S.mode}, detectors=${S.det}${S.diff ? ', difference image' : ''}${S.sa ? `, shift-and-add ${S.sapmra}/${S.sapmdec} mas/yr` : ''}`);
    L.push('Visits in this field:');
    VISITS.forEach((v) => L.push(`  ${v.label}: ${v.range} (${v.idx.length} exposures)`));
    const mem = fr.members || [];
    L.push(`SPHEREx exposures in this frame (${mem.length}${mem.length > 25 ? ', first 25 listed' : ''}):`);
    mem.slice(0, 25).forEach((i) => { const e = ex[i]; L.push(`  ${e.obs_id}  D${e.det}  ${mjdToIso(e.mjd)} UTC  ${e.wave ? e.wave.toFixed(3) + ' um' : ''}  ${e.collection}`); });
    if (MOVERS.length) {
      L.push(`Automatic mover candidates (first vs last visit, >${MOVER_SIGMA} sigma):`);
      MOVERS.slice(0, 10).forEach((mv, k) => L.push(`  M${k + 1}  ${mv.ra.toFixed(5)} ${mv.dec.toFixed(5)}  ${mv.snr.toFixed(1)} sigma  ~${mv.pm.toFixed(1)}"/yr (rough)`));
    }
    L.push('');
    L.push('Notes: ' + ($('reportNotes').value.trim() || '(none)'));
    L.push('');
    L.push(`Data: NASA SPHEREx spectral images via NASA/IPAC IRSA (${(m.collections || []).join(', ')}); Gaia DR3 (ESA) and CatWISE2020 via IRSA.`);
    L.push('Made with Skytrace (NASA Space Apps Challenge 2026, "Planet X and SPHEREx").');
    return L.join('\n');
  }
  function bindReport() {
    const refresh = () => { $('reportText').value = buildReport(); };
    $('reportModal').addEventListener('show.bs.modal', refresh);
    $('reportNotes').addEventListener('input', refresh);
    $('reportCopy').onclick = () => copyText($('reportText').value, $('reportMsg'), 'Report copied.');
    $('reportDownload').onclick = () => {
      const blob = new Blob([$('reportText').value], { type: 'text/plain' }), a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = `skytrace-report-${F ? F.meta.key : 'field'}-${new Date().toISOString().slice(0, 10)}.txt`;
      document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
      setMsg($('reportMsg'), 'Downloaded.', 'success');
    };
  }

  // ---------------------------------------------------------------- boot
  async function boot() {
    bind(); bindReport();
    const clock = () => { const c = $('hudClock'); if (c) c.textContent = new Date().toISOString().slice(11, 19); };
    clock(); setInterval(clock, 1000);
    const logo = (window.SKYTRACE_LOGO || '').trim();
    if (logo) {
      const im = $('brandLogo');
      im.onload = () => { im.classList.remove('d-none'); $('brandSvg').classList.add('d-none'); document.querySelector('.st-nav .navbar-brand').classList.add('visually-hidden'); };
      im.srcset = logo.replace(/\.png$/, '@2x.png') + ' 2x'; im.src = logo;
    }
    if (window.SkyJourney) {
      SkyJourney.attach($('veilSky'), { big: true, labels: true });
      SkyJourney.attach($('skyMap'), { labels: false, onPick: (ra, dec) => {
        $('coordInput').value = `${ra.toFixed(4)} ${dec >= 0 ? '+' : ''}${dec.toFixed(4)}`; onGo();
      } });
    }
    const p = readUrl();
    if (p.get('embed') === '1') document.body.classList.add('embed');
    await loadIndex();
    if (!INDEX.fields.length && !LIVE) { veil(true, 'No data found. Run backend/build_static.py first.'); return; }
    let key = p.get('field');
    const ra = parseFloat(p.get('ra')), dec = parseFloat(p.get('dec'));
    if (!INDEX.fields.some((f) => f.key === key)) key = null;
    if (!key && isFinite(ra) && isFinite(dec)) {
      let best = null, bd = Infinity; for (const f of INDEX.fields) { const d = angSepDeg(ra, dec, f.ra, f.dec); if (d < bd) { bd = d; best = f; } }
      if (best && bd < 0.07) key = best.key;
      else if (LIVE) { await liveBuild({ ra, dec }); applyParams(p); syncControls(); rebuild(); return; }
      else setMsg($('coordMsg'), `Link points to ${ra.toFixed(4)} ${dec.toFixed(4)}, outside the pre-built fields; showing a demo field.`, 'warning');
    }
    key = key || (INDEX.fields[0] && INDEX.fields[0].key);
    await openField(key, true);
    applyParams(p); groupVisits(); syncControls(); rebuild(); drawSpectrum(); renderProvenance();
    const pra = parseFloat(p.get('pra')), pdec = parseFloat(p.get('pdec'));
    if (isFinite(pra) && isFinite(pdec)) setPin(pra, pdec);
    if (p.get('play') === '1') startPlay();
  }
  // Read-only hooks used by the automated browser tests (tests/ui_test.py)
  window.__skytrace = { buildReport, get F() { return F; }, get FRAMES() { return FRAMES; }, get VISITS() { return VISITS; }, S, world2pix, pix2world, parseInput, raToHms, decToDms, get MOVERS() { return MOVERS; } };
  boot();
})();
