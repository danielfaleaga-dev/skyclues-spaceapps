"""Headless Streamlit tests of app.py (uses IRSA or the local FITS cache)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from skyclues import config, navigation, time_page

pytestmark = pytest.mark.network
APP = str(Path(__file__).resolve().parent.parent / "app.py")


def open_example(stem='sequence_m101'):
    at=AppTest.from_file(APP,default_timeout=120)
    at.session_state['level']='Científico'
    at.run();at.button(key='example_'+stem).click().run()
    assert not at.exception
    return at


def test_reference_sequence_view_renders_with_player():
    at=open_example()
    assert at.session_state['region']['report']=='sequence_m101'
    assert '2026-05-17' in at.get('iframe')[0].proto.srcdoc


def test_every_saved_result_renders():
    for label,path in time_page.reference_reports().items():
        at=AppTest.from_file(APP,default_timeout=120)
        import json
        state,qp={},{}
        navigation.set_from_report(state,qp,Path(path).stem,json.loads(Path(path).read_text(encoding='utf8')))
        at.session_state['region']=state['region'];at.session_state['nav']='Tiempo'
        at.run()
        assert not at.exception,label
        assert at.get('iframe'),label


def test_validated_example_buttons_open_the_examples():
    for stem in config.VALIDATED_EXAMPLES:
        at=open_example(stem)
        assert at.session_state['region']['report']==stem
        assert at.query_params['explorer']=='temporal'


def test_display_options_and_levels_do_not_change_the_science():
    at=open_example()
    region=at.session_state['region'].copy()
    for geometry in at.radio(key='w_geometry_label').options:
        at.radio(key='w_geometry_label').set_value(geometry).run()
        at.toggle(key='w_halo').set_value(True).run()
        assert not at.exception
        assert at.session_state['region']==region
    at.button_group(key='level').set_value('Sencillo').run()
    assert not at.exception and at.session_state['opt_halo']
    assert at.session_state['region']==region


@pytest.mark.parametrize("error, text", [
    ("transient", "no está disponible temporalmente"),
    ("permanent", "rechazó la solicitud"),
])
def test_irsa_failure_shows_a_clear_message_and_no_partial_data(monkeypatch, error, text):
    from skyclues import archive

    def fail(*a, **k):
        if error == "transient":
            raise archive.ArchiveTransientError("SIA2 spherex_dr1: HTTP 503 Server busy")
        raise archive.ArchivePermanentError("HTTP 400 de IRSA (no se reintenta)")

    monkeypatch.setattr(archive, "query_images", fail)
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    at.button_group(key='nav').set_value('Tiempo').run()
    assert not at.exception
    assert any(text in e.value for e in at.error)
    assert not any(m.label == "Épocas" for m in at.metric)


@pytest.mark.parametrize("qs", ["ra=nan&dec=10", "ra=400&dec=-95", "ra=abc&dec=1", "ra=10&dec=10&fov=9"])
def test_invalid_url_parameters_are_reported_and_never_queried(monkeypatch, qs):
    from skyclues import archive

    def no_query(*a, **k):
        raise AssertionError("IRSA must not be queried")

    monkeypatch.setattr(archive, "query_images", no_query)
    at = AppTest.from_file(APP, default_timeout=300)
    at.query_params = dict(p.split("=") for p in qs.split("&"))
    at.run()
    assert not at.exception
    assert any("no válid" in e.value for e in at.error)
    assert at.session_state["nav"] == "Región"
    # the widgets show valid defaults, never a clamped or NaN version of the input
    if "fov=9" not in qs:
        assert at.session_state["region"]["ra"] == pytest.approx(210.802429)


def test_partial_download_is_reported(monkeypatch):
    import json

    rep = json.loads((config.RESULTS_DIR / "sequence_m101.json").read_text(encoding="utf-8"))
    rep["retrieval"] = {"n_requested": 9, "n_failed": 2, "complete": False, "n_transient": 2}
    rep["retrieval_failures"] = [{"file": "x.fits", "kind": "transitorio", "error": "HTTP 503"},
                                 {"file": "y.fits", "kind": "transitorio", "error": "HTTP 503"}]
    at = AppTest.from_file(APP, default_timeout=300)
    state,qp={},{}
    r=navigation.set_region(state,qp,rep['target']['ra_deg'],rep['target']['dec_deg'],rep['target']['field_deg'])
    at.session_state['region']=r;at.session_state['nav']='Tiempo'
    at.session_state['time_reports']={time_page.search_key(navigation.explorer_inputs(r)):rep}
    at.run()
    assert not at.exception
    assert any("Descarga incompleta: 2 de 9" in w.value for w in at.warning)
    assert at.get("iframe")


def test_moving_target_is_shown_as_a_calculated_position():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    at.button(key="example_" + next(s for s in config.VALIDATED_EXAMPLES if "wise" in s)).click().run()
    assert not at.exception
    note = " ".join(str(x.proto) for x in at if hasattr(x, 'proto'))
    assert "Objetivo en movimiento" in note and "calculada" in note and "no es una detección" in note


def test_field_of_view_is_applied_to_the_search(monkeypatch):
    calls=[]
    def find(ra,dec,field_deg,**kw):
        calls.append((ra,dec,field_deg,kw))
        return None,{'target':{'ra_deg':ra,'dec_deg':dec,'field_deg':field_deg},'selected':None,'elapsed_s':0,'n_records':0}
    monkeypatch.setattr(time_page,'find_sequence',find)
    at=AppTest.from_file(APP,default_timeout=30)
    at.query_params={'ra':'83.8221','dec':'-5.3911','fov':'.3'}
    at.run();at.button_group(key='nav').set_value('Tiempo').run()
    assert not at.exception
    assert calls[-1][:3]==(83.8221,-5.3911,.3)
