"""Audit corrections checked on authentic SPHEREx FITS (local cache / data/reference).

Deliberate incompatibilities are applied to IN-MEMORY copies of real images
(``dataclasses.replace`` with new arrays or metadata); the FITS files are
never modified and their SHA-256 is checked afterwards. Run: pytest -m network
"""

import json
from dataclasses import replace

import numpy as np
import pytest

from skyclues import archive, config, player
from skyclues.compare import evaluate_pair
from skyclues.geometry import separation_deg
from skyclues.sequence import criterion, evaluate_sequence, load_sequence
from skyclues.targets import WISE0855

pytestmark = pytest.mark.network


def _report(name):
    p = config.RESULTS_DIR / f"{name}.json"
    if not p.exists():
        pytest.skip(f"missing {p.name}")
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def m101():
    return load_sequence(_report("sequence_m101"))


@pytest.fixture(scope="module")
def wise_pm():
    return _report("sequence_wise0855_pm"), load_sequence(_report("sequence_wise0855_pm"))


def _sep(a, b):
    return float(separation_deg(a[0], a[1], b[0], b[1])) * 3600


# ------------------------------------------------------------------ SC-01
def test_wise_example_is_centred_on_the_propagated_position(wise_pm):
    rep, seq = wise_pm
    a = seq.astrometry                                                  # from SIMBAD at search time
    assert seq.target_moves and "SIMBAD" in a.source
    assert (a.pmra_masyr, a.pmdec_masyr, a.parallax_mas) == (WISE0855.pmra_masyr, WISE0855.pmdec_masyr,
                                                             WISE0855.parallax_mas)
    assert _sep((a.ra_deg, a.dec_deg), (WISE0855.ra_deg, WISE0855.dec_deg)) < 1e-6
    assert seq.admissible and not seq.warnings
    assert [c["status"] for c in seq.criteria] == [c["status"] for c in rep["selected"]["criteria"]]
    for i, f in enumerate(seq.frames):
        assert _sep(seq.target_position(i), WISE0855.position_at(f.mjd)) < 1e-6   # one position per epoch
        assert _sep(seq.target_position(i), (seq.ra, seq.dec)) < 10          # centred (< 2 px)
    moved = _sep(seq.target_position(0), seq.target_position(seq.n - 1))
    dt_yr = (seq.frames[-1].mjd - seq.frames[0].mjd) / 365.25
    assert moved == pytest.approx(WISE0855.total_pm_arcsec_yr * dt_yr, rel=0.1)   # ~8 arcsec in one year
    assert "CALCULADA" in player.legend_html(moving=True) and "no una detección" in player.legend_html(moving=True)


def test_old_wise_example_is_annotated_and_still_contains_the_target():
    rep = _report("sequence_wise0855_mwir")
    assert rep["target"]["centre"]["propagated"] is False and "2010.4" in rep["target"]["centre"]["rule"]
    seq = load_sequence(rep)
    off = seq.metrics["target_offset_from_centre_arcsec"]
    assert all(120 < o < 140 for o in off)                       # ~2 arcmin off-centre ...
    assert max(off) < seq.field_deg * 3600 / 2                   # ... but inside the comparison field
    assert seq.admissible and "previous_evaluation" in rep
    # the target wavelength is read at the calculated position, not at the field centre
    from skyclues.compare import lambda_at

    for f in seq.frames:
        assert f.lambda_target_um == lambda_at(f.image, *f.expected_radec)[0]


# ------------------------------------------------------------------ SC-02
def _shift_lambda(frame, n_bw):
    img = frame.image
    return replace(frame, image=replace(img, wavelength_um=img.wavelength_um + n_bw * img.bandwidth_um))


