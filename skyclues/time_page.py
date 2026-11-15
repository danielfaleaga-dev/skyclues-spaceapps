"""Time Explorer page: authentic SPHEREx observations of the active region on different dates.

Presentation and orchestration only. The temporal engine (``sequence``, ``player``, ``motion``,
``quality``) is called exactly as before: same functions, same arguments, same thresholds. The
level (Sencillo / Científico) changes which explanations and tables are shown, never an argument.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from astropy.time import Time

from . import archive, config, motion_page, navigation, player, reference_page, release_ui, render, theme
from .quality import flag_census
from .sequence import STRICT, find_sequence, load_sequence, report_urls, save_report

STATUS_LABEL = {"pass": "✔ cumple", "warn": "▲ aviso", "fail": "✖ no cumple"}
GEOMETRY_OPTIONS = {
    "WCS: píxeles nativos, sin remuestreo de valores": "exact",
    "Rejilla común: vecino más próximo (remuestreado)": "nearest",
}
ALL_DETECTORS = [1, 2, 3, 4, 5, 6]
TABS = ["Secuencia", "Movimiento", "Calidad", "Procedencia"]
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
            label = (f"{p.stem.replace('sequence_', '')} · {len(fr)} épocas · D{fr[0]['detector']} · "
                     f"{fr[0]['lambda_target_um']:.2f} µm · {fr[0]['collection']}")
        else:
            label = (f"{p.stem.replace('pair_', '')} · pareja · D{sel['a']['detector']} · "
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
    report = json.loads(p.read_text(encoding="utf-8"))
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
        return ("NASA/IPAC IRSA no está disponible temporalmente (servidor ocupado, error 5xx o tiempo de espera "
                "agotado tras varios reintentos). No se ha mostrado ningún dato parcial. Pruebe de nuevo en unos "
                "minutos o abra una secuencia verificada.")
    if isinstance(err, archive.ArchivePermanentError):
        return ("IRSA rechazó la solicitud (error permanente, p. ej. HTTP 400/404). Reintentar no lo resolverá: "
                "revise las coordenadas y el campo de visión. No se ha mostrado ningún dato parcial.")
    if isinstance(err, archive.CorruptFitsError):
        return ("Un archivo FITS recibido está incompleto o dañado y se ha descartado (no se usa ni se guarda). "
                "No se ha mostrado ningún dato parcial. Pruebe de nuevo más tarde.")
    return "No se pudo completar el acceso a IRSA. No se ha mostrado ningún dato parcial."


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
    with st.popover("Opciones de búsqueda", help="Qué observaciones se consideran al buscar una secuencia comparable."):
        st.multiselect("Detectores", ALL_DETECTORS, key=theme.bind("dets", DEFAULTS["dets"]), on_change=theme.keep,
                       args=("dets",), help="D1–D3: 0.75–2.41 µm (SWIR) · D4–D6: 2.42–5.0 µm (MWIR)")
        st.slider("Máximo de épocas", 2, 8, key=theme.bind("max_frames", DEFAULTS["max_frames"]),
                  on_change=theme.keep, args=("max_frames",))
        if not opt("dets"):
            st.caption("Elija al menos un detector.")
        st.button("Buscar de nuevo con estas opciones", key="time_research", on_click=_request_search,
                  disabled=not opt("dets"), width="stretch")
        st.caption("Una búsqueda suele tardar de 1 a 2 minutos: los recortes FITS se descargan de IRSA.")


def display_options() -> None:
    with st.popover("Opciones de visualización", help="Cambian cómo se dibujan los fotogramas, nunca las métricas."):
        labels = list(GEOMETRY_OPTIONS)
        current = next(lbl for lbl, v in GEOMETRY_OPTIONS.items() if v == opt("geometry"))
        st.session_state["w_geometry_label"] = current
        st.radio(
            "Geometría de los fotogramas", labels, key="w_geometry_label",
            on_change=lambda: st.session_state.update(opt_geometry=GEOMETRY_OPTIONS[st.session_state["w_geometry_label"]]),
            help="WCS: cada píxel de cada época se dibuja donde lo sitúa su WCS, con su valor original; ningún valor "
                 "se remuestrea (en pantalla las posiciones se redondean al píxel de pantalla). Rejilla común: cada "
                 "época se copia a la rejilla de la época 1 por vecino más próximo (la que usan las métricas); una "
                 "estrella fija puede desplazarse hasta ½ píxel por eje.")
        st.checkbox("Restar el modelo zodiacal (IMAGE − ZODI)", key=theme.bind("subtract", True), on_change=theme.keep,
                    args=("subtract",),
                    help="El fondo zodiacal cambia con la fecha; restarlo evita confundirlo con un cambio del cielo.")
        st.checkbox("Destacar la región común a todas las épocas", key=theme.bind("restrict", False),
                    on_change=theme.keep, args=("restrict",),
                    help="Los píxeles válidos solo en algunas épocas se tiñen de azul claro.")
        st.toggle("Modo exploratorio: mostrar píxeles HALO", key=theme.bind("halo", False), on_change=theme.keep,
                  args=("halo",),
                  help="HALO marca vecinos de píxeles con transitorios (a menudo el desbordamiento de carga de una "
                       "estrella brillante) y de 'snowballs'. La documentación de SPHEREx recomienda precaución al "
                       "usarlos. En este modo se muestran en escala cobre; nunca se cuentan como válidos en las métricas.")
        st.caption("Las métricas y criterios usan siempre la máscara estricta: inutilizables + artefactos (HALO incluido).")


def active_options_note() -> str:
    """Options that differ from the defaults, named so a result is never silently different."""
    names = {"geometry": "rejilla común remuestreada", "subtract": "sin restar el modelo zodiacal",
             "restrict": "región común destacada", "halo": "píxeles HALO visibles"}
    on = [names[k] for k in names if opt(k) != DEFAULTS[k]]
    return "; ".join(on)


# ----------------------------------------------------------------------------- search
def run_search(inp: dict, refresh: bool) -> dict | None:
    dets, max_frames = list(opt("dets")), int(opt("max_frames"))
    fov = inp["fov"]
    sci = theme.scientific()
    box = st.status(f"Buscando observaciones comparables en NASA/IPAC IRSA (campo {fov * 60:.1f}′)…" if sci else 'Buscando imágenes para comparar…', expanded=True)
    stage_text = box.empty()
    stage_text.write("Conectando con el archivo; la primera búsqueda puede tardar varios minutos.")
    stages = {'catalog': 'Consultando las imágenes disponibles…', 'wavelengths': 'Buscando imágenes que se puedan comparar…',
              'download': 'Descargando las imágenes necesarias…', 'evaluate': 'Comprobando las fechas y la calidad…', 'done': 'Imágenes preparadas.'}
    try:
        with theme.loading("Buscando imágenes de esta zona del cielo…", "time_search"):
            _, rep = find_sequence(inp["ra"], inp["dec"], fov, detectors=dets, max_frames=max_frames, log=lambda m: None,
                                   progress=lambda stage, frac, msg: stage_text.write(msg if sci else stages.get(stage, 'Preparando las imágenes…')),
                                   astrometry=inp["astrometry"], **({"refresh": True} if refresh else {}))
    except ValueError as err:
        box.update(label="Entrada no válida", state="error", expanded=True)
        st.error(f"Entrada no válida: {err} No se ha realizado ninguna consulta.")
        return None
    except Exception as err:  # noqa: BLE001 - classified for the user
        box.update(label="La búsqueda no pudo completarse", state="error", expanded=True)
        st.error(irsa_error(err))
        with st.expander("Detalle técnico"):
            st.code(f"{type(err).__name__}: {err}", language=None)
        return None
    box.update(label=f"Búsqueda completada en {rep['elapsed_s']} s", state="complete", expanded=False)
    try:
        t = rep["target"]
        save_report(rep, f"search_{t['ra_deg']:.4f}_{t['dec_deg']:+.4f}_{fov:g}")
    except OSError:
        pass  # read-only deployments: the report stays in the session
    return rep


def pending(inp: dict, sci: bool) -> None:
    """The region has not been searched yet in this session (for instance, opened from a link)."""
    theme.region_strip(inp["label"], inp["ra"], inp["dec"], inp["fov"])
    st.html(('<div class="sc-empty"><b>Aún no se han buscado observaciones de esta región.</b><br>La búsqueda consulta '
            'el archivo NASA/IPAC IRSA y descarga los recortes FITS necesarios: suele tardar de 1 a 2 minutos. '
            'Puede seguir navegando mientras tanto.</div>') if sci else
            '<div class="sc-empty">Busca imágenes de esta zona tomadas en distintas fechas. Puede tardar unos minutos.</div>')
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button("Buscar observaciones", type="primary", key="time_search", on_click=_request_search,
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
        st.caption("Fuente seleccionada en Gaia DR3 (ICRS, J2016.0). Las posiciones para las fechas SPHEREx son cálculos, no detecciones." if sci else 'Fuente de catálogo; no confirma una detección SPHEREx.')
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
        report = json.loads(pinned.read_text(encoding="utf-8"))
        origin = pinned.stem
    else:
        reports = state.setdefault("time_reports", {})
        key = search_key(inp)
        report = reports.get(key)
        origin = "búsqueda de Time Explorer"
        if report is None or refresh:
            if not (autorun or refresh):
                pending(inp, sci)
                _footer(inp["ra"], inp["dec"], inp["fov"], refs, sci)
                return
            theme.region_strip(inp["label"], inp["ra"], inp["dec"], inp["fov"])
            new = run_search(inp, refresh)
            if new is None:
                st.button("Reintentar", key="time_retry", on_click=_request_search)
                return
            report = reports[key] = new
            st.rerun()

    retrieval = report.get("retrieval") or {}
    n_failed = retrieval.get("n_failed", len(report.get("retrieval_failures") or []))

    if not report.get("selected"):
        theme.region_strip(inp["label"], inp["ra"], inp["dec"], inp["fov"])
        _download_warning(report, retrieval, n_failed)
        st.warning(f"No se encontró una secuencia admisible ({report.get('n_records', 0)} imágenes, "
                   f"{report.get('n_candidates', 0)} con el campo completo). Pruebe un campo menor u otros detectores.")
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
            return
        box.update(label="Recortes FITS obtenidos", state="complete", expanded=False)

    with theme.loading("Verificando la integridad de los FITS y alineando épocas…" if sci else "Preparando las imágenes…", "time_sequence"):
        try:
            seq = cached_sequence(report_json)
        except (ValueError, RuntimeError, OSError) as err:
            st.error(f"No se pudo cargar la secuencia: {err}")
            return
    m = seq.metrics
    # Kept for Spectrum Explorer's reference to the open sequence (centre, field, catalogue astrometry).
    state["shared_region"] = {
        "ra": float(seq.ra), "dec": float(seq.dec), "fov": float(seq.field_deg), "label": origin,
        "astrometry": seq.astrometry.to_dict() if seq.astrometry is not None else None}

    # ---------------------------------------------------------------- summary
    status_cls = "sc-ok" if seq.admissible and not seq.warnings else ("sc-warn" if seq.admissible else "sc-fail")
    status_txt = ("Comparable" if not seq.warnings else "Comparable con avisos") if seq.admissible else "No comparable"
    theme.region_strip(inp["label"], float(seq.ra), float(seq.dec), float(seq.field_deg), theme.badge(status_txt, status_cls))
    _download_warning(report, retrieval, n_failed)

    centre_rule = (report.get("target", {}).get("centre") or {}).get("rule")
    if seq.target_moves and sci:
        a = seq.astrometry
        p0, p1 = seq.target_position(0), seq.target_position(seq.n - 1)
        theme.note(
            f'<b>Objetivo en movimiento: {a.name}</b> ({a.total_pm_arcsec_yr:.2f}″/año; {a.source}). Posición '
            f'<b>calculada</b> para la época 1: RA {p0[0]:.5f}°, Dec {p0[1]:+.5f}°; para la época {seq.n}: RA '
            f'{p1[0]:.5f}°, Dec {p1[1]:+.5f}°. La cruz del reproductor sigue ese cálculo; no es una detección de '
            'SPHEREx. Centro del campo: ' + (centre_rule or "—") + '.')
    elif seq.target_moves:
        st.caption('La cruz marca una posición calculada, no una detección.')
    elif centre_rule and sci:
        st.caption(f"Centro del campo: {centre_rule}.")

    f0 = seq.frames[0]
    det = f0.detector
    if sci:
        theme.facts([
            ("Épocas", str(seq.n), ""),
            ("Intervalo total", f"{m['span_days']:.1f} d", ""),
            ("λ en el objetivo", f"{f0.lambda_target_um:.3f} µm", f"dispersión {m['lambda_spread_target_bw']:.2f} BW"),
            ("Cobertura común válida", f"{m['coverage_common_valid']:.1%}", ""),
            ("Detector", f"D{det}", f"{config.BANDS_UM[det][0]}–{config.BANDS_UM[det][1]} µm")])
    else:
        theme.facts([
            ("Fechas disponibles", str(seq.n), ""),
            ("De la primera a la última", f"{m['span_days']:.0f} días", "")])
        st.caption({"sc-ok": "Imágenes preparadas para comparar entre fechas.",
                    "sc-warn": "Las fechas se pueden comparar, con avisos: consulte «Calidad» antes de sacar conclusiones.",
                    "sc-fail": "Estas fechas no cumplen los criterios para compararse: consulte «Calidad»."}[status_cls])

    tab_play, tab_move, tab_q, tab_meta = st.tabs(TABS, key="time_tab", on_change="rerun")

    if tab_play.open:
        with tab_play:
            with st.container(horizontal=True, vertical_alignment="center"):
                if sci:
                    display_options()
                    search_options()
                st.toggle("Mejora infrarroja", key=theme.bind("enhance", False), on_change=theme.keep,
                          args=("enhance",),
                          help="Combina varias exposiciones reales de la misma zona para reducir el ruido y "
                               "distinguir fuentes más débiles. No suaviza ni rellena la imagen.")
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
    with theme.loading("Preparando la reproducción…", "time_player"):
        html = cached_player(report_json, bool(opt("subtract")), bool(opt("restrict")), geometry, bool(opt("halo")),
                             simple=not sci, presentation=player.presentation_key())
    components.html(html, height=660, scrolling=True)
    active = active_options_note()
    if active and not sci:
        st.caption('Se conservan tus ajustes de visualización del modo Científico.')
    if sci:
        geo_txt = ("Geometría WCS: cada píxel nativo se dibuja donde lo sitúa su WCS, con su valor original "
                   "(sin remuestreo de valores); la rotación entre visitas se ve como píxeles inclinados. En "
                   f"pantalla, 1 píxel ≈ {player.screen_scale_arcsec(seq):.1f}″." if geometry == "exact" else
                   "Producto REMUESTREADO: cada época se copia a la rejilla de la época 1 por vecino más "
                   "próximo (desplazamiento de hasta ½ píxel por eje).")
        st.caption("Cada fotograma es una exposición SPHEREx real (sin fotogramas intermedios ni interpolación "
                   f"temporal), con la misma escala de intensidad. {geo_txt} El tamaño en pantalla es fijo: un "
                   "campo de visión mayor muestra más cielo, no es un zoom. Una diferencia visual no es por sí "
                   "sola una detección de movimiento o variabilidad.")
    else:
        st.markdown('Reproduce las fechas o usa **Blink** para alternar dos imágenes. Para comprobar un posible movimiento, abre «Movimiento».')


def _download_warning(report, retrieval, n_failed) -> None:
    if not n_failed:
        return
    kinds = {f.get("kind", "desconocido") for f in report.get("retrieval_failures") or []}
    st.warning(f"Descarga incompleta: {n_failed} de {retrieval.get('n_requested', '?')} recortes FITS no se pudieron "
               f"obtener de IRSA ({', '.join(sorted(kinds))}). La selección se hizo sin ellos, así que podría existir "
               "una secuencia mejor; repita la búsqueda más tarde para completarla.")
    with st.expander("Recortes no obtenidos"):
        st.dataframe(pd.DataFrame(report.get("retrieval_failures") or []).astype(str), hide_index=True)


def _quality(seq, m, sci: bool) -> None:
    if not sci:
        st.markdown('### Calidad de las imágenes')
        st.markdown('Estas fechas se pueden comparar entre sí.' if seq.admissible and not seq.warnings else
                    'Hay limitaciones al comparar estas fechas. Consulta el modo Científico para conocer los motivos.')
        theme.facts([('Zona comparable', f"{m['coverage_common_valid']:.0%}", 'con datos en todas las fechas')])
        return
    st.markdown("### Criterios de comparabilidad")
    st.caption("Se evalúan todas las épocas a la vez, siempre con la máscara estricta. Son los mismos en los dos niveles.")
    st.dataframe(pd.DataFrame([{"": c["id"], "criterio": c["criterion"], "valor": c["value"], "umbral": c["threshold"],
                                "estado": STATUS_LABEL[c["status"]], "verificación": c.get("basis", "efectiva")}
                               for c in seq.criteria]),
                 hide_index=True, width="stretch")
    if sci:
        st.caption("«verificación»: *efectiva* = calculada aquí con los datos; *garantía del archivo* = IRSA solo publica "
                   "imágenes con L2DQA = PASS y FINAST = 0 (Explanatory Supplement §3.2.12), así que el criterio se "
                   "comprueba en la cabecera pero no puede discriminar entre productos del archivo.")
    for n in seq.notes:
        theme.note(n)

    def tables():
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
        q = pd.DataFrame([{"época": i + 1, "fecha (UTC)": f.date_utc[:16], **{
            "L2 DQA": f.quality["L2DQAFLG"], "FINAST": f.quality["FINAST"],
            "válido en campo (%)": round(100 * f.quality["valid_fraction_in_field"], 1),
            "solo HALO (%)": round(100 * f.quality.get("halo_only_fraction_in_field", float("nan")), 2),
            "saturación (%)": round(100 * f.quality["saturation_fraction_in_field"], 3),
            "ZODI (MJy/sr)": round(f.quality["zodi_median_mjysr"], 3),
            "PSF FWHM (″)": round(float(f.quality["psf_fwhm_arcsec"] or float("nan")), 2),
            "desplaz. máx. rejilla común (px)": round(float(seq.placement_error_px(i)[seq.field_mask].max()), 2)}}
            for i, f in enumerate(seq.frames)])
        st.markdown("#### Calidad por época")
        st.dataframe(q, hide_index=True, width="stretch")
        st.caption("«solo HALO»: píxeles del campo enmascarados únicamente por HALO (visibles en el modo exploratorio). "
                   "«desplaz. máx.»: distancia máxima entre un píxel de la rejilla común y el píxel nativo que el vecino "
                   "más próximo copia allí (0 en la época de referencia).")
        k = st.selectbox("FLAGS de la época", list(range(1, seq.n + 1)), key="time_flags_epoch",
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

    if sci:
        st.markdown("### Cobertura y longitud de onda")
        tables()
    else:
        with st.expander("Cobertura, longitud de onda y calidad de cada fecha"):
            tables()
    with st.expander("Limitaciones científicas"):
        st.markdown(
            "- **Comparación definida:** brillo superficial (IMAGE − ZODI, MJy/sr) del mismo detector y canal LVF "
            "efectivo, en los píxeles válidos. No es fotometría de fuentes ni detección automática de movimiento.\n"
            "- La λ por píxel procede de la tabla WCS-WAVE (precisión de visualización, ~1 nm).\n"
            "- Las diferencias entre épocas pueden deberse a ruido, fondo, PSF, persistencia, rayos cósmicos o Δλ "
            "residual; no implican por sí solas variabilidad ni movimiento astronómico.\n"
            "- **Geometría:** el reproductor dibuja por defecto los píxeles nativos en su posición WCS, sin remuestreo "
            "de valores; la precisión visible la limita el píxel de pantalla (indicado en cada fotograma), no el WCS. "
            "Las métricas (máscaras, cobertura, S1–S9) usan la rejilla de la época 1 con vecino más próximo: "
            "decide qué píxel se compara (hasta ½ píxel por eje, ≈4″), nunca altera los valores.\n"
            "- **HALO:** excluido siempre de las métricas; el modo exploratorio solo lo muestra, marcado en cobre.\n"
            "- **Campo de visión:** campos mayores exigen que la región completa caiga dentro del detector en cada "
            "época, por lo que puede haber menos épocas comparables.\n"
            "- **Objetivos en movimiento:** la posición se calcula para cada fecha con Astropy a partir de la astrometría "
            "de SIMBAD (época del catálogo, movimiento propio, paralaje y velocidad radial cuando existen); sin "
            "movimiento propio en el catálogo, la posición es la misma en todas las fechas. Una posición calculada no "
            "es una detección. Las coordenadas introducidas a mano se usan tal cual para todas las fechas.")


def _provenance(seq, report: dict, is_saved: bool, sci: bool) -> None:
    if sci:
        release_ui.discovery(report)
    with st.container(horizontal=True, vertical_alignment="center"):
        if is_saved:
            st.button("Actualizar observaciones", key="refresh_saved", on_click=_refresh_saved,
                      help="Consulta de nuevo el archivo (SIA2) para esta región y repite la búsqueda.")
        else:
            st.button("Actualizar observaciones", key="refresh_observations", on_click=_request_search,
                      kwargs={"refresh": True}, disabled=not opt("dets"),
                      help="Consulta de nuevo el archivo (SIA2) para esta región y repite la búsqueda.")
    rows = []
    for i, f in enumerate(seq.frames):
        s = f.summary()
        tp = seq.target_position(i)
        rows.append({"época": i + 1, "fecha media (UTC)": s["date_utc"], "MJD": round(s["mjd"], 5),
                     "obs_id": s["obs_id"], "colección": s["collection"], "detector": s["detector"],
                     "objetivo calculado (RA, Dec °)": f"{tp[0]:.5f}, {tp[1]:+.5f}",
                     "λ objetivo (µm)": round(s["lambda_target_um"], 4),
                     "ancho de banda (µm)": round(s["bandwidth_target_um"], 4),
                     "exposición (s)": s["exptime_s"], "software": s["software_version"],
                     "archivo": s["file_name"], "SHA-256": s["sha256"][:16] + "…"})
    df = pd.DataFrame(rows).astype(str)
    st.markdown("### Observaciones de esta secuencia")
    simple_cols = ["época", "fecha media (UTC)"]
    st.dataframe(df if sci else df[simple_cols], hide_index=True, width="stretch")
    if not sci:
        st.caption('Imágenes reales de SPHEREx, disponibles en NASA/IPAC IRSA.')
        return
    st.caption("Fuente: NASA/IPAC Infrared Science Archive. SPHEREx DR1 Spectral Images, doi:10.26131/IRSA678; "
               "SPHEREx QR3. Integridad: SHA-256 de cada FITS comprobado frente al informe.")
    with st.expander("Recortes IRSA (reproducibles)", expanded=sci):
        st.code("\n".join(f"{i + 1}: {f.cutout_url}" for i, f in enumerate(seq.frames)), language=None)
    with st.expander("Opciones evaluadas al elegir la secuencia"):
        if report.get("options"):
            st.caption("Regla de selección: " + report.get("selection_rule", ""))
            optdf = pd.DataFrame(report["options"])
            optdf["cobertura"] = (optdf["coverage_common_valid"] * 100).round(1)
            st.dataframe(optdf[["origin", "detector", "n_frames", "cobertura", "lambda_spread_common_max_bw",
                                "span_days", "admissible", "dates"]].astype(str), hide_index=True, width="stretch")
            for r in report.get("rejected_larger_options", []):
                st.markdown(f"- Opción de **{r['n_frames']} épocas** (D{r.get('detector', '?')}, cobertura "
                            f"{r['coverage']:.1%}) descartada: {'; '.join(r['reasons'])}")
        else:
            st.caption("Resultado de pareja (sin exploración de secuencias).")
    obs = report.get("observations", [])
    if obs:
        with st.expander(f"Observaciones disponibles en el archivo ({len(obs)})"):
            odf = pd.DataFrame(obs)
            odf["fecha (UTC)"] = pd.Series(Time(odf["mjd_mid"].to_numpy(), format="mjd").isot).str.slice(0, 16)
            cols_obs = [c for c in ["fecha (UTC)", "collection", "detector", "obs_id", "lambda_est_um",
                                    "bandwidth_est_um", "exptime_s", "field_margin_px", "file_name"] if c in odf]
            st.caption(f"{len(odf)} imágenes con el campo completo dentro del detector (de {report.get('n_records')} "
                       "que contienen el objetivo). λ estimada desde metadatos; la decisión final usa el FITS.")
            st.dataframe(odf.sort_values("mjd_mid")[cols_obs].round(4), hide_index=True, width="stretch")


def _footer(ra: float, dec: float, fov: float, refs: dict[str, str], sci: bool) -> None:
    """Context tools that belong to the region, after the science: references, link, saved results."""
    st.html('<div style="height:.6rem"></div>')
    if sci:
        reference_page.render(ra, dec, fov, key="time_ref")
    release_ui.share(ra, dec, fov)
    if sci and refs:
        with st.expander("Resultados guardados"):
            st.selectbox("Abrir un resultado guardado (results/)", list(refs), index=None, key="time_saved",
                         placeholder="Elegir un resultado…", on_change=_open_saved_from_select, args=(refs,))
            st.caption("Abre la región del resultado con su centro y campo exactos, sin repetir la búsqueda.")
    st.caption("Datos: NASA/IPAC IRSA · SPHEREx DR1 y QR3 (SIA2). Cada fotograma es una observación real; la escala de "
               "intensidad es solo de visualización." if sci else 'Datos: SPHEREx · NASA/IPAC IRSA.')
