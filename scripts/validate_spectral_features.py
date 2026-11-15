"""Real-data validation of the A/B comparison and of the peak/valley inspection (SPHEREx DR1 cube).

Writes results/spectral_features_validation.json. Run with requirements-dev installed:

    .venv\\Scripts\\python scripts\\validate_spectral_features.py

Only byte ranges of the official FITS cubes are read (no tile is downloaded, no FITS is modified).
Positions: the nucleus of M101 (A) and its giant H II region NGC 5461 (B), and the position of the
official IRSA tutorial "Using SPHEREx HiPS All-Sky Mosaic Cubes", where the tutorial itself reports
strong emission at 3.3 µm.

Independent procedures (none of them calls ``spectral_features`` or the production aperture code):
  * Photutils exact-overlap aperture photometry in pixel coordinates (the tutorial's method);
  * differences, ratios and the reference scatter recomputed with plain NumPy from the tables;
  * the local continuum of each labelled feature refitted with ``numpy.polyfit``.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from astropy import units as u
from astropy.stats import SigmaClip
from photutils.aperture import ApertureStats, CircularAnnulus, CircularAperture, aperture_photometry

from skyclues import config, spectral_cube as sc, spectral_features as sf

M101_A = (210.802429, 54.34875)            # nucleus (centre of the validated M101 example)
M101_B = (210.923546, 54.319916)           # brightest arm pixel at 4.33 µm within 12′: NGC 5461
TUTORIAL = (60.8109955, 51.3404038)        # official IRSA cube tutorial
RADII = (2.0, 4.0, 7.0)                    # SkyClues default aperture and annulus (cube pixels)
#: Wavelengths that the official tutorial draws on its own spectrum plot (context only).
TUTORIAL_MARKS = {"Paβ": 1.282, "H− 1.6": 1.60, "Paα": 1.875, "Brγ": 2.166, "Brβ": 2.626, "PAH 3.3": 3.30,
                  "Brα": 4.052, "CO": 4.67}


def photutils_spectrum(ra: float, dec: float, radii) -> tuple[list, float]:
    """The tutorial's formula with Photutils exact overlaps (pixel-coordinate circles)."""
    tile = sc.tile_for(ra, dec)
    x, y = map(float, tile.wcs.world_to_pixel_values(ra, dec))
    outer = int(math.ceil(radii[2])) + 2
    x0, x1, y0, y1 = int(x) - outer, int(x) + outer, int(y) - outer, int(y) + outer
    assert 0 <= x0 and x1 <= 511 and 0 <= y0 and y1 <= 511, "position too close to the tile edge for this check"
    data = tile.read_rows({"IMAGE": list(range(102))}, y0, y1, x0, x1)["IMAGE"].astype(float)
    pos = (x - x0, y - y0)
    ap, ann = CircularAperture(pos, r=radii[0]), CircularAnnulus(pos, r_in=radii[1], r_out=radii[2])
    c0, c1, c2 = tile.wcs.pixel_to_world([x, x + 1, x], [y, y, y + 1])
    dx1, dy1 = c0.spherical_offsets_to(c1)
    dx2, dy2 = c0.spherical_offsets_to(c2)
    omega = abs(dx1 * dy2 - dx2 * dy1).to_value(u.sr)
    mask = ap.to_mask(method="exact").to_image(data.shape[1:]) > 0
    flux = []
    for plane, img in enumerate(data):
        if plane in (50, 51) or not np.isfinite(img[mask]).all():
            flux.append(None)
            continue
        bg = float(ApertureStats(img, ann, sigma_clip=SigmaClip(sigma=3.0, maxiters=10)).mean)
        total = float(aperture_photometry(img, ap)["aperture_sum"][0])
        flux.append((total - bg * float(ap.area_overlap(img))) * omega * 1e9)
    return flux, omega


