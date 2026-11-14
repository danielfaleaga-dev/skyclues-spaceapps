"""One active sky region for the whole application.

The region (centre RA/Dec, field-of-view DIAMETER in degrees, optional object identity) lives in
``session_state["region"]``. The name search, the coordinate fields and the Atlas all write it, and
Time Explorer and Spectrum Explorer both read it: there is no second copy to keep in step.

The URL parameters ``ra``/``dec``/``fov`` mirror the region so that a link restores it. They are
read only when a session starts; afterwards the session state is the single source of truth.

Nothing here touches the scientific engines: explorers receive the same (ra, dec, fov, astrometry)
they always received.
"""
from __future__ import annotations

import math
from urllib.parse import urlencode

from .targets import validate_coordinates, validate_fov_deg

DEFAULT_REGION = {"ra": 210.802429, "dec": 54.34875, "fov": 0.1}     # M101, the static control field
#: The object identity (name, catalogue astrometry) is kept while the centre stays this close to it.
ANCHOR_TOLERANCE_ARCSEC = 1.0
VIEWS = ("region", "time", "spectrum")
EXPLORER_PARAM = {"time": "temporal", "spectrum": "espectral"}
VIEW_OF_PARAM = {v: k for k, v in EXPLORER_PARAM.items()}


# ----------------------------------------------------------------------------- shareable links
def parse_region(params):
    ra, dec = validate_coordinates(params.get('ra'), params.get('dec'))
    fov = validate_fov_deg(params.get('fov', .1))
    explorer = params.get('explorer', 'temporal')
    if explorer not in ('temporal', 'espectral'):
        raise ValueError('Explorador desconocido')
    ch = params.get('canal', '63')
    if not str(ch).isdigit() or not 1 <= int(ch) <= 102:
        raise ValueError('Canal fuera de 1-102')
    return {'ra': ra, 'dec': dec, 'fov': fov, 'explorer': explorer, 'canal': int(ch)}


def region_query(ra, dec, fov, explorer='temporal', canal=63):
    d = parse_region(dict(ra=ra, dec=dec, fov=fov, explorer=explorer, canal=canal))
    p = {k: format(d[k], '.10g') for k in ('ra', 'dec', 'fov')}
    p['explorer'] = explorer
    if explorer == 'espectral':
        p['canal'] = str(d['canal'])
    return '?' + urlencode(p)


# ----------------------------------------------------------------------------- geometry helpers
def normalise_ra(ra: float) -> float:
    """RA folded into [0, 360) and rounded to 1e-7 deg, so 359.99999999 never prints as 360."""
    r = round(float(ra) % 360.0, 7)
    return 0.0 if r >= 360.0 else r


