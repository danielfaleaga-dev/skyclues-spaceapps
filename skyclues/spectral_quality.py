"""Why a spectral channel has no value: coverage of the aperture, masks and the extraction rule.

Pure functions over the rows of ``spectral_cube.Spectrum`` (no network, no Streamlit). Nothing here changes a
measurement: it only describes what the extraction already saw. The causes can coexist (a channel can lack data
in part of its aperture, show BLOOM and OVERFLOW pixels, and be rejected by the extraction rule at the same time),
so they are returned as a list, never as one exclusive category.

Extraction rule described (``spectral_cube.extract_spectrum``): a channel receives a flux only if EVERY pixel of
the aperture (weight > 0) has data (finite IMAGE and NHITS > 0) and at least half of the annulus is valid.
Invalid pixels are never filled or interpolated, and apertures with partial coverage are not measured.
"""
from __future__ import annotations

from dataclasses import dataclass, field

NO_DATA, BLOOM, OVERFLOW = "sin_datos", "bloom", "overflow"
INCOMPLETE, BLANK, NO_BACKGROUND = "apertura_incompleta", "canal_vacio_dr1", "sin_fondo"
NO_PIXELS = "sin_pixeles"

CAUSE_TEXT = {
    BLANK: "The channel is listed without data in DR1 (BLANKCH).",
    NO_DATA: "Aperture pixels without data in the cube (NaN value or NHITS = 0).",
    BLOOM: "Aperture pixels with the BLOOM mask of the FLAGS extension of the FITS.",
    OVERFLOW: "Aperture pixels with the OVERFLOW mask (saturation).",
    INCOMPLETE: "The current extraction requires the full aperture to have data; it does not fill or interpolate pixels.",
    NO_BACKGROUND: "Less than half of the background annulus has data.",
    NO_PIXELS: "The aperture contains no cube pixel at this position.",
}
REQUIRED = ("ap_pix_total", "ap_pix_invalidos", "ap_pix_nan", "ap_pix_nhits0", "ap_peso_total", "ap_peso_invalido",
            "ap_bloom", "ap_overflow")


@dataclass(frozen=True)
class ChannelQuality:
    canal: int
    lambda_um: float
    detector: int
    available: bool                      # the aperture counts exist (rows from an older extraction lack them)
    status: str                          # status of the extraction: ok | blank | no_data_aperture | no_background
    valid_for_extraction: bool           # the current extraction produced a flux for this channel
    rejected_incomplete_aperture: bool   # no flux because part of the aperture had no data
    caution: bool                        # has a flux, but with OVERFLOW/OUTLIER pixels in the aperture
    px_total: int | None = None
    px_valid: int | None = None
    px_invalid: int | None = None
    px_nan: int | None = None
    px_nhits0: int | None = None
    valid_pct: float | None = None       # valid pixels / pixels of the aperture (count)
    weight_lost_pct: float | None = None  # weight of the invalid pixels / weight of the aperture
    bloom: int | None = None
    overflow: int | None = None
    causes: tuple = field(default_factory=tuple)

    @property
    def affected(self) -> bool:
        """Anything worth telling about this channel (no value, or a value with a caution)."""
        return (not self.valid_for_extraction) or self.caution or bool(self.px_invalid) or bool(self.bloom)