@pytest.mark.parametrize("n_bw, s3, s4", [(0.40, "warn", "warn"), (0.65, "fail", "fail"), (15.43, "fail", "fail")])
def test_deliberate_spectral_mismatch_is_rejected(m101, n_bw, s3, s4):
    frames = list(m101.frames)
    frames[2] = _shift_lambda(frames[2], n_bw)
    seq = evaluate_sequence(frames, m101.ra, m101.dec, m101.field_deg, m101.mask_classes)
    assert criterion(seq, "S3")["status"] == s3 and criterion(seq, "S4")["status"] == s4
    assert seq.admissible == (s4 != "fail")
    a, b = m101.frames[0].image, frames[2].image
    ev = evaluate_pair(a, b, m101.ra, m101.dec, m101.field_deg)
    c = {x["id"]: x["status"] for x in ev.criteria}
    assert c["C3"] == s3 and c["C4"] == s4 and ev.admissible == (s4 != "fail")


def test_mixing_detectors_far_apart_in_wavelength_is_rejected():
    d3 = load_sequence(_report("sequence_wise0855"))            # same field, 2.15 um
    d6 = load_sequence(_report("sequence_wise0855_mwir"))       # same field, 4.82 um
    seq = evaluate_sequence([d3.frames[0], d6.frames[1]], d3.ra, d3.dec, d3.field_deg,
                            astrometry=d3.astrometry)
    assert criterion(seq, "S1")["status"] == "fail"
    assert seq.metrics["lambda_spread_target_bw"] > 40               # ~50 bandwidths apart
    assert criterion(seq, "S3")["status"] == "fail" and criterion(seq, "S4")["status"] == "fail"


def test_stored_options_with_spread_above_warning_are_marked_failed():
    rep = _report("sequence_wise0855_mwir")
    over = [o for o in rep["options"] if o["lambda_spread_common_max_bw"] > config.SPECTRAL_WARN_BW]
    assert over and all(o["status_after_audit"]["S4"] == "fail" for o in over)


# ------------------------------------------------------------------ SC-11
@pytest.mark.parametrize("value, status", [(0, "pass"), (1, "warn"), (2, "fail"), (5, "fail")])
def test_finast_is_enforced(m101, value, status):
    frames = list(m101.frames)
    img = frames[1].image
    frames[1] = replace(frames[1], image=replace(img, meta={**img.meta, "FINAST": value}))
    seq = evaluate_sequence(frames, m101.ra, m101.dec, m101.field_deg)
    s7 = criterion(seq, "S7")
    assert s7["status"] == status and s7["basis"] == "garantía del archivo"
    assert seq.admissible == (status != "fail")
    assert criterion(seq, "S5")["basis"] == "efectiva"


# ------------------------------------------------------------------ SC-04 / SC-06 on real files
def test_real_cutout_truncated_is_rejected(m101):
    data = m101.frames[0].path.read_bytes()
    archive.validate_fits_bytes(data)
    for cut in (1_330_000, (1_330_000 // 2880) * 2880, len(data) - 2880):
        with pytest.raises(archive.CorruptFitsError):
            archive.validate_fits_bytes(data[:cut])


def test_real_headers_get_satellite_halo_from_the_documentation(m101):
    defs = m101.frames[0].image.flag_defs
    assert defs.bits[29] == "SATELLITE_HALO" and "documentación" in defs.source and not defs.conflicts
    assert defs.bitmask(("unusable", "artifact")) & (1 << 29)


def test_fits_files_untouched_after_the_tests(m101, wise_pm):
    for rep, seq in ((_report("sequence_m101"), m101), wise_pm):
        for f, meta in zip(seq.frames, rep["selected"]["frames"]):
            assert archive.sha256(f.path) == meta["sha256"]


# ------------------------------------------------------------------ SC-10
def test_screen_scale_is_reported(m101):
    s = player.screen_scale_arcsec(m101)
    ny, nx = m101.shape
    assert s == pytest.approx(max(nx / (5.6 * 0.66 * 110), ny / (5.0 * 0.85 * 110)) * 6.15, rel=0.03)
    note = player.precision_note(m101)
    assert f"{s:.1f}″" in note and "PSF" in note and "remuestreo" in note
    assert "exacta" not in player.legend_html(geometry="exact")
