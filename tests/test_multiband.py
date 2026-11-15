"""Multiband false-colour composition: offline tests with the synthetic DR1 fixture (never real data)."""
import io
import json
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from matplotlib import image as mpimg
from matplotlib.colors import to_rgba
from streamlit.testing.v1 import AppTest

from skyclues import archive, config, multiband as mb, multiband_page as mpage, multiband_view as mv
from skyclues import spectral_cube as sc, spectrum_page as page
from test_spectral_offline import cube  # noqa: F401 - synthetic FITS fixture, explicitly never real data

APP = str(Path(__file__).resolve().parents[1] / 'app.py')
NUMS = {'R': 90, 'G': 40, 'B': 10}
# The fixture's pixels are HEALPix order-10 pixels (~3.4'): a 1.5 deg field holds ~540 of them.
FOV = 1.5


def synth_map(tile, plane, image, nhits=None, ra=None, dec=None, fov=FOV, boxes=((0, 0),)):
    """ChannelMap with explicit arrays on the synthetic tile's real WCS (one patch per box)."""
    image = np.asarray(image, float)
    nhits = np.where(np.isfinite(image), 4, 0) if nhits is None else nhits
    patches = []
    for x0, y0 in boxes:
        patches.append(sc.Patch(tile, x0, y0, image.copy(), np.asarray(nhits).copy(), np.zeros(image.shape, 'i4')))
    return sc.ChannelMap(tile.channels[plane], ra, dec, fov, patches)


@pytest.fixture
def grads(cube):
    """Three different, known channel images: x gradient (R), y gradient (G), radial (B)."""
    yy, xx = np.mgrid[0:32, 0:32].astype(float)
    arrays = {NUMS['R'] - 1: 1 + xx, NUMS['G'] - 1: 100 + 3 * yy, NUMS['B'] - 1: -5 + np.hypot(xx - 16, yy - 16)}
    calls = []

    def map_fn(ra, dec, fov, plane):
        calls.append((ra, dec, fov, plane))
        return synth_map(cube.tile, plane, arrays[plane], ra=ra, dec=dec, fov=fov)
    return arrays, map_fn, calls


def build(cube, map_fn, mode='independiente', nums=NUMS):
    return mb.build(*cube.centre, FOV, cube.tile.channels, dict(nums), mode, map_fn=map_fn)


# 1 ------------------------------------------------------------------ channel <-> wavelength
def test_channels_and_wavelengths_come_from_the_fits_table(cube):
    comp = build(cube, None)                       # through the real range reader of the fixture
    with fits.open(io.BytesIO(cube.raw)) as h:
        tab = h['SPECTRAL_CHANNELS'].data
        for r, n in NUMS.items():
            c = comp.channels[r]
            assert c.number == n and c.plane == n - 1 == comp.maps[r].channel.plane
            assert c.wavelength_um == tab['WAVELENGTH'][n - 1]
            assert c.bandwidth_um == tab['BANDWIDTH'][n - 1]
            assert (c.wl_min_um, c.wl_max_um) == (tab['WL_MIN'][n - 1], tab['WL_MAX'][n - 1])
    prov = json.loads(json.dumps(comp.provenance(), default=str))
    assert prov['canales']['R']['lambda_um'] == pytest.approx(float(tab['WAVELENGTH'][89]))
    assert mv.assignment_table(comp)['canal'].tolist() == [90, 40, 10]


# 2 ------------------------------------------------------------------ empty channels excluded
@pytest.mark.parametrize('bad', [51, 52])
def test_blank_channels_cannot_enter_a_composition(cube, bad):
    chans = cube.tile.channels
    assert {51, 52}.isdisjoint(c.number for c in mb.selectable(chans))
    assert {51, 52}.isdisjoint(mb.default_numbers(chans).values())
    calls = []
    for role in mb.ROLES:
        with pytest.raises(ValueError, match='BLANKCH'):
            mb.build(*cube.centre, FOV, chans, {**NUMS, role: bad}, map_fn=lambda *a: calls.append(a))
    assert calls == []                            # refused before any read


