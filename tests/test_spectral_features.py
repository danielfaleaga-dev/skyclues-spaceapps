"""Comparación de espectros y picos/valles: pruebas SINTÉTICAS del núcleo numérico (sin red).

Todos los espectros de este archivo son SIMULADOS (leyes de potencia, cuerpos negros, ruido
gaussiano de dispersión conocida) sobre la rejilla real de 102 canales del cubo DR1. Validan
los algoritmos; nunca se presentan como observaciones.
"""
import math

import numpy as np
import pytest

from skyclues import spectral_features as sf
from test_spectral_offline import cube  # noqa: F401  (cubo sintético compartido, nunca datos reales)

# First and last central wavelength of each detector, read from the SPECTRAL_CHANNELS table of
# tile 2858 (M101) on 14-11-2026; 17 channels per detector, logarithmically spaced.
EDGES = [(0.753, 1.102), (1.113, 1.631), (1.656, 2.399), (2.445, 3.768), (3.833, 4.405), (4.435, 4.988)]
LAM = np.concatenate([a * (b / a) ** (np.arange(17) / 16) for a, b in EDGES])
DET = np.repeat(np.arange(1, 7), 17)
N = 102
BLANK = (50, 51)                      # 0-based indices of channels 51 and 52
POWER = 100 * LAM ** -2.0             # F_nu of a Rayleigh-Jeans tail (SIMULATED)
C2 = 14387.8                          # µm K


def planck_nu(t):
    return LAM ** -3 / (np.exp(C2 / (LAM * t)) - 1)


def mk(values, label="A", **kw):
    v = np.array(values, float)
    v[list(BLANK)] = np.nan
    return sf.series_from_arrays(v, LAM, label=label, detector=DET, **kw)


def meta(ra, dec, r_ap=2.0, r_in=4.0, r_out=7.0):
    return {"ra": ra, "dec": dec, "r_ap": r_ap, "r_in": r_in, "r_out": r_out, "subpixels": 5, "pixel_arcsec": 12.883,
            "pixel_sr": 3.9e-9, "n_aperture_px": 12.57, "tiles": ["2858"]}


# ----------------------------------------------------------------------------- comparison
def test_identical_spectra():
    c = sf.compare(mk(POWER, "A"), mk(POWER, "B"))
    assert c.comparable and not c.issues
    both = [r for r in c.rows if r["diferencia"] is not None]
    assert len(both) == 100 and all(r["diferencia"] == 0 for r in both)
    assert all(r["relacion"] == 1 for r in both)
    assert c.summary["identicos"] and c.summary["relacion_mediana"] == 1 and c.summary["relacion_dispersion"] == 0


def test_known_difference_and_ratio():
    b = POWER.copy()
    c = sf.compare(mk(2 * b + 3, "A"), mk(b, "B"))
    for r, vb in zip(c.rows, b):
        if r["diferencia"] is not None:
            assert r["diferencia"] == pytest.approx(vb + 3, rel=1e-12)
            assert r["relacion"] == pytest.approx(2 + 3 / vb, rel=1e-12)
    assert c.summary["fraccion_a_mayor"] == 1.0 and c.summary["n_ambos"] == 100


def test_blank_and_missing_channels_are_never_filled():
    a, b = POWER.copy(), POWER.copy()
    a[10] = np.nan
    b[20] = np.inf                                    # not a measurement either
    c = sf.compare(mk(a, "A"), mk(b, "B"))
    by = {r["canal"]: r for r in c.rows}
    for canal in (51, 52, 11, 21):
        assert by[canal]["diferencia"] is None and by[canal]["relacion"] is None
        assert by[canal]["estado_relacion"] == "falta A o B"
    assert by[11]["a"] is None and by[11]["b"] is not None and by[21]["b"] is None
    assert c.summary == {**c.summary, "n_ambos": 98, "n_solo_a": 1, "n_solo_b": 1, "n_ninguno": 2}