def channel_quality(row: dict) -> ChannelQuality:
    status = row["status"]
    base = dict(canal=int(row["canal"]), lambda_um=float(row["lambda_um"]), detector=int(row["detector"]),
                status=status, valid_for_extraction=status == "ok", caution=bool(row.get("precaucion")) and status == "ok")
    if status == "blank":                                    # declared empty by the product: no pixel is read
        return ChannelQuality(available=True, rejected_incomplete_aperture=False, causes=(BLANK,), **base)
    if any(row.get(k) is None for k in REQUIRED):
        return ChannelQuality(available=False, rejected_incomplete_aperture=status == "no_data_aperture", **base)
    total, bad = int(row["ap_pix_total"]), int(row["ap_pix_invalidos"])
    weight, bad_w = float(row["ap_peso_total"]), float(row["ap_peso_invalido"])
    bloom, overflow = int(row["ap_bloom"]), int(row["ap_overflow"])
    rejected = status == "no_data_aperture" and bad > 0
    causes = []
    if total == 0:
        causes.append(NO_PIXELS)
    if bad:
        causes.append(NO_DATA)
    if bloom:
        causes.append(BLOOM)
    if overflow:
        causes.append(OVERFLOW)
    if rejected:
        causes.append(INCOMPLETE)
    if status == "no_background":
        causes.append(NO_BACKGROUND)
    return ChannelQuality(
        available=True, rejected_incomplete_aperture=rejected, px_total=total, px_valid=total - bad, px_invalid=bad,
        px_nan=int(row["ap_pix_nan"]), px_nhits0=int(row["ap_pix_nhits0"]),
        valid_pct=100.0 * (total - bad) / total if total else None,
        weight_lost_pct=100.0 * bad_w / weight if weight else None, bloom=bloom, overflow=overflow,
        causes=tuple(causes), **base)


def spectrum_quality(spec) -> list[ChannelQuality]:
    return [channel_quality(r) for r in spec.rows]


def summary(qs: list[ChannelQuality]) -> dict:
    """Counts for a whole spectrum. The groups overlap on purpose (a channel can be in several)."""
    real = [q for q in qs if q.status != "blank"]
    return {"canales": len(qs), "con_valor": sum(q.valid_for_extraction for q in qs),
            "vacios_dr1": sum(q.status == "blank" for q in qs),
            "rechazados_apertura_incompleta": sum(q.rejected_incomplete_aperture for q in qs),
            "sin_fondo": sum(q.status == "no_background" for q in qs),
            "con_bloom": sum(bool(q.bloom) for q in real), "con_overflow": sum(bool(q.overflow) for q in real),
            "con_precaucion": sum(q.caution for q in qs), "sin_informacion": sum(not q.available for q in qs)}


def has_unreported_loss(qs: list[ChannelQuality]) -> bool:
    """True when some channel lacks a value for a reason other than being empty in DR1 (channels 51 and 52)."""
    return any((not q.valid_for_extraction) and q.status != "blank" for q in qs)


