"""Preset fields. Coordinates are catalogue positions (ICRS, epoch J2000).

They are NOT propagated for proper motion: for high-proper-motion objects
(Barnard's Star, WISE 0855, eps Ind B) the object is displaced from these
positions at SPHEREx epochs. A propagated position is not a detection.
"""

PRESETS = {
    "M101 (galaxia, campo de control estático)": {
        "ra": 210.802429, "dec": 54.348750, "source": "SIMBAD (M101)", "high_pm": False,
    },
    "WISE 0855−0714 (coordenadas del enunciado NASA)": {
        # 08h55m10.831s -07d14m42.53s as given in the Space Apps challenge text.
        "ra": 133.7951292, "dec": -7.2451472, "source": "NASA Space Apps 2026 challenge", "high_pm": True,
    },
}


def resolve_name(name: str):
    """Resolve an object name with CDS Sesame (network). Returns (ra, dec)."""
    from astropy.coordinates import SkyCoord

    c = SkyCoord.from_name(name)
    return float(c.ra.deg), float(c.dec.deg)