def test_negative_values_and_zero_never_divide():
    a = np.linspace(-5, 5, N)
    b = np.zeros(N)
    b[60:] = -2.0
    b[80:] = 4.0
    with np.errstate(all="raise"):                    # any division by zero would raise here
        c = sf.compare(mk(a, "A"), mk(b, "B"))
    by = {r["canal"]: r for r in c.rows}
    assert by[10]["diferencia"] == pytest.approx(a[9]) and by[10]["relacion"] is None      # B = 0
    assert by[70]["relacion"] is None and "≤ 0" in by[70]["estado_relacion"]               # B < 0
    assert by[90]["relacion"] == pytest.approx(a[89] / 4.0)                                # both > 0
    assert all(r["relacion"] is None or (r["a"] > 0 and r["b"] > 0) for r in c.rows)


def test_ratio_withheld_when_denominator_is_inside_reference_scatter():
    ref = np.full(N, 1.0)
    b = np.full(N, 2.0)                               # 2 reference scatters: not a stable denominator
    b[30:] = 10.0
    c = sf.compare(mk(np.full(N, 20.0), "A", ref_scatter=ref), mk(b, "B", ref_scatter=ref))
    by = {r["canal"]: r for r in c.rows}
    assert by[5]["relacion"] is None and "no fiable" in by[5]["estado_relacion"] and by[5]["diferencia"] == 18.0
    assert by[40]["relacion"] == 2.0 and by[40]["estado_relacion"] == "válida"
    no_ref = sf.compare(mk(np.full(N, 20.0), "A"), mk(b, "B"))
    assert no_ref.rows[5]["relacion"] == 10.0 and "sin filtro" in no_ref.rows[5]["estado_relacion"]
    assert not no_ref.summary["filtro_estabilidad"]


def test_different_extractions_or_units_block_the_operations():
    a = mk(POWER, "A", meta=meta(10, 10))
    c = sf.compare(a, mk(POWER, "B", meta=meta(10.01, 10, r_ap=3.0)))
    assert not c.comparable and not c.rows and "r_ap" in c.issues[0]
    c = sf.compare(a, mk(POWER, "B", quantity="pixel", meta=meta(10.01, 10)))
    assert not c.comparable and "Magnitudes distintas" in c.issues[0]
    other = sf.series_from_arrays(POWER, LAM * 1.001, label="B", detector=DET)
    assert "tablas de canales" in sf.compare(a, other).issues[0]


def test_contamination_and_overlap_are_reported():
    pix_deg = 12.883 / 3600
    a = mk(POWER, "A", meta=meta(10.0, 0.0))
    assert any("solapan" in n for n in sf.compare(a, mk(POWER, "B", meta=meta(10.0, 3 * pix_deg))).notes)
    far = sf.compare(a, mk(POWER, "B", meta=meta(10.0, 6 * pix_deg)))
    assert far.comparable and any("anillo de fondo de la otra" in n for n in far.notes)
    assert far.separation_arcsec == pytest.approx(6 * 12.883, abs=0.01)
    assert not sf.compare(a, mk(POWER, "B", meta=meta(10.0, 12 * pix_deg))).notes
    assert any("misma posición" in n for n in sf.compare(a, mk(POWER, "B", meta=meta(10.0, 0.0))).notes)


def test_real_extraction_path_two_positions(cube):
    """Synthetic cube: constant background per plane and +7 MJy/sr in one pixel. A on it, B off it."""
    from skyclues import spectral_cube as sc
    ra_b, dec_b = map(float, cube.tile.wcs.pixel_to_world_values(16, 26))
    spec_a, spec_b = sc.extract_spectrum(*cube.centre), sc.extract_spectrum(ra_b, dec_b)
    c = sf.compare(sf.series_from_spectrum(spec_a, "pixel", "A"), sf.series_from_spectrum(spec_b, "pixel", "B"))
    assert c.comparable and c.unit == "MJy/sr"
    for r in c.rows:
        if r["canal"] in (51, 52):
            assert r["diferencia"] is None and r["estado_a"] == "canal sin datos en DR1"
        else:
            plane = r["canal"] - 1
            assert r["diferencia"] == pytest.approx(7.0) and r["relacion"] == pytest.approx((plane + 17) / (plane + 10))
    f = sf.compare(sf.series_from_spectrum(spec_a, "flux", "A"), sf.series_from_spectrum(spec_b, "flux", "B"))
    omega = spec_a.pixel_solid_angle_sr
    assert f.comparable and f.unit == "mJy" and f.summary["diferencia_mediana"] == pytest.approx(7 * omega * 1e9, rel=1e-6)
    assert f.summary["n_relacion"] == 0                # B is zero after background subtraction: no ratio


