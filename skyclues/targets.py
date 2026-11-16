"""Preset fields, name resolution and input validation.

Every target carries its catalogue astrometry (``astrometry.Astrometry``):
position at the catalogue epoch plus proper motion, parallax and radial
velocity when known. Searches and markers use the position *propagated to
each observation date*, never the catalogue position at every date. A
propagated position is a calculation, not a SPHEREx detection.
"""

from __future__ import annotations

import math

from .astrometry import Astrometry, query_simbad

#: SIMBAD basic data (ICRS, epoch J2000.0), queried 2026-11-14.
WISE0855 = Astrometry(
    name="WISEA J085510.74-071442.5", ra_deg=133.81890825, dec_deg=-7.247048, epoch_jyear=2000.0,
    pmra_masyr=-8123.7, pmdec_masyr=673.2, parallax_mas=439.0, rv_kms=None,
    source="SIMBAD 2026-11-14; astrometry 2021ApJS..253....7K (Kirkpatrick et al. 2021)")
M101 = Astrometry(
    name="M 101", ra_deg=210.80242916666668, dec_deg=54.34875, epoch_jyear=2000.0,
    source="SIMBAD 2026-11-14 (galaxy: no measurable proper motion)")

#: Coordinates printed in the NASA Space Apps 2026 challenge text for WISE 0855
#: (08h55m10.831s -07d14m42.53s). They are not J2000.0 positions: the SIMBAD
#: track passes within 0.34 arcsec of them at epoch 2010.40 (WISE era).
CHALLENGE_WISE0855 = {"ra_deg": 133.7951292, "dec_deg": -7.2451472, "epoch_jyear_estimated": 2010.40}

PRESETS = {
    "M101 (galaxy, static control field)": {
        "ra": M101.ra_deg, "dec": M101.dec_deg, "astrometry": M101, "high_pm": False,
    },
    "WISE 0855−0714 (brown dwarf, 8.2″/yr)": {
        "ra": WISE0855.ra_deg, "dec": WISE0855.dec_deg, "astrometry": WISE0855, "high_pm": True,
    },
}


def resolve_name(name: str) -> tuple[Astrometry, list[str]]:
    """Astrometry for an object name (network) and the warnings that apply.

    SIMBAD (TAP) first: position, proper motion, parallax and radial
    velocity. If SIMBAD is unavailable, CDS Sesame gives only a position:
    the result then has no proper motion and a warning says so.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Type the name of an object.")
    try:
        a = query_simbad(name)
        return a, a.warnings()
    except LookupError:
        raise
    except RuntimeError as err:
        from astropy.coordinates import SkyCoord

        c = SkyCoord.from_name(name)
        a = Astrometry(name=name, ra_deg=float(c.ra.deg), dec_deg=float(c.dec.deg), epoch_jyear=2000.0,
                       source="CDS Sesame (position only; SIMBAD not available)")
        return a, [f"SIMBAD not available ({str(err)[:80]}): no proper motion. "
                   "If the object moves, the position for the SPHEREx dates will be wrong."]


# ----------------------------------------------------------------------------- validation
def validate_coordinates(ra, dec) -> tuple[float, float]:
    """(ra, dec) in degrees as finite floats inside RA [0, 360) and Dec [-90, 90].

    Raises ValueError with a message for the user. Values are never clamped
    or wrapped silently: an out-of-range value is an input error.
    """
    try:
        r, d = float(ra), float(dec)
    except (TypeError, ValueError):
        raise ValueError(f"Non-numeric coordinates: RA={ra!r}, Dec={dec!r}.") from None
    if not (math.isfinite(r) and math.isfinite(d)):
        raise ValueError(f"Non-finite coordinates: RA={r}, Dec={d}.")
    if not 0.0 <= r < 360.0:
        raise ValueError(f"RA out of range: {r}° (must be in [0°, 360°)).")
    if not -90.0 <= d <= 90.0:
        raise ValueError(f"Dec out of range: {d}° (must be in [−90°, +90°]).")
    return r, d


def validate_fov_deg(value) -> float:
    """Field-of-view diameter in degrees inside [FOV_MIN_DEG, FOV_MAX_DEG]; ValueError otherwise."""
    from . import config

    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Non-numeric field of view: {value!r}.") from None
    if not math.isfinite(v) or not config.FOV_MIN_DEG <= v <= config.FOV_MAX_DEG:
        raise ValueError(f"Field of view {v}° outside [{config.FOV_MIN_DEG}°, {config.FOV_MAX_DEG}°] "
                         f"({config.FOV_MIN_DEG * 60:g}′–{config.FOV_MAX_DEG * 60:g}′).")
    return round(v, 4)


def clamp_fov_deg(value, default: float | None = None) -> float:
    """Field-of-view diameter in degrees, limited to [FOV_MIN_DEG, FOV_MAX_DEG].

    For widgets that enforce their own limits. Invalid input (text, NaN,
    None) returns the default field. Query parameters use validate_fov_deg.
    """
    from . import config

    default = config.DEFAULT_FIELD_DEG if default is None else default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(v):
        return default
    return round(min(max(v, config.FOV_MIN_DEG), config.FOV_MAX_DEG), 4)


def fov_pixels(fov_deg: float) -> int:
    """Approximate width of the field in SPHEREx pixels (6.15 arcsec/px)."""
    from . import config

    return int(round(fov_deg * 3600 / config.NOMINAL_PIXEL_SCALE_ARCSEC))
