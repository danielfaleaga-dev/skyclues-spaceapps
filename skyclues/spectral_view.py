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
SERIES = "#1f1f1f"                           # one series: the spectrum
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
def colorbar_png(info: dict, width_in: float = 3.0) -> bytes:
    from matplotlib.cm import ScalarMappable
    import matplotlib as mpl

    norm = ImageNormalize(vmin=info["vmin"], vmax=info["vmax"],
                          stretch=AsinhStretch(0.1) if info["stretch"] == "asinh" else LinearStretch(), clip=True)
    fig = Figure(figsize=(width_in, 0.88), dpi=130, facecolor="white")
    ax = fig.add_axes([0.08, 0.65, 0.84, 0.23])
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=mpl.colormaps[info["cmap"]]), cax=ax, orientation="horizontal")
    # Ticks evenly spaced in display (stretched) space, so asinh does not crowd them at one end.
    cb.set_ticks(np.asarray(norm.inverse(np.linspace(0.0, 1.0, 5)), float))
    cb.ax.xaxis.set_major_formatter(mpl.ticker.FormatStrFormatter("%.3g"))
    cb.ax.tick_params(labelsize=9, colors=INK)
    cb.set_label("MJy/sr (IMAGE, zodiacal light already subtracted)" if info["layer"] == "image"
                 else "NHITS: input pixels averaged", fontsize=8, color=INK)
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
                aperture: sc.Aperture | None = None, pixel_arcsec: float = 12.9, size: int = 470, pick_b=None):
    """Altair chart: the PNG as background, invisible native-pixel points for hover/click,
    the field circle, the target (+) and the extraction position with its aperture/annulus.

    With ``pick_b`` (a second position to compare) both positions are drawn in the colour of their
    spectrum (A, B), labelled, each with the same aperture and annulus.
    """
    import altair as alt

    if pick_b is not None and pick is not None and aperture is not None:
        return _field_chart_ab(png, info, pixels, cmap, target, pick, pick_b, aperture, pixel_arcsec, size)

    R = info["half_arcsec"]
    xs = alt.Scale(domain=[-R, R], reverse=True, nice=False, zero=False)
    # Square plot with the same fixed extent on both axes: one angular unit has the same length
    # horizontally and vertically by construction. The frame never depends on the width the browser
    # measures: a vertical domain derived from ``height/width`` became infinite (blank chart: no
    # image, no circle, no vertical ticks) when the chart was built while its column had no width.
    ys = alt.Scale(domain=[-R, R], nice=False, zero=False)
    tx, ty = "Offset to the east (″) · east to the left", "Offset to the north (″)"
    X = alt.X("este:Q", scale=xs, title=tx)
    Y = alt.Y("norte:Q", scale=ys, title=ty)
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    # The PNG is anchored to data coordinates (its exact extent, +-R arcsec), never to screen
    # pixels, so it stays registered with the axes and the overlays whatever the chart size.
    bg = alt.Chart(pd.DataFrame({"e1": [R], "e2": [-R], "n1": [-R], "n2": [R], "url": [uri]})).mark_image(
        aspect=False).encode(x=alt.X("e1:Q", scale=xs, title=tx), x2="e2:Q",
                             y=alt.Y("n1:Q", scale=ys, title=ty), y2="n2:Q", url="url:N")
    frame = frame_for(cmap)
    curves = [_circle(0.0, 0.0, cmap.field_deg / 2 * 3600, "field of view")]
    if pick is not None and aperture is not None:
        e0, n0 = offsets_arcsec(frame, *pick)
        e0, n0 = float(e0), float(n0)
        curves += [_circle(e0, n0, aperture.r_ap * pixel_arcsec, "apertura"),
                   _circle(e0, n0, aperture.r_in * pixel_arcsec, "background annulus"),
                   _circle(e0, n0, aperture.r_out * pixel_arcsec, "background annulus (ext.)")]
    cdf = pd.concat(curves, ignore_index=True)
    lines = alt.Chart(cdf).mark_line(strokeWidth=1.4, clip=True).encode(
        x=X, y=Y, order="orden:Q", detail="curva:N",
        color=alt.Color("curva:N", scale=alt.Scale(
            domain=["field of view", "apertura", "background annulus", "background annulus (ext.)"],
            range=["#1f5fbf", "#eda100", "#eb6834", "#eb6834"]), legend=None),
        strokeDash=alt.condition(alt.datum.curva == "field of view", alt.value([5, 4]), alt.value([1, 0])))
    sel = alt.selection_point(name="pick", on="click", nearest=True, fields=["ra", "dec"], empty=False)
    px = max(4.0, size * pixel_arcsec / (2 * R))
    pts = alt.Chart(pixels).mark_square(size=px * px, opacity=0.001).encode(
        x=X, y=Y,
        tooltip=[alt.Tooltip("ra:Q", title="RA (°)", format=".5f"), alt.Tooltip("dec:Q", title="Dec (°)", format="+.5f"),
                 alt.Tooltip("valor:Q", title="value (MJy/sr)", format=".4g"), alt.Tooltip("nhits:Q", title="NHITS"),
                 alt.Tooltip("flags:N", title="FLAGS"), alt.Tooltip("tesela:Q", title="HEALPix tile")]
    ).add_params(sel)
    marks = []
    if target is not None:
        e, n = offsets_arcsec(frame, *target)
        marks.append({"este": float(e), "norte": float(n), "m": "objetivo"})
    if pick is not None:
        e, n = offsets_arcsec(frame, *pick)
        marks.append({"este": float(e), "norte": float(n), "m": "spectrum position"})
    layers = [bg, lines, pts]
    if marks:
        layers.append(alt.Chart(pd.DataFrame(marks)).mark_point(size=140, strokeWidth=2, filled=False).encode(
            x=X, y=Y, shape=alt.Shape("m:N", scale=alt.Scale(domain=["objetivo", "spectrum position"],
                                                             range=["cross", "diamond"]), legend=None),
            color=alt.Color("m:N", scale=alt.Scale(domain=["objetivo", "spectrum position"],
                                                   range=["#1f5fbf", "#eda100"]), legend=None),
            tooltip=[alt.Tooltip("m:N", title="mark")]))
    return alt.layer(*layers).properties(width=size, height=size)


