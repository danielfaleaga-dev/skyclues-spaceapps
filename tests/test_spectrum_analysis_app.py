"""Spectrum Explorer: dos posiciones (A, B), comparación e inspección de picos y valles en la página.

Cubo SINTÉTICO compartido (nunca datos reales) y, donde se indica, un pico SIMULADO añadido al
espectro de A para ejercitar la interfaz. La corrección numérica se prueba en
test_spectral_features.py; aquí se prueba la integración y la conservación del estado.
"""
import copy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from skyclues import spectral_cube as sc, spectral_features as sf, spectrum_analysis as sa, spectrum_page as page
from test_spectral_app import app_cube, spectral_app  # noqa: F401
from test_spectral_offline import cube  # noqa: F401

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def place_b(at, cube, dy=10):
    ra, dec = map(float, cube.tile.wcs.pixel_to_world_values(16, 16 + dy))
    at.session_state[sa.B_KEY] = {"ra": ra, "dec": dec, "region": tuple(at.session_state["sx_region_key"])}
    return ra, dec


def inspector(at):
    """The table of the examined interval (the page also shows the comparison table)."""
    return next(d.value for d in at.dataframe if list(d.value.columns)[0] == "Magnitud")


def text_of(at) -> str:
    return " ".join(str(x.value) for kind in ("caption", "markdown", "warning", "subheader") for x in getattr(at, kind))


@pytest.fixture
def bumped(monkeypatch):
    """SIMULATED: +40 % in channel 31 of the spectrum of the centre (A); every other position untouched."""
    real = sc.extract_spectrum

    def extract(ra, dec, aperture=None, subpixels=5):
        spec = real(ra, dec, aperture, subpixels)
        if abs(dec - extract.centre[1]) < 1e-5 and abs(ra - extract.centre[0]) < 1e-5:
            spec = copy.deepcopy(spec)
            spec.rows[30]["flujo_mjy"] *= 1.4
        return spec
    monkeypatch.setattr(sc, "extract_spectrum", extract)
    return extract


def test_one_position_is_the_default_and_nothing_is_compared(app_cube):
    at = spectral_app(app_cube)
    assert sa.B_KEY not in at.session_state
    assert at.button_group(key="w_sx_active").value == "Point A"
    assert "Espectro exploratorio de una posición" in text_of(at)
    assert not [b for b in at.button if b.key == "sx_b_remove"]
    assert "ningún pico ni valle" in text_of(at)           # flat synthetic spectrum: nothing is labelled


def test_click_places_b_only_when_b_is_the_active_point(app_cube):
    pick = {"ra": 123.456789, "dec": -12.345678}
    state = {"sx_field": {"selection": {"pick": [pick]}}, "sx_region_key": (1.0, 2.0, 0.1), "sx_pick_ra": 9.0,
             "sx_pick_dec": 8.0, "opt_sx_active": "Point B"}
    import streamlit as st
    orig = st.session_state
    try:
        page.st.session_state = state
        page._set_pick_from_chart()
    finally:
        page.st.session_state = orig
    assert state[sa.B_KEY] == {"ra": pick["ra"], "dec": pick["dec"], "region": (1.0, 2.0, 0.1)}
    assert (state["sx_pick_ra"], state["sx_pick_dec"]) == (9.0, 8.0)          # A untouched


def test_second_position_is_extracted_like_a_and_can_be_removed(app_cube):
    at = spectral_app(app_cube)
    spec_a = at.session_state["sx_spec_params"]
    ra_b, dec_b = place_b(at, app_cube)
    at.run()
    assert not at.exception
    txt = text_of(at)
    assert "Espectros exploratorios de dos posiciones" in txt and "Misma extracción en ambos" in txt
    assert f"B: RA {ra_b:.5f}°" in txt and "A: rombo negro · B: cuadrado cobrizo" in txt
    assert at.session_state["sx_spec_params"] == spec_a                         # A and its extraction unchanged
    assert at.button_group(key="w_sx_derived").value == "Diferencia A − B"
    at.button_group(key="w_sx_derived").set_value("Relación A / B").run()
    assert not at.exception and at.session_state["opt_sx_derived"] == "Relación A / B"
    at.button(key="sx_b_remove").click().run()
    assert not at.exception and sa.B_KEY not in at.session_state
    assert "Espectro exploratorio de una posición" in text_of(at)
    assert at.session_state["sx_spec_params"] == spec_a


