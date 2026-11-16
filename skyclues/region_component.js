// SkyClues · region selector.
//
// One region (centre RA/Dec + field-of-view diameter), three ways to change it in the same place:
// the object search, the coordinate fields and the Atlas (Aladin Lite). Everything on screen is
// updated here, in the browser, at interaction speed; Python only hears about a change once the
// interaction settles (debounced), so dragging the map never reruns the application per frame.
//
// Loop prevention: Python owns `data.rev`. It increases only when the region was changed outside
// this component (name resolved, saved sequence opened, link restored). The map is recentred only
// then; the echo of our own updates comes back with the same `rev` and is ignored.
export default function (c) {
  const root = c.parentElement;
  const $ = (sel) => root.querySelector(sel);
  let S = root.__skyRegion;
  // Streamlit can replace component HTML after a code update while retaining the root.
  // The old Aladin instance then belongs to a detached map: rebuild instead of painting it.
  if (S && S.mapElement !== $('.rg-map')) {
    clearTimeout(S.flushTimer); clearTimeout(S.queryTimer); clearTimeout(S.nameTick); clearTimeout(S.unlock);
    if (S.resize) S.resize.disconnect();
    S = null;
  }
  const first = !S;
  if (first) S = root.__skyRegion = { rev: null, cur: null, lock: false, gaiaKey: null, active: -1, items: [], mapElement: $('.rg-map') };
  S.api = c;
  S.data = c.data;
  const D = () => S.data;

  // ---------------------------------------------------------------- numbers and formats
  const reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const normRa = (ra) => { const r = ((ra % 360) + 360) % 360; return r >= 359.99999995 ? 0 : r; };
  const r7 = (v) => Math.round(v * 1e7) / 1e7;
  const fovDeg = (arcmin) => Math.round((arcmin / 60) * 1e4) / 1e4;
  const fmtRa = (v) => normRa(v).toFixed(6);
  const fmtDec = (v) => (v < 0 ? '−' : '+') + Math.abs(v).toFixed(6);
  const fmtArcmin = (deg) => (Math.round(deg * 600) / 10).toFixed(1);
  const pad = (n, w) => String(n).padStart(w, '0');
  function sexaRa(ra) {
    let t = Math.round(normRa(ra) / 15 * 36000);           // tenths of a second of time
    if (t >= 24 * 36000) t = 0;
    const h = Math.floor(t / 36000), m = Math.floor((t % 36000) / 600), s = (t % 600) / 10;
    return `${pad(h, 2)}h ${pad(m, 2)}m ${s.toFixed(1).padStart(4, '0')}s`;
  }
  function sexaDec(dec) {
    const t = Math.round(Math.abs(dec) * 3600);
    const d = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
    return `${dec < 0 ? '−' : '+'}${pad(d, 2)}° ${pad(m, 2)}′ ${pad(s, 2)}″`;
  }
  const clean = (t) => String(t).trim().replace(/[−–]/g, '-').replace(',', '.');
  const DECIMAL = /^[+-]?(\d+\.?\d*|\.\d+)$/;
  function parseRa(text) {
    const t = clean(text);
    if (DECIMAL.test(t)) { const v = Number(t); return v >= 0 && v < 360 ? v : NaN; }
    const m = t.match(/^(\d{1,2})\s*[h:\s]\s*(\d{1,2})\s*[m:\s]\s*(\d{1,2}(?:\.\d*)?)\s*s?$/i);
    if (!m) return NaN;
    const [h, mi, s] = [Number(m[1]), Number(m[2]), Number(m[3])];
    return h < 24 && mi < 60 && s < 60 ? (h + mi / 60 + s / 3600) * 15 : NaN;
  }
  function parseDec(text) {
    const t = clean(text).replace(/°/g, 'd').replace(/[′']/g, 'm').replace(/[″"]/g, 's');
    if (DECIMAL.test(t)) { const v = Number(t); return v >= -90 && v <= 90 ? v : NaN; }
    const m = t.match(/^([+-]?)(\d{1,2})\s*[d:\s]\s*(\d{1,2})\s*[m:\s]\s*(\d{1,2}(?:\.\d*)?)\s*s?$/i);
    if (!m) return NaN;
    const [d, mi, s] = [Number(m[2]), Number(m[3]), Number(m[4])];
    if (mi >= 60 || s >= 60) return NaN;
    const v = (m[1] === '-' ? -1 : 1) * (d + mi / 60 + s / 3600);
    return v >= -90 && v <= 90 ? v : NaN;
  }
  function sepArcsec(a, b) {
    const k = Math.PI / 180, p1 = a.dec * k, p2 = b.dec * k, dl = (a.ra - b.ra) * k;
    const h = Math.sin((p1 - p2) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * Math.asin(Math.min(1, Math.sqrt(h))) / k * 3600;
  }
  const keyOf = (r) => JSON.stringify([r7(normRa(r.ra)), r7(r.dec), r.fov]);

  // ---------------------------------------------------------------- talking to Python
  function flush(now) {
    clearTimeout(S.flushTimer);
    const send = () => {
      const key = keyOf(S.cur);
      if (key === S.sentKey) return;
      S.sentKey = key;
      S.api.setStateValue('region', { ra: r7(normRa(S.cur.ra)), dec: r7(S.cur.dec), fov: S.cur.fov });
    };
    if (now) send(); else S.flushTimer = setTimeout(send, 320);
  }

  // ---------------------------------------------------------------- the readouts
  function paint(skip) {
    const { ra, dec, fov } = S.cur, ra_in = $('#rg-ra'), dec_in = $('#rg-dec');
    if (skip !== 'ra' && document.activeElement !== ra_in) { ra_in.value = fmtRa(ra); mark(ra_in, false); }
    if (skip !== 'dec' && document.activeElement !== dec_in) { dec_in.value = fmtDec(dec); mark(dec_in, false); }
    $('.rg-sexa-ra').textContent = sexaRa(ra);
    $('.rg-sexa-dec').textContent = sexaDec(dec);
    const am = fov * 60;
    if (skip !== 'fov') $('#rg-fov').value = String(am);
    if (skip !== 'fovn' && document.activeElement !== $('#rg-fovn')) { $('#rg-fovn').value = fmtArcmin(fov); mark($('#rg-fovn'), false); }
    $('#rg-fov').style.setProperty('--fill', `${((am - D().fov_min * 60) / ((D().fov_max - D().fov_min) * 60)) * 100}%`);
    const sx = Math.round(fov * 3600 / D().spherex_px), cube = Math.round(fov * 3600 / D().cube_px);
    $('.rg-fovhint').textContent = D().level === 'simple'
      ? 'Slide to cover more or less sky. The orange circle on the map marks the area you are going to explore.'
      : `${fmtArcmin(fov)}′ = ${fov.toFixed(4)}° in diameter · ≈ ${sx} SPHEREx px (${D().spherex_px}″) · ≈ ${cube} cube px (${D().cube_px}″)`;
    chip();
    identity();
  }
  function chip() {
    let t = `${D().level === 'simple' ? 'Area' : 'Field'} ${fmtArcmin(S.cur.fov)}′`;
    if (S.aladin) {
      const v = S.aladin.getFoV()[0];
      t += ` · view ${v >= 1 ? v.toFixed(2) + '°' : (v * 60).toFixed(1) + '′'}`;
    }
    $('.rg-chip').textContent = t;
  }
  function mark(input, bad, msg) {
    input.setAttribute('aria-invalid', bad ? 'true' : 'false');
    const m = input.closest('.rg-field').querySelector('.rg-err');
    if (m) m.textContent = bad ? msg : '';
  }
  // The name belongs to the region only while the centre is still on the object.
  function identity() {
    const o = D().object, line = $('.rg-object'), notes = $('.rg-notes');
    const on = o && o.anchor && sepArcsec(S.cur, { ra: o.anchor[0], dec: o.anchor[1] }) <= D().anchor_arcsec;
    line.classList.toggle('rg-err-text', false);
    line.dataset.loading = String(!!S.resolving);
    if (S.resolving) {
      const seconds = Math.floor((Date.now() - (S.searchStarted || Date.now())) / 1000);
      line.textContent = `Searching for “${S.resolving}”…` + (seconds ? ` · ${seconds} s` : '');
      notes.replaceChildren();
      if (seconds >= 15) {const p = document.createElement('p'); p.textContent = 'The catalogue is taking a while to respond. The map is still available.'; notes.append(p);}
      clearTimeout(S.nameTick);
      S.nameTick = setTimeout(() => {if (root.isConnected !== false && S.resolving) identity();}, 1000);
      return;
    }
    clearTimeout(S.nameTick);
    if (D().notice) { line.textContent = D().notice; line.classList.add('rg-err-text'); notes.replaceChildren(); return; }
    if (on) {
      line.innerHTML = '';
      const detail = D().level === 'simple' ? o.short_detail : o.detail;
      const b = document.createElement('b'); b.textContent = o.name; line.append(b, document.createTextNode(detail ? ` · ${detail}` : ''));
      const visibleNotes = D().level === 'simple' ? o.short_notes : o.notes;
      notes.replaceChildren(...(visibleNotes || []).map((n) => { const p = document.createElement('p'); p.textContent = n; return p; }));
    } else {
      line.textContent = o && o.name ? `Free region (the centre is no longer over ${o.name}).` : 'Free region, defined by its coordinates.';
      notes.replaceChildren();
    }
  }

  // ---------------------------------------------------------------- the map
  function drawCircle(radius) {
    if (!S.aladin) return;
    const r = radius === undefined ? S.cur.fov / 2 : radius;
    S.halo.removeAll(); S.ring.removeAll();
    S.halo.add(S.A.circle(S.cur.ra, S.cur.dec, r));
    S.ring.add(S.A.circle(S.cur.ra, S.cur.dec, r));
    S.drawn = r;
  }
  function tweenCircle() {
    cancelAnimationFrame(S.raf);
    const from = S.drawn === undefined ? S.cur.fov / 2 : S.drawn, to = S.cur.fov / 2;
    if (!S.aladin || reduced() || Math.abs(from - to) < 1e-9) { drawCircle(to); return; }
    const t0 = performance.now(), dur = 160;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - (1 - k) ** 3;
      drawCircle(from + (to - from) * e);
      if (k < 1) S.raf = requestAnimationFrame(step);
    };
    S.raf = requestAnimationFrame(step);
  }
  // Keep the whole field visible: only zooms when the circle no longer fits (never to "follow" the FOV).
  function keepVisible() {
    if (!S.aladin) return;
    const [vx, vy] = S.aladin.getFoV(), min = Math.min(vx, vy || vx);
    if (S.cur.fov > min * 0.92) zoomTo(S.cur.fov * 1.6);
  }
  function zoomTo(fov) {
    if (!reduced() && typeof S.aladin.zoomToFoV === 'function') S.aladin.zoomToFoV(fov, 0.2);
    else S.aladin.setFoV(fov);
  }
  function frame() { if (S.aladin) zoomTo(Math.max(S.cur.fov * 2.5, 0.05)); }
  function goto(ra, dec, animate) {
    if (!S.aladin) return;
    // A new coordinate edit can arrive before the previous 200 ms animation ends.
    // Stop it even for a distant, instantaneous move, so it cannot restore an old centre.
    clearTimeout(S.unlock);
    if (typeof S.aladin.stopAnimation === 'function') S.aladin.stopAnimation();
    const move = S.moveId = (S.moveId || 0) + 1;
    const [vra, vdec] = S.aladin.getRaDec();
    const far = sepArcsec({ ra: vra, dec: vdec }, { ra, dec }) / 3600 > 6 * S.aladin.getFoV()[0];
    const done = () => { if (move === S.moveId) { S.lock = false; drawCircle(); chip(); } };
    const finish = () => { if (move === S.moveId) { S.aladin.gotoRaDec(ra, dec); done(); } };
    S.lock = true;
    drawCircle();
    if (animate && !reduced() && !far && typeof S.aladin.animateToRaDec === 'function') {
      S.aladin.animateToRaDec(ra, dec, 0.2, finish);
      S.unlock = setTimeout(() => { if (S.lock) finish(); }, 600);   // safety net
    } else {
      S.aladin.gotoRaDec(ra, dec);
      done();
    }
  }
  function onMapMove() {
    if (S.lock || !S.aladin) return;
    const [ra0, dec] = S.aladin.getRaDec(), ra = normRa(ra0);
    if (sepArcsec({ ra, dec }, S.cur) < 0.001) { chip(); return; }      // redraw nudge, not a move
    S.cur = { ...S.cur, ra, dec };
    drawCircle(); paint(); gaiaStatus(); flush();
  }

  // ---------------------------------------------------------------- changes made in the fields
  function setCentre(ra, dec, skip) {
    // Blurring an unchanged input must not lock the map while the user starts dragging it.
    if (sepArcsec(S.cur, {ra: normRa(ra), dec}) < 1e-6) { paint(skip); flush(); return; }
    S.cur = { ...S.cur, ra: normRa(ra), dec };
    paint(skip); goto(S.cur.ra, S.cur.dec, true); gaiaStatus(); flush();
  }
  function setFov(arcmin, skip) {
    const lo = D().fov_min * 60, hi = D().fov_max * 60;
    S.cur = { ...S.cur, fov: fovDeg(Math.min(hi, Math.max(lo, arcmin))) };
    paint(skip); tweenCircle(); keepVisible(); gaiaStatus(); flush();
  }
  function coordField(input, parse, which, msg) {
    let timer;
    const apply = (strict) => {
      clearTimeout(timer);
      const v = parse(input.value);
      if (Number.isNaN(v)) { if (strict && input.value.trim() !== '') mark(input, true, msg); return; }
      mark(input, false);
      const other = which === 'ra' ? S.cur.dec : S.cur.ra;
      if (which === 'ra') setCentre(v, other, 'ra'); else setCentre(other, v, 'dec');
    };
    input.addEventListener('input', () => {          // a value still being typed must not move the map yet
      clearTimeout(timer); mark(input, false);
      timer = setTimeout(() => apply(true), 750);
    });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); apply(true); } });
    input.addEventListener('blur', () => { apply(true); if (input.getAttribute('aria-invalid') !== 'true') paint(); });
  }

  // ---------------------------------------------------------------- object search
  const norm = (s) => String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    .replace(/\b(m|ngc|ic|hd|hip)\s*(?=\d)/g, '$1 ').replace(/\s+/g, ' ').trim();
  const canSuggest = q => q.length >= 3 || /^(m|messier|ngc|ic|hd|hip)\s*\d*$/.test(q);
  function suggestions() {
    const input = $('#rg-q'), list = $('#rg-list'), q = norm(input.value);
    const searchStatus = $('.rg-search-status');
    searchStatus.hidden = true;
    S.items = [];
    if (q && document.activeElement === input && S.suggesting !== false) {
      const local = D().local.filter((x) => [x.id, ...x.aliases].some((a) => norm(a).includes(q))).slice(0, 6)
        .map(x => ({...x, label: [x.id, ...x.aliases].find(a => norm(a).startsWith(q)) || x.id}));
      const current = norm(D().remote_query || '') === q;
      const remote = current ? D().remote : [];
      const seen = new Set();
      for (const it of [...remote, ...local]) { if (!seen.has(norm(it.id))) { seen.add(norm(it.id)); S.items.push(it); } }
      S.items = S.items.slice(0, 12);
      if (canSuggest(q) && !S.resolving) {
        const loading = !current || D().search_state === 'loading';
        searchStatus.dataset.loading = String(loading);
        searchStatus.textContent = loading ? 'Searching the catalogues for suggestions…'
          : D().search_message || (S.items.length ? 'Refine the name to see more matches.' : 'No suggestions. Press Enter to search for the full name.');
        searchStatus.hidden = false;
      }
    }
    list.replaceChildren(...S.items.map((it, i) => {
      const li = document.createElement('li');
      li.id = `rg-opt-${i}`; li.setAttribute('role', 'option'); li.setAttribute('aria-selected', i === S.active ? 'true' : 'false');
      const a = document.createElement('span'); a.className = 'rg-opt-name'; a.textContent = it.label || it.id;
      const b = document.createElement('span'); b.className = 'rg-opt-meta';
      const alias = [...new Set((it.aliases || []).map(x => x.replace(/\s+/g, ' ').trim()))]
        .filter(x => norm(x) !== norm(it.label || it.id)).slice(0, 3).join(', ');
      b.textContent = [it.type, alias].filter(Boolean).join(' · ');
      li.append(a, b);
      li.addEventListener('mousedown', (e) => { e.preventDefault(); pick(it.id, it.label); });
      return li;
    }));
    list.hidden = S.items.length === 0;
    input.setAttribute('aria-expanded', String(!list.hidden));
    if (S.active >= 0 && S.active < S.items.length) input.setAttribute('aria-activedescendant', `rg-opt-${S.active}`);
    else input.removeAttribute('aria-activedescendant');
  }
  function pick(name, label) {
    const text = String(name).trim();
    if (!text) return;
    clearTimeout(S.queryTimer);
    $('#rg-q').value = label || text; S.active = -1; S.resolving = label || text; S.searchStarted = Date.now(); S.suggesting = false;
    $('.rg-search-status').hidden = true;
    $('#rg-list').hidden = true; $('#rg-q').setAttribute('aria-expanded', 'false');
    identity();
    S.api.setTriggerValue('pick', { name: text, n: Date.now() });
  }

  // ---------------------------------------------------------------- layers and overlays
  function layerInfo(id) {
    const L = D().layers.find((l) => l.id === id) || D().layers[0];
    $('.rg-layerinfo').textContent = D().level === 'simple'
      ? `Reference map: ${L.label}, from another mission and epoch. These are not SPHEREx data: those open in Time and Spectrum.`
      : `${L.mission} · ${L.product} · ${L.bands} · ${L.epoch}. Context map served by NASA/IPAC IRSA; not SPHEREx data.`;
    return L;
  }
  function setLayer(id) {
    const L = layerInfo(id);
    $('#rg-layer').value = L.id;
    if (!S.aladin) return;
    try {
      S.aladin.setImageSurvey(S.aladin.newImageSurvey(L.url, { name: L.label, imgFormat: L.format }));
    } catch (e) { status(`No se pudo cargar ${L.label}: ${e.message || e}`, true); }
  }
  function status(text, bad) { const el = $('.rg-status'); $('.rg-map-message').textContent = text || ''; el.classList.toggle('rg-err-text', !!bad); el.dataset.loading = String(!!text && !bad); el.hidden = !text; }
  function overlays() {
    if (!S.aladin) return;
    const o = D().object, mk = o && o.anchor ? JSON.stringify([o.name, o.anchor]) : null;
    if (mk !== S.markerKey) {
      S.markerKey = mk; S.marker.removeAll();
      if (o && o.anchor) S.marker.addSources([o.gaia_source_id
        ? S.A.source(o.anchor[0], o.anchor[1], {name: o.name})
        : S.A.marker(o.anchor[0], o.anchor[1], { popupTitle: o.name, popupDesc: o.marker_note || '' })]);
    }
    if (S.gaiaKey !== D().gaia_key) {
      S.gaiaKey = D().gaia_key; S.gaia.removeAll();
      if (D().gaia && D().gaia.length) S.gaia.addSources(D().gaia.map((s) => S.A.source(s.ra, s.dec, s)));
    }
    $('.rg-gaiainfo').textContent = D().gaia_note || '';
    constellationVisibility();
    gaiaStatus();
  }

  function gaiaCurrent() {
    const r = D().gaia_region;
    return r && Math.abs(S.cur.fov - r.fov) < 1e-9 && sepArcsec(S.cur, r) < 0.002;
  }
  function gaiaStatus() {
    const on = $('#rg-gaia').checked, current = gaiaCurrent();
    if (S.gaia) S.gaia[on && current && D().gaia_status === 'ready' ? 'show' : 'hide']();
    const el = $('.rg-gaia-status');
    // Stale responses must never paint over a newer local drag, even before Python hears it.
    const state = on && current ? D().gaia_status : 'off';
    const empty = state === 'ready' && !(D().gaia || []).length;
    el.hidden = !(state === 'loading' || state === 'error' || empty);
    el.dataset.state = state;
    $('.rg-gaia-message').textContent = state === 'loading' ? 'Consultando fuentes Gaia DR3…'
      : state === 'error' ? 'Gaia DR3 not available.' : empty ? 'No Gaia DR3 sources were found in this field.' : '';
    $('.rg-gaia-retry').hidden = state !== 'error';
    $('.rg-gaiainfo').textContent = on && current ? (D().level === 'simple' ? D().gaia_note_simple : D().gaia_note) || '' : '';
  }
  function pickGaia(source) {
    if (!gaiaCurrent() || !$('#rg-gaia').checked || D().gaia_status !== 'ready') return;
    const sid = source.data.source_id;
    if (typeof sid !== 'string') return; // Gaia's 64-bit identifiers must never pass through Number.
    clearTimeout(S.flushTimer); clearTimeout(S.queryTimer);
    S.cur = {...S.cur, ra: source.ra, dec: source.dec}; S.sentKey = keyOf(S.cur);
    $('#rg-q').value = `Gaia DR3 ${sid}`; $('#rg-list').hidden = true;
    $('#rg-q').setAttribute('aria-expanded', 'false'); S.active = -1;
    S.resolving = `Gaia DR3 ${sid}`; S.searchStarted = Date.now();
    paint(); goto(source.ra, source.dec, false);
    S.api.setTriggerValue('gaia_pick', {source_id: sid, key: D().gaia_key, fov: S.cur.fov, n: Date.now()});
  }

  function constellationVisibility() {
    if (!S.constLines) return;
    const on = !!D().constellations_on, wide = S.aladin.getFoV()[0] >= 3;
    S.constLines[on && wide ? 'show' : 'hide']();
    S.constNames[on && wide ? 'show' : 'hide']();
    $('#rg-constellations').checked = on;
    $('.rg-constinfo').textContent = on ? (wide
      ? (D().level === 'simple' ? 'Constellations to help you orient yourself; the orange circle still marks your field.' : 'Traditional figures of 88 constellations · not IAU boundaries. The orange circle remains the scientific field.')
      : 'Constellations hidden in small fields. Press Orientation to enlarge only the view.') : '';
  }

  // ---------------------------------------------------------------- applying data from Python
  function apply() {
    const d = D();
    root.querySelector('.sc-region').dataset.level = d.level;
    if (S.rev !== d.rev) {
      const mounted = S.rev !== null;
      S.rev = d.rev; S.resolving = null;
      S.cur = { ra: normRa(d.region.ra), dec: d.region.dec, fov: d.region.fov };
      S.sentKey = keyOf(S.cur);
      clearTimeout(S.flushTimer);
      if (document.activeElement !== $('#rg-q')) $('#rg-q').value = d.object ? d.object.name : '';
      else if (d.object) $('#rg-q').value = d.object.name;
      if (S.aladin) { goto(S.cur.ra, S.cur.dec, mounted); if (mounted) frame(); }
    } else if (S.cur && Math.abs(S.cur.fov - d.region.fov) < 1e-4 && keyOf(S.cur) === S.sentKey) {
      S.cur.fov = d.region.fov; S.sentKey = keyOf(S.cur);     // adopt Python's rounding of the same field
    }
    if (d.notice || (d.pick_done && d.pick_done === S.pickSeen)) S.resolving = null;
    S.pickSeen = d.pick_done;
    $('#rg-gaia').checked = !!d.gaia_on;
    layerInfo($('#rg-layer').value || d.layer);
    paint(); suggestions(); overlays();

  }

  // ---------------------------------------------------------------- first mount
  if (first) {
    const d = D();
    const fov = $('#rg-fov');
    fov.min = String(d.fov_min * 60); fov.max = String(d.fov_max * 60); fov.step = '0.5';
    $('.rg-fovmin').textContent = `${d.fov_min * 60}′`; $('.rg-fovmax').textContent = `${d.fov_max * 60}′`;
    fov.addEventListener('input', () => setFov(Number(fov.value), 'fov'));
    const fovn = $('#rg-fovn'), fovMsg = `Entre ${d.fov_min * 60}′ y ${d.fov_max * 60}′`;
    let fovTimer;
    const applyFov = (strict) => {
      clearTimeout(fovTimer);
      const t = clean(fovn.value), v = DECIMAL.test(t) ? Number(t) : NaN;
      if (Number.isNaN(v) || v < d.fov_min * 60 - 1e-9 || v > d.fov_max * 60 + 1e-9) { if (strict && t !== '') mark(fovn, true, fovMsg); return; }
      mark(fovn, false); setFov(v, 'fovn');
    };
    fovn.addEventListener('input', () => { clearTimeout(fovTimer); mark(fovn, false); fovTimer = setTimeout(() => applyFov(true), 750); });
    fovn.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); applyFov(true); } });
    fovn.addEventListener('blur', () => { applyFov(true); if (fovn.getAttribute('aria-invalid') !== 'true') paint(); });
    coordField($('#rg-ra'), parseRa, 'ra', 'RA between 0° and 360° (or hh mm ss)');
    coordField($('#rg-dec'), parseDec, 'dec', 'Dec between −90° and +90° (or ±dd mm ss)');

    const q = $('#rg-q');
    q.addEventListener('input', () => {
      S.active = -1; S.suggesting = true; suggestions();
      clearTimeout(S.queryTimer);
      S.queryTimer = setTimeout(() => S.api.setStateValue('query', q.value), 550);
    });
    q.addEventListener('focus', suggestions);
    q.addEventListener('blur', () => { $('#rg-list').hidden = true; $('.rg-search-status').hidden = true; q.setAttribute('aria-expanded', 'false'); });
    q.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        if (!S.items.length) return;
        e.preventDefault();
        S.active = (S.active + (e.key === 'ArrowDown' ? 1 : -1) + S.items.length + (S.active < 0 && e.key === 'ArrowUp' ? 1 : 0)) % S.items.length;
        suggestions();
      } else if (e.key === 'Enter') {
        e.preventDefault(); const chosen = S.active >= 0 && S.items[S.active]; pick(chosen ? chosen.id : q.value, chosen && chosen.label);
      } else if (e.key === 'Escape') { S.active = -1; S.suggesting = false; $('#rg-list').hidden = true; $('.rg-search-status').hidden = true; q.setAttribute('aria-expanded', 'false'); }
    });

    for (const L of d.layers) { const o = document.createElement('option'); o.value = L.id; o.textContent = L.label; $('#rg-layer').append(o); }
    $('#rg-layer').addEventListener('change', (e) => { setLayer(e.target.value); S.api.setStateValue('layer', e.target.value); });
    $('#rg-gaia').addEventListener('change', (e) => { gaiaStatus(); S.api.setStateValue('gaia', e.target.checked); });
    $('.rg-gaia-retry').addEventListener('click', () => S.api.setTriggerValue('gaia_retry', Date.now()));
    $('#rg-constellations').addEventListener('change', (e) => S.api.setStateValue('constellations', e.target.checked));
    $('.rg-wide').addEventListener('click', () => zoomTo(60));
    $('.rg-frame').addEventListener('click', frame);
    for (const b of root.querySelectorAll('.rg-cta')) {
      b.addEventListener('click', () => {
        clearTimeout(S.flushTimer);
        S.sentKey = keyOf(S.cur);
        S.api.setTriggerValue('open', { view: b.dataset.view, ra: r7(normRa(S.cur.ra)), dec: r7(S.cur.dec), fov: S.cur.fov, n: Date.now() });
      });
    }

    apply();
    setLayer(d.layer);
    status('Loading the atlas…');
    const slow = setTimeout(() => {
      if (!S.aladin) status('The atlas is slow to load (it needs WebGL2 and access to jsDelivr and IRSA). The name, coordinates and field still work.', true);
    }, 20000);
    import(d.aladin).then(async ({ default: A }) => {
      await A.init;
      if (root.isConnected === false || root.__skyRegion !== S) return;
      S.A = A;
      S.aladin = A.aladin($('.rg-map'), {
        target: `${S.cur.ra} ${S.cur.dec}`, fov: Math.max(S.cur.fov * 2.5, 0.05), cooFrame: 'ICRSd', survey: [],
        showReticle: true, reticleColor: '#ffffff', reticleSize: 16, showCooLocation: false, showZoomControl: true,
        showFullscreenControl: false, showLayersControl: false, showGotoControl: false, showShareControl: false,
        showSettingsControl: false, showSimbadPointerControl: false, showProjectionControl: false, showFrame: false,
        showCooGrid: false, showCooGridControl: false, showStatusBar: false, showContextMenu: false,
        showFov: false, log: false,
        backgroundColor: 'rgb(13,15,18)',
      });
      S.halo = A.graphicOverlay({ color: 'rgba(8,10,12,0.72)', lineWidth: 5 }); S.aladin.addOverlay(S.halo);
      S.ring = A.graphicOverlay({ color: '#ff8a3d', lineWidth: 2 }); S.aladin.addOverlay(S.ring);
      S.marker = A.catalog({ name: 'Objeto buscado', color: '#ffffff', sourceSize: 14 }); S.aladin.addCatalog(S.marker);
      S.gaia = A.catalog({ name: 'Gaia DR3 (J2016.0)', color: '#7fd6ff', shape: 'circle', sourceSize: 8 }); S.aladin.addCatalog(S.gaia);
      S.gaiaHits = [];
      S.aladin.on('objectClicked', (source) => {
        if (source && source.catalog === S.gaia) S.gaiaHits.push(source);
      });
      S.constLines = A.graphicOverlay({name: 'Traditional figures (not IAU boundaries)', color: '#91aab9', lineWidth: 1});
      S.aladin.addOverlay(S.constLines);
      for (const c of D().constellations) for (const line of c.lines) S.constLines.add(A.polyline(line));
      S.constNames = A.catalog({name: 'Constelaciones', color: '#c4d1d9', sourceSize: 0,
        displayLabel: true, labelColumn: 'name', labelColor: '#c4d1d9', labelFont: '12px sans-serif'});
      S.aladin.addCatalog(S.constNames);
      S.constNames.addSources(D().constellations.map(c => A.source(c.label[0], c.label[1], {name: c.name})));
      // Aladin redraws overlays only on a view change: nudge it when the box is resized.
      S.resize = new ResizeObserver(() => {
        if (!S.aladin || S.lock) return;
        const [r, dd] = S.aladin.getRaDec(); S.lock = true; S.aladin.gotoRaDec(r, dd); S.lock = false; drawCircle(); chip();
      });
      S.resize.observe($('.rg-map'));
      S.aladin.on('positionChanged', onMapMove);
      S.aladin.on('zoomChanged', () => { chip(); constellationVisibility(); });
      S.aladin.on('click', (e) => {
        const hits = S.gaiaHits.splice(0);
        if (!e || e.ra === undefined || e.isDragging) return;
        if (hits.length) {
          const distance = s => {const p = S.aladin.world2pix(s.ra, s.dec); return p ? (p[0]-e.x)**2+(p[1]-e.y)**2 : Infinity;};
          hits.sort((a,b) => distance(a)-distance(b));
          pickGaia(hits[0]);
        } else setCentre(e.ra, e.dec);
      });
      clearTimeout(slow);
      status('');
      setLayer($('#rg-layer').value);
      S.markerKey = undefined; S.gaiaKey = undefined;
      S.lock = true; S.aladin.gotoRaDec(S.cur.ra, S.cur.dec); S.lock = false;
      drawCircle(); overlays(); chip();
      root.querySelector('.sc-region').classList.add('rg-ready');
    }).catch((e) => {
      clearTimeout(slow);
      status(`Could not start the atlas (${e.message || e}). The name, coordinates and field still work.`, true);
    });
    // v2 also calls cleanup when data changes: retain handlers while the root is mounted.
    return () => {
      if (root.isConnected === false) {
        clearTimeout(S.flushTimer); clearTimeout(S.queryTimer); clearTimeout(S.nameTick); clearTimeout(S.unlock);
        if (S.resize) S.resize.disconnect();
      }
    };
  }
  apply();
}
