"""Access to SPHEREx spectral images at NASA/IPAC IRSA.

* Discovery: IVOA SIA2 (``https://irsa.ipac.caltech.edu/SIA``) through pyvo.
* Retrieval: IRSA IBE cutouts (``<access_url>?center=ra,dec&size=deg``), which
  keep every extension of the Level-2 MEF (IMAGE, FLAGS, VARIANCE, ZODI, EPSF,
  WCS-WAVE).

Downloaded files are stored byte-for-byte as served by IRSA in
``data/cache`` and are never modified. Writes are atomic (unique temporary
name + rename), and one process never downloads the same URL twice at the
same time, so concurrent app sessions share the cache safely.

``data/reference`` (optional, read-only) may hold verified copies of the
cutouts used by the validated example sequences, under the same file names
as the cache; ``fetch`` uses them before contacting IRSA.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
import uuid
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import astropy.units as u
import pyvo
import requests

from . import config
from .geometry import FootprintMap


# ----------------------------------------------------------------------------- errors
class ArchiveError(RuntimeError):
    """Base class of archive access errors."""


class ArchiveTransientError(ArchiveError):
    """Timeout, connection error, HTTP 408/425/429 or 5xx after every allowed attempt:
    retrying later may succeed."""


class ArchivePermanentError(ArchiveError):
    """HTTP 4xx (other than 408/425/429) or an invalid request: retrying will not help."""


class CorruptFitsError(ArchiveError):
    """A FITS file (received or stored) is truncated or lacks required extensions."""


TRANSIENT_STATUS = frozenset({408, 425, 429})
#: Extensions every SPHEREx Level-2 cutout must contain (IRSA keeps them all).
REQUIRED_EXTENSIONS = ("IMAGE", "FLAGS", "VARIANCE", "ZODI", "WCS-WAVE")


def is_transient_status(code: int) -> bool:
    return code in TRANSIENT_STATUS or 500 <= code <= 599


def _retry_after_s(resp) -> float | None:
    try:
        v = float(resp.headers.get("Retry-After", ""))
    except (TypeError, ValueError, AttributeError):
        return None
    return v if v >= 0 else None


def http_get(url: str, headers: dict | None = None, ok_status=(200,), validate=None, sleep=None,
             retries: int | None = None, deadline_s: float | None = None):
    """GET with bounded retries for transient failures only.

    * retried: timeouts, connection errors, HTTP 408/425/429 and 5xx, and a
      response rejected by ``validate`` (e.g. a FITS truncated in transit);
    * not retried: any other status (400, 404, ...) -> ArchivePermanentError;
    * exponential back-off ``HTTP_BACKOFF_S * 2**k`` capped at
      ``HTTP_BACKOFF_MAX_S`` (a server ``Retry-After`` is honoured up to the
      cap), never after the last attempt, and never past ``deadline_s``.

    Raises ArchiveTransientError (or CorruptFitsError) once attempts or the
    time budget are exhausted.
    """
    retries = config.HTTP_RETRIES if retries is None else retries
    deadline = time.monotonic() + (config.HTTP_DEADLINE_S if deadline_s is None else deadline_s)
    hdrs = {**config.HTTP_HEADERS, **(headers or {})}
    last: Exception | None = None
    for attempt in range(retries):
        wait = None
        try:
            r = requests.get(url, headers=hdrs, timeout=config.HTTP_TIMEOUT_S)
        except (requests.Timeout, requests.ConnectionError) as err:
            last = ArchiveTransientError(f"{type(err).__name__} ({url.split('?')[0].rsplit('/', 1)[-1]}): "
                                         f"{str(err)[:160]}")
        except requests.RequestException as err:      # malformed URL, too many redirects...
            raise ArchivePermanentError(f"{type(err).__name__}: {str(err)[:200]}") from err
        else:
            if r.status_code in ok_status:
                if validate is None:
                    return r
                try:
                    validate(r.content)
                    return r
                except CorruptFitsError as err:
                    last = err                        # partial transfer: one more attempt may succeed
            elif is_transient_status(r.status_code):
                last = ArchiveTransientError(f"HTTP {r.status_code} de IRSA: {r.text[:100]!r}")
                wait = _retry_after_s(r)
            else:
                raise ArchivePermanentError(f"HTTP {r.status_code} de IRSA (no se reintenta): {r.text[:120]!r}")
        if attempt == retries - 1:
            break
        delay = min(config.HTTP_BACKOFF_MAX_S, wait if wait is not None else config.HTTP_BACKOFF_S * 2 ** attempt)
        if time.monotonic() + delay > deadline:
            break
        (sleep or time.sleep)(delay)
    if isinstance(last, CorruptFitsError):
        raise last
    raise ArchiveTransientError(f"Sin respuesta válida tras {attempt + 1} intentos: {last}")


def _timeout_session(timeout=None):
    """requests.Session with SkyClues headers and a default timeout (for pyvo)."""
    s = requests.Session()
    s.headers.update(config.HTTP_HEADERS)
    req = s.request

    def request(*a, **k):
        k.setdefault("timeout", timeout or config.HTTP_TIMEOUT_S)
        return req(*a, **k)

    s.request = request
    return s


def classify_exception(err: Exception) -> type:
    """ArchiveTransientError or ArchivePermanentError for an exception raised by
    pyvo/requests (HTTP status when known; network errors are transient)."""
    if isinstance(err, ArchiveError):
        return type(err)
    chain = [err, getattr(err, "cause", None), err.__cause__, err.__context__]
    for e in chain:
        if isinstance(e, (requests.Timeout, requests.ConnectionError)):
            return ArchiveTransientError
    for e in chain:
        code = getattr(e, "code", None)
        resp = getattr(e, "response", None)
        if not isinstance(code, int) and resp is not None:
            code = getattr(resp, "status_code", None)
        if isinstance(code, int) and 100 <= code <= 599:
            return ArchiveTransientError if is_transient_status(code) else ArchivePermanentError
    return ArchiveTransientError        # unknown service failure: bounded retries


# ----------------------------------------------------------------------------- FITS integrity
def validate_fits_bytes(data: bytes, required=REQUIRED_EXTENSIONS) -> None:
    """Raise CorruptFitsError unless ``data`` is a complete SPHEREx Level-2 FITS.

    Checks: FITS signature, length a multiple of the 2880-byte block, every
    HDU readable without truncation warnings, every required extension
    present with its data.
    """
    from astropy.io import fits
    from astropy.utils.exceptions import AstropyUserWarning

    if data[:6] != b"SIMPLE":
        raise CorruptFitsError("no es un FITS (falta la cabecera SIMPLE)")
    if len(data) % 2880:
        raise CorruptFitsError(f"longitud {len(data)} B no múltiplo de 2880: archivo truncado")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", AstropyUserWarning)
            with fits.open(io.BytesIO(data), memmap=False, lazy_load_hdus=False) as hdul:
                names = [h.name for h in hdul]
                missing = [n for n in required if n not in names]
                if missing:
                    raise CorruptFitsError(f"faltan extensiones {missing} (presentes: {names})")
                for h in hdul:
                    if h.name in required:
                        _ = h.data
                info = hdul.fileinfo(len(hdul) - 1)
                expected = int(info["datLoc"]) + int(info["datSpan"])
                if expected != len(data):
                    raise CorruptFitsError(f"tamaño {len(data)} B distinto del declarado por las cabeceras "
                                           f"({expected} B)")
    except CorruptFitsError:
        raise
    except Exception as err:
        raise CorruptFitsError(f"FITS ilegible: {type(err).__name__}: {str(err)[:160]}") from err


_validated: dict[tuple, bool] = {}
_validated_guard = threading.Lock()


def validate_fits_file(path: Path) -> None:
    """validate_fits_bytes for a file on disk (memoised by path, size and mtime)."""
    st = path.stat()
    key = (str(path), st.st_size, st.st_mtime_ns)
    with _validated_guard:
        if _validated.get(key):
            return
    validate_fits_bytes(path.read_bytes())
    with _validated_guard:
        _validated[key] = True


def quarantine(path: Path) -> Path:
    """Move a corrupt CACHE file aside (``*.corrupt-<time>``); it is never deleted silently."""
    if config.REFERENCE_DIR.resolve() in path.resolve().parents:
        raise CorruptFitsError(f"Archivo de referencia dañado {path.name}: no se modifica; restáurelo del "
                               "repositorio o de IRSA")
    dest = path.with_name(f"{path.name}.corrupt-{time.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}")
    try:
        os.replace(path, dest)
    except FileNotFoundError:     # another thread already moved it
        pass
    return dest

_FILE_RE = re.compile(
    r"level2_(?P<obsid>[0-9A-Z_]+)D(?P<det>[1-6])_spx_l2b(?:_retry)?-v(?P<ver>\d+)-(?P<pdate>\d{4}-\d{3})\.fits"
)


@dataclass
class ObservationRecord:
    """One SPHEREx Level-2 detector image, as described by the archive."""

    obs_id: str
    collection: str
    detector: int
    bandpass: str
    mjd_start: float
    mjd_end: float
    exptime_s: float
    em_min_um: float
    em_max_um: float
    access_url: str
    s_region: str
    release_date: str
    l2b_version: str
    processing_date: str
    file_name: str
    publisher_did: str = ""
    product_level: str = ""

    @property
    def mjd_mid(self) -> float:
        return 0.5 * (self.mjd_start + self.mjd_end)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mjd_mid"] = self.mjd_mid
        return d


def _detector_from(bandpass: str, url: str) -> int:
    m = re.search(r"D(\d)$", bandpass or "")
    if m:
        return int(m.group(1))
    m = _FILE_RE.search(url)
    if m:
        return int(m.group("det"))
    raise ValueError(f"Cannot determine detector for {url}")


def _meta_cache_path(kind: str, key: str) -> Path:
    h = hashlib.sha1(key.encode()).hexdigest()[:20]
    return config.CACHE_DIR / "meta" / f"{kind}_{h}.json"


def atomic_write(path: Path, data: bytes | str) -> Path:
    """Write ``data`` to ``path`` through a unique temporary file and an atomic rename.

    Readers never see a partial file, and concurrent writers of the same path
    cannot interleave (the last complete write wins; contents are identical).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}-{uuid.uuid4().hex[:12]}.part")
    try:
        if isinstance(data, str):
            tmp.write_text(data, encoding="utf-8")
        else:
            tmp.write_bytes(data)
        for attempt in range(20):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                # Windows refuses a rename onto a file that another writer is
                # replacing or a reader holds open: wait briefly and retry.
                if attempt == 19:
                    if path.exists():   # another writer completed the same file
                        break
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return path


