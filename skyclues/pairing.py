"""Search for scientifically comparable pairs of SPHEREx observations.

Stage 1 - metadata only (cheap):
    SIA2 records -> s_region homography -> target pixel on the detector,
    margin of the field inside the detector, and an estimate of the LVF
    wavelength at the target from the detector's WCS-WAVE table (read with a
    ~11 kB HTTP range request on one file per detector and collection).
Stage 2 - FITS (exact):
    download IBE cutouts of the best candidate pairs and evaluate them with
    ``compare.evaluate_pair`` using each file's own WCS, FLAGS and spectral WCS.
"""

from __future__ import annotations

import io
import itertools
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from astropy.io import fits
from astropy.time import Time

from . import archive, config, fitsdata
from .compare import evaluate_pair
from .geometry import bilinear_lookup


@dataclass
class Candidate:
    rec: archive.ObservationRecord
    x: float
    y: float
    margin_px: float
    lam_um: float = float("nan")
    bw_um: float = float("nan")
    # Pixel positions of sample points across the field (centre + ring),
    # identical sky points for every candidate, and the wavelength there.
    xs: np.ndarray | None = None
    ys: np.ndarray | None = None
    lam_pts: np.ndarray | None = None


def field_samples(ra: float, dec: float, field_deg: float, n_ring: int = 8):
    """Centre plus a ring at 0.9 x the field radius (sky coordinates)."""
    ang = np.linspace(0, 2 * np.pi, n_ring, endpoint=False)
    r = 0.45 * field_deg
    cosd = max(np.cos(np.radians(dec)), 1e-6)
    ras = np.concatenate([[ra], ra + r * np.cos(ang) / cosd])
    decs = np.concatenate([[dec], dec + r * np.sin(ang)])
    return ras, decs


@lru_cache(maxsize=256)
def wave_table_from_url(access_url: str) -> dict:
    """WCS-WAVE table of a full Level-2 file (disk-cached per file URL)."""
    cpath = archive._meta_cache_path("wave", access_url)
    if cpath.exists():
        d = json.loads(cpath.read_text(encoding="utf-8"))
        return {**d, "X": np.array(d["X"]), "Y": np.array(d["Y"]), "VALUES": np.array(d["VALUES"])}
    tab = _wave_table_live(access_url)
    archive.atomic_write(cpath, json.dumps({**tab, "X": tab["X"].tolist(), "Y": tab["Y"].tolist(),
                                            "VALUES": tab["VALUES"].tolist()}))
    return tab


def _wave_table_live(access_url: str) -> dict:
    """Read the WCS-WAVE table of a full Level-2 file from its last bytes."""
    # Same retry policy as every archive request: transient errors only, bounded.
    # Only 206 (partial content) is accepted; any other non-transient status is permanent.
    blob = archive.http_get(access_url, headers={"Range": "bytes=-11520"}, ok_status=(206,)).content
    # The tail is 4 FITS blocks and files are block-aligned, so HDU headers
    # can only start at multiples of 2880 bytes inside it.
    start = blob.rfind(b"XTENSION= 'BINTABLE'")
    while start > 0 and start % 2880:
        start = blob.rfind(b"XTENSION= 'BINTABLE'", 0, start)
    if start < 0 or start % 2880:
        raise RuntimeError("WCS-WAVE header not found in file tail")
    primary = fits.PrimaryHDU().header.tostring().encode()
    with fits.open(io.BytesIO(primary + blob[start:])) as hd:
        if hd[1].name != "WCS-WAVE":
            raise RuntimeError(f"Unexpected last extension {hd[1].name}")
        row = hd[1].data[0]
        hist = [str(v) for v in hd[1].header.get("HISTORY", []) if "Calibration source" in str(v)]
        return {"X": np.array(row["X"], float), "Y": np.array(row["Y"], float),
                "VALUES": np.array(row["VALUES"], float), "calibration": " ".join(hist),
                "detector": str(hd[1].header.get("DETECTOR", "")).strip()}


