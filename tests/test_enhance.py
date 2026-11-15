"""Synthetic tests of the infrared S/N enhancement. They validate the METHOD on controlled images;
they are NOT evidence of an astronomical improvement (that is ``scripts/validate_enhance.py``)."""
import math
from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from skyclues import enhance as en, motion
from skyclues.fitsdata import SpectralImage
from skyclues.quality import DOCUMENTED_BITS, FlagDefinitions

SCALE = 6.15 / 3600
RA0, DEC0 = 150.0, 10.0
FOV = 0.12
BIT = {name: 1 << bit for bit, name in DOCUMENTED_BITS.items()}


@pytest.fixture(autouse=True)
def synthetic_psf(monkeypatch):
    monkeypatch.setattr(motion, "psf_for", lambda img, x, y: motion.PSF(
        None, sigma_px=float(img.meta.get("PSF_SIGMA", 1.0)), description="SYNTHETIC Gaussian"))


def wcs_for(size, dx=0.0, dy=0.0, rot_deg=0.0):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [RA0, DEC0]
    w.wcs.crpix = [(size + 1) / 2 + dx, (size + 1) / 2 + dy]
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    w.wcs.cd = [[-SCALE * c, SCALE * s], [SCALE * s, SCALE * c]]
    return w


def sky(dx_px, dy_px):
    """Sky position at (dx, dy) native pixels east-ish/north of the field centre."""
    return RA0 - dx_px * SCALE / math.cos(math.radians(DEC0)), DEC0 + dy_px * SCALE


STARS = [(sky(-22, -18), 4000.0), (sky(20, -21), 3000.0), (sky(-19, 22), 3500.0), (sky(23, 19), 2500.0),
         (sky(-4, 25), 3000.0), (sky(26, -3), 2800.0)]


def exposure(seed=1, *, size=81, sigma=1.0, stars=STARS, extra=(), dx=0.0, dy=0.0, rot=0.0, lam=1.25, det=2,
             level=0.0, mjd=None, psf_sigma=1.0, wcs_error=0.0, collection="SYNTHETIC", version="1", noise=True):
    w = wcs_for(size, dx, dy, rot)
    truth = wcs_for(size, dx + wcs_error, dy, rot)       # where the sky really falls on the pixels
    yy, xx = np.indices((size, size))
    rng = np.random.default_rng(seed)
    data = (rng.normal(0, sigma, (size, size)) if noise else np.zeros((size, size))) + level
    for (ra, dec), flux in list(stars) + list(extra):
        x, y = truth.all_world2pix(ra, dec, 0)
        data += flux / (2 * np.pi * psf_sigma ** 2) * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * psf_sigma ** 2))
    img = SpectralImage(
        path=Path("synthetic"), image=data, flags=np.zeros((size, size), np.int64),
        variance=np.full((size, size), float(sigma) ** 2), zodi=np.zeros((size, size)), wcs=w,
        wavelength_um=np.full((size, size), float(lam)), bandwidth_um=np.full((size, size), 0.03),
        flag_defs=FlagDefinitions(bits=dict(DOCUMENTED_BITS)),
        meta={"DETECTOR": det, "OBSID": f"SYNTHETIC-{seed}", "MJD-AVG": 60000 + 0.01 * seed if mjd is None else mjd,
              "DATE-AVG": "SYNTHETIC", "L2DQAFLG": "Pass", "FINAST": 0, "PSF_FWHM": 14.5, "VERSION": version,
              "BUNIT": "MJy/sr", "XPOSURE": 113.6, "CRPIX1A": 1.0, "CRPIX2A": 1.0, "FILE": "synthetic",
              "PSF_SIGMA": psf_sigma},
        wave_table={})
    return en.Exposure(img, img.meta["OBSID"], float(img.meta["MJD-AVG"]), collection, "synthetic://", "not-a-real-fits")


def pix(stack, radec):
    x, y = stack.wcs.all_world2pix(radec[0], radec[1], 0)
    return float(x), float(y)


