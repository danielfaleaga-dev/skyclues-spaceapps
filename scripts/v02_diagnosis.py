"""Diagnóstico de los canales sin valor en V02 (NGC 7027, M82, Elias 29). Solo lectura.

Para cada canal lee los píxeles brutos del cubo DR1 (IMAGE, NHITS, FLAGS) en la apertura y el anillo,
con la misma geometría que extract_spectrum, y separa:
  - producto: píxeles NaN o con NHITS = 0 en el FITS;
  - extracción: regla que invalida el canal entero si UN píxel de la apertura (peso > 0) no tiene dato.
No modifica ni importa nada del analizador. Resultado: results/v02_diagnosis/diagnostico.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyclues import config, spectral_cube as sc  # noqa: E402
from skyclues.geometry import separation_deg  # noqa: E402

OUT = ROOT / "results" / "v02_diagnosis"
TARGETS = {"NGC 7027 (T01)": (316.75655, 42.236242), "M82 (T02)": (148.968458, 69.679703),
           "Elias 29 (T03)": (246.789292, -24.621806)}
R_AP, R_IN, R_OUT = config.CUBE_APERTURE_DEFAULT_PX


def diagnose(ra, dec):
    home = sc.tile_for(ra, dec)
    pix = home.pixel_scale_arcsec
    boxes = sc.tile_boxes(ra, dec, (R_OUT + 1) * pix / 3600)
    nz = home.shape[0]
    planes = list(range(nz))
    names = sc.flag_bits(home)
    per = [dict(n_ap=0, ap_nan=0, ap_nh0=0, ap_bad=0, ap_bad_w=[], ap_core_bad=0, ann_n=0, ann_nan=0, ann_nh0=0,
                flags={}) for _ in planes]
    for b in boxes:
        t = b.tile
        ny, nx = b.y1 - b.y0 + 1, b.x1 - b.x0 + 1
        yy, xx = np.mgrid[0:ny, 0:nx]
        rc, dc = t.wcs.pixel_to_world_values(xx + b.x0, yy + b.y0)
        dist = separation_deg(ra, dec, rc, dc) * 3600 / pix
        w = sc._aperture_weights(t, b.x0, b.y0, (ny, nx), ra, dec, R_AP, pix, 5)
        ann = (dist >= R_IN) & (dist < R_OUT)
        in_ap = w > 0
        got = t.read_rows({"IMAGE": planes, "NHITS": planes, "FLAGS": planes}, b.y0, b.y1, b.x0, b.x1)
        img, nh, fl = got["IMAGE"].astype(float), got["NHITS"], got["FLAGS"].astype(np.int64)
        for p in planes:
            d = per[p]
            im, n, f = img[p], nh[p], fl[p]
            bad_ap = in_ap & (~np.isfinite(im) | (n <= 0))
            d["n_ap"] += int(in_ap.sum())
            d["ap_nan"] += int((in_ap & ~np.isfinite(im)).sum())
            d["ap_nh0"] += int((in_ap & (n <= 0)).sum())
            d["ap_bad"] += int(bad_ap.sum())
            d["ap_bad_w"] += [round(float(x), 3) for x in w[bad_ap]]
            d["ap_core_bad"] += int((bad_ap & (w >= 0.999)).sum())
            d["ann_n"] += int(ann.sum())
            d["ann_nan"] += int((ann & ~np.isfinite(im)).sum())
            d["ann_nh0"] += int((ann & (n <= 0)).sum())
            for bit, nm in names.items():
                c = int((in_ap & ((f >> bit) & 1).astype(bool)).sum())
                if c:
                    d["flags"][nm] = d["flags"].get(nm, 0) + c
    rows = []
    for c in home.channels:
        d = per[c.plane]
        w_bad = d["ap_bad_w"]
        edge_only = d["ap_bad"] > 0 and d["ap_core_bad"] == 0
        # what the extraction does: invalid if any aperture pixel (weight > 0) lacks data
        extraction_invalid = d["ap_bad"] > 0
        # share of the aperture weight carried by the bad pixels (never used for the flux; for diagnosis only)
        rows.append({"canal": c.number, "lambda_um": c.wavelength_um, "detector": c.detector, "blank": c.blank,
                     "n_pix_apertura": d["n_ap"], "apertura_nan": d["ap_nan"], "apertura_nhits0": d["ap_nh0"],
                     "apertura_malos": d["ap_bad"], "malos_en_nucleo(w=1)": d["ap_core_bad"],
                     "peso_max_pixel_malo": max(w_bad) if w_bad else 0.0,
                     "peso_total_malos": round(float(sum(w_bad)), 3),
                     "solo_borde": edge_only, "extraccion_invalida": extraction_invalid,
                     "anillo_n": d["ann_n"], "anillo_nan": d["ann_nan"], "anillo_nhits0": d["ann_nh0"],
                     "banderas_apertura": d["flags"]})
    return rows


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {}
    for name, (ra, dec) in TARGETS.items():
        rows = diagnose(ra, dec)
        res[name] = rows
        inv = [r for r in rows if r["extraccion_invalida"] and not r["blank"]]
        core = [r for r in inv if r["malos_en_nucleo(w=1)"] > 0]
        edge = [r for r in inv if r["solo_borde"]]
        print(name, "| invalidados por la extracción:", len(inv), "| con píxeles malos en el núcleo (w=1):", len(core),
              "| solo en el borde:", len(edge))
        if edge:
            print("   solo borde:", [(r["canal"], r["apertura_malos"], r["peso_max_pixel_malo"]) for r in edge][:20])
        ann_bad = [r["canal"] for r in rows if r["anillo_n"] and (r["anillo_nan"] + r["anillo_nhits0"]) / r["anillo_n"] > 0.5]
        print("   anillo > 50 % sin dato en canales:", ann_bad)
    (OUT / "diagnostico.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
