"""Spectrum Explorer · multiband false-colour mode (Streamlit section).

Called from ``spectrum_page.render`` when the user chooses the multiband mode. It shares the
page's region (centre, FOV), its channel table and its cached channel maps, so switching mode
re-reads nothing that is already in memory and the region is never changed here.
"""

from __future__ import annotations

import json

import streamlit as st

from . import config, theme
from . import multiband as mb
from . import multiband_view as mv
from . import spectral_cube as sc

MODES = ["Single channel", "Multiband composite (RGB)"]
STRETCH_LABELS = {"Independent per channel": "independiente", "Common to the three channels (MJy/sr)": "comun"}
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


def set_kept(key: str, value) -> None:
    """Set a widget value from a callback AND in its stashed copy.

    A page that stashes a widget every run and restores it before drawing (see ``restore``) would
    otherwise give back the older stashed copy over a value changed by a callback, e.g. a click
    on a chart in the simple level."""
    st.session_state[key] = value
    st.session_state[_SHADOW + key] = value


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
    sci = theme.scientific()
    ok = mb.selectable(channels)
    by_number = {c.number: c for c in channels}
    numbers = [c.number for c in ok]
    defaults = mb.default_numbers(channels)
    restore(STATE_KEYS)
    for r in mb.ROLES:
        if st.session_state.get(ROLE_KEYS[r]) not in numbers:
            st.session_state[ROLE_KEYS[r]] = defaults[r]

    st.markdown("### Multiband composite · false colour" if sci else "### Imagen en color")
    st.markdown((
        '<div class="sc-note"><b>Display convention, not real colour.</b> Three infrared channels of the cube '
        '(0.75–5.0 µm, invisible to the eye) are assigned to red, green and blue. The values are those of the FITS, '
        'unmodified; only their representation changes. Channels 51 and 52 (no data in DR1) cannot be chosen.</div>') if sci else
        'Three colours represent infrared light that is invisible to the eye: this is **false colour**.',
        unsafe_allow_html=True)
    cols = st.columns(3)
    for col, r in zip(cols, mb.ROLES):
        with col:
            st.selectbox(f"{r} · {mb.ROLE_NAMES[r]}", numbers, key=ROLE_KEYS[r],
                         format_func=lambda n: f"Canal {n} · {by_number[n].wavelength_um:.3f} µm",
                         help="Only channels with data in DR1. Usual convention: R = longest λ, B = shortest λ.")
            c = by_number[st.session_state[ROLE_KEYS[r]]]
            if sci:
                st.caption(f"λ {c.wavelength_um:.3f} µm · ancho {c.bandwidth_um:.3f} µm "
                           f"({c.wl_min_um:.3f}–{c.wl_max_um:.3f}) · D{c.detector} subcanal {c.subchannel}")
    # Stable labels keep the browser's radio selection intact when changing detail level.
    mode = STRETCH_LABELS[st.radio("Contrast", list(STRETCH_LABELS), horizontal=True, key="mb_stretch",
                                   format_func=lambda x: 'Stretch each colour' if STRETCH_LABELS[x] == 'independiente' else 'Same contrast',
                                   help="Independent: each channel with its own contrast (the colours do not reflect "
                                        "brightness ratios). Common: same limits in MJy/sr for all three.")]
    chosen = tuple(int(st.session_state[ROLE_KEYS[r]]) for r in mb.ROLES)
    try:
        mb.select_channels(channels, dict(zip(mb.ROLES, chosen)))
    except ValueError as err:
        st.error(f"Invalid selection: {err}. Nothing has been read from the cube.")
        return
    key = (ra, dec, fov, chosen, mode)
    with theme.loading("Combining the three infrared colours…", "rgb"):
        try:
            comp = cached_composite(*key, channels, map_fn)
            png, info = cached_png(*key, comp)
            pixels = cached_pixels(*key, comp)
        except mb.InsufficientDataError as err:
            st.error(f"Insufficient data: {err}. Choose other channels or another region.")
            return
        except Exception as err:  # noqa: BLE001 - shown to the user, nothing partial is drawn
            show_error(err, "The composite could not be built")
            return

    left, right = st.columns([1.25, 1])
    with left:
        # Fixed square chart (same arcsecond length on both axes); on a narrow screen it scrolls
        # inside its own box instead of being scaled, which would misplace the pixel tooltips.
        with st.container(key="mb_field_box"):
            st.altair_chart(mv.composite_chart(png, info, pixels, comp, target=target), width="content",
                            key="mb_field")
        st.caption((
            "Exact WCS geometry: each native pixel (12.9″) at its position, without resampling; north up, east on the "
            "left. Colour only where the three channels have data. Pink/purple with white hatching: non-finite value or NHITS = 0 in at "
            "least one channel (never a partial colour). A purple tone without hatching can be a valid false colour; black can be valid low brightness. Grey dotted: outside the region read. Dashed circle: "
            "field of view; cross: target. Hover to see the original values (MJy/sr) of each channel.") if sci else
            'Pink with hatching: data missing. Purple without hatching can be a valid colour; black can be a faint area.')
    with right:
        cov = comp.coverage
        if not sci:
            theme.facts([('Area with data', f"{cov['fraccion_tres_canales']:.0%}", 'in all three colours')])
            st.markdown('Change the channels above to explore other combinations.')
            if cov['fraccion_tres_canales'] < mb.COVERAGE_WARN_FRACTION:
                st.warning('Only part of this area has data in all three colours. Try other channels.')
            if comp.display_stats()['poco_contraste']:
                st.info('With the same contrast, almost the whole area looks dark: the background sky is much fainter '
                        'than its brightest points. This is not a failure and no data are missing. To see the shape in each '
                        'colour, choose «Stretch each colour».')
            if comp.stretch.degenerate:
                st.info('Some colour is uniform because its brightness does not change in this area.')
            if any(mb.striping_lines(c) for c in comp.channels.values()):
                st.warning('These channels can show stripes produced by the instrument.')
            if any('OVERFLOW' in w for w in comp.warnings):
                st.warning('Some areas are too bright for the detector; their colours may be unreliable.')
            return
        st.dataframe(mv.assignment_table(comp), hide_index=True, width="stretch")
        c1, c2 = st.columns(2)
        c1.metric("Pixels with data in all 3 channels", f"{cov['fraccion_tres_canales']:.1%}",
                  f"{cov['tres_canales']} de {cov['n_campo']}", delta_color="off")
        c2.metric("With data in only 1–2 channels", f"{cov['parcial']}", "are shown as no data", delta_color="off")
        st.caption(
            f"Scale: asinh (a = {comp.stretch.asinh_a:g}) between percentiles {comp.stretch.percentiles[0]:g} and "
            f"{comp.stretch.percentiles[1]:g} of the {comp.stretch.n_pixels} pixels of the field with data in all three "
            f"channels; {mb.STRETCH_MODES[comp.stretch.mode]}. The contrast only affects the display. "
            "Alignment verified: same file and ETag, same WCS and same pixel centres in the three channels.")
    panel_cols = st.columns(3)
    for col, r in zip(panel_cols, mb.ROLES):
        c = comp.channels[r]
        col.image(cached_panel(*key, r, comp),
                  caption=f"{r}: channel {c.number} · {c.wavelength_um:.3f} µm (grey, same scale as in the composite; "
                          "pink: no data in this channel)", width="stretch")
    for w in comp.warnings:
        st.warning(w)
    st.markdown(
        '<div class="sc-note"><b>What this composite does not allow.</b> It is a visual aid for comparing the shape '
        'of the sky at three wavelengths of the combined cube (averaged dates). On its own it does not detect '
        'exoplanets or confirm moving objects, does not measure temperatures or chemical composition, does not detect '
        'variability (the cube is not temporal) and does not improve the signal-to-noise ratio: it does not add or average channels. '
        'A colour is due to the chosen scale as much as to the sky; for intensities, use the spectrum in single-channel '
        'mode.</div>', unsafe_allow_html=True)
    with st.expander("Provenance of the composite"):
        prov = comp.provenance()
        stats = sc.io_stats()
        st.markdown(
            f"- **Product:** SPHEREx DR1 All-Sky spectral cube, doi:{config.CUBE_DOI}; FITS per HEALPix tile of "
            f"order 5 read by HTTP ranges (single-channel mode reader, same cache verified with SHA-256).\n"
            f"- **Tiles:** {', '.join(str(t['tesela']) for t in comp.alignment['teselas'])}; resampling: none.\n"
            f"- **This process** has read {stats['bytes_network'] / 2**20:.1f} MiB of HTTP bodies in "
            f"{stats['requests']} attempts and {stats['bytes_cache'] / 2**20:.1f} MiB from the local cache.")
        st.download_button("Download provenance (JSON)", json.dumps(prov, ensure_ascii=False, indent=1,
                                                                     default=str).encode("utf-8"),
                           file_name=f"skyclues_rgb_{ra:.4f}_{dec:+.4f}_{'-'.join(map(str, chosen))}.json",
                           mime="application/json", key="mb_prov")
