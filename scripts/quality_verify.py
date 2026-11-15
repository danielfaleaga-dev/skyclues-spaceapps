"""Verificación del diagnóstico de calidad espectral con datos reales (NGC 7027, M82, Elias 29, M101).

1. Las causas coinciden con el FITS: se comparan los contadores de la extracción con una lectura independiente de
   los píxeles brutos (scripts/v02_diagnosis.py, que no usa el código de extracción).
2. Las mediciones no cambian: se vuelve a extraer con el código ANTERIOR (spectral_cube.py de HEAD) y con el nuevo,
   y todas las claves antiguas de cada fila deben ser idénticas; también se comparan con los resultados
   congelados de V02, V03 y NGC 7023.
3. El analizador (spectral_features.py) y geometry.py conservan las huellas de V02.
Escribe results/quality_diagnostics/verificacion.json.
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyclues import spectral_cube as new, spectral_quality as sq  # noqa: E402

OUT = ROOT / "results" / "quality_diagnostics"
TARGETS = {"NGC 7027": (316.75655, 42.236242), "M82": (148.968458, 69.679703), "Elias 29": (246.789292, -24.621806),
           "M101": (210.802429, 54.34875)}
FROZEN = {"NGC 7027": "results/blind_v02/T01/resultados.json", "M82": "results/blind_v02/T02/resultados.json",
          "Elias 29": "results/blind_v02/T03/resultados.json"}
ok_all = True


def check(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(("OK   " if cond else "FALLA"), name, detail, flush=True)


def load_old_cube():
    """spectral_cube.py as committed in HEAD (before this change), imported as skyclues.spectral_cube_old."""
    src = subprocess.run(["git", "show", "HEAD:skyclues/spectral_cube.py"], cwd=ROOT, capture_output=True, check=True).stdout
    mod = types.ModuleType("skyclues.spectral_cube_old")
    mod.__package__ = "skyclues"
    sys.modules[mod.__name__] = mod
    exec(compile(src.decode("utf-8"), "spectral_cube_old.py", "exec"), mod.__dict__)
    return mod


def load_diagnosis():
    spec = importlib.util.spec_from_file_location("v02_diagnosis", ROOT / "scripts" / "v02_diagnosis.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


old = load_old_cube()
diag = load_diagnosis()
result = {}
for name, (ra, dec) in TARGETS.items():
    n_spec, o_spec = new.extract_spectrum(ra, dec), old.extract_spectrum(ra, dec)
    # 2a. every key of the old rows is identical in the new rows
    same = all(all(k in nr and nr[k] == v for k, v in orow.items()) for orow, nr in zip(o_spec.rows, n_spec.rows))
    check(f"{name}: filas antiguas idénticas (código HEAD vs nuevo)", same and len(o_spec.rows) == len(n_spec.rows))
    extra = sorted(set(n_spec.rows[0]) - set(o_spec.rows[0]))
    check(f"{name}: solo claves nuevas de diagnóstico", all(k.startswith("ap_") for k in extra), str(extra))
    check(f"{name}: n_aperture_px y n_annulus_px idénticos", n_spec.n_aperture_px == o_spec.n_aperture_px and
          n_spec.n_annulus_px == o_spec.n_annulus_px)
    # 1. counters against an independent read of the raw pixels
    raw = diag.diagnose(ra, dec)
    bad = []
    for r, g in zip(n_spec.rows, raw):
        flags = g["banderas_apertura"]
        mine = (r["ap_pix_total"], r["ap_pix_invalidos"], r["ap_pix_nan"], r["ap_pix_nhits0"], r["ap_bloom"],
                r["ap_overflow"])
        truth = (g["n_pix_apertura"], g["apertura_malos"], g["apertura_nan"], g["apertura_nhits0"],
                 flags.get("BLOOM", 0), flags.get("OVERFLOW", 0))
        if mine != truth or abs(r["ap_peso_invalido"] - g["peso_total_malos"]) > 0.002 * max(1, g["apertura_malos"]):
            bad.append((r["canal"], mine, truth))
    check(f"{name}: contadores = lectura independiente del FITS (102 canales)", not bad, str(bad[:3]))
    qs = sq.spectrum_quality(n_spec)
    rejected = [q.canal for q in qs if q.rejected_incomplete_aperture]
    summary = sq.summary(qs)
    check(f"{name}: rechazado por apertura incompleta ⇔ estado «apertura sin datos»",
          rejected == [r["canal"] for r in n_spec.rows if r["status"] == "no_data_aperture"])
    # 2b. frozen results of V02: the same channels, the same fluxes
    if name in FROZEN:
        fz = json.loads((ROOT / FROZEN[name]).read_text(encoding="utf-8"))
        eq = all(all(nr.get(k) == v for k, v in fr.items()) for fr, nr in zip(fz["espectro"], n_spec.rows))
        check(f"{name}: filas idénticas a las congeladas de V02", eq)
        check(f"{name}: canales rechazados = canales sin valor congelados (menos los vacíos 51/52)",
              rejected == [c for c in fz["canales_sin_valor"] if c not in (51, 52)])
    with_bloom_all = sum(1 for q in qs if q.rejected_incomplete_aperture and q.bloom)
    result[name] = {**summary, "rechazados_con_bloom": with_bloom_all, "canales_rechazados": rejected,
                    "px_aperture": qs[0].px_total,
                    "perdida_de_peso_pct_por_canal_rechazado": {q.canal: round(q.weight_lost_pct, 1) for q in qs
                                                                if q.rejected_incomplete_aperture}}
    print("   ", name, {k: v for k, v in summary.items()}, "| rechazados con BLOOM:", with_bloom_all, flush=True)

# 2c. frozen V03 and NGC 7023 results
for rel, getter in (("results/blind_v03/C05/resultados.json", None), ("results/blind_v03/C12/resultados.json", None),
                    ("results/blind_v03/C14/resultados.json", None)):
    fz = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    s = new.extract_spectrum(fz["ra_deg"], fz["dec_deg"])
    check(f"{rel}: filas idénticas a las congeladas", all(all(nr.get(k) == v for k, v in fr.items())
                                                           for fr, nr in zip(fz["espectro"], s.rows)))
fz = json.loads((ROOT / "results/blind_ngc7023/resultados.json").read_text(encoding="utf-8"))
for k in "AB":
    s = new.extract_spectrum(fz["seleccion"][k]["ra"], fz["seleccion"][k]["dec"])
    check(f"NGC 7023 {k}: filas idénticas a las congeladas", all(all(nr.get(kk) == v for kk, v in fr.items())
                                                                  for fr, nr in zip(fz["espectros"][k], s.rows)))

# 3. analyzer and geometry untouched
v02 = json.loads((ROOT / "results/blind_v02/huellas_metodo.json").read_text(encoding="utf-8"))
for f in ("skyclues/spectral_features.py", "skyclues/geometry.py"):
    check(f"intacto desde V02: {f}", hashlib.sha256((ROOT / f).read_bytes()).hexdigest() == v02[f])
changed = hashlib.sha256((ROOT / "skyclues/spectral_cube.py").read_bytes()).hexdigest() != v02["skyclues/spectral_cube.py"]
print("INFO spectral_cube.py difiere de la huella de V02 (cambio aditivo esperado):", changed)

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "verificacion.json").write_text(json.dumps({"todo_correcto": ok_all, "objetivos": result}, indent=1,
                                                  ensure_ascii=False), encoding="utf-8")
print("\nTODO CORRECTO" if ok_all else "\nHAY FALLOS")
sys.exit(0 if ok_all else 1)