# ----------------------------------------------------------------------------- features: exact cases
@pytest.mark.parametrize("sign,kind", [(+1, "pico"), (-1, "valle")])
def test_peak_and_valley_of_known_amplitude(sign, kind):
    y = POWER.copy()
    y[30] += sign * 0.25 * POWER[30]
    (f,) = sf.find_features(mk(y))
    assert (f.kind, f.klass, f.canal, f.n_channels, f.width) == (kind, sf.QUANTIFIABLE, 31, 1, "estrecha")
    assert f.contrast == pytest.approx(sign * 0.25 * POWER[30], rel=1e-9)      # power law: continuum exact
    assert f.relative == pytest.approx(sign * 0.25, rel=1e-9) and f.continuum == pytest.approx(POWER[30], rel=1e-9)
    assert f.lam == pytest.approx(LAM[30]) and f.env_left == [28, 29, 30] and f.env_right == [32, 33, 34]
    assert f.unit == "mJy" and f.degree == 2 and f.detectors == [2]


def test_broad_feature():
    i = np.arange(N)
    depth = 0.3 * np.exp(-0.5 * ((i - 75) / 1.5) ** 2)             # SIMULATED band, sigma 1.5 channels
    (f,) = sf.find_features(mk(POWER * (1 - depth)))
    assert (f.kind, f.canal, f.width, f.klass) == ("valle", 76, "amplia", sf.QUANTIFIABLE)
    assert f.n_channels in (3, 4, 5) and f.relative == pytest.approx(-0.3, abs=0.03)
    assert f.lam_lo < LAM[75] < f.lam_hi and f.lam_centroid == pytest.approx(LAM[75], abs=0.01)


@pytest.mark.parametrize("name,spectrum", [("RJ", POWER), ("lam^-4", LAM ** -4.0), ("lam^+2", LAM ** 2.0),
                                           ("800 K", planck_nu(800)), ("1500 K", planck_nu(1500)),
                                           ("3000 K", planck_nu(3000)), ("5800 K", planck_nu(5800)),
                                           ("plano", np.full(N, 3.0)), ("cero", np.zeros(N))])
def test_smooth_spectra_have_no_features(name, spectrum):
    s = mk(spectrum)
    assert sf.find_features(s) == []
    assert sf.inspect_channel(s, 40).klass == sf.NO_FEATURE


def test_local_continuum_model_error_stays_below_the_relative_floor():
    worst = 0.0
    for t in (800, 1500, 3000, 5800):
        s = mk(planck_nu(t))
        for i in np.flatnonzero(s.measured):
            for h in sf.HALF_WIDTHS:
                if i - h < 0 or i + h >= N:
                    continue
                f = sf._evaluate(s, i - h, i + h, (), {}, origin="x")
                if f.relative is not None:
                    worst = max(worst, abs(f.relative))
    assert worst < 0.006 < sf.MIN_RELATIVE          # measured: 0.51 % (800 K, 9 channels)


def test_strong_peak_does_not_create_false_valleys():
    y = POWER.copy()
    y[30] *= 3
    assert [(f.canal, f.kind) for f in sf.find_features(mk(y))] == [(31, "pico")]


def test_valley_on_a_steep_slope_is_found_although_it_is_not_a_local_minimum():
    y = POWER.copy()
    y[25] *= 0.97                                       # still brighter than the next channel
    assert y[25] > y[26]
    (f,) = sf.find_features(mk(y))
    assert (f.canal, f.kind) == (26, "valle") and f.relative == pytest.approx(-0.03, rel=1e-6)


def test_two_channel_line_is_one_feature():
    y = POWER.copy()
    y[40] *= 1.3
    y[41] *= 1.25
    (f,) = sf.find_features(mk(y))
    assert (f.canal, f.canal_lo, f.canal_hi, f.n_channels) == (41, 41, 42, 2)