@pytest.mark.parametrize('nums,match', [({'R': 1, 'G': 1, 'B': 2}, 'distintos'), ({'R': 1, 'G': 2, 'B': 103}, 'inexistente'),
                                         ({'R': 1, 'G': 2}, 'exactamente'), ({'R': 1, 'G': 2, 'B': 3.0}, 'inexistente')])
def test_invalid_selections_are_refused(cube, nums, match):
    with pytest.raises(ValueError, match=match):
        mb.select_channels(cube.tile.channels, nums)


# 3 ------------------------------------------------------------------ integrity of the planes
def test_three_planes_are_verbatim_and_never_modified(cube):
    comp = build(cube, None)
    before = {r: (comp.maps[r].patches[0].image.copy(), comp.maps[r].patches[0].nhits.copy()) for r in mb.ROLES}
    for r, n in NUMS.items():
        np.testing.assert_array_equal(comp.maps[r].patches[0].image, cube.image[n - 1])
        np.testing.assert_array_equal(comp.maps[r].patches[0].nhits, cube.hits[n - 1])
    mv.composite_png(comp)
    mv.channel_panel_png(comp, 'G')
    mv.pixel_table(comp)
    for r in mb.ROLES:
        np.testing.assert_array_equal(comp.maps[r].patches[0].image, before[r][0])
        np.testing.assert_array_equal(comp.maps[r].patches[0].nhits, before[r][1])
    tab = mv.pixel_table(comp)                    # the hover table keeps the original values
    assert set(tab['R'].dropna().round(4)) <= set(np.round(cube.image[89].ravel(), 4))


# 4 ------------------------------------------------------------------ spatial alignment
def test_alignment_verified_and_no_resampling(cube, grads):
    _, map_fn, _ = grads
    comp = build(cube, map_fn)
    a = comp.alignment
    assert a['verificada'] and not a['varias_teselas'] and a['teselas'][0]['tesela'] == 445
    assert comp.provenance()['remuestreo'].startswith('ninguno')
    for u, v in zip(comp.maps['R'].patches[0].centres_world(), comp.maps['B'].patches[0].centres_world()):
        np.testing.assert_array_equal(u, v)


@pytest.mark.parametrize('defect', ['shift', 'shape', 'etag', 'wcs', 'centre', 'patches'])
def test_misaligned_planes_are_refused(cube, grads, defect):
    arrays, map_fn, _ = grads
    maps = {r: map_fn(*cube.centre, FOV, n - 1) for r, n in NUMS.items()}
    p = maps['G'].patches[0]
    if defect == 'shift':
        p.x0 += 1
    elif defect == 'shape':
        maps['G'].patches[0] = sc.Patch(p.tile, 0, 0, p.image[:-1], p.nhits[:-1], p.flags[:-1])
    elif defect in ('etag', 'wcs'):
        t = sc.CubeTile(**{**cube.tile.to_dict()})
        if defect == 'etag':
            t.etag = '"other"'
        else:
            h = t.header('IMAGE')
            h['CRVAL1'] += 0.01
            t.headers['IMAGE'] = h.tostring()
            t.__dict__.pop('_hcache', None)
        maps['G'].patches[0] = sc.Patch(t, p.x0, p.y0, p.image, p.nhits, p.flags)
    elif defect == 'centre':
        maps['G'] = sc.ChannelMap(maps['G'].channel, maps['G'].ra + 1e-3, maps['G'].dec, FOV, maps['G'].patches)
    else:
        maps['G'].patches.append(maps['G'].patches[0])
    with pytest.raises(mb.MultibandAlignmentError):
        mb.check_alignment(maps)


