"""Selective REAL-FITS validation. Run with .venv Python from the repository root.

Metadata discovery files are reproducible via moving_sources.discover. Only the
specified, spectrally selected groups (max 4 per case) are fetched, never all images.
"""
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from skyclues import moving_sources as s, non_sidereal as n, moving_view as v, render

ROOT=Path(__file__).resolve().parents[1]/'results'/'moving'


def run_case(label,discovery,low,high,group_index=0):
    d=json.loads((ROOT/(discovery+'_discovery.json')).read_text(encoding='utf-8'))
    groups=s.groups(d['rows'],low,high,max_frames=4)
    if not groups:
        return {'label':label,'status':'no_coverage','count':len(d['rows'])}
    rows=groups[group_index]
    frames,failures=n.fetch_frames(d['identity'],rows,.1,lambda msg:print(label,msg,flush=True))
    report=n.assess(frames,.1,progress=print);report['failures']=failures;report['identity']=d['identity']
    if frames:
        arrays,_,_=n.aligned(frames,.1)
        norm=render.shared_norm(arrays,lo=5,hi=99)
        for i,f in enumerate(frames):
            (ROOT/f'{label}_{i+1}.png').write_bytes(v.frame_png(f,.1,norm))
        if report.get('stack_allowed'):
            a=n.stack(frames,.1,True);b=n.stack(frames,.1,False)
            np.savez_compressed(ROOT/(label+'_stacks.npz'),follow=a['image'],control=b['image'],
                                contributions=a['contributions'],control_contributions=b['contributions'],
                                variance=a['variance'],control_variance=b['variance'])
            (ROOT/(label+'_stacks.png')).write_bytes(render.figure_png(v.stack_figure(a,b)))
            report['stack']={k:a[k] for k in ('method','limitation','backgrounds')}
            mid=np.array(a['image'].shape)//2;sl=np.s_[mid[0]-2:mid[0]+3,mid[1]-2:mid[1]+3]
            report['stack'].update(centre_follow_n=int(a['contributions'][tuple(mid)]),
                 centre_control_n=int(b['contributions'][tuple(mid)]),
                 central_response_follow=float(np.nanmean(a['image'][sl])),
                 central_response_control=float(np.nanmean(b['image'][sl])),
                 inference='No se considera mejora de S/N validada: falta covarianza y controles equivalentes.')
    (ROOT/(label+'.json')).write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    return {'label':label,'status':report['status'],'frames':len(frames),'failures':failures,
            'observed_motion':report.get('observed_motion',False)}


def stationary_control():
    from skyclues import sequence,archive
    seq=sequence.load_sequence(ROOT.parent/'sequence_m101.json')
    frames=[]
    for f in seq.frames:
        row={'obs_id':f.obs_id,'detector':f.detector,'collection':f.record['collection'],
             'version':archive._FILE_RE.search(f.cutout_url)['ver'],'mjd':f.mjd,
             'lambda_um':f.lambda_target_um,'bandwidth_um':f.bandwidth_target_um,
             'prediction':{'ra':seq.ra,'dec':seq.dec,'refined':True,
                           'source':'CONTROL ESTACIONARIO M101; sin efeméride'}}
        frames.append(n.MovingFrame(row,f.image,f.path,f.cutout_url,f.sha256))
    report=n.assess(frames,seq.field_deg)
    report['validation_role']='Campo estacionario auténtico; no es un objeto móvil simulado'
    (ROOT/'stationary_m101.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    assert not report['observed_motion']
    return {'label':'stationary_m101','status':report['status'],'frames':len(frames),'observed_motion':False}


if __name__=='__main__':
    cases=[('atlas_aug_continuum','atlas_aug',1,1.5,0),
           ('atlas_aug_co2_a','atlas_aug',4.23,4.28,0),
           ('atlas_aug_co2_b','atlas_aug',4.23,4.28,1),
           ('atlas_dec_continuum','atlas_dec',1,1.5,0),
           ('atlas_dec_co2','atlas_dec',4.23,4.28,0),
           ('atlas_dec_repeat','atlas_dec',.7,5.1,0),
           ('vesta_real','vesta',.7,5.1,1),
           ('pluto_real','pluto_year',.7,5.1,1),
           ('comet_29p_real','comet_swassmann_year',.7,5.1,0)]
    result=[]
    for case in cases:
        try:
            result.append(run_case(*case));print(result[-1],flush=True)
        except Exception as e:
            result.append({'label':case[0],'error':str(e)});print(result[-1],flush=True)
    result.append(stationary_control())
    (ROOT/'validation_summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
