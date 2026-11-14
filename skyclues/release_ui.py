"""Small app integration points for object search, share links and discovery status."""
from pathlib import Path
import streamlit as st
from . import object_search, navigation, config, releases

SEARCH=st.components.v2.component('sky_object_search',
 html='<label for="sky-name">Buscar un objeto o región del cielo</label><p>Escribe un nombre, por ejemplo: Andrómeda, M31, NGC 224, Barnard o WISE 0855.</p><input id="sky-name" maxlength="100" autocomplete="off"><button class="find">Buscar</button><div class="suggestions"></div>',
 css='label{font-weight:600}p{font-size:.85rem;color:#555}input{width:70%;padding:9px}button{padding:8px;cursor:pointer}.suggestions button{display:block;text-align:left;width:100%;margin:3px 0;border:1px solid #ccd4df;background:#f5f7fa}',
 js=Path(__file__).with_name('search_component.js').read_text(encoding='utf8'))
SHARE=st.components.v2.component('sky_share_region',html='<label>Enlace de esta región (FOV en grados)</label><input readonly aria-label="Enlace compartible"><button>Copiar enlace</button><span role="status"></span>',
 css='input{width:100%;padding:8px;box-sizing:border-box}button{margin:6px 0;padding:7px}',
 js="""export default function(c){const p=c.parentElement,u=new URL(window.location.href);u.search=c.data.query;u.hash='';const i=p.querySelector('input');i.value=u.href;p.querySelector('button').onclick=async()=>{i.select();try{await navigator.clipboard.writeText(i.value);p.querySelector('span').textContent='Copiado'}catch(e){p.querySelector('span').textContent='Seleccione el enlace y copie con Ctrl+C'}}}""")

@st.cache_data(ttl=3600,max_entries=128,show_spinner=False)
def suggestions(q):
    rows,status=object_search.remote_suggestions(q)
    if status.startswith('Sugerencias remotas no disponibles'):raise RuntimeError(status)
    return rows,status

@st.fragment
def search():
    state=st.session_state.get('sky_search',{})
    q=state.get('query','')
    remote,status=[],''
    if len(q.strip())>=3:
        try:remote,status=suggestions(q)
        except (ValueError,RuntimeError) as e:status=str(e)
    result=SEARCH(data={'query':q,'local':object_search.INDEX,'remote':remote},key='sky_search',
                  default={'query':''},on_query_change=lambda:None,on_pick_change=lambda:None)
    if status:st.caption(status)
    if result.pick:
        try:
            a,w,extended=object_search.resolve(result.pick)
            st.session_state['sky_selected']={'astrometry':a.to_dict(),'warnings':w,'extended':extended}
        except Exception as e:
            st.session_state.pop('sky_selected',None);st.warning(f'No se pudo resolver el nombre: {e}')
    selected=st.session_state.get('sky_selected')
    if selected:
        from .astrometry import Astrometry
        a=Astrometry.from_dict(selected['astrometry'])
        st.caption(f'{a.name} · ICRS RA {a.ra_deg:.8f}°, Dec {a.dec_deg:+.8f}° · catálogo J{a.epoch_jyear:.1f} · {a.source}')
        if selected['extended']:st.info('Centro catalogado de un objeto extenso; el campo de 3–30 minutos de arco puede mostrar solo una parte.')
        for w in selected['warnings']:st.caption(w)
        st.caption('Si hay movimiento propio, cada explorador reutiliza su cálculo de época. No es una detección observada.')
        if st.button('Ver en Atlas',key='open_object_atlas',on_click=_object_to_atlas,args=(a.to_dict(),)):
            st.rerun(scope='app')
        for mode,label in [('temporal','Abrir objeto en Time Explorer'),('espectral','Abrir objeto en Spectrum Explorer')]:
            if st.button(label,key='open_object_'+mode):
                try:fov=float(st.query_params.get('fov',config.DEFAULT_FIELD_DEG))
                except (ValueError,TypeError):fov=config.DEFAULT_FIELD_DEG
                spectral=st.session_state.get('explorer','').startswith('Spectrum')
                preset=st.session_state.get('sx_fov' if spectral else 'fov_preset')
                if preset=='Otro':fov=st.session_state.get('sx_fov_custom' if spectral else 'fov_custom',fov*60)/60
                elif preset:fov=float(preset.rstrip('′'))/60
                navigation.open_object(st.session_state,st.query_params,a,mode,fov)
                st.rerun(scope='app')


