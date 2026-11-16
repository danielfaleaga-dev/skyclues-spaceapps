"""Display of a multiband composition (false colour). Visualization only: cube values are never altered.

* Exact geometry, as in the single-channel view: each native mosaic pixel (12.9 arcsec) is a
  quadrilateral at its WCS position in a north-up / east-left TAN frame, with no resampling.
* A pixel is coloured only where the three channels hold data. Pixels without data in at least
  one channel are drawn in MASK_COLOR with white diagonal hatching, so that no uniform colour of
  the composition can be mistaken for them; sky outside the pixels read is dotted grey.
* The per-channel panels show each channel in grey with exactly the limits used in the
  composition, and that channel's own no-data pixels in MASK_COLOR.
"""

from __future__ import annotations

import base64
import io

import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib.collections import PolyCollection
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from . import multiband as mb
from . import render
from . import spectral_cube as sc
from . import spectral_view as sv

MASK_COLOR = render.MASK_COLOR
OUTSIDE_COLOR = sv.OUTSIDE_COLOR
DISPLAY_NPIX = sv.DISPLAY_NPIX
PANEL_NPIX = 260


def frame_for(comp: mb.Composite, npix: int = DISPLAY_NPIX):
    return sc.display_wcs(comp.ra, comp.dec, comp.field_deg * sv.FRAME_MARGIN, npix)


def _axes(npix: int):
    fig = Figure(figsize=(npix / 100, npix / 100), dpi=100, facecolor=OUTSIDE_COLOR)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    # Sky outside the pixels read for the field: dotted, never a data colour.
    ax.add_patch(Rectangle((-0.5, -0.5), npix, npix, facecolor=OUTSIDE_COLOR, edgecolor="none", hatch="..",
                           hatchcolor=sv.MUTED, linewidth=0, zorder=0))
    return fig, ax


def _mask_cells(ax, X: np.ndarray, Y: np.ndarray, mask: np.ndarray, hatched: bool) -> None:
    """Draw the pixels where ``mask`` is True as no-data cells (hatched in the composition)."""
    if not mask.any():
        return
    jj, ii = np.nonzero(mask)
    verts = np.stack([np.stack([X[jj, ii], Y[jj, ii]], -1), np.stack([X[jj, ii + 1], Y[jj, ii + 1]], -1),
                      np.stack([X[jj + 1, ii + 1], Y[jj + 1, ii + 1]], -1), np.stack([X[jj + 1, ii], Y[jj + 1, ii]], -1)],
                     axis=1)
    ax.add_collection(PolyCollection(verts, facecolors=MASK_COLOR, edgecolors="none", linewidths=0,
                                     hatch="////" if hatched else None, hatchcolor="white", antialiased=False,
                                     zorder=3))


def _finish(fig, ax, npix: int) -> bytes:
    ax.set_xlim(-0.5, npix - 0.5)
    ax.set_ylim(-0.5, npix - 0.5)
    buf = io.BytesIO()
    with mpl.rc_context({"hatch.linewidth": 1.0}):
        fig.savefig(buf, format="png", dpi=100, facecolor=OUTSIDE_COLOR)
    return buf.getvalue()


@render.serialized
def composite_png(comp: mb.Composite, npix: int = DISPLAY_NPIX) -> tuple[bytes, dict]:
    """PNG (npix x npix, no axes) of the composition in exact geometry, and its display info."""
    frame = frame_for(comp, npix)
    fig, ax = _axes(npix)
    for i, ps in enumerate(comp.patches):
        r, d = ps[0].corners_world()
        X, Y = frame.world_to_pixel_values(r, d)
        rgb = comp.rgb(i)
        ok = np.all(np.isfinite(rgb), axis=-1)
        rgba = np.zeros(rgb.shape[:2] + (4,))
        rgba[ok, :3] = np.clip(rgb[ok], 0.0, 1.0)
        rgba[ok, 3] = 1.0                                   # no-data cells stay transparent here
        ax.pcolormesh(X, Y, rgba, shading="flat", antialiased=False, edgecolors="none", linewidth=0, zorder=2)
        _mask_cells(ax, X, Y, ~ok, hatched=True)
    png = _finish(fig, ax, npix)
    half = comp.field_deg * sv.FRAME_MARGIN / 2 * 3600
    return png, {"half_arcsec": half, "npix": npix, "screen_arcsec_per_px": 2 * half / npix}


@render.serialized
def channel_panel_png(comp: mb.Composite, role: str, npix: int = PANEL_NPIX) -> bytes:
    """One channel of the composition in grey, with the composition's limits for that channel."""
    frame = frame_for(comp, npix)
    fig, ax = _axes(npix)
    cm = mpl.colormaps["gray"]
    for p in comp.maps[role].patches:
        r, d = p.corners_world()
        X, Y = frame.world_to_pixel_values(r, d)
        vals = comp.stretch.apply(role, np.where(p.valid, p.image, np.nan))
        ok = np.isfinite(vals)
        rgba = cm(np.clip(np.nan_to_num(vals), 0.0, 1.0))
        rgba[~ok] = to_rgba(MASK_COLOR)
        ax.pcolormesh(X, Y, rgba, shading="flat", antialiased=False, edgecolors="none", linewidth=0, zorder=2)
    return _finish(fig, ax, npix)


