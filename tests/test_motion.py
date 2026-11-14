"""«Buscar algo que se mueve»: SYNTHETIC experiments (offline).

Every image here is simulated and identified as such: point sources are rendered with the
official ePSF taken from a real SPHEREx reference FITS (data/reference, read-only), Gaussian
noise with a known variance, and per-image WCS errors. They test the method (known shifts,
null cases, faint sources, registration, masks), never a scientific claim.
"""
import math
from pathlib import Path

import numpy as np
import pytest
from astropy.wcs import WCS

from skyclues import config, motion

REF_FITS = sorted((config.ROOT / "data" / "reference").glob("*1D2_*.fits"))[0]
RA0, DEC0 = 150.0, 10.0
SCALE = 6.15 / 3600
N = 61


class _Defs:
    def names_bitmask(self, names):
        return 1   # bit 0 = simulated saturation in these tests


class FakeImage:
    """Minimal SpectralImage stand-in (SIMULATED)."""

    def __init__(self, data, var, wcs, mjd, obs_id, detector=2, flags=None, valid=None):
        self.image = data
        self.zodi = np.zeros_like(data)
        self.variance = var
        self.flags = np.zeros(data.shape, np.int64) if flags is None else flags
        self.flag_defs = _Defs()
        self.wcs = wcs
        self.wavelength_um = np.full(data.shape, 1.5)
        self._valid = np.ones(data.shape, bool) if valid is None else valid
        self.path = REF_FITS   # only its official EPSF table is read
        self.meta = {"MJD-AVG": mjd, "DATE-AVG": f"SIM-{mjd:.1f}", "OBSID": obs_id, "DETECTOR": detector,
                     "FINAST": 0, "ASTRONETSOLVED": True, "VERSION": "SIMULATED", "PSF_FWHM": 7.0,
                     "CRPIX1A": -990.0, "CRPIX2A": -990.0}

    def valid(self, mask_classes=None):
        return self._valid

    def detector_offset(self):
        return 1.0 - self.meta["CRPIX1A"] + 1.0, 1.0 - self.meta["CRPIX2A"] + 1.0


class FakeFrame:
    def __init__(self, image):
        self.image, self.record, self.sha256, self.cutout_url = image, {"collection": "SIMULATED"}, "sim", "sim://"


def _wcs(dra_arcsec=0.0, ddec_arcsec=0.0):
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crpix = [(N + 1) / 2, (N + 1) / 2]
    w.wcs.cdelt = [-SCALE, SCALE]
    w.wcs.crval = [RA0 + dra_arcsec / 3600 / math.cos(math.radians(DEC0)), DEC0 + ddec_arcsec / 3600]
    return w


def _offset(ra, dec, dxi, deta):
    return ra + dxi / 3600 / math.cos(math.radians(dec)), dec + deta / 3600


@pytest.fixture(scope="module")
def stars():
    rng = np.random.default_rng(7)
    out = []
    while len(out) < 14:
        dxi, deta = rng.uniform(-150, 150, 2)
        if math.hypot(dxi, deta) < 40 or any(math.hypot(dxi - a, deta - b) < 30 for a, b, _ in out):
            continue
        out.append((dxi, deta, float(rng.uniform(3000, 9000))))
    return out


def simulate(stars, *, target_shift=(0.0, 0.0), target_flux=4000.0, seasons=((0.0, 3), (365.0, 3)),
             wcs_sigma=0.4, seed=0, detector=2, saturate_target=False):
    """SIMULATED season images: stationary stars + one target that moves by target_shift between
    the first and last season. Returns frames, the Gaia-like catalogue and the true target track."""
    rng = np.random.default_rng(seed)
    psf = motion.psf_for(FakeImage(np.zeros((N, N)), np.ones((N, N)), _wcs(), 0, "x"), N / 2, N / 2)
    yy, xx = np.mgrid[0:N, 0:N].astype(float)
    t_last = seasons[-1][0]
    frames = []
    for s_mjd, n in seasons:
        for j in range(n):
            mjd = 60800.0 + s_mjd + j * 2.0
            frac = (mjd - 60800.0) / t_last if t_last else 0.0
            true = _wcs()
            err = rng.normal(0, wcs_sigma, 2)
            data = rng.normal(0.0, 1.0, (N, N)) + 5.0
            for dxi, deta, f in stars:
                x, y = true.all_world2pix(*_offset(RA0, DEC0, dxi, deta), 0)
                data += f * psf(xx - x, yy - y)
            tra, tdec = _offset(RA0, DEC0, target_shift[0] * frac, target_shift[1] * frac)
            x, y = true.all_world2pix(tra, tdec, 0)
            data += target_flux * psf(xx - x, yy - y)
            flags = np.zeros((N, N), np.int64)
            valid = np.ones((N, N), bool)
            if saturate_target:
                core = np.hypot(xx - x, yy - y) <= 1.0
                flags[core] = 1
                valid[core] = False
            # the archive WCS is wrong by `err`: the image claims positions displaced by err
            frames.append(FakeFrame(FakeImage(data, np.ones((N, N)), _wcs(*err), mjd, f"SIM_{s_mjd:.0f}_{j}",
                                              detector=detector, flags=flags, valid=valid)))
    gaia = {"sources": [{"source_id": str(1000 + i), "ra": _offset(RA0, DEC0, a, b)[0], "dec": _offset(RA0, DEC0, a, b)[1],
                         "ref_epoch": 2016.0, "pmra": 0.0, "pmdec": 0.0, "phot_g_mean_mag": 15.0}
                        for i, (a, b, _) in enumerate(stars)],
            "endpoint": "SIMULATED", "table": "SIMULATED", "query": "", "retrieved_utc": "", "sha256": "",
            "truncated": False, "catalogue_epoch": 2016.0}
    return frames, gaia


