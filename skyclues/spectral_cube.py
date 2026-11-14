"""SPHEREx DR1 All-Sky spectral cube: authentic channel maps and exploratory spectra.

Product (SPHEREx Explanatory Supplement v2.1, sections 2.5 and 3.4; doi:10.26131/IRSA679)
------------------------------------------------------------------------------------------
* 102 spectral channels, 17 per detector D1-D6 (0.75-5.0 um), built from ~1.2 million DR1
  spectral images taken on MANY DATES: a combined product, never a time sequence.
* For each channel the ZODI-subtracted input pixels are assigned to the nearest mosaic pixel
  ("each input pixel contributes to only a single mosaic pixel") and averaged:
  IMAGE = mean of the NHITS contributing input pixels (MJy/sr); IMAGE = NaN where NHITS = 0.
* Input pixels with TRANSIENT, SUR_ERROR, NONFUNC, DICHROIC, MISSING_DATA, HOT, COLD, PHANMISS,
  NONLINEAR, PERSIST, CROSSTALK, STREAK, BLOOM, SNOWBALL, HALO or SATELLITE_HALO are rejected
  before averaging. FLAGS is the bitwise OR of the propagated flags (OVERFLOW, SOURCE,
  OUTLIER) of the contributing pixels.
* Channels 51 and 52 (0-based planes 50 and 51: D3 channel 17 and D4 channel 1, next to the
  dichroic) hold no data in DR1: all NaN, NHITS = 0, listed in the BLANKCH keyword.
* Tiles of HEALPix order 5 (NESTED), 512 x 512 pixels of 12.9 arcsec (HEALPix order-14
  pixels: all of equal solid angle) in the HPX projection.
* Known issue: striping near strong lines (airglow He 1.083 um; Pa-alpha, PAH 3.3 um,
  Br-alpha in nebulae) caused by the LVF; it does not average down.

Access
------
The FITS cubes of the official IRSA tutorial ("Using SPHEREx HiPS All-Sky Mosaic Cubes"),
``<CUBE_DATA_URL>/Norder5/Dir<d>/Npix<ipix>_cube.fits``. Each one is ~320 MB, so SkyClues
NEVER downloads a whole tile: the files are uncompressed FITS, so the bytes of any row of any
plane sit at a computable offset, and only those rows are read with HTTP Range requests
(IBE cutouts refuse these files: HTTP 422 "lacks WCS data", verified 2026-11-14).

Integrity rules of the byte-range reader:
* a request carries at most ``CUBE_MAX_RANGES_PER_REQUEST`` ranges (IRSA answers ~100+
  ranges with the whole 320 MB file); any answer other than 206 is never read;
* every part's Content-Range must match what was requested and the file size, and the
  ETag must equal the one recorded with the layout (otherwise the file changed);
* bytes are kept exactly as served (optional verbatim disk cache, never modified);
  NaN and NHITS = 0 are kept as "no data", never filled or interpolated.

The exploratory spectrum follows the method of the official tutorial (circular aperture,
sigma-clipped annulus background, sum x pixel solid angle -> mJy). The tutorial and IRSA
state that a spectrum from the cube is only suitable for visualization; science-grade
spectrophotometry uses the IRSA SPHEREx Spectrophotometry Tool (forced photometry on the
Level-2 images), which has no documented programmatic interface.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import requests
from astropy.io import fits
from astropy.wcs import WCS

from . import archive, config
from .geometry import separation_deg

BLOCK = 2880
CUBE_EXTENSIONS = ("IMAGE", "NHITS", "FLAGS")
#: Flags propagated to the cube (Explanatory Supplement v2.1, sections 3.4.3 and 3.4.9).
PROPAGATED_FLAGS = ("OVERFLOW", "SOURCE", "OUTLIER")
#: Propagated flags worth a caution in a spectrum (saturated / outlier input pixel).
CAUTION_FLAGS = ("OVERFLOW", "OUTLIER")
_BITPIX_DTYPE = {8: "u1", 16: ">i2", 32: ">i4", 64: ">i8", -32: ">f4", -64: ">f8"}


# ----------------------------------------------------------------------------- errors
class CubeFormatError(archive.ArchiveError):
    """The cube file does not have the documented structure (refused, never guessed)."""


class RangeNotHonoured(archive.ArchivePermanentError):
    """The server ignored the Range header (it would send the whole file): nothing was read."""


class FileChangedError(archive.ArchiveTransientError):
    """ETag or size differ from the recorded layout: the file was replaced at IRSA."""


# ----------------------------------------------------------------------------- statistics
_stats_lock = threading.Lock()
_stats = {"requests": 0, "bytes_network": 0, "bytes_cache": 0}


def io_stats(reset: bool = False) -> dict:
    """Requests and bytes read so far by this process (network vs verbatim disk cache)."""
    with _stats_lock:
        out = dict(_stats)
        if reset:
            for k in _stats:
                _stats[k] = 0
    return out


def _count(key: str, n: int) -> None:
    with _stats_lock:
        _stats[key] += n


# ----------------------------------------------------------------------------- HEALPix
def _spread_bits(v: np.ndarray) -> np.ndarray:
    v = v.astype(np.int64)
    out = np.zeros_like(v)
    for b in range(30):
        out |= ((v >> b) & 1) << (2 * b)
    return out


def healpix_nest(order: int, ra_deg, dec_deg) -> np.ndarray:
    """HEALPix NESTED index of (ra, dec) at ``order`` (Gorski et al. 2005; same algorithm as
    the HEALPix C++ ``loc2pix``). Verified against the official tutorial (60.8109955,
    51.3404038 -> 445 at order 5) and, at run time, against every tile header (NPIX) and WCS."""
    nside = 1 << order
    ra = np.radians(np.asarray(ra_deg, float))
    z = np.sin(np.radians(np.asarray(dec_deg, float)))
    za = np.abs(z)
    tt = np.mod(ra, 2 * np.pi) / (np.pi / 2)              # in [0, 4)
    # equatorial belt (|z| <= 2/3)
    t1 = nside * (0.5 + tt)
    t2 = nside * (0.75 * z)
    jp = np.floor(t1 - t2).astype(np.int64)
    jm = np.floor(t1 + t2).astype(np.int64)
    ifp, ifm = jp // nside, jm // nside
    face_eq = np.where(ifp == ifm, ifp | 4, np.where(ifp < ifm, ifp, ifm + 8))
    ix_eq = jm & (nside - 1)
    iy_eq = nside - (jp & (nside - 1)) - 1
    # polar caps
    ntt = np.minimum(np.floor(tt).astype(np.int64), 3)
    tp = tt - ntt
    tmp = nside * np.sqrt(np.clip(3 * (1 - za), 0, None))
    jpp = np.minimum(np.floor(tp * tmp).astype(np.int64), nside - 1)
    jmp = np.minimum(np.floor((1 - tp) * tmp).astype(np.int64), nside - 1)
    north = z > 0
    face_p = np.where(north, ntt, ntt + 8)
    ix_p = np.where(north, nside - jmp - 1, jpp)
    iy_p = np.where(north, nside - jpp - 1, jmp)
    eq = za <= 2.0 / 3.0
    face = np.where(eq, face_eq, face_p)
    ix = np.where(eq, ix_eq, ix_p)
    iy = np.where(eq, iy_eq, iy_p)
    return face * nside * nside + _spread_bits(ix) + (_spread_bits(iy) << 1)


def tile_url(ipix: int, order: int = config.CUBE_ORDER) -> str:
    """URL of the FITS cube of one tile (path rule of the official tutorial)."""
    d = (int(ipix) // 10000) * 10000
    return f"{config.CUBE_DATA_URL}/Norder{order}/Dir{d}/Npix{int(ipix)}_cube.fits"


# ----------------------------------------------------------------------------- byte ranges
_tls = threading.local()


def _session() -> requests.Session:
    s = getattr(_tls, "session", None)
    if s is None:
        s = _tls.session = requests.Session()
        s.headers.update(config.HTTP_HEADERS)
    return s


def _parse_content_range(value: str | None) -> tuple[int, int, int]:
    """'bytes a-b/total' -> (a, b + 1, total); total -1 when '*'."""
    m = re.fullmatch(r"\s*bytes\s+(\d+)-(\d+)/(\d+|\*)\s*", value or "")
    if not m:
        raise CubeFormatError(f"Content-Range no válido: {value!r}")
    return int(m[1]), int(m[2]) + 1, (int(m[3]) if m[3] != "*" else -1)


def _parse_multipart(body: bytes, boundary: bytes) -> list[tuple[int, int, int, bytes]]:
    """Parts of a multipart/byteranges body as (start, stop, total, data), by declared length."""
    parts, delim = [], b"--" + boundary
    pos = body.find(delim)
    while pos >= 0:
        pos += len(delim)
        if body[pos:pos + 2] == b"--":
            break
        hdr_end = body.find(b"\r\n\r\n", pos)
        if hdr_end < 0:
            raise CubeFormatError("respuesta multipart truncada (cabecera de parte)")
        m = re.search(rb"(?im)^content-range:\s*([^\r\n]+)", body[pos:hdr_end])
        if not m:
            raise CubeFormatError("parte multipart sin Content-Range")
        start, stop, total = _parse_content_range(m.group(1).decode("latin-1"))
        data = body[hdr_end + 4: hdr_end + 4 + (stop - start)]
        if len(data) != stop - start:
            raise CubeFormatError("respuesta multipart truncada (datos)")
        parts.append((start, stop, total, data))
        pos = body.find(delim, hdr_end + 4 + len(data))
    return parts


def _request_ranges(url: str, spec: list[tuple[int, int]], size: int | None,
                    etag: str | None) -> tuple[dict, str | None, int, str | None]:
    """One GET with a Range header for ``spec`` ([start, stop) pairs). Returns
    ({(a, b): bytes}, etag, total size, last-modified). Never reads a 200 body."""
    if not spec or len(spec) > config.CUBE_MAX_RANGES_PER_REQUEST:
        raise ValueError(f"entre 1 y {config.CUBE_MAX_RANGES_PER_REQUEST} rangos por petición ({len(spec)})")
    header = "bytes=" + ",".join(f"{a}-{b - 1}" for a, b in spec)
    expected = sum(b - a for a, b in spec)
    cap = expected + 256 * len(spec) + 8192          # multipart headers are small
    try:
        resp = _session().get(url, headers={"Range": header}, stream=True, timeout=config.HTTP_TIMEOUT_S)
    except (requests.Timeout, requests.ConnectionError) as err:
        raise archive.ArchiveTransientError(f"{type(err).__name__}: {str(err)[:160]}") from err
    with resp:
        code = resp.status_code
        if code == 200:
            raise RangeNotHonoured("IRSA ignoró la petición por rangos (HTTP 200: enviaría el archivo completo); "
                                   "no se ha leído nada")
        if code != 206:
            if archive.is_transient_status(code):
                raise archive.ArchiveTransientError(f"HTTP {code} de IRSA (cubo espectral)")
            raise archive.ArchivePermanentError(f"HTTP {code} de IRSA (cubo espectral, no se reintenta)")
        got_etag = resp.headers.get("ETag")
        if etag and got_etag and got_etag != etag:
            raise FileChangedError(f"El cubo cambió en IRSA (ETag {got_etag} ≠ {etag})")
        try:
            clen = int(resp.headers.get("Content-Length", "-1"))
        except ValueError:
            clen = -1
        if clen > cap:
            raise RangeNotHonoured(f"respuesta de {clen} B para {expected} B pedidos; no se lee")
        chunks, got = [], 0
        try:
            for chunk in resp.iter_content(1 << 16):
                got += len(chunk)
                if got > cap:
                    raise RangeNotHonoured("respuesta mayor que lo pedido; lectura interrumpida")
                chunks.append(chunk)
        except (requests.ConnectionError, requests.exceptions.ChunkedEncodingError) as err:
            raise archive.ArchiveTransientError(f"transferencia interrumpida: {str(err)[:120]}") from err
        body = b"".join(chunks)
        ctype = resp.headers.get("Content-Type", "")
        if "multipart/byteranges" in ctype:
            m = re.search(r'boundary="?([^";]+)"?', ctype)
            if not m:
                raise CubeFormatError("multipart sin boundary")
            parts = _parse_multipart(body, m.group(1).encode("latin-1"))
        else:
            start, stop, total = _parse_content_range(resp.headers.get("Content-Range"))
            if len(body) != stop - start:
                raise archive.ArchiveTransientError(f"rango incompleto: {len(body)} de {stop - start} B")
            parts = [(start, stop, total, body)]
        last_modified = resp.headers.get("Last-Modified")
    totals = {p[2] for p in parts if p[2] >= 0}
    if len(totals) > 1 or (size is not None and totals and totals != {size}):
        raise FileChangedError(f"Tamaño del cubo distinto del registrado ({totals} ≠ {size})")
    out = {}
    for a, b in spec:
        for s, e, _, data in parts:
            if s <= a and b <= e:
                out[(a, b)] = data[a - s:b - s]
                break
        else:
            raise CubeFormatError(f"IRSA no devolvió el rango {a}-{b - 1}")
    total = next(iter(totals)) if totals else (size or -1)
    return out, got_etag, total, last_modified


def _with_retries(fn, sleep=None):
    """Retry transient failures (timeouts, 5xx, 429...) with the archive back-off policy.
    FileChangedError is not retried here: the caller reloads the layout."""
    deadline = time.monotonic() + config.HTTP_DEADLINE_S
    last = None
    for attempt in range(config.HTTP_RETRIES):
        try:
            return fn()
        except FileChangedError:
            raise
        except archive.ArchiveTransientError as err:
            last = err
        if attempt == config.HTTP_RETRIES - 1:
            break
        delay = min(config.HTTP_BACKOFF_MAX_S, config.HTTP_BACKOFF_S * 2 ** attempt)
        if time.monotonic() + delay > deadline:
            break
        (sleep or time.sleep)(delay)
    raise archive.ArchiveTransientError(f"Cubo espectral: sin respuesta válida tras {attempt + 1} intentos: {last}")


# Verbatim disk cache of byte ranges (exact bytes served by IRSA, keyed by URL + ETag).
_cache_bytes: int | None = None
_cache_lock = threading.Lock()


def _chunk_path(url: str, etag: str | None, a: int, b: int) -> Path:
    stem = url.rsplit("/", 1)[-1].replace(".fits", "")
    tag = hashlib.sha1(f"{url}|{etag}".encode()).hexdigest()[:12]
    return config.CACHE_DIR / "cube" / f"{stem}__{tag}" / f"{a}-{b}.bin"


def _cache_room(n: int) -> bool:
    global _cache_bytes
    with _cache_lock:
        if _cache_bytes is None:
            root = config.CACHE_DIR / "cube"
            _cache_bytes = sum(p.stat().st_size for p in root.rglob("*.bin")) if root.exists() else 0
        if _cache_bytes + n > config.CUBE_CACHE_MAX_MB * 2**20:
            return False
        _cache_bytes += n
        return True


def read_ranges(url: str, ranges: list[tuple[int, int]], size: int, etag: str | None,
                use_cache: bool = True) -> dict[tuple[int, int], bytes]:
    """Bytes of every [start, stop) range of ``url`` (verbatim), from the disk cache or IRSA.

    At most CUBE_MAX_RANGES_PER_REQUEST ranges per request; total limited to
    CUBE_MAX_BYTES_PER_CALL. Raises ArchiveTransientError, ArchivePermanentError,
    RangeNotHonoured, FileChangedError or CubeFormatError.
    """
    want = sorted(set((int(a), int(b)) for a, b in ranges))
    if any(a < 0 or b <= a or b > size for a, b in want):
        raise ValueError("rango fuera del archivo")
    total = sum(b - a for a, b in want)
    if total > config.CUBE_MAX_BYTES_PER_CALL:
        raise ValueError(f"lectura de {total / 2**20:.1f} MB > límite {config.CUBE_MAX_BYTES_PER_CALL / 2**20:.0f} MB")
    out, todo = {}, []
    for r in want:
        p = _chunk_path(url, etag, *r)
        if use_cache and p.exists() and p.stat().st_size == r[1] - r[0]:
            out[r] = p.read_bytes()
            _count("bytes_cache", len(out[r]))
        else:
            todo.append(r)
    step = config.CUBE_MAX_RANGES_PER_REQUEST
    batches = [todo[i:i + step] for i in range(0, len(todo), step)]

    def one(batch):
        got = _with_retries(lambda: _request_ranges(url, batch, size, etag))[0]
        _count("requests", 1)
        return got

    if len(batches) > 1:      # small pool, as for the Level-2 cutouts (IRSA throttles with 503)
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(config.DOWNLOAD_WORKERS, len(batches))) as pool:
            results = list(pool.map(one, batches))
    else:
        results = [one(b) for b in batches]
    for got in results:
        for r, data in got.items():
            out[r] = data
            _count("bytes_network", len(data))
            if use_cache and _cache_room(len(data)):
                try:
                    archive.atomic_write(_chunk_path(url, etag, *r), data)
                except OSError:
                    pass                      # read-only disk: the bytes are still used
    return out


# ----------------------------------------------------------------------------- tile layout
@dataclass(frozen=True)
class Channel:
    """One of the 102 cube channels, as declared by the SPECTRAL_CHANNELS table of the file."""

    plane: int              # 0-based plane index in the cube
    number: int             # 1-based channel number (1-102), as in the Explanatory Supplement
    detector: int
    subchannel: int         # 1-17 within the detector
    wavelength_um: float    # central wavelength (SPECTRAL_CHANNELS, WAVELENGTH)
    wl_min_um: float
    wl_max_um: float
    bandwidth_um: float
    resolving_power: float
    blank: bool             # listed in BLANKCH: no data in DR1

    @property
    def label(self) -> str:
        return (f"Canal {self.number} · {self.wavelength_um:.3f} µm · D{self.detector} subcanal "
                f"{self.subchannel}" + (" · SIN DATOS" if self.blank else ""))


def _end_card(buf: bytes) -> int | None:
    for i in range(0, len(buf) - 79, 80):
        if buf[i:i + 8] == b"END     " or buf[i:i + 80] == b"END" + b" " * 77:
            return i
    return None


def _data_nbytes(h: fits.Header) -> int:
    naxis = int(h.get("NAXIS", 0))
    if naxis == 0:
        return 0
    n = abs(int(h["BITPIX"])) // 8 * int(np.prod([int(h[f"NAXIS{k}"]) for k in range(1, naxis + 1)]))
    return int(h.get("GCOUNT", 1)) * (n + int(h.get("PCOUNT", 0)))


class _SpanReader:
    """Reads small header/table spans, fetching a few blocks ahead to save requests."""

    def __init__(self, url: str):
        self.url, self.spans = url, []
        self.size = self.etag = self.last_modified = None

    def read(self, a: int, b: int) -> bytes:
        for s, data in self.spans:
            if s <= a and b <= s + len(data):
                return data[a - s:b - s]
        stop = max(b, a + 8 * BLOCK)
        if self.size is not None:
            stop = min(stop, self.size)

        def once():
            return _request_ranges(self.url, [(a, stop)], self.size, self.etag)
        got, etag, total, lm = _with_retries(once)
        _count("requests", 1)
        _count("bytes_network", stop - a)
        if self.size is None:
            self.size, self.etag, self.last_modified = total, etag, lm
        data = got[(a, stop)]
        self.spans.append((a, data))
        return data[:b - a]


@dataclass
class CubeTile:
    """Layout of one tile's FITS cube (headers, data offsets, channel table). No pixel data."""

    ipix: int
    order: int
    url: str
    size: int
    etag: str | None
    last_modified: str | None
    headers: dict[str, str]           # EXTNAME -> header text
    data_offset: dict[str, int]
    data_nbytes: dict[str, int]
    channels_table: list[dict]        # SPECTRAL_CHANNELS rows
    wcs_wave_um: list[float]          # WCS-WAVE WAVELENGTHS (visualization fidelity)
    read_at: float = field(default_factory=time.time)

    # -- derived -------------------------------------------------------
    def header(self, name: str) -> fits.Header:
        cache = self.__dict__.setdefault("_hcache", {})
        if name not in cache:
            cache[name] = fits.Header.fromstring(self.headers[name])
        return cache[name]

    @property
    def shape(self) -> tuple[int, int, int]:
        h = self.header("IMAGE")
        return int(h["NAXIS3"]), int(h["NAXIS2"]), int(h["NAXIS1"])

    def dtype(self, ext: str) -> np.dtype:
        return np.dtype(_BITPIX_DTYPE[int(self.header(ext)["BITPIX"])])

    @property
    def wcs(self) -> WCS:
        """Celestial (RA/Dec, HPX) WCS of the tile, from the IMAGE header without the spectral axis."""
        if "_wcs" not in self.__dict__:
            h = self.header("IMAGE").copy()
            for k in list(h.keys()):
                if re.fullmatch(r"(CTYPE|CUNIT|CRPIX|CRVAL|CDELT|CNAME)3|P[CSV]3_\d+|PC\d_3|PC3_\d", k):
                    del h[k]
            h["WCSAXES"] = 2
            h["NAXIS"] = 2
            for k in ("NAXIS3",):
                h.remove(k, ignore_missing=True)
            self.__dict__["_wcs"] = WCS(h)
        return self.__dict__["_wcs"]

    @property
    def bunit(self) -> str:
        return str(self.header("IMAGE").get("BUNIT", "")).strip()

    @property
    def blank_spec(self) -> set[tuple[int, int]]:
        """(detector, subchannel) pairs listed in BLANKCH (e.g. 'D3:17,D4:01')."""
        out = set()
        for item in str(self.header("PRIMARY").get("BLANKCH", "")).split(","):
            m = re.fullmatch(r"\s*D(\d):(\d+)\s*", item)
            if m:
                out.add((int(m[1]), int(m[2])))
        return out

    @property
    def channels(self) -> list[Channel]:
        blank = self.blank_spec
        out = []
        for i, r in enumerate(self.channels_table):
            det, sub = int(r["DETECTOR"]), int(r["SUBCHAN"])
            out.append(Channel(plane=i, number=i + 1, detector=det, subchannel=sub,
                               wavelength_um=float(r["WAVELENGTH"]), wl_min_um=float(r["WL_MIN"]),
                               wl_max_um=float(r["WL_MAX"]), bandwidth_um=float(r["BANDWIDTH"]),
                               resolving_power=float(r["R"]), blank=(det, sub) in blank))
        return out

    @property
    def pixel_order(self) -> int:
        """HEALPix order of the mosaic pixels (tile order + log2 of the tile width)."""
        return self.order + int(round(math.log2(self.shape[2])))

    @property
    def pixel_solid_angle_sr(self) -> float:
        """Solid angle of every mosaic pixel: HEALPix pixels have equal area, 4*pi / (12 * 4**k)."""
        return 4 * math.pi / (12 * 4 ** self.pixel_order)

    @property
    def pixel_scale_arcsec(self) -> float:
        return math.degrees(math.sqrt(self.pixel_solid_angle_sr)) * 3600.0

    @property
    def mjd_range(self) -> tuple[float | None, float | None]:
        h = self.header("PRIMARY")
        return h.get("MJD-BEG"), h.get("MJD-END")

    def provenance(self) -> dict:
        h = self.header("PRIMARY")
        beg, end = self.mjd_range
        return {"tile": f"Norder{self.order}/Npix{self.ipix}", "url": self.url, "size_bytes": self.size,
                "etag": self.etag, "last_modified": self.last_modified, "pipeline_version": h.get("VERSION"),
                "created": h.get("DATE"), "inputs_from": h.get("DATE-BEG"), "inputs_to": h.get("DATE-END"),
                "mjd_beg": beg, "mjd_end": end, "blank_channels": h.get("BLANKCH"), "bunit": self.bunit}

    def ranges_for_rows(self, ext: str, planes, y0: int, y1: int) -> list[tuple[int, int]]:
        """Byte ranges of rows y0..y1 (inclusive, full width) of each plane in ``planes``."""
        nz, ny, nx = self.shape
        item = self.dtype(ext).itemsize
        base = self.data_offset[ext]
        out = []
        for p in planes:
            if not (0 <= p < nz and 0 <= y0 <= y1 < ny):
                raise ValueError(f"plano {p} o filas {y0}-{y1} fuera del cubo")
            a = base + ((p * ny + y0) * nx) * item
            out.append((a, a + (y1 - y0 + 1) * nx * item))
        return out

    def read_rows(self, ext_planes: dict[str, list[int]], y0: int, y1: int,
                  x0: int = 0, x1: int | None = None) -> dict[str, np.ndarray]:
        """{ext: array (n_planes, rows, cols)} in native byte order (values unchanged)."""
        x1 = self.shape[2] - 1 if x1 is None else x1
        spec = {ext: self.ranges_for_rows(ext, planes, y0, y1) for ext, planes in ext_planes.items()}
        got = read_ranges(self.url, [r for rs in spec.values() for r in rs], self.size, self.etag)
        out = {}
        for ext, rs in spec.items():
            dt = self.dtype(ext)
            stack = [np.frombuffer(got[r], dtype=dt).reshape(y1 - y0 + 1, self.shape[2])[:, x0:x1 + 1]
                     for r in rs]
            out[ext] = np.stack(stack).astype(dt.newbyteorder("="))
        return out

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _validate_layout(t: CubeTile) -> None:
    for ext in CUBE_EXTENSIONS:
        if ext not in t.headers:
            raise CubeFormatError(f"falta la extensión {ext}")
        h = t.header(ext)
        if int(h.get("NAXIS", 0)) != 3:
            raise CubeFormatError(f"{ext} no es un cubo 3D")
        if (int(h["NAXIS1"]), int(h["NAXIS2"]), int(h["NAXIS3"])) != t.shape[::-1]:
            raise CubeFormatError(f"{ext} con forma distinta de IMAGE")
        if float(h.get("BSCALE", 1)) != 1 or float(h.get("BZERO", 0)) != 0:
            raise CubeFormatError(f"{ext} con BSCALE/BZERO (no previsto)")
        if int(h["BITPIX"]) not in _BITPIX_DTYPE:
            raise CubeFormatError(f"BITPIX {h['BITPIX']} no previsto")
    hi = t.header("IMAGE")
    if int(hi.get("ORDER", -1)) != t.order or int(hi.get("NPIX", -1)) != t.ipix:
        raise CubeFormatError(f"cabecera ORDER/NPIX ({hi.get('ORDER')}/{hi.get('NPIX')}) ≠ tesela pedida "
                              f"({t.order}/{t.ipix})")
    if t.bunit != "MJy/sr":
        raise CubeFormatError(f"BUNIT {t.bunit!r} ≠ 'MJy/sr'")
    nz = t.shape[0]
    if len(t.channels_table) != nz:
        raise CubeFormatError(f"SPECTRAL_CHANNELS tiene {len(t.channels_table)} filas para {nz} planos")
    nx = t.shape[2]
    if nx & (nx - 1) or t.shape[1] != nx:
        raise CubeFormatError("la tesela no es cuadrada de lado potencia de 2 (HEALPix)")
    for c in t.channels:
        if c.number != 17 * (c.detector - 1) + c.subchannel:
            raise CubeFormatError(f"plano {c.plane}: D{c.detector} subcanal {c.subchannel} no sigue "
                                  "índice = 17·(banda−1) + (canal−1)")
        if not (c.wl_min_um <= c.wavelength_um <= c.wl_max_um):
            raise CubeFormatError(f"canal {c.number}: λ fuera de [WL_MIN, WL_MAX]")


