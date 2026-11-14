"""Temporal sequences of N comparable SPHEREx observations.

This module is the programming interface for the time player. A
``TemporalSequence`` holds N authentic observations of the same field, sorted
chronologically, with:

* the original Level-2 data of every frame (``frame.image``, never modified);
* a common reference pixel grid (the earliest frame) onto which every frame
  is *placed* by nearest-neighbour lookup through its own WCS (values copied,
  never interpolated, never invented). This grid is used for the statistics
  (masks, coverage, criteria); its position error is up to 0.5 px;
* the exact geometry of every frame's *native* pixels in reference-grid
  coordinates (``native_corners``), for display without resampling: each
  native pixel keeps its value and is drawn at its true sky position;
* per-frame validity masks, the comparison field and the common valid region;
* global comparability criteria S1-S9, evaluated over the whole set (all
  frames at once, not only consecutive pairs).

Typical use::

    seq, report = find_sequence(ra, dec, field_deg=0.1)
    for i, f in enumerate(seq.frames):
        data = seq.frame_data(i)          # MJy/sr on the reference grid, NaN = no valid data
        native = seq.native_data(i)       # MJy/sr on the frame's own grid (exact geometry)
        X, Y = seq.native_corners(i)      # its pixel corners in reference pixel coordinates
        f.date_utc, f.obs_id, f.lambda_target_um, f.quality
    seq.common_mask, seq.field_mask, seq.wcs, seq.criteria
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from astropy.time import Time

from . import archive, config, fitsdata
from .astrometry import Astrometry
from .compare import (BASIS_ARCHIVE, BASIS_EFFECTIVE, finast_status, lambda_at, map_onto, place_on_a,
                      spectral_status)
from .fitsdata import SpectralImage
from .geometry import separation_deg
from .pairing import build_candidates, estimate_wavelengths
from .quality import SATURATION

STRICT = ("unusable", "artifact")


# --------------------------------------------------------------------------- data model
@dataclass
class Frame:
    """One authentic observation inside a sequence."""

    image: SpectralImage              # original Level-2 data (read-only copy of the FITS)
    record: dict                      # archive metadata (SIA2) + provenance
    cutout_url: str
    path: Path
    sha256: str
    index_on_ref: tuple = None        # (iy, ix) of this frame's pixel for every reference pixel
    inside_ref: np.ndarray = None     # reference pixels covered by this frame's cutout
    lambda_target_um: float = float("nan")
    bandwidth_target_um: float = float("nan")
    quality: dict = field(default_factory=dict)
    #: expected (calculated) target position at this frame's date: (ra, dec) in
    #: degrees. A calculation from catalogue astrometry, not a detection.
    expected_radec: tuple = None

    @property
    def obs_id(self) -> str:
        return str(self.image.meta["OBSID"])

    @property
    def mjd(self) -> float:
        return float(self.image.meta["MJD-AVG"])

    @property
    def date_utc(self) -> str:
        return str(self.image.meta["DATE-AVG"])

    @property
    def detector(self) -> int:
        return int(self.image.meta["DETECTOR"])

    @property
    def collection(self) -> str:
        return self.record.get("collection", "")

    def on_reference(self, values: np.ndarray, valid: np.ndarray | None = None) -> np.ndarray:
        """Copy per-pixel ``values`` of this frame onto the reference grid (NaN if undefined)."""
        return place_on_a(values, self.index_on_ref, self.inside_ref, valid)

    def valid_on_reference(self, mask_classes=STRICT) -> np.ndarray:
        iy, ix = self.index_on_ref
        return self.inside_ref & self.image.valid(mask_classes)[iy, ix]

    def summary(self) -> dict:
        return {
            "obs_id": self.obs_id, "date_utc": self.date_utc, "mjd": self.mjd,
            "collection": self.collection, "detector": self.detector,
            "lambda_target_um": self.lambda_target_um, "bandwidth_target_um": self.bandwidth_target_um,
            "exptime_s": self.image.meta.get("XPOSURE"), "software_version": self.image.meta.get("VERSION"),
            "file_name": self.record.get("file_name"), "access_url": self.record.get("access_url"),
            "cutout_url": self.cutout_url, "local_file": self.path.name, "sha256": self.sha256,
            "expected_target_radec_deg": list(self.expected_radec) if self.expected_radec else None,
            "quality": self.quality,
        }


@dataclass
class TemporalSequence:
    ra: float
    dec: float
    field_deg: float
    frames: list[Frame]               # chronological
    mask_classes: tuple
    field_mask: np.ndarray            # reference grid
    valid_stack: np.ndarray           # (N, ny, nx) per-frame validity on the reference grid
    common_mask: np.ndarray           # field & valid in every frame
    lambda_spread_bw: np.ndarray      # (max-min) of lambda across frames / bandwidth, reference grid
    criteria: list[dict]
    metrics: dict
    notes: list[str]
    reference_index: int = 0
    astrometry: Astrometry | None = None   # catalogue astrometry of the target, if known
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def target_position(self, i: int) -> tuple[float, float]:
        """Calculated target position at the date of frame i (field centre if unknown)."""
        return self.frames[i].expected_radec or (self.ra, self.dec)

    @property
    def target_moves(self) -> bool:
        return self.astrometry is not None and self.astrometry.has_proper_motion

    # -- convenience ------------------------------------------------------
    @property
    def n(self) -> int:
        return len(self.frames)

    @property
    def wcs(self):
        """Celestial WCS of the reference grid (shared by every frame_data array)."""
        return self.frames[self.reference_index].image.wcs

    @property
    def shape(self):
        return self.field_mask.shape

    @property
    def admissible(self) -> bool:
        return all(c["status"] != "fail" for c in self.criteria)

    @property
    def warnings(self) -> list[dict]:
        return [c for c in self.criteria if c["status"] == "warn"]

    def frame_data(self, i: int, subtract_zodi: bool = True) -> np.ndarray:
        """Surface brightness of frame i on the reference grid (new array, MJy/sr).

        IMAGE - ZODI by default. NaN wherever the frame has no valid pixel
        (FLAGS, non-finite values, outside its cutout).
        """
        img = self.frames[i].image
        values = img.image - img.zodi if subtract_zodi else img.image
        return self.frames[i].on_reference(values, img.valid(self.mask_classes))

    def frame_status(self, i: int) -> np.ndarray:
        """0 = valid and in the common region, 1 = valid only in this frame, 2 = no valid data."""
        st = np.full(self.shape, 2, np.int8)
        st[self.valid_stack[i]] = 1
        st[self.common_mask] = 0
        return st

    # -- exact geometry (native pixels, no resampling) --------------------
    def _to_reference(self, i: int, x: np.ndarray, y: np.ndarray):
        if i == self.reference_index:
            return x, y
        ra, dec = self.frames[i].image.wcs.all_pix2world(x, y, 0)
        return self.wcs.all_world2pix(ra, dec, 0)

    def native_corners(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """Corners of frame i's NATIVE pixels in reference-grid pixel coordinates.

        Returns (X, Y), each of shape (ny + 1, nx + 1): native pixel (r, c) is
        the quadrilateral X[r:r+2, c:c+2], Y[r:r+2, c:c+2], computed through
        both celestial WCS (TAN-SIP). Only positions are transformed; pixel
        values are never resampled.
        """
        key = ("corners", i)
        if key not in self._cache:
            ny, nx = self.frames[i].image.shape
            yc, xc = np.mgrid[-0.5:ny:1.0, -0.5:nx:1.0]
            self._cache[key] = self._to_reference(i, xc, yc)
        return self._cache[key]

    def native_centres(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        """Centres (x, y) of frame i's native pixels in reference-grid pixel coordinates."""
        key = ("centres", i)
        if key not in self._cache:
            ny, nx = self.frames[i].image.shape
            yy, xx = np.mgrid[0:ny, 0:nx].astype(float)
            self._cache[key] = self._to_reference(i, xx, yy)
        return self._cache[key]

    def native_data(self, i: int, subtract_zodi: bool = True, ignore_names=()) -> np.ndarray:
        """Surface brightness of frame i on its OWN pixel grid (new array, MJy/sr).

        NaN where the pixel is invalid under the sequence mask. Flags in
        ``ignore_names`` (e.g. ``quality.CAUTION``) are not masked: use only for
        the exploratory display, together with ``native_caution``.
        """
        img = self.frames[i].image
        values = img.image - img.zodi if subtract_zodi else img.image
        return np.where(img.valid(self.mask_classes, ignore_names), values, np.nan)

    def native_caution(self, i: int) -> np.ndarray:
        """Native pixels of frame i masked only by a caution flag (HALO)."""
        return self.frames[i].image.caution(self.mask_classes)

    def native_common(self, i: int) -> np.ndarray:
        """Native pixels of frame i whose centre falls on a reference pixel of the common region."""
        x, y = self.native_centres(i)
        ix, iy = np.rint(x).astype(int), np.rint(y).astype(int)
        ny, nx = self.shape
        inside = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
        out = np.zeros(x.shape, bool)
        out[inside] = self.common_mask[iy[inside], ix[inside]]
        return out

    def placement_error_px(self, i: int) -> np.ndarray:
        """Distance (reference px) between each reference pixel centre and the
        centre of the frame-i pixel that nearest-neighbour placement copies there."""
        ref = self.frames[self.reference_index].image
        ny, nx = ref.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        ra, dec = ref.wcs.all_pix2world(xx, yy, 0)
        bx, by = self.frames[i].image.wcs.all_world2pix(ra, dec, 0)
        return np.hypot(bx - np.rint(bx), by - np.rint(by))

    def summary(self) -> dict:
        target = {"ra_deg": self.ra, "dec_deg": self.dec, "field_deg": self.field_deg}
        if self.astrometry is not None:
            target["astrometry"] = self.astrometry.to_dict()
        return {
            "target": target,
            "n_frames": self.n, "reference_index": self.reference_index,
            "mask_classes": list(self.mask_classes),
            "frames": [f.summary() for f in self.frames],
            "criteria": self.criteria, "metrics": self.metrics, "notes": self.notes,
            "admissible": self.admissible,
        }