class ObservationBatch(list):
    """List-compatible query result with per-request provenance (not global session state)."""
    def __init__(self, records, provenance):
        super().__init__(records)
        self.provenance = provenance


def query_images(ra: float, dec: float, radius_deg: float = 1.0 / 3600,
                 collections=config.WIDE_COLLECTIONS,
                 max_age_s: float = config.METADATA_CACHE_MAX_AGE_S) -> list[ObservationRecord]:
    """Query on demand; max_age_s=0 bypasses metadata cache, never masks a service outage."""
    from .targets import validate_coordinates
    from .releases import reconcile_products, validate_collections
    from datetime import datetime, timezone
    import math
    ra, dec = validate_coordinates(ra, dec)
    if not math.isfinite(radius_deg) or not 0 < radius_deg <= .5:
        raise ValueError("Radio de consulta inválido")
    collections = validate_collections(collections)
    key = f"{ra:.7f}|{dec:.7f}|{radius_deg:.7f}|{','.join(collections)}"
    cpath = _meta_cache_path("sia", key)
    cached = None
    if max_age_s > 0 and cpath.exists() and time.time() - cpath.stat().st_mtime < max_age_s:
        try:
            cached = json.loads(cpath.read_text(encoding="utf-8"))
            # Legacy lists have no verified retrieval date: refresh once, do not invent one.
            if not isinstance(cached, dict) or cached.get("schema") != 2:
                cached = None
        except (OSError, ValueError):
            cached = None
    if cached is not None:
        records = [ObservationRecord(**d) for d in cached["records"]]
        queried = cached["queried_utc"]
        origin = "cache"
    else:
        records = _query_images_live(ra, dec, radius_deg, collections)
        queried = datetime.now(timezone.utc).isoformat()
        origin = "IRSA"
        try:
            atomic_write(cpath, json.dumps({"schema": 2, "queried_utc": queried,
                                           "records": [asdict(r) for r in records]}))
        except OSError:
            pass  # read-only storage: fresh result remains usable, without claiming persistence
    selected, replacements = reconcile_products(records)
    return ObservationBatch(selected, {"origin": origin, "queried_utc": queried,
        "endpoint": config.SIA_URL, "collections": list(collections), "forced": max_age_s == 0,
        "raw_count": len(records), "selected_count": len(selected), "replacements": replacements})