def stack_of(n=4, **kw):
    return en.combine([exposure(seed=i + 1, **kw) for i in range(n)], RA0, DEC0, FOV)


# ----------------------------------------------------------------------------- aligned images
def test_aligned_images_gain_is_sqrt_n_and_flux_is_preserved():
    st = stack_of(4)
    assert st.n_exposures == 4 and st.selection["kind"] == "monochromatic"
    assert np.allclose(st.data[st.reference] + st.offsets[st.reference], st.exposures[st.reference].image.image)
    m = en.evaluate(st)
    assert m["pixel_noise_mjysr"]["ratio"] == pytest.approx(2.0, rel=0.05)
    assert 0.9 <= st.noise["null_scale"] <= 1.1                      # the variances describe the real noise
    assert m["gain"]["median"] == pytest.approx(2.0, rel=0.08)
    assert m["photometry"]["flux_ratio_median"] == pytest.approx(1.0, abs=0.01)
    assert m["detections"]["null_image_spurious"] == 0 and m["detections"]["negative_image"] == 0
    assert en.verdict(m)["accepted"]


def test_shifted_and_rotated_images_are_registered_through_their_wcs():
    exps = [exposure(1), exposure(2, dx=0.37, dy=-0.21, rot=7.0), exposure(3, dx=-3.4, dy=2.6, rot=-11.0),
            exposure(4, dx=1.5, dy=0.5, rot=3.0)]
    st = en.combine(exps, RA0, DEC0, FOV)
    m = en.evaluate(st)
    for radec, _ in STARS:                                            # every star where its sky position says
        x, y = pix(st, radec)
        c = en._centroid(st.image, x, y, 3)
        assert math.hypot(c["x"] - x, c["y"] - y) < 0.35
    assert np.hypot(*m["astrometry"]["median_shift_arcsec"]) < 0.25 * 6.15
    assert m["photometry"]["flux_ratio_median"] == pytest.approx(1.0, abs=0.02)
    assert m["resolution"]["width_ratio"] < 1.25
    assert m["gain"]["median"] > 1.7
    assert st.registration["checked"] and st.registration["max_shift_arcsec"] < 0.5 * 6.15


def test_registration_error_rejects_the_exposure_instead_of_shifting_the_stack():
    good = [exposure(i) for i in (1, 2, 3)]
    st = en.combine(good + [exposure(4, wcs_error=1.6)], RA0, DEC0, FOV)
    assert st.n_exposures == 3
    assert any("Registro" in r["reason"] for r in st.selection["rejected"])
    for radec, _ in STARS[:3]:
        x, y = pix(st, radec)
        c = en._centroid(st.image, x, y, 3)
        assert math.hypot(c["x"] - x, c["y"] - y) < 0.3            # no false displacement inherited


# ----------------------------------------------------------------------------- weights and variances
def test_different_variances_weight_and_propagate_exactly():
    exps = [exposure(1, sigma=1.0), exposure(2, sigma=3.0)]
    st = en.combine(exps, RA0, DEC0, FOV)
    w = st.weights[:, 40, 40]
    assert w[0] / w[1] == pytest.approx(9.0)
    assert st.variance[40, 40] == pytest.approx(1 / (1 / 1 + 1 / 9))  # 1 / sum(1 / sigma^2)
    # The noisy exposure adds almost nothing: the method says so instead of claiming an improvement.
    m = en.evaluate(st)
    assert m["pixel_noise_mjysr"]["ratio_vs_best"] < 1.1 and st.best == 0
    pixel = en.combine(exps, RA0, DEC0, FOV, weighting="pixel")
    assert pixel.variance[40, 40] == pytest.approx(st.variance[40, 40])


def test_no_gain_is_rejected():
    st = en.combine([exposure(1, sigma=1.0), exposure(2, sigma=30.0)], RA0, DEC0, FOV)
    m = en.evaluate(st)
    v = en.verdict(m)
    assert not v["accepted"] and "no aporta" in " ".join(v["reasons"])
    assert m["gain"]["vs_best_exposure_median"] == pytest.approx(1.0, abs=0.05)


