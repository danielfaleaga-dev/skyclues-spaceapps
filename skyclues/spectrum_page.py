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

from . import archive, config, multiband_page, reference_page
from . import spectral_cube as sc
from . import spectral_view as sv
from .astrometry import Astrometry
from .targets import PRESETS, clamp_fov_deg, fov_pixels, resolve_name, validate_coordinates, validate_fov_deg

SOURCES = ["Región de Time Explorer", "Coordenadas RA/Dec", "Campo predefinido", "Nombre (SIMBAD)"]
FOV_LABELS = [f"{a:g}′" for a in config.FOV_PRESETS_ARCMIN] + ["Otro"]
DEFAULT_RADEC = (210.802429, 54.34875)          # M101, as in Time Explorer
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


# ----------------------------------------------------------------------------- region
def _qp_region():
    qp, ra, dec, fov = st.query_params, None, None, None
    try:
        if "ra" in qp or "dec" in qp:
            ra, dec = validate_coordinates(qp.get("ra"), qp.get("dec"))
        if "fov" in qp:
            fov = validate_fov_deg(qp.get("fov"))
    except ValueError as err:
        raise ValueError(f"Parámetros de la URL no válidos: {err}") from err
    return ra, dec, fov


def fov_widget_state(fov_deg: float) -> dict:
    """Session-state values that make the FOV widgets show ``fov_deg``."""
    for lbl, a in zip(FOV_LABELS, config.FOV_PRESETS_ARCMIN):
        if abs(round(a / 60, 4) - fov_deg) < 1e-6:
            return {"sx_fov": lbl}
    return {"sx_fov": "Otro", "sx_fov_custom": round(fov_deg * 60, 1)}


def region_sidebar(shared: dict | None) -> dict | None:
    st.markdown("### Región del cielo")
    opts = SOURCES if shared else SOURCES[1:]
    if st.session_state.get("sx_source") not in opts:
        st.session_state["sx_source"] = opts[0] if shared else SOURCES[1]
    src = st.radio("Definir por", opts, key="sx_source",
                   help="«Región de Time Explorer» reutiliza el centro, el campo y la astrometría del objetivo "
                        "que se está viendo en Time Explorer.")
    q_ra, q_dec, q_fov = _qp_region()
    astro, label = None, None
    if src == SOURCES[0]:
        ra, dec = shared["ra"], shared["dec"]
        astro = Astrometry.from_dict(shared.get("astrometry"))
        label = shared.get("label") or "Time Explorer"
        st.caption(f"{label} · RA {ra:.5f}°, Dec {dec:+.5f}° · campo {shared['fov'] * 60:.1f}′ en Time Explorer.")
    elif src == "Coordenadas RA/Dec":
        if "sx_ra" not in st.session_state:
            base = (q_ra, q_dec) if q_ra is not None else ((shared["ra"], shared["dec"]) if shared else DEFAULT_RADEC)
            st.session_state["sx_ra"], st.session_state["sx_dec"] = float(base[0]), float(base[1])
        ra = st.number_input("RA (grados, ICRS)", format="%.6f", min_value=0.0, max_value=359.999999, key="sx_ra")
        dec = st.number_input("Dec (grados, ICRS)", format="%.6f", min_value=-90.0, max_value=90.0, key="sx_dec")
        label = "coordenadas introducidas"
    elif src == "Campo predefinido":
        name = st.selectbox("Campo", list(PRESETS), key="sx_preset")
        astro = PRESETS[name]["astrometry"]
        ra, dec, label = astro.ra_deg, astro.dec_deg, name
    else:
        obj = st.text_input("Nombre del objeto", "M101", key="sx_obj")
        if st.button("Resolver nombre", key="sx_resolve"):
            try:
                a, w = resolve_name(obj)
                st.session_state["sx_resolved"] = {"astrometry": a.to_dict(), "warnings": w}
            except Exception as err:  # noqa: BLE001 - shown to the user
                st.session_state.pop("sx_resolved", None)
                st.error(f"No se pudo resolver «{obj}»: {err}")
        res = st.session_state.get("sx_resolved")
        if not res:
            st.caption("Pulse «Resolver nombre» (SIMBAD: posición, movimiento propio y paralaje).")
            return None
        astro = Astrometry.from_dict(res["astrometry"])
        for w in res["warnings"]:
            st.warning(w)
        ra, dec, label = astro.ra_deg, astro.dec_deg, astro.name

    if "sx_fov" not in st.session_state:
        f0 = q_fov or (shared["fov"] if shared else round(6 / 60, 4))
        st.session_state.update(fov_widget_state(f0))
    choice = st.radio("Campo de visión (diámetro en el cielo)", FOV_LABELS, horizontal=True, key="sx_fov",
                      help="Región que se lee del cubo. No es un zoom: un campo mayor muestra más cielo.")
    if choice == "Otro":
        if "sx_fov_custom" not in st.session_state:
            st.session_state["sx_fov_custom"] = 6.0
        arcmin = st.number_input("Diámetro (minutos de arco)", min_value=config.FOV_MIN_DEG * 60,
                                 max_value=config.CUBE_FIELD_MAX_DEG * 60, step=0.5, format="%.1f", key="sx_fov_custom")
        fov = clamp_fov_deg(arcmin / 60)
    else:
        fov = round(config.FOV_PRESETS_ARCMIN[FOV_LABELS.index(choice)] / 60, 4)
    npx = int(round(fov * 3600 / 12.883))
    st.caption(f"{fov * 60:.1f}′ ≈ {npx} × {npx} píxeles del cubo (12.9″/px; Time Explorer: ≈ {fov_pixels(fov)} píxeles "
               "de 6.15″ por lado).")
    return {"ra": float(ra), "dec": float(dec), "fov": fov, "astrometry": astro, "label": label, "source": src}


