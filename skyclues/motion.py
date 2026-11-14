"""«Buscar algo que se mueve»: observed positions on individual SPHEREx Level-2 images.

This module measures where a source *is* in each original exposure (IMAGE − ZODI,
VARIANCE, FLAGS, the official EPSF extension and the celestial WCS of the file) and
decides, with explicit uncertainties and stationary controls, whether the source
has moved between observing seasons. It never uses the combined spectral cube,
screenshots, RGB composites or resampled products.

Method (all steps are reported in the result):

1. **PSF fit** of a 9×9 native-pixel stamp with the official ePSF of the zone of
   the detector where the source falls (cubic interpolation of the ×5 oversampled
   model), a free flux and a constant local background. Weighted least squares
   with the official VARIANCE; pixels flagged unusable/artifact (HALO included) are
   excluded. Position covariance from the fit, scaled by the reduced χ² when > 1.
   Without EPSF a Gaussian of the header PSF_FWHM is used and identified.
2. **Registration** with stationary sources: Gaia DR3 stars of the field (bright
   enough, isolated, with proper motion) are fitted in every image. Their Gaia
   proper motion is applied between dates; a free per-star zero point absorbs
   colour/blend offsets; the per-image offset of the WCS is solved jointly. The
   absolute offset with respect to Gaia is reported as WCS quality. Without Gaia,
   sources detected in the first image are used and assumed stationary (stated).
3. **Seasons**: images closer than ``SEASON_GAP_DAYS`` form a season; the season
   position is a weighted mean, with errors inflated by the internal scatter.
4. **Displacement** first → last season in the tangent plane, its covariance and
   significance S = √(Δᵀ C⁻¹ Δ).
5. **Stationary control**: every reference star is run through the same chain
   (leave-one-out registration). Its displacement must be compatible with zero
   (after its Gaia proper motion). The control calibrates the errors (factor ≥ 1)
   and gives the largest significance reached by a stationary source.
6. **Outcome**: ``MOTION_MEASURED`` only if S ≥ 5 after calibration, beyond every
   control, with enough references and target S/N; otherwise
   ``INSUFFICIENT_EVIDENCE``, ``INCOMPATIBLE_OBSERVATIONS`` or ``INSUFFICIENT_DATA``.

Catalogue predictions (SIMBAD/Gaia) are only *compared* with the measurement at
the end; they are never used to locate or fit the source.
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass, field

import numpy as np
from astropy.io import fits

from .geometry import gnomonic
from .quality import SATURATION

MOTION_MEASURED = "MOTION_MEASURED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
INCOMPATIBLE = "INCOMPATIBLE_OBSERVATIONS"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
OUTCOME_LABELS = {
    MOTION_MEASURED: "Movimiento medido",
    INSUFFICIENT_EVIDENCE: "Evidencia insuficiente",
    INCOMPATIBLE: "Observaciones incompatibles",
    INSUFFICIENT_DATA: "Datos insuficientes",
}
METHOD_VERSION = "skyclues-motion 1.0 (2026-11-14)"

STAMP_HALF = 4                 # 9x9 native pixels
SEARCH_RADIUS_ARCSEC = 20.0    # where the source is looked for in every image (around the selection)
DETECTION_SIGMA = 5.0          # matched-filter detection threshold
MIN_SNR_TARGET = 5.0           # PSF-flux S/N required for an image to enter a season mean
MIN_SEASON_SNR = 10.0          # joint-fit detection significance required in the seasons compared
MIN_SNR_REF = 8.0
CLIP_SIGMA = 3.0               # robust clipping of single images inside a season
REF_MAX_G = 19.0
REF_ISOLATION_ARCSEC = 15.0    # no other Gaia source within this distance, brighter than G_ref + 3
REF_TARGET_EXCLUSION_ARCSEC = 25.0
MAX_REF_RESIDUAL_ARCSEC = 3.0  # a reference this far from Gaia is a mismatch, not used
MIN_REFS = 3
SEASON_GAP_DAYS = 10.0
SIGNIFICANCE = 5.0
CONFUSION_RATIO = 0.5          # a second peak this strong inside the search radius = confusion


class MotionInputError(ValueError):
    """Inputs that cannot describe an investigation (no images, bad coordinates)."""


# ----------------------------------------------------------------------------- PSF
@dataclass
class PSF:
    """ePSF of one detector zone, normalised so its native-pixel samples sum to 1."""

    array: np.ndarray | None          # oversampled (ny, nx) or None for a Gaussian
    oversample: tuple[int, int] = (5, 5)
    sigma_px: float | None = None     # Gaussian fallback
    description: str = ""

    def __call__(self, dx, dy):
        dx, dy = np.asarray(dx, float), np.asarray(dy, float)
        if self.array is None:
            s = self.sigma_px
            return np.exp(-(dx * dx + dy * dy) / (2 * s * s)) / (2 * math.pi * s * s)
        return _cubic_sample(self.array, self.oversample, dx, dy)


def _keys(t):
    t = np.abs(t)
    a = -0.5
    return np.where(t <= 1, (a + 2) * t ** 3 - (a + 3) * t ** 2 + 1,
                    np.where(t < 2, a * t ** 3 - 5 * a * t ** 2 + 8 * a * t - 4 * a, 0.0))


def _cubic_sample(arr, ov, dx, dy):
    """Keys cubic convolution of an oversampled array centred at ((n-1)/2, (n-1)/2); 0 outside."""
    ny, nx = arr.shape
    u = (nx - 1) / 2 + dx * ov[0]
    v = (ny - 1) / 2 + dy * ov[1]
    iu, iv = np.floor(u).astype(int), np.floor(v).astype(int)
    pad = np.pad(arr, 3)
    out = np.zeros(np.broadcast(u, v).shape)
    for a in (-1, 0, 1, 2):
        wu = _keys(u - (iu + a))
        ii = np.clip(iu + a + 3, 0, nx + 5)
        for b in (-1, 0, 1, 2):
            jj = np.clip(iv + b + 3, 0, ny + 5)
            out = out + wu * _keys(v - (iv + b)) * pad[jj, ii]
    return out


@functools.lru_cache(maxsize=96)
def _epsf_table(path: str):
    with fits.open(path, mode="readonly", memmap=False) as hdul:
        if "EPSF" not in [h.name for h in hdul]:
            return None
        h = hdul["EPSF"]
        d = h.data
        calib = " ".join(str(v) for v in h.header.get("HISTORY", []) if "Calibration source" in str(v))
        return {"xc": np.array(d["XCENTER"], float), "yc": np.array(d["YCENTER"], float),
                "binx": np.array(d["BINX"], int), "biny": np.array(d["BINY"], int),
                "nstar": np.array(d["NSTAR"], int), "cwave": np.array(d["CWAVE"], float),
                "psf": np.array(d["EPSF"], float),
                "ov": (int(h.header.get("OVSMPX", 5)), int(h.header.get("OVSMPY", 5))),
                "calib": calib.replace("Calibration source file:", "").strip()}


def psf_for(img, x: float, y: float) -> PSF:
    """Official ePSF of the zone containing cutout pixel (x, y) (0-based); Gaussian if absent."""
    tab = _epsf_table(str(img.path))
    if tab is None:
        fwhm = float(img.meta.get("PSF_FWHM") or 2 * 6.15) / 6.15
        return PSF(None, sigma_px=fwhm / 2.3548,
                   description=f"Gaussiana PSF_FWHM={img.meta.get('PSF_FWHM')}″ (sin extensión EPSF)")
    ox, oy = img.detector_offset()
    xf, yf = x + ox - 1.0, y + oy - 1.0     # full-detector, 0-based
    k = int(np.argmin((tab["xc"] - xf) ** 2 + (tab["yc"] - yf) ** 2))
    arr = tab["psf"][k]
    ovx, ovy = tab["ov"]
    cy, cx = (arr.shape[0] - 1) // 2, (arr.shape[1] - 1) // 2
    norm = arr[cy % ovy::ovy, cx % ovx::ovx].sum()
    return PSF(arr / norm, (ovx, ovy),
               description=f"EPSF oficial zona ({tab['binx'][k]},{tab['biny'][k]}), {tab['nstar'][k]} estrellas, "
                           f"λc {tab['cwave'][k]:.3f} µm · {tab['calib']}")


# ----------------------------------------------------------------------------- fitting
def usable_mask(img) -> np.ndarray:
    """Strict mask (unusable + artifact, HALO included) of the original image."""
    return img.valid(("unusable", "artifact"))


def science_data(img) -> np.ndarray:
    return img.image - img.zodi


def fit_psf(data, var, usable, psf: PSF, x0: float, y0: float, *, half: int = STAMP_HALF,
            max_shift: float = 2.5, saturation=None) -> dict | None:
    """Weighted least-squares PSF fit (x, y, flux, background). None if not measurable."""
    ny, nx = data.shape
    xi, yi = int(round(x0)), int(round(y0))
    if xi - half < 0 or yi - half < 0 or xi + half >= nx or yi + half >= ny:
        return None
    ys, xs = np.mgrid[yi - half:yi + half + 1, xi - half:xi + half + 1]
    d, v, u = data[ys, xs], var[ys, xs], usable[ys, xs]
    m = u & np.isfinite(d) & np.isfinite(v) & (v > 0)
    if m.sum() < 20:
        return None
    X, Y, D, W = xs[m].astype(float), ys[m].astype(float), d[m], 1.0 / np.sqrt(v[m])
    border = (np.abs(xs - xi) == half) | (np.abs(ys - yi) == half)
    b0 = float(np.median(d[m & border])) if (m & border).any() else float(np.median(D))
    P0 = psf(X - x0, Y - y0)
    f0 = float(np.sum((D - b0) * P0 * W ** 2) / max(np.sum(P0 * P0 * W ** 2), 1e-30))
    p = np.array([x0, y0, f0, b0], float)
    h = 1e-3

    def evaluate(p):
        P = psf(X - p[0], Y - p[1])
        return p[2] * P + p[3], P

    def jacobian(p, P):
        dpx = (psf(X - p[0] - h, Y - p[1]) - psf(X - p[0] + h, Y - p[1])) / (2 * h)
        dpy = (psf(X - p[0], Y - p[1] - h) - psf(X - p[0], Y - p[1] + h)) / (2 * h)
        return np.column_stack([p[2] * dpx, p[2] * dpy, P, np.ones_like(P)]) * W[:, None]

    mod, P = evaluate(p)
    chi2 = float(np.sum(((D - mod) * W) ** 2))
    lam, converged = 1e-3, False
    for _ in range(60):
        J = jacobian(p, P)
        r = (D - mod) * W
        A = J.T @ J
        g = J.T @ r
        try:
            step = np.linalg.solve(A + lam * np.diag(np.diag(A)), g)
        except np.linalg.LinAlgError:
            return None
        trial = p + step
        tmod, tP = evaluate(trial)
        tchi2 = float(np.sum(((D - tmod) * W) ** 2))
        if tchi2 <= chi2:
            small = abs(step[0]) < 1e-5 and abs(step[1]) < 1e-5 and chi2 - tchi2 <= 1e-8 * max(chi2, 1)
            p, mod, P, chi2 = trial, tmod, tP, tchi2
            lam = max(lam / 3, 1e-7)
            if small:
                converged = True
                break
        else:
            lam *= 4
            if lam > 1e8:
                converged = True    # no further improvement possible: at the minimum
                break
    if abs(p[0] - x0) > max_shift or abs(p[1] - y0) > max_shift or not np.all(np.isfinite(p)):
        return None
    J = jacobian(p, P)
    dof = max(len(D) - 4, 1)
    chi2_red = chi2 / dof
    try:
        cov = np.linalg.inv(J.T @ J) * max(1.0, chi2_red)
    except np.linalg.LinAlgError:
        return None
    if not np.all(np.isfinite(np.diag(cov))) or np.any(np.diag(cov) <= 0):
        return None
    rr = np.hypot(xs - p[0], ys - p[1])
    core = rr <= 1.5
    sat = bool(saturation is not None and (saturation[ys, xs] & core).any())
    return {"x": float(p[0]), "y": float(p[1]), "flux": float(p[2]), "background": float(p[3]),
            "flux_err": float(math.sqrt(cov[2, 2])), "snr": float(p[2] / math.sqrt(cov[2, 2])),
            "cov_px": cov[:2, :2].tolist(), "chi2_red": float(chi2_red), "n_pix": int(len(D)),
            "n_masked_core": int((core & ~m).sum()), "saturated_core": sat, "converged": converged}


def _correlate(img, k):
    hy, hx = k.shape[0] // 2, k.shape[1] // 2
    win = np.lib.stride_tricks.sliding_window_view(np.pad(img, ((hy, hy), (hx, hx))), k.shape)
    return np.einsum("ijkl,kl->ij", win, k)


def matched_filter(data, var, usable, psf: PSF) -> np.ndarray:
    """Detection significance map (PSF-matched filter with the official variance)."""
    ky, kx = np.mgrid[-3:4, -3:4]
    k = psf(kx.astype(float), ky.astype(float))
    ok = usable & np.isfinite(data) & np.isfinite(var) & (var > 0)
    bg = float(np.median(data[ok])) if ok.any() else 0.0
    w = np.where(ok, 1.0 / np.where(ok, var, 1.0), 0.0)
    num = _correlate(np.where(ok, data - bg, 0.0) * w, k)
    den = np.sqrt(_correlate(w, k * k))
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), 0.0)


def find_peaks(snr_map, threshold: float = DETECTION_SIGMA, sep: int = 2) -> list[tuple[int, int, float]]:
    """Local maxima above threshold: (x, y, significance), strongest first."""
    win = np.lib.stride_tricks.sliding_window_view(np.pad(snr_map, sep, constant_values=-np.inf),
                                                   (2 * sep + 1, 2 * sep + 1))
    peak = (snr_map >= win.max(axis=(2, 3))) & (snr_map >= threshold)
    ys, xs = np.nonzero(peak)
    return sorted(((int(x), int(y), float(snr_map[y, x])) for x, y in zip(xs, ys)), key=lambda t: -t[2])


def detect_sources(img, threshold: float = DETECTION_SIGMA) -> list[dict]:
    """Sources detected in one original image (for choosing what to investigate)."""
    data, var, usable = science_data(img), img.variance, usable_mask(img)
    ny, nx = data.shape
    psf = psf_for(img, nx / 2, ny / 2)
    out = []
    for x, y, s in find_peaks(matched_filter(data, var, usable, psf), threshold):
        ra, dec = img.wcs.all_pix2world(x, y, 0)
        out.append({"x": x, "y": y, "significance": round(s, 1), "ra": float(ra), "dec": float(dec)})
    return out


# ----------------------------------------------------------------------------- geometry
def _sky(img, x, y):
    ra, dec = img.wcs.all_pix2world(x, y, 0)
    return float(ra), float(dec)


def _jacobian_arcsec(img, x, y, ra0, dec0):
    """d(xi, eta)/d(x, y) in arcsec per pixel at (x, y)."""
    pts = [(x + 0.5, y), (x - 0.5, y), (x, y + 0.5), (x, y - 0.5)]
    r, d = img.wcs.all_pix2world([p[0] for p in pts], [p[1] for p in pts], 0)
    xi, eta = gnomonic(np.asarray(r), np.asarray(d), ra0, dec0)
    xi, eta = np.asarray(xi) * 3600, np.asarray(eta) * 3600
    return np.array([[xi[0] - xi[1], xi[2] - xi[3]], [eta[0] - eta[1], eta[2] - eta[3]]])


def _tangent(ra, dec, ra0, dec0):
    xi, eta = gnomonic(ra, dec, ra0, dec0)
    return float(xi) * 3600, float(eta) * 3600


# ----------------------------------------------------------------------------- per-image measurements
def _gaia_references(gaia: dict | None, ra0, dec0, target_radec) -> list[dict]:
    if not gaia:
        return []
    src = [s for s in gaia.get("sources", []) if s.get("ra") is not None and s.get("dec") is not None]
    refs = []
    for s in src:
        g = s.get("phot_g_mean_mag")
        if g is None or g > REF_MAX_G or s.get("pmra") is None or s.get("pmdec") is None:
            continue
        if _sep(s["ra"], s["dec"], *target_radec) < REF_TARGET_EXCLUSION_ARCSEC:
            continue
        crowd = [o for o in src if o is not s and _sep(o["ra"], o["dec"], s["ra"], s["dec"]) < REF_ISOLATION_ARCSEC
                 and (o.get("phot_g_mean_mag") or 99) < g + 3]
        if crowd:
            continue
        refs.append(s)
    return refs


def _sep(ra1, dec1, ra2, dec2):
    from .geometry import separation_deg
    return float(separation_deg(ra1, dec1, ra2, dec2)) * 3600


def _gaia_shift(src, mjd, ra0, dec0):
    """Gaia proper-motion position at mjd (tangent plane, arcsec); catalogue J2016.0 reference."""
    from .references import expected_position
    jy = 2000.0 + (mjd - 51544.5) / 365.25
    ra, dec = expected_position(src, jy)
    return _tangent(ra, dec, ra0, dec0), (ra, dec)


def measure_image(img, frame_info: dict, start_radec, ra0, dec0, refs: list[dict],
                  search_radius_arcsec: float) -> dict:
    """Target + reference measurements in one image (no registration yet)."""
    data, var, usable = science_data(img), img.variance, usable_mask(img)
    sat = (img.flags & img.flag_defs.names_bitmask(SATURATION)) != 0
    x0, y0 = (float(v) for v in img.wcs.all_world2pix(start_radec[0], start_radec[1], 0))
    psf = psf_for(img, x0, y0)
    lam = float("nan")
    if 0 <= round(y0) < img.wavelength_um.shape[0] and 0 <= round(x0) < img.wavelength_um.shape[1]:
        lam = float(img.wavelength_um[int(round(y0)), int(round(x0))])
    out = {**frame_info, "psf_model": psf.description, "lambda_um": lam, "warnings": [],
           "astronet_solved": img.meta.get("ASTRONETSOLVED"), "finast": img.meta.get("FINAST"),
           "pixel_scale_arcsec": float(np.sqrt(abs(np.linalg.det(_jacobian_arcsec(img, x0, y0, ra0, dec0))))),
           "target": None, "references": {}}
    if not (0 <= x0 < data.shape[1] and 0 <= y0 < data.shape[0]):
        out["warnings"].append("La posición buscada queda fuera del recorte.")
        return out
    # Locate: strongest matched-filter peak within the search radius of the *selection*, never of a prediction.
    smap = matched_filter(data, var, usable, psf)
    scale = out["pixel_scale_arcsec"]
    rad_px = search_radius_arcsec / scale
    peaks = [p for p in find_peaks(smap, DETECTION_SIGMA) if math.hypot(p[0] - x0, p[1] - y0) <= rad_px]
    if not peaks:
        out["warnings"].append(f"Sin detección ≥ {DETECTION_SIGMA:g}σ a menos de {search_radius_arcsec:g}″ de la "
                               "posición seleccionada.")
    else:
        px, py, ps = peaks[0]
        fit = fit_psf(data, var, usable, psf_for(img, px, py), px, py, saturation=sat)
        if fit is None:
            out["warnings"].append("El ajuste PSF no convergió o el sello toca el borde/máscara.")
        else:
            fit["peak_significance"] = ps
            fit["confusion"] = len(peaks) > 1 and peaks[1][2] >= CONFUSION_RATIO * ps
            ra, dec = _sky(img, fit["x"], fit["y"])
            A = _jacobian_arcsec(img, fit["x"], fit["y"], ra0, dec0)
            cov = A @ np.array(fit["cov_px"]) @ A.T
            xi, eta = _tangent(ra, dec, ra0, dec0)
            fit.update(ra=ra, dec=dec, xi=xi, eta=eta, cov_arcsec2=cov.tolist())
            if fit["confusion"]:
                out["warnings"].append("Otra fuente comparable dentro del radio de búsqueda: posible confusión.")
            if fit["saturated_core"]:
                out["warnings"].append("Núcleo saturado (OVERFLOW/NONLINEAR): posición medida con las alas de la PSF.")
            out["target"] = fit
    for s in refs:
        (exi, eeta), (era, edec) = _gaia_shift(s, frame_info["mjd"], ra0, dec0)
        rx, ry = (float(v) for v in img.wcs.all_world2pix(era, edec, 0))
        f = fit_psf(data, var, usable, psf_for(img, rx, ry), rx, ry, max_shift=1.5, saturation=sat)
        if (f is None or f["snr"] < MIN_SNR_REF or f["saturated_core"] or f["n_masked_core"] > 0
                or f["chi2_red"] > 25):
            continue
        ra, dec = _sky(img, f["x"], f["y"])
        xi, eta = _tangent(ra, dec, ra0, dec0)
        if math.hypot(xi - exi, eta - eeta) > MAX_REF_RESIDUAL_ARCSEC:
            continue
        A = _jacobian_arcsec(img, f["x"], f["y"], ra0, dec0)
        cov = A @ np.array(f["cov_px"]) @ A.T
        out["references"][s["source_id"]] = {"xi": xi, "eta": eta, "gaia_xi": exi, "gaia_eta": eeta,
                                             "var_xi": float(cov[0, 0]), "var_eta": float(cov[1, 1]),
                                             "snr": f["snr"], "g": s.get("phot_g_mean_mag")}
    return out


# ----------------------------------------------------------------------------- registration
def solve_registration(meas: list[dict], exclude: str | None = None, iterations: int = 30) -> dict:
    """Joint per-image offsets o_k and per-star zero points P_j (gauge: Σ_k o_k = 0).

    r_jk = (measured − Gaia proper-motion position)_jk = P_j + o_k + noise. Stars seen
    in fewer than two images do not constrain the offsets.
    """
    K = len(meas)
    ids = {}
    for k, m in enumerate(meas):
        for sid in m["references"]:
            if sid != exclude:
                ids.setdefault(sid, []).append(k)
    ids = {s: ks for s, ks in ids.items() if len(ks) >= 2}
    res = {}
    for axis, gkey, vkey in (("xi", "gaia_xi", "var_xi"), ("eta", "gaia_eta", "var_eta")):
        r = {(s, k): meas[k]["references"][s][axis] - meas[k]["references"][s][gkey] for s, ks in ids.items() for k in ks}
        w = {(s, k): 1.0 / meas[k]["references"][s][vkey] for s, ks in ids.items() for k in ks}
        o = np.zeros(K)
        P = {s: 0.0 for s in ids}
        used = set(r)
        for it in range(iterations):
            for s in ids:
                ks = [k for k in ids[s] if (s, k) in used]
                if ks:
                    P[s] = sum(w[s, k] * (r[s, k] - o[k]) for k in ks) / sum(w[s, k] for k in ks)
            for k in range(K):
                js = [s for s in ids if (s, k) in used]
                if js:
                    o[k] = sum(w[s, k] * (r[s, k] - P[s]) for s in js) / sum(w[s, k] for s in js)
            con = [k for k in range(K) if any((s, k) in used for s in ids)]
            if con:   # gauge: mean offset of the constrained images is zero; others keep the mean WCS
                o[con] -= o[con].mean()
            if it in (10, 20):   # 4-sigma clipping of residuals, using the robust scatter
                resid = {key: (r[key] - P[key[0]] - o[key[1]]) * math.sqrt(w[key]) for key in r}
                vals = np.array(list(resid.values()))
                mad = 1.4826 * np.median(np.abs(vals - np.median(vals))) if len(vals) else 1.0
                used = {key for key, v in resid.items() if abs(v) <= 4 * max(mad, 1.0)}
        resid = [(r[key] - P[key[0]] - o[key[1]]) * math.sqrt(w[key]) for key in used]
        dof = max(len(resid) - len(ids) - K + 1, 1)
        chi2_red = float(np.sum(np.square(resid)) / dof) if resid else float("nan")
        err = np.full(K, np.nan)
        n = np.zeros(K, int)
        for k in range(K):
            js = [s for s in ids if (s, k) in used]
            n[k] = len(js)
            if js:
                err[k] = math.sqrt(1.0 / sum(w[s, k] for s in js) * max(1.0, chi2_red if math.isfinite(chi2_red) else 1))
        # absolute offset with respect to Gaia (WCS quality), per image: weighted mean of r_jk
        absolute = np.full(K, np.nan)
        for k in range(K):
            js = [s for s in ids if (s, k) in used]
            if js:
                absolute[k] = sum(w[s, k] * r[s, k] for s in js) / sum(w[s, k] for s in js)
        rms = float(np.sqrt(np.mean([(r[key] - P[key[0]] - o[key[1]]) ** 2 for key in used]))) if used else float("nan")
        # Empirical floors: single-star residual scatter (σ_s/√n for an image with n stars) and, for an
        # image without any measurable star, the scatter of the absolute WCS offsets between images.
        for k in range(K):
            if n[k] and math.isfinite(rms):
                err[k] = max(err[k], rms / math.sqrt(n[k]))
        fin = absolute[np.isfinite(absolute)]
        wcs_scatter = float(1.4826 * np.median(np.abs(fin - np.median(fin)))) if len(fin) >= 3 else float("nan")
        wcs_scatter = max(wcs_scatter, float(np.std(fin, ddof=1))) if len(fin) >= 3 else wcs_scatter
        for k in range(K):
            if not n[k]:
                err[k] = wcs_scatter
        res[axis] = {"offset": o, "err": err, "n": n, "chi2_red": chi2_red, "absolute": absolute, "rms": rms,
                     "wcs_scatter": wcs_scatter}
    n_k = np.minimum(res["xi"]["n"], res["eta"]["n"])
    return {"offset_xi": res["xi"]["offset"], "offset_eta": res["eta"]["offset"],
            "err_xi": res["xi"]["err"], "err_eta": res["eta"]["err"], "n_refs": n_k,
            "chi2_red": (res["xi"]["chi2_red"], res["eta"]["chi2_red"]),
            "rms_arcsec": (res["xi"]["rms"], res["eta"]["rms"]),
            "absolute_xi": res["xi"]["absolute"], "absolute_eta": res["eta"]["absolute"], "stars": sorted(ids),
            "wcs_scatter_arcsec": (res["xi"]["wcs_scatter"], res["eta"]["wcs_scatter"])}


# ----------------------------------------------------------------------------- seasons and displacement
def seasons(mjds, gap: float = SEASON_GAP_DAYS) -> list[list[int]]:
    order = sorted(range(len(mjds)), key=lambda i: mjds[i])
    groups: list[list[int]] = []
    for i in order:
        if groups and mjds[i] - mjds[groups[-1][-1]] <= gap:
            groups[-1].append(i)
        else:
            groups.append([i])
    return groups


def _wmean(values, variances, clip: float | None = CLIP_SIGMA):
    v, var = np.asarray(values, float), np.asarray(variances, float)
    if clip and len(v) >= 4:   # drop single images far from the weighted median (noise peak, cosmic ray)
        order = np.argsort(v)
        cw = np.cumsum((1 / var)[order])
        med = v[order][np.searchsorted(cw, cw[-1] / 2)]
        resid = (v - med) / np.sqrt(var)
        mad = 1.4826 * np.median(np.abs(resid))
        keep = np.abs(resid) <= clip * max(mad, 1.0)
        if keep.sum() >= 2:
            v, var = v[keep], var[keep]
    w = 1 / var
    mean = float(np.sum(w * v) / np.sum(w))
    err2 = float(1 / np.sum(w))
    chi2_red = float(np.sum(w * (v - mean) ** 2) / (len(v) - 1)) if len(v) > 1 else float("nan")
    if len(v) > 1 and chi2_red > 1:
        err2 *= chi2_red     # internal scatter larger than the formal errors
    return mean, err2, chi2_red


def displacement(mjds, xi, eta, var_xi, var_eta, gap: float = SEASON_GAP_DAYS) -> dict | None:
    groups = seasons(mjds, gap)
    if len(groups) < 2:
        return None
    rows = []
    for g in groups:
        mx, vx, cx = _wmean([xi[i] for i in g], [var_xi[i] for i in g])
        my, vy, cy = _wmean([eta[i] for i in g], [var_eta[i] for i in g])
        rows.append({"members": g, "mjd": float(np.mean([mjds[i] for i in g])), "xi": mx, "eta": my,
                     "err_xi": math.sqrt(vx), "err_eta": math.sqrt(vy), "scatter_chi2_red": [cx, cy]})
    a, b = rows[0], rows[-1]
    dxi, deta = b["xi"] - a["xi"], b["eta"] - a["eta"]
    sxi = math.hypot(a["err_xi"], b["err_xi"])
    seta = math.hypot(a["err_eta"], b["err_eta"])
    return {"seasons": rows, "dxi": dxi, "deta": deta, "err_dxi": sxi, "err_deta": seta,
            "delta_t_days": b["mjd"] - a["mjd"], "significance": math.hypot(dxi / sxi, deta / seta)}


# ----------------------------------------------------------------------------- investigation
@dataclass
class Investigation:
    outcome: str
    reasons: list[str]
    result: dict = field(default_factory=dict)

    @property
    def label(self) -> str:
        return OUTCOME_LABELS[self.outcome]


def _frame_info(frame) -> dict:
    img = frame.image
    rec = getattr(frame, "record", {}) or {}
    return {"obs_id": str(img.meta.get("OBSID")), "date_utc": str(img.meta.get("DATE-AVG")),
            "mjd": float(img.meta["MJD-AVG"]), "detector": int(img.meta["DETECTOR"]),
            "collection": rec.get("collection"), "software_version": img.meta.get("VERSION"),
            "file": img.path.name, "sha256": getattr(frame, "sha256", None),
            "cutout_url": getattr(frame, "cutout_url", None)}


def _untangent(xi, eta, ra0, dec0):
    """Inverse gnomonic projection: tangent-plane offsets (arcsec) → ICRS (deg)."""
    x = np.radians(np.asarray(xi, float) / 3600)
    y = np.radians(np.asarray(eta, float) / 3600)
    a0, d0 = math.radians(ra0), math.radians(dec0)
    rho = np.hypot(x, y)
    c = np.arctan(rho)
    safe = np.where(rho > 0, rho, 1.0)
    dec = np.arcsin(np.cos(c) * math.sin(d0) + np.where(rho > 0, y * np.sin(c) * math.cos(d0) / safe, 0.0))
    ra = a0 + np.arctan2(x * np.sin(c), rho * math.cos(d0) * np.cos(c) - y * math.sin(d0) * np.sin(c))
    return np.degrees(ra) % 360, np.degrees(dec)


@dataclass
class _Entry:
    """One registered original image inside a season fit."""

    k: int
    img: object
    data: np.ndarray
    var: np.ndarray
    usable: np.ndarray
    sat: np.ndarray
    mjd: float
    oxi: float
    oeta: float
    vxi: float          # registration variance (arcsec²)
    veta: float


def _entries(frames, meas, reg) -> list[_Entry]:
    out = []
    for k, (f, m) in enumerate(zip(frames, meas)):
        ex, ee = reg["err_xi"][k], reg["err_eta"][k]
        if not (math.isfinite(ex) and math.isfinite(ee)):
            continue
        img = f.image
        out.append(_Entry(k, img, science_data(img), img.variance, usable_mask(img),
                          (img.flags & img.flag_defs.names_bitmask(SATURATION)) != 0, m["mjd"],
                          float(reg["offset_xi"][k]), float(reg["offset_eta"][k]), ex * ex, ee * ee))
    return out


def _stamp(e: _Entry, x, y, half):
    ny, nx = e.data.shape
    x0, x1 = max(int(round(x)) - half, 0), min(int(round(x)) + half + 1, nx)
    y0, y1 = max(int(round(y)) - half, 0), min(int(round(y)) + half + 1, ny)
    if x1 - x0 < 2 * STAMP_HALF + 1 or y1 - y0 < 2 * STAMP_HALF + 1:
        return None
    ys, xs = np.mgrid[y0:y1, x0:x1]
    d, v, u = e.data[ys, xs], e.var[ys, xs], e.usable[ys, xs]
    m = u & np.isfinite(d) & np.isfinite(v) & (v > 0)
    if m.sum() < 30:
        return None
    return xs[m].astype(float), ys[m].astype(float), d[m], 1.0 / v[m]


class _SeasonModel:
    """Profile χ² of one source position shared by the images of a season.

    Each image keeps its own free flux and constant background (linear, solved
    exactly for every trial position). The trial position lives in the registered
    tangent plane; image k sees it displaced by its registration offset o_k.
    """

    def __init__(self, entries, track, ra0, dec0, radius):
        self.parts = []
        self.ra0, self.dec0 = ra0, dec0
        for e in entries:
            cx, cy = track(e)
            ra, dec = _untangent(cx + e.oxi, cy + e.oeta, ra0, dec0)
            x, y = (float(v) for v in e.img.wcs.all_world2pix(float(ra), float(dec), 0))
            scale = math.sqrt(abs(np.linalg.det(_jacobian_arcsec(e.img, x, y, ra0, dec0))))
            st = _stamp(e, x, y, STAMP_HALF + int(math.ceil(radius / scale)) + 1)
            if st is None:
                continue
            X, Y, D, w = st
            self.parts.append({"e": e, "cx": cx, "cy": cy, "X": X, "Y": Y, "D": D, "w": w,
                               "psf": psf_for(e.img, x, y), "S1": w.sum(), "Sd": (w * D).sum(),
                               "Sdd": (w * D * D).sum()})

    def chi2(self, dxi, deta, detail=False):
        dxi, deta = np.atleast_1d(np.asarray(dxi, float)), np.atleast_1d(np.asarray(deta, float))
        total = np.zeros(dxi.shape)
        null = 0.0
        per = []
        for p in self.parts:
            e = p["e"]
            ra, dec = _untangent(p["cx"] + e.oxi + dxi, p["cy"] + e.oeta + deta, self.ra0, self.dec0)
            x, y = e.img.wcs.all_world2pix(ra, dec, 0)
            P = p["psf"](p["X"][None, :] - np.asarray(x)[:, None], p["Y"][None, :] - np.asarray(y)[:, None])
            w, D = p["w"], p["D"]
            Spp, Sp, Spd = (P * P * w).sum(1), (P * w).sum(1), (P * w * D).sum(1)
            det = Spp * p["S1"] - Sp ** 2
            ok = det > 0
            sdet = np.where(ok, det, 1.0)
            F = np.where(ok, (Spd * p["S1"] - Sp * p["Sd"]) / sdet, 0.0)
            b = np.where(ok, (Spp * p["Sd"] - Sp * Spd) / sdet, p["Sd"] / p["S1"])
            c0 = p["Sdd"] - p["Sd"] ** 2 / p["S1"]
            c = np.where(ok & (F > 0), p["Sdd"] - F * Spd - b * p["Sd"], c0)
            total += c
            null += c0
            if detail:
                per.append({"F": F, "sF": np.sqrt(np.where(ok, p["S1"] / sdet, np.inf)), "x": np.asarray(x),
                            "y": np.asarray(y), "b": b})
        return (total, null, per) if detail else total


def season_fit(entries, track, ra0, dec0, radius: float, coarse: float | None = None) -> dict | None:
    """Joint maximum-likelihood position of one source in one season (see _SeasonModel)."""
    model = _SeasonModel(entries, track, ra0, dec0, radius)
    if not model.parts:
        return None
    coarse = coarse or (1.0 if radius > 6 else 0.5)
    g = np.arange(-radius, radius + 1e-9, coarse)
    gx, gy = np.meshgrid(g, g)
    inside = np.hypot(gx, gy) <= radius
    gx, gy = gx[inside], gy[inside]
    chi, null, _ = model.chi2(gx, gy, detail=True)
    improvement = null - chi
    i0 = int(np.argmin(chi))
    best = np.array([gx[i0], gy[i0]])
    # second, separated minimum = possible confusion
    far = np.hypot(gx - best[0], gy - best[1]) > 2.5 * 6.15
    confusion = bool(far.any() and improvement[far].max() >= CONFUSION_RATIO ** 2 * improvement[i0] > 0)
    # Newton refinement on the profile χ² with an adaptive finite-difference step
    h = 0.2
    H = None
    for _ in range(8):
        pts = best + h * np.array([[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]])
        c = model.chi2(pts[:, 0], pts[:, 1])
        dmax = max(c[1] + c[2], c[3] + c[4]) / 2 - c[0]
        if dmax > 25 and h > 0.01:
            h /= 2
            continue
        if dmax < 0.3 and h < 3:
            h *= 2
            continue
        gvec = np.array([(c[1] - c[2]) / (2 * h), (c[3] - c[4]) / (2 * h)])
        H = np.array([[(c[1] - 2 * c[0] + c[2]) / h ** 2, (c[5] - c[6] - c[7] + c[8]) / (4 * h * h)],
                      [(c[5] - c[6] - c[7] + c[8]) / (4 * h * h), (c[3] - 2 * c[0] + c[4]) / h ** 2]])
        if np.linalg.det(H) <= 0 or H[0, 0] <= 0:
            H = None
            break
        step = -np.linalg.solve(H, gvec)
        if np.hypot(*step) > 2 * h:
            step *= 2 * h / np.hypot(*step)
        best = best + step
        if np.hypot(*step) < 0.002:
            break
    if H is None or np.hypot(*best) > radius + 1:
        return None
    chi_b, null_b, per = model.chi2([best[0]], [best[1]], detail=True)
    cov = 2 * np.linalg.inv(H)
    # local reduced χ² (pixels within 3 px of the source) scales the errors when > 1
    num, dof = 0.0, 0
    images = []
    for p, q in zip(model.parts, per):
        F, sF, x, y, b = q["F"][0], q["sF"][0], q["x"][0], q["y"][0], q["b"][0]
        near = np.hypot(p["X"] - x, p["Y"] - y) <= 3
        mod = max(F, 0) * p["psf"](p["X"][near] - x, p["Y"][near] - y) + b
        num += float(np.sum((p["D"][near] - mod) ** 2 * p["w"][near]))
        dof += int(near.sum()) - 2
        rr = np.hypot(*np.mgrid[0:p["e"].sat.shape[0], 0:p["e"].sat.shape[1]][::-1] - np.array([x, y])[:, None, None])
        images.append({"k": p["e"].k, "snr": float(F / sF) if np.isfinite(sF) and sF > 0 else 0.0,
                       "saturated_core": bool((p["e"].sat & (rr <= 1.5)).any()), "x": float(x), "y": float(y)})
    chi2_local = num / max(dof - 2, 1)
    cov_fit = cov * max(1.0, chi2_local)
    # registration: offsets errors are independent between images; weight by S/N²
    wts = np.array([max(i["snr"], 0) ** 2 for i in images])
    if wts.sum() <= 0:
        return None
    wn = wts / wts.sum()
    ents = {p["e"].k: p["e"] for p in model.parts}
    reg_xi = float(np.sum(wn ** 2 * np.array([ents[i["k"]].vxi for i in images])))
    reg_eta = float(np.sum(wn ** 2 * np.array([ents[i["k"]].veta for i in images])))
    cov_tot = cov_fit + np.diag([reg_xi, reg_eta])
    # internal consistency: free single-image fits near the season position
    singles = []
    for p, i in zip(model.parts, images):
        e = p["e"]
        f = fit_psf(e.data, e.var, e.usable, p["psf"], i["x"], i["y"], max_shift=1.0, saturation=e.sat)
        if f is None or f["snr"] < MIN_SNR_TARGET:
            continue
        ra, dec = _sky(e.img, f["x"], f["y"])
        xi, eta = _tangent(ra, dec, ra0, dec0)
        A = _jacobian_arcsec(e.img, f["x"], f["y"], ra0, dec0)
        c = A @ np.array(f["cov_px"]) @ A.T + np.diag([e.vxi, e.veta])
        singles.append((xi - e.oxi - p["cx"], eta - e.oeta - p["cy"], c))
    chi2_int = float("nan")
    if len(singles) >= 2:
        r = [np.array([s[0] - best[0], s[1] - best[1]]) for s in singles]
        chi2_int = float(sum(v @ np.linalg.inv(s[2]) @ v for v, s in zip(r, singles)) / (2 * (len(singles) - 1)))
        if chi2_int > 1:
            cov_tot = cov_tot * chi2_int
    mjd = float(np.sum(wn * np.array([ents[i["k"]].mjd for i in images])))
    cx, cy = model.parts[0]["cx"], model.parts[0]["cy"]
    return {"dxi": float(best[0]), "deta": float(best[1]), "xi": float(cx + best[0]), "eta": float(cy + best[1]),
            "cov": cov_tot.tolist(), "err_xi": math.sqrt(cov_tot[0, 0]), "err_eta": math.sqrt(cov_tot[1, 1]),
            "err_fit": [math.sqrt(cov_fit[0, 0]), math.sqrt(cov_fit[1, 1])],
            "err_registration": [math.sqrt(reg_xi), math.sqrt(reg_eta)],
            "significance": float(math.sqrt(max(float(null_b - chi_b[0]), 0.0))), "chi2_red_local": chi2_local,
            "internal_chi2_red": chi2_int, "n_single_fits": len(singles), "mjd": mjd, "n_images": len(images),
            "images": images, "confusion": confusion,
            "saturated_core": any(i["saturated_core"] for i in images)}


def _season_disp(a: dict, b: dict) -> dict:
    d = np.array([b["xi"] - a["xi"], b["eta"] - a["eta"]])
    C = np.array(a["cov"]) + np.array(b["cov"])
    sig = float(math.sqrt(d @ np.linalg.inv(C) @ d))
    return {"dxi": float(d[0]), "deta": float(d[1]), "err_dxi": math.sqrt(C[0, 0]), "err_deta": math.sqrt(C[1, 1]),
            "cov": C.tolist(), "significance": sig, "delta_t_days": b["mjd"] - a["mjd"]}


def investigate(frames, source_radec, *, gaia: dict | None = None, astrometry=None,
                search_radius_arcsec: float = SEARCH_RADIUS_ARCSEC, source_label: str = "") -> Investigation:
    """Run the full chain on original images. ``frames``: objects with ``.image`` (SpectralImage)
    and optionally ``.record``, ``.sha256``, ``.cutout_url`` (sequence.Frame works).

    ``source_radec``: where the user selected the source (ICRS deg). It only defines the
    search circle in every season; catalogue predictions never locate or fit the source.
    """
    from .targets import validate_coordinates
    ra0, dec0 = validate_coordinates(*source_radec)
    if not math.isfinite(search_radius_arcsec) or not 3 <= search_radius_arcsec <= 60:
        raise MotionInputError("Radio de búsqueda fuera de 3–60″.")
    frames = list(frames)
    base = {"method": METHOD_VERSION, "source": {"label": source_label, "selected_ra": ra0, "selected_dec": dec0,
                                                  "search_radius_arcsec": search_radius_arcsec},
            "data_rule": "Imágenes individuales SPHEREx L2 originales (IMAGE − ZODI, VARIANCE, FLAGS, EPSF, WCS). "
                         "Sin cubo, sin remuestreo, sin capturas.",
            "thresholds": {"significance": SIGNIFICANCE, "min_season_detection": MIN_SEASON_SNR,
                           "min_refs": MIN_REFS, "min_snr_reference": MIN_SNR_REF,
                           "season_gap_days": SEASON_GAP_DAYS},
            "gaia": None if not gaia else {k: gaia.get(k) for k in ("endpoint", "table", "query", "retrieved_utc",
                                                                       "sha256", "truncated", "catalogue_epoch")}}
    if len(frames) < 2:
        return Investigation(INSUFFICIENT_DATA, ["Se necesitan al menos dos imágenes de fechas distintas."], base)
    infos = [_frame_info(f) for f in frames]
    dets = sorted({i["detector"] for i in infos})
    if len(dets) > 1:
        return Investigation(INCOMPATIBLE, [f"Detectores distintos ({', '.join(f'D{d}' for d in dets)}): PSF y "
                                            "distorsión diferentes; se exige el mismo detector."], {**base, "images": infos})
    bad = [i["obs_id"] for f, i in zip(frames, infos) if f.image.meta.get("FINAST") not in (0, None)]
    keep = [j for j, i in enumerate(infos) if i["obs_id"] not in bad]
    frames, infos = [frames[j] for j in keep], [infos[j] for j in keep]
    warns = [f"Excluidas por astrometría fina no válida (FINAST ≠ 0): {', '.join(bad)}."] if bad else []
    if len(seasons([i["mjd"] for i in infos])) < 2:
        return Investigation(INSUFFICIENT_DATA, ["Las imágenes válidas no abarcan dos temporadas (separación > "
                                                 f"{SEASON_GAP_DAYS:g} días)."], {**base, "images": infos, "warnings": warns})
    refs = _gaia_references(gaia, ra0, dec0, (ra0, dec0))
    meas = [measure_image(f.image, i, (ra0, dec0), ra0, dec0, refs, search_radius_arcsec)
            for f, i in zip(frames, infos)]
    reg = solve_registration(meas)
    if not gaia:
        warns.append("Sin catálogo Gaia: no hay registro con fuentes estacionarias ni control de falsos positivos.")
    rows = []
    for k, m in enumerate(meas):
        nref = int(reg["n_refs"][k])
        rows.append({"index": k, "obs_id": m["obs_id"], "date_utc": m["date_utc"], "mjd": m["mjd"],
                     "lambda_um": m["lambda_um"], "n_refs": nref, "psf_model": m["psf_model"],
                     "registration_mode": (f"{nref} estrellas Gaia" if nref >= MIN_REFS else
                                           f"{nref} estrella(s) Gaia · error empírico" if nref else
                                           "solo WCS del archivo · error empírico del WCS"),
                     "wcs_offset_vs_gaia_arcsec": [_f(reg["absolute_xi"][k]), _f(reg["absolute_eta"][k])],
                     "registration_offset_arcsec": [_f(reg["offset_xi"][k]), _f(reg["offset_eta"][k])],
                     "registration_err_arcsec": [_f(reg["err_xi"][k]), _f(reg["err_eta"][k])],
                     "file": m["file"], "sha256": m["sha256"], "cutout_url": m["cutout_url"],
                     "collection": m["collection"], "usable": False, "snr": None, "warnings": []})
    result = {**base, "detector": dets[0], "images": rows,
              "lambda_range_um": [_f(np.nanmin([r["lambda_um"] for r in rows])),
                                  _f(np.nanmax([r["lambda_um"] for r in rows]))],
              "registration": {"method": "Gaia DR3 (movimiento propio aplicado; punto cero libre por estrella)" if refs
                               else "ninguno", "stars": len(reg["stars"]), "chi2_red": list(reg["chi2_red"]),
                               "rms_arcsec": list(reg["rms_arcsec"]),
                               "wcs_scatter_arcsec": list(reg["wcs_scatter_arcsec"])},
              "warnings": warns}
    ents = _entries(frames, meas, reg)
    unregistered = [rows[k]["obs_id"] for k in range(len(rows)) if k not in {e.k for e in ents}]
    if unregistered:
        warns.append(f"Sin registro posible (ni estrellas ni error empírico del WCS): {', '.join(unregistered)}.")
    if not ents:
        why = ("Gaia DR3 no disponible: sin estrellas estacionarias no se pueden registrar las imágenes ni controlar "
               "falsos positivos." if not gaia else
               f"Ninguna imagen tiene estrellas Gaia estacionarias medibles ({len(refs)} candidatas aisladas con "
               f"G ≤ {REF_MAX_G:g} y movimiento propio): no se puede registrar ni estimar el error del WCS. Un campo "
               "mayor suele contener más estrellas de referencia.")
        return Investigation(INSUFFICIENT_EVIDENCE, [why], result)
    groups = seasons([e.mjd for e in ents])
    xs, ys = _tangent(ra0, dec0, ra0, dec0)
    fits_ = []
    for g in groups:
        sf = season_fit([ents[i] for i in g], lambda e: (xs, ys), ra0, dec0, search_radius_arcsec)
        if sf is None:
            continue
        sf["date_utc"] = _mjd_date(min(ents[i].mjd for i in g))
        sf["obs_ids"] = [rows[ents[i].k]["obs_id"] for i in g]
        for im in sf["images"]:
            rows[im["k"]].update(snr=im["snr"], saturated_core=im["saturated_core"])
        fits_.append(sf)
    result["seasons"] = fits_
    good = [s for s in fits_ if s["significance"] >= MIN_SEASON_SNR]
    for s in fits_:
        s["usable"] = s in good
        for im in s["images"]:
            rows[im["k"]]["usable"] = s["usable"]
    if not good:
        reason = ("La fuente no se detecta con significación ≥ "
                  f"{MIN_SEASON_SNR:g}σ en ninguna temporada (ajuste conjunto de sus exposiciones).")
        return Investigation(INSUFFICIENT_DATA if not fits_ else INSUFFICIENT_EVIDENCE, [reason], result)
    if len(good) < 2:
        weak = [f"{s['date_utc']} ({s['significance']:.1f}σ)" for s in fits_ if s not in good]
        return Investigation(INSUFFICIENT_EVIDENCE, [f"Solo una temporada con detección ≥ {MIN_SEASON_SNR:g}σ; "
                                                     f"débil o ausente en: {', '.join(weak) or '—'}."], result)
    a, b = good[0], good[-1]
    disp = _season_disp(a, b)
    control = _control(frames, meas, reg, refs, ra0, dec0, (a["mjd"], b["mjd"]))
    result["control"] = control
    k_cal = control.get("calibration_factor", 1.0)
    disp.update(first=a["date_utc"], last=b["date_utc"],
                err_dxi_calibrated=disp["err_dxi"] * k_cal, err_deta_calibrated=disp["err_deta"] * k_cal,
                significance_calibrated=disp["significance"] / k_cal,
                total_arcsec=math.hypot(disp["dxi"], disp["deta"]))
    disp["total_err_arcsec"] = _total_err(disp["dxi"], disp["deta"], disp["err_dxi_calibrated"],
                                          disp["err_deta_calibrated"])
    disp["rate_arcsec_yr"] = disp["total_arcsec"] / (disp["delta_t_days"] / 365.25)
    result["displacement"] = disp
    if astrometry is not None and getattr(astrometry, "has_proper_motion", False):
        result["catalogue_comparison"] = _compare_catalogue(astrometry, disp, a, b, ra0, dec0)
    reasons = []
    sig = disp["significance_calibrated"]
    worst = control.get("max_significance_calibrated", 0.0)
    if a["confusion"] or b["confusion"]:
        reasons.append("Otra fuente comparable dentro del radio de búsqueda: posible confusión.")
    sat_seasons = [s for s in (a, b) if s["saturated_core"]]
    if sat_seasons and any(s["n_single_fits"] < 3 for s in sat_seasons):
        reasons.append("Núcleo saturado y menos de tres medidas individuales por temporada: no se puede estimar "
                       "empíricamente el sesgo de un ajuste con las alas de la PSF.")
    if control.get("n", 0) < MIN_REFS:
        reasons.append(f"Control estacionario con {control.get('n', 0)} estrellas (< {MIN_REFS}): no se pueden "
                       "calibrar las incertidumbres ni estimar falsos positivos.")
    if sig >= SIGNIFICANCE and sig > worst and not reasons:
        outcome = MOTION_MEASURED
        reasons.append(f"Desplazamiento de {disp['total_arcsec']:.2f} ± {disp['total_err_arcsec']:.2f}″ entre "
                       f"{a['date_utc']} y {b['date_utc']} ({disp['delta_t_days']:.0f} d): {sig:.1f}σ tras calibrar "
                       f"con {control['n']} estrellas estacionarias (máximo de control {worst:.1f}σ).")
        if sat_seasons:
            reasons.append("Núcleo saturado: posición medida con las alas de la PSF; el error incluye la dispersión "
                           "entre exposiciones.")
    else:
        outcome = INSUFFICIENT_EVIDENCE
        if sig < SIGNIFICANCE:
            reasons.append(f"Desplazamiento {disp['total_arcsec']:.2f} ± {disp['total_err_arcsec']:.2f}″ en "
                           f"{disp['delta_t_days']:.0f} d: {sig:.1f}σ, por debajo de {SIGNIFICANCE:g}σ.")
        elif sig <= worst:
            reasons.append(f"{sig:.1f}σ no supera el máximo alcanzado por una estrella de control ({worst:.1f}σ).")
    return Investigation(outcome, reasons, result)


def _f(v):
    v = float(v)
    return v if math.isfinite(v) else None


def _total_err(dx, dy, sx, sy):
    r = math.hypot(dx, dy)
    if r == 0:
        return math.hypot(sx, sy) / math.sqrt(2)
    return math.sqrt((dx * sx) ** 2 + (dy * sy) ** 2) / r


def _control(frames, meas, reg, refs, ra0, dec0, epochs) -> dict:
    """Stationary control: each reference star through the same chain (leave-one-out registration,
    season fit around its Gaia proper-motion track). Its displacement must be zero."""
    by_id = {s["source_id"]: s for s in refs}
    out = []
    for sid in reg["stars"]:
        loo = solve_registration(meas, exclude=sid)
        ents = _entries(frames, meas, loo)
        groups = seasons([e.mjd for e in ents])
        if len(groups) < 2:
            continue

        def track(e, s=by_id[sid]):
            return _gaia_shift(s, e.mjd, ra0, dec0)[0]

        sfs = [season_fit([ents[i] for i in g], track, ra0, dec0, 3.0, coarse=0.5) for g in groups]
        sfs = [s for s in sfs if s is not None and s["significance"] >= MIN_SEASON_SNR]
        if len(sfs) < 2:
            continue
        # residual offsets from the Gaia track; compare the seasons closest to the target's
        a = min(sfs, key=lambda s: abs(s["mjd"] - epochs[0]))
        b = min(sfs, key=lambda s: abs(s["mjd"] - epochs[1]))
        if a is b:
            continue
        ra_ = {"xi": a["dxi"], "eta": a["deta"], "cov": a["cov"], "mjd": a["mjd"]}
        rb_ = {"xi": b["dxi"], "eta": b["deta"], "cov": b["cov"], "mjd": b["mjd"]}
        d = _season_disp(ra_, rb_)
        out.append({"gaia_source_id": sid, "g": by_id[sid].get("phot_g_mean_mag"),
                    "dxi": d["dxi"], "deta": d["deta"], "err_dxi": d["err_dxi"], "err_deta": d["err_deta"],
                    "significance": d["significance"], "delta_t_days": d["delta_t_days"]})
    if not out:
        return {"n": 0, "stars": [], "calibration_factor": 1.0, "max_significance_calibrated": 0.0}
    z2 = np.array([c["significance"] ** 2 for c in out])
    # χ² with 2 degrees of freedom has median 1.386; a factor ≥ 1 brings the controls to it.
    k = max(1.0, math.sqrt(float(np.median(z2)) / 1.386)) if len(out) >= MIN_REFS else 1.0
    for c in out:
        c["significance_calibrated"] = c["significance"] / k
    return {"n": len(out), "stars": out, "calibration_factor": k,
            "max_significance_calibrated": max(c["significance_calibrated"] for c in out),
            "n_above_threshold": sum(c["significance_calibrated"] >= SIGNIFICANCE for c in out),
            "median_offset_arcsec": float(np.median([math.hypot(c["dxi"], c["deta"]) for c in out])),
            "rule": "Cada estrella de referencia se registra sin sí misma (leave-one-out) y se mide con el mismo "
                    "ajuste conjunto por temporada que el objetivo. Debe seguir su trayectoria Gaia (desplazamiento "
                    "residual nulo). El factor de calibración ≥ 1 lleva la mediana de sus χ² (2 g.l.) a 1.386."}


def _compare_catalogue(astro, disp, a, b, ra0, dec0) -> dict:
    """Catalogue-predicted displacement between the same season epochs (context, not evidence)."""
    pa, pb = astro.position_at(a["mjd"]), astro.position_at(b["mjd"])
    xa, ya = _tangent(*pa, ra0, dec0)
    xb, yb = _tangent(*pb, ra0, dec0)
    pdx, pdy = xb - xa, yb - ya
    ex, ey = disp["err_dxi_calibrated"], disp["err_deta_calibrated"]
    diff = math.hypot((disp["dxi"] - pdx) / ex, (disp["deta"] - pdy) / ey)
    return {"source": astro.source, "name": astro.name, "predicted_dxi": pdx, "predicted_deta": pdy,
            "predicted_total_arcsec": math.hypot(pdx, pdy),
            "difference_sigma": diff, "consistent_3sigma": diff <= 3.0,
            "note": "Predicción calculada con la astrometría del catálogo (incluye paralaje si existe). Solo se "
                    "compara al final; no interviene en la búsqueda, el ajuste ni la decisión."}


def to_jsonable(inv: Investigation) -> dict:
    def conv(v):
        if isinstance(v, dict):
            return {str(k): conv(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [conv(x) for x in v]
        if isinstance(v, (np.floating, float)):
            v = float(v)
            return v if math.isfinite(v) else None
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, np.bool_):
            return bool(v)
        if isinstance(v, np.ndarray):
            return conv(v.tolist())
        return v
    return conv({"outcome": inv.outcome, "outcome_label": inv.label, "reasons": inv.reasons, **inv.result})


# ----------------------------------------------------------------------------- epochs for astrometry
MOTION_FIELD_DEG = 0.2         # 12′ cutouts: more stationary references than the 6′ default
PER_SEASON = 4
MAX_SEASONS = 3


@dataclass
class MotionFrame:
    """One original image used by an investigation (same fields as sequence.Frame that are needed)."""

    image: object
    record: dict
    cutout_url: str
    path: object
    sha256: str


def select_epochs(records, ra: float, dec: float, detector: int, *, field_deg: float = MOTION_FIELD_DEG,
                  per_season: int = PER_SEASON, max_seasons: int = MAX_SEASONS) -> dict:
    """Choose original images for astrometry: one detector, the longest baseline.

    Seasons are groups of visits closer than SEASON_GAP_DAYS. The first and last seasons
    (and a middle one when ``max_seasons`` ≥ 3) are kept; inside each, the images whose
    field is farthest from the detector edges. Wavelength may differ between images of
    one detector (LVF): positions do not depend on it to first order, and each image is
    fitted with its own ePSF. Photometric comparability (Time Explorer S1–S9) is a
    different, stricter question and is not claimed here.
    """
    from .pairing import build_candidates
    if detector not in range(1, 7):
        raise MotionInputError("Detector fuera de 1–6.")
    if not 1 <= per_season <= 8 or not 2 <= max_seasons <= 4:
        raise MotionInputError("Entre 1 y 8 imágenes por temporada y entre 2 y 4 temporadas.")
    cands = [c for c in build_candidates(records, ra, dec, field_deg) if c.rec.detector == detector]
    groups = seasons([c.rec.mjd_mid for c in cands])
    # Seasons with enough images for an internal-consistency check, then the longest baseline.
    rich = [g for g in groups if len(g) >= min(3, per_season)] or groups
    if len(rich) <= max_seasons:
        chosen = rich
    else:
        idx = sorted({round(i * (len(rich) - 1) / (max_seasons - 1)) for i in range(max_seasons)})
        chosen = [rich[i] for i in idx]
    picks = []
    for g in chosen:
        best = sorted(g, key=lambda i: -cands[i].margin_px)[:per_season]
        picks += [cands[i] for i in sorted(best, key=lambda i: cands[i].rec.mjd_mid)]
    return {"candidates": len(cands), "seasons_available": len(groups),
            "season_dates": [[_mjd_date(cands[g[0]].rec.mjd_mid), _mjd_date(cands[g[-1]].rec.mjd_mid), len(g)]
                             for g in groups],
            "selected": picks, "field_deg": field_deg, "detector": detector,
            "rule": f"Mismo detector D{detector}; temporadas separadas > {SEASON_GAP_DAYS:g} d; primera, intermedia(s) "
                    f"y última (máx. {max_seasons}); hasta {per_season} imágenes por temporada, las más alejadas del "
                    "borde del detector."}


def _mjd_date(mjd):
    from astropy.time import Time
    return Time(mjd, format="mjd").isot[:10]


def fetch_frames(selection: dict, ra: float, dec: float, progress=None) -> list[MotionFrame]:
    """Download (or reuse from cache) the cutouts of a selection; every FITS stays untouched."""
    from . import archive, fitsdata
    urls = [archive.cutout_url(c.rec.access_url, ra, dec, selection["field_deg"]) for c in selection["selected"]]
    got = archive.fetch_many(urls, progress=progress)
    frames = []
    for c, u in zip(selection["selected"], urls):
        path = got[u]
        if isinstance(path, Exception):
            raise path
        frames.append(MotionFrame(image=fitsdata.load(path), record=c.rec.to_dict(), cutout_url=u, path=path,
                                  sha256=archive.sha256(path)))
    return frames
