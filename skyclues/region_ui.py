"""Region selector: object search, coordinates, field of view and Atlas in one place.

The three inputs are not three tools: they are three ways to edit the single active region held
by ``navigation``. The interface runs in the browser (``region_component.js``); this module turns
its settled events into region changes and feeds it what only the server can provide (SIMBAD
suggestions, name resolution, Gaia DR3 sources).

No FITS query and no scientific analysis is started from here: moving the map only moves the region.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from . import atlas, config, navigation, object_search, references
from .astrometry import Astrometry

_HERE = Path(__file__).parent
_ARROW = ('<svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true"><path d="M3.5 9h11M10 4.5 14.5 9 '
          '10 13.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>')
_HTML = f"""
<div class="sc-region" data-level="simple">
  <div class="rg-panel">
    <div class="rg-field">
      <label for="rg-q">Objeto <span>nombre o catálogo</span></label>
      <div class="rg-combo">
        <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true"><circle cx="6.5" cy="6.5" r="4.6"
          stroke="currentColor" stroke-width="1.5"/><path d="m10 10 3.4 3.4" stroke="currentColor" stroke-width="1.5"
          stroke-linecap="round"/></svg>
        <input id="rg-q" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="rg-list"
               placeholder="M101, Andrómeda, Barnard, WISE 0855…" maxlength="100" autocomplete="off" spellcheck="false">
        <ul id="rg-list" role="listbox" aria-label="Objetos sugeridos" hidden></ul>
      </div>
      <p class="rg-object" role="status" aria-live="polite"></p>
      <div class="rg-notes"></div>
    </div>
    <div class="rg-coords">
      <div class="rg-field">
        <label for="rg-ra">RA <span>grados · ICRS</span></label>
        <input id="rg-ra" class="rg-num" type="text" inputmode="decimal" autocomplete="off" spellcheck="false"
               aria-label="Ascensión recta en grados" aria-describedby="rg-ra-sexa">
        <span class="rg-sexa rg-sexa-ra" id="rg-ra-sexa"></span><span class="rg-err" role="alert"></span>
      </div>
      <div class="rg-field">
        <label for="rg-dec">Dec <span>grados · ICRS</span></label>
        <input id="rg-dec" class="rg-num" type="text" inputmode="decimal" autocomplete="off" spellcheck="false"
               aria-label="Declinación en grados" aria-describedby="rg-dec-sexa">
        <span class="rg-sexa rg-sexa-dec" id="rg-dec-sexa"></span><span class="rg-err" role="alert"></span>
      </div>
    </div>
    <div class="rg-field">
      <label for="rg-fov">Campo de visión <span>diámetro en el cielo</span></label>
      <div class="rg-fovrow">
        <input id="rg-fov" type="range" aria-label="Campo de visión en minutos de arco">
        <div class="rg-fovbox"><input id="rg-fovn" class="rg-num" type="text" inputmode="decimal" autocomplete="off"
             aria-label="Campo de visión, valor en minutos de arco"><span aria-hidden="true">′</span></div>
      </div>
      <div class="rg-scale" aria-hidden="true"><span class="rg-fovmin"></span><span class="rg-fovmax"></span></div>
      <p class="rg-fovhint"></p><span class="rg-err" role="alert"></span>
    </div>
  </div>
  <div class="rg-actions">
    <button type="button" class="rg-cta rg-primary" data-view="time"><b>Ver en el tiempo</b>
      <small>Observaciones reales de fechas distintas</small>{_ARROW}</button>
    <button type="button" class="rg-cta" data-view="spectrum"><b>Explorar el espectro</b>
      <small>La misma región en 102 canales infrarrojos</small>{_ARROW}</button>
  </div>
  <div class="rg-mapcol">
    <div class="rg-mapwrap">
      <div class="rg-map" role="application" aria-label="Atlas del cielo: arrastre para mover la región"></div>
      <div class="rg-tools">
        <select id="rg-layer" class="rg-tool" aria-label="Mapa de contexto"></select>
        <label class="rg-tool"><input id="rg-gaia" type="checkbox"> Gaia DR3</label>
        <button type="button" class="rg-tool rg-frame" title="Ajustar el zoom del mapa a la región (no cambia el campo)">Encuadrar</button>
      </div>
      <div class="rg-chip" aria-hidden="true"></div>
      <div class="rg-status" role="status" hidden></div>
    </div>
    <p class="rg-layerinfo"></p>
    <p class="rg-gaiainfo" role="status"></p>
  </div>