def pixel_table(comp: mb.Composite, npix: int = DISPLAY_NPIX) -> pd.DataFrame:
    """One row per native pixel in the frame: position and the ORIGINAL values of the three channels."""
    frame = frame_for(comp, npix)
    half = comp.field_deg * sv.FRAME_MARGIN / 2 * 3600
    parts = []
    for i, ps in enumerate(comp.patches):
        r, d = ps[0].centres_world()
        e, n = sv.offsets_arcsec(frame, r, d)
        keep = (np.abs(e) <= half) & (np.abs(n) <= half)
        k = np.sum([p.valid for p in ps], axis=0)[keep]
        cols = {"este": e[keep], "norte": n[keep], "ra": np.round(r[keep], 6), "dec": np.round(d[keep], 6)}
        for role, p in zip(mb.ROLES, ps):
            cols[role] = np.round(np.where(p.valid, p.image, np.nan)[keep], 4)
            cols[f"nhits_{role}"] = p.nhits[keep].astype(int)
        cols["cobertura"] = np.where(k == 3, "data in all 3 channels",
                                     np.where(k == 0, "no data", "data only in " + k.astype(str) + " canal(es)"))
        cols["tesela"] = int(ps[0].tile.ipix)
        parts.append(pd.DataFrame(cols))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def composite_chart(png: bytes, info: dict, pixels: pd.DataFrame, comp: mb.Composite, target=None,
                    size: int = 470):
    """Altair chart: the PNG anchored to its exact sky extent, the field circle, the target and
    invisible native-pixel points whose tooltip gives the original value of each channel."""
    import altair as alt

    R = info["half_arcsec"]
    # Square plot with the same fixed extent on both axes: one arcsecond has the same length
    # horizontally and vertically by construction. The frame never depends on the width the browser
    # measures when the chart is created: a vertical domain derived from ``height/width`` became
    # infinite (blank chart: no image, no circle, no vertical ticks) when the chart was built while
    # its column had no width, and it was not recomputed afterwards.
    xs = alt.Scale(domain=[-R, R], reverse=True, nice=False, zero=False)
    ys = alt.Scale(domain=[-R, R], nice=False, zero=False)
    tx, ty = "Offset to the east (″) · east to the left", "Offset to the north (″)"
    X, Y = alt.X("este:Q", scale=xs, title=tx), alt.Y("norte:Q", scale=ys, title=ty)
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    bg = alt.Chart(pd.DataFrame({"e1": [R], "e2": [-R], "n1": [-R], "n2": [R], "url": [uri]})).mark_image(
        aspect=False).encode(x=alt.X("e1:Q", scale=xs, title=tx), x2="e2:Q",
                             y=alt.Y("n1:Q", scale=ys, title=ty), y2="n2:Q", url="url:N")
    circle = sv._circle(0.0, 0.0, comp.field_deg / 2 * 3600, "field of view")
    # Overlays in white over a dark halo: legible on any colour of the composition.
    halo = alt.Chart(circle).mark_line(strokeWidth=3.2, clip=True, color="#14181f", opacity=0.55).encode(
        x=X, y=Y, order="orden:Q")
    lines = halo + alt.Chart(circle).mark_line(strokeWidth=1.4, clip=True, color="#ffffff",
                                                strokeDash=[5, 4]).encode(x=X, y=Y, order="orden:Q")
    ch = comp.channels
    tip = [alt.Tooltip("ra:Q", title="RA (°)", format=".5f"), alt.Tooltip("dec:Q", title="Dec (°)", format="+.5f")]
    for r in mb.ROLES:
        tip.append(alt.Tooltip(f"{r}:Q", title=f"{r} · canal {ch[r].number} · {ch[r].wavelength_um:.3f} µm (MJy/sr)",
                               format=".4g"))
    tip += [alt.Tooltip("cobertura:N"), alt.Tooltip("tesela:Q", title="HEALPix tile")]
    px = max(4.0, size * comp.alignment["pixel_arcsec"] / (2 * R))
    pts = alt.Chart(pixels).mark_square(size=px * px, opacity=0.001).encode(x=X, y=Y, tooltip=tip)
    layers = [bg, lines, pts]
    if target is not None:
        e, n = sv.offsets_arcsec(frame_for(comp), *target)
        mark = alt.Chart(pd.DataFrame([{"este": float(e), "norte": float(n), "m": "objetivo"}]))
        layers.append(mark.mark_point(shape="cross", size=170, strokeWidth=4, filled=False, color="#14181f",
                                      opacity=0.6).encode(x=X, y=Y))
        layers.append(mark.mark_point(shape="cross", size=140, strokeWidth=1.8, filled=False, color="#ffffff").encode(
            x=X, y=Y, tooltip=[alt.Tooltip("m:N", title="marca")]))
    return alt.layer(*layers).properties(width=size, height=size)


def assignment_table(comp: mb.Composite) -> pd.DataFrame:
    """Per role: channel, real wavelength and band, display limits and coverage."""
    rows = []
    for r in mb.ROLES:
        c = comp.channels[r]
        rows.append({"color": f"{r} ({mb.ROLE_NAMES[r]})", "canal": c.number, "λ central (µm)": round(c.wavelength_um, 4),
                     "width (µm)": round(c.bandwidth_um, 4),
                     "interval (µm)": f"{c.wl_min_um:.3f}–{c.wl_max_um:.3f}", "detector": f"D{c.detector}·{c.subchannel}",
                     "pixels with data": comp.coverage["con_datos"][r],
                     "scale (MJy/sr)": f"{comp.stretch.vmin[r]:.4g} – {comp.stretch.vmax[r]:.4g}"})
    return pd.DataFrame(rows)
