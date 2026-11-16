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
# Decorative glyphs of the two explorers (pictograms of "several dates" and "light by wavelength"; never data).
_FRAMES = ('<svg class="rg-glyph" width="58" height="40" viewBox="0 0 58 40" fill="none" aria-hidden="true">'
           '<rect x="1" y="9" width="16" height="22" rx="3" stroke="currentColor" stroke-width="1.4" opacity=".35"/>'
           '<rect x="20" y="6" width="17" height="28" rx="3" stroke="currentColor" stroke-width="1.4" opacity=".6"/>'
           '<rect x="40" y="3" width="17" height="34" rx="3" stroke="currentColor" stroke-width="1.6"/>'
           '<circle cx="8" cy="22" r="1.8" fill="#c4411c" opacity=".45"/><circle cx="28.5" cy="19" r="2" fill="#c4411c" '
           'opacity=".7"/><circle cx="49" cy="15" r="2.3" fill="#c4411c"/></svg>')
_WAVE = ('<svg class="rg-glyph" width="58" height="40" viewBox="0 0 58 40" fill="none" aria-hidden="true">'
         '<path d="M1 34h56" stroke="currentColor" stroke-width="1" opacity=".3"/>'
         '<path d="M2 25c5 0 6-7 11-7s5 5 10 5 6-19 11-19 5 15 10 15 4 2 12 2" stroke="currentColor" stroke-width="1.7" '
         'stroke-linecap="round" stroke-linejoin="round"/>'
         '<path d="M34 3v31" stroke="#c4411c" stroke-width="1.2" stroke-dasharray="2 2"/></svg>')