def read_layout(ipix: int, order: int = config.CUBE_ORDER, url: str | None = None) -> CubeTile:
    """Read headers and channel tables of one tile with a few small range requests (~45 KB)."""
    url = url or tile_url(ipix, order)
    rd = _SpanReader(url)
    rd.read(0, BLOCK)
    headers, offsets, nbytes, off = {}, {}, {}, 0
    channels, wcs_wave = None, None
    while off < rd.size:
        buf = b""
        while (end := _end_card(buf)) is None:
            if len(buf) > 40 * BLOCK:
                raise CubeFormatError("cabecera FITS sin END")
            buf += rd.read(off + len(buf), min(off + len(buf) + BLOCK, rd.size))
        hlen = (end + 80 + BLOCK - 1) // BLOCK * BLOCK
        text = buf[:hlen].decode("ascii")
        h = fits.Header.fromstring(text)
        name = "PRIMARY" if off == 0 else str(h.get("EXTNAME", "")).strip()
        n = _data_nbytes(h)
        headers[name], offsets[name], nbytes[name] = text, off + hlen, n
        if h.get("XTENSION", "").strip() == "BINTABLE":
            raw = rd.read(off, off + hlen + (n + BLOCK - 1) // BLOCK * BLOCK)
            from astropy.table import Table

            tab = Table.read(fits.BinTableHDU.fromstring(raw))
            if name == "SPECTRAL_CHANNELS":
                channels = [{c: (v.item() if hasattr(v, "item") else v) for c, v in zip(tab.colnames, row)}
                            for row in tab]
            elif name == "WCS-WAVE":
                wcs_wave = [float(v) for v in np.asarray(tab["WAVELENGTHS"]).ravel()]
        off += hlen + (n + BLOCK - 1) // BLOCK * BLOCK
    if off != rd.size:
        raise CubeFormatError(f"estructura FITS ({off} B) ≠ tamaño del archivo ({rd.size} B)")
    if channels is None:
        raise CubeFormatError("falta la tabla SPECTRAL_CHANNELS")
    t = CubeTile(ipix=int(ipix), order=order, url=url, size=rd.size, etag=rd.etag,
                 last_modified=rd.last_modified, headers=headers, data_offset=offsets, data_nbytes=nbytes,
                 channels_table=channels, wcs_wave_um=wcs_wave or [])
    _validate_layout(t)
    return t


_tiles: dict[tuple[int, int], CubeTile] = {}
_tiles_lock = threading.Lock()


def _layout_cache_path(ipix: int, order: int) -> Path:
    return config.CACHE_DIR / "meta" / f"cube_o{order}_{ipix}.json"


def open_tile(ipix: int, order: int = config.CUBE_ORDER, refresh: bool = False) -> CubeTile:
    """CubeTile for a HEALPix tile: memory, then the JSON layout cache (12 h), then IRSA."""
    key = (order, int(ipix))
    with _tiles_lock:
        t = _tiles.get(key)
    if t is not None and not refresh and time.time() - t.read_at < config.METADATA_CACHE_MAX_AGE_S:
        return t
    path = _layout_cache_path(ipix, order)
    t = None
    if not refresh and path.exists() and time.time() - path.stat().st_mtime < config.METADATA_CACHE_MAX_AGE_S:
        try:
            t = CubeTile(**json.loads(path.read_text(encoding="utf-8")))
            _validate_layout(t)
        except (ValueError, TypeError, KeyError, CubeFormatError):
            t = None
    if t is None:
        t = read_layout(ipix, order)
        try:
            archive.atomic_write(path, json.dumps(t.to_dict()))
        except OSError:
            pass
    with _tiles_lock:
        _tiles[key] = t
    return t


def _forget_tile(ipix: int, order: int = config.CUBE_ORDER) -> None:
    with _tiles_lock:
        _tiles.pop((order, int(ipix)), None)
    try:
        _layout_cache_path(ipix, order).unlink(missing_ok=True)
    except OSError:
        pass


def hips_properties() -> dict:
    """HiPS 'properties' of the all-sky cube (key = value lines), cached 12 h."""
    path = config.CACHE_DIR / "meta" / "cube_hips_properties.json"
    if path.exists() and time.time() - path.stat().st_mtime < config.METADATA_CACHE_MAX_AGE_S:
        return json.loads(path.read_text(encoding="utf-8"))
    r = archive.http_get(f"{config.CUBE_HIPS_URL}/properties")
    props = {}
    for line in r.text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            props[k.strip()] = v.strip()
    try:
        archive.atomic_write(path, json.dumps(props))
    except OSError:
        pass
    return props


# ----------------------------------------------------------------------------- geometry
def display_wcs(ra: float, dec: float, size_deg: float, npix: int) -> WCS:
    """North-up, east-left TAN frame centred on (ra, dec): for sampling and display only."""
    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [ra, dec]
    w.wcs.crpix = [(npix + 1) / 2, (npix + 1) / 2]
    s = size_deg / npix
    w.wcs.cdelt = [-s, s]
    w.wcs.radesys = "ICRS"
    w.array_shape = (npix, npix)
    return w


def _disc_samples(ra: float, dec: float, radius_deg: float, step_deg: float):
    n = int(math.ceil(2 * radius_deg / step_deg)) + 1
    w = display_wcs(ra, dec, 2 * radius_deg, n)
    yy, xx = np.mgrid[0:n, 0:n]
    r, d = w.pixel_to_world_values(xx.ravel(), yy.ravel())
    keep = separation_deg(ra, dec, r, d) <= radius_deg
    return np.asarray(r)[keep], np.asarray(d)[keep]


@dataclass
class TileBox:
    tile: CubeTile
    x0: int
    x1: int
    y0: int
    y1: int


def tile_boxes(ra: float, dec: float, radius_deg: float, order: int = config.CUBE_ORDER) -> list[TileBox]:
    """Tiles and pixel boxes covering a disc (every pixel whose centre lies within it).

    The disc is sampled every 1/3 pixel; each sample's tile comes from ``healpix_nest`` and
    must fall inside that tile's WCS footprint (a run-time check of both)."""
    pix_deg = math.degrees(math.sqrt(4 * math.pi / (12 * 4 ** (order + 9))))
    r, d = _disc_samples(ra, dec, radius_deg + 1.5 * pix_deg, pix_deg / 3)
    ip = healpix_nest(order, r, d)
    out = []
    for ipix in np.unique(ip):
        t = open_tile(int(ipix), order)
        sel = ip == ipix
        x, y = t.wcs.world_to_pixel_values(r[sel], d[sel])
        nz, ny, nx = t.shape
        if np.any((x < -0.51) | (x > nx - 0.49) | (y < -0.51) | (y > ny - 0.49)) or not np.all(np.isfinite(x)):
            raise CubeFormatError(f"posiciones asignadas a la tesela {ipix} caen fuera de su WCS "
                                  "(índice HEALPix y WCS no concuerdan)")
        out.append(TileBox(t, int(max(0, math.floor(x.min()) - 1)), int(min(nx - 1, math.ceil(x.max()) + 1)),
                           int(max(0, math.floor(y.min()) - 1)), int(min(ny - 1, math.ceil(y.max()) + 1))))
    return out


def tile_for(ra: float, dec: float, order: int = config.CUBE_ORDER) -> CubeTile:
    return open_tile(int(healpix_nest(order, ra, dec)), order)


# ----------------------------------------------------------------------------- channel maps
@dataclass
class Patch:
    """Native pixels of one tile inside a field: values exactly as stored in the cube."""

    tile: CubeTile
    x0: int
    y0: int
    image: np.ndarray        # MJy/sr (ZODI already subtracted by the pipeline); NaN = no data
    nhits: np.ndarray        # number of input pixels averaged
    flags: np.ndarray        # OR of OVERFLOW / SOURCE / OUTLIER of the inputs

    @property
    def valid(self) -> np.ndarray:
        return np.isfinite(self.image) & (self.nhits > 0)

    def centres_world(self):
        ny, nx = self.image.shape
        yy, xx = np.mgrid[0:ny, 0:nx]
        return self.tile.wcs.pixel_to_world_values(xx + self.x0, yy + self.y0)

    def corners_world(self):
        ny, nx = self.image.shape
        yy, xx = np.mgrid[0:ny + 1, 0:nx + 1]
        return self.tile.wcs.pixel_to_world_values(xx + self.x0 - 0.5, yy + self.y0 - 0.5)


def flag_bits(tile: CubeTile) -> dict[int, str]:
    """Bit -> name from the FLAGS header (MSKNnnnn keywords, as shipped with the data)."""
    if "_flagbits" not in tile.__dict__:
        h, bits = tile.header("FLAGS"), {}
        for k in h:
            m = re.fullmatch(r"MSKN(\d{4})", k)
            if m:
                bits[int(m[1])] = str(h[k]).strip()
        tile.__dict__["_flagbits"] = bits
    return tile.__dict__["_flagbits"]


def flag_names(tile: CubeTile, value: int) -> list[str]:
    bits = flag_bits(tile)
    return [bits.get(b, f"BIT_{b}") for b in range(32) if int(value) >> b & 1]


@dataclass
class ChannelMap:
    channel: Channel
    ra: float
    dec: float
    field_deg: float
    patches: list[Patch]

    def in_field(self, p: Patch) -> np.ndarray:
        r, d = p.centres_world()
        return separation_deg(self.ra, self.dec, r, d) <= self.field_deg / 2

    def summary(self) -> dict:
        n_field = n_valid = 0
        vals, hits, fl = [], [], 0
        flag_px = {f: 0 for f in PROPAGATED_FLAGS}
        for p in self.patches:
            f = self.in_field(p)
            v = p.valid & f
            n_field += int(f.sum())
            n_valid += int(v.sum())
            vals.append(p.image[v])
            hits.append(p.nhits[v])
            for b, nm in flag_bits(p.tile).items():
                if nm in flag_px:
                    flag_px[nm] += int(((p.flags[v] >> b) & 1).sum())
        vals = np.concatenate(vals) if vals else np.array([])
        hits = np.concatenate(hits) if hits else np.array([], int)
        return {"n_field": n_field, "n_valid": n_valid, "valid_fraction": n_valid / n_field if n_field else 0.0,
                "nhits_median": float(np.median(hits)) if hits.size else 0.0,
                "nhits_min": int(hits.min()) if hits.size else 0,
                "value_p1": float(np.percentile(vals, 1)) if vals.size else float("nan"),
                "value_p99": float(np.percentile(vals, 99)) if vals.size else float("nan"),
                "flag_pixels": flag_px, "tiles": [p.tile.ipix for p in self.patches]}


def channel_map(ra: float, dec: float, field_deg: float, plane: int) -> ChannelMap:
    """Real cube values of one channel over a circular field (all tiles it touches)."""
    boxes = tile_boxes(ra, dec, field_deg / 2)
    patches, ch = [], None
    for b in boxes:
        try:
            got = b.tile.read_rows({e: [plane] for e in CUBE_EXTENSIONS}, b.y0, b.y1, b.x0, b.x1)
        except FileChangedError:
            _forget_tile(b.tile.ipix)
            raise
        patches.append(Patch(b.tile, b.x0, b.y0, got["IMAGE"][0].astype(np.float64), got["NHITS"][0],
                             got["FLAGS"][0]))
        ch = ch or b.tile.channels[plane]
    return ChannelMap(ch, ra, dec, field_deg, patches)


# ----------------------------------------------------------------------------- spectra
@dataclass(frozen=True)
class Aperture:
    """Radii in mosaic pixels (12.9 arcsec)."""

    r_ap: float = config.CUBE_APERTURE_DEFAULT_PX[0]
    r_in: float = config.CUBE_APERTURE_DEFAULT_PX[1]
    r_out: float = config.CUBE_APERTURE_DEFAULT_PX[2]

    def validate(self) -> "Aperture":
        mx = config.CUBE_APERTURE_MAX_PX
        if not (0 < self.r_ap <= mx[0] and self.r_ap < self.r_in < self.r_out and self.r_in <= mx[1]
                and self.r_out <= mx[2]):
            raise ValueError(f"Radios no válidos (apertura {self.r_ap}, anillo {self.r_in}–{self.r_out} px): "
                             f"se requiere 0 < apertura ≤ {mx[0]} < … y apertura < interior < exterior ≤ {mx[2]}.")
        return self


STATUS_TEXT = {
    "ok": "medido",
    "blank": "canal sin datos en DR1 (BLANKCH)",
    "no_data_aperture": "apertura con píxeles sin datos (NHITS = 0)",
    "no_background": "fondo insuficiente en el anillo",
}


@dataclass
class Spectrum:
    ra: float
    dec: float
    aperture: Aperture
    pixel_scale_arcsec: float
    pixel_solid_angle_sr: float
    rows: list[dict]
    tiles: list[dict]
    n_aperture_px: float           # sum of aperture weights (pixels)
    n_annulus_px: int
    subpixels: int
    warnings: list[str]

    def table(self):
        import pandas as pd

        return pd.DataFrame(self.rows)

    @property
    def n_measured(self) -> int:
        return sum(r["status"] == "ok" for r in self.rows)


def _aperture_weights(tile: CubeTile, x0: int, y0: int, shape, ra: float, dec: float, r_px: float,
                      pix_arcsec: float, n: int) -> np.ndarray:
    """Fraction of each pixel inside a circle of r_px pixels: n x n sub-pixel samples in the
    tile's pixel coordinates (equivalent to photutils' 'subpixel' method), distances on the sky."""
    ny, nx = shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    rc, dc = tile.wcs.pixel_to_world_values(xx + x0, yy + y0)
    dist = separation_deg(ra, dec, rc, dc) * 3600 / pix_arcsec
    w = (dist < r_px).astype(float)
    edge = np.abs(dist - r_px) < 1.0
    if edge.any():
        off = (np.arange(n) + 0.5) / n - 0.5
        ox, oy = np.meshgrid(off, off)
        ex, ey = xx[edge][:, None] + x0 + ox.ravel()[None, :], yy[edge][:, None] + y0 + oy.ravel()[None, :]
        rs, ds = tile.wcs.pixel_to_world_values(ex.ravel(), ey.ravel())
        inside = (separation_deg(ra, dec, rs, ds) * 3600 / pix_arcsec < r_px).reshape(ex.shape)
        w[edge] = inside.mean(axis=1)
    return w


def extract_spectrum(ra: float, dec: float, aperture: Aperture | None = None, subpixels: int = 5) -> Spectrum:
    """Exploratory spectrum at (ra, dec) from the cube (official tutorial method).

    Per channel: aperture sum of IMAGE (pixel fractions by sub-pixel sampling), minus the
    sigma-clipped (3 sigma, 10 iterations) mean of the annulus (pixel centres) times the
    aperture area, times the pixel solid angle -> mJy. A channel with any aperture pixel
    without data, or with < 50 % of the annulus holding data, gets no value (never filled).
    Also returned: the surface brightness of the single pixel that contains (ra, dec).
    No uncertainty is computed (the cube has no VARIANCE) and no aperture correction is applied.
    """
    from astropy.stats import sigma_clipped_stats

    ap = (aperture or Aperture()).validate()
    home = tile_for(ra, dec)
    pix = home.pixel_scale_arcsec
    boxes = tile_boxes(ra, dec, (ap.r_out + 1) * pix / 3600)
    nz = home.shape[0]
    planes = list(range(nz))
    ap_sum = np.zeros(nz)
    ap_bad = np.zeros(nz, bool)
    ap_w_total, ann_vals = 0.0, [[] for _ in planes]
    nh_min = np.full(nz, np.iinfo(np.int64).max)
    nh_sum = np.zeros(nz)
    flags_or = np.zeros(nz, np.int64)
    pixel_val = np.full(nz, np.nan)
    pixel_nh = np.zeros(nz, int)
    pixel_fl = np.zeros(nz, np.int64)
    n_ann, tiles = 0, []
    xh, yh = home.wcs.world_to_pixel_values(ra, dec)
    xc, yc = int(round(float(xh))), int(round(float(yh)))     # pixel that contains (ra, dec)
    for b in boxes:
        t = b.tile
        if t.shape[0] != nz:
            raise CubeFormatError("teselas con distinto número de canales")
        ny, nx = b.y1 - b.y0 + 1, b.x1 - b.x0 + 1
        yy, xx = np.mgrid[0:ny, 0:nx]
        rc, dc = t.wcs.pixel_to_world_values(xx + b.x0, yy + b.y0)
        dist = separation_deg(ra, dec, rc, dc) * 3600 / pix
        w = _aperture_weights(t, b.x0, b.y0, (ny, nx), ra, dec, ap.r_ap, pix, subpixels)
        ann = (dist >= ap.r_in) & (dist < ap.r_out)
        in_ap = w > 0
        contains = t.ipix == home.ipix and b.x0 <= xc <= b.x1 and b.y0 <= yc <= b.y1
        if not (in_ap.any() or ann.any() or contains):
            continue
        # IMAGE for every row of the box; NHITS/FLAGS only for the aperture rows (+ the home pixel).
        need = in_ap.any(axis=1)
        if contains:
            need[yc - b.y0] = True
        rows = np.where(need)[0]
        try:
            img = t.read_rows({"IMAGE": planes}, b.y0, b.y1, b.x0, b.x1)["IMAGE"].astype(np.float64)
            if rows.size:
                r0, r1 = int(rows.min()), int(rows.max())
                aux = t.read_rows({"NHITS": planes, "FLAGS": planes}, b.y0 + r0, b.y0 + r1, b.x0, b.x1)
        except FileChangedError:
            _forget_tile(t.ipix)
            raise
        tiles.append(t.provenance())
        n_ann += int(ann.sum())
        for p in planes:
            a = img[p][ann]
            ann_vals[p].append(a[np.isfinite(a)])
        if rows.size and in_ap.any():
            wa = w[r0:r1 + 1]
            m = wa > 0
            ap_w_total += float(wa.sum())
            vals = img[:, r0:r1 + 1, :][:, m]                   # (planes, n_aperture_pixels)
            ap_bad |= ~np.all(np.isfinite(vals), axis=1)
            ap_sum += np.nansum(vals * wa[m][None, :], axis=1)
            nh = aux["NHITS"][:, m]
            nh_min = np.minimum(nh_min, nh.min(axis=1))
            nh_sum += (nh * wa[m][None, :]).sum(axis=1)
            flags_or |= np.bitwise_or.reduce(aux["FLAGS"][:, m].astype(np.int64), axis=1)
        if contains:
            pixel_val = img[:, yc - b.y0, xc - b.x0]
            pixel_nh = aux["NHITS"][:, yc - b.y0 - r0, xc - b.x0]
            pixel_fl = aux["FLAGS"][:, yc - b.y0 - r0, xc - b.x0].astype(np.int64)
    rows = []
    warn = []
    for c in home.channels:
        p = c.plane
        a = np.concatenate(ann_vals[p]) if ann_vals[p] else np.array([])
        row = {"canal": c.number, "plano": c.plane, "detector": c.detector, "subcanal": c.subchannel,
               "lambda_um": c.wavelength_um, "ancho_um": c.bandwidth_um, "lambda_min_um": c.wl_min_um,
               "lambda_max_um": c.wl_max_um, "R": c.resolving_power,
               "pixel_mjysr": float(pixel_val[p]) if np.isfinite(pixel_val[p]) else None,
               "pixel_nhits": int(pixel_nh[p]), "pixel_flags": "|".join(flag_names(home, int(pixel_fl[p]))),
               "flujo_mjy": None, "fondo_mjysr": None, "fondo_sigma_mjysr": None,
               "n_fondo": int(a.size), "nhits_min_apertura": int(nh_min[p]) if nh_min[p] < 2**62 else 0,
               "nhits_medio_apertura": float(nh_sum[p] / ap_w_total) if ap_w_total else 0.0,
               "flags_apertura": "|".join(flag_names(home, int(flags_or[p]))),
               "precaucion": any(f in flag_names(home, int(flags_or[p])) for f in CAUTION_FLAGS)}
        if c.blank:
            row["status"] = "blank"
            if a.size or np.isfinite(pixel_val[p]) or not ap_bad[p]:
                warn.append(f"El canal {c.number} figura en BLANKCH pero contiene valores en esta región; "
                            "se muestra como sin datos según la documentación.")
        elif ap_bad[p] or ap_w_total == 0:
            row["status"] = "no_data_aperture"
        elif a.size < max(10, config.CUBE_ANNULUS_MIN_VALID * n_ann):
            row["status"] = "no_background"
        else:
            mean, _, std = sigma_clipped_stats(a, sigma=3.0, maxiters=10)
            net = ap_sum[p] - float(mean) * ap_w_total               # MJy/sr x pixel
            row.update(status="ok", fondo_mjysr=float(mean), fondo_sigma_mjysr=float(std),
                       flujo_mjy=float(net * home.pixel_solid_angle_sr * 1e9))   # MJy -> mJy
        row["estado"] = STATUS_TEXT[row["status"]]
        rows.append(row)
    if len({t["tile"] for t in tiles}) > 1:
        warn.append("La apertura o el anillo abarcan varias teselas HEALPix: se combinan sus píxeles (misma "
                    "rejilla HEALPix, mismo ángulo sólido por píxel).")
    return Spectrum(ra=ra, dec=dec, aperture=ap, pixel_scale_arcsec=pix,
                    pixel_solid_angle_sr=home.pixel_solid_angle_sr, rows=rows, tiles=tiles,
                    n_aperture_px=ap_w_total, n_annulus_px=n_ann, subpixels=subpixels, warnings=warn)


def cube_epoch_position(astrometry, ra: float | None = None, dec: float | None = None):
    """Position of a catalogue target for the cube: propagated to the middle of the input
    date range of its tile (MJD-BEG/MJD-END of the tile header).

    Returns (ra, dec, info). ``info`` has the dates and the motion over the input range;
    without proper motion the catalogue position is returned unchanged.
    """
    ra0, dec0 = (astrometry.ra_deg, astrometry.dec_deg) if astrometry is not None else (ra, dec)
    if astrometry is None or not astrometry.has_proper_motion:
        return ra0, dec0, {"propagated": False}
    from astropy.time import Time

    guess = astrometry.position_at(Time.now())
    t = tile_for(*guess)
    beg, end = t.mjd_range
    if beg is None or end is None:
        return guess[0], guess[1], {"propagated": True, "epoch": "fecha actual (la tesela no declara MJD-BEG/END)"}
    mid = 0.5 * (beg + end)
    ra_m, dec_m = astrometry.position_at(mid)
    if int(healpix_nest(config.CUBE_ORDER, ra_m, dec_m)) != t.ipix:
        t = tile_for(ra_m, dec_m)
        beg, end = t.mjd_range
        mid = 0.5 * (beg + end)
        ra_m, dec_m = astrometry.position_at(mid)
    r0, d0 = astrometry.position_at(beg)
    r1, d1 = astrometry.position_at(end)
    return ra_m, dec_m, {
        "propagated": True, "mjd_mid": mid, "mjd_beg": beg, "mjd_end": end,
        "date_mid": Time(mid, format="mjd").isot[:10], "date_beg": Time(beg, format="mjd").isot[:10],
        "date_end": Time(end, format="mjd").isot[:10],
        "motion_over_inputs_arcsec": float(separation_deg(r0, d0, r1, d1) * 3600)}


__all__ = ["Aperture", "Channel", "ChannelMap", "CubeTile", "Patch", "Spectrum", "channel_map",
           "cube_epoch_position", "display_wcs", "extract_spectrum", "healpix_nest", "hips_properties",
           "io_stats", "open_tile", "read_layout", "tile_url", "CubeFormatError", "RangeNotHonoured",
           "FileChangedError"]
