"""Final-version fixes: the bright-position explanation, the featured 3I/ATLAS example and the loading indicator.

Pure logic only (no network): the live behaviour was checked in the browser (results/ux_redesign/final_fixes).
"""
from __future__ import annotations

import re
from pathlib import Path

from skyclues import spectral_quality as sq

ROOT = Path(__file__).resolve().parent.parent


def _row(canal, status="no_data_aperture", bloom=0, overflow=0, bad=3, total=12):
    """A cube-spectrum row as ``spectral_cube.extract_spectrum`` reports it."""
    return {"canal": canal, "lambda_um": 0.75 + 0.04 * canal, "detector": 1, "status": status, "precaucion": False,
            "ap_pix_total": total, "ap_pix_invalidos": bad, "ap_pix_nan": bad, "ap_pix_nhits0": 0,
            "ap_peso_total": float(total), "ap_peso_invalido": float(bad), "ap_bloom": bloom, "ap_overflow": overflow}


def test_bright_source_explains_the_missing_channels():
    qs = [sq.channel_quality(_row(i, bloom=4, overflow=2 if i % 4 == 0 else 0)) for i in range(1, 41)]
    info = sq.too_bright(qs)
    assert info and info["rejected"] == 40 and info["bright"] == 40 and info["bloom"] == 40 and info["overflow"] == 10
    simple, sci = sq.bright_text(info, False), sq.bright_text(info, True)
    assert "too bright for the detector" in simple and "40 of the 40" in simple
    assert "BLOOM" in sci and "OVERFLOW" in sci and "does not fill or interpolate" in sci


def test_no_brightness_claim_when_the_cause_is_something_else():
    # channels rejected only for missing pixels (no BLOOM/OVERFLOW flag): another cause, so no "too bright" note
    qs = [sq.channel_quality(_row(i)) for i in range(1, 30)]
    assert sq.too_bright(qs) is None
    ok = [sq.channel_quality({**_row(i, status="ok", bad=0), "flujo_mjy": 1.0}) for i in range(1, 30)]
    assert sq.too_bright(ok) is None                      # nothing is missing
    blank = [sq.channel_quality({"canal": 51, "lambda_um": 3.0, "detector": 3, "status": "blank", "precaucion": False})]
    assert sq.too_bright(blank) is None                   # channels empty in DR1 are not a brightness problem


def test_a_minority_of_flagged_channels_is_not_reported_as_too_bright():
    qs = [sq.channel_quality(_row(i, bloom=1 if i == 1 else 0)) for i in range(1, 21)]
    assert sq.too_bright(qs) is None                      # 1 flagged channel of 20 rejected


def test_featured_example_is_wired_and_in_english():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "region_ui.open_atlas_comet" in app and "Follow 3I/ATLAS across the sky" in app
    assert "interstellar" in app
    region = (ROOT / "skyclues" / "region_ui.py").read_text(encoding="utf-8")
    # same JPL identity as the search box (3I/ATLAS = SPK-ID 1004083), nothing simulated
    assert "def open_atlas_comet" in region and "'1004083'" in region and "solar_lookup('3I/ATLAS')" in region
    new_text = "".join(re.findall(r"[\"']([^\"']{25,})[\"']", region[region.index("def open_atlas_comet"):][:1800]))
    assert not re.search(r"\b(el|la|los|las|para|porque|cometa|detectado)\b", new_text)   # no Spanish residue


def test_loading_indicator_stays_in_view():
    css = (ROOT / "skyclues" / "theme.css").read_text(encoding="utf-8")
    assert re.search(r'\[class\*="st-key-sc_loading_"\]\{position:sticky;top:[^;]+;bottom:[^;]+', css)


def test_negative_flux_note_and_plain_wording():
    from types import SimpleNamespace

    from skyclues import spectral_features as sf
    from skyclues import spectrum_analysis as sa

    simple, sci = sa.negative_flux_text(12, False), sa.negative_flux_text(12, True)
    assert "not negative light" in simple and "12 channels" in sci and "kept as measured" in sci
    feature = SimpleNamespace(klass=sf.NO_FEATURE, kind=None)
    assert "general shape of the light" in sa._plain(feature)


def test_presentation_only_changes_have_no_spanish_residue():
    root = ROOT / "skyclues"
    for name, marker in (("time_page.py", "MIN_PM_ARCSEC_YR"), ("enhance_page.py", "No additional points stand out"),
                         ("spectrum_analysis.py", "def negative_flux_text")):
        text = (root / name).read_text(encoding="utf-8")
        assert marker in text, (name, marker)
    page = (root / "time_page.py").read_text(encoding="utf-8")
    assert "moves = seq.target_moves and seq.astrometry.total_pm_arcsec_yr >= MIN_PM_ARCSEC_YR" in page
