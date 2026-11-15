"""Region selector: object search, coordinates, field of view and Atlas in one place.

The three inputs are not three tools: they are three ways to edit the single active region held
by ``navigation``. The interface runs in the browser (``region_component.js``); this module turns
its settled events into region changes and feeds it what only the server can provide (SIMBAD
suggestions, name resolution, Gaia DR3 sources).

No FITS query and no scientific analysis is started from here: moving the map only moves the region.
Presentation conventions, including translucent frosted loading, are documented in DESIGN_SYSTEM.md.
"""
from __future__ import annotations

from pathlib import Path

import json
import re

import streamlit as st

from . import atlas, config, navigation, object_search, references, solar_system, gaia_atlas
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
        <label class="rg-tool"><input id="rg-constellations" type="checkbox"> Constelaciones</label>
        <button type="button" class="rg-tool rg-wide" title="Ver 60 grados sin cambiar el campo científico">Orientación</button>
        <button type="button" class="rg-tool rg-frame" title="Ajustar el zoom del mapa a la región (no cambia el campo)">Encuadrar</button>
      </div>
      <div class="rg-chip" aria-hidden="true"></div>
      <div class="rg-status" role="status" hidden><div class="rg-loading-card">
        <span class="rg-activity" aria-hidden="true"></span><span class="rg-map-message"></span>
      </div></div>
      <div class="rg-gaia-status" role="status" aria-live="polite" hidden>
        <div class="rg-loading-card"><span class="rg-activity" aria-hidden="true"></span>
          <span class="rg-gaia-message"></span><span class="rg-loading-detail">Buscando estrellas en esta zona del cielo.<br>Puede seguir moviendo el mapa.</span>
          <button type="button" class="rg-gaia-retry" hidden>Reintentar</button></div>
      </div>
    </div>
    <p class="rg-layerinfo"></p>
    <p class="rg-gaiainfo" role="status"></p>
    <p class="rg-constinfo" role="status"></p>
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
    if object_search.normalize(object_search.canonical_name(q)) == 'm 102':
        return [{'id': 'NGC 5866', 'type': 'M102: identificación habitual, históricamente discutida', 'aliases': []},
                {'id': 'M101', 'type': 'M102: posible duplicado histórico', 'aliases': []}], 'Identificación ambigua'
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
        from datetime import datetime, timezone
        q = object_search.normalize(name)
        if name.startswith('JPL:'):
            candidates = solar_lookup(name[4:])
        elif q in solar_system.ALIASES or not re.match(r'^(m|messier|ngc|ic|hd|hip|wise|2mass|gaia)\s*\d', q):
            local = any(q in [object_search.normalize(v) for v in [x['id'], *x['aliases']]] for x in object_search.INDEX)
            try:
                candidates = [] if local else solar_lookup(name)
            except solar_system.ServiceError:
                if q in solar_system.ALIASES:
                    raise
                candidates = []
        else:
            candidates = []
        if candidates:
            exact = [x for x in candidates if object_search.normalize(solar_system.ALIASES.get(q, name)) in
                     [object_search.normalize(v) for v in [x['name'], x.get('pdes') or '', *x['aliases']]]]
            if len(candidates) > 1 and len(exact) != 1:
                st.session_state['solar_choices'] = candidates
                st.session_state['region_notice'] = 'Hay varias identidades JPL; elija el objeto debajo del atlas.'
                return
            identity = exact[0] if len(exact) == 1 else candidates[0]
            position = solar_position(identity, datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:00'))
            navigation.set_solar(st.session_state, st.query_params, position)
            st.session_state.pop('region_notice', None)
            st.session_state.pop('solar_choices', None)
            return
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


def _on_gaia_pick() -> None:
    state = st.session_state
    pick = _component_state().get('gaia_pick') or {}
    displayed = state.get('atlas_gaia_displayed') or {}
    source = (displayed.get('sources') or {}).get(pick.get('source_id'))
    if not state.get('atlas_gaia') or source is None or pick.get('key') != displayed.get('key'):
        return                         # stale/untrusted browser event: use only a server-held record
    try:
        # Include a recently changed FOV even if its debounce has not yet reached Python.
        fov = pick.get('fov', navigation.get_region(state, st.query_params)['fov'])
        old = navigation.get_region(state, st.query_params)
        navigation.move_region(state, st.query_params, old['ra'], old['dec'], fov)
        region = navigation.set_gaia(state, st.query_params, source, displayed['provenance'])
    except (ValueError, KeyError, TypeError) as err:
        state['region_notice'] = f'No se pudo seleccionar la fuente Gaia: {err}'
        return
    # Reuse the loaded field when recentering on one of its sources. Dragging later queries as usual.
    state['atlas_gaia_anchor'] = {k: region[k] for k in ('ra', 'dec', 'fov')}
    state.pop('region_notice', None)
    state.pop('solar_choices', None)


def _on_gaia_retry() -> None:
    st.session_state['atlas_gaia_retry'] = True


def _on_constellations() -> None:
    st.session_state['atlas_constellations'] = bool(_component_state().get('constellations'))


def _noop() -> None:
    pass


# ----------------------------------------------------------------------------- what the browser is told
def object_card(region: dict) -> dict | None:
    """Identity of the region's object for the selector (text only; no measurement)."""
    if not region.get("name"):
        return None
    astro = Astrometry.from_dict(region["astrometry"]) if region.get("astrometry") else None
    notes, detail, marker_note = list(region.get("notes") or []), "", "Posición de catálogo."
    if region.get('gaia'):
        alias = (region['gaia'].get('alias') or {}).get('name')
        detail = 'catálogo Gaia DR3 · ICRS · J2016.0' + (f' · {alias} (SIMBAD)' if alias else '')
        if astro.has_proper_motion:
            notes.append('Los exploradores calculan la posición esperada para sus propias fechas con la astrometría Gaia; ese cálculo no es una detección.')
        else:
            notes.append('Sin movimiento propio disponible: los exploradores conservan la posición de catálogo, sin inferir movimiento.')
        return {'name': region['name'], 'detail': detail, 'anchor': region['anchor'], 'notes': notes,
                'marker_note': notes[0], 'gaia_source_id': region['gaia']['source_id'],
                'short_detail': 'J2016.0' + (f' · {alias}' if alias else ''),
                'short_notes': ['Fuente de catálogo; no confirma una detección SPHEREx.']}
    if region.get('solar'):
        p = region['solar']
        detail = f"{p['utc']} UTC · {p['observer_label']}"
        marker_note = 'Posición calculada, no detección.'
        notes.append('Identidad resuelta. Posición calculada para esta fecha y observador; no demuestra datos SPHEREx disponibles.')
        return {'name': region['name'], 'detail': detail, 'anchor': region['anchor'], 'notes': notes, 'marker_note': marker_note,
                'short_detail': p['utc'][:10], 'short_notes': ['Posición calculada para esta fecha, no una detección.']}
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
    state = st.session_state
    held = state.get("atlas_gaia_field")
    anchor = state.get('atlas_gaia_anchor') or held
    moved = (held is None or abs(anchor["fov"] - region["fov"]) > 1e-9 or
             navigation.separation_arcsec(region["ra"], region["dec"], anchor["ra"], anchor["dec"]) > anchor["fov"] * 3600 / 4)
    if moved:
        held = state["atlas_gaia_field"] = {"ra": region["ra"], "dec": region["dec"], "fov": region["fov"]}
        state['atlas_gaia_anchor'] = held
    key = tuple(held[k] for k in ('ra', 'dec', 'fov'))
    job = gaia_atlas.CATALOGUE.poll(key, retry=state.pop('atlas_gaia_retry', False))
    if job['state'] == 'loading':
        state.setdefault('atlas_async_waiting', []).append(('catalogue', key))
    state['atlas_gaia_status'] = job['state']
    if job['state'] != 'ready':
        state.pop('atlas_gaia_displayed', None)
        return [], None, job.get('message', '')
    g = job['result']
    state['atlas_gaia_displayed'] = {'sources': {s['source_id']: s for s in g['sources']}, 'key': g['sha256'],
                                   'provenance': {k: g[k] for k in ('sha256', 'retrieved_utc', 'endpoint')}}
    rows = [{"ra": s["ra"], "dec": s["dec"], "source_id": s["source_id"], "G": s.get("phot_g_mean_mag")}
            for s in g["sources"]]
    note = (f"Gaia DR3 (ESA, posiciones J2016.0): {len(rows)} fuentes en un círculo de {held['fov'] * 60:g}′ centrado en "
            f"RA {held['ra']:.5f}°, Dec {held['dec']:+.5f}°" + (" · truncado a 500 por magnitud G" if g["truncated"] else "")
            + ". Pulse un marcador azul para seleccionar su fuente; no confirma una detección SPHEREx.")
    return rows, g["sha256"], note


def render(level: str) -> None:
    """Draw the selector. ``level`` ("simple" | "scientific") only changes wording."""
    state, params = st.session_state, st.query_params
    state['atlas_async_waiting'] = []
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
        state.pop('atlas_gaia_anchor', None)
        state.pop('atlas_gaia_displayed', None)
        state['atlas_gaia_status'] = 'off'
    alias_loading = False
    if region.get('gaia') and 'alias' not in region['gaia']:
        job = gaia_atlas.ALIASES.poll((region['gaia']['source_id'],))
        alias_loading = job['state'] == 'loading'
        if alias_loading:
            state['atlas_async_waiting'].append(('alias', (region['gaia']['source_id'],)))
        if not alias_loading:
            region['gaia']['alias'] = job.get('result')  # failure never blocks identity/coordinates
    REGION(
        data={"region": {"ra": region["ra"], "dec": region["dec"], "fov": region["fov"]}, "rev": region["rev"],
              "object": object_card(region), "notice": state.get("region_notice"),
              "pick_done": state.get("region_pick_done"), "level": level,
              "local": LOCAL_INDEX, "remote": remote, "remote_query": query,
              "layers": atlas.LAYERS, "layer": state.get("atlas_layer", "2mass"),
              "constellations_on": bool(state.get('atlas_constellations')),
              "constellations": json.loads((config.ROOT / 'data/constellations.json').read_text(encoding='utf8'))['figures'],
              "gaia_on": gaia_on, "gaia": gaia_rows, "gaia_key": gaia_key, "gaia_note": gaia_note,
              "gaia_note_simple": f"{len(gaia_rows)} objetos de catálogo. Pulsa un punto azul para seleccionarlo." if gaia_rows else '',
              "gaia_status": state.get('atlas_gaia_status', 'off'),
              "gaia_region": {k: region[k] for k in ('ra', 'dec', 'fov')},
              "fov_min": config.FOV_MIN_DEG, "fov_max": config.FOV_MAX_DEG,
              "anchor_arcsec": navigation.ANCHOR_TOLERANCE_ARCSEC,
              "spherex_px": config.NOMINAL_PIXEL_SCALE_ARCSEC, "cube_px": 12.9, "aladin": references.ALADIN_JS},
        key=KEY, default={"query": "", "gaia": gaia_on, "layer": state.get("atlas_layer", "2mass"), "region": None},
        on_region_change=_on_region, on_pick_change=_on_pick, on_open_change=_on_open,
        on_query_change=_noop, on_layer_change=_on_layer, on_gaia_change=_on_gaia,
        on_gaia_pick_change=_on_gaia_pick, on_gaia_retry_change=_on_gaia_retry,
        on_constellations_change=_on_constellations)
    solar_controls(region)
    if state['atlas_async_waiting']:
        _poll_jobs()


@st.fragment(run_every=0.7)
def _poll_jobs():
    """Only this tiny fragment polls; a finished job refreshes the component automatically."""
    for kind, key in st.session_state.get('atlas_async_waiting', []):
        jobs = gaia_atlas.CATALOGUE if kind == 'catalogue' else gaia_atlas.ALIASES
        if jobs.poll(key)['state'] != 'loading':
            st.rerun(scope='app')


@st.cache_data(ttl=3600, max_entries=128, show_spinner=False)
def solar_lookup(name):
    return solar_system.lookup(name)


@st.cache_data(ttl=3600, max_entries=128, show_spinner=False)
def solar_position(identity, utc):
    return solar_system.ephemeris(identity, utc)


@st.cache_data(ttl=43200, show_spinner=False)
def comet_table():
    return solar_system.atlas_observations()


def solar_controls(region):
    from datetime import datetime, timezone
    choices = st.session_state.get('solar_choices')
    if choices:
        chosen = st.selectbox('Identidad del objeto', choices, format_func=lambda x: f"{x['name']} · {x['type']} · {x['spkid']}")
        if st.button('Usar esta identidad'):
            try:
                with st.spinner('Calculando la posición con JPL Horizons…', show_time=True):
                    position = solar_position(chosen, datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:00'))
                navigation.set_solar(st.session_state, st.query_params, position)
                st.session_state.pop('solar_choices', None)
                st.session_state.pop('region_notice', None)
                st.rerun()
            except (ValueError, solar_system.ServiceError) as e:
                st.error(str(e))
    p = region.get('solar')
    if not p:
        return
    with st.expander('Fecha y procedencia de la posición', expanded=True):
        st.caption(f"{p['identity']['name']} · {p['utc']} UTC · {p['observer_label']} · {p['frame']}")
        with st.form('solar_epoch'):
            utc = st.text_input('Fecha y hora UTC', value=p['utc'])
            st.caption('Horizons: observador fijo en el geocentro terrestre (500@399). No es la posición aparente desde SPHEREx.')
            if st.form_submit_button('Calcular posición para esta fecha'):
                try:
                    with st.spinner('Calculando la posición para la fecha indicada…', show_time=True):
                        position = solar_position(p['identity'], utc)
                    navigation.set_solar(st.session_state, st.query_params, position)
                    st.rerun()
                except (ValueError, solar_system.ServiceError) as e:
                    st.error(str(e))
        st.caption('Tiempo y Espectro estudian este campo fijo: no siguen la órbita. El cubo combina fechas y no es un espectro del cuerpo móvil. Compartir la región conserva coordenadas, no la efeméride.')
        if p['identity'].get('spkid') == '1004083':
            st.markdown(f"[Observaciones oficiales de 3I/ATLAS]({solar_system.ATLAS_DOC}) · [Tabla original]({solar_system.ATLAS_TABLE})")
            if st.button('Consultar exposiciones oficiales de 3I/ATLAS'):
                try:
                    with st.spinner('Consultando las exposiciones oficiales de 3I/ATLAS en IRSA…', show_time=True):
                        st.session_state['comet_rows'] = comet_table()
                except (solar_system.ServiceError, ValueError) as e:
                    st.error(str(e))
            t = st.session_state.get('comet_rows')
            if t is not None:
                row = st.selectbox('Exposición histórica', list(range(len(t))), format_func=lambda i: str(t[i]['obs_title']))
                r = t[row]
                st.caption(f"{len(t)} exposiciones publicadas. Posición predicha comet_ra/comet_dec, no detección confirmada. Colección {r['obs_collection']}. IRSA advierte señal/ruido baja en muchas longitudes de onda.")
                st.markdown(f"[Acceso oficial a esta observación (DataLink)]({r['access_url']})")
                if st.button('Centrar en la posición histórica de esta exposición'):
                    from astropy.time import Time
                    historical = dict(p, ra=float(r['comet_ra']), dec=float(r['comet_dec']), utc=Time(float(r['t_min']), format='mjd').isot,
                                      kind='irsa_exposure_prediction', observer_label='predicción por exposición publicada por IRSA',
                                      observer=None, frame='ICRS (tabla IRSA)', source=solar_system.ATLAS_TABLE,
                                      exposure=str(r['obs_id']), access_url=str(r['access_url']))
                    navigation.set_solar(st.session_state, st.query_params, historical)
                    st.rerun()


def provenance() -> None:
    """Where the Atlas layers come from (shown on request; the maps are context, never SPHEREx data)."""
    for L in atlas.LAYERS:
        st.markdown(f"- **{L['label']}** — {L['mission']} · `{L['product']}` · {L['bands']} · {L['epoch']} · "
                    f"[HiPS IRSA]({L['url']}/properties)")
    st.markdown('Constelaciones: 88 nombres IAU, figuras tradicionales y posiciones J2000 de '
                '[D3-Celestial / Olaf Frohn](https://github.com/ofrohn/d3-celestial), licencia BSD. '
                'Serpens se dibuja en dos partes. Las líneas unen estrellas y **no son los límites oficiales IAU**. '
                'Se ocultan por debajo de 3° de vista para no saturar el campo científico.')
    sx = atlas.SPHEREX_HIPS
    st.markdown(f"- **SPHEREx**: IRSA publica `{sx['did']}` ({sx['kind']}, versión {sx['release']}). Sus teselas por "
                "plano no siguen la ruta HiPS estándar que carga Aladin Lite 3.8.1, así que no se ofrece como mapa. "
                "El cubo combinado se explora en «Espectro»; ningún mapa del atlas es una secuencia temporal.")
    st.caption("Gaia: catálogo ESA consultado en el servidor para la región. Las posiciones de otras misiones y épocas "
               "no deben compararse con SPHEREx para inferir movimiento o variabilidad.")
