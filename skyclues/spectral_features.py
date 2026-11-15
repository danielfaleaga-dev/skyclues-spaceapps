"""Comparison of two exploratory spectra (A, B) and inspection of peaks and valleys.

Numerical core only: no Streamlit, no I/O, no network. It works on the per-channel table that
``spectral_cube.extract_spectrum`` already produces and never changes it. The spectra of the
DR1 cube are exploratory (no variance, no aperture correction): nothing here turns them into
calibrated spectrophotometry, a line detection or a chemical identification.

Comparison (A vs B)
-------------------
Both spectra must come from the same extraction (aperture, annulus, sub-pixel sampling, pixel
solid angle) and the same channel table; otherwise the difference and the ratio are withheld
and the reason is reported. Per channel, only where BOTH have a value:

* difference ``A − B`` in the common unit;
* ratio ``A / B`` only where A > 0, B > 0 (beyond numerical precision) and B is at least
  ``RATIO_MIN_DENOMINATOR`` times its reference scatter (below). Elsewhere the ratio is undefined and says why. Nothing is
  interpolated; channels 51 and 52 (no data in DR1) stay empty.

Features (peaks and valleys)
----------------------------
1. **Local continuum.** For an interval of channels, the continuum is a least-squares
   polynomial in wavelength through the ``N_SIDE`` nearest measured channels on each side,
   contiguous with the interval (a channel without a value ends the environment: nothing is
   bridged). The interval itself, and the channels of features already found, are excluded.
   The polynomial has degree 2; with fewer than ``N_SIDE`` channels on either side (edge of
   the spectral range, channel without data) there is no continuum and the interval is
   *not evaluable*.
   When every environment value is positive the fit is done on ln(value) against ln(λ), so a
   power law is reproduced exactly and a smooth thermal spectrum to better than 0.6 % over
   the widest interval (0.2 % up to five channels; black bodies of 800–5800 K, real channel grid);
   with values ≤ 0 it is done on the values themselves and this is reported.
2. **Contrast** = original value − continuum, at the extreme channel of the interval. The
   original values are never smoothed or replaced.
3. **Reference scatter** σ_ref = the largest of (a) the residual scatter of the environment
   about its fit, (b) the robust scatter (3σ-clipped, started from the MAD) of the leave-one-out
   residuals of the whole detector, in absolute and in relative terms, and (c) the scatter of the background annulus propagated to the aperture,
   σ_ring · √(N_ap + N_ap²/N_ring) · Ω (flux) or σ_ring (single pixel). The contrast is compared
   with σ_ref · √(1 + leverage of the fit at that channel).
   **This is a descriptive threshold, not a photometric uncertainty and not a statistical
   significance**: the cube has no variance, mosaic noise is correlated and (c) ignores the
   source itself.
4. **Scan.** Trial intervals of 1, 3, 5, 7 and 9 channels centred on every channel; the
   narrowest scale within 10 % of the best contrast ratio is kept; the strongest candidate is
   accepted, its channels (the run of same-sign contrast around its extreme) are excluded
   from later environments, and the scan repeats.
   A contrast below ``MIN_RELATIVE`` of a positive continuum is never labelled: under that
   level the local polynomial cannot tell a feature from the curvature of a smooth spectrum.
5. **Classes** (never "detections"):
   ``cuantificable``  ratio ≥ Q_QUANTIFIABLE, valid environment on both sides, one detector,
                      no OVERFLOW/OUTLIER in the feature, stable coverage (NHITS);
   ``visible``        ratio ≥ Q_VISIBLE but one of the conditions above fails;
   ``no_evaluable``   missing data in the interval or no valid environment;
   ``sin_caracteristica``  below Q_VISIBLE: a fluctuation that is not labelled.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

import numpy as np

METHOD_VERSION = "skyclues-features 1.0 (2026-11-14)"
N_SIDE = 3                       # environment channels required on each side (fewer: no continuum)
DEGREE = 2                       # local polynomial
MAX_SKIP = 5                     # channels of other features an environment may step over
HALF_WIDTHS = (0, 1, 2, 3, 4)    # trial intervals of 1, 3, 5, 7, 9 channels
SCALE_TOLERANCE = 0.9            # narrowest scale within 10 % of the best ratio
Q_VISIBLE = 4.0                  # see tests/test_spectral_features.py: rates on pure noise
Q_QUANTIFIABLE = 6.0
MIN_RELATIVE = 0.01              # contrast below 1 % of a positive continuum is never labelled
MAX_FEATURES = 12
MAX_MANUAL_CHANNELS = 15         # widest interval a local continuum is attempted for
BROAD_MIN_CHANNELS = 3           # half-height width from which a feature is called broad
COVERAGE_CHANGE = 2.0            # NHITS ratio feature/environment beyond which coverage "changes"
RATIO_MIN_DENOMINATOR = 3.0      # B must exceed this many reference scatters for A/B
MIN_RESIDUALS = 6                # leave-one-out residuals needed for a detector scatter
MAD_TO_SIGMA = 1.4826

UNITS = {"flux": "mJy", "pixel": "MJy/sr"}
COLUMNS = {"flux": "flujo_mjy", "pixel": "pixel_mjysr"}
QUANTITY_NAMES = {"flux": "densidad de flujo en apertura", "pixel": "brillo superficial del píxel"}

QUANTIFIABLE, VISIBLE, NOT_EVALUABLE, NO_FEATURE = "cuantificable", "visible", "no_evaluable", "sin_caracteristica"
CLASS_LABELS = {QUANTIFIABLE: "Cuantificable", VISIBLE: "Visible", NOT_EVALUABLE: "No evaluable",
                NO_FEATURE: "Sin característica"}
CLASS_MEANING = {
    QUANTIFIABLE: "se puede caracterizar respecto a un entorno espectral válido",
    VISIBLE: "hay una variación en los valores, pero no se puede caracterizar con fiabilidad",
    NOT_EVALUABLE: "faltan datos adecuados para concluir nada",
    NO_FEATURE: "el valor no se aparta de su entorno más que la dispersión de referencia",
}
#: Documented instrumental artefact of the cube (Explanatory Supplement, known issues): not a line list.
KNOWN_ARTEFACTS = ((1.083, "He I 1.083 µm del resplandor atmosférico: el mosaico presenta rayado documentado "
                           "en este canal; un pico aquí puede ser instrumental"),)


class FeatureInputError(ValueError):
    """Inputs that cannot describe a spectrum or an interval."""


# ----------------------------------------------------------------------------- series
@dataclass(frozen=True)
class Series:
    """One spectrum as arrays in channel order. ``value`` is NaN where there is no value."""

    label: str
    quantity: str
    unit: str
    canal: np.ndarray
    lam: np.ndarray
    lam_min: np.ndarray
    lam_max: np.ndarray
    detector: np.ndarray
    value: np.ndarray
    status: tuple
    caution: np.ndarray
    nhits: np.ndarray
    ref_scatter: np.ndarray          # background scatter propagated to the measurement (NaN if unknown)
    meta: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return int(self.canal.size)

    @property
    def measured(self) -> np.ndarray:
        return np.isfinite(self.value)

    def index(self, canal: int) -> int:
        hit = np.flatnonzero(self.canal == int(canal))
        if not hit.size:
            raise FeatureInputError(f"Canal {canal} fuera de la tabla del espectro.")
        return int(hit[0])


def series_from_arrays(value, lam=None, *, label: str = "A", quantity: str = "flux", lam_min=None, lam_max=None,
                       detector=None, canal=None, caution=None, nhits=None, ref_scatter=None, status=None,
                       meta: dict | None = None) -> Series:
    """Build a Series from plain arrays (used by the tests and by any caller with its own table)."""
    if quantity not in UNITS:
        raise FeatureInputError("Magnitud desconocida.")
    v = np.array(value, dtype=float)
    n = v.size
    if n < 3 or v.ndim != 1:
        raise FeatureInputError("Un espectro necesita al menos tres canales.")
    lam = np.linspace(0.75, 5.0, n) if lam is None else np.array(lam, dtype=float)
    if lam.shape != v.shape or not np.all(np.isfinite(lam)) or not np.all(np.diff(lam) > 0):
        raise FeatureInputError("Las longitudes de onda deben ser finitas y crecientes, una por canal.")
    v = np.where(np.isfinite(v), v, np.nan)                      # ±inf is not a measurement
    half = np.gradient(lam) / 2
    arr = lambda a, d, t: np.array(d if a is None else a, dtype=t)   # noqa: E731
    return Series(label=label, quantity=quantity, unit=UNITS[quantity],
                  canal=arr(canal, np.arange(1, n + 1), int), lam=lam,
                  lam_min=arr(lam_min, lam - half, float), lam_max=arr(lam_max, lam + half, float),
                  detector=arr(detector, np.arange(n) * 6 // n + 1, int), value=v,
                  status=tuple(status) if status is not None else tuple("ok" if np.isfinite(x) else "sin_valor"
                                                                        for x in v),
                  caution=arr(caution, np.zeros(n, bool), bool), nhits=arr(nhits, np.full(n, np.nan), float),
                  ref_scatter=arr(ref_scatter, np.full(n, np.nan), float), meta=dict(meta or {}))


def series_from_spectrum(spec, quantity: str = "flux", label: str = "A") -> Series:
    """The chosen quantity of a ``spectral_cube.Spectrum`` (values untouched)."""
    if quantity not in COLUMNS:
        raise FeatureInputError("Magnitud desconocida.")
    rows = spec.rows
    num = lambda k: np.array([np.nan if r.get(k) is None else float(r[k]) for r in rows])   # noqa: E731
    value, sig = num(COLUMNS[quantity]), num("fondo_sigma_mjysr")
    if quantity == "flux":
        n_ap = float(spec.n_aperture_px)
        n_bg = np.array([float(r.get("n_fondo") or 0) for r in rows])
        with np.errstate(divide="ignore", invalid="ignore"):
            ref = sig * np.sqrt(n_ap + np.where(n_bg > 0, n_ap ** 2 / n_bg, np.nan)) * spec.pixel_solid_angle_sr * 1e9
        nhits = np.array([float(r.get("nhits_min_apertura") or 0) for r in rows])
        caution = np.array([bool(r.get("precaucion")) for r in rows])
        status = tuple(r["status"] for r in rows)
    else:
        ref = sig
        nhits = np.array([float(r.get("pixel_nhits") or 0) for r in rows])
        caution = np.array([any(f in ("OVERFLOW", "OUTLIER") for f in str(r.get("pixel_flags") or "").split("|"))
                            for r in rows])
        status = tuple("blank" if r["status"] == "blank" else ("ok" if np.isfinite(v) else "pixel_sin_datos")
                       for r, v in zip(rows, value))
    ap = spec.aperture
    meta = {"ra": float(spec.ra), "dec": float(spec.dec), "r_ap": float(ap.r_ap), "r_in": float(ap.r_in),
            "r_out": float(ap.r_out), "subpixels": int(spec.subpixels),
            "pixel_arcsec": float(spec.pixel_scale_arcsec), "pixel_sr": float(spec.pixel_solid_angle_sr),
            "n_aperture_px": float(spec.n_aperture_px), "n_annulus_px": int(spec.n_annulus_px),
            "tiles": sorted({str(t.get("tile")) for t in spec.tiles})}
    return series_from_arrays(value, num("lambda_um"), label=label, quantity=quantity, lam_min=num("lambda_min_um"),
                              lam_max=num("lambda_max_um"), detector=[int(r["detector"]) for r in rows],
                              canal=[int(r["canal"]) for r in rows], caution=caution, nhits=nhits, ref_scatter=ref,
                              status=status, meta=meta)


# ----------------------------------------------------------------------------- comparison
@dataclass
class Comparison:
    label_a: str
    label_b: str
    quantity: str
    unit: str
    comparable: bool                 # difference and ratio computed
    issues: list                     # why they are withheld
    notes: list                      # cautions that do not block the operation
    separation_arcsec: float | None
    rows: list
    summary: dict

    def table(self):
        import pandas as pd

        return pd.DataFrame(self.rows)


def _separation_arcsec(a: Series, b: Series) -> float | None:
    try:
        from .geometry import separation_deg

        return float(separation_deg(a.meta["ra"], a.meta["dec"], b.meta["ra"], b.meta["dec"])) * 3600
    except (KeyError, TypeError):
        return None


def compatibility(a: Series, b: Series) -> tuple[list, list, float | None]:
    """(issues that forbid A − B and A / B, cautions, separation). Nothing is silently equalised."""
    issues, notes = [], []
    if a.quantity != b.quantity or a.unit != b.unit:
        issues.append(f"Magnitudes distintas ({a.unit} y {b.unit}): no se restan ni se dividen.")
    same_grid = (a.n == b.n and np.array_equal(a.canal, b.canal) and np.allclose(a.lam, b.lam, rtol=0, atol=1e-6)
                 and np.allclose(a.lam_min, b.lam_min, rtol=0, atol=1e-6)
                 and np.allclose(a.lam_max, b.lam_max, rtol=0, atol=1e-6))
    if not same_grid:
        issues.append("Las tablas de canales de A y B no coinciden (longitudes de onda o intervalos distintos): "
                      "no se comparan canal a canal.")
    ma, mb = a.meta, b.meta
    if "pixel_sr" in ma and "pixel_sr" in mb and not math.isclose(ma["pixel_sr"], mb["pixel_sr"], rel_tol=1e-9):
        issues.append("Píxeles de distinto ángulo sólido en A y B.")
    if a.quantity == "flux" and ma and mb:
        diff = [k for k in ("r_ap", "r_in", "r_out", "subpixels") if ma.get(k) != mb.get(k)]
        if diff:
            issues.append("Extracciones distintas en A y B (" + ", ".join(
                f"{k}: {ma.get(k)} y {mb.get(k)}" for k in diff) + "): los flujos no son equivalentes.")
        elif "n_aperture_px" in ma and not math.isclose(ma["n_aperture_px"], mb["n_aperture_px"], rel_tol=0.02):
            notes.append(f"El área efectiva de la apertura difiere ({ma['n_aperture_px']:.2f} y "
                         f"{mb['n_aperture_px']:.2f} píxeles) por el muestreo de los bordes.")
    sep = _separation_arcsec(a, b)
    if sep is not None:
        pix = ma.get("pixel_arcsec") or float("nan")
        if sep < 0.05:
            notes.append("A y B son la misma posición: la comparación es trivial.")
        elif a.quantity == "pixel":
            if math.isfinite(pix) and sep < pix / 2:
                notes.append("A y B caen probablemente en el mismo píxel del cubo.")
        elif math.isfinite(pix):
            r_ap, r_in, r_out = ma["r_ap"] * pix, ma["r_in"] * pix, ma["r_out"] * pix
            if sep < 2 * r_ap:
                notes.append(f"Las aperturas se solapan (separación {sep:.0f}″ < {2 * r_ap:.0f}″): A y B comparten "
                             "píxeles y no son medidas independientes.")
            if r_in - r_ap < sep < r_out + r_ap:
                notes.append(f"Cada apertura cae en el anillo de fondo de la otra (separación {sep:.0f}″; anillo "
                             f"{r_in:.0f}″–{r_out:.0f}″): el fondo restado en una posición incluye luz de la otra.")
    if ma.get("tiles") and mb.get("tiles") and set(ma["tiles"]) != set(mb["tiles"]):
        notes.append("A y B se leen de teselas HEALPix distintas (misma rejilla y mismo ángulo sólido por píxel).")
    return issues, notes, sep


def _missing(status: str) -> str:
    return {"ok": "con valor", "blank": "canal sin datos en DR1", "no_data_aperture": "apertura con píxeles sin datos",
            "no_background": "fondo insuficiente", "pixel_sin_datos": "píxel sin datos"}.get(status, "sin valor")


def compare(a: Series, b: Series) -> Comparison:
    """Channel-by-channel comparison of two spectra extracted in the same way."""
    issues, notes, sep = compatibility(a, b)
    ok = not issues
    rows, n = [], min(a.n, b.n)
    ref_known = bool(np.isfinite(b.ref_scatter).any())
    tiny = _numeric_floor(a, b)
    for i in range(n if ok else 0):
        va, vb = a.value[i], b.value[i]
        both = bool(np.isfinite(va) and np.isfinite(vb))
        row = {"canal": int(a.canal[i]), "lambda_um": float(a.lam[i]), "lambda_min_um": float(a.lam_min[i]),
               "lambda_max_um": float(a.lam_max[i]), "detector": int(a.detector[i]),
               "a": float(va) if np.isfinite(va) else None, "b": float(vb) if np.isfinite(vb) else None,
               "estado_a": _missing(a.status[i]), "estado_b": _missing(b.status[i]),
               "precaucion": bool(a.caution[i] or b.caution[i]), "diferencia": None, "relacion": None,
               "estado_relacion": "falta A o B"}
        if both:
            row["diferencia"] = float(va - vb)
            rb = b.ref_scatter[i]
            if vb <= tiny or va <= tiny:
                row["estado_relacion"] = "no definida: A o B ≤ 0"
            elif np.isfinite(rb) and vb < RATIO_MIN_DENOMINATOR * rb:
                row["estado_relacion"] = (f"no fiable: B < {RATIO_MIN_DENOMINATOR:g} × la dispersión de referencia")
            else:
                row["relacion"] = float(va / vb)
                row["estado_relacion"] = "válida" if np.isfinite(rb) else "válida (sin filtro de estabilidad)"
        rows.append(row)
    d = np.array([r["diferencia"] for r in rows if r["diferencia"] is not None], float)
    q = np.array([r["relacion"] for r in rows if r["relacion"] is not None], float)
    summary = {"n_canales": int(n), "n_ambos": int(d.size),
               "n_solo_a": int(sum(r["a"] is not None and r["b"] is None for r in rows)),
               "n_solo_b": int(sum(r["b"] is not None and r["a"] is None for r in rows)),
               "n_ninguno": int(sum(r["a"] is None and r["b"] is None for r in rows)),
               "n_relacion": int(q.size), "filtro_estabilidad": ref_known, "identicos": bool(d.size and np.all(d == 0))}
    if d.size:
        summary.update(diferencia_mediana=float(np.median(d)), diferencia_min=float(d.min()),
                       diferencia_max=float(d.max()), fraccion_a_mayor=float(np.mean(d > 0)))
    if q.size:
        med = float(np.median(q))
        mad = float(np.median(np.abs(q - med))) * MAD_TO_SIGMA
        summary.update(relacion_mediana=med, relacion_dispersion=mad)
        if q.size >= MIN_RESIDUALS and mad > 0:
            dev = [(abs(r["relacion"] - med) / mad, r) for r in rows if r["relacion"] is not None]
            far = sorted((x for x in dev if x[0] >= Q_VISIBLE), key=lambda x: -x[0])[:5]
            summary["canales_apartados"] = [{"canal": r["canal"], "lambda_um": r["lambda_um"],
                                             "relacion": r["relacion"], "desviaciones": float(k)} for k, r in far]
    return Comparison(a.label, b.label, a.quantity, a.unit, ok, issues, notes, sep, rows, summary)


# ----------------------------------------------------------------------------- features
@dataclass
class Feature:
    serie: str
    origin: str                      # "automática" | "selección"
    klass: str
    kind: str | None                 # "pico" | "valle"
    reasons: list
    limitations: list
    unit: str
    canal: int | None = None         # extreme channel
    canal_lo: int | None = None      # half-height interval
    canal_hi: int | None = None
    trial_lo: int | None = None      # interval excluded from the continuum
    trial_hi: int | None = None
    mask_lo: int | None = None       # run of same-sign contrast around the extreme
    mask_hi: int | None = None
    lam: float | None = None
    lam_centroid: float | None = None
    lam_lo: float | None = None
    lam_hi: float | None = None
    width_um: float | None = None
    n_channels: int | None = None
    width: str | None = None         # "estrecha" | "amplia"
    value: float | None = None
    continuum: float | None = None
    contrast: float | None = None
    relative: float | None = None
    ratio: float | None = None       # contrast / (σ_ref √(1 + leverage)); descriptive
    ref: float | None = None
    ref_local: float | None = None
    ref_detector: float | None = None
    ref_background: float | None = None
    degree: int | None = None
    env_left: list = field(default_factory=list)
    env_right: list = field(default_factory=list)
    detectors: list = field(default_factory=list)
    nhits_feature: float | None = None
    nhits_env: float | None = None
    caution_channels: list = field(default_factory=list)

    @property
    def label(self) -> str:
        return CLASS_LABELS[self.klass]

    def contains(self, canal: int) -> bool:
        lo, hi = (self.mask_lo, self.mask_hi) if self.mask_lo is not None else (self.trial_lo, self.trial_hi)
        return lo is not None and lo <= int(canal) <= hi

    def to_dict(self) -> dict:
        return {**asdict(self), "label": self.label}


def _side(value, start: int, step: int, masked) -> list:
    out, j, n = [], start, len(value)
    while 0 <= j < n and len(out) < N_SIDE and abs(j - start) < N_SIDE + MAX_SKIP:
        if not math.isfinite(value[j]):
            break                                        # a channel without a value ends the environment
        if j not in masked:
            out.append(j)
        j += step
    return out


def _fit(x, y, x0, degree: int):
    """Least-squares polynomial; returns (prediction at x0, leverage at x0, residual scatter)."""
    X = np.vander(np.asarray(x, float), degree + 1, increasing=True)
    P = np.vander(np.atleast_1d(np.asarray(x0, float)), degree + 1, increasing=True)
    G = np.linalg.inv(X.T @ X)
    beta = G @ X.T @ np.asarray(y, float)
    res = np.asarray(y, float) - X @ beta
    dof = len(x) - (degree + 1)
    s = math.sqrt(float(res @ res) / dof) if dof > 0 else float("nan")
    return P @ beta, np.einsum("ij,jk,ik->i", P, G, P), s


def _continuum(s: Series, env: list, idx: list, degree: int):
    """Continuum at ``idx`` from the environment ``env``: (prediction, leverage, scatter, log-space?).

    Values and scatter are returned in the unit of the spectrum whatever the space of the fit.
    """
    lam0 = float(s.lam[idx[len(idx) // 2]])
    y = s.value[env]
    if np.all(y > 0):
        pred, lev, s_ln = _fit(np.log(s.lam[env] / lam0), np.log(y), np.log(s.lam[idx] / lam0), degree)
        pred = np.exp(pred)
        return pred, lev, s_ln * pred, True
    pred, lev, s_lin = _fit(s.lam[env] - lam0, y, s.lam[idx] - lam0, degree)
    return pred, lev, np.full(len(idx), s_lin), False


def _numeric_floor(*series: Series) -> float:
    """Values this small relative to the spectrum are rounding noise, not measurements of zero."""
    top = [float(np.max(np.abs(s.value[s.measured]))) for s in series if s.measured.any()]
    return 1e-9 * max(top) if top else 0.0


def _evaluate(s: Series, lo: int, hi: int, masked, sdet, *, origin: str, centre: int | None = None) -> Feature:
    """Characterise the interval of indices [lo, hi]. ``centre``: index that must be the extreme (scan)."""
    f = Feature(serie=s.label, origin=origin, klass=NOT_EVALUABLE, kind=None, reasons=[], limitations=[], unit=s.unit,
                trial_lo=int(s.canal[lo]), trial_hi=int(s.canal[hi]))
    idx = list(range(lo, hi + 1))
    bad = [int(s.canal[j]) for j in idx if not math.isfinite(s.value[j])]
    if bad:
        why = sorted({_missing(s.status[s.index(c)]) for c in bad})
        f.reasons.append(f"Canales sin valor en el intervalo ({', '.join(map(str, bad))}: {'; '.join(why)}). "
                         "No se interpolan.")
        return f
    left, right = _side(s.value, lo - 1, -1, masked), _side(s.value, hi + 1, 1, masked)
    f.env_left, f.env_right = [int(s.canal[j]) for j in left[::-1]], [int(s.canal[j]) for j in right]
    for name, side, edge in (("menor", left, lo - 1), ("mayor", right, hi + 1)):
        if len(side) < N_SIDE:
            cause = ("borde del intervalo espectral" if not 0 <= edge < s.n else
                     f"canal {int(s.canal[edge])}: {_missing(s.status[edge])}"
                     if not math.isfinite(s.value[edge]) else "canales sin valor o de otra característica")
            f.reasons.append(f"Sin entorno válido hacia λ {name} ({len(side)} de {N_SIDE} canales; {cause}): "
                             "no hay continuo local fiable.")
    if f.reasons:
        return f
    env = left + right
    degree = DEGREE
    pred, lev, s_env, log_space = _continuum(s, env, idx, degree)
    d = s.value[idx] - pred
    k = int(np.argmax(np.abs(d)))
    s_local = float(s_env[k])
    if centre is not None and idx[k] != centre:
        f.klass, f.reasons = NO_FEATURE, ["El extremo no está en el centro del intervalo de prueba."]
        return f
    j = idx[k]
    contrast = float(d[k])
    sd = _detector_ref(sdet, int(s.detector[j]), float(pred[k]))
    refs = [v for v in (s_local, sd, float(s.ref_scatter[j])) if math.isfinite(v)]
    ref = max(refs) if refs else float("nan")
    tiny = _numeric_floor(s)
    scale = ref * math.sqrt(1.0 + float(lev[k])) if math.isfinite(ref) else float("nan")
    if abs(contrast) <= tiny:
        ratio = 0.0
    elif not math.isfinite(scale) or scale <= tiny:
        ratio = math.copysign(math.inf, contrast)
    else:
        ratio = contrast / scale
    a = b = k
    while a > 0 and d[a - 1] * contrast > 0 and abs(d[a - 1]) >= 0.5 * abs(contrast):
        a -= 1
    while b < len(idx) - 1 and d[b + 1] * contrast > 0 and abs(d[b + 1]) >= 0.5 * abs(contrast):
        b += 1
    half = idx[a:b + 1]
    w = np.abs(d[a:b + 1])
    ma = mb = k                                           # same-sign run: what later environments must avoid
    while ma > 0 and d[ma - 1] * contrast > 0 and abs(d[ma - 1]) > tiny:
        ma -= 1
    while mb < len(idx) - 1 and d[mb + 1] * contrast > 0 and abs(d[mb + 1]) > tiny:
        mb += 1
    f.mask_lo, f.mask_hi = int(s.canal[idx[ma]]), int(s.canal[idx[mb]])
    f.kind = "pico" if contrast > 0 else "valle" if contrast < 0 else None
    f.canal, f.canal_lo, f.canal_hi = int(s.canal[j]), int(s.canal[half[0]]), int(s.canal[half[-1]])
    f.lam, f.lam_lo, f.lam_hi = float(s.lam[j]), float(s.lam_min[half[0]]), float(s.lam_max[half[-1]])
    f.lam_centroid = float(np.sum(w * s.lam[half]) / np.sum(w)) if np.sum(w) > 0 else f.lam
    f.width_um, f.n_channels = f.lam_hi - f.lam_lo, len(half)
    f.width = "amplia" if len(half) >= BROAD_MIN_CHANNELS else "estrecha"
    f.value, f.continuum, f.contrast = float(s.value[j]), float(pred[k]), contrast
    f.relative = contrast / f.continuum if f.continuum > tiny else None
    f.ratio, f.ref, f.degree = float(ratio), (ref if math.isfinite(ref) else None), degree
    f.ref_local = s_local if math.isfinite(s_local) else None
    f.ref_detector = sd if math.isfinite(sd) else None
    f.ref_background = float(s.ref_scatter[j]) if math.isfinite(s.ref_scatter[j]) else None
    f.detectors = sorted({int(s.detector[t]) for t in env + idx})
    nf, ne = s.nhits[idx], s.nhits[env]
    f.nhits_feature = float(np.nanmedian(nf)) if np.isfinite(nf).any() else None
    f.nhits_env = float(np.nanmedian(ne)) if np.isfinite(ne).any() else None
    f.caution_channels = [int(s.canal[t]) for t in idx if s.caution[t]]

    blockers = []                                        # conditions that cap the class at "visible"
    if f.caution_channels:
        blockers.append("Píxeles de entrada con OVERFLOW u OUTLIER en los canales "
                        f"{', '.join(map(str, f.caution_channels))}: el valor puede no ser fiable.")
    if len(f.detectors) > 1:
        blockers.append("El intervalo y su entorno abarcan los detectores "
                        f"{', '.join(f'D{x}' for x in f.detectors)}: calibración y resolución distintas pueden "
                        "producir un escalón.")
    if f.nhits_feature and f.nhits_env and not (1 / COVERAGE_CHANGE <= f.nhits_feature / f.nhits_env
                                                <= COVERAGE_CHANGE):
        blockers.append(f"Cambio de cobertura: NHITS {f.nhits_feature:.0f} en la característica y "
                        f"{f.nhits_env:.0f} en el entorno.")
    if any(s.caution[t] for t in env):
        f.limitations.append("Algún canal del entorno tiene OVERFLOW u OUTLIER: el continuo puede estar afectado.")
    if not log_space:
        f.limitations.append("Valores ≤ 0 en el entorno: continuo ajustado sobre los valores, no sobre sus "
                             "logaritmos; menos fiable si el espectro tiene mucha pendiente.")
    if f.n_channels == 1:
        f.limitations.append("Un solo canal: cada canal equivale a un elemento de resolución, así que no se "
                             "distingue de un valor atípico del mosaico.")
    if f.relative is None:
        f.limitations.append("Continuo ≤ 0: no se calcula el contraste relativo.")
    if (hi - lo + 1) >= 7:
        f.limitations.append("Característica ancha: si se extiende más allá del intervalo, el entorno la incluye y "
                             "el contraste queda subestimado.")
    for lam0, text in KNOWN_ARTEFACTS:
        if f.lam_lo <= lam0 <= f.lam_hi:
            f.limitations.append(text + ".")
    f.limitations = blockers + f.limitations
    aq = abs(ratio)
    if aq < Q_VISIBLE:
        f.klass = NO_FEATURE
        f.reasons.append(f"Contraste de {aq:.1f} veces la dispersión de referencia, por debajo de {Q_VISIBLE:g}: "
                         "fluctuación que no se etiqueta.")
    elif f.relative is not None and abs(f.relative) < MIN_RELATIVE:
        f.klass = NO_FEATURE
        f.reasons.append(f"Contraste del {abs(f.relative):.2%} del continuo, por debajo del {MIN_RELATIVE:.0%}: no "
                         "se distingue de la curvatura de un espectro suave.")
    elif aq >= Q_QUANTIFIABLE and not blockers:
        f.klass = QUANTIFIABLE
        f.reasons.append(f"Contraste de {_fmt_ratio(aq)} veces la dispersión de referencia (criterio "
                         f"{Q_QUANTIFIABLE:g}), con entorno válido a ambos lados.")
    else:
        f.klass = VISIBLE
        f.reasons.append(f"Contraste de {_fmt_ratio(aq)} veces la dispersión de referencia" + (
            f", entre {Q_VISIBLE:g} y {Q_QUANTIFIABLE:g}." if aq < Q_QUANTIFIABLE else
            ", pero hay condiciones que impiden caracterizarla con fiabilidad."))
    return f


def _fmt_ratio(v: float) -> str:
    return "más de 1000" if v > 1000 else f"{v:.1f}"


def _robust_sigma(r) -> float:
    """Scatter about the median: MAD to start, then a 3-sigma clipped standard deviation (more
    efficient than the MAD on a dozen values, and still blind to a few features)."""
    r = np.asarray(r, float)
    med = float(np.median(r))
    sig = float(np.median(np.abs(r - med))) * MAD_TO_SIGMA
    for _ in range(10):
        keep = np.abs(r - med) <= 3.0 * sig
        if keep.sum() < 3:
            break
        new = float(np.sqrt(np.mean((r[keep] - med) ** 2))) / 0.9865      # 0.9865: std of a normal cut at 3 sigma
        if abs(new - sig) <= 1e-6 * max(sig, 1e-300):
            break
        sig = new
    return sig


def detector_scatter(s: Series) -> dict:
    """Robust scatter per detector of the leave-one-out residuals (value − continuum of its neighbours).

    Returns {detector: {"abs": scatter in the unit of the spectrum, "rel": scatter relative to the
    continuum, or NaN}}. The reference used for a channel is the larger of ``abs`` and
    ``rel × continuum``: noise that grows with the signal and noise that does not are both covered.
    """
    res: dict[int, list] = {}
    for i in np.flatnonzero(s.measured):
        left, right = _side(s.value, i - 1, -1, ()), _side(s.value, i + 1, 1, ())
        if len(left) < N_SIDE or len(right) < N_SIDE:
            continue
        pred, lev, _, _ = _continuum(s, left + right, [int(i)], 2)
        r = float(s.value[i] - pred[0]) / math.sqrt(1.0 + float(lev[0]))
        res.setdefault(int(s.detector[i]), []).append((r, r / float(pred[0]) if pred[0] > 0 else float("nan")))
    out = {}
    for det, pairs in res.items():
        if len(pairs) < MIN_RESIDUALS:
            continue
        r = np.array(pairs)
        rel = r[:, 1][np.isfinite(r[:, 1])]
        out[det] = {"abs": _robust_sigma(r[:, 0]),
                    "rel": _robust_sigma(rel) if rel.size >= MIN_RESIDUALS else float("nan")}
    return out


def _detector_ref(sdet: dict, det: int, continuum: float) -> float:
    d = sdet.get(det)
    if not d:
        return float("nan")
    rel = d["rel"] * continuum if math.isfinite(d["rel"]) and continuum > 0 else float("nan")
    vals = [v for v in (d["abs"], rel) if math.isfinite(v)]
    return max(vals) if vals else float("nan")


def find_features(s: Series) -> list[Feature]:
    """Peaks and valleys of a spectrum (see the module docstring). Sorted by wavelength."""
    sdet = detector_scatter(s)
    masked: set[int] = set()
    cache: dict[tuple[int, int], Feature] = {}
    found: list[Feature] = []
    measured = [int(i) for i in np.flatnonzero(s.measured)]
    while len(found) < MAX_FEATURES:
        best = None
        for i in measured:
            if i in masked:
                continue
            trials = []
            for h in HALF_WIDTHS:
                lo, hi = i - h, i + h
                if lo < 0 or hi >= s.n or any(t in masked for t in range(lo, hi + 1)):
                    continue
                if (i, h) not in cache:
                    cache[i, h] = _evaluate(s, lo, hi, masked, sdet, origin="automática", centre=i)
                f = cache[i, h]
                if f.ratio is not None and f.klass in (QUANTIFIABLE, VISIBLE):
                    trials.append((h, f))
            if not trials:
                continue
            top = max(abs(f.ratio) for _, f in trials)
            h, f = next((h, f) for h, f in trials if abs(f.ratio) >= SCALE_TOLERANCE * top)
            if best is None or (abs(f.ratio), abs(f.contrast)) > (abs(best[1].ratio), abs(best[1].contrast)):
                best = (i, f, h)
        if best is None:
            break
        i, f, h = best
        found.append(f)
        masked.update(range(s.index(f.mask_lo), s.index(f.mask_hi) + 1))
        reach = max(HALF_WIDTHS) + N_SIDE + MAX_SKIP + h + 1
        for key in [k for k in cache if abs(k[0] - i) <= reach]:
            del cache[key]
    return sorted(found, key=lambda f: f.lam)


def _masked_for(s: Series, features, lo: int, hi: int) -> set:
    out = set()
    for f in features or ():
        if f.mask_lo is None:
            continue
        a, b = s.index(f.mask_lo), s.index(f.mask_hi)
        if b < lo or a > hi:                              # features that do not touch the interval
            out.update(range(a, b + 1))
    return out


def measure_interval(s: Series, canal_lo: int, canal_hi: int, features=()) -> Feature:
    """Characterise the channels [canal_lo, canal_hi] chosen by the user (same rules as the scan)."""
    lo, hi = sorted((s.index(canal_lo), s.index(canal_hi)))
    if hi - lo + 1 > MAX_MANUAL_CHANNELS:
        return Feature(serie=s.label, origin="selección", klass=NOT_EVALUABLE, kind=None, unit=s.unit, limitations=[],
                       trial_lo=int(s.canal[lo]), trial_hi=int(s.canal[hi]),
                       reasons=[f"Intervalo de {hi - lo + 1} canales: demasiado ancho para un continuo local "
                                f"(máximo {MAX_MANUAL_CHANNELS}). Lo que se ve a esa escala es la forma general del "
                                "espectro."])
    return _evaluate(s, lo, hi, _masked_for(s, features, lo, hi), detector_scatter(s), origin="selección")


def inspect_channel(s: Series, canal: int, features=()) -> Feature:
    """The feature that contains a channel: a found one, or the best trial centred on it."""
    for f in features or ():
        if f.contains(canal):
            return f
    i = s.index(canal)
    sdet, trials, last = detector_scatter(s), [], None
    for h in HALF_WIDTHS:
        lo, hi = i - h, i + h
        if lo < 0 or hi >= s.n:
            continue
        f = _evaluate(s, lo, hi, _masked_for(s, features, lo, hi), sdet, origin="selección", centre=i)
        if h == 0:
            last = f
        if f.ratio is not None:
            trials.append(f)
    if not trials:
        return last
    top = max(abs(f.ratio) for f in trials)
    return next(f for f in trials if abs(f.ratio) >= SCALE_TOLERANCE * top)


def unlabelled_extrema(s: Series, features=()) -> int:
    """Local maxima and minima of the plotted values that are NOT labelled as features."""
    inside = set()
    for f in features or ():
        inside.update(range(s.index(f.mask_lo), s.index(f.mask_hi) + 1))
    v, n = s.value, 0
    for i in range(1, s.n - 1):
        if i in inside or not (math.isfinite(v[i - 1]) and math.isfinite(v[i]) and math.isfinite(v[i + 1])):
            continue
        if (v[i] - v[i - 1]) * (v[i + 1] - v[i]) < 0:
            n += 1
    return n


def method_summary() -> dict:
    """Parameters of the method, for exports and reports."""
    return {"metodo": METHOD_VERSION, "canales_entorno_por_lado": N_SIDE, "grado_del_continuo": DEGREE,
            "intervalos_de_prueba_canales": [2 * h + 1 for h in HALF_WIDTHS], "umbral_visible": Q_VISIBLE,
            "umbral_cuantificable": Q_QUANTIFIABLE, "contraste_relativo_minimo": MIN_RELATIVE,
            "continuo": "polinomio local en ln(valor)–ln(λ) si el entorno es positivo; en valor–λ si no",
            "relacion_denominador_minimo": RATIO_MIN_DENOMINATOR,
            "cambio_de_cobertura": COVERAGE_CHANGE, "suavizado": "ninguno",
            "nota": "Umbrales descriptivos sobre una dispersión de referencia; no son incertidumbres fotométricas "
                    "ni significación estadística."}
