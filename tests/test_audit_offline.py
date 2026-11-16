"""Offline tests for the independent-audit corrections SC-01..SC-11.

No network: archive and catalogue calls are replaced by fakes. Synthetic
arrays and FITS exercise the logic only and are never shown as observations.
"""

import math

import numpy as np
import pytest
import requests
from astropy.io import fits

from skyclues import archive, config, sequence
from skyclues.astrometry import Astrometry
from skyclues.compare import finast_status, spectral_status
from skyclues.quality import (DOCUMENTED_BITS, FlagDefinitions, flag_census, read_flag_definitions,
                              valid_pixel_mask)
from skyclues.targets import CHALLENGE_WISE0855, M101, WISE0855, validate_coordinates, validate_fov_deg

# SIMBAD basic data (2026-11-14), used as fixed inputs.
BARNARD = Astrometry("NAME Barnard's star", 269.4520769586187, 4.693364966576667, 2000.0,
                     -801.551, 10362.394, 546.9759, -110.11, "SIMBAD / Gaia DR3")
EPS_IND_B = Astrometry("* eps Ind B", 331.04414658852124, -56.782844195116105, 2000.0,
                       3981.977, -2466.832, 270.658, None, "SIMBAD / Gaia DR3")


def _sep(a, b):
    from skyclues.geometry import separation_deg

    return float(separation_deg(a[0], a[1], b[0], b[1])) * 3600


# ------------------------------------------------------------------ SC-01 proper motion
def test_challenge_coordinates_are_the_wise_era_position_not_j2000():
    ch = (CHALLENGE_WISE0855["ra_deg"], CHALLENGE_WISE0855["dec_deg"])
    ts = np.arange(2009.5, 2011.5, 0.02)
    d = [_sep(WISE0855.position_at(t), ch) for t in ts]
    k = int(np.argmin(d))
    assert d[k] < 0.6 and abs(ts[k] - 2010.40) < 0.05           # epoch of the challenge coordinates
    assert _sep(WISE0855.position_at(2000.0), ch) > 80          # so they are NOT J2000.0
    # at SPHEREx epochs the object is ~2 arcmin from the challenge coordinates
    off_2026 = _sep(WISE0855.position_at(2026.33), ch)
    assert 120 < off_2026 < 135
    assert 205 < _sep(WISE0855.position_at(2026.33), (WISE0855.ra_deg, WISE0855.dec_deg)) < 220


@pytest.mark.parametrize("astro, expected_arcsec", [(WISE0855, 211.7), (BARNARD, 270.4), (EPS_IND_B, 121.6)])
def test_propagation_matches_proper_motion_times_elapsed_time(astro, expected_arcsec):
    moved = _sep(astro.position_at(2026.0), (astro.ra_deg, astro.dec_deg))
    linear = astro.total_pm_arcsec_yr * 26.0
    assert moved == pytest.approx(linear, rel=0.01)             # parallax/perspective: < 1 %
    assert moved == pytest.approx(expected_arcsec, abs=1.0)


def test_parallax_is_applied_with_the_right_amplitude():
    no_plx = Astrometry(**{**WISE0855.to_dict(), "parallax_mas": None})
    shifts = [_sep(WISE0855.position_at(2026.0 + f), no_plx.position_at(2026.0 + f))
              for f in np.linspace(0, 1, 25)]
    assert 0.30 < max(shifts) < 0.50                            # parallax 0.439 arcsec
    assert any("parallax" in w for w in no_plx.warnings())


def test_static_target_and_missing_parameter_warnings():
    assert M101.position_at(2026.4) == (M101.ra_deg, M101.dec_deg)
    assert not M101.has_proper_motion and "No proper motion" in M101.warnings()[0]
    assert any("radial velocity" in w for w in EPS_IND_B.warnings())
    assert BARNARD.warnings() == []
    assert Astrometry.from_dict(WISE0855.to_dict()) == WISE0855
    # MJD and Julian-year inputs agree
    from astropy.time import Time

    t = Time(2026.3, format="jyear", scale="tdb")
    assert _sep(WISE0855.position_at(t.mjd), WISE0855.position_at(2026.3)) < 1e-3


