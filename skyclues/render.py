"""Display of SPHEREx data. Visualization only: the data arrays are never altered.

Rules enforced here:
* invalid / masked pixels are NaN and drawn in a dedicated, labelled colour;
  they are never filled or interpolated;
* both epochs share one intensity normalisation (same vmin/vmax/stretch), so
  apparent brightness changes are not produced by independent stretching;
* the displayed quantity is stated (IMAGE or IMAGE - ZODI, MJy/sr).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from astropy.visualization import AsinhStretch, ImageNormalize  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402

from .compare import PairEvaluation, place_on_a  # noqa: E402
from .fitsdata import SpectralImage  # noqa: E402

MASK_COLOR = "#e0457b"
INK = "#14181f"
GRID = "#9aa4b2"
ACCENT = "#1f5fbf"


def display_array(img: SpectralImage, subtract_zodi: bool = True,
                  mask_classes=("unusable", "artifact")) -> np.ndarray:
    """IMAGE (optionally minus ZODI) with invalid pixels set to NaN (a new array)."""
    data = img.image - img.zodi if subtract_zodi else img.image.copy()
    data = np.where(img.valid(mask_classes), data, np.nan)
    return data


def aligned_b(b: SpectralImage, ev: PairEvaluation, subtract_zodi: bool = True,
              mask_classes=("unusable", "artifact")) -> np.ndarray:
    """B values placed on A's pixel grid by nearest neighbour (no interpolation)."""
    data_b = display_array(b, subtract_zodi, mask_classes)
    return place_on_a(data_b, ev.b_index, ev.in_b)


def shared_norm(arrays, lo=1.0, hi=99.5, region=None) -> ImageNormalize:
    vals = []
    for a in arrays:
        v = a[region] if region is not None else a
        vals.append(v[np.isfinite(v)])
    allv = np.concatenate(vals) if vals else np.array([0.0, 1.0])
    vmin, vmax = np.percentile(allv, [lo, hi]) if allv.size else (0.0, 1.0)
    return ImageNormalize(vmin=vmin, vmax=vmax, stretch=AsinhStretch(0.1), clip=True)


def _cmap():
    cm = plt.get_cmap("gray").copy()
    cm.set_bad(MASK_COLOR)
    return cm


def to_rgba(data: np.ndarray, norm: ImageNormalize) -> np.ndarray:
    """Explicit RGBA rendering: grey scale for valid pixels, MASK_COLOR for NaN.

    Building the RGBA array ourselves (instead of relying on matplotlib's
    'bad' colour through a third-party norm) guarantees that masked pixels
    can never be drawn as bright or dark sky.
    """
    from matplotlib.colors import to_rgba as _c

    finite = np.isfinite(data)
    scaled = np.zeros(data.shape, float)
    scaled[finite] = np.asarray(norm(data[finite]), float)
    rgba = plt.get_cmap("gray")(np.clip(scaled, 0.0, 1.0))
    rgba[~finite] = _c(MASK_COLOR)
    return rgba


def _style_axes(ax):
    ax.set_facecolor("white")
    ax.coords.grid(True, color=GRID, ls=":", lw=0.6, alpha=0.8)
    ax.coords[0].set_axislabel("RA (ICRS)", color=INK)
    ax.coords[1].set_axislabel("Dec (ICRS)", color=INK)
    for c in ax.coords:
        c.set_ticklabel(color=INK, size=8)


def _mark_target(ax, ra, dec, field_deg):
    from astropy import units as u
    from astropy.visualization.wcsaxes import SphericalCircle

    ax.add_patch(SphericalCircle((ra * u.deg, dec * u.deg), field_deg / 2 * u.deg, edgecolor=ACCENT,
                                 facecolor="none", lw=1.0, ls="--", transform=ax.get_transform("icrs")))
    ax.scatter([ra], [dec], s=60, marker="+", color=ACCENT, lw=1.2, transform=ax.get_transform("icrs"))


def frame_figure(data: np.ndarray, wcs, norm, title: str, ra: float, dec: float, field_deg: float,
                 subtitle: str = ""):
    fig = plt.figure(figsize=(5.2, 5.4), dpi=130, facecolor="white")
    ax = fig.add_subplot(1, 1, 1, projection=wcs)
    ax.imshow(to_rgba(data, norm), origin="lower", interpolation="nearest")
    _style_axes(ax)
    _mark_target(ax, ra, dec, field_deg)
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    if subtitle:
        fig.text(0.02, 0.01, subtitle, fontsize=7, color="#4a5463")
    from matplotlib.cm import ScalarMappable

    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=_cmap()), ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("MJy/sr", color=INK, fontsize=8)
    cb.ax.tick_params(labelsize=7, colors=INK)
    fig.tight_layout()
    return fig


COVERAGE_LABELS = ["Fuera del campo", "Válido en A y B", "Solo válido en A", "Solo válido en B", "Sin datos válidos"]
COVERAGE_COLORS = ["#ffffff", "#2e7d32", "#f2b134", "#5b8def", MASK_COLOR]


def coverage_codes(ev: PairEvaluation) -> np.ndarray:
    codes = np.zeros(ev.field_mask.shape, int)
    f = ev.field_mask
    codes[f & ev.valid_a & ev.valid_b_on_a] = 1
    codes[f & ev.valid_a & ~ev.valid_b_on_a] = 2
    codes[f & ~ev.valid_a & ev.valid_b_on_a] = 3
    codes[f & ~ev.valid_a & ~ev.valid_b_on_a] = 4
    return codes


def coverage_figure(ev: PairEvaluation, wcs, ra, dec, field_deg):
    fig = plt.figure(figsize=(5.2, 5.4), dpi=130, facecolor="white")
    ax = fig.add_subplot(1, 1, 1, projection=wcs)
    ax.imshow(coverage_codes(ev), origin="lower", cmap=ListedColormap(COVERAGE_COLORS), vmin=-0.5, vmax=4.5,
              interpolation="nearest")
    _style_axes(ax)
    _mark_target(ax, ra, dec, field_deg)
    ax.set_title("Cobertura válida común (rejilla de A)", color=INK, fontsize=10, loc="left")
    from matplotlib.patches import Patch

    ax.legend(handles=[Patch(facecolor=c, edgecolor="#cfd5dd", label=l)
                       for c, l in zip(COVERAGE_COLORS[1:], COVERAGE_LABELS[1:])],
              loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2, fontsize=7, frameon=False)
    fig.tight_layout()
    return fig


def dlambda_figure(ev: PairEvaluation, wcs, ra, dec, field_deg, limit=0.5):
    fig = plt.figure(figsize=(5.2, 5.4), dpi=130, facecolor="white")
    ax = fig.add_subplot(1, 1, 1, projection=wcs)
    cm = plt.get_cmap("RdBu_r").copy()
    cm.set_bad("#ffffff")
    im = ax.imshow(ev.dlambda_bw, origin="lower", cmap=cm, vmin=-limit, vmax=limit, interpolation="nearest")
    _style_axes(ax)
    _mark_target(ax, ra, dec, field_deg)
    ax.set_title("(λA − λB) / ancho de banda", color=INK, fontsize=10, loc="left")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.ax.tick_params(labelsize=7, colors=INK)
    fig.tight_layout()
    return fig