_HTML = f"""
<div class="sc-region" data-level="simple">
  <div class="rg-panel">
    <div class="rg-field rg-search">
      <label for="rg-q">Search for an object <span>name or catalogue</span></label>
      <div class="rg-combo">
        <svg width="15" height="15" viewBox="0 0 15 15" fill="none" aria-hidden="true"><circle cx="6.5" cy="6.5" r="4.6"
          stroke="currentColor" stroke-width="1.5"/><path d="m10 10 3.4 3.4" stroke="currentColor" stroke-width="1.5"
          stroke-linecap="round"/></svg>
        <input id="rg-q" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="rg-list"
               placeholder="M101, Andromeda, Barnard, WISE 0855…" maxlength="100" autocomplete="off" spellcheck="false">
        <ul id="rg-list" role="listbox" aria-label="Suggested objects" hidden></ul>
      </div>
      <p class="rg-search-status" role="status" aria-live="polite" hidden></p>
      <p class="rg-object" role="status" aria-live="polite"></p>
      <div class="rg-notes"></div>
    </div>
    <div class="rg-group">
    <p class="rg-label rg-grouptitle">Position in the sky <span class="rg-sci">ICRS · degrees</span></p>
    <p class="rg-help rg-simple">Right ascension (RA) and declination (Dec) are the «longitude» and «latitude» of the sky.
      They fill in by themselves when you search or move the map; you can also type them.</p>
    <div class="rg-coords">
      <div class="rg-field">
        <label for="rg-ra">RA <span>degrees · ICRS</span></label>
        <input id="rg-ra" class="rg-num" type="text" inputmode="decimal" autocomplete="off" spellcheck="false"
               aria-label="Right ascension in degrees" aria-describedby="rg-ra-sexa">
        <span class="rg-sexa rg-sexa-ra" id="rg-ra-sexa"></span><span class="rg-err" role="alert"></span>
      </div>
      <div class="rg-field">
        <label for="rg-dec">Dec <span>degrees · ICRS</span></label>
        <input id="rg-dec" class="rg-num" type="text" inputmode="decimal" autocomplete="off" spellcheck="false"
               aria-label="Declination in degrees" aria-describedby="rg-dec-sexa">
        <span class="rg-sexa rg-sexa-dec" id="rg-dec-sexa"></span><span class="rg-err" role="alert"></span>
      </div>
    </div>
    </div>
    <div class="rg-field rg-group">
      <label for="rg-fov"><b class="rg-simple">Region size</b><b class="rg-sci">Field of view</b>
        <span>diameter · arcminutes</span></label>
      <div class="rg-fovrow">
        <input id="rg-fov" type="range" aria-label="Field of view in arcminutes">
        <div class="rg-fovbox"><input id="rg-fovn" class="rg-num" type="text" inputmode="decimal" autocomplete="off"
             aria-label="Field of view, value in arcminutes"><span aria-hidden="true">′</span></div>
      </div>
      <div class="rg-scale" aria-hidden="true"><span class="rg-fovmin"></span><span class="rg-fovmax"></span></div>
      <p class="rg-fovhint"></p><span class="rg-err" role="alert"></span>
    </div>
  </div>
  <div class="rg-actions">
    <p class="rg-label rg-actions-title">Investigate this area</p>
    <button type="button" class="rg-cta rg-time" data-view="time">{_FRAMES}<b>View over time</b>
      <small>Real images from different dates: does anything change or move?</small>{_ARROW}</button>
    <button type="button" class="rg-cta rg-spectrum" data-view="spectrum">{_WAVE}<b>Explore the spectrum</b>
      <small>Its light in 102 infrared colours: what does it emit or absorb?</small>{_ARROW}</button>
  </div>
  <div class="rg-mapcol">
    <p class="rg-label rg-maptitle"><span class="rg-maptag">Reference map</span>
      <span class="rg-simple">Drag to move around the sky; the wheel or the buttons zoom the view without changing the area.</span>
      <span class="rg-sci">Context atlas (other missions): orientation and choice of centre, not SPHEREx data.</span></p>
    <div class="rg-mapwrap">
      <div class="rg-map" role="application" aria-label="Sky atlas: drag to move the region"></div>
      <div class="rg-tools">
        <select id="rg-layer" class="rg-tool" aria-label="Context map"></select>
        <label class="rg-tool"><input id="rg-gaia" type="checkbox"> Gaia DR3</label>
        <label class="rg-tool"><input id="rg-constellations" type="checkbox"> Constellations</label>
        <button type="button" class="rg-tool rg-wide" title="View 60 degrees without changing the scientific field">Orientation</button>
        <button type="button" class="rg-tool rg-frame" title="Fit the map zoom to the region (does not change the field)">Frame</button>
      </div>
      <div class="rg-chip" aria-hidden="true"></div>
      <div class="rg-status" role="status" hidden><div class="rg-loading-card">
        <span class="rg-activity" aria-hidden="true"></span><span class="rg-map-message"></span>
      </div></div>
      <div class="rg-gaia-status" role="status" aria-live="polite" hidden>
        <div class="rg-loading-card"><span class="rg-activity" aria-hidden="true"></span>
          <span class="rg-gaia-message"></span><span class="rg-loading-detail">Searching for stars in this area of the sky.<br>You can keep moving the map.</span>
          <button type="button" class="rg-gaia-retry" hidden>Retry</button></div>
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
        return [{'id': 'NGC 5866', 'type': 'M102: usual identification, historically disputed', 'aliases': []},
                {'id': 'M101', 'type': 'M102: possible historical duplicate', 'aliases': []}], 'Ambiguous identification'
    rows, status = object_search.remote_suggestions(q)
    failed = status.startswith("Remote suggestions not available")
    solar_rows, solar_failed = [], False
    if not object_search.catalogue_prefix(q) and not re.match(r'^(gaia|wise|2mass)\b', object_search.normalize(q)):
        try:
            solar_rows = solar_system.suggestions(q)
        except solar_system.ServiceError:
            solar_failed = True
    if failed and (solar_failed or not solar_rows):
        raise RuntimeError(status)          # never cache a total outage as an empty catalogue
    # Partial failures are surfaced too; valid results from the other service remain selectable.
    return solar_rows + rows, ('A catalogue is not responding; you can search for the full name.' if failed or solar_failed else '')


SUGGESTIONS = gaia_atlas.Jobs(suggestions, ttl=3600, capacity=128, workers=2)


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
        st.session_state["region_notice"] = f"Invalid region: {err}"


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
                st.session_state['region_notice'] = 'There are several JPL identities; choose the object below the atlas.'
                return
            identity = exact[0] if len(exact) == 1 else candidates[0]
            position = solar_position(identity, datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:00'))
            navigation.set_solar(st.session_state, st.query_params, position)
            st.session_state.pop('region_notice', None)
            st.session_state.pop('solar_choices', None)
            return
        astro_dict, warnings, extended = resolve(name)
    except Exception as err:  # noqa: BLE001 - shown to the user next to the search box
        st.session_state["region_notice"] = f"Could not resolve “{name}”: {err}"
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
        st.session_state["region_notice"] = f"Invalid region: {err}"
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
        state['region_notice'] = f'The Gaia source could not be selected: {err}'
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
    # A fresh edit can retry a failed suggestion request, while successful cache entries remain instant.
    st.session_state['search_retry'] = True


# ----------------------------------------------------------------------------- what the browser is told
def object_card(region: dict) -> dict | None:
    """Identity of the region's object for the selector (text only; no measurement)."""
    if not region.get("name"):
        return None
    astro = Astrometry.from_dict(region["astrometry"]) if region.get("astrometry") else None
    notes, detail, marker_note = list(region.get("notes") or []), "", "Catalogue position."
    if region.get('gaia'):
        alias = (region['gaia'].get('alias') or {}).get('name')
        detail = 'Gaia DR3 catalogue · ICRS · J2016.0' + (f' · {alias} (SIMBAD)' if alias else '')
        if astro.has_proper_motion:
            notes.append('The explorers compute the expected position for their own dates with Gaia astrometry; that calculation is not a detection.')
        else:
            notes.append('No proper motion available: the explorers keep the catalogue position, without inferring motion.')
        return {'name': region['name'], 'detail': detail, 'anchor': region['anchor'], 'notes': notes,
                'marker_note': notes[0], 'gaia_source_id': region['gaia']['source_id'],
                'short_detail': 'J2016.0' + (f' · {alias}' if alias else ''),
                'short_notes': ['Catalogue source; it does not confirm a SPHEREx detection.']}
    if region.get('solar'):
        p = region['solar']
        detail = f"{p['utc']} UTC · {p['observer_label']}"
        marker_note = 'Calculated position, not a detection.'
        notes.append('Identity resolved. Position calculated for this date and observer; it does not show that SPHEREx data are available.')
        return {'name': region['name'], 'detail': detail, 'anchor': region['anchor'], 'notes': notes, 'marker_note': marker_note,
                'short_detail': p['utc'][:10], 'short_notes': ['Position calculated for this date, not a detection.']}
    if region.get("report"):
        detail = "verified sequence · fixed centre and field"
    elif astro is not None:
        detail = f"catalogue J{astro.epoch_jyear:.1f}"
        if astro.has_proper_motion:
            detail = f"proper motion {astro.total_pm_arcsec_yr:.2f}″/yr"
            marker_note = ("Position calculated for today with the catalogue astrometry; the maps are from other "
                           "epochs and the object may appear shifted.")
            notes.insert(0, "The map shows the position calculated for today. Each explorer calculates it for the "
                            "dates of its own observations; a calculated position is not a detection.")
    if region.get("extended"):
        notes.append("Catalogued centre of an extended object: the field may show only a part of it.")
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
    note = (f"Gaia DR3 (ESA, J2016.0 positions): {len(rows)} sources in a circle of {held['fov'] * 60:g}′ centred on "
            f"RA {held['ra']:.5f}°, Dec {held['dec']:+.5f}°" + (" · truncated to 500 by G magnitude" if g["truncated"] else "")
            + ". Press a blue marker to select its source; it does not confirm a SPHEREx detection.")
    return rows, g["sha256"], note


