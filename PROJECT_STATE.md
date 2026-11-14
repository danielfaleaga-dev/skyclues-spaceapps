# SkyClues — estado del proyecto

Última actualización: 14-11-2026, Claude Code A (misión 3: robustez científica, FOV y preparación de la primera versión pública). El contexto estable está en [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md).

## Objetivo inmediato
Primera versión pública (pendiente de autorización para desplegar): decidir si se versionan los FITS de los ejemplos (ver «Decisiones pendientes»), hacer el refinamiento visual (Codex) y desplegar en Streamlit Community Cloud.

## Terminado y verificado
| Componente | Verificación |
|---|---|
| Entorno: Python 3.11 en `.venv`; `requirements.txt` (solo runtime, versiones fijadas) y `requirements-dev.txt` (pytest) | instalado y en uso |
| Consulta SIA2 a `spherex_dr1` y `spherex_qr3`, con caché JSON de 12 h | prueba real |
| Recortes IBE: caché intacta con SHA-256, reintentos ante 503, 3 descargas en paralelo. **Novedades:** escritura atómica con nombre temporal único (reintento ante el bloqueo de Windows), una sola descarga por URL aunque la pidan varios hilos, y almacén opcional de solo lectura `data/reference/` | pruebas unitarias: 8 escritores concurrentes, 5 hilos → 1 descarga, prioridad de `data/reference/` sin red |
| Lectura MEF con WCS celeste y espectral; FLAGS leídos de MSKN | pruebas reales |
| Estimación de λ sin descargar (homografía `s_region` + tabla WCS-WAVE) | λ estimada = λ del FITS |
| Parejas (C1–C9) y secuencias de N épocas (S1–S9 globales); regla de selección sin cambios | pruebas originales en verde |
| **Geometría exacta (nueva, modo por defecto del reproductor):** cada píxel nativo de cada época se dibuja como un cuadrilátero en su posición WCS real (`TemporalSequence.native_corners`), con su valor original y sin remuestreo. La rejilla común por vecino más próximo se mantiene para las métricas y como vista opcional, con la etiqueta «REMUESTREADO» en la leyenda y en cada fotograma | pruebas reales: posición dibujada = posición WCS (< 0.01″); valores idénticos bit a bit al FITS; máscara = píxeles nativos inválidos |
| **HALO (nuevo):** se añade SATELLITE_HALO (bit 29, siempre enmascarado). Modo exploratorio opcional: los píxeles enmascarados **solo** por HALO se muestran en escala cobre (el brillo conserva el orden), con su leyenda. Las métricas y criterios usan siempre la máscara estricta | pruebas: solo cambian los píxeles HALO; todos tienen el bit 28; los criterios, métricas y máscaras no cambian |
| **Búsqueda con progreso (nuevo):** `find_sequence(progress=…)` informa de 5 etapas y de cada recorte (descargados / ya en caché); `load_sequence(progress=…)` descarga en paralelo. La app muestra una barra de progreso y mensajes claros cuando IRSA falla, sin datos parciales | prueba unitaria de etapas; en el navegador, búsqueda real de M101 a 12′ en D2: 8 recortes descargados con la barra de progreso, 143.8 s, 2 épocas, 96.0 % |
| **Accesos rápidos a ejemplos validados (nuevo):** botones para M101 (4 épocas) y WISE 0855 (D6, 3 épocas) | AppTest y navegador |
| **Campo de visión (FOV) seleccionable (nuevo; recomendación oficial del desafío):** valores predefinidos de 3′, 6′ (por defecto), 12′ y 18′, o un valor personalizado entre 3′ y 30′, con su equivalencia en grados y píxeles. Se aplica de verdad a la búsqueda: los candidatos deben contener el campo completo, λ se muestrea en todo el campo, el recorte IRSA tiene ese tamaño y la cobertura se calcula sobre ese campo. La URL lo guarda (`fov=`) y valores no válidos se acotan. Se distingue del zoom (tamaño en pantalla fijo) y se avisa de que los campos mayores tardan más | AppTest: búsqueda de 18′ → `field_deg = 0.3` y recortes `size=0.30000`; búsquedas reales de 18′ y 30′ (ver tabla) |
| **Varias sesiones simultáneas (defecto encontrado y corregido):** el texto matemático de matplotlib (etiquetas de los ejes WCS) fallaba con `ParseException` al dibujar desde varios hilos, como hace Streamlit con cada visitante. Ahora las figuras son `Figure` independientes de pyplot y todo el dibujo se hace bajo `render.RENDER_LOCK`. La app muestra PNG generados bajo ese bloqueo | prueba: 4 hilos generan 16 fotogramas idénticos byte a byte a los secuenciales (4 de 4 ejecuciones) y pyplot no queda con figuras abiertas |
| **Instalación limpia (simula el despliegue):** clon nuevo del commit, entorno nuevo con **Python 3.14.3** y solo `requirements-dev.txt`; `bundle_reference.py` → 7 FITS, 28.0 MB, SHA-256 correcto; sin caché, las pruebas sin red y las 3 pruebas de la app con los ejemplos pasan **con 0 descargas** (servido desde `data/reference/`) | ejecutado |
| Reproductor: reproducción, pausa, velocidad, repetición, paso, deslizador, blink y teclado | **navegador real, tras los cambios**: siguiente/anterior, reproducción a 1 fps, pausa y blink 1↔2 |

