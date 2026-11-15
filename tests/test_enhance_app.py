"""«Mejora infrarroja» inside Time Explorer (headless Streamlit).

The saved M101 and WISE 0855 sequences use authentic FITS from the reference store or the cache;
the «exposiciones próximas» route is exercised with explicitly simulated service replies."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from skyclues import archive, enhance_page

pytestmark = pytest.mark.network
APP = str(Path(__file__).resolve().parent.parent / "app.py")


def open_example(stem="sequence_m101", level="Científico"):
    at = AppTest.from_file(APP, default_timeout=180)
    at.session_state["level"] = level
    at.run()
    at.button(key="example_" + stem).click().run()
    assert not at.exception
    return at


def html(at) -> str:
    return " ".join(str(getattr(e.proto, "body", "")) for e in at.get("html"))


def text(at) -> str:
    return " ".join(m.value for m in list(at.markdown) + list(at.caption))


def test_toggle_shows_the_combined_image_and_returns_to_the_sequence():
    at = open_example()
    assert at.get("iframe") and not at.session_state["opt_enhance"]
    region = dict(at.session_state["region"])
    at.toggle(key="w_enhance").set_value(True).run()
    assert not at.exception
    assert "Imagen mejorada" in html(at) and not at.get("iframe")
    assert at.get("imgs") or at.get("image")
    assert "Ganancia S/N" in html(at) and "mismo canal" in html(at)
    assert at.session_state["region"] == region                     # the region and its FOV are untouched
    assert any("Exposiciones combinadas" in e.label for e in at.expander)
    at.toggle(key="w_enhance").set_value(False).run()
    assert not at.exception and at.get("iframe")                    # the original sequence, unchanged


def test_both_levels_show_the_same_product():
    at = open_example()
    at.toggle(key="w_enhance").set_value(True).run()
    product = enhance_page._sequence_product
    sci = html(at)
    at.button_group(key="level").set_value("Sencillo").run()
    assert not at.exception and at.session_state["opt_enhance"]
    simple = html(at)
    assert "Imagen mejorada" in simple and "Mejora de la señal" in simple
    assert "Ganancia S/N" not in simple and "VARIANCE" not in simple       # no jargon in Sencillo
    assert "Ganancia S/N" in sci
    assert not any("Exposiciones combinadas" in e.label for e in at.expander)
    assert enhance_page._sequence_product is product
    at.button_group(key="level").set_value("Científico").run()
    assert not at.exception and "Ganancia S/N" in html(at)


def test_moving_target_sequence_is_not_combined_across_a_year():
    at = open_example("sequence_wise0855_pm")
    at.toggle(key="w_enhance").set_value(True).run()
    assert not at.exception
    assert "No disponible para estas observaciones" in html(at)
    assert "emborronaría" in text(at)
    assert "Imagen mejorada" not in html(at)


def test_nearby_route_states_available_processing_result(monkeypatch):
    calls = []

    def fake(*args):
        calls.append(args)
        return enhance_page._sequence_product.__wrapped__(REPORT[0], args[-1])

    at = open_example()
    REPORT.append(__import__("json").dumps(__import__("json").loads(
        (Path(APP).parent / "results" / "sequence_m101.json").read_text(encoding="utf-8")), sort_keys=True, default=str))
    monkeypatch.setattr(enhance_page, "_nearby_product", fake)
    at.toggle(key="w_enhance").set_value(True).run()
    at.selectbox(key="w_enhance_what").set_value("near0").run()
    assert not at.exception and "Disponible" in html(at) and not calls       # nothing is downloaded unasked
    assert "Imagen mejorada" not in html(at)
    at.button(key="enhance_run").click().run()
    assert not at.exception and len(calls) >= 1
    assert calls[0][3] == 2 and calls[0][2] == pytest.approx(0.1)             # same detector, same FOV
    assert "Imagen mejorada" in html(at)
    at.button_group(key="level").set_value("Sencillo").run()
    assert not at.exception and "Imagen mejorada" in html(at)                 # no second request to press
    assert at.session_state["opt_enhance_what"] == "near0"


REPORT: list = []


def test_nearby_route_reports_too_few_exposures_and_archive_failures(monkeypatch):
    monkeypatch.setattr(enhance_page, "_nearby_product", lambda *a: {
        "ok": False, "reason": "El archivo solo contiene 1 exposición del detector D2 con este campo completo."})
    at = open_example()
    at.toggle(key="w_enhance").set_value(True).run()
    at.selectbox(key="w_enhance_what").set_value("near1").run()
    at.button(key="enhance_run").click().run()
    assert not at.exception
    assert "No disponible para estas observaciones" in html(at) and "solo contiene 1 exposición" in text(at)

    def fail(*a):
        raise archive.ArchiveTransientError("SIA2: HTTP 503")

    monkeypatch.setattr(enhance_page, "_nearby_product", fail)
    at = open_example()
    at.toggle(key="w_enhance").set_value(True).run()
    at.selectbox(key="w_enhance_what").set_value("near2").run()
    at.button(key="enhance_run").click().run()
    assert not at.exception
    assert any("no está disponible temporalmente" in e.value for e in at.error)
    assert "Imagen mejorada" not in html(at) and at.button(key="enhance_retry")


def test_rejected_combination_is_not_presented_as_an_improvement(monkeypatch):
    real = enhance_page.enhance.verdict
    monkeypatch.setattr(enhance_page.enhance, "verdict", lambda m, **k: {
        "accepted": False, "reasons": ["Ganancia S/N mediana 1.05 < 1.2: la combinación no aporta una mejora medible."]})
    enhance_page._sequence_product.clear()
    try:
        at = open_example()
        at.toggle(key="w_enhance").set_value(True).run()
        assert not at.exception
        assert "No disponible para estas observaciones" in html(at) and "Imagen mejorada" not in html(at)
        assert "no aporta una mejora medible" in text(at)
        assert any("rechazada" in e.label for e in at.expander)               # diagnostics only, in Científico
    finally:
        monkeypatch.setattr(enhance_page.enhance, "verdict", real)
        enhance_page._sequence_product.clear()
