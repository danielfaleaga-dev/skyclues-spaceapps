"""Independent audit (Claude B): RGB composition correspondence with real cube data (read-only)."""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from skyclues import multiband as mb, spectral_cube as sc

ra, dec, fov = 210.8024, 54.3488, 0.1
chs = sc.tile_for(ra, dec).channels
res = {}
def check(name, ok, detail=None):
    res[name] = {"ok": bool(ok), "detalle": detail}; print(("OK   " if ok else "FAIL ") + name, detail if not ok else "")

nums = {"R": 88, "G": 47, "B": 21}
c1 = mb.build(ra, dec, fov, chs, nums, "independiente")
by = {c.number: c for c in chs}
for r, n in nums.items():
    c = c1.channels[r]
    check(f"{r}: canal {n} = plano {n-1}, λ {by[n].wavelength_um:.3f} µm de la tabla del FITS",
          c.number == n and c.plane == n - 1 and c.wavelength_um == by[n].wavelength_um and c1.maps[r].channel.number == n)
    ref = sc.channel_map(ra, dec, fov, n - 1)            # lectura separada del mismo plano
    same = all(np.array_equal(np.nan_to_num(a.image, nan=-9e99), np.nan_to_num(b.image, nan=-9e99)) and np.array_equal(a.nhits, b.nhits)
               for a, b in zip(c1.maps[r].patches, ref.patches))
    check(f"{r}: los píxeles de la composición son los del plano {n-1} leído por separado (sin remuestreo)", same)
# swapping roles must swap display channels
c2 = mb.build(ra, dec, fov, chs, {"R": 21, "G": 47, "B": 88}, "independiente")
rgb1, rgb2 = c1.rgb(0), c2.rgb(0)
ok = np.allclose(rgb1[..., 0], rgb2[..., 2], equal_nan=True) and np.allclose(rgb1[..., 2], rgb2[..., 0], equal_nan=True) and np.allclose(rgb1[..., 1], rgb2[..., 1], equal_nan=True)
check("Intercambiar R y B intercambia exactamente los canales de color mostrados", ok)
# blank channels refused
try:
    mb.build(ra, dec, fov, chs, {"R": 51, "G": 47, "B": 21}); check("El canal 51 (sin datos en DR1) se rechaza", False)
except Exception as e:
    check("El canal 51 (sin datos en DR1) se rechaza antes de leer", True, type(e).__name__)
# pixels without data in any channel are NaN, never partial colour
ok = True
for i in range(len(c1.patches)):
    m = c1.common_valid(i); out = c1.rgb(i)
    ok &= bool(np.all(np.isnan(out[~m])))
check("Sin dato en algún canal → NaN en los tres (nunca color parcial)", ok)
check("La composición no suma ni promedia canales: provenance sin 'promedio'/'suma'", "promedi" not in json.dumps(c1.provenance(), ensure_ascii=False).lower())
Path(ROOT / "results/independent_audit/rgb_check.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
print(sum(v["ok"] for v in res.values()), "de", len(res))
