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
        assert int({m.label: m.value for m in at.metric}["Épocas"]) >= 2


def test_display_options_render_without_changing_the_verdict():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    metrics = {m.label: m.value for m in at.metric}
    for geometry in list(at.radio(key="geometry").options):
        at.radio(key="geometry").set_value(geometry).run()
        at.toggle(key="halo").set_value(True).run()
        assert not at.exception
        assert {m.label: m.value for m in at.metric} == metrics


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
    at.radio(key="mode").set_value("Nueva búsqueda").run()
    at.button(key="search").click().run()
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
    assert any("no válido" in e.value for e in at.error)
    assert at.radio(key="mode").value == "Nueva búsqueda"
    # the widgets show valid defaults, never a clamped or NaN version of the input
    if "fov=9" not in qs:
        assert at.number_input(key="ra_in").value == pytest.approx(210.802429)


def test_partial_download_is_reported(monkeypatch):
    import json

    rep = json.loads((config.RESULTS_DIR / "sequence_m101.json").read_text(encoding="utf-8"))
    rep["retrieval"] = {"n_requested": 9, "n_failed": 2, "complete": False, "n_transient": 2}
    rep["retrieval_failures"] = [{"file": "x.fits", "kind": "transitorio", "error": "HTTP 503"},
                                 {"file": "y.fits", "kind": "transitorio", "error": "HTTP 503"}]
    at = AppTest.from_file(APP, default_timeout=300)
    at.session_state["mode"] = "Nueva búsqueda"
    at.session_state["report"] = rep
    at.run()
    assert not at.exception
    assert any("Descarga incompleta: 2 de 9" in w.value for w in at.warning)
    assert any(m.label == "Épocas" for m in at.metric)            # the sequence itself is still shown


def test_moving_target_is_shown_as_a_calculated_position():
    at = AppTest.from_file(APP, default_timeout=300)
    at.run()
    at.button(key="example_" + next(s for s in config.VALIDATED_EXAMPLES if "wise" in s)).click().run()
    assert not at.exception
    note = " ".join(md.value for md in at.markdown)
    assert "Objetivo en movimiento" in note and "calculada" in note and "no es una detección" in note


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
