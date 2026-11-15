"""Catalogue autocomplete contracts: real service notation, identities and partial failures."""
import json
import pytest
from skyclues import object_search as search, solar_system as solar, region_ui, navigation


@pytest.mark.parametrize('typed,expected', [
    ('ngc', "ident.id LIKE 'NGC %'"),
    ('NGC8', "ident.id LIKE 'NGC     8%'"),
    ('M13', "ident.id LIKE 'M  13%'"),
    ('Messier 13', "ident.id LIKE 'M  13%'"),
    ('ic1', "ident.id LIKE 'IC    1%'"),
])
def test_simbad_padded_identifier_query(typed, expected, monkeypatch):
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def raise_for_status(self): pass
        def iter_content(self, size):
            yield json.dumps({'metadata': [{'name': n} for n in ['main_id', 'otype', 'id']],
                              'data': [['M  31', 'AGN', search.catalogue_prefix(typed)[1].upper() + '   224']]}).encode()
    def request(url, **kw):
        calls.append(kw['params']['QUERY'])
        return Response()
    monkeypatch.setattr(search.requests, 'get', request)
    rows, _ = search.remote_suggestions(typed)
    assert any(expected in q for q in calls) and 'TOP 24' in calls[0] and 'ORDER BY' not in calls[0]
    assert rows[0]['label'].endswith(' 224') and rows[0]['id'] == 'M  31'


def test_short_catalogue_prefixes_are_searchable():
    assert all(search.can_suggest(q) for q in ['M', 'm1', 'IC', 'ngc', 'atlas'])
    assert not search.can_suggest('a') and not search.can_suggest('')


def test_atlas_suggestions_include_interstellar_identity_beyond_first_twelve(monkeypatch):
    # Synthetic ordering, official identifier fields: many ATLAS comets precede 3I in JPL.
    rows = [{'name': 'ATLAS', 'type': 'comet (integrated barycenter)', 'spkid': str(1003000+i),
             'pdes': f'C/2015 A{i}', 'alias': []} for i in range(14)]
    rows.append({'name': 'ATLAS (C/2025 N1)', 'type': 'comet (integrated barycenter)',
                 'spkid': '1004083', 'pdes': 'C/2025 N1', 'alias': ['3I', 'K25N010']})
    monkeypatch.setattr(solar, 'request_json', lambda *a: {'result': rows})
    result = solar.suggestions('atlas')
    assert result[0]['id'] == 'JPL:1004083'
    assert result[0]['label'] == '3I/ATLAS (C/2025 N1)'
    assert len(result) == 12 and result[0]['type'] == 'Cometa'


def test_universal_suggestions_query_jpl_but_catalogue_prefix_does_not(monkeypatch):
    region_ui.suggestions.clear()
    calls = []
    monkeypatch.setattr(search, 'remote_suggestions', lambda q: ([], 'SIMBAD'))
    def planets(q):
        calls.append(q)
        return [{'id': 'JPL:615', 'label': 'Atlas', 'type': 'Satélite natural', 'aliases': []}]
    monkeypatch.setattr(solar, 'suggestions', planets)
    assert region_ui.suggestions('atlas')[0][0]['id'] == 'JPL:615'
    region_ui.suggestions('NGC')
    assert calls == ['atlas']
    region_ui.suggestions.clear()


def test_partial_failure_preserves_jpl_choices(monkeypatch):
    region_ui.suggestions.clear()
    monkeypatch.setattr(search, 'remote_suggestions', lambda q: ([], 'Sugerencias remotas no disponibles'))
    monkeypatch.setattr(solar, 'suggestions', lambda q: [{'id': 'JPL:615'}])
    rows, message = region_ui.suggestions('Atlas')
    assert rows == [{'id': 'JPL:615'}] and 'no responde' in message
    region_ui.suggestions.clear()


def test_click_solar_suggestion_resolves_exact_id_and_preserves_field(monkeypatch):
    state, params = {}, {}
    navigation.set_region(state, params, 10, 20, .2)
    state['region_ui'] = {'pick': {'name': 'JPL:1004083', 'n': 123}}
    monkeypatch.setattr(region_ui.st, 'session_state', state)
    monkeypatch.setattr(region_ui.st, 'query_params', params)
    calls = []
    identity = {'name': 'ATLAS (C/2025 N1)', 'spkid': '1004083', 'pdes': 'C/2025 N1', 'type': 'comet', 'aliases': []}
    def lookup(q):
        calls.append(q)
        return [identity]
    monkeypatch.setattr(region_ui, 'solar_lookup', lookup)
    monkeypatch.setattr(region_ui, 'solar_position', lambda i, t: {
        'identity': i, 'utc': t, 'observer_label': 'geocentro terrestre', 'observer': '500@399',
        'ra': 123.4, 'dec': -21.5, 'frame': 'ICRF', 'source': solar.HORIZONS, 'kind': 'ephemeris'})
    region_ui._on_pick()
    assert calls == ['1004083']
    assert state['region']['solar']['identity']['spkid'] == '1004083'
    assert (state['region']['ra'], state['region']['dec'], state['region']['fov']) == (123.4, -21.5, .2)

