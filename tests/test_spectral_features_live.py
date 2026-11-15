"""Comparación A/B y picos/valles con datos REALES del cubo DR1 (IRSA; solo rangos de bytes).

M101: A = núcleo, B = región H II gigante NGC 5461. La validación completa e independiente
(Photutils, NumPy) está en scripts/validate_spectral_features.py; aquí se fija lo esencial.
"""
import math

import numpy as np
import pytest

from skyclues import spectral_cube as sc, spectral_features as sf

pytestmark = pytest.mark.network

A = (210.802429, 54.34875)
B = (210.923546, 54.319916)


@pytest.fixture(scope="module")
def spectra():
    return sc.extract_spectrum(*A), sc.extract_spectrum(*B)


def test_two_real_positions_are_extracted_identically_and_compared(spectra):
    spec_a, spec_b = spectra
    sa, sb = sf.series_from_spectrum(spec_a, "flux", "A"), sf.series_from_spectrum(spec_b, "flux", "B")
    c = sf.compare(sa, sb)
    assert c.comparable and c.unit == "mJy" and c.separation_arcsec == pytest.approx(275, abs=2)
    assert spec_a.aperture == spec_b.aperture and spec_a.pixel_solid_angle_sr == spec_b.pixel_solid_angle_sr
    assert c.summary["n_ambos"] == 100 and c.summary["n_ninguno"] == 2          # channels 51 and 52: no data
    by = {r["canal"]: r for r in c.rows}
    assert by[51]["diferencia"] is None and by[52]["relacion"] is None and by[51]["estado_a"] == "canal sin datos en DR1"
    for r in c.rows:                                                            # exact arithmetic, valid domain only
        if r["diferencia"] is not None:
            assert r["diferencia"] == r["a"] - r["b"]
        if r["relacion"] is not None:
            assert r["a"] > 0 and r["b"] > 0 and r["relacion"] == r["a"] / r["b"]
    assert c.summary["fraccion_a_mayor"] == 1.0                                 # the nucleus is brighter everywhere


def test_peak_near_3p3_um_is_quantifiable_in_b_and_absent_in_a(spectra):
    spec_a, spec_b = spectra
    sa, sb = sf.series_from_spectrum(spec_a, "flux", "A"), sf.series_from_spectrum(spec_b, "flux", "B")
    an_a, an_b = sf.analyse(sa), sf.analyse(sb)
    canal = int(sb.canal[int(np.flatnonzero((sb.lam_min <= 3.30) & (3.30 <= sb.lam_max))[0])])
    fb = sf.inspect_channel(sb, canal, an_b.features, an_b.scatter)
    assert (fb.kind, fb.klass, fb.canal) == ("pico", sf.QUANTIFIABLE, 63) and fb.relative > 1.0
    assert fb.detectors == [4] and not fb.caution_channels
    # independent refit of the local continuum (numpy.polyfit, ln–ln, degree 2, three channels per side)
    env = [c - 1 for c in fb.env_left + fb.env_right]
    cont = math.exp(np.polyval(np.polyfit(np.log(sb.lam[env]), np.log(sb.value[env]), 2), math.log(sb.lam[62])))
    assert fb.continuum == pytest.approx(cont, rel=1e-9) and fb.contrast == pytest.approx(sb.value[62] - cont, rel=1e-9)
    fa = sf.measure_interval(sa, fb.trial_lo, fb.trial_hi, an_a.features, an_a.scatter)
    assert fa.klass == sf.NO_FEATURE and abs(fa.ratio) < sf.Q_VISIBLE
    assert not an_a.features                                                    # nothing is labelled in the nucleus
    assert {f.canal for f in an_b.features if f.klass == sf.QUANTIFIABLE} >= {40, 63, 76, 93}


def test_repeated_extraction_is_reproducible_and_local(spectra):
    sc.io_stats(reset=True)
    again = sc.extract_spectrum(*B)
    assert sc.io_stats()["requests"] == 0 and again.rows == spectra[1].rows