# 5 ------------------------------------------------------------------ masks and NaN
def test_missing_data_in_any_channel_is_never_coloured(cube, grads):
    arrays, _, _ = grads
    arrays = {k: v.copy() for k, v in arrays.items()}
    arrays[NUMS['R'] - 1][16, 16] = np.nan                 # NaN in R only
    arrays[NUMS['B'] - 1][16, 10] = np.inf                 # invalid value in B only
    hits_g = np.full((32, 32), 4)
    hits_g[10, 16] = 0                                     # NHITS = 0 in G only

    def map_fn(ra, dec, fov, plane):
        nh = hits_g if plane == NUMS['G'] - 1 else None
        return synth_map(cube.tile, plane, arrays[plane], nh, ra=ra, dec=dec, fov=fov)
    comp = build(cube, map_fn)
    rgb = comp.rgb(0)
    for y, x in [(16, 16), (16, 10), (10, 16)]:
        assert np.isnan(rgb[y, x]).all()                  # no partial colour
    assert np.isfinite(rgb[15, 15]).all()
    cov = comp.coverage
    assert cov['parcial'] == 3 and cov['tres_canales'] == cov['n_campo'] - 3
    assert cov['con_datos']['R'] == cov['n_campo'] - 1
    assert any('Cobertura distinta' in w for w in comp.warnings)
    assert comp.stretch.n_pixels == cov['tres_canales']
    tab = mv.pixel_table(comp)
    row = tab[(tab.R.isna()) & (tab.G.notna())]
    assert (row['cobertura'] == 'datos solo en 2 canal(es)').all() and len(row) == 1
    # rendered: the masked cell is mask colour / white hatch, a valid cell has its exact colour
    png, info = mv.composite_png(comp)
    img = mpimg.imread(io.BytesIO(png))[..., :3]
    frame = mv.frame_for(comp)
    n = info['npix']

    def screen(x, y):
        r, d = cube.tile.wcs.pixel_to_world_values(x, y)
        X, Y = frame.world_to_pixel_values(r, d)
        return int(round(n - 1 - float(Y))), int(round(float(X)))
    i, j = screen(16, 16)
    patch = img[i - 3:i + 4, j - 3:j + 4].reshape(-1, 3)
    mask = np.array(to_rgba(mv.MASK_COLOR)[:3])
    # every screen pixel lies on the mask -> white segment (hatch lines are antialiased)
    t = (patch - mask) / (1 - mask)
    assert np.all(np.ptp(t, axis=1) < 0.03) and t.min() > -0.02 and t.max() < 1.02
    assert (t.mean(axis=1) < 0.02).any() and (t.mean(axis=1) > 0.5).any()       # both fill and hatch
    i, j = screen(15, 15)
    np.testing.assert_allclose(img[i, j], rgb[15, 15], atol=1.5 / 255)


def test_insufficient_common_data_is_refused(cube, grads):
    arrays, _, _ = grads

    def map_fn(ra, dec, fov, plane):
        a = arrays[plane].copy()
        if plane == NUMS['B'] - 1:
            a[:, 3:] = np.nan                              # B covers almost nothing of the field
        return synth_map(cube.tile, plane, a, ra=ra, dec=dec, fov=fov)
    with pytest.raises(mb.InsufficientDataError):
        build(cube, map_fn)


def test_all_nan_channel_is_refused_not_painted(cube, grads):
    arrays, _, _ = grads

    def map_fn(ra, dec, fov, plane):
        a = np.full((32, 32), np.nan) if plane == NUMS['G'] - 1 else arrays[plane]
        return synth_map(cube.tile, plane, a, ra=ra, dec=dec, fov=fov)
    with pytest.raises(mb.InsufficientDataError, match='0 píxeles'):
        build(cube, map_fn)


# 6 ------------------------------------------------------------------ RGB assignment
def test_each_colour_carries_its_assigned_channel(cube, grads):
    arrays, map_fn, _ = grads
    comp = build(cube, map_fn)
    rgb = comp.rgb(0)
    ok = comp.common_valid(0)
    for k, r in enumerate(mb.ROLES):
        expected = comp.stretch.apply(r, arrays[NUMS[r] - 1])
        np.testing.assert_array_equal(rgb[..., k][ok], expected[ok])
    assert np.all(np.diff(rgb[16, 2:30, 0]) >= 0) and np.ptp(rgb[2:30, 16, 0]) == 0      # R follows x only
    assert np.all(np.diff(rgb[2:30, 16, 1]) >= 0) and np.ptp(rgb[16, 2:30, 1]) == 0      # G follows y only
    swapped = build(cube, map_fn, nums={'R': 10, 'G': 40, 'B': 90})
    np.testing.assert_array_equal(swapped.rgb(0)[..., 0], rgb[..., 2])
    np.testing.assert_array_equal(swapped.rgb(0)[..., 2], rgb[..., 0])
    assert any('orden cromático' in w for w in swapped.warnings)
    assert not any('orden cromático' in w for w in comp.warnings)


