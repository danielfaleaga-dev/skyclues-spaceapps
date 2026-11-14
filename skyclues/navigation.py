"""Navigation contracts; FOV in degrees. No spectral engine modifications."""
from urllib.parse import urlencode
from .targets import validate_coordinates, validate_fov_deg


def parse_region(params):
    ra,dec=validate_coordinates(params.get('ra'),params.get('dec'))
    fov=validate_fov_deg(params.get('fov',.1))
    explorer=params.get('explorer','temporal')
    if explorer not in ('temporal','espectral'):raise ValueError('Explorador desconocido')
    ch=params.get('canal','63')
    if not str(ch).isdigit() or not 1<=int(ch)<=102:raise ValueError('Canal fuera de 1-102')
    return {'ra':ra,'dec':dec,'fov':fov,'explorer':explorer,'canal':int(ch)}


def region_query(ra,dec,fov,explorer='temporal',canal=63):
    d=parse_region(dict(ra=ra,dec=dec,fov=fov,explorer=explorer,canal=canal))
    p={k:format(d[k],'.10g') for k in ('ra','dec','fov')};p['explorer']=explorer
    if explorer=='espectral':p['canal']=str(d['canal'])
    return '?'+urlencode(p)


def open_object(state,params,astro,explorer,fov):
    from .spectrum_page import fov_widget_state
    fov=validate_fov_deg(fov)
    state['report']=None
    for k in ('ra_in','dec_in','fov_preset','fov_custom','sx_ra','sx_dec','sx_fov','sx_fov_custom'):
        state.pop(k,None)
    # Time uses existing name astrometry; Spectrum uses its existing named-object epoch handling.
    if explorer=='espectral':
        state.update(explorer='Spectrum Explorer · longitud de onda',sx_source='Nombre (SIMBAD)',sx_obj=astro.name,
                     sx_resolved={'astrometry':astro.to_dict(),'warnings':astro.warnings()},**fov_widget_state(fov))
    else:
        state.update(explorer='Time Explorer · tiempo',mode='Nueva búsqueda',how='Nombre (SIMBAD)',obj_name=astro.name,
                     resolved={'astrometry':astro.to_dict(),'warnings':astro.warnings()})
    params.clear();params.update({'ra':str(astro.ra_deg),'dec':str(astro.dec_deg),'fov':str(fov),'explorer':explorer})


# ----------------------------------------------------------------------------- common region (name / coordinates / atlas)
DEFAULT_REGION = {"ra": 210.802429, "dec": 54.34875, "fov": 0.1}
TIME_KEYS = ("ra_in", "dec_in", "fov_preset", "fov_custom")
SPECTRUM_KEYS = ("sx_ra", "sx_dec", "sx_fov", "sx_fov_custom")
LOCATE_KEYS = ("loc_ra", "loc_dec", "loc_fov")


def current_region(state, params) -> dict:
    """The one region shared by the three locating methods and both explorers.

    The URL parameters ra/dec/fov are the common state (both explorers and the name
    search already write them); then the region of the open Time sequence; then M101.
    """
    out = None
    try:
        if "ra" in params and "dec" in params:
            ra, dec = validate_coordinates(params.get("ra"), params.get("dec"))
            fov = validate_fov_deg(params.get("fov", DEFAULT_REGION["fov"]))
            out = {"ra": ra, "dec": dec, "fov": fov}
    except ValueError:
        out = None
    if out is None and state.get("shared_region"):
        sh = state["shared_region"]
        out = {"ra": float(sh["ra"]), "dec": float(sh["dec"]), "fov": float(sh["fov"])}
    out = out or dict(DEFAULT_REGION)
    sel = state.get("sky_region")
    if sel and abs(sel["ra"] - out["ra"]) < 1e-6 and abs(sel["dec"] - out["dec"]) < 1e-6:
        out.update(source=sel.get("source"), astrometry=sel.get("astrometry"))
    return out


def set_region(state, params, ra, dec, fov, source: str, astrometry: dict | None = None) -> dict:
    """Write a region chosen with any locating method; every coordinate field follows it."""
    ra, dec = validate_coordinates(ra, dec)
    fov = validate_fov_deg(fov)
    state["sky_region"] = {"ra": ra, "dec": dec, "fov": fov, "source": source, "astrometry": astrometry}
    for k in TIME_KEYS + SPECTRUM_KEYS + LOCATE_KEYS:
        state.pop(k, None)
    params.update({"ra": format(ra, ".6f"), "dec": format(dec, ".6f"), "fov": format(fov, "g")})
    return state["sky_region"]


def open_region(explorer: str) -> None:
    """Callback: open the common region in one explorer (no search is started automatically)."""
    import streamlit as st
    from .astrometry import Astrometry
    from .spectrum_page import fov_widget_state
    state, params = st.session_state, st.query_params
    r = current_region(state, params)
    if r.get("astrometry"):
        open_object(state, params, Astrometry.from_dict(r["astrometry"]), explorer, r["fov"])
        return
    for k in TIME_KEYS + SPECTRUM_KEYS:
        state.pop(k, None)
    params.clear()
    params.update({"ra": format(r["ra"], ".6f"), "dec": format(r["dec"], ".6f"), "fov": format(r["fov"], "g"),
                   "explorer": explorer})
    if explorer == "espectral":
        state.update(explorer="Spectrum Explorer · longitud de onda", sx_source="Coordenadas RA/Dec",
                     sx_ra=r["ra"], sx_dec=r["dec"], **fov_widget_state(r["fov"]))
    else:
        state["report"] = None
        state.update(explorer="Time Explorer · tiempo", mode="Nueva búsqueda", how="Coordenadas RA/Dec")


def request_locate(state, mode: str) -> None:
    """Switch the locating method on the next full run (safe from fragments and callbacks)."""
    state["locate_pending"] = mode


def apply_pending(state) -> None:
    mode = state.pop("locate_pending", None)
    if mode:
        state["locate_mode"] = mode
