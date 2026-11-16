"""Intérprete espectral V1: registro de referencias y motor de compatibilidad.

Pruebas de coherencia funcional (no es una validación ciega nueva):

* SINTÉTICAS: geometría real de los 102 canales (λ, WL_MIN, WL_MAX, R y detector leídos del resultado congelado
  de V03/C05) con valores SIMULADOS. Nunca se presentan como observaciones.
* REALES: los espectros congelados de V02/V03 (sin modificarlos) y M101/NGC 5461 desde la caché local del cubo.
"""
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from skyclues import spectral_features as sf, spectral_interpreter as si, spectral_references as sr

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY = json.loads((ROOT / "results/blind_v03/C05/resultados.json").read_text(encoding="utf-8"))["espectro"]
LAM = np.array([r["lambda_um"] for r in GEOMETRY])
LMIN = np.array([r["lambda_min_um"] for r in GEOMETRY])
LMAX = np.array([r["lambda_max_um"] for r in GEOMETRY])
DET = np.array([r["detector"] for r in GEOMETRY])
RES = {int(r["canal"]): float(r["R"]) for r in GEOMETRY}
BLANK = (50, 51)


def mk(values, label="A", caution=None, ref=1.0):
    """SIMULATED spectrum on the real channel grid; reference scatter fixed (descriptive threshold)."""
    v = np.array(values, float)
    v[list(BLANK)] = np.nan
    return sf.series_from_arrays(v, LAM, label=label, lam_min=LMIN, lam_max=LMAX, detector=DET,
                                 ref_scatter=np.full(102, ref), caution=caution)


BASE = 100.0 * LAM ** -1.0                           # smooth continuum (SIMULATED)


def bump(ch, factor, base=BASE, width=1):
    v = base.copy()
    for c in range(ch, ch + width):
        v[c - 1] *= factor
    return v


def feature_at(s, canal):
    an = sf.analyse(s)
    return sf.inspect_channel(s, canal, an.features, an.scatter)


def ids(ms):
    return [m.reference.id for m in ms]


# ----------------------------------------------------------------------------- registry
def test_library_is_versioned_and_every_reference_has_a_verifiable_source():
    assert sr.LIBRARY_VERSION.startswith("skyclues-referencias 1.0")
    assert len({r.id for r in sr.REFERENCES}) == len(sr.REFERENCES) == 6
    for r in sr.REFERENCES:
        assert r.sources and all(s.url.startswith("https://") and s.citation and s.used_for for s in r.sources)
        assert r.nature in (sr.EMISSION, sr.ABSORPTION) and r.form in (sr.BAND, sr.LINE)
        assert r.lam_range_um[0] <= r.lam_um <= r.lam_range_um[1]
        assert r.conditions and r.confounders and r.plain and r.scientific
        assert r.to_dict()["fuentes"]
    assert {r.id for r in sr.REFERENCES if r.needs_absorption_model} == {"h2o_hielo_3p0", "co2_hielo_4p27",
                                                                           "co_hielo_4p67"}


def test_hydrogen_wavelengths_agree_with_the_rydberg_formula():
    """NIST Ritz values against the Rydberg formula with the reduced mass of hydrogen (independent check)."""
    r_h = 109737.31568 / (1 + 1 / 1836.15267)                       # cm⁻¹
    lam = lambda lo, up: 1e4 / (r_h * (1 / lo ** 2 - 1 / up ** 2))    # noqa: E731  µm, vacuum
    assert sr.BY_ID["hi_pfund_delta"].lam_um == pytest.approx(lam(5, 9), abs=1e-4)
    assert sr.BY_ID["hi_brackett_alpha"].lam_um == pytest.approx(lam(4, 5), abs=1e-4)


def test_documented_widths_are_converted_not_invented():
    assert sr.cm1_to_um(390, 3.0) == pytest.approx(0.351, abs=1e-3)
    assert sr.BY_ID["co2_hielo_4p27"].fwhm_um == pytest.approx(4.27 ** 2 * 20e-4)
    assert sr.BY_ID["pah_3p3"].fwhm_um is None and sr.BY_ID["hi_pfund_delta"].fwhm_um is None
    assert 1e4 / 2141.3 == pytest.approx(sr.BY_ID["co_hielo_4p67"].lam_um, abs=1e-3)