# ----------------------------------------------------------------------------- features: noise
def test_pure_noise_is_rarely_labelled():
    """SIMULATED Gaussian noise. Without a background reference the scatter is estimated from a dozen
    residuals per detector, so some fluctuations pass: the measured rates are documented."""
    visible = quantifiable = 0
    for seed in range(120):
        y = POWER + np.random.default_rng(seed).normal(0, 0.5, N)
        fs = sf.find_features(mk(y))
        visible += sum(f.klass == sf.VISIBLE for f in fs)
        quantifiable += sum(f.klass == sf.QUANTIFIABLE for f in fs)
    assert quantifiable <= 5 and visible / 120 <= 0.25           # measured on 300: ~0.015 and ~0.10 per spectrum


def test_pure_noise_with_a_background_reference_is_not_labelled():
    labelled = 0
    for seed in range(120):
        y = POWER + np.random.default_rng(1000 + seed).normal(0, 0.5, N)
        labelled += len(sf.find_features(mk(y, ref_scatter=np.full(N, 0.5))))
    assert labelled <= 2


@pytest.mark.parametrize("amplitude,min_found", [(12, 0.95), (20, 1.0)])
def test_noisy_peak_is_recovered_within_its_reference_scatter(amplitude, min_found):
    sigma, found, pulls = 0.5, 0, []
    for seed in range(60):
        y = POWER + np.random.default_rng(2000 + seed).normal(0, sigma, N)
        y[30] += amplitude * sigma
        hit = [f for f in sf.find_features(mk(y, ref_scatter=np.full(N, sigma))) if f.canal == 31]
        if hit:
            found += 1
            assert hit[0].kind == "pico"
            pulls.append((hit[0].contrast - amplitude * sigma) / (sigma * math.sqrt(1.5)))
    assert found / 60 >= min_found
    assert abs(np.mean(pulls)) < 0.6 and np.std(pulls) < 1.5


def test_faint_fluctuation_is_not_called_quantifiable():
    quantifiable = 0
    for seed in range(60):
        y = POWER + np.random.default_rng(3000 + seed).normal(0, 0.5, N)
        y[30] += 3 * 0.5                                 # a 3-sigma bump
        quantifiable += any(f.klass == sf.QUANTIFIABLE and f.canal == 31
                            for f in sf.find_features(mk(y, ref_scatter=np.full(N, 0.5))))
    assert quantifiable == 0


# ----------------------------------------------------------------------------- features: quality
def test_edges_of_the_spectral_range_are_not_evaluable():
    y = POWER.copy()
    y[0] *= 2
    y[-1] *= 2
    s = mk(y)
    assert sf.find_features(s) == []
    for canal in (1, 102):
        f = sf.measure_interval(s, canal, canal)
        assert f.klass == sf.NOT_EVALUABLE and "borde del intervalo espectral" in f.reasons[0] and f.contrast is None


def test_no_reliable_continuum_next_to_channels_without_data():
    y = POWER.copy()
    y[49] *= 2                                           # channel 50, next to the empty channel 51
    s = mk(y)
    assert sf.find_features(s) == []
    f = sf.inspect_channel(s, 50)
    assert f.klass == sf.NOT_EVALUABLE and "canal 51" in f.reasons[0] and "continuo local fiable" in f.reasons[0]
    g = sf.measure_interval(s, 49, 53)
    assert g.klass == sf.NOT_EVALUABLE and "No se interpolan" in g.reasons[0] and "51, 52" in g.reasons[0]


def test_feature_across_detectors_is_only_visible():
    y = POWER.copy()
    y[17] *= 1.5                                         # channel 18: first of D2, environment reaches D1
    (f,) = sf.find_features(mk(y))
    assert f.klass == sf.VISIBLE and f.detectors == [1, 2] and "detectores D1, D2" in f.limitations[0]


def test_caution_flags_and_coverage_changes_cap_the_class():
    y = POWER.copy()
    y[30] *= 1.5
    caution = np.zeros(N, bool)
    caution[30] = True
    (f,) = sf.find_features(mk(y, caution=caution))
    assert f.klass == sf.VISIBLE and f.caution_channels == [31] and "OVERFLOW" in f.limitations[0]
    nhits = np.full(N, 40.0)
    nhits[30] = 8.0
    (g,) = sf.find_features(mk(y, nhits=nhits))
    assert g.klass == sf.VISIBLE and "Cambio de cobertura" in g.limitations[0]
    (h,) = sf.find_features(mk(y, nhits=np.full(N, 40.0)))
    assert h.klass == sf.QUANTIFIABLE


