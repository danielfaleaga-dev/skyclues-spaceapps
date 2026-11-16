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

METHOD = 'non-sidereal 1.1'
#: Flags ignored ONLY where the target itself is measured. The Level-2 pipeline marks as OUTLIER
#: ("Pixel flagged by Detect Outliers") compact sources that are not in its reference catalogue
#: (SOURCE = "Pixel mapped to a known source"): a moving body is, by construction, such a source.
#: With the strict mask its own core is removed and nothing can be measured. Background, controls'
#: sky and stationary stars keep the strict mask; the number of OUTLIER pixels used is reported.
TARGET_IGNORED_FLAGS = {'OUTLIER'}
SEARCH_PX = 2.5                 # the fit starts at the prediction and may move this far (native px)
MIN_POSITION_SNR = 8.
POSITION_FLOOR_PX = {'compact': .3, 'extended': .5, 'saturated': 1.}   # undersampled PSF: no finer claim
MIN_WING_SNR = 30.              # a saturated or masked core is measured from the PSF wings only if this bright
MIN_SEPARATION_PX = 3.          # closer positions cannot be told apart from one stationary source
MIN_SHIFT_PX = 2.               # an observed displacement never rests on sub-pixel precision
ABSENT_FRACTION = .5            # "gone": less than half the flux, at 3 sigma
MIN_COMMON_STARS = 4
LABELS = {'predicted': 'Predicted position', 'candidate': 'Candidate signal',
          'observed': 'Motion observed', 'unevaluable': 'Not evaluable', 'no_coverage': 'No coverage'}
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


def target_valid(img):
    """Usable pixels for measuring the moving target (strict mask, OUTLIER allowed)."""
    return img.valid(('unusable','artifact'),TARGET_IGNORED_FLAGS)


def inside(img,x,y):
    ny,nx = img.image.shape
    return np.isfinite(x+y) and -.5<=x<nx-.5 and -.5<=y<ny-.5


