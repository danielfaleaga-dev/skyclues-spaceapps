"""Synthetic algorithm tests. These are NOT evidence of astronomical detections."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.wcs import WCS

from skyclues import non_sidereal as n, moving_sources as s, motion


@pytest.fixture(autouse=True)
def synthetic_psf(monkeypatch):
    monkeypatch.setattr(motion,'psf_for',lambda *a:motion.PSF(None,sigma_px=1.,description='SYNTHETIC Gaussian'))


def frame(shift=0,seed=1,flux=4000,wcs_error=0,stars=True,extended=False):
    size=181
    w=WCS(naxis=2);w.wcs.ctype=['RA---TAN','DEC--TAN'];w.wcs.crval=[150,10]
    w.wcs.crpix=[91+wcs_error,91];w.wcs.cdelt=[-6.15/3600,6.15/3600]
    yy,xx=np.indices((size,size));rng=np.random.default_rng(seed)
    data=rng.normal(0,1,(size,size))+10+.01*xx+.015*yy
    sigma=4 if extended else 1
    data+=flux/(2*np.pi*sigma*sigma)*np.exp(-((xx-90-shift)**2+(yy-90)**2)/(2*sigma*sigma))
    if stars:
        for x,y in [(35,35),(75,35),(120,35),(145,65),(145,125),(115,145),(60,140),(30,110)]:
            data+=3000/(2*np.pi)*np.exp(-((xx-x)**2+(yy-y)**2)/2)
    img=SimpleNamespace(image=data,zodi=np.zeros_like(data),variance=np.ones_like(data),wcs=w,
                        wavelength_um=np.full_like(data,1.25),bandwidth_um=np.full_like(data,.03),
                        meta={'L2DQAFLG':'Pass','FINAST':0,'PSF_FWHM':14.5},shape=data.shape)
    img.mask=np.ones_like(data,dtype=bool);img.valid=lambda *a:img.mask
    ra,dec=w.all_pix2world(90+shift,90,0)
    row={'obs_id':f'SYNTHETIC-{seed}','detector':2,'collection':'SYNTHETIC','version':'1',
         'lambda_um':1.25,'bandwidth_um':.03,'mjd':60000+seed*.01,
         'prediction':{'ra':float(ra),'dec':float(dec),'refined':True,'source':'SYNTHETIC'}}
    return n.MovingFrame(row,img,Path('synthetic'),'synthetic://','not-a-real-fits')


def test_compact_extended_and_controls():
    f=frame(stars=False)
    r=n.evaluate_frame(f)
    assert r['status']=='candidate'
    assert r['tests'][0]['candidate'] and r['tests'][0]['psf']=='SYNTHETIC Gaussian'
    e=n.evaluate_frame(frame(extended=True,stars=False))
    assert any(t['candidate'] for t in e['tests'] if t['morphology']=='extended')
    assert all(len(t['controls'])>=4 for t in r['tests'] if t['candidate'])


@pytest.mark.parametrize('noise_seed',[4,7,12])
def test_weak_signal_is_not_detection(noise_seed):
    f=frame(flux=0,seed=noise_seed,stars=False)
    r=n.assess([f],.1)
    assert r['status']=='predicted' and not r['observed_motion']


def test_masks_nan_bad_variance_and_quality():
    f=frame(stars=False)
    f.image.mask[85:96,85:96]=False
    f.image.image[85:96,85:96]=np.nan
    f.image.variance[30:50]=np.nan
    r=n.evaluate_frame(f)
    assert not r['tests'][0]['evaluable']
    f.image.meta['L2DQAFLG']='Fail'
    assert n.evaluate_frame(f)['status']=='unevaluable'


def test_partial_and_no_coverage_do_not_become_black():
    f=frame()
    p=f.prediction
    w,shape=n.grid(p['ra']+.15,p['dec'],.3)
    data,var,c=n.resample(f,w,shape)
    assert 0<c.mean()<1
    assert np.isnan(data[~c]).all() and np.isnan(var[~c]).all()
    f.row['prediction']['ra']+=5
    assert n.evaluate_frame(f)['status']=='no_coverage'
    assert n.assess([f],.1)['status']=='no_coverage'


@pytest.mark.parametrize('key,value',[('detector',5),('collection','OTHER'),('version','2'),('lambda_um',1.3)])
def test_mixed_bands_and_releases_rejected(key,value):
    a,b=frame(),frame(seed=2)
    b.row[key]=value
    with pytest.raises(ValueError):n.stack([a,b],.1)


def test_stack_tracks_known_motion_and_preserves_counts():
    fs=[frame(shift=s,seed=i+1,stars=False,flux=100) for i,s in enumerate([-8,0,8])]
    a=n.stack(fs,.1,True);b=n.stack(fs,.1,False)
    cy,cx=np.array(a['image'].shape)//2
    assert np.nanmax(a['image'][cy-2:cy+3,cx-2:cx+3])>np.nanmax(b['image'])*1.4
    assert a['contributions'].max()==3
    assert np.isnan(a['image'][a['contributions']==0]).all()


def test_no_common_overlap_is_not_observed_motion():
    a,b=frame(),frame(seed=2)
    b.image.wcs.wcs.crval[0]+=3;b.row['prediction']['ra']+=3
    r=n.assess([a,b],.1)
    assert r['common_valid_fraction']==0 and not r['observed_motion']


def test_measured_motion_and_stationary_control():
    a,b=frame(shift=-12),frame(shift=12,seed=2)
    r=n.assess([a,b],.2)
    assert r['observed_motion'],r['motion']
    assert abs(np.linalg.norm(r['motion']['measured_displacement_arcsec'])-24*6.15)<4
    r=n.assess([frame(),frame(seed=2)],.2)
    assert not r['observed_motion']


def test_wcs_error_only_is_removed_by_independent_stars():
    a,b=frame(),frame(seed=2,wcs_error=1.5)
    r=n.assess([a,b],.2)
    assert not r['observed_motion']
    assert np.linalg.norm(r['motion']['measured_displacement_arcsec'])<4


def test_contaminating_stationary_sources_prevent_motion_claim():
    a,b=frame(shift=-12),frame(shift=12,seed=2)
    yy,xx=np.indices(b.image.shape)
    b.image.image+=4000/(2*np.pi)*np.exp(-((xx-78)**2+(yy-90)**2)/2)
    r=n.assess([a,b],.2)
    assert not r['observed_motion'] and 'contaminación' in r['motion_reason']


def test_prediction_does_not_supply_measured_displacement():
    a,b=frame(),frame(seed=2)
    # Move only the prediction to empty sky, not the pixels.
    b.row['prediction']['ra']+=.03
    r=n.assess([a,b],.2)
    assert not r['observed_motion']


def test_groups_are_pairwise_compatible():
    rows=[]
    for i,lam in enumerate([1.,1.006,1.012]):
        r=deepcopy(frame().row);r.update(url=f'synthetic://{i}',lambda_um=lam,margin_px=20)
        rows.append(r)
    assert all(all(s.compatible(a,b) for a in group for b in group) for group in s.groups(rows,.9,1.5))


def test_invalid_identity_and_time_ranges():
    with pytest.raises(ValueError):s.discover({'spkid':'wrong'},'2025-01-01','2025-01-02')
    with pytest.raises(ValueError):s.discover({'spkid':'999'},'2025-01-01','2027-01-01')
    with pytest.raises(ValueError):s.discover({'spkid':'999'},'2025-01-01','2025-01-02',step_days=0)


def test_missing_observer_orbit_is_service_limit_not_empty_sky():
    with pytest.raises(s.solar_system.ServiceError,match='cobertura orbital'):
        s.parse_most(b'MOST: ephem_step reset to the time range: -15.500000 day.')
    assert len(s.parse_most(b'No matching images found'))==0


def test_variable_plane_background_does_not_create_signal():
    f=frame(flux=0,stars=False)
    before=n.evaluate_frame(f)
    yy,xx=np.indices(f.image.shape)
    f.image.image+=300+2*xx-3*yy
    after=n.evaluate_frame(f)
    assert after['status']=='predicted'
    assert after['tests'][0]['response']==pytest.approx(before['tests'][0]['response'],abs=1e-6)


def test_sip_nonconvergence_is_missing_coverage():
    from astropy.wcs import NoConvergence
    class BadWCS:
        def all_world2pix(self,*args):
            raise NoConvergence('synthetic divergent coordinate',best_solution=np.array([[1.,2.],[3.,4.]]),
                                accuracy=np.ones((2,2)),niter=20,divergent=np.array([1]),slow_conv=None)
    x,y=n.world_to_pixel(BadWCS(),[150.,170.],[10.,10.])
    assert x[0]==1 and y[0]==2 and np.isnan(x[1]) and np.isnan(y[1])


def test_cached_reference_keeps_each_exposure_time(monkeypatch):
    import io
    from astropy.table import Table
    from astropy.time import Time
    row=frame().row;row.update(mjd_start=60000,mjd_end=60000.001,mjd=60000.0005)
    prediction=deepcopy(row['prediction']);prediction.pop('refined')
    row['prediction']=prediction
    calls=[]
    def query(identity,start,end,**kw):
        calls.append((start,end,kw))
        r=deepcopy(row);r['prediction'].update(ra=155.,dec=11.)
        return {'rows':[r],'provenance':{'source':'SIMULATED'},
                'workspace_url':'https://irsa.ipac.caltech.edu/workspace/SYNTHETIC'}
    monkeypatch.setattr(s,'discover',query)
    times=[Time(row['mjd']+v/86400,format='mjd').datetime.strftime('%Y-%b-%d %H:%M:%S.%f') for v in [-.5,.5]]
    tab=Table({'Date':times,'RA_obs':[154.999,155.001],'Dec_obs':[11.,11.],'segment':[0,0]})
    buf=io.StringIO();tab.write(buf,format='ascii.ipac')
    monkeypatch.setattr(s,'_request',lambda url,**kw:(buf.getvalue().encode(),{'url':url}))
    out=s.refine_prediction({'spkid':'999'},row)
    assert out['prediction']['ra']==pytest.approx(155,abs=1e-6) and out['prediction']['mjd']==row['mjd']
    assert out['prediction']['refined'] and calls[0][2]['step_days']==1/86400
    assert out['prediction']['sample_gap_s']==pytest.approx(1,abs=1e-5)
    assert 'punto medio' in out['prediction']['time_basis']


def test_track_ra_wrap_and_no_extrapolation_or_coarse_gap():
    from astropy.table import Table
    from astropy.time import Time
    tab=Table({'Date':['2025-Aug-01 00:00:00.000','2025-Aug-01 00:00:01.000'],
               'RA_obs':[359.999,.001],'Dec_obs':[0.,0.],'segment':[0,0]})
    mid=Time('2025-08-01T00:00:00.500').mjd
    p=s.track_position(tab,mid)
    assert min(p['ra'],360-p['ra'])<1e-6
    with pytest.raises(s.solar_system.ServiceError):s.track_position(tab,mid+1)
    tab['segment'][1]=1
    with pytest.raises(s.solar_system.ServiceError):s.track_position(tab,mid)
    tab['segment'][1]=0;tab['Date'][1]='2025-Aug-01 00:01:00.000'
    with pytest.raises(s.solar_system.ServiceError):s.track_position(tab,mid)


def test_fits_dates_and_identity_verified(monkeypatch,tmp_path):
    f=frame();f.image.meta.update(DETECTOR=2,OBSID='WRONG',**{'MJD-AVG':f.row['mjd']})
    row=f.row;row['url']='https://irsa.ipac.caltech.edu/example.fits'
    monkeypatch.setattr(n.archive,'fetch',lambda u:tmp_path/'fixture.fits')
    monkeypatch.setattr(n.fitsdata,'load',lambda p:f.image)
    frames,fail=n.fetch_frames({'spkid':'999'},[row],.1)
    assert not frames and 'diferentes' in fail[0]['error']
    f.image.meta.update(OBSID=row['obs_id'],**{'MJD-AVG':f.row['mjd']+1})
    frames,fail=n.fetch_frames({'spkid':'999'},[row],.1)
    assert not frames and 'fecha' in fail[0]['error']


def test_joint_native_weak_signal_and_negative_tracks():
    fs=[frame(shift=2*i-7,seed=20+i,flux=12,stars=False) for i in range(8)]
    rs=[n.evaluate_frame(f,'compact') for f in fs]
    assert not any(r['tests'][0]['candidate'] for r in rs)
    joint=n.joint_signal(fs,rs)
    assert any(t['candidate'] for t in joint['tests']),joint
    blank=[frame(shift=2*i-7,seed=50+i,flux=0,stars=False) for i in range(8)]
    assert not any(t['candidate'] for t in n.joint_signal(blank,[n.evaluate_frame(f,'compact') for f in blank])['tests'])