def test_frame_weights_do_not_bias_bright_sources_when_variance_follows_the_signal():
    exps = []
    for i in range(6):
        e = exposure(i + 1, dx=0.5 * (i % 2), dy=0.33 * (i % 3))
        e.image.variance = 1.0 + np.clip(e.image.image, 0, None) * 0.5      # source photon noise in VARIANCE
        exps.append(e)
    frame = en.evaluate(en.combine(exps, RA0, DEC0, FOV))
    pixel = en.evaluate(en.combine(exps, RA0, DEC0, FOV, weighting="pixel"))
    assert frame["photometry"]["flux_ratio_median"] == pytest.approx(1.0, abs=0.01)
    assert pixel["photometry"]["flux_ratio_median"] < 0.99          # the textbook weights lose flux


# ----------------------------------------------------------------------------- masks and coverage
def test_invalid_pixels_never_become_signal():
    exps = [exposure(i + 1) for i in range(3)]
    exps[0].image.image[30:34, 30:34] = np.nan
    exps[1].image.variance[30:34, 30:34] = 0.0
    exps[1].image.flags[50, 50] = BIT["HOT"]
    for e in exps:                                                  # one region invalid everywhere
        e.image.flags[10:13, 60:63] = BIT["TRANSIENT"]
        e.image.image[10:13, 60:63] = 1e6                          # a huge value under the mask
    st = en.combine(exps, RA0, DEC0, FOV)
    assert (st.n[30:34, 30:34] == 1).all() and st.n[50, 50] == 2
    assert np.isnan(st.image[10:13, 60:63]).all() and (st.n[10:13, 60:63] == 0).all()
    assert np.nanmax(st.image) < 1e4
    assert en.measure_source(st, 61, 11) is None                     # nothing is measured on missing data


def test_partial_coverage_is_propagated_and_tiny_overlap_is_rejected():
    half = exposure(4, dx=-28.0)                                    # covers part of the field only
    st = en.combine([exposure(1), exposure(2), exposure(3), half], RA0, DEC0, FOV)
    assert st.n_exposures == 4 and st.n.max() == 4 and st.n[st.field].min() == 3
    assert (st.coverage[st.field] >= 3).all()
    far = exposure(5, dx=-74.0)                                     # shares almost nothing
    st2 = en.combine([exposure(1), exposure(2), far], RA0, DEC0, FOV)
    assert st2.n_exposures == 2
    assert any("nivel de cielo" in r["reason"] for r in st2.selection["rejected"])


def test_saturation_is_not_recovered_by_stacking():
    exps = [exposure(i + 1) for i in range(4)]
    x, y = (int(round(float(v))) for v in exps[0].image.wcs.all_world2pix(*STARS[0][0], 0))
    for e in exps:
        e.image.flags[y - 1:y + 2, x - 1:x + 2] = BIT["OVERFLOW"]
    st = en.combine(exps, RA0, DEC0, FOV)
    sx, sy = (int(round(v)) for v in pix(st, STARS[0][0]))
    assert np.isnan(st.image[sy, sx]) and st.n[sy, sx] == 0
    assert en.measure_source(st, sx, sy) is None
    exps[0].image.flags[:] = 0                                      # saturated in three of four: one remains
    st = en.combine(exps, RA0, DEC0, FOV)
    assert st.n[sy, sx] == 1


def test_nonphysical_negatives_are_removed_but_bright_single_values_are_kept():
    exps = [exposure(i + 1) for i in range(4)]
    exps[2].image.image[40, 12] = -80.0                             # unflagged dead-like pixel
    exps[1].image.image[12, 40] = +80.0                             # unflagged cosmic ray or a transient
    st = en.combine(exps, RA0, DEC0, FOV)
    assert st.selection["nonphysical_negative_pixels"][2] == 1 and sum(st.selection["nonphysical_negative_pixels"]) == 1
    assert st.n[40, 12] == 3 and abs(st.image[40, 12]) < 3
    assert st.n[12, 40] == 4 and st.image[12, 40] > 15              # kept: it could be real


