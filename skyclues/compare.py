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


def spectral_status(value_bw: float) -> str:
    """lambda mismatch in bandwidth units: <= SPECTRAL_PASS_BW pass, <= SPECTRAL_WARN_BW
    warn, above it fail (not comparable). NaN (cannot be evaluated) fails."""
    if value_bw is None or not np.isfinite(value_bw):
        return "fail"
    return _status(value_bw <= config.SPECTRAL_PASS_BW, value_bw <= config.SPECTRAL_WARN_BW)


def finast_status(values) -> str:
    """FINAST (fine-astrometry status, Explanatory Supplement): 0 good -> pass;
    1 partial solution (offsets of a couple of pixels in the image corners) -> warn;
    >= 2 poor, "should not be used", or missing/unreadable -> fail."""
    try:
        v = [int(x) for x in values]
    except (TypeError, ValueError):
        return "fail"
    if any(x >= 2 or x < 0 for x in v):
        return "fail"
    return "warn" if any(x == 1 for x in v) else "pass"


#: What a criterion's result rests on (shown to the user).
BASIS_EFFECTIVE = "effective"
#: IRSA only publishes images with L2DQA = PASS and FINAST = 0 (Explanatory
#: Supplement §3.2.12): these checks re-read the header but cannot discriminate
#: among archive products; they only protect against non-standard files.
BASIS_ARCHIVE = "archive guarantee"