</div>
"""

REGION = st.components.v2.component(
    "sky_region",
    html=_HTML,
    css=(_HERE / "region_component.css").read_text(encoding="utf-8"),
    js=(_HERE / "region_component.js").read_text(encoding="utf-8"),
    isolate_styles=False,
)
KEY = "region_ui"
LOCAL_INDEX = [{"id": x["id"], "aliases": x["aliases"], "type": x["type"]} for x in object_search.INDEX]


@st.cache_data(ttl=3600, max_entries=128, show_spinner=False)
def suggestions(q: str):
    rows, status = object_search.remote_suggestions(q)
    if status.startswith("Sugerencias remotas no disponibles"):
        raise RuntimeError(status)          # never cache an outage
    return rows, status


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def resolve(name: str):
    a, warnings, extended = object_search.resolve(name)
    return a.to_dict(), list(warnings), bool(extended)


def _component_state() -> dict:
    v = st.session_state.get(KEY)
    try:
        return dict(v) if v else {}
    except (TypeError, ValueError):
        return {}


# ----------------------------------------------------------------------------- events from the browser
def _on_region() -> None:
    v = _component_state().get("region")
    if not v:
        return
    try:
        navigation.move_region(st.session_state, st.query_params, v["ra"], v["dec"], v["fov"])
        st.session_state.pop("region_notice", None)
    except (ValueError, KeyError, TypeError) as err:
        st.session_state["region_notice"] = f"Región no válida: {err}"


def _on_pick() -> None:
    v = _component_state().get("pick") or {}
    name = str(v.get("name", "")).strip()
    st.session_state["region_pick_done"] = v.get("n")
    if not name:
        return
    try:
        astro_dict, warnings, extended = resolve(name)
    except Exception as err:  # noqa: BLE001 - shown to the user next to the search box
        st.session_state["region_notice"] = f"No se pudo resolver «{name}»: {err}"
        return
    astro = Astrometry.from_dict(astro_dict)
    navigation.set_object(st.session_state, st.query_params, astro, warnings, extended,
                          position=atlas.object_position_now(astro))
    st.session_state.pop("region_notice", None)


def _on_open() -> None:
    v = _component_state().get("open") or {}
    try:
        navigation.move_region(st.session_state, st.query_params, v["ra"], v["dec"], v["fov"])
    except (ValueError, KeyError, TypeError) as err:
        st.session_state["region_notice"] = f"Región no válida: {err}"
        return
    if v.get("view") in ("time", "spectrum"):
        st.session_state["view_request"] = v["view"]


def _on_layer() -> None:
    v = _component_state().get("layer")
    if any(v == L["id"] for L in atlas.LAYERS):
        st.session_state["atlas_layer"] = v


def _on_gaia() -> None:
    st.session_state["atlas_gaia"] = bool(_component_state().get("gaia"))


def _noop() -> None:
    pass


# ----------------------------------------------------------------------------- what the browser is told
def object_card(region: dict) -> dict | None:
    """Identity of the region's object for the selector (text only; no measurement)."""
    if not region.get("name"):
        return None
    astro = Astrometry.from_dict(region["astrometry"]) if region.get("astrometry") else None
    notes, detail, marker_note = list(region.get("notes") or []), "", "Posición de catálogo."
    if region.get("report"):
        detail = "secuencia verificada · centro y campo fijos"
    elif astro is not None:
        detail = f"catálogo J{astro.epoch_jyear:.1f}"
        if astro.has_proper_motion:
            detail = f"movimiento propio {astro.total_pm_arcsec_yr:.2f}″/año"
            marker_note = ("Posición calculada para hoy con la astrometría del catálogo; los mapas son de otras "
                           "épocas y el objeto puede aparecer desplazado.")
            notes.insert(0, "El mapa muestra la posición calculada para hoy. Cada explorador la calcula para las "
                            "fechas de sus propias observaciones; una posición calculada no es una detección.")
    if region.get("extended"):
        notes.append("Centro catalogado de un objeto extenso: el campo puede mostrar solo una parte.")
    return {"name": region["name"], "detail": detail, "anchor": region.get("anchor"), "notes": notes,
            "marker_note": marker_note}