def _with_retries(what: str, fn, sleep=None):
    """Call ``fn()`` retrying only transient failures (see http_get); permanent
    errors raise ArchivePermanentError at once."""
    deadline = time.monotonic() + config.HTTP_DEADLINE_S
    last = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            return fn()
        except Exception as err:  # pyvo wraps HTTP and network errors in DALServiceError
            kind = classify_exception(err)
            if kind is ArchivePermanentError:
                raise ArchivePermanentError(f"{what}: {type(err).__name__}: {str(err)[:200]}") from err
            last = err
        if attempt == config.HTTP_RETRIES - 1:
            break
        delay = min(config.HTTP_BACKOFF_MAX_S, config.HTTP_BACKOFF_S * 2 ** attempt)
        if time.monotonic() + delay > deadline:
            break
        (sleep or time.sleep)(delay)
    raise ArchiveTransientError(f"{what}: sin respuesta tras {attempt + 1} intentos: "
                                f"{type(last).__name__}: {str(last)[:200]}") from last


def sia2_service():
    """(service, route) for config.SIA_URL.

    Normal route: one request to ``/SIA/capabilities`` to find the query
    endpoint. If that request fails (it alone can answer 502 while queries
    work), the documented query endpoint ``https://irsa.ipac.caltech.edu/SIA``
    is used directly (``check_baseurl=False``) instead of blocking the search.
    Collections and query parameters are identical on both routes; failures
    of the query itself are retried and classified by ``_with_retries``.
    """
    try:
        return pyvo.dal.SIA2Service(config.SIA_URL, session=_timeout_session()), "capabilities"
    except Exception:  # noqa: BLE001 - any capabilities failure: use the known query endpoint
        return (pyvo.dal.SIA2Service(config.SIA_URL, session=_timeout_session(), check_baseurl=False),
                "directo (capabilities no disponible)")


