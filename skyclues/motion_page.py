"""Time Explorer tab «Find something that moves» (inspection and measurement on original images)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from . import archive, config, motion, references, saved_text, theme
from .astrometry import Astrometry

SOURCE_MODES = ["Catalogue target", "Source detected in epoch 1", "RA/Dec coordinates"]
IMAGE_MODES = ["Epochs of this sequence", "Extend the time baseline (same detector)"]
BADGE = {motion.MOTION_MEASURED: "sc-ok", motion.INSUFFICIENT_EVIDENCE: "sc-warn",
         motion.INCOMPATIBLE: "sc-fail", motion.INSUFFICIENT_DATA: "sc-fail"}


@st.cache_data(ttl=12 * 3600, max_entries=16, show_spinner=False)
def _gaia(ra: float, dec: float, fov: float) -> dict:
    return references.fetch_gaia(ra, dec, fov)


def _gaia_or_none(ra, dec, fov):
    try:
        return _gaia(round(ra, 6), round(dec, 6), round(fov, 4)), None
    except references.ReferenceError as err:
        return None, str(err)


@st.cache_data(max_entries=8, show_spinner=False)
def _investigate_extended(ra: float, dec: float, detector: int, per_season: int, radius: float,
                          start_ra: float, start_dec: float, astro_json: str | None,
                          label: str = "selection in Time Explorer") -> dict:
    recs = archive.query_images(ra, dec)
    sel = motion.select_epochs(recs, ra, dec, detector, per_season=per_season)
    frames = motion.fetch_frames(sel, ra, dec)
    gaia, err = _gaia_or_none(ra, dec, sel["field_deg"])
    astro = Astrometry.from_dict(json.loads(astro_json)) if astro_json else None
    inv = motion.investigate(frames, (start_ra, start_dec), gaia=gaia, astrometry=astro,
                             search_radius_arcsec=radius, source_label=label)
    out = motion.to_jsonable(inv)
    out["selection"] = {k: v for k, v in sel.items() if k != "selected"}
    if err:
        out.setdefault("warnings", []).append(err)
    return out


def saved_investigations() -> dict[str, Path]:
    out = {}
    for p in sorted(config.RESULTS_DIR.glob("motion_*.json")):
        if p.stem.startswith("motion_search_"):
            continue
        try:
            r = saved_text.motion(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if "outcome" not in r:
            continue
        d = r.get("displacement") or {}
        extra = (f" · {d['total_arcsec']:.2f}″ in {d['delta_t_days']:.0f} d"
                 if d and r["outcome"] == motion.MOTION_MEASURED else "")
        out[f"{p.stem.replace('motion_', '')} · D{r.get('detector', '?')} · {r['outcome_label']}{extra}"] = p
    return out


def show_result(r: dict, key: str, simple: bool = False) -> None:
    if simple:
        # Plain-language verdicts: the outcome comes from the engine unchanged; only the wording is simpler.
        plain = {
            motion.MOTION_MEASURED: ("ok", "Motion detected",
                                     "We compare the position of the object in real images from different dates, aligned "
                                     "with fixed reference stars: it has moved by more than the uncertainty of the measurement "
                                     "can explain."),
            motion.INSUFFICIENT_EVIDENCE: ("warn", "Motion not confirmed",
                                           "These images do not show a displacement clearly larger than their "
                                           "uncertainty. That does not prove that the object is still: it may move "
                                           "less than these images allow us to measure."),
            motion.INCOMPATIBLE: ("fail", "Not evaluable",
                                  "The images are not comparable with each other (detector, coverage or quality), so "
                                  "we cannot say whether there was motion."),
            motion.INSUFFICIENT_DATA: ("", "Insufficient data",
                                       "Suitable images are missing (for example, from two different seasons) to "
                                       "check whether there was motion.")}
        kind, label, text = plain.get(r["outcome"], ("", r["outcome_label"], ""))
        reasons = r.get("reasons") or []
        more = ("Reason: " + reasons[0]) if reasons and r["outcome"] != motion.MOTION_MEASURED else ""
        theme.result(kind, label, text, more)
        d = r.get('displacement')
        if d and r['outcome'] == motion.MOTION_MEASURED:
            theme.facts([('Change of position', f"{d['total_arcsec']:.2f} ± {d['total_err_arcsec']:.2f}″",
                          "± is the uncertainty of the measurement"),
                         ('Time between images', f"{d['delta_t_days']:.0f} days", f"{d['first']} → {d['last']}")])
        st.caption('In Scientific you can review the measurements, the reasons and the images used.')
        return
    st.markdown(f'<span class="sc-badge {BADGE.get(r["outcome"], "")}">{r["outcome_label"]} · {r["outcome"]}</span>'
                f' &nbsp; <span class="sc-badge">{r.get("source", {}).get("label") or "selected source"}</span>',
                unsafe_allow_html=True)
    for why in r.get("reasons", []):
        st.markdown(f"- {why}")
    d = r.get("displacement")
    if d:
        measured = r["outcome"] == motion.MOTION_MEASURED
        if not measured:
            st.caption("Fit figures shown for transparency. **They are not a motion measurement**: the "
                       "reasons above prevent validating them.")
        c = st.columns(4)
        c[0].metric("Measured displacement" if measured else "Apparent displacement (not validated)",
                    f"{d['total_arcsec']:.2f}″", f"± {d['total_err_arcsec']:.2f}″", delta_color="off")
        c[1].metric("Interval", f"{d['delta_t_days']:.0f} d", f"{d['first']} → {d['last']}", delta_color="off")
        c[2].metric("Significance", f"{d['significance_calibrated']:.1f}σ", f"threshold {motion.SIGNIFICANCE:g}σ",
                    delta_color="off")
        ctl = r.get("control") or {}
        c[3].metric("Stationary control", f"{ctl.get('n', 0)} stars",
                    f"max. {ctl.get('max_significance_calibrated', 0):.1f}σ", delta_color="off")
        st.caption(f"Δξ (east) = {d['dxi']:+.2f} ± {d['err_dxi_calibrated']:.2f}″ · Δη (north) = {d['deta']:+.2f} ± "
                   f"{d['err_deta_calibrated']:.2f}″ · mean apparent rate {d['rate_arcsec_yr']:.2f}″/yr (includes "
                   "parallax and the geometry of the dates; it is not a fitted proper motion). Control "
                   f"calibration factor: {ctl.get('calibration_factor', 1):.2f}.")
    cc = r.get("catalogue_comparison")
    if cc:
        st.info(f"Comparison with the catalogue ({cc['source']}): **predicted** displacement "
                f"{cc['predicted_total_arcsec']:.2f}″ (Δξ {cc['predicted_dxi']:+.2f}″, Δη {cc['predicted_deta']:+.2f}″) "
                f"between the same dates; difference from the measurement {cc['difference_sigma']:.1f}σ "
                f"({'compatible' if cc['consistent_3sigma'] else 'not compatible'} at 3σ). The prediction plays no part "
                "in the search, the fit or the decision.")
    seasons = r.get("seasons") or []
    if seasons:
        st.markdown("**Measured position per season** (joint fit of the exposures; tangent at the selection)")
        st.dataframe(pd.DataFrame([{
            "season": s["date_utc"], "images": s["n_images"], "detection (σ)": round(s["significance"], 1),
            "ξ (″)": round(s["xi"], 2), "σξ (″)": round(s["err_xi"], 2), "η (″)": round(s["eta"], 2),
            "ση (″)": round(s["err_eta"], 2), "registration (″)": f"{s['err_registration'][0]:.2f}/{s['err_registration'][1]:.2f}",
            "internal χ²": None if s.get("internal_chi2_red") is None else round(s["internal_chi2_red"], 2),
            "saturated core": "yes" if s["saturated_core"] else "no", "confusion": "yes" if s["confusion"] else "no",
            "used": "yes" if s.get("usable") else "no"} for s in seasons]), hide_index=True, width="stretch")
    imgs = r.get("images") or []
    if imgs:
        with st.expander(f"Original images used ({len(imgs)})"):
            st.dataframe(pd.DataFrame([{
                "date (UTC)": (i.get("date_utc") or "")[:16], "obs_id": i.get("obs_id"),
                "λ (µm)": None if i.get("lambda_um") is None else round(i["lambda_um"], 3),
                "S/N": None if i.get("snr") is None else round(i["snr"], 1), "registration mode": i.get("registration_mode"),
                "WCS − Gaia (″)": _pair(i.get("wcs_offset_vs_gaia_arcsec")),
                "file": i.get("file"), "SHA-256": (i.get("sha256") or "")[:16] + "…"} for i in imgs]),
                hide_index=True, width="stretch")
            st.caption(imgs[0].get("psf_model", ""))
    ctl = r.get("control") or {}
    if ctl.get("stars"):
        with st.expander(f"Control: {ctl['n']} stationary stars measured the same way as the source"):
            st.dataframe(pd.DataFrame([{"Gaia DR3": c["gaia_source_id"], "G": c.get("g"),
                                        "Δξ (″)": round(c["dxi"], 2), "Δη (″)": round(c["deta"], 2),
                                        "σ (″)": f"{c['err_dxi']:.2f}/{c['err_deta']:.2f}",
                                        "significance": round(c["significance_calibrated"], 1)} for c in ctl["stars"]]),
                         hide_index=True, width="stretch")
            st.caption(ctl.get("rule", ""))
    for w in r.get("warnings", []):
        st.caption(f"Warning: {w}")
    st.download_button("Download reproducible result (JSON)", json.dumps(r, ensure_ascii=False, indent=1),
                       file_name=f"skyclues_motion_{r.get('detector', 'x')}_{(seasons or [{}])[0].get('date_utc', 'na')}.json",
                       mime="application/json", key=f"{key}_download")


def _pair(v):
    if not v or v[0] is None:
        return "—"
    return f"{v[0]:+.2f}, {v[1]:+.2f}"


def render(seq, report_json: str, level: str = "scientific") -> None:
    """Presentation level changes explanations, never measurement or its parameters."""
    sci = level == 'scientific'
    if level == "simple":
        st.markdown(
            '<div class="sc-note"><b>Is anything moving?</b> Choose a point to check whether its position changes between dates.</div>',
            unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="sc-note"><b>Find something that moves.</b> Measures the position of a source in each original '
            'SPHEREx exposure (IMAGE − ZODI, VARIANCE, FLAGS and the official ePSF model), registers each image with '
            'stationary Gaia stars of the field and compares seasons with uncertainties. Possible results: '
            '<i>Motion measured</i>, <i>Insufficient evidence</i>, <i>Incompatible observations</i> or <i>Insufficient '
            'data</i>. A position computed from the catalogue is never counted as a detection.</div>',
            unsafe_allow_html=True)
    saved = saved_investigations()
    if saved:
        with st.expander("Saved real investigations (results/motion_*.json)" if sci else 'Saved investigations'):
            label = st.selectbox("Result", list(saved), key="mv_saved")
            show_result(saved_text.motion(json.loads(saved[label].read_text(encoding="utf-8"))), key="mv_saved_view", simple=not sci)
    a = seq.astrometry
    modes = SOURCE_MODES if a is not None else SOURCE_MODES[1:]
    src_mode = st.radio("Source to investigate", modes, horizontal=True, key="mv_source")
    f0 = seq.frames[0]
    if src_mode == SOURCE_MODES[0]:
        start = seq.target_position(0)
        st.caption((f"{a.name}: catalogue position computed for epoch 1 (RA {start[0]:.6f}°, Dec "
                   f"{start[1]:+.6f}°). It only defines the search circle; the position is measured in each season.") if sci else f'Selected object: {a.name}.')
    elif src_mode == SOURCE_MODES[1]:
        dets = motion.detect_sources(f0.image)
        if not dets:
            st.warning("There are no sources ≥ 5σ in epoch 1 of this field.")
            return
        opts = {f"#{i + 1} · {d['significance']:.0f}σ · RA {d['ra']:.5f}°, Dec {d['dec']:+.5f}° · pixel ({d['x']}, {d['y']})": d
                for i, d in enumerate(dets[:25])}
        d = opts[st.selectbox("Detected source (PSF-matched filter, epoch 1)" if sci else 'Point in the first image', list(opts), key="mv_detected",
                             format_func=lambda x: x if sci else 'Point ' + x.split(' · ')[0].lstrip('#'))]
        start = (d["ra"], d["dec"])
    else:
        c1, c2 = st.columns(2)
        start = (c1.number_input("RA (°)", value=float(seq.ra), format="%.6f", key="mv_ra"),
                 c2.number_input("Dec (°)", value=float(seq.dec), format="%.6f", key="mv_dec"))
    radius = st.session_state.get('mv_radius', st.session_state.get('_mv_radius', int(motion.SEARCH_RADIUS_ARCSEC)))
    if sci:
        radius = st.slider("Search radius around the selection (″)", 5, 40, radius,
                           key="mv_radius", help="The source is searched for in each season inside this circle, without using "
                                                 "predictions. It must cover the possible displacement between the dates.")
    st.session_state['_mv_radius'] = radius
    span = seq.metrics["span_days"]
    img_mode = st.radio("Images", IMAGE_MODES, key="mv_images", horizontal=True,
                        captions=[f"{seq.n} images · {span:.0f} d · field {seq.field_deg * 60:g}′",
                                  f"D{f0.detector}, up to {motion.MAX_SEASONS} seasons as far apart as possible, "
                                  f"cutouts of {motion.MOTION_FIELD_DEG * 60:g}′"])
    per_season = motion.PER_SEASON
    if img_mode == IMAGE_MODES[1]:
        per_season = st.select_slider(
            "Images per season", [2, 3, 4, 6, 8], value=motion.PER_SEASON, key="mv_per_season",
            help="More exposures per season improve the signal of a faint source and the internal consistency "
                 "check, at the cost of more cutouts (~4 MB each).")
        if sci:
            st.caption(f"Up to {motion.MAX_SEASONS * per_season} cutouts (~{4 * motion.MAX_SEASONS * per_season} MB, "
                   "reused from the cache). The result depends on the exposures chosen: it is recorded in "
                   "the report.")
    if img_mode == IMAGE_MODES[0] and span < 30:
        st.caption(f"This sequence spans {span:.0f} days: only large motions would be detected. The extended "
                   "time baseline usually covers a year.")
    run = st.button("Investigate motion", type="primary", key="mv_run")
    key = json.dumps([report_json[:64], len(report_json), src_mode, start, radius, img_mode, per_season],
                     default=str)
    label = a.name if src_mode == SOURCE_MODES[0] and a else src_mode
    if run:
        with st.status("Measuring positions in the original images…", expanded=True) as box, theme.loading("Comparing the position between dates…", "motion"):
            try:
                if img_mode == IMAGE_MODES[0]:
                    box.write("Querying Gaia DR3 (stationary stars of the field)…")
                    gaia, err = _gaia_or_none(seq.ra, seq.dec, seq.field_deg)
                    box.write("Fitting the ePSF and registering each epoch…")
                    inv = motion.investigate(seq.frames, start, gaia=gaia, astrometry=a,
                                             search_radius_arcsec=float(radius),
                                             source_label=label)
                    out = motion.to_jsonable(inv)
                    if err:
                        out.setdefault("warnings", []).append(err)
                else:
                    box.write("Selecting seasons and downloading cutouts (or reading the cache)…")
                    out = _investigate_extended(round(float(start[0]), 6), round(float(start[1]), 6),
                                                int(f0.detector), int(per_season), float(radius),
                                                float(start[0]), float(start[1]),
                                                json.dumps(a.to_dict()) if a else None, label)
                box.update(label=f"Investigation completed: {out['outcome_label']}", state="complete", expanded=False)
                st.session_state["mv_result"] = {"key": key, "result": out}
            except (archive.ArchiveError, motion.MotionInputError, ValueError) as err:
                box.update(label="The investigation could not be completed", state="error")
                st.error(f"{type(err).__name__}: {err}. No partial result has been shown.")
    res = st.session_state.get("mv_result")
    if res and res["key"] == key:
        show_result(res["result"], key="mv_current", simple=not sci)
    elif res:
        st.caption("The selection has changed: press «Investigate motion» to get a new result.")
