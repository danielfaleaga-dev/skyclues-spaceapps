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
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path

import astropy.units as u
import pyvo
import requests

from . import config
from .geometry import FootprintMap

_FILE_RE = re.compile(
    r"level2_(?P<obsid>[0-9A-Z_]+)D(?P<det>[1-6])_spx_l2b-v(?P<ver>\d+)-(?P<pdate>\d{4}-\d{3})\.fits"
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


def query_images(ra: float, dec: float, radius_deg: float = 1.0 / 3600,
                 collections=config.WIDE_COLLECTIONS,
                 max_age_s: float = config.METADATA_CACHE_MAX_AGE_S) -> list[ObservationRecord]:
    """SIA2 search for SPHEREx spectral images overlapping a sky circle.

    Results are cached as JSON for ``max_age_s`` (archive metadata only; IRSA
    ingests new data weekly). Pass ``max_age_s=0`` to force a fresh query.
    """
    key = f"{ra:.7f}|{dec:.7f}|{radius_deg:.7f}|{','.join(collections)}"
    cpath = _meta_cache_path("sia", key)
    if max_age_s > 0 and cpath.exists() and time.time() - cpath.stat().st_mtime < max_age_s:
        return [ObservationRecord(**d) for d in json.loads(cpath.read_text(encoding="utf-8"))]
    records = _query_images_live(ra, dec, radius_deg, collections)
    atomic_write(cpath, json.dumps([asdict(r) for r in records]))
    return records


def _query_images_live(ra, dec, radius_deg, collections) -> list[ObservationRecord]:
    svc = pyvo.dal.SIA2Service(config.SIA_URL)
    records: list[ObservationRecord] = []
    for coll in collections:
        last_err = None
        for attempt in range(config.HTTP_RETRIES):
            try:
                res = svc.search(pos=(ra * u.deg, dec * u.deg, radius_deg * u.deg), collection=coll)
                tab = res.to_table()
                break
            except Exception as err:  # network / service errors
                last_err = err
                time.sleep(2 * (attempt + 1))
        else:
            raise RuntimeError(f"SIA2 query failed for {coll}: {last_err}")
        for row in tab:
            if str(row["dataproduct_subtype"]).strip() not in ("science", ""):
                continue
            url = str(row["access_url"])
            m = _FILE_RE.search(url)
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


def local_copy(url: str) -> Path | None:
    """Existing local file for ``url`` (reference store first, then cache), or None."""
    path = _cache_path(url)
    ref = config.REFERENCE_DIR / path.name
    if ref.exists():
        return ref
    return path if path.exists() else None


def fetch(url: str, refresh: bool = False) -> Path:
    """Return a local copy of ``url``, downloading it to the cache only if needed."""
    if not refresh and (hit := local_copy(url)) is not None:
        return hit
    path = _cache_path(url)
    with _lock_for(url):
        if path.exists() and not refresh:      # another thread finished it meanwhile
            return path
        last = None
        for attempt in range(config.HTTP_RETRIES):
            try:
                r = requests.get(url, headers=config.HTTP_HEADERS, timeout=config.HTTP_TIMEOUT_S)
                if r.status_code == 200 and r.content[:6] == b"SIMPLE":
                    return atomic_write(path, r.content)
                last = f"HTTP {r.status_code}: {r.text[:80]!r}"
            except requests.RequestException as err:
                last = repr(err)
            # IRSA answers 503 "Server busy, retry later" under load: back off.
            time.sleep(min(60, 5 * 2 ** attempt))
    raise RuntimeError(f"Download failed after {config.HTTP_RETRIES} attempts: {url} ({last})")


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
        hit = local_copy(u)
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