def _gaia(region: dict):
    """Gaia DR3 sources for the overlay. Re-queried only when the region leaves the field already
    fetched, so nudging the map does not send one catalogue query per movement."""
    from .reference_page import cached_gaia

    state = st.session_state
    held = state.get("atlas_gaia_field")
    moved = (held is None or abs(held["fov"] - region["fov"]) > 1e-9 or
             navigation.separation_arcsec(region["ra"], region["dec"], held["ra"], held["dec"]) > held["fov"] * 3600 / 4)
    if moved:
        held = state["atlas_gaia_field"] = {"ra": region["ra"], "dec": region["dec"], "fov": region["fov"]}
    try:
        g = cached_gaia(held["ra"], held["dec"], held["fov"])
    except references.ReferenceError as err:
        state.pop("atlas_gaia_field", None)
        return [], None, f"Gaia DR3 no disponible: {err} El atlas sigue funcionando sin el catálogo."
    rows = [{"ra": s["ra"], "dec": s["dec"], "source_id": s["source_id"], "G": s.get("phot_g_mean_mag")}
            for s in g["sources"]]
    note = (f"Gaia DR3 (ESA, posiciones J2016.0): {len(rows)} fuentes en un círculo de {held['fov'] * 60:g}′ centrado en "
            f"RA {held['ra']:.5f}°, Dec {held['dec']:+.5f}°" + (" · truncado a 500 por magnitud G" if g["truncated"] else "")
            + ". Catálogo de otra misión: no se compara con SPHEREx para inferir movimiento.")
    return rows, g["sha256"], note


def render(level: str) -> None:
    """Draw the selector. ``level`` ("simple" | "scientific") only changes wording."""
    state, params = st.session_state, st.query_params
    region = navigation.get_region(state, params)
    comp = _component_state()
    query = str(comp.get("query") or "")
    remote = []
    if len(query.strip()) >= 3:
        try:
            remote, _ = suggestions(query)
        except (ValueError, RuntimeError):
            remote = []                       # local index and full-name search still work
    gaia_on = bool(state.get("atlas_gaia"))
    gaia_rows, gaia_key, gaia_note = ([], None, "")
    if gaia_on:
        gaia_rows, gaia_key, gaia_note = _gaia(region)
    else:
        state.pop("atlas_gaia_field", None)
    REGION(
        data={"region": {"ra": region["ra"], "dec": region["dec"], "fov": region["fov"]}, "rev": region["rev"],
              "object": object_card(region), "notice": state.get("region_notice"),
              "pick_done": state.get("region_pick_done"), "level": level,
              "local": LOCAL_INDEX, "remote": remote, "remote_query": query,
              "layers": atlas.LAYERS, "layer": state.get("atlas_layer", "2mass"),
              "gaia_on": gaia_on, "gaia": gaia_rows, "gaia_key": gaia_key, "gaia_note": gaia_note,
              "fov_min": config.FOV_MIN_DEG, "fov_max": config.FOV_MAX_DEG,
              "anchor_arcsec": navigation.ANCHOR_TOLERANCE_ARCSEC,
              "spherex_px": config.NOMINAL_PIXEL_SCALE_ARCSEC, "cube_px": 12.9, "aladin": references.ALADIN_JS},
        key=KEY, default={"query": "", "gaia": gaia_on, "layer": state.get("atlas_layer", "2mass"), "region": None},
        on_region_change=_on_region, on_pick_change=_on_pick, on_open_change=_on_open,
        on_query_change=_noop, on_layer_change=_on_layer, on_gaia_change=_on_gaia)


def provenance() -> None:
    """Where the Atlas layers come from (shown on request; the maps are context, never SPHEREx data)."""
    for L in atlas.LAYERS:
        st.markdown(f"- **{L['label']}** — {L['mission']} · `{L['product']}` · {L['bands']} · {L['epoch']} · "
                    f"[HiPS IRSA]({L['url']}/properties)")
    sx = atlas.SPHEREX_HIPS
    st.markdown(f"- **SPHEREx**: IRSA publica `{sx['did']}` ({sx['kind']}, versión {sx['release']}). Sus teselas por "
                "plano no siguen la ruta HiPS estándar que carga Aladin Lite 3.8.1, así que no se ofrece como mapa. "
                "El cubo combinado se explora en «Espectro»; ningún mapa del atlas es una secuencia temporal.")
    st.caption("Gaia: catálogo ESA consultado en el servidor para la región. Las posiciones de otras misiones y épocas "
               "no deben compararse con SPHEREx para inferir movimiento o variabilidad.")
