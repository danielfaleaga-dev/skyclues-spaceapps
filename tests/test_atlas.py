"""Atlas and the common region state (name / coordinates / atlas → Time or Spectrum Explorer).

The Aladin Lite component itself runs in the browser (verified in a real browser, see
PROJECT_STATE). Here its selection event is SIMULATED by replacing the component with a
stub that returns the event the JS sends ({ra, dec, fov, view, layer}).
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from skyclues import atlas, navigation, references

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class Params(dict):
    def update(self, d):   # st.query_params-like
        super().update({k: str(v) for k, v in d.items()})


# ----------------------------------------------------------------------------- layers and provenance
def test_layers_identify_mission_product_and_are_official_hips():
    ids = [L["id"] for L in atlas.LAYERS]
    assert len(ids) == len(set(ids))
    for L in atlas.LAYERS:
        assert L["url"].startswith("https://irsa.ipac.caltech.edu/data/hips/")
        assert all(L[k] for k in ("mission", "product", "bands", "epoch", "note"))
        assert "SPHEREx" not in L["mission"]          # no SPHEREx map is presented as a layer
    assert {"allwise", "w1", "w2"} <= set(ids) and "2mass" in ids
    assert atlas.SPHEREX_HIPS["release"] and "combined" in atlas.SPHEREX_HIPS["kind"]


def test_object_position_now_uses_catalogue_motion():
    from skyclues.astrometry import Astrometry
    still = Astrometry("A", 10.0, 0.0, 2000.0)
    assert atlas.object_position_now(still) == (10.0, 0.0)
    moving = Astrometry("B", 10.0, 0.0, 2000.0, pmra_masyr=0.0, pmdec_masyr=10000.0)
    assert atlas.object_position_now(moving)[1] > 0.05     # 10″/yr over > 26 yr




def test_region_from_url_and_single_source_of_truth():
    state, params = {}, {'ra':'83.8221','dec':'-5.3911','fov':'.2'}
    r=navigation.get_region(state,params)
    assert (r['ra'],r['dec'],r['fov'])==(83.8221,-5.3911,.2)
    params['ra']='12'
    assert navigation.get_region(state,params) is r
    navigation.move_region(state,params,150.,2.,.1)
    assert state['region']['ra']==150 and params['ra']=='150.000000'


@pytest.mark.parametrize('ra,dec,fov',[(360,0,.1),(10,91,.1),(10,0,.6),(10,0,.01),(float('nan'),0,.1)])
def test_set_region_rejects_invalid_regions(ra,dec,fov):
    with pytest.raises(ValueError):navigation.set_region({}, {}, ra, dec, fov)


def test_bad_link_reports_errors_without_clamping():
    state={}
    r=navigation.get_region(state,{'ra':'nan','dec':'0','fov':'10'})
    assert r['ra']==navigation.DEFAULT_REGION['ra'] and len(state['region_errors'])==2


def test_named_object_retained_on_zoom_removed_on_drag():
    from skyclues.object_search import resolve
    a,_,_=resolve('Barnard'); state,params={},{}
    pos=atlas.object_position_now(a)
    navigation.set_object(state,params,a,position=pos)
    navigation.move_region(state,params,*pos,.2)
    inp=navigation.explorer_inputs(state['region'])
    assert inp['astrometry'].name==a.name and inp['ra']==a.ra_deg and inp['follow']
    navigation.move_region(state,params,pos[0]+.01,pos[1],.2)
    assert state['region']['astrometry'] is None


def test_unified_component_and_gaia_outage(monkeypatch):
    from skyclues import region_ui, reference_page
    calls=[]
    monkeypatch.setattr(region_ui,'REGION',lambda **kw:calls.append(kw['data']))
    def down(*a,**k):raise references.ReferenceError('Gaia no responde')
    from skyclues import gaia_atlas
    monkeypatch.setattr(gaia_atlas.CATALOGUE,'poll',lambda *a,**k:{'state':'error','message':'Gaia no disponible'})
    at=AppTest.from_file(APP,default_timeout=30)
    at.session_state['atlas_gaia']=True
    at.run()
    assert not at.exception and len(calls)==1
    d=calls[0]
    assert d['region']['fov']==.1 and d['gaia']==[] and 'no disponible' in d['gaia_note']
    assert at.button_group(key='nav').options==['Region','Time','Spectrum']
    assert not at.radio


@pytest.mark.parametrize('view',['time','spectrum'])
def test_component_open_is_one_region_without_confirmation(monkeypatch,view):
    from skyclues import region_ui
    state={'region_ui':{'open':{'ra':83.8,'dec':-5.4,'fov':.2,'view':view}}}; params={}
    monkeypatch.setattr(region_ui.st,'session_state',state)
    monkeypatch.setattr(region_ui.st,'query_params',params)
    region_ui._on_open()
    assert state['view_request']==view
    assert navigation.explorer_inputs(state['region'])['ra']==83.8
    assert params['fov']=='0.2'


def test_rejected_component_event_preserves_region(monkeypatch):
    from skyclues import region_ui
    state={'region_ui':{'region':{'ra':12,'dec':0,'fov':8}}};params={}
    before=navigation.get_region(state,params).copy()
    monkeypatch.setattr(region_ui.st,'session_state',state)
    monkeypatch.setattr(region_ui.st,'query_params',params)
    region_ui._on_region()
    assert state['region']==before and 'Invalid region' in state['region_notice']