def test_documented_artefact_is_flagged_not_identified():
    y = POWER.copy()
    i = int(np.argmin(np.abs(LAM - 1.083)))
    y[i] *= 1.5
    (f,) = sf.find_features(mk(y))
    assert any("1.083" in t and "instrumental" in t for t in f.limitations)
    assert not any(w in " ".join(f.limitations + f.reasons).lower() for w in ("detección de", "se identifica"))


def test_linear_fallback_with_non_positive_values():
    y = np.random.default_rng(5).normal(0, 0.01, N)       # background-subtracted sky around zero
    y[30] += 5.0
    f = next(f for f in sf.find_features(mk(y)) if f.canal == 31)
    assert f.kind == "pico" and f.contrast == pytest.approx(5.0, abs=0.05)
    assert f.relative is None or abs(f.relative) > 1
    assert any("Valores ≤ 0" in t for t in f.limitations)


# ----------------------------------------------------------------------------- user selection
def test_manual_interval_matches_the_scan_and_wide_intervals_are_refused():
    y = POWER.copy()
    y[25] *= 1.25                                        # channel 26: its environment stays inside D2
    s = mk(y)
    (auto,) = sf.find_features(s)
    manual = sf.measure_interval(s, 25, 27)
    assert manual.origin == "selección" and manual.canal == 26 and manual.contrast == pytest.approx(auto.contrast)
    assert (manual.trial_lo, manual.trial_hi) == (25, 27) and manual.klass == sf.QUANTIFIABLE
    assert (manual.mask_lo, manual.mask_hi) == (26, 26) and manual.contains(26) and not manual.contains(27)
    wide = sf.measure_interval(s, 20, 40)
    assert wide.klass == sf.NOT_EVALUABLE and "demasiado ancho" in wide.reasons[0]
    with pytest.raises(sf.FeatureInputError):
        sf.measure_interval(s, 0, 5)


def test_inspect_channel():
    y = POWER.copy()
    y[30] *= 1.25
    s = mk(y)
    feats = sf.find_features(s)
    assert sf.inspect_channel(s, 31, feats) is feats[0]
    quiet = sf.inspect_channel(s, 60, feats)
    assert quiet.klass == sf.NO_FEATURE and quiet.continuum == pytest.approx(POWER[59], rel=1e-9)
    assert abs(quiet.contrast) < 1e-9 * POWER[59]


def test_other_features_are_excluded_from_the_environment():
    y = POWER.copy()
    y[30] *= 2.0
    y[33] *= 0.8
    feats = sf.find_features(mk(y))
    assert [(f.canal, f.kind) for f in feats] == [(31, "pico"), (34, "valle")]
    assert feats[0].contrast == pytest.approx(POWER[30], rel=1e-9)
    assert feats[1].contrast == pytest.approx(-0.2 * POWER[33], rel=1e-9) and 31 not in feats[1].env_left


def test_unlabelled_extrema_are_counted_not_labelled():
    y = POWER + np.random.default_rng(7).normal(0, 0.3, N)
    s = mk(y, ref_scatter=np.full(N, 0.3))
    feats = sf.find_features(s)
    assert sf.unlabelled_extrema(s, feats) > 20 and len(feats) <= 1


def test_inputs_are_never_modified_and_results_are_plain_data():
    import json
    y = POWER.copy()
    y[30] *= 1.25
    s = mk(y)
    before = s.value.copy()
    feats = sf.find_features(s)
    sf.compare(s, mk(POWER, "B"))
    assert np.array_equal(s.value, before, equal_nan=True)
    json.dumps([f.to_dict() for f in feats] + [sf.method_summary()])
    assert sf.method_summary()["suavizado"] == "ninguno"


def test_invalid_inputs():
    with pytest.raises(sf.FeatureInputError):
        sf.series_from_arrays([1.0, 2.0])
    with pytest.raises(sf.FeatureInputError):
        sf.series_from_arrays([1.0, 2.0, 3.0], [1.0, 1.0, 2.0])
    with pytest.raises(sf.FeatureInputError):
        sf.series_from_arrays([1.0, 2.0, 3.0], quantity="otra")