def build_candidates(records, ra, dec, field_deg, min_margin_px=2.0):
    out = []
    sras, sdecs = field_samples(ra, dec, field_deg)
    for rec in records:
        try:
            fp = archive.footprint(rec)
        except ValueError:
            continue
        x, y = fp.sky_to_pixel(ra, dec)
        margin = fp.field_margin_px(ra, dec, field_deg / 2)
        if margin >= min_margin_px:
            xs, ys = fp.sky_to_pixel(sras, sdecs)
            out.append(Candidate(rec=rec, x=float(x), y=float(y), margin_px=margin,
                                 xs=np.asarray(xs), ys=np.asarray(ys)))
    return out


def estimate_wavelengths(cands: list[Candidate]) -> dict:
    """Fill lam/bw estimates; one WCS-WAVE table per (detector, collection)."""
    tables = {}
    groups = {}
    for c in cands:
        groups.setdefault((c.rec.detector, c.rec.collection), []).append(c)
    probes = {key: max(group, key=lambda c: c.margin_px) for key, group in groups.items()}
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = dict(zip(probes, pool.map(lambda p: wave_table_from_url(p.rec.access_url), probes.values())))
    for key, group in groups.items():
        probe, tab = probes[key], fetched[key]
        tables[key] = {"calibration": tab["calibration"], "probe": probe.rec.file_name}
        for c in group:
            lam, bw = bilinear_lookup(tab["X"], tab["Y"], tab["VALUES"], c.x, c.y)
            c.lam_um, c.bw_um = float(lam), float(bw)
            c.lam_pts = np.array([bilinear_lookup(tab["X"], tab["Y"], tab["VALUES"], px, py)[0]
                                  for px, py in zip(c.xs, c.ys)])
    return tables


def rank_pairs(cands: list[Candidate], require_same_collection: bool = False):
    pairs = []
    for a, b in itertools.combinations(cands, 2):
        if a.rec.detector != b.rec.detector:
            continue
        dt = abs(a.rec.mjd_mid - b.rec.mjd_mid)
        if dt < config.MIN_TIME_SEPARATION_DAYS:
            continue
        same_coll = a.rec.collection == b.rec.collection
        if require_same_collection and not same_coll:
            continue
        bw = 0.5 * (a.bw_um + b.bw_um)
        dl = abs(a.lam_um - b.lam_um) / bw
        if not np.isfinite(dl) or dl > config.SPECTRAL_PRESELECT_BW:
            continue
        dl_field = float(np.max(np.abs(a.lam_pts - b.lam_pts)) / bw)
        first, second = (a, b) if a.rec.mjd_mid <= b.rec.mjd_mid else (b, a)
        pairs.append({
            "a": first, "b": second, "dt_days": dt, "dlambda_bw_est": dl,
            "dlambda_field_max_bw_est": dl_field,
            "same_collection": same_coll, "min_margin_px": min(a.margin_px, b.margin_px),
        })

    # 1) spectral match over the whole field (LVF gradients can be anti-parallel
    #    between visits), 2) homogeneous processing, 3) match at the target,
    # 4) margin inside the detector, 5) longer baseline.
    def bucket(v):
        return 0 if v <= config.SPECTRAL_PASS_BW else (1 if v <= config.SPECTRAL_WARN_BW else 2)

    pairs.sort(key=lambda p: (bucket(p["dlambda_field_max_bw_est"]), not p["same_collection"],
                              round(p["dlambda_bw_est"] / 0.05), -min(p["min_margin_px"], 60), -p["dt_days"]))
    return pairs


