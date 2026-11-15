"""REAL-FITS validation of the infrared S/N enhancement (``skyclues.enhance``).

Run with the .venv Python from the repository root:

    python scripts/validate_enhance.py            # every case
    python scripts/validate_enhance.py wise0855_d6_nov2025

Every case combines authentic SPHEREx Level-2 exposures (cutouts served by NASA/IPAC IRSA, read from
the verbatim cache when present) and measures, on the same pixels, what one exposure gives and what
the combination gives. Outputs in ``results/enhance/``: one JSON per case (exposures with URL and
SHA-256, selection, metrics, verdict), the comparison figures, and a summary table.

The selection of exposures is reproducible: sidereal cases come from the SIA2 records of the field
(``enhance.nearby_exposures``) or from a saved Time Explorer sequence; moving bodies from the saved
MOST discoveries used by ``validate_motion.py``. When the archive cannot be queried, the exposures
listed in a previous JSON of the same case are fetched again by URL.

Nothing here changes the motion detectors or their accepted results.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import numpy as np
from astropy.time import Time

from skyclues import archive, enhance as en, enhance_view as view, fitsdata, motion, non_sidereal
from skyclues.geometry import gnomonic, separation_deg

OUT = ROOT / "results" / "enhance"
PX = 6.15
WISE = dict(ra=133.7601752, dec=-7.2422453, fov=0.2, detector=6, collection="spherex_dr1", catalogue="allwise",
            target=(133.76020235140194, -7.2422441274445735))

SIDEREAL = [
    dict(label="m101_sequence", title="M101 · secuencia de Time Explorer (mismo canal)", sequence="sequence_m101.json",
         catalogue="2mass", role="Campo estacionario · monocromático"),
    dict(label="m101_d2_dec2025", title="M101 · D2 · diciembre de 2025 (banda ancha)", ra=210.802429, dec=54.34875,
         fov=0.2, detector=2, mjd=61018.0, collection="spherex_dr1", catalogue="2mass",
         role="Campo estacionario · banda ancha"),
    dict(label="wise0855_d6_nov2025", title="WISE 0855−0714 · D6 · noviembre de 2025", mjd=60991.4,
         season="2025-11-10", role="Objeto débil · banda ancha", **WISE),
    dict(label="wise0855_d6_dec2025", title="WISE 0855−0714 · D6 · diciembre de 2025", mjd=61021.6,
         season="2025-12-12", role="Objeto débil · banda ancha", **WISE),
    dict(label="wise0855_d6_apr2026", title="WISE 0855−0714 · D6 · abril–mayo de 2026", mjd=61163.0,
         season="2026-04-26", role="Objeto débil · banda ancha", **WISE),
    dict(label="wise0855_d6_may2025", title="WISE 0855−0714 · D6 · mayo de 2025 (solo dos exposiciones)",
         mjd=60800.75, role="Caso límite · dos exposiciones", **WISE),
]
MOVING = [  # label, title, discovery, detector, last characters of the first exposure id
    ("atlas_aug_d1_comoving", "3I/ATLAS · D1 · 9-8-2025 · siguiendo la efeméride", "atlas_aug", 1, "0343_1"),
    ("juno_d1_comoving", "3 Juno · D1 · julio de 2025 · siguiendo la efeméride", "juno_year", None, None),
    ("vesta_d1_comoving", "4 Vesta · D1 · siguiendo la efeméride", "vesta_year", None, None),
]
TAP = {"allwise": ("allwise_p3as_psd", "ra, dec, w1mpro, w2mpro"), "2mass": ("fp_psc", "ra, dec, j_m, h_m, k_m")}
#: The same catalogues at CDS VizieR, used only when IRSA TAP does not answer.
VIZIER = {"allwise": ('"II/328/allwise"', "RAJ2000 AS ra, DEJ2000 AS dec, W1mag AS w1mpro, W2mag AS w2mpro"),
          "2mass": ('"II/246/out"', "RAJ2000 AS ra, DEJ2000 AS dec, Jmag AS j_m, Hmag AS h_m, Kmag AS k_m")}


def jsonable(v):
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    return str(v)


def save(label, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{label}.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=jsonable),
                                       encoding="utf-8")


# ----------------------------------------------------------------------------- exposures
def exposures_for(case):
    """(exposures, provenance of the selection). Archive first; previous manifest if it cannot be queried."""
    if "sequence" in case:
        from skyclues import sequence
        seq = sequence.load_sequence(ROOT / "results" / case["sequence"])
        case.update(ra=float(seq.ra), dec=float(seq.dec), fov=float(seq.field_deg))
        return [en.exposure_from(f) for f in seq.frames], {
            "rule": f"fotogramas de results/{case['sequence']} (criterios S1–S9 de Time Explorer)"}
    rule = (f"enhance.nearby_exposures: D{case['detector']}, {case['collection']}, campo completo en el detector, "
            f"|Δt| ≤ {en.NEARBY_DAYS:g} d alrededor de MJD {case['mjd']}, máx. {en.MAX_NEARBY}")
    try:
        recs = archive.query_images(case["ra"], case["dec"])
        cands = en.nearby_exposures(recs, case["ra"], case["dec"], case["fov"], case["detector"], case["mjd"],
                                    collection=case["collection"])
        exps, failures = en.fetch_exposures(cands, case["ra"], case["dec"], case["fov"])
        return exps, {"rule": rule, "sia2": getattr(recs, "provenance", {}), "candidates": len(cands),
                      "failures": failures}
    except archive.ArchiveError as err:
        prev = OUT / f"{case['label']}.json"
        if not prev.exists():
            raise
        rows = json.loads(prev.read_text(encoding="utf-8"))["exposures"]
        got = archive.fetch_many([r["cutout_url"] for r in rows])
        exps = []
        for r in rows:
            path = got[r["cutout_url"]]
            if isinstance(path, Exception):
                raise path
            exps.append(en.Exposure(fitsdata.load(path), r["obs_id"], r["mjd"], r["collection"], r["cutout_url"],
                                    archive.sha256(path)))
        return exps, {"rule": rule, "sia2": {"origin": "manifiesto anterior", "error": str(err)[:200]}}


# ----------------------------------------------------------------------------- external catalogue
def catalogue(name, label, ra, dec, radius_deg):
    """Independent catalogue positions from NASA/IPAC IRSA (Gator; TAP at IRSA or CDS if it does not
    answer), saved so the comparison can be repeated offline."""
    path = OUT / f"catalogue_{label}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    table, cols = TAP[name]
    names = [c.strip() for c in cols.split(",")]
    errors = []
    rows = service = query = None
    try:
        import requests
        from astropy.io import ascii as ioascii
        service = "https://irsa.ipac.caltech.edu/cgi-bin/Gator/nph-query"
        params = {"catalog": table, "spatial": "cone", "objstr": f"{ra:.7f} {dec:.7f}",
                  "radius": f"{radius_deg * 3600:.1f}", "radunits": "arcsec", "outfmt": "1", "selcols": ",".join(names)}
        resp = requests.get(service, params=params, headers={"User-Agent": "astropy-client"}, timeout=120)
        resp.raise_for_status()
        tab = ioascii.read(resp.text.splitlines(), format="ipac")
        query = resp.url
        rows = [{c: (None if np.ma.is_masked(r[c]) else float(r[c])) for c in names} for r in tab]
    except Exception as err:  # noqa: BLE001 - external service: try the next one, record every failure
        errors.append(f"Gator: {type(err).__name__}: {str(err)[:120]}")
    if rows is None:
        import pyvo
        for service, (tbl, sel, pos) in (
                ("https://irsa.ipac.caltech.edu/TAP", (table, cols, "ra, dec")),
                ("https://tapvizier.cds.unistra.fr/TAPVizieR/tap", (*VIZIER[name], "RAJ2000, DEJ2000"))):
            query = (f"SELECT {sel} FROM {tbl} WHERE 1 = CONTAINS(POINT('ICRS', {pos}), "
                     f"CIRCLE('ICRS', {ra:.7f}, {dec:.7f}, {radius_deg:.5f}))")
            try:
                tab = pyvo.dal.TAPService(service).search(query).to_table()
                rows = [{c: (None if np.ma.is_masked(r[c]) else float(r[c])) for c in names} for r in tab]
                break
            except Exception as err:  # noqa: BLE001
                errors.append(f"{service}: {type(err).__name__}: {str(err)[:120]}")
    if rows is None:
        raise RuntimeError(" · ".join(errors))
    out = {"catalogue": name, "table": table, "service": service, "query": query,
           "queried_utc": Time.now().isot[:19], "service_errors": errors, "rows": rows}
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=0), encoding="utf-8")
    return out


def crossmatch(sources, cat, radius_arcsec=PX):
    """Fraction of detections with a catalogue source within one native pixel, and the chance rate
    (the same test with the detections displaced 40 arcsec in four directions)."""
    if not cat["rows"] or not sources:
        return None
    cr = np.array([r["ra"] for r in cat["rows"]])
    cd = np.array([r["dec"] for r in cat["rows"]])

    def nearest(ra, dec):
        return float(np.min(separation_deg(cr, cd, ra, dec)) * 3600)

    for s in sources:
        s["catalogue_arcsec"] = nearest(s["ra"], s["dec"])
    chance = []
    for de, dn in ((40, 0), (-40, 0), (0, 40), (0, -40)):
        chance.append(np.mean([nearest(s["ra"] + de / 3600 / math.cos(math.radians(s["dec"])), s["dec"] + dn / 3600)
                               <= radius_arcsec for s in sources]))

    def frac(rows):
        return {"n": len(rows), "matched": int(sum(s["catalogue_arcsec"] <= radius_arcsec for s in rows))}

    new = [s for s in sources if s["detected_in_single"] == 0 and not s.get("single_exposure_only")]
    old = [s for s in sources if s["detected_in_single"] > 0]
    return {"catalogue": cat["catalogue"], "n_catalogue": len(cat["rows"]), "radius_arcsec": radius_arcsec,
            "all": frac(sources), "new_in_combined": frac(new), "seen_in_single": frac(old),
            "chance_fraction": float(np.mean(chance)),
            "note": "Coincidencia = fuente del catálogo a menos de un píxel nativo. «chance_fraction»: la misma "
                    "prueba con las detecciones desplazadas 40″ en cuatro direcciones (coincidencias casuales)."}


# ----------------------------------------------------------------------------- positions
def stack_position(stack, x, y):
    """ePSF fit on the combined image (reference exposure's ePSF): sky position and formal error."""
    if stack.oversample != 1:
        return None
    img = stack.exposures[stack.reference].image
    var = stack.variance * (stack.noise.get("scale") or 1.0) ** 2
    fit = motion.fit_psf(stack.image, var, np.isfinite(stack.image), motion.psf_for(img, x, y), x, y, max_shift=2.0)
    if fit is None or not fit["converged"]:
        return None
    dx, dy = en.placement_correction(stack, fit["x"], fit["y"])
    ra, dec = stack.wcs.all_pix2world(fit["x"] + dx, fit["y"] + dy, 0)
    raw = stack.wcs.all_pix2world(fit["x"], fit["y"], 0)
    fit_err = PX * math.sqrt(float(np.max(np.linalg.eigvalsh(np.array(fit["cov_px"])))))
    place = stack.registration.get("placement_rms_arcsec") or 0.0
    return {"ra": float(ra), "dec": float(dec), "snr": fit["snr"], "fit_error_arcsec": fit_err,
            "error_arcsec": math.hypot(fit_err, place), "chi2_red": fit["chi2_red"],
            "uncorrected_radec_deg": [float(raw[0]), float(raw[1])],
            "placement_correction_arcsec": [dx * PX, dy * PX],
            "note": "Ajuste ePSF sobre la imagen combinada; se corrige el desplazamiento medio conocido del "
                    "remuestreo por vecino más próximo y se suma en cuadratura su dispersión en el campo."}


def single_positions(stack, ra, dec):
    """The same fit on every exposure's native pixels (strict mask), starting at the same sky position."""
    out = []
    for e in stack.exposures:
        x, y = (float(v) for v in non_sidereal.world_to_pixel(e.image.wcs, ra, dec))
        fit = non_sidereal._fit_position(e.image, x, y, e.image.valid(), 2.0) if non_sidereal.inside(e.image, x, y) else None
        if fit is None or not fit["converged"]:
            out.append(None)
            continue
        r, d = e.image.wcs.all_pix2world(fit["x"], fit["y"], 0)
        err = PX * math.sqrt(float(np.max(np.linalg.eigvalsh(np.array(fit["cov_px"])))))
        out.append({"ra": float(r), "dec": float(d), "snr": fit["snr"], "error_arcsec": err})
    return out


def astrometry_vs_catalogue(stack, sources, cat, max_snr=40.0):
    """Offsets from independent catalogue positions, for the combination and for single exposures,
    in faint sources (where noise, not the pixel phase, limits a position)."""
    cr = np.array([r["ra"] for r in cat["rows"]])
    cd = np.array([r["dec"] for r in cat["rows"]])
    comb, single, formal_c, formal_s, tried, measured = [], [], [], [], 0, 0
    for s in sources:
        if s.get("snr") is None or not 6 <= s["snr"] <= max_snr or s.get("catalogue_arcsec", 99) > PX:
            continue
        k = int(np.argmin(separation_deg(cr, cd, s["ra"], s["dec"])))
        p = stack_position(stack, s["x"], s["y"])
        if p is None:
            continue
        comb.append(float(separation_deg(p["ra"], p["dec"], cr[k], cd[k]) * 3600))
        formal_c.append(p["error_arcsec"])
        for q in single_positions(stack, s["ra"], s["dec"]):
            tried += 1
            if q is not None and q["snr"] >= 5:
                measured += 1
                single.append(float(separation_deg(q["ra"], q["dec"], cr[k], cd[k]) * 3600))
                formal_s.append(q["error_arcsec"])
    if len(comb) < 5:
        return None
    return {"n_sources": len(comb), "combined_median_offset_arcsec": float(np.median(comb)),
            "single_median_offset_arcsec": float(np.median(single)) if single else None,
            "combined_formal_error_arcsec": float(np.median(formal_c)),
            "single_formal_error_arcsec": float(np.median(formal_s)) if formal_s else None,
            "single_fits_tried": tried, "single_fits_measured": measured,
            "note": f"Fuentes con S/N combinada entre 6 y {max_snr:g} y contrapartida de catálogo a menos de un "
                    "píxel. Separación entre la posición ajustada (ePSF) y la del catálogo. En las exposiciones "
                    "individuales solo cuentan los ajustes que convergen con S/N ≥ 5: las que no se pueden medir "
                    "no entran en su mediana, lo que la favorece."}


def target_analysis(case, stack, metrics):
    """The catalogued faint object of the case: what one exposure shows and what the combination shows."""
    ra, dec = case["target"]
    x, y = (float(v) for v in stack.wcs.all_world2pix(ra, dec, 0))
    near = sorted((s for s in metrics["sources"] if math.hypot(s["x"] - x, s["y"] - y) <= 2.5),
                  key=lambda s: -s["significance"])
    out = {"selected_radec_deg": [ra, dec], "detected_in_combination": bool(near)}
    if not near:
        m = en.measure_source(stack, round(x), round(y))
        out.update(snr=m["snr"] if m else None, snr_single=m["snr_single"] if m else None,
                   reason="Sin detección ≥ 5σ en la posición del objeto en la imagen combinada.")
        return out, (round(x), round(y))
    s = near[0]
    out.update({k: s.get(k) for k in ("x", "y", "ra", "dec", "significance", "significance_single", "detected_in_single",
                                      "snr", "snr_single", "snr_single_median", "snr_single_best", "gain",
                                      "gain_vs_best", "flux_mjy", "flux_err_mjy", "single_exposure_fraction",
                                      "single_exposure_only", "n_contributions")})
    out["offset_from_selection_arcsec"] = float(math.hypot(s["x"] - x, s["y"] - y) * PX)
    p = stack_position(stack, s["x"], s["y"])
    singles = single_positions(stack, s["ra"], s["dec"])
    out["position_fit"] = p
    out["single_position_fits"] = {
        "tried": len(singles), "measured_snr5": int(sum(q is not None and q["snr"] >= 5 for q in singles)),
        "measured_snr8": int(sum(q is not None and q["snr"] >= 8 for q in singles)),
        "snr": [None if q is None else round(q["snr"], 1) for q in singles],
        "error_arcsec": [None if q is None else round(q["error_arcsec"], 2) for q in singles]}
    ref = ROOT / "results" / "motion_wise0855_d6.json"
    if p and case.get("season") and ref.exists():
        r = json.loads(ref.read_text(encoding="utf-8"))
        season = next((q for q in r["seasons"] if q["date_utc"] == case["season"]), None)
        if season:
            ra0, dec0 = r["source"]["selected_ra"], r["source"]["selected_dec"]
            xi, eta = (float(v) * 3600 for v in gnomonic(p["ra"], p["dec"], ra0, dec0))
            out["accepted_detector_comparison"] = {
                "combined_xi_eta_arcsec": [xi, eta], "detector_xi_eta_arcsec": [season["xi"], season["eta"]],
                "detector_error_arcsec": [season["err_xi"], season["err_eta"]],
                "difference_arcsec": float(math.hypot(xi - season["xi"], eta - season["eta"])),
                "note": "Posición ajustada en la imagen combinada frente a la posición de la misma temporada medida "
                        "por el detector estelar aceptado (ajuste conjunto en píxeles nativos, results/"
                        "motion_wise0855_d6.json). Comparación de coherencia: no sustituye ni modifica esa medida."}
    return out, (s["x"], s["y"])


# ----------------------------------------------------------------------------- cases
def row_for(case_label, title, role, stack, metrics, extra=None):
    sel = stack.selection
    g, pn, res, ast = metrics["gain"], metrics["pixel_noise_mjysr"], metrics["resolution"], metrics["astrometry"]
    verdict = en.verdict(metrics)
    dates = [str(e.image.meta.get("DATE-AVG"))[:16] for e in stack.exposures]
    r2 = lambda v, n=2: None if v is None else round(float(v), n)  # noqa: E731
    return {"label": case_label, "title": title, "role": role, "n_exposures": stack.n_exposures,
            "rejected_exposures": len(sel["rejected"]), "detector": sel["detector"], "kind": sel["kind"],
            "lambda_range_um": [round(v, 4) for v in sel["lambda_range_um"]],
            "first_utc": min(dates), "last_utc": max(dates), "span_days": round(sel["span_days"], 2),
            "pixel_noise_single_mjysr": round(pn["single_median"], 5),
            "pixel_noise_combined_mjysr": round(pn["combined"], 5), "pixel_noise_ratio": round(pn["ratio"], 2),
            "null_scale": r2(stack.noise.get("null_scale"), 3),
            "sources_measured": g["n_sources"], "gain_median": r2(g["median"]),
            "gain_p16_p84": None if g["median"] is None else [round(g["p16"], 2), round(g["p84"], 2)],
            "gain_vs_best_exposure": r2(g["vs_best_exposure_median"]), "sqrt_n": round(g["sqrt_n"], 2),
            "detections_single_median": metrics["detections"]["single_median"],
            "detections_combined": metrics["detections"]["combined"],
            "new_in_combined": metrics["detections"]["new_in_combined"],
            "single_exposure_only": metrics["detections"]["single_exposure_only"],
            "null_spurious": metrics["detections"]["null_image_spurious"],
            "negative_image": metrics["detections"]["negative_image"],
            "psf_width_ratio": r2(res["width_ratio"], 3),
            "centroid_shift_arcsec": None if ast["median_shift_arcsec"] is None
            else round(float(np.hypot(*ast["median_shift_arcsec"])), 2),
            "flux_ratio": r2(metrics["photometry"]["flux_ratio_median"], 4),
            "registration_max_arcsec": r2(stack.registration.get("max_shift_arcsec")),
            "accepted": verdict["accepted"], "reasons": verdict["reasons"], **(extra or {})}


def run_sidereal(case):
    exps, how = exposures_for(case)
    try:
        stack = en.combine(exps, case["ra"], case["dec"], case["fov"])
    except en.EnhanceError as err:
        row = {"label": case["label"], "title": case["title"], "role": case["role"], "n_exposures": len(exps),
               "accepted": False, "reasons": [str(err)]}
        save(case["label"], {**row, "selection_rule": how})
        return row
    metrics = en.evaluate(stack)
    payload = en.summary(stack, metrics)
    payload.update(case={k: v for k, v in case.items() if k != "target"}, selection_rule=how,
                   repeatability=en.repeatability(stack, metrics["sources"]))
    extra = {}
    try:
        cat = catalogue(case["catalogue"], case["label"], case["ra"], case["dec"], case["fov"] / 2 + 0.01)
        payload["catalogue_crossmatch"] = crossmatch(metrics["sources"], cat)
        payload["astrometry_vs_catalogue"] = astrometry_vs_catalogue(stack, metrics["sources"], cat)
        payload["sources"] = metrics["sources"]
    except Exception as err:  # noqa: BLE001 - an external service; reported, never hidden
        payload["catalogue_crossmatch"] = {"unavailable": f"{type(err).__name__}: {str(err)[:200]}"}
    cm = payload.get("catalogue_crossmatch") or {}
    if "new_in_combined" in cm:
        extra["new_with_catalogue_counterpart"] = f"{cm['new_in_combined']['matched']}/{cm['new_in_combined']['n']}"
        extra["chance_match_fraction"] = round(cm["chance_fraction"], 3)
    av = payload.get("astrometry_vs_catalogue")
    if av:
        extra["position_offset_combined_arcsec"] = round(av["combined_median_offset_arcsec"], 2)
        extra["position_offset_single_arcsec"] = None if av["single_median_offset_arcsec"] is None \
            else round(av["single_median_offset_arcsec"], 2)
        extra["single_position_fits"] = f"{av['single_fits_measured']}/{av['single_fits_tried']}"
    rp = payload.get("repeatability")
    if rp:
        extra["repeatability_ratio"] = None if rp["ratio"] is None else round(rp["ratio"], 2)
        extra["repeatability_expected"] = round(rp["expected_ratio"], 2)
    new = [s for s in metrics["sources"] if s["detected_in_single"] == 0 and not s.get("single_exposure_only")]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{case['label']}_comparison.png").write_bytes(view.comparison_png(stack, marks=new, dpi=140))
    (OUT / f"{case['label']}_null.png").write_bytes(view.diagnostic_png(stack, dpi=140))
    if case.get("target"):
        t, (tx, ty) = target_analysis(case, stack, metrics)
        payload["target"] = t
        r1 = lambda vals: None if not vals else [None if v is None else round(v, 1) for v in vals]  # noqa: E731
        extra.update(target_snr_combined=None if t.get("snr") is None else round(t["snr"], 1),
                     target_snr_single=r1(t.get("snr_single")),
                     target_significance_combined=None if t.get("significance") is None else round(t["significance"], 1),
                     target_significance_single=r1(t.get("significance_single")))
        (OUT / f"{case['label']}_target.png").write_bytes(
            view.zoom_png(stack, tx, ty, title=case["title"] + " · posición del objeto", dpi=140))
    save(case["label"], payload)
    return row_for(case["label"], case["title"], case["role"], stack, metrics, extra)


def run_moving(label, title, name, detector, first):
    """Co-moving stack of a known body along its ephemeris, with displaced-track controls.

    The position in this image is set by the ephemeris: nothing here is a measurement of motion.
    """
    import validate_motion as vm
    from skyclues import moving_sources as ms
    from skyclues.quality import SATURATION

    d = vm.discovery(name)
    rows = vm.pick(ms.motion_groups(d["rows"]), detector, first)
    base = {"label": label, "title": title, "role": "Objeto móvil · siguiendo la efeméride"}
    if rows is None:
        return {**base, "accepted": False, "reasons": ["No hay exposiciones del mismo detector lo bastante próximas."]}
    frames, failures = non_sidereal.fetch_frames(d["identity"], rows, 0.1, lambda m: None)
    centres = [(f.prediction["ra"], f.prediction["dec"]) for f in frames]
    fov = 0.1
    base.update(n_exposures=len(frames), detector=rows[0]["detector"])

    def centre(stack):
        c = (stack.shape[0] - 1) // 2
        return en.measure_source(stack, c, c), c

    try:
        stack = en.combine(frames, centres[0][0], centres[0][1], fov, purpose="comoving", centres=centres)
    except en.EnhanceError as err:
        row = {**base, "accepted": False, "reasons": [str(err)]}
        save(label, row)
        return row
    m, c = centre(stack)
    controls = []
    for de, dn in ((0, 90), (-120, 0), (75, -75)):
        moved = [(r + de / 3600 / math.cos(math.radians(dd)), dd + dn / 3600) for r, dd in centres]
        try:
            cm, _ = centre(en.combine(frames, moved[0][0], moved[0][1], fov, purpose="comoving", centres=moved))
            controls.append({"offset_arcsec": [de, dn], "snr": None if cm is None else cm["snr"],
                             "single_exposure_fraction": None if cm is None else cm["single_exposure_fraction"]})
        except en.EnhanceError as err:
            controls.append({"offset_arcsec": [de, dn], "error": str(err)})
    saturated = []
    for f, (ra, dec) in zip(frames, centres):
        x, y = (float(v) for v in non_sidereal.world_to_pixel(f.image.wcs, ra, dec))
        yy, xx = np.indices(f.image.shape)
        core = np.hypot(xx - x, yy - y) <= 1.5
        saturated.append(int(((f.image.flags & f.image.flag_defs.names_bitmask(SATURATION)) != 0)[core].sum()))
    sel = stack.selection
    row = {**base, "kind": sel["kind"], "lambda_range_um": [round(v, 4) for v in sel["lambda_range_um"]],
           "span_days": round(sel["span_days"], 3), "n_exposures": stack.n_exposures,
           "target_outlier_pixels_used": sel.get("target_outlier_pixels_used"), "saturated_core_pixels": saturated,
           "displaced_track_snr": [None if k.get("snr") is None else round(k["snr"], 1) for k in controls]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{label}_target.png").write_bytes(view.zoom_png(stack, c, c, title=title, dpi=140))
    if m is None:
        row.update(accepted=False, reasons=[
            "No evaluable: el núcleo del objeto no tiene píxeles válidos en la combinación (saturación con "
            f"desbordamiento en {sum(v > 0 for v in saturated)} de {len(saturated)} exposiciones). Combinar no "
            "recupera la información perdida por saturación."])
    else:
        ctl = [k["snr"] for k in controls if k.get("snr") is not None]
        measured = [v for v in m["snr_single"] if v is not None]
        row.update(target_snr_combined=round(m["snr"], 1),
                   target_snr_single=[None if v is None else round(v, 1) for v in m["snr_single"]],
                   sqrt_n=round(math.sqrt(stack.n_exposures), 2), accepted=False)
        controls_txt = "Controles con la trayectoria desplazada: S/N " + ", ".join(f"{v:.1f}" for v in ctl) + "."
        if len(measured) < max(2, stack.n_exposures // 2):
            row["reasons"] = [
                f"No representativo: solo {len(measured)} de {stack.n_exposures} exposiciones tienen el núcleo del "
                f"objeto sin píxeles saturados ({sum(v > 0 for v in saturated)} con desbordamiento). El objeto ya "
                f"tiene S/N {max(measured):.0f} en una exposición: combinar no aporta nada medible y no recupera la "
                "saturación. " + controls_txt]
        else:
            row["gain_median"] = None if m["gain"] is None else round(m["gain"], 2)
            row["reasons"] = [
                f"S/N {m['snr']:.0f} en la combinación frente a {m['snr_single_median']:.0f} (mediana) por exposición: "
                f"ganancia {m['gain']:.2f}. " + controls_txt + " No se adopta para medir movimiento: el objeto ya se "
                "mide en cada exposición y esta imagen hereda la efeméride; no mejora la medida aceptada."]
    save(label, {"method": en.METHOD, "selection": sel, "identity": d["identity"],
                 "exposures": [e.provenance() for e in stack.exposures], "predictions_deg": centres,
                 "failures": failures, "centre": m, "displaced_track_controls": controls, "noise": stack.noise,
                 "note": "La efeméride fija el centro de esta imagen. No es una medida de posición ni de movimiento; "
                         "el detector no sideral (results/moving/*) no la usa.", "summary": row})
    return row


def epoch_comparison(first="wise0855_d6_nov2025", last="wise0855_d6_apr2026"):
    """Objective C: each epoch combined on its own, then compared. A consistency check against the
    accepted stellar detector; it does not feed or replace that measurement."""
    try:
        a = json.loads((OUT / f"{first}.json").read_text(encoding="utf-8"))["target"]["position_fit"]
        b = json.loads((OUT / f"{last}.json").read_text(encoding="utf-8"))["target"]["position_fit"]
        ref = json.loads((ROOT / "results" / "motion_wise0855_d6.json").read_text(encoding="utf-8"))["displacement"]
    except (OSError, KeyError, TypeError, ValueError):
        return None
    if not a or not b:
        return None
    dx, dy = (float(v) * 3600 for v in gnomonic(b["ra"], b["dec"], a["ra"], a["dec"]))
    err = math.hypot(a["error_arcsec"], b["error_arcsec"])
    return {"epochs": [first, last], "displacement_east_north_arcsec": [dx, dy],
            "displacement_arcsec": math.hypot(dx, dy), "error_arcsec": err,
            "accepted_detector_east_north_arcsec": [ref["dxi"], ref["deta"]],
            "accepted_detector_arcsec": ref["total_arcsec"],
            "accepted_detector_error_arcsec": [ref["err_dxi_calibrated"], ref["err_deta_calibrated"]],
            "difference_arcsec": math.hypot(dx - ref["dxi"], dy - ref["deta"]),
            "note": "Desplazamiento entre las posiciones ajustadas en dos imágenes combinadas independientes (una por "
                    "temporada), frente al desplazamiento aceptado del detector estelar entre las mismas temporadas "
                    "(results/motion_wise0855_d6.json). Comprobación de coherencia; la decisión de movimiento sigue "
                    "siendo la del detector."}


def markdown(rows):
    def f(v, nd=2):
        return "—" if v is None else (f"{v:.{nd}f}".replace(".", ",") if isinstance(v, float) else str(v))
    lines = ["| Caso | Exposiciones | Detector · λ (µm) | Intervalo | Ruido/píxel (MJy/sr) antes → después | "
             "S/N: ganancia mediana (p16–p84) · frente a la mejor · √N | Fuentes ≥ 5σ antes → después (nuevas) | "
             "PSF | Δ centroide | Flujo | Resultado |", "|---|---:|---|---:|---|---|---|---:|---:|---:|---|"]
    for r in rows:
        if "pixel_noise_ratio" not in r:
            lam = " – ".join(f(float(v), 2) for v in r.get("lambda_range_um", [])) or "—"
            obj = (f"objeto: S/N {f(r.get('target_snr_combined'), 1)}; ganancia {f(r.get('gain_median'))} · "
                   f"√N {f(r.get('sqrt_n'))}" if r.get("target_snr_combined") is not None else "—")
            lines.append(f"| {r['title']} | {r.get('n_exposures', '—')} | D{r.get('detector', '?')} · {lam} | "
                         f"{f(r.get('span_days'))} d | — | {obj} | — | — | — | — | "
                         f"{'Aceptado' if r['accepted'] else 'No adoptado'}: {r['reasons'][0]} |")
            continue
        lam = " – ".join(f(float(v), 2) for v in r["lambda_range_um"])
        gain = "—" if r["gain_median"] is None else (
            f"{f(r['gain_median'])} ({f(r['gain_p16_p84'][0])}–{f(r['gain_p16_p84'][1])}) · "
            f"{f(r['gain_vs_best_exposure'])} · {f(r['sqrt_n'])}")
        kind = "mismo canal" if r["kind"] == "monochromatic" else "banda ancha"
        lines.append(
            f"| {r['title']} | {r['n_exposures']} | D{r['detector']} · {lam} ({kind}) | {f(r['span_days'], 1)} d | "
            f"{f(r['pixel_noise_single_mjysr'], 4)} → {f(r['pixel_noise_combined_mjysr'], 4)} "
            f"(×{f(r['pixel_noise_ratio'])}) | {gain} | {f(float(r['detections_single_median']), 0)} → "
            f"{r['detections_combined']} ({r['new_in_combined']}) | {f(r['psf_width_ratio'])} | "
            f"{f(r['centroid_shift_arcsec'])}″ | {f(r['flux_ratio'], 3)} | "
            f"{'**Aceptado**' if r['accepted'] else '**Rechazado**: ' + r['reasons'][0]} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    only = set(sys.argv[1:])
    rows = []
    for case in SIDEREAL:
        if only and case["label"] not in only:
            continue
        try:
            rows.append(run_sidereal(dict(case)))
        except Exception as err:  # noqa: BLE001 - a failed case is reported, never hidden
            rows.append({"label": case["label"], "title": case["title"], "role": case["role"], "accepted": False,
                         "error": f"{type(err).__name__}: {err}", "reasons": [f"{type(err).__name__}: {err}"]})
        print(json.dumps(rows[-1], ensure_ascii=False, default=jsonable), flush=True)
    for label, title, name, detector, first in MOVING:
        if only and label not in only:
            continue
        try:
            rows.append(run_moving(label, title, name, detector, first))
        except Exception as err:  # noqa: BLE001
            rows.append({"label": label, "title": title, "role": "Objeto móvil", "accepted": False,
                         "error": f"{type(err).__name__}: {err}", "reasons": [f"{type(err).__name__}: {err}"]})
        print(json.dumps(rows[-1], ensure_ascii=False, default=jsonable), flush=True)
    if not only:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "enhance_validation_summary.json").write_text(
            json.dumps({"method": en.METHOD, "generated_utc": Time.now().isot[:19], "cases": rows,
                        "wise0855_epoch_comparison": epoch_comparison()}, indent=1,
                       ensure_ascii=False, default=jsonable), encoding="utf-8")
        (OUT / "RESULTS.md").write_text(markdown(rows), encoding="utf-8")
