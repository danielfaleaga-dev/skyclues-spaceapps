"""Spectrum Explorer: «¿Qué podría indicar este espectro?» (presentation of the spectral interpreter V1).

Presentation only. Every verdict, hypothesis and limitation comes from ``spectral_interpreter`` (engine) and
``spectral_references`` (registry) and is the same in both levels: Sencillo says it in everyday words, Científico
adds wavelengths, redshift and its source, resolution and detector, quality, alternatives and bibliography.
A and B are always interpreted separately: a difference between them is never an identification.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from . import spectral_features as sf
from . import spectral_interpreter as si
from . import spectral_references as sr
from . import theme

REFS_OPTION = "sx_refs"            # show the reference marks on the plot (persistent option, off by default)
SECTION_KEY = "sx_interp"


# ----------------------------------------------------------------------------- what is interpreted
@dataclass
class Context:
    series: dict                                     # {"A": Series, "B": Series}
    redshifts: dict                                  # {"A": Redshift, ...}
    selected: dict = field(default_factory=dict)     # the examined interval: {"A": Interpretation, ...}
    overview: dict = field(default_factory=dict)     # every labelled feature: {"A": [Interpretation], ...}
    surveys: dict = field(default_factory=dict)      # {"A": [Coverage], ...}


def build(specs: dict, pairs: list, quals: dict, found: dict | None) -> Context:
    """Interpretations for the spectra on the page. ``specs`` = {"A": Spectrum, ...}; ``pairs`` = [(Series,
    Analysis)] as the analysis section has them; ``found`` = the examined interval measured in each spectrum."""
    ctx = Context(series={s.label: s for s, _ in pairs}, redshifts={})
    for s, an in pairs:
        spec = specs[s.label]
        rs = sr.redshift_at(spec.ra, spec.dec)
        ctx.redshifts[s.label] = rs
        kw = dict(redshift=rs, resolution=si.resolution_of(spec), qualities=quals.get(s.label),
                  aperture_arcsec=spec.aperture.r_ap * spec.pixel_scale_arcsec)
        ctx.overview[s.label] = si.interpret_features(s, an.features, **kw)
        ctx.surveys[s.label] = si.survey(s, an.features, an.scatter, redshift=rs)
        if found and s.label in found:
            ctx.selected[s.label] = si.interpret(s, found[s.label], **kw)
    return ctx


def chart_marks(ctx: Context) -> list[dict] | None:
    """Reference positions for the plot (A's redshift), or None while the marks are switched off."""
    if not theme.persistent(REFS_OPTION, False):
        return None
    rs = ctx.redshifts.get("A", sr.UNKNOWN_Z)
    lit = {m.reference.id for it in ctx.selected.values() for m in it.matches}
    marks = [{"lambda_um": r.lam_um * (1 + (rs.z or 0.0)), "nombre": r.name, "naturaleza": sr.NATURE_TEXT[r.nature],
              "nota": (f"desplazada con z = {rs.z:.6f} ({rs.object_name})" if rs.known else
                       "en reposo: z desconocido"), "destacada": r.id in lit, "etiqueta": ""} for r in sr.REFERENCES]
    shown = [m for m, r in zip(marks, sr.REFERENCES) if r.id in lit]
    if shown:                                       # one short label for the compatible group, never one per mark
        shown[0]["etiqueta"] = " · ".join(r.short for r in sr.REFERENCES if r.id in lit)
    return marks


# ----------------------------------------------------------------------------- wording (pure, same facts)
def _um(v: float, digits: int = 1) -> str:
    return f"{v:.{digits}f}".replace(".", ",") + " µm"


def observed_text(it: si.Interpretation) -> str:
    f = it.feature
    if "sin_caracteristica" in it.codes:
        return "Aquí no destaca ningún pico ni valle."
    if f is None or f.lam is None or "no_evaluable" in it.codes:
        return "En esta zona no se puede valorar ningún pico ni valle: faltan datos o el entorno no es fiable."
    if f.kind == "pico":
        return f"Detectamos un exceso de emisión cerca de {_um(f.lam)}."
    return f"Detectamos una disminución de luz (posible absorción) cerca de {_um(f.lam)}."


def meaning_text(it: si.Interpretation) -> str:
    ms = it.matches
    if ms:
        first = ms[0].reference
        if it.verdict == si.NOT_EVALUABLE:
            return f"Cae donde se esperaría {first.plain_name}, pero estos datos no permiten interpretarlo."
        text = f"Podría relacionarse con {first.plain_name}"
        if len(ms) > 1:
            kind = "emisiones" if first.nature == sr.EMISSION else "absorciones"
            text += f", aunque otras {kind} cercanas, como la del {ms[1].reference.plain_name}, también pueden contribuir"
        if it.verdict == si.WEAK:
            text += ", pero esta vista no basta para sostenerlo"
        return text + "."
    if it.verdict == si.NONE:
        opposite = [m for m in it.others if m.status == si.OPPOSITE]
        extra = (f" En esa posición, el {opposite[0].reference.plain_name} se vería como una disminución de luz, no "
                 "como un exceso." if opposite and opposite[0].reference.nature == sr.ABSORPTION else "")
        return (f"No coincide con ninguna de las {len(sr.REFERENCES)} referencias que SkyClues compara; eso no descarta "
                "otras sustancias." + extra)
    return "SkyClues no puede interpretarlo."


def why_text(it: si.Interpretation) -> str | None:
    if not it.matches:
        return None
    ref, rs = it.matches[0].reference, it.redshift
    where = ("su posición coincide con la que tendría esa luz, una vez corregida la velocidad a la que se aleja la "
             f"galaxia {rs.object_name}" if rs.known else "su posición coincide con la que tiene esa luz")
    return f"{where[0].upper()}{where[1:]}. {ref.plain}"


PLAIN_LIMITS = {
    "visible": "La señal es leve.",
    "precaucion": "Parte de la luz pudo saturarse en esta zona.",
    "entorno": "Parte de la luz pudo saturarse junto a esta zona.",
    "bloom": "La luz de una fuente brillante pudo desbordarse sobre esta zona.",
    "detectores": "Coincide con el paso entre dos detectores, que puede crear picos y valles falsos.",
    "varias": "SPHEREx no separa colores tan próximos.",
    "hielo": "Para hablar de hielo hay que medir la banda completa y que haya una fuente de luz detrás; esta vista "
             "no lo hace.",
    "z_desconocido": "No sabemos si esta luz viene de una galaxia lejana que se aleja: se compara como si estuviera en "
                     "reposo.",
    "no_evaluable": "Faltan datos en esa zona o a su alrededor.",
    "sin_caracteristica": "Que no se vea nada no demuestra que falte una sustancia.",
}


def limits_text(it: si.Interpretation) -> list[str]:
    out = [PLAIN_LIMITS[c] for c in dict.fromkeys(it.codes) if c in PLAIN_LIMITS]
    if it.matches or it.verdict == si.NONE:
        out.append("Un pico o un valle no basta para identificar un material.")
    return list(dict.fromkeys(out))


def _z_text(rs: sr.Redshift) -> tuple[str, str]:
    if rs.known:
        return f"z = {rs.z:.6f}", f"{rs.object_name} · NED, dentro de su isofota D25 · ±{rs.sigma:.4f}"
    return "desconocido", "se compara en reposo (z = 0); nunca se estima de una coincidencia"


def _match_rows(it: si.Interpretation) -> list[dict]:
    rows = []
    for m in it.matches + it.others + it.orientative:
        r = m.reference
        rows.append({"Referencia": r.name, "Tipo": f"{sr.NATURE_TEXT[r.nature]} · {sr.FORM_TEXT[r.form]}",
                     "λ en reposo (µm)": (f"{r.lam_range_um[0]:.3f}–{r.lam_range_um[1]:.3f}"
                                          if r.lam_range_um[0] != r.lam_range_um[1] else f"{r.lam_um:.4f}"),
                     "λ esperada (µm)": f"{m.lam_obs_um:.4f}",
                     "Canal previsto": " y ".join(map(str, m.predicted_channels)),
                     "Compatibilidad": si.STATUS_LABELS[m.status],
                     "z para la que se mantiene": ("—" if m.z_range is None else
                                                   f"{m.z_range[0]:+.4f} a {m.z_range[1]:+.4f}"),
                     "Motivo": " ".join(m.reasons)})
    return rows


# ----------------------------------------------------------------------------- page section
def render(ctx: Context, sci: bool, inspect_key: str) -> None:
    with st.container(key=SECTION_KEY):
        _render(ctx, sci, inspect_key)


def _render(ctx: Context, sci: bool, inspect_key: str) -> None:
    theme.eyebrow("¿Qué podría indicar este espectro?")
    st.toggle("Mostrar referencias en el gráfico" if sci else "Mostrar en el gráfico dónde caen las referencias",
              key=theme.bind(REFS_OPTION, False), on_change=theme.keep, args=(REFS_OPTION,),
              help="Líneas punteadas en la posición esperada de cada referencia de la biblioteca (con el desplazamiento "
                   "al rojo de A si se conoce). En terracota, las compatibles con lo que examinas. No cambia el "
                   "espectro ni ningún resultado.")
    if ctx.selected:
        for k, it in ctx.selected.items():
            (_scientific_block if sci else _simple_block)(k, it)
    else:
        _overview(ctx, sci, inspect_key)
    if sci:
        _library_expander(ctx)


def _simple_block(k: str, it: si.Interpretation) -> None:
    st.html(f'<p style="margin:.35rem 0 .1rem"><b>{k}</b> · {theme.badge(it.label, si.VERDICT_BADGE[it.verdict])}</p>')
    st.markdown(f"{observed_text(it)} {meaning_text(it)}")
    why = why_text(it)
    if why:
        st.markdown(f"**Por qué:** {why}")
    limits = limits_text(it)
    if limits:
        st.markdown("**Qué impide estar seguros:** " + " ".join(limits))


def _scientific_block(k: str, it: si.Interpretation) -> None:
    st.html(f'<p style="margin:.35rem 0 .1rem">Espectro {k}: {theme.badge(it.label, si.VERDICT_BADGE[it.verdict])} '
            f'<span class="sc-muted">{si.VERDICT_MEANING[it.verdict]}.</span></p>')
    o, f = it.observation, it.feature
    z, zsrc = _z_text(it.redshift)
    if "lambda_um" in o:
        theme.facts([
            (theme.unit("λ") + " observada", f"{o['lambda_um']:.3f} µm",
             f"centroide {o['centroide_um']:.3f} · media altura {o['media_altura_um'][0]:.3f}–{o['media_altura_um'][1]:.3f}"
             f" (canales {o['canales_media_altura'][0]}–{o['canales_media_altura'][1]})"),
            ("Detector · resolución", f"D{o['detector']} · R = {o['R']:.0f}",
             f"elemento de resolución ≈ {o['elemento_resolucion_um']:.3f} µm" +
             ("" if o["R_del_fits"] else " (R estimada)")),
            ("Desplazamiento al rojo", z, zsrc),
            ("Datos", f"{f.kind} · {f.label.lower()}",
             f"contraste / dispersión {abs(o['contraste_sobre_dispersion']):.1f} (descriptivo, no significación)")])
    else:
        theme.facts([("Intervalo examinado", f"canales {f.trial_lo}–{f.trial_hi}" if f is not None else "—",
                      f.label.lower() if f is not None else ""), ("Desplazamiento al rojo", z, zsrc)])
    rows = _match_rows(it)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height="content")
    # the general limit that applies: a match is not an identification; no match does not exclude other substances
    general = it.limitations[:1] if it.matches else it.limitations[2:3]
    st.markdown("**Qué impide la certeza**\n" + "\n".join(f"- {b}" for b in it.blockers + general))
    refs = list(dict.fromkeys(m.reference for m in it.matches + it.others))
    if refs:
        with st.expander(f"Condiciones, confusiones y bibliografía · espectro {k}"):
            for r in refs:
                st.markdown(f"**{r.name}** — {r.scientific} *{r.process}; {r.transition}.* {r.width_note}\n\n"
                            "Condiciones: " + " ".join(r.conditions) + "\n\nOtras causas posibles: " +
                            " ".join(r.confounders) + "\n\n" +
                            "\n".join(f"- [{s.citation}]({s.url}): {s.used_for}" for s in r.sources))


