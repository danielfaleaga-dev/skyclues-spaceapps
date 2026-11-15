"""Spectrum Explorer page (Streamlit): the same sky in the 102 channels of the SPHEREx DR1 cube.

Kept apart from Time Explorer on purpose: here every image is a channel of a COMBINED product
(many dates averaged), never an observation of one date. Shared with Time Explorer: the region
(RA/Dec, field of view, catalogue astrometry), name resolution, input validation and the
no-data colour convention.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from . import archive, config, multiband_page, navigation, reference_page, release_ui, spectrum_analysis, theme
from . import spectral_cube as sc
from . import spectral_view as sv
from .astrometry import Astrometry
from .targets import validate_coordinates, validate_fov_deg

DEFAULT_LAMBDA_UM = 1.6
LAYERS = {"IMAGE · brillo superficial (MJy/sr)": "image", "NHITS · cobertura (píxeles de entrada)": "nhits"}
QUANTITY_LABELS = {"Densidad de flujo en apertura (mJy) · exploratoria": "flux",
                   "Brillo superficial del píxel (MJy/sr)": "pixel"}
#: widget keys of the single-channel mode kept while the multiband mode is shown: given back through
#: the Session State API, or as the initial value of sliders created with an explicit default.
#: (The channel needs neither: it is restored from the ``canal`` URL parameter.)
SINGLE_STATE_KEYS = ("sx_layer", "sx_pick_ra", "sx_pick_dec", "sx_quantity")
SINGLE_SLIDER_KEYS = ("sx_rap", "sx_ann")


# ----------------------------------------------------------------------------- cached data
@st.cache_resource(show_spinner=False, max_entries=48)
def cached_map(ra: float, dec: float, fov: float, plane: int) -> sc.ChannelMap:
    return sc.channel_map(ra, dec, fov, plane)


@st.cache_data(show_spinner=False, max_entries=48)
def cached_png(ra: float, dec: float, fov: float, plane: int, layer: str):
    return sv.field_png(cached_map(ra, dec, fov, plane), layer)


@st.cache_data(show_spinner=False, max_entries=48)
def cached_pixels(ra: float, dec: float, fov: float, plane: int) -> pd.DataFrame:
    return sv.pixel_table(cached_map(ra, dec, fov, plane))


@st.cache_resource(show_spinner=False, max_entries=16)
def cached_spectrum(ra: float, dec: float, r_ap: float, r_in: float, r_out: float) -> sc.Spectrum:
    return sc.extract_spectrum(ra, dec, sc.Aperture(r_ap, r_in, r_out))


@st.cache_resource(show_spinner=False, max_entries=16)
def cached_epoch(astro_json: str):
    return sc.cube_epoch_position(Astrometry.from_dict(json.loads(astro_json)))


def channel_list(ra: float, dec: float) -> list[sc.Channel]:
    """Channel definitions from the SPECTRAL_CHANNELS table of the tile that holds (ra, dec)."""
    return sc.tile_for(ra, dec).channels


def error_message(err: Exception) -> str:
    if isinstance(err, sc.RangeNotHonoured):
        return ("IRSA no atendió la lectura parcial del cubo (habría enviado el archivo completo de ~320 MB). "
                "No se ha descargado ni mostrado nada. Pruebe de nuevo más tarde.")
    if isinstance(err, sc.FileChangedError):
        return ("El cubo cambió en IRSA mientras se leía (ETag distinto). Se ha descartado lo leído; recargue la "
                "página para leer la versión nueva.")
    if isinstance(err, sc.CubeFormatError):
        return ("El archivo del cubo no tiene la estructura documentada; no se interpreta. "
                f"Detalle: {err}")
    if isinstance(err, archive.ArchiveTransientError):
        return ("NASA/IPAC IRSA no está disponible temporalmente para el cubo espectral (error 5xx o tiempo de "
                "espera agotado tras varios reintentos). No se ha mostrado ningún dato parcial.")
    if isinstance(err, archive.ArchivePermanentError):
        return "IRSA rechazó la solicitud del cubo (error permanente). No se ha mostrado ningún dato parcial."
    if isinstance(err, ValueError):
        return f"Entrada no válida: {err}"
    return "No se pudo leer el cubo espectral. No se ha mostrado ningún dato parcial."


def _show_error(err: Exception, what: str) -> None:
    st.error(f"{what}: {error_message(err)}")
    with st.expander("Detalle técnico"):
        st.code(f"{type(err).__name__}: {err}", language=None)


def _set_pick_from_chart() -> None:
    ev = st.session_state.get("sx_field")
    try:
        pts = ev["selection"]["pick"]
    except (KeyError, TypeError):
        return
    if pts:
        ra, dec = float(pts[0]["ra"]), float(pts[0]["dec"])
        if spectrum_analysis.place_click(st.session_state, ra, dec):    # the click placed the comparison point B
            return
        st.session_state["sx_pick_ra"], st.session_state["sx_pick_dec"] = ra, dec


def _step_channel(delta: int, numbers: list[int]) -> None:
    cur = st.session_state.get("sx_channel", numbers[0])
    i = min(max(numbers.index(cur) + delta, 0), len(numbers) - 1)
    st.session_state["sx_channel"] = numbers[i]




# ----------------------------------------------------------------------------- state kept across views
#: Widgets of this page. Streamlit forgets a widget that is not drawn, so their values are copied
#: aside while another view is shown and given back on return: leaving the page loses nothing.
PAGE_KEYS = ("sx_mode", "sx_channel") + SINGLE_STATE_KEYS + SINGLE_SLIDER_KEYS + multiband_page.STATE_KEYS


def stash_state() -> None:
    """Call while another view is shown."""
    multiband_page.stash(PAGE_KEYS)


def _region_extra(epoch_info: dict, follow: bool) -> str:
    if not epoch_info.get("propagated"):
        return ""
    return theme.badge("centro en la posición esperada del objeto" if follow else "centro fijo de la secuencia")


def reading_guide(quantity: str, sci: bool) -> list[tuple[str, str]]:
    """What the spectrum plot shows, in the words of each level. The same facts in both."""
    unit = ("<b>mJy</b> (milijansky): cuánta luz llega de la apertura por unidad de frecuencia "
            "(1 mJy = 10⁻²⁹ W·m⁻²·Hz⁻¹)."
            if quantity == "flux" else
            "<b>MJy/sr</b> (megajansky por estereorradián): brillo de un píxel por unidad de área del cielo, no la luz "
            "total de una fuente.")
    extra = (" La barra horizontal de cada punto es el intervalo del canal (WL_MIN–WL_MAX), no un error." if sci else
             " Un valor alto significa más luz en ese canal; cerca de cero, que apenas se distingue del fondo.")
    return [
        ("Eje horizontal · longitud de onda",
         "El «color» infrarrojo de la luz, en <b>µm</b> (micrómetros, millonésimas de metro; no son partes por millón). "
         "De 0.75 a 5.0 µm, todo invisible para el ojo. Cada punto es uno de los 102 canales reales."),
        ("Eje vertical · " + ("densidad de flujo" if quantity == "flux" else "brillo superficial"), unit + extra),
        ("Picos y valles",
         "Un pico es un canal más brillante que sus vecinos (posible emisión); un valle, uno más débil (posible "
         "absorción, por ejemplo de hielos o gases). También los producen el ruido, una fuente vecina o el mosaico."),
        ("Qué no se puede concluir",
         "Este espectro es exploratorio y no tiene incertidumbres: no basta para afirmar que hay una línea, una "
         "molécula o un hielo, ni para medir temperaturas. Sirve para decidir qué merece un análisis calibrado."),
    ]


# ----------------------------------------------------------------------------- page
def render(level: str) -> None:
    """Spectrum Explorer for the active region. ``level`` only changes wording and how much is shown."""
    sci = level == "scientific"
    state, params = st.session_state, st.query_params
    region = navigation.get_region(state, params)
    errors = state.pop("region_errors", [])
    for e in errors:
        st.error(e)
    if errors:
        return
    inp = navigation.explorer_inputs(region)
    if region.get("gaia"):
        st.caption("Fuente seleccionada en Gaia DR3: coordenadas de catálogo ICRS, J2016.0. La posición calculada para el cubo no confirma una detección SPHEREx." if sci else "Fuente de catálogo; no confirma una detección SPHEREx.")
    if region.get("solar"):
        st.info("Cuerpo móvil: este cubo combina muchas fechas. Se muestra el cielo en una coordenada fija; no es un espectro identificado del objeto ni una detección." if sci else "Esta imagen muestra la zona del cielo, no un espectro identificado del objeto móvil.")
    multiband_page.restore(("sx_mode", "sx_channel"))
    try:
        ra_c, dec_c = validate_coordinates(inp["ra"], inp["dec"])
        fov = validate_fov_deg(inp["fov"])
    except ValueError as err:
        st.error(f"Entrada no válida: {err} No se ha leído nada del cubo.")
        return

    astro = inp["astrometry"]
    epoch_info = {"propagated": False}
    if astro is not None and astro.has_proper_motion:
        try:
            with st.spinner("Consultando la época del cubo y calculando la posición esperada…", show_time=True):
                expected_ra, expected_dec, epoch_info = cached_epoch(json.dumps(astro.to_dict(), sort_keys=True))
            # A saved sequence keeps its exact centre; a named object is centred on its expected position.
            if inp["follow"]:
                ra_c, dec_c = expected_ra, expected_dec
        except Exception as err:  # noqa: BLE001
            _show_error(err, "No se pudo leer la cabecera de la tesela")
            return
    try:
        with theme.loading("Abriendo la región y leyendo los canales disponibles en IRSA…" if sci else "Preparando esta zona del cielo…", "spectrum_region"):
            channels = channel_list(ra_c, dec_c)
    except Exception as err:  # noqa: BLE001
        theme.region_strip(inp["label"], ra_c, dec_c, fov)
        _show_error(err, "No se pudo leer la tabla de canales del cubo")
        return
    numbers = [c.number for c in channels]
    by_number = {c.number: c for c in channels}

    # region bookkeeping: a new region resets the spectrum position; the same region keeps it
    region_key = (round(ra_c, 6), round(dec_c, 6), fov)
    if state.get("sx_region_key") != region_key:
        state["sx_region_key"] = region_key
        state["sx_pick_ra"], state["sx_pick_dec"] = ra_c, dec_c
        state.pop("_keep_sx_pick_ra", None)
        state.pop("_keep_sx_pick_dec", None)
        state["sx_spec_params"] = None
    if "sx_channel" not in state:
        try:
            q = int(state.get("sx_canal") or params.get("canal", ""))
        except ValueError:
            q = None
        state["sx_channel"] = q if q in by_number else min(
            numbers, key=lambda n: abs(by_number[n].wavelength_um - DEFAULT_LAMBDA_UM))
    state["sx_canal"] = int(state["sx_channel"])
    navigation.write_url(params, {"ra": ra_c, "dec": dec_c, "fov": fov}, "spectrum", state["sx_canal"])

    theme.region_strip(inp["label"], ra_c, dec_c, fov, _region_extra(epoch_info, inp["follow"]) if sci else '')
    theme.note(("<b>Producto combinado, no temporal.</b> " +
            "Cada imagen es un canal del cubo DR1: el promedio de muchas exposiciones de fechas distintas (sin luz "
            "zodiacal), en píxeles de 12.9″. Sirve para ver cómo cambia el cielo con la longitud de onda; no muestra "
            "cambios en el tiempo (para eso, «Tiempo» usa observaciones individuales de 6.15″/px).") if sci else
            "Explora esta zona en distintos colores infrarrojos. Para comparar fechas, abre «Tiempo».")
    if epoch_info.get("warning"):
        st.warning(epoch_info["warning"] + f" Época de referencia: {astro.epoch_jyear:.2f}. No es una detección.")
    if epoch_info.get("propagated") and "mjd_mid" in epoch_info and sci:
        mv = epoch_info["motion_over_inputs_arcsec"]
        theme.note(
            f"<b>Objetivo en movimiento: {astro.name}</b> ({astro.total_pm_arcsec_yr:.2f}″/año). "
            f"Época de referencia del catálogo: {astro.epoch_jyear:.2f}. Posición <b>esperada, calculada</b> para "
            f"el punto medio del intervalo de entradas de esta tesela (no es una época efectiva de observación) "
            f"({epoch_info['date_mid']}; entradas del {epoch_info['date_beg']} al {epoch_info['date_end']}). "
            f"Durante ese intervalo el objeto se desplaza {mv:.1f}″ ({mv / 12.883:.2f} píxeles del cubo): en el "
            "promedio puede aparecer alargado. La cruz es un cálculo, no una detección.")

    # ---------------------------------------------------------------- display mode
    view_mode = st.segmented_control("Imagen infrarroja", multiband_page.MODES, required=True, default=multiband_page.MODES[0], key="sx_mode",
                         label_visibility="visible",
                         help="«Composición multibanda» combina tres canales reales en falso color (R, G, B) con el "
                              "mismo centro y campo. Puede volver a «Un canal» en cualquier momento.")
    if view_mode == multiband_page.MODES[1]:
        multiband_page.stash(SINGLE_STATE_KEYS + SINGLE_SLIDER_KEYS)
        state.pop("sx_channel", None)       # given back from the stored channel on return
        target = (expected_ra, expected_dec) if epoch_info.get("propagated") else (ra_c, dec_c)
        multiband_page.render_section(ra_c, dec_c, fov, channels, target, cached_map, _show_error)
        st.caption("Vuelve a «Un canal» para explorar el espectro de un punto.")
        _footer(ra_c, dec_c, fov, state["sx_canal"])
        return
    multiband_page.stash(multiband_page.STATE_KEYS)
    multiband_page.restore(SINGLE_STATE_KEYS)
    if not sci:
        multiband_page.stash(SINGLE_STATE_KEYS + SINGLE_SLIDER_KEYS)
    # Streamlit drops the value of a widget that was not drawn in a run: a missing pick position is
    # rebuilt even when the region did not change (regression of 2ec4881, fixed in a2a6881).
    if "sx_pick_ra" not in state or "sx_pick_dec" not in state:
        state["sx_pick_ra"], state["sx_pick_dec"] = ra_c, dec_c
        state["sx_spec_params"] = None

    # ---------------------------------------------------------------- channel selector
    theme.eyebrow("Canal espectral · longitud de onda creciente" if sci else "Elige un color infrarrojo")
    b1, mid, b2 = st.columns([1, 14, 1], vertical_alignment="center")
    b1.button("◀", key="sx_prev", on_click=_step_channel, args=(-1, numbers), help="Canal anterior (λ menor)")
    b2.button("▶", key="sx_next", on_click=_step_channel, args=(1, numbers), help="Canal siguiente (λ mayor)")
    with mid:
        number = st.select_slider("Canal (longitud de onda creciente)", options=numbers, key="sx_channel",
                                  format_func=lambda n: f"{n} · {by_number[n].wavelength_um:.3f} µm",
                                  label_visibility="collapsed")
    ch = by_number[number]

    left, right = st.columns([1.25, 1], gap="large")
    defaults = config.CUBE_APERTURE_DEFAULT_PX
    with left:
        layer_label = (st.radio("Capa", list(LAYERS), horizontal=True, key="sx_layer") if sci else
                       state.get('sx_layer', next(iter(LAYERS))))
        layer = LAYERS[layer_label]
        if not sci and layer == 'nhits':
            st.caption('Mostrando cobertura; puedes cambiar a brillo en «Científico».')
        with theme.loading(f"Leyendo el canal {ch.number} del cubo en IRSA…" if sci else "Preparando la imagen…", "spectrum_image"):
            try:
                cmap = cached_map(ra_c, dec_c, fov, ch.plane)
                png, info = cached_png(ra_c, dec_c, fov, ch.plane, layer)
                pixels = cached_pixels(ra_c, dec_c, fov, ch.plane)
            except Exception as err:  # noqa: BLE001
                _show_error(err, f"No se pudo leer el canal {ch.number}")
                return
        pick = (state["sx_pick_ra"], state["sx_pick_dec"])
        ap_now = sc.Aperture(state.get("sx_rap", multiband_page.kept('sx_rap', defaults[0])), state.get("sx_rin", defaults[1]),
                             state.get("sx_rout", defaults[2]))
        tile0 = cmap.patches[0].tile
        target = (expected_ra, expected_dec) if epoch_info.get("propagated") else (ra_c, dec_c)
        pick_b = spectrum_analysis.point_b(region_key)      # second position, only if the user placed one
        chart = sv.field_chart(png, info, pixels, cmap, target=target, pick=pick, aperture=ap_now,
                               pixel_arcsec=tile0.pixel_scale_arcsec, pick_b=pick_b)
        st.altair_chart(chart, on_select=_set_pick_from_chart, selection_mode="pick", key="sx_field",
                        width="stretch")
        st.image(sv.colorbar_png(info))
        spectrum_analysis.point_controls(sci, region_key)
        if sci:
            st.caption(
                "Geometría WCS: cada píxel nativo del cubo (12.9″) se dibuja en su posición, con su valor original, sin "
                f"remuestreo ni suavizado; norte arriba, este a la izquierda (raster base de "
                f"{info['npix']} píxeles, {info['screen_arcsec_per_px']:.1f}″/px; su tamaño en pantalla se adapta al visor). "
                f"Escala de visualización propia de cada canal "
                f"({'percentiles 1–99.5 del campo, asinh' if layer == 'image' else 'lineal'}); compare intensidades entre "
                "canales con el espectro. Rosa/morado: valor no finito o NHITS = 0 (sin dato utilizable); no significa cielo oscuro. Gris claro: fuera de la región leída. "
                "Cruz azul: objetivo; rombo ámbar: posición del espectro, con su apertura y su anillo de fondo. "
                "Pase el cursor para ver el valor de cada píxel; haga clic para elegir la posición del espectro.")
        else:
            st.markdown("Pulsa la imagen para elegir un punto. **Rosa: sin datos.**")

    with right:
        if ch.blank:
            st.warning((f"**Canal {ch.number} sin datos en DR1.** {ch.wavelength_um:.3f} µm, D{ch.detector} subcanal "
                       f"{ch.subchannel}: canal contiguo al divisor dicroico. La documentación oficial lo publica "
                       f"vacío (todo NaN, NHITS = 0; cabecera BLANKCH = '{tile0.header('PRIMARY').get('BLANKCH')}') "
                       "para conservar la numeración. SkyClues no lo rellena ni lo interpola.") if sci else
                       f"El canal {ch.number} no tiene datos. Elige otro color infrarrojo.")
        s = cmap.summary()
        if sci:
            theme.facts([
                ("λ central", f"{ch.wavelength_um:.3f} µm", f"{ch.wl_min_um:.3f}–{ch.wl_max_um:.3f} µm"),
                ("Detector · subcanal", f"D{ch.detector} · {ch.subchannel}", f"R = λ/Δλ = {ch.resolving_power:.0f}"),
                ("Píxeles con datos", f"{s['valid_fraction']:.1%}", f"{s['n_valid']} de {s['n_field']}"),
                ("NHITS mediano", f"{s['nhits_median']:.0f}", f"mínimo {s['nhits_min']}")])
            st.caption(f"Canal {ch.number} de 102 = plano {ch.plane} del cubo (0-based) · ancho {ch.bandwidth_um:.3f} µm · "
                       f"teselas HEALPix {', '.join(str(t) for t in s['tiles'])} · píxeles del campo con OVERFLOW: "
                       f"{s['flag_pixels']['OVERFLOW']}, OUTLIER: {s['flag_pixels']['OUTLIER']}, SOURCE: "
                       f"{s['flag_pixels']['SOURCE']}. λ, intervalo y R proceden de la tabla SPECTRAL_CHANNELS del FITS.")
        else:
            theme.facts([
                ("Longitud de onda", f"{ch.wavelength_um:.2f} µm", f"canal {ch.number} de 102"),
                ("Píxeles con datos", f"{s['valid_fraction']:.0%}", "del campo en este canal")])

        mx = config.CUBE_APERTURE_MAX_PX
        pxs = tile0.pixel_scale_arcsec

        def measure_controls():
            st.number_input("RA (°)", format="%.6f", min_value=0.0, max_value=359.999999, key="sx_pick_ra")
            st.number_input("Dec (°)", format="%.6f", min_value=-90.0, max_value=90.0, key="sx_pick_dec")
            ap = st.slider("Radio de apertura (píxeles del cubo)", 1.0, mx[0],
                           multiband_page.kept("sx_rap", defaults[0]), 0.5, key="sx_rap")
            rin, rout = st.slider("Anillo de fondo: radios interior y exterior (píxeles)", 1.5, mx[2],
                                  multiband_page.kept("sx_ann", defaults[1:]), 0.5, key="sx_ann")
            st.caption(f"Apertura {ap * pxs:.0f}″ · anillo {rin * pxs:.0f}″–{rout * pxs:.0f}″ (1 píxel = {pxs:.2f}″).")
            return ap, rin, rout

        theme.eyebrow("Posición del espectro")
        if sci:
            r_ap, r_in, r_out = measure_controls()
        else:
            st.markdown('El rombo naranja marca el punto elegido.' if pick_b is None else
                        'El rombo azul (A) y el cuadrado naranja (B) marcan los dos puntos.')
            r_ap = state.get('sx_rap', multiband_page.kept('sx_rap', defaults[0]))
            r_in, r_out = state.get('sx_ann', multiband_page.kept('sx_ann', defaults[1:]))
        state["sx_rin"], state["sx_rout"] = r_in, r_out
        go = st.button("Obtener el espectro en esta posición", type="primary", key="sx_extract")

    # ---------------------------------------------------------------- spectrum
    # One plot and, under it, its context. Later analyses (comparing two spectra, inspecting peaks and
    # valleys, molecular or ice references, SPLICES) attach to this same plot and context, not to a new mode.
    params_now = (round(state["sx_pick_ra"], 6), round(state["sx_pick_dec"], 6), r_ap, r_in, r_out)
    if go or state.get("sx_spec_params") is None:
        state["sx_spec_params"] = params_now
    if pick_b is None:
        st.markdown("### Espectro exploratorio de una posición" if sci else "### La luz del punto elegido")
    else:
        st.markdown("### Espectros exploratorios de dos posiciones" if sci else "### La luz de los dos puntos")
    sp = state["sx_spec_params"]
    if sp != params_now:
        st.caption("La posición o la apertura han cambiado: pulse «Obtener el espectro en esta posición» para "
                   "actualizarlo. Se muestra el espectro anterior.")
    try:
        validate_coordinates(sp[0], sp[1])
        sc.Aperture(*sp[2:]).validate()
        with theme.loading("Leyendo los 102 canales alrededor de la posición…" if sci else "Preparando el espectro de este punto…", "spectrum_plot"):
            spec = cached_spectrum(*sp)
    except Exception as err:  # noqa: BLE001
        _show_error(err, "No se pudo obtener el espectro")
        return
    qlabel = (st.radio("Magnitud representada", list(QUANTITY_LABELS), horizontal=True, key="sx_quantity") if sci else
              state.get('sx_quantity', next(iter(QUANTITY_LABELS))))
    quantity = QUANTITY_LABELS[qlabel]
    # The plot, the second spectrum (same aperture and annulus as A, never tuned per position), A − B, A / B
    # and the peaks and valleys: all on these axes.
    spectrum_analysis.render(spec, quantity, ch.number, sci, region_key,
                             lambda ra, dec: cached_spectrum(round(ra, 6), round(dec, 6), *sp[2:]), _show_error)
    n_missing = sum(r["status"] != "ok" for r in spec.rows)
    if sci:
        st.caption(
            f"Posición RA {spec.ra:.5f}°, Dec {spec.dec:+.5f}°. {spec.n_measured} de 102 canales con valor; {n_missing} sin "
            "valor (marcas rosas sobre el eje: canales 51 y 52 sin datos en DR1, o apertura/fondo sin datos). Un punto "
            "por canal real; la barra horizontal es el intervalo del canal (WL_MIN–WL_MAX), no un error. Sin curva ni "
            "interpolación. Contorno hueco: algún píxel de entrada de la apertura tenía OVERFLOW (saturación) u OUTLIER. "
            "Línea discontinua vertical: canal mostrado arriba.")
        with st.expander("Cómo leer este gráfico"):
            theme.reading_guide(reading_guide(quantity, sci))
    else:
        st.markdown('Cuanto más alto el punto, más luz en ese color infrarrojo. **Marcas rosas: sin datos.**')
        st.caption('Vista orientativa: los picos por sí solos no identifican materiales.')
        if spec.warnings:
            st.warning('Hay datos limitados en esta posición. El modo Científico muestra los detalles.')
        _footer(ra_c, dec_c, fov, state['sx_canal'])
        return
    for w in spec.warnings:
        st.warning(w)
    method = (
        "Fotometría de apertura sobre el cubo combinado, adaptando el método del tutorial de IRSA: apertura circular "
        f"sobre el cielo de {spec.aperture.r_ap:g} píxeles ({spec.aperture.r_ap * spec.pixel_scale_arcsec:.0f}″; "
        f"fracciones de píxel con {spec.subpixels}×{spec.subpixels} submuestras), menos la media con recorte 3σ del "
        f"anillo {spec.aperture.r_in:g}–{spec.aperture.r_out:g} píxeles por el área de la apertura, multiplicada por el "
        f"ángulo sólido del píxel ({spec.pixel_solid_angle_sr:.4e} sr, píxeles HEALPix de igual área) → mJy. IRSA "
        "advierte que un espectro extraído del cubo <b>solo es apropiado para visualización</b>: no tiene "
        "incertidumbres (el cubo no incluye varianza; la dispersión del fondo no es un error del flujo). El tutorial "
        "usa círculos en coordenadas de píxel y Photutils con solapamiento exacto; aquí se usan distancias angulares y "
        "submuestras, por lo que los valores pueden diferir. No corrige la fracción de la PSF fuera de la apertura, "
        "puede incluir fuentes vecinas y el rayado del mosaico cerca de líneas intensas. No es una medida de precisión "
        "del flujo de una estrella ni permite afirmar la presencia de líneas o materiales. Para espectrofotometría "
        f'científica, use la <a href="{config.SPECTROPHOTOMETRY_TOOL_URL}" target="_blank">herramienta oficial SPHEREx '
        "Spectrophotometry de IRSA</a> (fotometría forzada sobre las imágenes Level 2, con incertidumbres; solo "
        "interfaz web, sin API documentada).")
    if sci:
        theme.note("<b>Qué es y qué no es este espectro.</b> " + method)
    else:
        theme.note("<b>Espectro exploratorio, no calibrado.</b> Sirve para ver la forma general de la luz de este punto. "
                   "No tiene incertidumbres y no permite afirmar la presencia de líneas o materiales. Para medidas "
                   f'científicas, use la <a href="{config.SPECTROPHOTOMETRY_TOOL_URL}" target="_blank">herramienta '
                   "oficial SPHEREx Spectrophotometry de IRSA</a>.")
        with st.expander("Método y limitaciones del espectro"):
            st.html(f'<div class="sc-note">{method}</div>')

    with st.expander("Tabla del espectro (valores por canal)"):
        df = spec.table()
        cols = ["canal", "lambda_um", "lambda_min_um", "lambda_max_um", "detector", "subcanal", "estado", "flujo_mjy",
                "fondo_mjysr", "fondo_sigma_mjysr", "n_fondo", "pixel_mjysr", "pixel_nhits", "nhits_min_apertura",
                "flags_apertura"]
        st.dataframe(df[cols], hide_index=True, width="stretch")
        st.caption("«fondo_sigma_mjysr» es la dispersión (recortada a 3σ) de los píxeles del anillo: describe el "
                   "fondo, no es la incertidumbre del flujo.")
        meta = {"producto": "SPHEREx DR1 All-Sky spectral cube", "doi": config.CUBE_DOI,
                "metodo": "fotometría de apertura exploratoria (tutorial oficial IRSA); solo visualización",
                "ra_deg": spec.ra, "dec_deg": spec.dec, "apertura_px": spec.aperture.r_ap,
                "anillo_px": [spec.aperture.r_in, spec.aperture.r_out], "pixel_arcsec": spec.pixel_scale_arcsec,
                "pixel_sr": spec.pixel_solid_angle_sr, "unidades": {"flujo_mjy": "mJy", "pixel_mjysr": "MJy/sr"},
                "teselas": spec.tiles}
        csv = "".join(f"# {k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in meta.items()) + \
            df[cols].to_csv(index=False)
        st.download_button("Descargar CSV con procedencia", csv.encode("utf-8"),
                           file_name=f"skyclues_espectro_{spec.ra:.4f}_{spec.dec:+.4f}.csv", mime="text/csv",
                           key="sx_csv")

    with st.expander("Procedencia del producto y limitaciones"):
        prov = pd.DataFrame(spec.tiles).drop_duplicates("tile")
        st.dataframe(prov.astype(str), hide_index=True, width="stretch")
        stats = sc.io_stats()
        st.markdown(
            f"- **Producto:** SPHEREx DR1 All-Sky spectral cube, doi:{config.CUBE_DOI}. Ficheros FITS por tesela HEALPix "
            f"de orden 5 ({config.CUBE_DATA_URL}), los mismos del [tutorial oficial]({config.CUBE_TUTORIAL_URL}).\n"
            "- **Lectura:** solo las filas necesarias, por rangos de bytes HTTP (cada tesela pesa ~320 MB y nunca se "
            "descarga entera); bytes verificados con Content-Range, tamaño y ETag; caché local con SHA-256. "
            f"Este proceso ha leído {stats['bytes_network'] / 2**20:.1f} MiB de cuerpos HTTP "
            f"en {stats['requests']} intentos (sin contar cabeceras HTTP/TLS).\n"
            "- **Valores:** IMAGE en MJy/sr con la luz zodiacal ya restada por el pipeline; cada píxel es la media de "
            "NHITS píxeles de entrada (asignación al píxel más próximo, sin suavizado). Los píxeles de entrada con "
            "TRANSIENT, SUR_ERROR, NONFUNC, DICHROIC, MISSING_DATA, HOT, COLD, PHANMISS, NONLINEAR, PERSIST, "
            "CROSSTALK, STREAK, BLOOM, SNOWBALL, HALO o SATELLITE_HALO se excluyeron antes de promediar; FLAGS solo "
            "conserva OVERFLOW, SOURCE y OUTLIER (Explanatory Supplement v2.1, §2.5 y §3.4).\n"
            "- **λ:** de la tabla SPECTRAL_CHANNELS de cada FITS (λ central, WL_MIN, WL_MAX, R). "
            "Canal n = 17·(detector − 1) + subcanal; plano = n − 1.\n"
            "- **Limitaciones:** producto combinado de fechas distintas (no temporal); píxel de 12.9″ (≈ 2 píxeles "
            "Level 2); rayado del mosaico cerca de líneas intensas (He 1.083 µm, Paα, PAH 3.3 µm, Brα) que no se "
            "promedia; los canales 51 y 52 están vacíos en DR1; espectro sin incertidumbres ni corrección de "
            "apertura (solo visualización).")
    _footer(ra_c, dec_c, fov, state["sx_canal"])


def _footer(ra: float, dec: float, fov: float, canal: int) -> None:
    st.html('<div style="height:.6rem"></div>')
    reference_page.render(ra, dec, fov, key="spectrum_ref")
    release_ui.share(ra, dec, fov, "espectral", canal)
    st.caption("Datos: NASA/IPAC IRSA · SPHEREx DR1 All-Sky spectral cube (doi:10.26131/IRSA679), leído por rangos de "
               "bytes de los FITS oficiales (sin descargar teselas completas)." if theme.scientific() else 'Datos: SPHEREx · NASA/IPAC IRSA.')
