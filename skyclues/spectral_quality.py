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
    BLANK: "El canal figura sin datos en DR1 (BLANKCH).",
    NO_DATA: "Píxeles de la apertura sin datos en el cubo (valor NaN o NHITS = 0).",
    BLOOM: "Píxeles de la apertura con la máscara BLOOM de la extensión FLAGS del FITS.",
    OVERFLOW: "Píxeles de la apertura con la máscara OVERFLOW (saturación).",
    INCOMPLETE: "La extracción actual exige la apertura completa con datos; no rellena ni interpola píxeles.",
    NO_BACKGROUND: "Menos de la mitad del anillo de fondo tiene datos.",
    NO_PIXELS: "La apertura no contiene ningún píxel del cubo en esta posición.",
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


# ----------------------------------------------------------------------------- wording
def plain(q: ChannelQuality) -> str | None:
    """One sentence for the Sencillo level; None when there is nothing to say."""
    if q.status == "blank":
        return "Este color no tiene datos en el catálogo de SPHEREx."
    if q.status == "no_background":
        return "Este canal no puede analizarse porque no hay suficiente información de fondo alrededor del punto."
    if q.status == "no_data_aperture":
        return "Este canal no puede analizarse porque parte de la región seleccionada no tiene datos utilizables."
    if q.caution:
        return "Este canal tiene datos, pero parte de la luz pudo saturarse: tómalo con cautela."
    return None


def status_text(q: ChannelQuality) -> str:
    """Short status for the scientific table."""
    if q.status == "blank":
        return "Sin datos en DR1"
    if q.rejected_incomplete_aperture:
        return "Rechazado: apertura incompleta"
    if q.status == "no_data_aperture":
        return "Rechazado: apertura sin datos"
    if q.status == "no_background":
        return "Rechazado: fondo insuficiente"
    return "Válido, con precaución" if q.caution else "Válido"


def cause_names(q: ChannelQuality) -> str:
    names = {NO_DATA: "sin datos", BLOOM: "BLOOM", OVERFLOW: "OVERFLOW", INCOMPLETE: "apertura incompleta",
             BLANK: "canal vacío en DR1", NO_BACKGROUND: "fondo insuficiente", NO_PIXELS: "apertura sin píxeles"}
    return " · ".join(names[c] for c in q.causes) or "—"


def _pct(q: ChannelQuality) -> str:
    if not q.available or q.px_total is None:
        return "no disponible"
    if not q.px_total:
        return "0 píxeles en la apertura"
    return f"{q.px_valid} de {q.px_total} ({q.valid_pct:.0f} %)"


def table_rows(qs: list[ChannelQuality]) -> list[dict]:
    """Rows for the scientific table (one per channel)."""
    out = []
    for q in qs:
        invalid = ("—" if not q.available or q.px_invalid is None else
                   f"{q.px_invalid} (NaN {q.px_nan} · NHITS = 0 {q.px_nhits0})")
        out.append({"Canal": q.canal, "λ (µm)": round(q.lambda_um, 3), "Detector": f"D{q.detector}",
                    "Píxeles válidos": _pct(q), "Píxeles sin datos": invalid,
                    "Peso perdido": "—" if q.weight_lost_pct is None else f"{q.weight_lost_pct:.0f} %",
                    # text, not numbers: blank channels have no counts and a mixed column cannot be serialised
                    "BLOOM": "—" if q.bloom is None else str(q.bloom),
                    "OVERFLOW": "—" if q.overflow is None else str(q.overflow),
                    "Estado": status_text(q), "Causas": cause_names(q)})
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
