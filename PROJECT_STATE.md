# SkyClues — estado del proyecto

Última actualización: 14-11-2026, Claude Code A (cierre de la misión 1). El contexto estable está en [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

## Objetivo inmediato
Hito 3 (visor temporal): pasar de una pareja A/B a una **secuencia de N épocas comparables** (mismo detector y mismo canal LVF) con animación, pausa y blink.

## Terminado y verificado
| Componente | Verificación |
|---|---|
| Entorno: Python 3.11 en `.venv`, `requirements.txt` con versiones fijadas | instalado y en uso |
| App Streamlit `app.py` (tema claro) | arranca en `localhost:8501`; se revisaron en el navegador las pestañas A/B, Cobertura y espectro, y época B |
| Consulta SIA2 a IRSA en `spherex_dr1` y `spherex_qr3` (`skyclues/archive.py`) | prueba real: 376 imágenes de M101 |
| Recortes IBE con caché y reintentos ante el 503 «Server busy» | prueba real; SHA-256 comprobado |
| Lectura MEF: IMAGE, FLAGS, VARIANCE, ZODI, WCS celeste TAN-SIP y WCS espectral `W` (WAVE-TAB) (`fitsdata.py`) | prueba real: ida y vuelta WCS < 1e-3 px; λ dentro de la banda |
| FLAGS leídos de las claves MSKN de cada archivo; política «estricta» o «básica» (`quality.py`) | pruebas unitarias y reales |
| Estimación de λ sin descargar: polígono `s_region` → homografía → tabla WCS-WAVE leída con una petición *range* de 11 kB (`geometry.py`, `pairing.py`) | λ estimada = λ del FITS (< 0.1 ancho de banda); convención de esquinas confirmada |
| Criterios C1–C9 de comparabilidad (`compare.py`, umbrales en `config.py`) | reevaluados desde los FITS en las pruebas |
| Visualización sin fabricar datos: RGBA explícito, máscara rosa, escala compartida, B colocado sobre la rejilla de A por vecino más próximo (`render.py`) | prueba: los NaN coinciden exactamente con los píxeles inválidos y los válidos valen IMAGE − ZODI |

**Defecto corregido:** antes los píxeles enmascarados se pintaban en blanco, como si fueran estrellas. Ahora la imagen RGBA se compone de forma explícita y una prueba lo comprueba.

## Pareja de referencia (datos reales, `results/pair_m101.json`)
M101, RA 210.802429, Dec +54.34875, campo de 0.1°. Colección QR3, detector D2.
- A: `level2_2026W21_2A_0081_4D2_spx_l2b-v27-2026-268.fits`, 22-05-2026 00:12 UTC
- B: `level2_2026W25_2A_0311_1D2_spx_l2b-v27-2026-273.fits`, 19-06-2026 22:17 UTC
- Δt = 28.9 d · λ = 1.5198 / 1.5197 µm · |Δλ| máximo en la zona común = 0.00 anchos de banda · cobertura común válida 97.9 % (2655 px) · L2DQA Pass/Pass · FINAST 0/0 · software 7.0.5 en ambas · sin saturación
- Los 9 criterios pasan. Nota: posible airglow de He I (D1/D2).
- Prueba nula (`results/pair_m101_null_test.json`): mediana de A − B = −0.0002 MJy/sr frente a una señal de 0.90; χ con mediana −0.005 y dispersión robusta 1.36 (inflada por el desfase subpíxel del vecino más próximo).
- Alternativa evaluada en una iteración anterior: DR1 D2, 16-05-2025 frente a 07-12-2025 (Δt = 205 d). Es admisible pero C4 da aviso: los gradientes LVF son antiparalelos y Δλ alcanza 0.52 anchos de banda en el borde.

## Pruebas
```
.venv\Scripts\python -m pytest -q          # 19 passed (8 sin red + 11 con IRSA o caché), 14-11-2026
.venv\Scripts\python -m pytest -m "not network"
.venv\Scripts\python scripts\find_pair.py --ra 210.802429 --dec 54.34875 --field 0.1 --name pair_m101   # ~110 s en frío
.venv\Scripts\python scripts\null_test.py
.venv\Scripts\streamlit run app.py
```

## Archivos importantes
`app.py` (UI) · `skyclues/{config,archive,geometry,fitsdata,quality,compare,pairing,render,targets}.py` · `scripts/find_pair.py`, `scripts/null_test.py` · `tests/` · `results/*.json` (versionados) · `data/cache/` (FITS de IRSA intactos; ignorados por git; se regeneran con la URL del informe y se comprueban por SHA-256).

## Problemas abiertos
1. La bandera **HALO** coincide con estrellas brillantes en algunas exposiciones y la máscara estricta las tapa. Falta confirmar su significado en la tabla 16 del suplemento (el PDF pesa más de 10 MB y no se pudo leer con la herramienta web; hay que descargarlo localmente).
2. La alineación por vecino más próximo (≤ 0.5 px) no basta para un blink o una diferencia fina. Valorar un remuestreo conservativo claramente etiquetado.
3. Los recortes siguen los ejes del detector y aún no hay vista con el norte arriba.
4. Una búsqueda en frío tarda unos 110 s (SIA2 más 8 recortes de unos 4 MB, por la extensión EPSF) e IRSA devuelve 503 bajo carga.
5. La λ por píxel viene de WCS-WAVE, con precisión de visualización (~1 nm). Para ciencia hacen falta CWAVE/CBAND, que no están implementados.
6. Solo se ha validado M101. Los objetos de NASA no se han ejecutado.
7. Streamlit no recarga los módulos de `skyclues/`: hay que reiniciar el servidor tras editarlos.

## Pendiente / siguiente tarea prioritaria
1. **Claude A:** `select_sequence()`, que a partir de los candidatos ya calculados elija todas las épocas del mismo detector con |Δλ| en el campo ≤ 0.25 anchos de banda y cobertura común suficiente, y ejecutarla en M101 y en RW Aur, R Dra y WISE 0855.
2. **Codex:** animación, pausa y navegación por fechas, blink A/B, URL compartible (ya existen `?ra=&dec=&fov=`) y pulido visual de `app.py`.
3. **Claude B (posterior):** Spectrum Explorer con `spherex_dr1_cube` / HiPS (ver CONTEXT).

## Información para Codex
- API: `archive.query_images(ra, dec)` → `ObservationRecord`; `pairing.find_pair(ra, dec, field_deg)` → `(best, report)`; `fitsdata.load(path)` → `SpectralImage`; `compare.evaluate_pair(a, b, ra, dec, field)` → `PairEvaluation` (`criteria`, `metrics`, `common`, `b_index`…); `render.display_array`, `aligned_b`, `shared_norm`, `to_rgba`, `frame_figure`.
- Reglas para la UI: misma `shared_norm` para todas las épocas; los NaN se dibujan siempre con `MASK_COLOR`; hay que indicar la magnitud mostrada (IMAGE − ZODI) y que B está sobre la rejilla de A.
- `app.py` es un único script. Si se divide, conviene no tocar `skyclues/` en paralelo con Claude A.
