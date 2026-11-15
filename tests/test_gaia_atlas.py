"""Atlas Gaia selection and asynchronous lifecycle, with controlled network doubles."""
from threading import Event
import json
import subprocess
from pathlib import Path

import pytest
from skyclues import gaia_atlas, navigation, region_ui
from test_spectral_app import app_cube
from test_spectral_offline import cube

SOURCE = {'source_id':'6051234567890123456', 'ra':323.201930123, 'dec':-21.785755987,
          'ref_epoch':2016., 'pmra':12., 'pmdec':-30., 'parallax':None, 'radial_velocity':None}


def test_slow_empty_cache_failure_retry_and_old_result():
    gates = {k:Event() for k in ['old','new','empty','error']}
    calls=[]
    def fetch(k):
        calls.append(k)
        assert gates[k].wait(5)
        if k=='error' and calls.count(k)==1:raise TimeoutError()
        return [] if k=='empty' else k
    jobs=gaia_atlas.Jobs(fetch)
    try:
        assert jobs.poll(('old',))['state']=='loading'
        assert jobs.poll(('old',))['state']=='loading'  # no duplicated request
        assert jobs.poll(('new',))['state']=='loading'
        gates['old'].set(); jobs.entries[('old',)][0].result(5)
        assert jobs.poll(('new',))['state']=='loading'  # old completion cannot satisfy new field
        gates['new'].set(); jobs.entries[('new',)][0].result(5)
        assert jobs.poll(('new',))=={'state':'ready','result':'new'}
        assert jobs.poll(('new',))['state']=='ready'  # cached: no artificial loading
        jobs.poll(('empty',));gates['empty'].set();jobs.entries[('empty',)][0].result(5)
        assert jobs.poll(('empty',))=={'state':'ready','result':[]}
        jobs.poll(('error',));gates['error'].set()
        with pytest.raises(TimeoutError):jobs.entries[('error',)][0].result(5)
        assert jobs.poll(('error',))['state']=='error'
        assert jobs.poll(('error',))['state']=='error'  # no hidden retry storm
        jobs.poll(('error',),retry=True);jobs.entries[('error',)][0].result(5)
        assert jobs.poll(('error',))['state']=='ready'
        assert calls.count('old')==1 and calls.count('new')==1 and calls.count('error')==2
    finally:
        for e in gates.values():e.set()
        jobs.pool.shutdown(wait=True)


def state_for_click():
    return {'atlas_gaia':True,'atlas_gaia_displayed':{'key':'sha', 'sources':{SOURCE['source_id']:SOURCE},
            'provenance':{'sha256':'sha','retrieved_utc':'2026-11-14'}},
            'region_ui':{'gaia_pick':{'source_id':SOURCE['source_id'],'key':'sha','fov':.2}}}


def test_exact_source_selection_without_remote_resolution(monkeypatch):
    state,qp=state_for_click(),{}
    navigation.set_region(state,qp,323.21,-21.78,.1)
    monkeypatch.setattr(region_ui.st,'session_state',state)
    monkeypatch.setattr(region_ui.st,'query_params',qp)
    def no_network(*a,**k):raise AssertionError('Selection must reuse loaded rows')
    monkeypatch.setattr(region_ui,'resolve',no_network)
    monkeypatch.setattr(gaia_atlas.references,'fetch_gaia',no_network)
    region_ui._on_gaia_pick()
    r=state['region']
    assert r['name']=='Gaia DR3 '+SOURCE['source_id']
    assert (r['ra'],r['dec'],r['fov'])==(SOURCE['ra'],SOURCE['dec'],.2)
    assert r['astrometry']['epoch_jyear']==2016.
    assert r['astrometry']['pmra_masyr']==12.
    assert 'J2016.0' in region_ui.object_card(r)['detail']
    assert 'detección SPHEREx' in ' '.join(region_ui.object_card(r)['notes'])
    r['gaia']['alias']={'name':'HD 123', 'source':'SIMBAD'}
    assert region_ui.object_card(r)['name']==r['name'] and 'HD 123' in region_ui.object_card(r)['detail']
    for view in ['time','spectrum','region']:
        navigation.write_url(qp,r,view)
        assert state['region']==r
        assert navigation.explorer_inputs(r)['astrometry'].name==r['name']
    navigation.move_region(state,qp,r['ra']+.01,r['dec'],.2)
    assert state['region']['gaia'] is None


@pytest.mark.parametrize('change',[{'source_id':'6051234567890123457'}, {'key':'old'}, {'source_id':6051234567890123456}])
def test_unknown_or_stale_id_does_not_select(monkeypatch,change):
    state,qp=state_for_click(),{}
    r=navigation.get_region(state,qp).copy()
    state['region_ui']['gaia_pick'].update(change)
    monkeypatch.setattr(region_ui.st,'session_state',state);monkeypatch.setattr(region_ui.st,'query_params',qp)
    region_ui._on_gaia_pick()
    assert state['region']==r


def test_actual_component_selection_loading_and_stale_responses():
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run(['node',str(root/'tests/gaia_atlas_harness.cjs')],cwd=root,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr


def test_gaia_identity_survives_both_explorers(app_cube, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from skyclues import time_page, config
    monkeypatch.setattr(gaia_atlas.ALIASES,'poll',lambda *a,**k:{'state':'ready','result':None})
    def find(ra,dec,field_deg,**kw):
        return None, {'target':{'ra_deg':ra,'dec_deg':dec,'field_deg':field_deg},'selected':None,'elapsed_s':0,'n_records':0}
    monkeypatch.setattr(time_page,'find_sequence',find)
    src=dict(SOURCE,ra=app_cube.centre[0],dec=app_cube.centre[1],pmra=None,pmdec=None)
    state,qp={},{}
    navigation.set_region(state,qp,10,20,.2)
    navigation.set_gaia(state,qp,src,{'sha256':'synthetic-offline-test'})
    at=AppTest.from_file(str(config.ROOT/'app.py'),default_timeout=30)
    at.session_state['region']=state['region']
    at.run()
    for view in ['Espectro','Tiempo','Región']:
        at.button_group(key='nav').set_value(view).run()
        assert not at.exception
        r=at.session_state['region']
        assert r['name']=='Gaia DR3 '+SOURCE['source_id'] and r['fov']==.2
        assert (r['ra'],r['dec'])==app_cube.centre
        assert r['astrometry']['epoch_jyear']==2016.