#: Route used by the last live SIA2 query ("capabilities" or "directo …"), for diagnostics.
last_sia2_route: str | None = None


def _query_images_live(ra, dec, radius_deg, collections) -> list[ObservationRecord]:
    global last_sia2_route
    svc, last_sia2_route = sia2_service()
    records: list[ObservationRecord] = []
    for coll in collections:
        tab = _with_retries(f"SIA2 {coll}", lambda: svc.search(
            pos=(ra * u.deg, dec * u.deg, radius_deg * u.deg), collection=coll).to_table())
        for row in tab:
            if str(row["dataproduct_subtype"]).strip() not in ("science", ""):
                continue
            url = str(row["access_url"])
            m = _FILE_RE.search(url)
            if m is None or str(row['obs_collection']).strip() != coll:
                raise ArchivePermanentError('Producto SIA2 fuera del perfil L2b verificado; no se interpreta.')
            if 'calib_level' in tab.colnames and str(row['calib_level']) != '2':
                raise ArchivePermanentError('Nivel de producto incompatible con imagen L2b.')
            records.append(ObservationRecord(
                obs_id=str(row["obs_id"]),
                collection=str(row["obs_collection"]) or coll,
                detector=_detector_from(str(row["energy_bandpassname"]), url),
                bandpass=str(row["energy_bandpassname"]),
                mjd_start=float(row["t_min"]),
                mjd_end=float(row["t_max"]),
                exptime_s=float(row["t_exptime"]),
                em_min_um=float(row["em_min"]) * 1e6,
                em_max_um=float(row["em_max"]) * 1e6,
                access_url=url,
                s_region=str(row["s_region"]),
                release_date=str(row["obs_release_date"]),
                l2b_version=m.group("ver") if m else "",
                processing_date=m.group("pdate") if m else "",
                file_name=url.rsplit("/", 1)[-1],
                publisher_did=str(row["obs_publisher_did"]) if "obs_publisher_did" in tab.colnames else "",
                product_level=str(row["calib_level"]) if "calib_level" in tab.colnames else "",
            ))
    return records


def footprint(rec: ObservationRecord) -> FootprintMap:
    return FootprintMap(rec.s_region)


def cutout_url(access_url: str, ra: float, dec: float, size_deg: float) -> str:
    return f"{access_url}?center={ra:.7f},{dec:.7f}&size={size_deg:.5f}"


def _cache_path(url: str) -> Path:
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    name = url.split("?")[0].rsplit("/", 1)[-1].replace(".fits", "")
    return config.CACHE_DIR / f"{name}__{key}.fits"


_url_locks: dict[str, threading.Lock] = {}
_url_locks_guard = threading.Lock()


