"""Time Explorer option «Infrared enhancement»: one exposure next to the combination of several.

Presentation and orchestration only; the science is ``enhance`` (selection, combination, checks)
and its figures ``enhance_view``. The level (Simple / Scientific) changes the explanations and
tables shown, never an argument: both levels read the same cached product.

States the user sees: *Available* (exposures can be looked for), *Processing*, *Enhanced image*
(a measured gain that passed every check) and *Not available for these observations* (with the
reason: too few compatible exposures, a target that moves, or a combination that failed a check).
"""
from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import streamlit as st

from . import archive, enhance, enhance_view, theme
from .astrometry import Astrometry
from .geometry import separation_deg

SEQUENCE = "sequence"
FAINT_TARGET_SNR = 30.0
PX = 6.15


def pipeline_key() -> str:
    """Caches carry the method version, so a change of method never serves an old product."""
    return enhance.METHOD


def _jsonable(v):
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return str(v)


def _product(exps, ra, dec, fov, motion_arcsec, target=None) -> dict:
    try:
        stack = enhance.combine(exps, ra, dec, fov, target_motion_arcsec=motion_arcsec)
    except enhance.EnhanceError as err:
        return {"ok": False, "reason": str(err)}
    metrics = enhance.evaluate(stack)
    verdict = enhance.verdict(metrics)
    new = [s for s in metrics["sources"] if s["detected_in_single"] == 0 and not s.get("single_exposure_only")]
    out = {"ok": True, "stack": stack, "metrics": metrics, "verdict": verdict, "new": new,
           "summary": enhance.summary(stack, metrics), "target": _target(stack, metrics, target),
           "png": {simple: enhance_view.comparison_png(stack, marks=new, simple=simple) for simple in (True, False)}}
    out["diagnostic"] = enhance_view.diagnostic_png(stack)
    return out


def _target(stack, metrics, radec) -> dict | None:
    """The named target of the region in the combination: the same aperture statistic as every source."""
    if radec is None:
        return None
    x, y = (float(v) for v in stack.wcs.all_world2pix(radec[0], radec[1], 0))
    near = sorted((s for s in metrics["sources"] if math.hypot(s["x"] - x, s["y"] - y) <= 2.5 * stack.oversample),
                  key=lambda s: -s["significance"])
    if near and near[0].get("snr") is not None:
        s = near[0]
        return {"detected": True, "snr": s["snr"], "snr_single_median": s["snr_single_median"],
                "snr_single_best": s["snr_single_best"], "detected_in_single": s["detected_in_single"],
                "significance": s["significance"], "single_exposure_only": bool(s.get("single_exposure_only")),
                "offset_arcsec": math.hypot(s["x"] - x, s["y"] - y) * stack.pixel_scale_arcsec}
    ny, nx = stack.shape
    if not (0 <= round(x) < nx and 0 <= round(y) < ny):
        return None
    m = enhance.measure_source(stack, round(x), round(y))
    return None if m is None else {"detected": False, "snr": m["snr"], "snr_single_median": m["snr_single_median"],
                                   "snr_single_best": m["snr_single_best"]}


@st.cache_resource(show_spinner=False, max_entries=6)
def _sequence_product(report_json: str, pipeline: str) -> dict:
    from .time_page import cached_sequence

    seq = cached_sequence(report_json)
    target = seq.target_position(0) if seq.astrometry is not None else None
    return _product(seq.frames, seq.ra, seq.dec, seq.field_deg,
                    seq.metrics.get("target_motion_in_sequence_arcsec"), target)


@st.cache_resource(show_spinner=False, max_entries=6)
def _nearby_product(ra: float, dec: float, fov: float, detector: int, mjd: float, collection: str,
                    astro_json: str | None, pipeline: str) -> dict:
    recs = archive.query_images(ra, dec)
    cands = enhance.nearby_exposures(recs, ra, dec, fov, detector, mjd, collection=collection)
    if len(cands) < 2:
        return {"ok": False, "reason": f"The archive only contains {len(cands)} exposure of detector D{detector} "
                                       f"with this full field within {enhance.NEARBY_DAYS:g} days of that date."}
    exps, failures = enhance.fetch_exposures(cands, ra, dec, fov)
    astro = Astrometry.from_dict(json.loads(astro_json)) if astro_json else None
    motion_arcsec, target = None, None
    if astro is not None and exps:
        target = astro.position_at(mjd)
        if astro.has_proper_motion:
            p0, p1 = astro.position_at(min(e.mjd for e in exps)), astro.position_at(max(e.mjd for e in exps))
            motion_arcsec = float(separation_deg(p0[0], p0[1], p1[0], p1[1])) * 3600
    out = _product(exps, ra, dec, fov, motion_arcsec, target)
    out["failures"] = failures
    return out


