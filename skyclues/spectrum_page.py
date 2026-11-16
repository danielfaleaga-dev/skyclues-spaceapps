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
LAYERS = {"IMAGE · surface brightness (MJy/sr)": "image", "NHITS · coverage (input pixels)": "nhits"}
QUANTITY_LABELS = {"Aperture flux density (mJy) · exploratory": "flux",
                   "Surface brightness of the pixel (MJy/sr)": "pixel"}
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
        return ("IRSA did not serve the partial read of the cube (it would have sent the whole ~320 MB file). "
                "Nothing has been downloaded or shown. Try again later.")
    if isinstance(err, sc.FileChangedError):
        return ("The cube changed at IRSA while it was being read (different ETag). What was read has been discarded; reload the "
                "page to read the new version.")
    if isinstance(err, sc.CubeFormatError):
        return ("The cube file does not have the documented structure; it is not interpreted. "
                f"Detail: {err}")
    if isinstance(err, archive.ArchiveTransientError):
        return ("NASA/IPAC IRSA is temporarily unavailable for the spectral cube (5xx error or "
                "timeout after several retries). No partial data have been shown.")
    if isinstance(err, archive.ArchivePermanentError):
        return "IRSA rejected the cube request (permanent error). No partial data have been shown."
    if isinstance(err, ValueError):
        return f"Invalid input: {err}"
    return "The spectral cube could not be read. No partial data have been shown."


def _show_error(err: Exception, what: str) -> None:
    if not theme.scientific():
        st.error(f'{what}. Try again; Scientific mode shows the details.')
        return
    st.error(f"{what}: {error_message(err)}")
    with st.expander("Technical detail"):
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
        multiband_page.set_kept("sx_pick_ra", ra)       # also the stashed copy: restore() must not undo the click
        multiband_page.set_kept("sx_pick_dec", dec)


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
    return theme.badge("centre at the expected position of the object" if follow else "fixed centre of the sequence")


