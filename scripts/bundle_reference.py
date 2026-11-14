"""Copy the FITS cutouts of the validated example sequences to data/reference.

The copies are byte-identical to the IRSA cutouts: SHA-256 checked against
the saved report and structure checked (complete Level-2 MEF) before
copying. ``archive.fetch`` reads data/reference before the cache or IRSA, so
the examples open without network access. ``data/reference/MANIFEST.json``
records the provenance of every file (report, observation, IRSA cutout URL,
source Level-2 file, SHA-256, size, data release reference).

An existing reference file is never overwritten: if its SHA-256 differs
from the report the script stops and reports it.

    python scripts/bundle_reference.py                 # the validated examples (config.VALIDATED_EXAMPLES)
    python scripts/bundle_reference.py sequence_m101   # specific reports in results/
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from astropy.time import Time  # noqa: E402

from skyclues import archive, config  # noqa: E402

RELEASES = {
    "spherex_dr1": "SPHEREx DR1 Spectral Images, NASA/IPAC IRSA, doi:10.26131/IRSA678",
    "spherex_qr3": "SPHEREx Quick Release 3 Spectral Images, NASA/IPAC IRSA",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", default=list(config.VALIDATED_EXAMPLES))
    args = ap.parse_args()
    config.REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    mpath = config.REFERENCE_DIR / "MANIFEST.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {"files": {}}
    total = 0
    for name in args.names:
        rep = json.loads((config.RESULTS_DIR / f"{name}.json").read_text(encoding="utf-8"))
        sel = rep["selected"]
        frames = sel["frames"] if rep.get("kind") == "sequence" else [sel["a"], sel["b"]]
        for f in frames:
            dst = config.REFERENCE_DIR / archive._cache_path(f["cutout_url"]).name
            if dst.exists():
                if archive.sha256(dst) != f["sha256"]:
                    raise SystemExit(f"{dst.name} ya existe en data/reference y su SHA-256 no coincide con "
                                     f"{name}.json: no se sobrescribe. Revíselo a mano.")
            else:
                src = archive.fetch(f["cutout_url"])          # cache or IRSA; integrity-checked
                data = src.read_bytes()
                archive.validate_fits_bytes(data)
                if archive.hashlib.sha256(data).hexdigest() != f["sha256"]:
                    raise SystemExit(f"SHA-256 de {src.name} distinto del informe {name}.json; no se copia")
                archive.atomic_write(dst, data)
            entry = manifest["files"].setdefault(dst.name, {"used_by": []})
            entry.update({
                "sha256": f["sha256"], "bytes": dst.stat().st_size,
                "obs_id": f.get("obs_id"), "date_utc": f.get("date_utc"), "detector": f.get("detector"),
                "collection": f.get("collection"), "source_file": f.get("file_name"),
                "cutout_url": f["cutout_url"], "release": RELEASES.get(f.get("collection"), f.get("collection")),
            })
            if name not in entry["used_by"]:
                entry["used_by"].append(name)
            total += dst.stat().st_size
            print(f"{name}: {dst.name} ({dst.stat().st_size / 1e6:.1f} MB, sha256 ok)")
    manifest.update({
        "description": "Copias byte a byte de recortes IRSA usados por los ejemplos validados de SkyClues. "
                       "No modificar: la app comprueba su SHA-256 frente a los informes de results/.",
        "credit": "Datos: NASA/IPAC Infrared Science Archive (IRSA), misión SPHEREx.",
        "updated_utc": Time.now().isot[:19],
    })
    archive.atomic_write(mpath, json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"data/reference: {total / 1e6:.1f} MB · MANIFEST.json con {len(manifest['files'])} archivos")


if __name__ == "__main__":
    main()
