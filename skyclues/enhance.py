"""Infrared S/N enhancement: inverse-variance combination of compatible SPHEREx exposures.

A physical and statistical product, not a cosmetic denoiser. Several authentic Level-2 exposures of
the SAME detector that cover the same sky are placed on one pixel grid and averaged with their
official variances. Nothing is smoothed, interpolated, filled or invented:

* every output pixel takes, from each exposure, the value of the native pixel that contains its
  centre (nearest neighbour through each WCS). Values are copied, never interpolated;
* only pixels valid under the strict mask (unusable + artifact flags, finite, variance > 0) take
  part. A pixel no exposure covers stays NaN;
* a single additive constant per exposure ties the residual sky levels (IMAGE - ZODI is not exactly
  zero-based and the zodiacal model error changes with date). It cannot create or remove a source;
* there is NO sigma-clipping of bright values: the official FLAGS already carry the pipeline's own
  transient/outlier detection, and a second clipping would remove real, undersampled star cores or
  the very source under study. A signal that comes from one exposure only is *labelled*, not deleted;
* the only values removed beyond the official mask are NON-PHYSICAL NEGATIVES: a pixel more than
  ``NONPHYSICAL_SIGMA`` below its own local sky AND below what the other exposures measure there
  (real files contain unflagged pixels at -100 sigma). No astronomical source is negative, so this
  cannot delete one; the number removed per exposure is reported.

Uncertainties: the placement can copy one native pixel into more than one output pixel, so output
pixels are not independent. ``linear_stat`` propagates the official variances exactly through that
mapping for any linear statistic (an aperture sum, a background-subtracted flux). The result is then
checked against the data with a *null image* (half of the exposures minus the other half): the sky
cancels and what remains is noise. Reported errors are never smaller than that empirical scatter.

Three purposes are kept apart (``PURPOSES``): a deep image of approximately stationary sky (the only
one produced here for display), a co-moving stack of a known moving body, and the comparison between
epochs. The motion detectors (``motion``, ``non_sidereal``) do not use this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math

import numpy as np
from astropy.wcs import WCS

from . import config, motion
from .geometry import separation_deg
from .non_sidereal import world_to_pixel

METHOD = "infrared-snr 1.0 (2026-11-15)"
PURPOSES = ("deep", "comoving")

# ---- selection thresholds, each with its reason ---------------------------------------------
#: Same effective LVF channel over the whole field (the limit Time Explorer already uses, S4).
#: Above it the product is a BROAD-BAND image: valid for detection and positions, not for
#: monochromatic brightness.
MONOCHROMATIC_BW = config.SPECTRAL_WARN_BW
#: The sky-level constant of an exposure is the median of its difference with the reference over
#: the pixels they share; below this number of shared pixels (the S5 minimum) it is not reliable.
MIN_SHARED_PIXELS = config.MIN_COMMON_VALID_PIXELS
#: A point source's S/N scales as 1/sqrt(noise-equivalent area). An exposure whose official ePSF is
#: this much wider than the group median would dilute the resolution for less than its share of
#: S/N; it is rejected instead of homogenising (blurring) the others.
MAX_PSF_AREA_RATIO = 1.5
#: Registration measured with common compact sources. A shift beyond half a native pixel moves the
#: flux of a star into its neighbours: the exposure is rejected. No correction is applied to the
#: others, so the stack cannot inherit a shift that its WCS does not have.
MAX_REGISTRATION_PX = 0.5
MIN_REGISTRATION_SOURCES = 3
#: A target that moves more than half a native pixel between the first and last exposure is blurred
#: by a sky-fixed stack.
MAX_TARGET_MOTION_PX = 0.5
#: A stacked signal is "from one exposure" when a single frame carries more than this fraction of the
#: quadratic S/N (transient, artifact or moving body): labelled, never counted as a stationary source.
SINGLE_EXPOSURE_FRACTION = 0.8
#: A value this many sigma below the exposure's own local sky and below the other exposures is not
#: sky: by chance it happens once in ~3 million pixels.
NONPHYSICAL_SIGMA = 5.0
TARGET_APERTURE_PX = 3.0     # co-moving stacks: radius where the object's own OUTLIER pixels are admitted
APERTURE_PX = 1.5            # native pixels (9.2 arcsec); holds the core of the undersampled PSF
ANNULUS_PX = (3.0, 6.0)
DETECTION_SIGMA = 5.0


class EnhanceError(ValueError):
    """The exposures cannot be combined for the stated purpose (the message says why)."""


# ----------------------------------------------------------------------------- data model
@dataclass(eq=False)
class Exposure:
    """One authentic Level-2 exposure and its provenance."""

    image: object                 # fitsdata.SpectralImage (read-only copy of the FITS)
    obs_id: str = ""
    mjd: float = float("nan")
    collection: str = ""
    url: str = ""
    sha256: str = ""

    @property
    def detector(self) -> int:
        return int(str(self.image.meta.get("DETECTOR")).lstrip("D"))

    def provenance(self) -> dict:
        m = self.image.meta
        return {"obs_id": self.obs_id, "mjd": self.mjd, "date_utc": str(m.get("DATE-AVG") or ""),
                "detector": self.detector, "collection": self.collection, "version": m.get("VERSION"),
                "exptime_s": m.get("XPOSURE"), "bunit": m.get("BUNIT"), "file": m.get("FILE"),
                "cutout_url": self.url, "sha256": self.sha256}


def exposure_from(obj) -> Exposure:
    """Adapter for ``sequence.Frame`` and ``non_sidereal.MovingFrame`` (or an Exposure)."""
    if isinstance(obj, Exposure):
        return obj
    img = obj.image
    row = getattr(obj, "row", None) or getattr(obj, "record", None) or {}
    return Exposure(image=img, obs_id=str(img.meta.get("OBSID") or row.get("obs_id") or ""),
                    mjd=float(img.meta.get("MJD-AVG") or row.get("mjd") or float("nan")),
                    collection=str(row.get("collection") or ""), url=str(getattr(obj, "cutout_url", "") or ""),
                    sha256=str(getattr(obj, "sha256", "") or ""))


@dataclass
class Stack:
    """A combined image, everything needed to audit it and the exposures it came from."""

    exposures: list[Exposure]
    selection: dict
    wcs: WCS
    shape: tuple
    oversample: int
    field: np.ndarray              # comparison field (circle of the requested FOV) on the grid
    data: np.ndarray               # (N, ny, nx) placed values minus the sky constant; NaN = not valid
    var: np.ndarray                # (N, ny, nx) official variances of the placed pixels
    weights: np.ndarray            # (N, ny, nx) weight of each placed pixel (0 = not used)
    index: list                    # per exposure: flat native index of every output pixel (-1 = none)
    native_var: list               # per exposure: flat native variance
    offsets: np.ndarray            # sky constant subtracted from each exposure (MJy/sr)
    image: np.ndarray              # combined surface brightness (MJy/sr); NaN where nothing is valid
    variance: np.ndarray           # per-pixel variance of the weighted mean: sum(w^2 var) / sum(w)^2
    n: np.ndarray                  # valid contributions per pixel
    coverage: np.ndarray           # exposures whose cutout covers the pixel (valid or not)
    lam: np.ndarray                # weighted mean wavelength per pixel (um)
    lam_spread_bw: np.ndarray      # (max - min) wavelength of the contributions / bandwidth
    reference: int
    placement: np.ndarray = None   # (2, ny, nx) weighted mean offset (grid px) between each output pixel
    #                                centre and the centres of the native pixels copied there
    null: np.ndarray = None        # (half A - half B) / 2
    null_variance: np.ndarray = None
    noise: dict = field(default_factory=dict)
    registration: dict = field(default_factory=dict)

    @property
    def n_exposures(self) -> int:
        return len(self.exposures)

    @property
    def best(self) -> int:
        """The exposure with the lowest noise (largest weight): the most demanding single reference."""
        w = [float(np.median(self.weights[i][self.weights[i] > 0])) if (self.weights[i] > 0).any() else 0.0
             for i in range(self.n_exposures)]
        return int(np.argmax(w))

    @property
    def pixel_scale_arcsec(self) -> float:
        return config.NOMINAL_PIXEL_SCALE_ARCSEC / self.oversample

    def single(self, i: int):
        """Exposure i alone on the same grid: (values, variance)."""
        return self.data[i], self.var[i]


# ----------------------------------------------------------------------------- instrument
def psf_area(img, x: float | None = None, y: float | None = None) -> float:
    """Noise-equivalent area (native pixels) of the official ePSF at (x, y): 1 / sum(p^2).

    Averaged over a 5x5 grid of sub-pixel phases, because the PSF is undersampled and the value
    for one phase is not representative."""
    ny, nx = img.shape
    x = (nx - 1) / 2 if x is None else x
    y = (ny - 1) / 2 if y is None else y
    psf = motion.psf_for(img, x, y)
    ky, kx = np.mgrid[-4:5, -4:5].astype(float)
    areas = []
    for dy in np.linspace(-0.4, 0.4, 5):
        for dx in np.linspace(-0.4, 0.4, 5):
            p = psf(kx - dx, ky - dy)
            s = float(p.sum())
            if s > 0:
                p = p / s
                areas.append(1.0 / float(np.sum(p * p)))
    return float(np.mean(areas)) if areas else float("nan")


def _lambda_at(img, ra, dec):
    x, y = world_to_pixel(img.wcs, ra, dec)
    ny, nx = img.shape
    if not (np.isfinite(x + y) and -0.5 <= x < nx - 0.5 and -0.5 <= y < ny - 0.5):
        return float("nan"), float("nan")
    ix, iy = int(round(float(x))), int(round(float(y)))
    return float(img.wavelength_um[iy, ix]), float(img.bandwidth_um[iy, ix])


# ----------------------------------------------------------------------------- selection
def select(exposures, ra: float, dec: float, field_deg: float, *, purpose: str = "deep",
           target_motion_arcsec: float | None = None) -> dict:
    """Which exposures may be combined, which are rejected and why, and what the product is.

    Never raises for a scientific reason: ``ok`` is False and ``reason`` explains it.
    """
    if purpose not in PURPOSES:
        raise ValueError(f"purpose debe ser uno de {PURPOSES}")
    exps = [exposure_from(e) for e in exposures]
    rejected, kept = [], []

    def drop(e, why):
        rejected.append({"obs_id": e.obs_id, "mjd": e.mjd, "reason": why})

    out = {"method": METHOD, "purpose": purpose, "ok": False, "reason": "", "rejected": rejected,
           "accepted": [], "warnings": []}
    if len(exps) < 2:
        out["reason"] = "More than one exposure is needed to combine."
        return out
    dets = sorted({e.detector for e in exps})
    if len(dets) > 1:
        out["reason"] = ("The exposures come from different detectors (" + ", ".join(f"D{d}" for d in dets) +
                         "): different bands, PSF and calibration. This product only combines one detector.")
        return out
    # One processing: cross-release compatibility has not been established (Time Explorer S8).
    groups: dict = {}
    for e in exps:
        groups.setdefault((e.collection, e.image.meta.get("VERSION"), e.image.meta.get("BUNIT")), []).append(e)
    main = max(groups.values(), key=len)
    for g in groups.values():
        if g is not main:
            for e in g:
                drop(e, "Collection, software version or units differ from the rest: calibrations are not mixed.")
    areas = {}
    for e in main:
        m = e.image.meta
        if str(m.get("L2DQAFLG", "")).strip() != "Pass":
            drop(e, f"Control de calidad oficial L2 = {m.get('L2DQAFLG')}.")
        elif m.get("FINAST") != 0:
            drop(e, f"Invalid fine astrometry (FINAST = {m.get('FINAST')}): it cannot be registered.")
        else:
            x, y = world_to_pixel(e.image.wcs, ra, dec)
            ny, nx = e.image.shape
            inside = np.isfinite(x + y) and 0 <= x < nx and 0 <= y < ny
            areas[id(e)] = psf_area(e.image, float(x) if inside else None, float(y) if inside else None)
            kept.append(e)
    finite = [a for a in areas.values() if np.isfinite(a)]
    if finite:
        med = float(np.median(finite))
        for e in list(kept):
            a = areas[id(e)]
            if np.isfinite(a) and a > MAX_PSF_AREA_RATIO * med:
                kept.remove(e)
                drop(e, f"Incompatible PSF: equivalent noise area {a:.1f} px against a median of {med:.1f} px "
                        f"(> {MAX_PSF_AREA_RATIO:g}×). Combining it would degrade the resolution.")
    kept.sort(key=lambda e: e.mjd)
    out["accepted"] = [e.obs_id for e in kept]
    out["exposures"] = kept
    if len(kept) < 2:
        out["reason"] = "After the quality checks fewer than two compatible exposures remain."
        return out
    lam = np.array([_lambda_at(e.image, ra, dec) for e in kept], float)
    ok_lam = np.isfinite(lam[:, 0])
    bw = float(np.nanmedian(lam[:, 1])) if ok_lam.any() else float("nan")
    spread = float((np.nanmax(lam[:, 0]) - np.nanmin(lam[:, 0])) / bw) if ok_lam.sum() >= 2 else float("nan")
    mjd = np.array([e.mjd for e in kept])
    out.update(
        detector=dets[0], n=len(kept), collection=kept[0].collection, version=kept[0].image.meta.get("VERSION"),
        bunit=kept[0].image.meta.get("BUNIT"),
        lambda_um=[float(v) for v in lam[:, 0]], bandwidth_um=bw,
        lambda_range_um=[float(np.nanmin(lam[:, 0])), float(np.nanmax(lam[:, 0]))] if ok_lam.any() else None,
        lambda_spread_centre_bw=spread,
        mjd=[float(v) for v in mjd], span_days=float(mjd.max() - mjd.min()),
        psf_area_px=[float(areas[id(e)]) for e in kept],
        psf_fwhm_arcsec=kept[0].image.meta.get("PSF_FWHM"))
    scale = config.NOMINAL_PIXEL_SCALE_ARCSEC
    if purpose == "deep" and target_motion_arcsec is not None and target_motion_arcsec > MAX_TARGET_MOTION_PX * scale:
        out["reason"] = (f"The target moves {target_motion_arcsec:.1f}″ between the first and the last date "
                         f"(more than {MAX_TARGET_MOTION_PX:g} pixels): a combination fixed on the sky would "
                         "blur it. The dates are compared separately.")
        return out
    out["ok"] = True
    return out


def product_kind(spread_bw: float) -> str:
    return "monochromatic" if np.isfinite(spread_bw) and spread_bw <= MONOCHROMATIC_BW else "broadband"


# ----------------------------------------------------------------------------- grid and placement
def _field_grid(ra, dec, field_deg, oversample):
    scale = config.NOMINAL_PIXEL_SCALE_ARCSEC / oversample
    n = int(math.ceil(field_deg * 3600 / scale)) + 2
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(n + 1) / 2, (n + 1) / 2]
    w.wcs.cdelt = [-scale / 3600, scale / 3600]
    return w, (n, n)


def _place(img, ra, dec):
    """For every grid position (ra, dec): flat index of the native pixel containing it (-1 = none)."""
    x, y = world_to_pixel(img.wcs, ra, dec)
    ny, nx = img.shape
    ok = np.isfinite(x) & np.isfinite(y)
    ix = np.rint(np.where(ok, x, 0)).astype(int)
    iy = np.rint(np.where(ok, y, 0)).astype(int)
    ok &= (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    return np.where(ok, iy * nx + ix, -1)


def _robust_std(a) -> float:
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    if a.size < 8:
        return float("nan")
    return float(1.4826 * np.median(np.abs(a - np.median(a))))


def frame_weights(data, var, in_field, weighting: str = "frame"):
    """Weights of every placed pixel (0 where it is not valid).

    ``frame`` (default): one inverse variance per exposure, the median official variance of its
    valid pixels in the field. The official VARIANCE includes the photon noise of the source itself,
    so a per-pixel inverse variance gives LESS weight to the exposures in which a star happens to
    fall centred on a pixel and biases bright sources low (measured: -5 % in M101). A weight that
    does not depend on the pixel's own signal is unbiased, and it is the inverse-variance optimum
    for the faint, background-limited sources this product is for.
    ``pixel``: the textbook per-pixel 1/variance, kept for comparison and tests."""
    ok = np.isfinite(data) & np.isfinite(var) & (var > 0)
    if weighting == "pixel":
        return np.where(ok, 1.0 / np.where(ok, var, 1.0), 0.0)
    if weighting != "frame":
        raise ValueError("weighting must be 'frame' or 'pixel'")
    w = np.zeros(data.shape)
    for i in range(len(data)):
        m = ok[i] & in_field
        if not m.any():
            m = ok[i]
        if m.any():
            w[i] = np.where(ok[i], 1.0 / float(np.median(var[i][m])), 0.0)
    return w


def _weighted(data, var, w):
    """Weighted mean over axis 0 with exact per-pixel variance: (mean, variance, n)."""
    den = w.sum(axis=0)
    used = w > 0
    mean = np.divide((np.where(used, data, 0.0) * w).sum(axis=0), den, out=np.full(den.shape, np.nan), where=den > 0)
    variance = np.divide((np.where(used, var, 0.0) * w * w).sum(axis=0), den * den,
                         out=np.full(den.shape, np.nan), where=den > 0)
    return mean, variance, used.sum(axis=0)


def combine(exposures, ra: float, dec: float, field_deg: float, *, purpose: str = "deep", oversample: int = 1,
            target_motion_arcsec: float | None = None, check_registration: bool = True,
            centres=None, weighting: str = "frame") -> Stack:
    """Select, place, tie sky levels and average. Raises EnhanceError when nothing valid can be made.

    ``oversample`` = 1 uses the native grid of the reference exposure (its own pixels are then
    untouched originals). ``oversample`` > 1 uses a north-up grid of finer pixels: the placement
    error falls with it, at the price of correlated output pixels (handled by ``linear_stat``).
    ``centres`` (purpose "comoving") gives one (ra, dec) per exposure: each is placed on the grid as
    if its centre were the grid centre, i.e. the stack follows a predicted track.
    """
    if oversample not in (1, 2, 3):
        raise ValueError("oversample must be 1, 2 or 3")
    exps_in = [exposure_from(e) for e in exposures]
    sel = select(exps_in, ra, dec, field_deg, purpose=purpose, target_motion_arcsec=target_motion_arcsec)
    if not sel["ok"]:
        raise EnhanceError(sel["reason"])
    exps = sel.pop("exposures")
    if purpose == "comoving":
        if centres is None or len(centres) != len(exps_in):
            raise ValueError("A combination that follows the object needs a predicted position for each exposure.")
        by_id = {id(e): c for e, c in zip(exps_in, centres)}
        centres = [by_id[id(e)] for e in exps]
        oversample = max(oversample, 1)

    # Reference: the exposure with most valid pixels in the field (earliest on ties).
    def field_valid(e, c=None):
        ny, nx = e.image.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        r, d = e.image.wcs.all_pix2world(xx, yy, 0)
        cr, cd = c or (ra, dec)
        return int((e.image.valid() & (separation_deg(r, d, cr, cd) <= field_deg / 2)).sum())

    counts = [field_valid(e, centres[i] if centres else None) for i, e in enumerate(exps)]
    reference = int(np.argmax(counts))
    if oversample == 1 and purpose == "deep":
        ref = exps[reference].image
        wcs, shape = ref.wcs, ref.shape
    else:
        wcs, shape = _field_grid(ra, dec, field_deg, oversample)
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    g_ra, g_dec = wcs.all_pix2world(xx, yy, 0)
    in_field = separation_deg(g_ra, g_dec, ra, dec) <= field_deg / 2

    data, var, index, native_var, lam, bwm = [], [], [], [], [], []
    target_outliers = []
    for i, e in enumerate(exps):
        img = e.image
        if centres:      # follow the track: same offsets from this exposure's predicted position
            from astropy.coordinates import SkyCoord
            import astropy.units as u
            c0 = SkyCoord(ra * u.deg, dec * u.deg)
            g = SkyCoord(g_ra * u.deg, g_dec * u.deg)
            moved = SkyCoord(centres[i][0] * u.deg, centres[i][1] * u.deg).directional_offset_by(
                c0.position_angle(g), c0.separation(g))
            idx = _place(img, moved.ra.deg, moved.dec.deg)
        else:
            idx = _place(img, g_ra, g_dec)
        valid = img.valid()
        if centres:
            # The pipeline flags an uncatalogued compact source as OUTLIER: a moving body is one. As in
            # the non-sidereal detector, that flag is ignored ONLY inside the object's aperture, around
            # this exposure's predicted position; everywhere else the strict mask stands.
            from .non_sidereal import target_valid
            tx, ty = world_to_pixel(img.wcs, centres[i][0], centres[i][1])
            py, px = np.indices(img.shape)
            with np.errstate(invalid="ignore"):
                near = np.hypot(px - float(tx), py - float(ty)) <= TARGET_APERTURE_PX
            extra = target_valid(img) & near & ~valid
            target_outliers.append(int(extra.sum()))
            valid = valid | extra
        flat_ok = valid.ravel()
        values = (img.image - img.zodi).ravel()
        v = img.variance.ravel()
        good = (idx >= 0) & flat_ok[np.clip(idx, 0, None)]
        good &= np.isfinite(values[np.clip(idx, 0, None)]) & np.isfinite(v[np.clip(idx, 0, None)]) & (v[np.clip(idx, 0, None)] > 0)
        safe = np.clip(idx, 0, None)
        data.append(np.where(good, values[safe], np.nan))
        var.append(np.where(good, v[safe], np.nan))
        lam.append(np.where(idx >= 0, img.wavelength_um.ravel()[safe], np.nan))
        bwm.append(np.where(idx >= 0, img.bandwidth_um.ravel()[safe], np.nan))
        index.append(idx)
        native_var.append(v)
    data, var, lam, bwm = np.array(data), np.array(var), np.array(lam), np.array(bwm)
    if centres:
        cy, cx = (shape[0] - 1) // 2, (shape[1] - 1) // 2
        sel["lambda_um"] = [float(v) for v in lam[:, cy, cx]]
        sel["bandwidth_um"] = float(np.nanmedian(bwm[:, cy, cx]))
        if np.isfinite(sel["lambda_um"]).any():
            sel["lambda_range_um"] = [float(np.nanmin(sel["lambda_um"])), float(np.nanmax(sel["lambda_um"]))]
            sel["lambda_spread_centre_bw"] = float((sel["lambda_range_um"][1] - sel["lambda_range_um"][0])
                                                   / sel["bandwidth_um"])
        sel["target_outlier_pixels_used"] = target_outliers
        sel["warnings"].append(
            "Combination FOLLOWING A PREDICTED TRAJECTORY: the stars end up shifted and the position of the "
            "object in this image is set by the ephemeris. It is not a measurement of its position or its motion.")
    coverage = np.sum([ix >= 0 for ix in index], axis=0)

    # Sky constants: median difference with the reference over shared valid pixels of the field.
    offsets = np.zeros(len(exps))
    keep = np.ones(len(exps), bool)
    for i in range(len(exps)):
        if i == reference:
            continue
        shared = in_field & np.isfinite(data[i]) & np.isfinite(data[reference])
        if shared.sum() < MIN_SHARED_PIXELS:
            keep[i] = False
            sel["rejected"].append({"obs_id": exps[i].obs_id, "mjd": exps[i].mjd, "reason":
                                    f"It only shares {int(shared.sum())} valid pixels with the reference "
                                    f"(< {MIN_SHARED_PIXELS}): its sky level cannot be linked."})
            continue
        offsets[i] = float(np.median((data[i] - data[reference])[shared]))

    registration = {"checked": False}
    if check_registration and purpose == "deep":
        registration = measure_registration(exps, reference)
        for i, r in enumerate(registration["frames"]):
            if keep[i] and r.get("rejected"):
                keep[i] = False
                sel["rejected"].append({"obs_id": exps[i].obs_id, "mjd": exps[i].mjd, "reason": r["rejected"]})

    if keep.sum() < 2:
        raise EnhanceError("Fewer than two exposures share enough valid sky to be combined.")
    if not keep.all():
        ref_obs = exps[reference].obs_id
        sel_idx = np.nonzero(keep)[0]
        exps = [exps[i] for i in sel_idx]
        data, var, lam, bwm = data[sel_idx], var[sel_idx], lam[sel_idx], bwm[sel_idx]
        index = [index[i] for i in sel_idx]
        native_var = [native_var[i] for i in sel_idx]
        offsets = offsets[sel_idx]
        coverage = np.sum([ix >= 0 for ix in index], axis=0)
        reference = next(i for i, e in enumerate(exps) if e.obs_id == ref_obs)
        registration["frames"] = [registration["frames"][i] for i in sel_idx] if registration.get("frames") else []
        for k in ("lambda_um", "mjd", "psf_area_px", "target_outlier_pixels_used"):
            if k in sel:
                sel[k] = [sel[k][i] for i in sel_idx]
        sel["accepted"] = [e.obs_id for e in exps]
        sel["n"] = len(exps)
        sel["span_days"] = float(max(sel["mjd"]) - min(sel["mjd"]))
        sel["lambda_range_um"] = [float(np.nanmin(sel["lambda_um"])), float(np.nanmax(sel["lambda_um"]))]
        sel["lambda_spread_centre_bw"] = float((sel["lambda_range_um"][1] - sel["lambda_range_um"][0]) / sel["bandwidth_um"])
    # Zero-sum constants: the level of the combination is the mean calibrated level, not one frame's.
    offsets = offsets - offsets.mean()
    data = data - offsets[:, None, None]
    sel["nonphysical_negative_pixels"] = _drop_nonphysical(data, var, oversample)

    w = frame_weights(data, var, in_field, weighting)
    image, variance, n = _weighted(data, var, w)
    ok = w > 0
    den = w.sum(axis=0)
    sel["weighting"] = weighting
    with np.errstate(invalid="ignore"):
        lam_eff = np.divide((np.where(ok, lam, 0.0) * w).sum(axis=0), den, out=np.full(den.shape, np.nan), where=den > 0)
        lam_used = np.where(ok, lam, np.nan)
        any_ok = ok.any(axis=0)
        hi = np.where(any_ok, np.nanmax(np.where(ok, lam, -np.inf), axis=0), np.nan)
        lo = np.where(any_ok, np.nanmin(np.where(ok, lam, np.inf), axis=0), np.nan)
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            bw_med = np.nanmedian(np.where(ok, bwm, np.nan), axis=0)
        spread = (hi - lo) / bw_med
    del lam_used
    in_common = in_field & (n >= 2)
    sel["lambda_spread_field_bw"] = float(np.nanmax(spread[in_common])) if in_common.any() else float("nan")
    worst = np.nanmax([sel["lambda_spread_field_bw"], sel["lambda_spread_centre_bw"]])
    sel["kind"] = product_kind(float(worst))
    if sel["kind"] == "broadband":
        sel["warnings"].append(
            "BROADBAND product: it combines different wavelengths of the same detector. It is useful for detecting "
            "and locating sources; its brightness is not monochromatic and must not be compared between dates or with a channel.")
    stack = Stack(exposures=exps, selection=sel, wcs=wcs, shape=shape, oversample=oversample, field=in_field,
                  data=data, var=var, weights=w, index=index, native_var=native_var, offsets=offsets, image=image,
                  variance=variance, n=n, coverage=coverage, lam=lam_eff, lam_spread_bw=spread,
                  reference=reference, registration=registration)
    _placement(stack)
    _null_image(stack)
    return stack


def _placement(stack: Stack) -> None:
    """Where the copied native pixels really are, relative to the output pixels that hold them.

    Nearest-neighbour placement moves every value by up to half a native pixel. Averaged over the
    exposures the displacement mostly cancels; what remains at each position is a known, computable
    registration error of the combined image (``placement``), summarised in ``registration``.
    A source measured at x appears displaced by minus this vector: ``placement_correction`` undoes it.
    Sky-fixed stacks only (a co-moving stack has no single sky position per pixel).
    """
    if stack.selection.get("purpose") != "deep":
        return
    ny, nx = stack.shape
    yy, xx = np.mgrid[0:ny, 0:nx].astype(float)
    num = np.zeros((2, ny, nx))
    den = stack.weights.sum(axis=0)
    for i, e in enumerate(stack.exposures):
        idx = stack.index[i]
        w = stack.weights[i]
        if not (w > 0).any():
            continue
        iy, ix = np.divmod(np.clip(idx, 0, None), e.image.shape[1])
        ra, dec = e.image.wcs.all_pix2world(ix.astype(float), iy.astype(float), 0)
        gx, gy = world_to_pixel(stack.wcs, ra, dec)
        ok = (w > 0) & np.isfinite(gx) & np.isfinite(gy)
        num[0] += np.where(ok, (gx - xx) * w, 0.0)
        num[1] += np.where(ok, (gy - yy) * w, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        stack.placement = np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)
    m = stack.field & np.isfinite(stack.placement[0])
    if m.any():
        r = np.hypot(stack.placement[0][m], stack.placement[1][m]) * stack.pixel_scale_arcsec
        stack.registration["placement_rms_arcsec"] = float(np.sqrt(np.mean(r ** 2)))
        stack.registration["placement_max_arcsec"] = float(r.max())
        stack.registration["placement_note"] = (
            "Weighted mean displacement between the centre of each pixel of the combination and the centres of the "
            "native pixels copied into it (nearest neighbour). It is the product's own registration error: "
            "a position measured on the combined image inherits it unless it is corrected.")


def placement_correction(stack: Stack, x: float, y: float) -> tuple[float, float]:
    """(dx, dy) in grid pixels to ADD to a position measured on the combined image at (x, y)."""
    if stack.placement is None:
        return 0.0, 0.0
    ny, nx = stack.shape
    xi, yi = int(np.clip(round(x), 0, nx - 1)), int(np.clip(round(y), 0, ny - 1))
    sl = (slice(max(0, yi - 1), yi + 2), slice(max(0, xi - 1), xi + 2))
    px, py = stack.placement[0][sl], stack.placement[1][sl]
    img = stack.image[sl]
    ok = np.isfinite(px) & np.isfinite(py) & np.isfinite(img)
    if not ok.any():
        return 0.0, 0.0
    w = np.where(ok, img - np.min(img[ok]), 0.0)          # the pixels that carry the source weigh most
    if w.sum() <= 0:
        w = ok.astype(float)
    return float(np.sum(np.where(ok, px, 0.0) * w) / w.sum()), float(np.sum(np.where(ok, py, 0.0) * w) / w.sum())


def _drop_nonphysical(data, var, oversample: int) -> list[int]:
    """Set to NaN the placed values that are negative beyond noise with respect to BOTH the exposure's
    own local sky and the other exposures at the same sky position. Returns the count per exposure."""
    import warnings
    counts = []
    bad_all = np.zeros(data.shape, bool)
    for i in range(len(data)):
        others = np.delete(data, i, axis=0)
        v_others = np.delete(var, i, axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            ref = np.nanmedian(others, axis=0)
            v_ref = np.nanmedian(v_others, axis=0)
        sigma = np.sqrt(var[i])
        with np.errstate(invalid="ignore"):
            below_sky = data[i] - _local_median(data[i], 5 * oversample) < -NONPHYSICAL_SIGMA * sigma
            below_rest = data[i] - ref < -NONPHYSICAL_SIGMA * np.sqrt(var[i] + v_ref)
        bad_all[i] = np.isfinite(data[i]) & below_sky & below_rest
    for i in range(len(data)):
        counts.append(int(bad_all[i].sum()))
        data[i][bad_all[i]] = np.nan
        var[i][bad_all[i]] = np.nan
    return counts


# ----------------------------------------------------------------------------- registration check
def measure_registration(exps, reference: int) -> dict:
    """Shift of each exposure relative to the reference, from compact sources both contain.

    The same ePSF position fit and strict mask as the non-sidereal detector's star registration
    (``non_sidereal._common_stars``), which is not modified. Nothing is corrected with it: an
    exposure beyond ``MAX_REGISTRATION_PX`` is rejected, the rest are combined with their own WCS.
    """
    from types import SimpleNamespace
    from . import non_sidereal

    scale = config.NOMINAL_PIXEL_SCALE_ARCSEC
    ref = SimpleNamespace(image=exps[reference].image)
    frames, radial = [], []
    for i, e in enumerate(exps):
        if i == reference:
            frames.append({"obs_id": e.obs_id, "reference": True, "n_sources": None, "shift_arcsec": [0.0, 0.0]})
            continue
        try:
            shifts = np.array(non_sidereal._common_stars(ref, SimpleNamespace(image=e.image), []))
        except Exception as err:  # noqa: BLE001 - a failed check is reported, never assumed good
            frames.append({"obs_id": e.obs_id, "n_sources": 0, "error": str(err)[:160]})
            continue
        row = {"obs_id": e.obs_id, "n_sources": int(len(shifts))}
        if len(shifts) >= MIN_REGISTRATION_SOURCES:
            med = np.median(shifts, axis=0)
            scatter = float(np.median(np.linalg.norm(shifts - med, axis=1)) * 1.4826)
            row.update(shift_arcsec=[float(med[0]), float(med[1])], shift_px=float(np.linalg.norm(med) / scale),
                       scatter_arcsec=scatter, error_arcsec=float(scatter / math.sqrt(len(shifts))))
            radial.append(float(np.linalg.norm(med)))
            if np.linalg.norm(med) > MAX_REGISTRATION_PX * scale:
                row["rejected"] = (f"Registration: shifted {np.linalg.norm(med):.1f}″ with respect to the reference according to "
                                   f"{len(shifts)} common sources (> {MAX_REGISTRATION_PX:g} pixels).")
        frames.append(row)
    verified = [f for f in frames if "shift_arcsec" in f and not f.get("reference")]
    return {"checked": True, "frames": frames, "n_verified": len(verified),
            "max_shift_arcsec": max(radial) if radial else None,
            "rms_shift_arcsec": float(np.sqrt(np.mean(np.square(radial)))) if radial else None,
            "note": "Median displacement of common compact sources (ePSF fit, strict mask) with respect to the "
                    "reference exposure. No correction is applied." if verified else
                    "Not enough common compact sources: the registration relies on the official WCS (FINAST = 0) "
                    "and could not be verified with stars."}


# ----------------------------------------------------------------------------- noise: null image
def _halves(stack: Stack):
    """Two interleaved halves, alternating in wavelength order so both sample the same band."""
    lam = np.array(stack.selection.get("lambda_um") or np.arange(stack.n_exposures), float)
    order = np.lexsort((np.arange(len(lam)), np.nan_to_num(lam, nan=np.inf)))
    a = np.zeros(len(lam), bool)
    a[order[0::2]] = True
    return a, ~a


def _null_image(stack: Stack) -> None:
    """(half A - half B) / 2: stationary sky cancels, noise stays. Calibrates the reported errors."""
    a, b = _halves(stack)
    if a.sum() < 1 or b.sum() < 1:
        return
    ma, va, _ = _weighted(stack.data[a], stack.var[a], stack.weights[a])
    mb, vb, _ = _weighted(stack.data[b], stack.var[b], stack.weights[b])
    stack.null = (ma - mb) / 2
    stack.null_variance = (va + vb) / 4
    z = stack.null / np.sqrt(stack.null_variance)
    region = stack.field & np.isfinite(z)
    # Bright sources leave sampling residuals in a difference of undersampled images: they are a
    # systematic of the placement, measured separately, not part of the pixel-noise calibration.
    faint = stack.field & (np.abs(stack.image - _local_median(stack.image, 5 * stack.oversample))
                           < 5 * np.sqrt(stack.variance))
    scale = _robust_std(z[faint & region]) if (faint & region).sum() >= 50 else float("nan")
    # The same test for single exposures: differences of pairs, in the same faint pixels.
    order = np.argsort(np.where(a, 0, 1), kind="stable")
    pairs = []
    for i, j in zip(np.nonzero(a)[0], np.nonzero(b)[0]):
        zz = (stack.data[i] - stack.data[j]) / np.sqrt(stack.var[i] + stack.var[j])
        m = faint & np.isfinite(zz)
        if m.sum() >= 50:
            pairs.append(_robust_std(zz[m]))
    del order
    single = float(np.median(pairs)) if pairs else float("nan")
    stack.noise = {
        "null_scale": scale, "null_pixels": int((faint & region).sum()),
        "scale": float(max(1.0, scale)) if np.isfinite(scale) else None,
        "single_scale": single, "single_pairs": [float(v) for v in pairs],
        "single": float(max(1.0, single)) if np.isfinite(single) else None,
        "null_scale_all_pixels": _robust_std(z[region]) if region.sum() >= 50 else float("nan"),
        "note": "Robust scatter of the null image (half A − half B)/2 divided by its formal error, over the "
                "pixels without a bright source: 1 = the official variances describe the real noise. «single_scale» "
                "is the same test with differences of two individual exposures. The published errors of "
                "the combination and of each exposure are multiplied by that factor when it is greater than 1; they are never "
                "reduced."}


def _local_median(img, half: int = 5):
    """Median in a (2*half+1)^2 window ignoring NaN (large-scale sky and galaxy light)."""
    pad = np.pad(img, half, constant_values=np.nan)
    win = np.lib.stride_tricks.sliding_window_view(pad, (2 * half + 1, 2 * half + 1))
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmedian(win, axis=(2, 3))


# ----------------------------------------------------------------------------- exact error propagation
def linear_stat(stack: Stack, coeffs: np.ndarray, which: int | None = None):
    """Value and standard error of sum(coeffs * image) with exact variance propagation.

    ``which`` = None: the combined image; an integer: that exposure alone on the same grid. The
    statistic is defined only if every pixel with a non-zero coefficient is valid in the image used
    (returns None otherwise). The variance follows each native pixel through the placement, so a
    native pixel copied to several output pixels is counted once with its summed coefficient
    (correlated output pixels). The error includes the empirical null-image factor when > 1.
    """
    use = coeffs != 0
    if not use.any():
        return None
    scale = stack.noise.get("scale") or 1.0
    if which is not None:
        d = stack.data[which]
        if not np.isfinite(d[use]).all():
            return None
        value = float(np.sum(coeffs[use] * d[use]))
        variance = _native_variance(stack, which, coeffs * 1.0)
        return value, math.sqrt(variance) * (stack.noise.get("single") or 1.0)
    if not np.isfinite(stack.image[use]).all():
        return None
    value = float(np.sum(coeffs[use] * stack.image[use]))
    w = stack.weights
    den = w.sum(axis=0)
    variance = 0.0
    for i in range(stack.n_exposures):
        frac = np.divide(w[i], den, out=np.zeros(den.shape), where=den > 0)
        variance += _native_variance(stack, i, coeffs * frac)
    return value, math.sqrt(variance) * scale


def _native_variance(stack: Stack, i: int, c: np.ndarray) -> float:
    idx = stack.index[i].ravel()
    cf = c.ravel()
    m = (cf != 0) & (idx >= 0)
    if not m.any():
        return 0.0
    summed = np.bincount(idx[m], weights=cf[m], minlength=stack.native_var[i].size)
    nz = summed != 0
    return float(np.sum(summed[nz] ** 2 * stack.native_var[i][nz]))


def aperture_coeffs(stack: Stack, x: float, y: float, radius_px: float = APERTURE_PX,
                    annulus_px=ANNULUS_PX) -> np.ndarray | None:
    """Coefficients of 'aperture sum minus the annulus mean': a linear, local-sky-subtracted flux.

    Radii in native pixels. The annulus uses the pixels of the ring valid in the combined image and
    in every exposure, so the same pixels define the sky for all the images compared."""
    o = stack.oversample
    ny, nx = stack.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    r = np.hypot(xx - x, yy - y)
    ap = r <= radius_px * o
    ring = (r >= annulus_px[0] * o) & (r <= annulus_px[1] * o) & np.isfinite(stack.data).all(axis=0)
    if ap.sum() < 3 or ring.sum() < 20 or not ap[max(0, int(round(y)))][max(0, int(round(x)))]:
        return None
    c = np.zeros(stack.shape)
    c[ap] = 1.0
    c[ring] -= ap.sum() / ring.sum()
    return c


# ----------------------------------------------------------------------------- measurements
def _flux_mjy(stack: Stack, value: float) -> float:
    """Sum of MJy/sr over pixels -> mJy."""
    omega = (stack.pixel_scale_arcsec / 206264.806) ** 2
    return value * omega * 1e9


def measure_source(stack: Stack, x: float, y: float) -> dict | None:
    """The same aperture statistic in every exposure and in the combination."""
    c = aperture_coeffs(stack, x, y)
    if c is None:
        return None
    full = linear_stat(stack, c)
    if full is None:
        return None
    singles = [linear_stat(stack, c, i) for i in range(stack.n_exposures)]
    snr_i = [s[0] / s[1] if s and s[1] > 0 else None for s in singles]
    have = [v for v in snr_i if v is not None]
    if not have:
        return None
    ra, dec = stack.wcs.all_pix2world(x, y, 0)
    snr = full[0] / full[1]
    med = float(np.median(have))
    quad = float(np.sum(np.square(have)))
    fluxes = np.array([s[0] for s in singles if s])
    errs = np.array([s[1] for s in singles if s])
    wmean = float(np.sum(fluxes / errs ** 2) / np.sum(1 / errs ** 2))
    chi2 = float(np.sum(((fluxes - wmean) / errs) ** 2) / max(len(fluxes) - 1, 1))
    return {"x": float(x), "y": float(y), "ra": float(ra), "dec": float(dec),
            "flux_mjy": _flux_mjy(stack, full[0]), "flux_err_mjy": _flux_mjy(stack, full[1]),
            "snr": float(snr), "snr_single": [None if v is None else float(v) for v in snr_i],
            "snr_single_median": med, "snr_single_best": float(max(have)),
            "snr_reference": snr_i[stack.reference],
            "snr_best_exposure": snr_i[stack.best],
            "gain": float(snr / med) if med > 0 else None,
            "gain_vs_best": float(snr / snr_i[stack.best]) if snr_i[stack.best] and snr_i[stack.best] > 0 else None,
            "gain_ideal": float(math.sqrt(quad) / med) if med > 0 else None,
            "n_measured": len(have),
            "flux_ratio_to_single_mean": float(full[0] / wmean) if wmean != 0 else None,
            "single_scatter_chi2": chi2,
            "single_exposure_fraction": float(max(np.square(have)) / quad) if quad > 0 else None}


def dominance(stack: Stack, x: int, y: int, sky=None) -> float | None:
    """Largest share of a detection's weighted signal (3x3 pixels around its peak, above the local
    sky) that comes from ONE exposure. A stationary source seen by N similar exposures gives ~1/N; an
    unflagged cosmic ray, a hot pixel or a moving body gives ~1. Works on the pixels each exposure
    really has there, so a frame with a masked neighbour cannot hide (unlike an aperture statistic)."""
    ny, nx = stack.shape
    o = stack.oversample
    sl = (slice(max(0, y - o), y + o + 1), slice(max(0, x - o), x + o + 1))
    sky = _local_median(stack.image, 5 * o) if sky is None else sky
    contrib = []
    for i in range(stack.n_exposures):
        w = stack.weights[i][sl]
        d = np.where(w > 0, stack.data[i][sl] - sky[sl], 0.0)
        contrib.append(float(np.sum(d * w)))
    pos = [c for c in contrib if c > 0]
    total = float(np.sum(pos))
    return float(max(pos) / total) if total > 0 else None


def _kernel(stack: Stack):
    """Detection kernel: official ePSF of the reference at the field centre, sampled on the grid."""
    img = stack.exposures[stack.reference].image
    psf = motion.psf_for(img, (img.shape[1] - 1) / 2, (img.shape[0] - 1) / 2)
    h = 3 * stack.oversample
    ky, kx = np.mgrid[-h:h + 1, -h:h + 1].astype(float)
    k = psf(kx / stack.oversample, ky / stack.oversample)
    return k / k.sum()


def significance_map(stack: Stack, layer="stack") -> np.ndarray:
    """PSF-matched significance of compact sources above the local sky.

    ``layer``: "stack", "null", "negative" (the combined image with its sign reversed) or an
    exposure index. The map is normalised by its own robust scatter, so the threshold means the
    same in a single exposure, in the combination and in the null image whatever the pixel
    correlations; NaN where the matched filter lacks valid pixels."""
    if layer == "stack":
        d, v = stack.image, stack.variance
    elif layer == "negative":
        d, v = -stack.image, stack.variance
    elif layer == "null":
        d, v = stack.null, stack.null_variance
    else:
        d, v = stack.single(int(layer))
    ok = np.isfinite(d) & np.isfinite(v) & (v > 0)
    resid = d - _local_median(d, 5 * stack.oversample)
    k = _kernel(stack)
    w = np.where(ok, 1.0 / np.where(ok, v, 1.0), 0.0)
    num = motion._correlate(np.where(ok & np.isfinite(resid), resid, 0.0) * w, k)
    den = motion._correlate(w, k * k)
    full = motion._correlate(ok.astype(float), (k > 0.02 * k.max()).astype(float))
    need = float((k > 0.02 * k.max()).sum())
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where((den > 0) & (full >= need - 0.5), num / np.sqrt(den), np.nan)
    s = _robust_std(z[stack.field & np.isfinite(z)])
    return z / s if np.isfinite(s) and s > 0 else np.full(z.shape, np.nan)


def detect(stack: Stack, layer="stack", threshold: float = DETECTION_SIGMA, zmap=None) -> list[dict]:
    z = significance_map(stack, layer) if zmap is None else zmap
    zz = np.where(np.isfinite(z) & stack.field, z, -np.inf)
    out = []
    for x, y, s in motion.find_peaks(zz, threshold, sep=2 * stack.oversample):
        ra, dec = stack.wcs.all_pix2world(x, y, 0)
        out.append({"x": int(x), "y": int(y), "significance": float(s), "ra": float(ra), "dec": float(dec)})
    return out


def _centroid(img, x, y, half):
    """Flux-weighted centroid and noise-equivalent area of a compact source above its local sky."""
    ny, nx = img.shape
    xi, yi = int(round(x)), int(round(y))
    if xi - half < 0 or yi - half < 0 or xi + half >= nx or yi + half >= ny:
        return None
    st = img[yi - half:yi + half + 1, xi - half:xi + half + 1]
    if not np.isfinite(st).all():
        return None
    yy, xx = np.mgrid[-half:half + 1, -half:half + 1]
    edge = (np.abs(xx) == half) | (np.abs(yy) == half)
    f = st - np.median(st[edge])
    core = np.hypot(xx, yy) <= half - 1
    f = np.where(core, f, 0.0)
    tot = f.sum()
    if tot <= 0:
        return None
    return {"x": xi + float((f * xx).sum() / tot), "y": yi + float((f * yy).sum() / tot),
            "area": float(tot * tot / np.sum(f * f))}


def evaluate(stack: Stack, *, threshold: float = DETECTION_SIGMA, bright_snr: float = 30.0) -> dict:
    """Quantitative before/after: noise, source S/N gain, resolution, positions and false detections."""
    o = stack.oversample
    field_px = stack.field & np.isfinite(stack.image)
    ref = stack.reference
    sig_single = [float(np.sqrt(np.nanmedian(stack.var[i][stack.field & np.isfinite(stack.var[i])])))
                  * (stack.noise.get("single") or 1.0) for i in range(stack.n_exposures)]
    sig_stack = float(np.sqrt(np.nanmedian(stack.variance[field_px]))) * (stack.noise.get("scale") or 1.0)
    z_stack = significance_map(stack, "stack")
    found = detect(stack, "stack", threshold, z_stack)
    z_singles = [significance_map(stack, i) for i in range(stack.n_exposures)]
    singles = [detect(stack, i, threshold, z) for i, z in enumerate(z_singles)]
    null = detect(stack, "null", threshold) if stack.null is not None else []
    negative = detect(stack, "negative", threshold)
    # A bright star leaves a residual in the difference of two undersampled halves (it falls on a
    # different pixel phase in each exposure). That is a sampling systematic AT a real source, not a
    # false source: only null-image peaks away from every combined-image source count as spurious.
    near = 3 * o
    null_elsewhere = [d for d in null if all(math.hypot(d["x"] - s["x"], d["y"] - s["y"]) > near for s in found)]
    # ...and a peak that one exposure shows on its own is a feature of that exposure (an unflagged
    # cosmic ray, a moving body), not something the combination created. What is left is spurious.
    def one_exposure(d):
        vals = [abs(float(z[d["y"], d["x"]])) for z in z_singles if np.isfinite(z[d["y"], d["x"]])]
        return bool(vals) and max(vals) >= threshold
    null_transient = [d for d in null_elsewhere if one_exposure(d)]
    null_spurious = [d for d in null_elsewhere if not one_exposure(d)]

    sources = []
    sky = _local_median(stack.image, 5 * o)
    for s in found:
        m = measure_source(stack, s["x"], s["y"])
        peak_single = [float(z[s["y"], s["x"]]) if np.isfinite(z[s["y"], s["x"]]) else None for z in z_singles]
        dom = dominance(stack, s["x"], s["y"], sky)
        row = {**s, "significance_single": peak_single,
               "detected_in_single": int(sum(v is not None and v >= threshold for v in peak_single)),
               "n_contributions": int(stack.n[s["y"], s["x"]]), "dominance": dom,
               "single_exposure_only": bool(stack.n_exposures >= 3 and dom is not None
                                            and dom > SINGLE_EXPOSURE_FRACTION)}
        if m:
            row.update({k: m[k] for k in ("flux_mjy", "flux_err_mjy", "snr", "snr_single", "snr_single_median",
                                           "snr_single_best", "snr_reference", "snr_best_exposure", "gain",
                                           "gain_vs_best", "gain_ideal",
                                           "flux_ratio_to_single_mean", "single_scatter_chi2",
                                           "single_exposure_fraction")})
            row["single_exposure_only"] = bool(row["single_exposure_only"] or (
                stack.n_exposures >= 3 and m["single_exposure_fraction"] is not None
                and m["single_exposure_fraction"] > SINGLE_EXPOSURE_FRACTION))
        sources.append(row)
    new = [s for s in sources if s["detected_in_single"] == 0 and not s.get("single_exposure_only")]
    measured = [s for s in sources if s.get("gain") is not None and s["snr_single_median"] > 3
                and not s.get("single_exposure_only")]
    gains = np.array([s["gain"] for s in measured])
    ideal = np.array([s["gain_ideal"] for s in measured])
    vs_best = np.array([s["gain_vs_best"] for s in measured if s.get("gain_vs_best") is not None
                        and s["snr_best_exposure"] > 3])
    bright = [s for s in measured if s["snr"] >= bright_snr]

    # Resolution and positions: centroid and noise-equivalent area of bright compact sources, in the
    # combination and in each exposure on the same grid.
    half = 3 * o
    areas, shifts = [], []
    for s in bright:
        c = _centroid(stack.image, s["x"], s["y"], half)
        cs = [_centroid(stack.data[i], s["x"], s["y"], half) for i in range(stack.n_exposures)]
        cs = [v for v in cs if v]
        if c and len(cs) >= 2:
            areas.append((c["area"], float(np.median([v["area"] for v in cs]))))
            mx, my = np.mean([v["x"] for v in cs]), np.mean([v["y"] for v in cs])
            shifts.append((c["x"] - mx, c["y"] - my))
    areas, shifts = np.array(areas), np.array(shifts)
    px = stack.pixel_scale_arcsec
    out = {
        "method": METHOD, "kind": stack.selection["kind"], "n_exposures": stack.n_exposures,
        "pixel_noise_mjysr": {"single_median": float(np.median(sig_single)), "single": sig_single,
                              "reference": sig_single[ref], "best_single": sig_single[stack.best],
                              "combined": sig_stack,
                              "ratio": float(np.median(sig_single) / sig_stack),
                              "ratio_vs_best": float(sig_single[stack.best] / sig_stack),
                              "ideal_ratio": float(math.sqrt(np.median(stack.n[field_px])))},
        "noise_calibration": stack.noise,
        "contributions": {"median": float(np.median(stack.n[field_px])), "min": int(stack.n[field_px].min()),
                          "max": int(stack.n[field_px].max()),
                          "field_fraction_valid": float(field_px.sum() / max(stack.field.sum(), 1)),
                          "field_fraction_all": float((stack.field & (stack.n == stack.n_exposures)).sum()
                                                      / max(stack.field.sum(), 1))},
        "detections": {"threshold": threshold, "combined": len(found),
                       "single": [len(s) for s in singles], "single_median": float(np.median([len(s) for s in singles])),
                       "reference": len(singles[ref]), "new_in_combined": len(new),
                       "single_exposure_only": int(sum(bool(s.get("single_exposure_only")) for s in sources)),
                       "null_image": len(null), "null_image_elsewhere": len(null_elsewhere),
                       "null_image_at_sources": len(null) - len(null_elsewhere),
                       "null_image_single_exposure": len(null_transient),
                       "null_image_spurious": len(null_spurious),
                       "negative_image": len(negative)},
        "gain": {"n_sources": int(len(gains)),
                 "median": float(np.median(gains)) if len(gains) else None,
                 "p16": float(np.percentile(gains, 16)) if len(gains) else None,
                 "p84": float(np.percentile(gains, 84)) if len(gains) else None,
                 "ideal_median": float(np.median(ideal)) if len(ideal) else None,
                 "vs_best_exposure_median": float(np.median(vs_best)) if len(vs_best) else None,
                 "vs_best_exposure_n": int(len(vs_best)),
                 "sqrt_n": float(math.sqrt(stack.n_exposures))},
        "photometry": {"n_sources": len(bright),
                       "flux_ratio_median": float(np.median([s["flux_ratio_to_single_mean"] for s in bright]))
                       if bright else None,
                       "flux_ratio_scatter": _robust_std([s["flux_ratio_to_single_mean"] for s in bright])
                       if len(bright) >= 8 else None,
                       "single_scatter_chi2_median": float(np.median([s["single_scatter_chi2"] for s in bright]))
                       if bright else None},
        "resolution": {"n_sources": int(len(areas)),
                       "area_combined_px": float(np.median(areas[:, 0])) / o ** 2 if len(areas) else None,
                       "area_single_px": float(np.median(areas[:, 1])) / o ** 2 if len(areas) else None,
                       "area_ratio": float(np.median(areas[:, 0] / areas[:, 1])) if len(areas) else None,
                       "width_ratio": float(np.sqrt(np.median(areas[:, 0] / areas[:, 1]))) if len(areas) else None},
        "astrometry": {"n_sources": int(len(shifts)),
                       "median_shift_arcsec": [float(v) * px for v in np.median(shifts, axis=0)] if len(shifts) else None,
                       "rms_shift_arcsec": float(np.sqrt(np.mean(np.sum(shifts ** 2, axis=1)))) * px if len(shifts) else None,
                       "note": "Centroid in the combination minus the mean of the centroids of the individual exposures "
                               "on the same grid."},
        "registration": stack.registration, "sources": sources,
    }
    return out


def verdict(metrics: dict, *, min_gain: float = 1.2) -> dict:
    """Accept only a measured gain with no material loss of validity. Reasons are explicit."""
    reasons, ok = [], True
    g = metrics["gain"]["median"]
    if g is None or metrics["gain"]["n_sources"] < 3:
        ok = False
        reasons.append("There are not at least three measurable sources to quantify the gain.")
    elif g < min_gain:
        ok = False
        reasons.append(f"Median S/N gain {g:.2f} < {min_gain:g}: the combination does not provide a measurable improvement.")
    else:
        # The demanding reference: the best single exposure, not the typical one. A set in which one
        # exposure alone is nearly as good as the combination is not an improvement.
        b = metrics["gain"]["vs_best_exposure_median"]
        if b is None:
            b = metrics["pixel_noise_mjysr"]["ratio_vs_best"]
        if b < min_gain:
            ok = False
            reasons.append(f"Compared with the best individual exposure the gain is only {b:.2f} (< {min_gain:g}): "
                           "the combination does not provide a measurable improvement over it.")
    det = metrics["detections"]
    limit = max(1, 0.05 * det["combined"])
    if det["null_image_spurious"] > limit:
        ok = False
        reasons.append(f"The null image contains {det['null_image_spurious']} detections far from any source and with no "
                       "origin in a specific exposure: noise or registration produces spurious structures.")
    if det["negative_image"] > limit:
        ok = False
        reasons.append(f"The inverted combined image contains {det['negative_image']} detections: there is negative "
                       "structure that the noise does not explain.")
    res = metrics["resolution"]
    if res["width_ratio"] is not None and res["width_ratio"] > 1.25:
        ok = False
        reasons.append(f"The PSF broadens by {100 * (res['width_ratio'] - 1):.0f} %: material loss of resolution.")
    ast = metrics["astrometry"]
    if ast["median_shift_arcsec"] is not None and np.hypot(*ast["median_shift_arcsec"]) > 0.25 * config.NOMINAL_PIXEL_SCALE_ARCSEC:
        ok = False
        reasons.append("The positions in the combination shift with respect to the individual exposures.")
    ph = metrics["photometry"]
    if ph["flux_ratio_median"] is not None and abs(ph["flux_ratio_median"] - 1) > 0.05:
        ok = False
        reasons.append(f"The flux of the bright sources changes by {100 * (ph['flux_ratio_median'] - 1):+.1f} %.")
    if ok:
        reasons.append(f"Median S/N gain {g:.2f} over {metrics['gain']['n_sources']} sources "
                       f"({metrics['gain']['vs_best_exposure_median'] or metrics['pixel_noise_mjysr']['ratio_vs_best']:.2f} "
                       "against the best exposure), with no spurious detections "
                       "in the null image above the control and no material degradation of resolution, "
                       "positions or fluxes.")
    return {"accepted": bool(ok), "reasons": reasons}


# ----------------------------------------------------------------------------- finding exposures
#: Exposures of one visit season: the limit the non-sidereal stacks already use ("more than seven
#: days: stability is not assumed"). Inside it a star with 10 arcsec/yr moves 0.4 arcsec (0.06 px).
NEARBY_DAYS = 7.0
MAX_NEARBY = 12              # ~4 MB per cutout: at most ~50 MB for one enhanced image


def nearby_exposures(records, ra: float, dec: float, field_deg: float, detector: int, mjd: float, *,
                     collection: str | None = None, window_days: float = NEARBY_DAYS,
                     max_frames: int = MAX_NEARBY) -> list:
    """Archive exposures of ``detector`` that contain the whole field within ``window_days`` of ``mjd``.

    Same detector and same collection only; any LVF position (the result is then a broad-band
    product, stated as such by ``combine``). Nearest in time first, returned in time order.
    """
    from .pairing import build_candidates

    cands = [c for c in build_candidates(records, ra, dec, field_deg)
             if c.rec.detector == detector and abs(c.rec.mjd_mid - mjd) <= window_days
             and (collection is None or c.rec.collection == collection)]
    cands.sort(key=lambda c: abs(c.rec.mjd_mid - mjd))
    return sorted(cands[:max_frames], key=lambda c: c.rec.mjd_mid)


def fetch_exposures(cands, ra: float, dec: float, field_deg: float, progress=None) -> tuple[list[Exposure], list[dict]]:
    """Cutouts of the candidates (cache first). Returns (exposures, failures); FITS stay untouched."""
    from . import archive, fitsdata

    urls = [archive.cutout_url(c.rec.access_url, ra, dec, field_deg) for c in cands]
    got = archive.fetch_many(urls, progress=progress)
    exps, failures = [], []
    for c, u in zip(cands, urls):
        path = got[u]
        if isinstance(path, Exception):
            failures.append({"obs_id": c.rec.obs_id, "cutout_url": u, "error": str(path)[:200]})
            continue
        img = fitsdata.load(path)
        exps.append(Exposure(image=img, obs_id=str(img.meta.get("OBSID") or c.rec.obs_id),
                             mjd=float(img.meta.get("MJD-AVG") or c.rec.mjd_mid), collection=c.rec.collection,
                             url=u, sha256=archive.sha256(path)))
    return exps, failures


def summary(stack: Stack, metrics: dict) -> dict:
    """JSON-able record of a combination: what went in, what came out, and the checks."""
    sel = {k: v for k, v in stack.selection.items() if k != "exposures"}
    return {"method": METHOD, "selection": sel, "exposures": [e.provenance() for e in stack.exposures],
            "sky_constants_mjysr": [float(v) for v in stack.offsets],
            "weights_relative": [float(np.median(stack.weights[i][stack.weights[i] > 0]) /
                                       max(float(np.max(stack.weights)), 1e-300))
                                 if (stack.weights[i] > 0).any() else 0.0 for i in range(stack.n_exposures)],
            "reference_exposure": stack.exposures[stack.reference].obs_id,
            "best_exposure": stack.exposures[stack.best].obs_id,
            "grid": {"oversample": stack.oversample, "pixel_arcsec": stack.pixel_scale_arcsec,
                     "shape": list(stack.shape),
                     "note": "native grid of the reference exposure" if stack.oversample == 1 and
                             stack.selection.get("purpose") == "deep" else "grid with north up"},
            "metrics": {k: v for k, v in metrics.items() if k != "sources"},
            "sources": metrics.get("sources", []), "verdict": verdict(metrics)}


def repeatability(stack: Stack, sources, *, max_snr: float = 30.0) -> dict | None:
    """Model-free check of the gain: do two independent halves of the exposures agree better than
    two single exposures do? Uses only differences of the same aperture flux, no variance model.

    For N equal exposures the scatter of (half A - half B) should be sqrt(N/2) times smaller than
    the scatter of (exposure i - exposure j). Faint sources only: for bright ones the difference is
    dominated by the pixel phase of the undersampled PSF, which is not noise.
    """
    a, b = _halves(stack)
    if a.sum() < 2 or b.sum() < 2:
        return None
    ma, _, na = _weighted(stack.data[a], stack.var[a], stack.weights[a])
    mb, _, nb = _weighted(stack.data[b], stack.var[b], stack.weights[b])
    pairs = list(zip(np.nonzero(a)[0], np.nonzero(b)[0]))
    d_half, d_single = [], []
    for s in sources:
        if s.get("snr") is None or s["snr"] > max_snr or s.get("single_exposure_only"):
            continue
        c = aperture_coeffs(stack, s["x"], s["y"])
        if c is None:
            continue
        use = c != 0
        if not (np.isfinite(ma[use]).all() and np.isfinite(mb[use]).all()
                and (na[use] == a.sum()).all() and (nb[use] == b.sum()).all()):
            continue
        d_half.append(float(np.sum(c[use] * (ma[use] - mb[use]))))
        for i, j in pairs:
            d_single.append(float(np.sum(c[use] * (stack.data[i][use] - stack.data[j][use]))))
    if len(d_half) < 8:
        return None
    sh, ss = _robust_std(d_half), _robust_std(d_single)
    return {"n_sources": len(d_half), "n_single_pairs": len(pairs),
            "scatter_half_mjy": _flux_mjy(stack, sh), "scatter_single_mjy": _flux_mjy(stack, ss),
            "ratio": float(ss / sh) if sh > 0 else None, "expected_ratio": float(math.sqrt(stack.n_exposures / 2)),
            "note": "Robust scatter of the aperture-flux difference between two individual exposures, "
                    "divided by that of two independent halves of the set, for sources with combined S/N "
                    f"< {max_snr:g}. No variance model."}
