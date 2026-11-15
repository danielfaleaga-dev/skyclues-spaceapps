"""UI orchestration with explicitly simulated service replies, no browser claims."""
from copy import deepcopy
from datetime import date
import json

import pytest
from streamlit.testing.v1 import AppTest
from skyclues import moving_page as page, navigation, config

APP=str(config.ROOT/'app.py')
IDENTITY={'spkid':'999','name':'Pluto','type':'planet'}
ROW={'obs_id':'SIMULATED','detector':2,'collection':'SIMULATED','version':'1','mjd':60898.,
     'lambda_um':1.25,'bandwidth_um':.03,'margin_px':100,'url':'synthetic://fixture'}


def app():
    state,qp={},{}
    navigation.set_region(state,qp,150,10,.2)
    navigation.set_solar(state,qp,{'identity':IDENTITY,'ra':150,'dec':10,'utc':'2025-08-01T00:00:00',
        'observer':'500@399','observer_label':'geocentro terrestre','kind':'ephemeris','frame':'ICRF','source':'SIMULATED'})
    at=AppTest.from_file(APP,default_timeout=20)
    at.session_state['region']=state['region'];at.session_state['nav']='Tiempo'
    return at.run()


def reply(rows):
    return {'rows':deepcopy(rows),'identity':IDENTITY,'excluded_products':[]}


def test_empty_and_failure_are_different(monkeypatch):
    monkeypatch.setattr(page,'discover',lambda *a,**k:reply([]))
    at=app();at.button(key='moving_search').click().run()
    assert not at.exception and any('Sin cobertura' in m.value for m in at.info)
    def fail(*a,**k):raise RuntimeError('Servicio no disponible, reintente')
    monkeypatch.setattr(page,'discover',fail)
    at=app();at.button(key='moving_search').click().run()
    assert not at.exception and any('Servicio no disponible' in m.value for m in at.error)
    assert not any('Sin cobertura' in m.value for m in at.info)


def test_solar_route_preserves_region_and_never_uses_fixed_field_engine(monkeypatch):
    from skyclues import time_page
    def forbidden(*a,**k):raise AssertionError('Stellar fixed-field search must not handle a solar target')
    monkeypatch.setattr(time_page,'find_sequence',forbidden)
    monkeypatch.setattr(page,'discover',lambda *a,**k:reply([ROW]))
    at=app();region=deepcopy(at.session_state['region'])
    at.button(key='moving_search').click().run()
    assert not at.exception
    at.button_group(key='level').set_value('Científico').run()
    assert not at.exception and at.session_state['region']==region
    assert at.session_state['region']['fov']==.2
    assert any(s.label=='Secuencia de observaciones compatibles' for s in at.selectbox)


def test_dates_survive_navigation_and_switching_levels(monkeypatch):
    monkeypatch.setattr(page,'discover',lambda *a,**k:reply([ROW]))
    at=app()
    at.date_input(key='w_moving_start').set_value(date(2025,12,1)).run()
    at.date_input(key='w_moving_end').set_value(date(2025,12,20)).run()
    at.button(key='moving_search').click().run()
    at.button_group(key='nav').set_value('Región').run()
    at.button_group(key='nav').set_value('Tiempo').run()
    assert not at.exception
    assert at.date_input(key='w_moving_start').value==date(2025,12,1)
    assert at.date_input(key='w_moving_end').value==date(2025,12,20)
    assert any(s.label=='Secuencia de observaciones compatibles' for s in at.selectbox)


def test_failed_fits_is_not_no_coverage(monkeypatch):
    monkeypatch.setattr(page,'discover',lambda *a,**k:reply([ROW]))
    monkeypatch.setattr(page,'prepare',lambda *a:([],[{'obs_id':'SIMULATED','error':'Timeout de prueba'}]))
    at=app();at.button(key='moving_search').click().run();at.button(key='moving_prepare').click().run()
    assert not at.exception
    assert any('No evaluable' in m.value for m in at.info)
    assert at.button(key='moving_retry')
