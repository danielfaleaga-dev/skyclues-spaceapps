"""Headless Streamlit tests of app.py (uses IRSA or the local FITS cache)."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

pytestmark = pytest.mark.network
APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_reference_pair_view_renders_without_errors():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Cobertura común válida" in labels
    assert any("Comparable" in md.value for md in at.markdown)


def test_new_search_flow_runs_and_selects_a_pair():
    at = AppTest.from_file(APP, default_timeout=600)
    at.run()
    at.sidebar.radio[0].set_value("Nueva búsqueda").run()
    assert not at.exception
    at.sidebar.multiselect[0].set_value([2]).run()   # one detector keeps the test short
    at.sidebar.button[0].click().run()
    assert not at.exception
    assert any(m.label == "Separación temporal" for m in at.metric)