# --------------------------------------------------------------------------- evaluation
def _status(ok_pass: bool, ok_warn: bool = False) -> str:
    return "pass" if ok_pass else ("warn" if ok_warn else "fail")


def evaluate_sequence(frames: list[Frame], ra: float, dec: float, field_deg: float,
                      mask_classes=STRICT, astrometry: Astrometry | None = None) -> TemporalSequence:
    """Align N frames on the earliest one and evaluate global criteria S1-S9.

    ``ra, dec`` is the field centre. With ``astrometry`` the target position
    is propagated to every frame's date (``frame.expected_radec``) and the
    target wavelength is read there; without it the field centre is used.
    Frames are shallow-copied (the SpectralImage is shared and read-only), so
    one Frame can take part in several candidate sequences safely.
    """
    frames = [replace(f) for f in sorted(frames, key=lambda f: f.mjd)]
    ref = frames[0].image
    ny, nx = ref.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    ra_r, dec_r = ref.wcs.all_pix2world(xx, yy, 0)
    field_mask = separation_deg(ra_r, dec_r, ra, dec) <= field_deg / 2
    n_field = int(field_mask.sum())

    for f in frames:
        iy, ix, inside, _, _ = map_onto(ref, f.image)
        f.index_on_ref, f.inside_ref = (iy, ix), inside
        f.expected_radec = astrometry.position_at(f.mjd) if astrometry is not None else None
        f.lambda_target_um, f.bandwidth_target_um = lambda_at(f.image, *(f.expected_radec or (ra, dec)))

    valid_stack = np.stack([f.valid_on_reference(mask_classes) for f in frames])
    common = field_mask & valid_stack.all(axis=0)
    n_common = int(common.sum())
    coverage = n_common / n_field if n_field else 0.0
    geom = float((field_mask & np.logical_and.reduce([f.inside_ref for f in frames])).sum() / max(n_field, 1))

    lam_stack = np.stack([f.on_reference(f.image.wavelength_um) for f in frames])
    spread = (np.nanmax(lam_stack, axis=0) - np.nanmin(lam_stack, axis=0)) / ref.bandwidth_um
    spread = np.where(field_mask, spread, np.nan)
    sp_common = spread[common]
    lam_t = np.array([f.lambda_target_um for f in frames])
    bw_t = float(np.nanmedian([f.bandwidth_target_um for f in frames]))
    spread_target = float((np.nanmax(lam_t) - np.nanmin(lam_t)) / bw_t)

    mjd = np.array([f.mjd for f in frames])
    gaps = np.diff(mjd)
    sat_frac, zodi_med = [], []
    for f in frames:
        iy, ix = f.index_on_ref
        region = field_mask & f.inside_ref
        bits = f.image.flag_defs.names_bitmask(SATURATION)
        sat_frac.append(float(np.count_nonzero((f.image.flags[iy, ix] & bits)[region]) / max(region.sum(), 1)))
        zodi_med.append(float(np.nanmedian(f.on_reference(f.image.zodi)[field_mask])))
        halo_only = f.image.caution(mask_classes)[iy, ix] & region
        f.quality = {
            "L2DQAFLG": str(f.image.meta.get("L2DQAFLG")).strip(),
            "FINAST": f.image.meta.get("FINAST"),
            "valid_fraction_in_field": float(valid_stack[frames.index(f)][field_mask].mean()) if n_field else 0.0,
            "saturation_fraction_in_field": sat_frac[-1],
            "halo_only_fraction_in_field": float(halo_only.sum() / max(region.sum(), 1)),
            "zodi_median_mjysr": zodi_med[-1],
            "psf_fwhm_arcsec": f.image.meta.get("PSF_FWHM"),
        }

    dets = {f.detector for f in frames}
    colls = {f.collection for f in frames}
    vers = {f.image.meta.get("VERSION") for f in frames}
    dqa = [f.quality["L2DQAFLG"] for f in frames]
    fin = [f.image.meta.get("FINAST") for f in frames]
    max_sp = float(np.max(sp_common)) if sp_common.size else float("nan")

    criteria = [
        {"id": "S1", "criterion": "Mismo detector en todas las épocas",
         "value": ", ".join(f"D{d}" for d in sorted(dets)), "threshold": "uno solo",
         "status": _status(len(dets) == 1)},
        {"id": "S2", "criterion": "Fechas distintas (separación mínima entre épocas consecutivas)",
         "value": f"mín {gaps.min():.2f} d · total {mjd[-1] - mjd[0]:.1f} d" if len(gaps) else "una sola época",
         "threshold": f"≥ {config.MIN_TIME_SEPARATION_DAYS} d",
         "status": _status(len(gaps) > 0 and gaps.min() >= config.MIN_TIME_SEPARATION_DAYS)},
        {"id": "S3", "criterion": "Mismo canal efectivo en el objetivo (dispersión de λ entre todas las épocas)",
         "value": f"{(np.nanmax(lam_t) - np.nanmin(lam_t)) * 1000:.1f} nm = {spread_target:.2f} × ancho de banda",
         "threshold": f"≤ {config.SPECTRAL_PASS_BW} (aviso ≤ {config.SPECTRAL_WARN_BW}; rechazo por encima)",
         "status": spectral_status(spread_target)},
        {"id": "S4", "criterion": "Dispersión espectral máxima en la región común",
         "value": (f"máx {max_sp:.2f} × ancho de banda; "
                   f"{np.mean(sp_common <= config.SPECTRAL_PASS_BW) if sp_common.size else 0:.0%} "
                   f"de la región ≤ {config.SPECTRAL_PASS_BW}") if sp_common.size else "sin región común",
         "threshold": (f"≤ {config.SPECTRAL_PASS_BW} en toda la región (aviso ≤ {config.SPECTRAL_WARN_BW}; "
                       "rechazo por encima)"),
         "status": spectral_status(max_sp)},
        {"id": "S5", "criterion": "Cobertura válida común a TODAS las épocas",
         "value": f"{coverage:.1%} ({n_common} px; solapamiento geométrico {geom:.1%})",
         "threshold": f"≥ {config.COVERAGE_PASS:.0%} (aviso ≥ {config.COVERAGE_WARN:.0%})",
         "status": _status(coverage >= config.COVERAGE_PASS and n_common >= config.MIN_COMMON_VALID_PIXELS,
                           coverage >= config.COVERAGE_WARN and n_common >= config.MIN_COMMON_VALID_PIXELS)},
        {"id": "S6", "criterion": "Control de calidad oficial L2 en todas",
         "value": " / ".join(dqa), "threshold": "todas Pass",
         "status": _status(all(d == "Pass" for d in dqa)), "basis": BASIS_ARCHIVE},
        {"id": "S7", "criterion": "Astrometría fina válida en todas (FINAST)",
         "value": " / ".join(str(v) for v in fin),
         "threshold": "todas 0 (1 = solución parcial: aviso; ≥ 2 = no utilizable: rechazo)",
         "status": finast_status(fin), "basis": BASIS_ARCHIVE},
        {"id": "S8", "criterion": "Mismo procesamiento (colección y versión de software)",
         "value": f"{', '.join(sorted(colls))} · v{', '.join(sorted(str(v) for v in vers))}",
         "threshold": "una colección y una versión",
         "status": _status(len(colls) == 1 and len(vers) == 1, True)},
        {"id": "S9", "criterion": "Saturación en el campo (OVERFLOW/NONLINEAR), peor época",
         "value": f"{max(sat_frac):.2%}", "threshold": f"≤ {config.SATURATION_WARN_FRACTION:.1%}",
         "status": _status(max(sat_frac) <= config.SATURATION_WARN_FRACTION, True)},
    ]
    for c in criteria:
        c.setdefault("basis", BASIS_EFFECTIVE)

    # Pairwise lambda mismatch at the target (all pairs, not only consecutive).
    pair_dl = [[abs(a - b) / bw_t for b in lam_t] for a in lam_t]
    # Common coverage lost by each frame: coverage without it minus coverage with all.
    loss = []
    for i in range(len(frames)):
        others = np.delete(valid_stack, i, axis=0)
        cov_wo = float((field_mask & others.all(axis=0)).sum() / max(n_field, 1)) if len(frames) > 1 else coverage
        loss.append(cov_wo - coverage)

    metrics = {
        "n_frames": len(frames),
        "mjd": mjd.tolist(),
        "intervals_days": gaps.tolist(),
        "span_days": float(mjd[-1] - mjd[0]),
        "n_field_px": n_field,
        "n_common_px": n_common,
        "coverage_common_valid": coverage,
        "geometric_overlap": geom,
        "lambda_target_um": lam_t.tolist(),
        "bandwidth_target_um": [f.bandwidth_target_um for f in frames],
        "lambda_spread_target_bw": spread_target,
        "lambda_spread_common_max_bw": max_sp,
        "lambda_pairwise_target_bw": pair_dl,
        "coverage_gain_if_frame_removed": loss,
        "saturation_fraction": sat_frac,
        "zodi_median_mjysr": zodi_med,
        "mask_classes": list(mask_classes),
    }
    notes = []
    if astrometry is not None and astrometry.has_proper_motion:
        pos = [f.expected_radec for f in frames]
        off = [float(separation_deg(p[0], p[1], ra, dec)) * 3600 for p in pos]
        moved = float(separation_deg(pos[0][0], pos[0][1], pos[-1][0], pos[-1][1])) * 3600
        metrics["target_expected_radec_deg"] = [list(p) for p in pos]
        metrics["target_offset_from_centre_arcsec"] = off
        metrics["target_motion_in_sequence_arcsec"] = moved
        notes.append(f"Objetivo con movimiento propio ({astrometry.total_pm_arcsec_yr:.2f}″/año): posición calculada "
                     f"para cada fecha desde {astrometry.name} (época {astrometry.epoch_jyear:.1f}); se desplaza "
                     f"{moved:.1f}″ durante la secuencia y queda a {min(off):.0f}–{max(off):.0f}″ del centro del campo. "
                     "Es un cálculo, no una detección.")
        if max(off) > field_deg * 3600 / 2:
            notes.append("La posición calculada del objetivo queda FUERA del campo de comparación en alguna época.")
    if astrometry is not None:
        notes += astrometry.warnings() if astrometry.has_proper_motion else []
    if max(zodi_med) - min(zodi_med) > 0.05 * max(abs(z) for z in zodi_med):
        notes.append(f"El fondo zodiacal modelado varía entre épocas ({min(zodi_med):.3f}–{max(zodi_med):.3f} MJy/sr): "
                     "la secuencia muestra IMAGE − ZODI por defecto.")
    if any(f.detector in (1, 2) for f in frames):
        notes.append("Detectores 1–2: posible contaminación por airglow de He I (HE_AIRGLOW_CONT).")
    return TemporalSequence(ra=ra, dec=dec, field_deg=field_deg, frames=frames, mask_classes=tuple(mask_classes),
                            field_mask=field_mask, valid_stack=valid_stack, common_mask=common,
                            lambda_spread_bw=spread, criteria=criteria, metrics=metrics, notes=notes,
                            astrometry=astrometry)


