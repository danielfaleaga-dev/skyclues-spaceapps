"""Bounded IRSA audit and independent tutorial photometry; writes JSON evidence.

Run with requirements-dev installed. No full cube download; no original FITS edits.
The tutorial's 5/40/60 pixel aperture is evaluated independently with Photutils.
The production sky aperture is also checked with a brute-force SkyCoord oracle.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.stats import SigmaClip, sigma_clipped_stats
from photutils.aperture import CircularAperture, CircularAnnulus, ApertureStats, aperture_photometry
from skyclues import config, spectral_cube as sc

RA, DEC = 60.8109955, 51.3404038


def tutorial_photometry(tile, radii):
    """Tutorial formula using Photutils exact overlaps, independent of extract_spectrum."""
    x,y=map(float,tile.wcs.world_to_pixel_values(RA,DEC))
    outer=int(np.ceil(radii[2]))+2
    x0,x1=max(0,int(x)-outer),min(511,int(x)+outer)
    y0,y1=max(0,int(y)-outer),min(511,int(y)+outer)
    data=tile.read_rows({'IMAGE':list(range(102))},y0,y1,x0,x1)['IMAGE']
    pos=(x-x0,y-y0)
    ap=CircularAperture(pos,r=radii[0])
    ann=CircularAnnulus(pos,r_in=radii[1],r_out=radii[2])
    c0,c1,c2=tile.wcs.pixel_to_world([x,x+1,x],[y,y,y+1])
    dx1,dy1=c0.spherical_offsets_to(c1)
    dx2,dy2=c0.spherical_offsets_to(c2)
    omega=abs(dx1*dy2-dx2*dy1).to_value(u.sr)
    flux=[]
    for i,img in enumerate(data):
        if i in [50,51]: flux.append(None); continue
        bg=float(ApertureStats(img,ann,sigma_clip=SigmaClip(sigma=3,maxiters=10)).mean)
        total=float(aperture_photometry(img,ap)['aperture_sum'][0])
        flux.append((total-bg*float(ap.area_overlap(img)))*omega*1e9)
    return flux,omega,hashlib.sha256(data.tobytes()).hexdigest()


def sky_oracle(tile, radii=(2,4,7)):
    """All subpixels via Astropy separation, no production geometry/weight helpers."""
    x,y=map(float,tile.wcs.world_to_pixel_values(RA,DEC))
    x0,y0=int(x)-12,int(y)-12
    yy,xx=np.mgrid[y0:y0+25,x0:x0+25]
    centre=SkyCoord(RA*u.deg,DEC*u.deg)
    scale=tile.pixel_scale_arcsec
    distance=centre.separation(tile.wcs.pixel_to_world(xx,yy)).arcsec/scale
    ann=(distance>=radii[1])&(distance<radii[2])
    weights=np.zeros_like(distance)
    for dx in [-.4,-.2,0,.2,.4]:
        for dy in [-.4,-.2,0,.2,.4]:
            weights += (centre.separation(tile.wcs.pixel_to_world(xx+dx,yy+dy)).arcsec/scale<radii[0])/25
    data=tile.read_rows({'IMAGE':list(range(102))},y0,y0+24,x0,x0+24)['IMAGE']
    flux=[]
    for p,img in enumerate(data):
        if p in [50,51] or not np.isfinite(img[weights>0]).all(): flux.append(None); continue
        bg=float(sigma_clipped_stats(img[ann],sigma=3,maxiters=10)[0])
        flux.append(float(np.sum((img[weights>0].astype(float)-bg)*weights[weights>0])*tile.pixel_solid_angle_sr*1e9))
    return flux


def audit():
    out={'position_icrs_deg':[RA,DEC], 'tutorial_url':config.CUBE_TUTORIAL_URL,
         'limitations':['Exploratory, no flux uncertainty or aperture correction.',
                         'Sky circles differ from tutorial pixel circles; no claim of identical photometry.']}
    sc.io_stats(reset=True)
    tile=sc.open_tile(445,refresh=True)
    out['layout_io']=sc.io_stats(reset=True)
    out['provenance']=tile.provenance()
    props=sc.hips_properties()
    waves=np.array([c.wavelength_um for c in tile.channels])
    official=np.fromstring(props['data_cube_crval3_arr'].strip('[]'),sep=' ')
    if official.size!=102:
        official=np.fromstring(props['data_cube_crval3_arr'].strip('[]'),sep=',')
    np.testing.assert_allclose(waves,official,rtol=1e-6)
    out['wavelength_max_difference_um']=float(np.max(np.abs(waves-official)))
    tracemalloc.start()
    start=time.perf_counter()
    m=sc.channel_map(RA,DEC,.1,62)
    out['map_io']=sc.io_stats(reset=True)
    out['map_summary']=m.summary()
    spec=sc.extract_spectrum(RA,DEC)
    out['spectrum_io']=sc.io_stats(reset=True)
    out['elapsed_map_and_spectrum_s']=time.perf_counter()-start
    out['python_peak_bytes']=tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert out['python_peak_bytes'] < 100*2**20
    assert out['spectrum_io']['bytes_network']+out['spectrum_io']['bytes_cache'] < 12*2**20
    sc.extract_spectrum(RA,DEC)
    out['repeat_spectrum_io']=sc.io_stats(reset=True)
    assert out['repeat_spectrum_io']['requests']==0
    for p in [50,51,62]:
        d=tile.read_rows({e:[p] for e in sc.CUBE_EXTENSIONS},190,230,215,260)
        assert np.array_equal(np.isnan(d['IMAGE']),d['NHITS']==0)
        if p in [50,51]: assert np.isnan(d['IMAGE']).all()
    ref=sky_oracle(tile)
    diffs=[abs(r['flujo_mjy']-f) for r,f in zip(spec.rows,ref) if r['flujo_mjy'] is not None and f is not None]
    out['sky_oracle_max_abs_difference_mjy']=max(diffs)
    assert max(diffs)<.001
    compact,omega,_=tutorial_photometry(tile,(2,4,7))
    tutorial,omega,sha=tutorial_photometry(tile,(5,40,60))
    out['tutorial_radii_px']=[5,40,60]
    out['tutorial_local_solid_angle_sr']=omega
    out['healpix_solid_angle_sr']=tile.pixel_solid_angle_sr
    assert abs(omega/tile.pixel_solid_angle_sr-1)<.001
    out['tutorial_cutout_sha256']=sha
    out['channels']=[dict(row,independent_sky_mjy=ref[i],photutils_compact_mjy=compact[i],
                          tutorial_5_40_60_mjy=tutorial[i]) for i,row in enumerate(spec.rows)]
    # A local maximum is a smoke check only; the independent numerical checks above are decisive.
    assert spec.rows[62]['flujo_mjy']>max(spec.rows[61]['flujo_mjy'],spec.rows[63]['flujo_mjy'])
    assert tutorial[62]>max(tutorial[61],tutorial[63])
    # Verify HEALPix/WCS routing independently on real polar tiles (headers only).
    out['polar_tiles']=[]
    for ra,dec in [(30,89),(210,-89)]:
        t=sc.tile_for(ra,dec)
        x,y=map(float,t.wcs.world_to_pixel_values(ra,dec))
        assert -.5<=x<511.5 and -.5<=y<511.5
        out['polar_tiles'].append({'ra':ra,'dec':dec,'npix':t.ipix,'x':x,'y':y})
    out['validation_io']=sc.io_stats(reset=True)
    return out


if __name__=='__main__':
    result=audit()
    path=config.RESULTS_DIR/'spectrum_validation.json'
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='channels'},indent=2))
    print('Channel 63:',result['channels'][62])
