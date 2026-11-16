"""Diagnóstico de calidad espectral: cobertura de la apertura, máscaras y regla de extracción.

Cubo SINTÉTICO (nunca datos reales): se perforan píxeles concretos de la apertura y se marcan con BLOOM u OVERFLOW.
La comprobación contra los FITS reales (NGC 7027, M82, Elias 29, M101) está en scripts/quality_verify.py.
"""
import re

import numpy as np
import pytest

from skyclues import spectral_cube as sc, spectral_features as sf, spectral_quality as sq, spectrum_analysis as sa
from test_spectral_app import app_cube, spectral_app  # noqa: F401
from test_spectral_offline import cube  # noqa: F401

BITS = {0: "OVERFLOW", 1: "BLOOM"}
UNIT = 1 << 0, 1 << 1       # OVERFLOW, BLOOM


@pytest.fixture
def punched(cube, monkeypatch):
    """Channels 1–3: the centre pixel has no data (NaN, NHITS = 0) and BLOOM. Channel 4: one NaN pixel and one
    NHITS = 0 pixel, no mask. Channel 5: OVERFLOW on a pixel that has data. Channel 6: BLOOM on a pixel that has data."""
    monkeypatch.setattr(sc, "flag_bits", lambda tile: BITS)
    original = cube.tile.read_rows

    def changed(exts, y0, y1, x0=0, x1=None):
        out = original(exts, y0, y1, x0, x1)

        def put(ext, plane, y, x, value):
            if ext in out and plane in exts[ext] and y0 <= y <= y1 and x >= x0 and (x1 is None or x <= x1):
                out[ext][exts[ext].index(plane), y - y0, x - x0] = value

        for p in (0, 1, 2):
            put("IMAGE", p, 16, 16, np.nan); put("NHITS", p, 16, 16, 0); put("FLAGS", p, 16, 16, UNIT[1])
        put("IMAGE", 3, 16, 17, np.nan)             # NaN with NHITS > 0
        put("NHITS", 3, 17, 16, 0)                  # NHITS = 0 with a finite value
        put("FLAGS", 4, 16, 16, UNIT[0])
        put("FLAGS", 5, 16, 16, UNIT[1])
        return out
    monkeypatch.setattr(cube.tile, "read_rows", changed)
    return cube


def test_coverage_counts_match_the_pixels_of_the_aperture(punched):
    spec = sc.extract_spectrum(*punched.centre)
    w = sc._aperture_weights(punched.tile, 0, 0, (32, 32), *punched.centre, 2.0, punched.tile.pixel_scale_arcsec, 5)
    rows = spec.rows
    for r in rows:
        assert r["ap_pix_total"] == int((w > 0).sum()) and r["ap_peso_total"] == pytest.approx(float(w.sum()))
    for i in (0, 1, 2):                              # no data + BLOOM → no flux
        r = rows[i]
        assert (r["status"], r["flujo_mjy"]) == ("no_data_aperture", None)
        assert (r["ap_pix_invalidos"], r["ap_pix_nan"], r["ap_pix_nhits0"]) == (1, 1, 1)
        assert (r["ap_bloom"], r["ap_overflow"]) == (1, 0) and r["ap_peso_invalido"] == pytest.approx(1.0)
    r = rows[3]                                      # NaN and NHITS = 0 are counted apart; both reject the channel
    assert r["status"] == "no_data_aperture" and (r["ap_pix_invalidos"], r["ap_pix_nan"], r["ap_pix_nhits0"]) == (2, 1, 1)
    assert (r["ap_bloom"], r["ap_overflow"]) == (0, 0)
    r = rows[4]                                      # OVERFLOW on a pixel with data: measured, with caution
    assert r["status"] == "ok" and r["precaucion"] and (r["ap_pix_invalidos"], r["ap_overflow"], r["ap_bloom"]) == (0, 1, 0)
    r = rows[5]                                      # BLOOM on a pixel with data: measured, nothing rejected
    assert r["status"] == "ok" and not r["precaucion"] and (r["ap_pix_invalidos"], r["ap_bloom"]) == (0, 1)
    r = rows[6]
    assert r["status"] == "ok" and (r["ap_pix_invalidos"], r["ap_bloom"], r["ap_overflow"]) == (0, 0, 0)