def _pick(inspect_key: str, canal: int) -> None:
    st.session_state[inspect_key] = {"lo": int(canal), "hi": int(canal)}


def _overview(ctx: Context, sci: bool, inspect_key: str) -> None:
    items = [(k, it) for k, its in ctx.overview.items() for it in its]
    if not items:
        st.markdown("El analizador no señala picos ni valles en este espectro: no hay nada que interpretar. Eso no "
                    "demuestra que falten sustancias." if not sci else
                    "Sin características clasificadas por el analizador: no hay nada que interpretar. La ausencia de "
                    "una característica no demuestra la ausencia de una sustancia (sin incertidumbres).")
    else:
        st.markdown(f"SkyClues compara cada pico o valle señalado con {len(sr.REFERENCES)} referencias conocidas "
                    "(hielos, compuestos de carbono e hidrógeno). Elige uno para ver qué podría indicar." if not sci else
                    f"Cada característica clasificada se compara con la biblioteca ({sr.LIBRARY_VERSION}). Pulse "
                    "«Examinar» o seleccione el canal en el gráfico para ver hipótesis, pruebas y límites.")
        for k, it in items:
            f = it.feature
            left, right = st.columns([4, 1], vertical_alignment="center")
            where = f"{f.lam:.3f} µm (canal {f.canal})" if sci else f"cerca de {_um(f.lam)}"
            left.html(f'<p style="margin:0"><b>{k}</b> · {f.kind} {where} '
                      f'{theme.badge(it.label, si.VERDICT_BADGE[it.verdict])}</p>')
            right.button("Examinar", key=f"sx_interp_{k}_{f.canal}", on_click=_pick, args=(inspect_key, f.canal),
                         help="Examina este pico o valle en el gráfico y muestra su interpretación.")
    if sci:
        with st.expander("Dónde caería cada referencia en este espectro"):
            rows = [{"Espectro": k, "Referencia": c.reference.name, "λ esperada (µm)": round(c.lam_obs_um, 4),
                     "Canal": " y ".join(map(str, c.channels)) or "—", "Estado": si.COVERAGE_LABELS[c.status],
                     "Motivo": " ".join(c.reasons)} for k, cs in ctx.surveys.items() for c in cs]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption("Sin cobertura válida no se concluye ni presencia ni ausencia. «Nada señalado» tampoco demuestra "
                       "ausencia: el espectro no tiene incertidumbres.")


