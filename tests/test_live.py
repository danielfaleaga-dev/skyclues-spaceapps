"""Tests against real NASA/IPAC IRSA data (SIA2 + IBE cutouts).

They re-derive every property of the reference pair (results/pair_m101.json)
from the FITS files themselves. Run with:  pytest -m network
"""

import json

import numpy as np
import pytest
from astropy.coordinates import SkyCoord
from matplotlib.colors import to_rgba as mpl_rgba

from skyclues import archive, config, fitsdata, render
from skyclues.compare import evaluate_pair, lambda_at, pixel_at
from skyclues.geometry import separation_deg
from skyclues.pairing import wave_table_from_url

pytestmark = pytest.mark.network

REPORT = config.RESULTS_DIR / "pair_m101.json"


@pytest.fixture(scope="module")
def report():
    if not REPORT.exists():
        pytest.skip("run scripts/find_pair.py first")
    return json.loads(REPORT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def pair(report):
    sel = report["selected"]
    paths = [archive.fetch(sel[t]["cutout_url"]) for t in ("a", "b")]
    return sel, paths, [fitsdata.load(p) for p in paths]


def test_sia2_query_returns_spherex_images():
    recs = archive.query_images(210.802429, 54.34875, collections=("spherex_qr3",))
    assert len(recs) > 20
    assert {r.detector for r in recs} == {1, 2, 3, 4, 5, 6}
    assert all("/ibe/data/spherex/qr3/" in r.access_url for r in recs)
    assert all(r.mjd_end > r.mjd_start > 60000 for r in recs)
    for r in recs:  # band limits from SIA2 agree with the documented detector bands
        lo, hi = config.BANDS_UM[r.detector]
        assert abs(r.em_min_um - lo) < 0.03 and abs(r.em_max_um - hi) < 0.03


def test_downloaded_files_match_report_checksums(pair):
    sel, paths, _ = pair
    for tag, p in zip(("a", "b"), paths):
        assert archive.sha256(p) == sel[tag]["sha256"]


def test_fits_structure_units_and_wcs(pair, report):
    _, _, imgs = pair
    ra, dec = report["target"]["ra_deg"], report["target"]["dec_deg"]
    for img in imgs:
        assert img.meta["BUNIT"].replace(" ", "") == "MJy/sr"
        assert img.image.shape == img.flags.shape == img.variance.shape == img.zodi.shape
        # real headers define bits 0-28; bit 29 (SATELLITE_HALO) is added from the documentation
        assert img.flag_defs.source.startswith("cabecera") and not img.flag_defs.unknown_names()
        assert img.flag_defs.bits[29] == "SATELLITE_HALO"
        # WCS round trip pixel -> sky -> pixel
        ny, nx = img.shape
        px = np.array([[0, 0], [nx - 1, ny - 1], [nx / 2, ny / 3]], float)
        back = img.wcs.all_world2pix(img.wcs.all_pix2world(px, 0), 0)
        assert np.max(np.abs(back - px)) < 1e-3
        # Target near the cutout centre
        x, y = pixel_at(img, ra, dec)
        assert abs(x - (nx - 1) / 2) < 2 and abs(y - (ny - 1) / 2) < 2
        # Per-pixel wavelength lies inside the detector band
        lo, hi = config.BANDS_UM[img.meta["DETECTOR"]]
        assert lo - 0.02 < np.nanmin(img.wavelength_um) and np.nanmax(img.wavelength_um) < hi + 0.02


def test_s_region_corner_convention_matches_fits_wcs(pair):
    _, _, imgs = pair
    img = imgs[0]
    recs = archive.query_images(*img.wcs.all_pix2world([[0, 0]], 0)[0], collections=("spherex_qr3", "spherex_dr1"))
    rec = next(r for r in recs if r.file_name == img.path.name.split("__")[0] + ".fits")
    off_x, off_y = img.detector_offset()   # cutout 0-based -> full 1-based
    corners_full = np.array([[0.5, 0.5], [2040.5, 0.5], [2040.5, 2040.5], [0.5, 2040.5]])
    sky = img.wcs.all_pix2world(corners_full - [off_x, off_y], 0)
    poly = archive.footprint(rec).corners
    sep_arcsec = separation_deg(sky[:, 0], sky[:, 1], poly[:, 0], poly[:, 1]) * 3600
    assert np.max(sep_arcsec) < 10  # < 2 px; SIP extrapolation over the full detector


def test_metadata_wavelength_estimate_agrees_with_fits(report):
    ra, dec = report["target"]["ra_deg"], report["target"]["dec_deg"]
    for ev in report["evaluated"]:
        for tag, i in (("a", 0), ("b", 1)):
            lam_fits = ev["metrics"]["lambda_target_um"][i]
            bw = ev["metrics"]["bandwidth_target_um"][i]
            assert abs(ev[tag]["lambda_est_um"] - lam_fits) < 0.1 * bw


def test_wave_table_from_range_request_equals_cutout_table(pair):
    sel, _, imgs = pair
    tab = wave_table_from_url(sel["a"]["access_url"])
    assert np.allclose(tab["VALUES"], imgs[0].wave_table["VALUES"])
    assert np.array_equal(tab["X"], imgs[0].wave_table["X"])


def test_selected_pair_is_admissible_from_fits(pair, report):
    sel, _, (a, b) = pair
    t = report["target"]
    ev = evaluate_pair(a, b, t["ra_deg"], t["dec_deg"], t["field_deg"],
                       collections=(sel["a"]["collection"], sel["b"]["collection"]))
    assert ev.admissible
    assert a.meta["DETECTOR"] == b.meta["DETECTOR"]
    assert abs(a.meta["MJD-AVG"] - b.meta["MJD-AVG"]) >= config.MIN_TIME_SEPARATION_DAYS
    assert ev.metrics["dlambda_target_bw"] <= config.SPECTRAL_PASS_BW
    assert ev.metrics["coverage_common_valid"] >= config.COVERAGE_PASS
    la, _ = lambda_at(a, t["ra_deg"], t["dec_deg"])
    lb, _ = lambda_at(b, t["ra_deg"], t["dec_deg"])
    assert abs(la - lb) * 1000 < 10  # nm


def test_pair_are_distinct_observations(pair):
    _, _, (a, b) = pair
    assert a.meta["OBSID"] != b.meta["OBSID"]
    assert a.meta["DATE-AVG"][:10] != b.meta["DATE-AVG"][:10]
    assert not np.array_equal(a.image, b.image)


def test_masks_are_applied_and_visible(pair, report):
    _, _, (a, b) = pair
    for img in (a, b):
        invalid = ~img.valid()
        assert invalid.any(), "expected some flagged pixels in a real exposure"
        disp = render.display_array(img)
        assert np.array_equal(np.isnan(disp), invalid)
        # valid pixels keep exactly IMAGE - ZODI (no smoothing / filling)
        assert np.array_equal(disp[~invalid], (img.image - img.zodi)[~invalid])
        rgba = render.to_rgba(disp, render.shared_norm([disp]))
        mask_c = np.array(mpl_rgba(render.MASK_COLOR))
        assert np.all(np.isclose(rgba[invalid], mask_c))


def test_original_fits_untouched_by_processing(pair):
    sel, paths, (a, _) = pair
    before = archive.sha256(paths[0])
    render.display_array(a)
    a.valid()
    assert archive.sha256(paths[0]) == before == sel["a"]["sha256"]


def test_target_inside_both_footprints(pair, report):
    _, _, imgs = pair
    t = SkyCoord(report["target"]["ra_deg"], report["target"]["dec_deg"], unit="deg")
    for img in imgs:
        assert img.wcs.footprint_contains(t)