def test_the_flux_and_the_existing_row_values_do_not_change(punched):
    """Same extraction with and without the new diagnostic keys: every existing key keeps its value."""
    spec = sc.extract_spectrum(*punched.centre)
    for i, r in enumerate(spec.rows):
        if r["status"] == "ok":
            assert r["flujo_mjy"] == pytest.approx(7 * punched.tile.pixel_solid_angle_sr * 1e9, rel=1e-10)
            assert r["fondo_mjysr"] == pytest.approx(10 + i)
        else:
            assert r["flujo_mjy"] is None
    assert [r["status"] for r in spec.rows[:6]] == ["no_data_aperture"] * 4 + ["ok", "ok"]
    assert spec.rows[50]["status"] == spec.rows[51]["status"] == "blank"


def test_causes_coexist_and_are_not_exclusive_categories(punched):
    qs = {q.canal: q for q in sq.spectrum_quality(sc.extract_spectrum(*punched.centre))}
    assert set(qs[1].causes) == {sq.NO_DATA, sq.BLOOM, sq.INCOMPLETE} and sq.OVERFLOW not in qs[1].causes
    assert qs[1].rejected_incomplete_aperture and not qs[1].valid_for_extraction
    assert set(qs[4].causes) == {sq.NO_DATA, sq.INCOMPLETE} and sq.BLOOM not in qs[4].causes
    assert qs[5].valid_for_extraction and qs[5].caution and qs[5].causes == (sq.OVERFLOW,) and not qs[5].rejected_incomplete_aperture
    assert qs[6].valid_for_extraction and not qs[6].caution and qs[6].causes == (sq.BLOOM,) and qs[6].affected
    assert not qs[7].affected and qs[7].causes == () and qs[7].valid_pct == 100.0
    assert qs[51].causes == (sq.BLANK,) and qs[51].status == "blank" and not qs[51].rejected_incomplete_aperture
    assert qs[1].px_valid == qs[1].px_total - 1 and qs[1].valid_pct == pytest.approx(100 * qs[1].px_valid / qs[1].px_total)
    assert 0 < qs[1].weight_lost_pct < 20
    s = sq.summary(list(qs.values()))
    assert (s["rechazados_apertura_incompleta"], s["vacios_dr1"], s["con_bloom"], s["con_overflow"],
            s["con_precaucion"]) == (4, 2, 4, 1, 1)             # the groups overlap on purpose (BLOOM: 1–3 and 6)
    assert sq.has_unreported_loss(list(qs.values()))


def test_only_empty_dr1_channels_is_not_a_loss(cube):
    qs = sq.spectrum_quality(sc.extract_spectrum(*cube.centre))
    assert not sq.has_unreported_loss(qs) and sq.summary(qs)["vacios_dr1"] == 2
    assert [q.canal for q in qs if q.affected] == [51, 52]


def test_rows_without_coverage_information_do_not_break_anything():
    row = {"canal": 7, "lambda_um": 1.0, "detector": 1, "status": "no_data_aperture", "precaucion": False}
    q = sq.channel_quality(row)
    assert not q.available and q.rejected_incomplete_aperture and q.causes == ()
    assert sq.table_rows([q])[0]["Píxeles válidos"] == "no disponible" and sq.plain(q).startswith("Este canal no puede")
    assert sq.plain(sq.channel_quality({**row, "status": "ok"})) is None


def test_aperture_without_cube_pixels_is_described_not_crashed():
    row = {"canal": 7, "lambda_um": 1.0, "detector": 1, "status": "no_data_aperture", "precaucion": False,
           "ap_pix_total": 0, "ap_pix_invalidos": 0, "ap_pix_nan": 0, "ap_pix_nhits0": 0, "ap_peso_total": 0.0,
           "ap_peso_invalido": 0.0, "ap_bloom": 0, "ap_overflow": 0}
    q = sq.channel_quality(row)
    assert q.causes == (sq.NO_PIXELS,) and not q.rejected_incomplete_aperture
    assert sq.table_rows([q])[0]["Píxeles válidos"] == "0 píxeles en la apertura"


