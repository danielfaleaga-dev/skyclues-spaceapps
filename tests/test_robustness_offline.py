"""Offline tests for mission-3 fixes: HALO handling, exact-geometry drawing,
FOV limits, atomic cache writes, download de-duplication and search progress.
Arrays are synthetic fixtures for the logic only (never shown as observations)."""

import threading
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.colors import to_rgba as mpl_rgba  # noqa: E402

from skyclues import archive, config, render, sequence  # noqa: E402
from skyclues.fitsdata import SpectralImage  # noqa: E402
from skyclues.quality import (CAUTION, DOCUMENTED_BITS, OFFICIAL_CUBE_REJECT, FlagDefinitions,  # noqa: E402
                              valid_pixel_mask)
from skyclues.targets import clamp_fov_deg, fov_pixels  # noqa: E402

BIT = {name: bit for bit, name in DOCUMENTED_BITS.items()}
STRICT = ("unusable", "artifact")


# ------------------------------------------------------------------ HALO
def test_satellite_halo_documented_and_always_masked():
    defs = FlagDefinitions(bits=dict(DOCUMENTED_BITS))
    assert DOCUMENTED_BITS[29] == "SATELLITE_HALO"
    assert defs.classify("SATELLITE_HALO") == "artifact"
    assert defs.bitmask(STRICT) & (1 << 29)
    assert "SATELLITE_HALO" not in CAUTION and CAUTION == {"HALO"}
    # every flag the official cube rejects is masked by the strict policy
    assert all(defs.bitmask(STRICT) & (1 << BIT[n]) for n in OFFICIAL_CUBE_REJECT)


def test_ignoring_halo_unmasks_only_pure_halo_pixels():
    defs = FlagDefinitions(bits=dict(DOCUMENTED_BITS))
    img, var = np.ones((1, 5)), np.ones((1, 5))
    flags = np.array([[0,
                       1 << BIT["HALO"],
                       (1 << BIT["HALO"]) | (1 << BIT["TRANSIENT"]),
                       1 << BIT["SATELLITE_HALO"],
                       (1 << BIT["HALO"]) | (1 << BIT["SOURCE"])]], np.int64)
    strict = valid_pixel_mask(img, flags, var, defs, STRICT)
    explore = valid_pixel_mask(img, flags, var, defs, STRICT, CAUTION)
    assert strict.tolist() == [[True, False, False, False, False]]
    assert explore.tolist() == [[True, True, False, False, True]]


def _image(flags, values=None):
    ny, nx = flags.shape
    values = np.arange(ny * nx, dtype=float).reshape(ny, nx) if values is None else values
    return SpectralImage(path=Path("synthetic"), image=values, flags=flags, variance=np.ones((ny, nx)),
                         zodi=np.zeros((ny, nx)), wcs=None, wavelength_um=np.ones((ny, nx)),
                         bandwidth_um=np.ones((ny, nx)), flag_defs=FlagDefinitions(bits=dict(DOCUMENTED_BITS)),
                         meta={}, wave_table={})


def test_caution_mask_is_halo_only():
    flags = np.zeros((2, 3), np.int64)
    flags[0, 1] = 1 << BIT["HALO"]
    flags[1, 1] = (1 << BIT["HALO"]) | (1 << BIT["BLOOM"])
    caution = _image(flags).caution(STRICT)
    assert caution.tolist() == [[False, True, False], [False, False, False]]


def test_native_rgba_marks_caution_pixels_distinctly():
    data = np.linspace(0, 9, 10).reshape(2, 5)
    data[1, 4] = np.nan
    caution = np.zeros(data.shape, bool)
    caution[0, 1:4] = True
    norm = render.shared_norm([data])
    rgba = render.native_rgba(data, norm, caution=caution)
    mask_c = np.array(mpl_rgba(render.MASK_COLOR))
    assert np.allclose(rgba[1, 4], mask_c)                                  # no data -> mask colour
    grey = rgba[~caution & np.isfinite(data)]
    assert np.allclose(grey[:, 0], grey[:, 1]) and np.allclose(grey[:, 1], grey[:, 2])
    cop = rgba[caution]
    assert np.all(cop[:, 0] > cop[:, 2] + 0.05)                              # copper hue, never grey sky
    lum = cop[:, :3] @ np.array([0.2126, 0.7152, 0.0722])
    assert np.all(np.diff(lum) > 0)                                          # brightness order preserved
    assert not np.any(np.all(np.isclose(cop, mask_c), axis=-1))