# 7 ------------------------------------------------------------------ stretch reproducibility
@pytest.mark.parametrize('mode', list(mb.STRETCH_MODES))
def test_stretch_is_documented_and_reproducible(cube, grads, mode):
    arrays, map_fn, _ = grads
    a, b = build(cube, map_fn, mode), build(cube, map_fn, mode)
    assert a.stretch == b.stretch
    np.testing.assert_array_equal(a.rgb(0), b.rgb(0))
    assert mv.composite_png(a)[0] == mv.composite_png(b)[0]
    spec = mb.StretchSpec.from_dict(json.loads(json.dumps(a.stretch.to_dict())))
    assert spec == a.stretch
    # independent formula: asinh(x / a) / asinh(1 / a), x = clip((v - vmin) / (vmax - vmin), 0, 1)
    ok = a.common_valid(0)
    for r in mb.ROLES:
        v = arrays[NUMS[r] - 1][ok]
        lo, hi = np.percentile(np.concatenate([arrays[NUMS[q] - 1][a.field_masks[0] & ok] for q in mb.ROLES])
                               if mode == 'comun' else v[a.field_masks[0][ok]], [1, 99.5])
        assert (a.stretch.vmin[r], a.stretch.vmax[r]) == pytest.approx((lo, hi))
        x = np.clip((v - lo) / (hi - lo), 0, 1)
        np.testing.assert_allclose(a.stretch.apply(r, v), np.arcsinh(x / .1) / np.arcsinh(1 / .1), atol=1e-12)
    if mode == 'comun':
        assert len(set(a.stretch.vmin.values())) == len(set(a.stretch.vmax.values())) == 1
        assert not any('Escala independiente' in w for w in a.warnings)
    else:
        assert any('NO reflejan' in w for w in a.warnings)


def test_flat_channel_is_reported_not_amplified(cube, grads):
    arrays, _, _ = grads

    def map_fn(ra, dec, fov, plane):
        a = np.full((32, 32), 7.0) if plane == NUMS['B'] - 1 else arrays[plane]
        return synth_map(cube.tile, plane, a, ra=ra, dec=dec, fov=fov)
    comp = build(cube, map_fn)
    assert comp.stretch.degenerate == ('B',)
    assert np.ptp(comp.rgb(0)[..., 2][comp.common_valid(0)]) == 0
    assert any('no tiene contraste' in w for w in comp.warnings)


# 8 ------------------------------------------------------------------ several tiles
def test_field_split_over_several_tiles(cube, grads):
    arrays, _, _ = grads
    other = sc.CubeTile(**{**cube.tile.to_dict(), 'ipix': 446})
    other.headers = dict(cube.tile.headers)

    def map_fn(ra, dec, fov, plane):
        left = sc.Patch(cube.tile, 0, 0, arrays[plane][:, :16].copy(), np.full((32, 16), 4), np.zeros((32, 16), 'i4'))
        right = sc.Patch(other, 16, 0, arrays[plane][:, 16:].copy(), np.full((32, 16), 4), np.zeros((32, 16), 'i4'))
        return sc.ChannelMap(cube.tile.channels[plane], ra, dec, fov, [left, right])
    comp = build(cube, map_fn)
    assert [t['tesela'] for t in comp.alignment['teselas']] == [445, 446]
    assert any('varias teselas' in w for w in comp.warnings)
    whole = build(cube, grads[1])
    assert comp.coverage == whole.coverage and comp.stretch == whole.stretch
    np.testing.assert_array_equal(np.hstack([comp.rgb(0), comp.rgb(1)]), whole.rgb(0))
    assert set(mv.pixel_table(comp)['tesela']) == {445, 446}

    def swapped(ra, dec, fov, plane):                      # G read in the opposite tile order
        m = map_fn(ra, dec, fov, plane)
        if plane == NUMS['G'] - 1:
            m.patches.reverse()
        return m
    with pytest.raises(mb.MultibandAlignmentError):
        build(cube, swapped)


