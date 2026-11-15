"""Verificaciones V03: método intacto, resultados congelados íntegros, procedencia SPHEREx y reproducibilidad."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from skyclues import config, spectral_cube as sc  # noqa: E402

OUT = ROOT / "results" / "blind_v03"
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
ok = True


def check(name, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(("OK   " if cond else "FALLA"), name, detail)


# 1. analyzer unchanged since V02 freeze
v02 = json.loads((ROOT / "results/blind_v02/huellas_metodo.json").read_text(encoding="utf-8"))
for f, h in v02.items():
    check(f"método intacto: {f}", sha(ROOT / f) == h)

# 2. frozen files match RESUMEN_CONGELADO.md
text = (OUT / "RESUMEN_CONGELADO.md").read_text(encoding="utf-8")
for rel, h in re.findall(r"- `([^`]+)`: `([0-9a-f]{64})`", text):
    check(f"congelado íntegro: {rel}", sha(OUT / rel) == h)

# 3. data come from SPHEREx DR1 (IRSA) and 4. reproducibility (re-extract, compare to the frozen rows)
for k in ("C05", "C12", "C14"):
    r = json.loads((OUT / k / "resultados.json").read_text(encoding="utf-8"))
    check(f"{k}: productos de IRSA/SPHEREx", all(p["url"].startswith(config.CUBE_DATA_URL) for p in r["productos_spherex"]),
          str([p["ipix"] for p in r["productos_spherex"]]))
    check(f"{k}: apertura por defecto", (r["apertura_px"]["r_ap"], r["apertura_px"]["r_in"], r["apertura_px"]["r_out"]) == tuple(config.CUBE_APERTURE_DEFAULT_PX))
    spec = sc.extract_spectrum(r["ra_deg"], r["dec_deg"])
    same = all((a["flujo_mjy"] is None and b["flujo_mjy"] is None) or abs(a["flujo_mjy"] - b["flujo_mjy"]) <= 1e-9 * max(1, abs(b["flujo_mjy"]))
               for a, b in zip(spec.rows, r["espectro"]))
    check(f"{k}: reextracción idéntica", same and len(spec.rows) == len(r["espectro"]))
print("\nTODO CORRECTO" if ok else "\nHAY FALLOS")
sys.exit(0 if ok else 1)
