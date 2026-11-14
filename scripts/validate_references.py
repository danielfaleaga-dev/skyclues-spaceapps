"""Small real-service audit: Gaia cones, AllWISE centre tiles, independent astrometry.

Run from the repository: python scripts/validate_references.py
No FITS downloads; no original scientific files are modified.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import astropy.units as u
from astropy.coordinates import SkyCoord, Distance
from astropy.time import Time
from astropy_healpix import HEALPix
import numpy as np
from PIL import Image
import requests

from skyclues import config, references as ref
from skyclues.spectral_cube import healpix_nest

FIELDS = {"m101": (210.802429, 54.34875, .1), "wise0855": (133.760100, -7.242247, .1),
          "barnard": (269.4485, 4.7394, .05)}


def validate():
    report = {"validated_utc": datetime.now(timezone.utc).isoformat(), "fields": {}, "wise": []}
    for name, (ra, dec, fov) in FIELDS.items():
        result = ref.fetch_gaia(ra, dec, fov)
        sources = result["sources"]
        assert sources
        coords = SkyCoord([s['ra'] for s in sources]*u.deg, [s['dec'] for s in sources]*u.deg)
        sep = coords.separation(SkyCoord(ra*u.deg, dec*u.deg)).deg
        assert np.max(sep) <= fov / 2 + 1e-9
        report['fields'][name] = {k:v for k,v in result.items() if k != 'sources'}
        report['fields'][name].update(count=len(sources), max_separation_deg=float(np.max(sep)),
                                      sample=sources[0])
        if name == 'barnard':
            s = next(s for s in sources if s['source_id']=='4472832130942575872')
            basic=dict(ra=s['ra']*u.deg,dec=s['dec']*u.deg,pm_ra_cosdec=s['pmra']*u.mas/u.yr,
                       pm_dec=s['pmdec']*u.mas/u.yr,obstime=Time(2016,format='jyear',scale='tcb'))
            epoch=Time(2026,format='jyear',scale='tcb')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                angular=SkyCoord(**basic).apply_space_motion(new_obstime=epoch)
            spatial=SkyCoord(**basic,distance=Distance(parallax=s['parallax']*u.mas),
                             radial_velocity=s['radial_velocity']*u.km/u.s).apply_space_motion(new_obstime=epoch)
            calculated=SkyCoord(*ref.expected_position(s,2026),unit='deg')
            difference=calculated.separation(angular).arcsec
            assert difference < .0001
            report['high_pm']={'source':s,'epoch':2026.0,'calculated':ref.expected_position(s,2026),
                'motion_arcsec':float(calculated.separation(SkyCoord(**basic)).arcsec),
                'angular_oracle_error_arcsec':float(difference),
                'difference_from_3d_arcsec':float(calculated.separation(spatial).arcsec),
                'limitation':'Approximate angular motion; excludes perspective acceleration, observer parallax and covariance.'}
        else:
            ipix=int(healpix_nest(8,ra,dec))
            assert ipix==int(HEALPix(nside=256,order='nested',frame='icrs').skycoord_to_healpix(SkyCoord(ra*u.deg,dec*u.deg)))
            for band, base in ref.WISE_URLS.items():
                p=requests.get(base+'/properties',timeout=(8,25));p.raise_for_status()
                properties=dict(line.split('=',1) for line in p.text.splitlines() if '=' in line and not line.startswith('#'))
                properties={k.strip():v.strip() for k,v in properties.items()}
                assert properties['hips_frame']=='equatorial' and properties['hips_order']=='8'
                assert 'jpeg' in properties['hips_tile_format']
                url=f'{base}/Norder8/Dir{ipix//10000*10000}/Npix{ipix}.jpg'
                r=requests.get(url,timeout=(8,25));r.raise_for_status()
                assert len(r.content)<2**20
                im=Image.open(io.BytesIO(r.content));im.load()
                assert im.size==(512,512) and np.std(np.asarray(im))>0
                report['wise'].append({'field':name,'band':band,'url':url,'bytes':len(r.content),
                    'sha256':hashlib.sha256(r.content).hexdigest(),'dimensions':im.size,
                    'properties_sha256':hashlib.sha256(p.content).hexdigest(),
                    'title':properties['obs_title'],'hips_order':8,'frame':'equatorial'})
        print(name,len(sources),'sources',result['response_bytes'],'bytes',flush=True)
    path=config.RESULTS_DIR/'references_validation.json'
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(path,flush=True)
    return report


if __name__=='__main__':
    validate()
