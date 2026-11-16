"""Spectrum Explorer: the second position (B), the comparison and the peaks and valleys.

Everything here attaches to the one image and the one spectrum plot of the page; there is no
comparison mode, page or panel. Presentation only: every number comes from
``spectral_features`` and is the same in both levels (Simple / Scientific).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import streamlit as st

from . import config, theme
from . import spectral_features as sf
from . import spectral_quality as sq
from . import spectral_view as sv
from . import spectrum_interpretation as sxi

POINTS = ["Point A", "Point B"]
DERIVED = {"Difference A − B": "diferencia", "A / B ratio": "relacion"}
B_KEY, INSPECT_KEY, CHART_KEY = "sx_b", "sx_inspect", "sx_spectrum_chart"
RANK = {sf.QUANTIFIABLE: 3, sf.VISIBLE: 2, sf.NO_FEATURE: 1, sf.NOT_EVALUABLE: 0}
BADGE = {sf.QUANTIFIABLE: "sc-ok", sf.VISIBLE: "sc-warn", sf.NOT_EVALUABLE: "", sf.NO_FEATURE: ""}  # theme.py classes


# ----------------------------------------------------------------------------- the two positions
def point_b(region_key) -> tuple[float, float] | None:
    """Position B, if one was placed in the region now open (a new region starts with A only)."""
    b = st.session_state.get(B_KEY)
    if not b:
        return None
    if tuple(b.get("region", ())) != tuple(region_key):
        st.session_state.pop(B_KEY, None)
        return None
    return float(b["ra"]), float(b["dec"])


def place_click(state, ra: float, dec: float) -> bool:
    """A click on the image. True if it placed B (A is then left exactly as it was)."""
    if state.get("opt_sx_active") != POINTS[1] or state.get("sx_region_key") is None:
        return False
    state[B_KEY] = {"ra": float(ra), "dec": float(dec), "region": tuple(state["sx_region_key"])}
    return True


def _remove_b() -> None:
    st.session_state.pop(B_KEY, None)
    st.session_state["opt_sx_active"] = POINTS[0]


def point_controls(sci: bool, region_key) -> None:
    """Next to the image: which point the next click places, and the way back to a single position."""
    with st.container(key="sx_points"):
        _point_controls(sci, region_key)


def _point_controls(sci: bool, region_key) -> None:
    has_b = point_b(region_key) is not None
    left, right = st.columns([3, 2], vertical_alignment="bottom")
    with left:
        st.segmented_control(
            "A click on the image places" if sci else "Pressing the image chooses", POINTS, required=True,
            key=theme.bind("sx_active", POINTS[0]), on_change=theme.keep, args=("sx_active",),
            help="A is the spectrum position. B is a second point: its spectrum is drawn on the same axes, "
                 "extracted in exactly the same way as A's.")
    if has_b:
        right.button("Remove point B", key="sx_b_remove", on_click=_remove_b,
                     help="Back to working with a single position. It does not change point A or its spectrum.")
        st.caption("A: black diamond · B: copper square, with the colours of their spectra. Solid line: aperture; "
                   "dashed: background annulus (the same radii for both)." if sci else
                   "A: black diamond · B: copper square, with the same colours as their curves.")
    elif st.session_state.get("opt_sx_active") == POINTS[1]:
        st.caption("Press the image to place point B and compare its spectrum with A's.")


# ----------------------------------------------------------------------------- features (cached)
@st.cache_data(show_spinner=False, max_entries=64)
def _cached_analysis(label: str, quantity: str, value: np.ndarray, ref: np.ndarray, caution: np.ndarray,
                     nhits: np.ndarray, _series) -> sf.Analysis:
    return sf.analyse(_series)


def analysis_of(series: sf.Series) -> sf.Analysis:
    """Peaks, valleys and the detector scatter of a spectrum (computed once per spectrum)."""
    return _cached_analysis(series.label, series.quantity, series.value, series.ref_scatter, series.caution,
                            series.nhits, series)


def _on_select() -> None:
    """Selection on the spectrum plot: a clicked channel or a dragged wavelength interval."""
    state = st.session_state
    try:
        sel = state[CHART_KEY]["selection"]
    except (KeyError, TypeError):
        return
    table = state.get("_sx_channels") or []
    span = (sel.get("intervalo") or {}).get("lambda_um")
    if span and len(span) == 2 and table:
        lo, hi = sorted(float(v) for v in span)
        inside = [c for c, lam in table if lo <= lam <= hi]
        if not inside:                                   # narrower than a channel: the channel under it
            inside = [min(table, key=lambda t: abs(t[1] - (lo + hi) / 2))[0]]
        state[INSPECT_KEY] = {"lo": min(inside), "hi": max(inside)}
        return
    picked = sel.get("canal") or []
    if picked and picked[0].get("canal") is not None:
        c = int(picked[0]["canal"])
        state[INSPECT_KEY] = {"lo": c, "hi": c}
    else:
        state.pop(INSPECT_KEY, None)


def _clear_inspection() -> None:
    st.session_state.pop(INSPECT_KEY, None)


def inspected(sel, pairs: list) -> dict | None:
    """The same interval measured in every spectrum shown: {"A": Feature, "B": Feature}.
    ``pairs``: [(Series, Analysis)], A first."""
    if not sel:
        return None
    try:
        if sel["lo"] == sel["hi"]:
            cands = [(s, sf.inspect_channel(s, sel["lo"], an.features, an.scatter)) for s, an in pairs]
            ref_s, ref = max(cands, key=lambda c: (RANK[c[1].klass], abs(c[1].ratio or 0.0)))
            out = {}
            for s, an in pairs:                       # the interval found in one spectrum, measured in all
                out[s.label] = ref if s is ref_s else sf.measure_interval(s, ref.trial_lo, ref.trial_hi,
                                                                         an.features, an.scatter)
            return out
        return {s.label: sf.measure_interval(s, sel["lo"], sel["hi"], an.features, an.scatter) for s, an in pairs}
    except sf.FeatureInputError:
        return None


# ----------------------------------------------------------------------------- wording
def _num(v, unit: str = "", signed: bool = False) -> str:
    if v is None:
        return "—"
    return (f"{v:+.4g}" if signed else f"{v:.4g}") + (f" {unit}" if unit else "")


def _plain(f: sf.Feature) -> str:
    """One sentence of everyday language for a measured interval (same result as the scientific table)."""
    if f.klass == sf.NOT_EVALUABLE:
        return "cannot be assessed: data are missing in that colour or around it."
    if f.klass == sf.NO_FEATURE or f.kind is None:
        return "does not stand out from the neighbouring colours."
    up = f.kind == "pico"
    size = (f"un {abs(f.relative):.0%}" if f.relative is not None and abs(f.relative) < 10
            else f"{abs(f.contrast):.3g} {f.unit}")
    text = f"{'peak' if up else 'valley'}: {size} {'brighter' if up else 'fainter'} than the neighbouring colours"
    return text + (". It stands out clearly." if f.klass == sf.QUANTIFIABLE else
                   ". It is a slight variation or based on doubtful data.")


NOT_IDENTIFIED, NOT_APPLICABLE = "Not identified", "Not applicable"


def _labelled(f: sf.Feature) -> bool:
    """A classified feature (a centre, a type and a half-height width exist only for these)."""
    return f.klass in (sf.QUANTIFIABLE, sf.VISIBLE) and f.lam is not None


def _comma(v: float, digits: int = 3) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def _channels(lo: int, hi: int) -> str:
    return f"canal {lo}" if lo == hi else f"canales {lo}–{hi}"


def _examined_span(f: sf.Feature, series: sf.Series | None) -> tuple[float, float] | None:
    if series is None or f.trial_lo is None:
        return None
    return float(series.lam_min[series.index(f.trial_lo)]), float(series.lam_max[series.index(f.trial_hi)])


def _where(f: sf.Feature, series: sf.Series | None = None) -> str:
    """Header text: the centre of a classified feature, otherwise only the interval that was examined
    (never a wavelength presented as the centre of something that was not identified)."""
    um = theme.unit("µm")        # the header is set in capitals: µ must never read as M
    if _labelled(f):
        return f"{_comma(f.lam)}&nbsp;{um} ({_channels(f.canal_lo, f.canal_hi)})"
    span = _examined_span(f, series)
    where = _channels(f.trial_lo, f.trial_hi)
    return f"{_comma(span[0])}–{_comma(span[1])}&nbsp;{um} ({where})" if span else where


def _heading(f: sf.Feature, sci: bool, series: sf.Series | None) -> str:
    if not sci:
        return "What you have flagged · " + _where(f, series)
    return ("Feature examined · " if _labelled(f) else "Interval examined · ") + _where(f, series)


def _science_rows(fs: dict, series: sf.Series | None = None) -> pd.DataFrame:
    """Inspector table. A centre, a type and a half-height width are given only for a classified feature;
    the exploratory values of the interval (value, continuum, contrast, scatter) are always kept."""
    def col(f: sf.Feature) -> list:
        span = _examined_span(f, series)
        examined = (f"{span[0]:.3f}–{span[1]:.3f} · " if span else "") + _channels(f.trial_lo, f.trial_hi)
        if f.contrast is None:
            return [f.label, NOT_IDENTIFIED, examined, NOT_APPLICABLE, NOT_APPLICABLE,
                    f"— · {f.trial_lo}–{f.trial_hi}", "—", "—", "—", "—", "—", "—", "—", "—", "—"]
        refs = " · ".join(f"{n} {_num(v)}" for n, v in (("entorno", f.ref_local), ("detector", f.ref_detector),
                                                         ("fondo", f.ref_background)) if v is not None)
        if _labelled(f):
            kind, centre = f"{f.kind} · {f.width}", f"{f.lam:.3f} (centroide {f.lam_centroid:.3f})"
            half = f"{f.lam_lo:.3f}–{f.lam_hi:.3f} ({f.width_um:.3f})"
            chans = f"{f.canal_lo}–{f.canal_hi} · {f.trial_lo}–{f.trial_hi}"
        else:
            kind, centre, half = NOT_IDENTIFIED, NOT_APPLICABLE, NOT_APPLICABLE
            chans = f"{NOT_APPLICABLE.lower()} · {f.trial_lo}–{f.trial_hi}"
        value = _num(f.value, f.unit) + ("" if f.canal is None else f" (canal {f.canal})")
        return [f.label, kind, examined, centre, half, chans, value,
                _num(f.continuum, f.unit), _num(f.contrast, f.unit, signed=True),
                "—" if f.relative is None else f"{f.relative:+.1%}",
                "> 1000" if abs(f.ratio) > 1000 else f"{abs(f.ratio):.1f}", f"{_num(f.ref, f.unit)} ({refs})",
                f"{f.env_left[0]}–{f.env_left[-1]} y {f.env_right[0]}–{f.env_right[-1]}",
                ", ".join(f"D{d}" for d in f.detectors),
                "—" if f.nhits_feature is None else f"{f.nhits_feature:.0f} / {f.nhits_env:.0f}"]
    names = ["Class", "Type", "Interval examined (µm)", "Centre of the feature (µm)",
             "Interval at half height (µm)", "Channels: at half height · outside the fit",
             "Highest-contrast value in the interval", "Local continuum", "Contrast", "Relative contrast",
             "Contrast / reference scatter", "Reference scatter", "Surrounding channels", "Detectors",
             "NHITS of the interval / surroundings"]
    return pd.DataFrame({"Quantity": names, **{f"Espectro {k}": col(f) for k, f in fs.items()}})


def _feature_list(fs: list) -> str:
    return ", ".join(f"{f.kind} en {f.lam:.2f} µm" for f in fs)


# ----------------------------------------------------------------------------- page section
def render(spec_a, quantity: str, channel_number: int, sci: bool, region_key, extract, show_error) -> None:
    """The spectrum plot and what attaches to it. ``extract(ra, dec)`` returns the spectrum of another
    position with the SAME aperture and annulus as ``spec_a`` (nothing is tuned per position)."""
    with st.container(key="sx_analysis"):            # scope of the full-opacity explanatory notes (theme.CSS)
        _render(spec_a, quantity, channel_number, sci, region_key, extract, show_error)


def _render(spec_a, quantity: str, channel_number: int, sci: bool, region_key, extract, show_error) -> None:
    state = st.session_state
    unit = sf.UNITS[quantity]
    spec_b, b_pos = None, point_b(region_key)
    if b_pos is not None:
        try:
            with theme.loading("Reading the 102 channels around point B…" if sci else
                               "Preparing the spectrum of point B…", "spectrum_b"):
                spec_b = extract(*b_pos)
        except Exception as err:  # noqa: BLE001
            show_error(err, "The spectrum of point B could not be obtained")
    quals = {"A": sq.spectrum_quality(spec_a), **({"B": sq.spectrum_quality(spec_b)} if spec_b is not None else {})}
    sa = sf.series_from_spectrum(spec_a, quantity, "A")
    sb = sf.series_from_spectrum(spec_b, quantity, "B") if spec_b is not None else None
    pairs = [(s, analysis_of(s)) for s in (sa, sb) if s is not None]
    fa, fb = pairs[0][1].features, (pairs[1][1].features if sb is not None else [])
    state["_sx_channels"] = [(int(c), float(v)) for c, v in zip(sa.canal, sa.lam)]
    sel = state.get(INSPECT_KEY)
    found = inspected(sel, pairs)
    focus = None
    if found:
        ref = max(found.values(), key=lambda f: (RANK[f.klass], abs(f.ratio or 0.0)))
        # The band drawn is the interval reported for the feature (half height); without one, what was selected.
        focus = ((ref.lam_lo, ref.lam_hi) if ref.lam_lo is not None and ref.klass in (sf.QUANTIFIABLE, sf.VISIBLE)
                 else (float(sa.lam_min[sa.index(ref.trial_lo)]), float(sa.lam_max[sa.index(ref.trial_hi)])))
    # What the features could indicate (each spectrum on its own): read from the results above, never recomputed.
    interp = sxi.build({"A": spec_a, **({"B": spec_b} if sb is not None else {})}, pairs, quals, found)

    st.altair_chart(sv.spectrum_chart(spec_a, quantity, selected_channel=channel_number, other=spec_b,
                                      features=fa + fb, focus=focus, interactive=True,
                                      references=sxi.chart_marks(interp)),
                    width="stretch", key=CHART_KEY, on_select=_on_select, selection_mode=["canal", "intervalo"])

    # ------------------------------------------------------------ A and B
    if sb is not None:
        cmp = sf.compare(sa, sb)
        for issue in cmp.issues:
            st.warning(f"A y B no se restan ni se dividen: {issue}")
        if cmp.comparable:
            label = st.segmented_control("Channel-by-channel comparison", list(DERIVED), required=True,
                                         key=theme.bind("sx_derived", next(iter(DERIVED))), on_change=theme.keep,
                                         args=("sx_derived",), label_visibility="collapsed")
            kind = DERIVED[label]
            st.altair_chart(sv.derived_chart(cmp.rows, kind, unit, focus=focus, selected_channel=channel_number),
                            width="stretch", key="sx_derived_chart")
            _comparison_text(cmp, spec_a, spec_b, kind, sci)
    elif not sci:
        st.caption("To compare with another point, choose «Point B» next to the image and press it.")

    # ------------------------------------------------------------ the selected channel or interval
    if found:
        head = st.columns([5, 1], vertical_alignment="center")
        with head[0]:
            theme.eyebrow(_heading(max(found.values(), key=lambda f: (RANK[f.klass], abs(f.ratio or 0.0))), sci, sa))
        head[1].button("Remove", key="sx_inspect_clear", on_click=_clear_inspection,
                       help="Stop examining this interval. The spectrum does not change.")
        if sci:
            st.html("".join(f'<p style="margin:.1rem 0">Espectro {k}: {theme.badge(f.label, BADGE[f.klass])} '
                            f'<span class="sc-muted">{sf.CLASS_MEANING[f.klass]}.</span></p>' for k, f in found.items()))
            rows = _science_rows(found, sa)
            st.dataframe(rows, hide_index=True, width="stretch", height="content")   # every row, no blank tail
            for k, f in found.items():
                notes = f.reasons + f.limitations
                if notes:
                    st.markdown(f"**{k}** · " + " ".join(notes))
            st.caption("Contrast = original value − local continuum (degree-2 polynomial through the three valid channels "
                       "on each side, without the feature). The reference scatter is a descriptive threshold: "
                       "it is not a flux uncertainty or a statistical significance.")
        else:
            for k, f in found.items():
                st.markdown(f"**{k}** — {_plain(f)}")
            st.caption("A peak or a valley does not by itself identify a material.")
        _interval_quality(quals, found, sci)
    else:
        st.caption("Press a point on the chart, or drag over an interval, to examine that peak or valley." if not sci
                   else "Press a point on the chart or drag over a wavelength interval to "
                        "characterise it against its surroundings. Double-click undoes the selection.")

    # ------------------------------------------------------------ what the scan marked
    marked = [(s, f) for s, f in ((sa, fa), (sb, fb)) if s is not None]
    if any(f for _, f in marked):
        if sci:
            parts = [f"{s.label}: {sum(x.klass == sf.QUANTIFIABLE for x in f)} cuantificables y "
                     f"{sum(x.klass == sf.VISIBLE for x in f)} visibles" for s, f in marked]
            st.caption("Chart marks (▼ peak, ▲ valley; filled = quantifiable, hollow = visible). " +
                       " · ".join(parts) + ". None is a detection: the cube has no uncertainties.")
        else:
            st.markdown("Flagged on the chart (▼ peak, ▲ valley): " + " · ".join(
                f"**{s.label}**: {_feature_list(f) or 'nada destacable'}" for s, f in marked) + ".")
    elif sci:
        st.caption("The method flags no peak or valley in this spectrum above its criteria.")
    if sci:
        with st.expander("Peaks and valleys: table, method and criteria"):
            rows = [{"espectro": f.serie, "tipo": f.kind, "clase": f.label.lower(), "canal": f.canal,
                     "lambda_um": round(f.lam, 4), "intervalo_um": f"{f.lam_lo:.3f}–{f.lam_hi:.3f}",
                     "canales": f.n_channels, "valor": f.value, "continuo": f.continuum, "contraste": f.contrast,
                     "relativo": f.relative, "contraste_sobre_dispersion": None if abs(f.ratio) > 1e6 else f.ratio,
                     "limitaciones": " ".join(f.limitations)} for _, fs in marked for f in fs]
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            m = sf.method_summary()
            small = " · ".join(f"{s.label}: {sf.unlabelled_extrema(s, f)}" for s, f in marked)
            st.markdown(
                f"- **Local continuum:** polynomial of degree {m['grado_del_continuo']} fitted to the "
                f"{m['canales_entorno_por_lado']} channels with a value on each side of the interval, adjacent to it; the "
                "feature and those already flagged are left out of the fit. ln(value) is fitted against ln(λ) if the "
                "surroundings are positive. Next to a channel without data or at the edge of the spectral interval there is no "
                "continuum: the feature is *not evaluable*.\n"
                "- **No smoothing.** The marks are computed from the original values; nothing is interpolated.\n"
                f"- **Criteria:** contrast ≥ {m['umbral_visible']:g} times the reference scatter for "
                f"*visible* and ≥ {m['umbral_cuantificable']:g} for *quantifiable*, which also requires a single detector, "
                "no OVERFLOW/OUTLIER and stable coverage (NHITS). Below "
                f"{m['contraste_relativo_minimo']:.0%} of the continuum nothing is flagged.\n"
                "- **Reference scatter:** the largest of that of the surroundings, the robust one of the detector and that of the background annulus "
                "propagated to the aperture. It is a descriptive threshold, not a photometric error.\n"
                f"- **Unflagged oscillations** (local maxima and minima below the criteria): {small}.\n"
                "- **What it is not:** neither a detection nor an identification. A peak near a known band does not "
                f"prove that band. Method: {m['metodo']}.")
    sxi.render(interp, sci, INSPECT_KEY)
    _quality_section(quals, sci)


# ----------------------------------------------------------------------------- why a channel has no value
def _interval_quality(quals: dict, found: dict, sci: bool) -> None:
    """Coverage of the aperture for the channels examined (and their immediate surroundings), only if something
    is wrong with them. The diagnosis never changes a measurement: it explains the missing or cautioned ones."""
    ref = max(found.values(), key=lambda f: (RANK[f.klass], abs(f.ratio or 0.0)))
    if ref.trial_lo is None:
        return
    lo, hi = ref.trial_lo - sf.N_SIDE, ref.trial_hi + sf.N_SIDE
    window = {k: [q for q in qs if lo <= q.canal <= hi] for k, qs in quals.items()}
    if not any(q.affected for w in window.values() for q in w):
        return
    if not sci:
        single = ref.trial_lo == ref.trial_hi
        for k, w in window.items():
            text = _plain_quality(w, ref.trial_lo if single else None)
            if text:
                st.markdown(f"**{k}** — {text}")
        return
    st.markdown("**Aperture quality in the interval and its surroundings**")
    _quality_table(_quality_rows(window))
    st.caption(f"{sq.CAUSE_TEXT[sq.INCOMPLETE]} The causes can coexist: they are not mutually exclusive categories. The "
               f"channels {lo}–{hi} that have something to report are shown.")


QUALITY_WIDTHS = {"Spectrum": 70, "Channel": 55, "λ (µm)": 60, "Detector": 65, "Valid pixels": 130,
                  "Pixels without data": 170, "Lost weight": 90, "BLOOM": 60, "OVERFLOW": 80, "Status": 200, "Causes": 260}


def _quality_rows(parts: dict) -> list:
    """Rows of the coverage table for {label: [ChannelQuality]}; the spectrum column only when there are two."""
    return [({"Spectrum": k} if len(parts) > 1 else {}) | r for k, qs in parts.items()
            for r in sq.table_rows([q for q in qs if q.affected])]


def _quality_table(rows: list) -> None:
    """The scientific coverage table: fixed widths so that no column is cut at the usual page width."""
    cfg = {c: st.column_config.Column(width=w) for c, w in QUALITY_WIDTHS.items()}
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config=cfg)


def _plain_quality(window: list, channel: int | None) -> str | None:
    """Sencillo wording for the channels around a selection (or for the single channel selected)."""
    if channel is not None:
        one = next((q for q in window if q.canal == channel), None)
        parts = [sq.plain(one)] if one is not None and (not one.valid_for_extraction or one.caution) else []
        near = [q for q in window if q.canal != channel and not q.valid_for_extraction and q.status != "blank"]
        if near:                            # the neighbours decide whether the environment of the channel exists
            parts.append(f"Near this colour, {len(near)} {'colour' if len(near) == 1 else 'colours'} cannot be analysed "
                         "because part of the selected region has no usable data.")
        return " ".join(parts) or None
    lost = [q for q in window if not q.valid_for_extraction and q.status != "blank"]
    blank = [q for q in window if q.status == "blank"]
    caution = [q for q in window if q.caution]
    parts = []
    if lost:
        parts.append(f"{len(lost)} of {len(window)} {'colour' if len(lost) == 1 else 'colours'} in this area cannot be "
                     "analysed because part of the selected region has no usable data.")
    if blank:
        parts.append("Some colour in this area has no data in the SPHEREx catalogue.")
    if caution:
        parts.append(f"In {len(caution)} {'colour' if len(caution) == 1 else 'colours'} there are data, but part of the light "
                     f"may have saturated: {'take it' if len(caution) == 1 else 'take them'} with caution.")
    return " ".join(parts) or None


def _quality_section(quals: dict, sci: bool) -> None:
    """One collapsed section for the whole spectrum (nothing is added to the plot)."""
    if not sci:
        lines = []
        for k, qs in quals.items():
            lost = [(q.canal, q.lambda_um) for q in qs if not q.valid_for_extraction and q.status != "blank"]
            if lost:
                lines.append(f"- **{k}:** {len(lost)} {'colour' if len(lost) == 1 else 'colours'} not analysed "
                             f"({sq.ranges_text(lost)}).")
        if not lines:
            return
        with st.expander("Why are some colours missing?"):
            st.markdown("In those colours, part of the selected region has no usable data in the SPHEREx "
                        "catalogue, so SkyClues does not analyse them. Values are not filled in or invented.\n" + "\n".join(lines))
        return
    with st.expander("Channel quality: aperture coverage and masks"):
        for k, qs in quals.items():
            s = sq.summary(qs)
            first = next((q for q in qs if q.available and q.px_total), None)
            st.markdown(
                f"**{k}** — {s['con_valor']} of {s['canales']} channels with a value"
                + (f" (aperture of {first.px_total} pixels)" if first else "")
                + f". No value: {s['rechazados_apertura_incompleta']} because of incomplete aperture, {s['vacios_dr1']} empty "
                  f"in DR1 and {s['sin_fondo']} because of insufficient background. With BLOOM in the aperture: {s['con_bloom']}; with "
                  f"OVERFLOW: {s['con_overflow']}; with caution (OVERFLOW/OUTLIER) and a value: {s['con_precaucion']}. "
                  "The groups overlap." + (f" No coverage information: {s['sin_informacion']}."
                                              if s["sin_informacion"] else ""))
        rows = _quality_rows(quals)
        if rows:
            _quality_table(rows)
        else:
            st.caption("No channel has pixels without data, BLOOM/OVERFLOW masks or values with caution.")
        st.caption(
            f"{sq.CAUSE_TEXT[sq.INCOMPLETE]} Coverage counts the aperture pixels (those with weight > 0); "
            "«lost weight» is the part of the aperture area occupied by pixels without data. BLOOM and OVERFLOW are "
            "FITS masks (FLAGS extension) counted in those pixels; their origin is not interpreted. The causes "
            "can coexist. Only channels with something to report are shown; the spectrum table lists all 102.")


def _comparison_text(cmp: sf.Comparison, spec_a, spec_b, kind: str, sci: bool) -> None:
    s, unit = cmp.summary, cmp.unit
    if not s["n_ambos"]:
        st.warning("A and B have no channel with a value in common: there is nothing to compare.")
        return
    more = round(s["fraccion_a_mayor"] * s["n_ambos"])
    sep = "" if cmp.separation_arcsec is None else f"{cmp.separation_arcsec:.0f}″"
    close = [n for n in cmp.notes if "solapan" in n or "background annulus of the other" in n or "same position" in n]
    if not sci:
        text = f"A is brighter than B in **{more} of {s['n_ambos']}** infrared colours with data in both."
        if s.get("n_relacion", 0) >= sf.MIN_RESIDUALS:
            text += (f" Overall, A shines about **{s['relacion_mediana']:.2g} times** as much as B, and that ratio "
                     f"varies by about {s['relacion_dispersion'] / s['relacion_mediana']:.0%} depending on the colour.")
        st.markdown(text)
        if close:
            st.warning("The two points are very close: their measurements are mixed and the comparison is less reliable.")
        st.caption("A difference between two points does not by itself indicate different materials.")
        return
    ap = spec_a.aperture
    st.caption(
        f"A: RA {spec_a.ra:.5f}°, Dec {spec_a.dec:+.5f}° · B: RA {spec_b.ra:.5f}°, Dec {spec_b.dec:+.5f}° · separation "
        f"{sep}. Same extraction for both: aperture {ap.r_ap:g} px, annulus {ap.r_in:g}–{ap.r_out:g} px, "
        f"{spec_a.subpixels}×{spec_a.subpixels} subsamples, unit {unit}. Channels with a value in both: {s['n_ambos']} "
        f"of {s['n_canales']} (A only {s['n_solo_a']}, B only {s['n_solo_b']}, neither {s['n_ninguno']}).")
    facts = [("A − B, median", f"{s['diferencia_mediana']:+.4g} {unit}",
              f"de {s['diferencia_min']:+.3g} a {s['diferencia_max']:+.3g}"),
             ("A > B", f"{more} de {s['n_ambos']}", "channels with a value in both")]
    if s.get("n_relacion"):
        facts.append(("A / B, median", f"{s['relacion_mediana']:.3g}",
                      f"robust scatter {s['relacion_dispersion']:.2g} · {s['n_relacion']} valid channels"))
    theme.facts(facts)
    for n in cmp.notes:
        st.caption("Warning: " + n)
    away = s.get("canales_apartados") or []
    if away:
        st.caption("Channels where A/B departs most from its median (descriptive): " + ", ".join(
            f"{c['canal']} ({c['lambda_um']:.3f} µm, A/B {c['relacion']:.3g})" for c in away) + ".")
    st.caption("A/B is only computed where A > 0, B > 0 and B exceeds "
               f"{sf.RATIO_MIN_DENOMINATOR:g} times the background scatter propagated to the aperture; elsewhere it is "
               "marked in grey on the axis with its reason. A difference or a ratio other than 1 does not imply a different "
               "composition: extinction, the local background and the mixing of sources also produce it.")
    with st.expander("Comparison table (values per channel)"):
        df = cmp.table()[["canal", "lambda_um", "lambda_min_um", "lambda_max_um", "detector", "a", "b", "estado_a",
                          "estado_b", "diferencia", "relacion", "estado_relacion", "precaucion"]]
        st.dataframe(df, hide_index=True, width="stretch")
        meta = {"producto": "SPHEREx DR1 All-Sky spectral cube", "doi": config.CUBE_DOI,
                "metodo": "comparison of two exploratory spectra extracted the same way; display only",
                "magnitud": sf.QUANTITY_NAMES[cmp.quantity], "unidad": unit,
                "a": {"ra_deg": spec_a.ra, "dec_deg": spec_a.dec}, "b": {"ra_deg": spec_b.ra, "dec_deg": spec_b.dec},
                "separacion_arcsec": cmp.separation_arcsec, "apertura_px": ap.r_ap, "anillo_px": [ap.r_in, ap.r_out],
                "submuestras": spec_a.subpixels, "pixel_sr": spec_a.pixel_solid_angle_sr, "avisos": cmp.notes,
                "criterios": sf.method_summary(), "teselas": sorted({str(t.get("tile")) for t in
                                                                     spec_a.tiles + spec_b.tiles})}
        csv = "".join(f"# {k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in meta.items()) + df.to_csv(index=False)
        st.download_button("Download the comparison CSV", csv.encode("utf-8"), mime="text/csv",
                           file_name=f"skyclues_comparacion_{spec_a.ra:.4f}_{spec_a.dec:+.4f}__"
                                     f"{spec_b.ra:.4f}_{spec_b.dec:+.4f}.csv", key="sx_cmp_csv")