def find_pair(ra: float, dec: float, field_deg: float = config.DEFAULT_FIELD_DEG,
              collections=config.WIDE_COLLECTIONS, detectors=None,
              max_download_pairs: int = config.MAX_PAIRS_TO_DOWNLOAD,
              require_same_collection: bool = False, log=print):
    """Return (best_result | None, report) for the field centred on (ra, dec)."""
    records = archive.query_images(ra, dec, collections=collections)
    log(f"SIA2: {len(records)} imágenes contienen el objetivo ({', '.join(collections)})")
    if detectors:
        records = [r for r in records if r.detector in set(detectors)]
    cands = build_candidates(records, ra, dec, field_deg)
    log(f"Con el campo completo dentro del detector: {len(cands)}")
    tables = estimate_wavelengths(cands)
    pairs = rank_pairs(cands, require_same_collection)
    log(f"Parejas preseleccionadas (mismo detector, Δt ≥ {config.MIN_TIME_SEPARATION_DAYS} d, "
        f"|Δλ| estimado ≤ {config.SPECTRAL_PRESELECT_BW} BW): {len(pairs)}")

    evaluated, failures = [], []
    top = pairs[:max_download_pairs]
    archive.fetch_many([archive.cutout_url(c.rec.access_url, ra, dec, field_deg)
                        for p in top for c in (p["a"], p["b"])])  # parallel prefetch into the cache
    for p in top:
        try:
            pa = archive.fetch_cutout(p["a"].rec, ra, dec, field_deg)
            pb = archive.fetch_cutout(p["b"].rec, ra, dec, field_deg)
            ia, ib = fitsdata.load(pa), fitsdata.load(pb)
        except Exception as err:  # keep searching; report the failure
            failures.append({"a": p["a"].rec.file_name, "b": p["b"].rec.file_name, "error": str(err)[:300]})
            log(f"  fallo al recuperar {p['a'].rec.obs_id} ↔ {p['b'].rec.obs_id}: {str(err)[:120]}")
            continue
        ev = evaluate_pair(ia, ib, ra, dec, field_deg,
                           collections=(p["a"].rec.collection, p["b"].rec.collection))
        evaluated.append({"pair": p, "paths": (pa, pb), "images": (ia, ib), "evaluation": ev})
        log(f"  {p['a'].rec.obs_id} D{p['a'].rec.detector} ↔ {p['b'].rec.obs_id}: "
            f"admisible={ev.admissible} cobertura={ev.metrics['coverage_common_valid']:.1%} "
            f"|Δλ|={ev.metrics['dlambda_target_bw']:.2f} BW")

    ok = [e for e in evaluated if e["evaluation"].admissible]
    ok.sort(key=lambda e: (len(e["evaluation"].warnings), -e["evaluation"].metrics["coverage_common_valid"]))
    best = ok[0] if ok else None
    report = {
        "target": {"ra_deg": ra, "dec_deg": dec, "field_deg": field_deg},
        "collections": list(collections),
        "n_records": len(records),
        "n_candidates": len(cands),
        "n_preselected_pairs": len(pairs),
        "wave_tables": {f"D{k[0]}|{k[1]}": v for k, v in tables.items()},
        "evaluated": [summarize(e) for e in evaluated],
        "retrieval_failures": failures,
        "observations": [
            {"obs_id": c.rec.obs_id, "collection": c.rec.collection, "detector": c.rec.detector,
             "mjd_mid": c.rec.mjd_mid, "em_min_um": c.rec.em_min_um, "em_max_um": c.rec.em_max_um,
             "exptime_s": c.rec.exptime_s, "file_name": c.rec.file_name,
             "lambda_est_um": c.lam_um, "bandwidth_est_um": c.bw_um, "field_margin_px": c.margin_px}
            for c in cands
        ],
        "selected": summarize(best) if best else None,
        "generated_utc": Time.now().isot[:19],
    }
    return best, report


def summarize(e) -> dict:
    p, ev = e["pair"], e["evaluation"]
    out = {"admissible": ev.admissible, "criteria": ev.criteria, "metrics": ev.metrics, "notes": ev.notes,
           "preselection": {"dt_days": p["dt_days"], "dlambda_bw_est": p["dlambda_bw_est"],
                            "dlambda_field_max_bw_est": p["dlambda_field_max_bw_est"],
                            "min_margin_px": p["min_margin_px"]}}
    for tag, cand, path, img in zip(("a", "b"), (p["a"], p["b"]), e["paths"], e["images"]):
        out[tag] = {
            **cand.rec.to_dict(),
            "cutout_url": archive.cutout_url(cand.rec.access_url, *ev.metrics["target_radec_deg"],
                                             ev.metrics["field_deg"]),
            "local_file": path.name,
            "sha256": archive.sha256(path),
            "lambda_est_um": cand.lam_um,
            "header": {k: _jsonable(v) for k, v in img.meta.items() if k != "CALIB_HISTORY"},
        }
    return out


def _jsonable(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def save_report(report: dict, name: str):
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.RESULTS_DIR / f"{name}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=_jsonable), encoding="utf-8")
    return path
