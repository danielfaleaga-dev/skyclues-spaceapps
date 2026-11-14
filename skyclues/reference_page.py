"""Shared Streamlit fragment: reference controls never rerun the scientific viewer."""
from __future__ import annotations

import streamlit as st

from . import references as ref
from .reference_view import viewer_html
from .targets import validate_coordinates, validate_fov_deg


@st.cache_data(ttl=12 * 3600, max_entries=32, show_spinner=False)
def cached_gaia(ra: float, dec: float, fov: float) -> dict:
    return ref.fetch_gaia(ra, dec, fov)


@st.fragment
def render(ra: float, dec: float, fov: float, *, key: str) -> None:
    ra, dec = validate_coordinates(ra, dec)
    fov = validate_fov_deg(fov)
    with st.expander("Referencias astronómicas · Gaia / WISE"):
        st.caption(f"Misma región: ICRS RA {ra:.6f}°, Dec {dec:+.6f}° · diámetro {60*fov:g}′. "
                   "El centro y el campo se cambian en el explorador.")
        if not st.toggle("Abrir visor de referencias", key=f"{key}_open"):
            return
        st.info("Referencia independiente: Gaia es un catálogo; AllWISE es una imagen infrarroja de otra misión "
                "(era WISE 2010–2011, producto combinado; época local no verificada). W1 ≈ 3.4 µm / W2 ≈ 4.6 µm; "
                "resolución WISE ≈ 6″, diferente de la resolución y bandas de SPHEREx. Una diferencia visual "
                "no demuestra variabilidad. No se restan imágenes ni se asocian fuentes automáticamente.")
        use_gaia = st.checkbox("Consultar Gaia DR3 en este campo", key=f"{key}_query")
        result, error = None, None
        if use_gaia:
            if st.button("Reintentar / actualizar Gaia", key=f"{key}_retry"):
                cached_gaia.clear(ra, dec, fov)
            try:
                with st.spinner("Consultando Gaia DR3 (máximo 500 fuentes)…"):
                    result = cached_gaia(ra, dec, fov)
            except ref.ReferenceError as err:
                error = str(err)
                st.warning(error)
        epoch = st.number_input("Época de la posición calculada (año juliano TCB)", min_value=2000.0,
                                max_value=2050.0, value=2026.0, step=0.1, key=f"{key}_epoch")
        st.caption("Círculos cian: Gaia DR3 J2016.0. Cruces ámbar opcionales: posición calculada aproximada "
                   "con RA, Dec, ref_epoch, pmra (= μα cos δ) y pmdec; sin paralaje, velocidad radial, "
                   "aceleración perspectiva ni incertidumbre propagada. No es una detección SPHEREx. "
                   "Fuentes sin movimiento propio: solo posición de catálogo.")
        if result:
            st.caption(f"{len(result['sources'])} fuentes · consulta {result['retrieved_utc']} · "
                       "selección circular en J2016.0, ordenada por magnitud G; no incluye fuentes externas "
                       "que pudieran entrar en el campo en otra época. La ausencia en Gaia no descarta una fuente infrarroja.")
            if result["truncated"]:
                st.warning("Campo truncado a 500 fuentes por magnitud G. No es un censo completo.")
            with st.expander("Procedencia de Gaia y tabla de parámetros"):
                st.markdown(f"[ESA Gaia DR3]({ref.GAIA_DOC}) · `{ref.GAIA_TABLE}`. "
                            "RA/Dec en grados; errores/paralaje en mas; pm en mas/año; velocidad radial en km/s; G en mag; RUWE adimensional.")
                st.dataframe(result["sources"], hide_index=True)
                st.code(result["query"], language="sql")
                st.caption(f"SHA-256 de la respuesta CSV: {result['sha256']}")
        st.iframe(viewer_html(ra, dec, fov, result, epoch, error), height=760)
        st.markdown(f"AllWISE/IPAC: [W1]({ref.WISE_URLS['W1']}/properties) · "
                    f"[W2]({ref.WISE_URLS['W2']}/properties) · "
                    "[suplemento AllWISE](https://wise2.ipac.caltech.edu/docs/release/allwise/expsup/) · "
                    "[Aladin Lite 3.8.1 / CDS](https://github.com/cds-astro/aladin-lite/releases/tag/v3.8.1). "
                    "HiPS JPEG para contexto visual, sin uso fotométrico; no tiene una época única por fuente.")
