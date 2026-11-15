"""Figures of the infrared S/N enhancement. Rendering only: no value is changed here.

Every panel of one figure shares the same intensity normalisation, so a darker sky in the combined
panel is lower noise, not a different stretch. Pixels without valid data use the mask colour.
"""
from __future__ import annotations

import numpy as np
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from matplotlib.patches import Circle

from . import render

EMBER = "#c4411c"
INK = "#14171c"
MUTED = "#5b6470"


def _north_east(stack):
    """Unit vectors (dx, dy) of north and east on the grid, at its centre."""
    ny, nx = stack.shape
    cx, cy = (nx - 1) / 2, (ny - 1) / 2
    ra, dec = stack.wcs.all_pix2world(cx, cy, 0)
    d = 30 / 3600
    xn, yn = stack.wcs.all_world2pix(ra, dec + d, 0)
    xe, ye = stack.wcs.all_world2pix(ra + d / max(np.cos(np.radians(dec)), 1e-6), dec, 0)
    n = np.array([xn - cx, yn - cy], float)
    e = np.array([xe - cx, ye - cy], float)
    return n / np.linalg.norm(n), e / np.linalg.norm(e)


def _decorate(ax, stack, title, window=None):
    ny, nx = stack.shape
    if window is None:
        yy, xx = np.nonzero(stack.field)
        x0, x1, y0, y1 = xx.min() - .5, xx.max() + .5, yy.min() - .5, yy.max() + .5
    else:
        x0, x1, y0, y1 = window
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_color("#e3e6ea")
    ax.set_title(title, fontsize=10.5, color=INK, loc="left", pad=6)
    span = x1 - x0
    px = stack.pixel_scale_arcsec
    bar = 60 / px if span * px > 200 else 20 / px
    label = "1′" if span * px > 200 else "20″"
    bx, by = x0 + 0.06 * span, y0 + 0.06 * (y1 - y0)
    ax.plot([bx, bx + bar], [by, by], color="white", lw=3.2, solid_capstyle="butt")
    ax.plot([bx, bx + bar], [by, by], color=INK, lw=1.4, solid_capstyle="butt")
    ax.text(bx + bar / 2, by + 0.025 * (y1 - y0), label, color="white", fontsize=8, ha="center", va="bottom",
            bbox=dict(facecolor=INK, edgecolor="none", alpha=.55, pad=1.2))


def _compass(ax, stack, window=None):
    n, e = _north_east(stack)
    if window is None:
        yy, xx = np.nonzero(stack.field)
        x0, x1, y0, y1 = xx.min(), xx.max(), yy.min(), yy.max()
    else:
        x0, x1, y0, y1 = window
    L = 0.09 * (x1 - x0)
    ox, oy = x1 - 0.13 * (x1 - x0), y0 + 0.13 * (y1 - y0)
    for v, t in ((n, "N"), (e, "E")):
        ax.annotate("", xy=(ox + L * v[0], oy + L * v[1]), xytext=(ox, oy),
                    arrowprops=dict(arrowstyle="-|>", color="white", lw=1.1, mutation_scale=7))
        ax.text(ox + 1.45 * L * v[0], oy + 1.45 * L * v[1], t, color="white", fontsize=7.5, ha="center", va="center")


def _norm(stack, single):
    return render.shared_norm([single, stack.image], lo=2, hi=99.6, region=stack.field)


@render.serialized
def comparison_png(stack, *, index: int | None = None, marks=(), simple: bool = False, window=None,
                   single_title: str | None = None, combined_title: str | None = None, dpi: int = 120) -> bytes:
    """One exposure next to the combination, same grid, same normalisation."""
    i = stack.reference if index is None else index
    single = stack.data[i]
    norm = _norm(stack, single)
    fig = Figure(figsize=(9.6, 5.2), dpi=dpi, facecolor="white")
    axes = [fig.add_axes([0.02, 0.15, 0.47, 0.78]), fig.add_axes([0.51, 0.15, 0.47, 0.78])]
    date = str(stack.exposures[i].image.meta.get("DATE-AVG") or "")[:10]
    titles = (single_title or f"Una exposición · {date}",
              combined_title or f"Combinación · {stack.n_exposures} exposiciones")
    for ax, data, title in zip(axes, (single, stack.image), titles):
        ax.imshow(render.to_rgba(data, norm), origin="lower", interpolation="nearest")
        _decorate(ax, stack, title, window)
        for m in marks:
            ax.add_patch(Circle((m["x"], m["y"]), 3.2 * stack.oversample, fill=False, edgecolor=EMBER, linewidth=1.1))
    _compass(axes[1], stack, window)
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=render._cmap()), cax=fig.add_axes([0.25, 0.075, 0.5, 0.022]),
                      orientation="horizontal")
    cb.set_label("Brillo (misma escala en las dos imágenes)" if simple else
                 "IMAGE − ZODI − constante de cielo · MJy/sr · escala asinh común", fontsize=8.5, color=INK)
    cb.ax.tick_params(labelsize=7.5, colors=INK)
    return render.figure_png(fig)


