"""SPHEREx FLAGS decoding and pixel-validity masks.

Flag names are read from each file's own FLAGS header (MSKNnnnn keywords), so
the decoding follows the definitions shipped with the data; documented bits
the header omits (SATELLITE_HALO, bit 29, in DR1/QR3 headers) are added from
the official documentation, and any set bit defined nowhere is masked as an
artifact. Every flag is assigned to one of three classes:

* ``unusable``  - the pixel carries no trustworthy measurement.
* ``artifact``  - the pixel is affected by an instrumental or transient effect
                  that can mimic or hide astrophysical change.
* ``info``      - informational only (never masked).

Unknown flag names are treated as ``artifact`` (conservative) and reported.

HALO (bit 28) stays an ``artifact`` and is masked in every comparability
metric. The SPHEREx Explanatory Supplement (v2.1, Table 16 and section 3.2.1)
sets it on the edge neighbours of TRANSIENT pixels (often the charge spill of a
bright star) and around snowballs, and recommends *caution* -- not exclusion --
in science use; the official all-sky cube and photometry masks reject it.
SkyClues therefore offers an *exploratory display* that shows HALO-only pixels
with a distinct, labelled colour (``CAUTION``), never as ordinary valid sky.
SATELLITE_HALO (bit 29) is "not recommended" and is never shown.
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
    27: "SNOWBALL", 28: "HALO", 29: "SATELLITE_HALO",
}

UNUSABLE = {"OVERFLOW", "SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR"}
INFO = {"FULLSAMPLE", "SOURCE"}
# Everything else that is defined is an artifact class (masked by default):
# TRANSIENT, DICHROIC, PHANMISS, PERSIST, OUTLIER, CROSSTALK, GHOST*, STREAK,
# BLOOM, SNOWBALL, HALO, SATELLITE_HALO.
SATURATION = {"OVERFLOW", "NONLINEAR"}
# Artifact flags whose official recommendation is "caution" (exploratory display only).
CAUTION = {"HALO"}

# Official SPHEREx rejection lists (Explanatory Supplement v2.1), for reference.
OFFICIAL_CUBE_REJECT = {"TRANSIENT", "SUR_ERROR", "NONFUNC", "DICHROIC", "MISSING_DATA", "HOT", "COLD",
                        "PHANMISS", "NONLINEAR", "PERSIST", "CROSSTALK", "STREAK", "BLOOM", "SNOWBALL",
                        "HALO", "SATELLITE_HALO"}
OFFICIAL_PHOTOMETRY_REJECT = {"SUR_ERROR", "NONFUNC", "MISSING_DATA", "HOT", "COLD", "NONLINEAR", "PERSIST",
                              "BLOOM", "SNOWBALL", "HALO", "SATELLITE_HALO"}


#: FLAGS is a 32-bit integer image.
N_FLAG_BITS = 32
UNDEFINED_PREFIX = "UNDEFINED_BIT_"


@dataclass
class FlagDefinitions:
    """Bit -> flag name for one file.

    ``bits`` merges the file's own FLAGS header (MSKN keywords, authoritative
    when present) with the documented bits it does not define: real DR1/QR3
    headers stop at bit 28, so SATELLITE_HALO (bit 29) comes from the
    documentation. A bit defined nowhere is *undefined*; if it is ever set it
    is masked as an artifact (conservative) and listed by ``flag_census``.
    """

    bits: dict[int, str]
    descriptions: dict[int, str] = field(default_factory=dict)
    source: str = "header"
    conflicts: dict[int, tuple[str, str]] = field(default_factory=dict)   # bit -> (header, documented)

    def classify(self, name: str) -> str:
        if name in UNUSABLE:
            return "unusable"
        if name in INFO:
            return "info"
        return "artifact"

    def unknown_names(self) -> list[str]:
        known = set(DOCUMENTED_BITS.values())
        return sorted(n for n in self.bits.values() if n not in known)

    @property
    def undefined_bits_mask(self) -> int:
        return sum(1 << b for b in range(N_FLAG_BITS) if b not in self.bits)

    def bitmask(self, classes: tuple[str, ...]) -> int:
        """Bits masked for ``classes``; undefined bits count as ``artifact``."""
        mask = 0
        for bit, name in self.bits.items():
            if self.classify(name) in classes:
                mask |= 1 << bit
        if "artifact" in classes:
            mask |= self.undefined_bits_mask
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
    if not bits:
        return FlagDefinitions(bits=dict(DOCUMENTED_BITS), source="documentación (cabecera sin MSKN)")
    conflicts = {b: (bits[b], DOCUMENTED_BITS[b]) for b in bits
                 if b in DOCUMENTED_BITS and bits[b] != DOCUMENTED_BITS[b]}
    added = {b: n for b, n in DOCUMENTED_BITS.items() if b not in bits}
    for b, n in added.items():
        bits[b] = n
        desc.setdefault(b, "definido en la documentación oficial (ausente en la cabecera)")
    source = "cabecera" + (f" + documentación (bits {', '.join(map(str, sorted(added)))})" if added else "")
    return FlagDefinitions(bits=bits, descriptions=desc, source=source, conflicts=conflicts)


DEFAULT_MASK_CLASSES = ("unusable", "artifact")


def valid_pixel_mask(image, flags, variance, defs: FlagDefinitions,
                     mask_classes: tuple[str, ...] = DEFAULT_MASK_CLASSES,
                     ignore_names: frozenset | set | tuple = ()) -> np.ndarray:
    """True where the pixel holds a usable measurement.

    A pixel is invalid if IMAGE is non-finite, VARIANCE is non-finite or <= 0,
    or any flag bit in ``mask_classes`` is set. Flags named in ``ignore_names``
    are not masked (used only to *identify* caution pixels for display).
    """
    bad_bits = defs.bitmask(mask_classes) & ~defs.names_bitmask(set(ignore_names))
    ok = np.isfinite(image)
    if variance is not None:
        ok &= np.isfinite(variance) & (variance > 0)
    ok &= (flags.astype(np.int64) & bad_bits) == 0
    return ok


def flag_census(flags, defs: FlagDefinitions, region: np.ndarray | None = None) -> list[dict]:
    """Fraction of pixels carrying each defined flag (optionally inside a region),
    plus a row for every UNDEFINED bit that is actually set (masked as artifact)."""
    f = flags.astype(np.int64) & ((1 << N_FLAG_BITS) - 1)
    if region is not None:
        f = f[region]
    n = f.size
    rows = []
    for bit in range(N_FLAG_BITS):
        count = int(np.count_nonzero(f & (1 << bit)))
        if bit in defs.bits:
            name = defs.bits[bit]
            cls, desc = defs.classify(name), defs.descriptions.get(bit, "")
        elif count:
            name, cls = f"{UNDEFINED_PREFIX}{bit}", "artifact"
            desc = "bit activo sin definición en la cabecera ni en la documentación: enmascarado por prudencia"
        else:
            continue
        rows.append({"bit": bit, "name": name, "class": cls, "pixels": count,
                     "fraction": count / n if n else 0.0, "description": desc})
    return rows