def fetch_frames(identity, rows, fov, progress=None):
    if not 0.05 <= fov <= .5 or not 1 <= len(rows) <= 8:
        raise ValueError('FOV or number of exposures out of bounds.')
    log = progress or (lambda message: None)
    frames, failures = [], []
    for n,row in enumerate(rows):
        try:
            log(f'Computing the position for exposure {n+1} of {len(rows)}…')
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
                raise ValueError('FITS and metadata identify different exposures.')
            mjd = float(img.meta['MJD-AVG'])
            if abs(mjd-row['mjd'])*86400 > 2:
                raise ValueError('The FITS date does not match the per-exposure prediction.')
            f = MovingFrame({**row, 'mjd':mjd,'context_deg':size},img,path,url,archive.sha256(path))
            x,y = target_pixel(f)
            f.row['prediction_inside'] = bool(inside(img,x,y))
            if inside(img,x,y):
                ix,iy = int(np.clip(round(x),0,img.shape[1]-1)),int(np.clip(round(y),0,img.shape[0]-1))
                f.row.update(lambda_um=float(img.wavelength_um[iy,ix]),
                             bandwidth_um=float(img.bandwidth_um[iy,ix]))
            log('Checking nearby background stars…')
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
        return {'evaluable':False,'reason':'position outside coverage'}
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
    finite=np.isfinite(data)&np.isfinite(var)&(var>0)
    ok=img.valid()[y0:y1,x0:x1]&finite                  # sky and controls: strict mask
    ok_ap=target_valid(img)[y0:y1,x0:x1]&finite         # the tested aperture: OUTLIER allowed
    fy,fx=np.mgrid[int(y)-h:int(y)+h+2,int(x)-h:int(x)+h+2]
    fr=np.hypot(fx-x,fy-y)
    expected=int(np.sum(fr<=r))
    coverage=float(np.sum(ap&ok_ap)/max(expected,1))
    expected_ann=int(np.sum((fr>=max(1.6*r,5))&(fr<=max(2.5*r,8))))
    if coverage<.8 or np.sum(ann&ok)<max(30,.65*expected_ann):
        return {'evaluable':False,'coverage':min(coverage,1.),'reason':'aperture or background with insufficient coverage'}
    a=np.stack([np.ones_like(dx),dx/r,dy/r],axis=-1)
    bg=ann&ok
    for _ in range(4):
        beta=np.linalg.lstsq(a[bg],data[bg],rcond=None)[0]
        resid=data-np.einsum('ijk,k->ij',a,beta)
        scatter=max(_mad(resid[bg]),float(np.sqrt(np.median(var[bg]))))
        bg=ann&ok&(np.abs(resid)<3.5*scatter)
        if bg.sum()<30:
            return {'evaluable':False,'reason':'contaminated or insufficient background'}
    cov=np.linalg.pinv(a[bg].T@a[bg])*scatter**2
    support=ap&ok_ap
    noise=np.maximum(var,scatter**2)
    psf_description=None
    if compact:
        psf=motion.psf_for(img,x,y)  # optical model only; stellar motion detector is untouched
        p=psf(dx,dy)
        w=np.where(support,1/np.where(noise>0,noise,1),0.)
        den=float(np.sum(p*p*w))
        if not np.isfinite(den) or den<=0:
            return {'evaluable':False,'reason':'PSF not evaluable'}
        weights=p*w/den
        psf_description=psf.description
    else:
        weights=support.astype(float)
    flux=float(np.sum(np.where(ok_ap,resid,0)*weights))
    sensitivity=np.sum(a*weights[...,None],axis=(0,1))
    err=math.sqrt(float(np.sum(np.where(ok_ap,noise,0)*weights**2)+sensitivity@cov@sensitivity))
    lam=img.wavelength_um[y0:y1,x0:x1][support]
    bw=img.bandwidth_um[y0:y1,x0:x1][support]
    spread=float(np.ptp(lam)/np.median(bw)) if len(lam) else np.inf
    return {'evaluable':bool(spread<=1.),'reason':'' if spread<=1 else 'excessive spectral gradient in the aperture',
            'response':flux,'error':err,'snr':flux/err,'background':float(beta[0]),
            'background_scatter':scatter,'background_pixels':int(bg.sum()),
            'coverage':min(coverage,1.),'spectral_span_bw':spread,'radius_arcsec':radius,
            'psf':psf_description,'x':x,'y':y,'outlier_pixels_used':int(np.sum(support&~ok))}


def evaluate_frame(frame, morphology='both'):
    img=frame.image
    x,y=target_pixel(frame)
    if not inside(img,x,y):
        return {'status':'no_coverage','tests':[],'reason':'The predicted position falls outside the FITS.'}
    from .compare import finast_status
    if str(img.meta.get('L2DQAFLG','')).strip()!='Pass' or finast_status([img.meta.get('FINAST')])=='fail':
        return {'status':'unevaluable','tests':[],'reason':'Official quality control or astrometry not suitable.',
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
            'Excess consistent with the predicted position; identification and motion not yet confirmed.' if candidates else
            'There is not enough evidence of signal against the noise and the controls.' if valid else
            'Mask, background or coverage prevent evaluating the signal.',
            'prediction_xy':[x,y], 'dqa':{k:img.meta.get(k) for k in
              ('L1DQAFLG','L2DQAFLG','FINAST','ASTRONETSOLVED','HE_AIRGLOW_CONT','AURORA_CONT')},
            'stellar_context':frame.row.get('stellar_context',{'unavailable':'Not requested'}),
            'position_measured':None}


def grid(ra,dec,fov,scale=6.15):
    n=int(np.ceil(fov*3600/scale))
    w=WCS(naxis=2)
    w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crval=[ra,dec]
    w.wcs.crpix=[(n+1)/2,(n+1)/2];w.wcs.cdelt=[-scale/3600,scale/3600]
    return w,(n,n)