def independent_contrast(lam, values, feature: sf.Feature) -> dict:
    """Continuum by numpy.polyfit (degree 2 in ln–ln) through the environment channels of the feature."""
    env = [c - 1 for c in feature.env_left + feature.env_right]
    k = feature.canal - 1
    y = np.array([values[i] for i in env], float)
    if not np.all(np.isfinite(y)) or values[k] is None:
        return {"continuo": None, "contraste": None, "relativo": None}
    if np.all(y > 0):
        coef = np.polyfit(np.log(lam[env]), np.log(y), 2)
        cont = float(np.exp(np.polyval(coef, math.log(lam[k]))))
    else:
        cont = float(np.polyval(np.polyfit(lam[env], y, 2), lam[k]))
    return {"continuo": cont, "contraste": float(values[k] - cont),
            "relativo": float((values[k] - cont) / cont) if cont > 0 else None}


def feature_report(series: sf.Series, analysis: sf.Analysis, other_values=None) -> list:
    out = []
    for f in analysis.features:
        row = {k: v for k, v in f.to_dict().items() if k in (
            "kind", "klass", "label", "canal", "canal_lo", "canal_hi", "trial_lo", "trial_hi", "lam", "lam_lo",
            "lam_hi", "n_channels", "width", "value", "continuum", "contrast", "relative", "ratio", "ref",
            "ref_local", "ref_detector", "ref_background", "env_left", "env_right", "detectors", "nhits_feature",
            "nhits_env", "limitations", "reasons")}
        if row["ratio"] is not None and not math.isfinite(row["ratio"]):
            row["ratio"] = None
        ind = independent_contrast(series.lam, [None if not np.isfinite(v) else float(v) for v in series.value], f)
        assert abs(ind["contraste"] - f.contrast) <= 1e-6 * max(1.0, abs(f.contrast)), (ind, f.contrast)
        row["polyfit_independiente"] = ind
        if other_values is not None:
            row["sobre_fotometria_photutils"] = independent_contrast(series.lam, other_values, f)
        row["marcas_del_tutorial_en_el_intervalo"] = [n for n, w in TUTORIAL_MARKS.items() if f.lam_lo <= w <= f.lam_hi]
        out.append(row)
    return out


def channel_with(series: sf.Series, wavelength: float) -> int:
    return int(series.canal[int(np.flatnonzero((series.lam_min <= wavelength) & (wavelength <= series.lam_max))[0])])


def inspect_33(series: sf.Series, analysis: sf.Analysis) -> dict:
    canal = channel_with(series, 3.30)
    f = sf.inspect_channel(series, canal, analysis.features, analysis.scatter)
    near = [{"canal": int(series.canal[i]), "lambda_um": float(series.lam[i]),
             "valor": None if not np.isfinite(series.value[i]) else float(series.value[i]),
             "nhits": float(series.nhits[i]), "precaucion": bool(series.caution[i])}
            for i in range(series.index(canal) - 4, series.index(canal) + 5)]
    return {"canal_que_contiene_3.30um": canal, "clase": f.klass, "tipo": f.kind, "canal_extremo": f.canal,
            "lambda_um": f.lam, "intervalo_um": [f.lam_lo, f.lam_hi], "valor": f.value, "continuo": f.continuum,
            "contraste": f.contrast, "relativo": f.relative,
            "contraste_sobre_dispersion": None if f.ratio is None or not math.isfinite(f.ratio) else f.ratio,
            "motivos": f.reasons, "limitaciones": f.limitations, "canales_vecinos": near}


