"""Scientific coherence of the integrated version, on REAL data (local cache; the network is used only
if a cutout or a cube range is missing).

Run:  python scripts/integration_verify.py        ->  results/integration_v1/verificacion_cientifica.json

What it checks (nothing here changes a method; it only reads and compares):

1. Independence: the motion and sequence code never imports the S/N enhancement, and the spectral
   code and the Time code do not import each other.
2. Motion is not altered by the combined images: the measured motion of 3I/ATLAS (D1, 9-8-2025) is
   computed, the same exposures are combined (co-moving stack), and the motion is computed again.
   Pixels, variances and flags of every exposure are hashed before and after.
3. The same for a stationary field (M101): the saved sequence is combined and its frames, metrics
   and the «no motion» result stay identical.
4. Spectrum: 102 channels always; channels without data keep their own status (51/52 blank in DR1
   versus an aperture without data) and are never filled; the interpreter gives verdicts, never
   probabilities, and never the word «identificado».
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from skyclues import enhance as en, moving_sources as ms, non_sidereal as ns, sequence  # noqa: E402
from skyclues import spectral_cube as sc, spectral_features as sf, spectral_interpreter as si  # noqa: E402
from skyclues import spectral_quality as sq, spectral_references as sr  # noqa: E402
import validate_motion as vm  # noqa: E402

OUT = ROOT / "results" / "integration_v1"
CHECKS: list[dict] = []


def check(name: str, ok: bool, detail) -> None:
    CHECKS.append({"comprobacion": name, "ok": bool(ok), "detalle": detail})
    print(("OK   " if ok else "FALLO") + " " + name, flush=True)


def imports_of(module: str) -> set[str]:
    tree = ast.parse((ROOT / "skyclues" / f"{module}.py").read_text(encoding="utf-8"))
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            out.update(a.name for a in node.names)
            if node.module:
                out.add(node.module.split(".")[-1])
        elif isinstance(node, ast.Import):
            out.update(a.name.split(".")[-1] for a in node.names)
    return out


def digest(frames) -> str:
    h = hashlib.sha256()
    for f in frames:
        img = f.image
        for a in (img.image, img.variance, img.flags, img.zodi, img.wavelength_um):
            h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def independence() -> None:
    enhance_mods = {"enhance", "enhance_page", "enhance_view"}
    motion_side = ["motion", "motion_page", "non_sidereal", "moving_sources", "moving_page", "moving_view",
                   "sequence", "player"]
    bad = {m: sorted(imports_of(m) & enhance_mods) for m in motion_side if imports_of(m) & enhance_mods}
    check("El código de movimiento y de secuencias no importa la mejora S/N", not bad, bad or motion_side)
    spectral = sorted(p.stem for p in (ROOT / "skyclues").glob("spectr*.py"))
    time_side = enhance_mods | {"motion", "motion_page", "non_sidereal", "moving_sources", "moving_page", "time_page"}
    bad = {m: sorted(imports_of(m) & time_side) for m in spectral if imports_of(m) & time_side}
    check("El código de Espectro no importa el de Tiempo, Movimiento ni S/N", not bad, bad or spectral)
    spectral_set = set(spectral)
    bad = {m: sorted(imports_of(m) & spectral_set) for m in sorted(enhance_mods) if imports_of(m) & spectral_set}
    check("La mejora S/N no importa el código de Espectro", not bad, bad or sorted(enhance_mods))


def moving_object() -> None:
    d = vm.discovery("atlas_aug")
    rows = vm.pick(ms.motion_groups(d["rows"]), 1, "0343_1")
    frames, failures = ns.fetch_frames(d["identity"], rows, vm.FOV, lambda msg: None)
    before = digest(frames)
    first = vm.summary(ns.assess(frames, vm.FOV))
    centres = [(f.prediction["ra"], f.prediction["dec"]) for f in frames]
    stack_info = {}
    try:
        stack = en.combine(frames, centres[0][0], centres[0][1], vm.FOV, purpose="comoving", centres=centres)
        metrics = en.evaluate(stack)
        stack_info = {"exposiciones": stack.n_exposures, "aceptada": bool(en.verdict(metrics)["accepted"]),
                      "ganancia_mediana": metrics["gain"].get("median")}
    except en.EnhanceError as err:
        stack_info = {"no_combinable": str(err)}
    try:
        en.evaluate(en.combine(frames, centres[0][0], centres[0][1], vm.FOV))
        stack_info["apilado_fijo"] = "combinado"
    except en.EnhanceError as err:
        stack_info["apilado_fijo"] = f"rechazado: {err}"
    after = digest(frames)
    second = vm.summary(ns.assess(frames, vm.FOV))
    check("3I/ATLAS D1: las exposiciones no cambian al combinarlas (SHA-256 de píxeles, varianza y banderas)",
          before == after, {"antes": before, "despues": after, "fallos_descarga": failures, "combinacion": stack_info})
    check("3I/ATLAS D1: el movimiento medido es idéntico antes y después de la combinación S/N",
          json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True), {"antes": first, "despues": second})
    frozen = json.loads((vm.ROOT / "atlas_aug_motion_d1.json").read_text(encoding="utf-8"))["motion"]
    same = (first["observed_motion"] and abs(first["displacement_arcsec"] - frozen["displacement_arcsec"]) < 0.05
            and abs(first["error_arcsec"] - frozen["error_arcsec"]) < 0.05)
    check("3I/ATLAS D1: reproduce el resultado guardado del detector no sideral", same,
          {"ahora": [first.get("displacement_arcsec"), first.get("error_arcsec")],
           "guardado": [round(frozen["displacement_arcsec"], 3), round(frozen["error_arcsec"], 3)]})


def stationary_field() -> None:
    seq = sequence.load_sequence(ROOT / "results" / "sequence_m101.json")
    before, metrics_before = digest(seq.frames), json.dumps(seq.metrics, sort_keys=True, default=str)

    def no_motion():
        from skyclues import archive
        frames = []
        for f in seq.frames:
            row = {"obs_id": f.obs_id, "detector": f.detector, "collection": f.record["collection"],
                   "version": archive._FILE_RE.search(f.cutout_url)["ver"], "mjd": f.mjd,
                   "lambda_um": f.lambda_target_um, "bandwidth_um": f.bandwidth_target_um,
                   "prediction": {"ra": seq.ra, "dec": seq.dec, "refined": True, "source": "CONTROL ESTACIONARIO M101"}}
            frames.append(ns.MovingFrame(row, f.image, f.path, f.cutout_url, f.sha256))
        return vm.summary(ns.assess(frames, seq.field_deg))

    first = no_motion()
    stack = en.combine(seq.frames, seq.ra, seq.dec, seq.field_deg,
                       target_motion_arcsec=seq.metrics.get("target_motion_in_sequence_arcsec"))
    m = en.evaluate(stack)
    second = no_motion()
    check("M101: la secuencia guardada no cambia al combinarla (píxeles, varianza, banderas y métricas)",
          before == digest(seq.frames) and metrics_before == json.dumps(seq.metrics, sort_keys=True, default=str),
          {"exposiciones": stack.n_exposures, "aceptada": bool(en.verdict(m)["accepted"]),
           "ganancia_mediana": m["gain"].get("median")})
    check("M101: «sin movimiento» antes y después de la combinación S/N",
          not first["observed_motion"] and json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True),
          {"antes": first, "despues": second})
    ref = stack.reference
    untouched = np.array_equal(np.nan_to_num(stack.data[ref] + stack.offsets[ref], nan=-1e30)[np.isfinite(stack.data[ref])],
                               (stack.exposures[ref].image.image - stack.exposures[ref].image.zodi)[np.isfinite(stack.data[ref])])
    check("M101: en la rejilla nativa, la imagen de referencia de la combinación son sus píxeles originales",
          bool(untouched), {"referencia": stack.exposures[ref].obs_id})


def keys_of(obj, found=None) -> set[str]:
    found = set() if found is None else found
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(str(k))
            keys_of(v, found)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            keys_of(v, found)
    return found


def spectrum(label: str, ra: float, dec: float) -> None:
    spec = sc.extract_spectrum(ra, dec)
    rows = spec.rows
    status = {}
    for r in rows:
        status[r["status"]] = status.get(r["status"], 0) + 1
    blank = sorted(int(r["canal"]) for r in rows if r["status"] == "blank")
    valued = [r for r in rows if r["status"] == "ok"]
    def has_value(r) -> bool:
        return r["flujo_mjy"] is not None and bool(np.isfinite(r["flujo_mjy"]))

    missing_with_value = [int(r["canal"]) for r in rows if r["status"] != "ok" and has_value(r)]
    check(f"{label}: 102 canales; los canales sin dato conservan su causa y ningún valor",
          len(rows) == 102 and blank == [51, 52] and not missing_with_value and all(has_value(r) for r in valued),
          {"canales": len(rows), "estados": status, "blank_DR1": blank, "sin_dato_con_valor": missing_with_value})
    s = sf.series_from_spectrum(spec, "flux", "A")
    an = sf.analyse(s)
    its = si.interpret_features(s, an.features, redshift=sr.redshift_at(spec.ra, spec.dec),
                                resolution=si.resolution_of(spec), qualities=sq.spectrum_quality(spec),
                                aperture_arcsec=spec.aperture.r_ap * spec.pixel_scale_arcsec)
    dumped = [it.to_dict() for it in its]
    text = json.dumps(dumped, ensure_ascii=False).lower()
    keys = keys_of(dumped)
    numeric_prob = sorted(k for k in keys if "prob" in k.lower() or "confianza" in k.lower() or "score" in k.lower())
    check(f"{label}: el intérprete da veredictos, no probabilidades ni identificaciones",
          not numeric_prob and "identificad" not in text and "hemos encontrado" not in text
          and all(it.verdict in si.VERDICT_LABELS for it in its)
          and all("no identifica una sustancia" in it.limitations[0] for it in its),
          {"veredictos": [[round(float(it.feature.lam), 3), it.label] for it in its], "claves_prohibidas": numeric_prob})
    survey = si.survey(s, an.features, an.scatter, redshift=sr.redshift_at(spec.ra, spec.dec))
    no_data = [c.reference.id for c in survey if c.status == si.COV_NO_DATA]
    check(f"{label}: una referencia sobre canales sin dato no concluye presencia ni ausencia",
          all("ni presencia ni ausencia" in c.reasons[0] for c in survey if c.status == si.COV_NO_DATA),
          {"referencias_sin_cobertura": no_data})


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    independence()
    moving_object()
    stationary_field()
    spectrum("NGC 5461 (M101)", 210.923546, 54.319916)
    spectrum("NGC 7027", 316.75655, 42.2362417)
    payload = {"metodos": {"snr": en.METHOD, "no_sideral": getattr(ns, "METHOD", None),
                           "analizador": sf.METHOD_VERSION, "interprete": si.ENGINE_VERSION,
                           "biblioteca": sr.LIBRARY_VERSION},
               "superadas": sum(c["ok"] for c in CHECKS), "total": len(CHECKS), "comprobaciones": CHECKS}
    (OUT / "verificacion_cientifica.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False, default=str),
                                                      encoding="utf-8")
    print(f"{payload['superadas']} de {payload['total']} comprobaciones superadas")
    sys.exit(0 if payload["superadas"] == payload["total"] else 1)