def test_b_uses_the_aperture_of_a_never_its_own(app_cube, monkeypatch):
    seen = []
    real = page.cached_spectrum

    def spy(ra, dec, r_ap, r_in, r_out):
        seen.append((round(ra, 6), round(dec, 6), r_ap, r_in, r_out))
        return real(ra, dec, r_ap, r_in, r_out)
    monkeypatch.setattr(page, "cached_spectrum", spy)
    at = spectral_app(app_cube)
    place_b(at, app_cube)
    at.slider(key="sx_rap").set_value(3.0).run()           # aperture changed but not applied yet
    assert {s[2:] for s in seen} == {(2.0, 4.0, 7.0)}
    at.button(key="sx_extract").click().run()
    assert not at.exception
    assert {s[2:] for s in seen[-2:]} == {(3.0, 4.0, 7.0)} and len({s[:2] for s in seen[-2:]}) == 2


def test_selection_inspector_and_state_survive_level_mode_and_view_changes(app_cube, bumped):
    bumped.centre = app_cube.centre
    at = spectral_app(app_cube)
    ra_b, dec_b = place_b(at, app_cube)
    at.session_state[sa.INSPECT_KEY] = {"lo": 31, "hi": 31}
    at.run()
    assert not at.exception
    table = inspector(at)
    assert list(table.columns) == ["Magnitud", "Espectro A", "Espectro B"]
    by = dict(zip(table["Magnitud"], zip(table["Espectro A"], table["Espectro B"])))
    assert by["Clase"] == ("Cuantificable", "Sin característica") and by["Tipo"] == ("pico · estrecha", "No identificada")
    assert by["Contraste relativo"][0] == "+40.0%"
    # B was examined over the same interval but holds no feature: no type, no centre, its values kept
    assert by["Centro de la característica (µm)"][1] == "No aplica" and by["Intervalo a media altura (µm)"][1] == "No aplica"
    assert by["Intervalo examinado (µm)"][0] == by["Intervalo examinado (µm)"][1]
    assert by["Contraste"][1] not in ("—", "") and by["Continuo local"][1] != "—"
    head = next(h.body for h in at.html if "examinad" in h.body and "sc-eyebrow" in h.body)
    assert "Característica examinada · " in head and '<span class="sc-unit">µm</span>' in head
    keep = {k: at.session_state[k] for k in (sa.B_KEY, sa.INSPECT_KEY, "sx_spec_params", "sx_channel")}
    at.session_state["opt_sx_derived"] = "Relación A / B"

    at.button_group(key="level").set_value("Simple").run()
    assert not at.exception
    simple = text_of(at)
    assert "pico: un 40% más brillante que los colores vecinos. Se distingue con claridad." in simple
    assert "**B** — no destaca sobre los colores vecinos." in simple and "no identifica por sí solo un material" in simple
    assert "A es más brillante que B" in simple
    at.button_group(key="sx_mode").set_value("Composición multibanda (RGB)").run()
    at.button_group(key="sx_mode").set_value("Un canal").run()
    at.button_group(key="nav").set_value("Time").run()
    at.button_group(key="nav").set_value("Spectrum").run()
    at.button_group(key="level").set_value("Scientific").run()
    assert not at.exception
    assert {k: at.session_state[k] for k in keep} == keep
    assert at.session_state["opt_sx_derived"] == "Relación A / B" and at.session_state["opt_sx_active"] == "Point A"
    at.button(key="sx_inspect_clear").click().run()
    assert not at.exception and sa.INSPECT_KEY not in at.session_state and sa.B_KEY in at.session_state


def test_interval_with_no_data_is_reported_not_filled(app_cube):
    at = spectral_app(app_cube)
    at.session_state[sa.INSPECT_KEY] = {"lo": 49, "hi": 53}
    at.run()
    assert not at.exception
    table = inspector(at)
    assert table["Espectro A"][0] == "No evaluable"
    assert "No se interpolan" in text_of(at)


def test_new_region_starts_with_a_single_position(app_cube):
    at = spectral_app(app_cube)
    place_b(at, app_cube)
    at.run()
    assert sa.B_KEY in at.session_state
    at.session_state["region"] = {**at.session_state["region"], "ra": app_cube.centre[0] + 0.01}
    at.run()
    assert not at.exception and sa.B_KEY not in at.session_state