def too_bright(qs: list[ChannelQuality]) -> dict | None:
    """Counts when the channels without a value are explained by a very bright source at the position.

    The instrument flags the pixels around a saturated source (OVERFLOW, and BLOOM for the charge that spills into
    neighbours) and the cube leaves them without data, so the extraction (which needs every aperture pixel) rejects
    the channel. Returned only when most of the rejected channels carry one of those flags; otherwise the missing
    values have another cause and no brightness claim is made. Nothing here changes a measurement.
    """
    rejected = [q for q in qs if q.status != "blank" and not q.valid_for_extraction and q.available]
    if not rejected:
        return None
    bright = [q for q in rejected if q.bloom or q.overflow]
    if len(bright) < max(3, (len(rejected) + 1) // 2):
        return None
    return {"rejected": len(rejected), "bright": len(bright), "bloom": sum(bool(q.bloom) for q in rejected),
            "overflow": sum(bool(q.overflow) for q in rejected), "measured": sum(q.valid_for_extraction for q in qs),
            "channels": len(qs)}


def bright_text(info: dict, scientific: bool) -> str:
    """Why the spectrum is empty or partial at a very bright position, in the wording of each level."""
    if scientific:
        return (f"<b>Very bright position.</b> {info['bright']} of the {info['rejected']} channels without a value have "
                f"aperture pixels flagged by the instrument as BLOOM (charge spilling from a saturated source; {info['bloom']} "
                f"channels) or OVERFLOW (saturation; {info['overflow']} channels). The cube leaves those pixels without data "
                "and the extraction requires every pixel of the aperture, so it does not measure them and does not fill or "
                "interpolate. This is a limit of the observation at this position, not a spectrum of zero light. Try a "
                "nearby position away from the brightest source.")
    return ("<b>This spot is too bright for the detector.</b> The instrument saturates around very bright sources and "
            f"leaves those pixels without data, so SPHEREx gives no value here in {info['rejected']} of the "
            f"{info['channels']} colours. It is a limit of the observation, not an error. Press another point on the image, "
            "away from the brightest spot, to see its spectrum.")


# ----------------------------------------------------------------------------- wording
def plain(q: ChannelQuality) -> str | None:
    """One sentence for the Sencillo level; None when there is nothing to say."""
    if q.status == "blank":
        return "This colour has no data in the SPHEREx catalogue."
    if q.status == "no_background":
        return "This channel cannot be analysed because there is not enough background information around the point."
    if q.status == "no_data_aperture":
        return "This channel cannot be analysed because part of the selected region has no usable data."
    if q.caution:
        return "This channel has data, but part of the light may have saturated: take it with caution."
    return None


def status_text(q: ChannelQuality) -> str:
    """Short status for the scientific table."""
    if q.status == "blank":
        return "No data in DR1"
    if q.rejected_incomplete_aperture:
        return "Rejected: incomplete aperture"
    if q.status == "no_data_aperture":
        return "Rejected: aperture without data"
    if q.status == "no_background":
        return "Rejected: insufficient background"
    return "Valid, with caution" if q.caution else "Valid"


def cause_names(q: ChannelQuality) -> str:
    names = {NO_DATA: "no data", BLOOM: "BLOOM", OVERFLOW: "OVERFLOW", INCOMPLETE: "incomplete aperture",
             BLANK: "channel empty in DR1", NO_BACKGROUND: "insufficient background", NO_PIXELS: "aperture without pixels"}
    return " · ".join(names[c] for c in q.causes) or "—"


def _pct(q: ChannelQuality) -> str:
    if not q.available or q.px_total is None:
        return "not available"
    if not q.px_total:
        return "0 pixels in the aperture"
    return f"{q.px_valid} de {q.px_total} ({q.valid_pct:.0f} %)"


def table_rows(qs: list[ChannelQuality]) -> list[dict]:
    """Rows for the scientific table (one per channel)."""
    out = []
    for q in qs:
        invalid = ("—" if not q.available or q.px_invalid is None else
                   f"{q.px_invalid} (NaN {q.px_nan} · NHITS = 0 {q.px_nhits0})")
        out.append({"Channel": q.canal, "λ (µm)": round(q.lambda_um, 3), "Detector": f"D{q.detector}",
                    "Valid pixels": _pct(q), "Pixels without data": invalid,
                    "Lost weight": "—" if q.weight_lost_pct is None else f"{q.weight_lost_pct:.0f} %",
                    # text, not numbers: blank channels have no counts and a mixed column cannot be serialised
                    "BLOOM": "—" if q.bloom is None else str(q.bloom),
                    "OVERFLOW": "—" if q.overflow is None else str(q.overflow),
                    "Status": status_text(q), "Causes": cause_names(q)})
    return out


def ranges_text(channels: list[tuple[int, float]]) -> str:
    """'canales 53–56 (2.72–2.96 µm), 63' style summary of consecutive channels: [(canal, λ), …]."""
    if not channels:
        return ""
    channels = sorted(channels)
    runs, cur = [], [channels[0]]
    for c in channels[1:]:
        if c[0] == cur[-1][0] + 1:
            cur.append(c)
        else:
            runs.append(cur)
            cur = [c]
    runs.append(cur)
    parts = [f"{r[0][1]:.2f} µm" if len(r) == 1 else f"{r[0][1]:.2f}–{r[-1][1]:.2f} µm" for r in runs]
    return ", ".join(parts)
