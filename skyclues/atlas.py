"""Atlas: interactive sky locator (Aladin Lite) that feeds the same region to both explorers.

The Atlas is not a third explorer and not a measuring instrument: it shows authentic
HiPS maps of other missions to help choose a centre and a field of view. The chosen
region is written to the common region state (URL parameters ra/dec/fov) that Time
Explorer and Spectrum Explorer already read.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from astropy.time import Time

from . import config, navigation, references
from .astrometry import Astrometry
from .targets import validate_coordinates, validate_fov_deg

IRSA_HIPS = "https://irsa.ipac.caltech.edu/data/hips"
#: Official HiPS image surveys mirrored by NASA/IPAC IRSA (properties verified 2026-11-14, HTTP 200).
LAYERS = [
    {"id": "2mass", "label": "2MASS J·H·K (color)", "url": f"{IRSA_HIPS}/CDS/2MASS/Color", "format": "jpeg",
     "mission": "2MASS (UMass/IPAC)", "product": "ivo://CDS/P/2MASS/color", "bands": "J 1.23, H 1.66, Ks 2.16 µm",
     "epoch": "observaciones 1997–2001",
     "note": "Infrarrojo cercano, la región espectral más próxima a los detectores D1–D3 de SPHEREx."},
    {"id": "allwise", "label": "AllWISE W4·W2·W1 (color)", "url": f"{IRSA_HIPS}/CDS/AllWISE/RGB-W4-W2-W1",
     "format": "jpeg", "mission": "WISE/NEOWISE (NASA/JPL/IPAC)", "product": "ivo://CDS/P/allWISE/color",
     "bands": "W1 3.4, W2 4.6, W4 22 µm", "epoch": "era WISE 2010–2011",
     "note": "Composición de color de otra misión; no son datos SPHEREx."},
    {"id": "w1", "label": "AllWISE W1 (3.4 µm)", "url": references.WISE_URLS["W1"], "format": "jpeg",
     "mission": "WISE/NEOWISE", "product": "ivo://CDS/P/allWISE/W1", "bands": "W1 3.4 µm",
     "epoch": "era WISE 2010–2011", "note": "Imagen de contexto, sin uso fotométrico."},
    {"id": "w2", "label": "AllWISE W2 (4.6 µm)", "url": references.WISE_URLS["W2"], "format": "jpeg",
     "mission": "WISE/NEOWISE", "product": "ivo://CDS/P/allWISE/W2", "bands": "W2 4.6 µm",
     "epoch": "era WISE 2010–2011", "note": "Imagen de contexto, sin uso fotométrico."},
    {"id": "dss", "label": "DSS2 (color, óptico)", "url": f"{IRSA_HIPS}/CDS/DSS2/color", "format": "jpeg",
     "mission": "Digitized Sky Survey (STScI)", "product": "ivo://CDS/P/DSS2/color", "bands": "óptico (placas B/R)",
     "epoch": "placas fotográficas ≈1950–1990", "note": "Óptico; útil para orientarse, no comparable con SPHEREx."},
]
#: Official SPHEREx global HiPS, inspected but not offered as a map layer (see PROJECT_STATE).
SPHEREX_HIPS = {"did": "ivo://IPAC/P/SPHEREx/DR1/cube", "url": f"{IRSA_HIPS}/SPHEREx/spherex_allsky_cube",
                "release": "2026-11-01", "kind": "cubo HiPS de 102 planos PNG (0.75–5.0 µm), producto combinado"}
FOV_PRESETS_ARCMIN = (3, 6, 12, 18, 30)

ATLAS = st.components.v2.component(
    "sky_atlas",
    html=('<div class="sc-atlas"><div class="row"><label>Mapa <select class="layer" aria-label="Capa del atlas"></select>'
          '</label><label>Campo de la región <select class="fov" aria-label="Diámetro de la región"></select></label>'
          '<button class="fit" disabled>Ajustar al zoom</button>'
          '<button class="use" disabled>Seleccionar esta región</button></div>'
          '<div class="map" aria-label="Atlas del cielo"></div>'
          '<div class="centre" role="status"></div><div class="view"></div><div class="warn"></div>'
          '<div class="note"></div><div class="layerinfo"></div><div class="status" role="status"></div></div>'),
    css=(".sc-atlas{font:14px system-ui,sans-serif;color:#172433}.sc-atlas .row{display:flex;gap:12px;flex-wrap:wrap;"
         "align-items:center;margin:4px 0 8px}.sc-atlas select,.sc-atlas button{font:inherit;padding:5px 8px}"
         ".sc-atlas .use{background:#1f5fbf;color:#fff;border:1px solid #1f5fbf;border-radius:4px;cursor:pointer}"
         ".sc-atlas .fit{border:1px solid #9aa6b5;border-radius:4px;background:#f5f7fa;cursor:pointer}"
         ".sc-atlas .map{width:100%;height:520px;position:relative;background:#10141a}"
         ".sc-atlas .centre{font-variant-numeric:tabular-nums;margin-top:6px;font-weight:600}"
         ".sc-atlas .view,.sc-atlas .layerinfo,.sc-atlas .status,.sc-atlas .note{font-size:13px;color:#435266;margin:2px 0}"
         ".sc-atlas .warn{font-size:13px;color:#7a5300}.sc-atlas .err{color:#a32626}"),
    js=Path(__file__).with_name("atlas_component.js").read_text(encoding="utf-8"),
    isolate_styles=False,
)


def object_position_now(astro: Astrometry) -> tuple[float, float]:
    """Position of a catalogued object today (calculated, not observed)."""
    if astro.has_proper_motion:
        return astro.position_at(Time.now())
    return astro.ra_deg, astro.dec_deg


def render() -> None:
    state, params = st.session_state, st.query_params
    region = navigation.current_region(state, params)
    view = state.get("atlas_view")
    if view is None:
        view = state["atlas_view"] = {**region, "nonce": 0}
    st.caption("Atlas: mapas HiPS auténticos de otras misiones para orientarse y elegir una región. Arrastre para "
               "moverse, rueda o botones para el zoom, clic para centrar. El círculo amarillo es la región que se "
               "enviará a los exploradores; no es una medida ni una imagen SPHEREx.")
    gaia_rows, gaia_key = [], None
    if st.checkbox("Mostrar Gaia DR3 en la región seleccionada (ESA, J2016.0, máx. 500 fuentes)", key="atlas_gaia"):
        from .reference_page import cached_gaia
        try:
            g = cached_gaia(region["ra"], region["dec"], region["fov"])
            gaia_rows = [{"ra": s["ra"], "dec": s["dec"], "source_id": s["source_id"], "G": s.get("phot_g_mean_mag")}
                         for s in g["sources"]]
            gaia_key = f"{g['sha256']}"
            st.caption(f"Gaia DR3: {len(gaia_rows)} fuentes del círculo seleccionado (posiciones J2016.0)"
                       + (" · truncado a 500 por magnitud G" if g["truncated"] else "")
                       + ". Seleccione otra región para consultar otro campo.")
        except references.ReferenceError as err:
            st.warning(f"{err} El atlas sigue disponible sin Gaia.")
    marker = view.get("marker")
    result = ATLAS(data={"ra": view["ra"], "dec": view["dec"], "fov": view["fov"], "nonce": view["nonce"],
                         "layers": LAYERS, "default_layer": "2mass", "fov_presets": list(FOV_PRESETS_ARCMIN),
                         "fov_min": config.FOV_MIN_DEG, "fov_max": config.FOV_MAX_DEG, "aladin": references.ALADIN_JS,
                         "gaia": gaia_rows, "gaia_key": gaia_key, "marker": marker},
                   key="sky_atlas", on_select_change=lambda: None)
    pick = result.select if result is not None else None
    if pick:
        try:
            ra, dec = validate_coordinates(pick["ra"], pick["dec"])
            fov = validate_fov_deg(round(float(pick["fov"]), 4))
        except (ValueError, TypeError, KeyError) as err:
            st.error(f"Selección no válida: {err}")
        else:
            astro = None
            if marker and marker.get("astrometry"):
                # Keeping the object's catalogue astrometry only while the centre was not moved away.
                if _sep_arcsec(ra, dec, marker["ra"], marker["dec"]) <= 1.0:
                    astro = marker["astrometry"]
            navigation.set_region(state, params, ra, dec, fov, source="Atlas", astrometry=astro)
            state["atlas_view"] = {"ra": ra, "dec": dec, "fov": fov, "nonce": view["nonce"], "marker": marker}
            region = navigation.current_region(state, params)
    sel = state.get("sky_region")
    if sel and sel.get("source") == "Atlas":
        st.success(f"Región seleccionada en el atlas: RA {sel['ra']:.6f}°, Dec {sel['dec']:+.6f}° · diámetro "
                   f"{sel['fov'] * 60:g}′ ({sel['fov']:g}°). Los campos de coordenadas de ambos exploradores usan "
                   "ahora esta región.")
        if sel.get("astrometry"):
            st.caption("Centro sobre el objeto buscado: al abrirlo se conserva su astrometría de catálogo "
                       "(posición calculada para cada fecha).")
        c1, c2 = st.columns(2)
        c1.button("Abrir región en Time Explorer", key="atlas_to_time", type="primary",
                  on_click=navigation.open_region, args=("temporal",))
        c2.button("Abrir región en Spectrum Explorer", key="atlas_to_spectrum",
                  on_click=navigation.open_region, args=("espectral",))
    with st.expander("Procedencia de las capas"):
        for L in LAYERS:
            st.markdown(f"- **{L['label']}** — {L['mission']} · `{L['product']}` · {L['bands']} · {L['epoch']} · "
                        f"[HiPS IRSA]({L['url']}/properties)")
        st.markdown(f"- **SPHEREx**: IRSA publica `{SPHEREX_HIPS['did']}` ({SPHEREX_HIPS['kind']}, versión "
                    f"{SPHEREX_HIPS['release']}). Sus teselas por plano no siguen la ruta HiPS estándar que carga "
                    "Aladin Lite 3.8.1, así que no se ofrece como mapa aquí. El cubo combinado se explora en Spectrum "
                    "Explorer; ningún mapa del atlas es una secuencia temporal.")
        st.caption("Gaia: catálogo ESA consultado en el servidor para el círculo seleccionado. Las posiciones de otras "
                   "misiones y épocas no deben compararse con SPHEREx para inferir movimiento o variabilidad.")


def _sep_arcsec(ra1, dec1, ra2, dec2) -> float:
    from .geometry import separation_deg
    return float(separation_deg(ra1, dec1, ra2, dec2)) * 3600


def show_object(astro: Astrometry) -> None:
    """Centre the atlas on a resolved object (position calculated for today)."""
    ra, dec = object_position_now(astro)
    view = st.session_state.get("atlas_view") or {"nonce": 0}
    note = ("Posición calculada para hoy con la astrometría del catálogo; los mapas son de otras épocas y el objeto "
            "puede aparecer desplazado." if astro.has_proper_motion else "Posición de catálogo.")
    region = navigation.current_region(st.session_state, st.query_params)
    st.session_state["atlas_view"] = {"ra": ra, "dec": dec, "fov": region["fov"], "nonce": view["nonce"] + 1,
                                      "marker": {"ra": ra, "dec": dec, "label": astro.name, "note": note,
                                                 "astrometry": astro.to_dict()}}


def show_region(ra: float, dec: float, fov: float) -> None:
    view = st.session_state.get("atlas_view") or {"nonce": 0}
    st.session_state["atlas_view"] = {"ra": ra, "dec": dec, "fov": fov, "nonce": view["nonce"] + 1, "marker": None}


__all__ = ["LAYERS", "SPHEREX_HIPS", "render", "show_object", "show_region", "object_position_now"]