def _lock_for(url: str) -> threading.Lock:
    with _url_locks_guard:
        return _url_locks.setdefault(url, threading.Lock())


def is_reference(path: Path) -> bool:
    return config.REFERENCE_DIR.resolve() in Path(path).resolve().parents


def local_copy(url: str) -> Path | None:
    """Existing local file for ``url`` (reference store first, then cache), or None.

    Presence only; ``fetch`` also verifies the file's integrity.
    """
    path = _cache_path(url)
    ref = config.REFERENCE_DIR / path.name
    if ref.exists():
        return ref
    return path if path.exists() else None


def _valid_local(url: str) -> Path | None:
    """Local copy that passes the FITS integrity check. A corrupt cache file is
    quarantined (and None returned so that it is downloaded again); a corrupt
    reference file raises CorruptFitsError and is left untouched."""
    hit = local_copy(url)
    if hit is None:
        return None
    try:
        validate_fits_file(hit)
        return hit
    except CorruptFitsError as err:
        if is_reference(hit):
            raise CorruptFitsError(f"Archivo de referencia dañado {hit.name} ({err}); no se modifica") from err
        quarantine(hit)
        return None


def fetch(url: str, refresh: bool = False) -> Path:
    """Return a verified local copy of ``url``, downloading it to the cache only if needed.

    Every file (downloaded or cached) must pass ``validate_fits_bytes`` before
    it is used; nothing incomplete is ever written to the cache. Reference
    files are never overwritten. Raises ArchiveTransientError,
    ArchivePermanentError or CorruptFitsError.
    """
    if not refresh and (hit := _valid_local(url)) is not None:
        return hit
    path = _cache_path(url)
    with _lock_for(url):
        if not refresh and (hit := _valid_local(url)) is not None:   # another thread finished it meanwhile
            return hit
        r = http_get(url, validate=validate_fits_bytes)
        return atomic_write(path, r.content)


def redownload(url: str, path: Path) -> Path:
    """Replace a CACHE copy that failed a check (e.g. SHA-256 against a report):
    the old file is quarantined, never deleted. Reference files are refused."""
    if is_reference(path):
        raise CorruptFitsError(f"El archivo de referencia {path.name} no coincide con el informe; no se modifica")
    with _lock_for(url):
        if path.exists():
            quarantine(path)
    return fetch(url)


def fetch_cutout(rec: ObservationRecord, ra: float, dec: float, size_deg: float) -> Path:
    return fetch(cutout_url(rec.access_url, ra, dec, size_deg))


def fetch_many(urls: list[str], workers: int = config.DOWNLOAD_WORKERS,
               progress=None) -> dict[str, Path | Exception]:
    """Download several URLs concurrently (small pool: IRSA throttles with 503).

    Duplicates are fetched once; files already on disk are not downloaded.
    ``progress(done, total, n_downloaded)`` is called after each URL.
    """
    unique = list(dict.fromkeys(urls))
    out: dict[str, Path | Exception] = {}
    todo = []
    for u in unique:
        try:
            hit = _valid_local(u)
        except CorruptFitsError as err:      # damaged reference file: reported, never replaced
            out[u] = err
            continue
        if hit is not None:
            out[u] = hit
        else:
            todo.append(u)
    total, downloaded = len(unique), 0
    if progress:
        progress(len(out), total, 0)

    def one(u):
        try:
            return u, fetch(u)
        except Exception as err:  # reported per URL
            return u, err

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for fut in as_completed([pool.submit(one, u) for u in todo]):
            u, res = fut.result()
            out[u] = res
            downloaded += not isinstance(res, Exception)
            if progress:
                progress(len(out), total, downloaded)
    return {u: out[u] for u in unique}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def records_table(records: list[ObservationRecord]):
    import pandas as pd

    from astropy.time import Time

    rows = []
    for r in records:
        rows.append({
            "fecha (UTC)": Time(r.mjd_mid, format="mjd").isot[:19],
            "MJD": round(r.mjd_mid, 5),
            "colección": r.collection,
            "detector": r.detector,
            "banda (µm)": f"{r.em_min_um:.2f}–{r.em_max_um:.2f}",
            "obs_id": r.obs_id,
            "exp (s)": round(r.exptime_s, 1),
        })
    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values("MJD").reset_index(drop=True)
    return df


__all__ = [
    "ObservationRecord", "query_images", "footprint", "cutout_url", "fetch",
    "fetch_cutout", "sha256", "records_table",
]
