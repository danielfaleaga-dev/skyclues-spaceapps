"""SkyClues - Streamlit entry point.

Run:  streamlit run app.py

One active sky region (``skyclues.navigation``), chosen in the «Region» view by name, coordinates or
on the Atlas, and two scientific explorers that read it: «Time» (individual observations of
different dates) and «Spectrum» (the combined DR1 cube in 102 channels). The presentation level
(Simple / Scientific) changes wording and how much detail is shown; it is never an input of a
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
    st.error("Unknown explorer in URL")
    st.stop()
if "canal" in qp and (not str(qp["canal"]).isdigit() or not 1 <= int(qp["canal"]) <= 102):
    st.error("URL channel outside 1–102")
    st.stop()

# ---------------------------------------------------------------- view and level (plain session state)
if "nav" not in state:
    state["nav"] = theme.NAV_LABEL[navigation.initial_view(qp)]
if "level" not in state:
    state["level"] = "Scientific" if qp.get("nivel") == "cientifico" else "Simple"
request = state.pop("view_request", None)
if request in navigation.VIEWS:
    if request == "time" and state["nav"] != "Time":
        state["time_autorun"] = True          # an explicit action: opening Time searches the region
    state["nav"] = theme.NAV_LABEL[request]


def _nav_changed() -> None:
    if state.get("nav") == "Time":
        state["time_autorun"] = True


region = navigation.get_region(state, qp)

with st.container(horizontal=True, vertical_alignment="center", horizontal_alignment="distribute", key="sc_header"):
    st.html(theme.brand_html(), width="content")
    st.segmented_control("View", list(theme.NAV), key="nav", required=True, label_visibility="collapsed",
                         on_change=_nav_changed, width="content")
    st.segmented_control("Detail level", list(theme.LEVELS), key="level", required=True,
                         label_visibility="collapsed", width="content",
                         help="Simple explains the essentials. Scientific adds parameters, units, tables and methods. "
                              "The data, the region and the results are the same.")

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
            "region", "Region · choose where to look", "Which area of the sky do you want to investigate?",
            "SkyClues opens real infrared observations from NASA's SPHEREx space telescope. Pick an object or "
            "an area of the sky and find out whether something changed between dates or what infrared light it emits.",
            '<ol class="sc-steps" aria-label="What you can do">'
            '<li data-v="region"><i></i>Search for a name or move the map</li>'
            '<li data-v="time"><i></i>Time: does anything change between dates?</li>'
            '<li data-v="spectrum"><i></i>Spectrum: what infrared light does it emit?</li></ol>')
    else:
        theme.hero(
            "region", "Sky region", "Centre and field of the exploration",
            "Name, coordinates and atlas edit a single region (ICRS centre and field of view). The circle is the "
            "scientific field, of fixed angular diameter; zooming the map does not change it.")
    # Featured example: the project's strongest result, one compact row under the header (same lookup as the search box).
    with st.container(key="featured_atlas_block"):
        st.html('<p class="sc-eyebrow">' + ("Featured · a comet from another star" if level == "simple"
                                            else "Featured · interstellar object") + "</p>")
        with st.container(horizontal=True, vertical_alignment="center"):
            if level == "simple":
                st.markdown("**3I/ATLAS** comes from outside our Solar System: only the third visitor of its kind ever "
                            "detected. SPHEREx photographed it in 2025. See how far it moved between images taken hours "
                            "apart, measured against the fixed stars.")
            else:
                st.markdown("**3I/ATLAS** (C/2025 N1), an interstellar comet. Search its SPHEREx exposures along the JPL "
                            "Horizons trajectory and measure its displacement between same-detector exposures, registered "
                            "on stationary reference stars, with its uncertainty.")
            st.button("Follow 3I/ATLAS across the sky", key="featured_atlas", type="primary",
                      on_click=region_ui.open_atlas_comet)
    region_ui.render(level)

    examples = [(stem, title) for stem, title in config.VALIDATED_EXAMPLES.items() if time_page.saved_path(stem)]
    if examples:
        st.html('<div style="height:1.4rem"></div><p class="sc-eyebrow">'
                + ("Examples ready to explore" if level == "simple" else "Verified sequences") + "</p>")
        with st.container(horizontal=True, vertical_alignment="center"):
            for stem, title in examples:
                st.button(title, key=f"example_{stem}", on_click=time_page.open_saved, args=(stem, title.split(" · ")[0]))
        st.caption("Real observations already checked: they open in «Time» without repeating the archive search."
                   if level == "scientific" else
                   "Real SPHEREx images already checked: they open in «Time» instantly.")
    if level == "scientific":
        with st.expander("Provenance of the atlas maps"):
            region_ui.provenance()
elif view == "time":
    navigation.write_url(qp, region, view)
    time_page.render(level)
else:
    spectrum_page.render(level)
    if level == "scientific":
        st.caption(f"Published cube: {config.CUBE_RELEASE_ID} · DOI {config.CUBE_DOI}. Updating SIA2 observations does not "
                   "modify this cube.")