def track_centre(frames):
    """Sky midpoint between the first and last predicted positions: a fixed-star view centred here
    shows both ends of the track whenever the displacement fits in the field. Display only."""
    a,b=frames[0].prediction,frames[-1].prediction
    mid=SkyCoord(a['ra']*u.deg,a['dec']*u.deg).cartesian+SkyCoord(b['ra']*u.deg,b['dec']*u.deg).cartesian
    c=SkyCoord(mid)
    return float(c.ra.deg),float(c.dec.deg)


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
        raise ValueError('Stacking needs at least two exposures from the same detector, release and band.')
    if max(f.row['mjd'] for f in frames)-min(f.row['mjd'] for f in frames)>7:
        raise ValueError('More than seven days: stability is not assumed in order to combine these exposures.')
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
            'method':'Nearest neighbour, outer median background, inverse-variance mean; '+
                     ('robust 4σ rejection.' if len(frames)>=3 else 'two images: no outlier rejection.'),
            'limitation':'Exploratory resampled product; diagonal variance with no resampling or background covariance. '
                         'It is not used to declare detection or motion.'}


def assess(frames,fov,morphology='both',progress=None):
    log=progress or (lambda msg:None)
    results=[]
    for f in frames:
        log('Evaluating signal, background and control positions…')
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
            'motion_reason':'The prediction is not a measurement. Without independent registration and positions measured '
                            'with verified uncertainties, observed motion is not declared.'}
    report['stack_allowed']=(len(frames)>=2 and max(f.row['mjd'] for f in frames)-min(f.row['mjd'] for f in frames)<=7
                             and all(moving_sources.compatible(a.row,b.row) for a in frames for b in frames))
    report['joint_signal']=joint_signal(frames,results)
    if any(t.get('candidate') for t in report['joint_signal'].get('tests',[])):
        report['status']='candidate'
    log('Checking measured positions and star-field background controls…')
    report['motion'] = measure_motion(frames,results)
    for entry,position in zip(report['frames'],report['motion']['positions']):
        entry['analysis']['position_measured']=position
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
    out={'tests':[],'method':'Inverse-variance combination of native responses following the predictions; '
         'controls over eight displaced trajectories, empirical scatter floor.',
         'limitation':'It is not equivalent to absolute photometry or to a calibrated global detection probability.'}
    if (len(frames)<3 or max(f.row['mjd'] for f in frames)-min(f.row['mjd'] for f in frames)>7 or
            not all(moving_sources.compatible(a.row,b.row) for a in frames for b in frames)):
        out['reason']='At least three compatible exposures within seven days are needed.'
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


# ----------------------------------------------------------------------------- measured motion
# The decision is made from pixels only:
#   1. a position is fitted in every exposure, starting at the prediction (which only locates the test);
#   2. the source must be GONE from that same sky position in another exposure of the same detector,
#      and the other exposure's source must be gone from this one (a star stays, a moving body does not);
#   3. both exposures are registered with stars they share, measured with the same fit;
#   4. the displacement between the two measured positions must be significant and larger than two
#      native pixels and than the scatter of those stars.
# Wavelengths do not have to match: a position is not a brightness. The prediction is compared with
# the measurement only at the end.

def _fit_position(img,x,y,usable,max_shift=SEARCH_PX):
    """Free-position ePSF fit near (x, y); None when nothing measurable is there."""
    flags=getattr(img,'flags',None)
    saturation=None
    if flags is not None and getattr(img,'flag_defs',None) is not None:
        from .quality import SATURATION
        saturation=(flags&img.flag_defs.names_bitmask(SATURATION))!=0
    psf=motion.psf_for(img,x,y)
    fit=motion.fit_psf(img.image-img.zodi,img.variance,usable,psf,x,y,max_shift=max_shift,saturation=saturation)
    if fit is not None:
        fit['psf']=psf.description
    return fit