def reading_guide(quantity: str, sci: bool) -> list[tuple[str, str]]:
    """What the spectrum plot shows, in the words of each level. The same facts in both."""
    unit = ("<b>mJy</b> (millijansky): how much light arrives from the aperture per unit of frequency "
            "(1 mJy = 10⁻²⁹ W·m⁻²·Hz⁻¹)."
            if quantity == "flux" else
            "<b>MJy/sr</b> (megajansky per steradian): brightness of a pixel per unit area of sky, not the total "
            "light of a source.")
    extra = (" The horizontal bar of each point is the channel interval (WL_MIN–WL_MAX), not an error." if sci else
             " A high value means more light in that channel; close to zero, that it is hardly distinguishable from the background.")
    return [
        ("Horizontal axis · wavelength",
         "The infrared «colour» of the light, in <b>µm</b> (micrometres, millionths of a metre; not parts per million). "
         "From 0.75 to 5.0 µm, all invisible to the eye. Each point is one of the 102 real channels."),
        ("Vertical axis · " + ("flux density" if quantity == "flux" else "surface brightness"), unit + extra),
        ("Peaks and valleys",
         "A peak is a brighter channel than its neighbours (possible emission); a valley, a fainter one (possible "
         "absorption, for example by ices or gases). Noise, a neighbouring source or the mosaic also produce them."),
        ("What cannot be concluded",
         "This spectrum is exploratory and has no uncertainties: it is not enough to claim that there is a line, a "
         "molecule or an ice, or to measure temperatures. It is useful for deciding what deserves a calibrated analysis."),
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
        st.caption("Source selected in Gaia DR3: ICRS catalogue coordinates, J2016.0. The position calculated for the cube does not confirm a SPHEREx detection." if sci else "Catalogue source; it does not confirm a SPHEREx detection.")
    if region.get("solar"):
        st.info("Moving body: this cube combines many dates. The sky is shown at a fixed coordinate; it is not an identified spectrum of the object or a detection." if sci else "This image shows the area of the sky, not an identified spectrum of the moving object.")
    multiband_page.restore(("sx_mode", "sx_channel"))
    try:
        ra_c, dec_c = validate_coordinates(inp["ra"], inp["dec"])
        fov = validate_fov_deg(inp["fov"])
    except ValueError as err:
        st.error(f"Invalid input: {err} Nothing has been read from the cube.")
        return

    astro = inp["astrometry"]
    epoch_info = {"propagated": False}
    if astro is not None and astro.has_proper_motion:
        try:
            with st.spinner("Querying the epoch of the cube and calculating the expected position…", show_time=True):
                expected_ra, expected_dec, epoch_info = cached_epoch(json.dumps(astro.to_dict(), sort_keys=True))
            # A saved sequence keeps its exact centre; a named object is centred on its expected position.
            if inp["follow"]:
                ra_c, dec_c = expected_ra, expected_dec
        except Exception as err:  # noqa: BLE001
            _show_error(err, "The tile header could not be read")
            return
    try:
        with theme.loading("Opening the region and reading the available channels at IRSA…" if sci else "Preparing this area of the sky…", "spectrum_region"):
            channels = channel_list(ra_c, dec_c)
    except Exception as err:  # noqa: BLE001
        theme.region_strip(inp["label"], ra_c, dec_c, fov)
        _show_error(err, "The cube channel table could not be read")
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

    if not sci:
        theme.hero("spectrum", "Spectrum · the infrared light of this area", "What infrared light does this area emit?",
                   "Infrared light is invisible to the eye. SPHEREx splits it into 102 colours (wavelengths). "
                   "Choose a colour to see the image, press a point and get its spectrum: how much light arrives in each "
                   "colour. Its peaks and valleys can give clues about gas, dust or ices, but do not identify them on their "
                   "own.")
    theme.region_strip(inp["label"], ra_c, dec_c, fov, _region_extra(epoch_info, inp["follow"]) if sci else '')
    theme.note(("<b>Producto combinado, no temporal.</b> " +
            "Cada imagen es un canal del cubo DR1: el promedio de muchas exposiciones de fechas distintas (sin luz "
            "zodiacal), en píxeles de 12.9″. Sirve para ver cómo cambia el cielo con la longitud de onda; no muestra "
            "cambios en el tiempo (para eso, «Time» usa observaciones individuales de 6.15″/px).") if sci else
            "Estas imágenes combinan muchas fechas: muestran colores, no cambios en el tiempo. Para comparar fechas, "
            "abre «Time».")
    if epoch_info.get("warning"):
        st.warning(epoch_info["warning"] + f" Reference epoch: {astro.epoch_jyear:.2f}. It is not a detection.")
    if epoch_info.get("propagated") and "mjd_mid" in epoch_info and sci:
        mv = epoch_info["motion_over_inputs_arcsec"]
        theme.note(
            f"<b>Moving target: {astro.name}</b> ({astro.total_pm_arcsec_yr:.2f}″/yr). "
            f"Catalogue reference epoch: {astro.epoch_jyear:.2f}. <b>Expected, calculated</b> position for "
            f"the midpoint of the input interval of this tile (it is not an effective observation epoch) "
            f"({epoch_info['date_mid']}; inputs from {epoch_info['date_beg']} to {epoch_info['date_end']}). "
            f"During that interval the object moves {mv:.1f}″ ({mv / 12.883:.2f} cube pixels): in the "
            "average it may appear elongated. The cross is a calculation, not a detection.")
    elif epoch_info.get('propagated') and not sci:
        st.caption('The cross marks a calculated position, not a detection.')

    # ---------------------------------------------------------------- display mode
    view_mode = st.segmented_control("Infrared image", multiband_page.MODES, required=True, default=multiband_page.MODES[0], key="sx_mode",
                         label_visibility="visible",
                         help="«Multiband composite» combines three real channels in false colour (R, G, B) with the "
                              "same centre and field. You can go back to «Single channel» at any time.")
    if view_mode == multiband_page.MODES[1]:
        multiband_page.stash(SINGLE_STATE_KEYS + SINGLE_SLIDER_KEYS)
        state.pop("sx_channel", None)       # given back from the stored channel on return
        target = (expected_ra, expected_dec) if epoch_info.get("propagated") else (ra_c, dec_c)
        multiband_page.render_section(ra_c, dec_c, fov, channels, target, cached_map, _show_error)
        st.caption("Go back to «Single channel» to explore the spectrum of a point.")
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
    theme.eyebrow("Spectral channel · increasing wavelength" if sci else "Choose an infrared colour")
    b1, mid, b2 = st.columns([1, 14, 1], vertical_alignment="center")
    b1.button("◀", key="sx_prev", on_click=_step_channel, args=(-1, numbers), help="Previous channel (shorter λ)")
    b2.button("▶", key="sx_next", on_click=_step_channel, args=(1, numbers), help="Next channel (longer λ)")
    with mid:
        number = st.select_slider("Channel (increasing wavelength)", options=numbers, key="sx_channel",
                                  format_func=lambda n: f"{n} · {by_number[n].wavelength_um:.3f} µm",
                                  label_visibility="collapsed")
    ch = by_number[number]

    left, right = st.columns([1.25, 1], gap="large")
    defaults = config.CUBE_APERTURE_DEFAULT_PX
    with left:
        layer_label = (st.radio("Layer", list(LAYERS), horizontal=True, key="sx_layer") if sci else
                       state.get('sx_layer', next(iter(LAYERS))))
        layer = LAYERS[layer_label]
        if not sci and layer == 'nhits':
            st.caption('Showing coverage; you can switch to brightness in «Scientific».')
        with theme.loading(f"Reading channel {ch.number} of the cube at IRSA…" if sci else "Preparing the image…", "spectrum_image"):
            try:
                cmap = cached_map(ra_c, dec_c, fov, ch.plane)
                png, info = cached_png(ra_c, dec_c, fov, ch.plane, layer)
                pixels = cached_pixels(ra_c, dec_c, fov, ch.plane)
            except Exception as err:  # noqa: BLE001
                _show_error(err, f"Channel {ch.number} could not be read")
                return
        pick = (state["sx_pick_ra"], state["sx_pick_dec"])
        ap_now = sc.Aperture(state.get("sx_rap", multiband_page.kept('sx_rap', defaults[0])), state.get("sx_rin", defaults[1]),
                             state.get("sx_rout", defaults[2]))
        tile0 = cmap.patches[0].tile
        target = (expected_ra, expected_dec) if epoch_info.get("propagated") else (ra_c, dec_c)
        pick_b = spectrum_analysis.point_b(region_key)      # second position, only if the user placed one
        chart = sv.field_chart(png, info, pixels, cmap, target=target, pick=pick, aperture=ap_now,
                               pixel_arcsec=tile0.pixel_scale_arcsec, pick_b=pick_b)
        # Fixed square chart; on a narrow screen it scrolls inside its own box instead of being scaled.
        with st.container(key="sx_field_box"):
            st.altair_chart(chart, on_select=_set_pick_from_chart, selection_mode="pick", key="sx_field",
                            width="content")
        st.image(sv.colorbar_png(info))
        spectrum_analysis.point_controls(sci, region_key)
        if sci:
            st.caption(
                "WCS geometry: each native pixel of the cube (12.9″) is drawn at its position, with its original value, without "
                f"resampling or smoothing; north up, east on the left (base raster of "
                f"{info['npix']} pixels, {info['screen_arcsec_per_px']:.1f}″/px; its size on screen adapts to the viewer). "
                f"Display scale specific to each channel "
                f"({'percentiles 1–99.5 of the field, asinh' if layer == 'image' else 'linear'}); compare intensities between "
                "channels with the spectrum. Pink/purple: non-finite value or NHITS = 0 (no usable data); it does not mean dark sky. Light grey: outside the region read. "
                "Blue cross: target; amber diamond: spectrum position, with its aperture and background annulus. "
                "Hover to see the value of each pixel; click to choose the spectrum position.")
        else:
            st.markdown("Press the image to choose a point. **Pink: no data.**")

    with right:
        if ch.blank:
            st.warning((f"**Channel {ch.number} has no data in DR1.** {ch.wavelength_um:.3f} µm, D{ch.detector} subchannel "
                       f"{ch.subchannel}: channel adjacent to the dichroic splitter. The official documentation publishes it "
                       f"empty (all NaN, NHITS = 0; BLANKCH header = '{tile0.header('PRIMARY').get('BLANKCH')}') "
                       "to keep the numbering. SkyClues does not fill it in or interpolate it.") if sci else
                       f"Channel {ch.number} has no data. Choose another infrared colour.")
        s = cmap.summary()
        if sci:
            theme.facts([
                (theme.unit("λ") + " central", f"{ch.wavelength_um:.3f} µm", f"{ch.wl_min_um:.3f}–{ch.wl_max_um:.3f} µm"),
                ("Detector · subchannel", f"D{ch.detector} · {ch.subchannel}", f"R = λ/Δλ = {ch.resolving_power:.0f}"),
                ("Pixels with data", f"{s['valid_fraction']:.1%}", f"{s['n_valid']} de {s['n_field']}"),
                ("Median NHITS", f"{s['nhits_median']:.0f}", f"minimum {s['nhits_min']}")])
            st.caption(f"Channel {ch.number} of 102 = plane {ch.plane} of the cube (0-based) · width {ch.bandwidth_um:.3f} µm · "
                       f"HEALPix tiles {', '.join(str(t) for t in s['tiles'])} · field pixels with OVERFLOW: "
                       f"{s['flag_pixels']['OVERFLOW']}, OUTLIER: {s['flag_pixels']['OUTLIER']}, SOURCE: "
                       f"{s['flag_pixels']['SOURCE']}. λ, interval and R come from the SPECTRAL_CHANNELS table of the FITS.")
        else:
            theme.facts([
                ("Wavelength", f"{ch.wavelength_um:.2f} µm", f"canal {ch.number} de 102"),
                ("Pixels with data", f"{s['valid_fraction']:.0%}", "of the field in this channel")])

        mx = config.CUBE_APERTURE_MAX_PX
        pxs = tile0.pixel_scale_arcsec

        def measure_controls():
            st.number_input("RA (°)", format="%.6f", min_value=0.0, max_value=359.999999, key="sx_pick_ra")
            st.number_input("Dec (°)", format="%.6f", min_value=-90.0, max_value=90.0, key="sx_pick_dec")
            ap = st.slider("Aperture radius (cube pixels)", 1.0, mx[0],
                           multiband_page.kept("sx_rap", defaults[0]), 0.5, key="sx_rap")
            rin, rout = st.slider("Background annulus: inner and outer radii (pixels)", 1.5, mx[2],
                                  multiband_page.kept("sx_ann", defaults[1:]), 0.5, key="sx_ann")
            st.caption(f"Aperture {ap * pxs:.0f}″ · annulus {rin * pxs:.0f}″–{rout * pxs:.0f}″ (1 pixel = {pxs:.2f}″).")
            return ap, rin, rout

        theme.eyebrow("Spectrum position")
        if sci:
            r_ap, r_in, r_out = measure_controls()
        else:
            st.markdown('The orange diamond marks the chosen point.' if pick_b is None else
                        'The black diamond (A) and the copper square (B) mark the two points.')
            r_ap = state.get('sx_rap', multiband_page.kept('sx_rap', defaults[0]))
            r_in, r_out = state.get('sx_ann', multiband_page.kept('sx_ann', defaults[1:]))
        state["sx_rin"], state["sx_rout"] = r_in, r_out
        go = st.button("Get the spectrum at this position", type="primary", key="sx_extract")

    # ---------------------------------------------------------------- spectrum
    # One plot and, under it, its context. Later analyses (comparing two spectra, inspecting peaks and
    # valleys, molecular or ice references, SPLICES) attach to this same plot and context, not to a new mode.
    params_now = (round(state["sx_pick_ra"], 6), round(state["sx_pick_dec"], 6), r_ap, r_in, r_out)
    if go or state.get("sx_spec_params") is None:
        state["sx_spec_params"] = params_now
    if pick_b is None:
        st.markdown("### Exploratory spectrum of a position" if sci else "### The light of the chosen point")
    else:
        st.markdown("### Espectros exploratorios de dos posiciones" if sci else "### The light of the two points")
    sp = state["sx_spec_params"]
    if sp != params_now:
        st.caption("The position or the aperture have changed: press «Get the spectrum at this position» to "
                   "update it. The previous spectrum is shown.")
    try:
        validate_coordinates(sp[0], sp[1])
        sc.Aperture(*sp[2:]).validate()
        with theme.loading("Reading the 102 channels around the position…" if sci else "Preparing the spectrum of this point…", "spectrum_plot"):
            spec = cached_spectrum(*sp)
    except Exception as err:  # noqa: BLE001
        _show_error(err, "The spectrum could not be obtained")
        return
    qlabel = (st.radio("Quantity shown", list(QUANTITY_LABELS), horizontal=True, key="sx_quantity") if sci else
              state.get('sx_quantity', next(iter(QUANTITY_LABELS))))
    quantity = QUANTITY_LABELS[qlabel]
    # The plot, the second spectrum (same aperture and annulus as A, never tuned per position), A − B, A / B
    # and the peaks and valleys: all on these axes.
    spectrum_analysis.render(spec, quantity, ch.number, sci, region_key,
                             lambda ra, dec: cached_spectrum(round(ra, 6), round(dec, 6), *sp[2:]), _show_error)
    n_missing = sum(r["status"] != "ok" for r in spec.rows)
    if sci:
        st.container(key="sx_notes_plot").caption(
            f"Position RA {spec.ra:.5f}°, Dec {spec.dec:+.5f}°. {spec.n_measured} of 102 channels with a value; {n_missing} without "
            "a value (pink marks on the axis: channels 51 and 52 without data in DR1, or aperture/background without data). One point "
            "per real channel; the horizontal bar is the channel interval (WL_MIN–WL_MAX), not an error. No curve or "
            "interpolation. Hollow outline: some input pixel of the aperture had OVERFLOW (saturation) or OUTLIER. "
            "Vertical dashed line: channel shown above.")
        with st.expander("How to read this chart"):
            theme.reading_guide(reading_guide(quantity, sci))
    else:
        theme.reading_guide([
            ("Horizontal axis", "The infrared colour (wavelength, in µm): from 0.75 µm on the left to 5 µm on "
                               "the right."),
            ("Height of each point", "How much light arrives in that colour. One point per measured colour; the pink marks "
                                     "are colours without data, not zero light."),
            ("Peaks and valleys", "A peak is more light than in the neighbouring colours; a valley, less. Press one on the "
                               "chart to examine it.")])
        st.container(key="sx_notes_plot_simple").caption('Indicative view: peaks on their own do not identify materials.')
        if spec.warnings:
            st.warning('There are limited data at this position. Scientific mode shows the details.')
        _footer(ra_c, dec_c, fov, state['sx_canal'])
        return
    for w in spec.warnings:
        st.warning(w)
    method = (
        "Aperture photometry on the combined cube, adapting the method of the IRSA tutorial: circular aperture "
        f"on the sky of {spec.aperture.r_ap:g} pixels ({spec.aperture.r_ap * spec.pixel_scale_arcsec:.0f}″; "
        f"pixel fractions with {spec.subpixels}×{spec.subpixels} subsamples), minus the 3σ-clipped mean of the "
        f"annulus {spec.aperture.r_in:g}–{spec.aperture.r_out:g} pixels times the area of the aperture, multiplied by the "
        f"solid angle of the pixel ({spec.pixel_solid_angle_sr:.4e} sr, equal-area HEALPix pixels) → mJy. IRSA "
        "warns that a spectrum extracted from the cube <b>is only appropriate for visualisation</b>: it has no "
        "uncertainties (the cube includes no variance; the background scatter is not a flux error). The tutorial "
        "uses circles in pixel coordinates and Photutils with exact overlap; here angular distances and "
        "subsamples are used, so the values may differ. It does not correct the fraction of the PSF outside the aperture, "
        "may include neighbouring sources and the striping of the mosaic near intense lines. It is not a precision measurement "
        "of the flux of a star nor does it allow claiming the presence of lines or materials. For scientific spectrophotometry "
        f'use the <a href="{config.SPECTROPHOTOMETRY_TOOL_URL}" target="_blank">official IRSA SPHEREx '
        "Spectrophotometry tool</a> (forced photometry on the Level 2 images, with uncertainties; web "
        "interface only, no documented API).")
    if sci:
        theme.note("<b>What this spectrum is and is not.</b> " + method)
    else:
        theme.note("<b>Exploratory spectrum, not calibrated.</b> It is useful for seeing the general shape of the light at this point. "
                   "It has no uncertainties and does not allow claiming the presence of lines or materials. For scientific "
                   f'measurements, use the <a href="{config.SPECTROPHOTOMETRY_TOOL_URL}" target="_blank">official '
                   "IRSA SPHEREx Spectrophotometry tool</a>.")
        with st.expander("Method and limitations of the spectrum"):
            st.html(f'<div class="sc-note">{method}</div>')

    with st.expander("Spectrum table (values per channel)"):
        df = spec.table()
        cols = ["canal", "lambda_um", "lambda_min_um", "lambda_max_um", "detector", "subcanal", "estado", "flujo_mjy",
                "fondo_mjysr", "fondo_sigma_mjysr", "n_fondo", "pixel_mjysr", "pixel_nhits", "nhits_min_apertura",
                "flags_apertura"]
        cols += [c for c in ("ap_pix_total", "ap_pix_invalidos", "ap_pix_nan", "ap_pix_nhits0", "ap_bloom",
                             "ap_overflow") if c in df.columns]          # coverage of the aperture (diagnostic)
        st.dataframe(df[cols], hide_index=True, width="stretch")
        st.caption("«fondo_sigma_mjysr» is the scatter (clipped at 3σ) of the annulus pixels: it describes the "
                   "background, it is not the flux uncertainty.")
        meta = {"producto": "SPHEREx DR1 All-Sky spectral cube", "doi": config.CUBE_DOI,
                "metodo": "exploratory aperture photometry (official IRSA tutorial); display only",
                "ra_deg": spec.ra, "dec_deg": spec.dec, "apertura_px": spec.aperture.r_ap,
                "anillo_px": [spec.aperture.r_in, spec.aperture.r_out], "pixel_arcsec": spec.pixel_scale_arcsec,
                "pixel_sr": spec.pixel_solid_angle_sr, "unidades": {"flujo_mjy": "mJy", "pixel_mjysr": "MJy/sr"},
                "teselas": spec.tiles}
        csv = "".join(f"# {k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in meta.items()) + \
            df[cols].to_csv(index=False)
        st.download_button("Download CSV with provenance", csv.encode("utf-8"),
                           file_name=f"skyclues_espectro_{spec.ra:.4f}_{spec.dec:+.4f}.csv", mime="text/csv",
                           key="sx_csv")

    with st.expander("Provenance of the product and limitations"):
        prov = pd.DataFrame(spec.tiles).drop_duplicates("tile")
        st.dataframe(prov.astype(str), hide_index=True, width="stretch")
        stats = sc.io_stats()
        st.markdown(
            f"- **Product:** SPHEREx DR1 All-Sky spectral cube, doi:{config.CUBE_DOI}. FITS files per HEALPix tile "
            f"of order 5 ({config.CUBE_DATA_URL}), the same ones as in the [official tutorial]({config.CUBE_TUTORIAL_URL}).\n"
            "- **Reading:** only the necessary rows, by HTTP byte ranges (each tile weighs ~320 MB and is never "
            "downloaded whole); bytes verified with Content-Range, size and ETag; local cache with SHA-256. "
            f"This process has read {stats['bytes_network'] / 2**20:.1f} MiB of HTTP bodies "
            f"in {stats['requests']} attempts (not counting HTTP/TLS headers).\n"
            "- **Values:** IMAGE in MJy/sr with the zodiacal light already subtracted by the pipeline; each pixel is the mean of "
            "NHITS input pixels (assignment to the nearest pixel, no smoothing). Input pixels with "
            "TRANSIENT, SUR_ERROR, NONFUNC, DICHROIC, MISSING_DATA, HOT, COLD, PHANMISS, NONLINEAR, PERSIST, "
            "CROSSTALK, STREAK, BLOOM, SNOWBALL, HALO or SATELLITE_HALO were excluded before averaging "
            "(Explanatory Supplement v2.1, §2.5 and §3.4). The FLAGS extension of the cube declares those masks (plus "
            "OVERFLOW, SOURCE and OUTLIER) and the active ones appear in the resulting pixels; SkyClues counts BLOOM and "
            "OVERFLOW in the aperture pixels and treats OVERFLOW and OUTLIER as caution. A channel with any "
            "aperture pixel without data (NaN value or NHITS = 0) is not measured: see «Channel quality».\n"
            "- **λ:** from the SPECTRAL_CHANNELS table of each FITS (central λ, WL_MIN, WL_MAX, R). "
            "Channel n = 17·(detector − 1) + subchannel; plane = n − 1.\n"
            "- **Limitations:** combined product of different dates (not temporal); 12.9″ pixel (≈ 2 Level 2 "
            "pixels); striping of the mosaic near intense lines (He 1.083 µm, Paα, PAH 3.3 µm, Brα) that is not "
            "averaged; channels 51 and 52 are empty in DR1; spectrum without uncertainties or aperture correction "
            "(display only).")
    _footer(ra_c, dec_c, fov, state["sx_canal"])


def _footer(ra: float, dec: float, fov: float, canal: int) -> None:
    st.html('<div style="height:.6rem"></div>')
    if theme.scientific():
        reference_page.render(ra, dec, fov, key="spectrum_ref")
    release_ui.share(ra, dec, fov, "espectral", canal)
    st.caption("Data: NASA/IPAC IRSA · SPHEREx DR1 All-Sky spectral cube (doi:10.26131/IRSA679), read by byte "
               "ranges from the official FITS files (without downloading whole tiles)." if theme.scientific() else 'Data: SPHEREx · NASA/IPAC IRSA.')
