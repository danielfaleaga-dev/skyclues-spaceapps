"""Headless Streamlit tests of app.py (uses IRSA or the local FITS cache)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from skyclues import config

pytestmark = pytest.mark.network
APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_reference_sequence_view_renders_with_player():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    assert not at.exception
    metrics = {m.label: m.value for m in at.metric}
    assert int(metrics["Épocas"]) >= 3
    assert "Cobertura común válida" in metrics
    assert any("Comparable" in md.value for md in at.markdown)


def test_every_saved_result_renders():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    for label in at.selectbox(key="ref_label").options:
        at.selectbox(key="ref_label").set_value(label).run()
        assert not at.exception, label


def test_new_search_flow_runs_and_selects_a_sequence():
    at = AppTest.from_file(APP, default_timeout=600)
    at.run()
    at.radio(key="mode").set_value("Nueva búsqueda").run()
    assert not at.exception
    at.sidebar.multiselect[0].set_value([2]).run()   # one detector keeps the test short
    at.button(key="search").click().run()
    assert not at.exception
    assert any(m.label == "Épocas" for m in at.metric)


def test_validated_example_buttons_open_the_examples():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    at.radio(key="mode").set_value("Nueva búsqueda").run()
    for stem in config.VALIDATED_EXAMPLES:
        at.button(key=f"example_{stem}").click().run()
        assert not at.exception
        assert at.radio(key="mode").value == "Secuencia de referencia"
        assert at.selectbox(key="ref_label").value.startswith(stem.replace("sequence_", "") + " ·")
        assert int({m.label: m.value for m in at.metric}["Épocas"]) >= 3


def test_display_options_render_without_changing_the_verdict():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    for geometry in list(at.radio(key="geometry").options):
        at.radio(key="geometry").set_value(geometry).run()
        at.toggle(key="halo").set_value(True).run()
        assert not at.exception
        assert {m.label: m.value for m in at.metric} == metrics


def test_field_of_view_is_applied_to_the_search():
    at = AppTest.from_file(APP, default_timeout=900)
    at.run()
    at.radio(key="mode").set_value("Nueva búsqueda").run()
    at.radio(key="fov_preset").set_value("Otro").run()
    at.number_input(key="fov_custom").set_value(100.0).run()       # beyond the limit: clamped
    assert any(f"{config.FOV_MAX_DEG * 60:g}′" in c.value for c in at.caption)
    at.radio(key="fov_preset").set_value("18′").run()
    assert any("Campo grande" in w.value for w in at.warning)      # larger field: time warning
    at.sidebar.multiselect[0].set_value([2]).run()
    at.button(key="search").click().run()
    assert not at.exception
    rep = at.session_state["report"]
    assert rep["target"]["field_deg"] == pytest.approx(0.3)
    assert all("size=0.30000" in o for o in [f["cutout_url"] for f in rep["selected"]["frames"]])
    assert any("18.0′" in md.value for md in at.markdown)
