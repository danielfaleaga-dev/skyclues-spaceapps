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
VERDICT_LABELS = {COMPATIBLE: "Compatible reference", SEVERAL: "Several compatible references",
                  WEAK: "Match insufficiently supported", NONE: "No compatible reference",
                  NOT_EVALUABLE: "Not evaluable"}
VERDICT_MEANING = {
    COMPATIBLE: "a single reference matches in position and type, with data without reservations; it is not an identification",
    SEVERAL: "several references match in position and type: SkyClues cannot tell them apart and keeps all of them",
    WEAK: "some reference matches in position and type, but the signal or the data are not enough to support it",
    NONE: "no reference in the library matches; this does not exclude other substances or processes",
    NOT_EVALUABLE: "the data in this interval do not allow any reference to be assessed"}
VERDICT_BADGE = {COMPATIBLE: "sc-ok", SEVERAL: "sc-ok", WEAK: "sc-warn", NONE: "", NOT_EVALUABLE: ""}  # theme.py classes

# status of one reference against one feature
MATCH, MATCH_WEAK = "compatible", "insuficiente"
OPPOSITE, WIDTH, ADJACENT, ORIENTATIVE = "naturaleza_opuesta", "anchura_incoherente", "contigua", "orientativa"
STATUS_LABELS = {MATCH: "Compatible", MATCH_WEAK: "Matches, insufficiently supported",
                 OPPOSITE: "Not compatible: opposite type", WIDTH: "Not compatible: width",
                 ADJACENT: "Not compatible: adjacent channel", ORIENTATIVE: "Indicative only"}

# coverage of a reference over the whole spectrum
COV_FEATURE, COV_NO_SIGNAL, COV_NO_DATA, COV_OUTSIDE = ("con_caracteristica", "sin_senal", "sin_cobertura",
                                                        "fuera_de_rango")
COVERAGE_LABELS = {COV_FEATURE: "There is one feature flagged", COV_NO_SIGNAL: "Nothing flagged",
                   COV_NO_DATA: "No valid coverage", COV_OUTSIDE: "Outside the SPHEREx range"}

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
        basis = ("half-height interval of the feature (union of WL_MIN–WL_MAX of its channels), widened "
                 "by the documented error of the band centre")
    else:
        a, b = f.trial_lo, f.trial_hi
        lo, hi = table[a].lam_min, table[b].lam_max
        basis = "interval examined (not a classified feature): indicative only"
    return Window(float(lo), float(hi), sr.BAND_CENTRE_ERROR_UM[table[a].detector],
                  sr.BAND_CENTRE_ERROR_UM[table[b].detector], int(a), int(b), basis)


