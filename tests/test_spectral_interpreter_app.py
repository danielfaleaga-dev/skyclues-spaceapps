"""Spectrum Explorer: sección «What could this spectrum indicate?» en la página (integración).

Cubo SINTÉTICO compartido (nunca datos reales) y un pico SIMULADO añadido al espectro de A en el canal 61
(3,275 µm en la rejilla sintética) para ejercitar la interfaz. La coherencia científica del motor se prueba en
test_spectral_interpreter.py; aquí, la integración, los dos niveles y la conservación del estado.
"""
import copy

import pandas as pd
import pytest

from skyclues import spectral_cube as sc, spectral_references as sr, spectral_view as sv
from skyclues import spectrum_analysis as sa
from test_spectral_app import app_cube, spectral_app  # noqa: F401
from test_spectral_offline import cube  # noqa: F401
from test_spectrum_analysis_app import place_b, text_of


@pytest.fixture
def peak(monkeypatch):
    """SIMULATED: +40 % in channel 61 of the spectrum of the centre (A); every other position untouched."""
    real = sc.extract_spectrum

    def extract(ra, dec, aperture=None, subpixels=5):
        spec = real(ra, dec, aperture, subpixels)
        if abs(dec - extract.centre[1]) < 1e-5 and abs(ra - extract.centre[0]) < 1e-5:
            spec = copy.deepcopy(spec)
            spec.rows[60]["flujo_mjy"] *= 1.4
        return spec
    monkeypatch.setattr(sc, "extract_spectrum", extract)
    return extract


def html_of(at) -> str:
    return " ".join(str(getattr(x, "body", "")) for x in at.get("html"))


def frames(at) -> list[pd.DataFrame]:
    return [d.value for d in at.dataframe]


def interp_table(at) -> pd.DataFrame:
    return next(d for d in frames(at) if "Compatibility" in d.columns)


def level(at, name):
    at.button_group(key="level").set_value(name).run()
    assert not at.exception


def test_section_is_present_in_both_levels_and_says_nothing_without_features(app_cube):
    at = spectral_app(app_cube)
    assert not at.exception
    assert "What could this spectrum indicate?" in html_of(at)
    assert at.toggle(key="w_sx_refs").value is False
    assert "nothing to interpret" in text_of(at)
    level(at, "Simple")
    assert "What could this spectrum indicate?" in html_of(at)
    assert "nothing to interpret" in text_of(at) and "does not prove that substances are missing" in text_of(at)


def test_selecting_a_feature_explains_it_in_both_levels_with_the_same_result(app_cube, peak):
    peak.centre = app_cube.centre
    at = spectral_app(app_cube)
    assert "Compatible reference" in html_of(at)                     # overview badge for the simulated peak
    assert 'class="sc-badge sc-ok">Referencia compatible' in html_of(at)   # a class theme.py actually styles
    at.button(key="sx_interp_A_61").click().run()
    assert not at.exception and at.session_state[sa.INSPECT_KEY] == {"lo": 61, "hi": 61}
    table = interp_table(at)
    row = dict(zip(table["Referencia"], table["Compatibility"]))
    assert row["Aromatic PAH (3.3 µm)"] == "Compatible"
    assert row["H I Pfund δ (3.297 µm)"] == "Not compatible: adjacent channel"
    sci_txt = " ".join(str(m.value) for m in at.markdown)
    assert "What prevents certainty" in sci_txt and "does not identify a substance" in sci_txt
    assert "«Visible» signal" not in sci_txt                           # quantifiable: no cap from the signal
    assert "desconocido" in html_of(at)                               # z of an uncatalogued position, stated
    level(at, "Simple")
    txt = text_of(at)
    assert "We detected an excess of emission near 3.3 µm" in txt
    assert "It could be related to aromatic carbon compounds (PAH)" in txt
    assert "We have found" not in txt and "A peak or a valley is not enough to identify a material." in txt
    assert "Compatible reference" in html_of(at)
    assert at.session_state[sa.INSPECT_KEY] == {"lo": 61, "hi": 61}  # level change keeps the selection
    assert not [d for d in frames(at) if "Compatibility" in d.columns]   # no scientific table in Sencillo


def test_reference_marks_toggle_survives_level_changes(app_cube, peak):
    peak.centre = app_cube.centre
    at = spectral_app(app_cube)
    at.toggle(key="w_sx_refs").set_value(True).run()
    assert not at.exception and at.session_state["opt_sx_refs"] is True
    level(at, "Simple")
    assert at.toggle(key="w_sx_refs").value is True
    level(at, "Scientific")
    assert at.toggle(key="w_sx_refs").value is True and at.session_state["opt_sx_refs"] is True


def test_a_and_b_are_interpreted_separately(app_cube, peak):
    peak.centre = app_cube.centre
    at = spectral_app(app_cube)
    place_b(at, app_cube)
    at.session_state[sa.INSPECT_KEY] = {"lo": 61, "hi": 61}
    at.run()
    assert not at.exception
    page = html_of(at)
    page = page[page.index("What could this spectrum indicate?"):]   # the section (the inspector also names A, B)
    assert "Spectrum A: " in page and "Spectrum B: " in page
    assert page.index("Compatible reference") < page.index("Spectrum B: ")
    assert "No evaluable" in page[page.index("Spectrum B: "):]       # B has no peak: nothing to interpret there
    sci_txt = " ".join(str(m.value) for m in at.markdown)
    assert "does not identify a substance" in sci_txt                   # A: a match is not an identification
    assert "that none matches does not exclude other substances" in sci_txt   # B: no match excludes nothing
    level(at, "Simple")
    txt = text_of(at)
    assert "No peak or valley stands out here." in txt and "We detected an excess of emission" in txt


def test_chart_draws_reference_marks_only_when_asked(cube):
    spec = sc.extract_spectrum(*cube.centre)
    marks = [{"lambda_um": r.lam_um, "nombre": r.name, "naturaleza": "emisión", "nota": "en reposo",
              "destacada": r.id == "pah_3p3", "etiqueta": "PAH 3,3" if r.id == "pah_3p3" else ""}
             for r in sr.REFERENCES]
    plain = sv.spectrum_chart(spec, "flux").to_dict()
    marked = sv.spectrum_chart(spec, "flux", references=marks).to_dict()
    assert len(marked["layer"]) == len(plain["layer"]) + 2           # dotted rules + one label, nothing else
    rules = [lay for lay in marked["layer"] if lay.get("mark", {}).get("strokeDash") == [1, 3]]
    assert len(rules) == 1 and rules[0]["mark"]["type"] == "rule"
