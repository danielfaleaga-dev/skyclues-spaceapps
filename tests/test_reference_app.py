"""Reference panel uses the exact explorer field and survives a Gaia outage."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from skyclues import reference_page as page, references as ref
from test_spectral_app import app_cube, spectral_app
from test_spectral_offline import cube

APP=str(Path(__file__).resolve().parents[1]/'app.py')


def test_time_reference_region_and_gaia_outage(monkeypatch):
    calls=[]
    def outage(ra,dec,fov): calls.append((ra,dec,fov));raise ref.ReferenceError('Gaia DR3 no disponible')
    monkeypatch.setattr(page,'cached_gaia',outage)
    at=AppTest.from_file(APP,default_timeout=30)
    at.session_state['level']='Scientific'
    at.run()
    assert not at.exception
    at.button(key='example_sequence_m101').click().run()
    shared=at.session_state['region']
    at.toggle(key='time_ref_open').set_value(True).run()
    assert not at.exception and not calls
    at.checkbox(key='time_ref_query').check().run()
    assert not at.exception
    assert calls[-1]==(shared['ra'],shared['dec'],shared['fov'])
    assert any('Gaia DR3 no disponible' in x.value for x in at.warning)
    html=next(x.proto.srcdoc for x in at.get('iframe') if 'gaiaLoaded' in x.proto.srcdoc)
    assert 'AllWISE' in html and '"gaiaLoaded": false' in html
    assert at.session_state['region']['report']=='sequence_m101'


def test_spectrum_reference_field_and_transfer(app_cube,monkeypatch):
    calls=[]
    def html(ra,dec,fov,*args): calls.append((ra,dec,fov));return '<p>Reference test</p>'
    monkeypatch.setattr(page,'viewer_html',html)
    at=spectral_app(app_cube)
    key=at.session_state['sx_region_key']
    at.toggle(key='spectrum_ref_open').set_value(True).run()
    assert not at.exception and calls[-1]==pytest.approx(key)
    from skyclues import time_page
    def result(inp,refresh):
        return {'target':{'ra_deg':inp['ra'],'dec_deg':inp['dec'],'field_deg':inp['fov']},'selected':None,'n_records':0}
    monkeypatch.setattr(time_page,'run_search',result)
    at.button_group(key='nav').set_value('Time').run()
    at.toggle(key='time_ref_open').set_value(True).run()
    assert not at.exception and calls[-1]==pytest.approx(key)
