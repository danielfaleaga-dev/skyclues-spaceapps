"""Multiband composition with authentic SPHEREx DR1 cube data (IRSA byte ranges, isolated cache)."""
import numpy as np
import pytest

from scripts.validate_multiband import independent_checks
from skyclues import multiband as mb, multiband_view as mv, spectral_cube as sc

pytestmark = pytest.mark.network


@pytest.fixture
def fresh(tmp_store, monkeypatch):
    monkeypatch.setattr(sc, '_tiles', {})
    monkeypatch.setattr(sc, '_cache_bytes', None)


@pytest.mark.parametrize('ra,dec,fov,tiles', [(210.802429, 54.34875, 0.05, [2858]),
                                              (213.737429, 54.34875, 0.1, [2856, 2857, 2858, 2859])])
def test_authentic_composite_values_alignment_and_seams(fresh, ra, dec, fov, tiles):
    chans = sc.tile_for(ra, dec).channels
    assert [c.number for c in chans if c.blank] == [51, 52]
    for bad in (51, 52):
        with pytest.raises(ValueError, match='BLANKCH'):
            mb.select_channels(chans, {'R': bad, 'G': 40, 'B': 10})
    sc.io_stats(reset=True)
    comp = mb.build(ra, dec, fov, chans, mb.default_numbers(chans))
    io = sc.io_stats()
    assert io['bytes_network'] < 4 * 2**20                     # rows of three planes, never whole tiles
    assert [t['tesela'] for t in comp.alignment['teselas']] == tiles
    for r, c in comp.channels.items():
        assert comp.maps[r].channel == c and c.wl_min_um <= c.wavelength_um <= c.wl_max_um
    checks = independent_checks(comp)
    assert checks['duplicados_entre_teselas'] == checks['faltan_respecto_a_healpix'] == 0
    assert checks['sobran_respecto_a_healpix'] == 0 and checks['pixeles_campo'] == comp.coverage['n_campo']
    assert comp.coverage['fraccion_tres_canales'] > 0.99
    rgb = np.concatenate([comp.rgb(i)[comp.common_valid(i)] for i in range(len(comp.patches))])
    assert np.isfinite(rgb).all() and rgb.min() >= 0 and rgb.max() <= 1
    png, _ = mv.composite_png(comp)
    again = mb.build(ra, dec, fov, chans, mb.default_numbers(chans))
    assert mv.composite_png(again)[0] == png
