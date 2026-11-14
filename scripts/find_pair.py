"""Reproducible search for a comparable SPHEREx pair.

Usage:
    python scripts/find_pair.py --ra 210.802429 --dec 54.34875 --field 0.1 --name pair_m101

Writes results/<name>.json with every criterion, metric, file name, cutout URL
and SHA-256 of the cached FITS so the selection can be re-checked.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skyclues import config  # noqa: E402
from skyclues.pairing import find_pair, save_report  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ra", type=float, required=True)
    ap.add_argument("--dec", type=float, required=True)
    ap.add_argument("--field", type=float, default=config.DEFAULT_FIELD_DEG)
    ap.add_argument("--name", required=True)
    ap.add_argument("--detectors", type=int, nargs="*")
    ap.add_argument("--max-pairs", type=int, default=config.MAX_PAIRS_TO_DOWNLOAD)
    ap.add_argument("--same-collection", action="store_true")
    args = ap.parse_args()

    best, report = find_pair(args.ra, args.dec, args.field, detectors=args.detectors,
                             max_download_pairs=args.max_pairs,
                             require_same_collection=args.same_collection)
    path = save_report(report, args.name)
    print(f"Informe: {path}")
    if best is None:
        print("Ninguna pareja admisible entre las evaluadas.")
        return 1
    sel = report["selected"]
    print("PAREJA SELECCIONADA")
    for tag in ("a", "b"):
        o = sel[tag]
        print(f"  {tag.upper()}: {o['obs_id']} D{o['detector']} {o['collection']} "
              f"{o['header']['DATE-AVG']} λ={sel['metrics']['lambda_target_um'][0 if tag == 'a' else 1]:.4f} µm")
    for c in sel["criteria"]:
        print(f"  [{c['status'].upper():4}] {c['id']} {c['criterion']}: {c['value']}")
    for n in sel["notes"]:
        print(f"  NOTA: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
