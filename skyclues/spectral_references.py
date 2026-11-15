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
NATURE_TEXT = {EMISSION: "emisión", ABSORPTION: "absorción"}
FORM_TEXT = {BAND: "banda", LINE: "línea"}


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
NIST = Source("nist_asd", "Kramida, A., Ralchenko, Yu., Reader, J. y NIST ASD Team, NIST Atomic Spectra Database "
              "(v5), H I, consulta del 15-11-2026", "https://physics.nist.gov/asd",
              "Longitudes de onda de Ritz en el vacío: n = 9→5 (Pfund δ) 3,296991 µm y n = 5→4 (Brackett α) "
              "4,052269 µm; otras líneas de H I entre 3,2 y 4,1 µm (series de Pfund y Humphreys).")
BOOGERT = Source("boogert2015", "Boogert, A. C. A., Gerakines, P. A. y Whittet, D. C. B. 2015, ARA&A 53, 541, "
                 "«Observations of the Icy Universe»", "https://doi.org/10.1146/annurev-astro-082214-122348",
                 "Tabla de bandas de hielo: H₂O 3,0 µm (3333 cm⁻¹, FWHM ≈ 390 cm⁻¹); CO₂ 4,27 µm (2341 cm⁻¹, "
                 "FWHM ≈ 20 cm⁻¹); CO 4,67 µm (2141,3 cm⁻¹, FWHM 3–9 cm⁻¹). Las bandas se observan en absorción "
                 "frente a una fuente infrarroja de fondo o embebida; exceso de absorción entre 3,3 y 3,7 µm (ala "
                 "larga del hielo de agua). arXiv:1501.05317.")
HORA = Source("hora2026", "Hora, J. L., Noh, J. K., Melnick, G. J. et al. 2026, ApJ (aceptado), «SPHEREx Wide-Field "
              "Infrared Spectral Mapping of Interstellar Ices and Polycyclic Aromatic Hydrocarbons»",
              "https://arxiv.org/abs/2603.12390",
              "Con SPHEREx: hielos de H₂O (3,05 µm), CO₂ (4,27 µm) y CO (4,67 µm) y PAH de 3,28 µm (imagen "
              "3,24–3,34 µm). Profundidad óptica τ = ln(F_C/F_I) con continuo interpolado entre longitudes de onda "
              "vecinas; sin flujo de fondo detectable no se puede medir τ. La línea de H I de 3,297 µm contribuye "
              "al flujo del PAH (el artículo la llama Pfγ; según NIST es Pfδ). La banda de CO está insuficientemente "
              "muestreada. Efecto de bandeado del mosaico en el centro de la banda PAH (§II.1.2, tabla 1).")
VAN_DIEDENHOVEN = Source("vandiedenhoven2004", "van Diedenhoven, B., Peeters, E., Van Kerckhoven, C. et al. 2004, "
                         "ApJ 611, 928, «The profiles of the 3–12 micron PAH features»",
                         "https://arxiv.org/abs/astro-ph/0405098",
                         "La banda de 3,3 µm (estiramiento C–H aromático) varía poco de posición entre fuentes "
                         "(4–6,5 cm⁻¹); su anchura varía sin explicación conocida.")
TIELENS = Source("tielens2008", "Tielens, A. G. G. M. 2008, ARA&A 46, 289, «Interstellar Polycyclic Aromatic "
                 "Hydrocarbon Molecules»", "https://doi.org/10.1146/annurev.astro.46.060407.145211",
                 "Revisión general de la emisión de PAH excitada por fotones ultravioleta.")
VACCA = Source("vacca2011", "Vacca, W. D. y Sandell, G. 2011, espectro SpeX de 0,8–5 µm de TW Hya",
               "https://arxiv.org/abs/1102.0535",
               "Líneas de H I medidas: Pfβ 4,6538 µm y Hu ε 4,6727 µm, junto a la banda del hielo de CO.")
