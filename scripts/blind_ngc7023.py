"""Validación espectral ciega en NGC 7023 (SKYCLUES_SPECTRAL_BLIND_VALIDATION_01).

Uso:
    python scripts/blind_ngc7023.py select    # imagen de referencia (detector 1) y posiciones A/B por regla fija
    python scripts/blind_ngc7023.py extract   # espectros A/B, detector congelado, resultados y figura

La regla de selección está en results/blind_ngc7023/PROTOCOLO.md y se fijó antes de ver ningún espectro.
Este script no ajusta nada del método: solo llama al código de la aplicación.
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyclues import spectral_cube as sc, spectral_features as sf  # noqa: E402
from skyclues.geometry import separation_deg  # noqa: E402

OUT = ROOT / "results" / "blind_ngc7023"
NOMINAL = (315.4038, 68.1633)
FIELD_DEG = 0.1                       # 6 arcmin
STAR_SEARCH_ARCSEC = 30.0
A_RANGE_ARCSEC = (60.0, 150.0)
MIN_AB_PX = 9.0                       # r_ap + r_out
FROZEN = ["skyclues/spectral_features.py", "skyclues/spectral_cube.py", "skyclues/geometry.py",
          "scripts/blind_ngc7023.py"]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def position_angle_deg(ra0, dec0, ra, dec):
    """East of north, degrees."""
    r0, d0, r, d = map(np.radians, (ra0, dec0, ra, dec))
    y = np.sin(r - r0) * np.cos(d)
    x = np.cos(d0) * np.sin(d) - np.sin(d0) * np.cos(d) * np.cos(r - r0)
    return np.degrees(np.arctan2(y, x)) % 360


# ----------------------------------------------------------------------------- stage 1: selection
def reference_pixels():
    tile = sc.tile_for(*NOMINAL)
    planes = [c.plane for c in tile.channels if c.detector == 1 and not c.blank]
    stack, ra, dec, chans = [], None, None, []
    for p in planes:
        m = sc.channel_map(*NOMINAL, FIELD_DEG, p)
        vals, rr, dd = [], [], []
        for patch in m.patches:
            f = m.in_field(patch)
            r, d = patch.centres_world()
            v = np.where(patch.valid, patch.image, np.nan)
            vals.append(v[f]); rr.append(r[f]); dd.append(d[f])
        stack.append(np.concatenate(vals))
        if ra is None:
            ra, dec = np.concatenate(rr), np.concatenate(dd)
        chans.append({"canal": m.channel.number, "lambda_um": m.channel.wavelength_um})
    ref = np.nanmedian(np.vstack(stack), axis=0)
    return ra, dec, ref, chans, tile.pixel_scale_arcsec


def select():
    OUT.mkdir(parents=True, exist_ok=True)
    ra, dec, ref, chans, pix = reference_pixels()
    ok = np.isfinite(ref)
    d_nom = separation_deg(*NOMINAL, ra, dec) * 3600
    near = ok & (d_nom < STAR_SEARCH_ARCSEC)
    i_star = int(np.flatnonzero(near)[np.argmax(ref[near])])
    star = (float(ra[i_star]), float(dec[i_star]))
    rho = separation_deg(*star, ra, dec) * 3600
    ring = np.floor(rho / pix).astype(int)
    med = {k: float(np.nanmedian(ref[ok & (ring == k)])) for k in np.unique(ring[ok])}
    rel = np.array([ref[i] / med[ring[i]] - 1 if ok[i] and med[ring[i]] > 0 else np.nan for i in range(ra.size)])
    # mean relative excess over a disc of the aperture radius (2 px)
    excess = np.full(ra.size, np.nan)
    for i in np.flatnonzero(ok):
        disc = (separation_deg(ra[i], dec[i], ra, dec) * 3600 < 2.0 * pix) & np.isfinite(rel)
        excess[i] = float(np.mean(rel[disc]))
    cand_a = ok & (rho >= A_RANGE_ARCSEC[0]) & (rho <= A_RANGE_ARCSEC[1]) & np.isfinite(excess)
    i_a = int(np.flatnonzero(cand_a)[np.argmax(excess[cand_a])])
    sep_a = separation_deg(ra[i_a], dec[i_a], ra, dec) * 3600
    cand_b = (ok & np.isfinite(excess) & (np.abs(rho - rho[i_a]) <= pix) & (sep_a >= MIN_AB_PX * pix))
    i_b = int(np.flatnonzero(cand_b)[np.argmin(excess[cand_b])])
    pos = lambda i: {"ra": float(ra[i]), "dec": float(dec[i]), "dist_estrella_arcsec": float(rho[i]),
                     "pa_estrella_deg": float(position_angle_deg(*star, ra[i], dec[i])),
                     "brillo_ref_mjysr": float(ref[i]), "exceso_relativo": float(excess[i])}
    sel = {"actividad": "SKYCLUES_SPECTRAL_BLIND_VALIDATION_01", "fecha_utc": now(),
           "nominal": {"ra": NOMINAL[0], "dec": NOMINAL[1]}, "campo_deg": FIELD_DEG,
           "imagen_referencia": {"definicion": "mediana de los canales del detector 1", "canales": chans},
           "escala_px_arcsec": pix, "estrella": {"ra": star[0], "dec": star[1],
                                                 "dist_nominal_arcsec": float(d_nom[i_star]),
                                                 "brillo_ref_mjysr": float(ref[i_star])},
           "A": pos(i_a), "B": pos(i_b),
           "separacion_AB_arcsec": float(sep_a[i_b]), "n_candidatos_A": int(cand_a.sum()),
           "n_candidatos_B": int(cand_b.sum()),
           "huellas_sha256": {f: sha256(ROOT / f) for f in FROZEN}}
    (OUT / "seleccion.json").write_text(json.dumps(sel, indent=2, ensure_ascii=False), encoding="utf-8")
    np.savez_compressed(OUT / "referencia.npz", ra=ra, dec=dec, ref=ref, excess=excess)
    _plot_reference(ra, dec, ref, excess, star, sel, pix)
    print(json.dumps({k: sel[k] for k in ("estrella", "A", "B", "separacion_AB_arcsec")}, indent=2))


def _plot_reference(ra, dec, ref, excess, star, sel, pix):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    east = (ra - star[0]) * math.cos(math.radians(star[1])) * 3600
    north = (dec - star[1]) * 3600
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, val, title, kw in (
            (axes[0], np.log10(np.clip(ref, np.nanpercentile(ref, 2), None)), "Referencia: mediana del detector 1 "
             "(0,75–1,09 µm), log", {"cmap": "gray"}),
            (axes[1], excess, "Exceso relativo sobre la mediana azimutal (disco de 2 px)",
             {"cmap": "RdBu_r", "vmin": -0.6, "vmax": 0.6})):
        sc_ = ax.scatter(east, north, c=val, s=22, marker="s", **kw)
        fig.colorbar(sc_, ax=ax, shrink=0.8)
        for key, col in (("A", "#1f6fd1"), ("B", "#eb6834")):
            p = sel[key]
            x = (p["ra"] - star[0]) * math.cos(math.radians(star[1])) * 3600
            y = (p["dec"] - star[1]) * 3600
            for r, ls in ((2, "-"), (4, "--"), (7, "--")):
                ax.add_patch(plt.Circle((x, y), r * pix, fill=False, color=col, ls=ls, lw=1.2))
            ax.annotate(key, (x, y), color=col, fontsize=13, weight="bold", ha="center", va="center")
        ax.plot(0, 0, marker="*", color="#c4411c", ms=12)
        for r in (60, 150):
            ax.add_patch(plt.Circle((0, 0), r, fill=False, color="#888", ls=":", lw=0.8))
        ax.set_xlim(190, -190); ax.set_ylim(-190, 190); ax.set_aspect("equal")
        ax.set_xlabel("Este (″) respecto de la estrella"); ax.set_ylabel("Norte (″)"); ax.set_title(title, fontsize=9)
    fig.suptitle("NGC 7023 · SPHEREx DR1 · selección de A/B por regla morfológica (antes de ver espectros)", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "seleccion.png", dpi=130)


# ----------------------------------------------------------------------------- stage 2: spectra
def extract():
    sel = json.loads((OUT / "seleccion.json").read_text(encoding="utf-8"))
    for f, h in sel["huellas_sha256"].items():
        if f != "scripts/blind_ngc7023.py" and sha256(ROOT / f) != h:
            raise SystemExit(f"{f} ha cambiado desde la selección: el método no está congelado")
    sc.io_stats(reset=True)
    t0 = time.perf_counter()
    spec = {k: sc.extract_spectrum(sel[k]["ra"], sel[k]["dec"]) for k in "AB"}
    t_extract = time.perf_counter() - t0
    io = sc.io_stats()
    series = {k: sf.series_from_spectrum(spec[k], "flux", k) for k in "AB"}
    an = {k: sf.analyse(series[k]) for k in "AB"}
    cmp = sf.compare(series["A"], series["B"])
    cross = []
    for k, other in (("A", "B"), ("B", "A")):
        for f in an[k].features:
            g = sf.measure_interval(series[other], f.trial_lo, f.trial_hi, an[other].features, an[other].scatter)
            cross.append({"encontrada_en": k, "medida_en": other, "canales": [f.trial_lo, f.trial_hi],
                          "clase_origen": f.klass, "clase_en_otro": g.klass, "contraste_otro": g.contrast,
                          "relativo_otro": g.relative, "cociente_otro": g.ratio, "razones_otro": g.reasons})
    not_eval = {}
    for k in "AB":
        s = series[k]
        ne = []
        for c in s.canal:
            g = sf.inspect_channel(s, int(c), an[k].features, an[k].scatter)
            if g.klass == sf.NOT_EVALUABLE:
                ne.append(int(c))
        not_eval[k] = ne
    res = {"actividad": sel["actividad"], "fecha_utc": now(), "metodo": sf.method_summary(),
           "huellas_sha256": {f: sha256(ROOT / f) for f in FROZEN}, "seleccion": sel,
           "apertura_px": {"A": asdict(spec["A"].aperture), "B": asdict(spec["B"].aperture)}, "escala_px_arcsec": spec["A"].pixel_scale_arcsec,
           "n_apertura_px": {k: spec[k].n_aperture_px for k in "AB"},
           "n_anillo_px": {k: spec[k].n_annulus_px for k in "AB"},
           "avisos_extraccion": {k: spec[k].warnings for k in "AB"},
           "comparacion": {"comparable": cmp.comparable, "problemas": cmp.issues, "notas": cmp.notes,
                           "separacion_arcsec": cmp.separation_arcsec, "resumen": cmp.summary},
           "caracteristicas": {k: [f.to_dict() for f in an[k].features] for k in "AB"},
           "dispersion_detector": {k: {str(d): v for d, v in an[k].scatter.items()} for k in "AB"},
           "canales_no_evaluables": not_eval, "medidas_cruzadas": cross,
           "espectros": {k: spec[k].rows for k in "AB"},
           "rendimiento": {"extraccion_s": round(t_extract, 2), **io}}
    (OUT / "resultados.json").write_text(json.dumps(res, indent=2, ensure_ascii=False, default=_json),
                                         encoding="utf-8")
    _plot_spectra(series, an, cmp)
    _table(an, series)


def _json(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _plot_spectra(series, an, cmp):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax, bx) = plt.subplots(2, 1, figsize=(11, 7.5), sharex=True, gridspec_kw={"height_ratios": [3, 1.4]})
    for k, col, mk in (("A", "#1f6fd1", "D"), ("B", "#eb6834", "s")):
        s = series[k]
        ax.errorbar(s.lam, s.value, xerr=[s.lam - s.lam_min, s.lam_max - s.lam], fmt=mk, ms=3.5, color=col,
                    elinewidth=0.6, label=f"{k}")
        for f in an[k].features:
            filled = f.klass == sf.QUANTIFIABLE
            y = f.value * (1.06 if f.kind == "pico" else 0.94)
            ax.plot(f.lam, y, marker="v" if f.kind == "pico" else "^", ms=8, color=col,
                    mfc=col if filled else "white")
    for c in (51, 52):
        lam = series["A"].lam[series["A"].index(c)]
        ax.axvline(lam, color="#e48ab5", lw=0.8, ls=":")
    ax.set_ylabel("Flujo en apertura (mJy)"); ax.set_yscale("log"); ax.legend()
    ax.set_title("NGC 7023 · espectros exploratorios A/B (SPHEREx DR1, misma apertura) · ▼ pico ▲ valle; "
                 "relleno = cuantificable, hueco = visible", fontsize=9)
    rows = [r for r in cmp.rows if r["relacion"] is not None]
    bx.plot([r["lambda_um"] for r in rows], [r["relacion"] for r in rows], "o", ms=3, color="#444")
    bx.set_ylabel("A / B"); bx.set_xlabel("Longitud de onda (µm)")
    fig.tight_layout()
    fig.savefig(OUT / "espectros.png", dpi=130)


def _table(an, series):
    lines = ["| Espectro | Tipo | Clase | λ (µm) | Canales a media altura | Contraste | Relativo | Contraste/dispersión | Detectores |",
             "|---|---|---|---|---|---|---|---|---|"]
    for k in "AB":
        for f in sorted(an[k].features, key=lambda f: f.lam):
            lines.append(f"| {k} | {f.kind} · {f.width} | {f.label} | {f.lam:.3f} | {f.canal_lo}–{f.canal_hi} | "
                         f"{f.contrast:+.4g} {f.unit} | {'—' if f.relative is None else f'{f.relative:+.1%}'} | "
                         f"{abs(f.ratio):.1f} | {', '.join(f'D{d}' for d in f.detectors)} |")
    (OUT / "caracteristicas.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    {"select": select, "extract": extract}[sys.argv[1]]()