def _field_chart_ab(png, info, pixels, cmap, target, pick, pick_b, aperture, pixel_arcsec, size):
    """Field with the two compared positions. Same geometry and click behaviour as ``field_chart``."""
    import altair as alt

    R = info["half_arcsec"]
    xs = alt.Scale(domain=[-R, R], reverse=True, nice=False, zero=False)
    ys = alt.Scale(domain=[-R, R], nice=False, zero=False)       # fixed square frame, see ``field_chart``
    tx, ty = "Offset to the east (″) · east to the left", "Offset to the north (″)"
    X = alt.X("este:Q", scale=xs, title=tx)
    Y = alt.Y("norte:Q", scale=ys, title=ty)
    uri = "data:image/png;base64," + base64.b64encode(png).decode()
    bg = alt.Chart(pd.DataFrame({"e1": [R], "e2": [-R], "n1": [-R], "n2": [R], "url": [uri]})).mark_image(
        aspect=False).encode(x=alt.X("e1:Q", scale=xs, title=tx), x2="e2:Q",
                             y=alt.Y("n1:Q", scale=ys, title=ty), y2="n2:Q", url="url:N")
    frame = frame_for(cmap)
    curves = [_circle(0.0, 0.0, cmap.field_deg / 2 * 3600, "field of view").assign(trazo="campo")]
    marks = []
    if target is not None:
        e, n = offsets_arcsec(frame, *target)
        marks.append({"este": float(e), "norte": float(n), "m": "objetivo", "letra": "", "nota": "target"})
    for letter, pos, role in (("A", pick, "spectrum position"), ("B", pick_b, "comparison point")):
        e0, n0 = (float(v) for v in offsets_arcsec(frame, *pos))
        curves += [_circle(e0, n0, aperture.r_ap * pixel_arcsec, f"aperture {letter}").assign(trazo="continuo"),
                   _circle(e0, n0, aperture.r_in * pixel_arcsec, f"ring {letter}").assign(trazo="anillo"),
                   _circle(e0, n0, aperture.r_out * pixel_arcsec, f"ring {letter} (ext.)").assign(trazo="anillo")]
        marks.append({"este": e0, "norte": n0, "m": letter, "letra": letter, "nota": f"{letter} · {role}"})
    names = ["field of view"] + [f"{k} {s}" for s in "AB" for k in ("aperture", "ring")] + [
        f"ring {s} (ext.)" for s in "AB"]
    colour = {"field of view": "#1f5fbf", **{n: (SERIES if " A" in n else SERIES_B) for n in names[1:]}}
    lines = alt.Chart(pd.concat(curves, ignore_index=True)).mark_line(strokeWidth=1.5, clip=True).encode(
        x=X, y=Y, order="orden:Q", detail="curva:N",
        color=alt.Color("curva:N", scale=alt.Scale(domain=names, range=[colour[n] for n in names]), legend=None),
        strokeDash=alt.StrokeDash("trazo:N", scale=alt.Scale(domain=["continuo", "anillo", "campo"],
                                                              range=[[1, 0], [3, 3], [5, 4]]), legend=None))
    sel = alt.selection_point(name="pick", on="click", nearest=True, fields=["ra", "dec"], empty=False)
    px = max(4.0, size * pixel_arcsec / (2 * R))
    pts = alt.Chart(pixels).mark_square(size=px * px, opacity=0.001).encode(
        x=X, y=Y,
        tooltip=[alt.Tooltip("ra:Q", title="RA (°)", format=".5f"), alt.Tooltip("dec:Q", title="Dec (°)", format="+.5f"),
                 alt.Tooltip("valor:Q", title="value (MJy/sr)", format=".4g"), alt.Tooltip("nhits:Q", title="NHITS"),
                 alt.Tooltip("flags:N", title="FLAGS"), alt.Tooltip("tesela:Q", title="HEALPix tile")]
    ).add_params(sel)
    mdf = pd.DataFrame(marks)
    # White under-stroke: a dark marker (A is drawn in the ink of its curve) stays visible on any sky.
    under = alt.Chart(mdf).mark_point(size=150, strokeWidth=4.6, filled=False, color="#ffffff", opacity=0.9).encode(
        x=X, y=Y, shape=alt.Shape("m:N", scale=alt.Scale(domain=["objetivo", "A", "B"],
                                                         range=["cross", "diamond", "square"]), legend=None))
    symbols = alt.Chart(mdf).mark_point(size=150, strokeWidth=2.2, filled=False).encode(
        x=X, y=Y, shape=alt.Shape("m:N", scale=alt.Scale(domain=["objetivo", "A", "B"],
                                                         range=["cross", "diamond", "square"]), legend=None),
        color=alt.Color("m:N", scale=alt.Scale(domain=["objetivo", "A", "B"],
                                               range=["#1f5fbf", SERIES, SERIES_B]), legend=None),
        tooltip=[alt.Tooltip("nota:N", title="mark")])
    letters = mdf[mdf.letra != ""]
    # Identity is never colour alone: each position carries its letter (ink on a white halo).
    halo = alt.Chart(letters).mark_text(dx=14, dy=-13, fontSize=15, fontWeight="bold", stroke="#ffffff",
                                        strokeWidth=4, strokeJoin="round").encode(x=X, y=Y, text="letra:N")
    text = alt.Chart(letters).mark_text(dx=14, dy=-13, fontSize=15, fontWeight="bold", color=INK).encode(
        x=X, y=Y, text="letra:N")
    return alt.layer(bg, lines, pts, under, symbols, halo, text).properties(width=size, height=size)


