"""Display of the SPHEREx DR1 spectral cube. Visualization only: cube values are never altered.

* Channel maps are drawn in exact geometry: every native mosaic pixel (HEALPix, 12.9 arcsec)
  is a quadrilateral at its WCS position in a north-up / east-left TAN display frame, with its
  original value (no resampling, no smoothing). Pixels without data (NaN, NHITS = 0) are drawn
  in MASK_COLOR; sky outside the pixels read for the field is drawn in OUTSIDE_COLOR.
* Each channel has its own display stretch (percentiles 1-99.5 of the valid field pixels,
  asinh); the colour bar gives the real MJy/sr values. Brightness must be compared between
  channels with the spectrum, not with the images.
* The spectrum shows one point per real channel, horizontal bars = channel band
  (WL_MIN-WL_MAX, not an uncertainty), no connecting curve, and the channels without a value
  as marks on the axis. Nothing is interpolated.
"""

from __future__ import annotations

import base64
import io

import numpy as np
import pandas as pd
from astropy.visualization import AsinhStretch, ImageNormalize, LinearStretch
from matplotlib.figure import Figure

from . import render
from . import spectral_cube as sc

FRAME_MARGIN = 1.10          # display frame = 1.1 x field diameter
DISPLAY_NPIX = 540
MASK_COLOR = render.MASK_COLOR               # no data in this channel (NaN, NHITS = 0)
OUTSIDE_COLOR = "#eef1f5"                    # not read: outside the field's tile boxes
SERIES = "#2a78d6"                           # one series: the spectrum
INK, INK_2, MUTED = "#14181f", "#4a5463", "#9aa4b2"
BAND_FILL = "#f3f5f8"


def frame_for(cmap: sc.ChannelMap, npix: int = DISPLAY_NPIX):
    return sc.display_wcs(cmap.ra, cmap.dec, cmap.field_deg * FRAME_MARGIN, npix)


def field_norm(cmap: sc.ChannelMap, layer: str = "image") -> ImageNormalize:
    vals = []
    for p in cmap.patches:
        v = p.valid & cmap.in_field(p)
        vals.append((p.image if layer == "image" else p.nhits.astype(float))[v])
    allv = np.concatenate(vals) if vals else np.array([])
    if layer == "nhits":
        hi = float(allv.max()) if allv.size else 1.0
        return ImageNormalize(vmin=0.0, vmax=max(hi, 1.0), stretch=LinearStretch(), clip=True)
    if not allv.size:
        return ImageNormalize(vmin=0.0, vmax=1.0, stretch=AsinhStretch(0.1), clip=True)
    lo, hi = np.percentile(allv, [1.0, 99.5])
    if hi <= lo:
        hi = lo + 1e-6
    return ImageNormalize(vmin=float(lo), vmax=float(hi), stretch=AsinhStretch(0.1), clip=True)


def _rgba(data: np.ndarray, norm: ImageNormalize, cmap_name: str) -> np.ndarray:
    import matplotlib as mpl
    from matplotlib.colors import to_rgba

    finite = np.isfinite(data)
    scaled = np.zeros(data.shape, float)
    scaled[finite] = np.asarray(norm(data[finite]), float)
    rgba = mpl.colormaps[cmap_name](np.clip(scaled, 0.0, 1.0))
    rgba[~finite] = to_rgba(MASK_COLOR)
    return rgba


def layer_values(p: sc.Patch, layer: str) -> np.ndarray:
    """IMAGE (MJy/sr) or NHITS, with no-data pixels as NaN (a new array; the patch is unchanged)."""
    if layer == "nhits":
        return np.where(p.nhits > 0, p.nhits.astype(float), np.nan)
    return np.where(p.valid, p.image, np.nan)


@render.serialized
def field_png(cmap: sc.ChannelMap, layer: str = "image", npix: int = DISPLAY_NPIX) -> tuple[bytes, dict]:
    """PNG (npix x npix, no axes) of the channel map in exact geometry, and the display scale."""
    frame = frame_for(cmap, npix)
    norm = field_norm(cmap, layer)
    cm_name = "gray" if layer == "image" else "viridis"
    fig = Figure(figsize=(npix / 100, npix / 100), dpi=100, facecolor=OUTSIDE_COLOR)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    ax.set_facecolor(OUTSIDE_COLOR)
    for p in cmap.patches:
        r, d = p.corners_world()
        X, Y = frame.world_to_pixel_values(r, d)
        ax.pcolormesh(X, Y, _rgba(layer_values(p, layer), norm, cm_name), shading="flat",
                      antialiased=False, edgecolors="none", linewidth=0)
    ax.set_xlim(-0.5, npix - 0.5)
    ax.set_ylim(-0.5, npix - 0.5)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, facecolor=OUTSIDE_COLOR)
    half = cmap.field_deg * FRAME_MARGIN / 2 * 3600
    screen = cmap.field_deg * FRAME_MARGIN * 3600 / npix
    return buf.getvalue(), {"vmin": float(norm.vmin), "vmax": float(norm.vmax), "layer": layer,
                            "stretch": "asinh" if layer == "image" else "lineal", "cmap": cm_name,
                            "half_arcsec": half, "screen_arcsec_per_px": screen, "npix": npix}


