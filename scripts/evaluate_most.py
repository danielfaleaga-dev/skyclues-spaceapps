"""Live, bounded MOST evaluation. Metadata only; never downloads full FITS.

Run from the repository: python scripts/evaluate_most.py
The cached FITS validation is separately reproduced by validate_moving.py.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
from skyclues import moving_sources as s, solar_system

ROOT = Path('results/moving')


def key(row):
    return str(row['observationid']), int(s.archive._FILE_RE.search(str(row['uri']))['det'])


def separation(a, b):
    return float(SkyCoord(a[0]*u.deg,a[1]*u.deg).separation(SkyCoord(b[0]*u.deg,b[1]*u.deg)).arcsec)


def query(sid, start, end, step, mode='Brief', refresh=True):
    params={'catalog':'spherex','input_type':'naifid_input','obj_naifid':sid,
            'obs_begin':Time(start).strftime('%Y %m %d %H:%M:%S'),
            'obs_end':Time(end).strftime('%Y %m %d %H:%M:%S'),'output_mode':mode}
    if step is not None: params['ephem_step']=str(step)
    t=perf_counter()
    raw,p=s._request(s.MOST,params,refresh=refresh)
    meta={'elapsed_s':perf_counter()-t,'bytes':len(raw),'provenance':p,'requested_step_days':step}
    if mode!='Brief': return raw,meta
    tab=s.parse_most(raw)
    meta.update(rows=len(tab),columns=tab.colnames)
    return tab,meta


def main():
    refs=s.published_predictions(solar_system.ATLAS_TABLE)
    out={'reference':next(iter(refs.values()))['provenance'],'queries':[],'precise_crosschecks':[]}
    tables={}
    for name,sid,start,end,step in [
        ('atlas_default','1004083','2025-08-01','2025-08-16',None),
        ('atlas_002','1004083','2025-08-01','2025-08-16',.02),
        ('atlas_0005','1004083','2025-08-01','2025-08-16',.005),
        ('vesta_default','20000004','2025-08-01','2025-08-31',None),
        ('vesta_002','20000004','2025-08-01','2025-08-31',.02),
        ('atlas_dec','1004083','2025-12-01','2025-12-20',.02),
        ('pluto_year','999','2025-04-10','2026-04-10',.02),
    ]:
        tab,meta=query(sid,start,end,step)
        tables[name]=tab
        bykey={key(r):r for r in tab}
        if sid=='1004083':
            relevant={k:p for k,p in refs.items() if Time(start).mjd<=p['mjd_start']<Time(end).mjd}
            common=bykey.keys()&relevant.keys()
            offsets=[separation((float(bykey[k]['ra_obj']),float(bykey[k]['dec_obj'])),
                                (relevant[k]['ra'],relevant[k]['dec'])) for k in common]
            meta.update(reference_rows=len(relevant),matched_reference=len(common),
                        missing_reference=sorted(relevant.keys()-bykey.keys()),
                        additional=sorted(bykey.keys()-relevant.keys()),
                        separation_arcsec={'min':min(offsets),'median':float(np.median(offsets)),
                                           'p95':float(np.percentile(offsets,95)),'max':max(offsets)})
        if name in ('atlas_default','atlas_002','atlas_0005'):
            url=tab.meta['keywords']['output_url']['value']+'/orbital_path.tbl'
            raw,p=s._request(url)
            track=s.Table.read(raw.decode(),format='ascii.ipac')
            delta=np.diff(track['JD'])*86400
            meta['track']={'rows':len(track),'median_step_s':float(np.median(delta)),
                          'min_step_s':float(min(delta)),'max_step_s':float(max(delta)),'provenance':p}
        out['queries'].append({'name':name,**meta})
        print(name,meta['rows'],round(meta['elapsed_s'],3),meta.get('separation_arcsec'),flush=True)
        (ROOT/'most_evaluation.json').write_text(json.dumps(out,indent=2),encoding='utf-8')

    _,meta=query('1004083','2025-08-01','2025-08-16',.02,refresh=False)
    out['cache_repeat']=meta
    # Stratified actual exposure midpoints across both seasons; no special algorithm.
    sample=[]
    for prefix in ['atlas_aug','atlas_dec']:
        d=json.loads((ROOT/(prefix+'_discovery.json')).read_text())
        unique={r['obs_id']:r for r in d['rows'] if (r['obs_id'],r['detector']) in refs}
        rows=list(unique.values())
        sample.extend(rows[i] for i in np.linspace(0,len(rows)-1,5,dtype=int))
    for row in sample:
        a=Time(row['mjd_start']-120/86400,format='mjd')
        b=Time(row['mjd_end']+120/86400,format='mjd')
        tab,meta=query('1004083',a,b,1/86400,refresh=False)
        match=next((r for r in tab if key(r)==(row['obs_id'],row['detector'])),None)
        ref=refs[(row['obs_id'],row['detector'])]
        detail={'obs_id':row['obs_id'],'detector':row['detector'],'mjd':row['mjd'],
                'reference':[ref['ra'],ref['dec']],**meta}
        if match is not None:
            pos=[float(match['ra_obj']),float(match['dec_obj'])]
            detail.update(most=pos,separation_arcsec=separation(pos,detail['reference']),
                          reference_time_difference_s=abs(row['mjd_start']-ref['mjd_start'])*86400)
        # The match coordinates refer to exposure START. Evaluate its actual midpoint.
        initial={**row,'prediction':{'refined':False,'frame':'J2000 (MOST)',
                    'observer':'MOST/SPHEREx (NAIF -453)','uncertainty_arcsec':None}}
        p=s.refine_prediction({'spkid':'1004083'},initial)['prediction']
        detail.update(midpoint_prediction=p,
                      midpoint_separation_arcsec=separation((p['ra'],p['dec']),detail['reference']))
        out['precise_crosschecks'].append(detail)
        print(row['obs_id'],detail.get('separation_arcsec','NO MATCH'),round(meta['elapsed_s'],3),flush=True)
        (ROOT/'most_evaluation.json').write_text(json.dumps(out,indent=2),encoding='utf-8')

    # Full service output exposes spacecraft orbit time coverage and processing log.
    raw,meta=query('20000004','2025-08-05T00:04:00','2025-08-05T00:12:00',1/86400,mode='Full')
    html=raw.decode()
    lines=[re.sub('<[^>]*>',' ',line).strip() for line in html.splitlines()]
    relevant=[line for line in lines if line.startswith('MOST:')]
    out['observer_log']={**meta,'lines':relevant}
    (ROOT/'most_observer_response.html').write_bytes(raw)
    (ROOT/'most_evaluation.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
    print('Observer log:',relevant,flush=True)


if __name__=='__main__': main()