def to_time_explorer(ra: float, dec: float, fov: float) -> None:
    """Callback: open the same region in Time Explorer (new search with these coordinates)."""
    st.session_state["explorer"] = "Time Explorer · tiempo"
    st.session_state["mode"] = "Nueva búsqueda"
    st.session_state.pop("report", None)
    for k in ("ra_in", "dec_in", "fov_preset", "fov_custom", "how"):
        st.session_state.pop(k, None)
    st.query_params.clear()
    st.query_params.update({"ra": f"{ra:.6f}", "dec": f"{dec:.6f}", "fov": f"{fov:g}"})


def _set_pick_from_chart() -> None:
    ev = st.session_state.get("sx_field")
    try:
        pts = ev["selection"]["pick"]
    except (KeyError, TypeError):
        return
    if pts:
        st.session_state["sx_pick_ra"] = float(pts[0]["ra"])
        st.session_state["sx_pick_dec"] = float(pts[0]["dec"])


def _step_channel(delta: int, numbers: list[int]) -> None:
    cur = st.session_state.get("sx_channel", numbers[0])
    i = min(max(numbers.index(cur) + delta, 0), len(numbers) - 1)
    st.session_state["sx_channel"] = numbers[i]


# ----------------------------------------------------------------------------- page
def render(shared: dict | None) -> None:
    with st.sidebar:
        try:
            region = region_sidebar(shared)
        except ValueError as err:
            st.error(str(err))
            return
        st.markdown("---")
        st.caption("Datos: NASA/IPAC IRSA · SPHEREx DR1 All-Sky spectral cube (doi:10.26131/IRSA679), leído "
                   "por rangos de bytes de los FITS oficiales (sin descargar teselas completas).")

    st.markdown("# SkyClues · Spectrum Explorer")
    st.markdown('<div class="sc-sub">El mismo cielo en 102 canales infrarrojos (0.75–5.0 µm) · cubo combinado '
                'SPHEREx DR1 · prototipo científico · NASA Space Apps 2026</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sc-note"><b>Producto combinado, no temporal.</b> Cada imagen es un canal del cubo DR1: el '
        'promedio de muchas exposiciones de fechas distintas (sin luz zodiacal), en píxeles de 12.9″. Sirve para '
        'ver cómo cambia el cielo con la longitud de onda; no muestra cambios en el tiempo (para eso, Time '
        'Explorer usa observaciones individuales de 6.15″/px).</div>', unsafe_allow_html=True)
    if region is None:
        st.info("Defina una región en la barra lateral.")
        return
    try:
        ra_c, dec_c = validate_coordinates(region["ra"], region["dec"])
        fov = validate_fov_deg(region["fov"])
    except ValueError as err:
        st.error(f"Entrada no válida: {err} No se ha leído nada del cubo.")
        return

    astro = region["astrometry"]
    epoch_info = {"propagated": False}
    if astro is not None and astro.has_proper_motion:
        try:
            expected_ra, expected_dec, epoch_info = cached_epoch(json.dumps(astro.to_dict(), sort_keys=True))
            # A transferred field must keep its exact centre; the expected target is a separate marker.
            if region["source"] != SOURCES[0]:
                ra_c, dec_c = expected_ra, expected_dec
        except Exception as err:  # noqa: BLE001
            _show_error(err, "No se pudo leer la cabecera de la tesela")
            return
    reference_page.render(ra_c, dec_c, fov, key="spectrum_ref")
    try:
        channels = channel_list(ra_c, dec_c)
    except Exception as err:  # noqa: BLE001
        _show_error(err, "No se pudo leer la tabla de canales del cubo")
        return
    numbers = [c.number for c in channels]
    by_number = {c.number: c for c in channels}

    # shareable URL and region bookkeeping
    region_key = (round(ra_c, 6), round(dec_c, 6), fov)
    # Streamlit drops the value of a widget that was not drawn in a run (e.g. while Time Explorer is
    # shown), so a missing pick position must be rebuilt even when the region did not change.
    if st.session_state.get("sx_region_key") != region_key or "sx_pick_ra" not in st.session_state \
            or "sx_pick_dec" not in st.session_state:
        st.session_state["sx_region_key"] = region_key
        st.session_state["sx_pick_ra"], st.session_state["sx_pick_dec"] = ra_c, dec_c
        st.session_state["sx_spec_params"] = None
    if "sx_channel" not in st.session_state:
        try:
            q = int(st.query_params.get("canal", ""))
        except ValueError:
            q = None
        st.session_state["sx_channel"] = q if q in by_number else min(
            numbers, key=lambda n: abs(by_number[n].wavelength_um - DEFAULT_LAMBDA_UM))
    st.query_params.update({"explorer": "espectral", "ra": f"{ra_c:.6f}", "dec": f"{dec_c:.6f}", "fov": f"{fov:g}",
                            "canal": str(st.session_state["sx_channel"])})

    st.markdown(f'<span class="sc-badge">Centro RA {ra_c:.5f}° · Dec {dec_c:+.5f}° · campo {fov * 60:.1f}′</span> '
                f'&nbsp; <span class="sc-badge">{region["label"]}</span>', unsafe_allow_html=True)
    if epoch_info.get("warning"):
        st.warning(epoch_info["warning"] + f" Época de referencia: {astro.epoch_jyear:.2f}. No es una detección.")
    if epoch_info.get("propagated") and "mjd_mid" in epoch_info:
        mv = epoch_info["motion_over_inputs_arcsec"]
        st.markdown(
            f'<div class="sc-note"><b>Objetivo en movimiento: {astro.name}</b> ({astro.total_pm_arcsec_yr:.2f}″/año). '
            f'Época de referencia del catálogo: {astro.epoch_jyear:.2f}. Posición <b>esperada, calculada</b> para '
            f'el punto medio del intervalo de entradas de esta tesela (no es una época efectiva de observación) '
            f'({epoch_info["date_mid"]}; entradas del {epoch_info["date_beg"]} al {epoch_info["date_end"]}). '
            f'Durante ese intervalo el objeto se desplaza {mv:.1f}″ ({mv / 12.883:.2f} píxeles del cubo): en el '
            'promedio puede aparecer alargado. La cruz es un cálculo, no una detección.</div>', unsafe_allow_html=True)
    st.button("Abrir esta región en Time Explorer", key="sx_to_time", on_click=to_time_explorer,
              args=(ra_c, dec_c, fov), help="Búsqueda de observaciones individuales de distintas fechas en la misma región.")

    # ---------------------------------------------------------------- display mode
    view_mode = st.radio("Modo de visualización", multiband_page.MODES, horizontal=True, key="sx_mode",
                         help="«Composición multibanda» combina tres canales reales en falso color (R, G, B) con el "
                              "mismo centro y campo. Puede volver a «Un canal» en cualquier momento.")
    if view_mode == multiband_page.MODES[1]:
        multiband_page.stash(SINGLE_STATE_KEYS + SINGLE_SLIDER_KEYS)
        st.session_state.pop("sx_channel", None)       # given back from the ``canal`` URL parameter on return
        target = (expected_ra, expected_dec) if epoch_info.get("propagated") else (ra_c, dec_c)
        multiband_page.render_section(ra_c, dec_c, fov, channels, target, cached_map, _show_error)
        st.caption("El espectro exploratorio se obtiene en el modo «Un canal»; al volver se conservan la región, el "
                   "canal y la posición elegidos.")
        return
    multiband_page.stash(multiband_page.STATE_KEYS)
    multiband_page.restore(SINGLE_STATE_KEYS)

    # ---------------------------------------------------------------- channel selector
    st.markdown("### Canal espectral")
    b1, mid, b2 = st.columns([1, 10, 1])
    b1.button("◀", key="sx_prev", on_click=_step_channel, args=(-1, numbers), help="Canal anterior (λ menor)")
    b2.button("▶", key="sx_next", on_click=_step_channel, args=(1, numbers), help="Canal siguiente (λ mayor)")
    with mid:
        number = st.select_slider("Canal (longitud de onda creciente)", options=numbers, key="sx_channel",
                                  format_func=lambda n: f"{n} · {by_number[n].wavelength_um:.3f} µm",
                                  label_visibility="collapsed")
    ch = by_number[number]

    left, right = st.columns([1.25, 1])
    with left:
        layer = LAYERS[st.radio("Capa", list(LAYERS), horizontal=True, key="sx_layer")]
        with st.spinner(f"Leyendo el canal {ch.number} del cubo en IRSA…"):
            try:
                cmap = cached_map(ra_c, dec_c, fov, ch.plane)
                png, info = cached_png(ra_c, dec_c, fov, ch.plane, layer)
                pixels = cached_pixels(ra_c, dec_c, fov, ch.plane)
            except Exception as err:  # noqa: BLE001
                _show_error(err, f"No se pudo leer el canal {ch.number}")
                return
        pick = (st.session_state["sx_pick_ra"], st.session_state["sx_pick_dec"])
        ap_now = sc.Aperture(st.session_state.get("sx_rap", config.CUBE_APERTURE_DEFAULT_PX[0]),
                             st.session_state.get("sx_rin", config.CUBE_APERTURE_DEFAULT_PX[1]),
                             st.session_state.get("sx_rout", config.CUBE_APERTURE_DEFAULT_PX[2]))
        tile0 = cmap.patches[0].tile
        target = (expected_ra, expected_dec) if epoch_info.get("propagated") else (ra_c, dec_c)
        chart = sv.field_chart(png, info, pixels, cmap, target=target, pick=pick, aperture=ap_now,
                               pixel_arcsec=tile0.pixel_scale_arcsec)
        st.altair_chart(chart, on_select=_set_pick_from_chart, selection_mode="pick", key="sx_field",
                        width="stretch")
        st.image(sv.colorbar_png(info))
        st.caption(
            "Geometría WCS: cada píxel nativo del cubo (12.9″) se dibuja en su posición, con su valor original, sin "
            f"remuestreo ni suavizado; norte arriba, este a la izquierda (raster base de "
            f"{info['npix']} píxeles, {info['screen_arcsec_per_px']:.1f}″/px; su tamaño en pantalla se adapta al visor). "
            f"Escala de visualización propia de cada canal "
            f"({'percentiles 1–99.5 del campo, asinh' if layer == 'image' else 'lineal'}); compare intensidades entre "
            "canales con el espectro. Rosa: sin datos (NaN, NHITS = 0). Gris claro: fuera de la región leída. "
            "Cruz azul: objetivo; rombo ámbar: posición del espectro, con su apertura y su anillo de fondo. "
            "Pase el cursor para ver el valor de cada píxel; haga clic para elegir la posición del espectro.")

    with right:
        if ch.blank:
            st.warning(f"**Canal {ch.number} sin datos en DR1.** {ch.wavelength_um:.3f} µm, D{ch.detector} subcanal "
                       f"{ch.subchannel}: canal contiguo al divisor dicroico. La documentación oficial lo publica "
                       f"vacío (todo NaN, NHITS = 0; cabecera BLANKCH = '{tile0.header('PRIMARY').get('BLANKCH')}') "
                       "para conservar la numeración. SkyClues no lo rellena ni lo interpola.")
        c1, c2 = st.columns(2)
        c1.metric("λ central (µm)", f"{ch.wavelength_um:.3f}")
        c2.metric("Detector · subcanal", f"D{ch.detector} · {ch.subchannel}")
        c1.metric("Intervalo del canal", f"{ch.wl_min_um:.3f}–{ch.wl_max_um:.3f} µm")
        c2.metric("Resolución R = λ/Δλ", f"{ch.resolving_power:.0f}")
        s = cmap.summary()
        c1.metric("Píxeles con datos en el campo", f"{s['valid_fraction']:.1%}", f"{s['n_valid']} de {s['n_field']}",
                  delta_color="off")
        c2.metric("NHITS mediano", f"{s['nhits_median']:.0f}", f"mínimo {s['nhits_min']}", delta_color="off")
        st.caption(f"λ {ch.wavelength_um:.3f} µm · intervalo {ch.wl_min_um:.3f}–{ch.wl_max_um:.3f} µm · "
                   f"Canal {ch.number} de 102 = plano {ch.plane} del cubo (0-based) · ancho {ch.bandwidth_um:.3f} µm · "
                   f"teselas HEALPix {', '.join(str(t) for t in s['tiles'])} · píxeles del campo con OVERFLOW: "
                   f"{s['flag_pixels']['OVERFLOW']}, OUTLIER: {s['flag_pixels']['OUTLIER']}, SOURCE: "
                   f"{s['flag_pixels']['SOURCE']}. λ, intervalo y R proceden de la tabla SPECTRAL_CHANNELS del FITS.")

        st.markdown("#### Posición del espectro")
        st.number_input("RA (°)", format="%.6f", min_value=0.0, max_value=359.999999, key="sx_pick_ra")
        st.number_input("Dec (°)", format="%.6f", min_value=-90.0, max_value=90.0, key="sx_pick_dec")
        mx = config.CUBE_APERTURE_MAX_PX
        pxs = tile0.pixel_scale_arcsec
        r_ap = st.slider("Radio de apertura (píxeles del cubo)", 1.0, mx[0],
                         multiband_page.kept("sx_rap", config.CUBE_APERTURE_DEFAULT_PX[0]), 0.5, key="sx_rap")
        r_in, r_out = st.slider("Anillo de fondo: radios interior y exterior (píxeles)", 1.5, mx[2],
                                multiband_page.kept("sx_ann", config.CUBE_APERTURE_DEFAULT_PX[1:]), 0.5, key="sx_ann")
        st.session_state["sx_rin"], st.session_state["sx_rout"] = r_in, r_out
        st.caption(f"Apertura {r_ap * pxs:.0f}″ · anillo {r_in * pxs:.0f}″–{r_out * pxs:.0f}″ (1 píxel = {pxs:.2f}″).")
        go = st.button("Obtener el espectro en esta posición", type="primary", key="sx_extract")

    # ---------------------------------------------------------------- spectrum
    params = (round(st.session_state["sx_pick_ra"], 6), round(st.session_state["sx_pick_dec"], 6), r_ap, r_in, r_out)
    if go or st.session_state.get("sx_spec_params") is None:
        st.session_state["sx_spec_params"] = params
    st.markdown("### Espectro exploratorio de una posición")
    sp = st.session_state["sx_spec_params"]
    if sp != params:
        st.caption("La posición o la apertura han cambiado: pulse «Obtener el espectro en esta posición» para "
                   "actualizarlo. Se muestra el espectro anterior.")
    try:
        validate_coordinates(sp[0], sp[1])
        sc.Aperture(*sp[2:]).validate()
        with st.spinner("Leyendo los 102 canales alrededor de la posición (solo las filas necesarias)…"):
            spec = cached_spectrum(*sp)
    except Exception as err:  # noqa: BLE001
        _show_error(err, "No se pudo obtener el espectro")
        return
    qlabel = st.radio("Magnitud representada", list(QUANTITY_LABELS), horizontal=True, key="sx_quantity")
    quantity = QUANTITY_LABELS[qlabel]
    st.altair_chart(sv.spectrum_chart(spec, quantity, selected_channel=ch.number), width="stretch")
    n_missing = sum(r["status"] != "ok" for r in spec.rows)
    st.caption(
        f"Posición RA {spec.ra:.5f}°, Dec {spec.dec:+.5f}°. {spec.n_measured} de 102 canales con valor; {n_missing} sin "
        "valor (marcas rosas sobre el eje: canales 51 y 52 sin datos en DR1, o apertura/fondo sin datos). Un punto "
        "por canal real; la barra horizontal es el intervalo del canal (WL_MIN–WL_MAX), no un error. Sin curva ni "
        "interpolación. Contorno hueco: algún píxel de entrada de la apertura tenía OVERFLOW (saturación) u OUTLIER. "
        "Línea discontinua vertical: canal mostrado arriba.")
    for w in spec.warnings:
        st.warning(w)
    st.markdown(
        '<div class="sc-note"><b>Qué es y qué no es este espectro.</b> Fotometría de apertura sobre el cubo '
        f'combinado, adaptando el método del tutorial de IRSA: apertura circular sobre el cielo de {spec.aperture.r_ap:g} '
        f'píxeles ({spec.aperture.r_ap * spec.pixel_scale_arcsec:.0f}″; fracciones de píxel con {spec.subpixels}×'
        f'{spec.subpixels} submuestras), menos la media con recorte 3σ del anillo {spec.aperture.r_in:g}–'
        f'{spec.aperture.r_out:g} píxeles por el área de la apertura, multiplicada por el ángulo sólido del píxel '
        f'({spec.pixel_solid_angle_sr:.4e} sr, píxeles HEALPix de igual área) → mJy. IRSA advierte que un espectro '
        'extraído del cubo <b>solo es apropiado para visualización</b>: no tiene incertidumbres (el cubo no incluye '
        'varianza; la dispersión del fondo no es un error del flujo). El tutorial usa círculos en coordenadas de '
        'píxel y Photutils con solapamiento exacto; aquí se usan distancias angulares y submuestras, por lo que '
        'los valores pueden diferir. No corrige la fracción de la PSF fuera de la apertura, puede incluir fuentes vecinas y el '
        'rayado del mosaico cerca de líneas intensas. No es una medida de precisión del flujo de una estrella ni '
        'permite afirmar la presencia de líneas o materiales. Para espectrofotometría científica, use la '
        f'<a href="{config.SPECTROPHOTOMETRY_TOOL_URL}" target="_blank">herramienta oficial SPHEREx '
        'Spectrophotometry de IRSA</a> (fotometría forzada sobre las imágenes Level 2, con incertidumbres; solo '
        'interfaz web, sin API documentada).</div>', unsafe_allow_html=True)

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