def render(level: str) -> None:
    """Draw the selector. ``level`` ("simple" | "scientific") only changes wording."""
    state, params = st.session_state, st.query_params
    state['atlas_async_waiting'] = []
    region = navigation.get_region(state, params)
    comp = _component_state()
    query = str(comp.get("query") or "")
    remote, search_state, search_message = [], 'idle', ''
    if object_search.can_suggest(query):
        job = SUGGESTIONS.poll((query.strip(),))
        if state.pop('search_retry', False) and job['state'] == 'error':
            job = SUGGESTIONS.poll((query.strip(),), retry=True)
        search_state = job['state']
        if search_state == 'loading':
            state['atlas_async_waiting'].append(('search', (query.strip(),)))
        elif search_state == 'ready':
            remote, search_message = job['result']
        else:
            search_message = 'Suggestions are not available. Press Enter to search for the full name.'
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
              "search_state": search_state, "search_message": search_message,
              "layers": atlas.LAYERS, "layer": state.get("atlas_layer", "2mass"),
              "constellations_on": bool(state.get('atlas_constellations')),
              "constellations": json.loads((config.ROOT / 'data/constellations.json').read_text(encoding='utf8'))['figures'],
              "gaia_on": gaia_on, "gaia": gaia_rows, "gaia_key": gaia_key, "gaia_note": gaia_note,
              "gaia_note_simple": f"{len(gaia_rows)} catalogue objects. Press a blue dot to select it." if gaia_rows else '',
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
    solar_controls(region, level)
    if state['atlas_async_waiting']:
        _poll_jobs()


@st.fragment(run_every=0.7)
def _poll_jobs():
    """Only this tiny fragment polls; a finished job refreshes the component automatically."""
    for kind, key in st.session_state.get('atlas_async_waiting', []):
        jobs = SUGGESTIONS if kind == 'search' else gaia_atlas.CATALOGUE if kind == 'catalogue' else gaia_atlas.ALIASES
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


