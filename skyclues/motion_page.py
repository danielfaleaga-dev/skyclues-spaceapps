"""Time Explorer tab «Buscar algo que se mueve» (inspection and measurement on original images)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from . import archive, config, motion, references
from .astrometry import Astrometry

SOURCE_MODES = ["Objetivo del catálogo", "Fuente detectada en la época 1", "Coordenadas RA/Dec"]
IMAGE_MODES = ["Épocas de esta secuencia", "Ampliar la base temporal (mismo detector)"]
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
                          label: str = "selección en Time Explorer") -> dict:
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
            r = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if "outcome" not in r:
            continue
        d = r.get("displacement") or {}
        extra = (f" · {d['total_arcsec']:.2f}″ en {d['delta_t_days']:.0f} d"
                 if d and r["outcome"] == motion.MOTION_MEASURED else "")
        out[f"{p.stem.replace('motion_', '')} · D{r.get('detector', '?')} · {r['outcome_label']}{extra}"] = p
    return out


def show_result(r: dict, key: str) -> None:
    st.markdown(f'<span class="sc-badge {BADGE.get(r["outcome"], "")}">{r["outcome_label"]} · {r["outcome"]}</span>'
                f' &nbsp; <span class="sc-badge">{r.get("source", {}).get("label") or "fuente seleccionada"}</span>',
                unsafe_allow_html=True)
    for why in r.get("reasons", []):
        st.markdown(f"- {why}")
    d = r.get("displacement")
    if d:
        measured = r["outcome"] == motion.MOTION_MEASURED
        if not measured:
            st.caption("Cifras del ajuste mostradas por transparencia. **No son una medida de movimiento**: los "
                       "motivos anteriores impiden validarlas.")
        c = st.columns(4)
        c[0].metric("Desplazamiento medido" if measured else "Desplazamiento aparente (no validado)",
                    f"{d['total_arcsec']:.2f}″", f"± {d['total_err_arcsec']:.2f}″", delta_color="off")
        c[1].metric("Intervalo", f"{d['delta_t_days']:.0f} d", f"{d['first']} → {d['last']}", delta_color="off")
        c[2].metric("Significación", f"{d['significance_calibrated']:.1f}σ", f"umbral {motion.SIGNIFICANCE:g}σ",
                    delta_color="off")
        ctl = r.get("control") or {}
        c[3].metric("Control estacionario", f"{ctl.get('n', 0)} estrellas",
                    f"máx. {ctl.get('max_significance_calibrated', 0):.1f}σ", delta_color="off")
        st.caption(f"Δξ (este) = {d['dxi']:+.2f} ± {d['err_dxi_calibrated']:.2f}″ · Δη (norte) = {d['deta']:+.2f} ± "
                   f"{d['err_deta_calibrated']:.2f}″ · tasa media aparente {d['rate_arcsec_yr']:.2f}″/año (incluye "
                   "paralaje y la geometría de las fechas; no es un movimiento propio ajustado). Factor de "
                   f"calibración del control: {ctl.get('calibration_factor', 1):.2f}.")
    cc = r.get("catalogue_comparison")
    if cc:
        st.info(f"Comparación con el catálogo ({cc['source']}): desplazamiento **previsto** "
                f"{cc['predicted_total_arcsec']:.2f}″ (Δξ {cc['predicted_dxi']:+.2f}″, Δη {cc['predicted_deta']:+.2f}″) "
                f"entre las mismas fechas; diferencia con la medida {cc['difference_sigma']:.1f}σ "
                f"({'compatible' if cc['consistent_3sigma'] else 'no compatible'} a 3σ). La predicción no interviene "
                "en la búsqueda, el ajuste ni la decisión.")
    seasons = r.get("seasons") or []
    if seasons:
        st.markdown("**Posición medida por temporada** (ajuste conjunto de las exposiciones; tangente en la selección)")
        st.dataframe(pd.DataFrame([{
            "temporada": s["date_utc"], "imágenes": s["n_images"], "detección (σ)": round(s["significance"], 1),
            "ξ (″)": round(s["xi"], 2), "σξ (″)": round(s["err_xi"], 2), "η (″)": round(s["eta"], 2),
            "ση (″)": round(s["err_eta"], 2), "registro (″)": f"{s['err_registration'][0]:.2f}/{s['err_registration'][1]:.2f}",
            "χ² interno": None if s.get("internal_chi2_red") is None else round(s["internal_chi2_red"], 2),
            "núcleo saturado": "sí" if s["saturated_core"] else "no", "confusión": "sí" if s["confusion"] else "no",
            "usada": "sí" if s.get("usable") else "no"} for s in seasons]), hide_index=True, width="stretch")
    imgs = r.get("images") or []
    if imgs:
        with st.expander(f"Imágenes originales usadas ({len(imgs)})"):
            st.dataframe(pd.DataFrame([{
                "fecha (UTC)": (i.get("date_utc") or "")[:16], "obs_id": i.get("obs_id"),
                "λ (µm)": None if i.get("lambda_um") is None else round(i["lambda_um"], 3),
                "S/N": None if i.get("snr") is None else round(i["snr"], 1), "registro": i.get("registration_mode"),
                "WCS − Gaia (″)": _pair(i.get("wcs_offset_vs_gaia_arcsec")),
                "archivo": i.get("file"), "SHA-256": (i.get("sha256") or "")[:16] + "…"} for i in imgs]),
                hide_index=True, width="stretch")
            st.caption(imgs[0].get("psf_model", ""))
    ctl = r.get("control") or {}
    if ctl.get("stars"):
        with st.expander(f"Control: {ctl['n']} estrellas estacionarias medidas igual que la fuente"):
            st.dataframe(pd.DataFrame([{"Gaia DR3": c["gaia_source_id"], "G": c.get("g"),
                                        "Δξ (″)": round(c["dxi"], 2), "Δη (″)": round(c["deta"], 2),
                                        "σ (″)": f"{c['err_dxi']:.2f}/{c['err_deta']:.2f}",
                                        "significación": round(c["significance_calibrated"], 1)} for c in ctl["stars"]]),
                         hide_index=True, width="stretch")
            st.caption(ctl.get("rule", ""))
    for w in r.get("warnings", []):
        st.caption(f"Aviso: {w}")
    st.download_button("Descargar resultado reproducible (JSON)", json.dumps(r, ensure_ascii=False, indent=1),
                       file_name=f"skyclues_motion_{r.get('detector', 'x')}_{(seasons or [{}])[0].get('date_utc', 'na')}.json",
                       mime="application/json", key=f"{key}_download")


def _pair(v):
    if not v or v[0] is None:
        return "—"
    return f"{v[0]:+.2f}, {v[1]:+.2f}"


def render(seq, report_json: str) -> None:
    st.markdown(
        '<div class="sc-note"><b>Buscar algo que se mueve.</b> Mide la posición de una fuente en cada exposición '
        'SPHEREx original (IMAGE − ZODI, VARIANCE, FLAGS y el modelo ePSF oficial), registra cada imagen con '
        'estrellas Gaia estacionarias del campo y compara temporadas con incertidumbres. Resultados posibles: '
        '<i>Movimiento medido</i>, <i>Evidencia insuficiente</i>, <i>Observaciones incompatibles</i> o <i>Datos '
        'insuficientes</i>. Una posición calculada con el catálogo nunca se cuenta como detección.</div>',
        unsafe_allow_html=True)
    saved = saved_investigations()
    if saved:
        with st.expander("Investigaciones reales guardadas (results/motion_*.json)"):
            label = st.selectbox("Resultado", list(saved), key="mv_saved")
            show_result(json.loads(saved[label].read_text(encoding="utf-8")), key="mv_saved_view")
    a = seq.astrometry
    modes = SOURCE_MODES if a is not None else SOURCE_MODES[1:]
    src_mode = st.radio("Fuente a investigar", modes, horizontal=True, key="mv_source")
    f0 = seq.frames[0]
    if src_mode == SOURCE_MODES[0]:
        start = seq.target_position(0)
        st.caption(f"{a.name}: posición de catálogo calculada para la época 1 (RA {start[0]:.6f}°, Dec "
                   f"{start[1]:+.6f}°). Solo define el círculo de búsqueda; la posición se mide en cada temporada.")
    elif src_mode == SOURCE_MODES[1]:
        dets = motion.detect_sources(f0.image)
        if not dets:
            st.warning("No hay fuentes ≥ 5σ en la época 1 de este campo.")
            return
        opts = {f"#{i + 1} · {d['significance']:.0f}σ · RA {d['ra']:.5f}°, Dec {d['dec']:+.5f}° · píxel ({d['x']}, {d['y']})": d
                for i, d in enumerate(dets[:25])}
        d = opts[st.selectbox("Fuente detectada (filtro adaptado a la PSF, época 1)", list(opts), key="mv_detected")]
        start = (d["ra"], d["dec"])
    else:
        c1, c2 = st.columns(2)
        start = (c1.number_input("RA (°)", value=float(seq.ra), format="%.6f", key="mv_ra"),
                 c2.number_input("Dec (°)", value=float(seq.dec), format="%.6f", key="mv_dec"))
    radius = st.slider("Radio de búsqueda alrededor de la selección (″)", 5, 40, int(motion.SEARCH_RADIUS_ARCSEC),
                       key="mv_radius", help="La fuente se busca en cada temporada dentro de este círculo, sin usar "
                                             "predicciones. Debe cubrir el desplazamiento posible entre las fechas.")
    span = seq.metrics["span_days"]
    img_mode = st.radio("Imágenes", IMAGE_MODES, key="mv_images", horizontal=True,
                        captions=[f"{seq.n} imágenes · {span:.0f} d · campo {seq.field_deg * 60:g}′",
                                  f"D{f0.detector}, hasta {motion.MAX_SEASONS} temporadas lo más separadas posible, "
                                  f"recortes de {motion.MOTION_FIELD_DEG * 60:g}′"])
    per_season = motion.PER_SEASON
    if img_mode == IMAGE_MODES[1]:
        per_season = st.select_slider(
            "Imágenes por temporada", [2, 3, 4, 6, 8], value=motion.PER_SEASON, key="mv_per_season",
            help="Más exposiciones por temporada mejoran la señal de una fuente débil y la comprobación de "
                 "consistencia interna, a cambio de más recortes (~4 MB cada uno).")
        st.caption(f"Hasta {motion.MAX_SEASONS * per_season} recortes (~{4 * motion.MAX_SEASONS * per_season} MB, "
                   "se reutilizan desde la caché). El resultado depende de las exposiciones elegidas: se registra en "
                   "el informe.")
    if img_mode == IMAGE_MODES[0] and span < 30:
        st.caption(f"Esta secuencia abarca {span:.0f} días: solo se detectarían movimientos grandes. La base "
                   "temporal ampliada suele cubrir un año.")
    run = st.button("Investigar movimiento", type="primary", key="mv_run")
    key = json.dumps([report_json[:64], len(report_json), src_mode, start, radius, img_mode, per_season],
                     default=str)
    label = a.name if src_mode == SOURCE_MODES[0] and a else src_mode
    if run:
        with st.status("Midiendo posiciones en las imágenes originales…", expanded=True) as box:
            try:
                if img_mode == IMAGE_MODES[0]:
                    box.write("Consultando Gaia DR3 (estrellas estacionarias del campo)…")
                    gaia, err = _gaia_or_none(seq.ra, seq.dec, seq.field_deg)
                    box.write("Ajustando la ePSF y registrando cada época…")
                    inv = motion.investigate(seq.frames, start, gaia=gaia, astrometry=a,
                                             search_radius_arcsec=float(radius),
                                             source_label=label)
                    out = motion.to_jsonable(inv)
                    if err:
                        out.setdefault("warnings", []).append(err)
                else:
                    box.write("Seleccionando temporadas y descargando recortes (o leyendo la caché)…")
                    out = _investigate_extended(round(float(start[0]), 6), round(float(start[1]), 6),
                                                int(f0.detector), int(per_season), float(radius),
                                                float(start[0]), float(start[1]),
                                                json.dumps(a.to_dict()) if a else None, label)
                box.update(label=f"Investigación completada: {out['outcome_label']}", state="complete", expanded=False)
                st.session_state["mv_result"] = {"key": key, "result": out}
            except (archive.ArchiveError, motion.MotionInputError, ValueError) as err:
                box.update(label="La investigación no pudo completarse", state="error")
                st.error(f"{type(err).__name__}: {err}. No se ha mostrado ningún resultado parcial.")
    res = st.session_state.get("mv_result")
    if res and res["key"] == key:
        show_result(res["result"], key="mv_current")
    elif res:
        st.caption("Ha cambiado la selección: pulse «Investigar movimiento» para obtener un resultado nuevo.")
