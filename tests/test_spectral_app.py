"""Streamlit integration with synthetic cube + real offline Time Explorer references."""
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest
from skyclues import config, archive, spectral_cube as sc, spectrum_page as page
from test_spectral_offline import cube  # shared synthetic FITS fixture, explicitly never real data

APP=str(Path(__file__).resolve().parents[1]/'app.py')


def test_simple_level_preserves_hidden_measurement_controls(app_cube):
    at=spectral_app(app_cube)
    at.slider(key='sx_rap').set_value(3.0).run()
    at.radio(key='sx_quantity').set_value(list(page.QUANTITY_LABELS)[1]).run()
    at.radio(key='sx_layer').set_value(list(page.LAYERS)[1]).run()
    at.button(key='sx_extract').click().run()
    original=at.session_state['sx_spec_params']
    region=at.session_state['sx_region_key']
    at.button_group(key='level').set_value('Sencillo').run()
    assert not at.exception
    assert at.session_state['sx_spec_params']==original
    assert at.session_state['sx_region_key']==region
    assert not any(s.key=='sx_rap' for s in at.slider)
    assert not any(r.key in ('sx_layer','sx_quantity') for r in at.radio)
    assert not any('Método y limitaciones' in x.label or 'Tabla del espectro' in x.label for x in at.expander)
    at.button_group(key='level').set_value('Científico').run()
    assert not at.exception
    assert at.slider(key='sx_rap').value==3.0
    assert at.radio(key='sx_quantity').value==list(page.QUANTITY_LABELS)[1]
    assert at.radio(key='sx_layer').value==list(page.LAYERS)[1]
    assert at.session_state['sx_spec_params']==original


def test_simple_rgb_preserves_channels_and_contrast(app_cube):
    from skyclues import multiband_page
    at=spectral_app(app_cube)
    at.button_group(key='sx_mode').set_value(multiband_page.MODES[1]).run()
    at.radio(key='mb_stretch').set_value(list(multiband_page.STRETCH_LABELS)[1]).run()
    channels=[at.selectbox(key='mb_'+r).value for r in ('R','G','B')]
    at.button_group(key='level').set_value('Sencillo').run()
    assert not at.exception
    assert not any('Procedencia' in x.label for x in at.expander)
    assert [at.selectbox(key='mb_'+r).value for r in ('R','G','B')]==channels
    at.button_group(key='level').set_value('Científico').run()
    assert not at.exception
    assert at.radio(key='mb_stretch').value==list(multiband_page.STRETCH_LABELS)[1]
    assert [at.selectbox(key='mb_'+r).value for r in ('R','G','B')]==channels

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
    at.session_state['level']='Científico'
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
    at.button_group(key='nav').set_value('Tiempo').run()
    assert not at.exception
    assert at.session_state['region']['ra']==pytest.approx(key[0],abs=1e-6)
    assert at.session_state['region']['dec']==pytest.approx(key[1],abs=1e-6)
    assert at.session_state['region']['fov']==.1
    assert not any(m.label=='Épocas' for m in at.metric)


def test_time_transfer_keeps_wise_region_not_expected_marker(app_cube,monkeypatch):
    monkeypatch.setattr(page,'cached_epoch',lambda _: (app_cube.centre[0],app_cube.centre[1],
        {'propagated':True,'mjd_mid':60000,'date_mid':'2023-02-25','date_beg':'2023-01-01',
         'date_end':'2023-05-01','motion_over_inputs_arcsec':3}))
    at=AppTest.from_file(APP,default_timeout=30)
    at.session_state['level']='Científico'
    at.run()
    stem=next(s for s in config.VALIDATED_EXAMPLES if 'wise' in s)
    at.button(key='example_'+stem).click().run()
    assert not at.exception
    shared=at.session_state['region'].copy()
    at.button_group(key='nav').set_value('Espectro').run()
    assert not at.exception
    assert at.session_state['sx_region_key']==(round(shared['ra'],6),round(shared['dec'],6),shared['fov'])
    text=' '.join(str(x.proto) for x in at if hasattr(x, 'proto'))
    assert 'no es una época efectiva' in text and 'no una detección' in text
    at.button_group(key='nav').set_value('Tiempo').run()
    assert not at.exception
    assert at.session_state['region']['ra']==pytest.approx(shared['ra'],abs=1e-6)
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
    assert any('no válid' in e.value for e in at.error)


def test_click_callback_uses_native_pixel_coordinates(app_cube,monkeypatch):
    pick={'ra':123.456789,'dec':-12.345678}
    state={'sx_field':{'selection':{'pick':[pick]}}}
    monkeypatch.setattr(page.st,'session_state',state)
    page._set_pick_from_chart()
    assert state['sx_pick_ra']==pick['ra'] and state['sx_pick_dec']==pick['dec']


def test_single_channel_chart_frame_does_not_depend_on_browser_width(cube):
    """Regression: the vertical domain was ``[-R*height/width, R*height/width]``; a chart created while
    its column had no width got an infinite domain and drew nothing (blank image), in both the
    single-position and the A/B charts."""
    import json
    import numpy as np
    from skyclues import spectral_view as sv
    from test_multiband import synth_map
    yy, xx = np.mgrid[0:32, 0:32].astype(float)
    ra, dec = cube.centre
    cmap = synth_map(cube.tile, 10, 1 + xx + yy, ra=ra, dec=dec, fov=1.5)
    png, info = sv.field_png(cmap, 'image')
    pixels = sv.pixel_table(cmap)
    R = info['half_arcsec']
    ap = sc.Aperture(2.0, 4.0, 6.0)
    pick_b = (ra + 0.1, dec + 0.1)
    for kw in ({}, {'pick': (ra, dec), 'aperture': ap}, {'pick': (ra, dec), 'aperture': ap, 'pick_b': pick_b}):
        spec = sv.field_chart(png, info, pixels, cmap, target=(ra, dec), **kw).to_dict()
        text = json.dumps(spec)
        assert 'height/width' not in text and '"container"' not in text
        assert spec['width'] == spec['height']
        domains = [enc['scale']['domain'] for layer in spec['layer'] for ch, enc in layer.get('encoding', {}).items()
                   if ch in ('x', 'y') and 'scale' in enc]
        assert domains and all(d == [-R, R] for d in domains)


def test_chart_click_survives_the_restore_of_kept_widget_state(monkeypatch):
    """Simple level: the page stashes the pick position every run and gives it back before drawing
    (spectrum_page.render). A click, applied by the chart callback before that restore, must not be
    overwritten by the older stashed copy (blocker found in the final evaluation)."""
    from skyclues import multiband_page
    state={'sx_field':{'selection':{'pick':[{'ra':83.9,'dec':-5.3}]}},'sx_region_key':(1.0,2.0,.1),
           'sx_pick_ra':83.8,'sx_pick_dec':-5.4,'opt_sx_active':'Punto A'}
    monkeypatch.setattr(page.st,'session_state',state)
    keys=page.SINGLE_STATE_KEYS
    multiband_page.stash(keys)                     # end of the previous run in Sencillo: old position kept aside
    page._set_pick_from_chart()                    # the click: callback runs before the script
    multiband_page.restore(keys)                   # start of this run: kept values are given back
    assert (state['sx_pick_ra'],state['sx_pick_dec'])==(83.9,-5.3)
    multiband_page.stash(keys)                     # next run keeps the new position, not the old one
    multiband_page.restore(keys)
    assert (state['sx_pick_ra'],state['sx_pick_dec'])==(83.9,-5.3)