def solar_controls(region, level='scientific'):
    from datetime import datetime, timezone
    sci = level == 'scientific'
    choices = st.session_state.get('solar_choices')
    if choices:
        chosen = st.selectbox('Object identity', choices, format_func=lambda x: f"{x['name']} · {x['type']} · {x['spkid']}")
        if st.button('Use this identity'):
            try:
                with st.spinner('Computing the position with JPL Horizons…', show_time=True):
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
    with st.expander('Date and provenance of the position' if sci else 'Date of the object', expanded=True):
        st.caption(f"{p['identity']['name']} · {p['utc']} UTC · {p['observer_label']}" + (f" · {p['frame']}" if sci else ''))
        with st.form('solar_epoch'):
            utc = st.text_input('UTC date and time', value=p['utc'])
            if sci:
                st.caption('Horizons: observer fixed at the Earth\'s geocentre (500@399). This is not the apparent position from SPHEREx.')
            if st.form_submit_button('Calculate position for this date'):
                try:
                    with st.spinner('Calculating the position for the given date…', show_time=True):
                        position = solar_position(p['identity'], utc)
                    navigation.set_solar(st.session_state, st.query_params, position)
                    st.rerun()
                except (ValueError, solar_system.ServiceError) as e:
                    st.error(str(e))
        st.caption('Time looks for exposures along the object\'s trajectory. Spectrum keeps the field fixed: '
                   'the cube combines dates and is not a spectrum of the moving body. Sharing coordinates does not keep the ephemeris.' if sci else
                   'In Time you can look for images that follow the path of the object. Spectrum shows this fixed area of the sky.')
        if p['identity'].get('spkid') == '1004083':
            st.markdown(f"[Official 3I/ATLAS observations]({solar_system.ATLAS_DOC}) · [Original table]({solar_system.ATLAS_TABLE})")
            if st.button('Query the official 3I/ATLAS exposures'):
                try:
                    with st.spinner('Querying the official 3I/ATLAS exposures at IRSA…', show_time=True):
                        st.session_state['comet_rows'] = comet_table()
                except (solar_system.ServiceError, ValueError) as e:
                    st.error(str(e))
            t = st.session_state.get('comet_rows')
            if t is not None:
                row = st.selectbox('Historical exposure', list(range(len(t))), format_func=lambda i: str(t[i]['obs_title']))
                r = t[row]
                st.caption(f"{len(t)} exposures published. Predicted position comet_ra/comet_dec, not a confirmed detection. Collection {r['obs_collection']}. IRSA warns of low signal-to-noise at many wavelengths." if sci else
                           f"{len(t)} observations published. The predicted position does not confirm that the comet is visible in the image.")
                st.markdown(f"[Official access to this observation (DataLink)]({r['access_url']})")
                if st.button('Centre on the historical position of this exposure'):
                    from astropy.time import Time
                    historical = dict(p, ra=float(r['comet_ra']), dec=float(r['comet_dec']), utc=Time(float(r['t_min']), format='mjd').isot,
                                      kind='irsa_exposure_prediction', observer_label='per-exposure prediction published by IRSA',
                                      observer=None, frame='ICRS (IRSA table)', source=solar_system.ATLAS_TABLE,
                                      exposure=str(r['obs_id']), access_url=str(r['access_url']))
                    navigation.set_solar(st.session_state, st.query_params, historical)
                    st.rerun()


def provenance() -> None:
    """Where the Atlas layers come from (shown on request; the maps are context, never SPHEREx data)."""
    for L in atlas.LAYERS:
        st.markdown(f"- **{L['label']}** — {L['mission']} · `{L['product']}` · {L['bands']} · {L['epoch']} · "
                    f"[HiPS IRSA]({L['url']}/properties)")
    st.markdown('Constellations: 88 IAU names, traditional figures and J2000 positions from '
                '[D3-Celestial / Olaf Frohn](https://github.com/ofrohn/d3-celestial), BSD licence. '
                'Serpens is drawn in two parts. The lines join stars and **are not the official IAU boundaries**. '
                'They are hidden below 3° of view so as not to crowd the scientific field.')
    sx = atlas.SPHEREX_HIPS
    st.markdown(f"- **SPHEREx**: IRSA publishes `{sx['did']}` ({sx['kind']}, version {sx['release']}). Its per-plane tiles "
                "do not follow the standard HiPS path that Aladin Lite 3.8.1 loads, so it is not offered as a map. "
                "The combined cube is explored in «Spectrum»; no atlas map is a time sequence.")
    st.caption("Gaia: ESA catalogue queried on the server for the region. Positions from other missions and epochs "
               "must not be compared with SPHEREx to infer motion or variability.")
