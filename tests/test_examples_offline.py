"""SC-09: the validated examples open with NO network and an EMPTY cache,
from the byte-identical copies in data/reference (provenance in MANIFEST.json)."""

import json

import pytest
import requests

from skyclues import archive, config
from skyclues.sequence import load_sequence, report_urls

REF = config.REFERENCE_DIR


def _no_network(*a, **k):
    raise AssertionError("network access attempted")


@pytest.mark.skipif(not (REF / "MANIFEST.json").exists(), reason="run scripts/bundle_reference.py")
@pytest.mark.parametrize("name", list(config.VALIDATED_EXAMPLES))
def test_validated_example_opens_offline(name, tmp_path, monkeypatch):
    import pyvo

    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "empty_cache")
    monkeypatch.setattr(requests, "get", _no_network)
    monkeypatch.setattr(requests.Session, "request", _no_network)
    monkeypatch.setattr(pyvo.dal, "SIA2Service", _no_network)
    rep = json.loads((config.RESULTS_DIR / f"{name}.json").read_text(encoding="utf-8"))
    manifest = json.loads((REF / "MANIFEST.json").read_text(encoding="utf-8"))["files"]
    for url, f in zip(report_urls(rep), rep["selected"]["frames"]):
        path = archive.local_copy(url)
        assert path is not None and path.parent == REF
        m = manifest[path.name]
        assert m["sha256"] == f["sha256"] == archive.sha256(path) and m["bytes"] == path.stat().st_size
        assert m["cutout_url"] == url and name in m["used_by"] and m["release"]
    seq = load_sequence(rep)                         # SHA-256 verified against the report
    assert seq.n >= 2 and seq.admissible
    assert not (tmp_path / "empty_cache").exists() or not list((tmp_path / "empty_cache").glob("*.fits"))
