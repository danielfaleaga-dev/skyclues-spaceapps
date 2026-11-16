"""SkyClues - Streamlit entry point.

Run:  streamlit run app.py

One active sky region (``skyclues.navigation``), chosen in the «Región» view by name, coordinates or
on the Atlas, and two scientific explorers that read it: «Tiempo» (individual observations of
different dates) and «Espectro» (the combined DR1 cube in 102 channels). The presentation level
(Sencillo / Científico) changes wording and how much detail is shown; it is never an input of a
calculation.
"""

from __future__ import annotations

import os

import streamlit as st
import streamlit.components.v1 as components

from skyclues import config, navigation, region_ui, release_ui, spectrum_page, theme, time_page

st.set_page_config(page_title="SkyClues", page_icon=str(theme.BRAND_DIR / "favicon.png"), layout="wide",
                   initial_sidebar_state="collapsed")
release_ui.releases.configure_cube_release(os.environ.get("SKYCLUES_CUBE_RELEASE", release_ui.releases.ACTIVE_CUBE))
theme.inject()

state, qp = st.session_state, st.query_params

# ---------------------------------------------------------------- link parameters (checked once, never clamped)
if qp.get("explorer", "temporal") not in ("temporal", "espectral"):
    st.error("Explorador de URL desconocido")
    st.stop()
if "canal" in qp and (not str(qp["canal"]).isdigit() or not 1 <= int(qp["canal"]) <= 102):
    st.error("Canal de URL fuera de 1–102")
    st.stop()

# ---------------------------------------------------------------- view and level (plain session state)
if "nav" not in state:
    state["nav"] = theme.NAV_LABEL[navigation.initial_view(qp)]
if "level" not in state:
    state["level"] = "Científico" if qp.get("nivel") == "cientifico" else "Sencillo"
request = state.pop("view_request", None)
if request in navigation.VIEWS:
    if request == "time" and state["nav"] != "Tiempo":
        state["time_autorun"] = True          # an explicit action: opening Time searches the region
    state["nav"] = theme.NAV_LABEL[request]


def _nav_changed() -> None:
    if state.get("nav") == "Tiempo":
        state["time_autorun"] = True


region = navigation.get_region(state, qp)

with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute", key="sc_header"):
    st.html(theme.brand_html(), width="content")
    st.segmented_control("Vista", list(theme.NAV), key="nav", required=True, label_visibility="collapsed",
                         on_change=_nav_changed, width="content")
    st.segmented_control("Nivel de detalle", list(theme.LEVELS), key="level", required=True,
                         label_visibility="collapsed", width="content",
                         help="Sencillo explica lo esencial. Científico añade parámetros, unidades, tablas y métodos. "
                              "Los datos, la región y los resultados son los mismos.")

view = theme.NAV.get(state.get("nav"), "region")
level = theme.level()
if view != "spectrum":
    spectrum_page.stash_state()        # keep the channel, the pick and the mode while another view is shown
theme.area_flag(view)                  # the visible area gives its accent to the shared styles

if state.get("_last_view") not in (None, view):
    # A new view starts at its top, where its loading indicator is drawn: otherwise a long wait is shown
    # as a dimmed copy of the previous view with the indicator out of sight.
    with st.container(key="sc_scroll_top"):
        components.html("<script>const m=window.parent.document.querySelector('[data-testid=\"stMain\"]');"
                        "if(m)m.scrollTo(0,0);window.parent.scrollTo(0,0);</script>", height=0)
state["_last_view"] = view

# ---------------------------------------------------------------- views
if view == "region":
    navigation.write_url(qp, region, view)
    for e in state.pop("region_errors", []):
        st.error(e)
    if level == "simple":
        theme.hero(
            "region", "Región · elige dónde mirar", "¿Qué zona del cielo quieres investigar?",
            "SkyClues abre observaciones infrarrojas reales del telescopio espacial SPHEREx (NASA). Elige un objeto o "
            "una zona del cielo y descubre si algo cambió entre fechas o qué luz infrarroja emite.",
            '<ol class="sc-steps" aria-label="Qué puedes hacer">'
            '<li data-v="region"><i></i>Busca un nombre o mueve el mapa</li>'
            '<li data-v="time"><i></i>Tiempo: ¿algo cambia entre fechas?</li>'
            '<li data-v="spectrum"><i></i>Espectro: ¿qué luz infrarroja emite?</li></ol>')
    else:
        theme.hero(
            "region", "Región del cielo", "Centro y campo de la exploración",
            "Nombre, coordenadas y atlas editan una única región (centro ICRS y campo de visión). El círculo es el "
            "campo científico, de diámetro angular fijo; el zoom del mapa no lo modifica.")
    region_ui.render(level)

    examples = [(stem, title) for stem, title in config.VALIDATED_EXAMPLES.items() if time_page.saved_path(stem)]
    if examples:
        st.html('<div style="height:1.4rem"></div><p class="sc-eyebrow">'
                + ("Ejemplos listos para explorar" if level == "simple" else "Secuencias verificadas") + "</p>")
        with st.container(horizontal=True, vertical_alignment="center"):
            for stem, title in examples:
                st.button(title, key=f"example_{stem}", on_click=time_page.open_saved, args=(stem, title.split(" · ")[0]))
        st.caption("Observaciones reales ya comprobadas: se abren en «Tiempo» sin repetir la búsqueda en el archivo."
                   if level == "scientific" else
                   "Imágenes reales de SPHEREx ya comprobadas: se abren en «Tiempo» al instante.")
    if level == "scientific":
        with st.expander("Procedencia de los mapas del atlas"):
            region_ui.provenance()
elif view == "time":
    navigation.write_url(qp, region, view)
    time_page.render(level)
else:
    spectrum_page.render(level)
    if level == "scientific":
        st.caption(f"Cubo publicado: {config.CUBE_RELEASE_ID} · DOI {config.CUBE_DOI}. Actualizar observaciones SIA2 no "
                   "modifica este cubo.")