def test_redshift_only_inside_the_d25_isophote_of_a_curated_galaxy():
    m51a = sr.redshift_at(202.4695833, 47.1952778)                  # V03/C14: nucleus of M51a
    assert (m51a.z, m51a.source, m51a.object_name) == (0.001745, "ned", "M51a (NGC 5194)")
    m51b = sr.redshift_at(202.49808, 47.26617)                       # centre of M51b, also inside M51a's D25
    assert m51b.z == 0.001518 and m51b.object_name.startswith("M51b")
    assert not sr.redshift_at(202.47, 47.45).known                   # 15′ north: outside both
    assert sr.redshift_at(233.7379167, 23.5030556).z == 0.018398     # V03/C05: Arp 220
    m82 = next(g for g in sr.GALAXIES if g.name.startswith("M82"))
    t = math.radians(m82.pa_deg)
    along = (m82.ra_deg + 200 * math.sin(t) / 3600 / math.cos(math.radians(m82.dec_deg)),
             m82.dec_deg + 200 * math.cos(t) / 3600)
    across = (m82.ra_deg + 200 * math.cos(t) / 3600 / math.cos(math.radians(m82.dec_deg)),
              m82.dec_deg - 200 * math.sin(t) / 3600)
    assert m82.inside(*along)[0] and not m82.inside(*across)[0]     # ellipse, not a circle
    assert not sr.redshift_at(60.81, 51.34).known and "never estimated" in sr.UNKNOWN_Z.note
    with pytest.raises(ValueError):
        sr.user_redshift(-1.5)


# ----------------------------------------------------------------------------- synthetic: emission
def test_quantifiable_peak_at_3p3_keeps_pah_and_pfund_delta_without_choosing():
    s = mk(bump(63, 1.5))
    f = feature_at(s, 63)
    assert (f.kind, f.klass, f.canal) == ("pico", sf.QUANTIFIABLE, 63)
    it = si.interpret(s, f, resolution=RES)
    assert it.verdict == si.SEVERAL and ids(it.matches) == ["pah_3p3", "hi_pfund_delta"]
    assert all(m.status == si.MATCH and m.predicted_channels == (63,) for m in it.matches)
    lo, hi = it.matches[0].z_range                                   # unknown z: the range where it would hold
    assert lo < 0 < hi and hi == pytest.approx((3.342 + 0.001) / 3.28 - 1, abs=1e-4)
    assert any("does not separate them" in b for b in it.blockers)
    assert not it.redshift.known and "z = 0" in " ".join(it.limitations)
    assert it.observation["R"] == 35.0 and it.observation["R_del_fits"]


def test_visible_peak_is_only_insufficiently_supported():
    s = mk(bump(63, 1.25))                                           # contrast ≈ 6 × the reference scatter
    f = feature_at(s, 63)
    assert f.klass == sf.VISIBLE
    it = si.interpret(s, f, resolution=RES)
    assert it.verdict == si.WEAK and {m.status for m in it.matches} == {si.MATCH_WEAK}
    assert any("not a statistical significance" in b for b in it.blockers)


def test_single_brackett_alpha_is_one_compatible_reference():
    s = mk(bump(75, 1.5))
    it = si.interpret(s, feature_at(s, 75), resolution=RES)
    assert it.verdict == si.COMPATIBLE and ids(it.matches) == ["hi_brackett_alpha"]
    assert it.window.margin_lo_um == 0.010                           # D5: documented band-centre accuracy


def test_known_redshift_is_applied_and_moves_the_reference():
    z = sr.user_redshift(0.018398)
    s = mk(bump(75, 1.5))
    it = si.interpret(s, feature_at(s, 75), redshift=z, resolution=RES)
    assert it.verdict == si.NONE and not it.matches                  # 4.052 × 1.0184 = 4.127 µm: channel 77/78
    s2 = mk(bump(77, 1.5))
    it2 = si.interpret(s2, feature_at(s2, 77), redshift=z, resolution=RES)
    m = it2.matches[0]
    assert it2.verdict == si.COMPATIBLE and m.lam_obs_um == pytest.approx(4.052269 * 1.018398, rel=1e-12)
    assert m.z_range is None and m.lam_rest_um == 4.052269


