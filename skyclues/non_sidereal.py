"""Conservative, object-independent analysis of known non-sidereal targets.

Predictions locate tests; they never supply measured displacements. Native data
and variances are used for signal tests. Nearest-neighbour stacks are diagnostic,
explicitly resampled, with no filling of missing data or precision photometry.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import warnings

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astropy.wcs import WCS, NoConvergence
from astropy.wcs.utils import proj_plane_pixel_scales
import astropy.units as u

from . import archive, fitsdata, motion, moving_sources
from .geometry import gnomonic

METHOD = 'non-sidereal 1.0'
LABELS = {'predicted': 'Posición prevista', 'candidate': 'Señal candidata',
          'observed': 'Movimiento observado', 'unevaluable': 'No evaluable', 'no_coverage': 'Sin cobertura'}
SCALES_ARCSEC = (12., 24., 48., 96.)


@dataclass
class MovingFrame:
    row: dict
    image: object
    path: object
    cutout_url: str
    sha256: str

    @property
    def prediction(self):
        return self.row['prediction']


def pixel_scale(img):
    return float(np.sqrt(np.prod(proj_plane_pixel_scales(img.wcs)[:2]))*3600)


def target_pixel(frame):
    p = frame.prediction
    x,y = world_to_pixel(frame.image.wcs,p['ra'],p['dec'])
    return float(x),float(y)


def world_to_pixel(wcs,ra,dec):
    """Distant, non-overlapping SIP fields can diverge. Never use those solutions."""
    ra,dec=np.broadcast_arrays(ra,dec)
    try:
        return wcs.all_world2pix(ra,dec,0)
    except NoConvergence as e:
        xy=np.array(e.best_solution,copy=True).reshape(-1,2)
        bad=set([] if e.divergent is None else np.atleast_1d(e.divergent).tolist())
        bad.update([] if e.slow_conv is None else np.atleast_1d(e.slow_conv).tolist())
        if not bad:
            xy[:]=np.nan
        else:
            xy[list(bad)]=np.nan
        return xy[:,0].reshape(ra.shape),xy[:,1].reshape(dec.shape)


def inside(img,x,y):
    ny,nx = img.image.shape
    return np.isfinite(x+y) and -.5<=x<nx-.5 and -.5<=y<ny-.5


def fetch_frames(identity, rows, fov, progress=None):
    if not 0.05 <= fov <= .5 or not 1 <= len(rows) <= 8:
        raise ValueError('FOV o cantidad de exposiciones fuera de límites.')
    log = progress or (lambda message: None)
    frames, failures = [], []
    for n,row in enumerate(rows):
        try:
            log(f'Calculando la posición para la exposición {n+1} de {len(rows)}…')
            row = moving_sources.refine_prediction(identity, row)
            p = row['prediction']
            # Preserve requested FOV; extra context is explicit, used for local sky/control apertures.
            size = max(fov,.25)
            url = archive.cutout_url(row['url'],p['ra'],p['dec'],size)
            log(f'Recuperando imagen {n+1} de {len(rows)}…')
            path = archive.fetch(url)
            img = fitsdata.load(path)
            det = int(str(img.meta['DETECTOR']).lstrip('D'))
            if det != row['detector'] or str(img.meta['OBSID']) != row['obs_id']:
                raise ValueError('FITS y metadatos identifican exposiciones diferentes.')
            mjd = float(img.meta['MJD-AVG'])
            if abs(mjd-row['mjd'])*86400 > 2:
                raise ValueError('La fecha FITS no coincide con la predicción por exposición.')
            f = MovingFrame({**row, 'mjd':mjd,'context_deg':size},img,path,url,archive.sha256(path))
            x,y = target_pixel(f)
            f.row['prediction_inside'] = bool(inside(img,x,y))
            if inside(img,x,y):
                ix,iy = int(np.clip(round(x),0,img.shape[1]-1)),int(np.clip(round(y),0,img.shape[0]-1))
                f.row.update(lambda_um=float(img.wavelength_um[iy,ix]),
                             bandwidth_um=float(img.bandwidth_um[iy,ix]))
            log('Comprobando estrellas de fondo próximas…')
            try:
                f.row['stellar_context']=moving_sources.stellar_context(f.row)
            except (RuntimeError,ValueError,OSError) as e:
                f.row['stellar_context']={'unavailable':str(e)[:200]}
            frames.append(f)
        except (RuntimeError, ValueError, OSError) as e:
            failures.append({'obs_id':row['obs_id'],'detector':row['detector'],'error':str(e)[:350]})
    return frames, failures


def _mad(a):
    return float(1.4826*np.median(np.abs(a-np.median(a)))) if len(a) else np.nan


def _measure(img, x, y, radius, compact=False):
    """A fixed-position test: ePSF amplitude+plane or aperture above a robust sky plane.

    Propagates VARIANCE and background-plane covariance; annular scatter sets an
    independent noise floor. No clipping inside the source, no smoothing.
    """
    if not inside(img,x,y):
        return {'evaluable':False,'reason':'posición fuera de cobertura'}
    scale = pixel_scale(img)
    r = radius/scale
    h = math.ceil(max(2.5*r,8))
    ny,nx = img.image.shape
    x0,x1=max(0,int(x)-h),min(nx,int(x)+h+2)
    y0,y1=max(0,int(y)-h),min(ny,int(y)+h+2)
    yy,xx=np.mgrid[y0:y1,x0:x1]
    dx,dy=xx-x,yy-y
    rr=np.hypot(dx,dy)
    ap=rr<=r
    ann=(rr>=max(1.6*r,5))&(rr<=max(2.5*r,8))
    data=(img.image-img.zodi)[y0:y1,x0:x1]
    var=img.variance[y0:y1,x0:x1]
    ok=img.valid()[y0:y1,x0:x1]&np.isfinite(data)&np.isfinite(var)&(var>0)
    fy,fx=np.mgrid[int(y)-h:int(y)+h+2,int(x)-h:int(x)+h+2]
    fr=np.hypot(fx-x,fy-y)
    expected=int(np.sum(fr<=r))
    coverage=float(np.sum(ap&ok)/max(expected,1))
    expected_ann=int(np.sum((fr>=max(1.6*r,5))&(fr<=max(2.5*r,8))))
    if coverage<.8 or np.sum(ann&ok)<max(30,.65*expected_ann):
        return {'evaluable':False,'coverage':min(coverage,1.),'reason':'apertura o fondo con cobertura insuficiente'}
    a=np.stack([np.ones_like(dx),dx/r,dy/r],axis=-1)
    bg=ann&ok
    for _ in range(4):
        beta=np.linalg.lstsq(a[bg],data[bg],rcond=None)[0]
        resid=data-np.einsum('ijk,k->ij',a,beta)
        scatter=max(_mad(resid[bg]),float(np.sqrt(np.median(var[bg]))))
        bg=ann&ok&(np.abs(resid)<3.5*scatter)
        if bg.sum()<30:
            return {'evaluable':False,'reason':'fondo contaminado o insuficiente'}
    cov=np.linalg.pinv(a[bg].T@a[bg])*scatter**2
    support=ap&ok
    noise=np.maximum(var,scatter**2)
    psf_description=None
    if compact:
        psf=motion.psf_for(img,x,y)  # optical model only; stellar motion detector is untouched
        p=psf(dx,dy)
        w=np.where(support,1/np.where(noise>0,noise,1),0.)
        den=float(np.sum(p*p*w))
        if not np.isfinite(den) or den<=0:
            return {'evaluable':False,'reason':'PSF no evaluable'}
        weights=p*w/den
        psf_description=psf.description
    else:
        weights=support.astype(float)
    flux=float(np.sum(np.where(ok,resid,0)*weights))
    sensitivity=np.sum(a*weights[...,None],axis=(0,1))
    err=math.sqrt(float(np.sum(np.where(ok,noise,0)*weights**2)+sensitivity@cov@sensitivity))
    lam=img.wavelength_um[y0:y1,x0:x1][support]
    bw=img.bandwidth_um[y0:y1,x0:x1][support]
    spread=float(np.ptp(lam)/np.median(bw)) if len(lam) else np.inf
    return {'evaluable':bool(spread<=1.),'reason':'' if spread<=1 else 'gradiente espectral excesivo en apertura',
            'response':flux,'error':err,'snr':flux/err,'background':float(beta[0]),
            'background_scatter':scatter,'background_pixels':int(bg.sum()),
            'coverage':min(coverage,1.),'spectral_span_bw':spread,'radius_arcsec':radius,
            'psf':psf_description,'x':x,'y':y}


def evaluate_frame(frame, morphology='both'):
    img=frame.image
    x,y=target_pixel(frame)
    if not inside(img,x,y):
        return {'status':'no_coverage','tests':[],'reason':'La posición prevista cae fuera del FITS.'}
    from .compare import finast_status
    if str(img.meta.get('L2DQAFLG','')).strip()!='Pass' or finast_status([img.meta.get('FINAST')])=='fail':
        return {'status':'unevaluable','tests':[],'reason':'Control de calidad o astrometría oficial no aptos.',
                'quality': {k:img.meta.get(k) for k in ('L2DQAFLG','FINAST')}}
    tests=[]
    configurations=[]
    if morphology in ('both','compact'):
        configurations.append(('compact',max(12.,float(img.meta.get('PSF_FWHM') or 12)*1.5)))
    if morphology in ('both','extended'):
        configurations.extend(('extended',r) for r in SCALES_ARCSEC)
    for kind,r in configurations:
        m=_measure(img,x,y,r,kind=='compact')
        controls=[]
        # Same statistic at eight predeclared nearby positions. Not a blind survey.
        distance=(150 if kind=='compact' else max(4*r,75))/pixel_scale(img)
        centre=SkyCoord(frame.prediction['ra']*u.deg,frame.prediction['dec']*u.deg)
        for j,angle in enumerate(np.arange(8)*np.pi/4):
            sky=centre.directional_offset_by(angle*u.rad,distance*pixel_scale(img)*u.arcsec)
            cx,cy=world_to_pixel(img.wcs,sky.ra.deg,sky.dec.deg)
            c=_measure(img,float(cx),float(cy),r,kind=='compact')
            if c.get('evaluable'):
                c['control_index']=j
                controls.append(c)
        m.update(morphology=kind,controls=controls)
        snrs=[c['snr'] for c in controls]
        m['control_max_snr']=max(snrs,default=None)
        # Conservative family-wise threshold, plus empirical local controls.
        m['candidate']=bool(m.get('evaluable') and len(snrs)>=4 and m['snr']>=6 and
                            m['snr']>max(snrs)+2)
        m['contamination_warning']=bool(snrs and max(snrs)>=5)
        tests.append(m)
    valid=[m for m in tests if m.get('evaluable')]
    candidates=[m for m in valid if m.get('candidate')]
    status='candidate' if candidates else 'predicted' if valid else 'unevaluable'
    return {'status':status,'tests':tests,'reason':
            'Exceso compatible en la posición prevista; identificación y movimiento aún no confirmados.' if candidates else
            'No hay evidencia suficiente de señal frente al ruido y los controles.' if valid else
            'Máscara, fondo o cobertura impiden evaluar la señal.',
            'prediction_xy':[x,y], 'dqa':{k:img.meta.get(k) for k in
              ('L1DQAFLG','L2DQAFLG','FINAST','ASTRONETSOLVED','HE_AIRGLOW_CONT','AURORA_CONT')},
            'stellar_context':frame.row.get('stellar_context',{'unavailable':'No solicitado'}),
            'position_measured':None}


def grid(ra,dec,fov,scale=6.15):
    n=int(np.ceil(fov*3600/scale))
    w=WCS(naxis=2)
    w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crval=[ra,dec]
    w.wcs.crpix=[(n+1)/2,(n+1)/2];w.wcs.cdelt=[-scale/3600,scale/3600]
    return w,(n,n)


def requested_field(shape,fov):
    yy,xx=np.indices(shape)
    return np.hypot(xx-(shape[1]-1)/2,yy-(shape[0]-1)/2)<=fov*3600/6.15/2


def resample(frame,wcs,shape):
    """Nearest native pixel; unknown area and masked pixels remain distinct."""
    yy,xx=np.indices(shape)
    ra,dec=wcs.all_pix2world(xx,yy,0)
    sx,sy=world_to_pixel(frame.image.wcs,ra,dec)
    finite=np.isfinite(sx)&np.isfinite(sy)
    ix=np.rint(np.where(finite,sx,0)).astype(int);iy=np.rint(np.where(finite,sy,0)).astype(int)
    ny,nx=frame.image.image.shape
    covered=finite&(sx>=-.5)&(sy>=-.5)&(sx<nx-.5)&(sy<ny-.5)
    ix=np.clip(ix,0,nx-1);iy=np.clip(iy,0,ny-1)
    good=covered&frame.image.valid()[iy,ix]
    data=(frame.image.image-frame.image.zodi)[iy,ix]
    var=frame.image.variance[iy,ix]
    good &= np.isfinite(data)&np.isfinite(var)&(var>0)
    return np.where(good,data,np.nan),np.where(good,var,np.nan),covered


def aligned(frames,fov,follow=True):
    arrays,variances,coverage=[],[],[]
    p0=frames[0].prediction
    for f in frames:
        p=f.prediction if follow else p0
        w,shape=grid(p['ra'],p['dec'],fov)
        d,v,c=resample(f,w,shape)
        arrays.append(d);variances.append(v);coverage.append(c)
    return np.array(arrays),np.array(variances),np.array(coverage)


def stack(frames,fov,follow=True):
    if len(frames)<2 or any(not moving_sources.compatible(a.row,b.row) for a in frames for b in frames):
        raise ValueError('El apilamiento necesita al menos dos exposiciones del mismo detector, liberación y banda.')
    if max(f.row['mjd'] for f in frames)-min(f.row['mjd'] for f in frames)>7:
        raise ValueError('Más de siete días: no se presupone estabilidad para combinar estas exposiciones.')
    data,var,geom=aligned(frames,fov,follow)
    yy,xx=np.indices(data.shape[1:]);rr=np.hypot(xx-(data.shape[2]-1)/2,yy-(data.shape[1]-1)/2)*6.15
    backgrounds=[]
    for i in range(len(data)):
        bg=data[i][(rr>max(120,fov*3600*.3))&np.isfinite(data[i])]
        if len(bg)<30:
            backgrounds.append(None)
            data[i]=np.nan
        else:
            backgrounds.append(float(np.median(bg)));data[i]-=backgrounds[-1]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        median=np.nanmedian(data,axis=0)
        scatter=1.4826*np.nanmedian(np.abs(data-median),axis=0)
        keep=np.isfinite(data)&np.isfinite(var)&(var>0)
        if len(frames)>=3:
            keep &= np.abs(data-median)<=4*np.sqrt(var+scatter**2)
        weights=np.where(keep,1/np.where(keep,var,1),0)
        den=weights.sum(axis=0)
        mean=np.divide(np.nansum(data*weights,axis=0),den,out=np.full_like(den,np.nan),where=den>0)
        variance=np.divide(1.,den,out=np.full_like(den,np.nan),where=den>0)
    n=keep.sum(axis=0)
    return {'image':mean,'variance':variance,'contributions':n,'geometric_contributions':geom.sum(axis=0),
            'backgrounds':backgrounds,'follow':follow,'n_frames':len(frames),
            'method':'Vecino más próximo, fondo mediano exterior, media inversa de varianza; '+
                     ('rechazo robusto 4σ.' if len(frames)>=3 else 'dos imágenes: sin rechazo de valores atípicos.'),
            'limitation':'Producto exploratorio remuestreado; varianza diagonal sin covarianza de remuestreo ni de fondo. '
                         'No se usa para declarar detección o movimiento.'}


def assess(frames,fov,morphology='both',progress=None):
    log=progress or (lambda msg:None)
    results=[]
    for f in frames:
        log('Evaluando señal, fondo y posiciones de control…')
        results.append(evaluate_frame(f,morphology))
    if not frames:
        return {'method':METHOD,'status':'no_coverage','frames':[]}
    fixed,_,geom=aligned(frames,fov,False)
    common=np.all(np.isfinite(fixed),axis=0)
    field=requested_field(common.shape,fov)
    report={'method':METHOD,'status':'candidate' if any(r['status']=='candidate' for r in results) else
            'predicted' if any(r['status']=='predicted' for r in results) else
            'no_coverage' if all(r['status']=='no_coverage' for r in results) else 'unevaluable',
            'fov_deg':fov,'morphology':morphology,'common_valid_fraction':float(common[field].mean()),
            'common_geometric_fraction':float(np.all(geom,axis=0)[field].mean()),
            'compatible':all(moving_sources.compatible(a.row,b.row) for a in frames for b in frames),
            'frames':[{'observation':f.row,'cutout_url':f.cutout_url,'sha256':f.sha256,
                       'wcs':f.image.wcs.to_header(relax=True).tostring(), 'analysis':r}
                      for f,r in zip(frames,results)],
            'observed_motion':False,
            'motion_reason':'La predicción no es una medida. Sin registro independiente y posiciones medidas '
                            'con incertidumbres verificadas no se declara movimiento observado.'}
    report['stack_allowed']=(len(frames)>=2 and max(f.row['mjd'] for f in frames)-min(f.row['mjd'] for f in frames)<=7
                             and all(moving_sources.compatible(a.row,b.row) for a in frames for b in frames))
    report['joint_signal']=joint_signal(frames,results)
    if any(t.get('candidate') for t in report['joint_signal'].get('tests',[])):
        report['status']='candidate'
    log('Comprobando posiciones medidas y controles del fondo estelar…')
    report['motion'] = measure_motion(frames,results)
    if report['motion']['observed']:
        report.update(status='observed',observed_motion=True,motion_reason=report['motion']['reason'])
    else:
        report['motion_reason']=report['motion']['reason']
    return report


def joint_signal(frames,results):
    """Native matched-position combination for weak sources, without resampling noise.

    Images remain available separately. Empirical offset tracks calibrate the
    variance floor; this can only produce a candidate, never measured motion.
    """
    out={'tests':[],'method':'Combinación inversa de varianza de respuestas nativas siguiendo las predicciones; '
         'controles sobre ocho trayectorias desplazadas, suelo de dispersión empírica.',
         'limitation':'No equivale a fotometría absoluta ni a probabilidad global calibrada de detección.'}
    if (len(frames)<3 or max(f.row['mjd'] for f in frames)-min(f.row['mjd'] for f in frames)>7 or
            not all(moving_sources.compatible(a.row,b.row) for a in frames for b in frames)):
        out['reason']='Se necesitan al menos tres exposiciones compatibles dentro de siete días.'
        return out
    keys={(t['morphology'],0 if t['morphology']=='compact' else round(t.get('radius_arcsec',0),1))
          for r in results for t in r['tests'] if t.get('evaluable')}
    def combine(ms):
        values=np.array([m['response'] for m in ms]);errors=np.array([m['error'] for m in ms])
        median=np.median(values)
        keep=np.abs(values-median)<=4*np.sqrt(errors**2+_mad(values)**2)
        if keep.sum()<3:return None
        w=1/errors[keep]**2
        return float(np.sum(w*values[keep])/w.sum()),float(1/np.sqrt(w.sum())),int(keep.sum())
    for kind,radius in sorted(keys):
        measurements=[next((t for t in r['tests'] if t.get('evaluable') and t['morphology']==kind and
                          (kind=='compact' or round(t['radius_arcsec'],1)==radius)),None) for r in results]
        measurements=[m for m in measurements if m]
        if len(measurements)<3:continue
        combined=combine(measurements)
        if combined is None:continue
        controls=[]
        for index in range(8):
            track=[next((c for c in m['controls'] if c['control_index']==index),None) for m in measurements]
            if all(c is not None for c in track):
                v=combine(track)
                if v:controls.append(v[0])
        amplitude,err,count=combined
        floor=max(err,_mad(np.array(controls))) if len(controls)>=4 else np.inf
        snr=amplitude/floor
        out['tests'].append({'morphology':kind,'radius_arcsec':None if kind=='compact' else radius,'response':amplitude,
            'formal_error':err,'calibrated_error':floor if np.isfinite(floor) else None,
            'snr':snr,'contributions':count,'control_responses':controls,
            'candidate':bool(len(controls)>=4 and snr>=6 and amplitude>max(controls)+2*floor)})
    return out


def _compact_position(img,x,y):
    """Shared ePSF primitive only, independently gated for this morphology.

    Neither the stellar seasons/detector nor its thresholds are changed. A diffuse
    aperture response never enters this astrometric test.
    """
    if img.meta.get('FINAST')!=0:
        return None
    psf=motion.psf_for(img,x,y)
    fit=motion.fit_psf(img.image-img.zodi,img.variance,img.valid(),psf,x,y,max_shift=2.)
    if (not fit or fit['snr']<8 or fit['chi2_red']>3 or fit['n_masked_core'] or
            not fit['converged']):
        return None
    ra,dec=img.wcs.all_pix2world(fit['x'],fit['y'],0)
    # Conservative native-pixel floor; no subpixel precision claim for this prototype.
    err=max(pixel_scale(img),pixel_scale(img)*math.sqrt(np.max(np.linalg.eigvalsh(fit['cov_px']))))
    return {'ra':float(ra),'dec':float(dec),'error_arcsec':err,'fit':fit}


def measure_motion(frames,results):
    out={'observed':False,'positions':[],'controls':[],
         'reason':'Sin dos posiciones compactas medidas y controles estacionarios comunes, el movimiento no está demostrado.'}
    for f,result in zip(frames,results):
        compact=next((r for r in result['tests'] if r['morphology']=='compact'),{})
        stars=f.row.get('stellar_context',{})
        confused=any(s['separation_arcsec']<12 for s in stars.get('nearby',[]))
        p=_compact_position(f.image,*target_pixel(f)) if compact.get('candidate') and not confused else None
        out['positions'].append(p)
    chosen=[i for i,p in enumerate(out['positions']) if p]
    if len(chosen)<2:
        return out
    ia,ib=chosen[0],chosen[-1]
    a,b=frames[ia],frames[ib]
    if not moving_sources.compatible(a.row,b.row):
        out['reason']='Las dos posiciones no pertenecen a bandas y calibraciones compatibles.';return out
    pa,pb=out['positions'][ia],out['positions'][ib]
    for origin,other,measured in ((a,b,pa),(b,a,pb)):
        x,y=world_to_pixel(other.image.wcs,measured['ra'],measured['dec'])
        if inside(other.image,float(x),float(y)):
            old=_compact_position(other.image,float(x),float(y))
            separation=SkyCoord(pa['ra']*u.deg,pa['dec']*u.deg).separation(SkyCoord(pb['ra']*u.deg,pb['dec']*u.deg)).arcsec
            if old and separation>3*pixel_scale(other.image):
                out['reason']='Persiste una fuente en la misma posición del cielo: posible contaminación estelar.'
                return out
    # Match isolated image sources in sky coordinates. Predictions only EXCLUDE
    # the target zone; they do not set the measured shift or registration.
    sources=motion.detect_sources(a.image,threshold=12)[:60]
    controls=[]
    for s in sources:
        sep=min(SkyCoord(s['ra']*u.deg,s['dec']*u.deg).separation(
            SkyCoord(f.prediction['ra']*u.deg,f.prediction['dec']*u.deg)).arcsec for f in (a,b))
        if sep<120:
            continue
        if any(t is not s and math.hypot(t['x']-s['x'],t['y']-s['y'])<4 for t in sources):
            continue
        x,y=world_to_pixel(b.image.wcs,s['ra'],s['dec'])
        if not inside(b.image,float(x),float(y)):
            continue
        c1=_compact_position(a.image,s['x'],s['y']);c2=_compact_position(b.image,float(x),float(y))
        if not c1 or not c2:
            continue
        dx,dy=gnomonic(c2['ra'],c2['dec'],c1['ra'],c1['dec'])
        controls.append([float(dx*3600),float(dy*3600)])
        if len(controls)>=12:
            break
    out['controls']=controls
    if len(controls)<4:
        out['reason']='No hay cuatro estrellas comunes medibles para verificar el registro; se conserva la señal como candidata.'
        return out
    c=np.array(controls);shift=np.median(c,axis=0)
    residual=c-shift
    control_radius=float(np.max(np.linalg.norm(residual,axis=1)))
    if control_radius>2*max(pixel_scale(a.image),pixel_scale(b.image)):
        out['reason']='Registro inconsistente entre las estrellas de control.';return out
    dx,dy=gnomonic(pb['ra'],pb['dec'],pa['ra'],pa['dec'])
    disp=np.array([dx*3600,dy*3600])-shift
    err=math.sqrt(pa['error_arcsec']**2+pb['error_arcsec']**2+control_radius**2)
    sig=float(np.linalg.norm(disp)/err)
    out.update(registration_arcsec=shift.tolist(),control_radius_arcsec=control_radius,
               measured_displacement_arcsec=disp.tolist(),error_arcsec=err,significance=sig,
               observed=bool(sig>=5 and np.linalg.norm(disp)>3*control_radius),
               reason='Desplazamiento medido de una respuesta compacta, tras registro con estrellas comunes.' if sig>=5 and
                    np.linalg.norm(disp)>3*control_radius else 'Desplazamiento no significativo frente a los controles y errores.')
    return out