def test_psf_is_the_official_epsf_and_normalised():
    img = FakeImage(np.zeros((N, N)), np.ones((N, N)), _wcs(), 0, "x")
    psf = motion.psf_for(img, 30, 30)
    assert "EPSF oficial" in psf.description and psf.array is not None
    yy, xx = np.mgrid[-6:7, -6:7].astype(float)
    assert abs(psf(xx, yy).sum() - 1) < 0.02
    assert abs(psf(xx + 0.37, yy - 0.21).sum() - 1) < 0.03   # flux conserved at sub-pixel phases


def test_known_synthetic_shift_is_measured(stars):
    frames, gaia = simulate(stars, target_shift=(6.0, -4.0), seed=1)
    inv = motion.investigate(frames, (RA0, DEC0), gaia=gaia, source_label="SIMULATED")
    r = motion.to_jsonable(inv)
    assert r["outcome"] == motion.MOTION_MEASURED, r["reasons"]
    d = r["displacement"]
    assert abs(d["dxi"] - 6.0) < 3 * d["err_dxi_calibrated"] + 0.05
    assert abs(d["deta"] + 4.0) < 3 * d["err_deta_calibrated"] + 0.05
    assert r["control"]["n"] >= motion.MIN_REFS


@pytest.mark.parametrize("seed", range(6))
def test_stationary_target_is_never_reported_as_motion(stars, seed):
    frames, gaia = simulate(stars, target_shift=(0.0, 0.0), wcs_sigma=0.8, seed=100 + seed)
    r = motion.to_jsonable(motion.investigate(frames, (RA0, DEC0), gaia=gaia))
    assert r["outcome"] == motion.INSUFFICIENT_EVIDENCE
    assert r["displacement"]["significance_calibrated"] < motion.SIGNIFICANCE


def test_errors_are_honest_pulls(stars):
    pulls = []
    for seed in range(8):
        frames, gaia = simulate(stars, target_shift=(2.0, 1.0), target_flux=2500, seed=200 + seed)
        d = motion.to_jsonable(motion.investigate(frames, (RA0, DEC0), gaia=gaia))["displacement"]
        pulls += [(d["dxi"] - 2.0) / d["err_dxi_calibrated"], (d["deta"] - 1.0) / d["err_deta_calibrated"]]
    assert np.std(pulls) < 1.6 and abs(np.mean(pulls)) < 1.0


def test_registration_removes_wcs_errors(stars):
    # SIMULATED archive-WCS errors of σ = 1″ per axis: > 3× the largest offset measured against
    # Gaia in the real investigations (0.32″).
    frames, gaia = simulate(stars, target_shift=(0.0, 0.0), wcs_sigma=1.0, seed=5)
    r = motion.to_jsonable(motion.investigate(frames, (RA0, DEC0), gaia=gaia))
    assert r["outcome"] == motion.INSUFFICIENT_EVIDENCE
    assert r["displacement"]["total_arcsec"] < 0.2
    raw = [math.hypot(*im["wcs_offset_vs_gaia_arcsec"]) for im in r["images"]]
    assert min(raw) > 1.0   # the archive-WCS errors were really there and were removed


def test_wcs_errors_beyond_reference_tolerance_degrade_conservatively(stars):
    # SIMULATED σ = 2″: images whose WCS is > 3″ off lose their references (absolute residual cut)
    # and fall back to the empirical WCS error. The method must not claim motion.
    frames, gaia = simulate(stars, target_shift=(0.0, 0.0), wcs_sigma=2.0, seed=5)
    r = motion.to_jsonable(motion.investigate(frames, (RA0, DEC0), gaia=gaia))
    assert r["outcome"] == motion.INSUFFICIENT_EVIDENCE
    assert any(im["n_refs"] == 0 for im in r["images"])
    assert r["displacement"]["significance_calibrated"] < 1.0


def test_without_gaia_no_measurement_is_claimed(stars):
    frames, _ = simulate(stars, target_shift=(8.0, 0.0), seed=6)
    inv = motion.investigate(frames, (RA0, DEC0), gaia=None)
    assert inv.outcome == motion.INSUFFICIENT_EVIDENCE
    assert "Gaia" in " ".join(inv.reasons)