QUANTITIES = {
    "flux": ("flujo_mjy", "Aperture flux (mJy)"),
    "pixel": ("pixel_mjysr", "Pixel brightness (MJy/sr)"),
}
SERIES_B = "#c06a2b"                         # second spectrum (comparison point B)
FOCUS = "#c4411c"                            # selection accent of the interface
CAUTION = "OVERFLOW/OUTLIER in the aperture"
Y_AXIS_EXTENT = 62                           # same left margin in the spectrum and in the A−B / A/B panel
X_DOMAIN = [0.70, 5.05]
GLYPHS = {("pico", True): "▼", ("pico", False): "▽", ("valle", True): "▲", ("valle", False): "△"}
#: Display words for the analyser's internal kind/width values (the values stay as they are: they are contracts).
KIND_TEXT = {"pico": "peak", "valle": "valley"}
WIDTH_TEXT = {"estrecha": "narrow", "amplia": "broad"}

#: English headers shown for the raw data columns of the spectrum tables. The columns themselves (and the CSV/JSON
#: downloads) keep their identifiers: they are contracts. Only the displayed header changes.
COLUMN_LABELS = {
    "canal": "Channel", "lambda_um": "λ (µm)", "lambda_min_um": "λ min (µm)", "lambda_max_um": "λ max (µm)",
    "detector": "Detector", "subcanal": "Subchannel", "estado": "Status", "flujo_mjy": "Flux (mJy)",
    "fondo_mjysr": "Background (MJy/sr)", "fondo_sigma_mjysr": "Background scatter (MJy/sr)", "n_fondo": "Background pixels",
    "pixel_mjysr": "Pixel (MJy/sr)", "pixel_nhits": "Pixel NHITS", "nhits_min_apertura": "Min NHITS in aperture",
    "flags_apertura": "Aperture flags", "ap_pix_total": "Aperture pixels", "ap_pix_invalidos": "Invalid pixels",
    "ap_pix_nan": "NaN pixels", "ap_pix_nhits0": "NHITS = 0 pixels", "ap_bloom": "BLOOM pixels",
    "ap_overflow": "OVERFLOW pixels", "a": "A", "b": "B", "estado_a": "Status A", "estado_b": "Status B",
    "diferencia": "Difference A − B", "relacion": "Ratio A / B", "estado_relacion": "Ratio status", "precaucion": "Caution",
}


