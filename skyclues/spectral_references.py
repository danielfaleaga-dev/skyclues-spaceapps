"""Registry of documented spectroscopic references for the spectral interpreter (V1).

Data only: no Streamlit, no network, no inference. Every value comes from a cited primary or review source
(``Source``); nothing is fitted or learnt. Widths are stored only where a source documents them; profiles are
never invented. Wavelengths are rest-frame vacuum values in micrometres.

Also holds the small, curated table of galaxies whose redshift is applied to a spectrum (``Galaxy``): NED
heliocentric redshift and the RC3 D25 isophote, used only to decide whether a position lies inside the galaxy.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

LIBRARY_VERSION = "skyclues-referencias 1.0 (2026-11-15)"
CONSULTED = "2026-11-15"

EMISSION, ABSORPTION = "emision", "absorcion"
BAND, LINE = "banda", "linea"
NATURE_TEXT = {EMISSION: "emission", ABSORPTION: "absorption"}
FORM_TEXT = {BAND: "banda", LINE: "line"}


@dataclass(frozen=True)
class Source:
    key: str
    citation: str
    url: str
    used_for: str                     # what was taken from it (what the reader can check there)


@dataclass(frozen=True)
class Reference:
    id: str                           # stable identifier, never reused
    name: str                         # scientific name
    plain_name: str                   # Sencillo wording
    carrier: str                      # substance or species
    transition: str                   # transition or vibrational mode
    process: str
    family: str                       # "hielo" | "pah" | "hidrogeno"
    lam_um: float                     # nominal rest wavelength (vacuum)
    lam_range_um: tuple[float, float]  # documented range of the peak position (lam_um, lam_um if a single value)
    nature: str                       # EMISSION | ABSORPTION
    form: str                         # BAND | LINE
    fwhm_um: float | None             # documented FWHM; None if no source gives it
    width_note: str
    conditions: tuple[str, ...]       # what must hold for the interpretation to make sense
    confounders: tuple[str, ...]      # what else can produce the same signal
    plain: str                        # one-sentence explanation (Sencillo)
    scientific: str                   # explanation (Científico)
    sources: tuple[Source, ...]
    needs_absorption_model: bool = False   # V1 cannot assess its depth against a reliable band continuum
    short: str = ""                   # label for the reference marks of the plot

    def to_dict(self) -> dict:
        return {"id": self.id, "nombre": self.name, "portador": self.carrier, "transicion": self.transition,
                "proceso": self.process, "lambda_reposo_um": self.lam_um, "intervalo_documentado_um": list(self.lam_range_um),
                "naturaleza": self.nature, "forma": self.form, "fwhm_um": self.fwhm_um, "anchura": self.width_note,
                "condiciones": list(self.conditions), "confusiones": list(self.confounders),
                "fuentes": [{"cita": s.citation, "url": s.url, "uso": s.used_for} for s in self.sources]}


def cm1_to_um(width_cm1: float, lam_um: float) -> float:
    """A width in wavenumber (cm⁻¹) at ``lam_um``, in µm: Δλ = λ² Δσ (λ in µm, σ in cm⁻¹, factor 10⁻⁴)."""
    return lam_um ** 2 * width_cm1 * 1e-4


# ----------------------------------------------------------------------------- sources
NIST = Source("nist_asd", "Kramida, A., Ralchenko, Yu., Reader, J. and NIST ASD Team, NIST Atomic Spectra Database "
              "(v5), H I, queried on 15-11-2026", "https://physics.nist.gov/asd",
              "Ritz wavelengths in vacuum: n = 9→5 (Pfund δ) 3.296991 µm and n = 5→4 (Brackett α) "
              "4.052269 µm; other H I lines between 3.2 and 4.1 µm (Pfund and Humphreys series).")
BOOGERT = Source("boogert2015", "Boogert, A. C. A., Gerakines, P. A. y Whittet, D. C. B. 2015, ARA&A 53, 541, "
                 "«Observations of the Icy Universe»", "https://doi.org/10.1146/annurev-astro-082214-122348",
                 "Table of ice bands: H₂O 3.0 µm (3333 cm⁻¹, FWHM ≈ 390 cm⁻¹); CO₂ 4.27 µm (2341 cm⁻¹, "
                 "FWHM ≈ 20 cm⁻¹); CO 4.67 µm (2141.3 cm⁻¹, FWHM 3–9 cm⁻¹). The bands are observed in absorption "
                 "against a background or embedded infrared source; excess absorption between 3.3 and 3.7 µm (long "
                 "wing of water ice). arXiv:1501.05317.")
HORA = Source("hora2026", "Hora, J. L., Noh, J. K., Melnick, G. J. et al. 2026, ApJ (accepted), «SPHEREx Wide-Field "
              "Infrared Spectral Mapping of Interstellar Ices and Polycyclic Aromatic Hydrocarbons»",
              "https://arxiv.org/abs/2603.12390",
              "With SPHEREx: ices of H₂O (3.05 µm), CO₂ (4.27 µm) and CO (4.67 µm) and the PAH at 3.28 µm (image "
              "3.24–3.34 µm). Optical depth τ = ln(F_C/F_I) with a continuum interpolated between neighbouring "
              "wavelengths; without a detectable background flux τ cannot be measured. The H I line at 3.297 µm contributes "
              "to the PAH flux (the paper calls it Pfγ; according to NIST it is Pfδ). The CO band is undersampled. "
              "Striping effect of the mosaic at the centre of the PAH band (§II.1.2, table 1).")
VAN_DIEDENHOVEN = Source("vandiedenhoven2004", "van Diedenhoven, B., Peeters, E., Van Kerckhoven, C. et al. 2004, "
                         "ApJ 611, 928, «The profiles of the 3–12 micron PAH features»",
                         "https://arxiv.org/abs/astro-ph/0405098",
                         "The 3.3 µm band (aromatic C–H stretch) varies little in position between sources "
                         "(4–6.5 cm⁻¹); its width varies for no known reason.")
TIELENS = Source("tielens2008", "Tielens, A. G. G. M. 2008, ARA&A 46, 289, «Interstellar Polycyclic Aromatic "
                 "Hydrocarbon Molecules»", "https://doi.org/10.1146/annurev.astro.46.060407.145211",
                 "General review of PAH emission excited by ultraviolet photons.")
VACCA = Source("vacca2011", "Vacca, W. D. & Sandell, G. 2011, SpeX 0.8–5 µm spectrum of TW Hya",
               "https://arxiv.org/abs/1102.0535",
               "Measured H I lines: Pfβ 4.6538 µm and Hu ε 4.6727 µm, next to the CO ice band.")
HUI = Source("hui2026", "Hui, H., Bock, J. et al. 2026, ApJS 284, 10, «Spectral response of SPHEREx»",
             "https://doi.org/10.3847/1538-4365/ae522c",
             "R = λ/Δλ with Δλ the integral of the response normalised to its peak; design R 41.4 (bands 1–3), "
             "35 (4), 110 (5) and 125 (6), measured to 5 %; non-Gaussian, asymmetric response near the dichroic "
             "splitter; band centre with error < 1 nm in bands 1–4 and < 10 nm in 5–6.")
NED = Source("ned", "NASA/IPAC Extragalactic Database (NED), preferred heliocentric z, queried on 15-11-2026",
             "https://ned.ipac.caltech.edu", "Redshift and position of the galaxies in the curated table.")
RC3 = Source("rc3", "de Vaucouleurs, G. et al. 1991, Third Reference Catalogue of Bright Galaxies (RC3), via NED",
             "https://ned.ipac.caltech.edu", "D25 diameter, axis ratio and position angle of each galaxy.")
SPHEREX_CUBE = Source("spherex_cube", "SPHEREx DR1 All-Sky spectral cube, SPECTRAL_CHANNELS table of the FITS "
                      "(doi:10.26131/IRSA679)", "https://doi.org/10.26131/IRSA679",
                      "Central λ, WL_MIN–WL_MAX limits and median R of each channel; they are read from the file itself.")

INSTRUMENT_SOURCES = (HUI, SPHEREX_CUBE)
SHORT = {"nist_asd": "NIST ASD", "boogert2015": "Boogert et al. 2015", "hora2026": "Hora et al. 2026",
         "vandiedenhoven2004": "van Diedenhoven et al. 2004", "tielens2008": "Tielens 2008",
         "vacca2011": "Vacca & Sandell 2011", "hui2026": "Hui et al. 2026", "ned": "NED", "rc3": "RC3",
         "spherex_cube": "SPHEREx DR1 (SPECTRAL_CHANNELS)"}


def short(s: Source) -> str:
    """Short citation (author and year) of a source."""
    return SHORT.get(s.key, s.key)

# Band-centre accuracy (Hui et al. 2026): added to the compatibility window on each side.
BAND_CENTRE_ERROR_UM = {1: 0.001, 2: 0.001, 3: 0.001, 4: 0.001, 5: 0.010, 6: 0.010}

# ----------------------------------------------------------------------------- the six references
_H2O_FWHM = cm1_to_um(390, 3.0)
_CO2_FWHM = cm1_to_um(20, 4.27)
_CO_FWHM = (cm1_to_um(3, 4.67), cm1_to_um(9, 4.67))

REFERENCES: tuple[Reference, ...] = (
    Reference(
        id="h2o_hielo_3p0", name="H₂O ice (3.0 µm)", plain_name="water ice", carrier="Solid H₂O",
        transition="O–H stretch (several components)", process="absorption by ice mantles on dust grains",
        family="hielo", lam_um=3.0, lam_range_um=(3.0, 3.05), nature=ABSORPTION, form=BAND, fwhm_um=_H2O_FWHM,
        width_note=f"FWHM ≈ 390 cm⁻¹ ≈ {_H2O_FWHM:.2f} µm (Boogert et al. 2015): it spans several D4 channels. "
                   "Centre at 3.0 µm in Boogert et al. 2015; 3.05 µm in Hora et al. 2026.",
        conditions=("Absorption: it needs an infrared continuum source behind the ice (background star or "
                    "embedded protostar).",
                    "A depression consistent with the width of the band against a reliable continuum on both sides; "
                    "never an isolated minimum.",
                    "Depth measurement with a continuum that spans the whole band (τ = ln F_C/F_I)."),
        confounders=("Long wing of the band itself (3.3–3.7 µm) and, in the same area, the 3.3 µm PAH emission.",
                     "The shape of the continuum of the source and the local continuum of the analyser, which uses only three "
                     "channels on each side and may end up inside the band."),
        plain="The water ice that covers cold dust grains absorbs this light when there is an infrared "
              "source behind it.",
        scientific="Broad O–H stretching band of water ice, the main component of interstellar ice "
                   "mantles. It is observed in absorption against an infrared continuum.",
        sources=(BOOGERT, HORA), needs_absorption_model=True, short="H₂O ice"),
    Reference(
        id="pah_3p3", name="Aromatic PAH (3.3 µm)", plain_name="aromatic carbon compounds (PAH)",
        carrier="polycyclic aromatic hydrocarbons (PAH)", transition="aromatic C–H stretch",
        process="emission from molecules excited by ultraviolet photons", family="pah", lam_um=3.29,
        lam_range_um=(3.28, 3.30), nature=EMISSION, form=BAND, fwhm_um=None,
        width_note="Position 3.28–3.30 µm depending on the source (3.28 µm in Hora et al. 2026; ≈ 3.29 µm and a variation of "
                   "4–6.5 cm⁻¹ in van Diedenhoven et al. 2004). No width is used: it is not documented here and, "
                   "in any case, the band is narrower than a D4 channel (the Hora et al. 2026 image "
                   "integrates 3.24–3.34 µm).",
        conditions=("Emission: it needs ultraviolet radiation to excite the molecules (star-forming "
                    "regions, nebulae, star-forming galaxies).",
                    "Unresolved at SPHEREx resolution: it matches in position, not in profile."),
        confounders=("H I Pfund δ (3.297 µm) falls in the same D4 channel (Hora et al. 2026).",
                     "Striping (banding) of the cube mosaic near intense lines, documented at the centre of the "
                     "PAH band (Hora et al. 2026).",
                     "Other nearby 3.4 µm features fall in the adjacent channel: SPHEREx does not separate 3.3 from 3.4 µm."),
        plain="Ring-shaped carbon molecules that glow at this colour when illuminated by the ultraviolet "
              "light of young stars.",
        scientific="Emission band of the aromatic C–H stretch of PAHs, the shortest of the family of 3–12 µm "
                   "infrared bands.",
        sources=(VAN_DIEDENHOVEN, HORA, TIELENS), short="PAH 3,3"),
    Reference(
        id="hi_pfund_delta", name="H I Pfund δ (3,297 µm)", plain_name="ionised hydrogen (Pfund δ line)",
        carrier="atomic hydrogen", transition="n = 9 → 5 (Pfund δ)",
        process="recombination emission in ionised gas", family="hidrogeno", lam_um=3.296991,
        lam_range_um=(3.296991, 3.296991), nature=EMISSION, form=LINE, fwhm_um=None,
        width_note="Line much narrower than a channel: unresolved in SPHEREx. It is not required to be resolved.",
        conditions=("Ionised gas (H II regions, planetary nebulae, accretion or winds from young stars).",
                    "Weak line of the Pfund series: it is usually accompanied by more intense H I lines (e.g. "
                    "Brα), which V1 does not check."),
        confounders=("The 3.3 µm PAH band falls in the same D4 channel.",
                     "Other nearby H I lines (Pfund and Humphreys series) and the striping of the mosaic."),
        plain="Light that hydrogen emits when it recombines in ionised gas, for example near hot "
              "stars.",
        scientific="H I recombination line, transition n = 9 → 5. Ritz wavelength in vacuum "
                   "(NIST ASD).",
        sources=(NIST, HORA), short="Pfδ"),
    Reference(
        id="hi_brackett_alpha", name="H I Brackett α (4,052 µm)", plain_name="ionised hydrogen (Brackett α line)",
        carrier="atomic hydrogen", transition="n = 5 → 4 (Brackett α)",
        process="recombination emission in ionised gas", family="hidrogeno", lam_um=4.052269,
        lam_range_um=(4.052269, 4.052269), nature=EMISSION, form=LINE, fwhm_um=None,
        width_note="Line much narrower than a D5 channel: unresolved. It is not required to be resolved.",
        conditions=("Ionised gas (H II regions, planetary nebulae, accretion or winds from young stars).",),
        confounders=("Nearby weak lines of the Humphreys series (e.g. n = 14 → 6 at 4.0209 µm, NIST).",
                     "Striping of the cube mosaic near intense lines such as Brα."),
        plain="Light that hydrogen emits when it recombines in ionised gas, for example near hot "
              "stars.",
        scientific="H I recombination line, transition n = 5 → 4. Ritz wavelength in vacuum "
                   "(NIST ASD).",
        sources=(NIST, HORA), short="Brα"),
    Reference(
        id="co2_hielo_4p27", name="CO₂ ice (4.27 µm)", plain_name="carbon dioxide ice",
        carrier="Solid CO₂", transition="asymmetric C=O stretch",
        process="absorption by ice mantles on dust grains", family="hielo", lam_um=4.27,
        lam_range_um=(4.27, 4.27), nature=ABSORPTION, form=BAND, fwhm_um=_CO2_FWHM,
        width_note=f"FWHM ≈ 20 cm⁻¹ ≈ {_CO2_FWHM:.3f} µm (Boogert et al. 2015): of the order of one D5 channel.",
        conditions=("Absorption: it needs an infrared continuum source behind the ice.",
                    "A reliable continuum on both sides of the band; without a detectable background flux its "
                    "depth is not measured (Hora et al. 2026)."),
        confounders=("Since it occupies a single channel, a low channel cannot be told apart from an outlier of the mosaic.",),
        plain="Carbon dioxide ice on cold dust grains absorbs this light when there is an infrared "
              "source behind it.",
        scientific="Stretching band of CO₂ ice, observed in absorption against an infrared continuum.",
        sources=(BOOGERT, HORA), needs_absorption_model=True, short="CO₂ ice"),
    Reference(
        id="co_hielo_4p67", name="CO ice (4.67 µm)", plain_name="carbon monoxide ice",
        carrier="Solid CO", transition="C≡O stretch (several components)",
        process="absorption by ice mantles on dust grains", family="hielo", lam_um=4.67,
        lam_range_um=(4.67, 4.67), nature=ABSORPTION, form=BAND, fwhm_um=_CO_FWHM[1],
        width_note=f"FWHM 3–9 cm⁻¹ ≈ {_CO_FWHM[0]:.3f}–{_CO_FWHM[1]:.3f} µm (Boogert et al. 2015): narrower than "
                   "a D6 channel and insufficiently sampled (Hora et al. 2026). Its depth is diluted in "
                   "the channel.",
        conditions=("Absorption: it needs an infrared continuum source behind the ice.",
                    "A reliable continuum on both sides of the band."),
        confounders=("The H I emission lines Pfβ (4.6538 µm) and Hu ε (4.6727 µm) fall in the same channels and "
                     "may fill in the band (Vacca & Sandell 2011).",),
        plain="Carbon monoxide ice, which forms on the coldest and densest dust, absorbs this light when "
              "there is an infrared source behind it.",
        scientific="Stretching band of CO ice, narrow; observed in absorption against an infrared "
                   "continuum.",
        sources=(BOOGERT, HORA, VACCA), needs_absorption_model=True, short="CO ice"),
)
BY_ID = {r.id: r for r in REFERENCES}


def library_summary() -> dict:
    return {"version": LIBRARY_VERSION, "consulta": CONSULTED, "referencias": [r.to_dict() for r in REFERENCES]}


# ----------------------------------------------------------------------------- redshift of known galaxies
INTERNAL_VELOCITY_KMS = 300.0      # assumed bound on internal motions (rotation) added to the systemic z
C_KMS = 299792.458


@dataclass(frozen=True)
class Galaxy:
    name: str
    ned_name: str
    ra_deg: float
    dec_deg: float
    z: float
    z_flag: str
    d25_arcsec: float                 # RC3 major-axis isophotal diameter D25
    axis_ratio: float                 # b/a = 10**-log(a/b), RC3
    pa_deg: float | None              # position angle of the major axis, east of north (None: not given)

    def inside(self, ra: float, dec: float) -> tuple[bool, float]:
        """Whether (ra, dec) lies within the D25 ellipse, and its separation from the centre (arcsec).
        Without a position angle, the circle of the semi-minor axis is used (never a larger area)."""
        d = math.radians(dec)
        e = (ra - self.ra_deg) * math.cos(d) * 3600.0          # east offset (arcsec), small-angle
        n = (dec - self.dec_deg) * 3600.0
        sep = math.hypot(e, n)
        a = self.d25_arcsec / 2
        b = a * self.axis_ratio
        if self.pa_deg is None:
            return sep <= b, sep
        t = math.radians(self.pa_deg)
        major = e * math.sin(t) + n * math.cos(t)
        minor = e * math.cos(t) - n * math.sin(t)
        return (major / a) ** 2 + (minor / b) ** 2 <= 1.0, sep


GALAXIES: tuple[Galaxy, ...] = (
    Galaxy("Arp 220", "ARP 220", 233.73836, 23.50368, 0.018398, "SLS", 90.8, 10 ** -0.09, None),
    Galaxy("M51a (NGC 5194)", "MESSIER 051a", 202.46963, 47.19521, 0.001745, "SLS", 673.2, 10 ** -0.21, 163.0),
    Galaxy("M51b (NGC 5195)", "MESSIER 051b", 202.49808, 47.26617, 0.001518, "S1L", 345.3, 10 ** -0.10, 79.0),
    Galaxy("M101 (NGC 5457)", "MESSIER 101", 210.80227, 54.34895, 0.000804, "S1L", 1730.4, 10 ** -0.03, None),
    Galaxy("M82 (NGC 3034)", "MESSIER 082", 148.97050, 69.67948, 0.000897, "UUN", 673.2, 10 ** -0.42, 65.0),
)
REDSHIFT_SOURCES = (NED, RC3)


@dataclass(frozen=True)
class Redshift:
    """The redshift applied to one spectrum position, or why there is none."""

    z: float | None
    sigma: float                      # uncertainty used in the window (internal motions); 0 when z is None
    source: str                       # "ned" | "usuario" | "desconocido"
    object_name: str | None = None
    separation_arcsec: float | None = None
    note: str = ""
    references: tuple[Source, ...] = field(default_factory=tuple)

    @property
    def known(self) -> bool:
        return self.z is not None

    def to_dict(self) -> dict:
        return {"z": self.z, "sigma_z": self.sigma, "fuente": self.source, "objeto": self.object_name,
                "separacion_arcsec": self.separation_arcsec, "nota": self.note}


UNKNOWN_Z = Redshift(None, 0.0, "desconocido",
                     note="No documented redshift for this position: it is compared at rest (z = 0). "
                          "A different z would shift the references; it is never estimated from a coincidence.")


def redshift_at(ra: float, dec: float) -> Redshift:
    """NED redshift of the curated galaxy whose D25 ellipse contains the position (the closest one, relative to
    its size, if several do). Any other position: unknown z. Never estimated from the spectrum."""
    best = None
    for g in GALAXIES:
        ok, sep = g.inside(ra, dec)
        if ok:
            score = sep / (g.d25_arcsec / 2)
            if best is None or score < best[0]:
                best = (score, g, sep)
    if best is None:
        return UNKNOWN_Z
    _, g, sep = best
    sigma = INTERNAL_VELOCITY_KMS / C_KMS
    return Redshift(g.z, sigma, "ned", g.name, sep,
                    note=f"Heliocentric z of {g.ned_name} in NED ({g.z:.6f}, flag {g.z_flag}); the position is "
                         f"{sep:.0f}″ from the centre, inside its D25 isophote (RC3). ±{sigma:.4f} is added for "
                         f"internal motions of up to {INTERNAL_VELOCITY_KMS:.0f} km/s (assumption).",
                    references=REDSHIFT_SOURCES)


def user_redshift(z: float, note: str = "") -> Redshift:
    """A redshift given by the user (kept apart from the curated table; its source is the user)."""
    if not math.isfinite(z) or z <= -1:
        raise ValueError("z must be a finite number greater than −1.")
    return Redshift(float(z), 0.0, "usuario", note=note or "z entered by the user; SkyClues does not check it.")
