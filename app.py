"""SkyClues - Streamlit entry point.

Run:  streamlit run app.py
"""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st
from astropy.time import Time

from skyclues import archive, config, fitsdata, render
from skyclues.compare import evaluate_pair
from skyclues.pairing import find_pair, save_report
from skyclues.quality import flag_census
from skyclues.targets import PRESETS, resolve_name

st.set_page_config(page_title="SkyClues", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; max-width: 1400px;}
      h1, h2, h3 {letter-spacing: -0.01em; color: #14181f;}
      .sc-sub {color:#4a5463; font-size: 0.95rem; margin-top:-0.6rem;}
      .sc-badge {display:inline-block; padding:2px 10px; border-radius:12px; font-size:0.8rem;
                 font-weight:600; border:1px solid #cfd5dd; background:#f3f5f8; color:#14181f;}
      .sc-ok {background:#e8f3ea; border-color:#9cc9a3; color:#1e5b28;}
      .sc-warn {background:#fff5e0; border-color:#f0c96b; color:#7a5300;}
      .sc-fail {background:#fdecef; border-color:#f0a3b6; color:#8a1a36;}
      .sc-note {border-left:3px solid #1f5fbf; background:#f3f6fb; padding:0.6rem 0.9rem;
                color:#14181f; font-size:0.9rem; margin:0.4rem 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

REFERENCE_REPORT = config.RESULTS_DIR / "pair_m101.json"
STATUS_LABEL = {"pass": "✔ cumple", "warn": "▲ aviso", "fail": "✖ no cumple"}


@st.cache_resource(show_spinner=False)
def load_image(cutout_url: str, expected_sha256: str | None):
    path = archive.fetch(cutout_url)
    digest = archive.sha256(path)
    return fitsdata.load(path), digest, (expected_sha256 is None or digest == expected_sha256)


def load_selected(report: dict):
    sel = report["selected"]
    out = []
    for tag in ("a", "b"):
        img, digest, ok = load_image(sel[tag]["cutout_url"], sel[tag].get("sha256"))
        out.append((img, digest, ok))
    return out


def fmt_date(mjd: float) -> str:
    return Time(mjd, format="mjd").isot[:16].replace("T", " ") + " UTC"


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("### Región del cielo")
    qp = st.query_params
    mode = st.radio("Origen", ["Pareja de referencia (M101)", "Nueva búsqueda"],
                    index=1 if "ra" in qp else 0)
    run_search = False
    if mode == "Nueva búsqueda":
        how = st.radio("Definir por", ["Coordenadas RA/Dec", "Campo predefinido", "Nombre (Sesame/SIMBAD)"],
                       horizontal=False)
        ra0 = float(qp.get("ra", 210.802429))
        dec0 = float(qp.get("dec", 54.34875))
        if how == "Campo predefinido":
            name = st.selectbox("Campo", list(PRESETS))
            ra0, dec0 = PRESETS[name]["ra"], PRESETS[name]["dec"]
            if PRESETS[name]["high_pm"]:
                st.warning("Objeto de alto movimiento propio: la posición es de catálogo (J2000) "
                           "y no está propagada a la fecha de observación.")
        elif how == "Nombre (Sesame/SIMBAD)":
            obj = st.text_input("Nombre del objeto", "M101")
            if st.button("Resolver nombre"):
                try:
                    st.session_state["resolved"] = resolve_name(obj)
                except Exception as err:
                    st.error(f"No se pudo resolver: {err}")
            if "resolved" in st.session_state:
                ra0, dec0 = st.session_state["resolved"]
            st.caption("Posición de catálogo (época J2000), sin propagar movimiento propio.")
        ra = st.number_input("RA (grados, ICRS)", value=ra0, format="%.6f", min_value=0.0, max_value=360.0)
        dec = st.number_input("Dec (grados, ICRS)", value=dec0, format="%.6f", min_value=-90.0, max_value=90.0)
        fov = st.select_slider("Diámetro del campo (grados)", options=[0.05, 0.1, 0.15, 0.2],
                               value=float(qp.get("fov", config.DEFAULT_FIELD_DEG)))
        dets = st.multiselect("Detectores", [1, 2, 3, 4, 5, 6], default=[1, 2, 3, 4, 5, 6],
                              help="D1–D3: 0.75–2.41 µm (SWIR) · D4–D6: 2.42–5.0 µm (MWIR)")
        same = st.checkbox("Exigir misma colección (DR1 con DR1, QR3 con QR3)", value=False)
        run_search = st.button("Buscar pareja comparable", type="primary")
    st.markdown("---")
    st.markdown("### Máscara de calidad")
    mask_policy = st.radio(
        "Píxeles excluidos", ["Estricta: inutilizables + artefactos", "Básica: solo inutilizables"],
        help="Inutilizables: OVERFLOW, SUR_ERROR, NONFUNC, MISSING_DATA, HOT, COLD, NONLINEAR. "
             "Artefactos: TRANSIENT, PERSIST, OUTLIER, CROSSTALK, GHOST*, STREAK, BLOOM, SNOWBALL, HALO, "
             "DICHROIC, PHANMISS. SOURCE y FULLSAMPLE son informativos y nunca se enmascaran.")
    MASK = ("unusable", "artifact") if mask_policy.startswith("Estricta") else ("unusable",)
    st.markdown("---")
    st.caption("Datos: NASA/IPAC IRSA · SPHEREx DR1 y QR3 (SIA2). "
               "Las imágenes se muestran tal como se publican; la escala de intensidad es "
               "solo de visualización.")

# ---------------------------------------------------------------- header
st.markdown("# SkyClues")
st.markdown('<div class="sc-sub">Explorador temporal de observaciones SPHEREx auténticas · '
            'prototipo científico · NASA Space Apps 2026</div>', unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------- data
if mode == "Nueva búsqueda" and run_search:
    st.query_params.update({"ra": f"{ra:.6f}", "dec": f"{dec:.6f}", "fov": str(fov)})
    log_box = st.status("Consultando NASA/IPAC IRSA…", expanded=True)
    try:
        best, report = find_pair(ra, dec, fov, detectors=dets, require_same_collection=same,
                                 log=lambda m: log_box.write(m))
        log_box.update(label="Búsqueda completada", state="complete", expanded=False)
        st.session_state["report"] = report
        save_report(report, f"search_{ra:.4f}_{dec:+.4f}_{fov}")
    except Exception as err:
        log_box.update(label="La consulta falló", state="error")
        st.error(f"Error de acceso a IRSA: {err}")
        st.stop()

if mode == "Pareja de referencia (M101)":
    if not REFERENCE_REPORT.exists():
        st.info("No existe todavía la pareja de referencia. Ejecute `python scripts/find_pair.py` "
                "o use «Nueva búsqueda».")
        st.stop()
    report = json.loads(REFERENCE_REPORT.read_text(encoding="utf-8"))
else:
    report = st.session_state.get("report")
    if report is None:
        st.info("Defina una región y pulse «Buscar pareja comparable».")
        st.stop()

sel = report.get("selected")
if not sel:
    st.warning(f"No se encontró una pareja admisible: {report['n_records']} imágenes, "
               f"{report['n_candidates']} con el campo completo, "
               f"{report['n_preselected_pairs']} parejas preseleccionadas. "
               "Pruebe un campo menor u otros detectores.")
    if report.get("evaluated"):
        st.dataframe(pd.DataFrame([{c["id"]: STATUS_LABEL[c["status"]] for c in e["criteria"]}
                                   for e in report["evaluated"]]))
    st.stop()

ra_t, dec_t = report["target"]["ra_deg"], report["target"]["dec_deg"]
fov_t = report["target"]["field_deg"]
with st.spinner("Cargando FITS (caché local o IRSA)…"):
    (img_a, dig_a, ok_a), (img_b, dig_b, ok_b) = load_selected(report)
ev = evaluate_pair(img_a, img_b, ra_t, dec_t, fov_t, collections=(sel["a"]["collection"], sel["b"]["collection"]),
                   mask_classes=MASK)
m = ev.metrics

# ---------------------------------------------------------------- summary
status_cls = "sc-ok" if ev.admissible and not ev.warnings else ("sc-warn" if ev.admissible else "sc-fail")
status_txt = ("Comparable" if not ev.warnings else "Comparable con avisos") if ev.admissible else "No comparable"
st.markdown(f'<span class="sc-badge {status_cls}">{status_txt}</span> &nbsp; '
            f'<span class="sc-badge">RA {ra_t:.5f}° · Dec {dec_t:+.5f}° · campo {fov_t}°</span>',
            unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Separación temporal", f"{m['delta_t_days']:.1f} días")
c2.metric("Longitud de onda en el objetivo", f"{m['lambda_target_um'][0]:.3f} µm",
          f"Δλ = {abs(m['lambda_target_um'][0] - m['lambda_target_um'][1]) * 1000:.1f} nm", delta_color="off")
c3.metric("Cobertura común válida", f"{m['coverage_common_valid']:.1%}")
c4.metric("Detector", f"D{img_a.meta['DETECTOR']}",
          f"{config.BANDS_UM[img_a.meta['DETECTOR']][0]}–{config.BANDS_UM[img_a.meta['DETECTOR']][1]} µm",
          delta_color="off")

tab_ab, tab_native, tab_cov, tab_q, tab_meta, tab_obs = st.tabs(
    ["Comparación A/B", "Vistas nativas", "Cobertura y espectro", "Calidad (FLAGS)",
     "Metadatos y procedencia", "Observaciones disponibles"])

subtract = True
with tab_ab:
    left, right = st.columns([3, 2])
    with right:
        which = st.radio("Época", [f"A · {fmt_date(m['mjd'][0])}", f"B · {fmt_date(m['mjd'][1])}"])
        subtract = st.checkbox("Restar el modelo zodiacal (IMAGE − ZODI)", value=True,
                               help="El fondo zodiacal cambia con la fecha; restarlo evita confundirlo con un cambio del cielo.")
        st.markdown(
            '<div class="sc-note">B se muestra sobre la rejilla de píxeles de A por <b>vecino más próximo</b> '
            '(valores copiados, sin interpolar). Ambas épocas comparten la <b>misma escala</b> de intensidad. '
            f'Los píxeles <span style="color:{render.MASK_COLOR}"><b>en color rosa</b></span> están enmascarados '
            'por FLAGS o carecen de datos: no se rellenan.</div>', unsafe_allow_html=True)
        st.caption("Cruz y círculo azules: objetivo y campo de comparación.")
    da = render.display_array(img_a, subtract, MASK)
    db = render.aligned_b(img_b, ev, subtract, MASK)
    norm = render.shared_norm([da, db], region=ev.field_mask)
    qty = "IMAGE − ZODI" if subtract else "IMAGE"
    with left:
        if which.startswith("A"):
            fig = render.frame_figure(da, img_a.wcs, norm, f"A · {fmt_date(m['mjd'][0])} · {qty}", ra_t, dec_t, fov_t,
                                      subtitle=img_a.meta["FILE"])
        else:
            fig = render.frame_figure(db, img_a.wcs, norm, f"B · {fmt_date(m['mjd'][1])} · {qty} (rejilla de A)",
                                      ra_t, dec_t, fov_t, subtitle=img_b.meta["FILE"])
        st.pyplot(fig, clear_figure=True, width="content")
        plt.close("all")

with tab_native:
    st.caption("Cada imagen en su rejilla original del detector (orientación distinta en cada visita). "
               "Misma escala de intensidad.")
    na = render.display_array(img_a, subtract, MASK)
    nb = render.display_array(img_b, subtract, MASK)
    cols = st.columns(2)
    for col, img, data, tag, mjd in ((cols[0], img_a, na, "A", m["mjd"][0]), (cols[1], img_b, nb, "B", m["mjd"][1])):
        with col:
            st.pyplot(render.frame_figure(data, img.wcs, norm, f"{tag} · {fmt_date(mjd)}", ra_t, dec_t, fov_t,
                                          subtitle=img.meta["FILE"]), clear_figure=True)
    plt.close("all")

with tab_cov:
    cols = st.columns(2)
    with cols[0]:
        st.pyplot(render.coverage_figure(ev, img_a.wcs, ra_t, dec_t, fov_t), clear_figure=True)
    with cols[1]:
        st.pyplot(render.dlambda_figure(ev, img_a.wcs, ra_t, dec_t, fov_t), clear_figure=True)
    plt.close("all")
    st.markdown(
        f"Los filtros LVF de SPHEREx hacen que la longitud de onda dependa de la posición en el detector. "
        f"En la zona común, la mediana de |Δλ| es **{m['dlambda_common_median_bw']:.2f}** anchos de banda y el "
        f"máximo **{m['dlambda_common_max_bw']:.2f}**; el **{m['fraction_common_within_pass_bw']:.0%}** de los "
        f"píxeles comunes difiere ≤ {config.SPECTRAL_PASS_BW} anchos de banda.")

with tab_q:
    cols = st.columns(2)
    for col, img, tag in ((cols[0], img_a, "A"), (cols[1], img_b, "B")):
        with col:
            st.markdown(f"**{tag}** — FLAGS dentro del recorte ({img.flag_defs.source})")
            df = pd.DataFrame(flag_census(img.flags, img.flag_defs))
            df["fraction"] = (df["fraction"] * 100).round(2)
            df = df.rename(columns={"bit": "bit", "name": "flag", "class": "clase", "pixels": "píxeles",
                                    "fraction": "%", "description": "descripción"})
            st.dataframe(df[df["píxeles"] > 0], hide_index=True, width="stretch")
    st.caption("Clases: «unusable» y «artifact» se enmascaran para la comparación; «info» (SOURCE, FULLSAMPLE) "
               "no se enmascara. Nombres leídos de las claves MSKN de cada FITS.")

with tab_meta:
    rows = []
    for tag, img, s, dig, ok in (("A", img_a, sel["a"], dig_a, ok_a), ("B", img_b, sel["b"], dig_b, ok_b)):
        lam, bw = m["lambda_target_um"][0 if tag == "A" else 1], m["bandwidth_target_um"][0 if tag == "A" else 1]
        rows.append({
            "época": tag, "fecha media (UTC)": img.meta["DATE-AVG"], "MJD-AVG": img.meta["MJD-AVG"],
            "obs_id": img.meta["OBSID"], "colección": s["collection"], "detector": img.meta["DETECTOR"],
            "λ en objetivo (µm)": round(lam, 4), "ancho de banda (µm)": round(bw, 4),
            "exposición (s)": img.meta["XPOSURE"], "software": img.meta["VERSION"],
            "L2 DQA": img.meta["L2DQAFLG"], "PSF FWHM (″)": round(img.meta["PSF_FWHM"] or float("nan"), 2),
            "archivo": img.meta["FILE"], "SHA-256": dig[:16] + "…",
            "integridad": "coincide con el informe" if ok else "DIFERENTE del informe",
        })
    st.dataframe(pd.DataFrame(rows).set_index("época").T, width="stretch")
    st.markdown("**Recortes IRSA (reproducibles)**")
    st.code(f"A: {sel['a']['cutout_url']}\nB: {sel['b']['cutout_url']}", language=None)
    st.caption("Fuente: NASA/IPAC Infrared Science Archive. SPHEREx DR1 Spectral Images, doi:10.26131/IRSA678.")

with tab_obs:
    obs = report.get("observations", [])
    if obs:
        df = pd.DataFrame(obs)
        df["fecha (UTC)"] = Time(df["mjd_mid"].to_numpy(), format="mjd").isot
        df["fecha (UTC)"] = df["fecha (UTC)"].str.slice(0, 16)
        df = df.sort_values("mjd_mid")[["fecha (UTC)", "collection", "detector", "obs_id", "lambda_est_um",
                                        "bandwidth_est_um", "exptime_s", "field_margin_px", "file_name"]]
        st.caption(f"{len(df)} imágenes con el campo completo dentro del detector "
                   f"(de {report['n_records']} que contienen el objetivo). λ estimada desde metadatos "
                   "(polígono s_region + tabla WCS-WAVE del detector); la decisión final usa el FITS.")
        st.dataframe(df.round(4), hide_index=True, width="stretch")

# ---------------------------------------------------------------- criteria
st.markdown("### Criterios de comparabilidad")
crit = pd.DataFrame([{"": c["id"], "criterio": c["criterion"], "valor": c["value"], "umbral": c["threshold"],
                      "estado": STATUS_LABEL[c["status"]]} for c in ev.criteria])
st.dataframe(crit, hide_index=True, width="stretch")
for n in ev.notes:
    st.markdown(f'<div class="sc-note">{n}</div>', unsafe_allow_html=True)

with st.expander("Limitaciones científicas de esta comparación"):
    st.markdown(
        "- **Comparación definida:** brillo superficial (IMAGE − ZODI, MJy/sr) del mismo detector y canal LVF "
        "efectivo, en los píxeles válidos de ambas fechas. No es fotometría de fuentes ni detección de movimiento.\n"
        "- La longitud de onda por píxel procede de la tabla WCS-WAVE (precisión de visualización, ~1 nm); "
        "para ciencia, IRSA recomienda los productos de calibración CWAVE/CBAND.\n"
        "- Una diferencia visual entre A y B puede deberse a ruido, fondo, PSF, persistencia, rayos cósmicos o "
        "Δλ residual; no implica variabilidad ni movimiento astronómico.\n"
        "- Los recortes se alinean con los ejes del detector; B se coloca sobre la rejilla de A por vecino más "
        "próximo (error de posición ≤ ½ píxel ≈ 3″).\n"
        "- Las coordenadas de catálogo no se propagan por movimiento propio.")
