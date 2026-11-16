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

MOTION='Motion · close dates over the same sky'
BANDS={MOTION:None,'Continuum · 1.0–1.5 µm':(1.,1.5),'CO₂ · 4,23–4,28 µm':(4.23,4.28),'All bands':(.7,5.1)}
FOLLOW,FIXED='Follow the object','Fixed star field'


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
    positions=analyse(identity_json,rows_json,fov,pipeline)['motion']['positions']
    return moving_view.build(frames,fov,follow,simple,animate,positions)


def _select(identity,ij,fov):
    cols=st.columns(2)
    start=cols[0].date_input('From (UTC)',key=theme.bind('moving_start',date(2025,8,1)),
                            on_change=theme.keep,args=('moving_start',))
    end=cols[1].date_input('To (UTC)',key=theme.bind('moving_end',date(2025,8,31)),
                          on_change=theme.keep,args=('moving_end',))
    query_key=(identity['spkid'],start.isoformat(),end.isoformat())
    store=st.session_state.setdefault('moving_discoveries',{})
    if st.button('Find SPHEREx observations',type='primary',key='moving_search'):
        try:
            with theme.loading('Querying SPHEREx observations along the trajectory…','moving_discovery'):
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
        st.info('Not evaluable: the products found do not have a compatible L2 format.' if d.get('excluded_products') else
                'No coverage: the query found no exposures in this interval. You can try other dates.');return
    if d.get('reference_warning'):
        st.warning('The reference table did not respond. The MOST positions for each exposure will be used, with their provenance made explicit.')
    st.caption(f"{len(d['rows'])} exposures found · NASA/IPAC IRSA")
    motion_sets=sources.motion_groups(d['rows'])
    # Measuring a displacement is the first choice whenever the archive allows it.
    band=st.selectbox('What to compare',list(BANDS),key=theme.bind('moving_band',MOTION if motion_sets else list(BANDS)[1]),
                      on_change=theme.keep,args=('moving_band',),
                      help='Motion: images from the same detector taken hours apart, which share sky. '
                           'Bands group images of the same wavelength to compare brightness.')
    gs=motion_sets if band==MOTION else sources.groups(d['rows'],*BANDS[band])
    if not gs:
        st.info('There are no images close enough in time to measure a displacement. Choose a band or widen the dates.'
                if band==MOTION else
                'There are exposures, but none in this wavelength range. Choose another band.');return
    def label(i):
        g=gs[i]
        if band==MOTION:
            t=[Time(r['mjd'],format='mjd').isot[:16].replace('T',' ') for r in g]
            lam=sorted(r['lambda_um'] for r in g)
            return f"{len(g)} images · {t[0]} → {t[-1][-5:] if t[0][:10]==t[-1][:10] else t[-1]} UTC · D{g[0]['detector']} · {lam[0]:.2f}–{lam[-1]:.2f} µm"
        dates=[Time(r['mjd'],format='mjd').isot[:10] for r in g]
        return f"{len(g)} {'images' if len(g)>1 else 'image'} · {dates[0]}"+(' → '+dates[-1] if len(g)>1 else '')+f" · D{g[0]['detector']} · {g[0]['lambda_um']:.3f} µm"
    group_key='moving_group_'+str(identity['spkid'])+'_'+band+'_'+start.isoformat()+'_'+end.isoformat()
    selected=st.selectbox('Sequence of compatible observations',range(len(gs)),format_func=label,
                           key=theme.bind(group_key,0),on_change=theme.keep,args=(group_key,))
    rows_json=json.dumps(gs[selected],sort_keys=True)
    selection=(ij,rows_json,fov,pipeline_key())
    active=st.session_state.get('moving_active')
    if st.button('Prepare images',key='moving_prepare',type='primary'):
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
    st.markdown('### Observations of the moving object')
    active=st.session_state.get('moving_active')
    ready=active and active[0]==ij and active[2:]==(fov,pipeline_key())
    with st.expander('Observations and dates',expanded=not ready):
        st.write('Each image uses the position predicted for its date, keeping the selected field.')
        if scientific:
            st.caption(f"Search centre: {region['solar'].get('utc','date not specified')} · "
                       f"{region['solar'].get('observer_label','observer not specified')}. "
                       'The exposure positions are kept separately.')
        selection=_select(identity,ij,fov)
    if selection is None:
        return
    try:
        with theme.loading('Retrieving images and verifying their positions…','moving_fetch'):
            frames,failures=prepare(*selection)
        for fail in failures:
            st.warning(f"{fail['obs_id']}: {fail['error']}")
        if failures and st.button('Retry images',key='moving_retry'):
            prepare.clear(*selection);analyse.clear(*selection);st.rerun()
        if not frames:
            st.info('Not evaluable: no usable images were retrieved. This is not an absence of signal.');return
        with theme.loading('Evaluating signal, background and control positions…','moving_analysis'):
            report=analyse(*selection)
    except (RuntimeError,ValueError,OSError) as e:
        st.error(str(e));return
    st.markdown('**'+ns.LABELS[report['status']]+'**')
    releases=sorted({f"{f.row['collection'].replace('spherex_','').upper()} · calibration v{f.row['version']}" for f in frames})
    st.caption('SPHEREx '+', '.join(releases))
    if any(f.row['collection']=='spherex_qr2' for f in frames):
        st.warning('Earlier QR2 product: this query did not find a DR1 replacement for these exposures.')
    motion=report['motion']
    motion_set=st.session_state.get('opt_moving_band')==MOTION
    if report['observed_motion']:
        minutes=motion['interval_hours']*60
        theme.facts([
            ('Measured displacement',f"{motion['displacement_arcsec']:.0f}″",f"± {motion['error_arcsec']:.0f}″"),
            ('Interval',f"{minutes:.0f} min" if minutes<180 else f"{motion['interval_hours']:.1f} h",''),
            ('Apparent rate',f"{motion['rate_arcsec_per_hour']:.0f}″/h",'on the sky, as seen from SPHEREx'),
            ('Control stars',str(motion['control_stars']),f"they do not move: ≤ {motion['control_radius_arcsec']:.1f}″")])
        st.write(motion['reason'] if scientific else
                 'The object appears in one place in the first image and in another in the last, and is no longer where it was: '
                 'it has moved relative to the stars.')
    else:
        st.write(report['motion_reason'] if scientific or motion.get('pair') else
                 'The signal still has to be confirmed. The cross marks a predicted position.')
    common=report['common_valid_fraction']
    # A fixed-star view needs shared sky, not a shared wavelength: positions are comparable, brightness is not.
    views=[FIXED,FOLLOW] if common>=.3 and len(frames)>1 and (motion_set or report['compatible']) else [FOLLOW]
    view_key='moving_view_motion' if motion_set else 'moving_view'
    default=FIXED if motion_set and FIXED in views else FOLLOW
    if theme.persistent(view_key,default) not in views:
        st.session_state['opt_'+view_key]=FOLLOW
    view=(st.radio('Display',views,horizontal=True,key=theme.bind(view_key,default),
                   on_change=theme.keep,args=(view_key,)) if len(views)>1 else views[0])
    notes=[]
    if len(frames)>1 and common<.3:
        notes.append('The images do not share enough sky to compare a fixed background.')
    if not report['compatible']:
        notes.append('The images are at different wavelengths: their position is comparable, their brightness is not.'
                     if motion_set else
                     'The FITS calibration reveals incompatible bands: they are reviewed separately, with no animation or stacking.')
    if not report['observed_motion'] and any(any(s['separation_arcsec']<12 for s in
                                                 f.row.get('stellar_context',{}).get('nearby',[])) for f in frames):
        notes.append('There are nearby stars that could be confused with the object.')
    if notes:
        st.warning(' '.join(notes))
    with theme.loading('Aligning the exposures to display them…','moving_render'):
        seen=[f['analysis']['status']=='candidate' or (f['analysis'].get('position_measured') or {}).get('measured')
              for f in report['frames']]
        animate=len(frames)>1 and all(seen) and (report['compatible'] or report['observed_motion'])
        html=display(*selection,view==FOLLOW,not scientific,animate,player.presentation_key())
    components.html(html,height=760,scrolling=True)
    if len(frames)>1 and not animate:
        st.caption('Review by dates: some image does not provide enough signal for an animation. Use Previous / Next.')
    if scientific:
        st.markdown('#### Quality and provenance')
        if report['joint_signal'].get('tests'):
            with st.expander('Faint signal: combination of native measurements'):
                st.json(report['joint_signal'])
        table=[]
        for f,r,m in zip(frames,report['frames'],motion['positions']):
            p=f.prediction
            off=m.get('offset_from_prediction_arcsec') or [None,None]
            table.append({'exposure':f.row['obs_id'],'UTC date':Time(f.row['mjd'],format='mjd').isot,
                          'detector':f.row['detector'],'λ (µm)':f.row['lambda_um'],'Δλ (µm)':f.row['bandwidth_um'],
                          'release':f.row['collection'],'calibration':f.row['version'],
                          'Predicted RA':p['ra'],'Predicted Dec':p['dec'],
                          'Measured RA':m.get('ra'),'Measured Dec':m.get('dec'),'S/N':m.get('snr'),
                          'measured − predicted E (″)':off[0],'measured − predicted N (″)':off[1],
                          'OUTLIER pixels used':m.get('outlier_pixels_in_core'),
                          'observer':p['observer'],'status':ns.LABELS[r['analysis']['status']],
                          'no measured position':m.get('reason','')})
        st.dataframe(pd.DataFrame(table),hide_index=True,width='stretch')
        if motion.get('pair'):
            with st.expander('Motion measurement: tests and controls'):
                st.write(motion['reason'])
                st.json({k:motion[k] for k in ('pair','registration_arcsec','control_radius_arcsec','control_stars',
                         'control_stars_rejected','measured_displacement_arcsec','error_arcsec','significance',
                         'rate_arcsec_per_hour','position_angle_deg','catalogue_comparison') if k in motion})
                st.caption('The position is fitted in the pixels of each image (official PSF), starting from the predicted one. '
                           'The object must appear at its position and have disappeared from it in the other image from the same '
                           'detector. The registration uses common stars, with the strict mask. OUTLIER pixels are admitted on the object: '
                           'the official pipeline flags compact sources that are absent from its catalogue this way. '
                           'The ephemeris is compared at the end and plays no part in the decision.')
        st.caption(f'Requested field: {fov*60:.1f}′. Context downloaded for backgrounds/controls: {max(fov,.25)*60:.1f}′. '
                   f'Common valid coverage: {common:.1%}. Each position corresponds to its exposure. '
                   'Unpublished orbital uncertainties remain unknown, never zero.')
        for i,r in enumerate(report['frames']):
            with st.expander(f"Analysis · {r['observation']['obs_id']}"):
                st.json(r['analysis']);st.markdown(f"[FITS original]({r['observation']['url']}) · [Cutout used]({r['cutout_url']})")
        if report['stack_allowed']:
            with st.expander('Stack following the object with a stationary control'):
                if st.button('Compare stacks',key='moving_stack'):
                    with theme.loading('Combining compatible observations…','moving_stack'):
                        a=ns.stack(frames,max(fov,.1),True);b=ns.stack(frames,max(fov,.1),False)
                        st.image(moving_view.render.figure_png(moving_view.stack_figure(a,b)))
                        st.write(a['method']);st.caption(a['limitation'])
                        st.write(f"Valid contributions per pixel: {int(a['contributions'].min())}–{int(a['contributions'].max())}.")
        st.download_button('Download reproducible report',json.dumps(report,indent=2,default=str),
                           file_name='moving_observations.json',mime='application/json')
        st.caption('Exploratory analysis of known objects. Extended apertures do not measure the position of the nucleus. '
                   'The stellar detector and Spectrum Explorer keep their previous engine.')