# --------------------------------------------------------------------------- metadata-stage proposals
def _compatible(a, b) -> bool:
    bw = 0.5 * (a.bw_um + b.bw_um)
    if abs(a.lam_um - b.lam_um) / bw > config.SPECTRAL_PASS_BW:
        return False
    return float(np.max(np.abs(a.lam_pts - b.lam_pts)) / bw) <= config.SPECTRAL_WARN_BW


def _distinct_dates(c, members) -> bool:
    return all(abs(c.rec.mjd_mid - m.rec.mjd_mid) >= config.MIN_TIME_SEPARATION_DAYS for m in members)


def propose_sequences(cands, max_frames: int = config.MAX_SEQUENCE_FRAMES) -> list[dict]:
    """Greedy spectrally-compatible sets of distinct epochs, one per (seed, collection rule).

    Every member is compatible with every other member (target and whole
    field estimates), so compatibility is global, not only consecutive.
    """
    proposals, seen = [], set()
    by_det = {}
    for c in cands:
        by_det.setdefault(c.rec.detector, []).append(c)
    for det, group in by_det.items():
        for seed in group:
            for same_coll in (True, False):
                pool = [c for c in group if c is not seed and (not same_coll or c.rec.collection == seed.rec.collection)]
                pool.sort(key=lambda c: (float(np.max(np.abs(c.lam_pts - seed.lam_pts))), -c.margin_px))
                members = [seed]
                for c in pool:
                    if len(members) >= max_frames:
                        break
                    if _distinct_dates(c, members) and all(_compatible(c, m) for m in members):
                        members.append(c)
                if len(members) < 2:
                    continue
                key = frozenset(m.rec.file_name for m in members)
                if key in seen:
                    continue
                seen.add(key)
                lam = np.array([m.lam_pts for m in members])
                bw = float(np.median([m.bw_um for m in members]))
                spread = float(np.max(lam.max(axis=0) - lam.min(axis=0)) / bw)
                mjd = sorted(m.rec.mjd_mid for m in members)
                proposals.append({
                    "detector": det, "members": sorted(members, key=lambda m: m.rec.mjd_mid),
                    "n": len(members), "spread_field_bw_est": spread,
                    "same_collection": len({m.rec.collection for m in members}) == 1,
                    "span_days": mjd[-1] - mjd[0], "min_margin_px": min(m.margin_px for m in members),
                })
    proposals.sort(key=lambda p: (-p["n"], p["spread_field_bw_est"] > config.SPECTRAL_PASS_BW,
                                  not p["same_collection"], -min(p["min_margin_px"], 60), -p["span_days"]))
    return proposals