# ----------------------------------------------------------------------------- presentation
def _options(seq, sci: bool) -> dict[str, str]:
    out = {SEQUENCE: (f"The {seq.n} dates of this sequence · same channel" if sci
                      else f"The {seq.n} dates of this sequence")}
    for i, f in enumerate(seq.frames):
        out[f"near{i}"] = (f"Exposures close to {f.date_utc[:10]} · broadband D{f.detector}" if sci
                           else f"Images close to {f.date_utc[:10]}")
    return out


def render(seq, report_json: str, sci: bool) -> None:
    options = _options(seq, sci)
    # The choice is an index into THIS sequence's dates: kept across levels and pages, but a new region
    # (or a new sequence of the same region) starts again from its own dates, never from another one's.
    ident = (round(float(seq.ra), 7), round(float(seq.dec), 7), float(seq.field_deg),
             tuple(str(f.date_utc) for f in seq.frames))
    if (st.session_state.get("enhance_what_for") != ident
            or theme.persistent("enhance_what", SEQUENCE) not in options):
        st.session_state["opt_enhance_what"] = SEQUENCE
    st.session_state["enhance_what_for"] = ident
    choice = st.selectbox("What to combine", list(options), format_func=options.get,
                          key=theme.bind("enhance_what", SEQUENCE), on_change=theme.keep, args=("enhance_what",),
                          help="The dates of the sequence share a wavelength: combining them preserves the "
                               "brightness. The exposures close to a date come from the same detector, taken a "
                               "few days apart and at neighbouring wavelengths: there are usually more of them, and they keep "
                               "that date separate from the others." if sci else
                               "Choose whether to combine the dates of this sequence or more images taken around "
                               "one of them.")
    if choice == SEQUENCE:
        with theme.loading("Combining the exposures and measuring the improvement…" if sci else "Combining the images…",
                           "enhance"):
            product = _sequence_product(report_json, pipeline_key())
    else:
        product = _nearby(seq, int(choice[4:]), sci)
        if product is None:
            return
    _show(product, sci)


def _nearby(seq, i: int, sci: bool) -> dict | None:
    f = seq.frames[i]
    astro = json.dumps(seq.astrometry.to_dict()) if seq.astrometry is not None else None
    args = (round(float(seq.ra), 7), round(float(seq.dec), 7), float(seq.field_deg), int(f.detector),
            round(float(f.mjd), 5), str(f.collection), astro, pipeline_key())
    asked = st.session_state.setdefault("enhance_asked", set())
    if args not in asked:
        st.html(theme.badge("Available"))
        st.markdown(
            f"Looks in the archive for exposures of detector D{f.detector} taken up to "
            f"{enhance.NEARBY_DAYS:g} days before or after {f.date_utc[:10]} (at most {enhance.MAX_NEARBY}, "
            "about 4 MB each) and combines them. Each date is combined separately: epochs are not mixed." if sci else
            f"Looks for more images of this area taken around {f.date_utc[:10]} and combines them. "
            "It can take a minute or two.")
        if st.button("Find and combine exposures" if sci else "Find and combine images", type="primary",
                     key="enhance_run"):
            asked.add(args)
            st.rerun()
        return None
    try:
        with theme.loading("Downloading exposures from IRSA and combining them…" if sci
                           else "Finding and combining images…", "enhance"):
            return _nearby_product(*args)
    except archive.ArchiveError as err:
        from .time_page import irsa_error
        asked.discard(args)
        st.error(irsa_error(err))
        st.button("Retry", key="enhance_retry")
        return None


def _unavailable(reasons: list[str], sci: bool) -> None:
    st.html(theme.badge("Not available for these observations", "sc-fail"))
    for r in reasons:
        st.markdown(f"- {r}")
    if not sci:
        st.caption("Try another «What to combine» option. The original sequence stays available unchanged.")


