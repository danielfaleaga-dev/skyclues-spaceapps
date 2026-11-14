import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def synthetic_l2_bytes(shape=(8, 8), tag: str = "TEST") -> bytes:
    """A structurally complete Level-2-like MEF (IMAGE, FLAGS, VARIANCE, ZODI,
    WCS-WAVE) for cache/integrity logic tests. Synthetic: never shown as data."""
    import numpy as np
    from astropy.io import fits

    ny, nx = shape
    hdus = [fits.PrimaryHDU(header=fits.Header([("OBJECT", tag)]))]
    for name, dtype in (("IMAGE", np.float32), ("FLAGS", np.int32), ("VARIANCE", np.float32),
                        ("ZODI", np.float32)):
        hdus.append(fits.ImageHDU(np.ones((ny, nx), dtype), name=name))
    cols = [fits.Column(name="X", format="3E", array=np.zeros((1, 3))),
            fits.Column(name="Y", format="3E", array=np.zeros((1, 3))),
            fits.Column(name="VALUES", format="18E", array=np.zeros((1, 18)))]
    hdus.append(fits.BinTableHDU.from_columns(cols, name="WCS-WAVE"))
    buf = io.BytesIO()
    fits.HDUList(hdus).writeto(buf)
    return buf.getvalue()


@pytest.fixture
def l2_bytes():
    return synthetic_l2_bytes


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    """Empty, isolated cache and reference store."""
    from skyclues import config

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "REFERENCE_DIR", tmp_path / "reference")
    return tmp_path
