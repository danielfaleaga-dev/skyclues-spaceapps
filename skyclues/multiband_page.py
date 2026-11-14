"""Spectrum Explorer · multiband false-colour mode (Streamlit section).

Called from ``spectrum_page.render`` when the user chooses the multiband mode. It shares the
page's region (centre, FOV), its channel table and its cached channel maps, so switching mode
re-reads nothing that is already in memory and the region is never changed here.
"""

from __future__ import annotations

import json

import streamlit as st

from . import config
from . import multiband as mb
from . import multiband_view as mv
from . import spectral_cube as sc

MODES = ["Un canal", "Composición multibanda (RGB)"]
STRETCH_LABELS = {"Independiente por canal": "independiente", "Común a los tres canales (MJy/sr)": "comun"}
#: widget keys of this section kept while the single-channel mode is shown.
STATE_KEYS = ("mb_R", "mb_G", "mb_B", "mb_stretch")
ROLE_KEYS = {r: f"mb_{r}" for r in mb.ROLES}
_SHADOW = "_keep_"


# Streamlit forgets the value of a widget that is not drawn in a run. Re-assigning the key while
# the widget is hidden keeps the value on the server but NOT on screen (the re-created widget would
# show its default). So the values are copied to plain keys while the widget is hidden and given
# back just before the widget is created again, which updates both server and screen.
def stash(keys) -> None:
    """Copy the values of widgets that are not drawn in this run (call before they disappear)."""
    for k in keys:
        if k in st.session_state:
            st.session_state[_SHADOW + k] = st.session_state[k]


def restore(keys) -> None:
    """Give back stashed values to widgets about to be created (Session State API, same run)."""
    for k in keys:
        saved = st.session_state.pop(_SHADOW + k, None)
        if saved is not None:          # even if the key lingers: only a write in this run reaches the screen
            st.session_state[k] = saved


def kept(key: str, default):
    """Initial value for a widget created with an explicit default (restoring it through the
    Session State API would raise Streamlit's duplicated-default warning)."""
    return st.session_state.get(_SHADOW + key, default)


@st.cache_resource(show_spinner=False, max_entries=16)
def cached_composite(ra: float, dec: float, fov: float, numbers: tuple[int, int, int], mode: str,
                     _channels, _map_fn) -> mb.Composite:
    return mb.build(ra, dec, fov, _channels, dict(zip(mb.ROLES, numbers)), mode, map_fn=_map_fn)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_png(ra: float, dec: float, fov: float, numbers: tuple[int, int, int], mode: str, _comp):
    return mv.composite_png(_comp)


@st.cache_data(show_spinner=False, max_entries=48)
def cached_panel(ra: float, dec: float, fov: float, numbers: tuple[int, int, int], mode: str, role: str, _comp):
    return mv.channel_panel_png(_comp, role)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_pixels(ra: float, dec: float, fov: float, numbers: tuple[int, int, int], mode: str, _comp):
    return mv.pixel_table(_comp)


def clear_caches() -> None:
    for fn in (cached_composite, cached_png, cached_panel, cached_pixels):
        fn.clear()