# ----------------------------------------------------------------------------- compatibility
def test_psf_incompatible_exposure_is_rejected():
    st = en.combine([exposure(1), exposure(2), exposure(3), exposure(4, psf_sigma=2.2)], RA0, DEC0, FOV)
    assert st.n_exposures == 3
    assert any("PSF incompatible" in r["reason"] for r in st.selection["rejected"])


def test_spectral_differences_change_the_product_not_the_method():
    mono = en.combine([exposure(1, lam=1.250), exposure(2, lam=1.255)], RA0, DEC0, FOV)
    assert mono.selection["kind"] == "monochromatic" and not mono.selection["warnings"]
    broad = en.combine([exposure(1, lam=1.25), exposure(2, lam=1.31), exposure(3, lam=1.40)], RA0, DEC0, FOV)
    assert broad.selection["kind"] == "broadband"
    assert "BANDA ANCHA" in broad.selection["warnings"][0] and "monocromático" in broad.selection["warnings"][0]
    assert broad.selection["lambda_range_um"] == pytest.approx([1.25, 1.40])
    assert np.nanmax(broad.lam_spread_bw) == pytest.approx(5.0)
    assert broad.lam[40, 40] == pytest.approx(np.mean([1.25, 1.31, 1.40]))


def test_detectors_and_calibrations_are_never_mixed():
    sel = en.select([exposure(1, det=2), exposure(2, det=5)], RA0, DEC0, FOV)
    assert not sel["ok"] and "detectores distintos" in sel["reason"]
    with pytest.raises(en.EnhanceError):
        en.combine([exposure(1, det=2), exposure(2, det=5)], RA0, DEC0, FOV)
    st = en.combine([exposure(1), exposure(2), exposure(3, collection="OTHER"), exposure(4, version="2")],
                    RA0, DEC0, FOV)
    assert st.n_exposures == 2 and len(st.selection["rejected"]) == 2
    bad = exposure(5)
    bad.image.meta["FINAST"] = 2
    worse = exposure(6)
    worse.image.meta["L2DQAFLG"] = "Fail"
    sel = en.select([exposure(1), exposure(2), bad, worse], RA0, DEC0, FOV)
    assert sel["n"] == 2 and {r["obs_id"] for r in sel["rejected"]} == {"SYNTHETIC-5", "SYNTHETIC-6"}
    assert not en.select([exposure(1)], RA0, DEC0, FOV)["ok"]


def test_temporal_differences_and_a_moving_target():
    exps = [exposure(1, mjd=60000.0), exposure(2, mjd=60200.0)]
    st = en.combine(exps, RA0, DEC0, FOV, target_motion_arcsec=1.0)
    assert st.selection["span_days"] == pytest.approx(200.0)
    with pytest.raises(en.EnhanceError, match="emborronaría"):
        en.combine(exps, RA0, DEC0, FOV, target_motion_arcsec=8.0)


# ----------------------------------------------------------------------------- faint and moving sources
FAINT = [(sky(-8, -9), 16.0), (sky(9, 7), 16.0), (sky(-11, 10), 16.0), (sky(7, -12), 16.0), (sky(0, 0), 16.0)]


def test_faint_sources_become_detectable_without_false_detections():
    exps = [exposure(i + 1, extra=FAINT, dx=0.4 * (i % 3), dy=0.3 * (i % 2)) for i in range(9)]
    st = en.combine(exps, RA0, DEC0, FOV)
    m = en.evaluate(st)
    found = 0
    for radec, _ in FAINT:
        x, y = pix(st, radec)
        hits = [s for s in m["sources"] if math.hypot(s["x"] - x, s["y"] - y) <= 1.5]
        if hits:
            found += 1
            assert hits[0]["snr_single_median"] < 5 < hits[0]["snr"]
            assert hits[0]["gain"] == pytest.approx(3.0, rel=0.35)
    assert found >= 4                                               # too faint in one exposure, measured in nine
    real = len(STARS) + len(FAINT)
    assert m["detections"]["combined"] <= real + 1                  # no forest of spurious sources
    assert m["detections"]["null_image_spurious"] == 0
    assert en.verdict(m)["accepted"]


