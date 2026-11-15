"""Preselección instrumental V03 (protocolo: results/blind_v03/PROTOCOLO_PRESELECCION.md).

Solo extract_spectrum con parámetros por defecto. No ejecuta el analizador de picos y valles.
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyclues import spectral_cube as sc  # noqa: E402

OUT = ROOT / "results" / "blind_v03"
# id, nominal position (ICRS), physical group (G1 SF/PDR, G2 nebula, G3 evolved/young star, G4 galaxy), label
CANDIDATES = [
    ("C01", "05h35m20.6s", "-05d25m14s", "G1", "Orion Bar"),
    ("C02", "05h41m38.4s", "-02d15m33s", "G2", "NGC 2023"),
    ("C03", "03h29m11s", "+31d18m00s", "G1", "NGC 1333"),
    ("C04", "00h59m01s", "+60d53m00s", "G1", "IC 63"),
    ("C05", "15h34m57.1s", "+23d30m11s", "G4", "Arp 220"),
    ("C06", "02h42m40.7s", "-00d00m48s", "G4", "NGC 1068"),
    ("C07", "06h19m58.2s", "-10d38m15s", "G3", "Red Rectangle"),
    ("C08", "21h02m18.8s", "+36d41m38s", "G3", "CRL 2688"),
    ("C09", "17h58m33.4s", "+66d38m00s", "G2", "NGC 6543"),
    ("C10", "23h23m24s", "+58d48m54s", "G2", "Cas A"),
    ("C11", "12h56m14.2s", "+56d52m25s", "G4", "Mrk 231"),
    ("C12", "11h01m51.9s", "-34d42m17s", "G3", "TW Hya"),
    ("C13", "22h29m38.5s", "-20d50m14s", "G2", "NGC 7293 (Helix)"),
    ("C14", "13h29m52.7s", "+47d11m43s", "G4", "M51 nucleus"),
]
MIN_USABLE, MIN_RUN, MIN_DET, MIN_PER_DET, MAX_BG = 60, 15, 4, 8, 0.2


def evaluate(cid, ra_s, dec_s, group, label):
    c = SkyCoord(ra_s, dec_s, frame="icrs")
    ra, dec = float(c.ra.deg), float(c.dec.deg)
    rec = {"id": cid, "grupo": group, "objeto": label, "ra_deg": ra, "dec_deg": dec}
    try:
        spec = sc.extract_spectrum(ra, dec)
    except Exception as err:  # noqa: BLE001
        rec.update(error=f"{type(err).__name__}: {err}", aceptado=False, motivos=["no se pudo extraer"])
        return rec
    rows = spec.rows
    omega = spec.pixel_solid_angle_sr
    usable, bg_ratio, neg = [], [], 0
    for r in rows:
        if r["status"] != "ok":
            continue
        if r["flujo_mjy"] <= 0:
            neg += 1
        if r["precaucion"] or r["flujo_mjy"] <= 0:
            continue
        usable.append(r["canal"])
        surf = r["flujo_mjy"] / (spec.n_aperture_px * omega * 1e9)          # MJy/sr
        bg_ratio.append(r["fondo_sigma_mjysr"] / surf)
    runs, cur = [], []
    for ch in sorted(usable):
        if cur and ch == cur[-1] + 1:
            cur.append(ch)
        else:
            if cur:
                runs.append(cur)
            cur = [ch]
    if cur:
        runs.append(cur)
    det = {}
    for r in rows:
        if r["canal"] in usable:
            det[r["detector"]] = det.get(r["detector"], 0) + 1
    n_det = sum(v >= MIN_PER_DET for v in det.values())
    bg_med = float(np.median(bg_ratio)) if bg_ratio else float("nan")
    longest = max((len(x) for x in runs), default=0)
    reasons = []
    if len(usable) < MIN_USABLE:
        reasons.append(f"A: {len(usable)} canales utilizables < {MIN_USABLE}")
    if longest < MIN_RUN:
        reasons.append(f"B: tramo continuo más largo {longest} < {MIN_RUN}")
    if n_det < MIN_DET:
        reasons.append(f"C: {n_det} detectores con ≥ {MIN_PER_DET} canales < {MIN_DET}")
    if not (bg_med <= MAX_BG):
        reasons.append(f"D: fondo/señal mediana {bg_med:.3g} > {MAX_BG}")
    notmeasured = {}
    for r in rows:
        if r["status"] != "ok":
            notmeasured[r["estado"]] = notmeasured.get(r["estado"], 0) + 1
    rec.update(canales_medidos=spec.n_measured, canales_utilizables=len(usable), canales_precaucion=
               sum(bool(r["precaucion"]) for r in rows if r["status"] == "ok"), flujo_no_positivo=neg,
               no_medidos=notmeasured, tramos=len(runs), tramo_mas_largo=longest, detectores_con_datos=det,
               detectores_cumplen=n_det, fondo_sobre_senal_mediana=bg_med, n_anillo_px=spec.n_annulus_px,
               rango_flujo_mjy=[min(r["flujo_mjy"] for r in rows if r["status"] == "ok"),
                                max(r["flujo_mjy"] for r in rows if r["status"] == "ok")] if spec.n_measured else None,
               aceptado=not reasons, motivos=reasons, avisos=spec.warnings, aperture=asdict(spec.aperture),
               canales_utilizables_lista=sorted(usable))
    return rec


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sc.io_stats(reset=True)
    res = []
    for cand in CANDIDATES:
        rec = evaluate(*cand)
        res.append(rec)
        print(rec["id"], rec["objeto"], "| medidos", rec.get("canales_medidos"), "| utilizables",
              rec.get("canales_utilizables"), "| tramo", rec.get("tramo_mas_largo"), "| det", rec.get("detectores_cumplen"),
              "| bg", None if rec.get("fondo_sobre_senal_mediana") is None else round(rec["fondo_sobre_senal_mediana"], 3),
              "|", "ACEPTADO" if rec["aceptado"] else "rechazado: " + "; ".join(rec["motivos"]), flush=True)
    acc = sorted((r for r in res if r["aceptado"]), key=lambda r: -r["canales_utilizables"])
    chosen = []
    for g in ("G1", "G2", "G3", "G4"):
        best = next((r for r in acc if r["grupo"] == g), None)
        if best:
            chosen.append(best)
    for r in acc:
        if len(chosen) >= 5:
            break
        if r not in chosen:
            chosen.append(r)
    chosen = sorted(chosen, key=lambda r: r["id"])
    out = {"criterios": {"A_min_utilizables": MIN_USABLE, "B_min_tramo": MIN_RUN, "C_min_detectores": MIN_DET,
                         "C_min_canales_por_detector": MIN_PER_DET, "D_max_fondo_sobre_senal": MAX_BG},
           "candidatos": res, "seleccionados": [r["id"] for r in chosen], "io": sc.io_stats()}
    (OUT / "preseleccion.json").write_text(json.dumps(out, indent=1, ensure_ascii=False, default=float), encoding="utf-8")
    print("\nSELECCIONADOS:", [(r["id"], r["objeto"], r["grupo"]) for r in chosen])


if __name__ == "__main__":
    main()
