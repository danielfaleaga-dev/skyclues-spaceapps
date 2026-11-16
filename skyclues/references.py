"""Bounded, read-only Gaia DR3 queries and explicitly approximate epoch positions.

The query selects a circular field at the *catalogue* epoch. It is not a
cross-match and is not complete for sources that move into the field later.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
from datetime import datetime, timezone

import numpy as np
import requests

from .config import HTTP_HEADERS
from .targets import validate_coordinates, validate_fov_deg

GAIA_TAP = "https://gea.esac.esa.int/tap-server/tap/sync"
GAIA_TABLE = "gaiadr3.gaia_source"
GAIA_DOC = "https://gea.esac.esa.int/archive/documentation/GDR3/Gaia_archive/chap_datamodel/sec_dm_main_source_catalogue/ssec_dm_gaia_source.html"
WISE_URLS = {b: f"https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/{b}" for b in ("W1", "W2")}
ALADIN_JS = "https://cdn.jsdelivr.net/npm/aladin-lite@3.8.1/dist/aladin.js"
MAX_SOURCES = 500
MAX_BYTES = 2 * 1024 * 1024
COLUMNS = ("source_id", "ra", "dec", "ref_epoch", "pmra", "pmdec", "parallax",
           "radial_velocity", "phot_g_mean_mag", "ruwe", "ra_error", "dec_error",
           "pmra_error", "pmdec_error", "parallax_error")


class ReferenceError(RuntimeError):
    """Unavailable service or invalid response; never interpreted as an empty sky."""


def gaia_query(ra: float, dec: float, fov: float, limit: int = MAX_SOURCES) -> str:
    ra, dec = validate_coordinates(ra, dec)
    fov = validate_fov_deg(fov)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_SOURCES:
        raise ValueError(f"Gaia limit: integer between 1 and {MAX_SOURCES}.")
    return (f"SELECT TOP {limit + 1} {','.join(COLUMNS)} FROM {GAIA_TABLE} "
            f"WHERE 1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',{ra:.10f},{dec:.10f},{fov / 2:.10f})) "
            "ORDER BY phot_g_mean_mag ASC, source_id ASC")


def parse_gaia(raw: bytes, limit: int) -> tuple[list[dict], bool]:
    """Validate the entire result, preserving 64-bit source identifiers as strings."""
    if len(raw) > MAX_BYTES:
        raise ReferenceError("Gaia exceeded the response limit (2 MiB).")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise ValueError("unexpected columns")
        rows = []
        for r in reader:
            if len(rows) >= limit + 1 or None in r:
                raise ValueError("more rows/columns than requested")
            sid = r["source_id"]
            if not sid.isdecimal() or not 0 < int(sid) < 2**63:
                raise ValueError("invalid source_id")
            row = {"source_id": sid}
            for k in COLUMNS[1:]:
                v = float(r[k]) if r[k] and r[k].strip() else None
                row[k] = v if v is not None and math.isfinite(v) else None
            validate_coordinates(row["ra"], row["dec"])
            if row["ref_epoch"] != 2016.0:
                raise ValueError("unexpected epoch for DR3")
            rows.append(row)
        if len({r["source_id"] for r in rows}) != len(rows):
            raise ValueError("repeated identifiers")
        return rows[:limit], len(rows) > limit
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, csv.Error) as err:
        raise ReferenceError(f"Invalid Gaia response: {err}") from err


def fetch_gaia(ra: float, dec: float, fov: float, limit: int = MAX_SOURCES) -> dict:
    query = gaia_query(ra, dec, fov, limit)
    try:
        # A single bounded request. Retrying is an explicit UI action; no long hidden waits.
        with requests.get(GAIA_TAP, params={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv",
                          "QUERY": query}, headers=HTTP_HEADERS, timeout=(8, 25), stream=True) as response:
            response.raise_for_status()
            chunks, n = [], 0
            for chunk in response.iter_content(65536):
                n += len(chunk)
                if n > MAX_BYTES:
                    raise ReferenceError("Gaia exceeded the response limit (2 MiB).")
                chunks.append(chunk)
        raw = b"".join(chunks)
    except requests.RequestException as err:
        raise ReferenceError(f"Gaia DR3 not available: {type(err).__name__}. You can retry; WISE is independent.") from err
    rows, truncated = parse_gaia(raw, limit)
    return {"sources": rows, "truncated": truncated, "limit": limit, "query": query,
            "endpoint": GAIA_TAP, "table": GAIA_TABLE, "ra": float(ra), "dec": float(dec),
            "fov": float(fov), "catalogue_epoch": 2016.0,
            "retrieved_utc": datetime.now(timezone.utc).isoformat(),
            "response_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def expected_position(source: dict, epoch: float) -> tuple[float, float] | None:
    """Uniform tangential motion on the sphere, with no distance or radial motion.

    Uses ra, dec, ref_epoch, pmra (= mu_alpha*cos(dec)), pmdec only. The unit
    direction is normalize(p + dt*v). No parallax, perspective acceleration,
    covariance, binaries, or apparent observer position. Context, not precision
    astrometry. Missing proper motion remains missing, never implicitly zero.
    """
    if not math.isfinite(epoch) or not 2000 <= epoch <= 2050:
        raise ValueError("Computed epoch outside 2000–2050 (Julian year TCB).")
    if any(source.get(k) is None for k in ("ra", "dec", "ref_epoch", "pmra", "pmdec")):
        return None
    a, d = np.deg2rad([source["ra"], source["dec"]])
    p = np.array([np.cos(d)*np.cos(a), np.cos(d)*np.sin(a), np.sin(d)])
    east = np.array([-np.sin(a), np.cos(a), 0.0])
    north = np.array([-np.sin(d)*np.cos(a), -np.sin(d)*np.sin(a), np.cos(d)])
    v = np.deg2rad(1 / 3600000) * (source["pmra"] * east + source["pmdec"] * north)
    p += (epoch - source["ref_epoch"]) * v
    p /= np.linalg.norm(p)
    return float(np.rad2deg(np.arctan2(p[1], p[0])) % 360), float(np.rad2deg(np.arcsin(p[2])))
