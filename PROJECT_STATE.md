# SkyClues — estado del proyecto

Última actualización: 14-11-2026, Claude Code A (misión 2: secuencias de N épocas y reproductor). El contexto estable está en [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

## Objetivo inmediato
Hito 4 (experiencia de usuario): pulir la interfaz (Codex), añadir contexto con Aladin Lite y ejecutar los demás objetos de NASA.

## Terminado y verificado
| Componente | Verificación |
|---|---|
| Entorno: Python 3.11 en `.venv`, `requirements.txt` con versiones fijadas | instalado y en uso |
| Consulta SIA2 a `spherex_dr1` y `spherex_qr3`, con caché JSON de 12 h (`archive.py`) | prueba real |
| Recortes IBE con caché intacta, SHA-256, reintentos ante 503 y **3 descargas en paralelo** (`fetch_many`) | prueba real |
| Lectura MEF con WCS celeste y espectral (`fitsdata.py`); FLAGS leídos de MSKN (`quality.py`) | pruebas reales |
| Estimación de λ sin descargar (homografía `s_region` + tabla WCS-WAVE por petición *range*, en caché de disco) | λ estimada = λ del FITS |
| Parejas, criterios C1–C9 (`pairing.py`, `compare.py`) | sin cambios; pruebas originales en verde |
| **Secuencias de N épocas, criterios globales S1–S9 sobre todo el conjunto (`sequence.py`)** | pruebas reales: intersección de máscaras, Δλ entre todos los pares, orden cronológico, alineación WCS < 0.75 px, datos idénticos al FITS y sin interpolar |
| **Regla de selección:** solo opciones admisibles con S5 = pass y cobertura ≥ (mejor − 15 puntos); entre ellas, menos avisos y después más épocas | pruebas unitarias: una secuencia de 3 épocas con cobertura del 62 % no supera a una pareja del 97 % |
| **Reproductor temporal (`player.py`, pestaña de la app):** reproducción, pausa, velocidad de 0.5 a 4 fps, repetición, anterior/siguiente, deslizador, blink A↔B (1–4 Hz), teclado y tabla de épocas | máquina de estados probada con Node; fotogramas con lienzo idéntico; HTML con N fotogramas reales; **probado en el navegador real**: siguiente/anterior, reproducción a 4 fps con repetición, pausa, blink 1↔4 y deslizador |
| Color de máscara (rosa) en el reproductor y región no común (azul claro, opcional) | prueba píxel a píxel |
| App Streamlit (`app.py`) basada en `TemporalSequence`; una pareja se trata como secuencia de 2 épocas | AppTest: vista de referencia, todos los resultados guardados y una búsqueda nueva |

## Secuencias de referencia (datos reales; los informes están en `results/`)
| Campo | Épocas | Fechas (UTC) | Intervalos (d) | λ en el objetivo | Cobertura común | Criterios |
|---|---|---|---|---|---|---|
| M101 (`sequence_m101`), QR3 D2 | 4 | 17-05, 22-05, 19-06 y 22-06-2026 | 4.5 · 28.3 · 3.5 (total 36.4) | 1.4151–1.4206 µm (dispersión 0.16 BW; máx. 0.24 en la región) | 94.0 % (2537 px) | 9/9 cumplen |
| WISE 0855 (`sequence_wise0855_mwir`), DR1 D6, detectores limitados a D5–D6 | 3 | 26-04, 30-04 y 08-05-2026 | 4.7 · 8.2 (total 12.9) | 4.823–4.826 µm (0.07 BW; máx. 0.11) | 88.0 % | 9/9 cumplen |
| WISE 0855 (`sequence_wise0855`), DR1 D3, todos los detectores | 3 | las mismas fechas | 4.7 · 8.2 | 2.156–2.159 µm (0.04 BW; máx. 0.07) | 86.8 % | 9/9 cumplen |

- Notas sobre WISE 0855: es una enana Y que emite sobre todo por encima de 3.5 µm, por eso la versión D5–D6 es la relevante. Con 12.9 días, el movimiento propio publicado (≈8″/año, no verificado aquí) supone ≈0.3″, muy por debajo de un píxel de 6.2″: **no se espera ver movimiento** en esta secuencia. La pareja `pair_wise0855` (DR1 D5, Δt = 373 d) sigue siendo la mejor línea base y el reproductor también la abre.
- **Razones de rechazo registradas:** las opciones de 4 épocas en WISE 0855 (D2 con cobertura del 81.7 % y D5 del 83.6 %) se descartaron porque S4 dio aviso: los gradientes LVF eran antiparalelos y la dispersión llegaba a 0.50 y 0.51 BW. En M101, 4 es el máximo de épocas espectralmente compatibles entre los recortes evaluados (91 propuestas).
- Las parejas originales (`pair_m101`, `pair_wise0855`) y la prueba nula siguen vigentes.

## Rendimiento
Búsqueda de secuencia en frío: 73 s en M101 y 70 s en WISE 0855, frente a ~110 s de la antigua búsqueda de parejas (el tiempo lo dominan los recortes de ~4 MB, que ahora se descargan de 3 en 3). En caliente, con metadatos y FITS en caché, tarda ~1 s.

## Pruebas
```
.venv\Scripts\python -m pytest -q          # 38 passed, 14-11-2026 (19 originales del motor sin cambios, 3 de la app, 16 nuevas)
.venv\Scripts\python -m pytest -m "not network"   # unitarias, incluida la máquina de estados del reproductor con Node
.venv\Scripts\python scripts\find_sequence.py --ra 210.802429 --dec 54.34875 --field 0.1 --name sequence_m101
.venv\Scripts\python scripts\find_sequence.py --ra 133.7951292 --dec -7.2451472 --field 0.1 --detectors 5 6 --name sequence_wise0855_mwir
.venv\Scripts\streamlit run app.py
```
Las 2 pruebas de la app de la misión 1 (vista de pareja y búsqueda de pareja) se adaptaron a la vista de secuencias. Las 19 pruebas del motor siguen sin cambios.

## API para Codex (`skyclues.sequence`, `skyclues.player`)
```python
from skyclues.sequence import find_sequence, load_sequence
seq, report = find_sequence(ra, dec, field_deg=0.1, detectors=None, max_frames=8)   # o bien:
seq = load_sequence("results/sequence_m101.json")      # también acepta informes de pareja (2 épocas)
seq.n, seq.frames                                       # cronológico
f = seq.frames[i]; f.date_utc, f.mjd, f.obs_id, f.collection, f.detector,
f.lambda_target_um, f.bandwidth_target_um, f.quality, f.cutout_url, f.sha256, f.record
f.image                                                 # SpectralImage original (IMAGE, FLAGS, VARIANCE, ZODI, WCS); no modificar
seq.frame_data(i, subtract_zodi=True)                   # MJy/sr en la rejilla de referencia; NaN = sin dato válido
seq.frame_status(i)                                     # 0 común · 1 válido solo aquí · 2 sin datos
seq.wcs, seq.field_mask, seq.common_mask, seq.valid_stack, seq.lambda_spread_bw
seq.criteria, seq.metrics, seq.notes, seq.admissible, seq.summary()
from skyclues import player
html = player.build_player(seq, subtract_zodi=True, restrict_to_common=False)  # componente listo
norm = player.sequence_norm(seq); player.frame_rgba(seq, i, norm); player.render_frame_png(...)
```
Reglas: una única `sequence_norm` para todas las épocas; los NaN se dibujan siempre con `MASK_COLOR`; hay que indicar la magnitud mostrada (IMAGE − ZODI) y que la rejilla es la de la época 1. La lógica de reproducción está en `PLAYER_CORE_JS`, separada del DOM.

## Archivos importantes
`app.py` · `skyclues/{config,archive,geometry,fitsdata,quality,compare,pairing,sequence,player,render,targets}.py` · `scripts/{find_pair,find_sequence,null_test}.py` · `tests/` · `results/*.json` (versionados; `results/search_*` lo ignora git) · `data/cache/` (FITS intactos y `meta/` con SIA2 y WCS-WAVE; ignorado por git).

## Problemas abiertos
1. La bandera **HALO** tapa estrellas brillantes con la máscara estricta. Falta confirmar su significado en la tabla 16 del suplemento (descargar el PDF en local).
2. La alineación por vecino más próximo (≤ 0.5 px) hace que una estrella fija pueda «saltar» un píxel entre épocas. Una diferencia visual no es movimiento. Falta valorar un remuestreo subpíxel etiquetado.
3. No hay vista con el norte arriba: la rejilla es la del detector de la época 1.
4. La λ por píxel tiene precisión de visualización (WCS-WAVE); CWAVE/CBAND no están implementados.
5. RW Aur, R Dra, Barnard y ε Ind B no se han ejecutado, y la propagación del movimiento propio no está implementada.
6. Con 8 épocas o campos más grandes, el HTML del reproductor crece (~80 kB por fotograma).
7. Streamlit no recarga `skyclues/`: hay que reiniciar el servidor tras editarlo.

## Siguiente tarea prioritaria
- **Codex:** refinamiento visual del reproductor y de la app, URL compartible con la secuencia elegida, accesibilidad y despliegue (con autorización).
- **Claude A:** objetos variables (RW Aur, R Dra) con la misma API, propagación del movimiento propio para el marcador del objetivo (sin presentarla como detección) y la bandera HALO.
- **Claude B:** Spectrum Explorer (ver CONTEXT).
