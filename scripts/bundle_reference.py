"""Copy the FITS cutouts of the validated example sequences to data/reference.

The copies are byte-identical to the IRSA cutouts (SHA-256 checked against
the saved report). ``archive.fetch`` reads data/reference before the cache
or IRSA, so the examples open without network access. Whether to version
these files (~4 MB each) is a repository decision; see PROJECT_STATE.md.

    python scripts/bundle_reference.py                 # the validated examples (config.VALIDATED_EXAMPLES)
    python scripts/bundle_reference.py sequence_m101   # specific reports in results/
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skyclues import archive, config  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", default=list(config.VALIDATED_EXAMPLES))
    args = ap.parse_args()
    config.REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for name in args.names:
        rep = json.loads((config.RESULTS_DIR / f"{name}.json").read_text(encoding="utf-8"))
        sel = rep["selected"]
        frames = sel["frames"] if rep.get("kind") == "sequence" else [sel["a"], sel["b"]]
        for f in frames:
            src = archive.fetch(f["cutout_url"])
            digest = archive.sha256(src)
            if digest != f["sha256"]:
                raise SystemExit(f"SHA-256 mismatch for {src.name}; not copied")
            dst = config.REFERENCE_DIR / archive._cache_path(f["cutout_url"]).name
            if src.resolve() != dst.resolve():
                shutil.copyfile(src, dst)
            total += dst.stat().st_size
            print(f"{name}: {dst.name} ({dst.stat().st_size / 1e6:.1f} MB, sha256 ok)")
    print(f"data/reference: {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