def _fixed_flux(img,x,y,usable,half=4,wings=False):
    """PSF amplitude and constant sky at a FIXED position (weighted least squares). (flux, error) or None."""
    data,var=img.image-img.zodi,img.variance
    ny,nx=data.shape
    if not np.isfinite(x+y):
        return None
    xi,yi=int(round(x)),int(round(y))
    if xi-half<0 or yi-half<0 or xi+half>=nx or yi+half>=ny:
        return None
    ys,xs=np.mgrid[yi-half:yi+half+1,xi-half:xi+half+1]
    m=usable[ys,xs]&np.isfinite(data[ys,xs])&np.isfinite(var[ys,xs])&(var[ys,xs]>0)
    core=np.hypot(xs-x,ys-y)<=1.5
    if m.sum()<40 or ((core&~m).any() and not wings):      # wings=True: a saturated core is fitted from its wings
        return None
    p=motion.psf_for(img,x,y)(xs[m]-x,ys[m]-y)
    a=np.column_stack([p,np.ones_like(p)])
    w=1/var[ys,xs][m]
    try:
        cov=np.linalg.inv(a.T@(a*w[:,None]))
    except np.linalg.LinAlgError:
        return None
    beta=cov@(a.T@(data[ys,xs][m]*w))
    resid=data[ys,xs][m]-a@beta
    scale=max(1.,float(np.sum(resid**2*w)/max(m.sum()-2,1)))      # never more optimistic than the residuals
    return float(beta[0]),float(math.sqrt(cov[0,0]*scale))


def locate(frame):
    """Where the source IS in this exposure, from its pixels. The prediction only starts the fit."""
    img=frame.image
    out={'measured':False,'obs_id':frame.row.get('obs_id'),'mjd':frame.row.get('mjd')}
    x0,y0=target_pixel(frame)
    if not inside(img,x0,y0):
        return {**out,'reason':'The predicted position falls outside the image.'}
    if img.meta.get('FINAST')!=0:
        return {**out,'reason':'Official astrometry is not fine (FINAST ≠ 0): the position is not measured.'}
    fit=_fit_position(img,x0,y0,target_valid(img))
    if fit is None:
        return {**out,'reason':'No measurable source next to the predicted position (edge, mask or fit with no solution).'}
    if not fit['converged']:
        return {**out,'reason':'The position fit does not converge.','snr':fit['snr']}
    wings=bool(fit['n_masked_core'] or fit['saturated_core'])
    if wings and fit['snr']<MIN_WING_SNR:
        return {**out,'reason':'Saturated or masked core: the fit with the PSF wings is not reliable '
                               f"(S/N {fit['snr']:.1f} < {MIN_WING_SNR:g}, reduced χ² {fit['chi2_red']:.0f}). "
                               'The position is not measured.','snr':fit['snr'],'chi2_red':fit['chi2_red']}
    if fit['snr']<MIN_POSITION_SNR:
        return {**out,'reason':f"Insufficient signal to measure a position (S/N {fit['snr']:.1f} < {MIN_POSITION_SNR:g}).",
                'snr':fit['snr']}
    scale=pixel_scale(img)
    kind='saturated' if wings else 'compact' if fit['chi2_red']<=3 else 'extended'
    fit_err=math.sqrt(float(np.max(np.linalg.eigvalsh(np.array(fit['cov_px'])))))
    ra,dec=img.wcs.all_pix2world(fit['x'],fit['y'],0)
    p=frame.prediction
    east,north=gnomonic(float(ra),float(dec),p['ra'],p['dec'])
    ys,xs=np.indices(img.image.shape)
    core=np.hypot(xs-fit['x'],ys-fit['y'])<=1.5
    strict=img.valid()
    flags=getattr(img,'flags',None)
    known=None
    if flags is not None and getattr(img,'flag_defs',None) is not None:
        known=int(((flags&img.flag_defs.names_bitmask({'SOURCE'}))!=0)[core].sum())
    return {**out,'measured':True,'ra':float(ra),'dec':float(dec),'x':fit['x'],'y':fit['y'],
            'flux':fit['flux'],'flux_err':fit['flux_err'],'snr':fit['snr'],'chi2_red':fit['chi2_red'],
            'morphology':kind,'psf':fit['psf'],
            'error_arcsec':scale*max(POSITION_FLOOR_PX[kind],fit_err),'fit_error_arcsec':scale*fit_err,
            'offset_from_prediction_arcsec':[float(east*3600),float(north*3600)],
            'outlier_pixels_in_core':int((core&~strict&target_valid(img)).sum()),
            'known_source_pixels_in_core':known,'masked_core_pixels':int(fit['n_masked_core']),
            'note':('Saturated or masked core: position measured with the PSF wings, with a minimum error of '
                    'one pixel. ' if wings else '')+'Position measured in the pixels. The prediction only places the search.'}