def render_section(ra: float, dec: float, fov: float, channels: list[sc.Channel], target, map_fn, show_error) -> None:
    """Channel selectors, composition, per-channel panels, warnings and provenance."""
    ok = mb.selectable(channels)
    by_number = {c.number: c for c in channels}
    numbers = [c.number for c in ok]
    defaults = mb.default_numbers(channels)
    restore(STATE_KEYS)
    for r in mb.ROLES:
        if st.session_state.get(ROLE_KEYS[r]) not in numbers:
            st.session_state[ROLE_KEYS[r]] = defaults[r]

    st.markdown("### Composición multibanda · falso color")
    st.markdown(
        '<div class="sc-note"><b>Convención de visualización, no color real.</b> Tres canales infrarrojos del cubo '
        '(0.75–5.0 µm, invisibles para el ojo) se asignan a rojo, verde y azul. Los valores son los del FITS, sin '
        'modificar; solo cambia su representación. Los canales 51 y 52 (sin datos en DR1) no pueden elegirse.</div>',
        unsafe_allow_html=True)
    cols = st.columns(3)
    for col, r in zip(cols, mb.ROLES):
        with col:
            st.selectbox(f"{r} · {mb.ROLE_NAMES[r]}", numbers, key=ROLE_KEYS[r],
                         format_func=lambda n: f"Canal {n} · {by_number[n].wavelength_um:.3f} µm",
                         help="Solo canales con datos en DR1. Convención habitual: R = λ más larga, B = λ más corta.")
            c = by_number[st.session_state[ROLE_KEYS[r]]]
            st.caption(f"λ {c.wavelength_um:.3f} µm · ancho {c.bandwidth_um:.3f} µm "
                       f"({c.wl_min_um:.3f}–{c.wl_max_um:.3f}) · D{c.detector} subcanal {c.subchannel}")
    mode = STRETCH_LABELS[st.radio("Escala de visualización", list(STRETCH_LABELS), horizontal=True, key="mb_stretch",
                                   help="Independiente: cada canal con su propio contraste (los colores no reflejan "
                                        "cocientes de brillo). Común: mismos límites en MJy/sr para los tres.")]
    chosen = tuple(int(st.session_state[ROLE_KEYS[r]]) for r in mb.ROLES)
    try:
        mb.select_channels(channels, dict(zip(mb.ROLES, chosen)))
    except ValueError as err:
        st.error(f"Selección no válida: {err}. No se ha leído nada del cubo.")
        return
    key = (ra, dec, fov, chosen, mode)
    with st.spinner("Leyendo los tres canales del cubo en IRSA (solo las filas del campo)…"):
        try:
            comp = cached_composite(*key, channels, map_fn)
            png, info = cached_png(*key, comp)
            pixels = cached_pixels(*key, comp)
        except mb.InsufficientDataError as err:
            st.error(f"Datos insuficientes: {err}. Elija otros canales u otra región.")
            return
        except Exception as err:  # noqa: BLE001 - shown to the user, nothing partial is drawn
            show_error(err, "No se pudo construir la composición")
            return

    left, right = st.columns([1.25, 1])
    with left:
        st.altair_chart(mv.composite_chart(png, info, pixels, comp, target=target), width="stretch",
                        key="mb_field")
        st.caption(
            "Geometría WCS exacta: cada píxel nativo (12.9″) en su posición, sin remuestreo; norte arriba, este a la "
            "izquierda. Color solo donde los tres canales tienen datos. Rosa con rayado blanco: sin datos en al "
            "menos un canal (nunca un color parcial). Punteado gris: fuera de la región leída. Círculo discontinuo: "
            "campo de visión; cruz: objetivo. Pase el cursor para ver los valores originales (MJy/sr) de cada canal.")
    with right:
        st.dataframe(mv.assignment_table(comp), hide_index=True, width="stretch")
        cov = comp.coverage
        c1, c2 = st.columns(2)
        c1.metric("Píxeles con datos en los 3 canales", f"{cov['fraccion_tres_canales']:.1%}",
                  f"{cov['tres_canales']} de {cov['n_campo']}", delta_color="off")
        c2.metric("Con datos solo en 1–2 canales", f"{cov['parcial']}", "se muestran sin datos", delta_color="off")
        st.caption(
            f"Escala: asinh (a = {comp.stretch.asinh_a:g}) entre los percentiles {comp.stretch.percentiles[0]:g} y "
            f"{comp.stretch.percentiles[1]:g} de los {comp.stretch.n_pixels} píxeles del campo con datos en los tres "
            f"canales; {mb.STRETCH_MODES[comp.stretch.mode]}. El contraste solo afecta a la visualización. "
            "Alineación verificada: mismo archivo y ETag, mismo WCS y mismos centros de píxel en los tres canales.")
    panel_cols = st.columns(3)
    for col, r in zip(panel_cols, mb.ROLES):
        c = comp.channels[r]
        col.image(cached_panel(*key, r, comp),
                  caption=f"{r}: canal {c.number} · {c.wavelength_um:.3f} µm (gris, misma escala que en la composición; "
                          "rosa: sin datos en este canal)", width="stretch")
    for w in comp.warnings:
        st.warning(w)
    st.markdown(
        '<div class="sc-note"><b>Qué no permite esta composición.</b> Es una ayuda visual para comparar la forma '
        'del cielo en tres longitudes de onda del cubo combinado (fechas promediadas). Por sí sola no detecta '
        'exoplanetas ni confirma objetos en movimiento, no mide temperaturas ni composición química, no detecta '
        'variabilidad (el cubo no es temporal) y no mejora la relación señal/ruido: no suma ni promedia canales. '
        'Un color se debe a la escala elegida tanto como al cielo; para intensidades, use el espectro del modo de '
        'un canal.</div>', unsafe_allow_html=True)
    with st.expander("Procedencia de la composición"):
        prov = comp.provenance()
        stats = sc.io_stats()
        st.markdown(
            f"- **Producto:** SPHEREx DR1 All-Sky spectral cube, doi:{config.CUBE_DOI}; FITS por tesela HEALPix de "
            f"orden 5 leídos por rangos HTTP (lector del modo de un canal, misma caché verificada con SHA-256).\n"
            f"- **Teselas:** {', '.join(str(t['tesela']) for t in comp.alignment['teselas'])}; remuestreo: ninguno.\n"
            f"- **Este proceso** ha leído {stats['bytes_network'] / 2**20:.1f} MiB de cuerpos HTTP en "
            f"{stats['requests']} intentos y {stats['bytes_cache'] / 2**20:.1f} MiB de la caché local.")
        st.download_button("Descargar procedencia (JSON)", json.dumps(prov, ensure_ascii=False, indent=1,
                                                                     default=str).encode("utf-8"),
                           file_name=f"skyclues_rgb_{ra:.4f}_{dec:+.4f}_{'-'.join(map(str, chosen))}.json",
                           mime="application/json", key="mb_prov")
