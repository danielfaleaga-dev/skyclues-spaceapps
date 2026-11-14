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
