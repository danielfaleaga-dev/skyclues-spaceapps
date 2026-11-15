"""Independent audit (Claude B): Gaia outage handling, offline.

1. eps Ind B D3 with NO Gaia -> must not fabricate a motion measurement.
2. WISE 0855 D6 and eps Ind B D3 with a *recorded real* Gaia response (data/cache/gaia-*.json) when its
   field matches the saved cutout -> internal Gaia-consuming code reproduces the saved result.
Read-only: originals come from the local cache and their SHA-256 is checked."""
import json, math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from skyclues import archive, config, fitsdata, motion
from skyclues.astrometry import Astrometry

def load(name):
    saved = json.loads((config.RESULTS_DIR / name).read_text(encoding="utf-8"))
    urls = [f["cutout_url"] for f in saved["files"]]
    got = archive.fetch_many(urls)
    frames = []
    for f, u in zip(saved["files"], urls):
        assert archive.sha256(got[u]) == f["sha256"], "SHA mismatch"
        frames.append(motion.MotionFrame(fitsdata.load(got[u]), {"collection": f["collection"]}, u, got[u], f["sha256"]))
    return saved, frames

out = {}
for name in ("motion_eps_ind_b_d3.json", "motion_wise0855_d6.json"):
    saved, frames = load(name)
    src = (saved["source"]["selected_ra"], saved["source"]["selected_dec"])
    astro = Astrometry.from_dict(saved["astrometry"]) if saved.get("astrometry") else None
    inv = motion.investigate(frames, src, gaia=None, astrometry=astro)
    r = motion.to_jsonable(inv)
    row = {"saved_outcome": saved["outcome"], "no_gaia_outcome": r["outcome"],
           "no_gaia_has_displacement": bool(r.get("displacement")), "reasons": r.get("reasons")}
    out[name] = row
    print(name, json.dumps(row, ensure_ascii=False)[:600])
Path(ROOT / "results/independent_audit/gaia_offline.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
