"""Display translation of the Spanish text stored inside saved results.

The saved JSON files under ``results/`` are scientific records and are never modified. They were written
with Spanish explanatory text (reasons, criteria, notes), which the interface now shows in English. This
module translates those strings when a saved result is LOADED, in memory only: an exact-match table plus a
few patterns for sentences with variable numbers. Numbers, identifiers and data are carried over unchanged;
a string that matches nothing is returned as it is (never guessed).
"""
from __future__ import annotations

import re

EXACT = {
    "SIMBAD 2026-11-14 (galaxia: sin movimiento propio medible)": "SIMBAD 2026-11-14 (galaxy: no measurable proper motion)",
    "Sin movimiento propio en el catálogo: se usa la posición de catálogo para todas las fechas (correcto para objetos lejanos; incorrecto si el objeto se mueve).":
        "No proper motion in the catalogue: the catalogue position is used for all dates (correct for distant objects; incorrect if the object moves).",
    "posición de catálogo (sin movimiento propio)": "catalogue position (no proper motion)",
    "coordenadas introducidas (sin astrometría: se usan para todas las fechas)": "coordinates entered (no astrometry: they are used for all dates)",
    "Mismo detector en todas las épocas": "Same detector in all epochs",
    "Fechas distintas (separación mínima entre épocas consecutivas)": "Distinct dates (minimum separation between consecutive epochs)",
    "Mismo canal efectivo en el objetivo (dispersión de λ entre todas las épocas)": "Same effective channel at the target (λ spread across all epochs)",
    "≤ 0.25 (aviso ≤ 0.5; rechazo por encima)": "≤ 0.25 (warning ≤ 0.5; rejection above)",
    "Dispersión espectral máxima en la región común": "Maximum spectral spread in the common region",
    "≤ 0.25 en toda la región (aviso ≤ 0.5; rechazo por encima)": "≤ 0.25 over the whole region (warning ≤ 0.5; rejection above)",
    "≤ 0.25 en toda la región (aviso hasta 0.5)": "≤ 0.25 over the whole region (warning up to 0.5)",
    "Cobertura válida común a TODAS las épocas": "Valid coverage common to ALL epochs",
    "garantía del archivo": "archive guarantee",
    "efectiva": "effective",
    "Astrometría fina válida en todas (FINAST)": "Valid fine astrometry in all (FINAST)",
    "Astrometría fina válida en todas (FINAST = 0)": "Valid fine astrometry in all (FINAST = 0)",
    "todas 0 (1 = solución parcial: aviso; ≥ 2 = no utilizable: rechazo)": "all 0 (1 = partial solution: warning; ≥ 2 = unusable: rejection)",
    "Mismo procesamiento (colección y versión de software)": "Same processing (collection and software version)",
    "una colección y una versión": "one collection and one version",
    "Saturación en el campo (OVERFLOW/NONLINEAR), peor época": "Saturation in the field (OVERFLOW/NONLINEAR), worst epoch",
    "Detectores 1–2: posible contaminación por airglow de He I (HE_AIRGLOW_CONT).": "Detectors 1–2: possible He I airglow contamination (HE_AIRGLOW_CONT).",
    "admisible y S5 pass; cobertura común ≥ (mejor cobertura − 15%); entre ellas: menos avisos, después más épocas, más cobertura y más intervalo":
        "admissible and S5 pass; common coverage ≥ (best coverage − 15%); among those: fewer warnings, then more epochs, more coverage and longer interval",
    "auditoría independiente: astrometría por época (SC-01), rechazo espectral (SC-02), FLAGS oficiales y bits sin definir (SC-06), FINAST (SC-11)":
        "independent audit: per-epoch astrometry (SC-01), spectral rejection (SC-02), official FLAGS and undefined bits (SC-06), FINAST (SC-11)",
    "los mismos recortes (SHA-256 comprobado); centro del campo sin cambios": "the same cutouts (SHA-256 verified); field centre unchanged",
    "ningún cambio de estado": "no change of state",
    "posición calculada (movimiento propio + paralaje) en la época mediana de las observaciones del archivo, redondeada a 0.1 años":
        "position calculated (proper motion + parallax) at the median epoch of the archive observations, rounded to 0.1 years",
    "Sin velocidad radial: se desprecia la aceleración de perspectiva (efecto mínimo en pocas décadas).":
        "No radial velocity: perspective acceleration is neglected (minimal effect over a few decades).",
    "Otra fuente comparable dentro del radio de búsqueda: posible confusión.": "Another comparable source within the search radius: possible confusion.",
    "Núcleo saturado y menos de tres medidas individuales por temporada: no se puede estimar empíricamente el sesgo de un ajuste con las alas de la PSF.":
        "Saturated core and fewer than three individual measurements per season: the bias of a fit using the PSF wings cannot be estimated empirically.",
    "Imágenes individuales SPHEREx L2 originales (IMAGE − ZODI, VARIANCE, FLAGS, EPSF, WCS). Sin cubo, sin remuestreo, sin capturas.":
        "Original individual SPHEREx L2 images (IMAGE − ZODI, VARIANCE, FLAGS, EPSF, WCS). No cube, no resampling, no screenshots.",
    "Gaia DR3 (movimiento propio aplicado; punto cero libre por estrella)": "Gaia DR3 (proper motion applied; free zero point per star)",
    "Cada estrella de referencia se registra sin sí misma (leave-one-out) y se mide con el mismo ajuste conjunto por temporada que el objetivo. Debe seguir su trayectoria Gaia (desplazamiento residual nulo). El factor de calibración ≥ 1 lleva la mediana de sus χ² (2 g.l.) a 1.386.":
        "Each reference star is registered without itself (leave-one-out) and measured with the same joint per-season fit as the target. It must follow its Gaia trajectory (null residual displacement). A calibration factor ≥ 1 brings the median of its χ² (2 d.o.f.) to 1.386.",
    "Predicción calculada con la astrometría del catálogo (incluye paralaje si existe). Solo se compara al final; no interviene en la búsqueda, el ajuste ni la decisión.":
        "Prediction calculated with the catalogue astrometry (includes parallax if it exists). It is only compared at the end; it plays no part in the search, the fit or the decision.",
    "el χ² del ajuste no tiene un mínimo definido (curvatura no positiva; típico de un núcleo saturado o enmascarado)":
        "the fit χ² has no defined minimum (non-positive curvature; typical of a saturated or masked core)",
    "Misma llamada que la pestaña «Buscar algo que se mueve» (ejemplo WISE 0855, base ampliada)":
        "Same call as the “Find something that moves” tab (WISE 0855 example, extended baseline)",
}