def column_config(df) -> dict:
    """``st.dataframe(..., column_config=...)`` with English headers for the known columns."""
    return {c: COLUMN_LABELS[c] for c in df.columns if c in COLUMN_LABELS}



def _series_frame(spec: sc.Spectrum, quantity: str, label: str) -> pd.DataFrame:
    df = spec.table()
    df["valor"] = df[QUANTITIES[quantity][0]]
    df["serie"] = label
    df["contorno"] = np.where(df["precaucion"], CAUTION, "no caution")
    if quantity == "pixel":
        df["estado"] = np.where(df["valor"].isna() & (df["status"] != "blank"), "pixel without data (NHITS = 0)",
                                df["estado"])
    return df


def _detector_bands(df: pd.DataFrame, xsc):
    import altair as alt

    bands = pd.DataFrame([{"d": f"D{d}", "a": float(df[df.detector == d].lambda_min_um.min()),
                           "b": float(df[df.detector == d].lambda_max_um.max()), "par": d % 2} for d in range(1, 7)])
    band = alt.Chart(bands).mark_rect(opacity=1.0).encode(
        x=alt.X("a:Q", scale=xsc), x2="b:Q",
        color=alt.Color("par:N", scale=alt.Scale(domain=[0, 1], range=["#ffffff", BAND_FILL]), legend=None))
    band_lbl = alt.Chart(bands.assign(m=lambda t: (t.a + t.b) / 2)).mark_text(
        color=INK_2, fontSize=11, baseline="top").encode(x=alt.X("m:Q", scale=xsc), y=alt.value(4), text="d:N")
    return band, band_lbl


def _focus_layer(focus, xsc):
    import altair as alt

    return alt.Chart(pd.DataFrame({"a": [float(focus[0])], "b": [float(focus[1])]})).mark_rect(
        color=FOCUS, opacity=0.12, stroke=FOCUS, strokeWidth=1, strokeOpacity=0.55).encode(
        x=alt.X("a:Q", scale=xsc), x2="b:Q")


def _reference_layers(refs: list[dict], xsc):
    """Documented reference positions: thin dashed rules behind the data, named only in the tooltip; the ones
    compatible with the examined feature in the selection accent, with one short label."""
    import altair as alt

    df = pd.DataFrame(refs)
    tip = [alt.Tooltip("nombre:N", title="reference"), alt.Tooltip("naturaleza:N", title="type"),
           alt.Tooltip("lambda_um:Q", title="λ expected (µm)", format=".3f"), alt.Tooltip("nota:N", title="note")]
    rule = alt.Chart(df).mark_rule(strokeDash=[1, 3], strokeWidth=1.4, strokeCap="round").encode(   # dotted: not the
                                                                                                   # dashed channel rule
        x=alt.X("lambda_um:Q", scale=xsc),
        color=alt.condition("datum.destacada", alt.value(FOCUS), alt.value(MUTED)),
        opacity=alt.condition("datum.destacada", alt.value(0.9), alt.value(0.6)), tooltip=tip)
    layers = [rule]
    lab = df[df["etiqueta"] != ""]
    if len(lab):
        layers.append(alt.Chart(lab).mark_text(align="left", dx=4, fontSize=11, baseline="top", color=FOCUS).encode(
            x=alt.X("lambda_um:Q", scale=xsc), y=alt.value(18), text="etiqueta:N", tooltip=tip))
    return layers