def _frame_from(cand, ra, dec, field_deg, path: Path) -> Frame:
    rec = cand.rec.to_dict()
    rec["lambda_est_um"] = cand.lam_um
    return Frame(image=fitsdata.load(path), record=rec,
                 cutout_url=archive.cutout_url(cand.rec.access_url, ra, dec, field_deg),
                 path=path, sha256=archive.sha256(path))


def pruning_path(frames: list[Frame], ra, dec, field_deg, mask_classes=STRICT,
                 astrometry: Astrometry | None = None) -> list[TemporalSequence]:
    """Evaluate the full set, then greedily drop the frame that costs most common
    coverage, down to two frames. Every state is a candidate option."""
    states = [evaluate_sequence(frames, ra, dec, field_deg, mask_classes, astrometry)]
    current = list(states[0].frames)
    while len(current) > 2:
        best = None
        for i in range(len(current)):
            trial = evaluate_sequence(current[:i] + current[i + 1:], ra, dec, field_deg, mask_classes, astrometry)
            if best is None or trial.metrics["coverage_common_valid"] > best.metrics["coverage_common_valid"]:
                best = trial
        states.append(best)
        current = list(best.frames)
    return states


def criterion(seq: TemporalSequence, cid: str) -> dict:
    return next(c for c in seq.criteria if c["id"] == cid)


