"""Temporal player for a TemporalSequence (HTML/JS embedded in Streamlit).

Each frame is one authentic observation rendered with ONE shared intensity
normalisation. There are no intermediate or interpolated frames: the player
only switches between the N real images.

Two geometries (``geometry=``):

* ``"exact"`` (default): every native pixel is drawn as a quadrilateral at its
  true position on the sky (both WCS, TAN-SIP), with its own unchanged value.
  No resampling, so a fixed star does not jump by nearest-neighbour rounding.
* ``"nearest"``: the frame placed on the reference grid by nearest neighbour
  (the grid used for the statistics; position error up to 0.5 px).

``show_halo=True`` is the exploratory display: pixels masked only by HALO
("caution recommended" in the SPHEREx documentation) are drawn in a distinct
copper scale. Comparability metrics never change with these options.

The playback logic lives in ``PLAYER_CORE_JS`` (a DOM-free state machine) so
it can be tested with Node; ``player_html`` adds the DOM glue.
"""

from __future__ import annotations

import base64
import io
import json

import matplotlib

matplotlib.use("Agg")
import numpy as np  # noqa: E402
from astropy.time import Time  # noqa: E402
from matplotlib.cm import ScalarMappable  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from . import config, render  # noqa: E402
from .quality import CAUTION  # noqa: E402
from .sequence import TemporalSequence  # noqa: E402

FIG_SIZE_IN = (5.6, 5.0)
DPI = 110
AX_RECT = [0.15, 0.11, 0.66, 0.85]
CB_RECT = [0.86, 0.11, 0.03, 0.85]
GEOMETRIES = ("exact", "nearest")
GEOMETRY_LABEL = {
    "exact": ("geometría WCS: cada píxel nativo se dibuja donde lo sitúa su WCS (TAN-SIP), con su valor original "
              "(sin remuestreo de valores)"),
    "nearest": "REMUESTREADO por vecino más próximo (error de posición hasta ½ px por eje, ≈0.7 px)",
}
FRAME_STAMP = {
    "exact": "Píxeles nativos en su posición WCS · sin remuestreo de valores",
    "nearest": "REMUESTREADO · vecino más próximo en la rejilla de la época 1",
}


def screen_scale_arcsec(seq: TemporalSequence) -> float:
    """Sky size of one screen pixel of the player image (arcsec).

    The axes have a fixed size in pixels; with equal aspect the field's
    longer side sets the scale. Positions on screen are therefore rounded to
    about half this value, independently of the WCS precision.
    """
    from astropy.wcs.utils import proj_plane_pixel_scales

    ny, nx = seq.shape
    ax_w, ax_h = FIG_SIZE_IN[0] * AX_RECT[2] * DPI, FIG_SIZE_IN[1] * AX_RECT[3] * DPI
    native_px_per_screen_px = max(nx / ax_w, ny / ax_h)
    pix_arcsec = float(np.mean(proj_plane_pixel_scales(seq.wcs.celestial))) * 3600
    return native_px_per_screen_px * pix_arcsec


def precision_note(seq: TemporalSequence) -> str:
    """What limits the positional precision of the display (four separate things)."""
    psf = [f.quality.get("psf_fwhm_arcsec") for f in seq.frames]
    psf = [float(p) for p in psf if p is not None and np.isfinite(float(p))]
    s = screen_scale_arcsec(seq)
    return (f"Precisión de posición: (1) WCS: cálculo exacto de cada esquina de píxel (TAN-SIP); "
            f"(2) pantalla: 1 píxel de pantalla ≈ {s:.1f}″, así que lo dibujado se redondea ±{s / 2:.1f}″; "
            f"(3) instrumento: píxel SPHEREx ≈ {config.NOMINAL_PIXEL_SCALE_ARCSEC}″"
            + (f", PSF ≈ {min(psf):.1f}–{max(psf):.1f}″ FWHM" if psf else "")
            + "; (4) remuestreo: ninguno en geometría WCS; hasta ≈0.7 px nativos en la rejilla común.")


def sequence_norm(seq: TemporalSequence, subtract_zodi: bool = True):
    """One normalisation for every frame, from the region common to all frames."""
    arrays = [seq.frame_data(i, subtract_zodi) for i in range(seq.n)]
    region = seq.common_mask if seq.common_mask.any() else seq.field_mask
    return render.shared_norm(arrays, region=region)