@pytest.mark.parametrize("seed", [3, 11, 27])
def test_pure_noise_produces_no_sources(seed):
    exps = [exposure(seed * 10 + i, stars=()) for i in range(6)]
    st = en.combine(exps, RA0, DEC0, FOV)
    m = en.evaluate(st)
    assert m["detections"]["combined"] <= 1 and m["detections"]["new_in_combined"] <= 1
    assert not en.verdict(m)["accepted"]                            # nothing measurable: no claim


def test_signal_from_one_exposure_is_labelled_not_counted_as_a_deep_source():
    transient = [(sky(5, 5), 160.0)]
    exps = [exposure(i + 1, extra=transient if i == 2 else ()) for i in range(6)]
    st = en.combine(exps, RA0, DEC0, FOV)
    m = en.evaluate(st)
    x, y = pix(st, transient[0][0])
    hits = [s for s in m["sources"] if math.hypot(s["x"] - x, s["y"] - y) <= 1.5]
    assert hits and hits[0]["single_exposure_only"]
    assert m["detections"]["single_exposure_only"] >= 1
    assert m["detections"]["new_in_combined"] == 0


def moving_set(n=8, flux=25.0, step_px=4.0, flag_outlier=False):
    exps, centres = [], []
    for i in range(n):
        pos = sky(-14 + step_px * i, -6 + 1.5 * i)
        e = exposure(i + 1, extra=[(pos, flux)], stars=STARS[:4])
        if flag_outlier:
            x, y = (int(round(float(v))) for v in e.image.wcs.all_world2pix(pos[0], pos[1], 0))
            e.image.flags[y - 1:y + 2, x - 1:x + 2] = BIT["OUTLIER"]
        exps.append(e)
        centres.append(pos)
    return exps, centres


def centre_snr(st):
    c = (st.shape[0] - 1) // 2
    m = en.measure_source(st, c, c)
    return m["snr"] if m else None, m


def test_moving_source_needs_a_comoving_stack_and_a_wrong_track_shows_nothing():
    exps, centres = moving_set()
    ra, dec = centres[0]
    follow = en.combine(exps, ra, dec, 0.06, purpose="comoving", centres=centres)
    snr, m = centre_snr(follow)
    assert snr > 6 and m["snr_single_median"] < 5                   # visible only when followed
    assert "TRAYECTORIA PREVISTA" in " ".join(follow.selection["warnings"])
    wrong = [(r, d + 40 / 3600) for r, d in centres]                # same images, displaced track
    control = en.combine(exps, ra, dec + 40 / 3600, 0.06, purpose="comoving", centres=wrong)
    assert centre_snr(control)[0] < 3.5                             # the alignment creates no source
    fixed = en.combine(exps, ra, dec, 0.06)                         # sky-fixed: the body is diluted
    x, y = pix(fixed, centres[0])
    ms = en.measure_source(fixed, round(x), round(y))
    assert ms["snr"] < snr / 2
    with pytest.raises(ValueError):
        en.combine(exps, ra, dec, 0.06, purpose="comoving")


def test_outlier_flag_is_ignored_only_inside_the_moving_target_aperture():
    exps, centres = moving_set(flag_outlier=True)
    stray = exps[0].image
    stray.flags[5, 5] = BIT["OUTLIER"]                              # an unrelated flagged pixel stays masked
    ra, dec = centres[0]
    follow = en.combine(exps, ra, dec, 0.06, purpose="comoving", centres=centres)
    assert all(v == 9 for v in follow.selection["target_outlier_pixels_used"])
    assert centre_snr(follow)[0] > 6
    idx = follow.index[0]
    assert not np.isfinite(follow.data[0][idx == 5 * stray.shape[1] + 5]).any()
    # Sky-fixed (stationary) combination: the strict mask is never relaxed.
    fixed = en.combine(exps, ra, dec, 0.06)
    assert "target_outlier_pixels_used" not in fixed.selection
    x, y = pix(fixed, centres[0])
    assert not np.isfinite(fixed.data[0][int(round(y)), int(round(x))])