def choose(options: list[TemporalSequence]) -> TemporalSequence | None:
    """Selection rule (documented in config):

    1. only admissible options (no failed criterion) with S5 = pass;
    2. best = highest common valid coverage among them;
    3. keep options whose coverage >= best - tolerance;
    4. among those: fewest warnings first (quality before quantity), then the
       largest number of epochs, then higher coverage, then longer time span.
    """
    ok = [o for o in options if o.admissible and criterion(o, "S5")["status"] == "pass"]
    if not ok:
        return None
    best_cov = max(o.metrics["coverage_common_valid"] for o in ok)
    eligible = [o for o in ok if o.metrics["coverage_common_valid"] >= best_cov - config.SEQUENCE_COVERAGE_TOLERANCE]
    eligible.sort(key=lambda o: (len(o.warnings), -o.n, -o.metrics["coverage_common_valid"], -o.metrics["span_days"]))
    return eligible[0]


def _option_row(o: TemporalSequence, origin: str) -> dict:
    return {
        "origin": origin, "n_frames": o.n, "obs_ids": [f.obs_id for f in o.frames],
        "dates": [f.date_utc[:16] for f in o.frames], "detector": o.frames[0].detector,
        "coverage_common_valid": o.metrics["coverage_common_valid"],
        "lambda_spread_common_max_bw": o.metrics["lambda_spread_common_max_bw"],
        "span_days": o.metrics["span_days"], "admissible": o.admissible,
        "status": {c["id"]: c["status"] for c in o.criteria},
    }


