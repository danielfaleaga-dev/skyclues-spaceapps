"""Headless Streamlit tests of app.py (uses IRSA or the local FITS cache)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

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
    for label in at.sidebar.selectbox[0].options:
        at.sidebar.selectbox[0].set_value(label).run()
        assert not at.exception, label


def test_new_search_flow_runs_and_selects_a_sequence():
    at = AppTest.from_file(APP, default_timeout=600)
    at.run()
    at.sidebar.radio[0].set_value("Nueva búsqueda").run()
    assert not at.exception
    at.sidebar.multiselect[0].set_value([2]).run()   # one detector keeps the test short
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert any(m.label == "Épocas" for m in at.metric)