def _show(p: dict, sci: bool) -> None:
    if not p["ok"]:
        _unavailable([p["reason"]], sci)
        return
    stack, m, verdict = p["stack"], p["metrics"], p["verdict"]
    sel = stack.selection
    if not verdict["accepted"]:
        _unavailable(verdict["reasons"], sci)
        if sci:
            with st.expander("Combination rejected: image and controls (diagnostic, not a result)"):
                st.image(p["png"][False], width="stretch")
                _controls(p)
        return
    broadband = sel["kind"] == "broadband"
    st.html(theme.badge("Enhanced image", "sc-ok") + " " + (
        theme.badge("Broadband" if sci else "Mixed infrared colours", "sc-warn") if broadband else
        theme.badge("Same channel" if sci else "Same infrared colour")))
    st.image(p["png"][not sci], width="stretch")
    g, pn, det = m["gain"], m["pixel_noise_mjysr"], m["detections"]
    lam = sel["lambda_range_um"]
    span = sel["span_days"]
    t = p.get("target")
    target_fact = []
    # Shown only for a faint target, where noise limits the measurement: for a bright one the aperture
    # S/N is set by the pixel phase of the undersampled PSF and says nothing about the improvement.
    if (t and t.get("snr") is not None and not t.get("single_exposure_only")
            and t["snr_single_median"] < FAINT_TARGET_SNR):
        target_fact = [("Target signal" if not sci else "Target · S/N", f"{t['snr']:.1f}",
                        f"{t['snr_single_median']:.1f} in one exposure (median)" if sci
                        else f"{t['snr_single_median']:.1f} in a single image")]
    if sci:
        theme.facts([
            ("Exposures", str(stack.n_exposures), f"{len(sel['rejected'])} rechazadas" if sel["rejected"] else ""),
            (f"Detector D{sel['detector']}", f"{lam[0]:.2f}–{lam[1]:.2f} µm" if broadband else f"{np.mean(lam):.3f} µm",
             "broadband" if broadband else "same channel"),
            ("Interval", f"{span:.1f} d" if span >= 1 else f"{span * 24:.1f} h", ""),
            ("S/N gain", f"×{g['median']:.2f}", f"mediana de {g['n_sources']} fuentes · √N = {g['sqrt_n']:.2f}"),
            ("Noise per pixel", f"{pn['combined']:.4f}", f"{pn['single_median']:.4f} MJy/sr in one exposure"),
            *target_fact])
    else:
        theme.facts([
            ("Combined images", str(stack.n_exposures), ""),
            ("Signal improvement", f"×{g['median']:.1f}", "compared with a single image"),
            ("Distinguishable points", f"{det['combined']}", f"{det['single_median']:.0f} in a single image"),
            *target_fact])
    if sci:
        theme.note(
            "<b>What this image is.</b> Mean weighted by the inverse variance of each exposure (IMAGE − ZODI, "
            "VARIANCE extension), with the strict mask and no interpolation: each pixel copies the value of the native "
            "pixel that contains its centre. The gain is the ratio between the S/N of the same sources in the "
            "combination and in one exposure (median), with the same aperture and propagated errors, checked against "
            f"a null image. Gain ×{g['median']:.2f}: equivalent to a single exposure about "
            f"{g['median'] ** 2:.0f} times longer." + (" <b>Broadband:</b> it mixes wavelengths of the same detector; it is useful for "
                                      "detecting and locating sources, not for measuring monochromatic brightness or comparing it "
                                      "between dates." if broadband else ""))
    else:
        st.markdown(
            f"By combining {stack.n_exposures} real images of the same area, the noise goes down and fainter "
            "points can be told apart. Nothing is smoothed or invented: each point is the average of the real measurements "
            f"of that piece of sky. «×{g['median']:.1f}» means that the same objects, measured the same way in the two "
            "images, stand out above the noise that many times more than in a single image." + (" This image mixes neighbouring infrared colours: it is useful for seeing and locating "
                                        "objects, not for comparing their brightness between dates." if broadband else ""))
    if p["new"]:
        # The null image holds only noise: as many peaks there as new ones here means the new ones are
        # not distinguishable from noise, so they are not presented as sources.
        null_peaks = det["null_image_spurious"]
        if null_peaks >= len(p["new"]):
            st.caption(f"The circles mark {len(p['new'])} peaks ≥ 5σ that no exposure detects, but the null "
                       f"image, which only contains noise, shows {null_peaks}: they cannot be told apart from noise and are not "
                       "detections." if sci else
                       f"The circles mark {len(p['new'])} points that only appear in the combined image, but the "
                       "noise produces as many: they cannot be taken as real objects.")
        else:
            st.caption(f"The circles mark {len(p['new'])}"
                       + ("sources ≥ 5σ in the combination that no individual exposure detects "
                          f"(null image: {null_peaks} spurious peaks)." if sci
                          else "points that can only be told apart in the combined image."))
    if det["single_exposure_only"] and sci:
        st.caption(f"{det['single_exposure_only']} detections come from a single exposure (transient, artefact "
                   "or moving object): they are identified, not counted as stationary sources and not removed.")
    if t and t.get("single_exposure_only"):
        st.caption("The signal at the target position comes from a single exposure: it is not interpreted.")
    for w in sel["warnings"] if sci else []:
        st.caption("Warning: " + w)
    if p.get("failures"):
        st.caption(f"{len(p['failures'])} exposures could not be downloaded from IRSA and are not part of the "
                   "combination.")
    st.caption("The original dates are not modified: turn off «Infrared enhancement» to go back to the sequence. "
               "This image plays no part in the motion measurement.")
    if sci:
        _details(p)