def _evidence(f: sf.Feature, series: sf.Series, qualities) -> tuple[list[str], list[str], list[str]]:
    """(hard, weak, codes): conditions that make the interval not evaluable, conditions that leave any
    coincidence insufficiently supported, and their codes (for the wording of each level). Read from the analyzer
    and the coverage diagnosis, never recomputed."""
    hard, weak, codes = [], [], []
    if f.klass == sf.NOT_EVALUABLE:
        hard.append("The analyser cannot assess this interval: " + " ".join(f.reasons or ["data missing."]))
        return hard, weak, ["no_evaluable"]
    if f.klass == sf.NO_FEATURE or f.kind not in KIND_NATURE:
        hard.append("The analyser flags no peak or valley in this interval, so there is nothing to "
                    "interpret. Not seeing a feature does not prove that a substance is absent: the spectrum "
                    "has no uncertainties.")
        return hard, weak, ["sin_caracteristica"]
    if len(f.detectors) > 1:
        codes.append("detectores")
        hard.append(f"The interval and its surroundings span detectors {', '.join(f'D{d}' for d in f.detectors)}: "
                    "a calibration or resolution jump between detectors produces peaks and valleys that are not "
                    "substances. It is not interpreted.")
    if f.klass == sf.VISIBLE:
        codes.append("visible")
        weak.append(f"«Visible» signal, not «quantifiable»: contrast of {abs(f.ratio):.1f} times the "
                    f"reference scatter (between {sf.Q_VISIBLE:g} and {sf.Q_QUANTIFIABLE:g}, or with some reservation from the analyser). "
                    "It is a descriptive threshold, not a statistical significance.")
    if f.caution_channels:
        codes.append("precaucion")
        weak.append("OVERFLOW or OUTLIER in channels " + ", ".join(map(str, f.caution_channels)) +
                    ": the value may not be reliable.")
    env = [c for c in list(f.env_left) + list(f.env_right)]
    env_caution = [c for c in env if series.caution[series.index(c)]]
    if env_caution:
        codes.append("entorno")
        weak.append("OVERFLOW or OUTLIER in the surroundings (channels " + ", ".join(map(str, env_caution)) +
                    "): the local continuum may be affected.")
    if qualities:
        lo, hi = f.trial_lo - sf.N_SIDE, f.trial_hi + sf.N_SIDE
        bloom = [q.canal for q in qualities if lo <= q.canal <= hi and q.valid_for_extraction and q.bloom]
        if bloom:
            codes.append("bloom")
            weak.append("Pixels with BLOOM in the aperture (channels " + ", ".join(map(str, bloom)) +
                        "): light spilling over from a bright source may contaminate the value.")
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
        m.reasons.append(f"Its expected position ({lam_obs:.3f} µm, channel {_channels(predicted)}) lies "
                         f"{dist:.3f} µm from the interval of the feature, less than one resolution element "
                         f"({element:.3f} µm): a line there would peak in the adjacent channel.")
        return m
    if not labelled:
        m.status = ORIENTATIVE
        m.reasons.append("It falls in the interval examined, which is not an assessable feature.")
        return m
    nature = KIND_NATURE[f.kind]
    if nature != ref.nature:
        m.status, m.z_range = OPPOSITE, None
        m.reasons.append(f"The reference is an {sr.NATURE_TEXT[ref.nature]} and here there is a {f.kind}: they are not "
                         "compatible.")
        return m
    if ref.fwhm_um is not None:
        span = ref.fwhm_um / table[predicted[0]].element_um
        if span >= 3 and f.width != "amplia":
            m.status, m.z_range = WIDTH, None
            m.reasons.append(f"The documented band is about {ref.fwhm_um:.2f} µm wide (≈ {span:.0f} channels) and here the "
                             f"feature spans {f.n_channels} channel{'s' if f.n_channels != 1 else ''} at half "
                             "height: an isolated minimum is not consistent with it.")
            return m
    m.reasons.append(f"Its expected position ({lam_obs:.3f} µm) falls inside the half-height interval "
                     f"({win.lo_um:.3f}–{win.hi_um:.3f} µm) and the type matches ({sr.NATURE_TEXT[ref.nature]}).")
    if ref.needs_absorption_model:
        m.status = MATCH_WEAK
        m.reasons.append("For an ice a coherent depression is needed against a reliable continuum that spans the "
                         "band, and an infrared source behind it. The local continuum of the analyser (three channels on each "
                         "side) does not guarantee it and V1 has no absorption model: indicative reference only.")
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
                              ["There is no interval examined."], limitations, ["sin_intervalo"])
    labelled = _labelled(feature)
    hard, weak, codes = _evidence(feature, series, None if feature.trial_lo is None else qualities)
    if feature.trial_lo is None:
        return Interpretation(series.label, NOT_EVALUABLE, feature, obs, None, redshift, [], [], [],
                              hard or ["Interval without channels."], limitations, codes or ["no_evaluable"])
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
        blockers.append("Several references fall in the same interval and SPHEREx does not separate them at this resolution: "
                        "all are kept as hypotheses.")
    if any(m.reference.needs_absorption_model for m in matches):
        codes.append("hielo")
    if matches and not redshift.known:
        codes.append("z_desconocido")
    return Interpretation(series.label, verdict, feature, obs, win, redshift, matches, others, orient, blockers,
                          limitations, codes)