def frame_rgba(seq: TemporalSequence, i: int, norm, subtract_zodi: bool = True,
               restrict_to_common: bool = False) -> np.ndarray:
    """RGBA of frame i on the reference grid (nearest-neighbour placement)."""
    data = seq.frame_data(i, subtract_zodi)
    return render.sequence_rgba(data, norm, seq.common_mask if restrict_to_common else None)


def native_frame_rgba(seq: TemporalSequence, i: int, norm, subtract_zodi: bool = True,
                      restrict_to_common: bool = False, show_halo: bool = False) -> np.ndarray:
    """RGBA of frame i on its own native grid (for the exact-geometry display)."""
    data = seq.native_data(i, subtract_zodi, CAUTION if show_halo else ())
    return render.native_rgba(data, norm, seq.native_caution(i) if show_halo else None,
                              seq.native_common(i) if restrict_to_common else None)


@render.serialized
def render_frame_png(seq: TemporalSequence, i: int, norm, subtract_zodi: bool = True,
                     restrict_to_common: bool = False, geometry: str = "exact",
                     show_halo: bool = False) -> bytes:
    """PNG of frame i with a fixed layout (identical axes for every frame).

    Runs under ``render.RENDER_LOCK``: matplotlib text rendering is not
    thread-safe and the app serves several sessions in parallel threads.
    """
    if geometry not in GEOMETRIES:
        raise ValueError(f"geometry must be one of {GEOMETRIES}")
    fig = Figure(figsize=FIG_SIZE_IN, dpi=DPI, facecolor="white")   # not registered in pyplot
    ax = fig.add_axes(AX_RECT, projection=seq.wcs)
    render._style_axes(ax)
    if geometry == "exact":
        render.draw_native(ax, seq.native_corners(i),
                           native_frame_rgba(seq, i, norm, subtract_zodi, restrict_to_common, show_halo),
                           seq.shape)
    else:
        rgba = frame_rgba(seq, i, norm, subtract_zodi, restrict_to_common)
        if show_halo:
            f = seq.frames[i]
            caution = f.on_reference(seq.native_caution(i).astype(float)) == 1
            data = f.on_reference(seq.native_data(i, subtract_zodi, CAUTION))
            rgba = render.native_rgba(data, norm, caution, seq.common_mask if restrict_to_common else None)
        ax.imshow(rgba, origin="lower", interpolation="nearest")
    render._mark_sequence_target(ax, seq, i)
    fig.text(0.01, 0.01, FRAME_STAMP[geometry] + f" · pantalla ≈{screen_scale_arcsec(seq):.1f}″/px"
             + (" · HALO visible (exploratorio)" if show_halo else ""),
             fontsize=6.5, color=render.INK if geometry == "exact" else "#8a1a36")
    cax = fig.add_axes(CB_RECT)
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=render._cmap()), cax=cax)
    cb.set_label(("IMAGE − ZODI" if subtract_zodi else "IMAGE") + " [MJy/sr]", color=render.INK, fontsize=8)
    cb.ax.tick_params(labelsize=7, colors=render.INK)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, facecolor="white")  # no bbox_inches: fixed canvas
    return buf.getvalue()


def frame_metadata(seq: TemporalSequence) -> list[dict]:
    t0 = seq.frames[0].mjd
    out = []
    for i, f in enumerate(seq.frames):
        out.append({
            "i": i,
            "date": Time(f.mjd, format="mjd").isot[:16].replace("T", " ") + " UTC",
            "dt_days": round(f.mjd - t0, 2),
            "obs_id": f.obs_id,
            "collection": f.collection,
            "detector": f.detector,
            "lambda_um": round(f.lambda_target_um, 4),
            "bandwidth_um": round(f.bandwidth_target_um, 4),
            "exptime_s": round(float(f.image.meta.get("XPOSURE") or float("nan")), 1),
            "valid_pct": round(100 * f.quality.get("valid_fraction_in_field", float("nan")), 1),
            "dqa": f.quality.get("L2DQAFLG", ""),
            "file": f.record.get("file_name", f.path.name),
        })
    return out