def _controls(p: dict) -> None:
    stack, m = p["stack"], p["metrics"]
    det, res, ast, ph, reg = m["detections"], m["resolution"], m["astrometry"], m["photometry"], stack.registration
    st.image(p["diagnostic"], width="stretch")

    def num(v, fmt="{:.2f}"):
        return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)

    shift = None if ast["median_shift_arcsec"] is None else float(np.hypot(*ast["median_shift_arcsec"]))

    def bright(k):
        return f"{k} fuente brillante" if k == 1 else f"{k} fuentes brillantes"
    st.markdown(
        f"- **Noise:** the null image (half A − half B)/2 has a scatter of {num(stack.noise.get('null_scale'))} "
        f"times its formal error ({num(stack.noise.get('single_scale'))} in differences of individual exposures). "
        "The errors are multiplied by that factor when it is greater than 1.\n"
        f"- **Detections ≥ {det['threshold']:g}σ:** {det['combined']} in the combination, {det['single_median']:.0f} "
        f"(median) per exposure; {det['new_in_combined']} new. Null image: {det['null_image_spurious']} "
        f"spurious, {det['null_image_at_sources']} sampling residuals on real sources and "
        f"{det['null_image_single_exposure']} single-exposure features. Inverted image: {det['negative_image']}.\n"
        f"- **Resolution:** PSF width ×{num(res['width_ratio'])} compared with one exposure "
        f"({bright(res['n_sources'])}).\n"
        f"- **Positions:** combined − individual centroid {num(shift)}″ (median); registration between exposures "
        f"≤ {num(reg.get('max_shift_arcsec'))}″ with common sources; resampling error of its own "
        f"{num(reg.get('placement_rms_arcsec'))}″ (rms).\n"
        f"- **Flux:** combination / mean-of-exposures ratio {num(ph['flux_ratio_median'], '{:.3f}')} "
        f"({bright(ph['n_sources'])}).\n"
        f"- **Non-physical values:** {sum(stack.selection.get('nonphysical_negative_pixels', []))} negative pixels "
        f"more than {enhance.NONPHYSICAL_SIGMA:g}σ below their sky and below the other exposures, discarded.")


def _details(p: dict) -> None:
    stack, sel = p["stack"], p["stack"].selection
    reg = {f["obs_id"]: f for f in stack.registration.get("frames", [])}
    rows = []
    for i, e in enumerate(stack.exposures):
        r = reg.get(e.obs_id, {})
        rows.append({"date (UTC)": str(e.image.meta.get("DATE-AVG") or "")[:16], "obs_id": e.obs_id,
                     "λ (µm)": round(sel["lambda_um"][i], 4), "relative weight": round(p["summary"]["weights_relative"][i], 2),
                     "sky (MJy/sr)": round(float(stack.offsets[i]), 4),
                     "registration (″)": "referencia" if r.get("reference") else (
                         f"{math.hypot(*r['shift_arcsec']):.2f} ({r['n_sources']} fuentes)" if "shift_arcsec" in r
                         else "unverified"),
                     "negatives discarded": sel["nonphysical_negative_pixels"][i],
                     "archivo": e.image.meta.get("FILE"), "SHA-256": (e.sha256 or "")[:16] + "…"})
    with st.expander(f"Exposiciones combinadas ({stack.n_exposures})"):
        st.dataframe(pd.DataFrame(rows).astype(str), hide_index=True, width="stretch")
        if sel["rejected"]:
            st.markdown("**Rechazadas**")
            st.dataframe(pd.DataFrame([{"obs_id": r["obs_id"], "motivo": r["reason"]} for r in sel["rejected"]]),
                         hide_index=True, width="stretch")
        st.caption(f"Collection {sel.get('collection') or '—'} · software {sel.get('version')} · {sel.get('bunit')} · "
                   f"method {enhance.METHOD}. Cutouts served by NASA/IPAC IRSA; the original FITS files are not modified.")
    with st.expander("Combination checks"):
        _controls(p)
    st.download_button("Download the combination report (JSON)",
                       json.dumps(p["summary"], ensure_ascii=False, indent=1, default=_jsonable),
                       file_name=f"skyclues_mejora_D{sel['detector']}_{stack.n_exposures}exp.json",
                       mime="application/json", key="enhance_download")