# 9 ------------------------------------------------------------------ centre and FOV preserved
def test_centre_and_field_are_passed_unchanged(cube, grads):
    _, map_fn, calls = grads
    comp = build(cube, map_fn)
    assert (comp.ra, comp.dec, comp.field_deg) == (*cube.centre, FOV)
    assert calls == [(*cube.centre, FOV, NUMS[r] - 1) for r in mb.ROLES]
    prov = comp.provenance()
    assert (prov['centro_ra_deg'], prov['centro_dec_deg'], prov['campo_deg']) == (*cube.centre, FOV)


# 11 ----------------------------------------------------------------- external failures
@pytest.mark.parametrize('error', [archive.ArchiveTransientError, archive.ArchivePermanentError, sc.RangeNotHonoured,
                                   sc.FileChangedError, sc.CubeFormatError])
def test_reader_failures_propagate_without_a_composite(cube, error):
    n = []

    def map_fn(ra, dec, fov, plane):
        n.append(plane)
        if len(n) == 2:
            raise error('test')
        return synth_map(cube.tile, plane, np.ones((32, 32)), ra=ra, dec=dec, fov=fov)
    with pytest.raises(error):
        build(cube, map_fn)


# ------------------------------------------------------------------- Streamlit (10, 9, 11, 12)
@pytest.fixture
def app_cube(cube, monkeypatch):
    monkeypatch.setattr(config, 'REFERENCE_DIR', Path(APP).parent / 'data' / 'reference')

    def no_network(*a, **k):
        raise AssertionError('Offline app test attempted network access')
    monkeypatch.setattr(archive.requests.sessions.Session, 'request', no_network)
    cached = [page.cached_map, page.cached_pixels, page.cached_png, page.cached_spectrum, page.cached_epoch]
    for fn in cached:
        fn.clear()
    mpage.clear_caches()
    yield cube
    for fn in cached:
        fn.clear()
    mpage.clear_caches()


def spectral_app(cube, channel=63):
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state['level'] = 'Científico'
    at.query_params = {'explorer': 'espectral', 'ra': str(cube.centre[0]), 'dec': str(cube.centre[1]), 'fov': '.5',
                       'canal': str(channel)}
    at.run()
    assert not at.exception
    return at


def no_widget_state_warning(at):
    return not any('default value' in w.value or 'Session State' in w.value for w in at.warning)


def test_switch_to_multiband_and_back_keeps_region_channel_and_pick(app_cube):
    at = spectral_app(app_cube)
    key, url = at.session_state['sx_region_key'], dict(at.query_params)
    at.select_slider(key='sx_channel').set_value(94).run()
    at.number_input(key='sx_pick_ra').set_value(app_cube.centre[0] + .001).run()
    at.slider(key='sx_rap').set_value(3.0).run()
    at.button_group(key='sx_mode').set_value(mpage.MODES[1]).run()
    assert not at.exception
    offered = {int(o.split()[1]) for o in at.selectbox(key='mb_R').options}
    assert len(offered) == 100 and {51, 52}.isdisjoint(offered)
    at.selectbox(key='mb_R').set_value(90).run()
    at.selectbox(key='mb_B').set_value(10).run()
    assert not at.exception
    assert at.session_state['sx_region_key'] == key
    assert all(at.query_params[k] == url[k] for k in ('ra', 'dec', 'fov'))
    text = ' '.join(m.value for m in at.markdown)
    assert 'Convención de visualización, no color real' in text and 'no detecta' in text
    lam = app_cube.tile.channels[89].wavelength_um
    assert any(c.value.startswith(f'λ {lam:.3f} µm') for c in at.caption)
    assert not any(e for e in at.error)
    # back to single-channel: channel, pick and aperture preserved, spectrum shown again
    at.button_group(key='sx_mode').set_value(mpage.MODES[0]).run()
    assert not at.exception and no_widget_state_warning(at)
    assert at.session_state['sx_channel'] == 94
    assert at.number_input(key='sx_pick_ra').value == pytest.approx(app_cube.centre[0] + .001)
    assert at.slider(key='sx_rap').value == 3.0
    assert at.session_state['sx_region_key'] == key
    # what the browser draws, not only the server value: a re-created widget shows its proto
    # default unless the value is sent with set_value (found in the browser test)
    ch = at.select_slider(key='sx_channel').proto
    assert ch.set_value and ch.raw_value[0].startswith('94 ')
    ra = at.number_input(key='sx_pick_ra').proto
    assert ra.set_value and ra.value == pytest.approx(app_cube.centre[0] + .001)
    rap = at.slider(key='sx_rap').proto
    assert (list(rap.value) if rap.set_value else list(rap.default)) == [3.0]
    # and the multiband selection survives the round trip, also on screen
    at.button_group(key='sx_mode').set_value(mpage.MODES[1]).run()
    assert not at.exception and no_widget_state_warning(at)
    assert at.selectbox(key='mb_R').value == 90 and at.selectbox(key='mb_B').value == 10
    for role, n in (('R', 90), ('B', 10)):
        sb = at.selectbox(key=f'mb_{role}').proto
        assert sb.set_value and sb.raw_value.startswith(f'Canal {n} ')