def test_unknown_redshift_is_never_estimated_from_a_coincidence():
    s = mk(bump(64, 1.5))                                            # 3.383 µm: PAH only if z ≈ 0.02–0.05
    it = si.interpret(s, feature_at(s, 64), resolution=RES)
    assert it.verdict == si.NONE and not it.redshift.known
    assert {m.status for m in it.others} == {si.ADJACENT} and all(m.z_range is None for m in it.others)
    assert "z" not in json.dumps([m.to_dict()["z_compatible"] for m in it.others]).replace("null", "")


# ----------------------------------------------------------------------------- synthetic: absorption
def test_isolated_minimum_is_not_water_ice_and_a_broad_one_is_only_orientative():
    s = mk(bump(60, 0.7))
    it = si.interpret(s, feature_at(s, 60), resolution=RES)
    assert it.verdict == si.NONE and [m.status for m in it.others] == [si.WIDTH]
    assert "isolated minimum" in it.others[0].reasons[0]
    wide = BASE.copy()
    wide[57:62] *= np.array([0.9, 0.8, 0.7, 0.8, 0.9])               # SIMULATED broad depression, channels 58-62
    s2 = mk(wide)
    f2 = feature_at(s2, 60)
    assert (f2.kind, f2.width) == ("valle", "amplia")
    it2 = si.interpret(s2, f2, resolution=RES)
    assert it2.verdict == si.WEAK and ids(it2.matches) == ["h2o_hielo_3p0"]
    assert it2.matches[0].status == si.MATCH_WEAK and "orientativa" in it2.matches[0].reasons[-1]


def test_ice_wavelength_with_a_peak_is_of_the_opposite_nature():
    s = mk(bump(81, 1.5))                                            # 4.257 µm, peak where CO2 ice absorbs
    it = si.interpret(s, feature_at(s, 81), resolution=RES)
    assert it.verdict == si.NONE and [(m.reference.id, m.status) for m in it.others] == [
        ("co2_hielo_4p27", si.OPPOSITE)]


def test_quantifiable_co2_valley_is_never_more_than_insufficient():
    s = mk(bump(81, 0.6))
    f = feature_at(s, 81)
    assert f.klass == sf.QUANTIFIABLE
    it = si.interpret(s, f, resolution=RES)
    assert it.verdict == si.WEAK and ids(it.matches) == ["co2_hielo_4p27"]


# ----------------------------------------------------------------------------- synthetic: limits
def test_feature_outside_the_library_has_no_compatible_reference():
    s = mk(bump(40, 1.5))                                            # 1.876 µm (not in the V1 library)
    it = si.interpret(s, feature_at(s, 40), resolution=RES)
    assert it.verdict == si.NONE and not it.matches and not it.others
    assert any("does not exclude other substances" in x for x in it.limitations)


def test_channels_without_data_are_not_evaluable_and_absence_is_not_concluded():
    v = bump(63, 1.5)
    v[60:66] = np.nan                                                # channels 61-66 without value
    s = mk(v)
    f = sf.measure_interval(s, 62, 64)
    it = si.interpret(s, f, resolution=RES)
    assert it.verdict == si.NOT_EVALUABLE and not it.matches
    cov = {c.reference.id: c for c in si.survey(s)}
    assert cov["pah_3p3"].status == si.COV_NO_DATA and "neither presence nor absence" in cov["pah_3p3"].reasons[0]
    assert cov["hi_brackett_alpha"].status == si.COV_NO_SIGNAL
    assert "No demuestra ausencia" in cov["hi_brackett_alpha"].reasons[0]


def test_step_between_detectors_is_not_a_substance():
    v = BASE.copy()
    v[68:] *= 1.6                                                    # SIMULATED calibration step D4 -> D5
    s = mk(v)
    an = sf.analyse(s)
    edge = [f for f in an.features if 66 <= f.canal <= 71]
    assert edge and len(edge[0].detectors) == 2
    it = si.interpret(s, edge[0], resolution=RES)
    assert it.verdict == si.NOT_EVALUABLE and "no son sustancias" in it.blockers[0]


