"""Atlas and the common region state (name / coordinates / atlas → Time or Spectrum Explorer).

The Aladin Lite component itself runs in the browser (verified in a real browser, see
PROJECT_STATE). Here its selection event is SIMULATED by replacing the component with a
stub that returns the event the JS sends ({ra, dec, fov, view, layer}).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from skyclues import atlas, navigation, references

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class Params(dict):
    def update(self, d):   # st.query_params-like
        super().update({k: str(v) for k, v in d.items()})


# ----------------------------------------------------------------------------- common region (pure)
def test_region_from_url_parameters_first():
    r = navigation.current_region({"shared_region": {"ra": 1, "dec": 2, "fov": .1}},
                                  {"ra": "83.8221", "dec": "-5.3911", "fov": "0.2"})
    assert (r["ra"], r["dec"], r["fov"]) == (pytest.approx(83.8221), pytest.approx(-5.3911), 0.2)


def test_region_falls_back_to_open_sequence_then_m101():
    assert navigation.current_region({"shared_region": {"ra": 1, "dec": 2, "fov": .1}}, {})["ra"] == 1
    assert navigation.current_region({}, {}) == navigation.DEFAULT_REGION
    assert navigation.current_region({}, {"ra": "nan", "dec": "0"}) == navigation.DEFAULT_REGION


def test_set_region_validates_and_resets_every_coordinate_field():
    state = {k: 1 for k in navigation.TIME_KEYS + navigation.SPECTRUM_KEYS + navigation.LOCATE_KEYS}
    params = Params()
    navigation.set_region(state, params, 83.8221, -5.3911, 0.2, source="Atlas")
    assert not set(state) & set(navigation.TIME_KEYS + navigation.SPECTRUM_KEYS + navigation.LOCATE_KEYS)
    assert params == {"ra": "83.822100", "dec": "-5.391100", "fov": "0.2"}
    r = navigation.current_region(state, params)
    assert r["source"] == "Atlas" and r["astrometry"] is None


@pytest.mark.parametrize("ra,dec,fov", [(360, 0, .1), (10, 91, .1), (10, 0, 0.6), (10, 0, 0.01), (float("nan"), 0, .1)])
def test_set_region_rejects_invalid_regions(ra, dec, fov):
    with pytest.raises(ValueError):
        navigation.set_region({}, Params(), ra, dec, fov, source="Atlas")


def test_region_source_only_applies_to_the_same_centre():
    state, params = {}, Params()
    navigation.set_region(state, params, 10, 0, .1, source="Atlas", astrometry={"name": "X"})
    params.update({"ra": "11", "dec": "0"})
    assert "astrometry" not in navigation.current_region(state, params)


# ----------------------------------------------------------------------------- layers and provenance
def test_layers_identify_mission_product_and_are_official_hips():
    ids = [L["id"] for L in atlas.LAYERS]
    assert len(ids) == len(set(ids))
    for L in atlas.LAYERS:
        assert L["url"].startswith("https://irsa.ipac.caltech.edu/data/hips/")
        assert all(L[k] for k in ("mission", "product", "bands", "epoch", "note"))
        assert "SPHEREx" not in L["mission"]          # no SPHEREx map is presented as a layer
    assert {"allwise", "w1", "w2"} <= set(ids) and "2mass" in ids
    assert atlas.SPHEREX_HIPS["release"] and "combinado" in atlas.SPHEREX_HIPS["kind"]


def test_presets_respect_explorer_limits():
    from skyclues import config
    assert all(config.FOV_MIN_DEG <= a / 60 <= config.FOV_MAX_DEG for a in atlas.FOV_PRESETS_ARCMIN)


def test_object_position_now_uses_catalogue_motion():
    from skyclues.astrometry import Astrometry
    still = Astrometry("A", 10.0, 0.0, 2000.0)
    assert atlas.object_position_now(still) == (10.0, 0.0)
    moving = Astrometry("B", 10.0, 0.0, 2000.0, pmra_masyr=0.0, pmdec_masyr=10000.0)
    assert atlas.object_position_now(moving)[1] > 0.05     # 10″/yr over > 26 yr


# ----------------------------------------------------------------------------- app (AppTest)
def _app(monkeypatch, pick=None, **state):
    calls = []

    def fake_atlas(**kw):   # SIMULATED Aladin component
        calls.append(kw["data"])
        return SimpleNamespace(select=pick)
    monkeypatch.setattr(atlas, "ATLAS", fake_atlas)
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in state.items():
        at.session_state[k] = v
    return at, calls


def test_locate_has_three_methods_and_atlas_is_not_an_explorer(monkeypatch):
    at, calls = _app(monkeypatch)
    at.run()
    assert not at.exception
    assert at.radio(key="locate_mode").options == ["Por nombre", "Coordenadas", "Atlas"]
    assert at.radio(key="explorer").options == ["Time Explorer · tiempo", "Spectrum Explorer · longitud de onda"]
    at.radio(key="locate_mode").set_value("Atlas").run()
    assert not at.exception and calls
    d = calls[-1]
    assert (d["ra"], d["dec"], d["fov"]) == (pytest.approx(210.802429), pytest.approx(54.34875), 0.1)
    assert d["fov_max"] == 0.5 and d["aladin"] == references.ALADIN_JS


@pytest.mark.parametrize("explorer,check", [
    ("atlas_to_time", lambda at: (at.number_input(key="ra_in").value, at.number_input(key="dec_in").value)),
    ("atlas_to_spectrum", lambda at: (at.session_state["sx_ra"], at.session_state["sx_dec"]))])
def test_atlas_selection_opens_explorer_with_exact_coordinates(monkeypatch, explorer, check):
    pick = {"ra": 83.8221, "dec": -5.3911, "fov": 0.2, "view": 0.5, "layer": "2mass"}
    at, _ = _app(monkeypatch, pick, locate_mode="Atlas")
    at.run()
    assert not at.exception
    assert any("Región seleccionada en el atlas" in s.value for s in at.success)
    assert at.query_params["ra"] == "83.822100" and at.query_params["fov"] == "0.2"
    at.button(key=explorer).click().run()
    assert not at.exception
    ra, dec = check(at)
    assert ra == pytest.approx(83.8221, abs=1e-6) and dec == pytest.approx(-5.3911, abs=1e-6)


def test_oversized_atlas_selection_is_rejected_not_cropped(monkeypatch):
    at, _ = _app(monkeypatch, {"ra": 83.8, "dec": -5.4, "fov": 1.5, "view": 2.0, "layer": "2mass"}, locate_mode="Atlas")
    at.run()
    assert not at.exception
    assert any("Selección no válida" in e.value for e in at.error)
    assert "sky_region" not in at.session_state


def test_named_object_astrometry_kept_only_on_its_centre(monkeypatch):
    from skyclues.astrometry import Astrometry
    a = Astrometry("Barnard's star", 269.452075, 4.693391, 2000.0, pmra_masyr=-801.551, pmdec_masyr=10362.394,
                   parallax_mas=547.45, source="SIMBAD")
    ra, dec = atlas.object_position_now(a)
    marker = {"ra": ra, "dec": dec, "label": a.name, "note": "", "astrometry": a.to_dict()}
    view = {"ra": ra, "dec": dec, "fov": 0.1, "nonce": 1, "marker": marker}
    at, _ = _app(monkeypatch, {"ra": ra, "dec": dec, "fov": 0.1, "view": .3, "layer": "2mass"},
                 locate_mode="Atlas", atlas_view=view)
    at.run()
    assert at.session_state["sky_region"]["astrometry"]["name"] == "Barnard's star"
    at, _ = _app(monkeypatch, {"ra": ra + 0.01, "dec": dec, "fov": 0.1, "view": .3, "layer": "2mass"},
                 locate_mode="Atlas", atlas_view=view)
    at.run()
    assert at.session_state["sky_region"]["astrometry"] is None   # moved away: plain fixed coordinates


def test_gaia_failure_keeps_atlas_usable(monkeypatch):
    from skyclues import reference_page

    def down(*a, **k):   # SIMULATED external outage
        raise references.ReferenceError("Gaia DR3 (ESA) no responde.")
    monkeypatch.setattr(reference_page, "cached_gaia", down)
    at, calls = _app(monkeypatch, locate_mode="Atlas", atlas_gaia=True)
    at.run()
    assert not at.exception and calls and calls[-1]["gaia"] == []
    assert any("sin Gaia" in w.value for w in at.warning)


def test_coordinates_panel_opens_both_explorers(monkeypatch):
    at, _ = _app(monkeypatch, locate_mode="Coordenadas")
    at.run()
    at.number_input(key="loc_ra").set_value(83.8221)
    at.number_input(key="loc_dec").set_value(-5.3911)
    at.number_input(key="loc_fov").set_value(12.0)
    at.button(key="loc_time").click().run()
    assert not at.exception
    assert at.number_input(key="ra_in").value == pytest.approx(83.8221)
    assert at.number_input(key="dec_in").value == pytest.approx(-5.3911)
    assert at.query_params["fov"] == "0.2"
    at.radio(key="locate_mode").set_value("Coordenadas").run()
    at.button(key="loc_spectrum").click().run()
    assert not at.exception
    assert at.session_state["sx_ra"] == pytest.approx(83.8221)
    assert at.radio(key="explorer").value.startswith("Spectrum")


def test_coordinates_to_atlas_switches_method_and_recentres(monkeypatch):
    at, calls = _app(monkeypatch, locate_mode="Coordenadas")
    at.run()
    at.number_input(key="loc_ra").set_value(150.0)
    at.number_input(key="loc_dec").set_value(2.0)
    at.button(key="loc_atlas").click().run()
    assert not at.exception
    assert at.radio(key="locate_mode").value == "Atlas"
    assert calls[-1]["ra"] == pytest.approx(150.0) and calls[-1]["nonce"] >= 1
