"""Mission-3 checks on authentic SPHEREx FITS (local cache of IRSA cutouts,
re-downloaded if missing): exact geometry without resampling, HALO display,
display options that never touch the metrics. Run: pytest -m network"""

import json
import struct

import numpy as np
import pytest
from matplotlib.colors import to_rgba as mpl_rgba

from skyclues import config, player, render
from skyclues.geometry import separation_deg
from skyclues.quality import CAUTION
from skyclues.sequence import load_sequence, report_urls

pytestmark = pytest.mark.network


def _report(name):
    p = config.RESULTS_DIR / f"{name}.json"
    if not p.exists():
        pytest.skip(f"run scripts/find_sequence.py for {name}")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def m101():
    return load_sequence(_report("sequence_m101"))


def _png_size(b: bytes):
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", b[16:24])


def test_nearest_neighbour_error_is_real_and_exact_geometry_removes_it(m101):
    seq = m101
    errs = [float(seq.placement_error_px(i)[seq.field_mask].max()) for i in range(seq.n)]
    assert errs[0] < 1e-6             # reference frame (SIP round trip only)
    assert max(errs) > 0.5            # the defect: rotated visits shift by up to ~0.7 px on the common grid
    assert max(errs) <= np.sqrt(0.5) + 0.01
    for i in range(seq.n):
        img = seq.frames[i].image
        ny, nx = img.shape
        x, y = seq.native_centres(i)
        rng = np.random.default_rng(i)
        r, c = rng.integers(0, ny, 200), rng.integers(0, nx, 200)
        ra_n, dec_n = img.wcs.all_pix2world(c.astype(float), r.astype(float), 0)    # native pixel on the sky
        ra_d, dec_d = seq.wcs.all_pix2world(x[r, c], y[r, c], 0)                     # where it is drawn
        assert separation_deg(ra_n, dec_n, ra_d, dec_d).max() * 3600 < 0.01          # < 0.01 arcsec
        X, Y = seq.native_corners(i)
        assert X.shape == (ny + 1, nx + 1) == Y.shape
    X0, Y0 = seq.native_corners(0)
    assert np.array_equal(X0[0], np.arange(-0.5, seq.shape[1], 1.0))                 # reference: regular grid
    assert np.array_equal(Y0[:, 0], np.arange(-0.5, seq.shape[0], 1.0))


def test_native_data_are_the_original_values(m101):
    seq = m101
    for i, f in enumerate(seq.frames):
        img = f.image
        nat = seq.native_data(i)
        valid = img.valid(seq.mask_classes)
        assert np.array_equal(np.isfinite(nat), valid)
        assert np.array_equal(nat[valid], (img.image - img.zodi)[valid])          # bit-identical, not resampled
        raw = seq.native_data(i, subtract_zodi=False)
        assert np.array_equal(raw[valid], img.image[valid])


def test_exact_rgba_masks_exactly_the_invalid_native_pixels(m101):
    seq = m101
    norm = player.sequence_norm(seq)
    mask_c = np.array(mpl_rgba(render.MASK_COLOR))
    for i in range(seq.n):
        rgba = player.native_frame_rgba(seq, i, norm)
        is_mask = np.all(np.isclose(rgba, mask_c), axis=-1)
        assert np.array_equal(is_mask, ~seq.frames[i].image.valid(seq.mask_classes))


def test_halo_exploratory_marks_only_halo_pixels_and_metrics_stay_strict(m101):
    seq = m101
    before = (json.dumps(seq.criteria), json.dumps(seq.metrics), seq.common_mask.copy(), seq.valid_stack.copy())
    norm = player.sequence_norm(seq)
    mask_c = np.array(mpl_rgba(render.MASK_COLOR))
    total = 0
    for i, f in enumerate(seq.frames):
        caution = seq.native_caution(i)
        total += int(caution.sum())
        halo_bit = f.image.flag_defs.names_bitmask(CAUTION)
        assert np.all(f.image.flags[caution] & halo_bit)                          # every marked pixel has HALO
        strict = player.native_frame_rgba(seq, i, norm, show_halo=False)
        explore = player.native_frame_rgba(seq, i, norm, show_halo=True)
        assert np.all(np.isclose(strict[caution], mask_c))                         # strict: masked
        changed = np.any(~np.isclose(strict, explore), axis=-1)
        assert np.array_equal(changed, caution)                                    # only HALO pixels change
        cop = explore[caution]
        assert np.all(cop[:, 0] > cop[:, 2])                                       # copper, not grey sky
    assert total > 0, "M101 should contain HALO-only pixels around bright stars"
    for geometry in player.GEOMETRIES:
        player.build_player(seq, geometry=geometry, show_halo=True)
    after = (json.dumps(seq.criteria), json.dumps(seq.metrics), seq.common_mask, seq.valid_stack)
    assert before[:2] == after[:2]
    assert np.array_equal(before[2], after[2]) and np.array_equal(before[3], after[3])


def test_both_geometries_fixed_canvas_and_labelled(m101):
    seq = m101
    norm = player.sequence_norm(seq)
    sizes = {_png_size(player.render_frame_png(seq, i, norm, geometry=g, show_halo=h))
             for i in range(seq.n) for g in player.GEOMETRIES for h in (False, True)}
    assert len(sizes) == 1
    assert "sin remuestreo" in player.legend_html(geometry="exact")
    assert "REMUESTREADO" in player.legend_html(geometry="nearest")
    assert "HALO" in player.legend_html(show_halo=True) and "HALO" not in player.legend_html()
    with pytest.raises(ValueError):
        player.render_frame_png(seq, 0, norm, geometry="bilinear")


def test_concurrent_rendering_is_deterministic_and_leaves_no_pyplot_state(m101):
    from concurrent.futures import ThreadPoolExecutor

    import matplotlib.pyplot as plt

    seq = m101
    norm = player.sequence_norm(seq)
    serial = [player.render_frame_png(seq, i, norm) for i in range(seq.n)]
    with ThreadPoolExecutor(4) as pool:            # several app sessions rendering at once
        par = list(pool.map(lambda k: player.render_frame_png(seq, k % seq.n, norm), range(4 * seq.n)))
        pngs = list(pool.map(lambda _: render.figure_png(render.sequence_coverage_figure(seq)), range(4)))
    assert all(p == serial[k % seq.n] for k, p in enumerate(par))
    assert len(set(pngs)) == 1 and _png_size(pngs[0])[0] > 0
    assert plt.get_fignums() == []                 # nothing registered in pyplot's global state


def test_load_sequence_reports_progress_from_local_files():
    rep = _report("sequence_wise0855_mwir")
    seen = []
    seq = load_sequence(rep, progress=lambda d, t, n: seen.append((d, t, n)))
    assert seq.n == len(report_urls(rep)) and seen[-1][:2] == (seq.n, seq.n)