def test_faint_source_is_measured_with_larger_but_honest_errors(stars):
    # SIMULATED flux 60 (≈ 27–40σ per image with this ePSF and unit noise): still measurable.
    frames, gaia = simulate(stars, target_shift=(6.0, 0.0), target_flux=60.0, seed=7)
    r = motion.to_jsonable(motion.investigate(frames, (RA0, DEC0), gaia=gaia))
    d = r["displacement"]
    assert r["outcome"] == motion.MOTION_MEASURED
    assert abs(d["dxi"] - 6.0) < 3 * d["err_dxi_calibrated"] and abs(d["deta"]) < 3 * d["err_deta_calibrated"]


def test_source_below_detection_threshold_is_never_measured(stars):
    # SIMULATED flux 5 (≈ 2–3σ per image, < 10σ per season): too faint to claim anything.
    frames, gaia = simulate(stars, target_shift=(6.0, 0.0), target_flux=5.0, seed=7)
    inv = motion.investigate(frames, (RA0, DEC0), gaia=gaia)
    assert inv.outcome in (motion.INSUFFICIENT_EVIDENCE, motion.INSUFFICIENT_DATA)
    assert "detecta" in " ".join(inv.reasons) or "temporada" in " ".join(inv.reasons)


def test_single_season_is_insufficient_data(stars):
    frames, gaia = simulate(stars, seasons=((0.0, 3),), seed=8)
    inv = motion.investigate(frames, (RA0, DEC0), gaia=gaia)
    assert inv.outcome == motion.INSUFFICIENT_DATA


def test_one_image_is_insufficient_data(stars):
    frames, gaia = simulate(stars, seasons=((0.0, 1),), seed=9)
    assert motion.investigate(frames, (RA0, DEC0), gaia=gaia).outcome == motion.INSUFFICIENT_DATA


def test_mixed_detectors_are_incompatible(stars):
    a, gaia = simulate(stars, seasons=((0.0, 2),), seed=10, detector=2)
    b, _ = simulate(stars, seasons=((365.0, 2),), seed=11, detector=3)
    assert motion.investigate(a + b, (RA0, DEC0), gaia=gaia).outcome == motion.INCOMPATIBLE


def test_saturated_core_is_reported(stars):
    frames, gaia = simulate(stars, target_shift=(6.0, 0.0), target_flux=20000, seed=12, saturate_target=True)
    r = motion.to_jsonable(motion.investigate(frames, (RA0, DEC0), gaia=gaia))
    assert all(s["saturated_core"] for s in r["seasons"])


def test_catalogue_prediction_never_changes_the_decision(stars):
    from skyclues.astrometry import Astrometry
    frames, gaia = simulate(stars, target_shift=(0.0, 0.0), seed=13)
    wrong = Astrometry("SIMULATED", RA0, DEC0, 2016.0, pmra_masyr=8000.0, pmdec_masyr=0.0)
    with_cat = motion.to_jsonable(motion.investigate(frames, (RA0, DEC0), gaia=gaia, astrometry=wrong))
    without = motion.to_jsonable(motion.investigate(frames, (RA0, DEC0), gaia=gaia))
    assert with_cat["outcome"] == without["outcome"] == motion.INSUFFICIENT_EVIDENCE
    assert with_cat["displacement"] == without["displacement"]
    assert not with_cat["catalogue_comparison"]["consistent_3sigma"]   # measured ≠ predicted, reported only


def test_invalid_inputs():
    with pytest.raises(ValueError):
        motion.investigate([], (400.0, 0.0))
    with pytest.raises(motion.MotionInputError):
        motion.investigate([], (10.0, 0.0), search_radius_arcsec=100)


def test_season_grouping():
    assert motion.seasons([0, 2, 5, 30, 31, 200]) == [[0, 1, 2], [3, 4], [5]]


def test_select_epochs_longest_baseline():
    from types import SimpleNamespace
    recs = [SimpleNamespace(detector=2, mjd_mid=m, access_url=f"u{m}") for m in
            [0, 1, 2, 3, 100, 101, 102, 300, 301, 302, 303, 304]]
    import skyclues.pairing as pairing
    orig = pairing.build_candidates
    try:
        pairing.build_candidates = lambda r, ra, dec, f: [SimpleNamespace(rec=x, margin_px=10 + i) for i, x in enumerate(r)]
        sel = motion.select_epochs(recs, 10.0, 0.0, 2, per_season=2, max_seasons=2)
    finally:
        pairing.build_candidates = orig
    mjds = [c.rec.mjd_mid for c in sel["selected"]]
    assert mjds == [2, 3, 303, 304] and sel["seasons_available"] == 3


def test_reference_fits_untouched():
    import hashlib, json
    man = json.loads((config.ROOT / "data/reference/MANIFEST.json").read_text(encoding="utf-8"))
    entry = man["files"][REF_FITS.name]
    assert hashlib.sha256(REF_FITS.read_bytes()).hexdigest() == entry["sha256"]