def audit() -> dict:
    out = {"metodo": sf.method_summary(), "tutorial_url": config.CUBE_TUTORIAL_URL,
           "posiciones_icrs_deg": {"M101_A_nucleo": M101_A, "M101_B_NGC5461": M101_B, "tutorial_IRSA": TUTORIAL},
           "radios_px": RADII,
           "limitaciones": [
               "Espectros exploratorios del cubo combinado: sin incertidumbres ni corrección de apertura.",
               "Las clases de las características son criterios descriptivos, no detecciones estadísticas.",
               "La coincidencia de un pico con una longitud de onda marcada en el tutorial no identifica una "
               "molécula ni una línea: esa identificación no forma parte de esta fase."]}

    # ---- cold and warm extraction of A and B (empty temporary cache), resources
    real_cache = config.CACHE_DIR
    with tempfile.TemporaryDirectory() as tmp:
        config.CACHE_DIR = Path(tmp)
        sc._tiles.clear()
        sc._cache_bytes = None
        sc.io_stats(reset=True)
        tracemalloc.start()
        t0 = time.perf_counter()
        cold_a = sc.extract_spectrum(*M101_A, sc.Aperture(*RADII))
        ta, io_a = time.perf_counter() - t0, sc.io_stats(reset=True)
        t0 = time.perf_counter()
        cold_b = sc.extract_spectrum(*M101_B, sc.Aperture(*RADII))
        tb, io_b = time.perf_counter() - t0, sc.io_stats(reset=True)
        t0 = time.perf_counter()
        warm_b = sc.extract_spectrum(*M101_B, sc.Aperture(*RADII))
        tw, io_w = time.perf_counter() - t0, sc.io_stats(reset=True)
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        config.CACHE_DIR = real_cache
        sc._tiles.clear()
        sc._cache_bytes = None
    assert io_w["requests"] == 0 and warm_b.rows == cold_b.rows, "a repeated extraction must be identical and local"
    assert peak < 150 * 2**20
    out["rendimiento"] = {
        "extraccion_A_en_frio": {"segundos": ta, **io_a}, "extraccion_B_tras_A": {"segundos": tb, **io_b},
        "repeticion_B_desde_cache": {"segundos": tw, **io_w}, "memoria_python_pico_bytes": peak,
        "nota": "B se lee de las mismas teselas ya abiertas; sus filas son otras, así que se piden por rangos "
                "(no se descarga ninguna tesela completa). Una repetición no hace ninguna petición."}

    # ---- M101: two positions extracted the same way
    spec_a, spec_b = cold_a, cold_b
    sa, sb = sf.series_from_spectrum(spec_a, "flux", "A"), sf.series_from_spectrum(spec_b, "flux", "B")
    issues, notes, sep = sf.compatibility(sa, sb)
    assert not issues and np.array_equal(sa.canal, sb.canal) and np.array_equal(sa.lam, sb.lam)
    assert spec_a.aperture == spec_b.aperture and spec_a.pixel_solid_angle_sr == spec_b.pixel_solid_angle_sr
    cmp = sf.compare(sa, sb)
    out["m101"] = {"separacion_arcsec": sep, "avisos": notes, "unidad": cmp.unit,
                   "teselas": {"A": sa.meta["tiles"], "B": sb.meta["tiles"]},
                   "apertura_efectiva_px": {"A": spec_a.n_aperture_px, "B": spec_b.n_aperture_px},
                   "canales_medidos": {"A": spec_a.n_measured, "B": spec_b.n_measured},
                   "resumen_comparacion": cmp.summary}

    # independent recomputation of A − B, A / B and of the stability filter (plain NumPy)
    def col(spec, key):
        return np.array([np.nan if r[key] is None else r[key] for r in spec.rows], float)
    a, b = col(spec_a, "flujo_mjy"), col(spec_b, "flujo_mjy")
    n_ap, n_bg = spec_b.n_aperture_px, col(spec_b, "n_fondo")
    with np.errstate(divide="ignore", invalid="ignore"):          # channels without annulus data: no reference
        ref_b = col(spec_b, "fondo_sigma_mjysr") * np.sqrt(n_ap + n_ap**2 / n_bg) * spec_b.pixel_solid_angle_sr * 1e9
    both = np.isfinite(a) & np.isfinite(b)
    valid = both & (a > 0) & (b > 0) & (b >= sf.RATIO_MIN_DENOMINATOR * ref_b)
    prod_d = np.array([np.nan if r["diferencia"] is None else r["diferencia"] for r in cmp.rows])
    prod_q = np.array([np.nan if r["relacion"] is None else r["relacion"] for r in cmp.rows])
    assert np.array_equal(np.isfinite(prod_d), both) and np.allclose(prod_d[both], (a - b)[both], rtol=0, atol=0)
    assert np.array_equal(np.isfinite(prod_q), valid) and np.allclose(prod_q[valid], (a / b)[valid], rtol=1e-15)
    out["m101"]["recalculo_numpy"] = {"canales_con_ambos": int(both.sum()), "canales_con_relacion": int(valid.sum()),
                                      "diferencia_identica": True, "relacion_identica": True}

    # independent photometry (Photutils, pixel circles) of both positions
    pa, omega_a = photutils_spectrum(*M101_A, RADII)
    pb, omega_b = photutils_spectrum(*M101_B, RADII)
    assert abs(omega_a / spec_a.pixel_solid_angle_sr - 1) < 1e-3 and abs(omega_b / spec_b.pixel_solid_angle_sr - 1) < 1e-3

    def versus(prod, ind):
        rel = np.array([(p - i) / i for p, i in zip(prod, ind) if i is not None and np.isfinite(p) and abs(i) > 0])
        return {"canales": int(rel.size), "mediana_relativa": float(np.median(rel)),
                "mediana_abs_relativa": float(np.median(np.abs(rel))), "max_abs_relativa": float(np.max(np.abs(rel)))}
    out["m101"]["produccion_frente_a_photutils"] = {"A": versus(a, pa), "B": versus(b, pb)}
    assert out["m101"]["produccion_frente_a_photutils"]["A"]["mediana_abs_relativa"] < 0.10
    ind_d = np.array([np.nan if x is None or y is None else x - y for x, y in zip(pa, pb)])
    ok = np.isfinite(prod_d) & np.isfinite(ind_d)
    out["m101"]["diferencia_A_menos_B"] = {
        "mediana_produccion_mjy": float(np.median(prod_d[ok])), "mediana_photutils_mjy": float(np.median(ind_d[ok])),
        "mediana_abs_desacuerdo_mjy": float(np.median(np.abs(prod_d[ok] - ind_d[ok]))),
        "causa_del_desacuerdo": "círculo sobre el cielo con 5×5 submuestras (producción) frente a círculo en "
                                "coordenadas de píxel con solapamiento exacto (Photutils); mismo fondo y fórmula."}

    # features
    an_a, an_b = sf.analyse(sa), sf.analyse(sb)
    out["m101"]["caracteristicas"] = {"A": feature_report(sa, an_a, pa), "B": feature_report(sb, an_b, pb)}
    out["m101"]["oscilaciones_no_señaladas"] = {"A": sf.unlabelled_extrema(sa, an_a.features),
                                                "B": sf.unlabelled_extrema(sb, an_b.features)}
    out["m101"]["inspeccion_3.3um"] = {"A": inspect_33(sa, an_a), "B": inspect_33(sb, an_b)}
    f33 = out["m101"]["inspeccion_3.3um"]["B"]
    assert f33["tipo"] == "pico" and f33["clase"] in (sf.QUANTIFIABLE, sf.VISIBLE)
    # the same interval of B measured in A: the feature is in one spectrum and not in the other
    fb33 = sf.inspect_channel(sb, f33["canal_que_contiene_3.30um"], an_b.features, an_b.scatter)
    fa33 = sf.measure_interval(sa, fb33.trial_lo, fb33.trial_hi, an_a.features, an_a.scatter)
    out["m101"]["mismo_intervalo_en_A"] = {"clase": fa33.klass, "contraste": fa33.contrast, "relativo": fa33.relative,
                                           "contraste_sobre_dispersion": fa33.ratio}

    # ---- official tutorial position: the tutorial reports strong emission at 3.3 µm there
    tut = {}
    for name, radii in (("apertura_2_4_7_px", RADII), ("apertura_5_15_20_px", (5.0, 15.0, 20.0))):
        spec = sc.extract_spectrum(*TUTORIAL, sc.Aperture(*radii))
        s = sf.series_from_spectrum(spec, "flux", "T")
        an = sf.analyse(s)
        tut[name] = {"inspeccion_3.3um": inspect_33(s, an), "caracteristicas": feature_report(s, an)}
        assert tut[name]["inspeccion_3.3um"]["tipo"] == "pico"
    t_flux, _ = photutils_spectrum(*TUTORIAL, (5, 40, 60))            # the tutorial's own radii
    lam = sf.series_from_spectrum(sc.extract_spectrum(*TUTORIAL), "flux").lam
    c33 = tut["apertura_5_15_20_px"]["inspeccion_3.3um"]["canal_extremo"]
    env = [c33 - 1 + d for d in (-3, -2, -1, 1, 2, 3)]
    coef = np.polyfit(np.log(lam[env]), np.log([t_flux[i] for i in env]), 2)
    cont = float(np.exp(np.polyval(coef, math.log(lam[c33 - 1]))))
    tut["fotometria_del_tutorial_5_40_60_px"] = {
        "canal": c33, "flujo_mjy": t_flux[c33 - 1], "continuo_polyfit_mjy": cont,
        "contraste_mjy": t_flux[c33 - 1] - cont, "relativo": (t_flux[c33 - 1] - cont) / cont,
        "nota": "Fotometría independiente con los radios del tutorial (fuera del límite de la aplicación, 20 px). "
                "El contraste difiere del de la apertura de 5/15/20 px porque el anillo de fondo es otro."}
    assert tut["fotometria_del_tutorial_5_40_60_px"]["contraste_mjy"] > 0
    out["tutorial"] = tut
    out["io_validacion_total"] = sc.io_stats(reset=True)
    return out