def test_search_is_centred_on_the_position_at_the_observation_epoch(monkeypatch):
    from types import SimpleNamespace

    from astropy.time import Time

    mjds = [Time(y, format="jyear").mjd for y in (2025.62, 2026.30, 2026.34, 2026.71)]
    recs = [SimpleNamespace(detector=6, mjd_mid=m) for m in mjds]
    queried = []
    monkeypatch.setattr(sequence.archive, "query_images", lambda ra, dec, **k: queried.append((ra, dec)) or recs)
    monkeypatch.setattr(sequence, "build_candidates", lambda *a, **k: [])
    monkeypatch.setattr(sequence, "estimate_wavelengths", lambda c: None)
    _, rep = sequence.find_sequence(0.0, 0.0, 0.1, log=lambda m: None, astrometry=WISE0855)
    t = rep["target"]
    assert t["centre"]["epoch_jyear"] == 2026.3                 # median of the record epochs, 0.1 yr
    assert _sep((t["ra_deg"], t["dec_deg"]), WISE0855.position_at(2026.3)) < 1e-6
    assert _sep((t["ra_deg"], t["dec_deg"]), (WISE0855.ra_deg, WISE0855.dec_deg)) > 200
    assert t["astrometry"]["pmra_masyr"] == WISE0855.pmra_masyr
    assert _sep(queried[0], (0.0, 0.0)) > 1000                  # the (ra, dec) arguments are not used


# ------------------------------------------------------------------ SC-02 / SC-11 thresholds
def test_spectral_mismatch_above_warning_threshold_is_rejected():
    assert spectral_status(0.0) == "pass"
    assert spectral_status(config.SPECTRAL_PASS_BW) == "pass"
    assert spectral_status(0.26) == "warn"
    assert spectral_status(config.SPECTRAL_WARN_BW) == "warn"
    for v in (0.51, 0.65, 15.43, 50.0, float("nan"), None):
        assert spectral_status(v) == "fail", v


def test_finast_two_or_more_or_missing_is_rejected():
    assert finast_status([0, 0, 0]) == "pass"
    assert finast_status([0, 1]) == "warn"                      # partial solution
    for bad in ([0, 2], [3], [None], ["x"], [-1]):
        assert finast_status(bad) == "fail", bad


# ------------------------------------------------------------------ SC-06 FLAGS
def _real_style_header():
    """FLAGS header as shipped in DR1/QR3: MSKN keys only up to bit 28."""
    h = fits.Header()
    for bit, name in DOCUMENTED_BITS.items():
        if bit <= 28:
            h[f"MSKN{bit:04d}"] = name
    return h


def test_satellite_halo_from_documentation_when_header_stops_at_bit_28():
    defs = read_flag_definitions(_real_style_header())
    assert defs.bits[29] == "SATELLITE_HALO" and "documentation" in defs.source
    strict = defs.bitmask(("unusable", "artifact"))
    assert strict & (1 << 29)
    img, var = np.ones((1, 4)), np.ones((1, 4))
    flags = np.array([[0, 1 << 29, 1 << 21, (1 << 29) | (1 << 21)]], np.int32)
    assert valid_pixel_mask(img, flags, var, defs).tolist() == [[True, False, True, False]]


def test_undefined_active_bits_are_masked_and_reported():
    defs = read_flag_definitions(_real_style_header())
    img, var = np.ones((1, 5)), np.ones((1, 5))
    flags = np.array([[0, 1 << 30, 1 << 3, np.int32(-2 ** 31), 1 << 12]], np.int32)   # 30, 3, 31 undefined
    strict = valid_pixel_mask(img, flags, var, defs, ("unusable", "artifact"))
    assert strict.tolist() == [[True, False, False, False, True]]                  # FULLSAMPLE (12) is info
    # undefined bits never count as "unusable" (that class stays the documented list)
    assert valid_pixel_mask(img, flags, var, defs, ("unusable",)).all()
    rows = {r["name"]: r for r in flag_census(flags, defs)}
    for b in (3, 30, 31):
        assert rows[f"UNDEFINED_BIT_{b}"]["pixels"] == 1 and rows[f"UNDEFINED_BIT_{b}"]["class"] == "artifact"
    assert "UNDEFINED_BIT_4" not in rows                                            # inactive: not listed


def test_header_definitions_win_and_conflicts_are_recorded():
    h = _real_style_header()
    h["MSKN0029"] = "SOMETHING_NEW"
    defs = read_flag_definitions(h)
    assert defs.bits[29] == "SOMETHING_NEW" and defs.conflicts == {29: ("SOMETHING_NEW", "SATELLITE_HALO")}
    assert defs.bitmask(("unusable", "artifact")) & (1 << 29)                     # unknown name -> artifact


