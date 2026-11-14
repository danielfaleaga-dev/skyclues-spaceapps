"""Independent synthetic DR1 fixtures; no IRSA access or existing cache required."""
import io
from types import SimpleNamespace

import numpy as np
import pytest
import requests
from astropy.io import fits
from astropy import units as u
from astropy_healpix import HEALPix

from skyclues import archive, config, spectral_cube as sc


@pytest.fixture
def cube(tmp_store, monkeypatch):
    # A small FITS with 102 distinct planes, known background and central source.
    n = 32
    image = np.broadcast_to(np.arange(102, dtype='f4')[:, None, None] + 10, (102, n, n)).copy()
    image[:, 16, 16] += 7
    image[50:52] = np.nan
    hits = np.where(np.isfinite(image), 4, 0).astype('i4')
    flags = np.zeros_like(hits)
    h = sc.display_wcs(60.81, 51.34, n * np.degrees(np.sqrt(4*np.pi/(12*4**10))), n).to_header()
    h['ORDER'], h['NPIX'], h['BUNIT'] = 5, 445, 'MJy/sr'
    primary = fits.PrimaryHDU()
    primary.header['BLANKCH'] = 'D3:17,D4:01'
    hdus = [primary]
    for name, data in [('IMAGE', image), ('NHITS', hits), ('FLAGS', flags)]:
        hdus.append(fits.ImageHDU(data, header=h, name=name))
    wave = np.linspace(.75, 5, 102, dtype='f4')
    cols = [fits.Column(name=k, format=fmt, array=a) for k, fmt, a in [
        ('DETECTOR', 'I', np.arange(102)//17+1), ('SUBCHAN', 'I', np.arange(102)%17+1),
        ('WAVELENGTH', 'E', wave), ('WL_MIN', 'E', wave-.01), ('WL_MAX', 'E', wave+.01),
        ('BANDWIDTH', 'E', np.full(102,.02)), ('R', 'E', wave/.02)]]
    hdus.append(fits.BinTableHDU.from_columns(cols, name='SPECTRAL_CHANNELS'))
    hdus.append(fits.BinTableHDU.from_columns([
        fits.Column(name='WAVELENGTHS', format='102E', array=[wave])], name='WCS-WAVE'))
    buf = io.BytesIO()
    fits.HDUList(hdus).writeto(buf)
    raw = buf.getvalue()
    calls = []
    def read(url, ranges, size, etag):
        calls.append(ranges)
        return {r: raw[r[0]:r[1]] for r in ranges}, '"synthetic"', len(raw), None
    monkeypatch.setattr(sc, '_request_ranges', read)
    monkeypatch.setattr(sc, '_tiles', {})
    monkeypatch.setattr(sc, '_cache_bytes', None)
    tile = sc.read_layout(445)
    monkeypatch.setattr(sc, 'tile_for', lambda *a, **k: tile)
    monkeypatch.setattr(sc, 'tile_boxes', lambda *a, **k: [sc.TileBox(tile, 0, 31, 0, 31)])
    return SimpleNamespace(tile=tile, raw=raw, calls=calls, image=image, hits=hits,
                           centre=tuple(map(float, tile.wcs.pixel_to_world_values(16, 16))))


def test_real_planes_metadata_and_verbatim_bytes(cube):
    t = cube.tile
    assert t.shape == (102,32,32) and t.bunit == 'MJy/sr'
    assert [c.number for c in t.channels if c.blank] == [51,52]
    with fits.open(io.BytesIO(cube.raw)) as hdus:
        for p in [0,16,17,49,50,51,62,101]:
            c = t.channels[p]
            assert c.number == 17*(c.detector-1)+c.subchannel == p+1
            assert c.wavelength_um == hdus['SPECTRAL_CHANNELS'].data['WAVELENGTH'][p]
            got = t.read_rows({'IMAGE':[p], 'NHITS':[p]}, 3, 8, 2, 7)
            np.testing.assert_array_equal(got['IMAGE'][0], hdus['IMAGE'].data[p,3:9,2:8])
            np.testing.assert_array_equal(got['NHITS'][0], hdus['NHITS'].data[p,3:9,2:8])
    assert all(b-a < len(cube.raw) for call in cube.calls for a,b in call)


def test_channel_changes_keep_wcs_and_region(cube):
    maps = [sc.channel_map(*cube.centre, .1, p) for p in [0,62,50,51]]
    for m in maps:
        assert (m.ra,m.dec,m.field_deg) == (*cube.centre,.1)
        np.testing.assert_array_equal(m.patches[0].image, cube.image[m.channel.plane])
        for got, expected in zip(m.patches[0].centres_world(),maps[0].patches[0].centres_world()):
            np.testing.assert_array_equal(got,expected)
    assert all(m.summary()['n_valid'] == 0 for m in maps[2:])


def test_injected_flux_background_and_missing_channels(cube):
    spec = sc.extract_spectrum(*cube.centre)
    for i,row in enumerate(spec.rows):
        if i in (50,51):
            assert row['status'] == 'blank' and row['flujo_mjy'] is None and row['pixel_mjysr'] is None
        else:
            assert row['status'] == 'ok'
            assert row['fondo_mjysr'] == pytest.approx(10+i)
            assert row['flujo_mjy'] == pytest.approx(7*cube.tile.pixel_solid_angle_sr*1e9, rel=1e-10)
            assert row['pixel_mjysr'] == 17+i
    assert not any('error' in k or 'uncertainty' in k for k in spec.rows[0])


@pytest.mark.parametrize('problem', ['nan', 'zero_hits', 'background', 'blank_value'])
def test_missing_data_never_becomes_a_measurement(cube, monkeypatch, problem):
    original = cube.tile.read_rows
    def changed(exts,y0,y1,x0=0,x1=None):
        out = original(exts,y0,y1,x0,x1)
        if 'IMAGE' in out:
            if problem == 'background':
                out['IMAGE'][0] = np.nan
            if y0 <= 16 <= y1:
                if problem == 'nan': out['IMAGE'][0,16-y0,16-x0] = np.nan
                if problem == 'blank_value': out['IMAGE'][50:52,16-y0,16-x0] = 100
        if 'NHITS' in out and problem == 'zero_hits': out['NHITS'][0,16-y0,16-x0] = 0
        return out
    monkeypatch.setattr(cube.tile, 'read_rows', changed)
    s = sc.extract_spectrum(*cube.centre)
    if problem == 'blank_value':
        assert all(s.rows[i]['pixel_mjysr'] is None for i in [50,51])
    else:
        assert s.rows[0]['flujo_mjy'] is None
        assert s.rows[0]['pixel_mjysr'] is None


def test_cache_batching_limits_and_etag(cube, monkeypatch):
    cube.calls.clear()
    want = [(i*8,i*8+4) for i in range(130)]
    first = sc.read_ranges(cube.tile.url,want,len(cube.raw),'v1')
    assert sorted(map(len,cube.calls)) == [2,64,64]
    cube.calls.clear()
    assert sc.read_ranges(cube.tile.url,want,len(cube.raw),'v1') == first
    assert not cube.calls
    sc.read_ranges(cube.tile.url,want,len(cube.raw),'v2')
    assert len(cube.calls) == 3
    with pytest.raises(ValueError): sc.read_ranges('x',[(0,len(cube.raw)+1)],len(cube.raw),None)
    monkeypatch.setattr(config,'CUBE_MAX_BYTES_PER_CALL',1)
    with pytest.raises(ValueError): sc.read_ranges('x',[(0,2)],len(cube.raw),None)


def test_layout_cache_memory_disk_refresh(cube, monkeypatch):
    calls=[]
    monkeypatch.setattr(sc,'read_layout',lambda *a: calls.append(a) or cube.tile)
    assert sc.open_tile(445) is cube.tile
    assert sc.open_tile(445) is cube.tile
    assert len(calls)==1
    sc._tiles.clear()
    assert sc.open_tile(445).headers == cube.tile.headers
    assert len(calls)==1
    sc.open_tile(445, refresh=True)
    assert len(calls)==2


def test_damaged_same_length_cache_is_refetched(cube):
    args=(cube.tile.url,[(0,4)],len(cube.raw),'v1')
    assert sc.read_ranges(*args)[(0,4)]==cube.raw[:4]
    path=sc._chunk_path(cube.tile.url,'v1',0,4)
    path.write_bytes(b'BAD!')
    cube.calls.clear()
    assert sc.read_ranges(*args)[(0,4)]==cube.raw[:4]
    assert len(cube.calls)==1


def test_cache_quota_stops_new_writes(cube,monkeypatch):
    monkeypatch.setattr(config,'CUBE_CACHE_MAX_MB',0)
    monkeypatch.setattr(sc,'_cache_bytes',0)
    sc.read_ranges(cube.tile.url,[(0,4)],len(cube.raw),'quota')
    assert not sc._chunk_path(cube.tile.url,'quota',0,4).exists()


@pytest.mark.parametrize('defect',['units','scale','channels','shape','blank'])
def test_incompatible_fits_metadata_is_rejected(cube,defect):
    t=sc.CubeTile(**cube.tile.to_dict())
    h=t.header('IMAGE').copy()
    if defect=='units': h['BUNIT']='Jy'
    if defect=='scale': h['BSCALE']=2
    if defect=='shape': h['NAXIS1']=31
    if defect=='channels': t.channels_table[0]['SUBCHAN']=2
    if defect=='blank':
        ph=t.header('PRIMARY').copy(); ph['BLANKCH']=''; t.headers['PRIMARY']=ph.tostring()
    t.headers['IMAGE']=h.tostring()
    t.__dict__.pop('_hcache',None)
    with pytest.raises(sc.CubeFormatError): sc._validate_layout(t)


def test_truncated_header_does_not_loop(monkeypatch):
    raw=b' '*2880
    def read(url,ranges,size,etag):
        return {r:raw[r[0]:r[1]] for r in ranges},'test',len(raw),None
    monkeypatch.setattr(sc,'_request_ranges',read)
    with pytest.raises(sc.CubeFormatError,match='sin END'): sc.read_layout(445)


def test_insufficient_background_is_flagged(cube,monkeypatch):
    original=cube.tile.read_rows
    def changed(exts,y0,y1,x0=0,x1=None):
        out=original(exts,y0,y1,x0,x1)
        if 'IMAGE' in out:
            yy,xx=np.mgrid[y0:y1+1,x0:(x1 if x1 is not None else 31)+1]
            out['IMAGE'][0,(xx-16)**2+(yy-16)**2>9]=np.nan
        return out
    monkeypatch.setattr(cube.tile,'read_rows',changed)
    r=sc.extract_spectrum(*cube.centre).rows[0]
    assert r['status']=='no_background' and r['flujo_mjy'] is None
    assert r['pixel_mjysr']==17


@pytest.mark.parametrize('subpixels',[0,-1,26,2.5])
def test_subpixel_work_is_bounded(cube,subpixels):
    with pytest.raises(ValueError): sc.extract_spectrum(*cube.centre,subpixels=subpixels)


class Response:
    def __init__(self, status=206, body=b'abcd', **headers):
        self.status_code, self.body, self.headers, self.read = status, body, headers, False
    def __enter__(self): return self
    def __exit__(self,*a): pass
    def iter_content(self,n):
        self.read=True
        yield self.body


def request(monkeypatch, response, spec=None, etag='v1'):
    def get(url, **kw):
        assert kw['stream'] is True
        assert kw['headers']['Range'].startswith('bytes=')
        return response
    monkeypatch.setattr(sc,'_session',lambda: SimpleNamespace(get=get))
    return sc._request_ranges('https://example.test/cube',spec or [(0,4)],100,etag)


@pytest.mark.parametrize('status,error',[(200,sc.RangeNotHonoured),(404,archive.ArchivePermanentError),
                                        (502,archive.ArchiveTransientError),(429,archive.ArchiveTransientError)])
def test_unexpected_status_body_is_not_read(monkeypatch,status,error):
    r=Response(status)
    with pytest.raises(error): request(monkeypatch,r)
    assert not r.read


@pytest.mark.parametrize('headers,error',[
    ({'ETag':'v2','Content-Range':'bytes 0-3/100'},sc.FileChangedError),
    ({'ETag':'v1','Content-Range':'bytes 0-3/101'},sc.FileChangedError),
    ({'ETag':'v1','Content-Range':'bytes 0-3/*'},sc.CubeFormatError),
    ({'ETag':'v1','Content-Range':'bytes 0-3/2'},sc.CubeFormatError),
    ({'Content-Range':'bytes 0-3/100'},sc.FileChangedError),
    ({'ETag':'v1','Content-Range':'bytes 4-7/100'},sc.CubeFormatError),
    ({'ETag':'v1','Content-Length':'320000000'},sc.RangeNotHonoured),
])
def test_invalid_range_identity_rejected(monkeypatch,headers,error):
    with pytest.raises(error): request(monkeypatch,Response(**headers))


def test_multipart_and_single_integrity(monkeypatch):
    r=Response(**{'ETag':'v1','Content-Range':'bytes 0-3/100'})
    assert request(monkeypatch,r)[0][(0,4)] == b'abcd'
    body=b'--xyz\r\nContent-Range: bytes 0-3/100\r\n\r\nabcd\r\n--xyz\r\nContent-Range: bytes 8-11/100\r\n\r\nefgh\r\n--xyz--\r\n'
    r=Response(body=body,**{'ETag':'v1','Content-Type':'multipart/byteranges; boundary="xyz"'})
    assert request(monkeypatch,r,[(0,4),(8,12)])[0] == {(0,4):b'abcd',(8,12):b'efgh'}
    with pytest.raises(sc.CubeFormatError):
        request(monkeypatch,Response(body=body[:-9],**r.headers),[(0,4),(8,12)])
    with pytest.raises(archive.ArchiveTransientError):
        request(monkeypatch,Response(body=b'ab',**{'ETag':'v1','Content-Range':'bytes 0-3/100'}))


def test_retries_only_transient(monkeypatch):
    for exc,n in [(archive.ArchiveTransientError,config.HTTP_RETRIES),
                  (archive.ArchivePermanentError,1),(sc.FileChangedError,1),(sc.CubeFormatError,1)]:
        calls,waits=[],[]
        def fail(): calls.append(1); raise exc('test')
        with pytest.raises(exc): sc._with_retries(fail,sleep=waits.append)
        assert len(calls)==n and len(waits)==n-1


def test_healpix_against_independent_library():
    rng=np.random.default_rng(1234)
    ra=np.r_[rng.uniform(0,360,3000),60.8109955,0,90,180,270]
    dec=np.r_[rng.uniform(-90,90,3000),51.3404038,90,-90,90,-90]
    for order in [0,5,14]:
        oracle=HEALPix(nside=2**order,order='nested')
        np.testing.assert_array_equal(sc.healpix_nest(order,ra,dec),oracle.lonlat_to_healpix(ra*u.deg,dec*u.deg))
    assert sc.healpix_nest(5,60.8109955,51.3404038)==445


def test_missing_cube_dates_keep_catalogue_epoch(monkeypatch):
    from skyclues.targets import PRESETS
    a=next(v['astrometry'] for k,v in PRESETS.items() if '0855' in k)
    monkeypatch.setattr(sc,'tile_for',lambda *a: SimpleNamespace(mjd_range=(None,None)))
    ra,dec,info=sc.cube_epoch_position(a)
    assert (ra,dec)==(a.ra_deg,a.dec_deg)
    assert info['propagated'] is False and info['warning']

