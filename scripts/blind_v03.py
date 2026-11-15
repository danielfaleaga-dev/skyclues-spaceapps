"""Validación espectral ciega V02 (SKYCLUES_SPECTRAL_BLIND_VALIDATION_02).

Uso:  python scripts/blind_v03.py C05|C12|C14

Solo datos SPHEREx DR1 (cubo de IRSA). Sin catálogos ni servicios de nombres. El método no se ajusta:
el script llama al código de la aplicación con sus parámetros por defecto (results/blind_v03/PROTOCOLO_PRESELECCION.md y SELECCION).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyclues import spectral_cube as sc, spectral_features as sf  # noqa: E402
from skyclues.geometry import separation_deg  # noqa: E402

OUT = ROOT / "results" / "blind_v03"
TARGETS = {  # selected in results/blind_v03/PRESELECCION.md (nominal positions, ICRS), FOV in arcmin
    "C05": ("15h34m57.1s", "+23d30m11s", 4.0),
    "C12": ("11h01m51.9s", "-34d42m17s", 4.0),
    "C14": ("13h29m52.7s", "+47d11m43s", 4.0),
}
FROZEN = ["skyclues/spectral_features.py", "skyclues/spectral_cube.py", "skyclues/geometry.py"]
EXPECTED = {  # sha256 at protocol registration (commit 490c135)
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _json(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def check_frozen() -> dict:
    hashes = {f: sha256(ROOT / f) for f in FROZEN}
    ref = ROOT / "results" / "blind_v02" / "huellas_metodo.json"
    if ref.exists():
        old = json.loads(ref.read_text(encoding="utf-8"))
        if old != hashes:
            raise SystemExit("El código del método ha cambiado desde V02: se detiene la prueba.")
    else:
        raise SystemExit("faltan las huellas del método de V02")
    (OUT / "huellas_metodo.json").write_text(json.dumps(hashes, indent=2), encoding="utf-8")
    return hashes


# ----------------------------------------------------------------------------- coverage and images
def coverage(ra, dec, fov_deg):
    tile = sc.tile_for(ra, dec)
    per_channel, tiles = [], set()
    d1, d6 = [], []
    coords = None
    for c in tile.channels:
        m = sc.channel_map(ra, dec, fov_deg, c.plane)
        s = m.summary()
        tiles.update(s["tiles"])
        per_channel.append({"canal": c.number, "lambda_um": c.wavelength_um, "detector": c.detector,
                            "sin_datos_dr1": c.blank, "fraccion_valida": s["valid_fraction"],
                            "nhits_mediano": s["nhits_median"], "nhits_min": s["nhits_min"],
                            "pixeles_flag": s["flag_pixels"], "p1": s["value_p1"], "p99": s["value_p99"]})
        if c.detector in (1, 6) and not c.blank:
            vals, rr, dd = [], [], []
            for p in m.patches:
                f = m.in_field(p)
                r, d = p.centres_world()
                vals.append(np.where(p.valid, p.image, np.nan)[f]); rr.append(r[f]); dd.append(d[f])
            (d1 if c.detector == 1 else d6).append(np.concatenate(vals))
            if coords is None:
                coords = (np.concatenate(rr), np.concatenate(dd))
    img = {"d1": np.nanmedian(np.vstack(d1), axis=0), "d6": np.nanmedian(np.vstack(d6), axis=0)}
    prov = [{"ipix": t, "orden": 5, "url": sc.tile_url(t)} for t in sorted(tiles)]
    return per_channel, prov, coords, img


def plot_field(key, ra, dec, fov_deg, coords, img, pix, ap):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    east = (coords[0] - ra) * math.cos(math.radians(dec)) * 3600
    north = (coords[1] - dec) * 3600
    half = fov_deg * 3600 / 2
    size = max(8.0, 70.0 * (240.0 / (fov_deg * 3600)) ** 2)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, k, title in ((axes[0], "d1", "Mediana detector 1 (0,75–1,09 µm), asinh"),
                         (axes[1], "d6", "Mediana detector 6 (4,4–5,0 µm), asinh")):
        v = img[k]
        lo, hi = np.nanpercentile(v, 1), np.nanpercentile(v, 99.5)
        s_ = ax.scatter(east, north, c=np.arcsinh((v - lo) / max(hi - lo, 1e-9) * 10), s=size, marker="s",
                        cmap="gray")
        fig.colorbar(s_, ax=ax, shrink=0.8)
        for r, ls in ((ap.r_ap, "-"), (ap.r_in, "--"), (ap.r_out, "--")):
            ax.add_patch(plt.Circle((0, 0), r * pix, fill=False, color="#c4411c", ls=ls, lw=1.2))
        ax.set_xlim(half, -half); ax.set_ylim(-half, half); ax.set_aspect("equal")
        ax.set_xlabel("Este (″)"); ax.set_ylabel("Norte (″)"); ax.set_title(title, fontsize=9)
    fig.suptitle(f"{key} · SPHEREx DR1 · campo {fov_deg * 60:g}′ · apertura (continua) y anillo de fondo", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / key / "campo.png", dpi=130)
    plt.close(fig)


def plot_spectrum(key, s, an, anomalies):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 5.5))
    ok = np.isfinite(s.value)
    ax.errorbar(s.lam[ok], s.value[ok], xerr=[(s.lam - s.lam_min)[ok], (s.lam_max - s.lam)[ok]], fmt="D", ms=3.5,
                color="#1f6fd1", elinewidth=0.6, label="flujo en apertura")
    caution = ok & s.caution
    ax.plot(s.lam[caution], s.value[caution], "o", mfc="none", mec="#c4411c", ms=9, label="OVERFLOW/OUTLIER")
    for j in np.flatnonzero(~ok):
        ax.axvline(s.lam[j], color="#e48ab5", lw=0.8, ls=":")
    span = np.nanmax(s.value) - np.nanmin(s.value)
    for f in an.features:
        filled = f.klass == sf.QUANTIFIABLE
        y = f.value + (0.06 if f.kind == "pico" else -0.06) * span
        ax.plot(f.lam, y, marker="v" if f.kind == "pico" else "^", ms=10, color="#c4411c",
                mfc="#c4411c" if filled else "white")
        ax.annotate(f"{f.lam:.3f}", (f.lam, y), textcoords="offset points", xytext=(0, 9), ha="center", fontsize=8)
    for a in anomalies:
        ax.plot(a["lambda_um"], a["valor"], "x", color="#666", ms=7)
    ax.set_xlabel("Longitud de onda (µm)"); ax.set_ylabel(f"Flujo en apertura ({s.unit})")
    ax.set_title(f"{key} · espectro exploratorio completo (SPHEREx DR1) · ▼ pico ▲ valle (relleno = cuantificable, "
                 "hueco = visible) · × anomalía < criterio · línea rosa: canal sin valor", fontsize=8.5)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / key / "espectro.png", dpi=130)
    plt.close(fig)


# ----------------------------------------------------------------------------- one target
def run(key: str) -> None:
    hashes = check_frozen()
    ra_s, dec_s, fov_arcmin = TARGETS[key]
    c = SkyCoord(ra_s, dec_s, frame="icrs")
    ra, dec, fov = float(c.ra.deg), float(c.dec.deg), fov_arcmin / 60
    (OUT / key).mkdir(parents=True, exist_ok=True)
    sc.io_stats(reset=True)
    t0 = time.perf_counter()
    per_channel, prov, coords, img = coverage(ra, dec, fov)
    t_cov = time.perf_counter() - t0
    t1 = time.perf_counter()
    spec = sc.extract_spectrum(ra, dec)
    t_ext = time.perf_counter() - t1
    s = sf.series_from_spectrum(spec, "flux", key)
    an = sf.analyse(s)
    not_eval, anomalies = [], []
    for ch in s.canal:
        g = sf.inspect_channel(s, int(ch), an.features, an.scatter)
        if g.klass == sf.NOT_EVALUABLE:
            not_eval.append({"canal": int(ch), "causas": g.reasons})
        elif g.klass == sf.NO_FEATURE and g.ratio is not None and abs(g.ratio) >= sf.Q_PROVISIONAL:
            anomalies.append({"canal": int(ch), "lambda_um": float(s.lam[s.index(int(ch))]),
                              "valor": float(s.value[s.index(int(ch))]), "tipo": g.kind,
                              "intervalo": [g.trial_lo, g.trial_hi], "contraste": g.contrast,
                              "relativo": g.relative, "contraste_dispersion": g.ratio, "motivo": g.reasons})
    rows = spec.rows
    caution = [r["canal"] for r in rows if r["precaucion"]]
    flags = {}
    for r in rows:
        for t in (r["flags_apertura"] or "").split("|"):
            if t:
                flags[t] = flags.get(t, 0) + 1
    res = {"objetivo": key, "fecha_utc": now(), "coordenadas_dadas": {"ra": ra_s, "dec": dec_s, "fov_arcmin": fov_arcmin},
           "ra_deg": ra, "dec_deg": dec, "metodo": sf.method_summary(), "huellas_sha256_metodo": hashes,
           "productos_spherex": prov, "apertura_px": asdict(spec.aperture), "escala_px_arcsec": spec.pixel_scale_arcsec,
           "n_apertura_px": spec.n_aperture_px, "n_anillo_px": spec.n_annulus_px, "avisos_extraccion": spec.warnings,
           "canales_con_valor": spec.n_measured, "canales_sin_valor": [r["canal"] for r in rows if r["status"] != "ok"],
           "estado_sin_valor": {r["canal"]: r["estado"] for r in rows if r["status"] != "ok"},
           "canales_precaucion_overflow_outlier": caution, "flags_apertura_por_canal": flags,
           "caracteristicas": [f.to_dict() for f in an.features],
           "dispersion_detector": {str(d): v for d, v in an.scatter.items()},
           "canales_no_evaluables": not_eval, "anomalias_bajo_criterio": anomalies,
           "cobertura_campo": per_channel, "espectro": rows,
           "rendimiento": {"cobertura_s": round(t_cov, 1), "extraccion_s": round(t_ext, 1), **sc.io_stats()}}
    path = OUT / key / "resultados.json"
    path.write_text(json.dumps(res, indent=2, ensure_ascii=False, default=_json), encoding="utf-8")
    plot_field(key, ra, dec, fov, coords, img, spec.pixel_scale_arcsec, spec.aperture)
    plot_spectrum(key, s, an, anomalies)
    print(json.dumps({"objetivo": key, "ra": ra, "dec": dec, "canales_con_valor": spec.n_measured,
                      "precaucion": caution, "flags": flags, "avisos": spec.warnings,
                      "caracteristicas": [(f.kind, f.width, f.label, round(f.lam, 3), f.canal_lo, f.canal_hi,
                                           round(f.contrast, 4), None if f.relative is None else round(f.relative, 3),
                                           round(f.ratio, 1), f.detectors) for f in an.features],
                      "anomalias": [(a["canal"], round(a["lambda_um"], 3), a["tipo"],
                                     round(a["contraste_dispersion"], 1)) for a in anomalies],
                      "no_evaluables": [x["canal"] for x in not_eval], "rendimiento": res["rendimiento"]},
                     ensure_ascii=False, default=_json))


if __name__ == "__main__":
    run(sys.argv[1])