@render.serialized
def colorbar_png(info: dict, width_in: float = 5.4) -> bytes:
    from matplotlib.cm import ScalarMappable
    import matplotlib as mpl

    norm = ImageNormalize(vmin=info["vmin"], vmax=info["vmax"],
                          stretch=AsinhStretch(0.1) if info["stretch"] == "asinh" else LinearStretch(), clip=True)
    fig = Figure(figsize=(width_in, 0.62), dpi=130, facecolor="white")
    ax = fig.add_axes([0.04, 0.55, 0.92, 0.3])
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=mpl.colormaps[info["cmap"]]), cax=ax, orientation="horizontal")
    # Ticks evenly spaced in display (stretched) space, so asinh does not crowd them at one end.
    cb.set_ticks(np.asarray(norm.inverse(np.linspace(0.0, 1.0, 5)), float))
    cb.ax.xaxis.set_major_formatter(mpl.ticker.FormatStrFormatter("%.3g"))
    cb.ax.tick_params(labelsize=7, colors=INK)
    cb.set_label("MJy/sr (IMAGE, zodiacal ya restado)" if info["layer"] == "image"
                 else "NHITS: píxeles de entrada promediados", fontsize=7, color=INK)
    buf = io.BytesIO()
    with render.RENDER_LOCK:
        fig.savefig(buf, format="png", dpi=130, facecolor="white")
    return buf.getvalue()


def offsets_arcsec(frame, ra, dec) -> tuple[np.ndarray, np.ndarray]:
    """(east, north) offsets in arcsec of sky positions in a display frame (east positive)."""
    x, y = frame.world_to_pixel_values(ra, dec)
    n = frame.array_shape[0]
    c = (n - 1) / 2
    s = abs(frame.wcs.cdelt[0]) * 3600
    return -(np.asarray(x) - c) * s, (np.asarray(y) - c) * s


