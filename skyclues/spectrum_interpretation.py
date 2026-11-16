"""Spectrum Explorer: «What could this spectrum indicate?» (presentation of the spectral interpreter V1).

Presentation only. Every verdict, hypothesis and limitation comes from ``spectral_interpreter`` (engine) and
``spectral_references`` (registry) and is the same in both levels: Simple says it in everyday words, Scientific
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
              "nota": (f"shifted with z = {rs.z:.6f} ({rs.object_name})" if rs.known else
                       "at rest: z unknown"), "destacada": r.id in lit, "etiqueta": ""} for r in sr.REFERENCES]
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
        return "No peak or valley stands out here."
    if f is None or f.lam is None or "no_evaluable" in it.codes:
        return "No peak or valley can be assessed in this area: data are missing or the surroundings are not reliable."
    if f.kind == "pico":
        return f"We detected an excess of emission near {_um(f.lam)}."
    return f"We detected a decrease in light (possible absorption) near {_um(f.lam)}."


def meaning_text(it: si.Interpretation) -> str:
    ms = it.matches
    if ms:
        first = ms[0].reference
        if it.verdict == si.NOT_EVALUABLE:
            return f"It falls where {first.plain_name} would be expected, but these data do not allow it to be interpreted."
        text = f"It could be related to {first.plain_name}"
        if len(ms) > 1:
            kind = "emisiones" if first.nature == sr.EMISSION else "absorciones"
            text += f", although other nearby {kind}, such as that of {ms[1].reference.plain_name}, may also contribute"
        if it.verdict == si.WEAK:
            text += ", but this view is not enough to support it"
        return text + "."
    if it.verdict == si.NONE:
        opposite = [m for m in it.others if m.status == si.OPPOSITE]
        extra = (f" At that position, {opposite[0].reference.plain_name} would appear as a decrease in light, not "
                 "as an excess." if opposite and opposite[0].reference.nature == sr.ABSORPTION else "")
        return (f"No matches in the current library ({len(sr.REFERENCES)} references). This does not rule out other known "
                "physical features." + extra)
    return "SkyClues cannot interpret it."


def why_text(it: si.Interpretation) -> str | None:
    if not it.matches:
        return None
    ref, rs = it.matches[0].reference, it.redshift
    where = ("its position matches the one that light would have, once the speed at which the "
             f"galaxy {rs.object_name} is receding has been corrected for" if rs.known else "its position matches the one that this light has")
    return f"{where[0].upper()}{where[1:]}. {ref.plain}"


PLAIN_LIMITS = {
    "visible": "The signal is slight.",
    "precaucion": "Part of the light may have saturated in this area.",
    "entorno": "Part of the light may have saturated next to this area.",
    "bloom": "Light from a bright source may have spilled over onto this area.",
    "detectores": "It coincides with the junction between two detectors, which can create false peaks and valleys.",
    "varias": "SPHEREx does not separate colours this close.",
    "hielo": "To talk about ice the whole band has to be measured and there has to be a light source behind it; this view "
             "does not do that.",
    "z_desconocido": "We do not know whether this light comes from a distant galaxy that is receding: it is compared as if it were at "
                     "rest.",
    "no_evaluable": "Data are missing in that area or around it.",
    "sin_caracteristica": "Not seeing anything does not prove that a substance is absent.",
}


def limits_text(it: si.Interpretation) -> list[str]:
    out = [PLAIN_LIMITS[c] for c in dict.fromkeys(it.codes) if c in PLAIN_LIMITS]
    if it.matches or it.verdict == si.NONE:
        out.append("A peak or a valley is not enough to identify a material.")
    return list(dict.fromkeys(out))


def _z_text(rs: sr.Redshift) -> tuple[str, str]:
    if rs.known:
        return f"z = {rs.z:.6f}", f"{rs.object_name} · NED, dentro de su isofota D25 · ±{rs.sigma:.4f}"
    return "desconocido", "it is compared at rest (z = 0); it is never estimated from a coincidence"


def _match_rows(it: si.Interpretation) -> list[dict]:
    rows = []
    for m in it.matches + it.others + it.orientative:
        r = m.reference
        rows.append({"Reference": r.name, "Type": f"{sr.NATURE_TEXT[r.nature]} · {sr.FORM_TEXT[r.form]}",
                     "λ en reposo (µm)": (f"{r.lam_range_um[0]:.3f}–{r.lam_range_um[1]:.3f}"
                                          if r.lam_range_um[0] != r.lam_range_um[1] else f"{r.lam_um:.4f}"),
                     "λ esperada (µm)": f"{m.lam_obs_um:.4f}",
                     "Expected channel": " y ".join(map(str, m.predicted_channels)),
                     "Compatibility": si.STATUS_LABELS[m.status],
                     "z for which it holds": ("—" if m.z_range is None else
                                                   f"{m.z_range[0]:+.4f} a {m.z_range[1]:+.4f}"),
                     "Reason": " ".join(m.reasons)})
    return rows


# ----------------------------------------------------------------------------- page section
def render(ctx: Context, sci: bool, inspect_key: str) -> None:
    with st.container(key=SECTION_KEY):
        _render(ctx, sci, inspect_key)


def _render(ctx: Context, sci: bool, inspect_key: str) -> None:
    theme.eyebrow("What could this spectrum indicate?")
    st.toggle("Show references on the chart" if sci else "Show on the chart where the references fall",
              key=theme.bind(REFS_OPTION, False), on_change=theme.keep, args=(REFS_OPTION,),
              help="Dotted lines at the expected position of each reference in the library (with the redshift "
                   "of A if it is known). In terracotta, those compatible with what you are examining. It does not change the "
                   "spectrum or any result.")
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
        st.markdown(f"**Why:** {why}")
    limits = limits_text(it)
    if limits:
        st.markdown("**What prevents certainty:** " + " ".join(limits))


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
            ("Detector · resolution", f"D{o['detector']} · R = {o['R']:.0f}",
             f"resolution element ≈ {o['elemento_resolucion_um']:.3f} µm" +
             ("" if o["R_del_fits"] else " (R estimada)")),
            ("Redshift", z, zsrc),
            ("Data", f"{f.kind} · {f.label.lower()}",
             f"contrast / scatter {abs(o['contraste_sobre_dispersion']):.1f} (descriptive, not significance)")])
    else:
        theme.facts([("Interval examined", f"canales {f.trial_lo}–{f.trial_hi}" if f is not None else "—",
                      f.label.lower() if f is not None else ""), ("Redshift", z, zsrc)])
    rows = _match_rows(it)
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height="content")
    # the general limit that applies: a match is not an identification; no match does not exclude other substances
    general = it.limitations[:1] if it.matches else it.limitations[2:3]
    st.markdown("**What prevents certainty**\n" + "\n".join(f"- {b}" for b in it.blockers + general))
    refs = list(dict.fromkeys(m.reference for m in it.matches + it.others))
    if refs:
        with st.expander(f"Conditions, confusions and bibliography · spectrum {k}"):
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
        st.markdown("The analyser flags no peaks or valleys in this spectrum: there is nothing to interpret. This does not "
                    "prove that substances are missing." if not sci else
                    "No features classified by the analyser: there is nothing to interpret. The absence of "
                    "a feature does not prove the absence of a substance (no uncertainties).")
    else:
        st.markdown(f"SkyClues compares each peak or valley flagged with {len(sr.REFERENCES)} known references "
                    "(ices, carbon compounds and hydrogen). Choose one to see what it could indicate." if not sci else
                    f"Each classified feature is compared with the library ({sr.LIBRARY_VERSION}). Press "
                    "«Examine» or select the channel on the chart to see hypotheses, evidence and limits.")
        for k, it in items:
            f = it.feature
            left, right = st.columns([4, 1], vertical_alignment="center")
            where = f"{f.lam:.3f} µm (canal {f.canal})" if sci else f"cerca de {_um(f.lam)}"
            left.html(f'<p style="margin:0"><b>{k}</b> · {f.kind} {where} '
                      f'{theme.badge(it.label, si.VERDICT_BADGE[it.verdict])}</p>')
            right.button("Examine", key=f"sx_interp_{k}_{f.canal}", on_click=_pick, args=(inspect_key, f.canal),
                         help="Examine this peak or valley on the chart and show its interpretation.")
    if sci:
        with st.expander("Where each reference would fall in this spectrum"):
            rows = [{"Spectrum": k, "Reference": c.reference.name, "λ esperada (µm)": round(c.lam_obs_um, 4),
                     "Channel": " y ".join(map(str, c.channels)) or "—", "Status": si.COVERAGE_LABELS[c.status],
                     "Reason": " ".join(c.reasons)} for k, cs in ctx.surveys.items() for c in cs]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption("Without valid coverage neither presence nor absence is concluded. «Nothing flagged» does not prove "
                       "absence either: the spectrum has no uncertainties.")


def _library_expander(ctx: Context) -> None:
    with st.expander("Library of references, compatibility window and limits"):
        lib = [{"Id": r.id, "Reference": r.name, "Carrier": r.carrier, "Transition": r.transition,
                "λ en reposo (µm)": (f"{r.lam_range_um[0]:.3f}–{r.lam_range_um[1]:.3f}"
                                     if r.lam_range_um[0] != r.lam_range_um[1] else f"{r.lam_um:.6f}"),
                "Type": f"{sr.NATURE_TEXT[r.nature]} · {sr.FORM_TEXT[r.form]}",
                "Documented FWHM (µm)": "—" if r.fwhm_um is None else f"{r.fwhm_um:.3f}",
                "Sources": "; ".join(sr.short(s) for s in r.sources)} for r in sr.REFERENCES]
        st.dataframe(pd.DataFrame(lib), hide_index=True, width="stretch")
        m = si.method_summary()
        rs_rows = [{"Galaxy": g.name, "NED": g.ned_name, "z": g.z, "Indicator": g.z_flag, "D25 (″)": g.d25_arcsec,
                    "b/a": round(g.axis_ratio, 3), "PA (°)": "—" if g.pa_deg is None else f"{g.pa_deg:g}"}
                   for g in sr.GALAXIES]
        st.markdown(
            f"- **Engine:** {m['motor']} · **library:** {m['biblioteca']}. It uses the results of the analyser "
            f"({sf.METHOD_VERSION}); it does not repeat the extraction or look for peaks again.\n"
            "- **Window:** half-height interval of the feature (union of WL_MIN–WL_MAX of its channels, from the "
            "SPECTRAL_CHANNELS table of the FITS), widened only by the documented error of the band centre (1 nm in "
            "D1–D4, 10 nm in D5–D6; Hui et al. 2026). No universal tolerance in µm. Within λ/R outside it, "
            "«adjacent channel»: never compatible.\n"
            "- **Type:** peak ↔ emission, valley ↔ absorption. A documented band of 3 or more resolution elements "
            "requires a «broad» feature; an isolated minimum is not enough.\n"
            "- **Ices:** at most «insufficiently supported»: V1 has no absorption model or "
            "continuum that spans the band.\n"
            "- **Redshift:** expected λ = rest λ × (1 + z), only with a traceable z (curated table from "
            "NED, if the position is inside the D25 isophote of RC3; ±300 km/s for internal motions, assumption). "
            "Without it, it is compared at rest and this is declared. z is never estimated from a coincidence.\n"
            "- **Verdicts:** qualitative, without probabilities (there is no calibrated model). A difference between A and "
            "B is not an identification: each spectrum is interpreted separately.")
        st.dataframe(pd.DataFrame(rs_rows), hide_index=True, width="stretch")
        lims = next((it.limitations for it in ctx.selected.values()), None) or \
            next((its[0].limitations for its in ctx.overview.values() if its), [])
        if lims:
            st.markdown("**Limits of this interpretation**\n" + "\n".join(f"- {x}" for x in lims))
        used = dict.fromkeys([s for r in sr.REFERENCES for s in r.sources] + list(sr.INSTRUMENT_SOURCES) +
                             list(sr.REDSHIFT_SOURCES))
        st.markdown("**Fuentes**\n" + "\n".join(f"- [{s.citation}]({s.url}): {s.used_for}" for s in used))
