"""Spectrum Explorer: the second position (B), the comparison and the peaks and valleys.

Everything here attaches to the one image and the one spectrum plot of the page; there is no
comparison mode, page or panel. Presentation only: every number comes from
``spectral_features`` and is the same in both levels (Sencillo / Científico).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import streamlit as st

from . import config, theme
from . import spectral_features as sf
from . import spectral_view as sv

POINTS = ["Punto A", "Punto B"]
DERIVED = {"Diferencia A − B": "diferencia", "Relación A / B": "relacion"}
B_KEY, INSPECT_KEY, CHART_KEY = "sx_b", "sx_inspect", "sx_spectrum_chart"
RANK = {sf.QUANTIFIABLE: 3, sf.VISIBLE: 2, sf.NO_FEATURE: 1, sf.NOT_EVALUABLE: 0}
BADGE = {sf.QUANTIFIABLE: "ok", sf.VISIBLE: "warn", sf.NOT_EVALUABLE: "", sf.NO_FEATURE: ""}


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
    has_b = point_b(region_key) is not None
    left, right = st.columns([3, 2], vertical_alignment="bottom")
    with left:
        st.segmented_control(
            "El clic en la imagen coloca" if sci else "Al pulsar la imagen eliges", POINTS, required=True,
            key=theme.bind("sx_active", POINTS[0]), on_change=theme.keep, args=("sx_active",),
            help="A es la posición del espectro. B es un segundo punto: su espectro se dibuja sobre los mismos ejes, "
                 "extraído exactamente igual que el de A.")
    if has_b:
        right.button("Quitar el punto B", key="sx_b_remove", on_click=_remove_b,
                     help="Vuelve a trabajar con una sola posición. No cambia el punto A ni su espectro.")
        st.caption("A: rombo azul · B: cuadrado naranja, con los colores de sus espectros. Línea continua: apertura; "
                   "discontinua: anillo de fondo (los mismos radios en ambos)." if sci else
                   "A: rombo azul · B: cuadrado naranja, con los mismos colores que sus curvas.")
    elif st.session_state.get("opt_sx_active") == POINTS[1]:
        st.caption("Pulsa la imagen para colocar el punto B y comparar su espectro con el de A.")


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
        return "no se puede valorar: faltan datos en ese color o a su alrededor."
    if f.klass == sf.NO_FEATURE or f.kind is None:
        return "no destaca sobre los colores vecinos."
    up = f.kind == "pico"
    size = (f"un {abs(f.relative):.0%}" if f.relative is not None and abs(f.relative) < 10
            else f"{abs(f.contrast):.3g} {f.unit}")
    text = f"{'pico' if up else 'valle'}: {size} {'más brillante' if up else 'más débil'} que los colores vecinos"
    return text + (". Se distingue con claridad." if f.klass == sf.QUANTIFIABLE else
                   ". Es una variación leve o con datos dudosos.")


def _where(f: sf.Feature) -> str:
    if f.lam is None:
        return f"canales {f.trial_lo}–{f.trial_hi}" if f.trial_lo != f.trial_hi else f"canal {f.trial_lo}"
    ch = f"canal {f.canal_lo}" if f.canal_lo == f.canal_hi else f"canales {f.canal_lo}–{f.canal_hi}"
    return f"{f.lam:.3f} µm ({ch})"


def _science_rows(fs: dict) -> pd.DataFrame:
    def col(f: sf.Feature) -> list:
        if f.contrast is None:
            return [f.label, "—", "—", "—", f"{f.trial_lo}–{f.trial_hi}", "—", "—", "—", "—", "—", "—", "—", "—", "—"]
        refs = " · ".join(f"{n} {_num(v)}" for n, v in (("entorno", f.ref_local), ("detector", f.ref_detector),
                                                         ("fondo", f.ref_background)) if v is not None)
        return [f.label, f"{f.kind} · {f.width}" if f.kind else "—", f"{f.lam:.3f} (centroide {f.lam_centroid:.3f})",
                f"{f.lam_lo:.3f}–{f.lam_hi:.3f} ({f.width_um:.3f})",
                f"{f.canal_lo}–{f.canal_hi} de {f.trial_lo}–{f.trial_hi}", _num(f.value, f.unit),
                _num(f.continuum, f.unit), _num(f.contrast, f.unit, signed=True),
                "—" if f.relative is None else f"{f.relative:+.1%}",
                "> 1000" if abs(f.ratio) > 1000 else f"{abs(f.ratio):.1f}", f"{_num(f.ref, f.unit)} ({refs})",
                f"{f.env_left[0]}–{f.env_left[-1]} y {f.env_right[0]}–{f.env_right[-1]}",
                ", ".join(f"D{d}" for d in f.detectors),
                "—" if f.nhits_feature is None else f"{f.nhits_feature:.0f} / {f.nhits_env:.0f}"]
    names = ["Clase", "Tipo", "λ central (µm)", "Intervalo a media altura (µm)", "Canales (media altura de excluidos)",
             "Valor en el extremo", "Continuo local", "Contraste", "Contraste relativo",
             "Contraste / dispersión de referencia", "Dispersión de referencia", "Canales del entorno", "Detectores",
             "NHITS característica / entorno"]
    return pd.DataFrame({"Magnitud": names, **{f"Espectro {k}": col(f) for k, f in fs.items()}})


def _feature_list(fs: list) -> str:
    return ", ".join(f"{f.kind} en {f.lam:.2f} µm" for f in fs)


# ----------------------------------------------------------------------------- page section
def render(spec_a, quantity: str, channel_number: int, sci: bool, region_key, extract, show_error) -> None:
    """The spectrum plot and what attaches to it. ``extract(ra, dec)`` returns the spectrum of another
    position with the SAME aperture and annulus as ``spec_a`` (nothing is tuned per position)."""
    state = st.session_state
    unit = sf.UNITS[quantity]
    spec_b, b_pos = None, point_b(region_key)
    if b_pos is not None:
        try:
            with theme.loading("Leyendo los 102 canales alrededor del punto B…" if sci else
                               "Preparando el espectro del punto B…", "spectrum_b"):
                spec_b = extract(*b_pos)
        except Exception as err:  # noqa: BLE001
            show_error(err, "No se pudo obtener el espectro del punto B")
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
        focus = (float(sa.lam_min[sa.index(ref.trial_lo)]), float(sa.lam_max[sa.index(ref.trial_hi)]))

    st.altair_chart(sv.spectrum_chart(spec_a, quantity, selected_channel=channel_number, other=spec_b,
                                      features=fa + fb, focus=focus, interactive=True),
                    width="stretch", key=CHART_KEY, on_select=_on_select, selection_mode=["canal", "intervalo"])

    # ------------------------------------------------------------ A and B
    if sb is not None:
        cmp = sf.compare(sa, sb)
        for issue in cmp.issues:
            st.warning(f"A y B no se restan ni se dividen: {issue}")
        if cmp.comparable:
            label = st.segmented_control("Comparación canal a canal", list(DERIVED), required=True,
                                         key=theme.bind("sx_derived", next(iter(DERIVED))), on_change=theme.keep,
                                         args=("sx_derived",), label_visibility="collapsed")
            kind = DERIVED[label]
            st.altair_chart(sv.derived_chart(cmp.rows, kind, unit, focus=focus, selected_channel=channel_number),
                            width="stretch", key="sx_derived_chart")
            _comparison_text(cmp, spec_a, spec_b, kind, sci)
    elif not sci:
        st.caption("Para comparar con otro punto, elige «Punto B» junto a la imagen y púlsala.")

    # ------------------------------------------------------------ the selected channel or interval
    if found:
        head = st.columns([5, 1], vertical_alignment="center")
        with head[0]:
            theme.eyebrow(("Característica examinada · " if sci else "Lo que has señalado · ") + _where(
                max(found.values(), key=lambda f: (RANK[f.klass], abs(f.ratio or 0.0)))))
        head[1].button("Quitar", key="sx_inspect_clear", on_click=_clear_inspection,
                       help="Deja de examinar este intervalo. El espectro no cambia.")
        if sci:
            st.html("".join(f'<p style="margin:.1rem 0">Espectro {k}: {theme.badge(f.label, BADGE[f.klass])} '
                            f'<span class="sc-muted">{sf.CLASS_MEANING[f.klass]}.</span></p>' for k, f in found.items()))
            st.dataframe(_science_rows(found), hide_index=True, width="stretch")
            for k, f in found.items():
                notes = f.reasons + f.limitations
                if notes:
                    st.markdown(f"**{k}** · " + " ".join(notes))
            st.caption("Contraste = valor original − continuo local (polinomio de grado 2 por los tres canales válidos "
                       "de cada lado, sin la característica). La dispersión de referencia es un umbral descriptivo: "
                       "no es una incertidumbre del flujo ni una significación estadística.")
        else:
            for k, f in found.items():
                st.markdown(f"**{k}** — {_plain(f)}")
            st.caption("Un pico o un valle no identifica por sí solo un material.")
    else:
        st.caption("Pulsa un punto del gráfico, o arrastra sobre un intervalo, para examinar ese pico o valle." if not sci
                   else "Pulse un punto del gráfico o arrastre sobre un intervalo de longitudes de onda para "
                        "caracterizarlo respecto a su entorno. Doble clic deshace la selección.")

    # ------------------------------------------------------------ what the scan marked
    marked = [(s, f) for s, f in ((sa, fa), (sb, fb)) if s is not None]
    if any(f for _, f in marked):
        if sci:
            parts = [f"{s.label}: {sum(x.klass == sf.QUANTIFIABLE for x in f)} cuantificables y "
                     f"{sum(x.klass == sf.VISIBLE for x in f)} visibles" for s, f in marked]
            st.caption("Marcas del gráfico (▼ pico, ▲ valle; relleno = cuantificable, hueco = visible). " +
                       " · ".join(parts) + ". Ninguna es una detección: el cubo no tiene incertidumbres.")
        else:
            st.markdown("Señalado en el gráfico (▼ pico, ▲ valle): " + " · ".join(
                f"**{s.label}**: {_feature_list(f) or 'nada destacable'}" for s, f in marked) + ".")
    elif sci:
        st.caption("El método no señala ningún pico ni valle en este espectro por encima de sus criterios.")
    if sci:
        with st.expander("Picos y valles: tabla, método y criterios"):
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
                f"- **Continuo local:** polinomio de grado {m['grado_del_continuo']} ajustado a los "
                f"{m['canales_entorno_por_lado']} canales con valor a cada lado del intervalo, contiguos a él; la "
                "característica y las ya señaladas quedan fuera del ajuste. Se ajusta ln(valor) frente a ln(λ) si el "
                "entorno es positivo. Junto a un canal sin datos o en el borde del intervalo espectral no hay "
                "continuo: la característica es *no evaluable*.\n"
                "- **Sin suavizado.** Las marcas se calculan con los valores originales; nada se interpola.\n"
                f"- **Criterios:** contraste ≥ {m['umbral_visible']:g} veces la dispersión de referencia para "
                f"*visible* y ≥ {m['umbral_cuantificable']:g} para *cuantificable*, que además exige un solo detector, "
                "ningún OVERFLOW/OUTLIER y cobertura (NHITS) estable. Por debajo del "
                f"{m['contraste_relativo_minimo']:.0%} del continuo no se señala nada.\n"
                "- **Dispersión de referencia:** la mayor entre la del entorno, la robusta del detector y la del anillo "
                "de fondo propagada a la apertura. Es un umbral descriptivo, no un error fotométrico.\n"
                f"- **Oscilaciones no señaladas** (máximos y mínimos locales por debajo de los criterios): {small}.\n"
                "- **Qué no es:** ni una detección ni una identificación. Un pico cerca de una banda conocida no "
                f"demuestra esa banda. Método: {m['metodo']}.")


def _comparison_text(cmp: sf.Comparison, spec_a, spec_b, kind: str, sci: bool) -> None:
    s, unit = cmp.summary, cmp.unit
    if not s["n_ambos"]:
        st.warning("A y B no tienen ningún canal con valor en común: no hay nada que comparar.")
        return
    more = round(s["fraccion_a_mayor"] * s["n_ambos"])
    sep = "" if cmp.separation_arcsec is None else f"{cmp.separation_arcsec:.0f}″"
    close = [n for n in cmp.notes if "solapan" in n or "anillo de fondo de la otra" in n or "misma posición" in n]
    if not sci:
        text = f"A es más brillante que B en **{more} de {s['n_ambos']}** colores infrarrojos con dato en ambos."
        if s.get("n_relacion", 0) >= sf.MIN_RESIDUALS:
            text += (f" En conjunto, A brilla unas **{s['relacion_mediana']:.2g} veces** lo que B, y esa proporción "
                     f"cambia alrededor de un {s['relacion_dispersion'] / s['relacion_mediana']:.0%} según el color.")
        st.markdown(text)
        if close:
            st.warning("Los dos puntos están muy cerca: sus medidas se mezclan y la comparación es menos fiable.")
        st.caption("Una diferencia entre dos puntos no indica por sí sola materiales distintos.")
        return
    ap = spec_a.aperture
    st.caption(
        f"A: RA {spec_a.ra:.5f}°, Dec {spec_a.dec:+.5f}° · B: RA {spec_b.ra:.5f}°, Dec {spec_b.dec:+.5f}° · separación "
        f"{sep}. Misma extracción en ambos: apertura {ap.r_ap:g} px, anillo {ap.r_in:g}–{ap.r_out:g} px, "
        f"{spec_a.subpixels}×{spec_a.subpixels} submuestras, unidad {unit}. Canales con valor en ambos: {s['n_ambos']} "
        f"de {s['n_canales']} (solo A {s['n_solo_a']}, solo B {s['n_solo_b']}, ninguno {s['n_ninguno']}).")
    facts = [("A − B, mediana", f"{s['diferencia_mediana']:+.4g} {unit}",
              f"de {s['diferencia_min']:+.3g} a {s['diferencia_max']:+.3g}"),
             ("A > B", f"{more} de {s['n_ambos']}", "canales con valor en ambos")]
    if s.get("n_relacion"):
        facts.append(("A / B, mediana", f"{s['relacion_mediana']:.3g}",
                      f"dispersión robusta {s['relacion_dispersion']:.2g} · {s['n_relacion']} canales válidos"))
    theme.facts(facts)
    for n in cmp.notes:
        st.caption("Aviso: " + n)
    away = s.get("canales_apartados") or []
    if away:
        st.caption("Canales donde A/B se aparta más de su mediana (descriptivo): " + ", ".join(
            f"{c['canal']} ({c['lambda_um']:.3f} µm, A/B {c['relacion']:.3g})" for c in away) + ".")
    st.caption("A/B solo se calcula donde A > 0, B > 0 y B supera "
               f"{sf.RATIO_MIN_DENOMINATOR:g} veces la dispersión del fondo propagada a la apertura; en el resto se "
               "marca en gris sobre el eje con su motivo. Una diferencia o una relación distinta de 1 no implica una "
               "composición distinta: también la producen la extinción, el fondo local y la mezcla de fuentes.")
    with st.expander("Tabla de la comparación (valores por canal)"):
        df = cmp.table()[["canal", "lambda_um", "lambda_min_um", "lambda_max_um", "detector", "a", "b", "estado_a",
                          "estado_b", "diferencia", "relacion", "estado_relacion", "precaucion"]]
        st.dataframe(df, hide_index=True, width="stretch")
        meta = {"producto": "SPHEREx DR1 All-Sky spectral cube", "doi": config.CUBE_DOI,
                "metodo": "comparación de dos espectros exploratorios extraídos igual; solo visualización",
                "magnitud": sf.QUANTITY_NAMES[cmp.quantity], "unidad": unit,
                "a": {"ra_deg": spec_a.ra, "dec_deg": spec_a.dec}, "b": {"ra_deg": spec_b.ra, "dec_deg": spec_b.dec},
                "separacion_arcsec": cmp.separation_arcsec, "apertura_px": ap.r_ap, "anillo_px": [ap.r_in, ap.r_out],
                "submuestras": spec_a.subpixels, "pixel_sr": spec_a.pixel_solid_angle_sr, "avisos": cmp.notes,
                "criterios": sf.method_summary(), "teselas": sorted({str(t.get("tile")) for t in
                                                                     spec_a.tiles + spec_b.tiles})}
        csv = "".join(f"# {k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in meta.items()) + df.to_csv(index=False)
        st.download_button("Descargar CSV de la comparación", csv.encode("utf-8"), mime="text/csv",
                           file_name=f"skyclues_comparacion_{spec_a.ra:.4f}_{spec_a.dec:+.4f}__"
                                     f"{spec_b.ra:.4f}_{spec_b.dec:+.4f}.csv", key="sx_cmp_csv")
