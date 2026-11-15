"""Genera los informes congelados de V03 a partir de resultados.json (sin identificar los objetos)."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "blind_v03"
IDS = ["C05", "C12", "C14"]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def runs(nums):
    nums, out = sorted(nums), []
    for n in nums:
        if out and n == out[-1][1] + 1:
            out[-1][1] = n
        else:
            out.append([n, n])
    return ", ".join(str(a) if a == b else f"{a}–{b}" for a, b in out)


def report(k):
    r = json.loads((OUT / k / "resultados.json").read_text(encoding="utf-8"))
    ok = [x for x in r["espectro"] if x["status"] == "ok"]
    cov = [c for c in r["cobertura_campo"] if not c["sin_datos_dr1"]]
    L = [f"# {k} · informe congelado (fase ciega V03)", "",
         "Sin consulta de publicaciones ni resolución de nombres en esta fase. Datos en `resultados.json`; figuras `espectro.png` (espectro completo) y `campo.png`.", "",
         "## Datos de partida", "",
         f"- **Posición** (ICRS, nominal fijada en la preselección): RA {r['ra_deg']:.6f}°, Dec {r['dec_deg']:+.6f}° ({r['coordenadas_dadas']['ra']} {r['coordenadas_dadas']['dec']}). FOV {r['coordenadas_dadas']['fov_arcmin']:g}′. No se ha desplazado.",
         f"- **Producto SPHEREx:** cubo DR1 HiPS orden 5, teselas {', '.join(str(p['ipix']) for p in r['productos_spherex'])} (`hips_20261026`, DOI 10.26131/IRSA679).",
         f"- **Apertura:** {r['apertura_px']['r_ap']:g} px ({r['apertura_px']['r_ap'] * r['escala_px_arcsec']:.1f}″; {r['n_apertura_px']:.2f} px efectivos). **Anillo de fondo:** {r['apertura_px']['r_in']:g}–{r['apertura_px']['r_out']:g} px ({r['n_anillo_px']} px), media con recorte 3σ.",
         f"- **Método:** `{r['metodo'].get('version', r['metodo'].get('METHOD_VERSION', 'skyclues-features 1.0 (2026-11-14)'))}`, huellas del código idénticas a las de V02 (`huellas_metodo.json`).",
         f"- **Cobertura del campo:** ≥ {min(c['fraccion_valida'] for c in cov):.1%} de píxeles válidos; NHITS mediano {min(c['nhits_mediano'] for c in cov):.0f}–{max(c['nhits_mediano'] for c in cov):.0f}.", "",
         "## Canales y calidad", "",
         f"- **Con valor: {len(ok)} de 102.** Sin valor: {runs(r['canales_sin_valor'])} ({'; '.join(sorted(set(r['estado_sin_valor'].values())))}).",
         f"- **OVERFLOW/OUTLIER en la apertura:** {len(r['canales_precaucion_overflow_outlier'])} canales" + (f" ({runs(r['canales_precaucion_overflow_outlier'])})" if r['canales_precaucion_overflow_outlier'] else "") + ".",
         f"- **Rango del flujo en apertura:** {min(x['flujo_mjy'] for x in ok):.1f}–{max(x['flujo_mjy'] for x in ok):.1f} mJy; canales con flujo ≤ 0: {sum(x['flujo_mjy'] <= 0 for x in ok)}.",
         f"- **Dispersión mediana del anillo:** {sorted(x['fondo_sigma_mjysr'] for x in ok)[len(ok) // 2]:.4g} MJy/sr.", "",
         f"## Resultado del analizador (parámetros congelados)", "",
         f"**Características etiquetadas: {len(r['caracteristicas'])}.**", ""]
    if r["caracteristicas"]:
        L += ["| Tipo | Clase | λ del extremo (µm) | Media altura (µm) | Canales | Contraste (mJy) | Relativo | Contraste/dispersión | Detectores |", "|---|---|---|---|---|---|---|---|---|"]
        for f in r["caracteristicas"]:
            L.append(f"| {f['kind']} · {f['width']} | {f['label']} | {f['lam']:.3f} | {f['lam_lo']:.3f}–{f['lam_hi']:.3f} | {f['canal_lo']}–{f['canal_hi']} | {f['contrast']:+.4g} | {f['relative']:+.1%} | {abs(f['ratio']):.1f} | {', '.join('D%d' % d for d in f['detectors'])} |")
        L.append("")
        for f in r["caracteristicas"]:
            L.append(f"- **{f['lam']:.3f} µm** — continuo local {f['continuum']:.4g} mJy; dispersión de referencia = máx(entorno {f['ref_local']:.3g}, detector {f['ref_detector']:.3g}, fondo {f['ref_background']:.3g}); entorno canales {f['env_left'][0]}–{f['env_left'][-1]} y {f['env_right'][0]}–{f['env_right'][-1]}. " + " ".join(f["limitations"]))
        L.append("")
    L += ["**Anomalías por debajo del criterio** (de 2,5 a 5 veces la dispersión):", ""]
    if r["anomalias_bajo_criterio"]:
        L += ["| Canal | λ (µm) | Tipo | Intervalo | Contraste (mJy) | Relativo | Contraste/dispersión |", "|---|---|---|---|---|---|---|"]
        for a in r["anomalias_bajo_criterio"]:
            rel = "—" if a["relativo"] is None else f"{a['relativo']:+.1%}"
            L.append(f"| {a['canal']} | {a['lambda_um']:.3f} | {a['tipo']} | {a['intervalo'][0]}–{a['intervalo'][1]} | {a['contraste']:+.4g} | {rel} | {abs(a['contraste_dispersion']):.2f} |")
    else:
        L.append("Ninguna.")
    L += ["", f"**No evaluables ({len(r['canales_no_evaluables'])}):** {runs([x['canal'] for x in r['canales_no_evaluables']])}.", "",
          "## Conclusión registrada", "",
          "Resultado descriptivo del analizador: " + (", ".join(f"{f['kind']} {f['label'].lower()} en {f['lam']:.3f} µm ({abs(f['ratio']):.1f}×)" for f in r["caracteristicas"]) or "ninguna característica etiquetada") +
          ". Ninguna es una detección: el cubo no tiene incertidumbres. No se atribuye ninguna molécula ni se interpreta físicamente en esta fase."]
    (OUT / k / "INFORME_CONGELADO.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def summary():
    L = ["# V03 · resumen congelado (antes de cualquier consulta bibliográfica)", "",
         "Selección: `PRESELECCION.md` (commit `155d9e5`). Método `skyclues-features 1.0 (2026-11-14)` con las huellas de `huellas_metodo.json`, idénticas a V02. Posiciones nominales sin desplazar; sin comparación A/B.", "",
         "| Prueba | Canales con valor | Cuantificables | Visibles | Anomalías bajo criterio |", "|---|---|---|---|---|"]
    for k in IDS:
        r = json.loads((OUT / k / "resultados.json").read_text(encoding="utf-8"))
        q = sum(f["klass"] == "cuantificable" for f in r["caracteristicas"])
        v = sum(f["klass"] == "visible" for f in r["caracteristicas"])
        L.append(f"| {k} | {r['canales_con_valor']}/102 | {q} | {v} | {len(r['anomalias_bajo_criterio'])} |")
    L += ["", "## Huellas SHA-256", ""]
    for k in IDS:
        for f in ("resultados.json", "INFORME_CONGELADO.md", "espectro.png", "campo.png"):
            L.append(f"- `{k}/{f}`: `{sha(OUT / k / f)}`")
    for f in ("huellas_metodo.json", "preseleccion.json", "PRESELECCION.md"):
        L.append(f"- `{f}`: `{sha(OUT / f)}`")
    (OUT / "RESUMEN_CONGELADO.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    for k in IDS:
        report(k)
    summary()
