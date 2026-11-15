"""Multiband false-colour composition of three real channels of the SPHEREx DR1 cube.

What it is
----------
Three channels of the DR1 All-Sky cube (doi:10.26131/IRSA679) are shown together, one per
display colour (R, G, B). It is a DISPLAY CONVENTION for infrared light (0.75-5.0 um, invisible
to the eye), never the visible colour of the sky, and it is not a measurement.

Integrity rules
---------------
* Pixel values come from ``spectral_cube.channel_map``: the existing HTTP Range reader of the
  official FITS cubes (no second download engine, no whole tiles, verbatim byte cache). Values
  are never modified: the stretch only maps them to screen intensities.
* Channels listed in BLANKCH (51 and 52: no data in DR1) cannot be selected.
* The three planes of a tile share ONE celestial WCS (the cube's IMAGE header): pixel (x, y) is
  the same HEALPix pixel in every channel. ``check_alignment`` verifies it for every tile of the
  field (same file and ETag, same WCS, same pixel box, same pixel centres). No resampling is
  done; if the planes did not share the grid the composition is refused.
* A pixel is coloured only where ALL THREE channels hold data (finite IMAGE, NHITS > 0). A pixel
  with data in only one or two channels is drawn as "no data", never as a partial colour (a
  missing channel would otherwise look like a real absence of that colour).
* Stretch: asinh (a = 0.1) between percentiles 1 and 99.5 of the field pixels with data in the
  three channels, as in the single-channel view. Mode "independiente": limits per channel (each
  channel uses its full contrast; colours do NOT reflect brightness ratios between channels).
  Mode "comun": the same MJy/sr limits for the three (relative surface brightness preserved,
  faint channels may look dark). Deterministic and fully recorded in ``StretchSpec``.
* No coaddition, no detection, no physical inference (temperature, composition, motion,
  variability) and no change of the signal-to-noise ratio.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from astropy.visualization import AsinhStretch, ImageNormalize

from . import config
from . import spectral_cube as sc

ROLES = ("R", "G", "B")
ROLE_NAMES = {"R": "rojo", "G": "verde", "B": "azul"}
#: default assignment (nearest real channel): long, middle, short wavelength.
DEFAULT_LAMBDAS_UM = {"R": 4.5, "G": 2.2, "B": 1.2}
PERCENTILES = (1.0, 99.5)
ASINH_A = 0.1
STRETCH_MODES = {
    "independiente": "límites propios de cada canal (percentiles 1–99.5, asinh)",
    "comun": "mismos límites en MJy/sr para los tres canales (percentiles 1–99.5 del conjunto, asinh)",
}
#: display intensity (0-1, after the stretch) below which a colour is practically black on screen.
DARK_LEVEL = 0.10
#: display intensity above which a colour is saturated (white when the three are).
SATURATED_LEVEL = 0.99
#: the common scale is reported as lacking useful contrast when at least this fraction of the
#: field pixels has the three colours below DARK_LEVEL (presentation only; data are unchanged).
LOW_CONTRAST_FRACTION = 0.50
#: below this number of field pixels with data in the three channels the composition is refused.
MIN_COMMON_PIXELS = 50
#: warn when the pixels with data in the three channels are less than this fraction of the field.
COVERAGE_WARN_FRACTION = 0.90
#: Strong lines near which the DR1 mosaic shows LVF striping (Explanatory Supplement v2.1).
STRIPING_LINES_UM = {"He I 1.083 µm (airglow)": 1.083, "Paα 1.875 µm": 1.875, "PAH 3.3 µm": 3.3,
                     "Brα 4.05 µm": 4.05}


class MultibandAlignmentError(sc.CubeFormatError):
    """The three planes do not share the same native pixels: the composition is refused."""


class InsufficientDataError(ValueError):
    """Too few field pixels hold data in the three channels to build a composition."""


# ----------------------------------------------------------------------------- channels
def selectable(channels: list[sc.Channel]) -> list[sc.Channel]:
    """Channels that may enter a composition: every real channel except BLANKCH ones."""
    return [c for c in channels if not c.blank]


def default_numbers(channels: list[sc.Channel]) -> dict[str, int]:
    ok = selectable(channels)
    return {r: min(ok, key=lambda c: abs(c.wavelength_um - lam)).number for r, lam in DEFAULT_LAMBDAS_UM.items()}


def select_channels(channels: list[sc.Channel], numbers: dict[str, int]) -> dict[str, sc.Channel]:
    """{R, G, B: Channel}. Refuses missing roles, unknown or repeated channels and BLANKCH channels."""
    if set(numbers) != set(ROLES):
        raise ValueError("la composición necesita exactamente un canal para R, G y B")
    by_number = {c.number: c for c in channels}
    out = {}
    for role in ROLES:
        n = numbers[role]
        if not isinstance(n, (int, np.integer)) or int(n) not in by_number:
            raise ValueError(f"canal {n!r} inexistente para {role}")
        c = by_number[int(n)]
        if c.blank:
            raise ValueError(f"el canal {c.number} ({c.wavelength_um:.3f} µm) no tiene datos en DR1 (BLANKCH); "
                             "no puede formar parte de una composición")
        out[role] = c
    if len({c.number for c in out.values()}) != 3:
        raise ValueError("los tres canales deben ser distintos")
    return out


def striping_lines(c: sc.Channel) -> list[str]:
    """Documented strong lines that fall inside the channel band (possible mosaic striping)."""
    return [name for name, lam in STRIPING_LINES_UM.items() if c.wl_min_um <= lam <= c.wl_max_um]


# ----------------------------------------------------------------------------- stretch
@dataclass(frozen=True)
class StretchSpec:
    """Everything needed to reproduce the display mapping MJy/sr -> [0, 1] of each channel."""

    mode: str
    percentiles: tuple[float, float]
    asinh_a: float
    vmin: dict[str, float]
    vmax: dict[str, float]
    n_pixels: int                     # field pixels with data in the three channels used for the limits
    degenerate: tuple[str, ...] = ()  # channels with no contrast in the field (vmax forced above vmin)

    def norm(self, role: str) -> ImageNormalize:
        return ImageNormalize(vmin=self.vmin[role], vmax=self.vmax[role], stretch=AsinhStretch(self.asinh_a),
                              clip=True)

    def apply(self, role: str, values: np.ndarray) -> np.ndarray:
        """Display intensities in [0, 1]; NaN stays NaN (never a value)."""
        values = np.asarray(values, float)
        out = np.full(values.shape, np.nan)
        ok = np.isfinite(values)
        out[ok] = np.asarray(self.norm(role)(values[ok]), float)
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        d["description"] = STRETCH_MODES[self.mode]
        d["note"] = "solo afecta a la visualización; los valores del cubo no se modifican"
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "StretchSpec":
        return cls(mode=d["mode"], percentiles=tuple(d["percentiles"]), asinh_a=float(d["asinh_a"]),
                   vmin=dict(d["vmin"]), vmax=dict(d["vmax"]), n_pixels=int(d["n_pixels"]),
                   degenerate=tuple(d.get("degenerate", ())))


def compute_stretch(samples: dict[str, np.ndarray], mode: str) -> StretchSpec:
    """Limits from the field pixels with data in the three channels (``samples`` per role)."""
    if mode not in STRETCH_MODES:
        raise ValueError(f"modo de escala desconocido: {mode!r}")
    n = {len(v) for v in samples.values()}
    if len(n) != 1:
        raise ValueError("las muestras de los tres canales deben ser los mismos píxeles")
    lo_p, hi_p = PERCENTILES
    vmin, vmax, flat = {}, {}, []
    if mode == "comun":
        allv = np.concatenate([samples[r] for r in ROLES])
        lo, hi = (float(x) for x in np.percentile(allv, [lo_p, hi_p]))
        lims = {r: (lo, hi) for r in ROLES}
    else:
        lims = {r: tuple(float(x) for x in np.percentile(samples[r], [lo_p, hi_p])) for r in ROLES}
    for r in ROLES:
        lo, hi = lims[r]
        if not hi > lo:
            flat.append(r)
            hi = lo + max(abs(lo) * 1e-6, 1e-9)
        vmin[r], vmax[r] = lo, hi
    return StretchSpec(mode, (lo_p, hi_p), ASINH_A, vmin, vmax, n.pop(), tuple(flat))


# ----------------------------------------------------------------------------- composition
@dataclass
class Composite:
    ra: float
    dec: float
    field_deg: float
    channels: dict[str, sc.Channel]
    maps: dict[str, sc.ChannelMap]
    stretch: StretchSpec
    alignment: dict
    coverage: dict
    field_masks: list[np.ndarray]                     # per patch: pixel centre inside the field circle
    warnings: list[str] = field(default_factory=list)

    @property
    def patches(self) -> list[tuple[sc.Patch, sc.Patch, sc.Patch]]:
        return list(zip(*(self.maps[r].patches for r in ROLES)))

    def common_valid(self, i: int) -> np.ndarray:
        """Pixels of patch ``i`` with data in the three channels."""
        return np.logical_and.reduce([p.valid for p in self.patches[i]])

    def rgb(self, i: int) -> np.ndarray:
        """(ny, nx, 3) display intensities of patch ``i``; NaN wherever any channel lacks data."""
        ps = self.patches[i]
        ok = self.common_valid(i)
        out = np.full(ps[0].image.shape + (3,), np.nan)
        for k, (r, p) in enumerate(zip(ROLES, ps)):
            out[..., k][ok] = self.stretch.apply(r, p.image[ok])
        return out

    def display_stats(self) -> dict:
        """How the stretch renders the field pixels with data in the three channels (display only).

        Per colour: fraction clipped to black (value <= vmin) and saturated (>= SATURATED_LEVEL).
        Whole pixel: fraction practically black (three colours < DARK_LEVEL) and white (three
        colours >= SATURATED_LEVEL). ``poco_contraste`` is True when the dark fraction reaches
        LOW_CONTRAST_FRACTION. Measured on the same intensities that are drawn."""
        parts = [self.rgb(i)[self.common_valid(i) & self.field_masks[i]] for i in range(len(self.patches))]
        rgb = np.concatenate(parts) if parts else np.empty((0, 3))
        n = len(rgb)
        if not n:
            return {"n_pixeles": 0, "recortado_a_negro": {}, "saturado": {}, "fraccion_oscura": 0.0,
                    "fraccion_blanca": 0.0, "poco_contraste": False}
        dark = float(np.mean(np.all(rgb < DARK_LEVEL, axis=1)))
        return {"n_pixeles": n,
                "recortado_a_negro": {r: float(np.mean(rgb[:, k] <= 0.0)) for k, r in enumerate(ROLES)},
                "saturado": {r: float(np.mean(rgb[:, k] >= SATURATED_LEVEL)) for k, r in enumerate(ROLES)},
                "fraccion_oscura": dark,
                "fraccion_blanca": float(np.mean(np.all(rgb >= SATURATED_LEVEL, axis=1))),
                "umbral_oscuro": DARK_LEVEL, "umbral_saturado": SATURATED_LEVEL,
                "poco_contraste": self.stretch.mode == "comun" and dark >= LOW_CONTRAST_FRACTION}

    def provenance(self) -> dict:
        tiles = {}
        for ps in self.patches:
            tiles[ps[0].tile.ipix] = ps[0].tile.provenance()
        return {
            "producto": "SPHEREx DR1 All-Sky spectral cube", "doi": config.CUBE_DOI,
            "tipo": "composición de falso color (convención de visualización); no es color visible ni una medida",
            "centro_ra_deg": self.ra, "centro_dec_deg": self.dec, "campo_deg": self.field_deg,
            "canales": {r: {"canal": c.number, "plano": c.plane, "detector": c.detector, "subcanal": c.subchannel,
                            "lambda_um": c.wavelength_um, "lambda_min_um": c.wl_min_um, "lambda_max_um": c.wl_max_um,
                            "ancho_um": c.bandwidth_um, "R": c.resolving_power}
                        for r, c in self.channels.items()},
            "escala": self.stretch.to_dict(), "visualizacion": self.display_stats(),
            "alineacion": self.alignment, "cobertura": self.coverage,
            "remuestreo": "ninguno: los tres planos comparten la rejilla HEALPix nativa de cada tesela",
            "valores": "IMAGE original del cubo en MJy/sr (sin modificar); sin datos = NaN o NHITS = 0",
            "teselas": list(tiles.values()), "avisos": list(self.warnings)}


def check_alignment(maps: dict[str, sc.ChannelMap]) -> dict:
    """Verify that the three channel maps hold the SAME native pixels; raise otherwise."""
    m0 = maps[ROLES[0]]
    for r in ROLES[1:]:
        m = maps[r]
        if (m.ra, m.dec, m.field_deg) != (m0.ra, m0.dec, m0.field_deg):
            raise MultibandAlignmentError("los canales no corresponden al mismo centro y campo")
        if len(m.patches) != len(m0.patches):
            raise MultibandAlignmentError("los canales cubren teselas distintas")
    tiles, solid = [], set()
    for ps in zip(*(maps[r].patches for r in ROLES)):
        a = ps[0]
        wcs0 = a.tile.wcs.to_header_string()
        for b in ps[1:]:
            if (b.tile.ipix, b.tile.order, b.tile.url, b.tile.size, b.tile.etag) != \
                    (a.tile.ipix, a.tile.order, a.tile.url, a.tile.size, a.tile.etag):
                raise MultibandAlignmentError(f"tesela {a.tile.ipix}: los canales proceden de archivos o "
                                              "versiones distintas (ETag)")
            if (b.x0, b.y0, b.image.shape) != (a.x0, a.y0, a.image.shape):
                raise MultibandAlignmentError(f"tesela {a.tile.ipix}: recuadros de píxeles distintos")
            if b.tile.wcs.to_header_string() != wcs0:
                raise MultibandAlignmentError(f"tesela {a.tile.ipix}: WCS celeste distinto entre canales")
            if b.nhits.shape != b.image.shape or b.flags.shape != b.image.shape:
                raise MultibandAlignmentError(f"tesela {a.tile.ipix}: extensiones con forma distinta")
        # Same WCS and box imply the same centres; checked numerically once per tile and channel set.
        ca = a.centres_world()
        for b in ps[1:]:
            if b.tile is not a.tile:
                for u, v in zip(ca, b.centres_world()):
                    if not np.array_equal(u, v):
                        raise MultibandAlignmentError(f"tesela {a.tile.ipix}: centros de píxel distintos")
        solid.add(a.tile.pixel_solid_angle_sr)
        tiles.append({"tesela": int(a.tile.ipix), "x0": int(a.x0), "y0": int(a.y0),
                      "nx": int(a.image.shape[1]), "ny": int(a.image.shape[0]), "etag": a.tile.etag})
    if len(solid) != 1:
        raise MultibandAlignmentError("teselas con ángulos sólidos de píxel distintos")
    return {"verificada": True, "teselas": tiles, "varias_teselas": len(tiles) > 1,
            "pixel_arcsec": m0.patches[0].tile.pixel_scale_arcsec,
            "criterio": "mismo archivo y ETag, mismo WCS celeste, mismo recuadro y mismos centros de píxel "
                        "en los tres canales"}


def _coverage(maps, field_masks) -> tuple[dict, dict[str, np.ndarray]]:
    per = {r: 0 for r in ROLES}
    n_field = common = partial = none = 0
    samples = {r: [] for r in ROLES}
    for i, ps in enumerate(zip(*(maps[r].patches for r in ROLES))):
        f = field_masks[i]
        valid = [p.valid & f for p in ps]
        k = np.sum(valid, axis=0)
        n_field += int(f.sum())
        common += int((k == 3).sum())
        partial += int(((k > 0) & (k < 3)).sum())
        none += int((f & (k == 0)).sum())
        both = k == 3
        for r, p, v in zip(ROLES, ps, valid):
            per[r] += int(v.sum())
            samples[r].append(p.image[both])
    cov = {"n_campo": n_field, "con_datos": per, "tres_canales": common, "parcial": partial, "ninguno": none,
           "fraccion_tres_canales": common / n_field if n_field else 0.0}
    return cov, {r: (np.concatenate(v) if v else np.array([])) for r, v in samples.items()}


def build(ra: float, dec: float, field_deg: float, channels: list[sc.Channel], numbers: dict[str, int],
          mode: str = "independiente", map_fn=None) -> Composite:
    """Read the three channels (through ``map_fn``, default ``spectral_cube.channel_map``), verify
    they share the same native pixels, measure their common coverage and compute the stretch."""
    if mode not in STRETCH_MODES:
        raise ValueError(f"modo de escala desconocido: {mode!r}")
    chosen = select_channels(channels, numbers)          # refuses BLANKCH before any read
    map_fn = map_fn or sc.channel_map
    maps = {r: map_fn(ra, dec, field_deg, chosen[r].plane) for r in ROLES}
    for r in ROLES:
        if maps[r].channel.number != chosen[r].number:
            raise MultibandAlignmentError(f"{r}: se leyó el canal {maps[r].channel.number} en lugar del "
                                          f"{chosen[r].number}")
    alignment = check_alignment(maps)
    field_masks = [maps[ROLES[0]].in_field(p) for p in maps[ROLES[0]].patches]
    cov, samples = _coverage(maps, field_masks)
    if cov["tres_canales"] < MIN_COMMON_PIXELS:
        raise InsufficientDataError(
            f"solo {cov['tres_canales']} píxeles del campo tienen datos en los tres canales (mínimo "
            f"{MIN_COMMON_PIXELS}); no se construye la composición")
    stretch = compute_stretch(samples, mode)
    comp = Composite(ra, dec, field_deg, chosen, maps, stretch, alignment, cov, field_masks)
    comp.warnings = _warnings(comp, samples)
    return comp


def _warnings(comp: Composite, samples: dict[str, np.ndarray]) -> list[str]:
    w = []
    ch, cov, st = comp.channels, comp.coverage, comp.stretch
    if st.mode == "independiente":
        w.append("Escala independiente: cada canal usa todo su contraste, de modo que los colores NO reflejan "
                 "los cocientes de brillo entre canales (un canal mucho más débil puede verse tan intenso como "
                 "los demás). Para comparar intensidades use la escala común o el espectro.")
    else:
        lo, hi = st.vmin["R"], st.vmax["R"]
        for r in ROLES:
            own = float(np.percentile(samples[r], PERCENTILES[1]))
            if own < lo + 0.05 * (hi - lo):
                w.append(f"Escala común: el canal {ch[r].number} ({ROLE_NAMES[r]}) es mucho más débil que los demás "
                         "en MJy/sr y apenas aporta color; no significa que carezca de datos.")
        ds = comp.display_stats()
        if ds["poco_contraste"]:
            w.append(f"Escala común con poco contraste útil: en el {ds['fraccion_oscura']:.0%} del campo los tres colores "
                     f"quedan por debajo del {DARK_LEVEL:.0%} de la escala (casi negro), porque el cielo de fondo es "
                     f"mucho más tenue en MJy/sr que los píxeles más brillantes que fijan el límite común "
                     f"({lo:.4g}–{hi:.4g} MJy/sr). Es la consecuencia correcta de comparar intensidades físicas, no un "
                     "fallo ni falta de datos. Para ver la forma en cada canal use «Resaltar cada color».")
    for r in st.degenerate:
        w.append(f"El canal {ch[r].number} ({ROLE_NAMES[r]}) no tiene contraste en el campo (percentiles iguales): "
                 "su componente de color es uniforme.")
    lam = [ch[r].wavelength_um for r in ROLES]
    if not lam[0] > lam[1] > lam[2]:
        w.append("La asignación no sigue el orden cromático habitual (R = longitud de onda más larga, "
                 "B = más corta); es válida, pero los colores no siguen el orden de λ.")
    differ = len(set(cov["con_datos"].values())) > 1 or cov["parcial"] > 0
    if differ:
        w.append(f"Cobertura distinta entre canales: {cov['parcial']} píxeles del campo tienen datos en uno o dos "
                 "canales pero no en los tres; en la composición se muestran como sin datos (rosa), nunca con un "
                 "color parcial.")
    if cov["fraccion_tres_canales"] < COVERAGE_WARN_FRACTION:
        w.append(f"Solo el {cov['fraccion_tres_canales']:.0%} del campo tiene datos en los tres canales.")
    if comp.alignment["varias_teselas"]:
        w.append("El campo abarca varias teselas HEALPix: se dibujan los píxeles nativos de cada una (misma "
                 "rejilla, mismo ángulo sólido); no hay remuestreo ni costura interpolada.")
    for r in ROLES:
        lines = striping_lines(ch[r])
        if lines:
            w.append(f"El canal {ch[r].number} ({ROLE_NAMES[r]}) contiene {', '.join(lines)}: el mosaico DR1 puede "
                     "mostrar rayado cerca de líneas intensas (problema conocido del LVF); no es estructura del cielo.")
    flagged = {r: comp.maps[r].summary()["flag_pixels"] for r in ROLES}
    sat = {r: f["OVERFLOW"] for r, f in flagged.items() if f.get("OVERFLOW")}
    if sat:
        w.append("Píxeles con OVERFLOW (entradas saturadas) en el campo: " +
                 ", ".join(f"canal {ch[r].number}: {n}" for r, n in sat.items()) + ".")
    return w


__all__ = ["Composite", "InsufficientDataError", "MultibandAlignmentError", "ROLES", "STRETCH_MODES",
           "StretchSpec", "build", "check_alignment", "compute_stretch", "default_numbers", "select_channels",
           "selectable", "striping_lines"]
