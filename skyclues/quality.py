"""SPHEREx FLAGS decoding and pixel-validity masks.

Flag names are read from each file's own FLAGS header (MSKNnnnn keywords), so
the decoding follows the definitions shipped with the data. Every flag is
assigned to one of three classes:

* ``unusable``  - the pixel carries no trustworthy measurement.
* ``artifact``  - the pixel is affected by an instrumental or transient effect
                  that can mimic or hide astrophysical change.
* ``info``      - informational only (never masked).

Unknown flag names are treated as ``artifact`` (conservative) and reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# Documented SPHEREx Level-2 flag bits (IRSA, DR1/QR3), used only as fallback
# when a header does not carry MSKN keywords.
DOCUMENTED_BITS = {
    0: "TRANSIENT", 1: "OVERFLOW", 2: "SUR_ERROR", 6: "NONFUNC", 7: "DICHROIC",
    9: "MISSING_DATA", 10: "HOT", 11: "COLD", 12: "FULLSAMPLE", 14: "PHANMISS",
    15: "NONLINEAR", 17: "PERSIST", 19: "OUTLIER", 20: "CROSSTALK", 21: "SOURCE",
    22: "GHOST", 23: "GHOST_FPA", 24: "GHOST_EXT", 25: "STREAK", 26: "BLOOM",
    27: "SNOWBALL", 28: "HALO",
}

UNUSABLE = {"OVERFLOW", "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR"}
INFO = {"FULLSAMPLE", "SOURCE"}
# Everything else that is defined is an artifact class (masked by default):
# TRANSIENT, DICHROIC, PHANMISS, PERSIST, OUTLIER, CROSSTALK, GHOST*, STREAK,
# BLOOM, SNOWBALL, HALO.
SATURATION = {"OVERFLOW", "NONLINEAR"}


@dataclass
class FlagDefinitions:
    bits: dict[int, str]
    descriptions: dict[int, str] = field(default_factory=dict)
    source: str = "header"

    def classify(self, name: str) -> str:
        if name in UNUSABLE:
            return "unusable"
        if name in INFO:
            return "info"
        return "artifact"

    def unknown_names(self) -> list[str]:
        known = set(DOCUMENTED_BITS.values())
        return sorted(n for n in self.bits.values() if n not in known)

    def bitmask(self, classes: tuple[str, ...]) -> int:
        mask = 0
        for bit, name in self.bits.items():
            if self.classify(name) in classes:
                mask |= 1 << bit
        return mask

    def names_bitmask(self, names: set[str]) -> int:
        return sum(1 << b for b, n in self.bits.items() if n in names)


def read_flag_definitions(flags_header) -> FlagDefinitions:
    bits: dict[int, str] = {}
    desc: dict[int, str] = {}
    for key in flags_header:
        if key.startswith("MSKN") and key[4:].isdigit():
            bit = int(key[4:])
            bits[bit] = str(flags_header[key]).strip()
            dkey = f"MSKD{key[4:]}"
            if dkey in flags_header:
                desc[bit] = str(flags_header[dkey]).strip()
    if bits:
        return FlagDefinitions(bits=bits, descriptions=desc, source="header")
    return FlagDefinitions(bits=dict(DOCUMENTED_BITS), source="documented-fallback")


DEFAULT_MASK_CLASSES = ("unusable", "artifact")


def valid_pixel_mask(image, flags, variance, defs: FlagDefinitions,
                     mask_classes: tuple[str, ...] = DEFAULT_MASK_CLASSES) -> np.ndarray:
    """True where the pixel holds a usable measurement.

    A pixel is invalid if IMAGE is non-finite, VARIANCE is non-finite or <= 0,
    or any flag bit in ``mask_classes`` is set.
    """
    bad_bits = defs.bitmask(mask_classes)
    ok = np.isfinite(image)
    if variance is not None:
        ok &= np.isfinite(variance) & (variance > 0)
    ok &= (flags.astype(np.int64) & bad_bits) == 0
    return ok


def flag_census(flags, defs: FlagDefinitions, region: np.ndarray | None = None) -> list[dict]:
    """Fraction of pixels carrying each defined flag (optionally inside a region)."""
    f = flags.astype(np.int64)
    if region is not None:
        f = f[region]
    n = f.size
    rows = []
    for bit in sorted(defs.bits):
        name = defs.bits[bit]
        count = int(np.count_nonzero(f & (1 << bit)))
        rows.append({
            "bit": bit,
            "name": name,
            "class": defs.classify(name),
            "pixels": count,
            "fraction": count / n if n else 0.0,
            "description": defs.descriptions.get(bit, ""),
        })
    return rows
