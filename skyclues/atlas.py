"""Atlas data: the context maps offered by the region selector and where they come from.

The Atlas is not a third explorer and not a measuring instrument: it shows authentic HiPS maps of
other missions to help choose a centre and a field of view. The interface is in ``region_ui``
(one selector for name, coordinates and map); the chosen region lives in ``navigation``.
"""
from __future__ import annotations

from astropy.time import Time

from . import references
from .astrometry import Astrometry

IRSA_HIPS = "https://irsa.ipac.caltech.edu/data/hips"
#: Official HiPS image surveys mirrored by NASA/IPAC IRSA (properties verified 2026-11-14, HTTP 200).
LAYERS = [
    {"id": "2mass", "label": "2MASS J·H·K (color)", "url": f"{IRSA_HIPS}/CDS/2MASS/Color", "format": "jpeg",
     "mission": "2MASS (UMass/IPAC)", "product": "ivo://CDS/P/2MASS/color", "bands": "J 1.23, H 1.66, Ks 2.16 µm",
     "epoch": "observaciones 1997–2001",
     "note": "Infrarrojo cercano, la región espectral más próxima a los detectores D1–D3 de SPHEREx."},
    {"id": "allwise", "label": "AllWISE W4·W2·W1 (color)", "url": f"{IRSA_HIPS}/CDS/AllWISE/RGB-W4-W2-W1",
     "format": "jpeg", "mission": "WISE/NEOWISE (NASA/JPL/IPAC)", "product": "ivo://CDS/P/allWISE/color",
     "bands": "W1 3.4, W2 4.6, W4 22 µm", "epoch": "era WISE 2010–2011",
     "note": "Composición de color de otra misión; no son datos SPHEREx."},
    {"id": "w1", "label": "AllWISE W1 (3.4 µm)", "url": references.WISE_URLS["W1"], "format": "jpeg",
     "mission": "WISE/NEOWISE", "product": "ivo://CDS/P/allWISE/W1", "bands": "W1 3.4 µm",
     "epoch": "era WISE 2010–2011", "note": "Imagen de contexto, sin uso fotométrico."},
    {"id": "w2", "label": "AllWISE W2 (4.6 µm)", "url": references.WISE_URLS["W2"], "format": "jpeg",
     "mission": "WISE/NEOWISE", "product": "ivo://CDS/P/allWISE/W2", "bands": "W2 4.6 µm",
     "epoch": "era WISE 2010–2011", "note": "Imagen de contexto, sin uso fotométrico."},
    {"id": "dss", "label": "DSS2 (color, óptico)", "url": f"{IRSA_HIPS}/CDS/DSS2/color", "format": "jpeg",
     "mission": "Digitized Sky Survey (STScI)", "product": "ivo://CDS/P/DSS2/color", "bands": "óptico (placas B/R)",
     "epoch": "placas fotográficas ≈1950–1990", "note": "Óptico; útil para orientarse, no comparable con SPHEREx."},
]
#: Official SPHEREx global HiPS, inspected but not offered as a map layer (see PROJECT_STATE).
SPHEREX_HIPS = {"did": "ivo://IPAC/P/SPHEREx/DR1/cube", "url": f"{IRSA_HIPS}/SPHEREx/spherex_allsky_cube",
                "release": "2026-11-01", "kind": "cubo HiPS de 102 planos PNG (0.75–5.0 µm), producto combinado"}


def object_position_now(astro: Astrometry) -> tuple[float, float]:
    """Position of a catalogued object today (calculated, not observed)."""
    if astro.has_proper_motion:
        return astro.position_at(Time.now())
    return astro.ra_deg, astro.dec_deg


__all__ = ["LAYERS", "SPHEREX_HIPS", "object_position_now"]