def test_multiband_reader_failure_is_visible_without_image(app_cube, monkeypatch):
    def fail(*a):
        raise archive.ArchiveTransientError('test')
    monkeypatch.setattr(page, 'cached_map', fail)
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state['level'] = 'Científico'
    at.query_params = {'explorer': 'espectral', 'ra': str(app_cube.centre[0]), 'dec': str(app_cube.centre[1]),
                       'fov': '.5'}
    at.session_state['sx_mode'] = mpage.MODES[1]
    at.run()
    assert not at.exception
    assert any('composición' in e.value and 'temporalmente' in e.value for e in at.error)
    assert not at.metric


def test_insufficient_coverage_message_in_app(app_cube, monkeypatch):
    real = page.cached_map

    def sparse(ra, dec, fov, plane):
        m = real(ra, dec, fov, plane)
        p = m.patches[0]
        img = np.full(p.image.shape, np.nan)
        return sc.ChannelMap(m.channel, ra, dec, fov, [sc.Patch(p.tile, p.x0, p.y0, img, p.nhits, p.flags)])
    monkeypatch.setattr(page, 'cached_map', sparse)
    at = AppTest.from_file(APP, default_timeout=60)
    at.session_state['level'] = 'Científico'
    at.query_params = {'explorer': 'espectral', 'ra': str(app_cube.centre[0]), 'dec': str(app_cube.centre[1]),
                       'fov': '.5'}
    at.session_state['sx_mode'] = mpage.MODES[1]
    at.run()
    assert not at.exception
    assert any('Datos insuficientes' in e.value for e in at.error)


def test_returning_to_spectrum_explorer_with_the_same_region_keeps_working(app_cube):
    """Regression (already present in 2ec4881): Streamlit drops the pick widgets while Time Explorer
    is shown, and a second visit with an unchanged region raised KeyError 'sx_pick_ra'."""
    at = AppTest.from_file(APP, default_timeout=60).run()
    stem = next(s for s in config.VALIDATED_EXAMPLES if 'm101' in s)
    at.button(key='example_' + stem).click().run()
    explorer = ['Tiempo', 'Espectro']
    for _ in range(2):
        at.button_group(key='nav').set_value(explorer[1]).run()
        assert not at.exception
        at.button_group(key='nav').set_value(explorer[0]).run()
        assert not at.exception
    at.button_group(key='nav').set_value(explorer[1]).run()
    assert not at.exception
    assert at.session_state['sx_pick_ra'] == pytest.approx(at.session_state['sx_region_key'][0])
    at.button_group(key='sx_mode').set_value(mpage.MODES[1]).run()           # also through the multiband mode
    at.button_group(key='nav').set_value(explorer[0]).run()
    at.button_group(key='nav').set_value(explorer[1]).run()
    assert not at.exception
    at.button_group(key='sx_mode').set_value(mpage.MODES[0]).run()
    assert not at.exception
