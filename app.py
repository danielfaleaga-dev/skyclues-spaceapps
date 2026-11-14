"""SkyClues - Streamlit entry point.

Run:  streamlit run app.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from astropy.time import Time

from skyclues import archive, config, player, render
from skyclues.quality import flag_census
from skyclues.sequence import STRICT, find_sequence, load_sequence, report_urls, save_report
from skyclues.targets import PRESETS, clamp_fov_deg, fov_pixels, resolve_name

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

STATUS_LABEL = {"pass": "✔ cumple", "warn": "▲ aviso", "fail": "✖ no cumple"}
MODES = ["Secuencia de referencia", "Nueva búsqueda"]
GEOMETRY_OPTIONS = {
    "Exacta: píxeles nativos, sin remuestreo": "exact",
    "Rejilla común: vecino más próximo (remuestreado)": "nearest",
}
FOV_LABELS = [f"{a:g}′" for a in config.FOV_PRESETS_ARCMIN] + ["Otro"]


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
            label = (f"{p.stem.replace('sequence_', '')} · {len(fr)} épocas · D{fr[0]['detector']} · "
                     f"{fr[0]['lambda_target_um']:.2f} µm · {fr[0]['collection']}")
        else:
            label = (f"{p.stem.replace('pair_', '')} · pareja · D{sel['a']['detector']} · "
                     f"Δt {sel['metrics']['delta_t_days']:.0f} d · {sel['a']['collection']}")
        out[label] = str(p)
    return out


def label_for(stem: str, refs: dict[str, str]) -> str | None:
    return next((label for label, p in refs.items() if Path(p).stem == stem), None)


@st.cache_resource(show_spinner=False, max_entries=8)
def cached_sequence(report_json: str):
    # Comparability (masks, coverage, S1-S9) always uses the strict mask.
    return load_sequence(json.loads(report_json), mask_classes=STRICT)


@st.cache_data(show_spinner=False, max_entries=16)
def cached_player(report_json: str, subtract: bool, restrict: bool, geometry: str, halo: bool) -> str:
    return player.build_player(cached_sequence(report_json), subtract, restrict, geometry, halo)


def fmt_date(mjd: float) -> str:
    return Time(mjd, format="mjd").isot[:16].replace("T", " ") + " UTC"


def irsa_error(err: Exception) -> str:
    text = str(err)
    if any(k in text for k in ("503", "busy", "Download failed", "SIA2 query failed", "Range request")):
        return ("NASA/IPAC IRSA no respondió a tiempo (el servidor indica que está ocupado o no está disponible). "
                "No se ha mostrado ningún dato parcial. Pruebe de nuevo en unos minutos o abra un ejemplo validado.")
    return "No se pudo completar el acceso a IRSA. No se ha mostrado ningún dato parcial."


refs = reference_reports()
qp = st.query_params
if "mode" not in st.session_state:
    st.session_state["mode"] = MODES[1] if "ra" in qp else MODES[0]
if st.session_state.get("ref_label") not in refs:
    st.session_state.pop("ref_label", None)


def open_example(stem: str):
    label = label_for(stem, refs)
    if label:
        st.session_state["mode"] = MODES[0]
        st.session_state["ref_label"] = label


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    examples = [(stem, title) for stem, title in config.VALIDATED_EXAMPLES.items() if label_for(stem, refs)]
    if examples:
        st.markdown("### Ejemplos validados")
        for stem, title in examples:
            st.button(title, key=f"example_{stem}", on_click=open_example, args=(stem,), width="stretch")
        st.caption("Secuencias reales ya verificadas: se abren sin repetir la búsqueda.")
        st.markdown("---")

    st.markdown("### Región del cielo")
    mode = st.radio("Origen", MODES, key="mode")
    run_search = False
    fov = config.DEFAULT_FIELD_DEG
    if mode == MODES[0]:
        ref_label = st.selectbox("Resultado guardado", list(refs), key="ref_label") if refs else None
    else:
        how = st.radio("Definir por", ["Coordenadas RA/Dec", "Campo predefinido", "Nombre (Sesame/SIMBAD)"])
        try:
            ra0, dec0 = float(qp.get("ra", 210.802429)), float(qp.get("dec", 54.34875))
        except ValueError:
            ra0, dec0 = 210.802429, 54.34875
        if how == "Campo predefinido":
            name = st.selectbox("Campo", list(PRESETS))
            ra0, dec0 = PRESETS[name]["ra"], PRESETS[name]["dec"]
            if PRESETS[name]["high_pm"]:
                st.warning("Objeto de alto movimiento propio: la posición es de catálogo y no está "
                           "propagada a la fecha de observación.")
        elif how == "Nombre (Sesame/SIMBAD)":
            obj = st.text_input("Nombre del objeto", "M101")
            if st.button("Resolver nombre", key="resolve"):
                try:
                    st.session_state["resolved"] = resolve_name(obj)
                except Exception as err:
                    st.error(f"No se pudo resolver: {err}")
            if "resolved" in st.session_state:
                ra0, dec0 = st.session_state["resolved"]
            st.caption("Posición de catálogo (época J2000), sin propagar movimiento propio.")
        ra = st.number_input("RA (grados, ICRS)", value=min(max(ra0, 0.0), 360.0), format="%.6f",
                             min_value=0.0, max_value=360.0)
        dec = st.number_input("Dec (grados, ICRS)", value=min(max(dec0, -90.0), 90.0), format="%.6f",
                              min_value=-90.0, max_value=90.0)

        # Field of view: the sky region searched, downloaded and compared (not a screen zoom).
        fov_q = clamp_fov_deg(qp.get("fov", config.DEFAULT_FIELD_DEG))
        preset = next((lbl for lbl, a in zip(FOV_LABELS, config.FOV_PRESETS_ARCMIN)
                       if abs(round(a / 60, 4) - fov_q) < 1e-6), "Otro")
        fov_choice = st.radio(
            "Campo de visión (diámetro en el cielo)", FOV_LABELS, index=FOV_LABELS.index(preset),
            horizontal=True, key="fov_preset",
            help="Tamaño angular de la región que se busca en IRSA, se descarga y se compara entre épocas "
                 "(1′ = 1/60 de grado). No es el zoom de la pantalla. Todo el campo debe caer dentro del "
                 "detector en cada época.")
        if fov_choice == "Otro":
            arcmin = st.number_input("Diámetro personalizado (minutos de arco)", min_value=config.FOV_MIN_DEG * 60,
                                     max_value=config.FOV_MAX_DEG * 60, value=fov_q * 60, step=0.5,
                                     format="%.1f", key="fov_custom")
            fov = clamp_fov_deg(arcmin / 60)
        else:
            fov = round(config.FOV_PRESETS_ARCMIN[FOV_LABELS.index(fov_choice)] / 60, 4)
        npx = fov_pixels(fov)
        st.caption(f"{fov * 60:.1f}′ = {fov:.3f}° · ≈ {npx} × {npx} píxeles SPHEREx (6.15″/px). "
                   f"Límites: {config.FOV_MIN_DEG * 60:g}′–{config.FOV_MAX_DEG * 60:g}′.")
        if fov > config.FOV_SLOW_DEG:
            st.warning(f"Campo grande ({npx}² píxeles por época): la alineación, la evaluación y el reproductor "
                       "tardan más, y hay menos observaciones que contengan el campo completo.")

        dets = st.multiselect("Detectores", [1, 2, 3, 4, 5, 6], default=[1, 2, 3, 4, 5, 6],
                              help="D1–D3: 0.75–2.41 µm (SWIR) · D4–D6: 2.42–5.0 µm (MWIR)")
        max_frames = st.slider("Máximo de épocas", 2, 8, config.MAX_SEQUENCE_FRAMES)
        if not dets:
            st.caption("Elija al menos un detector.")
        run_search = st.button("Buscar secuencia comparable", type="primary", key="search", disabled=not dets)
        st.caption("Una búsqueda nueva suele tardar de 1 a 2 minutos: los recortes FITS se descargan de IRSA.")

    st.markdown("---")
    st.markdown("### Visualización")
    geometry = GEOMETRY_OPTIONS[st.radio(
        "Geometría de los fotogramas", list(GEOMETRY_OPTIONS), key="geometry",
        help="Exacta: cada píxel de cada época se dibuja en su posición real del cielo (WCS) con su valor "
             "original; nada se remuestrea. Rejilla común: cada época se copia a la rejilla de la época 1 por "
             "vecino más próximo (la que usan las métricas); una estrella fija puede desplazarse hasta "
             "½ píxel por eje.")]
    subtract = st.checkbox("Restar el modelo zodiacal (IMAGE − ZODI)", value=True,
                           help="El fondo zodiacal cambia con la fecha; restarlo evita confundirlo con un cambio del cielo.")
    restrict = st.checkbox("Destacar la región común a todas las épocas", value=False,
                           help="Los píxeles válidos solo en algunas épocas se tiñen de azul claro.")
    halo = st.toggle(
        "Modo exploratorio: mostrar píxeles HALO", value=False, key="halo",
        help="HALO marca vecinos de píxeles con transitorios (a menudo el desbordamiento de carga de una estrella "
             "brillante) y de 'snowballs'. La documentación de SPHEREx recomienda precaución al usarlos. En este modo "
             "se muestran en escala cobre; nunca se cuentan como válidos en las métricas.")
    st.caption("Las métricas y criterios usan siempre la máscara estricta: inutilizables + artefactos (HALO incluido).")
    st.markdown("---")
    st.caption("Datos: NASA/IPAC IRSA · SPHEREx DR1 y QR3 (SIA2). Cada fotograma es una observación real; "
               "la escala de intensidad es solo de visualización.")

# ---------------------------------------------------------------- header
st.markdown("# SkyClues")
st.markdown('<div class="sc-sub">Explorador temporal de observaciones SPHEREx auténticas · '
            'prototipo científico · NASA Space Apps 2026</div>', unsafe_allow_html=True)
st.write("")

# ---------------------------------------------------------------- data
if mode == MODES[1] and run_search:
    st.query_params.update({"ra": f"{ra:.6f}", "dec": f"{dec:.6f}", "fov": f"{fov:g}"})
    box = st.status(f"Buscando observaciones comparables en NASA/IPAC IRSA (campo {fov * 60:.1f}′)…", expanded=True)
    bar = box.progress(0.0, text="Iniciando la búsqueda…")
    try:
        _, rep = find_sequence(ra, dec, fov, detectors=dets, max_frames=max_frames, log=lambda m: None,
                               progress=lambda stage, frac, msg: bar.progress(frac, text=msg))
    except Exception as err:
        box.update(label="La búsqueda no pudo completarse", state="error", expanded=True)
        st.error(irsa_error(err))
        with st.expander("Detalle técnico"):
            st.code(f"{type(err).__name__}: {err}", language=None)
        st.stop()
    box.update(label=f"Búsqueda completada en {rep['elapsed_s']} s", state="complete", expanded=False)
    st.session_state["report"] = rep
    try:
        save_report(rep, f"search_{ra:.4f}_{dec:+.4f}_{fov:g}")
    except OSError:
        pass  # read-only deployments: the report stays in the session

if mode == MODES[0]:
    if not ref_label:
        st.info("No hay resultados guardados. Ejecute `python scripts/find_sequence.py` o use «Nueva búsqueda».")
        st.stop()
    report = json.loads(Path(refs[ref_label]).read_text(encoding="utf-8"))
else:
    report = st.session_state.get("report")
    if report is None:
        st.info("Defina una región y un campo de visión y pulse «Buscar secuencia comparable», "
                "o abra uno de los ejemplos validados de la barra lateral.")
        st.stop()

if not report.get("selected"):
    st.warning(f"No se encontró una secuencia admisible ({report.get('n_records', 0)} imágenes, "
               f"{report.get('n_candidates', 0)} con el campo completo). Pruebe un campo menor u otros detectores.")
    if report.get("options"):
        st.dataframe(pd.DataFrame(report["options"]).astype(str), hide_index=True)
    st.stop()

report_json = json.dumps(report, sort_keys=True, default=str)
urls = report_urls(report)
missing = [u for u in urls if archive.local_copy(u) is None]
if missing:
    box = st.status(f"Descargando {len(missing)} recortes FITS de IRSA…", expanded=True)
    bar = box.progress(0.0, text="Conectando con IRSA…")
    got = archive.fetch_many(urls, progress=lambda done, total, n: bar.progress(
        done / max(total, 1), text=f"{done} de {total} recortes listos ({n} descargados)"))
    failed = [r for r in got.values() if isinstance(r, Exception)]
    if failed:
        box.update(label="No se pudieron obtener todos los recortes", state="error", expanded=True)
        st.error(irsa_error(failed[0]))
        with st.expander("Detalle técnico"):
            st.code("\n".join(str(e) for e in failed), language=None)
        st.stop()
    box.update(label="Recortes FITS obtenidos", state="complete", expanded=False)

with st.spinner("Verificando la integridad de los FITS y alineando épocas…"):
    try:
        seq = cached_sequence(report_json)
    except (ValueError, RuntimeError, OSError) as err:
        st.error(f"No se pudo cargar la secuencia: {err}")
        st.stop()
m = seq.metrics

# ---------------------------------------------------------------- summary
status_cls = "sc-ok" if seq.admissible and not seq.warnings else ("sc-warn" if seq.admissible else "sc-fail")
status_txt = ("Comparable" if not seq.warnings else "Comparable con avisos") if seq.admissible else "No comparable"
st.markdown(f'<span class="sc-badge {status_cls}">{status_txt}</span> &nbsp; '
            f'<span class="sc-badge">RA {seq.ra:.5f}° · Dec {seq.dec:+.5f}° · campo de visión '
            f'{seq.field_deg * 60:.1f}′ ({seq.field_deg:g}°)</span>',
            unsafe_allow_html=True)
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Épocas", seq.n)
c2.metric("Intervalo total", f"{m['span_days']:.1f} d")
c3.metric("λ en el objetivo", f"{seq.frames[0].lambda_target_um:.3f} µm",
          f"dispersión {m['lambda_spread_target_bw']:.2f} BW", delta_color="off")
c4.metric("Cobertura común válida", f"{m['coverage_common_valid']:.1%}")
det = seq.frames[0].detector
c5.metric("Detector", f"D{det}", f"{config.BANDS_UM[det][0]}–{config.BANDS_UM[det][1]} µm", delta_color="off")

tab_play, tab_cov, tab_q, tab_meta, tab_opt, tab_obs = st.tabs(
    ["Reproductor temporal", "Cobertura y espectro", "Calidad por época", "Metadatos y procedencia",
     "Opciones evaluadas", "Observaciones disponibles"])

with tab_play:
    with st.spinner("Preparando fotogramas…"):
        html = cached_player(report_json, subtract, restrict, geometry, halo)
    components.html(html, height=640, scrolling=True)
    geo_txt = ("Geometría exacta: cada píxel nativo se dibuja en su posición real del cielo con su valor original "
               "(sin remuestreo); la rotación entre visitas se ve como píxeles inclinados." if geometry == "exact" else
               "Producto REMUESTREADO: cada época se copia a la rejilla de la época 1 por vecino más próximo "
               "(desplazamiento de hasta ½ píxel por eje).")
    st.caption("Cada fotograma es una exposición SPHEREx real (sin fotogramas intermedios ni interpolación temporal), "
               f"con la misma escala de intensidad. {geo_txt} El tamaño en pantalla es fijo: un campo de visión mayor "
               "muestra más cielo, no es un zoom. Una diferencia visual no es por sí sola una detección de movimiento "
               "o variabilidad.")

with tab_cov:
    cols = st.columns(2)
    with cols[0]:
        st.image(render.figure_png(render.sequence_coverage_figure(seq)))
    with cols[1]:
        st.image(render.figure_png(render.sequence_spread_figure(seq)))
    st.markdown(f"Región válida común a las {seq.n} épocas: **{m['coverage_common_valid']:.1%}** del campo "
                f"({m['n_common_px']} píxeles). Dispersión máxima de λ en esa región: "
                f"**{m['lambda_spread_common_max_bw']:.2f}** anchos de banda.")
    gain = pd.DataFrame({"época": [i + 1 for i in range(seq.n)], "fecha": [f.date_utc[:16] for f in seq.frames],
                         "cobertura ganada si se excluye (puntos)":
                             [round(100 * g, 1) for g in m["coverage_gain_if_frame_removed"]]})
    st.dataframe(gain, hide_index=True, width="stretch")

with tab_q:
    q = pd.DataFrame([{"época": i + 1, "fecha (UTC)": f.date_utc[:16], **{
        "L2 DQA": f.quality["L2DQAFLG"], "FINAST": f.quality["FINAST"],
        "válido en campo (%)": round(100 * f.quality["valid_fraction_in_field"], 1),
        "solo HALO (%)": round(100 * f.quality.get("halo_only_fraction_in_field", float("nan")), 2),
        "saturación (%)": round(100 * f.quality["saturation_fraction_in_field"], 3),
        "ZODI (MJy/sr)": round(f.quality["zodi_median_mjysr"], 3),
        "PSF FWHM (″)": round(float(f.quality["psf_fwhm_arcsec"] or float("nan")), 2),
        "desplaz. máx. rejilla común (px)": round(float(seq.placement_error_px(i)[seq.field_mask].max()), 2)}}
        for i, f in enumerate(seq.frames)])
    st.dataframe(q, hide_index=True, width="stretch")
    st.caption("«solo HALO»: píxeles del campo enmascarados únicamente por HALO (visibles en el modo exploratorio). "
               "«desplaz. máx.»: distancia máxima entre un píxel de la rejilla común y el píxel nativo que el vecino "
               "más próximo copia allí (0 en la época de referencia).")
    k = st.selectbox("FLAGS de la época", list(range(1, seq.n + 1)),
                     format_func=lambda i: f"{i} · {seq.frames[i - 1].date_utc[:16]}")
    img = seq.frames[k - 1].image
    df = pd.DataFrame(flag_census(img.flags, img.flag_defs))
    df["fraction"] = (df["fraction"] * 100).round(2)
    st.dataframe(df[df["pixels"] > 0].rename(columns={"name": "flag", "class": "clase", "pixels": "píxeles",
                                                      "fraction": "%", "description": "descripción"}),
                 hide_index=True, width="stretch")
    st.caption("«unusable» y «artifact» se enmascaran; «info» (SOURCE, FULLSAMPLE) no. Referencia: SPHEREx "
               "Explanatory Supplement v2.1, tabla 16 (HALO: «se recomienda precaución»; SATELLITE_HALO: "
               "«no recomendado»).")

with tab_meta:
    rows = []
    for i, f in enumerate(seq.frames):
        s = f.summary()
        rows.append({"época": i + 1, "fecha media (UTC)": s["date_utc"], "MJD": round(s["mjd"], 5),
                     "obs_id": s["obs_id"], "colección": s["collection"], "detector": s["detector"],
                     "λ objetivo (µm)": round(s["lambda_target_um"], 4),
                     "ancho de banda (µm)": round(s["bandwidth_target_um"], 4),
                     "exposición (s)": s["exptime_s"], "software": s["software_version"],
                     "archivo": s["file_name"], "SHA-256": s["sha256"][:16] + "…"})
    st.dataframe(pd.DataFrame(rows).astype(str), hide_index=True, width="stretch")
    st.markdown("**Recortes IRSA (reproducibles)**")
    st.code("\n".join(f"{i + 1}: {f.cutout_url}" for i, f in enumerate(seq.frames)), language=None)
    st.caption("Fuente: NASA/IPAC Infrared Science Archive. SPHEREx DR1 Spectral Images, doi:10.26131/IRSA678; "
               "SPHEREx QR3. Integridad: SHA-256 de cada FITS comprobado frente al informe.")

with tab_opt:
    if report.get("options"):
        st.caption("Regla de selección: " + report.get("selection_rule", ""))
        opt = pd.DataFrame(report["options"])
        opt["cobertura"] = (opt["coverage_common_valid"] * 100).round(1)
        st.dataframe(opt[["origin", "detector", "n_frames", "cobertura", "lambda_spread_common_max_bw",
                          "span_days", "admissible", "dates"]].astype(str), hide_index=True, width="stretch")
        for r in report.get("rejected_larger_options", []):
            st.markdown(f"- Opción de **{r['n_frames']} épocas** (D{r.get('detector', '?')}, cobertura "
                        f"{r['coverage']:.1%}) descartada: {'; '.join(r['reasons'])}")
    else:
        st.caption("Resultado de pareja (sin exploración de secuencias).")

with tab_obs:
    obs = report.get("observations", [])
    if obs:
        df = pd.DataFrame(obs)
        df["fecha (UTC)"] = pd.Series(Time(df["mjd_mid"].to_numpy(), format="mjd").isot).str.slice(0, 16)
        cols_obs = [c for c in ["fecha (UTC)", "collection", "detector", "obs_id", "lambda_est_um",
                                "bandwidth_est_um", "exptime_s", "field_margin_px", "file_name"] if c in df]
        st.caption(f"{len(df)} imágenes con el campo completo dentro del detector (de {report.get('n_records')} "
                   "que contienen el objetivo). λ estimada desde metadatos; la decisión final usa el FITS.")
        st.dataframe(df.sort_values("mjd_mid")[cols_obs].round(4), hide_index=True, width="stretch")

# ---------------------------------------------------------------- criteria
st.markdown("### Criterios de comparabilidad (todas las épocas a la vez)")
st.dataframe(pd.DataFrame([{"": c["id"], "criterio": c["criterion"], "valor": c["value"], "umbral": c["threshold"],
                            "estado": STATUS_LABEL[c["status"]]} for c in seq.criteria]),
             hide_index=True, width="stretch")
for n in seq.notes:
    st.markdown(f'<div class="sc-note">{n}</div>', unsafe_allow_html=True)

with st.expander("Limitaciones científicas"):
    st.markdown(
        "- **Comparación definida:** brillo superficial (IMAGE − ZODI, MJy/sr) del mismo detector y canal LVF "
        "efectivo, en los píxeles válidos. No es fotometría de fuentes ni detección automática de movimiento.\n"
        "- La λ por píxel procede de la tabla WCS-WAVE (precisión de visualización, ~1 nm).\n"
        "- Las diferencias entre épocas pueden deberse a ruido, fondo, PSF, persistencia, rayos cósmicos o Δλ "
        "residual; no implican por sí solas variabilidad ni movimiento astronómico.\n"
        "- **Geometría:** el reproductor dibuja por defecto los píxeles nativos en su posición WCS, sin remuestreo. "
        "Las métricas (máscaras, cobertura, S1–S9) usan la rejilla de la época 1 con vecino más próximo: "
        "decide qué píxel se compara (hasta ½ píxel por eje, ≈4″), nunca altera los valores.\n"
        "- **HALO:** excluido siempre de las métricas; el modo exploratorio solo lo muestra, marcado en cobre.\n"
        "- **Campo de visión:** campos mayores exigen que la región completa caiga dentro del detector en cada "
        "época, por lo que puede haber menos épocas comparables.\n"
        "- Las coordenadas de catálogo no se propagan por movimiento propio.")