## Medidas de esta sesión (datos reales)
- **Error del vecino más próximo:** en `sequence_m101`, las épocas 2 y 3 están giradas −5.97° respecto a la época 1. En la rejilla común, cada píxel puede desplazarse hasta **0.70 px (≈4.3″)**, y en el campo se duplican 20 píxeles nativos y se pierden otros 20. En `sequence_wise0855_mwir` la escala difiere un 0.54 % y el error llega a ±0.5 px por eje. La geometría exacta elimina ese error (< 0.01″). En dos estrellas brillantes de M101, el centroide varía 0.21 px entre épocas con el vecino más próximo y 0.13 px con la geometría nativa (muestra pequeña; es solo indicativo).
- **HALO en M101:** los píxeles enmascarados solo por HALO son el 0.4–1.4 % del campo por época. Están alrededor de las estrellas brillantes, como describe el suplemento.
- **FOV mayor (búsquedas reales en frío, limitadas a dos detectores):**

| Campo | FOV | Píxeles/época | Resultado | Tiempo | Memoria | Reproductor |
|---|---|---|---|---|---|---|
| M101, D2 | 18′ (0.3°) | 176² | 2 épocas, 93.5 %, 9/9 cumplen | 113 s (descargas 112 s) | — | 0.7 s · 322 kB |
| WISE 0855, D5–D6 | 30′ (0.5°) | 292² | 3 épocas D6, 86.0 %, 9/9 cumplen | 148 s (descargas 146 s) | pico 206 MB | 1.3 s · 916 kB |

  Con un campo mayor, la dispersión de λ entre épocas crece (0.29 BW en M101 a 18′), así que la regla de selección elige menos épocas. Cada recorte pesa unos 4 MB con cualquier FOV (lo domina la extensión EPSF).
- **Servidor Streamlit:** 224 MB de memoria residente (pico 264 MB) tras abrir los dos ejemplos en las dos geometrías, con y sin HALO, y una búsqueda de 18′. Community Cloud ofrece entre 690 MB y 2.7 GB.

## Secuencias de referencia (sin cambios; informes en `results/`)
| Campo | Épocas | Fechas (UTC) | λ en el objetivo | Cobertura común | Criterios |
|---|---|---|---|---|---|
| M101 (`sequence_m101`), QR3 D2 | 4 | 17-05, 22-05, 19-06 y 22-06-2026 (36.4 d) | 1.4151–1.4206 µm | 94.0 % | 9/9 |
| WISE 0855 (`sequence_wise0855_mwir`), DR1 D6 | 3 | 26-04, 30-04 y 08-05-2026 (12.9 d) | 4.823–4.826 µm | 88.0 % | 9/9 |
| WISE 0855 (`sequence_wise0855`), DR1 D3 | 3 | las mismas | 2.156–2.159 µm | 86.8 % | 9/9 |

Las parejas `pair_m101` y `pair_wise0855` y la prueba nula siguen vigentes. Con 12.9 días no se espera ver el movimiento propio de WISE 0855 (≈0.3″).

## Pruebas
```
.venv\Scripts\python -m pytest -q                 # 59 passed, 14-11-2026 (38 anteriores + 21 nuevas)
.venv\Scripts\python -m pytest -m "not network"   # 23 unitarias (incluye la máquina de estados del reproductor con Node)
```
Nuevas: `tests/test_robustness_offline.py` (10) y `tests/test_robustness_live.py` (7, incluida la de dibujo concurrente). `tests/test_app.py` pasa de 3 a 7 pruebas: ejemplos validados, opciones de visualización, FOV y un fallo simulado de IRSA (503), que muestra un mensaje claro sin datos parciales. Los selectores de las 3 pruebas existentes ahora usan claves de widget; sus aserciones no cambian. Las pruebas del motor (19) y de secuencias siguen sin cambios.