def test_plain_wording_for_the_simple_level():
    base = dict(canal=5, lambda_um=1.5, detector=2, available=True, valid_for_extraction=False,
                rejected_incomplete_aperture=True, caution=False)
    assert sq.plain(sq.ChannelQuality(status="no_data_aperture", **base)) == (
        "Este canal no puede analizarse porque parte de la región seleccionada no tiene datos utilizables.")
    assert "no hay suficiente información de fondo" in sq.plain(sq.ChannelQuality(status="no_background", **base))
    assert sq.ranges_text([(53, 2.72), (54, 2.8), (55, 2.9), (60, 3.3)]) == "2.72–2.90 µm, 3.30 µm"


# ----------------------------------------------------------------------------- page
def _text(at):
    return " ".join(str(x.value) for kind in ("caption", "markdown", "warning") for x in getattr(at, kind))


def _quality_frames(at):
    return [d.value for d in at.dataframe if "Causas" in list(d.value.columns)]


def test_simple_level_explains_in_plain_words_and_stays_quiet_without_losses(app_cube):
    at = spectral_app(app_cube)
    at.button_group(key="level").set_value("Simple").run()
    assert not at.exception and not any(e.label == "¿Por qué faltan algunos colores?" for e in at.expander)


def test_page_explains_rejected_channels_in_both_levels(punched, app_cube):
    at = spectral_app(punched)
    at.session_state[sa.INSPECT_KEY] = {"lo": 2, "hi": 2}
    at.run()
    assert not at.exception
    frames = _quality_frames(at)
    assert len(frames) == 2                                    # the interval and the whole-spectrum section
    interval, whole = frames
    assert list(interval.columns)[:2] == ["Canal", "λ (µm)"]                  # one position: no «Espectro» column
    by = {r["Canal"]: r for r in interval.to_dict("records")}
    assert by[2]["Estado"] == "Rechazado: apertura incompleta" and by[2]["Causas"] == "sin datos · BLOOM · apertura incompleta"
    assert by[2]["Píxeles sin datos"] == "1 (NaN 1 · NHITS = 0 1)"
    assert re.fullmatch(r"\d+ de \d+ \(\d+ %\)", by[2]["Píxeles válidos"])
    assert by[5]["Estado"] == "Válido, con precaución" and by[5]["Causas"] == "OVERFLOW"
    assert (by[2]["BLOOM"], by[2]["OVERFLOW"], by[5]["OVERFLOW"]) == ("1", "0", "1")
    blank = {r["Canal"]: r for r in whole.to_dict("records")}[51]               # no counts for a channel empty in DR1
    assert (blank["BLOOM"], blank["Estado"], blank["Causas"]) == ("—", "Sin datos en DR1", "canal vacío en DR1")
    assert {1, 2, 3, 4, 5} <= set(whole["Canal"]) and {51, 52} <= set(whole["Canal"])
    assert "Las causas pueden coexistir" in _text(at)
    # the table of the spectrum carries the new columns (CSV with provenance)
    assert any({"ap_pix_total", "ap_pix_invalidos", "ap_bloom", "ap_overflow"} <= set(d.value.columns) for d in at.dataframe)

    at.button_group(key="level").set_value("Simple").run()
    assert not at.exception
    txt = _text(at)
    assert "Este canal no puede analizarse porque parte de la región seleccionada no tiene datos utilizables." in txt
    assert any(e.label == "¿Por qué faltan algunos colores?" for e in at.expander)
    assert "Cerca de este color, 3 no pueden analizarse" in txt        # channels 1, 3 and 4 around the selected 2
    assert "4 colores sin analizar" in txt and not _quality_frames(at)
    assert at.session_state[sa.INSPECT_KEY] == {"lo": 2, "hi": 2}          # the level change keeps the selection


def test_second_position_gets_its_own_diagnosis_with_a_spectrum_column(punched, app_cube):
    at = spectral_app(punched)
    ra, dec = map(float, punched.tile.wcs.pixel_to_world_values(16, 26))    # B: far from the holes of A
    at.session_state[sa.B_KEY] = {"ra": ra, "dec": dec, "region": tuple(at.session_state["sx_region_key"])}
    at.session_state[sa.INSPECT_KEY] = {"lo": 2, "hi": 2}
    at.run()
    assert not at.exception
    interval = _quality_frames(at)[0]
    assert list(interval.columns)[0] == "Spectrum" and set(interval["Spectrum"]) == {"A"}      # B has nothing to tell here
    whole = _quality_frames(at)[1]
    assert {"A", "B"} == set(whole["Spectrum"]) and set(whole[whole["Spectrum"] == "B"]["Canal"]) == {51, 52}