def _gone(pos,origin,other):
    """Is the source measured in ``origin`` absent from the same sky position in ``other``?"""
    x,y=world_to_pixel(other.image.wcs,pos['ra'],pos['dec'])
    x,y=float(x),float(y)
    here=_fixed_flux(origin.image,pos['x'],pos['y'],target_valid(origin.image),wings=pos['morphology']=='saturated')
    there=_fixed_flux(other.image,x,y,target_valid(other.image)) if inside(other.image,x,y) else None
    if here is None or there is None:
        return {'testable':False,'reason':'The other image does not cover that sky position with valid pixels.'}
    f0,e0=here
    f1,e1=there
    return {'testable':True,'flux_here':f0,'flux_there':f1,'error_there':e1,
            'absent':bool(f1+3*e1<ABSENT_FRACTION*f0),'persistent':bool(f1-3*e1>ABSENT_FRACTION*f0),
            'ratio':f1/f0 if f0>0 else None}


def _common_stars(a,b,exclude):
    """Stars seen in both exposures, fitted with the same ePSF and the STRICT mask: (east, north) of b − a."""
    shifts=[]
    sources=motion.detect_sources(a.image,threshold=12)[:80]
    for s in sources:
        if any(SkyCoord(s['ra']*u.deg,s['dec']*u.deg).separation(SkyCoord(r*u.deg,d*u.deg)).arcsec<40 for r,d in exclude):
            continue
        if any(t is not s and math.hypot(t['x']-s['x'],t['y']-s['y'])<4 for t in sources):
            continue
        x,y=world_to_pixel(b.image.wcs,s['ra'],s['dec'])
        if not inside(b.image,float(x),float(y)):
            continue
        fa=_fit_position(a.image,s['x'],s['y'],a.image.valid(),2.)
        fb=_fit_position(b.image,float(x),float(y),b.image.valid(),2.)
        if not all(f and f['snr']>=8 and f['converged'] and not f['n_masked_core'] for f in (fa,fb)):
            continue
        ra1,dec1=a.image.wcs.all_pix2world(fa['x'],fa['y'],0)
        ra2,dec2=b.image.wcs.all_pix2world(fb['x'],fb['y'],0)
        dx,dy=gnomonic(float(ra2),float(dec2),float(ra1),float(dec1))
        shifts.append([float(dx*3600),float(dy*3600)])
        if len(shifts)>=16:
            break
    return shifts


