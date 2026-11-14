"""Aladin Lite v3 reference field. HTML controls act only inside this iframe."""
from __future__ import annotations

import json
from pathlib import Path

from . import references as ref
from .spectral_cube import healpix_nest
from .targets import validate_coordinates, validate_fov_deg


def viewer_html(ra: float, dec: float, fov: float, result: dict | None,
                epoch: float = 2026.0, error: str | None = None) -> str:
    ra, dec = validate_coordinates(ra, dec)
    fov = validate_fov_deg(fov)
    sources = []
    for source in (result or {}).get("sources", []):
        sources.append({**source, "expected": ref.expected_position(source, epoch)})
    ipix = int(healpix_nest(8, ra, dec))
    payload = {"ra": ra, "dec": dec, "fov": fov, "epoch": epoch, "sources": sources,
               "gaiaLoaded": result is not None, "gaiaError": error, "wise": ref.WISE_URLS,
               "tile": f"/Norder8/Dir{ipix // 10000 * 10000}/Npix{ipix}.jpg", "aladin": ref.ALADIN_JS}
    # Never permit catalogue/network text to close a script element.
    encoded = json.dumps(payload, allow_nan=False, ensure_ascii=True).replace("<", "\\u003c")
    return Path(__file__).with_name("reference_view.html").read_text(encoding="utf-8").replace("__PAYLOAD__", encoded)
