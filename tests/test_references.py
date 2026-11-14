"""Independent astrometric oracles and controlled service failures; no network."""
import csv
import io
import json
import warnings
import shutil
import subprocess
from pathlib import Path

import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
import pytest
import requests

from skyclues import references as ref
from skyclues.reference_view import viewer_html


def csv_bytes(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=ref.COLUMNS)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


@pytest.fixture
def source():
    return {**dict.fromkeys(ref.COLUMNS), 'source_id': '4472832130942575872',
            'ra': 269.44850252543836, 'dec': 4.739420051112412, 'ref_epoch': 2016.0,
            'pmra': -801.5509783684709, 'pmdec': 10362.394206546573}


def test_ids_nulls_and_truncation(source):
    rows, cut = ref.parse_gaia(csv_bytes([source, {**source, 'source_id': '4472832130942575873'}]), 1)
    assert rows[0]['source_id'] == '4472832130942575872'
    assert rows[0]['parallax'] is None and cut
    assert ref.parse_gaia(csv_bytes([]), 500) == ([], False)


@pytest.mark.parametrize('bad', [b'<html>offline</html>', b'', b'source_id,ra\n1,NaN'])
def test_invalid_service_payload(bad):
    with pytest.raises(ref.ReferenceError): ref.parse_gaia(bad, 500)


@pytest.mark.parametrize('change', [{'ra': float('nan')}, {'ref_epoch': 2000}, {'source_id': '4.47e18'}, {'dec': -91}])
def test_reject_invalid_astrometry(source, change):
    with pytest.raises(ref.ReferenceError): ref.parse_gaia(csv_bytes([{**source, **change}]), 500)


@pytest.mark.parametrize('args', [(float('nan'),0,.1), (360,0,.1), (0,91,.1), (0,0,1), (0,0,.1,501)])
def test_invalid_query_never_calls_network(args, monkeypatch):
    monkeypatch.setattr(ref.requests, 'get', lambda *a, **k: pytest.fail('Network reached'))
    with pytest.raises(ValueError): ref.fetch_gaia(*args)


@pytest.mark.parametrize('ra,dec', [(359.999, 0), (15, 89.9999), (269.4485,4.7394)])
def test_motion_against_astropy_and_epoch_identity(source,ra,dec):
    source = {**source, 'ra': ra, 'dec': dec}
    assert ref.expected_position(source, 2016) == pytest.approx((ra, dec), abs=1e-7)
    c = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, pm_ra_cosdec=source['pmra']*u.mas/u.yr,
                 pm_dec=source['pmdec']*u.mas/u.yr, obstime=Time(2016,format='jyear',scale='tcb'))
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')  # ERFA distance override is intentional for this no-distance oracle.
        expected = c.apply_space_motion(new_obstime=Time(2026,format='jyear',scale='tcb'))
    actual = SkyCoord(*ref.expected_position(source,2026),unit='deg')
    assert actual.separation(expected).arcsec < .0001
    assert 100 < actual.separation(c).arcsec < 110  # cannot silently show J2016 as J2026


def test_missing_motion_and_limits(source):
    assert ref.expected_position({**source,'pmra':None},2026) is None
    assert ref.expected_position({**source,'pmra':0,'pmdec':0},2026) == pytest.approx((source['ra'],source['dec']))
    with pytest.raises(ValueError): ref.expected_position(source,2100)


class Response:
    def __init__(self, raw, status=200): self.raw, self.status_code, self.closed = raw, status, False
    def __enter__(self): return self
    def __exit__(self,*a): self.closed=True
    def raise_for_status(self):
        if self.status_code != 200: raise requests.HTTPError(str(self.status_code))
    def iter_content(self,n):
        for i in range(0,len(self.raw),n): yield self.raw[i:i+n]


@pytest.mark.parametrize('status', [404,429,500,503])
def test_failed_gaia_is_not_empty_catalogue(status,monkeypatch):
    response=Response(b'failure',status)
    monkeypatch.setattr(ref.requests,'get',lambda *a,**k:response)
    with pytest.raises(ref.ReferenceError,match='no disponible'): ref.fetch_gaia(10,0,.1)
    assert response.closed


def test_timeout_and_size_guard(monkeypatch):
    def fail(*a,**k): raise requests.Timeout()
    monkeypatch.setattr(ref.requests,'get',fail)
    with pytest.raises(ref.ReferenceError,match='Timeout'): ref.fetch_gaia(10,0,.1)
    response=Response(b'x'*(ref.MAX_BYTES+1))
    monkeypatch.setattr(ref.requests,'get',lambda *a,**k:response)
    with pytest.raises(ref.ReferenceError,match='2 MiB'): ref.fetch_gaia(10,0,.1)
    assert response.closed


def test_provenance_query_and_html_safety(source,monkeypatch):
    seen={}
    def get(url,**kw): seen.update(url=url,**kw);return Response(csv_bytes([source]))
    monkeypatch.setattr(ref.requests,'get',get)
    result=ref.fetch_gaia(source['ra'],source['dec'],.1)
    assert 'TOP 501' in result['query'] and ',0.0500000000)' in result['query']
    assert seen['timeout']==(8,25) and seen['stream']
    assert len(result['sha256'])==64 and result['sources'][0]['source_id']==source['source_id']
    html=viewer_html(source['ra'],source['dec'],.1,result,error='</script><img src=x>')
    assert '</script><img' not in html
    payload=json.loads(html.split('const cfg=')[1].split(';\nconst el')[0])
    assert payload['fov']==.1 and payload['ra']==source['ra']
    assert payload['sources'][0]['expected'] != [source['ra'],source['dec']]


@pytest.mark.parametrize('mode',['success','wise_error','aladin_error'])
def test_iframe_independent_controls_and_failures(source,mode):
    node=shutil.which('node')
    assert node, 'Node.js is required for the reference viewer failure tests.'
    html=viewer_html(10,0,.1,{'sources':[source]})
    result=subprocess.run([node,str(Path(__file__).with_name('reference_view_harness.cjs')),mode],
                          input=html,encoding='utf-8',capture_output=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
