"""Offline unit tests. Arrays here are synthetic test fixtures for the logic
only; they are never shown or stored as observations."""

import numpy as np
import pytest
from astropy.io import fits
from astropy.wcs import WCS
from matplotlib.colors import to_rgba as mpl_rgba

from skyclues import render
from skyclues.compare import place_on_a
from skyclues.geometry import FootprintMap, bilinear_lookup, parse_s_region
from skyclues.quality import DOCUMENTED_BITS, FlagDefinitions, read_flag_definitions, valid_pixel_mask


def _tan_wcs(ra0=150.0, dec0=40.0, rot_deg=33.0, scale_arcsec=6.15):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra0, dec0]
    w.wcs.crpix = [1020.5, 1020.5]
    s = scale_arcsec / 3600
    t = np.radians(rot_deg)
    w.wcs.cd = np.array([[-s * np.cos(t), s * np.sin(t)], [s * np.sin(t), s * np.cos(t)]])
    return w


def test_parse_s_region_drops_closing_vertex():
    pts = parse_s_region("POLYGON ICRS 1 2 3 4 5 6 7 8 1 2")
    assert pts.shape == (4, 2)
    assert pts[0].tolist() == [1.0, 2.0]


def test_homography_reproduces_tan_wcs():
    w = _tan_wcs()
    corners = np.array([[0.5, 0.5], [2040.5, 0.5], [2040.5, 2040.5], [0.5, 2040.5]])
    sky = w.all_pix2world(corners, 1)  # 1-based pixels
    s_region = "POLYGON ICRS " + " ".join(f"{r} {d}" for r, d in np.vstack([sky, sky[:1]]))
    fp = FootprintMap(s_region)
    rng = np.random.default_rng(1)
    pix = rng.uniform(1, 2040, size=(200, 2))
    rd = w.all_pix2world(pix, 1)
    x, y = fp.sky_to_pixel(rd[:, 0], rd[:, 1])
    assert np.max(np.hypot(x - pix[:, 0], y - pix[:, 1])) < 0.01


def test_field_margin_sign():
    w = _tan_wcs()
    corners = np.array([[0.5, 0.5], [2040.5, 0.5], [2040.5, 2040.5], [0.5, 2040.5]])
    sky = w.all_pix2world(corners, 1)
    fp = FootprintMap("POLYGON " + " ".join(f"{r} {d}" for r, d in sky))
    ra_c, dec_c = w.all_pix2world([[1020.5, 1020.5]], 1)[0]
    assert fp.field_margin_px(ra_c, dec_c, 0.1) > 900
    ra_e, dec_e = w.all_pix2world([[5.0, 1020.5]], 1)[0]
    assert fp.field_margin_px(ra_e, dec_e, 0.1) < 0


def test_bilinear_lookup_exact_for_linear_tables():
    xs = np.array([1.0, 500.0, 2040.0])
    ys = np.array([1.0, 1000.0, 2040.0])
    gx, gy = np.meshgrid(xs, ys)
    values = np.stack([0.001 * gx + 0.002 * gy, 0.03 + 0 * gx], axis=-1)
    v = bilinear_lookup(xs, ys, values, 777.0, 1500.0)
    assert v[0] == pytest.approx(0.001 * 777 + 0.002 * 1500)
    assert v[1] == pytest.approx(0.03)


def _flag_header(extra=None):
    h = fits.Header()
    for bit, name in DOCUMENTED_BITS.items():
        h[f"MSKN{bit:04d}"] = name
    for bit, name in (extra or {}).items():
        h[f"MSKN{bit:04d}"] = name
    return h


def test_flag_classes_and_unknown_names():
    defs = read_flag_definitions(_flag_header({30: "NEWTHING"}))
    assert defs.source == "cabecera"            # header complete: nothing added from the documentation
    assert defs.classify("SOURCE") == "info"
    assert defs.classify("OVERFLOW") == "unusable"
    assert defs.classify("HALO") == "artifact"
    assert defs.classify("NEWTHING") == "artifact"   # unknown -> conservative
    assert defs.unknown_names() == ["NEWTHING"]
    strict = defs.bitmask(("unusable", "artifact"))
    assert not strict & (1 << 21)      # SOURCE never masked
    assert strict & (1 << 28)          # HALO masked in strict mode
    assert not defs.bitmask(("unusable",)) & (1 << 28)


def test_valid_mask_rules():
    defs = FlagDefinitions(bits=dict(DOCUMENTED_BITS))
    img = np.ones((3, 3))
    var = np.ones((3, 3))
    flags = np.zeros((3, 3), np.int64)
    img[0, 0] = np.nan
    var[0, 1] = 0.0
    flags[0, 2] = 1 << 1          # OVERFLOW
    flags[1, 0] = 1 << 21         # SOURCE only: still valid
    ok = valid_pixel_mask(img, flags, var, defs)
    assert ok.tolist() == [[False, False, False], [True, True, True], [True, True, True]]


def test_rgba_marks_every_invalid_pixel_and_only_those():
    data = np.linspace(-1, 10, 100).reshape(10, 10)
    data[2, 3] = np.nan
    data[7, 7] = np.nan
    norm = render.shared_norm([data])
    rgba = render.to_rgba(data, norm)
    mask_c = np.array(mpl_rgba(render.MASK_COLOR))
    is_mask = np.all(np.isclose(rgba, mask_c), axis=-1)
    assert is_mask.tolist() == (~np.isfinite(data)).tolist()
    # Valid pixels are grey (R=G=B), so they can never be confused with the mask colour.
    good = rgba[np.isfinite(data)]
    assert np.allclose(good[:, 0], good[:, 1]) and np.allclose(good[:, 1], good[:, 2])


def test_place_on_a_copies_values_without_inventing_new_ones():
    b_vals = np.arange(25, dtype=float).reshape(5, 5)
    iy = np.array([[0, 0, 4], [1, 2, 3]])
    ix = np.array([[0, 1, 4], [1, 2, 9 % 5]])
    inside = np.array([[True, True, False], [True, True, True]])
    out = place_on_a(b_vals, (iy, ix), inside)
    assert np.isnan(out[0, 2])
    finite = out[np.isfinite(out)]
    assert set(finite.tolist()) <= set(b_vals.ravel().tolist())