HUI = Source("hui2026", "Hui, H., Bock, J. et al. 2026, ApJS 284, 10, «Spectral response of SPHEREx»",
             "https://doi.org/10.3847/1538-4365/ae522c",
             "R = λ/Δλ con Δλ la integral de la respuesta normalizada a su pico; R de diseño 41,4 (bandas 1–3), "
             "35 (4), 110 (5) y 125 (6), medida al 5 %; respuesta no gaussiana y asimétrica cerca del divisor "
             "dicroico; centro de banda con error < 1 nm en las bandas 1–4 y < 10 nm en las 5–6.")
NED = Source("ned", "NASA/IPAC Extragalactic Database (NED), z heliocéntrico preferido, consulta del 15-11-2026",
             "https://ned.ipac.caltech.edu", "Desplazamiento al rojo y posición de las galaxias de la tabla curada.")
RC3 = Source("rc3", "de Vaucouleurs, G. et al. 1991, Third Reference Catalogue of Bright Galaxies (RC3), vía NED",
             "https://ned.ipac.caltech.edu", "Diámetro D25, cociente de ejes y ángulo de posición de cada galaxia.")
SPHEREX_CUBE = Source("spherex_cube", "SPHEREx DR1 All-Sky spectral cube, tabla SPECTRAL_CHANNELS del FITS "
                      "(doi:10.26131/IRSA679)", "https://doi.org/10.26131/IRSA679",
                      "λ central, límites WL_MIN–WL_MAX y R mediana de cada canal; se leen del propio archivo.")

