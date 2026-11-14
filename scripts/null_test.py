"""Null test on a comparable pair: for a static field, the normalised
difference chi = [(A - ZODI_A) - (B - ZODI_B)] / sqrt(VAR_A + VAR_B) over the
common valid pixels should be centred on 0 with unit-ish scatter.

Usage: python scripts/null_test.py [results/pair_m101.json]
"""

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skyclues import archive, config, fitsdata  # noqa: E402
from skyclues.compare import evaluate_pair, place_on_a  # noqa: E402


def main(path):
    rep = json.loads(Path(path).read_text(encoding="utf-8"))
    sel, t = rep["selected"], rep["target"]
    a = fitsdata.load(archive.fetch(sel["a"]["cutout_url"]))
    b = fitsdata.load(archive.fetch(sel["b"]["cutout_url"]))
    ev = evaluate_pair(a, b, t["ra_deg"], t["dec_deg"], t["field_deg"])
    sa = a.image - a.zodi
    sb = place_on_a(b.image - b.zodi, ev.b_index, ev.in_b)
    vb = place_on_a(b.variance, ev.b_index, ev.in_b)
    c = ev.common
    diff = sa[c] - sb[c]
    chi = diff / np.sqrt(a.variance[c] + vb[c])
    mad = 1.4826 * np.median(np.abs(chi - np.median(chi)))
    xa = np.array(a.detector_offset()) + a.wcs.all_world2pix([[t["ra_deg"], t["dec_deg"]]], 0)[0]
    xb = np.array(b.detector_offset()) + b.wcs.all_world2pix([[t["ra_deg"], t["dec_deg"]]], 0)[0]
    out = {
        "n_common_px": int(c.sum()),
        "median_diff_mjysr": float(np.median(diff)),
        "median_signal_a_mjysr": float(np.median(sa[c])),
        "chi_median": float(np.median(chi)),
        "chi_robust_std": float(mad),
        "frac_abs_chi_gt_5": float(np.mean(np.abs(chi) > 5)),
        "target_full_detector_px_a": xa.round(1).tolist(),
        "target_full_detector_px_b": xb.round(1).tolist(),
        "note": "B placed on A grid by nearest neighbour (<= 0.5 px offset); PSF/sub-pixel offsets inflate chi on bright sources.",
    }
    print(json.dumps(out, indent=2))
    (config.RESULTS_DIR / (Path(path).stem + "_null_test.json")).write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else config.RESULTS_DIR / "pair_m101.json")