def _clean(v):
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (np.floating, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


if __name__ == "__main__":
    result = _clean(audit())
    path = config.RESULTS_DIR / "spectral_features_validation.json"
    path.write_text(json.dumps(result, indent=1, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    m = result["m101"]
    print(f"Escrito {path}")
    print("Rendimiento:", json.dumps(result["rendimiento"], ensure_ascii=False))
    print("M101 separación %.0f″ · producción vs Photutils: %s" % (m["separacion_arcsec"],
                                                                    json.dumps(m["produccion_frente_a_photutils"])))
    print("Comparación:", json.dumps(m["resumen_comparacion"], ensure_ascii=False)[:600])
    for k in ("A", "B"):
        for f in m["caracteristicas"][k]:
            print("  %s %s %s canal %d %.3f µm contraste %+.2f mJy (%s) razón %s · Photutils %+.2f · marcas tutorial %s" % (
                k, f["kind"], f["klass"], f["canal"], f["lam"], f["contrast"],
                "—" if f["relative"] is None else "%+.0f%%" % (100 * f["relative"]),
                "—" if f["ratio"] is None else "%.1f" % f["ratio"],
                f["sobre_fotometria_photutils"]["contraste"] or float("nan"), f["marcas_del_tutorial_en_el_intervalo"]))
    print("3.3 µm A:", m["inspeccion_3.3um"]["A"]["clase"], "| B:", m["inspeccion_3.3um"]["B"]["clase"],
          "| mismo intervalo en A:", m["mismo_intervalo_en_A"])
    for k, v in result["tutorial"].items():
        print("Tutorial", k, json.dumps({a: b for a, b in (v.get("inspeccion_3.3um") or v).items()
                                          if a not in ("canales_vecinos", "motivos", "limitaciones")},
                                         ensure_ascii=False)[:420])
