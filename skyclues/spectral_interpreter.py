"""Spectral interpreter V1: what a feature found by the analyzer could correspond to, and what prevents certainty.

Three responsibilities kept apart:

A. **Observation.** What ``spectral_features`` measured (kind, class, channels, half-height interval, detectors,
   cautions). It is read, never recomputed: no new extraction, continuum or peak detector.
B. **Compatibility.** For each documented reference (``spectral_references``): its wavelength shifted by a
   traceable redshift, compared with the half-height interval of the feature; its nature (emission ↔ peak,
   absorption ↔ valley); its documented width against the channel width; and the quality of the data.
C. **Interpretation.** A qualitative verdict and the hypotheses that remain. No probabilities (there is no
   calibrated model), no identification, no redshift estimated from a coincidence.

Compatibility window (declared conservative approximation; the per-pixel spectral response is not available):
a narrow line at λ excites most the channel whose range of band centres (WL_MIN–WL_MAX of the FITS) contains λ.
The window is therefore the half-height interval of the feature (the union of the ranges of its half-height
channels), widened on each side only by the documented band-centre accuracy (Hui et al. 2026: 1 nm in D1–D4,
10 nm in D5–D6). There is no universal tolerance in µm. A reference outside the window but within one
resolution element (λ/R, R of the FITS) is reported as *contigua*, never as compatible.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import spectral_features as sf
from . import spectral_references as sr

ENGINE_VERSION = "skyclues-interprete 1.0 (2026-11-15)"

# ----------------------------------------------------------------------------- verdicts
COMPATIBLE, SEVERAL, WEAK, NONE, NOT_EVALUABLE = "compatible", "varias", "insuficiente", "ninguna", "no_evaluable"
VERDICT_LABELS = {COMPATIBLE: "Referencia compatible", SEVERAL: "Varias referencias compatibles",
                  WEAK: "Coincidencia insuficientemente respaldada", NONE: "Ninguna referencia compatible",
                  NOT_EVALUABLE: "No evaluable"}
VERDICT_MEANING = {
    COMPATIBLE: "una sola referencia coincide en posición y tipo, con datos sin reservas; no es una identificación",
    SEVERAL: "varias referencias coinciden en posición y tipo: SkyClues no puede distinguirlas y conserva todas",
    WEAK: "alguna referencia coincide en posición y tipo, pero la señal o los datos no bastan para sostenerla",
    NONE: "ninguna referencia de la biblioteca coincide; no excluye otras sustancias ni procesos",
    NOT_EVALUABLE: "los datos de este intervalo no permiten valorar ninguna referencia"}
VERDICT_BADGE = {COMPATIBLE: "sc-ok", SEVERAL: "sc-ok", WEAK: "sc-warn", NONE: "", NOT_EVALUABLE: ""}  # theme.py classes

# status of one reference against one feature
MATCH, MATCH_WEAK = "compatible", "insuficiente"
OPPOSITE, WIDTH, ADJACENT, ORIENTATIVE = "naturaleza_opuesta", "anchura_incoherente", "contigua", "orientativa"
STATUS_LABELS = {MATCH: "Compatible", MATCH_WEAK: "Coincide, insuficientemente respaldada",
                 OPPOSITE: "No compatible: tipo opuesto", WIDTH: "No compatible: anchura",
                 ADJACENT: "No compatible: canal contiguo", ORIENTATIVE: "Solo orientativa"}

# coverage of a reference over the whole spectrum
COV_FEATURE, COV_NO_SIGNAL, COV_NO_DATA, COV_OUTSIDE = ("con_caracteristica", "sin_senal", "sin_cobertura",
                                                        "fuera_de_rango")
COVERAGE_LABELS = {COV_FEATURE: "Hay una característica señalada", COV_NO_SIGNAL: "Nada señalado",
                   COV_NO_DATA: "Sin cobertura válida", COV_OUTSIDE: "Fuera del intervalo de SPHEREx"}

KIND_NATURE = {"pico": sr.EMISSION, "valle": sr.ABSORPTION}
LABELLED = (sf.QUANTIFIABLE, sf.VISIBLE)


# ----------------------------------------------------------------------------- channels and resolution
@dataclass(frozen=True)
class ChannelInfo:
    canal: int
    lam: float
    lam_min: float
    lam_max: float
    detector: int
    R: float
    R_from_fits: bool

    @property
    def element_um(self) -> float:
        """One resolution element λ/R (Hui et al. 2026: Δλ is the integral of the peak-normalised response)."""
        return self.lam / self.R


def resolution_of(spec) -> dict[int, float]:
    """Median resolving power of each channel, as the SPECTRAL_CHANNELS table of the FITS gives it."""
    return {int(r["canal"]): float(r["R"]) for r in spec.rows if r.get("R") not in (None, 0)}


def channel_table(series: sf.Series, resolution: dict | None = None) -> dict[int, ChannelInfo]:
    """Channel geometry of a spectrum. Without the R of the FITS, R is estimated as λ/(WL_MAX − WL_MIN) and
    declared as such."""
    out = {}
    for i, c in enumerate(series.canal):
        c = int(c)
        width = float(series.lam_max[i] - series.lam_min[i])
        from_fits = bool(resolution and c in resolution)
        R = float(resolution[c]) if from_fits else float(series.lam[i]) / width
        out[c] = ChannelInfo(c, float(series.lam[i]), float(series.lam_min[i]), float(series.lam_max[i]),
                             int(series.detector[i]), R, from_fits)
    return out


def channels_at(table: dict[int, ChannelInfo], lam_um: float) -> tuple[int, ...]:
    """Channels whose range of band centres contains λ (two where neighbouring ranges overlap); else the nearest."""
    inside = tuple(c for c, ch in table.items() if ch.lam_min <= lam_um <= ch.lam_max)
    if inside:
        return inside
    return (min(table, key=lambda c: abs(table[c].lam - lam_um)),)


# ----------------------------------------------------------------------------- structures
@dataclass(frozen=True)
class Window:
    lo_um: float
    hi_um: float
    margin_lo_um: float
    margin_hi_um: float
    canal_lo: int
    canal_hi: int
    basis: str

    def overlaps(self, lo: float, hi: float) -> bool:
        return hi >= self.lo_um - self.margin_lo_um and lo <= self.hi_um + self.margin_hi_um

    def distance(self, lo: float, hi: float) -> float:
        return max(0.0, (self.lo_um - self.margin_lo_um) - hi, lo - (self.hi_um + self.margin_hi_um))

    def to_dict(self) -> dict:
        return {"lambda_min_um": self.lo_um, "lambda_max_um": self.hi_um, "margen_um": [self.margin_lo_um,
                self.margin_hi_um], "canales": [self.canal_lo, self.canal_hi], "criterio": self.basis}


@dataclass
class Match:
    reference: sr.Reference
    status: str
    lam_rest_um: float
    lam_obs_um: float
    obs_range_um: tuple[float, float]
    predicted_channels: tuple[int, ...]
    distance_um: float
    element_um: float
    z_range: tuple[float, float] | None        # z for which it would stay compatible (only when z is unknown)
    reasons: list[str] = field(default_factory=list)

    @property
    def compatible(self) -> bool:
        return self.status in (MATCH, MATCH_WEAK)

    def to_dict(self) -> dict:
        return {"referencia": self.reference.id, "estado": self.status, "lambda_reposo_um": self.lam_rest_um,
                "lambda_esperada_um": self.lam_obs_um, "intervalo_esperado_um": list(self.obs_range_um),
                "canales_previstos": list(self.predicted_channels), "distancia_um": self.distance_um,
                "elemento_resolucion_um": self.element_um,
                "z_compatible": None if self.z_range is None else list(self.z_range), "motivos": self.reasons}


@dataclass
class Interpretation:
    serie: str
    verdict: str
    feature: sf.Feature | None
    observation: dict
    window: Window | None
    redshift: sr.Redshift
    matches: list[Match]           # coincide in position and nature: the hypotheses that remain
    others: list[Match]            # near or in the window, but not compatible (with the reason)
    orientative: list[Match]       # references inside an interval that cannot be evaluated
    blockers: list[str]            # what prevents a conclusion (feature level)
    limitations: list[str]         # what always applies to this interpretation
    codes: list[str] = field(default_factory=list)   # the blockers as codes (wording of each level)
    version: str = ENGINE_VERSION
    library: str = sr.LIBRARY_VERSION

    @property
    def label(self) -> str:
        return VERDICT_LABELS[self.verdict]

    @property
    def hypotheses(self) -> list[Match]:
        return self.matches

    def to_dict(self) -> dict:
        return {"serie": self.serie, "veredicto": self.verdict, "veredicto_texto": self.label,
                "observacion": self.observation, "ventana": None if self.window is None else self.window.to_dict(),
                "desplazamiento_al_rojo": self.redshift.to_dict(),
                "hipotesis": [m.to_dict() for m in self.matches], "otras": [m.to_dict() for m in self.others],
                "orientativas": [m.to_dict() for m in self.orientative], "impedimentos": self.blockers,
                "codigos": self.codes, "limitaciones": self.limitations, "motor": self.version,
                "biblioteca": self.library}


@dataclass
class Coverage:
    """Where a reference would fall in this spectrum and what the analyzer says there (whole-spectrum view)."""

    reference: sr.Reference
    status: str
    lam_obs_um: float
    channels: tuple[int, ...]
    feature: sf.Feature | None
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"referencia": self.reference.id, "estado": self.status, "lambda_esperada_um": self.lam_obs_um,
                "canales": list(self.channels), "motivos": self.reasons}


# ----------------------------------------------------------------------------- A. observation
def _labelled(f: sf.Feature | None) -> bool:
    return f is not None and f.klass in LABELLED and f.lam is not None and f.kind in KIND_NATURE


def observe(f: sf.Feature | None, table: dict[int, ChannelInfo]) -> dict:
    """What the analyzer measured, as it measured it (nothing recomputed)."""
    if f is None:
        return {}
    out = {"clase": f.klass, "clase_texto": f.label, "tipo": f.kind, "canales_examinados": [f.trial_lo, f.trial_hi],
           "detectores": list(f.detectors), "precaucion": list(f.caution_channels),
           "contraste": f.contrast, "contraste_relativo": f.relative,
           "contraste_sobre_dispersion": None if f.ratio is None else float(f.ratio),
           "motivos_analizador": list(f.reasons), "limitaciones_analizador": list(f.limitations), "unidad": f.unit}
    if _labelled(f):
        peak = table[f.canal]
        out |= {"lambda_um": f.lam, "centroide_um": f.lam_centroid, "media_altura_um": [f.lam_lo, f.lam_hi],
                "canales_media_altura": [f.canal_lo, f.canal_hi], "n_canales": f.n_channels, "anchura": f.width,
                "canal_maximo": f.canal, "detector": peak.detector, "R": peak.R, "R_del_fits": peak.R_from_fits,
                "elemento_resolucion_um": peak.element_um}
    return out


def _window(f: sf.Feature, table: dict[int, ChannelInfo], labelled: bool) -> Window:
    if labelled:
        lo, hi, a, b = f.lam_lo, f.lam_hi, f.canal_lo, f.canal_hi
        basis = ("intervalo a media altura de la característica (unión de WL_MIN–WL_MAX de sus canales), ampliado "
                 "por el error documentado del centro de banda")
    else:
        a, b = f.trial_lo, f.trial_hi
        lo, hi = table[a].lam_min, table[b].lam_max
        basis = "intervalo examinado (no es una característica clasificada): solo orientativo"
    return Window(float(lo), float(hi), sr.BAND_CENTRE_ERROR_UM[table[a].detector],
                  sr.BAND_CENTRE_ERROR_UM[table[b].detector], int(a), int(b), basis)


def _evidence(f: sf.Feature, series: sf.Series, qualities) -> tuple[list[str], list[str], list[str]]:
    """(hard, weak, codes): conditions that make the interval not evaluable, conditions that leave any
    coincidence insufficiently supported, and their codes (for the wording of each level). Read from the analyzer
    and the coverage diagnosis, never recomputed."""
    hard, weak, codes = [], [], []
    if f.klass == sf.NOT_EVALUABLE:
        hard.append("El analizador no puede valorar este intervalo: " + " ".join(f.reasons or ["faltan datos."]))
        return hard, weak, ["no_evaluable"]
    if f.klass == sf.NO_FEATURE or f.kind not in KIND_NATURE:
        hard.append("El analizador no señala ningún pico ni valle en este intervalo, así que no hay nada que "
                    "interpretar. Que no se vea una característica no demuestra que una sustancia falte: el espectro "
                    "no tiene incertidumbres.")
        return hard, weak, ["sin_caracteristica"]
    if len(f.detectors) > 1:
        codes.append("detectores")
        hard.append(f"El intervalo y su entorno abarcan los detectores {', '.join(f'D{d}' for d in f.detectors)}: "
                    "un salto de calibración o de resolución entre detectores produce picos y valles que no son "
                    "sustancias. No se interpreta.")
    if f.klass == sf.VISIBLE:
        codes.append("visible")
        weak.append(f"Señal «visible», no «cuantificable»: contraste de {abs(f.ratio):.1f} veces la dispersión de "
                    f"referencia (entre {sf.Q_VISIBLE:g} y {sf.Q_QUANTIFIABLE:g}, o con alguna reserva del analizador). "
                    "Es un umbral descriptivo, no una significación estadística.")
    if f.caution_channels:
        codes.append("precaucion")
        weak.append("OVERFLOW u OUTLIER en los canales " + ", ".join(map(str, f.caution_channels)) +
                    ": el valor puede no ser fiable.")
    env = [c for c in list(f.env_left) + list(f.env_right)]
    env_caution = [c for c in env if series.caution[series.index(c)]]
    if env_caution:
        codes.append("entorno")
        weak.append("OVERFLOW u OUTLIER en el entorno (canales " + ", ".join(map(str, env_caution)) +
                    "): el continuo local puede estar afectado.")
    if qualities:
        lo, hi = f.trial_lo - sf.N_SIDE, f.trial_hi + sf.N_SIDE
        bloom = [q.canal for q in qualities if lo <= q.canal <= hi and q.valid_for_extraction and q.bloom]
        if bloom:
            codes.append("bloom")
            weak.append("Píxeles con BLOOM en la apertura (canales " + ", ".join(map(str, bloom)) +
                        "): luz desbordada de una fuente brillante puede contaminar el valor.")
    return hard, weak, codes


# ----------------------------------------------------------------------------- B. compatibility
def _shifted(ref: sr.Reference, rs: sr.Redshift) -> tuple[float, tuple[float, float]]:
    z = rs.z or 0.0
    lo, hi = ref.lam_range_um
    return ref.lam_um * (1 + z), (lo * (1 + z - rs.sigma), hi * (1 + z + rs.sigma))


def _evaluate(ref: sr.Reference, f: sf.Feature, win: Window, table: dict[int, ChannelInfo], rs: sr.Redshift,
              weak: list[str], labelled: bool) -> Match | None:
    lam_obs, (lo, hi) = _shifted(ref, rs)
    predicted = channels_at(table, lam_obs)
    element = table[predicted[0]].element_um
    dist = win.distance(lo, hi)
    z_range = None
    if not rs.known:
        z_range = ((win.lo_um - win.margin_lo_um) / ref.lam_range_um[1] - 1,
                   (win.hi_um + win.margin_hi_um) / ref.lam_range_um[0] - 1)
    m = Match(ref, MATCH, ref.lam_um, lam_obs, (lo, hi), predicted, dist, element, z_range)
    if not win.overlaps(lo, hi):
        if dist > element or (labelled and KIND_NATURE[f.kind] != ref.nature):
            return None                     # far away, or nearby but of the opposite nature: not worth listing
        m.status, m.z_range = ADJACENT, None    # no z is ever suggested by a near miss
        m.reasons.append(f"Su posición esperada ({lam_obs:.3f} µm, canal {_channels(predicted)}) queda a "
                         f"{dist:.3f} µm del intervalo de la característica, menos de un elemento de resolución "
                         f"({element:.3f} µm): una línea ahí haría máximo en el canal contiguo.")
        return m
    if not labelled:
        m.status = ORIENTATIVE
        m.reasons.append("Cae en el intervalo examinado, que no es una característica evaluable.")
        return m
    nature = KIND_NATURE[f.kind]
    if nature != ref.nature:
        m.status, m.z_range = OPPOSITE, None
        m.reasons.append(f"La referencia es una {sr.NATURE_TEXT[ref.nature]} y aquí hay un {f.kind}: no son "
                         "compatibles.")
        return m
    if ref.fwhm_um is not None:
        span = ref.fwhm_um / table[predicted[0]].element_um
        if span >= 3 and f.width != "amplia":
            m.status, m.z_range = WIDTH, None
            m.reasons.append(f"La banda documentada mide unos {ref.fwhm_um:.2f} µm (≈ {span:.0f} canales) y aquí la "
                             f"característica ocupa {f.n_channels} canal{'es' if f.n_channels != 1 else ''} a media "
                             "altura: un mínimo aislado no es coherente con ella.")
            return m
    m.reasons.append(f"Su posición esperada ({lam_obs:.3f} µm) cae dentro del intervalo a media altura "
                     f"({win.lo_um:.3f}–{win.hi_um:.3f} µm) y el tipo coincide ({sr.NATURE_TEXT[ref.nature]}).")
    if ref.needs_absorption_model:
        m.status = MATCH_WEAK
        m.reasons.append("Para un hielo hace falta una depresión coherente frente a un continuo fiable que abarque la "
                         "banda y una fuente infrarroja detrás. El continuo local del analizador (tres canales a cada "
                         "lado) no lo garantiza y V1 no tiene un modelo de absorción: solo referencia orientativa.")
    if weak:
        m.status = MATCH_WEAK
    return m


def _channels(cs) -> str:
    return " y ".join(map(str, cs))


# ----------------------------------------------------------------------------- C. interpretation
def interpret(series: sf.Series, feature: sf.Feature | None, *, redshift: sr.Redshift = sr.UNKNOWN_Z,
              resolution: dict | None = None, qualities=None, aperture_arcsec: float | None = None,
              references=sr.REFERENCES) -> Interpretation:
    """Interpretation of one feature of one spectrum (A and B are always interpreted separately)."""
    table = channel_table(series, resolution)
    obs = observe(feature, table)
    limitations = _limitations(series, feature, table, redshift, aperture_arcsec, resolution)
    if feature is None:
        return Interpretation(series.label, NOT_EVALUABLE, None, obs, None, redshift, [], [], [],
                              ["No hay ningún intervalo examinado."], limitations, ["sin_intervalo"])
    labelled = _labelled(feature)
    hard, weak, codes = _evidence(feature, series, None if feature.trial_lo is None else qualities)
    if feature.trial_lo is None:
        return Interpretation(series.label, NOT_EVALUABLE, feature, obs, None, redshift, [], [], [],
                              hard or ["Intervalo sin canales."], limitations, codes or ["no_evaluable"])
    win = _window(feature, table, labelled)
    found = [m for m in (_evaluate(r, feature, win, table, redshift, weak or hard, labelled) for r in references) if m]
    matches = [m for m in found if m.status in (MATCH, MATCH_WEAK)]
    others = [m for m in found if m.status in (OPPOSITE, WIDTH, ADJACENT)]
    orient = [m for m in found if m.status == ORIENTATIVE]
    if hard:
        verdict = NOT_EVALUABLE
        for m in matches:                               # never "compatible" where nothing can be concluded
            m.status = MATCH_WEAK
    else:
        strong = [m for m in matches if m.status == MATCH]
        verdict = (SEVERAL if len(strong) > 1 else COMPATIBLE if strong else WEAK if matches else NONE)
    blockers = hard + weak
    if len(matches) > 1:
        codes.append("varias")
        blockers.append("Varias referencias caen en el mismo intervalo y SPHEREx no las separa a esta resolución: se "
                        "conservan todas como hipótesis.")
    if any(m.reference.needs_absorption_model for m in matches):
        codes.append("hielo")
    if matches and not redshift.known:
        codes.append("z_desconocido")
    return Interpretation(series.label, verdict, feature, obs, win, redshift, matches, others, orient, blockers,
                          limitations, codes)


def _limitations(series, f, table, rs: sr.Redshift, aperture_arcsec, resolution) -> list[str]:
    out = ["Coincidir en posición y tipo no identifica una sustancia: es una hipótesis compatible con los datos.",
           "El espectro del cubo es exploratorio y no tiene incertidumbres; «contraste / dispersión de referencia» "
           "es descriptivo, no una significación estadística. No se dan probabilidades: no hay un modelo calibrado.",
           f"Solo se compara con las {len(sr.REFERENCES)} referencias de la biblioteca ({sr.LIBRARY_VERSION}); que "
           "ninguna coincida no excluye otras sustancias ni procesos."]
    if f is not None and _labelled(f):
        ch = table[f.canal]
        out.append(f"Resolución en el canal {ch.canal} (D{ch.detector}): R = {ch.R:.0f}"
                   + ("" if ch.R_from_fits else " (estimada con la anchura del canal; la tabla del FITS no la da)")
                   + f", un elemento de resolución ≈ {ch.element_um:.3f} µm. Las líneas estrechas no se resuelven y "
                     "no se exige que se resuelvan; solo se compara su posición.")
    if rs.known:
        out.append(f"Desplazamiento al rojo z = {rs.z:.6f} ({rs.object_name}, {rs.source.upper()}): λ esperada = "
                   "λ en reposo × (1 + z). " + rs.note)
    else:
        out.append(rs.note)
    if aperture_arcsec:
        out.append(f"La apertura (radio {aperture_arcsec:.0f}″) mezcla toda la luz que contiene, menos el anillo de "
                   "fondo: la interpretación describe esa mezcla, no un objeto concreto dentro de ella, y una emisión "
                   "extendida que también llene el anillo queda en parte restada.")
    out.append("Ventana de compatibilidad (aproximación conservadora declarada, sin la respuesta espectral completa de "
               "cada píxel): intervalo a media altura de la característica, ampliado solo por el error documentado "
               "del centro de banda (1 nm en D1–D4, 10 nm en D5–D6; Hui et al. 2026).")
    return out


def interpret_features(series: sf.Series, features, **kw) -> list[Interpretation]:
    """One interpretation per feature labelled by the analyzer in this spectrum."""
    return [interpret(series, f, **kw) for f in features if _labelled(f)]


# extraction status of a channel without value, in words (same wording as spectral_cube.STATUS_TEXT)
_STATUS_TEXT = {"blank": "canal sin datos en DR1, BLANKCH", "no_data_aperture": "apertura con píxeles sin datos, NHITS = 0",
                "no_background": "fondo insuficiente en el anillo"}


def survey(series: sf.Series, features=(), scatter: dict | None = None, *, redshift: sr.Redshift = sr.UNKNOWN_Z,
           references=sr.REFERENCES) -> list[Coverage]:
    """For every reference: where it would fall and what the analyzer says there. Without valid coverage nothing
    is concluded; without a marked feature, absence is not concluded either (no uncertainties)."""
    table = channel_table(series)
    lam_lo, lam_hi = float(np.min(series.lam_min)), float(np.max(series.lam_max))
    out = []
    for ref in references:
        lam_obs, _ = _shifted(ref, redshift)
        if not lam_lo <= lam_obs <= lam_hi:
            out.append(Coverage(ref, COV_OUTSIDE, lam_obs, (), None,
                                [f"{lam_obs:.3f} µm queda fuera de 0,75–5,0 µm."]))
            continue
        chans = channels_at(table, lam_obs)
        valued = [c for c in chans if np.isfinite(series.value[series.index(c)])]
        if not valued:
            why = sorted({_STATUS_TEXT.get(series.status[series.index(c)], "sin valor") for c in chans})
            out.append(Coverage(ref, COV_NO_DATA, lam_obs, chans, None,
                                [f"Canal {_channels(chans)} sin valor ({'; '.join(why)}): no se puede concluir ni "
                                 "presencia ni ausencia."]))
            continue
        try:
            f = sf.inspect_channel(series, valued[0], features, scatter)
        except sf.FeatureInputError as err:
            out.append(Coverage(ref, COV_NO_DATA, lam_obs, chans, None, [str(err)]))
            continue
        if f.klass == sf.NOT_EVALUABLE:
            out.append(Coverage(ref, COV_NO_DATA, lam_obs, chans, f,
                                ["El analizador no puede valorar ese canal: " + " ".join(f.reasons)]))
        elif _labelled(f):
            out.append(Coverage(ref, COV_FEATURE, lam_obs, chans, f,
                                [f"{f.kind.capitalize()} {f.label.lower()} en {f.lam:.3f} µm."]))
        else:
            out.append(Coverage(ref, COV_NO_SIGNAL, lam_obs, chans, f,
                                ["El analizador no señala nada ahí. No demuestra ausencia: el espectro no tiene "
                                 "incertidumbres y la señal podría estar por debajo de sus criterios."]))
    return out


def method_summary() -> dict:
    return {"motor": ENGINE_VERSION, "biblioteca": sr.LIBRARY_VERSION,
            "ventana": "intervalo a media altura (WL_MIN–WL_MAX de sus canales) ± error del centro de banda",
            "error_centro_banda_um": sr.BAND_CENTRE_ERROR_UM, "contigua": "a menos de λ/R del intervalo",
            "naturaleza": {"pico": sr.EMISSION, "valle": sr.ABSORPTION},
            "anchura": "una banda documentada de ≥ 3 elementos de resolución exige una característica «amplia»",
            "hielos": "como máximo «insuficientemente respaldada» (sin modelo de absorción en V1)",
            "z": "solo de la tabla curada (NED, dentro de la isofota D25) o del usuario; nunca estimado",
            "veredictos": VERDICT_LABELS}
