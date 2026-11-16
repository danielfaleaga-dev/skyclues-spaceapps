"""Integrated version: the components (motion, S/N enhancement, spectrum, interpreter) do not interfere.

Offline. The exposures and the cube are SYNTHETIC (the builders of test_enhance.py and
test_spectral_offline.py); the same checks on real data are in scripts/integration_verify.py.
"""
import ast
import hashlib
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from skyclues import config, enhance as en, spectral_interpreter as si, spectrum_interpretation as sxi
from skyclues import spectrum_page as page
from test_enhance import DEC0, FOV, RA0, exposure, synthetic_psf  # noqa: F401
from test_spectral_app import app_cube  # noqa: F401
from test_spectral_offline import cube  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
APP = str(ROOT / "app.py")
ENHANCE = {"enhance", "enhance_page", "enhance_view"}
MOTION_SIDE = ["motion", "motion_page", "non_sidereal", "moving_sources", "moving_page", "moving_view", "sequence",
               "player"]


def imports_of(module: str) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse((ROOT / "skyclues" / f"{module}.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            out.update(a.name for a in node.names)
            if node.module:
                out.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            out.update(a.name.split(".")[-1] for a in node.names)
    return out


@pytest.mark.parametrize("module", MOTION_SIDE)
def test_motion_and_sequence_code_never_reads_the_enhancement(module):
    assert not imports_of(module) & ENHANCE


def test_spectrum_and_time_code_are_independent():
    spectral = {p.stem for p in (ROOT / "skyclues").glob("spectr*.py")}
    time_side = ENHANCE | {"motion", "motion_page", "non_sidereal", "moving_sources", "moving_page", "time_page"}
    assert {"spectral_interpreter", "spectral_references", "spectrum_interpretation", "spectral_quality"} <= spectral
    for module in spectral:
        assert not imports_of(module) & time_side, module
    for module in ENHANCE:
        assert not imports_of(module) & spectral, module


def digest(exposures) -> str:
    h = hashlib.sha256()
    for e in exposures:
        for a in (e.image.image, e.image.variance, e.image.flags, e.image.zodi, e.image.wavelength_um):
            h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def test_combining_never_modifies_the_exposures_it_reads():
    exps = [exposure(1), exposure(2, dx=0.37, dy=-0.21, rot=7.0), exposure(3, dx=-3.4, dy=2.6, rot=-11.0),
            exposure(4, dx=1.5, dy=0.5, rot=3.0)]
    exps[1].image.image[10, 10] = -500.0                 # a non-physical value the method discards: in its copy only
    before = digest(exps)
    stack = en.combine(exps, RA0, DEC0, FOV)
    metrics = en.evaluate(stack)
    en.verdict(metrics), en.summary(stack, metrics)
    assert digest(exps) == before
    assert exps[1].image.image[10, 10] == -500.0


def test_interpreter_output_has_verdicts_and_no_probabilities():
    assert set(si.VERDICT_LABELS) == {si.COMPATIBLE, si.SEVERAL, si.WEAK, si.NONE, si.NOT_EVALUABLE}
    words = " ".join(list(si.VERDICT_LABELS.values()) + list(si.VERDICT_MEANING.values())
                     + list(si.STATUS_LABELS.values()) + list(sxi.PLAIN_LIMITS.values())).lower()
    for banned in ("probab", "identificad", "confirmad", "hemos encontrado", "%"):
        assert banned not in words, banned
    assert "not an identification" in si.VERDICT_MEANING[si.COMPATIBLE]


def test_options_of_both_explorers_survive_a_round_trip_with_one_region(app_cube, monkeypatch):  # noqa: F811
    monkeypatch.setattr(page, "cached_epoch", lambda _: (app_cube.centre[0], app_cube.centre[1], {
        "propagated": True, "mjd_mid": 60000, "date_mid": "2023-02-25", "date_beg": "2023-01-01",
        "date_end": "2023-05-01", "motion_over_inputs_arcsec": 3}))
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state["level"] = "Scientific"
    at.run()
    stem = next(s for s in config.VALIDATED_EXAMPLES if "wise" in s)
    at.button(key="example_" + stem).click().run()
    assert not at.exception
    at.toggle(key="w_enhance").set_value(True).run()                     # Time: S/N option on
    assert not at.exception and at.session_state["opt_enhance"] is True
    shared = dict(at.session_state["region"])
    at.button_group(key="nav").set_value("Spectrum").run()
    assert not at.exception
    assert at.session_state["sx_region_key"] == (round(shared["ra"], 6), round(shared["dec"], 6), shared["fov"])
    at.toggle(key="w_sx_refs").set_value(True).run()                     # Spectrum: reference marks on
    assert not at.exception and at.session_state["opt_sx_refs"] is True
    assert at.session_state["opt_enhance"] is True                       # untouched by the other explorer
    at.button_group(key="level").set_value("Simple").run()
    assert not at.exception and at.session_state["opt_sx_refs"] is True and at.session_state["opt_enhance"] is True
    at.button_group(key="nav").set_value("Time").run()
    assert not at.exception
    assert at.session_state["region"]["ra"] == pytest.approx(shared["ra"], abs=1e-6)
    assert at.session_state["region"]["dec"] == pytest.approx(shared["dec"], abs=1e-6)
    assert at.session_state["region"]["fov"] == shared["fov"]
    assert at.session_state["opt_enhance"] is True and at.session_state["opt_sx_refs"] is True
    assert list(at.button_group(key="nav").options) == ["Region", "Time", "Spectrum"]
    assert list(at.button_group(key="level").options) == ["Simple", "Scientific"]
