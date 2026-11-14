import json, os, time
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
from urllib.parse import parse_qsl
import numpy as np
import pytest
from streamlit.testing.v1 import AppTest
from skyclues import archive, config, sequence, object_search as search, navigation, releases

@pytest.fixture
def record():
    report=json.loads((config.RESULTS_DIR/'sequence_m101.json').read_text(encoding='utf8'))
    # Use an existing real record schema; variants below are explicitly simulated products.
    f=report['selected']['frames'][0]
    return archive.ObservationRecord(f['obs_id'],f['collection'],f['detector'],'SPHEREx-D2',f['mjd'],f['mjd']+.001,
        f['exptime_s'],1.,2.,f['access_url'],'POLYGON ICRS 0 0 1 0 1 1','2026-11-14','27','2026-198',f['file_name'])

def test_refresh_discovers_new_observation_and_expiry(tmp_store,monkeypatch,record):
    newer=replace(record,obs_id='SIMULATED_NEW',file_name='level2_2026W44_1A_0001_1D2_spx_l2b-v27-2026-310.fits',access_url='https://example.test/new.fits',mjd_start=record.mjd_start+20,mjd_end=record.mjd_end+20)
    remote=[record];calls=[]
    def live(*args):calls.append(1);return list(remote)
    monkeypatch.setattr(archive,'_query_images_live',live)
    first=archive.query_images(10,0);remote.append(newer)
    cached=archive.query_images(10,0)
    assert len(cached)==1 and cached.provenance['origin']=='cache'
    assert cached.provenance['queried_utc']==first.provenance['queried_utc']
    fresh=archive.query_images(10,0,max_age_s=0)
    assert len(fresh)==2 and fresh.provenance['origin']=='IRSA' and len(calls)==2
    for p in config.CACHE_DIR.rglob('sia*.json'):os.utime(p,(0,0))
    assert len(archive.query_images(10,0))==2 and len(calls)==3

def test_replacement_duplicates_and_withdrawal(tmp_store,monkeypatch,record):
    newer=replace(record,l2b_version='99',file_name=record.file_name.replace('v27','v99'),access_url=record.access_url.replace('v27','v99'))
    monkeypatch.setattr(archive,'_query_images_live',lambda *a:[record,newer,newer])
    result=archive.query_images(10,0,max_age_s=0)
    assert len(result)==1 and result[0].l2b_version=='99'
    assert result.provenance['replacements']
    assert archive._cache_path(record.access_url)!=archive._cache_path(newer.access_url)
    monkeypatch.setattr(archive,'_query_images_live',lambda *a:[])
    assert not archive.query_images(10,0,max_age_s=0)

def test_refresh_failure_never_claims_cached_is_current(tmp_store,monkeypatch,record):
    monkeypatch.setattr(archive,'_query_images_live',lambda *a:[record]);archive.query_images(10,0)
    def down(*a):raise archive.ArchiveTransientError('HTTP 503')
    monkeypatch.setattr(archive,'_query_images_live',down)
    with pytest.raises(archive.ArchiveTransientError):archive.query_images(10,0,max_age_s=0)
    assert archive.query_images(10,0).provenance['origin']=='cache'

def test_proposal_calibration_guard(record):
    def candidate(r):return SimpleNamespace(rec=r,bw_um=.1,lam_um=1.5,lam_pts=np.array([1.5]*5),margin_px=20)
    a=candidate(record);b=candidate(replace(record,mjd_start=record.mjd_start+5,mjd_end=record.mjd_end+5,file_name='second'))
    assert sequence.propose_sequences([a,b])
    assert not sequence.propose_sequences([a,candidate(replace(b.rec,l2b_version='99'))])
    assert not sequence.propose_sequences([a,candidate(replace(b.rec,collection='spherex_dr1'))])

def test_reports_do_not_overwrite(tmp_path,monkeypatch):
    monkeypatch.setattr(config,'RESULTS_DIR',tmp_path)
    p=sequence.save_report({'old':1},'same');q=sequence.save_report({'new':2},'same')
    assert p!=q and json.loads(p.read_text())=={'old':1}

@pytest.mark.parametrize('bad',[{}, {'ra':'nan','dec':0},{'ra':360,'dec':0},{'ra':1,'dec':91},{'ra':1,'dec':0,'fov':6},{'ra':1,'dec':0,'explorer':'x'},{'ra':1,'dec':0,'canal':103}])
def test_url_rejects_bad_parameters(bad):
    with pytest.raises(ValueError):navigation.parse_region(bad)