# ----------------------------------------------------------------------------- JS
PLAYER_CORE_JS = r"""
function createPlayer(n, opts) {
  opts = opts || {};
  const s = {
    n: n, index: 0, playing: false, fps: opts.fps || 1, loop: opts.loop !== false,
    blink: false, blinkA: 0, blinkB: Math.min(1, n - 1), blinkFps: opts.blinkFps || 2
  };
  const clamp = (i) => Math.max(0, Math.min(s.n - 1, i));
  const api = {
    state: s,
    current() { return s.index; },
    intervalMs() { return 1000 / (s.blink ? s.blinkFps : s.fps); },
    play() {
      if (!s.blink && !s.loop && s.index === s.n - 1) s.index = 0;
      if (s.n > 1) s.playing = true;
    },
    pause() { s.playing = false; },
    toggle() { if (s.playing) api.pause(); else api.play(); },
    tick() {
      if (!s.playing) return s.index;
      if (s.blink) {
        s.index = (s.index === s.blinkA) ? s.blinkB : s.blinkA;
      } else if (s.index < s.n - 1) {
        s.index += 1;
      } else if (s.loop) {
        s.index = 0;
      } else {
        s.playing = false;
      }
      return s.index;
    },
    next() {
      s.playing = false;
      if (s.blink) { s.blink = false; }
      s.index = (s.index < s.n - 1) ? s.index + 1 : (s.loop ? 0 : s.index);
      return s.index;
    },
    prev() {
      s.playing = false;
      if (s.blink) { s.blink = false; }
      s.index = (s.index > 0) ? s.index - 1 : (s.loop ? s.n - 1 : 0);
      return s.index;
    },
    seek(i) { s.playing = false; s.blink = false; s.index = clamp(i); return s.index; },
    setFps(f) { s.fps = Math.max(0.1, Math.min(10, Number(f))); },
    setLoop(v) { s.loop = !!v; },
    setBlink(on, a, b, fps) {
      s.blink = !!on;
      if (a !== undefined) s.blinkA = clamp(a);
      if (b !== undefined) s.blinkB = clamp(b);
      if (fps !== undefined) s.blinkFps = Math.max(0.5, Math.min(10, Number(fps)));
      s.index = s.blink ? s.blinkA : s.index;
      s.playing = s.blink && s.blinkA !== s.blinkB;
    }
  };
  return api;
}
// Global keyboard shortcut for a keydown, or null to leave the key alone.
// A key pressed while a form control has the focus keeps its native meaning
// (slider and select move with the arrows, space toggles a checkbox or presses
// a button), so a shortcut never acts twice or on the wrong control.
function shortcutAction(code, tag, type, editable, modifiers) {
  if (modifiers) return null;
  const t = String(tag || '').toUpperCase();
  if (editable || t === 'INPUT' || t === 'SELECT' || t === 'TEXTAREA' || t === 'BUTTON' || t === 'OPTION') {
    return null;
  }
  return {Space: 'toggle', ArrowRight: 'next', ArrowLeft: 'prev'}[code] || null;
}
if (typeof module !== 'undefined') { module.exports = { createPlayer, shortcutAction }; }
"""

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root{--ink:#141414;--muted:#5a5a5a;--line:#dcdcda;--rule:#c9c9c6;--surface:#eeeeec;--accent:#c4411c;--mask:%(mask)s;--outside:%(outside)s;
  --r:3px;--ease:.22s cubic-bezier(.4,0,.2,1);--mono:"IBM Plex Mono",ui-monospace,Consolas,monospace}
*{box-sizing:border-box}
body{margin:0;font-family:"IBM Plex Sans","Segoe UI",Helvetica,Arial,sans-serif;color:var(--ink);background:transparent;line-height:1.45}
.sc{display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start}
.stage{position:relative;border:1px solid var(--rule);border-radius:var(--r);background:#fff;padding:6px;width:max-content;max-width:100%%}
.stage img{display:block;max-width:100%%;height:auto;image-rendering:pixelated}
.badge{position:absolute;left:12px;top:10px;background:rgba(255,255,255,.9);border:0;border-left:2px solid var(--accent);
  border-radius:0;padding:3px 8px;font-size:13px;font-weight:600}
.badge .sub{font-weight:400;color:var(--muted)}
.side{flex:1;min-width:280px;max-width:440px;padding:4px 0}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0}
.transport{display:grid;grid-template-columns:auto 1fr auto;gap:4px}
.transport button{white-space:nowrap;padding:8px 5px;font-size:12.5px}
/* flat rectangular controls: outline by default, black fill for the primary action */
button{font:inherit;font-size:13px;font-weight:500;border:1px solid var(--ink);background:rgba(255,255,255,.55);color:var(--ink);
  border-radius:var(--r);padding:8px 7px;cursor:pointer;transition:background-color var(--ease),border-color var(--ease),color var(--ease)}
