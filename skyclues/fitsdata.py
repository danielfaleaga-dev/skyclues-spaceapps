"""Reading SPHEREx Level-2 spectral-image MEFs (full images or IBE cutouts).

The file on disk is opened read-only; arrays are copied into memory so that
no operation can write back to the original FITS.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning

from .quality import FlagDefinitions, read_flag_definitions, valid_pixel_mask


@dataclass
class SpectralImage:
    path: Path
    image: np.ndarray        # MJy/sr, zodiacal light NOT subtracted (as delivered)
    flags: np.ndarray
    variance: np.ndarray     # (MJy/sr)^2
    zodi: np.ndarray         # MJy/sr, model of zodiacal light
    wcs: WCS                 # celestial WCS (TAN-SIP)
    wavelength_um: np.ndarray   # per-pixel central wavelength (WCS-WAVE, visualization accuracy)
    bandwidth_um: np.ndarray    # per-pixel bandwidth
    flag_defs: FlagDefinitions
    meta: dict
    wave_table: dict          # raw WCS-WAVE control grid (X, Y, VALUES)

    @property
    def shape(self):
        return self.image.shape

    def valid(self, mask_classes=("unusable", "artifact")) -> np.ndarray:
        return valid_pixel_mask(self.image, self.flags, self.variance, self.flag_defs, mask_classes)

    def detector_offset(self) -> tuple[float, float]:
        """Offset to convert cutout 0-based pixels to full-detector 1-based pixels."""
        return 1.0 - self.meta["CRPIX1A"] + 1.0, 1.0 - self.meta["CRPIX2A"] + 1.0


_META_KEYS = [
    "DETECTOR", "OBSID", "EXPIDN", "DATE-OBS", "MJD-OBS", "DATE-AVG", "MJD-AVG",
    "DATE-END", "MJD-END", "XPOSURE", "BUNIT", "L1DQAFLG", "L2DQAFLG", "PSF_FWHM",
    "FINAST", "ASTRONETSOLVED", "SPS_FLAGS", "NON_SURVEY", "HE_AIRGLOW_CONT",
    "AURORA_CONT", "SHUTTLE_GLOW_CONT", "CRPIX1A", "CRPIX2A", "PXSRCMSK",
    "OMEGA_MEDIAN", "DETCOORD",
]


def _spectral_wcs(header, hdul) -> WCS:
    logger = logging.getLogger("astropy")
    previous = logger.level
    logger.setLevel(logging.ERROR)  # silence the expected SIP notice for key 'W'
    try:
        sw = WCS(header, fobj=hdul, key="W")
    finally:
        logger.setLevel(previous)
    sw.sip = None
    return sw


def load(path: str | Path) -> SpectralImage:
    path = Path(path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FITSFixedWarning)
        with fits.open(path, mode="readonly", memmap=False) as hdul:
            names = [h.name for h in hdul]
            for required in ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "WCS-WAVE"):
                if required not in names:
                    raise ValueError(f"{path.name}: missing extension {required}")
            hi = hdul["IMAGE"].header
            image = np.array(hdul["IMAGE"].data, dtype=np.float64)
            flags = np.array(hdul["FLAGS"].data, dtype=np.int64)
            variance = np.array(hdul["VARIANCE"].data, dtype=np.float64)
            zodi = np.array(hdul["ZODI"].data, dtype=np.float64)
            wcs = WCS(hi)
            sw = _spectral_wcs(hi, hdul)
            ny, nx = image.shape
            yy, xx = np.mgrid[0:ny, 0:nx]
            lam, bw = sw.all_pix2world(xx, yy, 0)
            ww = hdul["WCS-WAVE"].data[0]
            wave_table = {
                "X": np.array(ww["X"], float),
                "Y": np.array(ww["Y"], float),
                "VALUES": np.array(ww["VALUES"], float),
                "calibration": " ".join(
                    str(v) for v in hdul["WCS-WAVE"].header.get("HISTORY", [])
                    if "Calibration source" in str(v)
                ),
            }
            flag_defs = read_flag_definitions(hdul["FLAGS"].header)
            meta = {k: hi.get(k) for k in _META_KEYS}
            meta["VERSION"] = hdul[0].header.get("VERSION")
            meta["FILE"] = path.name
            meta["CALIB_HISTORY"] = [str(v) for v in hi.get("HISTORY", []) if "[CALIB]" in str(v)]
    return SpectralImage(
        path=path, image=image, flags=flags, variance=variance, zodi=zodi, wcs=wcs,
        wavelength_um=np.asarray(lam, float), bandwidth_um=np.asarray(bw, float),
        flag_defs=flag_defs, meta=meta, wave_table=wave_table,
    )
