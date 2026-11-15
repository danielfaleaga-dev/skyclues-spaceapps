"""Known moving targets inside the existing Time Explorer; no new search or explorer."""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from astropy.time import Time

from . import moving_sources as sources, non_sidereal as ns, moving_view, player, theme

BANDS={'Continuo · 1,0–1,5 µm':(1.,1.5),'CO₂ · 4,23–4,28 µm':(4.23,4.28),'Todas las bandas':(.7,5.1)}


def pipeline_key():
    root=Path(__file__).parent
    return hashlib.sha256(b''.join((root/f).read_bytes() for f in
        ('non_sidereal.py','moving_sources.py','moving_view.py'))).hexdigest()


@st.cache_data(show_spinner=False,max_entries=24,ttl=86400)
def discover(identity_json,start,end,refresh=False):
    d=sources.discover(json.loads(identity_json),start,end,refresh=refresh)
    # A published reference is optional. Failure remains explicit and MOST refines selected rows.
    try:
        sources.attach_reference(d,refresh=refresh)
    except (RuntimeError,ValueError,OSError) as e:
        d['reference_warning']=str(e)
    sources.estimate_bands(d['rows'])
    return d


@st.cache_resource(show_spinner=False,max_entries=6)
def prepare(identity_json,rows_json,fov,pipeline):
    return ns.fetch_frames(json.loads(identity_json),json.loads(rows_json),fov)


@st.cache_data(show_spinner=False,max_entries=6)
def analyse(identity_json,rows_json,fov,pipeline):
    frames,_=prepare(identity_json,rows_json,fov,pipeline)
    return ns.assess(frames,fov)


@st.cache_data(show_spinner=False,max_entries=12)
def display(identity_json,rows_json,fov,pipeline,follow,simple,animate,presentation):
    frames,_=prepare(identity_json,rows_json,fov,pipeline)
    return moving_view.build(frames,fov,follow,simple,animate)


def _select(identity,ij,fov):
    cols=st.columns(2)
    start=cols[0].date_input('Desde (UTC)',key=theme.bind('moving_start',date(2025,8,1)),
                            on_change=theme.keep,args=('moving_start',))
    end=cols[1].date_input('Hasta (UTC)',key=theme.bind('moving_end',date(2025,8,31)),
                          on_change=theme.keep,args=('moving_end',))
    query_key=(identity['spkid'],start.isoformat(),end.isoformat())
    store=st.session_state.setdefault('moving_discoveries',{})
    if st.button('Buscar observaciones SPHEREx',type='primary',key='moving_search'):
        try:
            with theme.loading('Consultando observaciones SPHEREx a lo largo de la trayectoria…','moving_discovery'):
                args=(ij,start.isoformat(),(end+timedelta(days=1)).isoformat(),query_key in store)
                if query_key in store:
                    discover.clear(*args)
                store[query_key]=discover(*args)
        except (RuntimeError,ValueError,OSError) as e:
            st.error(str(e));return
    d=store.get(query_key)
    if d is None:
        return
    if not d['rows']:
        st.info('No evaluable: los productos encontrados no tienen un formato L2 compatible.' if d.get('excluded_products') else
                'Sin cobertura: la consulta no encontró exposiciones en este intervalo. Puede probar otras fechas.');return
    if d.get('reference_warning'):
        st.warning('La tabla de referencia no respondió. Se usarán las posiciones de MOST por exposición, con su procedencia explícita.')
    st.caption(f"{len(d['rows'])} exposiciones encontradas · NASA/IPAC IRSA")
    band=st.selectbox('Longitudes de onda',list(BANDS),key=theme.bind('moving_band',next(iter(BANDS))),
                      on_change=theme.keep,args=('moving_band',))
    gs=sources.groups(d['rows'],*BANDS[band])
    if not gs:
        st.info('Hay exposiciones, pero ninguna en este intervalo de longitudes de onda. Elija otra banda.');return
    def label(i):
        g=gs[i]
        dates=[Time(r['mjd'],format='mjd').isot[:10] for r in g]
        return f"{len(g)} {'imágenes' if len(g)>1 else 'imagen'} · {dates[0]}"+(' → '+dates[-1] if len(g)>1 else '')+f" · D{g[0]['detector']} · {g[0]['lambda_um']:.3f} µm"
    group_key='moving_group_'+str(identity['spkid'])+'_'+band+'_'+start.isoformat()+'_'+end.isoformat()
    selected=st.selectbox('Secuencia de observaciones compatibles',range(len(gs)),format_func=label,
                           key=theme.bind(group_key,0),on_change=theme.keep,args=(group_key,))
    rows_json=json.dumps(gs[selected],sort_keys=True)
    selection=(ij,rows_json,fov,pipeline_key())
    active=st.session_state.get('moving_active')
    if st.button('Preparar imágenes',key='moving_prepare',type='primary'):
        st.session_state['moving_active']=selection
        st.rerun()
    if active!=selection:
        return
    return selection