def test_caution_in_the_environment_caps_the_verdict():
    caution = np.zeros(102, bool)
    caution[[73, 76]] = True                                         # channels 74 and 77 (environment of 75)
    s = mk(bump(75, 1.5), caution=caution)
    f = feature_at(s, 75)
    assert f.klass == sf.QUANTIFIABLE
    it = si.interpret(s, f, resolution=RES)
    assert it.verdict == si.WEAK and any("surroundings" in b for b in it.blockers)


def test_spectrum_without_features_gives_nothing_to_interpret():
    s = mk(BASE)
    an = sf.analyse(s)
    assert not an.features and si.interpret_features(s, an.features) == []
    assert si.interpret(s, None).verdict == si.NOT_EVALUABLE
    flat = si.interpret(s, sf.inspect_channel(s, 63, an.features, an.scatter), resolution=RES)
    assert flat.verdict == si.NOT_EVALUABLE and ids(flat.orientative) == ["pah_3p3", "hi_pfund_delta"]
    assert {c.status for c in si.survey(s, an.features, an.scatter)} == {si.COV_NO_SIGNAL}


def test_without_the_fits_resolution_it_is_estimated_and_declared():
    s = mk(bump(63, 1.5))
    it = si.interpret(s, feature_at(s, 63))
    assert not it.observation["R_del_fits"] and "estimated" in " ".join(it.limitations)


def test_output_is_deterministic_and_serialisable():
    s = mk(bump(63, 1.5))
    a = json.dumps(si.interpret(s, feature_at(s, 63), resolution=RES).to_dict(), sort_keys=True)
    b = json.dumps(si.interpret(s, feature_at(s, 63), resolution=RES).to_dict(), sort_keys=True)
    assert a == b and "probabilit" not in a.lower().replace("no probabilities are given", "")
    assert si.method_summary()["motor"] == si.ENGINE_VERSION


# ----------------------------------------------------------------------------- real spectra (frozen, unmodified)
def frozen(rel, label="A"):
    j = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    scale = j["escala_px_arcsec"]
    spec = SimpleNamespace(rows=j["espectro"], n_aperture_px=j["n_apertura_px"],
                           pixel_solid_angle_sr=(scale / 206264.80624709636) ** 2,
                           aperture=SimpleNamespace(**j["apertura_px"]), ra=j["ra_deg"], dec=j["dec_deg"], subpixels=5,
                           pixel_scale_arcsec=scale, n_annulus_px=j["n_anillo_px"], tiles=[])
    s = sf.series_from_spectrum(spec, "flux", label)
    an = sf.analyse(s)
    # the analyzer reproduces the frozen features exactly: the interpreter reads the same results
    assert [(f.kind, f.klass, f.canal, f.canal_lo, f.canal_hi) for f in an.features] == [
        (f["kind"], f["klass"], f["canal"], f["canal_lo"], f["canal_hi"]) for f in j["caracteristicas"]]
    kw = dict(redshift=sr.redshift_at(j["ra_deg"], j["dec_deg"]), resolution=si.resolution_of(spec),
              aperture_arcsec=j["apertura_px"]["r_ap"] * scale)
    return s, an, kw


def test_arp220_redshift_is_applied_and_both_hypotheses_remain_unconfirmed():
    s, an, kw = frozen("results/blind_v03/C05/resultados.json")
    assert kw["redshift"].z == 0.018398
    it = si.interpret(s, sf.inspect_channel(s, 63, an.features, an.scatter), **kw)
    assert it.verdict == si.WEAK and ids(it.matches) == ["pah_3p3", "hi_pfund_delta"]
    pah, pfd = it.matches
    assert pah.lam_obs_um == pytest.approx(3.29 * 1.018398) and pfd.lam_obs_um == pytest.approx(3.296991 * 1.018398)
    assert pah.predicted_channels == (64,) and it.window.canal_lo == 63 and it.window.canal_hi == 64
    assert "radio 26″" in " ".join(it.limitations)