def _limitations(series, f, table, rs: sr.Redshift, aperture_arcsec, resolution) -> list[str]:
    out = ["Matching in position and type does not identify a substance: it is a hypothesis consistent with the data.",
           "The cube spectrum is exploratory and has no uncertainties; «contrast / reference scatter» "
           "is descriptive, not a statistical significance. No probabilities are given: there is no calibrated model.",
           f"It is only compared with the {len(sr.REFERENCES)} references of the library ({sr.LIBRARY_VERSION}); the fact that "
           "none matches does not exclude other substances or processes."]
    if f is not None and _labelled(f):
        ch = table[f.canal]
        out.append(f"Resolution in channel {ch.canal} (D{ch.detector}): R = {ch.R:.0f}"
                   + ("" if ch.R_from_fits else " (estimated from the channel width; the FITS table does not give it)")
                   + f", one resolution element ≈ {ch.element_um:.3f} µm. Narrow lines are not resolved and "
                     "they are not required to be resolved; only their position is compared.")
    if rs.known:
        out.append(f"Desplazamiento al rojo z = {rs.z:.6f} ({rs.object_name}, {rs.source.upper()}): λ esperada = "
                   "λ en reposo × (1 + z). " + rs.note)
    else:
        out.append(rs.note)
    if aperture_arcsec:
        out.append(f"The aperture (radius {aperture_arcsec:.0f}″) mixes all the light it contains, minus the background "
                   "annulus: the interpretation describes that mixture, not a specific object inside it, and extended "
                   "emission that also fills the annulus is partly subtracted.")
    out.append("Compatibility window (declared conservative approximation, without the full spectral response of "
               "each pixel): half-height interval of the feature, widened only by the documented error "
               "of the band centre (1 nm in D1–D4, 10 nm in D5–D6; Hui et al. 2026).")
    return out


def interpret_features(series: sf.Series, features, **kw) -> list[Interpretation]:
    """One interpretation per feature labelled by the analyzer in this spectrum."""
    return [interpret(series, f, **kw) for f in features if _labelled(f)]


# extraction status of a channel without value, in words (same wording as spectral_cube.STATUS_TEXT)
_STATUS_TEXT = {"blank": "channel without data in DR1, BLANKCH", "no_data_aperture": "aperture with pixels without data, NHITS = 0",
                "no_background": "insufficient background in the annulus"}


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
            why = sorted({_STATUS_TEXT.get(series.status[series.index(c)], "no value") for c in chans})
            out.append(Coverage(ref, COV_NO_DATA, lam_obs, chans, None,
                                [f"Channel {_channels(chans)} has no value ({'; '.join(why)}): neither presence nor absence "
                                 "can be concluded."]))
            continue
        try:
            f = sf.inspect_channel(series, valued[0], features, scatter)
        except sf.FeatureInputError as err:
            out.append(Coverage(ref, COV_NO_DATA, lam_obs, chans, None, [str(err)]))
            continue
        if f.klass == sf.NOT_EVALUABLE:
            out.append(Coverage(ref, COV_NO_DATA, lam_obs, chans, f,
                                ["The analyser cannot assess that channel: " + " ".join(f.reasons)]))
        elif _labelled(f):
            out.append(Coverage(ref, COV_FEATURE, lam_obs, chans, f,
                                [f"{f.kind.capitalize()} {f.label.lower()} en {f.lam:.3f} µm."]))
        else:
            out.append(Coverage(ref, COV_NO_SIGNAL, lam_obs, chans, f,
                                ["The analyser flags nothing there. This does not prove absence: the spectrum has no "
                                 "uncertainties and the signal could be below its criteria."]))
    return out


def method_summary() -> dict:
    return {"motor": ENGINE_VERSION, "biblioteca": sr.LIBRARY_VERSION,
            "ventana": "half-height interval (WL_MIN–WL_MAX of its channels) ± band-centre error",
            "error_centro_banda_um": sr.BAND_CENTRE_ERROR_UM, "contigua": "within λ/R of the interval",
            "naturaleza": {"pico": sr.EMISSION, "valle": sr.ABSORPTION},
            "anchura": "a documented band of ≥ 3 resolution elements requires a «broad» feature",
            "hielos": "at most «insufficiently supported» (no absorption model in V1)",
            "z": "only from the curated table (NED, inside the D25 isophote) or from the user; never estimated",
            "veredictos": VERDICT_LABELS}