#: Search stages reported to ``progress(stage, fraction, message)`` by find_sequence.
STAGES = ("catalog", "wavelengths", "download", "evaluate", "done")


def find_sequence(ra: float, dec: float, field_deg: float = config.DEFAULT_FIELD_DEG,
                  collections=config.WIDE_COLLECTIONS, detectors=None,
                  max_frames: int = config.MAX_SEQUENCE_FRAMES,
                  max_candidates: int = config.MAX_SEQUENCE_CANDIDATES,
                  mask_classes=STRICT, log=print, progress=None, astrometry: Astrometry | None = None):
    """Search IRSA and return (best TemporalSequence | None, JSON-able report).

    ``progress(stage, fraction, message)``, if given, is called at every stage
    (``STAGES``) and after each FITS cutout, with ``fraction`` in [0, 1].

    With ``astrometry`` of a moving target, ``ra, dec`` are ignored: the
    field is centred on the position calculated for the median date of the
    archive observations (rounded to 0.1 yr so that repeated searches reuse
    the same cutouts) and every frame gets its own calculated position.
    Invalid coordinates or field sizes raise ValueError before any query.
    """
    from .targets import validate_coordinates, validate_fov_deg

    def step(stage, frac, msg):
        if progress:
            progress(stage, min(1.0, max(0.0, frac)), msg)

    moving = astrometry is not None and astrometry.has_proper_motion
    if astrometry is not None:
        validate_coordinates(astrometry.ra_deg, astrometry.dec_deg)
        ra, dec = astrometry.position_at(round(Time.now().jyear, 1))   # provisional query position
    ra, dec = validate_coordinates(ra, dec)
    field_deg = validate_fov_deg(field_deg)

    t0 = time.time()
    step("catalog", 0.02, "Consultando el catálogo SPHEREx de IRSA (SIA2)…")
    records = archive.query_images(ra, dec, collections=collections)
    if detectors:
        records = [r for r in records if r.detector in set(detectors)]
    centre = {"rule": "coordenadas introducidas (sin astrometría: se usan para todas las fechas)"}
    if astrometry is not None:
        centre = {"rule": "posición de catálogo (sin movimiento propio)"}
    if moving and records:
        t_c = round(float(Time(float(np.median([r.mjd_mid for r in records])), format="mjd").jyear), 1)
        ra1, dec1 = astrometry.position_at(t_c)
        log(f"Movimiento propio: centro en la posición calculada para {t_c:.1f} "
            f"({float(separation_deg(ra, dec, ra1, dec1)) * 3600:.1f}″ de la consulta provisional; "
            f"{astrometry.offset_arcsec(t_c, astrometry.ra_deg, astrometry.dec_deg):.0f}″ de la posición de catálogo)")
        ra, dec = ra1, dec1
        centre = {"rule": "posición calculada (movimiento propio + paralaje) en la época mediana de las "
                          "observaciones del archivo, redondeada a 0.1 años", "epoch_jyear": t_c}
    log(f"SIA2: {len(records)} imágenes contienen el objetivo ({', '.join(collections)})")
    cands = build_candidates(records, ra, dec, field_deg)
    log(f"Con el campo completo dentro del detector: {len(cands)}")
    step("wavelengths", 0.10, f"{len(records)} imágenes contienen el objetivo; {len(cands)} cubren el campo "
                              "completo. Estimando λ desde metadatos…")
    estimate_wavelengths(cands)
    proposals = propose_sequences(cands, max_frames)
    log(f"Conjuntos espectralmente compatibles propuestos: {len(proposals)} "
        f"(máx. {max(p['n'] for p in proposals) if proposals else 0} épocas)")

    chosen_props = proposals[:max_candidates]
    urls = [archive.cutout_url(m.rec.access_url, ra, dec, field_deg) for p in chosen_props for m in p["members"]]
    t1 = time.time()

    def on_file(done, total, downloaded):
        step("download", 0.20 + 0.65 * done / max(total, 1),
             f"Recortes FITS: {done} de {total} listos ({downloaded} descargados de IRSA, "
             f"{done - downloaded} ya en caché local)")

    step("download", 0.20, f"{len(proposals)} conjuntos compatibles; obteniendo {len(set(urls))} recortes FITS…")
    got = archive.fetch_many(urls, progress=on_file)
    log(f"Recortes FITS: {len(set(urls))} en {time.time() - t1:.0f} s")
    step("evaluate", 0.86, "Alineando épocas y evaluando los criterios S1–S9…")

    failures = []
    for u in sorted(set(urls)):
        res = got.get(u)
        if isinstance(res, Exception) or res is None:
            failures.append({"file": u.split("?")[0].rsplit("/", 1)[-1], "cutout_url": u,
                             "kind": "transitorio" if isinstance(res, archive.ArchiveTransientError) else "permanente",
                             "error": str(res)[:200]})
    if failures:
        log(f"AVISO: {len(failures)} de {len(set(urls))} recortes no se pudieron obtener; "
            "la selección se hace sin ellos")
    options, origins = [], []
    for k, p in enumerate(chosen_props):
        frames = []
        for m in p["members"]:
            res = got.get(archive.cutout_url(m.rec.access_url, ra, dec, field_deg))
            if isinstance(res, Exception) or res is None:
                continue
            frames.append(_frame_from(m, ra, dec, field_deg, res))
        if len(frames) < 2:
            continue
        for s in pruning_path(frames, ra, dec, field_deg, mask_classes, astrometry):
            options.append(s)
            origins.append(f"propuesta {k + 1} ({p['n']} épocas)")
            log(f"  D{s.frames[0].detector} {s.n} épocas · cobertura común {s.metrics['coverage_common_valid']:.1%} · "
                f"dispersión λ {s.metrics['lambda_spread_common_max_bw']:.2f} BW · admisible={s.admissible}")

    best = choose(options)
    rejected_frames = []
    if best is not None:
        chosen_ids = {f.obs_id + f.record["file_name"] for f in best.frames}
        best_cov = max((o.metrics["coverage_common_valid"] for o in options
                        if o.admissible and criterion(o, "S5")["status"] == "pass"), default=0.0)
        for o in options:
            if o.n > best.n:
                why = []
                if criterion(o, "S5")["status"] != "pass":
                    why.append(f"cobertura común {o.metrics['coverage_common_valid']:.1%} < {config.COVERAGE_PASS:.0%}")
                elif o.metrics["coverage_common_valid"] < best_cov - config.SEQUENCE_COVERAGE_TOLERANCE:
                    why.append("pierde más de "
                               f"{config.SEQUENCE_COVERAGE_TOLERANCE:.0%} de cobertura frente a la mejor opción")
                why += [f"{c['id']} {c['status']}: {c['value']}" for c in o.criteria if c["status"] != "pass"]
                rejected_frames.append({"n_frames": o.n, "detector": o.frames[0].detector,
                                        "coverage": o.metrics["coverage_common_valid"],
                                        "obs_ids": [f.obs_id for f in o.frames],
                                        "reasons": why or ["peor puntuación"]})
    target = {"ra_deg": ra, "dec_deg": dec, "field_deg": field_deg, "centre": centre}
    if astrometry is not None:
        target["astrometry"] = astrometry.to_dict()
        target["astrometry_warnings"] = astrometry.warnings()
    n_req = len(set(urls))
    report = {
        "kind": "sequence",
        "target": target,
        "retrieval": {"n_requested": n_req, "n_failed": len(failures), "complete": not failures,
                      "n_transient": sum(f["kind"] == "transitorio" for f in failures)},
        "collections": list(collections),
        "n_records": len(records), "n_candidates": len(cands), "n_proposals": len(proposals),
        "proposals": [{"n": p["n"], "detector": p["detector"], "spread_field_bw_est": p["spread_field_bw_est"],
                       "same_collection": p["same_collection"], "span_days": p["span_days"],
                       "files": [m.rec.file_name for m in p["members"]]} for p in proposals[:10]],
        "options": [_option_row(o, origins[i]) for i, o in enumerate(options)],
        "rejected_larger_options": rejected_frames,
        "retrieval_failures": failures,
        "selected": best.summary() if best else None,
        "selection_rule": ("admisible y S5 pass; cobertura común ≥ (mejor cobertura − "
                           f"{config.SEQUENCE_COVERAGE_TOLERANCE:.0%}); entre ellas: menos avisos, después más épocas, "
                           "más cobertura y más intervalo"),
        "observations": [
            {"obs_id": c.rec.obs_id, "collection": c.rec.collection, "detector": c.rec.detector,
             "mjd_mid": c.rec.mjd_mid, "exptime_s": c.rec.exptime_s, "file_name": c.rec.file_name,
             "lambda_est_um": c.lam_um, "bandwidth_est_um": c.bw_um, "field_margin_px": c.margin_px}
            for c in cands],
        "elapsed_s": round(time.time() - t0, 1),
        "generated_utc": Time.now().isot[:19],
    }
    log(f"Total: {report['elapsed_s']} s")
    step("done", 1.0, f"Búsqueda completada en {report['elapsed_s']} s")
    return best, report


