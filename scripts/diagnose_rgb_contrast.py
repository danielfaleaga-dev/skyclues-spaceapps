"""Diagnóstico de «Mismo contraste» (RGB) con datos reales del cubo DR1; escribe evidencia JSON.

Para cada región y canales (por defecto 88/47/21) mide, en los dos modos de contraste: rangos
reales en MJy/sr de cada canal, límites de la escala, fracción de píxeles recortados a negro y
saturados por color, fracción casi negra y blanca, y si se avisa de poco contraste. Comprueba
además que el marco del gráfico no depende de la anchura del navegador. Solo lee; no modifica datos.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np

import altair as alt

from skyclues import multiband as mb, multiband_view as mv, spectral_cube as sc

alt.data_transformers.disable_max_rows()      # Streamlit does not apply this limit either

CASES = {
    "M101_3arcmin": (210.802429, 54.34875, 0.05),
    "M101_6arcmin": (210.802429, 54.34875, 0.1),
    "M101_30arcmin": (210.802429, 54.34875, 0.5),
    "plano_galactico_30arcmin": (275.714, -13.192, 0.5),
    "centro_galactico_6arcmin": (266.758, -26.102, 0.1),
    "Orion_6arcmin": (83.82, -5.39, 0.1),
    "M31_30arcmin": (10.6847, 41.2690, 0.5),
    "alta_latitud_1grado": (185.36, -3.88, 1.0),
}
COMBOS = {"88/47/21": {"R": 88, "G": 47, "B": 21}, "70/40/10": {"R": 70, "G": 40, "B": 10},
          "100/60/30": {"R": 100, "G": 60, "B": 30}}


def measure(comp: mb.Composite) -> dict:
    samples = {r: np.concatenate([p.image[comp.common_valid(i) & comp.field_masks[i]]
                                  for i, p in enumerate(comp.maps[r].patches)]) for r in mb.ROLES}
    ranges = {r: {"min": float(v.min()), "p1": float(np.percentile(v, 1)), "mediana": float(np.median(v)),
                  "p99_5": float(np.percentile(v, 99.5)), "max": float(v.max())} for r, v in samples.items()}
    return {"canales_MJy_sr": ranges, "vmin": comp.stretch.vmin, "vmax": comp.stretch.vmax,
            "visualizacion": comp.display_stats(),
            "aviso_poco_contraste": any("poco contraste útil" in w for w in comp.warnings)}


def chart_frame_ok(comp: mb.Composite) -> bool:
    png, info = mv.composite_png(comp)
    text = json.dumps(mv.composite_chart(png, info, mv.pixel_table(comp), comp).to_dict())
    return "height/width" not in text and '"container"' not in text


def main() -> None:
    out = {"fecha_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "casos": {}}
    for name, (ra, dec, fov) in CASES.items():
        chans = sc.tile_for(ra, dec).channels
        for cname, nums in COMBOS.items():
            if cname != "88/47/21" and not name.startswith(("M101_6", "plano", "Orion")):
                continue
            key = f"{name} · {cname}"
            try:
                res = {m: measure(mb.build(ra, dec, fov, chans, nums, m)) for m in mb.STRETCH_MODES}
                res["marco_independiente_de_la_anchura"] = chart_frame_ok(mb.build(ra, dec, fov, chans, nums, "comun"))
            except Exception as err:  # noqa: BLE001 - recorded as evidence
                res = {"error": f"{type(err).__name__}: {err}"}
            out["casos"][key] = res
            c = res.get("comun", {}).get("visualizacion", {})
            print(f"{key:45s} comun: oscura {c.get('fraccion_oscura', float('nan')):.0%} blanca "
                  f"{c.get('fraccion_blanca', float('nan')):.1%} aviso {res.get('comun', {}).get('aviso_poco_contraste')}"
                  f" | independiente: oscura {res.get('independiente', {}).get('visualizacion', {}).get('fraccion_oscura', float('nan')):.0%}")
    dest = Path(__file__).resolve().parents[1] / "results" / "rgb_contrast" / "diagnostico_mismo_contraste.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print("escrito", dest)


if __name__ == "__main__":
    main()