# (pattern, replacement) for sentences that carry numbers; applied with re.fullmatch
PATTERNS = [
    (r"propuesta (\d+) \((\d+) épocas\)", r"proposal \1 (\2 epochs)"),
    (r"(\d+) estrellas Gaia", r"\1 Gaia stars"),
    (r"EPSF oficial zona \((.*?)\), (\d+) estrellas, (.*)", r"Official EPSF zone (\1), \2 stars, \3"),
    (r"mín ([\d.]+) d · total ([\d.]+) d", r"min \1 d · total \2 d"),
    (r"([\d.]+) nm = ([\d.]+) × ancho de banda", r"\1 nm = \2 × bandwidth"),
    (r"máx ([\d.]+) × ancho de banda; (\d+)% de la región ≤ ([\d.]+)", r"max \1 × bandwidth; \2% of the region ≤ \3"),
    (r"([\d.]+%) \((\d+) px; solapamiento geométrico ([\d.]+%)\)", r"\1 (\2 px; geometric overlap \3)"),
    (r"(S\d) warn: máx ([\d.]+) × ancho de banda; (\d+)% de la región ≤ ([\d.]+)", r"\1 warn: max \2 × bandwidth; \3% of the region ≤ \4"),
    (r"El fondo zodiacal modelado varía entre épocas \((.*)\): la secuencia muestra IMAGE − ZODI por defecto\.",
     r"The modelled zodiacal background varies between epochs (\1): the sequence shows IMAGE − ZODI by default."),
    (r"Desplazamiento ([\d.]+) ± ([\d.]+)″ en (\d+) d: ([\d.]+)σ, por debajo de 5σ\.", r"Displacement \1 ± \2″ over \3 d: \4σ, below 5σ."),
    (r"Desplazamiento de ([\d.]+) ± ([\d.]+)″ entre (\S+) y (\S+) \((\d+) d\): ([\d.]+)σ tras calibrar con (\d+) estrellas estacionarias "
     r"\(máximo de control ([\d.]+)σ\)\.",
     r"Displacement of \1 ± \2″ between \3 and \4 (\5 d): \6σ after calibrating with \7 stationary stars (control maximum \8σ)."),
    (r"Temporada (\S+) \((\d+) imágenes\) sin ajuste válido: el χ² del ajuste no tiene un mínimo definido \(curvatura no positiva; "
     r"típico de un núcleo saturado o enmascarado\)\.",
     r"Season \1 (\2 images) without a valid fit: the fit χ² has no defined minimum (non-positive curvature; typical of a saturated or masked core)."),
    (r"Mismo detector (D\d); temporadas separadas > (\d+) d; primera, intermedia\(s\) y última \(máx\. (\d+)\); hasta (\d+) imágenes por "
     r"temporada, las más alejadas del borde del detector\.",
     r"Same detector \1; seasons separated by > \2 d; first, intermediate(s) and last (max. \3); up to \4 images per season, those farthest from the detector edge."),
    (r"Control estacionario: Gaia DR3 (\d+) \(G ([\d.]+), μ ([\d.]+) mas/año\) en el campo de (.*)",
     r"Stationary control: Gaia DR3 \1 (G \2, μ \3 mas/yr) in the field of \4"),
    (r"Objetivo con movimiento propio \((.*?)″/año\): posición calculada para cada fecha desde (.*?) \(época ([\d.]+)\); se desplaza "
     r"([\d.]+)″ durante la secuencia(.*?)Es un cálculo, no una detección\.",
     r"Target with proper motion (\1″/yr): position calculated for each date from \2 (epoch \3); it moves \4″ during the sequence\5It is a calculation, not a detection."),
]
_COMPILED = [(re.compile(p, re.S), r) for p, r in PATTERNS]
_TAILS = [(" y queda a ", " and lies "), (" del centro del campo. ", " from the field centre. ")]
OUTCOME = {"MOTION_MEASURED": "Motion measured", "INSUFFICIENT_EVIDENCE": "Insufficient evidence",
           "INCOMPATIBLE": "Incompatible observations", "INSUFFICIENT_DATA": "Insufficient data"}


def text(s: str) -> str:
    """English for a known Spanish string; any other string is returned unchanged."""
    if s in EXACT:
        return EXACT[s]
    for rx, rep in _COMPILED:
        m = rx.fullmatch(s)
        if m:
            out = m.expand(rep)
            for a, b in _TAILS:
                out = out.replace(a, b)
            return out
    return s


def tree(obj):
    """The same structure with its known Spanish strings translated (new objects; the input is not modified)."""
    if isinstance(obj, dict):
        return {k: tree(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [tree(v) for v in obj]
    if isinstance(obj, str):
        return text(obj)
    return obj


def motion(report: dict) -> dict:
    """A saved motion investigation for display: texts in English and the outcome label from the code's own table."""
    r = tree(report)
    if isinstance(r, dict) and r.get("outcome") in OUTCOME:
        r["outcome_label"] = OUTCOME[r["outcome"]]
    return r