def spectrum_chart(spec: sc.Spectrum, quantity: str = "flux", selected_channel: int | None = None,
                   width: int = 760, height: int = 320, *, other: sc.Spectrum | None = None, features=None,
                   focus=None, interactive: bool = False, references=None):
    """One point per real channel; no line, no smoothing; channels without a value marked on the axis.

    Optional, all on the same axes: ``other`` = a second spectrum (B) to compare with ``spec`` (A);
    ``features`` = peaks and valleys to mark (``spectral_features.Feature``: solid glyph = quantifiable,
    hollow = visible); ``focus`` = (λ_min, λ_max) of the interval under inspection; ``interactive`` =
    click a point (selection "canal") or drag an interval (selection "intervalo"); ``references`` = documented
    reference positions to mark ({lambda_um, nombre, naturaleza, nota, destacada, etiqueta}).
    """
    import altair as alt

    title = QUANTITIES[quantity][1]
    df = _series_frame(spec, quantity, "A")
    frames = [df] + ([_series_frame(other, quantity, "B")] if other is not None else [])
    two = len(frames) == 2
    allrows = pd.concat(frames, ignore_index=True)
    ok = allrows[allrows["valor"].notna()].copy()
    if two:
        gone = allrows[allrows["valor"].isna()]
        missing = gone.groupby(["canal", "lambda_um"], as_index=False).agg(
            estado=("estado", lambda s: ""), serie=("serie", lambda s: " and ".join(sorted(s))))
        why = {(r.canal, r.serie): r.estado for r in gone.itertuples()}
        missing["estado"] = [" · ".join(f"{s}: {why[(c, s)]}" for s in ser.split(" and "))
                             for c, ser in zip(missing.canal, missing.serie)]
    else:
        missing = df[df["valor"].isna()].copy()
    xsc = alt.Scale(domain=X_DOMAIN, nice=False, zero=False)
    X = alt.X("lambda_um:Q", scale=xsc, title="Wavelength (µm)")
    band, band_lbl = _detector_bands(df, xsc)
    zero = alt.Chart(pd.DataFrame({"y": [0.0]})).mark_rule(color=MUTED, strokeDash=[3, 3]).encode(y="y:Q")
    tip = [alt.Tooltip("canal:Q", title="channel"), alt.Tooltip("lambda_um:Q", title="λ (µm)", format=".3f"),
           alt.Tooltip("detector:Q"), alt.Tooltip("subcanal:Q", title="subchannel"),
           alt.Tooltip("valor:Q", title=title, format=".4g"),
           alt.Tooltip("fondo_mjysr:Q", title="annulus background (MJy/sr)", format=".4g"),
           alt.Tooltip("nhits_min_apertura:Q", title="min. NHITS in aperture"),
           alt.Tooltip("flags_apertura:N", title="FLAGS in aperture"), alt.Tooltip("estado:N", title="status")]
    axis = alt.Axis(minExtent=Y_AXIS_EXTENT, maxExtent=Y_AXIS_EXTENT) if two else alt.Axis()
    Y = alt.Y("valor:Q", title=title, scale=alt.Scale(zero=False, nice=True), axis=axis)
    by_series = alt.Scale(domain=["A", "B"], range=[SERIES, SERIES_B])
    if two:
        ok["relleno"] = np.where(ok["contorno"] == CAUTION, CAUTION, ok["serie"])
        bars = alt.Chart(ok).mark_rule(strokeWidth=1.2, opacity=0.6).encode(
            x=alt.X("lambda_min_um:Q", scale=xsc), x2="lambda_max_um:Q", y=Y,
            color=alt.Color("serie:N", scale=by_series, legend=None))
        pts = alt.Chart(ok).mark_point(size=64, strokeWidth=1.6).encode(
            x=X, y=Y,
            color=alt.Color("serie:N", scale=by_series, legend=alt.Legend(title=None, orient="bottom")),
            shape=alt.Shape("serie:N", scale=alt.Scale(domain=["A", "B"], range=["circle", "square"]),
                            legend=alt.Legend(title=None, orient="bottom")),
            fill=alt.Fill("relleno:N", scale=alt.Scale(domain=["A", "B", CAUTION], range=[SERIES, SERIES_B, "#ffffff"]),
                          legend=alt.Legend(title=None, orient="bottom", values=[CAUTION], labelLimit=400,
                                            symbolStrokeColor=INK_2)),
            tooltip=[alt.Tooltip("serie:N", title="espectro")] + tip)
    else:
        bars = alt.Chart(ok).mark_rule(color=SERIES, strokeWidth=1.2, opacity=0.6).encode(
            x=alt.X("lambda_min_um:Q", scale=xsc), x2="lambda_max_um:Q", y=Y)
        pts = alt.Chart(ok).mark_point(size=64, strokeWidth=1.6).encode(
            x=X, y=Y, color=alt.value(SERIES),
            fill=alt.Fill("contorno:N", scale=alt.Scale(domain=["no caution", CAUTION], range=[SERIES, "#ffffff"]),
                          legend=alt.Legend(title=None, orient="bottom", labelLimit=400)),
            tooltip=tip)
    if interactive:
        pts = pts.add_params(
            alt.selection_point(name="canal", on="click", nearest=True, fields=["canal", "serie"], empty=False),
            alt.selection_interval(name="intervalo", encodings=["x"]))
    miss = alt.Chart(missing).mark_tick(color=MASK_COLOR, thickness=2, size=14).encode(
        x=X, y=alt.value(alt.ExprRef(expr="height - 7")),   # on the axis of the plot area, whatever the legend
        tooltip=[alt.Tooltip("canal:Q", title="channel"), alt.Tooltip("lambda_um:Q", title="λ (µm)", format=".3f"),
                 alt.Tooltip("estado:N", title="status")])
    layers = [band, band_lbl, zero]
    if focus is not None:
        layers.append(_focus_layer(focus, xsc))
    if references:
        layers += _reference_layers(references, xsc)
    if selected_channel is not None:
        lam = float(df.loc[df.canal == selected_channel, "lambda_um"].iloc[0])
        layers.append(alt.Chart(pd.DataFrame({"x": [lam]})).mark_rule(color=INK_2, strokeDash=[2, 2]).encode(
            x=alt.X("x:Q", scale=xsc)))
    layers += [bars, pts, miss]
    marks = [f for f in (features or []) if f.kind in ("pico", "valle") and f.value is not None]
    if marks:
        fdf = pd.DataFrame([{
            "lambda_um": f.lam, "valor": f.value, "serie": f.serie, "tipo": f.kind,
            "glifo": GLYPHS[(f.kind, f.klass == "cuantificable")],
            "nota": f"{KIND_TEXT.get(f.kind, f.kind).capitalize()} · {f.label.lower()}", "canal": f.canal, "contraste": f.contrast,
            "relativo": f.relative} for f in marks])
        ftip = [alt.Tooltip("nota:N", title="feature"), alt.Tooltip("serie:N", title="espectro"),
                alt.Tooltip("canal:Q", title="channel"), alt.Tooltip("lambda_um:Q", title="λ (µm)", format=".3f"),
                alt.Tooltip("contraste:Q", title="contrast relative to the surroundings", format=".4g"),
                alt.Tooltip("relativo:Q", title="relative contrast", format="+.1%")]
        for kind, dy in (("pico", -15), ("valle", 16)):
            part = fdf[fdf.tipo == kind]
            if len(part):
                layers.append(alt.Chart(part).mark_text(dy=dy, fontSize=13, baseline="middle").encode(
                    x=X, y=Y, text="glifo:N", tooltip=ftip,
                    color=alt.Color("serie:N", scale=by_series, legend=None) if two else alt.value(SERIES)))
    if two:
        ends = ok.sort_values("lambda_um").groupby("serie", as_index=False).last()
        layers.append(alt.Chart(ends).mark_text(dx=9, align="left", fontSize=12, fontWeight="bold", color=INK).encode(
            x=X, y=Y, text="serie:N"))
    chart = alt.layer(*layers).properties(
        width="container", height=height, autosize=alt.AutoSizeParams(type="fit", contains="padding"))
    if two:
        chart = chart.properties(padding={"left": 5, "right": 18, "top": 5, "bottom": 5})
    return chart.resolve_scale(color="independent", fill="independent", shape="independent")