INSTRUMENT_SOURCES = (HUI, SPHEREX_CUBE)
SHORT = {"nist_asd": "NIST ASD", "boogert2015": "Boogert et al. 2015", "hora2026": "Hora et al. 2026",
         "vandiedenhoven2004": "van Diedenhoven et al. 2004", "tielens2008": "Tielens 2008",
         "vacca2011": "Vacca y Sandell 2011", "hui2026": "Hui et al. 2026", "ned": "NED", "rc3": "RC3",
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
        id="h2o_hielo_3p0", name="Hielo de H₂O (3,0 µm)", plain_name="hielo de agua", carrier="H₂O sólida",
        transition="estiramiento O–H (varias componentes)", process="absorción por mantos de hielo sobre granos de polvo",
        family="hielo", lam_um=3.0, lam_range_um=(3.0, 3.05), nature=ABSORPTION, form=BAND, fwhm_um=_H2O_FWHM,
        width_note=f"FWHM ≈ 390 cm⁻¹ ≈ {_H2O_FWHM:.2f} µm (Boogert et al. 2015): abarca varios canales de D4. "
                   "Centro 3,0 µm en Boogert et al. 2015; 3,05 µm en Hora et al. 2026.",
        conditions=("Absorción: necesita una fuente de continuo infrarrojo detrás del hielo (estrella de fondo o "
                    "protoestrella embebida).",
                    "Una depresión coherente con la anchura de la banda frente a un continuo fiable a ambos lados; "
                    "nunca un mínimo aislado.",
                    "Medida de profundidad con un continuo que abarque la banda completa (τ = ln F_C/F_I)."),
        confounders=("Ala larga de la propia banda (3,3–3,7 µm) y, en la misma zona, la emisión de PAH de 3,3 µm.",
                     "La forma del continuo de la fuente y el continuo local del analizador, que usa solo tres "
                     "canales a cada lado y puede quedar dentro de la banda."),
        plain="El hielo de agua que cubre los granos de polvo frío absorbe esta luz cuando hay una fuente "
              "infrarroja detrás.",
        scientific="Banda ancha de estiramiento O–H del hielo de agua, el componente principal de los mantos de "
                   "hielo interestelares. Se observa en absorción contra un continuo infrarrojo.",
        sources=(BOOGERT, HORA), needs_absorption_model=True, short="H₂O hielo"),
    Reference(
        id="pah_3p3", name="PAH aromático (3,3 µm)", plain_name="compuestos aromáticos de carbono (PAH)",
        carrier="hidrocarburos aromáticos policíclicos (PAH)", transition="estiramiento C–H aromático",
        process="emisión de moléculas excitadas por fotones ultravioleta", family="pah", lam_um=3.29,
        lam_range_um=(3.28, 3.30), nature=EMISSION, form=BAND, fwhm_um=None,
        width_note="Posición 3,28–3,30 µm según la fuente (3,28 µm en Hora et al. 2026; ≈ 3,29 µm y variación de "
                   "4–6,5 cm⁻¹ en van Diedenhoven et al. 2004). No se usa una anchura: no queda documentada aquí y, "
                   "en cualquier caso, la banda es más estrecha que un canal de D4 (la imagen de Hora et al. 2026 "
                   "integra 3,24–3,34 µm).",
        conditions=("Emisión: necesita radiación ultravioleta que excite las moléculas (regiones de formación "
                    "estelar, nebulosas, galaxias con formación estelar).",
                    "Sin resolver a la resolución de SPHEREx: coincide en posición, no en perfil."),
        confounders=("H I Pfund δ (3,297 µm) cae en el mismo canal de D4 (Hora et al. 2026).",
                     "Rayado (bandeado) del mosaico del cubo cerca de líneas intensas, documentado en el centro de la "
                     "banda PAH (Hora et al. 2026).",
                     "Otros rasgos próximos de 3,4 µm caen en el canal contiguo: SPHEREx no separa 3,3 de 3,4 µm."),
        plain="Moléculas de carbono con forma de anillos que brillan en este color cuando las ilumina la luz "
              "ultravioleta de estrellas jóvenes.",
        scientific="Banda de emisión del estiramiento C–H aromático de los PAH, la más corta de la familia de bandas "
                   "infrarrojas de 3–12 µm.",
        sources=(VAN_DIEDENHOVEN, HORA, TIELENS), short="PAH 3,3"),
    Reference(
        id="hi_pfund_delta", name="H I Pfund δ (3,297 µm)", plain_name="hidrógeno ionizado (línea Pfund δ)",
        carrier="hidrógeno atómico", transition="n = 9 → 5 (Pfund δ)",
        process="emisión por recombinación en gas ionizado", family="hidrogeno", lam_um=3.296991,
        lam_range_um=(3.296991, 3.296991), nature=EMISSION, form=LINE, fwhm_um=None,
        width_note="Línea mucho más estrecha que un canal: sin resolver en SPHEREx. No se exige que se resuelva.",
        conditions=("Gas ionizado (regiones H II, nebulosas planetarias, acreción o vientos de estrellas jóvenes).",
                    "Línea débil de la serie de Pfund: suele acompañarse de líneas más intensas de H I (p. ej. "
                    "Brα), lo que V1 no comprueba."),
        confounders=("La banda PAH de 3,3 µm cae en el mismo canal de D4.",
                     "Otras líneas de H I próximas (series de Pfund y Humphreys) y el rayado del mosaico."),
        plain="Luz que emite el hidrógeno cuando se recombina en gas ionizado, por ejemplo cerca de estrellas "
              "calientes.",
        scientific="Línea de recombinación de H I, transición n = 9 → 5. Longitud de onda de Ritz en el vacío "
                   "(NIST ASD).",
        sources=(NIST, HORA), short="Pfδ"),
    Reference(
        id="hi_brackett_alpha", name="H I Brackett α (4,052 µm)", plain_name="hidrógeno ionizado (línea Brackett α)",
        carrier="hidrógeno atómico", transition="n = 5 → 4 (Brackett α)",
        process="emisión por recombinación en gas ionizado", family="hidrogeno", lam_um=4.052269,
        lam_range_um=(4.052269, 4.052269), nature=EMISSION, form=LINE, fwhm_um=None,
        width_note="Línea mucho más estrecha que un canal de D5: sin resolver. No se exige que se resuelva.",
        conditions=("Gas ionizado (regiones H II, nebulosas planetarias, acreción o vientos de estrellas jóvenes).",),
        confounders=("Líneas débiles de la serie de Humphreys cercanas (p. ej. n = 14 → 6 a 4,0209 µm, NIST).",
                     "Rayado del mosaico del cubo cerca de líneas intensas como Brα."),
        plain="Luz que emite el hidrógeno cuando se recombina en gas ionizado, por ejemplo cerca de estrellas "
              "calientes.",
        scientific="Línea de recombinación de H I, transición n = 5 → 4. Longitud de onda de Ritz en el vacío "
                   "(NIST ASD).",
        sources=(NIST, HORA), short="Brα"),
    Reference(
        id="co2_hielo_4p27", name="Hielo de CO₂ (4,27 µm)", plain_name="hielo de dióxido de carbono",
        carrier="CO₂ sólido", transition="estiramiento asimétrico C=O",
        process="absorción por mantos de hielo sobre granos de polvo", family="hielo", lam_um=4.27,
        lam_range_um=(4.27, 4.27), nature=ABSORPTION, form=BAND, fwhm_um=_CO2_FWHM,
        width_note=f"FWHM ≈ 20 cm⁻¹ ≈ {_CO2_FWHM:.3f} µm (Boogert et al. 2015): del orden de un canal de D5.",
        conditions=("Absorción: necesita una fuente de continuo infrarrojo detrás del hielo.",
                    "Un continuo fiable a ambos lados de la banda; sin flujo de fondo detectable no se mide su "
                    "profundidad (Hora et al. 2026)."),
        confounders=("Al ocupar un solo canal, un canal bajo no se distingue de un valor atípico del mosaico.",),
        plain="El hielo de dióxido de carbono sobre granos de polvo frío absorbe esta luz cuando hay una fuente "
              "infrarroja detrás.",
        scientific="Banda de estiramiento del hielo de CO₂, observada en absorción contra un continuo infrarrojo.",
        sources=(BOOGERT, HORA), needs_absorption_model=True, short="CO₂ hielo"),
    Reference(
        id="co_hielo_4p67", name="Hielo de CO (4,67 µm)", plain_name="hielo de monóxido de carbono",
        carrier="CO sólido", transition="estiramiento C≡O (varias componentes)",
        process="absorción por mantos de hielo sobre granos de polvo", family="hielo", lam_um=4.67,
        lam_range_um=(4.67, 4.67), nature=ABSORPTION, form=BAND, fwhm_um=_CO_FWHM[1],
        width_note=f"FWHM 3–9 cm⁻¹ ≈ {_CO_FWHM[0]:.3f}–{_CO_FWHM[1]:.3f} µm (Boogert et al. 2015): más estrecha que "
                   "un canal de D6 y muestreada de forma insuficiente (Hora et al. 2026). Su profundidad se diluye en "
                   "el canal.",
        conditions=("Absorción: necesita una fuente de continuo infrarrojo detrás del hielo.",
                    "Un continuo fiable a ambos lados de la banda."),
        confounders=("Las líneas de emisión de H I Pfβ (4,6538 µm) y Hu ε (4,6727 µm) caen en los mismos canales y "
                     "pueden rellenar la banda (Vacca y Sandell 2011).",),
        plain="El hielo de monóxido de carbono, que se forma en el polvo más frío y denso, absorbe esta luz cuando "
              "hay una fuente infrarroja detrás.",
        scientific="Banda de estiramiento del hielo de CO, estrecha; observada en absorción contra un continuo "
                   "infrarrojo.",
        sources=(BOOGERT, HORA, VACCA), needs_absorption_model=True, short="CO hielo"),
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
                     note="Sin desplazamiento al rojo documentado para esta posición: se compara en reposo (z = 0). "
                          "Un z distinto movería las referencias; nunca se estima a partir de una coincidencia.")


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
                    note=f"z heliocéntrico de {g.ned_name} en NED ({g.z:.6f}, indicador {g.z_flag}); la posición está a "
                         f"{sep:.0f}″ del centro, dentro de su isofota D25 (RC3). Se añade ±{sigma:.4f} por movimientos "
                         f"internos de hasta {INTERNAL_VELOCITY_KMS:.0f} km/s (supuesto).",
                    references=REDSHIFT_SOURCES)


def user_redshift(z: float, note: str = "") -> Redshift:
    """A redshift given by the user (kept apart from the curated table; its source is the user)."""
    if not math.isfinite(z) or z <= -1:
        raise ValueError("z debe ser un número finito mayor que −1.")
    return Redshift(float(z), 0.0, "usuario", note=note or "z introducido por el usuario; SkyClues no lo comprueba.")
