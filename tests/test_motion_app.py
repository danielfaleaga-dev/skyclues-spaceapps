"""«Buscar algo que se mueve» inside Time Explorer, plus one real-data reproduction (network)."""
import json
import math
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from skyclues import config, motion, motion_page, references

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_saved_investigations_are_real_reports_only():
    saved = motion_page.saved_investigations()
    assert saved, "results/motion_*.json"
    for label, path in saved.items():
        r = json.loads(path.read_text(encoding="utf-8"))
        assert r["outcome"] in motion.OUTCOME_LABELS and r["outcome_label"] in label
        assert not path.stem.startswith("motion_search_")
        assert r["method"].startswith("skyclues-motion")
        assert all(im["sha256"] and im["cutout_url"].startswith("https://irsa.ipac.caltech.edu/") for im in r["images"])


def test_motion_tab_renders_and_gaia_outage_is_explained(monkeypatch):
    def down(*a, **k):   # SIMULATED external outage of the ESA Gaia archive
        raise references.ReferenceError("Gaia DR3 (ESA) no responde.")
    monkeypatch.setattr(motion_page, "_gaia", down)
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    assert any(t.label == "Buscar algo que se mueve" for t in at.tabs)
    assert at.selectbox(key="mv_saved").options
    at.button(key="mv_run").click().run()
    assert not at.exception
    out = at.session_state["mv_result"]["result"]
    assert out["outcome"] != motion.MOTION_MEASURED
    assert any("Gaia" in s for s in out["reasons"] + out.get("warnings", []))


@pytest.mark.network
def test_real_eps_ind_b_d3_reproduces_from_cached_originals():
    """REAL data: the 12 cached SPHEREx cutouts of results/motion_eps_ind_b_d3.json and a new Gaia
    DR3 query reproduce the saved measurement (files are read-only; SHA-256 must match)."""
    from skyclues import archive, fitsdata
    from skyclues.astrometry import Astrometry
    saved = json.loads((config.RESULTS_DIR / "motion_eps_ind_b_d3.json").read_text(encoding="utf-8"))
    urls = [f["cutout_url"] for f in saved["files"]]
    got = archive.fetch_many(urls)
    frames = []
    for f, u in zip(saved["files"], urls):
        assert archive.sha256(got[u]) == f["sha256"]
        frames.append(motion.MotionFrame(fitsdata.load(got[u]), {"collection": f["collection"]}, u, got[u], f["sha256"]))
    c = saved["cutout_centre"]
    gaia = references.fetch_gaia(c["ra"], c["dec"], saved["selection"]["field_deg"])
    inv = motion.investigate(frames, (saved["source"]["selected_ra"], saved["source"]["selected_dec"]), gaia=gaia,
                             astrometry=Astrometry.from_dict(saved["astrometry"]))
    r = motion.to_jsonable(inv)
    assert r["outcome"] == saved["outcome"] == motion.MOTION_MEASURED
    a, b = r["displacement"], saved["displacement"]
    assert math.hypot(a["dxi"] - b["dxi"], a["deta"] - b["deta"]) < 0.05
    for f, u in zip(saved["files"], urls):
        assert archive.sha256(got[u]) == f["sha256"]


def test_extended_baseline_offers_images_per_season(monkeypatch):
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception
    at.radio(key="mv_images").set_value(motion_page.IMAGE_MODES[1]).run()
    assert not at.exception
    assert at.select_slider(key="mv_per_season").value == motion.PER_SEASON
