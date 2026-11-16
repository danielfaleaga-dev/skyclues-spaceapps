"""New identity contracts, failure behavior, and preservation of scientific region inputs."""
import json
import pytest
from skyclues import config, navigation, object_search as search, solar_system as solar


@pytest.mark.parametrize('n', range(1,111))
def test_complete_messier_range_is_dynamic(n, monkeypatch):
    calls=[]
    monkeypatch.setattr(search,'INDEX',[])
    monkeypatch.setattr(search,'resolve_name',lambda name:(calls.append(name) or None, []))
    if n==102:
        with pytest.raises(ValueError,match='ambiguous'):search.resolve('Messier 102')
        assert not calls
    else:
        search.resolve(f'Messier {n}')
        assert calls==[f'M {n}']


@pytest.mark.parametrize('name,expected',[('NGC224','NGC 224'),('ic1396','IC 1396'),('m001','M 1')])
def test_catalogue_canonical_names(name,expected):
    assert search.canonical_name(name)==expected


def test_constellation_coverage_and_coordinates():
    d=json.loads((config.ROOT/'data/constellations.json').read_text(encoding='utf8'))
    f=d['figures']
    assert len(set(x['id'] for x in f))==88
    assert {'Ori','And','Sco','Cru','UMa'} <= {x['id'] for x in f}
    for x in f:
        for line in x['lines']:
            for ra,dec in line:assert 0<=ra<360 and -90<=dec<=90


def test_horizons_contract_and_solar_region(monkeypatch):
    calls=[]
    def answer(url, params):
        calls.append(params)
        return {'result':'$$SOE\n2026-Nov-14 12:00:00, , , 123.456789, -22.012345,\n$$EOE'}
    monkeypatch.setattr(solar,'request_json',answer)
    identity={'name':'ATLAS','spkid':'1004083','type':'comet','pdes':'C/2025 N1'}
    p=solar.ephemeris(identity,'2026-11-14T12:00:00')
    assert calls[0]['COMMAND']=="'DES=C/2025 N1;CAP'"
    assert calls[0]['CENTER']=="'500@399'" and calls[0]['QUANTITIES']=="'1'"
    state,qp={},{}
    navigation.set_region(state,qp,10,20,.2)
    navigation.set_solar(state,qp,p)
    r=state['region']; inp=navigation.explorer_inputs(r)
    assert r['fov']==.2 and r['solar']['utc']=='2026-11-14T12:00:00.000'
    assert inp['astrometry'] is None and inp['follow'] is False
    navigation.move_region(state,qp,100,10,.2)
    assert state['region']['solar'] is None


def test_lookup_aliases_deduction_and_no_spacecraft(monkeypatch):
    calls=[]
    def answer(url,params):
        calls.append(params)
        return {'result':[{'name':'Europa','spkid':'502','type':'natural satellite'},
                          {'name':'Clipper','spkid':'-159','type':'spacecraft'}]}
    monkeypatch.setattr(solar,'request_json',answer)
    assert len(solar.lookup('3I/ATLAS'))==1 and calls[-1]['sstr']=='3I'
    solar.lookup('C/2025 N1 (ATLAS)')
    assert calls[-1]['sstr']=='C/2025 N1'


@pytest.mark.parametrize('bad',['no table','$$SOE\nnow,,,nan,20\n$$EOE','$$SOE\nnow,,,400,20\n$$EOE'])
def test_ephemeris_rejects_missing_ambiguous_or_invalid_data(monkeypatch,bad):
    monkeypatch.setattr(solar,'request_json',lambda *a:{'result':bad})
    with pytest.raises(solar.ServiceError):solar.ephemeris({'name':'Mars','spkid':'499','type':'planet'},'2026-11-14')


def test_network_outage_is_explicit(monkeypatch):
    def down(*a,**k):raise solar.requests.Timeout()
    monkeypatch.setattr(solar.requests,'get',down)
    with pytest.raises(solar.ServiceError,match='not available'):solar.lookup('Bennu')