# --------------------------------------------------------------------------- persistence
def save_report(report: dict, name: str) -> Path:
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=_jsonable), encoding="utf-8")
    return path


def _jsonable(v):
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return str(v)


def report_urls(report: dict) -> list[str]:
    """Cutout URLs of the selected frames of a sequence or pair report."""
    sel = report["selected"]
    if report.get("kind") == "sequence":
        return [f["cutout_url"] for f in sel["frames"]]
    return [sel[k]["cutout_url"] for k in ("a", "b")]


def load_sequence(report: dict | str | Path, mask_classes=STRICT, verify: bool = True,
                  progress=None) -> TemporalSequence:
    """Rebuild a TemporalSequence from a saved sequence report or a pair report.

    FITS are taken from the local reference store or cache, or re-downloaded
    from the stored cutout URL (in parallel). With ``verify`` the SHA-256 must
    match the report. ``progress(done, total, n_downloaded)`` as in ``fetch_many``.
    """
    if not isinstance(report, dict):
        report = json.loads(Path(report).read_text(encoding="utf-8"))
    t = report["target"]
    sel = report["selected"]
    if report.get("kind") == "sequence":
        items = [(f["cutout_url"], f.get("sha256"), f) for f in sel["frames"]]
    else:  # pair report (pairing.find_pair)
        items = [(sel[k]["cutout_url"], sel[k].get("sha256"), sel[k]) for k in ("a", "b")]
    got = archive.fetch_many([u for u, _, _ in items], progress=progress)
    frames = []
    for url, digest, rec in items:
        path = got[url]
        name = url.split("?")[0].rsplit("/", 1)[-1]
        if isinstance(path, Exception):
            cls = type(path) if isinstance(path, archive.ArchiveError) else RuntimeError
            raise cls(f"No se pudo obtener {name}: {path}") from path
        actual = archive.sha256(path)
        if verify and digest and actual != digest and not archive.is_reference(path):
            # A cache copy that differs from the report: set it aside and download it once more.
            path = archive.redownload(url, path)
            actual = archive.sha256(path)
        if verify and digest and actual != digest:
            raise ValueError(f"SHA-256 de {path.name} distinto del informe: el FITS local no es el analizado "
                             f"({'archivo de referencia, no se modifica' if archive.is_reference(path) else 'también tras volver a descargarlo'})")
        frames.append(Frame(image=fitsdata.load(path), record=rec, cutout_url=url, path=path, sha256=actual))
    return evaluate_sequence(frames, t["ra_deg"], t["dec_deg"], t["field_deg"], mask_classes,
                             Astrometry.from_dict(t.get("astrometry")))


__all__ = ["Frame", "TemporalSequence", "evaluate_sequence", "find_sequence", "load_sequence",
           "propose_sequences", "pruning_path", "choose", "save_report", "criterion", "report_urls", "STAGES"]
