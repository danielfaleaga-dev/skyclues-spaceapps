"""Scientific comparability of two SPHEREx observations of the same field.

Defined comparison
------------------
Surface brightness (IMAGE - ZODI, MJy/sr) of the same sky pixels, observed by
the same detector at the same effective LVF channel (|delta lambda| small
compared with the local bandwidth), on different dates, restricted to pixels
that are valid (finite, positive variance, no unusable/artifact FLAGS) in
both observations.

Pixel correspondence uses each file's own celestial WCS (TAN-SIP). The pixels
of B are *placed* onto A's grid by nearest-neighbour lookup: values are copied
unchanged, never interpolated, and pixels without a valid counterpart stay
NaN.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config
from .fitsdata import SpectralImage
from .geometry import separation_deg
from .quality import SATURATION


@dataclass
class PairEvaluation:
    criteria: list[dict]
    metrics: dict
    common: np.ndarray            # bool on A grid
    field_mask: np.ndarray        # bool on A grid
    valid_a: np.ndarray
    valid_b_on_a: np.ndarray
    in_b: np.ndarray
    b_index: tuple[np.ndarray, np.ndarray]   # (iy, ix) of B pixel for each A pixel
    dlambda_bw: np.ndarray        # (lambda_A - lambda_B)/bandwidth_A on A grid (NaN outside overlap)
    notes: list[str] = field(default_factory=list)

    @property
    def admissible(self) -> bool:
        return all(c["status"] != "fail" for c in self.criteria)

    @property
    def warnings(self) -> list[dict]:
        return [c for c in self.criteria if c["status"] == "warn"]


def map_onto(a: SpectralImage, b: SpectralImage):
    """For every A pixel, the nearest B pixel (iy, ix) and whether it exists."""
    ny, nx = a.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    ra, dec = a.wcs.all_pix2world(xx, yy, 0)
    bx, by = b.wcs.all_world2pix(ra, dec, 0)
    ix = np.rint(bx).astype(int)
    iy = np.rint(by).astype(int)
    nby, nbx = b.shape
    inside = (ix >= 0) & (ix < nbx) & (iy >= 0) & (iy < nby)
    ix = np.clip(ix, 0, nbx - 1)
    iy = np.clip(iy, 0, nby - 1)
    return iy, ix, inside, ra, dec


def place_on_a(values_b: np.ndarray, b_index, inside: np.ndarray, valid: np.ndarray | None = None):
    """Copy B values onto A's grid (nearest neighbour); NaN where undefined."""
    iy, ix = b_index
    out = values_b[iy, ix].astype(float)
    ok = inside.copy()
    if valid is not None:
        ok &= valid[iy, ix]
    out[~ok] = np.nan
    return out


def pixel_at(img: SpectralImage, ra: float, dec: float):
    x, y = img.wcs.all_world2pix([[ra, dec]], 0)[0]
    return float(x), float(y)


def lambda_at(img: SpectralImage, ra: float, dec: float):
    x, y = pixel_at(img, ra, dec)
    ix, iy = int(round(x)), int(round(y))
    ny, nx = img.shape
    if not (0 <= ix < nx and 0 <= iy < ny):
        return float("nan"), float("nan")
    return float(img.wavelength_um[iy, ix]), float(img.bandwidth_um[iy, ix])


def _status(ok_pass: bool, ok_warn: bool = False) -> str:
    return "pass" if ok_pass else ("warn" if ok_warn else "fail")