# ------------------------------------------------------------------ exact geometry
def test_draw_native_places_quads_at_given_corners_with_original_colours():
    rgba = render.to_rgba(np.arange(6, dtype=float).reshape(2, 3), render.shared_norm([np.arange(6.0)]))
    yc, xc = np.mgrid[-0.5:2:1.0, -0.5:3:1.0]
    th = np.radians(6.0)                                     # rotated and sub-pixel shifted grid
    X = 0.3 + xc * np.cos(th) - yc * np.sin(th)
    Y = 0.2 + xc * np.sin(th) + yc * np.cos(th)
    fig, ax = plt.subplots()
    render.draw_native(ax, (X, Y), rgba, (3, 4))
    mesh = ax.collections[0]
    coords = mesh.get_coordinates()
    assert np.allclose(coords[..., 0], X) and np.allclose(coords[..., 1], Y)
    fig.canvas.draw()
    assert np.allclose(mesh.get_facecolor(), rgba.reshape(-1, 4))     # one colour per native pixel, unchanged
    assert ax.get_xlim() == (-0.5, 3.5) and ax.get_ylim() == (-0.5, 2.5)
    assert np.allclose(mpl_rgba(ax.get_facecolor()), mpl_rgba(render.MASK_COLOR))
    plt.close(fig)


# ------------------------------------------------------------------ FOV
def test_fov_limits_and_invalid_input():
    assert clamp_fov_deg(0.1) == 0.1
    assert clamp_fov_deg(0.001) == config.FOV_MIN_DEG
    assert clamp_fov_deg(5) == config.FOV_MAX_DEG
    assert clamp_fov_deg("abc") == config.DEFAULT_FIELD_DEG
    assert clamp_fov_deg(float("nan")) == config.DEFAULT_FIELD_DEG
    assert clamp_fov_deg(None) == config.DEFAULT_FIELD_DEG
    assert clamp_fov_deg("0.2") == 0.2
    assert [round(a / 60, 4) for a in config.FOV_PRESETS_ARCMIN] == [0.05, 0.1, 0.2, 0.3]
    assert config.FOV_MIN_DEG <= config.DEFAULT_FIELD_DEG <= config.FOV_MAX_DEG
    assert fov_pixels(0.1) == 59
    # the smallest field still holds enough pixels to pass S5 with full coverage
    r_px = config.FOV_MIN_DEG / 2 * 3600 / config.NOMINAL_PIXEL_SCALE_ARCSEC
    assert np.pi * r_px ** 2 * config.COVERAGE_PASS >= config.MIN_COMMON_VALID_PIXELS


# ------------------------------------------------------------------ cache robustness
@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "REFERENCE_DIR", tmp_path / "reference")
    return tmp_path


def test_atomic_write_concurrent_writers_leave_complete_file(tmp_path):
    target = tmp_path / "x.json"
    payloads = [(f"{k}" * 200_000).encode() for k in range(8)]
    threads = [threading.Thread(target=archive.atomic_write, args=(target, p)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert target.read_bytes() in payloads
    assert not list(tmp_path.glob("*.part"))


class _Resp:
    status_code = 200

    def __init__(self, content):
        self.content = content
        self.text = ""


def test_fetch_downloads_each_url_once_under_concurrency(tmp_store, monkeypatch):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        time.sleep(0.2)
        return _Resp(b"SIMPLE  = T" + b" " * 100)

    monkeypatch.setattr(archive.requests, "get", fake_get)
    url = "https://example.invalid/level2_TEST_D1_spx_l2b-v1-2026-001.fits?center=1,2&size=0.1"
    results = []
    threads = [threading.Thread(target=lambda: results.append(archive.fetch(url))) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1 and len(set(results)) == 1
    assert results[0].read_bytes().startswith(b"SIMPLE")


def test_fetch_many_uses_local_copies_and_reports_progress(tmp_store, monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("network must not be used")

    monkeypatch.setattr(archive.requests, "get", no_network)
    ua = "https://example.invalid/level2_A_D1_spx_l2b-v1-2026-001.fits?center=1,2&size=0.1"
    ub = "https://example.invalid/level2_B_D1_spx_l2b-v1-2026-001.fits?center=1,2&size=0.1"
    archive.atomic_write(archive._cache_path(ua), b"SIMPLE cache")
    ref = config.REFERENCE_DIR / archive._cache_path(ub).name
    archive.atomic_write(ref, b"SIMPLE reference")
    seen = []
    got = archive.fetch_many([ua, ub, ua], progress=lambda d, t, n: seen.append((d, t, n)))
    assert list(got) == [ua, ub]
    assert got[ub] == ref                                      # reference store has priority
    assert seen[-1] == (2, 2, 0)                               # 2 ready, 0 downloaded


def test_find_sequence_reports_every_stage(monkeypatch):
    monkeypatch.setattr(sequence.archive, "query_images", lambda *a, **k: [])
    stages = []
    best, rep = sequence.find_sequence(10.0, 20.0, 0.1, log=lambda m: None,
                                       progress=lambda s, f, m: stages.append((s, f)))
    assert best is None and rep["selected"] is None
    names = [s for s, _ in stages]
    assert names[0] == "catalog" and names[-1] == "done"
    assert set(names) <= set(sequence.STAGES)
    fr = [f for _, f in stages]
    assert fr == sorted(fr) and fr[-1] == 1.0