@pytest.mark.parametrize('mode',['temporal','espectral'])
def test_link_independent_sessions(mode):
    from test_spectral_app import APP
    query=dict(parse_qsl(navigation.region_query(210.802429,54.34875,.1,mode,63)[1:]))
    assert query['fov']=='0.1'
    assert navigation.parse_region(query)['canal']==63
    if mode=='temporal':
        for _ in range(2):
            at=AppTest.from_file(APP,default_timeout=30);at.query_params=query;at.run()
            assert not at.exception
            assert at.number_input(key='ra_in').value==pytest.approx(210.802429)
            assert at.radio(key='fov_preset').value=='6′'

@pytest.mark.parametrize('name,identity',[('Andrómeda','M  31'),('NGC224','M  31'),('m31','M  31'),('M101','M 101'),('Barnard','GJ 699'),('WISE 0855','WISEA J085510.74-071442.5'),('Epsilon Indi','* eps Ind'),('M42','M  42'),('M45','Cl Melotte   22'),('HD209458','HD 209458')])
def test_verified_aliases(name,identity):
    a,_,_=search.resolve(name)
    # Barnard's main ID in SIMBAD can differ from its GJ alias.
    if name!='Barnard':assert a.name==identity
    else:assert a.total_pm_arcsec_yr>10
    assert 0<=a.ra_deg<360 and a.source.startswith('https://simbad.')
    assert search.local_suggestions(name)

@pytest.mark.parametrize('bad',['', 'x'*101, 'HD%', 'x; DROP', '<script>', 'a\n'])
def test_search_validation(bad):
    with pytest.raises(ValueError):search.validate_name(bad)

def test_object_state_transfer():
    a,_,_=search.resolve('Barnard')
    for mode in ['temporal','espectral']:
        state,params={},{}
        navigation.open_object(state,params,a,mode,.1)
        assert float(params['ra'])==a.ra_deg and float(params['fov'])==.1
        r=state['resolved' if mode=='temporal' else 'sx_resolved']['astrometry']
        assert r['pmra_masyr']==a.pmra_masyr and r['epoch_jyear']==2000

def test_remote_outage_local_remains(monkeypatch):
    def down(*a,**kw):raise search.requests.Timeout()
    monkeypatch.setattr(search.requests,'get',down)
    rows,status=search.remote_suggestions('HD20945')
    assert not rows and 'no disponibles' in status
    assert search.resolve('M31')[0].ra_deg>10

def test_collection_allowlist():
    with pytest.raises(ValueError):releases.validate_collections(['spherex_future'])
    assert releases.CUBE_RELEASES[releases.ACTIVE_CUBE]['data_url']==config.CUBE_DATA_URL


def test_refresh_reaches_sequence_report(tmp_store,monkeypatch):
    calls=[]
    def query(*a,**kw):
        calls.append(kw);return archive.ObservationBatch([],{'origin':'IRSA','queried_utc':'2026-11-14T00:00:00Z'})
    monkeypatch.setattr(archive,'query_images',query)
    _,report=sequence.find_sequence(10,0,.1,refresh=True,log=lambda *a:None)
    assert calls[0]['max_age_s']==0 and report['discovery']['origin']=='IRSA'


def test_retry_filename_profile():
    m=archive._FILE_RE.search('level2_2026W23_2A_0336_3D2_spx_l2b_retry-v27-2026-271.fits')
    assert m and m.group('obsid')=='2026W23_2A_0336_3' and m.group('ver')=='27'


def test_cube_startup_rejects_unknown():
    with pytest.raises(ValueError):releases.configure_cube_release('future')


def test_refresh_ui_requests_new_query(monkeypatch):
    calls=[]
    def find(*a,**kw):
        calls.append(kw)
        return None,{'target':{'ra_deg':10.,'dec_deg':0.},'selected':None,'elapsed_s':0,'n_records':0}
    monkeypatch.setattr(sequence,'find_sequence',find)
    at=AppTest.from_file(str(config.ROOT/'app.py'),default_timeout=30)
    at.query_params={'ra':'10','dec':'0','fov':'.1'};at.run()
    at.button(key='refresh_observations').click().run()
    assert not at.exception and calls[-1]['refresh'] is True


def test_suggestion_cache_success_but_not_outage(monkeypatch):
    from skyclues import release_ui
    release_ui.suggestions.clear();calls=[]
    def answer(q):calls.append(q);return [],'https://simbad.harvard.edu'
    monkeypatch.setattr(search,'remote_suggestions',answer)
    release_ui.suggestions('ABC');release_ui.suggestions('ABC');assert calls==['ABC']
    release_ui.suggestions.clear()
    def outage(q):calls.append(q);return [],'Sugerencias remotas no disponibles'
    monkeypatch.setattr(search,'remote_suggestions',outage)
    for _ in range(2):
        with pytest.raises(RuntimeError):release_ui.suggestions('XYZ')
    assert calls[-2:]==['XYZ','XYZ']
    release_ui.suggestions.clear()