def derived_chart(rows: list[dict], kind: str, unit: str, focus=None, selected_channel: int | None = None,
                  height: int = 170):
    """A − B (``kind`` = "diferencia") or A / B ("relacion") per channel, on the wavelength axis of the
    spectrum above. Channels where the operation is not defined are marked on the axis with the reason:
    pink = A or B has no value, grey = the ratio is outside its domain. Nothing is interpolated."""
    import altair as alt

    if kind not in ("diferencia", "relacion"):
        raise ValueError("kind must be 'difference' or 'ratio'")
    df = pd.DataFrame(rows)
    df["valor"] = df[kind]
    df["motivo"] = np.where(df["a"].isna() | df["b"].isna(),
                            "A: " + df["estado_a"] + " · B: " + df["estado_b"], df["estado_relacion"])
    df["contorno"] = np.where(df["precaucion"], CAUTION, "no caution")
    ok, gone = df[df["valor"].notna()], df[df["valor"].isna()]
    title = f"A − B ({unit})" if kind == "diferencia" else "A / B (dimensionless)"
    xsc = alt.Scale(domain=X_DOMAIN, nice=False, zero=False)
    X = alt.X("lambda_um:Q", scale=xsc, title="Wavelength (µm)")
    Y = alt.Y("valor:Q", title=title, scale=alt.Scale(zero=False, nice=True),
              axis=alt.Axis(minExtent=Y_AXIS_EXTENT, maxExtent=Y_AXIS_EXTENT))
    band, _ = _detector_bands(df, xsc)
    ref = alt.Chart(pd.DataFrame({"y": [0.0 if kind == "diferencia" else 1.0]})).mark_rule(
        color=MUTED, strokeDash=[3, 3]).encode(y="y:Q")
    layers = [band, ref]
    if focus is not None:
        layers.append(_focus_layer(focus, xsc))
    if selected_channel is not None:
        lam = float(df.loc[df.canal == selected_channel, "lambda_um"].iloc[0])
        layers.append(alt.Chart(pd.DataFrame({"x": [lam]})).mark_rule(color=INK_2, strokeDash=[2, 2]).encode(
            x=alt.X("x:Q", scale=xsc)))
    tip = [alt.Tooltip("canal:Q", title="channel"), alt.Tooltip("lambda_um:Q", title="λ (µm)", format=".3f"),
           alt.Tooltip("a:Q", title=f"A ({unit})", format=".4g"), alt.Tooltip("b:Q", title=f"B ({unit})", format=".4g"),
           alt.Tooltip("valor:Q", title=title, format=".4g"), alt.Tooltip("motivo:N", title="status")]
    layers.append(alt.Chart(ok).mark_rule(color=INK_2, strokeWidth=1.2, opacity=0.5).encode(
        x=alt.X("lambda_min_um:Q", scale=xsc), x2="lambda_max_um:Q", y=Y))
    layers.append(alt.Chart(ok).mark_point(size=46, strokeWidth=1.5, color=INK_2).encode(
        x=X, y=Y, fill=alt.Fill("contorno:N", scale=alt.Scale(domain=["no caution", CAUTION],
                                                            range=[INK_2, "#ffffff"]), legend=None), tooltip=tip))
    for part, colour in ((gone[gone["a"].isna() | gone["b"].isna()], MASK_COLOR),
                         (gone[gone["a"].notna() & gone["b"].notna()], MUTED)):
        if len(part):
            layers.append(alt.Chart(part).mark_tick(color=colour, thickness=2, size=12).encode(
                x=X, y=alt.value(alt.ExprRef(expr="height - 6")),
                tooltip=[alt.Tooltip("canal:Q", title="channel"), alt.Tooltip("lambda_um:Q", title="λ (µm)", format=".3f"),
                         alt.Tooltip("motivo:N", title="no value")]))
    return alt.layer(*layers).properties(
        width="container", height=height, autosize=alt.AutoSizeParams(type="fit", contains="padding"),
        padding={"left": 5, "right": 18, "top": 5, "bottom": 5}).resolve_scale(color="independent",
                                                                                 fill="independent")


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