def test_plot_selection_callback(monkeypatch):
    table = [(c, 0.75 + 0.04 * (c - 1)) for c in range(1, 103)]
    state = {"_sx_channels": table, sa.CHART_KEY: {"selection": {"intervalo": {"lambda_um": [1.94, 2.08]}, "canal": []}}}
    monkeypatch.setattr(sa.st, "session_state", state)
    sa._on_select()
    assert state[sa.INSPECT_KEY] == {"lo": 31, "hi": 34}
    state[sa.CHART_KEY] = {"selection": {"intervalo": {"lambda_um": [1.951, 1.952]}, "canal": []}}
    sa._on_select()
    assert state[sa.INSPECT_KEY] == {"lo": 31, "hi": 31}       # narrower than a channel: that channel
    state[sa.CHART_KEY] = {"selection": {"intervalo": {}, "canal": [{"canal": 77, "serie": "B"}]}}
    sa._on_select()
    assert state[sa.INSPECT_KEY] == {"lo": 77, "hi": 77}
    state[sa.CHART_KEY] = {"selection": {"intervalo": {}, "canal": []}}
    sa._on_select()
    assert sa.INSPECT_KEY not in state


def test_same_numbers_in_both_levels(app_cube, bumped):
    bumped.centre = app_cube.centre
    spec = sc.extract_spectrum(*app_cube.centre)
    series = sf.series_from_spectrum(spec, "flux", "A")
    (f,) = sf.find_features(series)
    assert f.canal == 31 and f.relative == pytest.approx(0.4, rel=1e-6)
    rows = sa._science_rows({"A": f}, series)
    assert "un 40%" in sa._plain(f) and dict(zip(rows["Magnitud"], rows["Espectro A"]))["Contraste relativo"] == "+40.0%"


def test_an_interval_without_a_feature_is_never_given_a_type_or_a_centre(app_cube, bumped):
    """The defect seen in M101: A «Sin característica» showed «pico · estrecha» and a centre at 3.383 µm."""
    bumped.centre = app_cube.centre
    series = sf.series_from_spectrum(sc.extract_spectrum(*app_cube.centre), "flux", "A")
    an = sf.analyse(series)
    (peak,) = an.features
    flat = sf.measure_interval(series, 60, 62, an.features, an.scatter)       # far from the simulated peak
    assert flat.klass == sf.NO_FEATURE and flat.kind is not None and flat.contrast != 0   # the core is unchanged
    col = dict(zip(*sa._science_rows({"A": flat}, series).to_dict("list").values()))
    assert col["Tipo"] == "No identificada" and col["Centro de la característica (µm)"] == "No aplica"
    assert col["Intervalo a media altura (µm)"] == "No aplica" and col["Canales: a media altura · fuera del ajuste"].startswith("no aplica")
    assert col["Contraste"] == sa._num(flat.contrast, flat.unit, signed=True)          # kept, not set to zero
    assert col["Intervalo examinado (µm)"].endswith("canales 60–62")
    assert sa._heading(flat, True, series).startswith("Intervalo examinado · ")
    assert f"{flat.lam:.3f}".replace(".", ",") not in sa._heading(flat, True, series)   # no centre is shown
    assert sa._heading(peak, True, series).startswith("Característica examinada · " + f"{peak.lam:.3f}".replace(".", ","))
    assert "pico" not in sa._plain(flat) and "valle" not in sa._plain(flat)


def test_units_survive_the_capitals_of_labels():
    from skyclues import theme
    head = sa._where(sf.Feature(serie="A", origin="x", klass=sf.QUANTIFIABLE, kind="pico", reasons=[], limitations=[], unit="mJy", canal=63,
                                canal_lo=63, canal_hi=63, lam=3.293))
    assert head == '3.293&nbsp;<span class="sc-unit">µm</span> (channel 63)'
    assert ".sc-unit{text-transform:none!important" in theme.CSS
    css = theme.CSS
    assert css.index(".sc-unit{") > css.index(".sc-eyebrow{")              # declared after the capitals rule
    assert theme.unit("λ") == '<span class="sc-unit">λ</span>'
    # notes under the spectrum plots keep the full secondary tone (Streamlit fades captions to 60 %)
    assert '[class*="st-key-sx_notes_"] [data-testid="stCaptionContainer"]{opacity:1}' in css