def separation_arcsec(ra1, dec1, ra2, dec2) -> float:
    """Angular separation (haversine; exact across RA 0/360 and at the poles)."""
    p1, p2 = math.radians(dec1), math.radians(dec2)
    dl = math.radians(ra1 - ra2)
    h = math.sin((p1 - p2) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return math.degrees(2 * math.asin(min(1.0, math.sqrt(h)))) * 3600


def _clean(ra, dec, fov, rounded: bool = False) -> tuple[float, float, float]:
    """Validated region. Values set by code (catalogues, saved sequences) keep every digit; values
    coming from the map are rounded to 1e-7 deg (0.4 mas) and RA is folded into [0, 360)."""
    ra = _finite(ra, "RA")
    if rounded:
        ra, dec = normalise_ra(ra), round(_finite(dec, "Dec"), 7)
    ra, dec = validate_coordinates(ra, dec)
    return ra, dec, validate_fov_deg(fov)


def _finite(v, what):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{what} no numérica: {v!r}.") from None
    if not math.isfinite(f):
        raise ValueError(f"{what} no finita: {v!r}.")
    return f


# ----------------------------------------------------------------------------- the region
def _blank(ra, dec, fov, rev=0) -> dict:
    return {"ra": ra, "dec": dec, "fov": fov, "name": None, "astrometry": None, "anchor": None,
            "fixed_centre": False, "report": None, "notes": [], "extended": False, "rev": rev}


def get_region(state, params) -> dict:
    """The active region. Created once per session from the URL (or the default field)."""
    region = state.get("region")
    if region is not None:
        return region
    ra, dec, fov = DEFAULT_REGION["ra"], DEFAULT_REGION["dec"], DEFAULT_REGION["fov"]
    errors = []
    if "ra" in params or "dec" in params:
        try:
            ra, dec = validate_coordinates(params.get("ra"), params.get("dec"))
        except ValueError as err:
            errors.append(f"Coordenadas del enlace no válidas: {err} Se muestra la región por defecto y no se ha "
                          "realizado ninguna consulta.")
            ra, dec = DEFAULT_REGION["ra"], DEFAULT_REGION["dec"]
    if "fov" in params:
        try:
            fov = validate_fov_deg(params.get("fov"))
        except ValueError as err:
            errors.append(f"Campo de visión del enlace no válido: {err}")
    region = state["region"] = _blank(float(ra), float(dec), fov)
    if errors:
        state["region_errors"] = errors
    return region


def set_region(state, params, ra, dec, fov, *, name=None, astrometry=None, fixed_centre=False, report=None,
               notes=(), extended=False) -> dict:
    """Replace the region from outside the map (name search, saved sequence, link): the Atlas recentres."""
    ra, dec, fov = _clean(ra, dec, fov)
    rev = (state.get("region") or {}).get("rev", 0) + 1
    region = _blank(ra, dec, fov, rev)
    region.update(name=name, astrometry=astrometry, fixed_centre=bool(fixed_centre), report=report,
                  notes=list(notes), extended=bool(extended),
                  anchor=[ra, dec] if (name or astrometry or report) else None)
    state["region"] = region
    write_url(params, region)
    return region


def move_region(state, params, ra, dec, fov) -> dict:
    """The user moved the map, typed coordinates or changed the field of view.

    The object identity survives only while the centre stays on the object; a saved sequence stays
    attached only while centre and field are the ones it was computed for. ``rev`` is not changed:
    the Atlas already shows this position and must not be recentred by its own echo.
    """
    ra, dec, fov = _clean(ra, dec, fov, rounded=True)
    old = get_region(state, params)
    if separation_arcsec(ra, dec, old["ra"], old["dec"]) < 0.002:
        ra, dec = old["ra"], old["dec"]        # the map's echo of the same centre: keep every digit
    region = dict(old, ra=ra, dec=dec, fov=fov)
    anchor = old.get("anchor")
    on_anchor = bool(anchor) and separation_arcsec(ra, dec, anchor[0], anchor[1]) <= ANCHOR_TOLERANCE_ARCSEC
    if not on_anchor:
        region.update(name=None, astrometry=None, anchor=None, fixed_centre=False, report=None, notes=[],
                      extended=False)
    elif abs(fov - old["fov"]) > 1e-9:
        region.update(report=None)
    state["region"] = region
    write_url(params, region)
    return region


def set_object(state, params, astro, warnings=(), extended=False, position=None) -> dict:
    """Centre the region on a resolved object, keeping its catalogue astrometry.

    ``position`` is where the object is shown on the map (calculated for today when it has proper
    motion). Explorers do not use it: they receive the catalogue astrometry and compute the position
    for their own dates, exactly as before.
    """
    ra, dec = position if position is not None else (astro.ra_deg, astro.dec_deg)
    fov = get_region(state, params)["fov"]
    return set_region(state, params, ra, dec, fov, name=astro.name, astrometry=astro.to_dict(),
                      notes=list(warnings), extended=extended)


def set_from_report(state, params, stem: str, report: dict, label: str | None = None) -> dict:
    """Open a saved Time sequence: its exact centre and field, attached to the region."""
    t = report["target"]
    astro = t.get("astrometry")
    return set_region(state, params, t["ra_deg"], t["dec_deg"], t["field_deg"],
                      name=label or (astro or {}).get("name") or stem, astrometry=astro, fixed_centre=True,
                      report=stem)


def explorer_inputs(region: dict) -> dict:
    """What an explorer needs: centre, field and, for a named object, its catalogue astrometry.

    ``follow`` tells the explorer to centre on the object's position for ITS OWN dates (the
    behaviour of the former name search). A saved sequence keeps its exact centre instead.
    """
    from .astrometry import Astrometry

    astro = Astrometry.from_dict(region["astrometry"]) if region.get("astrometry") else None
    follow = astro is not None and not region.get("fixed_centre")
    ra, dec = (astro.ra_deg, astro.dec_deg) if follow else (region["ra"], region["dec"])
    return {"ra": float(ra), "dec": float(dec), "fov": float(region["fov"]), "astrometry": astro,
            "follow": follow, "label": region.get("name") or "coordenadas elegidas"}


# ----------------------------------------------------------------------------- URL mirror
def url_fields(region: dict) -> dict:
    ra = format(region["ra"], ".6f")
    if ra == "360.000000":
        ra = "0.000000"
    return {"ra": ra, "dec": format(region["dec"], ".6f"), "fov": format(region["fov"], "g")}


def write_url(params, region: dict, view: str | None = None, canal: int | None = None) -> None:
    """Mirror the region (and, inside an explorer, the view) in the URL. Writes only what changed."""
    want = url_fields(region)
    if view in EXPLORER_PARAM:
        want["explorer"] = EXPLORER_PARAM[view]
        if view == "spectrum" and canal is not None:
            want["canal"] = str(int(canal))
    for k in ("explorer", "canal"):
        if k not in want and (view is not None) and k in params:
            del params[k]
    for k, v in want.items():
        if params.get(k) != v:
            params[k] = v


def initial_view(params) -> str:
    return VIEW_OF_PARAM.get(params.get("explorer"), "region")


__all__ = ["DEFAULT_REGION", "VIEWS", "parse_region", "region_query", "get_region", "set_region", "move_region",
           "set_object", "set_from_report", "explorer_inputs", "write_url", "initial_view", "separation_arcsec",
           "normalise_ra"]