# ----------------------------------------------------------------------------- correlated pixels
def test_oversampled_grid_errors_account_for_correlated_pixels():
    exps = [exposure(i + 1, stars=(), dx=0.5 * (i % 2), dy=0.25 * i) for i in range(4)]
    st = en.combine(exps, RA0, DEC0, FOV, oversample=2)
    values, errors, naive = [], [], []
    for yy in range(26, st.shape[0] - 26, 12):
        for xx in range(26, st.shape[1] - 26, 12):
            c = en.aperture_coeffs(st, xx, yy)
            if c is None:
                continue
            v, e = en.linear_stat(st, c)
            values.append(v)
            errors.append(e)
            naive.append(math.sqrt(np.sum(c ** 2 * st.variance)))
    scatter = float(np.std(values))
    assert len(values) > 40
    assert np.mean(errors) == pytest.approx(scatter, rel=0.25)       # exact propagation matches the data
    assert np.mean(naive) < 0.7 * scatter                            # per-pixel variances alone do not
    native = en.combine(exps, RA0, DEC0, FOV)
    assert native.noise["null_scale"] == pytest.approx(1.0, abs=0.1)


def test_null_image_calibrates_underestimated_variances():
    exps = [exposure(i + 1, sigma=1.0) for i in range(6)]
    for e in exps:
        e.image.variance[:] = 0.25                                  # the file claims half the real noise
    st = en.combine(exps, RA0, DEC0, FOV)
    assert st.noise["null_scale"] == pytest.approx(2.0, rel=0.1)
    assert st.noise["scale"] == pytest.approx(2.0, rel=0.1) and st.noise["single"] == pytest.approx(2.0, rel=0.1)
    c = en.aperture_coeffs(st, 40, 40)
    _, err = en.linear_stat(st, c)
    assert err == pytest.approx(2.0 * math.sqrt(np.sum(c ** 2) * 0.25 / 6), rel=0.15)   # never optimistic


def test_exposure_adapter_reads_sequence_and_moving_frames():
    from types import SimpleNamespace
    e = exposure(1)
    frame = SimpleNamespace(image=e.image, record={"collection": "spherex_dr1"}, cutout_url="u", sha256="h")
    a = en.exposure_from(frame)
    assert (a.obs_id, a.collection, a.url, a.sha256, a.detector) == ("SYNTHETIC-1", "spherex_dr1", "u", "h", 2)
    moving = SimpleNamespace(image=e.image, row={"collection": "spherex_qr3", "obs_id": "x"}, cutout_url="v", sha256="k")
    assert en.exposure_from(moving).collection == "spherex_qr3"
    assert en.exposure_from(a) is a and a.provenance()["bunit"] == "MJy/sr"


def test_hot_pixel_with_a_masked_neighbour_cannot_pass_as_a_new_source():
    exps = [exposure(i + 1) for i in range(6)]
    exps[3].image.image[48, 30] = 45.0                              # unflagged single bright pixel
    exps[3].image.flags[48, 31] = BIT["TRANSIENT"]                  # its neighbour is masked in that exposure
    st = en.combine(exps, RA0, DEC0, FOV)
    m = en.evaluate(st)
    hits = [s for s in m["sources"] if math.hypot(s["x"] - 30, s["y"] - 48) <= 1.5]
    assert hits and hits[0]["dominance"] > 0.8 and hits[0]["single_exposure_only"]
    assert m["detections"]["new_in_combined"] == 0
    star = [s for s in m["sources"] if not s["single_exposure_only"]]
    assert len(star) >= len(STARS) and all(s["dominance"] < 0.5 for s in star)