def evaluate_pair(a: SpectralImage, b: SpectralImage, ra: float, dec: float,
                  field_deg: float, collections: tuple[str, str] | None = None,
                  mask_classes=("unusable", "artifact"), astrometry=None) -> PairEvaluation:
    """``ra, dec`` is the field centre; with ``astrometry`` the target
    wavelength of each image is read at the position calculated for its date."""
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
    pos_a = astrometry.position_at(a.meta["MJD-AVG"]) if astrometry is not None else (ra, dec)
    pos_b = astrometry.position_at(b.meta["MJD-AVG"]) if astrometry is not None else (ra, dec)
    lam_a_t, bw_a_t = lambda_at(a, *pos_a)
    lam_b_t, bw_b_t = lambda_at(b, *pos_b)
    dl_target = abs(lam_a_t - lam_b_t) / bw_a_t if np.isfinite(bw_a_t) else float("nan")

    mjd_a, mjd_b = a.meta["MJD-AVG"], b.meta["MJD-AVG"]
    dt = abs(mjd_b - mjd_a)

    sat_bits = a.flag_defs.names_bitmask(SATURATION)
    sat_a = float(np.count_nonzero((a.flags & sat_bits)[field_mask]) / max(n_field, 1))
    b_field = np.zeros(b.shape, bool)
    b_field[iy[field_mask & in_b], ix[field_mask & in_b]] = True
    sat_b = float(np.count_nonzero((b.flags & sat_bits)[b_field]) / max(b_field.sum(), 1))

    criteria = [
        {"id": "C1", "criterion": "Same detector (same instrument band)",
         "value": f"D{a.meta['DETECTOR']} / D{b.meta['DETECTOR']}", "threshold": "igual",
         "status": _status(a.meta["DETECTOR"] == b.meta["DETECTOR"])},
        {"id": "C2", "criterion": "Different observation dates",
         "value": f"Δt = {dt:.2f} d", "threshold": f"≥ {config.MIN_TIME_SEPARATION_DAYS} d",
         "status": _status(dt >= config.MIN_TIME_SEPARATION_DAYS)},
        {"id": "C3", "criterion": "Same effective channel at the target (LVF)",
         "value": f"|Δλ| = {abs(lam_a_t - lam_b_t) * 1000:.1f} nm = {dl_target:.2f} × bandwidth",
         "threshold": f"≤ {config.SPECTRAL_PASS_BW} (warning ≤ {config.SPECTRAL_WARN_BW}; rejection above)",
         "status": spectral_status(dl_target)},
        {"id": "C4", "criterion": "Maximum spectral mismatch in the common area",
         "value": (f"max |Δλ| = {np.max(dl_common):.2f} × bandwidth; "
                   f"{np.mean(dl_common <= config.SPECTRAL_PASS_BW):.0%} of the common area "
                   f"≤ {config.SPECTRAL_PASS_BW}") if dl_common.size else "no common area",
         "threshold": f"≤ {config.SPECTRAL_PASS_BW} (warning ≤ {config.SPECTRAL_WARN_BW}; rejection above)",
         "status": spectral_status(float(np.max(dl_common)) if dl_common.size else float("nan"))},
        {"id": "C5", "criterion": "Valid common coverage of the field",
         "value": f"{coverage:.1%} ({n_common} px; geometric overlap {geom_overlap:.1%})",
         "threshold": f"≥ {config.COVERAGE_PASS:.0%} (warning ≥ {config.COVERAGE_WARN:.0%})",
         "status": _status(coverage >= config.COVERAGE_PASS and n_common >= config.MIN_COMMON_VALID_PIXELS,
                           coverage >= config.COVERAGE_WARN and n_common >= config.MIN_COMMON_VALID_PIXELS)},
        {"id": "C6", "criterion": "Official L2 quality control (L2DQAFLG)",
         "value": f"{a.meta['L2DQAFLG']} / {b.meta['L2DQAFLG']}", "threshold": "Pass / Pass",
         "status": _status(str(a.meta["L2DQAFLG"]).strip() == "Pass" and str(b.meta["L2DQAFLG"]).strip() == "Pass"),
         "basis": BASIS_ARCHIVE},
        {"id": "C7", "criterion": "Valid fine astrometry (FINAST)",
         "value": f"{a.meta.get('FINAST')} / {b.meta.get('FINAST')}",
         "threshold": "0 / 0 (1 = partial solution: warning; ≥ 2 = unusable: rejection)",
         "status": finast_status([a.meta.get("FINAST"), b.meta.get("FINAST")]), "basis": BASIS_ARCHIVE},
        {"id": "C8", "criterion": "Same processing (collection and software version)",
         "value": f"{(collections or ('?', '?'))[0]} v{a.meta['VERSION']} / {(collections or ('?', '?'))[1]} v{b.meta['VERSION']}",
         "threshold": "identical (if they differ: calibration warning)",
         "status": _status((collections is None or collections[0] == collections[1])
                           and a.meta["VERSION"] == b.meta["VERSION"], True)},
        {"id": "C9", "criterion": "Saturation in the field (OVERFLOW/NONLINEAR)",
         "value": f"{sat_a:.2%} / {sat_b:.2%}", "threshold": f"≤ {config.SATURATION_WARN_FRACTION:.1%}",
         "status": _status(max(sat_a, sat_b) <= config.SATURATION_WARN_FRACTION, True)},
    ]
    for c in criteria:
        c.setdefault("basis", BASIS_EFFECTIVE)

    za = float(np.nanmedian(a.zodi[field_mask]))
    zb = float(np.nanmedian(place_on_a(b.zodi, (iy, ix), in_b)[field_mask]))
    metrics = {
        "target_radec_deg": [float(ra), float(dec)],
        "target_expected_radec_deg": [list(map(float, pos_a)), list(map(float, pos_b))],
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
            f"The modelled zodiacal background differs between dates ({za:.3f} vs {zb:.3f} MJy/sr): "
            "compare IMAGE − ZODI, not raw IMAGE."
        )
    if a.meta.get("HE_AIRGLOW_CONT") or b.meta.get("HE_AIRGLOW_CONT"):
        notes.append("Detectors 1–2: possible contamination by He I airglow (HE_AIRGLOW_CONT).")
    dl_full = np.where(field_mask & in_b, dl, np.nan)
    return PairEvaluation(criteria=criteria, metrics=metrics, common=common, field_mask=field_mask,
                          valid_a=valid_a, valid_b_on_a=valid_b_on_a, in_b=in_b, b_index=(iy, ix),
                          dlambda_bw=dl_full, notes=notes)
