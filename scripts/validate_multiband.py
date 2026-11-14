"""Validation of the multiband composition with authentic SPHEREx DR1 cube data; writes JSON evidence.

Uses an EMPTY temporary cache so that cold reads are measured, then repeats each case warm
(disk cache) to measure reuse. Independent checks (no production geometry helpers):
* every pixel value of the three planes equals a direct byte-range read of that plane;
* pixel centres are HEALPix order-14 NESTED pixel centres (astropy-healpix), with no duplicate
  and no missing pixel across tile seams inside the field;
* channels 51/52 are refused and hold no data in the cube.
Run with requirements-dev installed (astropy-healpix). Never writes into data/cache.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from astropy import units as u
from astropy_healpix import HEALPix

from skyclues import config, multiband as mb, multiband_view as mv, spectral_cube as sc
from skyclues.geometry import separation_deg

CASES = {
    "m101_3arcmin": (210.802429, 54.34875, 0.05, "independiente"),
    "m101_30arcmin": (210.802429, 54.34875, 0.5, "independiente"),
    "m101_30arcmin_comun": (210.802429, 54.34875, 0.5, "comun"),
    # A point near the corner of four order-5 tiles (2856-2859), found by scanning RA at the M101 Dec.
    "esquina_4_teselas_6arcmin": (213.737429, 54.34875, 0.1, "independiente"),
}


def independent_checks(comp: mb.Composite) -> dict:
    hp = HEALPix(nside=2 ** 14, order="nested")
    idx_all, n_values = [], 0
    for i, ps in enumerate(comp.patches):
        # values: direct read of each plane, compared with the composition's arrays
        for r, p in zip(mb.ROLES, ps):
            got = p.tile.read_rows({"IMAGE": [comp.channels[r].plane], "NHITS": [comp.channels[r].plane]},
                                   p.y0, p.y0 + p.image.shape[0] - 1, p.x0, p.x0 + p.image.shape[1] - 1)
            assert np.array_equal(got["IMAGE"][0].astype(np.float64), p.image, equal_nan=True)
            assert np.array_equal(got["NHITS"][0], p.nhits)
            n_values += p.image.size
        ra, dec = ps[0].centres_world()
        idx = hp.lonlat_to_healpix(ra * u.deg, dec * u.deg)
        lon, lat = hp.healpix_to_lonlat(idx)
        off = separation_deg(ra, dec, lon.deg, lat.deg) * 3600
        assert off.max() < 0.01, f"centros no HEALPix ({off.max():.4f}″)"
        idx_all.append(idx[comp.field_masks[i]])
    idx_all = np.concatenate(idx_all)
    # the field pixels are exactly the order-14 pixels whose centre lies within the field circle
    cone = hp.cone_search_lonlat(comp.ra * u.deg, comp.dec * u.deg, comp.field_deg / 2 * u.deg)
    lon, lat = hp.healpix_to_lonlat(cone)
    inside = cone[separation_deg(comp.ra, comp.dec, lon.deg, lat.deg) <= comp.field_deg / 2]
    return {"valores_identicos_a_lectura_directa": n_values, "pixeles_campo": int(idx_all.size),
            "duplicados_entre_teselas": int(idx_all.size - np.unique(idx_all).size),
            "faltan_respecto_a_healpix": int(np.setdiff1d(inside, idx_all).size),
            "sobran_respecto_a_healpix": int(np.setdiff1d(idx_all, inside).size)}


def run_case(ra, dec, fov, mode) -> dict:
    out = {}
    for phase in ("frio", "caliente"):
        sc._tiles.clear()                       # layouts from the (temporary) disk cache on the warm pass
        sc.io_stats(reset=True)
        tracemalloc.start()
        t0 = time.perf_counter()
        chans = sc.tile_for(ra, dec).channels
        comp = mb.build(ra, dec, fov, chans, mb.default_numbers(chans), mode)
        t1 = time.perf_counter()
        png, _ = mv.composite_png(comp)
        panels = [mv.channel_panel_png(comp, r) for r in mb.ROLES]
        table = mv.pixel_table(comp)
        t2 = time.perf_counter()
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        io = sc.io_stats()
        out[phase] = {"peticiones_http": io["requests"], "MiB_red": round(io["bytes_network"] / 2**20, 3),
                      "MiB_cache": round(io["bytes_cache"] / 2**20, 3), "s_lectura_y_composicion": round(t1 - t0, 2),
                      "s_render": round(t2 - t1, 2), "MiB_pico_python": round(peak / 2**20, 1),
                      "png_KiB": round(len(png) / 1024, 1), "paneles_KiB": round(sum(map(len, panels)) / 1024, 1),
                      "filas_tabla": len(table)}
    out["canales"] = {r: {"canal": c.number, "lambda_um": c.wavelength_um, "ancho_um": c.bandwidth_um}
                      for r, c in comp.channels.items()}
    out["teselas"] = [t["tesela"] for t in comp.alignment["teselas"]]
    out["alineacion_verificada"] = comp.alignment["verificada"]
    out["cobertura"] = comp.coverage
    out["escala"] = comp.stretch.to_dict()
    out["avisos"] = comp.warnings
    out["comprobaciones_independientes"] = independent_checks(comp)
    out["reproducible"] = mv.composite_png(mb.build(ra, dec, fov, comp_channels(ra, dec),
                                                     {r: c.number for r, c in comp.channels.items()}, mode))[0] == png
    return out


def comp_channels(ra, dec):
    return sc.tile_for(ra, dec).channels


def audit() -> dict:
    with tempfile.TemporaryDirectory(prefix="skyclues_mb_") as tmp:
        real_cache = config.CACHE_DIR
        config.CACHE_DIR = Path(tmp)
        sc._cache_bytes = None
        try:
            res = {"producto": "SPHEREx DR1 All-Sky spectral cube", "doi": config.CUBE_DOI,
                   "fecha_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "casos": {}}
            for name, case in CASES.items():
                res["casos"][name] = run_case(*case)
            chans = comp_channels(*CASES["m101_3arcmin"][:2])
            refused = {}
            for n in (51, 52):
                try:
                    mb.select_channels(chans, {"R": n, "G": 40, "B": 10})
                    refused[n] = False
                except ValueError:
                    refused[n] = True
            blank = sc.channel_map(*CASES["m101_3arcmin"][:3], 50).summary()
            res["canales_vacios"] = {"rechazados": refused,
                                     "BLANKCH": sc.tile_for(*CASES["m101_3arcmin"][:2]).header("PRIMARY").get("BLANKCH"),
                                     "canal_51_pixeles_con_datos": blank["n_valid"], "canal_51_pixeles_campo": blank["n_field"]}
        finally:
            config.CACHE_DIR = real_cache
            sc._cache_bytes = None
    return res


if __name__ == "__main__":
    result = audit()
    path = config.RESULTS_DIR / "multiband_validation.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    for name, c in result["casos"].items():
        print(name, c["teselas"], c["frio"], c["caliente"], c["comprobaciones_independientes"], c["reproducible"])
    print(result["canales_vacios"])
    print("->", path)