def share(ra,dec,fov,explorer='temporal',canal=63):
    with st.expander('Compartir esta región'):
        SHARE(data={'query':navigation.region_query(ra,dec,fov,explorer,canal)},key='share_region')
        st.caption('El enlace conserva el centro, no una detección ni todos los datos de la sesión. No vuelve a resolver nombres; los objetos móviles quedan en estas coordenadas fijas.')


def discovery(report):
    d=report.get('discovery') or {}
    if d.get('queried_utc'):
        st.caption(f"Observaciones: {d['origin']} · verificadas en IRSA {d['queried_utc']} · {d['selected_count']} productos ({d['raw_count']} representaciones).")
    else:st.caption('Resultado histórico: fecha de consulta a IRSA no registrada. No equivale a una verificación actual.')
    if d.get('replacements'):
        with st.expander('Productos duplicados o sustituidos'):st.json(d['replacements'])


def refresh_saved(ra,dec,fov,astrometry=None):
    from .spectrum_page import to_time_explorer
    to_time_explorer(ra,dec,fov)
    if astrometry:
        st.session_state.update(how='Nombre (SIMBAD)',obj_name=astrometry['name'],resolved={'astrometry':astrometry,'warnings':[]})
    st.session_state['release_force_refresh']=True


LOCATE_MODES = ["Por nombre", "Coordenadas", "Atlas"]


def _object_to_atlas(astro_dict):
    from . import atlas
    from .astrometry import Astrometry
    atlas.show_object(Astrometry.from_dict(astro_dict))
    navigation.request_locate(st.session_state, "Atlas")


def locate():
    """Three ways to locate a region; all of them write the same common region."""
    navigation.apply_pending(st.session_state)
    if st.session_state.get("locate_mode") not in LOCATE_MODES:
        st.session_state["locate_mode"] = LOCATE_MODES[0]
    mode = st.radio("Localizar una región del cielo", LOCATE_MODES, key="locate_mode", horizontal=True,
                    help="Por nombre (SIMBAD e índice local), por coordenadas RA/Dec o explorando el Atlas. "
                         "Los tres métodos comparten la misma región con Time Explorer y Spectrum Explorer.")
    if mode == "Por nombre":
        search()
    elif mode == "Coordenadas":
        coordinates()
    else:
        from . import atlas
        atlas.render()


def _coords_from_inputs():
    s = st.session_state
    return float(s["loc_ra"]), float(s["loc_dec"]), float(s["loc_fov"]) / 60


def _coords_to_atlas():
    from . import atlas
    try:
        ra, dec, fov = _coords_from_inputs()
        navigation.set_region(st.session_state, st.query_params, ra, dec, fov, source="Coordenadas")
    except ValueError as err:
        st.session_state["loc_error"] = str(err)
        return
    atlas.show_region(ra, dec, fov)
    navigation.request_locate(st.session_state, "Atlas")


def _coords_open(explorer):
    try:
        ra, dec, fov = _coords_from_inputs()
        navigation.set_region(st.session_state, st.query_params, ra, dec, fov, source="Coordenadas")
    except ValueError as err:
        st.session_state["loc_error"] = str(err)
        return
    navigation.open_region(explorer)


def coordinates():
    r = navigation.current_region(st.session_state, st.query_params)
    s = st.session_state
    s.setdefault("loc_ra", float(r["ra"]))
    s.setdefault("loc_dec", float(r["dec"]))
    s.setdefault("loc_fov", round(float(r["fov"]) * 60, 1))
    c1, c2, c3 = st.columns(3)
    c1.number_input("RA (grados, ICRS)", min_value=0.0, max_value=359.999999, format="%.6f", key="loc_ra")
    c2.number_input("Dec (grados, ICRS)", min_value=-90.0, max_value=90.0, format="%.6f", key="loc_dec")
    c3.number_input("Diámetro (minutos de arco)", min_value=config.FOV_MIN_DEG * 60, max_value=config.FOV_MAX_DEG * 60,
                    step=0.5, format="%.1f", key="loc_fov")
    err = s.pop("loc_error", None)
    if err:
        st.error(f"Coordenadas no válidas: {err}")
    st.caption("Coordenadas fijas para todas las fechas. Para un objeto con movimiento propio use «Por nombre».")
    b1, b2, b3 = st.columns(3)
    b1.button("Ver en Atlas", key="loc_atlas", on_click=_coords_to_atlas)
    b2.button("Abrir en Time Explorer", key="loc_time", on_click=_coords_open, args=("temporal",))
    b3.button("Abrir en Spectrum Explorer", key="loc_spectrum", on_click=_coords_open, args=("espectral",))
