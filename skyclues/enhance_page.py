"""Time Explorer option «Mejora infrarroja»: one exposure next to the combination of several.

Presentation and orchestration only; the science is ``enhance`` (selection, combination, checks)
and its figures ``enhance_view``. The level (Sencillo / Científico) changes the explanations and
tables shown, never an argument: both levels read the same cached product.

States the user sees: *Disponible* (exposures can be looked for), *Procesando*, *Imagen mejorada*
(a measured gain that passed every check) and *No disponible para estas observaciones* (with the
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
        return {"ok": False, "reason": f"El archivo solo contiene {len(cands)} exposición del detector D{detector} "
                                       f"con este campo completo a menos de {enhance.NEARBY_DAYS:g} días de esa fecha."}
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
    out = {SEQUENCE: (f"Las {seq.n} fechas de esta secuencia · mismo canal" if sci
                      else f"Las {seq.n} fechas de esta secuencia")}
    for i, f in enumerate(seq.frames):
        out[f"near{i}"] = (f"Exposiciones próximas al {f.date_utc[:10]} · banda ancha D{f.detector}" if sci
                           else f"Imágenes próximas al {f.date_utc[:10]}")
    return out


def render(seq, report_json: str, sci: bool) -> None:
    options = _options(seq, sci)
    if theme.persistent("enhance_what", SEQUENCE) not in options:
        st.session_state["opt_enhance_what"] = SEQUENCE
    choice = st.selectbox("Qué combinar", list(options), format_func=options.get,
                          key=theme.bind("enhance_what", SEQUENCE), on_change=theme.keep, args=("enhance_what",),
                          help="Las fechas de la secuencia comparten longitud de onda: su combinación conserva el "
                               "brillo. Las exposiciones próximas a una fecha son del mismo detector, tomadas con "
                               "pocos días de diferencia y a longitudes de onda vecinas: suelen ser más, y conservan "
                               "esa fecha separada de las demás." if sci else
                               "Elige si se combinan las fechas de esta secuencia o más imágenes tomadas alrededor "
                               "de una de ellas.")
    if choice == SEQUENCE:
        with theme.loading("Combinando las exposiciones y midiendo la mejora…" if sci else "Combinando las imágenes…",
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
        st.html(theme.badge("Disponible"))
        st.markdown(
            f"Busca en el archivo las exposiciones del detector D{f.detector} tomadas hasta "
            f"{enhance.NEARBY_DAYS:g} días antes o después del {f.date_utc[:10]} (como máximo {enhance.MAX_NEARBY}, "
            "unos 4 MB cada una) y las combina. Cada fecha se combina por separado: no se mezclan épocas." if sci else
            f"Busca más imágenes de esta zona tomadas alrededor del {f.date_utc[:10]} y las combina. "
            "Puede tardar uno o dos minutos.")
        if st.button("Buscar y combinar exposiciones" if sci else "Buscar y combinar imágenes", type="primary",
                     key="enhance_run"):
            asked.add(args)
            st.rerun()
        return None
    try:
        with theme.loading("Descargando exposiciones de IRSA y combinándolas…" if sci
                           else "Buscando y combinando imágenes…", "enhance"):
            return _nearby_product(*args)
    except archive.ArchiveError as err:
        from .time_page import irsa_error
        asked.discard(args)
        st.error(irsa_error(err))
        st.button("Reintentar", key="enhance_retry")
        return None


def _unavailable(reasons: list[str], sci: bool) -> None:
    st.html(theme.badge("No disponible para estas observaciones", "sc-fail"))
    for r in reasons:
        st.markdown(f"- {r}")
    if not sci:
        st.caption("Prueba con otra opción de «Qué combinar». La secuencia original sigue disponible sin cambios.")


def _show(p: dict, sci: bool) -> None:
    if not p["ok"]:
        _unavailable([p["reason"]], sci)
        return
    stack, m, verdict = p["stack"], p["metrics"], p["verdict"]
    sel = stack.selection
    if not verdict["accepted"]:
        _unavailable(verdict["reasons"], sci)
        if sci:
            with st.expander("Combinación rechazada: imagen y controles (diagnóstico, no es un resultado)"):
                st.image(p["png"][False], width="stretch")
                _controls(p)
        return
    broadband = sel["kind"] == "broadband"
    st.html(theme.badge("Imagen mejorada", "sc-ok") + (" " + theme.badge("Banda ancha") if broadband and sci else ""))
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
        target_fact = [("Señal del objetivo" if not sci else "Objetivo · S/N", f"{t['snr']:.1f}",
                        f"{t['snr_single_median']:.1f} en una exposición (mediana)" if sci
                        else f"{t['snr_single_median']:.1f} en una sola imagen")]
    if sci:
        theme.facts([
            ("Exposiciones", str(stack.n_exposures), f"{len(sel['rejected'])} rechazadas" if sel["rejected"] else ""),
            (f"Detector D{sel['detector']}", f"{lam[0]:.2f}–{lam[1]:.2f} µm" if broadband else f"{np.mean(lam):.3f} µm",
             "banda ancha" if broadband else "mismo canal"),
            ("Intervalo", f"{span:.1f} d" if span >= 1 else f"{span * 24:.1f} h", ""),
            ("Ganancia S/N", f"×{g['median']:.2f}", f"mediana de {g['n_sources']} fuentes · √N = {g['sqrt_n']:.2f}"),
            ("Ruido por píxel", f"{pn['combined']:.4f}", f"{pn['single_median']:.4f} MJy/sr en una exposición"),
            *target_fact])
    else:
        theme.facts([
            ("Imágenes combinadas", str(stack.n_exposures), ""),
            ("Mejora de la señal", f"×{g['median']:.1f}", "frente a una sola imagen"),
            ("Puntos distinguibles", f"{det['combined']}", f"{det['single_median']:.0f} en una sola imagen"),
            *target_fact])
    if sci:
        theme.note(
            "<b>Qué es esta imagen.</b> Media ponderada por la varianza inversa de cada exposición (IMAGE − ZODI, "
            "extensión VARIANCE), con la máscara estricta y sin interpolar: cada píxel copia el valor del píxel "
            "nativo que contiene su centro. La ganancia es el cociente entre la S/N de las mismas fuentes en la "
            "combinación y en una exposición (mediana), con la misma apertura y errores propagados y contrastados "
            "con una imagen nula." + (" <b>Banda ancha:</b> mezcla longitudes de onda del mismo detector; sirve para "
                                      "detectar y situar fuentes, no para medir brillo monocromático ni compararlo "
                                      "entre fechas." if broadband else ""))
    else:
        st.markdown(
            f"Al combinar {stack.n_exposures} imágenes reales de la misma zona, el ruido baja y se distinguen "
            "puntos más débiles. No se suaviza ni se inventa nada: cada punto es el promedio de las medidas reales "
            "de ese trozo de cielo." + (" Esta imagen mezcla colores infrarrojos vecinos: sirve para ver y situar "
                                        "objetos, no para comparar su brillo entre fechas." if broadband else ""))
    if p["new"]:
        st.caption(f"Los círculos señalan {len(p['new'])} "
                   + ("fuentes ≥ 5σ en la combinación que ninguna exposición individual detecta." if sci
                      else "puntos que solo se distinguen en la imagen combinada."))
    if det["single_exposure_only"] and sci:
        st.caption(f"{det['single_exposure_only']} detecciones proceden de una sola exposición (transitorio, artefacto "
                   "u objeto en movimiento): se identifican, no se cuentan como fuentes estacionarias ni se eliminan.")
    if t and t.get("single_exposure_only"):
        st.caption("La señal en la posición del objetivo procede de una sola exposición: no se interpreta.")
    for w in sel["warnings"] if sci else []:
        st.caption("Aviso: " + w)
    if p.get("failures"):
        st.caption(f"{len(p['failures'])} exposiciones no se pudieron descargar de IRSA y no forman parte de la "
                   "combinación.")
    st.caption("Las fechas originales no se modifican: desactiva «Mejora infrarroja» para volver a la secuencia. "
               "Esta imagen no interviene en la medida de movimiento.")
    if sci:
        _details(p)


def _controls(p: dict) -> None:
    stack, m = p["stack"], p["metrics"]
    det, res, ast, ph, reg = m["detections"], m["resolution"], m["astrometry"], m["photometry"], stack.registration
    st.image(p["diagnostic"], width="stretch")

    def num(v, fmt="{:.2f}"):
        return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else fmt.format(v)

    shift = None if ast["median_shift_arcsec"] is None else float(np.hypot(*ast["median_shift_arcsec"]))
    st.markdown(
        f"- **Ruido:** la imagen nula (mitad A − mitad B)/2 tiene una dispersión de {num(stack.noise.get('null_scale'))} "
        f"veces su error formal ({num(stack.noise.get('single_scale'))} en diferencias de exposiciones individuales). "
        "Los errores se multiplican por ese factor cuando es mayor que 1.\n"
        f"- **Detecciones ≥ {det['threshold']:g}σ:** {det['combined']} en la combinación, {det['single_median']:.0f} "
        f"(mediana) por exposición; {det['new_in_combined']} nuevas. Imagen nula: {det['null_image_spurious']} "
        f"espurias, {det['null_image_at_sources']} residuos de muestreo sobre fuentes reales y "
        f"{det['null_image_single_exposure']} rasgos de una sola exposición. Imagen invertida: {det['negative_image']}.\n"
        f"- **Resolución:** anchura de la PSF ×{num(res['width_ratio'])} respecto a una exposición "
        f"({res['n_sources']} fuentes brillantes).\n"
        f"- **Posiciones:** centroide combinado − individual {num(shift)}″ (mediana); registro entre exposiciones "
        f"≤ {num(reg.get('max_shift_arcsec'))}″ con fuentes comunes; error propio del remuestreo "
        f"{num(reg.get('placement_rms_arcsec'))}″ (rms).\n"
        f"- **Flujo:** cociente combinación / media de exposiciones {num(ph['flux_ratio_median'], '{:.3f}')} "
        f"({ph['n_sources']} fuentes brillantes).\n"
        f"- **Valores no físicos:** {sum(stack.selection.get('nonphysical_negative_pixels', []))} píxeles negativos "
        f"a más de {enhance.NONPHYSICAL_SIGMA:g}σ bajo su cielo y bajo las demás exposiciones, descartados.")


def _details(p: dict) -> None:
    stack, sel = p["stack"], p["stack"].selection
    reg = {f["obs_id"]: f for f in stack.registration.get("frames", [])}
    rows = []
    for i, e in enumerate(stack.exposures):
        r = reg.get(e.obs_id, {})
        rows.append({"fecha (UTC)": str(e.image.meta.get("DATE-AVG") or "")[:16], "obs_id": e.obs_id,
                     "λ (µm)": round(sel["lambda_um"][i], 4), "peso relativo": round(p["summary"]["weights_relative"][i], 2),
                     "cielo (MJy/sr)": round(float(stack.offsets[i]), 4),
                     "registro (″)": "referencia" if r.get("reference") else (
                         f"{math.hypot(*r['shift_arcsec']):.2f} ({r['n_sources']} fuentes)" if "shift_arcsec" in r
                         else "sin verificar"),
                     "negativos descartados": sel["nonphysical_negative_pixels"][i],
                     "archivo": e.image.meta.get("FILE"), "SHA-256": (e.sha256 or "")[:16] + "…"})
    with st.expander(f"Exposiciones combinadas ({stack.n_exposures})"):
        st.dataframe(pd.DataFrame(rows).astype(str), hide_index=True, width="stretch")
        if sel["rejected"]:
            st.markdown("**Rechazadas**")
            st.dataframe(pd.DataFrame([{"obs_id": r["obs_id"], "motivo": r["reason"]} for r in sel["rejected"]]),
                         hide_index=True, width="stretch")
        st.caption(f"Colección {sel.get('collection') or '—'} · software {sel.get('version')} · {sel.get('bunit')} · "
                   f"método {enhance.METHOD}. Recortes servidos por NASA/IPAC IRSA; los FITS originales no se modifican.")
    with st.expander("Controles de la combinación"):
        _controls(p)
    st.download_button("Descargar el informe de la combinación (JSON)",
                       json.dumps(p["summary"], ensure_ascii=False, indent=1, default=_jsonable),
                       file_name=f"skyclues_mejora_D{sel['detector']}_{stack.n_exposures}exp.json",
                       mime="application/json", key="enhance_download")
