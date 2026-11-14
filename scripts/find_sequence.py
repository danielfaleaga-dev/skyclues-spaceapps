"""Reproducible search for a temporal sequence of comparable SPHEREx observations.

Usage:
    python scripts/find_sequence.py --ra 210.802429 --dec 54.34875 --field 0.1 --name sequence_m101

Writes results/<name>.json (frames, criteria S1-S9, options considered,
rejection reasons, SHA-256 of every cached FITS).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skyclues import config  # noqa: E402
from skyclues.sequence import find_sequence, save_report  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ra", type=float, required=True)
    ap.add_argument("--dec", type=float, required=True)
    ap.add_argument("--field", type=float, default=config.DEFAULT_FIELD_DEG)
    ap.add_argument("--name", required=True)
    ap.add_argument("--detectors", type=int, nargs="*")
    ap.add_argument("--max-frames", type=int, default=config.MAX_SEQUENCE_FRAMES)
    ap.add_argument("--max-candidates", type=int, default=config.MAX_SEQUENCE_CANDIDATES)
    args = ap.parse_args()

    seq, report = find_sequence(args.ra, args.dec, args.field, detectors=args.detectors,
                                max_frames=args.max_frames, max_candidates=args.max_candidates)
    path = save_report(report, args.name)
    print(f"Informe: {path}")
    if seq is None:
        print("Ninguna secuencia admisible.")
        return 1
    print(f"SECUENCIA SELECCIONADA: {seq.n} épocas, D{seq.frames[0].detector}")
    for i, f in enumerate(seq.frames):
        print(f"  {i}: {f.date_utc[:19]}  {f.obs_id:<20} {f.collection:<12} λ={f.lambda_target_um:.4f} µm "
              f"válido={f.quality['valid_fraction_in_field']:.1%}")
    for c in seq.criteria:
        print(f"  [{c['status'].upper():4}] {c['id']} {c['criterion']}: {c['value']}")
    for n in seq.notes:
        print(f"  NOTA: {n}")
    for r in report["rejected_larger_options"]:
        print(f"  Rechazada opción de {r['n_frames']} épocas (cobertura {r['coverage']:.1%}): {'; '.join(r['reasons'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