def _library_expander(ctx: Context) -> None:
    with st.expander("Biblioteca de referencias, ventana de compatibilidad y límites"):
        lib = [{"Id": r.id, "Referencia": r.name, "Portador": r.carrier, "Transición": r.transition,
                "λ en reposo (µm)": (f"{r.lam_range_um[0]:.3f}–{r.lam_range_um[1]:.3f}"
                                     if r.lam_range_um[0] != r.lam_range_um[1] else f"{r.lam_um:.6f}"),
                "Tipo": f"{sr.NATURE_TEXT[r.nature]} · {sr.FORM_TEXT[r.form]}",
                "FWHM documentada (µm)": "—" if r.fwhm_um is None else f"{r.fwhm_um:.3f}",
                "Fuentes": "; ".join(sr.short(s) for s in r.sources)} for r in sr.REFERENCES]
        st.dataframe(pd.DataFrame(lib), hide_index=True, width="stretch")
        m = si.method_summary()
        rs_rows = [{"Galaxia": g.name, "NED": g.ned_name, "z": g.z, "Indicador": g.z_flag, "D25 (″)": g.d25_arcsec,
                    "b/a": round(g.axis_ratio, 3), "PA (°)": "—" if g.pa_deg is None else f"{g.pa_deg:g}"}
                   for g in sr.GALAXIES]
        st.markdown(
            f"- **Motor:** {m['motor']} · **biblioteca:** {m['biblioteca']}. Usa los resultados del analizador "
            f"({sf.METHOD_VERSION}); no repite la extracción ni busca picos de nuevo.\n"
            "- **Ventana:** intervalo a media altura de la característica (unión de WL_MIN–WL_MAX de sus canales, de la "
            "tabla SPECTRAL_CHANNELS del FITS), ampliado solo por el error documentado del centro de banda (1 nm en "
            "D1–D4, 10 nm en D5–D6; Hui et al. 2026). Sin tolerancia universal en µm. A menos de λ/R fuera de ella, "
            "«canal contiguo»: nunca compatible.\n"
            "- **Tipo:** pico ↔ emisión, valle ↔ absorción. Una banda documentada de 3 o más elementos de resolución "
            "exige una característica «amplia»; un mínimo aislado no basta.\n"
            "- **Hielos:** como máximo «insuficientemente respaldada»: V1 no tiene un modelo de absorción ni un "
            "continuo que abarque la banda.\n"
            "- **Desplazamiento al rojo:** λ esperada = λ en reposo × (1 + z), solo con un z trazable (tabla curada de "
            "NED, si la posición está dentro de la isofota D25 del RC3; ±300 km/s por movimientos internos, supuesto). "
            "Sin él, se compara en reposo y se declara. Nunca se estima z a partir de una coincidencia.\n"
            "- **Veredictos:** cualitativos, sin probabilidades (no hay un modelo calibrado). Una diferencia entre A y "
            "B no es una identificación: cada espectro se interpreta por separado.")
        st.dataframe(pd.DataFrame(rs_rows), hide_index=True, width="stretch")
        lims = next((it.limitations for it in ctx.selected.values()), None) or \
            next((its[0].limitations for its in ctx.overview.values() if its), [])
        if lims:
            st.markdown("**Límites de esta interpretación**\n" + "\n".join(f"- {x}" for x in lims))
        used = dict.fromkeys([s for r in sr.REFERENCES for s in r.sources] + list(sr.INSTRUMENT_SOURCES) +
                             list(sr.REDSHIFT_SOURCES))
        st.markdown("**Fuentes**\n" + "\n".join(f"- [{s.citation}]({s.url}): {s.used_for}" for s in used))