## Despliegue en Streamlit Community Cloud (preparado; **no desplegado**)
- `app.py` en la raíz; `requirements.txt` solo con dependencias de ejecución; `.streamlit/config.toml` con tema claro, sin estadísticas de uso y con la barra de herramientas mínima. No hacen falta `packages.txt` ni secretos.
- Python: se elige en *Advanced settings* al desplegar (por defecto, 3.12). Recomendado: 3.11, la versión de desarrollo.
- El reproductor es HTML y JS en `components.html`, sin dependencias externas ni CDN. Funciona en el navegador local.
- El disco no es persistente: la caché se pierde al reiniciar y la primera visita vuelve a descargar los FITS (unos 30–60 s por ejemplo si IRSA responde).

## Decisiones pendientes (usuario)
1. **¿Versionar los FITS de los ejemplos validados?** `scripts/bundle_reference.py` los copia a `data/reference/` (28 MB en 7 archivos idénticos a IRSA, con SHA-256 verificado). Ventaja: los ejemplos se abren al instante en la nube aunque IRSA esté saturado. Coste: unos 28 MB más en el historial de git. El código ya los usa si existen; no se han añadido al repositorio.
2. Autorización para desplegar. (El código ya está en GitHub, rama `main` de `danielfaleaga-dev/SkyClues`, subido el 14-11-2026 por petición del usuario; no se ha cambiado la visibilidad del repositorio.)

## API para Codex (`skyclues.sequence`, `skyclues.player`)
```python
from skyclues.sequence import find_sequence, load_sequence, report_urls
seq, report = find_sequence(ra, dec, field_deg=0.1, detectors=None, max_frames=8,
                            progress=lambda stage, frac, msg: ...)     # stage ∈ sequence.STAGES
seq = load_sequence("results/sequence_m101.json", progress=lambda done, total, n_downloaded: ...)
seq.frame_data(i)            # rejilla común (vecino más próximo): para estadísticas
seq.native_data(i)           # rejilla propia de la época: valores originales (NaN = inválido)
seq.native_corners(i)        # esquinas (X, Y) de sus píxeles en coordenadas de la rejilla común
seq.native_caution(i)        # píxeles enmascarados solo por HALO
seq.placement_error_px(i)    # desplazamiento del vecino más próximo en cada píxel
html = player.build_player(seq, subtract_zodi=True, restrict_to_common=False,
                           geometry="exact" | "nearest", show_halo=False)
```
Reglas: una única `sequence_norm`; los NaN se dibujan con `MASK_COLOR`; la geometría «nearest» debe mostrarse siempre como remuestreada; HALO solo es visible en modo exploratorio y con su color; las opciones de visualización no modifican nunca la secuencia ni sus métricas. Limitar el FOV con `targets.clamp_fov_deg` (3′–30′). Las figuras nuevas deben ser `Figure` (no pyplot), construirse con `@render.serialized` y mostrarse con `st.image(render.figure_png(fig))`, no con `st.pyplot`.

## Problemas abiertos
1. No hay vista con el norte arriba: los ejes son los del detector de la época 1.
2. La λ por píxel tiene precisión de visualización (WCS-WAVE); CWAVE/CBAND no están implementados.
3. RW Aur, R Dra, Barnard y ε Ind B no se han ejecutado, y la propagación del movimiento propio no está implementada.
4. Con 8 épocas y un FOV de 30′, el HTML del reproductor rondaría los 2.4 MB (unos 300 kB por fotograma).
5. Una búsqueda en frío depende de la velocidad de IRSA (unos 14–20 s por recorte, 3 en paralelo).
6. Streamlit no recarga `skyclues/`: hay que reiniciar el servidor tras editarlo.
7. No se ha probado con Python 3.12, la versión por defecto de Community Cloud (sí con 3.11 y en una instalación limpia con 3.14).

## Siguiente tarea prioritaria
- **Usuario:** decisiones pendientes 1 y 2.
- **Codex:** refinamiento visual, accesibilidad y despliegue (con autorización).
- **Claude A:** objetos variables (RW Aur, R Dra) y propagación del movimiento propio para el marcador del objetivo (sin presentarla como detección).
- **Claude B:** Spectrum Explorer (ver CONTEXT).