def test_m51_small_redshift_and_the_aperture_is_not_the_nucleus():
    s, an, kw = frozen("results/blind_v03/C14/resultados.json")
    assert kw["redshift"].object_name == "M51a (NGC 5194)"
    it = si.interpret(s, an.features[0], **kw)
    assert it.verdict == si.WEAK and ids(it.matches) == ["pah_3p3", "hi_pfund_delta"]
    assert it.matches[0].lam_obs_um - 3.29 == pytest.approx(3.29 * 0.001745)       # < 0.006 µm: same channel 63
    assert "not a specific object" in " ".join(it.limitations)
    b = sr.redshift_at(202.49808, 47.26617)                                     # a B point on M51b
    assert b.z != kw["redshift"].z


def test_tw_hya_detector_step_and_flags_prevent_conclusions():
    s, an, kw = frozen("results/blind_v03/C12/resultados.json")
    assert not kw["redshift"].known
    by = {f.canal: si.interpret(s, f, **kw) for f in an.features}
    assert by[69].verdict == si.NOT_EVALUABLE and not by[69].matches               # D4/D5 step at 3.83 µm
    assert by[75].verdict == si.NOT_EVALUABLE and ids(by[75].matches) == ["hi_brackett_alpha"]
    assert by[75].matches[0].status == si.MATCH_WEAK and any("OVERFLOW" in b for b in by[75].blockers)
    assert by[92].verdict == si.NONE


@pytest.mark.parametrize("rel", ["results/blind_v02/T01/resultados.json", "results/blind_v02/T02/resultados.json"])
def test_ngc7027_and_m82_without_coverage_at_3p3_are_not_evaluable(rel):
    s, an, kw = frozen(rel)
    it = si.interpret(s, sf.inspect_channel(s, 63, an.features, an.scatter), **kw)
    assert it.verdict == si.NOT_EVALUABLE and not it.matches
    survey = {c.reference.id: c for c in si.survey(s, an.features, an.scatter, redshift=kw["redshift"])}
    assert survey["pah_3p3"].status == survey["h2o_hielo_3p0"].status == si.COV_NO_DATA
    assert "NHITS = 0" in survey["pah_3p3"].reasons[0]                   # the cause in words, not an internal code
    assert "no_data_aperture" not in survey["pah_3p3"].reasons[0]


def test_m82_peak_at_4p67_is_not_co_ice():
    s, an, kw = frozen("results/blind_v02/T02/resultados.json")
    it = si.interpret(s, an.features[0], **kw)
    assert it.verdict == si.NONE and [(m.reference.id, m.status) for m in it.others] == [("co_hielo_4p67", si.OPPOSITE)]


@pytest.fixture(scope="module")
def m101():
    """M101 nucleus (A) and NGC 5461 (B) from the local cube cache; skipped if the cache lacks them."""
    from skyclues import archive, spectral_cube as sc
    real = archive.requests.sessions.Session.request

    def no_network(*a, **k):
        raise RuntimeError("sin red")
    archive.requests.sessions.Session.request = no_network
    try:
        return sc.extract_spectrum(210.802429, 54.34875), sc.extract_spectrum(210.923546, 54.319916)
    except Exception as err:  # noqa: BLE001
        pytest.skip(f"Caché del cubo de M101 no disponible: {err}")
    finally:
        archive.requests.sessions.Session.request = real


def test_m101_ngc5461_3p3_is_compatible_but_not_confirmed(m101):
    spec_a, spec_b = m101
    out = {}
    for spec, k in ((spec_a, "A"), (spec_b, "B")):                  # each original spectrum on its own
        s = sf.series_from_spectrum(spec, "flux", k)
        an = sf.analyse(s)
        out[k] = si.interpret(s, sf.inspect_channel(s, 63, an.features, an.scatter),
                              redshift=sr.redshift_at(spec.ra, spec.dec), resolution=si.resolution_of(spec),
                              aperture_arcsec=spec.aperture.r_ap * spec.pixel_scale_arcsec)
    b = out["B"]
    assert b.redshift.z == 0.000804 and b.feature.klass == sf.QUANTIFIABLE
    assert b.verdict == si.SEVERAL and ids(b.matches) == ["pah_3p3", "hi_pfund_delta"]
    assert out["A"].verdict == si.NOT_EVALUABLE                     # nothing marked in the nucleus at 3.3 µm