# ------------------------------------------------------------------ SC-03 HTTP retries
class _R:
    def __init__(self, status, content=b"", headers=None):
        self.status_code, self.content, self.text, self.headers = status, content, str(status), headers or {}


def _scripted(monkeypatch, script):
    calls = []

    def fake_get(url, **kw):
        calls.append(url)
        item = script[min(len(calls) - 1, len(script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(archive.requests, "get", fake_get)
    return calls


def test_transient_errors_are_retried_with_backoff_and_no_final_sleep(monkeypatch):
    sleeps = []
    calls = _scripted(monkeypatch, [_R(502), _R(503), _R(200, b"ok")])
    r = archive.http_get("https://example.invalid/x", sleep=sleeps.append)
    assert r.content == b"ok" and len(calls) == 3
    assert sleeps == [config.HTTP_BACKOFF_S, 2 * config.HTTP_BACKOFF_S]

    sleeps.clear()
    calls = _scripted(monkeypatch, [_R(503)])
    with pytest.raises(archive.ArchiveTransientError):
        archive.http_get("https://example.invalid/x", sleep=sleeps.append)
    assert len(calls) == config.HTTP_RETRIES and len(sleeps) == config.HTTP_RETRIES - 1   # none after the last
    assert sum(sleeps) <= config.HTTP_DEADLINE_S


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410])
def test_permanent_http_errors_fail_at_once(monkeypatch, status):
    sleeps = []
    calls = _scripted(monkeypatch, [_R(status)])
    with pytest.raises(archive.ArchivePermanentError):
        archive.http_get("https://example.invalid/x", sleep=sleeps.append)
    assert len(calls) == 1 and sleeps == []


def test_timeouts_retry_after_cap_and_deadline(monkeypatch):
    sleeps = []
    _scripted(monkeypatch, [requests.Timeout("read timed out"), requests.ConnectionError("reset"), _R(200, b"ok")])
    assert archive.http_get("https://example.invalid/x", sleep=sleeps.append).content == b"ok"
    sleeps.clear()
    _scripted(monkeypatch, [_R(429, headers={"Retry-After": "600"}), _R(200, b"ok")])
    archive.http_get("https://example.invalid/x", sleep=sleeps.append)
    assert sleeps == [config.HTTP_BACKOFF_MAX_S]                       # server asked 600 s: capped
    sleeps.clear()
    calls = _scripted(monkeypatch, [_R(503)])
    with pytest.raises(archive.ArchiveTransientError):
        archive.http_get("https://example.invalid/x", sleep=sleeps.append, deadline_s=5)
    assert len(calls) == 2 and sleeps == [config.HTTP_BACKOFF_S]       # next wait would pass the deadline


def _fake_sia2(monkeypatch, capabilities_ok: bool, query_errors=()):
    """SIA2Service stand-in. ``capabilities_ok`` False -> the capabilities route raises
    HTTP 502 (as observed on 14-11-2026); ``query_errors``: codes raised by successive
    searches before one succeeds. Records every service built and every search."""
    import pyvo

    log = {"built": [], "searches": []}
    errors = list(query_errors)

    class FakeSvc:
        def __init__(self, route):
            self.route = route

        def search(self, **k):
            log["searches"].append((self.route, k))
            if errors:
                code = errors.pop(0)
                raise pyvo.dal.DALServiceError(f"HTTP {code}", code=code, url=config.SIA_URL)
            return type("R", (), {"to_table": lambda self: []})()

    def ctor(url, session=None, check_baseurl=True):
        assert url == config.SIA_URL
        log["built"].append(check_baseurl)
        if check_baseurl and not capabilities_ok:
            raise pyvo.dal.DALServiceError("502 Server Error: Proxy Error", code=502,
                                           url=url + "/capabilities")
        return FakeSvc("capabilities" if check_baseurl else "direct")

    monkeypatch.setattr(archive.pyvo.dal, "SIA2Service", ctor)
    return log


def test_capabilities_502_but_direct_query_works(monkeypatch):
    sleeps = []
    monkeypatch.setattr(archive.time, "sleep", sleeps.append)
    ok = _fake_sia2(monkeypatch, capabilities_ok=True)
    archive._query_images_live(10.0, 20.0, 1 / 3600, config.WIDE_COLLECTIONS)
    assert archive.last_sia2_route == "capabilities" and ok["built"] == [True]

    log = _fake_sia2(monkeypatch, capabilities_ok=False)
    assert archive._query_images_live(10.0, 20.0, 1 / 3600, config.WIDE_COLLECTIONS) == []
    assert log["built"] == [True, False]                       # one capabilities attempt, then direct
    assert archive.last_sia2_route.startswith("direct") and sleeps == []
    # identical scientific query on both routes: same collections, position and radius
    assert [k for _, k in log["searches"]] == [k for _, k in ok["searches"]]
    assert [k["collection"] for _, k in log["searches"]] == list(config.WIDE_COLLECTIONS)


def test_direct_query_failures_keep_their_classification(monkeypatch):
    sleeps = []
    monkeypatch.setattr(archive.time, "sleep", sleeps.append)
    log = _fake_sia2(monkeypatch, capabilities_ok=False, query_errors=[502])
    archive._query_images_live(10.0, 20.0, 1 / 3600, ("spherex_dr1",))   # transient: retried, then OK
    assert len(log["searches"]) == 2 and sleeps == [config.HTTP_BACKOFF_S]

    sleeps.clear()
    _fake_sia2(monkeypatch, capabilities_ok=False, query_errors=[502] * 10)
    with pytest.raises(archive.ArchiveTransientError):                    # SIA really unavailable
        archive._query_images_live(10.0, 20.0, 1 / 3600, ("spherex_dr1",))
    assert len(sleeps) == config.HTTP_RETRIES - 1

    sleeps.clear()
    _fake_sia2(monkeypatch, capabilities_ok=False, query_errors=[400])
    with pytest.raises(archive.ArchivePermanentError):
        archive._query_images_live(10.0, 20.0, 1 / 3600, ("spherex_dr1",))
    assert sleeps == []


def test_error_classification():
    import pyvo

    assert archive.classify_exception(requests.Timeout()) is archive.ArchiveTransientError
    assert archive.classify_exception(pyvo.dal.DALServiceError("x", code=503)) is archive.ArchiveTransientError
    assert archive.classify_exception(pyvo.dal.DALServiceError("x", code=404)) is archive.ArchivePermanentError


# ------------------------------------------------------------------ SC-04 FITS integrity
def test_truncated_or_incomplete_fits_is_rejected(l2_bytes):
    good = l2_bytes()
    archive.validate_fits_bytes(good)
    for cut in (len(good) - 2880, len(good) // 2, len(good) - 100, 2880):
        with pytest.raises(archive.CorruptFitsError):
            archive.validate_fits_bytes(good[:cut])
    with pytest.raises(archive.CorruptFitsError):
        archive.validate_fits_bytes(b"<html>busy</html>" + b" " * 2863)
    hdul = fits.HDUList.fromstring(good)
    del hdul["WCS-WAVE"]
    import io

    buf = io.BytesIO()
    hdul.writeto(buf)
    with pytest.raises(archive.CorruptFitsError, match="WCS-WAVE"):
        archive.validate_fits_bytes(buf.getvalue())


URL = "https://example.invalid/level2_T_D1_spx_l2b-v1-2026-001.fits?center=1,2&size=0.1"


def test_partial_download_is_never_cached(tmp_store, monkeypatch, l2_bytes):
    good = l2_bytes()
    sleeps = []
    monkeypatch.setattr(archive.time, "sleep", sleeps.append)
    calls = _scripted(monkeypatch, [_R(200, good[: len(good) // 2]), _R(200, good)])
    path = archive.fetch(URL)
    assert path.read_bytes() == good and len(calls) == 2              # retried after the truncated body
    _scripted(monkeypatch, [_R(200, good[:5760])])
    path.unlink()
    with pytest.raises(archive.CorruptFitsError):
        archive.fetch(URL)
    assert not path.exists() and not list(path.parent.glob("*.part"))  # nothing incomplete left behind


def test_corrupt_cache_file_is_quarantined_and_downloaded_again(tmp_store, monkeypatch, l2_bytes):
    good = l2_bytes()
    path = archive._cache_path(URL)
    archive.atomic_write(path, good[:5760])                             # e.g. an older, truncated download
    calls = _scripted(monkeypatch, [_R(200, good)])
    assert archive.fetch(URL).read_bytes() == good and len(calls) == 1
    quarantined = list(path.parent.glob(path.name + ".corrupt-*"))
    assert len(quarantined) == 1 and quarantined[0].read_bytes() == good[:5760]   # kept, not deleted


def test_corrupt_reference_file_is_never_modified(tmp_store, monkeypatch, l2_bytes):
    ref = config.REFERENCE_DIR / archive._cache_path(URL).name
    bad = l2_bytes()[:5760]
    archive.atomic_write(ref, bad)
    calls = _scripted(monkeypatch, [_R(200, l2_bytes())])
    with pytest.raises(archive.CorruptFitsError, match="Reference file"):
        archive.fetch(URL)
    assert calls == [] and ref.read_bytes() == bad
    assert isinstance(archive.fetch_many([URL])[URL], archive.CorruptFitsError)
    with pytest.raises(archive.CorruptFitsError):
        archive.redownload(URL, ref)
    assert ref.read_bytes() == bad


def test_redownload_replaces_a_mismatching_cache_copy(tmp_store, monkeypatch, l2_bytes):
    old, new = l2_bytes(tag="old"), l2_bytes(tag="new")
    path = archive.atomic_write(archive._cache_path(URL), old)
    _scripted(monkeypatch, [_R(200, new)])
    assert archive.redownload(URL, path).read_bytes() == new
    assert [p.read_bytes() for p in path.parent.glob(path.name + ".corrupt-*")] == [old]


# ------------------------------------------------------------------ SC-05 partial retrieval
def test_failed_cutouts_are_counted_and_classified(monkeypatch):
    from types import SimpleNamespace

    rec = lambda n: SimpleNamespace(access_url=f"https://example.invalid/{n}.fits", file_name=f"{n}.fits",  # noqa: E731
                                    detector=2, mjd_mid=61000.0)
    members = [SimpleNamespace(rec=rec("a")), SimpleNamespace(rec=rec("b")), SimpleNamespace(rec=rec("c"))]
    prop = {"n": 3, "detector": 2, "members": members, "spread_field_bw_est": 0.0, "same_collection": True,
            "span_days": 10.0, "min_margin_px": 50}
    monkeypatch.setattr(sequence.archive, "query_images", lambda *a, **k: [m.rec for m in members])
    monkeypatch.setattr(sequence, "build_candidates", lambda *a, **k: [])
    monkeypatch.setattr(sequence, "estimate_wavelengths", lambda c: None)
    monkeypatch.setattr(sequence, "propose_sequences", lambda c, n: [prop])
    monkeypatch.setattr(sequence.archive, "fetch_many", lambda urls, progress=None: {
        u: (archive.ArchiveTransientError("503") if "/a." in u else archive.ArchivePermanentError("404"))
        for u in urls})
    _, rep = sequence.find_sequence(10.0, 20.0, 0.1, log=lambda m: None)
    assert rep["retrieval"] == {"n_requested": 3, "n_failed": 3, "complete": False, "n_transient": 1}
    assert {f["kind"] for f in rep["retrieval_failures"]} == {"transitorio", "permanente"}
    assert rep["selected"] is None


# ------------------------------------------------------------------ SC-08 input validation
@pytest.mark.parametrize("ra, dec", [("nan", 0), (float("nan"), 0), (0, float("inf")), (400, 0), (360, 0),
                                     (-0.1, 0), (10, -95), (10, 90.5), ("abc", 0), (None, None)])
def test_invalid_coordinates_are_rejected_not_clamped(ra, dec):
    with pytest.raises(ValueError):
        validate_coordinates(ra, dec)


def test_valid_coordinate_edges_and_fov_validation():
    assert validate_coordinates("0", "-90") == (0.0, -90.0)
    assert validate_coordinates(359.9999, 90) == (359.9999, 90.0)
    assert validate_fov_deg("0.1") == 0.1
    for bad in (0.01, 5, "nan", "x", None):
        with pytest.raises(ValueError):
            validate_fov_deg(bad)


def test_find_sequence_rejects_invalid_input_before_any_query(monkeypatch):
    def no_query(*a, **k):
        raise AssertionError("IRSA must not be queried")

    monkeypatch.setattr(sequence.archive, "query_images", no_query)
    for ra, dec, fov in ((float("nan"), 10.0, 0.1), (400.0, -95.0, 0.1), (10.0, 10.0, 5.0)):
        with pytest.raises(ValueError):
            sequence.find_sequence(ra, dec, fov, log=lambda m: None)
    assert math.isnan(float("nan"))
