"""Time Explorer page: authentic SPHEREx observations of the active region on different dates.

Presentation and orchestration only. The temporal engine (``sequence``, ``player``, ``motion``,
``quality``) is called exactly as before: same functions, same arguments, same thresholds. The
level (Simple / Scientific) changes which explanations and tables are shown, never an argument.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from astropy.time import Time

from . import archive, config, motion_page, navigation, player, reference_page, release_ui, saved_text, theme
from . import render as figures  # the module; `render` below is this page's entry point and would hide it
from .quality import flag_census
from .sequence import STRICT, find_sequence, load_sequence, report_urls, save_report

#: Proper motion below which a catalogued object is presented as fixed (display only; the sequence is unchanged).
MIN_PM_ARCSEC_YR = 0.01

STATUS_LABEL = {"pass": "✔ passes", "warn": "▲ warning", "fail": "✖ fails"}
GEOMETRY_OPTIONS = {
    "WCS: native pixels, no resampling of values": "exact",
    "Common grid: nearest neighbour (resampled)": "nearest",
}
ALL_DETECTORS = [1, 2, 3, 4, 5, 6]
TABS = ["Sequence", "Motion", "Quality", "Provenance"]
#: Display and search options. Stored apart from their widgets so that hiding the controls (Sencillo,
#: another view) never changes them: both levels always use the same values.
DEFAULTS = {"geometry": "exact", "subtract": True, "restrict": False, "halo": False, "enhance": False,
            "dets": ALL_DETECTORS, "max_frames": config.MAX_SEQUENCE_FRAMES}


# ----------------------------------------------------------------------------- saved results
def reference_reports() -> dict[str, str]:
    """Saved reports in results/ (sequences first), labelled from their content."""
    out = {}
    paths = sorted(config.RESULTS_DIR.glob("sequence_*.json")) + sorted(config.RESULTS_DIR.glob("pair_*.json"))
    for p in paths:
        if p.stem.endswith("null_test"):
            continue
        try:
            rep = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sel = rep.get("selected")
        if not sel:
            continue
        if rep.get("kind") == "sequence":
            fr = sel["frames"]
            label = (f"{p.stem.replace('sequence_', '')} · {len(fr)} epochs · D{fr[0]['detector']} · "
                     f"{fr[0]['lambda_target_um']:.2f} µm · {fr[0]['collection']}")
        else:
            label = (f"{p.stem.replace('pair_', '')} · pair · D{sel['a']['detector']} · "
                     f"Δt {sel['metrics']['delta_t_days']:.0f} d · {sel['a']['collection']}")
        out[label] = str(p)
    return out


def saved_path(stem: str | None) -> Path | None:
    if not stem:
        return None
    p = config.RESULTS_DIR / f"{stem}.json"
    return p if p.is_file() else None


def open_saved(stem: str, label: str | None = None) -> None:
    """Callback: make a saved sequence the active region and show it (no search is repeated)."""
    p = saved_path(stem)
    if p is None:
        return
    report = saved_text.tree(json.loads(p.read_text(encoding="utf-8")))   # display text only; the file is not modified
    navigation.set_from_report(st.session_state, st.query_params, stem, report, label)
    st.session_state["view_request"] = "time"


def _open_saved_from_select(refs: dict[str, str]) -> None:
    label = st.session_state.get("time_saved")
    if label in refs:
        open_saved(Path(refs[label]).stem)


@st.cache_resource(show_spinner=False, max_entries=8)
def cached_sequence(report_json: str):
    # Comparability (masks, coverage, S1-S9) always uses the strict mask.
    return load_sequence(json.loads(report_json), mask_classes=STRICT)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_player(report_json: str, subtract: bool, restrict: bool, geometry: str, halo: bool, simple: bool = False,
                  presentation: str = '') -> str:
    return player.build_player(cached_sequence(report_json), subtract, restrict, geometry, halo, simple)


def irsa_error(err: Exception) -> str:
    """User message by error class (never guessed from the text)."""
    if isinstance(err, archive.ArchiveTransientError):
        return ("NASA/IPAC IRSA is temporarily unavailable (server busy, 5xx error or timeout "
                "after several retries). No partial data has been shown. Try again in a few "
                "minutes or open a verified sequence.")
    if isinstance(err, archive.ArchivePermanentError):
        return ("IRSA rejected the request (permanent error, e.g. HTTP 400/404). Retrying will not fix it: "
                "check the coordinates and the field of view. No partial data has been shown.")
    if isinstance(err, archive.CorruptFitsError):
        return ("A received FITS file is incomplete or damaged and was discarded (it is neither used nor saved). "
                "No partial data has been shown. Try again later.")
    return "Could not complete access to IRSA. No partial data has been shown."


# ----------------------------------------------------------------------------- options
def opt(name: str):
    return theme.persistent(name, DEFAULTS[name])


def search_key(inp: dict) -> tuple:
    a = inp["astrometry"]
    return (round(inp["ra"], 7), round(inp["dec"], 7), inp["fov"], a.name if a is not None else None)


def _request_search(refresh: bool = False) -> None:
    st.session_state["time_autorun"] = True
    if refresh:
        st.session_state["time_refresh"] = True


def _refresh_saved() -> None:
    """Callback: query the archive again for the region of a saved sequence (SIA2, on demand)."""
    region = navigation.get_region(st.session_state, st.query_params)
    region.update(report=None, fixed_centre=False)
    _request_search(refresh=True)


def search_options() -> None:
    with st.popover("Search options", help="Which observations are considered when searching for a comparable sequence."):
        st.multiselect("Detectors", ALL_DETECTORS, key=theme.bind("dets", DEFAULTS["dets"]), on_change=theme.keep,
                       args=("dets",), help="D1–D3: 0.75–2.41 µm (SWIR) · D4–D6: 2.42–5.0 µm (MWIR)")
        st.slider("Maximum number of epochs", 2, 8, key=theme.bind("max_frames", DEFAULTS["max_frames"]),
                  on_change=theme.keep, args=("max_frames",))
        if not opt("dets"):
            st.caption("Choose at least one detector.")
        st.button("Search again with these options", key="time_research", on_click=_request_search,
                  disabled=not opt("dets"), width="stretch")
        st.caption("A search usually takes 1 to 2 minutes: the FITS cutouts are downloaded from IRSA.")


def display_options() -> None:
    with st.popover("Display options", help="They change how the frames are drawn, never the metrics."):
        labels = list(GEOMETRY_OPTIONS)
        current = next(lbl for lbl, v in GEOMETRY_OPTIONS.items() if v == opt("geometry"))
        st.session_state["w_geometry_label"] = current
        st.radio(
            "Frame geometry", labels, key="w_geometry_label",
            on_change=lambda: st.session_state.update(opt_geometry=GEOMETRY_OPTIONS[st.session_state["w_geometry_label"]]),
            help="WCS: each pixel of each epoch is drawn where its WCS places it, with its original value; no value "
                 "is resampled (on screen, positions are rounded to the screen pixel). Common grid: each "
                 "epoch is copied onto the epoch 1 grid by nearest neighbour (the one the metrics use); a "
                 "fixed star can shift by up to ½ pixel per axis.")
        st.checkbox("Subtract the zodiacal model (IMAGE − ZODI)", key=theme.bind("subtract", True), on_change=theme.keep,
                    args=("subtract",),
                    help="The zodiacal background changes with the date; subtracting it avoids mistaking it for a change in the sky.")
        st.checkbox("Highlight the region common to all epochs", key=theme.bind("restrict", False),
                    on_change=theme.keep, args=("restrict",),
                    help="Pixels that are valid in only some epochs are tinted light blue.")
        st.toggle("Exploratory mode: show HALO pixels", key=theme.bind("halo", False), on_change=theme.keep,
                  args=("halo",),
                  help="HALO marks neighbours of pixels with transients (often the charge overflow from a "
                       "bright star) and of 'snowballs'. The SPHEREx documentation recommends caution when "
                       "using them. In this mode they are shown on a copper scale; they are never counted as valid in the metrics.")
        st.caption("The metrics and criteria always use the strict mask: unusable + artifacts (HALO included).")


def active_options_note() -> str:
    """Options that differ from the defaults, named so a result is never silently different."""
    names = {"geometry": "resampled common grid", "subtract": "zodiacal model not subtracted",
             "restrict": "common region highlighted", "halo": "HALO pixels visible"}
    on = [names[k] for k in names if opt(k) != DEFAULTS[k]]
    return "; ".join(on)


# ----------------------------------------------------------------------------- search
def run_search(inp: dict, refresh: bool) -> dict | None:
    dets, max_frames = list(opt("dets")), int(opt("max_frames"))
    fov = inp["fov"]
    sci = theme.scientific()
    box = st.status(f"Searching for comparable observations in NASA/IPAC IRSA (field {fov * 60:.1f}′)…" if sci else 'Searching for images to compare…', expanded=True)
    stage_text = box.empty()
    stage_text.write("Connecting to the archive; the first search can take several minutes.")
    stages = {'catalog': 'Querying the available images…', 'wavelengths': 'Searching for images that can be compared…',
              'download': 'Downloading the required images…', 'evaluate': 'Checking the dates and the quality…', 'done': 'Images ready.'}
    try:
        with theme.loading("Searching for images of this area of the sky…", "time_search"):
            _, rep = find_sequence(inp["ra"], inp["dec"], fov, detectors=dets, max_frames=max_frames, log=lambda m: None,
                                   progress=lambda stage, frac, msg: stage_text.write(msg if sci else stages.get(stage, 'Preparing the images…')),
                                   astrometry=inp["astrometry"], **({"refresh": True} if refresh else {}))
    except ValueError as err:
        box.update(label="Invalid input", state="error", expanded=True)
        st.error(f"Invalid input: {err} No query was made.")
        return None
    except Exception as err:  # noqa: BLE001 - classified for the user
        box.update(label="The search could not be completed", state="error", expanded=True)
        st.error(irsa_error(err))
        with st.expander("Technical detail"):
            st.code(f"{type(err).__name__}: {err}", language=None)
        return None
    box.update(label=f"Search completed in {rep['elapsed_s']} s", state="complete", expanded=False)
    try:
        t = rep["target"]
        save_report(rep, f"search_{t['ra_deg']:.4f}_{t['dec_deg']:+.4f}_{fov:g}")
    except OSError:
        pass  # read-only deployments: the report stays in the session
    return rep


def pending(inp: dict, sci: bool) -> None:
    """The region has not been searched yet in this session (for instance, opened from a link)."""
    if not sci:
        theme.hero("time", "Time · observations on different dates", "Has anything changed in this area of the sky?",
                   "SPHEREx observes the same sky several times. SkyClues finds those real images, sorts them by "
                   "date and prepares them for comparison: you can play them as a sequence, alternate two dates "
                   "and check whether something moved.")
    theme.region_strip(inp["label"], inp["ra"], inp["dec"], inp["fov"])
    st.html(('<div class="sc-empty"><b>No observations have been searched for in this region yet.</b><br>The search queries '
            'the NASA/IPAC IRSA archive and downloads the FITS cutouts it needs: it usually takes 1 to 2 minutes. '
            'You can keep browsing in the meantime.</div>') if sci else
            '<div class="sc-empty"><b>We have not searched for images of this area yet.</b> The search queries the NASA archive '
            'and may take a minute or two.</div>')
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("Find observations", type="primary", key="time_search", on_click=_request_search,
                  disabled=not opt("dets"))
        if sci:
            search_options()


# ----------------------------------------------------------------------------- page
def render(level: str) -> None:
    sci = level == "scientific"
    state, params = st.session_state, st.query_params
    region = navigation.get_region(state, params)
    inp = navigation.explorer_inputs(region)
    if region.get("gaia"):
        st.caption("Selected source in Gaia DR3 (ICRS, J2016.0). Positions for the SPHEREx dates are calculations, not detections." if sci else 'Catalogue source; it does not confirm a SPHEREx detection.')
    if region.get('solar'):
        from . import moving_page
        moving_page.render(region,sci)
        return
    refs = reference_reports()

    for e in state.pop("region_errors", []):
        st.error(e)

    pinned = saved_path(region.get("report"))
    autorun = state.pop("time_autorun", False)
    refresh = state.pop("time_refresh", False)
    if pinned is not None and not refresh:
        report = saved_text.tree(json.loads(pinned.read_text(encoding="utf-8")))
        origin = pinned.stem
    else:
        reports = state.setdefault("time_reports", {})
        key = search_key(inp)
        report = reports.get(key)
        origin = "Time Explorer search"
        if report is None or refresh:
            if not (autorun or refresh):
                pending(inp, sci)
                _footer(inp["ra"], inp["dec"], inp["fov"], refs, sci)
                return
            theme.region_strip(inp["label"], inp["ra"], inp["dec"], inp["fov"])
            new = run_search(inp, refresh)
            if new is None:
                st.button("Retry", key="time_retry", on_click=_request_search)
                return
            report = reports[key] = new
            st.rerun()

    retrieval = report.get("retrieval") or {}
    n_failed = retrieval.get("n_failed", len(report.get("retrieval_failures") or []))

    if not report.get("selected"):
        theme.region_strip(inp["label"], inp["ra"], inp["dec"], inp["fov"])
        _download_warning(report, retrieval, n_failed)
        st.warning(f"No admissible sequence was found ({report.get('n_records', 0)} images, "
                   f"{report.get('n_candidates', 0)} with the full field). Try a smaller field or other detectors.")
        if report.get("options"):
            st.dataframe(pd.DataFrame(report["options"]).astype(str), hide_index=True)
        if sci:
            search_options()
        _footer(inp['ra'], inp['dec'], inp['fov'], refs, sci)
        return

    report_json = json.dumps(report, sort_keys=True, default=str)
    urls = report_urls(report)
    missing = [u for u in urls if archive.local_copy(u) is None]
    if missing:
        box = st.status(f"Downloading {len(missing)} FITS cutouts from IRSA…", expanded=True)
        bar = box.progress(0.0, text="Connecting to IRSA…")
        got = archive.fetch_many(urls, progress=lambda done, total, n: bar.progress(
            done / max(total, 1), text=f"{done} of {total} cutouts ready ({n} downloaded)"))
        failed = [r for r in got.values() if isinstance(r, Exception)]
        if failed:
            box.update(label="Not all cutouts could be retrieved", state="error", expanded=True)
            st.error(irsa_error(failed[0]))
            with st.expander("Technical detail"):
                st.code("\n".join(str(e) for e in failed), language=None)
            return
        box.update(label="FITS cutouts obtained", state="complete", expanded=False)

    with theme.loading("Verifying FITS integrity and aligning epochs…" if sci else "Preparing the images…", "time_sequence"):
        try:
            seq = cached_sequence(report_json)
        except (ValueError, RuntimeError, OSError) as err:
            st.error(f"Could not load the sequence: {err}")
            return
    m = seq.metrics
    # Kept for Spectrum Explorer's reference to the open sequence (centre, field, catalogue astrometry).
    state["shared_region"] = {
        "ra": float(seq.ra), "dec": float(seq.dec), "fov": float(seq.field_deg), "label": origin,
        "astrometry": seq.astrometry.to_dict() if seq.astrometry is not None else None}

    # ---------------------------------------------------------------- summary
    status_cls = "sc-ok" if seq.admissible and not seq.warnings else ("sc-warn" if seq.admissible else "sc-fail")
    status_txt = ("Comparable" if not seq.warnings else "Comparable with warnings") if seq.admissible else "Not comparable"
    theme.region_strip(inp["label"], float(seq.ra), float(seq.dec), float(seq.field_deg), theme.badge(status_txt, status_cls))
    _download_warning(report, retrieval, n_failed)
    _saturation_note(m, sci)

    centre_rule = (report.get("target", {}).get("centre") or {}).get("rule")
    # A catalogue proper motion of ~0 (e.g. a nebula) is not a moving target: no cross caption for it.
    moves = seq.target_moves and seq.astrometry.total_pm_arcsec_yr >= MIN_PM_ARCSEC_YR
    if moves and sci:
        a = seq.astrometry
        p0, p1 = seq.target_position(0), seq.target_position(seq.n - 1)
        theme.note(
            f'<b>Moving target: {a.name}</b> ({a.total_pm_arcsec_yr:.2f}″/yr; {a.source}). Position '
            f'<b>calculated</b> for epoch 1: RA {p0[0]:.5f}°, Dec {p0[1]:+.5f}°; for epoch {seq.n}: RA '
            f'{p1[0]:.5f}°, Dec {p1[1]:+.5f}°. The player cross follows that calculation; it is not a detection by '
            'SPHEREx. Field centre: ' + (centre_rule or "—") + '.')
    elif moves:
        st.caption('The cross in the images marks a calculated position, not a detection.')
    elif centre_rule and sci:
        st.caption(f"Field centre: {centre_rule}.")

    f0 = seq.frames[0]
    det = f0.detector
    if sci:
        theme.facts([
            ("Epochs", str(seq.n), ""),
            ("Total interval", f"{m['span_days']:.1f} d", ""),
            (theme.unit("λ") + " in the target", f"{f0.lambda_target_um:.3f} µm",
             f"dispersion {m['lambda_spread_target_bw']:.2f} BW"),
            ("Valid common coverage", f"{m['coverage_common_valid']:.1%}", ""),
            ("Detector", f"D{det}", f"{config.BANDS_UM[det][0]}–{config.BANDS_UM[det][1]} µm")])
    else:
        theme.facts([
            ("Observed dates", str(seq.n), "real SPHEREx images"),
            ("From first to last", f"{m['span_days']:.0f} days", ""),
            ("Same infrared colour", f"{f0.lambda_target_um:.2f} µm", "so that brightness is comparable")])
        theme.reading_guide([
            ("What you are looking at", "The same area of the sky photographed on different dates, one image per date. There "
                                 "are no invented images in between."),
            ("How to compare them", "“Play” shows them in order; “Blink” alternates two dates so that a change "
                                 "jumps out at you."),
            ("Is something moving?", "Blinking is not enough: the “Motion” tab measures it with fixed reference stars "
                                "and tells you whether it is confirmed.")])
        st.caption({"sc-ok": "Images prepared for comparison between dates.",
                    "sc-warn": "The dates can be compared, with warnings: check “Quality” before drawing conclusions.",
                    "sc-fail": "These dates do not meet the criteria for comparison: check “Quality”."}[status_cls])

    tab_play, tab_move, tab_q, tab_meta = st.tabs(TABS, key="time_tab", on_change="rerun")

    if tab_play.open:
        with tab_play:
            with st.container(horizontal=True, vertical_alignment="center"):
                if sci:
                    display_options()
                    search_options()
                st.toggle("Infrared enhancement", key=theme.bind("enhance", False), on_change=theme.keep,
                          args=("enhance",),
                          help="Combines several real exposures of the same area to reduce noise and "
                               "reveal fainter sources. It does not smooth or fill in the image.")
            if opt("enhance"):
                from . import enhance_page
                enhance_page.render(seq, report_json, sci)
            else:
                _sequence_player(seq, report_json, sci)

    if tab_move.open:
        with tab_move:
            motion_page.render(seq, report_json, level)

    if tab_q.open:
        with tab_q:
            _quality(seq, m, sci)

    if tab_meta.open:
        with tab_meta:
            _provenance(seq, report, pinned is not None, sci)

    _footer(float(seq.ra), float(seq.dec), float(seq.field_deg), refs, sci)


def _sequence_player(seq, report_json: str, sci: bool) -> None:
    geometry = opt("geometry")
    with theme.loading("Preparing the playback…", "time_player"):
        html = cached_player(report_json, bool(opt("subtract")), bool(opt("restrict")), geometry, bool(opt("halo")),
                             simple=not sci, presentation=player.presentation_key())
    components.html(html, height=660, scrolling=True)
    active = active_options_note()
    if active and not sci:
        st.caption('Your display settings from Scientific mode are kept.')
    if sci:
        geo_txt = ("WCS geometry: each native pixel is drawn where its WCS places it, with its original value "
                   "(no resampling of values); the rotation between visits shows up as tilted pixels. On "
                   f"screen, 1 pixel ≈ {player.screen_scale_arcsec(seq):.1f}″." if geometry == "exact" else
                   "RESAMPLED product: each epoch is copied onto the epoch 1 grid by nearest "
                   "neighbour (shift of up to ½ pixel per axis).")
        st.caption("Each frame is a real SPHEREx exposure (no intermediate frames or temporal "
                   f"interpolation), with the same intensity scale. {geo_txt} The on-screen size is fixed: a "
                   "larger field of view shows more sky, it is not a zoom. A visual difference is not by itself "
                   "a detection of motion or variability.")
    else:
        st.markdown('Play the dates or use **Blink** to alternate two images. To check for possible motion, open «Motion».')


def _download_warning(report, retrieval, n_failed) -> None:
    if not n_failed:
        return
    kinds = {f.get("kind", "desconocido") for f in report.get("retrieval_failures") or []}
    st.warning(f"Incomplete download: {n_failed} of {retrieval.get('n_requested', '?')} FITS cutouts could not be "
               f"retrieved from IRSA ({', '.join(sorted(kinds))}). The selection was made without them, so a "
               "better sequence may exist; repeat the search later to complete it.")
    with st.expander("Cutouts not obtained"):
        st.dataframe(pd.DataFrame(report.get("retrieval_failures") or []).astype(str), hide_index=True)


def _saturation_note(m: dict, sci: bool) -> None:
    """Explain pink (no-data) areas caused by saturation, using the saturated fraction the sequence measured.

    Shown only when the saturated pixels (OVERFLOW/NONLINEAR) exceed the sequence's own warning threshold; it never
    changes a metric or a mask."""
    fractions = [float(f) for f in (m.get("saturation_fraction") or [])]
    worst = max(fractions, default=0.0)
    if worst <= config.SATURATION_WARN_FRACTION:
        return
    if sci:
        theme.note(f"<b>Saturated pixels.</b> Up to {worst:.1%} of the field is flagged OVERFLOW or NONLINEAR in at least one "
                   f"epoch (warning threshold {config.SATURATION_WARN_FRACTION:.1%}). Those pixels have no valid data and are "
                   "excluded by the strict mask: they are not zero light. Per-epoch fractions are in the criteria of «Quality».")
    else:
        pct = f"{worst:.0%}" if worst >= 0.01 else f"{worst:.1%}"
        theme.note("<b>Part of this area is too bright for the detector.</b> The instrument saturates around very bright "
                   f"sources: up to {pct} of the area is saturated in at least one image, and saturated pixels have no valid data "
                   "(they appear pink). It is a limit of the observation, not an error. Move the map to a fainter position, "
                   "or try another object.")


def _quality(seq, m, sci: bool) -> None:
    if not sci:
        st.markdown('### Image quality')
        st.markdown('These dates can be compared with one another.' if seq.admissible and not seq.warnings else
                    'There are limitations when comparing these dates. See Scientific mode for the reasons.')
        theme.facts([('Comparable area', f"{m['coverage_common_valid']:.0%}", 'with data on all dates')])
        return
    st.markdown("### Comparability criteria")
    st.caption("All epochs are evaluated at once, always with the strict mask. They are the same at both levels.")
    st.dataframe(pd.DataFrame([{"": c["id"], "criterion": c["criterion"], "value": c["value"], "threshold": c["threshold"],
                                "status": STATUS_LABEL[c["status"]], "verification": c.get("basis", "effective")}
                               for c in seq.criteria]),
                 hide_index=True, width="stretch")
    if sci:
        st.caption("“verification”: *effective* = calculated here from the data; *archive guarantee* = IRSA only publishes "
                   "images with L2DQA = PASS and FINAST = 0 (Explanatory Supplement §3.2.12), so the criterion is "
                   "checked in the header but cannot discriminate between archive products.")
    for n in seq.notes:
        theme.note(n)

    def tables():
        cols = st.columns(2)
        with cols[0]:
            st.image(figures.figure_png(figures.sequence_coverage_figure(seq)))
        with cols[1]:
            st.image(figures.figure_png(figures.sequence_spread_figure(seq)))
        st.markdown(f"Valid region common to the {seq.n} epochs: **{m['coverage_common_valid']:.1%}** of the field "
                    f"({m['n_common_px']} pixels). Maximum λ spread in that region: "
                    f"**{m['lambda_spread_common_max_bw']:.2f}** bandwidths.")
        gain = pd.DataFrame({"epoch": [i + 1 for i in range(seq.n)], "date": [f.date_utc[:16] for f in seq.frames],
                             "coverage gained if excluded (points)":
                                 [round(100 * g, 1) for g in m["coverage_gain_if_frame_removed"]]})
        st.dataframe(gain, hide_index=True, width="stretch")
        q = pd.DataFrame([{"epoch": i + 1, "date (UTC)": f.date_utc[:16], **{
            "L2 DQA": f.quality["L2DQAFLG"], "FINAST": f.quality["FINAST"],
            "valid in field (%)": round(100 * f.quality["valid_fraction_in_field"], 1),
            "HALO only (%)": round(100 * f.quality.get("halo_only_fraction_in_field", float("nan")), 2),
            "saturation (%)": round(100 * f.quality["saturation_fraction_in_field"], 3),
            "ZODI (MJy/sr)": round(f.quality["zodi_median_mjysr"], 3),
            "PSF FWHM (″)": round(float(f.quality["psf_fwhm_arcsec"] or float("nan")), 2),
            "max. common-grid shift (px)": round(float(seq.placement_error_px(i)[seq.field_mask].max()), 2)}}
            for i, f in enumerate(seq.frames)])
        st.markdown("#### Quality per epoch")
        st.dataframe(q, hide_index=True, width="stretch")
        st.caption("“HALO only”: field pixels masked only by HALO (visible in exploratory mode). "
                   "“max. shift”: maximum distance between a pixel of the common grid and the native pixel that the nearest "
                   "neighbour copies there (0 in the reference epoch).")
        k = st.selectbox("FLAGS of the epoch", list(range(1, seq.n + 1)), key="time_flags_epoch",
                         format_func=lambda i: f"{i} · {seq.frames[i - 1].date_utc[:16]}")
        img = seq.frames[k - 1].image
        df = pd.DataFrame(flag_census(img.flags, img.flag_defs))
        df["fraction"] = (df["fraction"] * 100).round(2)
        st.dataframe(df[df["pixels"] > 0].rename(columns={"name": "flag", "class": "class", "pixels": "pixels",
                                                          "fraction": "%", "description": "description"}),
                     hide_index=True, width="stretch")
        st.caption("“unusable” and “artifact” are masked; “info” (SOURCE, FULLSAMPLE) is not. Reference: SPHEREx "
                   "Explanatory Supplement v2.1, table 16 (HALO: “caution recommended”; SATELLITE_HALO: "
                   "“not recommended”).")

    if sci:
        st.markdown("### Coverage and wavelength")
        tables()
    else:
        with st.expander("Coverage, wavelength and quality of each date"):
            tables()
    with st.expander("Scientific limitations"):
        st.markdown(
            "- **Defined comparison:** surface brightness (IMAGE − ZODI, MJy/sr) of the same detector and effective LVF "
            "channel, on the valid pixels. It is not source photometry or automatic motion detection.\n"
            "- The per-pixel λ comes from the WCS-WAVE table (display precision, ~1 nm).\n"
            "- Differences between epochs may be due to noise, background, PSF, persistence, cosmic rays or residual "
            "Δλ; by themselves they do not imply variability or astronomical motion.\n"
            "- **Geometry:** the player draws native pixels at their WCS position by default, without resampling "
            "of values; the visible precision is limited by the screen pixel (shown on each frame), not by the WCS. "
            "The metrics (masks, coverage, S1–S9) use the epoch 1 grid with nearest neighbour: "
            "it decides which pixel is compared (up to ½ pixel per axis, ≈4″), and never alters the values.\n"
            "- **HALO:** always excluded from the metrics; the exploratory mode only displays it, marked in copper.\n"
            "- **Field of view:** larger fields require the whole region to fall inside the detector in every "
            "epoch, so fewer epochs may be comparable.\n"
            "- **Moving targets:** the position is calculated for each date with Astropy from the SIMBAD astrometry "
            "(catalogue epoch, proper motion, parallax and radial velocity when they exist); without "
            "proper motion in the catalogue, the position is the same on all dates. A calculated position is not "
            "a detection. Coordinates typed in by hand are used as they are for all dates.")


def _provenance(seq, report: dict, is_saved: bool, sci: bool) -> None:
    if sci:
        release_ui.discovery(report)
    with st.container(horizontal=True, vertical_alignment="center"):
        if is_saved:
            st.button("Update observations", key="refresh_saved", on_click=_refresh_saved,
                      help="Query the archive (SIA2) again for this region and repeat the search.")
        else:
            st.button("Update observations", key="refresh_observations", on_click=_request_search,
                      kwargs={"refresh": True}, disabled=not opt("dets"),
                      help="Query the archive (SIA2) again for this region and repeat the search.")
    rows = []
    for i, f in enumerate(seq.frames):
        s = f.summary()
        tp = seq.target_position(i)
        rows.append({"epoch": i + 1, "mean date (UTC)": s["date_utc"], "MJD": round(s["mjd"], 5),
                     "obs_id": s["obs_id"], "collection": s["collection"], "detector": s["detector"],
                     "computed target (RA, Dec °)": f"{tp[0]:.5f}, {tp[1]:+.5f}",
                     "target λ (µm)": round(s["lambda_target_um"], 4),
                     "bandwidth (µm)": round(s["bandwidth_target_um"], 4),
                     "exposure (s)": s["exptime_s"], "software": s["software_version"],
                     "archivo": s["file_name"], "SHA-256": s["sha256"][:16] + "…"})
    df = pd.DataFrame(rows).astype(str)
    st.markdown("### Observations in this sequence")
    simple_cols = ["epoch", "mean date (UTC)"]
    st.dataframe(df if sci else df[simple_cols], hide_index=True, width="stretch")
    if not sci:
        st.caption('Real SPHEREx images, available at NASA/IPAC IRSA.')
        return
    st.caption("Source: NASA/IPAC Infrared Science Archive. SPHEREx DR1 Spectral Images, doi:10.26131/IRSA678; "
               "SPHEREx QR3. Integrity: SHA-256 of each FITS checked against the report.")
    with st.expander("IRSA cutouts (reproducible)", expanded=sci):
        st.code("\n".join(f"{i + 1}: {f.cutout_url}" for i, f in enumerate(seq.frames)), language=None)
    with st.expander("Options evaluated when choosing the sequence"):
        if report.get("options"):
            st.caption("Selection rule: " + report.get("selection_rule", ""))
            optdf = pd.DataFrame(report["options"])
            optdf["coverage (%)"] = (optdf["coverage_common_valid"] * 100).round(1)
            st.dataframe(optdf[["origin", "detector", "n_frames", "coverage (%)", "lambda_spread_common_max_bw",
                                "span_days", "admissible", "dates"]].astype(str), hide_index=True, width="stretch")
            for r in report.get("rejected_larger_options", []):
                st.markdown(f"- Option with **{r['n_frames']} epochs** (D{r.get('detector', '?')}, coverage "
                            f"{r['coverage']:.1%}) discarded: {'; '.join(r['reasons'])}")
        else:
            st.caption("Pair result (no sequence exploration).")
    obs = report.get("observations", [])
    if obs:
        with st.expander(f"Observations available in the archive ({len(obs)})"):
            odf = pd.DataFrame(obs)
            odf["date (UTC)"] = pd.Series(Time(odf["mjd_mid"].to_numpy(), format="mjd").isot).str.slice(0, 16)
            cols_obs = [c for c in ["date (UTC)", "collection", "detector", "obs_id", "lambda_est_um",
                                    "bandwidth_est_um", "exptime_s", "field_margin_px", "file_name"] if c in odf]
            st.caption(f"{len(odf)} images with the full field inside the detector (of {report.get('n_records')} "
                       "that contain the target). λ estimated from metadata; the final decision uses the FITS.")
            st.dataframe(odf.sort_values("mjd_mid")[cols_obs].round(4), hide_index=True, width="stretch")


def _footer(ra: float, dec: float, fov: float, refs: dict[str, str], sci: bool) -> None:
    """Context tools that belong to the region, after the science: references, link, saved results."""
    st.html('<div style="height:.6rem"></div>')
    if sci:
        reference_page.render(ra, dec, fov, key="time_ref")
    release_ui.share(ra, dec, fov)
    if sci and refs:
        with st.expander("Saved results"):
            st.selectbox("Open a saved result (results/)", list(refs), index=None, key="time_saved",
                         placeholder="Choose a result…", on_change=_open_saved_from_select, args=(refs,))
            st.caption("Opens the result region with its exact centre and field, without repeating the search.")
    st.caption("Data: NASA/IPAC IRSA · SPHEREx DR1 and QR3 (SIA2). Each frame is a real observation; the intensity scale "
               "is for display only." if sci else 'Data: SPHEREx · NASA/IPAC IRSA.')