def render(region,scientific=False):
    identity=region['solar']['identity']
    fov=region['fov']
    ij=json.dumps(identity,sort_keys=True)
    theme.region_strip(region.get('name') or identity['name'],region['ra'],region['dec'],fov)
    st.markdown('### Observaciones del objeto en movimiento')
    active=st.session_state.get('moving_active')
    ready=active and active[0]==ij and active[2:]==(fov,pipeline_key())
    with st.expander('Observaciones y fechas',expanded=not ready):
        st.write('Cada imagen usa la posición prevista para su fecha, conservando el campo seleccionado.')
        if scientific:
            st.caption(f"Centro del buscador: {region['solar'].get('utc','fecha no especificada')} · "
                       f"{region['solar'].get('observer_label','observador no especificado')}. "
                       'Las posiciones de las exposiciones se conservan por separado.')
        selection=_select(identity,ij,fov)
    if selection is None:
        return
    try:
        with theme.loading('Recuperando imágenes y verificando sus posiciones…','moving_fetch'):
            frames,failures=prepare(*selection)
        for fail in failures:
            st.warning(f"{fail['obs_id']}: {fail['error']}")
        if failures and st.button('Reintentar imágenes',key='moving_retry'):
            prepare.clear(*selection);analyse.clear(*selection);st.rerun()
        if not frames:
            st.info('No evaluable: no se recuperaron imágenes utilizables. No es una ausencia de señal.');return
        with theme.loading('Evaluando señal, fondo y posiciones de control…','moving_analysis'):
            report=analyse(*selection)
    except (RuntimeError,ValueError,OSError) as e:
        st.error(str(e));return
    st.markdown('**'+ns.LABELS[report['status']]+'**')
    releases=sorted({f"{f.row['collection'].replace('spherex_','').upper()} · calibración v{f.row['version']}" for f in frames})
    st.caption('SPHEREx '+', '.join(releases))
    if any(f.row['collection']=='spherex_qr2' for f in frames):
        st.warning('Producto QR2 anterior: esta consulta no encontró un reemplazo DR1 para estas exposiciones.')
    st.write(report['motion_reason'] if scientific else
             'La señal aún debe confirmarse. La cruz marca una posición prevista.'
             if not report['observed_motion'] else 'Las imágenes muestran un desplazamiento medido frente a estrellas comunes.')
    common=report['common_valid_fraction']
    views=['Seguir al objeto','Fondo estelar fijo'] if common>=.3 and len(frames)>1 and report['compatible'] else ['Seguir al objeto']
    if theme.persistent('moving_view','Seguir al objeto') not in views:
        st.session_state['opt_moving_view']='Seguir al objeto'
    view=(st.radio('Representación',views,horizontal=True,key=theme.bind('moving_view','Seguir al objeto'),
                   on_change=theme.keep,args=('moving_view',)) if len(views)>1 else views[0])
    notes=[]
    if len(frames)>1 and common<.3:
        notes.append('Las imágenes no comparten suficiente cielo para comparar un fondo fijo.')
    if not report['compatible']:
        st.warning('La calibración de los FITS revela bandas incompatibles: se revisan por separado, sin animación ni apilamiento.')
    if any(any(s['separation_arcsec']<12 for s in f.row.get('stellar_context',{}).get('nearby',[])) for f in frames):
        notes.append('Hay estrellas próximas que podrían confundirse con el objeto.')
    if notes:
        st.warning(' '.join(notes))
    with theme.loading('Alineando las exposiciones para visualizarlas…','moving_render'):
        animate=(len(frames)>1 and report['compatible'] and
                 all(f['analysis']['status']=='candidate' for f in report['frames']))
        html=display(*selection,view=='Seguir al objeto',not scientific,animate,player.presentation_key())
    components.html(html,height=760,scrolling=True)
    if len(frames)>1 and not animate:
        st.caption('Revisión por fechas: alguna imagen no aporta señal suficiente para una animación. Use Anterior / Siguiente.')
    if scientific:
        st.markdown('#### Calidad y procedencia')
        if report['joint_signal'].get('tests'):
            with st.expander('Señal débil: combinación de mediciones nativas'):
                st.json(report['joint_signal'])
        table=[]
        for f,r in zip(frames,report['frames']):
            p=f.prediction
            table.append({'exposición':f.row['obs_id'],'fecha UTC':Time(f.row['mjd'],format='mjd').isot,
                          'detector':f.row['detector'],'λ (µm)':f.row['lambda_um'],'Δλ (µm)':f.row['bandwidth_um'],
                          'liberación':f.row['collection'],'calibración':f.row['version'],
                          'RA prevista':p['ra'],'Dec prevista':p['dec'],'observador':p['observer'],
                          'estado':ns.LABELS[r['analysis']['status']]})
        st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch')
        st.caption(f'Campo solicitado: {fov*60:.1f}′. Contexto descargado para fondos/controles: {max(fov,.25)*60:.1f}′. '
                   f'Cobertura válida común: {common:.1%}. Cada posición corresponde a su exposición. '
                   'Las incertidumbres orbitales no publicadas permanecen desconocidas, nunca cero.')
        for i,r in enumerate(report['frames']):
            with st.expander(f"Análisis · {r['observation']['obs_id']}"):
                st.json(r['analysis']);st.markdown(f"[FITS original]({r['observation']['url']}) · [Recorte utilizado]({r['cutout_url']})")
        if report['stack_allowed']:
            with st.expander('Apilamiento con seguimiento y control estacionario'):
                if st.button('Comparar apilamientos',key='moving_stack'):
                    with theme.loading('Combinando observaciones compatibles…','moving_stack'):
                        a=ns.stack(frames,max(fov,.1),True);b=ns.stack(frames,max(fov,.1),False)
                        st.image(moving_view.render.figure_png(moving_view.stack_figure(a,b)))
                        st.write(a['method']);st.caption(a['limitation'])
                        st.write(f"Contribuciones válidas por píxel: {int(a['contributions'].min())}–{int(a['contributions'].max())}.")
        st.download_button('Descargar informe reproducible',json.dumps(report,indent=2,default=str),
                           file_name='moving_observations.json',mime='application/json')
        st.caption('Análisis exploratorio de objetos conocidos. Las aperturas extendidas no miden la posición del núcleo. '
                   'El detector estelar y Spectrum Explorer conservan su motor anterior.')
