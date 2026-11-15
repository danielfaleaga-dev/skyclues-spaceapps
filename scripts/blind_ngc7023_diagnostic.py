"""Diagnóstico (sin cambiar el método): por qué B no etiqueta el canal 63 y qué componente fija la dispersión.

Lee las posiciones de results/blind_ngc7023/seleccion.json, vuelve a extraer (caché local) y usa solo
funciones públicas de spectral_features con sus parámetros congelados.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyclues import spectral_cube as sc, spectral_features as sf  # noqa: E402

OUT = ROOT / "results" / "blind_ngc7023"
sel = json.loads((OUT / "seleccion.json").read_text(encoding="utf-8"))
out = {}
for k in "AB":
    spec = sc.extract_spectrum(sel[k]["ra"], sel[k]["dec"])
    s = sf.series_from_spectrum(spec, "flux", k)
    an = sf.analyse(s)
    rows = {}
    for c in (62, 63, 64, 65):
        f = sf.inspect_channel(s, c, an.features, an.scatter)
        rows[c] = {x: getattr(f, x) for x in ("klass", "kind", "trial_lo", "trial_hi", "value", "continuum", "contrast",
                                              "relative", "ratio", "ref", "ref_local", "ref_detector",
                                              "ref_background", "reasons", "limitations")}
    bg = {r["canal"]: {"fondo_mjysr": r["fondo_mjysr"], "fondo_sigma_mjysr": r["fondo_sigma_mjysr"],
                       "n_fondo": r["n_fondo"]} for r in spec.rows if 60 <= r["canal"] <= 66}
    out[k] = {"inspeccion": rows, "fondo": bg, "dispersion_detector": {str(d): v for d, v in an.scatter.items()},
              "n_apertura_px": spec.n_aperture_px}
(OUT / "diagnostico.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
for k in "AB":
    for c, r in out[k]["inspeccion"].items():
        print(k, c, r["klass"], r["kind"], f"[{r['trial_lo']}-{r['trial_hi']}]",
              *(f"{x}={r[x]:.3g}" if isinstance(r[x], float) else f"{x}={r[x]}" for x in
                ("contrast", "relative", "ratio", "ref_local", "ref_detector", "ref_background")))
    print(k, "fondo", {c: round(v["fondo_sigma_mjysr"], 3) for c, v in out[k]["fondo"].items()})