button:hover{background:var(--ink);color:#fff}
button.primary{background:var(--ink);color:#fff;border-color:var(--ink)}
button.primary:hover{background:#000}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--ink);outline-offset:3px}
input[type=range]{flex:1;min-width:90px;height:18px;accent-color:var(--accent);cursor:pointer}
input[type=checkbox]{accent-color:var(--ink);width:14px;height:14px;margin:0;cursor:pointer}
select{font:inherit;font-size:12.5px;color:var(--ink);border:1px solid var(--rule);border-radius:var(--r);padding:6px;background:rgba(255,255,255,.6);max-width:100%%}
label{display:inline-flex;gap:7px;align-items:center;font-size:13px;color:var(--muted)}
.box{border:0;border-top:1px solid var(--rule);border-radius:0;padding:14px 0 4px;background:transparent;margin-top:16px}
.box h4{margin:0 0 10px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}
.table-scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%%;font-size:11px;font-family:var(--mono);font-variant-numeric:tabular-nums}
td,th{padding:6px 5px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
th{color:var(--muted);font-weight:500}
tr.on{background:rgba(20,20,20,.05);box-shadow:inset 2px 0 var(--accent)}
tbody tr{cursor:pointer}tbody tr:hover{background:var(--surface)}
.legend{font-size:12px;color:var(--muted);margin-top:6px}
.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 4px -1px 8px;border:1px solid #c9ced6}
.kbd{font-size:11px;color:var(--muted)}
#pos{font-family:var(--mono);font-size:10.5px}
@media(prefers-reduced-motion:reduce){*{transition:none!important}}
"""

_BODY = """
<div class="sc">
  <div class="stage">
    <img id="frame" alt="Observación SPHEREx">
    <div class="badge" id="badge"></div>
  </div>
  <div class="side">
    <div class="row transport">
      <button id="prev" title="Época anterior (←)">◀ Anterior</button>
      <button id="play" class="primary" title="Reproducir / pausa (espacio)">▶ Reproducir</button>
      <button id="next" title="Época siguiente (→)">Siguiente ▶</button>
    </div>
    <div class="row">
      <input type="range" id="scrub" min="0" step="1" aria-label="Época">
      <span id="pos" class="kbd"></span>
    </div>
    <div class="row">
      <label>Velocidad
        <select id="fps">
          <option value="0.5">0.5 fps</option><option value="1" selected>1 fps</option>
          <option value="2">2 fps</option><option value="4">4 fps</option>
        </select></label>
      <label><input type="checkbox" id="loop" checked> Repetir</label>
    </div>
    <div class="box">
      <h4>Blink</h4>
      <div class="row">
        <label><input type="checkbox" id="blink"> Alternar</label>
        <select id="ba" aria-label="Primera época de blink"></select><span>↔</span><select id="bb" aria-label="Segunda época de blink"></select>
        <select id="bfps" aria-label="Frecuencia de blink"><option value="1">1 Hz</option><option value="2" selected>2 Hz</option><option value="4">4 Hz</option></select>
      </div>
    </div>
    <div class="box">
      <h4>Épocas (observaciones auténticas)</h4>
      <div class="table-scroll"><table><thead><tr><th>#</th><th>Fecha</th><th>Δt (d)</th><th>λ (µm)</th><th>válido</th></tr></thead>
      <tbody id="rows"></tbody></table></div>
    </div>
    <div class="legend">%(legend)s</div>
    <div class="kbd">Teclado (con el foco fuera de los controles): espacio = reproducir/pausa · ← → = paso.
      Con un control seleccionado, las teclas actúan solo sobre ese control.</div>
  </div>
</div>
"""

_GLUE_JS = r"""
(function(){
  const FR = %(frames)s, META = %(meta)s;
  const imgs = FR.map(src => { const im = new Image(); im.src = src; return im; });
  const P = createPlayer(FR.length, {fps: 1, loop: true, blinkFps: 2});
  const $ = id => document.getElementById(id);
  let timer = null;
  function fmt(m){ return m.lambda_um.toFixed(4); }
  function draw(){
    const i = P.current(), m = META[i], s = P.state;
    $('frame').src = imgs[i].src;
    $('badge').innerHTML = (i+1) + '/' + FR.length + ' · ' + m.date +
      ' <span class="sub">· Δt +' + m.dt_days.toFixed(1) + ' d · ' + m.obs_id + ' · D' + m.detector +
      ' · λ ' + fmt(m) + ' µm' + (s.blink ? ' · BLINK' : '') + '</span>';
    $('scrub').value = i; $('pos').textContent = 'época ' + (i+1) + ' de ' + FR.length;
    $('play').textContent = s.playing ? '❚❚ Pausa' : '▶ Reproducir';
    document.querySelectorAll('#rows tr').forEach((tr, k) => tr.classList.toggle('on', k === i));
    $('blink').checked = s.blink;
  }
  function schedule(){
    if (timer) clearInterval(timer);
    timer = setInterval(() => { if (P.state.playing) { P.tick(); draw(); } }, P.intervalMs());
  }
  $('scrub').max = FR.length - 1;
  META.forEach(m => {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>' + (m.i+1) + '</td><td>' + m.date + '</td><td>' + m.dt_days.toFixed(1) +
                   '</td><td>' + fmt(m) + '</td><td>' + m.valid_pct.toFixed(1) + '%%</td>';
    tr.title = m.obs_id + ' · ' + m.collection + ' · ' + m.file;
    tr.onclick = () => { P.seek(m.i); schedule(); draw(); };
    $('rows').appendChild(tr);
    ['ba','bb'].forEach(id => { const o = document.createElement('option'); o.value = m.i;
      o.textContent = (m.i+1) + ' · ' + m.date.slice(0,10); $(id).appendChild(o); });
  });
  $('bb').value = Math.min(1, FR.length - 1);
  $('play').onclick = () => { P.toggle(); schedule(); draw(); };
  $('next').onclick = () => { P.next(); schedule(); draw(); };
  $('prev').onclick = () => { P.prev(); schedule(); draw(); };
  $('scrub').oninput = e => { P.seek(+e.target.value); schedule(); draw(); };
  $('fps').onchange = e => { P.setFps(e.target.value); schedule(); };
  $('loop').onchange = e => { P.setLoop(e.target.checked); };
  const blinkSet = () => { P.setBlink($('blink').checked, +$('ba').value, +$('bb').value, $('bfps').value); schedule(); draw(); };
  ['blink','ba','bb','bfps'].forEach(id => $(id).onchange = blinkSet);
  document.addEventListener('keydown', e => {
    const el = e.target || {};
    const act = shortcutAction(e.code, el.tagName, el.type, !!el.isContentEditable,
                               e.ctrlKey || e.altKey || e.metaKey);
    if (!act) return;
    e.preventDefault();
    P[act](); schedule(); draw();
  });
  window.skycluesPlayer = P;
  schedule(); draw();
})();
"""


def legend_html(subtract_zodi: bool = True, restrict_to_common: bool = False, geometry: str = "exact",
                show_halo: bool = False, moving: bool = False, precision: str = "") -> str:
    legend = (f'Magnitud: {"IMAGE − ZODI" if subtract_zodi else "IMAGE"} (MJy/sr), misma escala en todas las épocas.'
              f'<span class="sw" style="background:{render.MASK_COLOR}"></span>sin datos válidos en esa época')
    if restrict_to_common:
        legend += (f'<span class="sw" style="background:{render.OUTSIDE_COMMON_COLOR}"></span>'
                   'válido solo en algunas épocas')
    if show_halo:
        legend += (f'<span class="sw" style="background:{render.CAUTION_SWATCH}"></span>'
                   'HALO (modo exploratorio: precaución recomendada; excluido de las métricas)')
    if moving:
        legend += (' · Círculo azul: campo de comparación. <b>+ azul: posición CALCULADA del objetivo para la fecha de '
                   'cada época</b> (movimiento propio y paralaje del catálogo; es un cálculo, no una detección de '
                   'SPHEREx). × gris: posición de catálogo en su época (si cae dentro del campo).')
    else:
        legend += (' · Círculo azul: campo de comparación; + azul: posición del objetivo (sin movimiento propio '
                   'conocido: la misma en todas las fechas; no es una detección).')
    legend += (' Fotogramas = observaciones reales, sin interpolación '
               f'temporal. Ejes: rejilla de la época 1; {GEOMETRY_LABEL[geometry]}.')
    if precision:
        legend += ' ' + precision
    return legend


def presentation_key() -> str:
    """Invalidate cached HTML when the shared player presentation changes."""
    import hashlib
    return hashlib.sha256((_CSS + _BODY + _GLUE_JS).encode()).hexdigest()


def observation_player(pngs: list[bytes], metadata: list[dict], legend: str, simple=False,
                       animate=True) -> str:
    """Shared transport/palette for other authentic time-series products in Time Explorer."""
    if not pngs or len(pngs) != len(metadata):
        raise ValueError('Imágenes y metadatos no coinciden')
    css = _CSS % {'mask': render.MASK_COLOR, 'outside': render.OUTSIDE_COMMON_COLOR}
    if simple:
        css += '.badge .sub,.kbd:not(#pos),td:nth-child(n+3),th:nth-child(n+3){display:none}'
    if not animate:
        css += '#play,.box:has(#blink),.row:has(#fps){display:none}'
    if len(pngs)==1:
        css += '.transport,.row:has(#scrub){display:none}'
    body = _BODY % {'legend': legend}
    frames = ['data:image/png;base64,'+base64.b64encode(p).decode() for p in pngs]
    glue = _GLUE_JS % {'frames':json.dumps(frames), 'meta':json.dumps(metadata)}
    if not animate:
        glue = glue.replace("P[act]();", "if (act === 'toggle') return; P[act]();")
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head>"
            f"<body>{body}<script>{PLAYER_CORE_JS}</script><script>{glue}</script></body></html>")


def player_html(seq: TemporalSequence, pngs: list[bytes], subtract_zodi: bool = True,
                restrict_to_common: bool = False, geometry: str = "exact", show_halo: bool = False, simple: bool = False) -> str:
    frames = ["data:image/png;base64," + base64.b64encode(p).decode() for p in pngs]
    css = _CSS % {"mask": render.MASK_COLOR, "outside": render.OUTSIDE_COMMON_COLOR}
    body = _BODY % {"legend": legend_html(subtract_zodi, restrict_to_common, geometry, show_halo,
                                          seq.target_moves, precision_note(seq))}
    glue = _GLUE_JS % {"frames": json.dumps(frames), "meta": json.dumps(frame_metadata(seq))}
    if simple:
        css += '.badge .sub,.kbd:not(#pos),td:nth-child(n+3),th:nth-child(n+3){display:none}.legend{font-size:14px;line-height:1.5}'
        legend = 'Rosa: sin datos. Cruz azul: posición de referencia.'
        if show_halo:
            legend += ' Cobre: zonas de calidad limitada.'
        body = _BODY % {'legend': legend}
        body = body.replace('Épocas (observaciones auténticas)', 'Fechas disponibles')
        glue = glue.replace("'época '", "'fecha '")
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head>"
            f"<body>{body}<script>{PLAYER_CORE_JS}</script><script>{glue}</script></body></html>")


def build_player(seq: TemporalSequence, subtract_zodi: bool = True, restrict_to_common: bool = False,
                 geometry: str = "exact", show_halo: bool = False, simple: bool = False) -> str:
    """Ready-to-embed HTML player. Display options never alter the sequence or its metrics."""
    norm = sequence_norm(seq, subtract_zodi)
    pngs = [render_frame_png(seq, i, norm, subtract_zodi, restrict_to_common, geometry, show_halo)
            for i in range(seq.n)]
    return player_html(seq, pngs, subtract_zodi, restrict_to_common, geometry, show_halo, simple)