@render.serialized
def diagnostic_png(stack, dpi: int = 120) -> bytes:
    """Null image in units of its formal error, and the number of exposures behind every pixel."""
    fig = Figure(figsize=(9.6, 5.0), dpi=dpi, facecolor="white")
    a1, a2 = fig.add_axes([0.02, 0.15, 0.47, 0.78]), fig.add_axes([0.51, 0.15, 0.47, 0.78])
    z = stack.null / np.sqrt(stack.null_variance) if stack.null is not None else np.full(stack.shape, np.nan)
    zn = Normalize(-5, 5)
    rgba = __import__("matplotlib").colormaps["RdBu_r"](zn(np.where(np.isfinite(z), z, 0)))
    rgba[~np.isfinite(z)] = __import__("matplotlib").colors.to_rgba(render.MASK_COLOR)
    a1.imshow(rgba, origin="lower", interpolation="nearest")
    _decorate(a1, stack, "Imagen nula · (mitad A − mitad B) / 2")
    cb = fig.colorbar(ScalarMappable(norm=zn, cmap="RdBu_r"), cax=fig.add_axes([0.08, 0.075, 0.35, 0.022]),
                      orientation="horizontal")
    cb.set_label("desviación / error formal (σ)", fontsize=8.5, color=INK)
    cb.ax.tick_params(labelsize=7.5, colors=INK)
    nn = Normalize(0, stack.n_exposures)
    a2.imshow(np.where(stack.n > 0, stack.n, np.nan), origin="lower", interpolation="nearest", cmap="viridis", norm=nn)
    a2.set_facecolor(render.MASK_COLOR)
    _decorate(a2, stack, "Exposiciones válidas por píxel")
    cb = fig.colorbar(ScalarMappable(norm=nn, cmap="viridis"), cax=fig.add_axes([0.57, 0.075, 0.35, 0.022]),
                      orientation="horizontal")
    cb.set_label("número de exposiciones", fontsize=8.5, color=INK)
    cb.ax.tick_params(labelsize=7.5, colors=INK)
    return render.figure_png(fig)


@render.serialized
def zoom_png(stack, x: float, y: float, half_px: int = 9, title: str = "", dpi: int = 120) -> bytes:
    """Every exposure and the combination around one position: same grid, same normalisation."""
    o = stack.oversample
    h = half_px * o
    window = (x - h - .5, x + h + .5, y - h - .5, y + h + .5)
    yy, xx = np.indices(stack.shape)
    box = (np.abs(xx - x) <= h) & (np.abs(yy - y) <= h)
    norm = render.shared_norm(list(stack.data) + [stack.image], lo=2, hi=99.8, region=box)
    n = stack.n_exposures + 1
    cols = min(n, 4)
    rows = int(np.ceil(n / cols))
    fig = Figure(figsize=(2.5 * cols, 2.75 * rows + 0.7), dpi=dpi, facecolor="white")
    for k in range(n):
        ax = fig.add_subplot(rows, cols, k + 1)
        last = k == n - 1
        data = stack.image if last else stack.data[k]
        ax.imshow(render.to_rgba(data, norm), origin="lower", interpolation="nearest")
        date = "" if last else str(stack.exposures[k].image.meta.get("DATE-AVG") or "")[:16].replace("T", " ")
        _decorate(ax, stack, f"Combinación · {stack.n_exposures}" if last else date, window)
        ax.title.set_fontsize(8.5)
        ax.add_patch(Circle((x, y), 3.2 * o, fill=False, edgecolor=EMBER, linewidth=1.0))
        if last:
            for s in ax.spines.values():
                s.set_color(EMBER)
                s.set_linewidth(1.4)
    if title:
        fig.suptitle(title, fontsize=10.5, color=INK, x=0.02, ha="left")
    fig.text(0.02, 0.012, "IMAGE − ZODI − constante de cielo (MJy/sr), escala asinh común a todos los paneles. "
             "Rosa: sin dato válido. Círculo: posición examinada.", fontsize=7.5, color=MUTED)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.90 if title else 0.95, bottom=0.07, wspace=0.06, hspace=0.18)
    return render.figure_png(fig)
