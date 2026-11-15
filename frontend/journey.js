/* Skytrace sky journey: an all-sky map (Mollweide projection, equatorial coordinates) with a small
   rocket that travels along the great circle to each new search position and circles it while the
   archive search runs. Click the map to choose a position.
   Only real geometry is drawn: the RA/Dec grid, the ecliptic (obliquity 23.4392911 deg, IAU J2000) and
   the Galactic plane (north Galactic pole RA 192.85948, Dec 27.12825, l of the north celestial pole
   122.93192 deg, the J2000 values used by astropy). No decorative stars. */
(function () {
  'use strict';
  const D2R = Math.PI / 180, R2D = 180 / Math.PI;
  const REDUCED = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---------- Mollweide (RA increases to the left, RA 0h at the centre) ----------
  function moll(ra, dec) {
    let lam = ((ra + 180) % 360 + 360) % 360 - 180;    // -180..180, 0 at centre
    lam = -lam * D2R;                                   // east to the left
    const phi = dec * D2R;
    let th = phi;
    if (Math.abs(Math.abs(phi) - Math.PI / 2) < 1e-9) th = phi;
    else for (let i = 0; i < 30; i++) {
      const f = 2 * th + Math.sin(2 * th) - Math.PI * Math.sin(phi);
      const d = f / (2 + 2 * Math.cos(2 * th)); th -= d; if (Math.abs(d) < 1e-10) break;
    }
    return [(2 * Math.SQRT2 / Math.PI) * lam * Math.cos(th), Math.SQRT2 * Math.sin(th)];
  }
  function invMoll(x, y) {
    if (Math.abs(y) > Math.SQRT2) return null;
    const th = Math.asin(y / Math.SQRT2);
    const lam = Math.PI * x / (2 * Math.SQRT2 * Math.cos(th));
    if (Math.abs(lam) > Math.PI) return null;
    const phi = Math.asin((2 * th + Math.sin(2 * th)) / Math.PI);
    return [((-lam * R2D) % 360 + 360) % 360, phi * R2D];
  }
  // ---------- great circles ----------
  const vec = (ra, dec) => [Math.cos(dec * D2R) * Math.cos(ra * D2R), Math.cos(dec * D2R) * Math.sin(ra * D2R), Math.sin(dec * D2R)];
  const radec = (v) => [((Math.atan2(v[1], v[0]) * R2D) % 360 + 360) % 360, Math.asin(Math.max(-1, Math.min(1, v[2]))) * R2D];
  function slerp(a, b, t) {
    const va = vec(a[0], a[1]), vb = vec(b[0], b[1]);
    const dot = Math.max(-1, Math.min(1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2])), om = Math.acos(dot);
    if (om < 1e-9) return a.slice();
    const s = Math.sin(om), k1 = Math.sin((1 - t) * om) / s, k2 = Math.sin(t * om) / s;
    return radec([k1 * va[0] + k2 * vb[0], k1 * va[1] + k2 * vb[1], k1 * va[2] + k2 * vb[2]]);
  }
  const sepDeg = (a, b) => { const va = vec(a[0], a[1]), vb = vec(b[0], b[1]); return Math.acos(Math.max(-1, Math.min(1, va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2]))) * R2D; };
  // ecliptic (lon, lat=0) -> equatorial
  const EPS = 23.4392911 * D2R;
  function eclToEq(l) { const L = l * D2R; return radec([Math.cos(L), Math.sin(L) * Math.cos(EPS), Math.sin(L) * Math.sin(EPS)]); }
  // Galactic (l, b=0) -> ICRS
  const GP_RA = 192.85948 * D2R, GP_DEC = 27.12825 * D2R, L_NCP = 122.93192 * D2R;
  function galToEq(l) {
    const b = 0, L = l * D2R;
    const sd = Math.sin(b) * Math.sin(GP_DEC) + Math.cos(b) * Math.cos(GP_DEC) * Math.cos(L_NCP - L);
    const dec = Math.asin(sd);
    const y = Math.cos(b) * Math.sin(L_NCP - L), x = Math.sin(b) * Math.cos(GP_DEC) - Math.cos(b) * Math.sin(GP_DEC) * Math.cos(L_NCP - L);
    return [((GP_RA + Math.atan2(y, x)) * R2D % 360 + 360) % 360, dec * R2D];
  }

  // ---------- one map instance per canvas ----------
  function SkyMap(canvas, opts) {
    this.c = canvas; this.ctx = canvas.getContext('2d'); this.opts = opts || {};
    this.fields = []; this.here = null; this.rocket = null; this.anim = null; this.hover = null;
    this.trail = [];
    const ro = new ResizeObserver(() => this.resize()); ro.observe(canvas); this.resize();
    if (this.opts.onPick) {
      canvas.style.cursor = 'crosshair';
      canvas.addEventListener('mousemove', (e) => { this.hover = this.pick(e); this.draw(); });
      canvas.addEventListener('mouseleave', () => { this.hover = null; this.draw(); });
      canvas.addEventListener('click', (e) => { const p = this.pick(e); if (p) this.opts.onPick(p[0], p[1]); });
    }
  }
  SkyMap.prototype.resize = function () {
    const r = this.c.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    const w = Math.max(160, r.width), h = w / 2;
    this.c.style.height = h + 'px';
    this.c.width = Math.round(w * dpr); this.c.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0); this.W = w; this.H = h; this.draw();
  };
  SkyMap.prototype.xy = function (ra, dec) {
    const [mx, my] = moll(ra, dec), s = (this.W / 2 - 6) / (2 * Math.SQRT2);
    return [this.W / 2 + mx * s, this.H / 2 - my * s];
  };
  SkyMap.prototype.pick = function (e) {
    const r = this.c.getBoundingClientRect(), s = (this.W / 2 - 6) / (2 * Math.SQRT2);
    return invMoll((e.clientX - r.left - this.W / 2) / s, -(e.clientY - r.top - this.H / 2) / s);
  };
  SkyMap.prototype.line = function (pts, style, width, dash) {
    const g = this.ctx; g.save(); g.strokeStyle = style; g.lineWidth = width; g.setLineDash(dash || []);
    g.beginPath(); let prev = null;
    for (const p of pts) {
      const q = this.xy(p[0], p[1]);
      if (prev && Math.abs(q[0] - prev[0]) < this.W * 0.4) g.lineTo(q[0], q[1]); else g.moveTo(q[0], q[1]);
      prev = q;
    }
    g.stroke(); g.restore();
  };
  SkyMap.prototype.draw = function () {
    const g = this.ctx, W = this.W, H = this.H; if (!W) return;
    g.clearRect(0, 0, W, H);
    // sky disc
    g.save(); g.beginPath();
    for (let i = 0; i <= 72; i++) { const d = -90 + i * 2.5; const p = this.xy(180.0001, d); i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1]); }
    for (let i = 0; i <= 72; i++) { const d = 90 - i * 2.5; const p = this.xy(179.9999, d); g.lineTo(p[0], p[1]); }
    g.closePath(); const grd = g.createRadialGradient(W / 2, H / 2, 4, W / 2, H / 2, W / 2);
    grd.addColorStop(0, '#132036'); grd.addColorStop(1, '#070b13'); g.fillStyle = grd; g.fill();
    g.strokeStyle = 'rgba(110,168,254,.45)'; g.lineWidth = 1; g.stroke(); g.restore();
    // graticule
    for (let d = -60; d <= 60; d += 30) { const pts = []; for (let ra = 0; ra <= 360; ra += 3) pts.push([ra === 360 ? 359.999 : ra, d]); this.line(pts, 'rgba(173,181,189,.16)', 0.8); }
    for (let h = 0; h < 24; h += 2) { const pts = []; for (let d = -90; d <= 90; d += 3) pts.push([h * 15 + (h === 12 ? 0.001 : 0), d]); this.line(pts, 'rgba(173,181,189,.16)', 0.8); }
    // Galactic plane and ecliptic
    const gp = [], ec = []; for (let l = 0; l <= 360; l += 2) { gp.push(galToEq(l)); ec.push(eclToEq(l)); }
    this.line(gp, 'rgba(206,212,218,.35)', 6); this.line(gp, 'rgba(206,212,218,.45)', 1);
    this.line(ec, 'rgba(255,193,7,.75)', 1.2, [4, 3]);
    g.font = '10px system-ui, sans-serif';
    if (W > 260) {
      g.fillStyle = 'rgba(255,193,7,.9)'; const e1 = this.xy(...eclToEq(120)); g.fillText('ecliptic', e1[0] - 18, e1[1] - 6);
      g.fillStyle = 'rgba(206,212,218,.8)'; const g1 = this.xy(...galToEq(50)); g.fillText('Milky Way plane', g1[0] + 6, g1[1] + 3);
      g.fillStyle = 'rgba(173,181,189,.7)'; const l0 = this.xy(0.001, 0), l12 = this.xy(359.999, 0);
      g.fillText('0h', l0[0] + 2, l0[1] + 11); g.fillText('24h', 4, H / 2 + 11); g.fillText('12h', W - 22, H / 2 + 11);
    }
    // pre-built fields
    for (const f of this.fields) {
      // challenge fields: blue diamonds with their name; the user's own searches: small grey diamonds, no label
      const user = f.user !== undefined ? f.user : /^RA\s/.test(f.name), p = this.xy(f.ra, f.dec), r = user ? 2.5 : 3.5;
      g.fillStyle = user ? 'rgba(173,181,189,.8)' : 'rgba(110,168,254,.95)';
      g.beginPath(); g.moveTo(p[0], p[1] - r); g.lineTo(p[0] + r, p[1]); g.lineTo(p[0], p[1] + r); g.lineTo(p[0] - r, p[1]); g.closePath(); g.fill();
      if (W > 320 && this.opts.labels && !user) { g.fillStyle = 'rgba(206,212,218,.75)'; g.fillText(f.name.split(' ')[0], p[0] + 5, p[1] - 4); }
    }
    // trail
    if (this.trail.length > 1) this.line(this.trail, 'rgba(255,214,102,.8)', 1.2, [2, 3]);
    // current target
    if (this.here) {
      const p = this.xy(this.here[0], this.here[1]), t = performance.now() / 1000;
      const r = REDUCED ? 6 : 5 + 2.5 * (1 + Math.sin(t * 3)) / 2;
      g.strokeStyle = '#ffc107'; g.lineWidth = 1.4; g.beginPath(); g.arc(p[0], p[1], r, 0, 2 * Math.PI); g.stroke();
      g.beginPath(); g.moveTo(p[0] - 10, p[1]); g.lineTo(p[0] - 6, p[1]); g.moveTo(p[0] + 6, p[1]); g.lineTo(p[0] + 10, p[1]);
      g.moveTo(p[0], p[1] - 10); g.lineTo(p[0], p[1] - 6); g.moveTo(p[0], p[1] + 6); g.lineTo(p[0], p[1] + 10); g.stroke();
    }
    if (this.rocket) drawRocket(g, this.xy(this.rocket.ra, this.rocket.dec), this.rocket.ang, this.rocket.scale || 1, this.rocket.flame);
    // hover readout
    if (this.hover) {
      const [ra, dec] = this.hover, txt = `RA ${(ra / 15).toFixed(2)}h  Dec ${dec >= 0 ? '+' : ''}${dec.toFixed(1)}°  click to search`;
      g.fillStyle = 'rgba(11,15,23,.85)'; g.fillRect(4, H - 18, g.measureText(txt).width + 10, 15);
      g.fillStyle = '#e9ecef'; g.fillText(txt, 9, H - 7);
    }
  };

  // small toy rocket, nose pointing along +x before rotation
  function drawRocket(g, p, ang, s, flame) {
    g.save(); g.translate(p[0], p[1]); g.rotate(ang); g.scale(s, s);
    if (flame) {
      const f = 6 + Math.random() * 5;
      const gr = g.createLinearGradient(-8, 0, -8 - f, 0); gr.addColorStop(0, 'rgba(255,214,102,.95)'); gr.addColorStop(1, 'rgba(253,126,20,0)');
      g.fillStyle = gr; g.beginPath(); g.moveTo(-7, -2.6); g.lineTo(-8 - f, 0); g.lineTo(-7, 2.6); g.closePath(); g.fill();
    }
    g.fillStyle = '#dc3545'; // fins
    g.beginPath(); g.moveTo(-3, -3); g.lineTo(-8, -7); g.lineTo(-7, -2.5); g.closePath(); g.fill();
    g.beginPath(); g.moveTo(-3, 3); g.lineTo(-8, 7); g.lineTo(-7, 2.5); g.closePath(); g.fill();
    g.fillStyle = '#f8f9fa'; // body
    g.beginPath(); g.moveTo(9, 0); g.quadraticCurveTo(5, -4, -7, -3); g.lineTo(-7, 3); g.quadraticCurveTo(5, 4, 9, 0); g.closePath(); g.fill();
    g.fillStyle = '#dc3545'; g.beginPath(); g.moveTo(9, 0); g.quadraticCurveTo(7, -2.4, 5, -3.1); g.lineTo(5, 3.1); g.quadraticCurveTo(7, 2.4, 9, 0); g.fill();
    g.fillStyle = '#6ea8fe'; g.beginPath(); g.arc(1.5, 0, 1.6, 0, 2 * Math.PI); g.fill();
    g.restore();
  }

  // ---------- journey controller shared by the card map and the loading-veil map ----------
  const maps = []; let cur = null, raf = null, mode = 'idle', flight = null, orbitT0 = 0;
  function heading(m, a, b) { const p = m.xy(a[0], a[1]), q = m.xy(b[0], b[1]); return Math.atan2(q[1] - p[1], q[0] - p[0]); }
  function tick() {
    const now = performance.now();
    for (const m of maps) {
      if (mode === 'fly' && flight) {
        const t = Math.min(1, (now - flight.t0) / flight.dur), e = t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
        const pos = slerp(flight.from, flight.to, e), ahead = slerp(flight.from, flight.to, Math.min(1, e + 0.02));
        m.trail = []; for (let k = 0; k <= 40; k++) { const u = e * k / 40; m.trail.push(slerp(flight.from, flight.to, u)); }
        let ang = heading(m, pos, ahead); const pp = m.xy(pos[0], pos[1]), pa = m.xy(ahead[0], ahead[1]);
        if (Math.abs(pa[0] - pp[0]) > m.W * 0.4) ang = m.rocket ? m.rocket.ang : 0;
        m.rocket = { ra: pos[0], dec: pos[1], ang, flame: true, scale: m.opts.big ? 1.6 : 1 };
        m.here = flight.to;
      } else if (mode === 'orbit' && cur) {
        const t = (now - orbitT0) / 1000, r = m.opts.big ? 3.2 : 2.4, a = t * 1.6;
        const decR = cur[1] + r * Math.sin(a), raR = cur[0] + r * Math.cos(a) / Math.max(0.2, Math.cos(cur[1] * D2R));
        m.rocket = { ra: raR, dec: Math.max(-89, Math.min(89, decR)), ang: -a - Math.PI / 2 * 0 + Math.PI, flame: true, scale: m.opts.big ? 1.6 : 1 };
        // tangent direction in screen space
        const nxt = m.xy(cur[0] + r * Math.cos(a + .05) / Math.max(0.2, Math.cos(cur[1] * D2R)), cur[1] + r * Math.sin(a + .05)), now2 = m.xy(m.rocket.ra, m.rocket.dec);
        m.rocket.ang = Math.atan2(nxt[1] - now2[1], nxt[0] - now2[0]);
        m.here = cur;
      } else if (cur) {
        m.here = cur; m.rocket = { ra: cur[0], dec: cur[1] + (m.opts.big ? 4.5 : 3.5), ang: -Math.PI / 2, flame: false, scale: m.opts.big ? 1.6 : 1 };
      }
      m.draw();
    }
    if (mode === 'fly' && flight && now - flight.t0 >= flight.dur) {
      const done = flight.resolve; cur = flight.to; mode = flight.thenOrbit ? 'orbit' : 'idle'; orbitT0 = now; flight = null;
      for (const m of maps) m.trail = [];
      if (mode === 'idle') { for (const m of maps) { m.rocket = { ra: cur[0], dec: cur[1] + (m.opts.big ? 4.5 : 3.5), ang: -Math.PI / 2, flame: false, scale: m.opts.big ? 1.6 : 1 }; m.draw(); } }
      done();
    }
    raf = mode !== 'idle' ? requestAnimationFrame(tick) : null;   // idle: static map, no CPU use
  }
  function kick() { if (!raf) raf = requestAnimationFrame(tick); }

  window.SkyJourney = {
    attach(canvas, opts) { const m = new SkyMap(canvas, opts); maps.push(m); kick(); return m; },
    setFields(fields) { for (const m of maps) { m.fields = fields || []; m.draw(); } },
    /** Fly to (ra, dec). If searching=true the rocket keeps circling until arrive() is called. */
    /** Returns a promise that resolves when the rocket lands. */
    travel(ra, dec, searching) {
      const to = [ra, dec];
      if (flight && sepDeg(flight.to, to) < 0.05) { flight.thenOrbit = !!searching; return flight.promise; }
      if (!cur || REDUCED || sepDeg(cur, to) < 0.05) {
        cur = to; mode = searching && !REDUCED ? 'orbit' : 'idle'; orbitT0 = performance.now(); flight = null;
        for (const m of maps) { m.here = cur; m.rocket = { ra: cur[0], dec: cur[1] + (m.opts.big ? 4.5 : 3.5), ang: -Math.PI / 2, flame: false, scale: m.opts.big ? 1.6 : 1 }; m.draw(); }
        kick(); return Promise.resolve();
      }
      const dur = Math.min(1800, 700 + sepDeg(cur, to) * 6);
      let resolve; const promise = new Promise((r) => { resolve = r; });
      flight = { from: cur, to, t0: performance.now(), dur, thenOrbit: !!searching, promise, resolve }; mode = 'fly'; kick();
      return promise;
    },
    arrive() { if (flight) flight.thenOrbit = false; if (mode === 'orbit') { mode = 'idle'; for (const m of maps) { m.rocket = { ra: cur[0], dec: cur[1] + (m.opts.big ? 4.5 : 3.5), ang: -Math.PI / 2, flame: false, scale: m.opts.big ? 1.6 : 1 }; m.draw(); } } },
    get position() { return cur; },
    _moll: moll, _invMoll: invMoll, _galToEq: galToEq, _eclToEq: eclToEq
  };
})();
