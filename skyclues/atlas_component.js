// SkyClues Atlas: Aladin Lite locator. One Aladin instance per mounted element; data updates
// recentre it only when Python sends a new nonce, so the user's panning is never undone.
export default function (c) {
  const { parentElement: p, data, setTriggerValue } = c;
  const el = (cls) => p.querySelector(cls);
  let st = p.__skyAtlas;
  const fmt = (v, n) => Number(v).toFixed(n);
  const sexa = (ra, dec) => {
    const h = ((ra % 360) + 360) % 360 / 15, hh = Math.floor(h), mm = Math.floor((h - hh) * 60),
      ss = ((h - hh) * 60 - mm) * 60;
    const s = dec < 0 ? '−' : '+', d = Math.abs(dec), dd = Math.floor(d), dm = Math.floor((d - dd) * 60),
      ds = ((d - dd) * 60 - dm) * 60;
    return `${String(hh).padStart(2, '0')}h${String(mm).padStart(2, '0')}m${ss.toFixed(1).padStart(4, '0')}s ` +
      `${s}${String(dd).padStart(2, '0')}°${String(dm).padStart(2, '0')}′${ds.toFixed(0).padStart(2, '0')}″`;
  };
  function regionFov() { return Number(el('.fov').value) / 60; }
  function readout() {
    if (!st.aladin) return;
    const [ra, dec] = st.aladin.getRaDec(), view = st.aladin.getFoV()[0], f = regionFov();
    el('.centre').textContent = `ICRS centre: RA ${fmt(ra, 6)}°, Dec ${fmt(dec, 6)}° (${sexa(ra, dec)})`;
    el('.view').textContent = `View: ${view >= 1 ? fmt(view, 2) + '°' : fmt(view * 60, 1) + '′'} · region: ${fmt(f * 60, 1)}′ ` +
      `(yellow circle; explorer limits ${data.fov_min * 60}′–${data.fov_max * 60}′)`;
    const warn = el('.warn');
    warn.textContent = view > data.fov_max * 1.0001
      ? `The view (${view >= 1 ? fmt(view, 2) + '°' : fmt(view * 60, 1) + '′'}) is larger than the explorers' maximum field (${data.fov_max * 60}′). ` +
        'Only the yellow circle will be selected; “Fit to zoom” proposes the maximum allowed, without silently cropping.'
      : '';
    st.circle.removeAll();
    st.circle.add(st.A.circle(ra, dec, f / 2));
  }
  function setLayer() {
    const L = data.layers.find((l) => l.id === el('.layer').value) || data.layers[0];
    el('.layerinfo').textContent = `${L.mission} · ${L.product} · ${L.bands} · ${L.epoch}. ${L.note}`;
    try {
      st.aladin.setImageSurvey(st.aladin.newImageSurvey(L.url, { name: L.label, imgFormat: L.format }));
      el('.status').textContent = `Layer: ${L.label} (official HiPS served by NASA/IPAC IRSA).`;
      el('.status').classList.remove('err');
    } catch (e) {
      el('.status').textContent = `Could not load ${L.label}: ${e.message || e}`;
      el('.status').classList.add('err');
    }
  }
  function drawGaia() {
    if (!st.aladin) return;
    if (st.gaiaKey === data.gaia_key) return;
    st.gaiaKey = data.gaia_key;
    st.gaia.removeAll();
    if (data.gaia && data.gaia.length) {
      st.gaia.addSources(data.gaia.map((s) => st.A.source(s.ra, s.dec, s)));
      st.gaia.show();
    }
  }
  function apply() {
    if (!st.aladin) return;
    if (st.nonce !== data.nonce) {
      st.nonce = data.nonce;
      el('.fov').value = String(Math.round(data.fov * 60 * 10) / 10);
      if (![...el('.fov').options].some((o) => o.value === el('.fov').value)) {
        const o = document.createElement('option'); o.value = el('.fov').value; o.textContent = `${el('.fov').value}′`;
        el('.fov').append(o); el('.fov').value = o.value;
      }
      st.aladin.gotoRaDec(data.ra, data.dec);
      st.aladin.setFoV(Math.max(data.fov * 2.5, 0.1));
      if (data.marker) {
        st.marker.removeAll();
        st.marker.addSources([st.A.marker(data.marker.ra, data.marker.dec, { popupTitle: data.marker.label, popupDesc: data.marker.note })]);
      }
    }
    drawGaia();
    readout();
  }
  if (!st) {
    st = p.__skyAtlas = { nonce: null, gaiaKey: null };
    const sel = el('.layer');
    for (const L of data.layers) { const o = document.createElement('option'); o.value = L.id; o.textContent = L.label; sel.append(o); }
    sel.value = data.default_layer;
    for (const a of data.fov_presets) { const o = document.createElement('option'); o.value = String(a); o.textContent = `${a}′`; el('.fov').append(o); }
    el('.status').textContent = 'Starting Aladin Lite 3.8.1…';
    const timer = setTimeout(() => {
      if (!st.aladin) { el('.status').textContent = 'Aladin Lite is taking too long or is not available (it requires WebGL2 and access to jsDelivr/IRSA). Use “By name” or “Coordinates”.'; el('.status').classList.add('err'); }
    }, 30000);
    import(data.aladin).then(async ({ default: A }) => {
      await A.init;
      st.A = A;
      st.aladin = A.aladin(el('.map'), {
        target: `${data.ra} ${data.dec}`, fov: Math.max(data.fov * 2.5, 0.1), cooFrame: 'ICRSd', survey: [],
        showReticle: true, showCooLocation: true, showZoomControl: true, showFullscreenControl: true,
        showLayersControl: false, showGotoControl: false, showShareControl: false, showSettingsControl: false,
        showSimbadPointerControl: false, showProjectionControl: false, showFrame: true, showCooGrid: false,
        backgroundColor: 'rgb(16,20,26)',
      });
      st.circle = A.graphicOverlay({ color: '#ffd23f', lineWidth: 2 }); st.aladin.addOverlay(st.circle);
      st.marker = A.catalog({ name: 'Searched object', color: '#ff7a59', sourceSize: 14 }); st.aladin.addCatalog(st.marker);
      st.gaia = A.catalog({ name: 'Gaia DR3 (J2016.0)', color: '#69e2ff', shape: 'circle', sourceSize: 8 }); st.aladin.addCatalog(st.gaia);
      // Aladin redraws overlays (region circle, Gaia) only on a view change: force one when the box resizes.
      st.resize = new ResizeObserver(() => { if (st.aladin) { const [r, d] = st.aladin.getRaDec(); st.aladin.gotoRaDec(r, d); } });
      st.resize.observe(el('.map'));
      st.aladin.on('positionChanged', readout);
      st.aladin.on('zoomChanged', readout);
      st.aladin.on('click', (e) => { if (e && e.ra !== undefined && !e.isDragging) st.aladin.gotoRaDec(e.ra, e.dec); });
      setLayer();
      sel.onchange = setLayer;
      el('.fov').onchange = readout;
      el('.fit').onclick = () => {
        const view = st.aladin.getFoV()[0] * 60, max = data.fov_max * 60, min = data.fov_min * 60;
        const v = Math.min(Math.max(view, min), max);
        if (![...el('.fov').options].some((o) => o.value === String(Math.round(v * 10) / 10))) {
          const o = document.createElement('option'); o.value = String(Math.round(v * 10) / 10); o.textContent = `${o.value}′`; el('.fov').append(o);
        }
        el('.fov').value = String(Math.round(v * 10) / 10);
        el('.note').textContent = view > max ? `The view spans ${fmt(view, 1)}′: ${max}′ is proposed, the maximum allowed (it is not silently cropped).`
          : view < min ? `The view spans ${fmt(view, 1)}′: ${min}′ is proposed, the minimum allowed.` : '';
        readout();
      };
      el('.use').onclick = () => {
        const [ra, dec] = st.aladin.getRaDec();
        setTriggerValue('select', { ra, dec, fov: regionFov(), view: st.aladin.getFoV()[0], layer: el('.layer').value });
      };
      clearTimeout(timer);
      el('.use').disabled = false; el('.fit').disabled = false;
      apply();
    }).catch((e) => { clearTimeout(timer); el('.status').textContent = `Could not start Aladin Lite (${e.message || e}). Use “By name” or “Coordinates”.`; el('.status').classList.add('err'); });
  } else {
    apply();
  }
}
