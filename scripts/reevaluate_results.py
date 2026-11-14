"""Re-evaluate the stored results with the corrected criteria (audit SC-01/02/06/11).

For every results/sequence_*.json and results/pair_*.json:

* attaches the catalogue astrometry of the target (SIMBAD, see
  skyclues.targets) so that the target position is propagated to each date;
* records how the field centre was chosen (the stored cutouts are kept: they
  are the analysed data, and their centre is NOT moved);
* re-evaluates the selected frames from the same FITS (SHA-256 checked) with
  the current code and stores the result in ``selected``;
* keeps the previous evaluation under ``previous_evaluation`` and lists every
  change under ``reevaluation`` (nothing is deleted).

Usage:  python scripts/reevaluate_results.py           (report only)
        python scripts/reevaluate_results.py --write   (update the JSON files)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from astropy.time import Time  # noqa: E402

from skyclues import archive, config, fitsdata  # noqa: E402
from skyclues.compare import evaluate_pair  # noqa: E402
from skyclues.geometry import separation_deg  # noqa: E402
from skyclues.sequence import load_sequence, save_report  # noqa: E402
from skyclues.targets import CHALLENGE_WISE0855, M101, WISE0855  # noqa: E402


def identify(t):
    ra, dec = t["ra_deg"], t["dec_deg"]
    if float(separation_deg(ra, dec, CHALLENGE_WISE0855["ra_deg"], CHALLENGE_WISE0855["dec_deg"])) * 3600 < 1:
        return WISE0855, {"rule": "coordenadas del enunciado NASA, que corresponden a la época ≈2010.4 (no "
                                  "J2000.0); NO propagadas: en 2026 el objetivo está a ≈2′ del centro del campo",
                          "epoch_jyear": CHALLENGE_WISE0855["epoch_jyear_estimated"], "propagated": False}
    if float(separation_deg(ra, dec, M101.ra_deg, M101.dec_deg)) * 3600 < 1:
        return M101, {"rule": "posición de catálogo (sin movimiento propio)", "propagated": False}
    return None, {"rule": "coordenadas introducidas (sin astrometría)", "propagated": False}


def statuses(criteria):
    return {c["id"]: c["status"] for c in criteria}


def diff(old, new):
    out = []
    so, sn = statuses(old["criteria"]), statuses(new["criteria"])
    for k in sn:
        if so.get(k) != sn[k]:
            out.append(f"{k}: {so.get(k)} → {sn[k]}")
    if old.get("admissible") != new.get("admissible"):
        out.append(f"admisible: {old.get('admissible')} → {new.get('admissible')}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    paths = sorted(config.RESULTS_DIR.glob("sequence_*.json")) + sorted(config.RESULTS_DIR.glob("pair_*.json"))
    for p in paths:
        rep = json.loads(p.read_text(encoding="utf-8"))
        if not rep.get("selected") or "target" not in rep:
            continue
        t = rep["target"]
        astro, centre = identify(t)
        if astro is not None:
            t["astrometry"] = astro.to_dict()
            t["astrometry_warnings"] = astro.warnings()
        t.setdefault("centre", centre)
        sel = rep["selected"]
        changes = []
        if rep.get("kind") == "sequence":
            seq = load_sequence(rep)
            new = seq.summary()
            old = {"criteria": sel["criteria"], "admissible": sel["admissible"],
                   "lambda_target_um": sel["metrics"]["lambda_target_um"]}
            changes = diff(old, new)
            lam_old, lam_new = old["lambda_target_um"], new["metrics"]["lambda_target_um"]
            if any(abs(a - b) > 1e-6 for a, b in zip(lam_old, lam_new)):
                changes.append("λ en el objetivo (µm): " + ", ".join(f"{a:.4f}→{b:.4f}" for a, b in zip(lam_old, lam_new)))
            if "target_offset_from_centre_arcsec" in new["metrics"]:
                off = new["metrics"]["target_offset_from_centre_arcsec"]
                changes.append(f"objetivo calculado a {min(off):.0f}–{max(off):.0f}″ del centro del campo")
            # stored option rows: S4 depends only on the stored spread, so its corrected status is exact
            for o in rep.get("options", []):
                v = o.get("lambda_spread_common_max_bw")
                if v is not None and v > config.SPECTRAL_WARN_BW and o["status"].get("S4") != "fail":
                    o.setdefault("status_after_audit", {})["S4"] = "fail"
                    changes.append(f"opción {o['obs_ids']}: S4 → fail ({v:.2f} BW)")
            rep["previous_evaluation"] = old
            rep["selected"] = new
        else:
            a = fitsdata.load(archive.fetch(sel["a"]["cutout_url"]))
            b = fitsdata.load(archive.fetch(sel["b"]["cutout_url"]))
            ev = evaluate_pair(a, b, t["ra_deg"], t["dec_deg"], t["field_deg"],
                               collections=(sel["a"]["collection"], sel["b"]["collection"]), astrometry=astro)
            old = {"criteria": sel["criteria"], "admissible": sel["admissible"],
                   "lambda_target_um": sel["metrics"]["lambda_target_um"]}
            changes = diff(old, {"criteria": ev.criteria, "admissible": ev.admissible})
            lam_new = ev.metrics["lambda_target_um"]
            if any(abs(x - y) > 1e-6 for x, y in zip(old["lambda_target_um"], lam_new)):
                changes.append("λ en el objetivo (µm): " + ", ".join(
                    f"{x:.4f}→{y:.4f}" for x, y in zip(old["lambda_target_um"], lam_new)))
            rep["previous_evaluation"] = old
            sel.update({"admissible": ev.admissible, "criteria": ev.criteria, "metrics": ev.metrics,
                        "notes": ev.notes})
        rep["reevaluation"] = {
            "date_utc": Time.now().isot[:19],
            "reason": "auditoría independiente: astrometría por época (SC-01), rechazo espectral (SC-02), "
                      "FLAGS oficiales y bits sin definir (SC-06), FINAST (SC-11)",
            "fits": "los mismos recortes (SHA-256 comprobado); centro del campo sin cambios",
            "changes": changes or ["ningún cambio de estado"],
        }
        print(f"{p.name}: " + ("; ".join(changes) if changes else "sin cambios de estado"))
        if args.write:
            save_report(rep, p.stem)


if __name__ == "__main__":
    main()
