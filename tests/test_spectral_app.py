"""Streamlit integration with synthetic cube + real offline Time Explorer references."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from skyclues import config, archive, spectral_cube as sc, spectrum_page as page
from test_spectral_offline import cube  # shared synthetic FITS fixture, explicitly never real data

APP=str(Path(__file__).resolve().parents[1]/'app.py')

@pytest.fixture
def app_cube(cube,monkeypatch):
    # Time reference files remain read-only; synthetic byte cache is isolated by cube.
    monkeypatch.setattr(config,'REFERENCE_DIR',Path(APP).parent/'data'/'reference')
    def no_network(*a,**k): raise AssertionError('Offline app test attempted network access')
    monkeypatch.setattr(archive.requests.sessions.Session,'request',no_network)
    cached=[page.cached_map,page.cached_pixels,page.cached_png,page.cached_spectrum,page.cached_epoch]
    for fn in cached: fn.clear()
    yield cube
    for fn in cached: fn.clear()


def spectral_app(cube,channel=63):
    at=AppTest.from_file(APP,default_timeout=30)
    at.query_params={'explorer':'espectral','ra':str(cube.centre[0]),'dec':str(cube.centre[1]),'fov':'.1','canal':str(channel)}
    at.run()
    assert not at.exception
    return at


def test_url_channels_pick_extraction_and_return(app_cube):
    at=spectral_app(app_cube)
    key=at.session_state['sx_region_key']
    for channel in [51,52,94]:
        at.select_slider(key='sx_channel').set_value(channel).run()
        assert not at.exception
        assert at.session_state['sx_region_key']==key
        assert at.query_params['canal']==str(channel)
        if channel in [51,52]: assert any('sin datos en DR1' in w.value for w in at.warning)
    old=at.session_state['sx_spec_params']
    at.number_input(key='sx_pick_ra').set_value(app_cube.centre[0]+.001).run()
    assert at.session_state['sx_spec_params']==old
    assert any('espectro anterior' in c.value for c in at.caption)
    at.button(key='sx_extract').click().run()
    assert not at.exception
    assert at.session_state['sx_spec_params'][0]==round(app_cube.centre[0]+.001,6)
    at.button(key='sx_to_time').click().run()
    assert not at.exception
    assert at.number_input(key='ra_in').value==pytest.approx(key[0],abs=1e-6)
    assert at.number_input(key='dec_in').value==pytest.approx(key[1],abs=1e-6)
    assert at.radio(key='fov_preset').value=='6′'
    assert not any(m.label=='Épocas' for m in at.metric)


def test_time_transfer_keeps_wise_region_not_expected_marker(app_cube,monkeypatch):
    monkeypatch.setattr(page,'cached_epoch',lambda _: (app_cube.centre[0],app_cube.centre[1],
        {'propagated':True,'mjd_mid':60000,'date_mid':'2023-02-25','date_beg':'2023-01-01',
         'date_end':'2023-05-01','motion_over_inputs_arcsec':3}))
    at=AppTest.from_file(APP,default_timeout=30).run()
    stem=next(s for s in config.VALIDATED_EXAMPLES if 'wise' in s)
    at.button(key='example_'+stem).click().run()
    assert not at.exception
    shared=at.session_state['shared_region'].copy()
    at.button(key='to_spectrum').click().run()
    assert not at.exception
    assert at.session_state['sx_region_key']==(round(shared['ra'],6),round(shared['dec'],6),shared['fov'])
    text=' '.join(md.value for md in at.markdown)
    assert 'no es una época efectiva' in text and 'no una detección' in text
    at.button(key='sx_to_time').click().run()
    assert not at.exception
    assert at.number_input(key='ra_in').value==pytest.approx(shared['ra'],abs=1e-6)
    assert 'report' not in at.session_state


@pytest.mark.parametrize('error,text',[(sc.RangeNotHonoured,'lectura parcial'),(sc.FileChangedError,'cambió'),
    (sc.CubeFormatError,'estructura documentada'),(archive.ArchiveTransientError,'temporalmente'),
    (archive.ArchivePermanentError,'rechazó')])
def test_cube_errors_are_visible_without_partial_spectrum(app_cube,monkeypatch,error,text):
    def fail(*a): raise error('test')
    monkeypatch.setattr(page,'channel_list',fail)
    at=spectral_app(app_cube)
    assert any(text in e.value for e in at.error)
    assert not at.metric


@pytest.mark.parametrize('query',[{'ra':'nan','dec':'10'},{'ra':'400','dec':'-95'},{'fov':'9'}])
def test_invalid_spectral_url_never_reads_cube(app_cube,monkeypatch,query):
    def fail(*a): raise AssertionError('must not read cube')
    monkeypatch.setattr(page,'channel_list',fail)
    at=AppTest.from_file(APP,default_timeout=30)
    at.query_params={'explorer':'espectral',**query}
    at.run()
    assert not at.exception
    assert any('URL no válidos' in e.value for e in at.error)


def test_click_callback_uses_native_pixel_coordinates(app_cube,monkeypatch):
    pick={'ra':123.456789,'dec':-12.345678}
    state={'sx_field':{'selection':{'pick':[pick]}}}
    monkeypatch.setattr(page.st,'session_state',state)
    page._set_pick_from_chart()
    assert state['sx_pick_ra']==pick['ra'] and state['sx_pick_dec']==pick['dec']
