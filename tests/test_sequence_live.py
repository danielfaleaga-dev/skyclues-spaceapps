"""Multi-epoch sequences and the player, checked against authentic SPHEREx FITS
(local cache of IRSA cutouts, re-downloaded if missing). Run: pytest -m network"""

import json
import struct

import numpy as np
import pytest
from astropy.io import fits
from matplotlib.colors import to_rgba as mpl_rgba

from skyclues import archive, config, player, render
from skyclues.geometry import separation_deg
from skyclues.sequence import load_sequence

pytestmark = pytest.mark.network

SEQ_REPORTS = ["sequence_m101", "sequence_wise0855", "sequence_wise0855_mwir"]


def _report(name):
    p = config.RESULTS_DIR / f"{name}.json"
    if not p.exists():
        pytest.skip(f"run scripts/find_sequence.py for {name}")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def m101():
    return _report("sequence_m101"), load_sequence(_report("sequence_m101"))


@pytest.mark.parametrize("name", SEQ_REPORTS)
def test_reference_sequences_have_at_least_three_admissible_epochs(name):
    rep = _report(name)
    seq = load_sequence(rep)                      # verifies SHA-256 of every FITS
    assert seq.n >= 3
    assert seq.admissible and not seq.warnings
    mjd = [f.mjd for f in seq.frames]
    assert mjd == sorted(mjd)
    assert min(np.diff(mjd)) >= config.MIN_TIME_SEPARATION_DAYS
    # Criteria re-derived from the FITS agree with the stored report
    assert [c["status"] for c in seq.criteria] == [c["status"] for c in rep["selected"]["criteria"]]
    assert seq.metrics["coverage_common_valid"] >= config.COVERAGE_PASS


def test_global_spectral_compatibility_all_pairs(m101):
    _, seq = m101
    bw = seq.frames[0].image.bandwidth_um
    lam = [f.on_reference(f.image.wavelength_um) for f in seq.frames]
    worst = 0.0
    for i in range(seq.n):
        for j in range(i + 1, seq.n):
            d = np.abs(lam[i] - lam[j])[seq.common_mask] / bw[seq.common_mask]
            worst = max(worst, float(d.max()))
    assert worst <= config.SPECTRAL_PASS_BW
    assert worst == pytest.approx(seq.metrics["lambda_spread_common_max_bw"], abs=1e-9)


def test_common_mask_is_intersection_of_frame_masks(m101):
    _, seq = m101
    manual = seq.field_mask.copy()
    for f in seq.frames:
        manual &= f.valid_on_reference(seq.mask_classes)
    assert np.array_equal(manual, seq.common_mask)
    assert seq.common_mask.sum() == seq.metrics["n_common_px"]


def test_frames_are_authentic_and_not_interpolated(m101):
    _, seq = m101
    for i, f in enumerate(seq.frames):
        with fits.open(f.path) as h:                       # independent re-read of the original file
            assert np.array_equal(np.asarray(h["IMAGE"].data, float), f.image.image, equal_nan=True)
            assert h["IMAGE"].header["OBSID"] == f.obs_id
        data = seq.frame_data(i)
        assert np.array_equal(np.isnan(data), ~seq.valid_stack[i])
        original = set((f.image.image - f.image.zodi)[f.image.valid()].ravel().tolist())
        assert set(data[np.isfinite(data)].ravel().tolist()) <= original


def test_wcs_alignment_within_nearest_neighbour_tolerance(m101):
    _, seq = m101
    ref = seq.frames[0].image
    ny, nx = ref.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    ra0, dec0 = ref.wcs.all_pix2world(xx, yy, 0)
    for f in seq.frames[1:]:
        iy, ix = f.index_on_ref
        ra1, dec1 = f.image.wcs.all_pix2world(ix, iy, 0)
        sep = separation_deg(ra0, dec0, ra1, dec1)[f.inside_ref & seq.field_mask] * 3600
        assert sep.max() < 0.75 * config.NOMINAL_PIXEL_SCALE_ARCSEC  # <= sqrt(2)/2 px + SIP margin


def test_pair_report_loads_as_two_frame_sequence():
    seq = load_sequence(_report("pair_wise0855"))
    assert seq.n == 2 and seq.admissible
    html = player.build_player(seq)
    assert html.count("data:image/png;base64,") == 2


def _png_size(b: bytes):
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", b[16:24])


def test_player_frames_fixed_layout_and_metadata(m101):
    _, seq = m101
    norm = player.sequence_norm(seq)
    pngs = [player.render_frame_png(seq, i, norm) for i in range(seq.n)]
    assert len({_png_size(p) for p in pngs}) == 1           # identical canvas: no jitter between frames
    assert len(set(pngs)) == seq.n                          # every frame is a distinct observation
    html = player.player_html(seq, pngs)
    assert html.count("data:image/png;base64,") == seq.n
    meta = player.frame_metadata(seq)
    assert [m["obs_id"] for m in meta] == [f.obs_id for f in seq.frames]
    assert [m["dt_days"] for m in meta] == sorted(m["dt_days"] for m in meta) and meta[0]["dt_days"] == 0
    for ctrl in ('id="play"', 'id="prev"', 'id="next"', 'id="fps"', 'id="loop"', 'id="blink"', 'id="scrub"'):
        assert ctrl in html


def test_player_colours_masks_and_common_region(m101):
    _, seq = m101
    norm = player.sequence_norm(seq)
    mask_c = np.array(mpl_rgba(render.MASK_COLOR))
    out_c = np.array(mpl_rgba(render.OUTSIDE_COMMON_COLOR))
    for i in range(seq.n):
        st = seq.frame_status(i)
        rgba = player.frame_rgba(seq, i, norm, restrict_to_common=True)
        assert np.all(np.isclose(rgba[st == 2], mask_c))
        assert np.all(np.isclose(rgba[st == 1], out_c))
        g = rgba[st == 0]
        assert np.allclose(g[:, 0], g[:, 1]) and np.allclose(g[:, 1], g[:, 2])   # grey sky only where common
        plain = player.frame_rgba(seq, i, norm, restrict_to_common=False)
        assert np.all(np.isclose(plain[st == 2], mask_c))


def test_cache_files_untouched(m101):
    rep, seq = m101
    for f, meta in zip(seq.frames, rep["selected"]["frames"]):
        assert archive.sha256(f.path) == meta["sha256"]