def measure_motion(frames,results=None):
    """Observed motion of one source between two exposures, or the precise reason why not."""
    positions=[locate(f) for f in frames]
    out={'observed':False,'positions':positions,'controls':[],'pairs':[],'method':METHOD,
         'reason':'Without two positions measured in the pixels, the motion is not demonstrated.'}
    located=[i for i,p in enumerate(positions) if p['measured']]
    if len(located)<2:
        why=[p['reason'] for p in positions if not p['measured']]
        if why:
            out['reason']+=' '+why[0]
        return out
    pairs=[]
    for n,i in enumerate(located):
        for j in located[n+1:]:
            a,b,pa,pb=frames[i],frames[j],positions[i],positions[j]
            sep=SkyCoord(pa['ra']*u.deg,pa['dec']*u.deg).separation(SkyCoord(pb['ra']*u.deg,pb['dec']*u.deg)).arcsec
            pair={'first':i,'second':j,'separation_arcsec':float(sep),'dt_days':float(b.row['mjd']-a.row['mjd']),
                  'same_detector':a.row.get('detector')==b.row.get('detector')}
            scale=max(pixel_scale(a.image),pixel_scale(b.image))
            if not pair['same_detector']:
                pair['status']='Different detectors: brightnesses at the same position are not compared.'
            elif sep<MIN_SEPARATION_PX*scale:
                pair['status']='Positions too close to be told apart from a fixed source.'
            else:
                pair['first_in_second']=_gone(pa,a,b)
                pair['second_in_first']=_gone(pb,b,a)
                t1,t2=pair['first_in_second'],pair['second_in_first']
                if t1.get('persistent') or t2.get('persistent'):
                    pair['status']='A source persists at the same sky position: possible stellar contamination.'
                elif not (t1['testable'] and t2['testable']):
                    pair['status']='No common sky to check that the source is not stationary.'
                elif t1['absent'] and t2['absent']:
                    pair['status']='ok'
                else:
                    pair['status']='The disappearance of the source on the other date is not conclusive.'
            pairs.append(pair)
    out['pairs']=pairs
    good=[p for p in pairs if p['status']=='ok']
    # The longest baseline whose two positions pass the appear/disappear test; otherwise the longest pair
    # is still registered and reported, so a non-detection carries its numbers and its cause.
    chosen=max(good or pairs,key=lambda p:(abs(p['dt_days']),p['separation_arcsec']))
    a,b=frames[chosen['first']],frames[chosen['second']]
    pa,pb=positions[chosen['first']],positions[chosen['second']]
    out['pair']=chosen
    if chosen['status']!='ok':
        out['reason']=chosen['status']
    predictions=[(f.prediction['ra'],f.prediction['dec']) for f in (a,b)]+[(p['ra'],p['dec']) for p in (pa,pb)]
    controls=_common_stars(a,b,predictions)
    out['controls']=controls
    if len(controls)<MIN_COMMON_STARS:
        if chosen['status']=='ok':
            out['reason']=(f'There are not {MIN_COMMON_STARS} measurable common stars to verify the registration; '
                           'the signal is kept as a candidate.')
        return out
    c=np.array(controls)
    shift=np.median(c,axis=0)
    resid=np.linalg.norm(c-shift,axis=1)
    scale=max(pixel_scale(a.image),pixel_scale(b.image))
    keep=resid<=max(3*1.4826*np.median(resid),.5*scale)          # one robust pass: blends and mismatches
    if keep.sum()>=MIN_COMMON_STARS:
        shift=np.median(c[keep],axis=0)
        resid=np.linalg.norm(c[keep]-shift,axis=1)
    control_radius=float(resid.max())
    dx,dy=gnomonic(pb['ra'],pb['dec'],pa['ra'],pa['dec'])
    disp=np.array([dx*3600,dy*3600])-shift
    size=float(np.linalg.norm(disp))
    err=math.sqrt(pa['error_arcsec']**2+pb['error_arcsec']**2+control_radius**2)
    hours=abs(chosen['dt_days'])*24
    out.update(registration_arcsec=shift.tolist(),control_radius_arcsec=control_radius,
               control_stars=int(len(resid)),control_stars_rejected=int((~keep).sum()),
               measured_displacement_arcsec=disp.tolist(),displacement_arcsec=size,error_arcsec=err,
               significance=size/err,interval_hours=hours,
               rate_arcsec_per_hour=size/hours if hours>0 else None,
               position_angle_deg=float(np.degrees(np.arctan2(disp[0],disp[1]))%360))
    px,py=gnomonic(b.prediction['ra'],b.prediction['dec'],a.prediction['ra'],a.prediction['dec'])
    predicted=np.array([px*3600,py*3600])
    out['catalogue_comparison']={
        'predicted_displacement_arcsec':predicted.tolist(),
        'difference_arcsec':float(np.linalg.norm(disp-predicted)),
        'difference_sigma':float(np.linalg.norm(disp-predicted)/err),
        'note':'Later comparison with the ephemeris. It plays no part in the measurement or the decision.'}
    if control_radius>2*scale:
        out['reason']='Inconsistent registration among the control stars.'
        return out
    if chosen['status']!='ok':
        return out
    significant=size/err>=5 and size>3*control_radius and size>=MIN_SHIFT_PX*scale
    out['observed']=bool(significant)
    out['reason']=('The source appears at its position in each image and has disappeared from it in the other; the '
                   'displacement was measured in the pixels after registering both images with common stars.'
                   if significant else 'Displacement not significant against the controls and errors.')
    return out