def evaluate_pair(a: SpectralImage, b: SpectralImage, ra: float, dec: float,
                  field_deg: float, collections: tuple[str, str] | None = None,
                  mask_classes=("unusable", "artifact")) -> PairEvaluation:
    iy, ix, in_b, ra_a, dec_a = map_onto(a, b)
    sep = separation_deg(ra_a, dec_a, ra, dec)
    field_mask = sep <= field_deg / 2
    valid_a = a.valid(mask_classes)
    valid_b = b.valid(mask_classes)
    valid_b_on_a = in_b & valid_b[iy, ix]
    common = field_mask & valid_a & valid_b_on_a

    n_field = int(field_mask.sum())
    n_common = int(common.sum())
    coverage = n_common / n_field if n_field else 0.0
    geom_overlap = float((field_mask & in_b).sum() / n_field) if n_field else 0.0

    lam_b_on_a = place_on_a(b.wavelength_um, (iy, ix), in_b)
    dl = (a.wavelength_um - lam_b_on_a) / a.bandwidth_um
    dl_common = np.abs(dl[common])
    lam_a_t, bw_a_t = lambda_at(a, ra, dec)
    lam_b_t, bw_b_t = lambda_at(b, ra, dec)
    dl_target = abs(lam_a_t - lam_b_t) / bw_a_t if np.isfinite(bw_a_t) else float("nan")

    mjd_a, mjd_b = a.meta["MJD-AVG"], b.meta["MJD-AVG"]
    dt = abs(mjd_b - mjd_a)

    sat_bits = a.flag_defs.names_bitmask(SATURATION)
    sat_a = float(np.count_nonzero((a.flags & sat_bits)[field_mask]) / max(n_field, 1))
    b_field = np.zeros(b.shape, bool)
    b_field[iy[field_mask & in_b], ix[field_mask & in_b]] = True
    sat_b = float(np.count_nonzero((b.flags & sat_bits)[b_field]) / max(b_field.sum(), 1))

    criteria = [
        {"id": "C1", "criterion": "Mismo detector (misma banda instrumental)",
         "value": f"D{a.meta['DETECTOR']} / D{b.meta['DETECTOR']}", "threshold": "igual",
         "status": _status(a.meta["DETECTOR"] == b.meta["DETECTOR"])},
        {"id": "C2", "criterion": "Fechas de observación diferentes",
         "value": f"Δt = {dt:.2f} d", "threshold": f"≥ {config.MIN_TIME_SEPARATION_DAYS} d",
         "status": _status(dt >= config.MIN_TIME_SEPARATION_DAYS)},
        {"id": "C3", "criterion": "Mismo canal efectivo en el objetivo (LVF)",
         "value": f"|Δλ| = {abs(lam_a_t - lam_b_t) * 1000:.1f} nm = {dl_target:.2f} × ancho de banda",
         "threshold": f"≤ {config.SPECTRAL_PASS_BW} (aviso ≤ {config.SPECTRAL_WARN_BW})",
         "status": _status(dl_target <= config.SPECTRAL_PASS_BW, dl_target <= config.SPECTRAL_WARN_BW)},
        {"id": "C4", "criterion": "Desajuste espectral máximo en la zona común",
         "value": (f"máx |Δλ| = {np.max(dl_common) if dl_common.size else float('nan'):.2f} × ancho de banda; "
                   f"{np.mean(dl_common <= config.SPECTRAL_PASS_BW) if dl_common.size else 0:.0%} de la zona común "
                   f"≤ {config.SPECTRAL_PASS_BW}"),
         "threshold": f"≤ {config.SPECTRAL_WARN_BW}",
         "status": _status(bool(dl_common.size) and np.max(dl_common) <= config.SPECTRAL_WARN_BW, True)},
        {"id": "C5", "criterion": "Cobertura común válida del campo",
         "value": f"{coverage:.1%} ({n_common} px; solapamiento geométrico {geom_overlap:.1%})",
         "threshold": f"≥ {config.COVERAGE_PASS:.0%} (aviso ≥ {config.COVERAGE_WARN:.0%})",
         "status": _status(coverage >= config.COVERAGE_PASS and n_common >= config.MIN_COMMON_VALID_PIXELS,
                           coverage >= config.COVERAGE_WARN and n_common >= config.MIN_COMMON_VALID_PIXELS)},
        {"id": "C6", "criterion": "Control de calidad oficial L2 (L2DQAFLG)",
         "value": f"{a.meta['L2DQAFLG']} / {b.meta['L2DQAFLG']}", "threshold": "Pass / Pass",
         "status": _status(str(a.meta["L2DQAFLG"]).strip() == "Pass" and str(b.meta["L2DQAFLG"]).strip() == "Pass")},
        {"id": "C7", "criterion": "Astrometría fina válida (FINAST = 0)",
         "value": f"{a.meta['FINAST']} / {b.meta['FINAST']}", "threshold": "0 / 0",
         "status": _status(a.meta["FINAST"] == 0 and b.meta["FINAST"] == 0, True)},
        {"id": "C8", "criterion": "Mismo procesamiento (colección y versión de software)",
         "value": f"{(collections or ('?', '?'))[0]} v{a.meta['VERSION']} / {(collections or ('?', '?'))[1]} v{b.meta['VERSION']}",
         "threshold": "iguales (si difieren: aviso de calibración)",
         "status": _status((collections is None or collections[0] == collections[1])
                           and a.meta["VERSION"] == b.meta["VERSION"], True)},
        {"id": "C9", "criterion": "Saturación en el campo (OVERFLOW/NONLINEAR)",
         "value": f"{sat_a:.2%} / {sat_b:.2%}", "threshold": f"≤ {config.SATURATION_WARN_FRACTION:.1%}",
         "status": _status(max(sat_a, sat_b) <= config.SATURATION_WARN_FRACTION, True)},
    ]

    za = float(np.nanmedian(a.zodi[field_mask]))
    zb = float(np.nanmedian(place_on_a(b.zodi, (iy, ix), in_b)[field_mask]))
    metrics = {
        "target_radec_deg": [float(ra), float(dec)],
        "mask_classes": list(mask_classes),
        "field_deg": field_deg,
        "n_field_px": n_field,
        "n_common_px": n_common,
        "coverage_common_valid": coverage,
        "geometric_overlap": geom_overlap,
        "valid_fraction_a": float(valid_a[field_mask].mean()) if n_field else 0.0,
        "valid_fraction_b_on_a": float(valid_b_on_a[field_mask].mean()) if n_field else 0.0,
        "lambda_target_um": [lam_a_t, lam_b_t],
        "bandwidth_target_um": [bw_a_t, bw_b_t],
        "dlambda_target_bw": dl_target,
        "dlambda_common_median_bw": float(np.median(dl_common)) if dl_common.size else None,
        "dlambda_common_max_bw": float(np.max(dl_common)) if dl_common.size else None,
        "fraction_common_within_pass_bw": float(np.mean(dl_common <= config.SPECTRAL_PASS_BW)) if dl_common.size else 0.0,
        "delta_t_days": dt,
        "mjd": [mjd_a, mjd_b],
        "saturation_fraction": [sat_a, sat_b],
        "zodi_median_mjysr": [za, zb],
    }
    notes = []
    if abs(za - zb) > 0.05 * max(abs(za), abs(zb), 1e-9):
        notes.append(
            f"El fondo zodiacal modelado difiere entre fechas ({za:.3f} vs {zb:.3f} MJy/sr): "
            "compare IMAGE − ZODI, no IMAGE en bruto."
        )
    if a.meta.get("HE_AIRGLOW_CONT") or b.meta.get("HE_AIRGLOW_CONT"):
        notes.append("Detectores 1–2: posible contaminación por airglow de He I (HE_AIRGLOW_CONT).")
    dl_full = np.where(field_mask & in_b, dl, np.nan)
    return PairEvaluation(criteria=criteria, metrics=metrics, common=common, field_mask=field_mask,
                          valid_a=valid_a, valid_b_on_a=valid_b_on_a, in_b=in_b, b_index=(iy, ix),
                          dlambda_bw=dl_full, notes=notes)