def pixel_table(cmap: sc.ChannelMap, npix: int = DISPLAY_NPIX) -> pd.DataFrame:
    """One row per native pixel shown in the frame: offsets, RA/Dec and its stored values."""
    frame = frame_for(cmap, npix)
    half = cmap.field_deg * FRAME_MARGIN / 2 * 3600
    parts = []
    for p in cmap.patches:
        r, d = p.centres_world()
        e, n = offsets_arcsec(frame, r, d)
        keep = (np.abs(e) <= half) & (np.abs(n) <= half)
        ny, nx = p.image.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        fl = p.flags[keep]
        names = {int(v): ("|".join(sc.flag_names(p.tile, int(v))) or "—") for v in np.unique(fl)}
        val = np.where(p.valid, p.image, np.nan)[keep]
        parts.append(pd.DataFrame({
            "este": e[keep], "norte": n[keep], "ra": np.round(r[keep], 6), "dec": np.round(d[keep], 6),
            "valor": np.round(val, 4), "nhits": p.nhits[keep].astype(int),
            "flags": [names[int(v)] for v in fl], "tesela": int(p.tile.ipix),
            "x": (xx + p.x0)[keep], "y": (yy + p.y0)[keep]}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def _circle(e0: float, n0: float, r_arcsec: float, label: str, k: int = 120) -> pd.DataFrame:
    t = np.linspace(0, 2 * np.pi, k)
    return pd.DataFrame({"este": e0 + r_arcsec * np.cos(t), "norte": n0 + r_arcsec * np.sin(t), "orden": np.arange(k),
                         "curva": label})


def field_chart(png: bytes, info: dict, pixels: pd.DataFrame, cmap: sc.ChannelMap, target=None, pick=None,
                aperture: sc.Aperture | None = None, pixel_arcsec: float = 12.9, size: int = 470):
    """Altair chart: the PNG as background, invisible native-pixel points for hover/click,
    the field circle, the target (+) and the extraction position with its aperture/annulus."""
    import altair as alt

    R = info["half_arcsec"]
    xs = alt.Scale(domain=[-R, R], reverse=True, nice=False, zero=False)
    ys = alt.Scale(domain=[-R, R], nice=False, zero=False)
    tx, ty = "Desplazamiento al este (″) · este a la izquierda", "Desplazamiento al norte (″)"
    X = alt.X("este:Q", scale=xs, title=tx)
    Y = alt.Y("norte:Q", scale=ys, title=ty)
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    # The PNG is anchored to data coordinates (its exact extent, +-R arcsec), never to screen
    # pixels, so it stays registered with the axes and the overlays whatever the chart size.
    bg = alt.Chart(pd.DataFrame({"e1": [R], "e2": [-R], "n1": [-R], "n2": [R], "url": [uri]})).mark_image(
        aspect=False).encode(x=alt.X("e1:Q", scale=xs, title=tx), x2="e2:Q",
                             y=alt.Y("n1:Q", scale=ys, title=ty), y2="n2:Q", url="url:N")
    frame = frame_for(cmap)
    curves = [_circle(0.0, 0.0, cmap.field_deg / 2 * 3600, "campo de visión")]
    if pick is not None and aperture is not None:
        e0, n0 = offsets_arcsec(frame, *pick)
        e0, n0 = float(e0), float(n0)
        curves += [_circle(e0, n0, aperture.r_ap * pixel_arcsec, "apertura"),
                   _circle(e0, n0, aperture.r_in * pixel_arcsec, "anillo de fondo"),
                   _circle(e0, n0, aperture.r_out * pixel_arcsec, "anillo de fondo (ext.)")]
    cdf = pd.concat(curves, ignore_index=True)
    lines = alt.Chart(cdf).mark_line(strokeWidth=1.4, clip=True).encode(
        x=X, y=Y, order="orden:Q", detail="curva:N",
        color=alt.Color("curva:N", scale=alt.Scale(
            domain=["campo de visión", "apertura", "anillo de fondo", "anillo de fondo (ext.)"],
            range=["#1f5fbf", "#eda100", "#eb6834", "#eb6834"]), legend=None),
        strokeDash=alt.condition(alt.datum.curva == "campo de visión", alt.value([5, 4]), alt.value([1, 0])))
    sel = alt.selection_point(name="pick", on="click", nearest=True, fields=["ra", "dec"], empty=False)
    px = max(4.0, size * pixel_arcsec / (2 * R))
    pts = alt.Chart(pixels).mark_square(size=px * px, opacity=0.001).encode(
        x=X, y=Y,
        tooltip=[alt.Tooltip("ra:Q", title="RA (°)", format=".5f"), alt.Tooltip("dec:Q", title="Dec (°)", format="+.5f"),
                 alt.Tooltip("valor:Q", title="valor (MJy/sr)", format=".4g"), alt.Tooltip("nhits:Q", title="NHITS"),
                 alt.Tooltip("flags:N", title="FLAGS"), alt.Tooltip("tesela:Q", title="tesela HEALPix")]
    ).add_params(sel)
    marks = []
    if target is not None:
        e, n = offsets_arcsec(frame, *target)
        marks.append({"este": float(e), "norte": float(n), "m": "objetivo"})
    if pick is not None:
        e, n = offsets_arcsec(frame, *pick)
        marks.append({"este": float(e), "norte": float(n), "m": "posición del espectro"})
    layers = [bg, lines, pts]
    if marks:
        layers.append(alt.Chart(pd.DataFrame(marks)).mark_point(size=140, strokeWidth=2, filled=False).encode(
            x=X, y=Y, shape=alt.Shape("m:N", scale=alt.Scale(domain=["objetivo", "posición del espectro"],
                                                             range=["cross", "diamond"]), legend=None),
            color=alt.Color("m:N", scale=alt.Scale(domain=["objetivo", "posición del espectro"],
                                                   range=["#1f5fbf", "#eda100"]), legend=None),
            tooltip=[alt.Tooltip("m:N", title="marca")]))
    return alt.layer(*layers).properties(width=size, height=size,
                                         autosize=alt.AutoSizeParams(type="pad", contains="content"))


QUANTITIES = {
    "flux": ("flujo_mjy", "Flujo en apertura (mJy)"),
    "pixel": ("pixel_mjysr", "Brillo del píxel (MJy/sr)"),
}


def spectrum_chart(spec: sc.Spectrum, quantity: str = "flux", selected_channel: int | None = None,
                   width: int = 760, height: int = 320):
    """One point per real channel; no line, no smoothing; channels without a value marked on the axis."""
    import altair as alt

    col, title = QUANTITIES[quantity]
    df = spec.table()
    df["valor"] = df[col]
    df["contorno"] = np.where(df["precaucion"], "OVERFLOW/OUTLIER en la apertura", "sin precaución")
    ok = df[df["valor"].notna()].copy()
    missing = df[df["valor"].isna()].copy()
    if quantity == "pixel":
        missing["estado"] = np.where(missing["status"] == "blank", missing["estado"], "píxel sin datos (NHITS = 0)")
    xsc = alt.Scale(domain=[0.70, 5.05], nice=False, zero=False)
    X = alt.X("lambda_um:Q", scale=xsc, title="Longitud de onda (µm)")
    bands = pd.DataFrame([{"d": f"D{d}", "a": float(df[df.detector == d].lambda_min_um.min()),
                           "b": float(df[df.detector == d].lambda_max_um.max()), "par": d % 2} for d in range(1, 7)])
    band = alt.Chart(bands).mark_rect(opacity=1.0).encode(
        x=alt.X("a:Q", scale=xsc), x2="b:Q",
        color=alt.Color("par:N", scale=alt.Scale(domain=[0, 1], range=["#ffffff", BAND_FILL]), legend=None))
    band_lbl = alt.Chart(bands.assign(m=lambda t: (t.a + t.b) / 2)).mark_text(
        color=INK_2, fontSize=11, baseline="top").encode(x=alt.X("m:Q", scale=xsc), y=alt.value(4), text="d:N")
    zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color=MUTED, strokeDash=[3, 3]).encode(y="y:Q")
    tip = [alt.Tooltip("canal:Q"), alt.Tooltip("lambda_um:Q", title="λ (µm)", format=".3f"),
           alt.Tooltip("detector:Q"), alt.Tooltip("subcanal:Q"),
           alt.Tooltip("valor:Q", title=title, format=".4g"),
           alt.Tooltip("fondo_mjysr:Q", title="fondo del anillo (MJy/sr)", format=".4g"),
           alt.Tooltip("nhits_min_apertura:Q", title="NHITS mín. en apertura"),
           alt.Tooltip("flags_apertura:N", title="FLAGS en apertura"), alt.Tooltip("estado:N")]
    Y = alt.Y("valor:Q", title=title, scale=alt.Scale(zero=False, nice=True))
    bars = alt.Chart(ok).mark_rule(color=SERIES, strokeWidth=1.2, opacity=0.6).encode(
        x=alt.X("lambda_min_um:Q", scale=xsc), x2="lambda_max_um:Q", y=Y)
    pts = alt.Chart(ok).mark_point(size=64, strokeWidth=1.6).encode(
        x=X, y=Y, color=alt.value(SERIES),
        fill=alt.Fill("contorno:N", scale=alt.Scale(domain=["sin precaución", "OVERFLOW/OUTLIER en la apertura"],
                                                    range=[SERIES, "#ffffff"]),
                      legend=alt.Legend(title=None, orient="bottom", labelLimit=400)),
        tooltip=tip)
    miss = alt.Chart(missing).mark_tick(color=MASK_COLOR, thickness=2, size=14).encode(
        x=X, y=alt.value(height - 7),
        tooltip=[alt.Tooltip("canal:Q"), alt.Tooltip("lambda_um:Q", title="λ (µm)", format=".3f"),
                 alt.Tooltip("estado:N")])
    layers = [band, band_lbl, zero, bars, pts, miss]
    if selected_channel is not None:
        lam = float(df.loc[df.canal == selected_channel, "lambda_um"].iloc[0])
        layers.insert(3, alt.Chart(pd.DataFrame({"x": [lam]})).mark_rule(color=INK_2, strokeDash=[2, 2]).encode(
            x=alt.X("x:Q", scale=xsc)))
    return alt.layer(*layers).properties(
        width=width, height=height, autosize=alt.AutoSizeParams(type="pad", contains="content")
    ).resolve_scale(color="independent")


@render.serialized
def channel_figure(cmap: sc.ChannelMap, layer: str = "image"):
    """Static matplotlib version with an RA/Dec grid (exact geometry), e.g. for reports and tests."""
    npix = 400
    frame = frame_for(cmap, npix)
    norm = field_norm(cmap, layer)
    fig = Figure(figsize=(5.4, 5.6), dpi=120, facecolor="white")
    ax = fig.add_subplot(1, 1, 1, projection=frame)
    ax.set_facecolor(OUTSIDE_COLOR)
    for p in cmap.patches:
        r, d = p.corners_world()
        X, Y = frame.world_to_pixel_values(r, d)
        ax.pcolormesh(X, Y, _rgba(layer_values(p, layer), norm, "gray" if layer == "image" else "viridis"),
                      shading="flat", antialiased=False, edgecolors="none", linewidth=0)
    ax.set_xlim(-0.5, npix - 0.5)
    ax.set_ylim(-0.5, npix - 0.5)
    ax.coords.grid(True, color=render.GRID, ls=":", lw=0.6)
    ax.coords[0].set_axislabel("RA (ICRS)")
    ax.coords[1].set_axislabel("Dec (ICRS)")
    c = cmap.channel
    ax.set_title(f"{c.label}", fontsize=9, loc="left")
    return fig
