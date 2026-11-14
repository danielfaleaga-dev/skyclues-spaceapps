# SkyClues — estado del proyecto

Última actualización: 14-11-2026, Claude Code: integración local de `feature/release-readiness` (Codex A) y `feature/multiband` (Claude Code A) en `main`. El contexto estable está en [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md). Las secciones anteriores conservadas más abajo son antecedentes; la primera sección prevalece sobre sus pendientes.

## Integración local de los dos desarrollos (14-11-2026)

Base común `2ec4881`. Rama temporal `integration/skyclues-complete`, fusiones explícitas (`--no-ff`) que conservan la genealogía, sin conflictos (las dos ramas no comparten archivos):

1. `cb0354b` — Integrar `feature/release-readiness` (`bee8fa8`, Codex A): actualización bajo demanda de observaciones SIA2, buscador con autocompletado (índice local + SIMBAD), enlaces compartibles `ra/dec/fov/explorer/canal`, identificación del cubo publicado. Detalle y evidencia en [`RELEASE_READINESS.md`](RELEASE_READINESS.md).
2. `d836b82` — Integrar `feature/multiband` (`47e7bd7`, Claude Code A): composición RGB de falso color en Spectrum Explorer (`multiband.py`, `multiband_view.py`, `multiband_page.py`). Tres canales auténticos del cubo DR1, cada uno con su propia normalización identificada; solo se colorean los píxeles con datos válidos en los tres (el resto con `MASK_COLOR`). Avisos de cobertura común, varias teselas, OVERFLOW/BLANKCH. Es solo visualización: sin fotometría, sin restas ni combinaciones físicas. Validación: `scripts/validate_multiband.py` → `results/multiband_validation.json`, captura `results/multiband_browser.jpg`.
3. `a2a6881` — Defecto revelado por la integración (preexistente en `2ec4881`, comprobado con `git archive`): `KeyError: 'sx_pick_ra'` al volver a Spectrum Explorer con la misma región después de pasar por Time Explorer, porque Streamlit descarta el valor de un widget no dibujado. Se reconstruye la posición si falta. Prueba de regresión `test_returning_to_spectrum_explorer_with_the_same_region_keeps_working` (falla sin la corrección).

### Regresión

`.venv\Scripts\python -m pytest -q` → **274 passed, 0 failed, 0 skipped**, 1 aviso conocido de Astropy (NaN del verificador independiente de Spectrum). FITS de referencia: 6/6 SHA-256 coinciden con `data/reference/MANIFEST.json`; `data/reference` sin cambios.

### Recorridos en navegador real (servidor de integración local)

- **A Time Explorer**: ejemplo M101, 4 épocas, 36.4 d, 1.420 µm, 94.0 %, D2; reproducción y paso de épocas.
- **B Buscador**: «Androm» sugiere M 31 (índice local); resuelve y abre en Time Explorer con centro, FOV 6′ y URL.
- **C Spectrum Explorer**: apertura desde el buscador en canal 33 (1.592 µm, 99.7 %); avance de canal; canal 51 vacío con aviso BLANKCH.
- **D Multibanda**: M31 RGB 88/56/10 con avisos (cobertura común 43 %, varias teselas, OVERFLOW 53 en canal 56). La cobertura del 43 % es real: el canal 10 solo tiene datos en 263 de 612 píxeles en DR1. Ida y vuelta canal único ↔ RGB conserva canal, posición y tripleta. Captura `results/integration_browser_m31_rgb.jpg`.
- **E Referencias**: Gaia (500 fuentes, aviso de truncamiento), ficha de fuente, AllWISE W2; centro y FOV conservados.
- **F Enlace compartido**: abierto en sesión independiente, restaura centro, FOV y canal (Spectrum) y región (Time).
- **G Actualizar observaciones**: M101 verificado en IRSA (376 productos), mismos resultados.
- **H Fallos externos** (instancia sin red mediante proxy inválido): error claro del cubo sin datos parciales; el ejemplo WISE 0855 se abre y reproduce desde `data/reference`; el buscador avisa y mantiene el índice local. Captura `results/integration_browser_offline.jpg`.

### Limitaciones pendientes (no bloqueantes)

- El enlace compartible no conserva el modo RGB ni la tripleta de canales; abre en canal único.
- El espectro solo se extrae en modo de canal único.
- Un servidor Streamlit arrancado antes de la integración debe reiniciarse (no recarga `skyclues/`; ver problema abierto 8).
- Siguen vigentes los límites de servicios y científicos de las secciones siguientes y de `RELEASE_READINESS.md`.

Sin push, despliegue, publicación ni envío a NASA. Ramas y worktrees originales conservados. La investigación de movimiento no se ha iniciado (requiere una orden aparte).

## Referencias astronómicas Gaia / WISE — integradas

Base comprobada antes de editar: `3e009ef`, árbol limpio y **173 pruebas satisfactorias**. Se mantienen los informes aceptados de Spectrum y todos los FITS originales. Sin push, despliegue, publicación ni gastos. El hash de esta entrega está en `git log -1 --oneline` (el documento forma parte del commit).

### Implementación

- Panel común `reference_page.py`, con `st.fragment` y `st.iframe`, en Time Explorer y Spectrum Explorer. Centro ICRS y FOV tomados del explorador; Aladin queda fijado al campo, sin otro sistema de navegación. Time también permite referencias antes de buscar una secuencia; Spectrum las conserva si falla la lectura de canales del cubo.
- Gaia oficial: `https://gea.esac.esa.int/tap-server/tap/sync`, tabla `gaiadr3.gaia_source`. Consulta cónica en J2016.0, TOP 501 para detectar truncamiento, máximo 500 fuentes por magnitud G, respuesta limitada a 2 MiB, timeout de conexión/lectura 8/25 s, caché en memoria 12 h / 32 campos. Reintento explícito, sin ciclos ocultos. Un fallo nunca se convierte en catálogo vacío. IDs de 64 bits conservados como texto; parámetros, unidades, consulta, fecha y SHA-256 disponibles.
- Aladin Lite **3.8.1** del paquete oficial CDS vía jsDelivr. La ruta histórica `aladin.cds.unistra.fr/AladinLite/api/v3/latest/aladin.js` y el enlace antiguo de API devolvieron 404; documentación operativa en `https://cds-astro.github.io/aladin-lite/`. Requiere WebGL2 y acceso del navegador a CDN/IRSA. Si falla Aladin, sigue disponible la tabla Gaia.
- AllWISE auténtico: `https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/W1` y `/W2`, orden 8, marco equatorial, teselas JPEG 512×512. Se comprueban propiedades y decodificación de una tesela central antes de indicar recepción. W1 ≈3.4 µm / W2 ≈4.6 µm; no se sustituyen ni alteran las imágenes SPHEREx. Las otras teselas se cargan progresivamente; el mensaje no certifica cobertura completa.
- Interruptores Gaia, posiciones calculadas y AllWISE, más selector W1/W2, ejecutados dentro del iframe: no reconstruyen SPHEREx. Selección por clic sobre el marcador o por ID, con ficha de coordenadas, movimiento propio, errores, paralaje, RV, G y RUWE. La consulta y la época usan un fragmento aislado.

### Integridad científica y límites

Gaia de catálogo se dibuja en **J2016.0** (círculos cian), separado de cruces calculadas para el año juliano TCB elegido (2000–2050). La aproximación angular usa `normalize(p + Δt·v)`, con RA/Dec, ref_epoch, pmra (= μα cos δ) y pmdec. No usa distancia/paralaje ni RV, no incluye aceleración perspectiva, paralaje del observador, binarias ni propagación de incertidumbres. No es una posición aparente de precisión ni una detección SPHEREx. Una fuente sin movimiento propio permanece solo en el catálogo. La selección está definida en 2016: no garantiza incluir fuentes que entren después ni ser completa si se trunca.

AllWISE combina fases de la era WISE **2010–2011**, según su suplemento. Las propiedades de estos HiPS mezclan descripción temporal genérica de All-Sky y límites temporales insuficientes para asignar una época local fiable: se informa «época local no verificada». No se usa esa metadata como fecha exacta de WISE 0855. JPEG para contexto visual, sin fotometría entre misiones, sin restas y sin inferir variabilidad por apariencia. No hay asociaciones automáticas; ausencia de Gaia no descarta emisión infrarroja.

### Validación y resultados

Informe reproducible: `results/references_validation.json`, generado por `scripts/validate_references.py` (requiere dependencias de desarrollo). Conserva consultas, conteos, muestras reales, hashes, URLs y medidas; no modifica `results/spectrum_validation.json`.

- **M101**, RA 210.802429°, Dec +54.348750°, FOV 6′: **283 fuentes Gaia**; **WISE 0855**, centro temporal RA 133.760100°, Dec −7.242247°, FOV 6′: **69 fuentes**. Todas las posiciones devueltas están dentro del cono, comprobadas con SkyCoord. No se identifica por ello ninguna de esas fuentes con WISE 0855.
- Campo de **Barnard**, FOV 3′: 166 fuentes. ID real `4472832130942575872`, movimiento calculado J2016→J2026 = **103.933478″**. Diferencia con el oráculo angular independiente de Astropy = **0.00000161″**; diferencia respecto al modelo espacial con distancia y RV = **0.064276″**, evidencia del límite de la aproximación. Se prueban además cruce RA=0 y proximidad polar.
- Cuatro teselas reales W1/W2 para M101/WISE 0855: HTTP 200, JPEG no uniforme de 512×512; índices verificados con astropy-healpix. **120,888 B** totales de teselas; **83,388 B** de las tres respuestas Gaia, aparte de propiedades y recursos del visor. Sin descargas masivas ni FITS nuevos.
- **28 pruebas nuevas**: 26 del motor/JavaScript y 2 de integración Streamlit. Incluyen IDs, nulos, truncamiento, límite de tamaño, coordenadas inválidas antes de red, HTTP 404/429/500/503, timeout, error WebGL, reintento WISE, controles independientes sin recrear Aladin, transferencia de región y conservación del visor científico ante fallo Gaia.
- **Regresión completa: 201 passed, 1 warning, 78.68 s**. El aviso conocido de Astropy corresponde al descarte de NaN del verificador independiente de Spectrum. Las 173 pruebas previas siguen pasando. Después se precisó el texto de época WISE y se cubrió el aviso de fallo tardío de Aladin tras ocultar/mostrar una banda; las 28 pruebas nuevas se repitieron satisfactoriamente.
- **Navegador real**: M101 y WISE 0855 en Time y Spectrum, Gaia y W1/W2 visibles, ocultación independiente, selección de fuente, centro/FOV conservados ida y vuelta. Barnard muestra marcadores J2016/J2026 separados y la ficha al pulsar; arrastrar no cambia la región. Fallo WISE HTTP 404 simulado localmente: mensaje visible, Gaia sigue utilizable. Se corrigió un estiramiento vertical al abrir una ficha larga; campo comprobado 460×460 y FOV 6′×6′ después de seleccionar. Captura: `results/references_browser.jpg`.

No quedan fallos bloqueantes conocidos de esta integración. Persisten los límites científicos y dependencias de servicios descritos; el refinamiento visual, astrometría aparente completa y asociación entre catálogos no forman parte de esta actividad.

## Validación anterior de Spectrum Explorer (base conservada)

## Objetivo inmediato
Completar funcionalidades y validación antes del refinamiento visual. Esta actividad no autoriza push, publicación, despliegue ni gastos.

## Validación de Spectrum Explorer — Codex

Estado de entrada confirmado: repositorio canónico `SkyClues`, árbol limpio y HEAD `e35942677806403eac596f53fcd75ad640af0989`. No se reconstruyeron los exploradores ni se modificaron FITS originales.

### Defectos corregidos

- **HTTP/FITS:** se rechazan Content-Range sin tamaño verificable o fuera del archivo, desaparición/cambio del ETag y multipart sin cierre. Los timeouts durante el cuerpo se clasifican como transitorios. Una cabecera truncada sin END produce error en lugar de un bucle. Se comprueban 102 planos, BLANKCH y concordancia de canales/área de píxel entre teselas. HTTP 200 sigue cerrándose sin leer el cuerpo.
- **Caché:** SHA-256 por rango detecta corrupción incluso si conserva la longitud. Los rangos antiguos sin digest se descargan de nuevo; los bytes originales no se reinterpretan como válidos. Se prueban memoria/disco/refresh, separación por ETag, cuota y lotes ≤64. Las estadísticas cuentan intentos y cuerpos HTTP realmente consumidos, incluidos delimitadores multipart; no HTTP/TLS ni `properties` (cliente genérico).
- **Espectro:** NHITS≤0 invalida la apertura y el brillo del píxel; los canales BLANKCH no muestran brillo aunque aparezcan valores contradictorios. En mapas, datos contradictorios en un canal declarado vacío provocan error. Se acota el trabajo de subpíxeles.
- **Método:** se retiró la afirmación de equivalencia exacta con el tutorial. SkyClues usa círculos sobre el cielo y 5×5 submuestras; el tutorial usa círculos en coordenadas de píxel y solapamiento exacto de Photutils. Se conserva el método existente y se identifica explícitamente su diferencia, sin inventar errores. La dispersión del fondo no se presenta como incertidumbre fotométrica.
- **Movimiento propio:** se eliminó la alternativa de propagar a la fecha actual cuando faltan fechas. Se conserva el catálogo con aviso. El punto medio de MJD-BEG/END se identifica como referencia para una posición esperada, no como época efectiva del cubo. WISE 0855: catálogo J2000.0, entradas 2025-05-05 a 2026-05-14, punto medio 2025-11-08, desplazamiento esperado 8.333″. No se afirma detección.
- **Integración:** transferir desde Time conserva RA/Dec/FOV, también para WISE; la marca de posición esperada se calcula por separado. Volver a Time inicia una búsqueda por coordenadas fijas y elimina el informe anterior para no mostrar datos de otra región. Las URL espectrales inválidas se rechazan antes de leer el cubo.
- **Lectura funcional:** mapa y espectro se ajustan a su columna sin tapar métricas; el mapa conserva igual escala angular en ambos ejes. Escala de color con ticks en espacio estirado y texto de tamaño legible. λ y su intervalo aparecen completos con unidades en una leyenda aunque una métrica se acorte. Sin refinamiento visual general.

### Evidencia científica independiente

Reproducción ejecutable: `scripts/validate_spectrum.py`; resultados por los **102 canales** y metadatos en [`results/spectrum_validation.json`](results/spectrum_validation.json).

- Posición oficial: RA 60.8109955°, Dec 51.3404038°, Npix445; λ de SPECTRAL_CHANNELS frente a `data_cube_crval3_arr`: diferencia máxima 2.37e−7 µm (redondeo float32). Se contrastó NaN ⇔ NHITS=0 en recortes de canales 51/52/63; 51/52 vacíos en la región probada. No se descargaron planos enteros para afirmar una comprobación global.
- La implementación independiente usa SkyCoord para **todos** los subpíxeles, sin los ayudantes geométricos del motor. Diferencia máxima del flujo sobre los 100 canales válidos: **3.09e−5 mJy**.
- Canal 63 (3.292999983 µm): SkyClues 2/4–7 px = **355.745064 mJy**, brillo del píxel = **12.005079 MJy/sr**, fondo = **3.866850 MJy/sr**. Photutils con círculos de rejilla 2/4–7 = **328.854263 mJy**; la diferencia geométrica no es un error estadístico ni una equivalencia exacta.
- Reproducción del tutorial con **Photutils, apertura 5 px y anillo 40–60 px**, todos los canales: canal 63 = **2548.417547 mJy**. El cambio de apertura y fondo impide equipararlo a los 355 mJy del valor predeterminado. Los vecinos inmediatos 62/64 dan **108.521952 / 209.637216 mJy** en SkyClues: la cifra «45–61 mJy en los vecinos» del relevo anterior no describe esos dos canales.
- Área HEALPix = **3.901114878e−9 sr** frente a **3.901076445e−9 sr** derivada localmente del WCS como en el tutorial (diferencia ≈0.001 %). Se registra SHA-256 del recorte independiente y ETag del FITS.
- HEALPix comparado con astropy-healpix en 3005 coordenadas, órdenes 0/5/14. Cabeceras/WCS reales comprobadas en el campo oficial y dos regiones polares, Npix1023 y Npix10240.

### Recursos medidos

En el campo oficial de 6′, lectura fría de los rangos requeridos: cabecera **80,640 B / 4 peticiones**, mapa **203,134 B / 1**, espectro **6,511,852 B / 6**. Mapa+espectro: **9.91 s**, pico **10,111,542 B** con tracemalloc (memoria Python de esas operaciones, no RSS total de Streamlit). Repetición del espectro: **0 peticiones**, 6,475,776 B de caché. Los verificadores independientes consumieron otros ~36.1 MB; ninguna tesela completa de 320.9 MB. No extrapolar estas cifras a campos/aperturas máximos o bordes entre teselas.

### Pruebas y estado externo

- Nuevas: `test_spectral_offline.py` (37), `test_spectral_app.py` (11), `test_spectral_live.py` (1): **49 pruebas**. Cubo sintético independiente servido por rangos, oráculos científicos y AppTest con red bloqueada.
- **Pasada final completa: 173 passed, 1 warning, 71.13 s**, incluidas las **49 nuevas** y las 124 anteriores. El aviso de Astropy informa de NaN descartados en el anillo del verificador independiente, no de datos rellenados. Las cuatro búsquedas reales de Time/SIA2 también pasan. Las 66 pruebas offline anteriores siguen intactas.
- Las primeras ejecuciones dentro del sandbox de Windows fallaron por permisos de `os.replace` en temporales. Al ejecutar fuera del sandbox pasaron; no se alteró la escritura atómica de Time Explorer para acomodar el entorno.
- IRSA SIA2 respondió **HTTP 200** a una consulta directa acotada; las pruebas de búsqueda real de la app y SIA2 pasaron. La caída 502 del relevo no se reproduce en esta comprobación. No se ha hecho una auditoría nueva de disponibilidad continua o equivalencia entre rutas.
- **Navegador real, localhost:8503:** escala asinh legible (0.788, 2.4, 4.95, 9.96, 20.4 MJy/sr), mapa sin solapamiento y con la misma escala angular en ambos ejes. Clic → RA 60.791315°, Dec 51.328439°, correspondiente al píxel nativo (240,216) con error <0.00013 px por el redondeo mostrado. El aviso conserva explícitamente el espectro anterior hasta pulsar actualizar; después se verifica la nueva posición en el espectro. Canales 51 y 52: mapa vacío y aviso visible. Regreso a Time: centro original 60.810995°, 51.340404° y FOV 6′, sin informe antiguo. Ejemplo temporal real de WISE → Spectrum → canal 94: centro conservado 133.760100°, −7.242247°, FOV 6′ y advertencia completa de época/intervalo/posición esperada. Los controles y las magnitudes fueron revisados funcionalmente; no se rediseñó la interfaz.

### Repositorio y entrega local

Cambios preparados para un único commit local de validación sobre `e359426`: motor, correcciones funcionales del visor, 49 pruebas, verificador independiente, informe numérico, README/CONTEXT/STATE y dependencias de desarrollo. Los cuatro commits locales anteriores (`bf9152b`, `65396a3`, `e3410de`, `e359426`) se conservan. **Sin push ni despliegue.** El hash del commit de esta validación se consulta con `git log -1 --oneline` (este documento está contenido en él).

### Límites y siguiente resultado técnico

El resultado sigue siendo exploratorio, sin incertidumbres ni corrección de apertura. La validación numérica independiente está concentrada en el campo oficial: siguiente prioridad técnica, ampliar a **2–3 posiciones, fuentes compactas y cruces de teselas**, medir la sensibilidad a apertura/fondo y comprobar presupuesto de memoria en el FOV/apertura máximos. No confundir esas futuras comprobaciones con espectrofotometría calibrada. El refinamiento visual general, multibanda avanzada y publicación siguen fuera del alcance.

## Historial anterior a esta validación

## Auditoría independiente de `d62b945` (PASS_WITH_CORRECTIONS) — correcciones
| Hallazgo | Estado | Causa | Corrección | Prueba |
|---|---|---|---|---|
| **SC-01** movimiento propio (alta) | corregido | posiciones fijas para todas las fechas; las coordenadas del enunciado de WISE 0855 se trataban como J2000 | nuevo `skyclues/astrometry.py`: `Astrometry.position_at(fecha)` con `SkyCoord.apply_space_motion` (movimiento propio, distancia del paralaje, velocidad radial) más paralaje geocéntrico; SIMBAD TAP (CDS y, si falla, el espejo de Harvard) para nombres, con aviso si solo hay posición (Sesame). `find_sequence(astrometry=…)` centra el campo en la posición calculada para la época mediana de las observaciones (redondeada a 0.1 años) y cada época recibe su posición (`Frame.expected_radec`); λ del objetivo se lee ahí. Marcadores: «+» posición calculada por época, «×» posición de catálogo, leyenda «es un cálculo, no una detección». Los informes guardan la astrometría | `test_audit_offline` (época 2010.40 de las coordenadas del enunciado, 211.7″/270.4″/121.6″ de J2000 a 2026.0, paralaje 0.44″, avisos, centrado), `test_audit_live`, `test_app` |
| **SC-02** rechazo espectral (media) | corregido | S4 y C4 nunca daban «fail» | S3/S4/C3/C4: ≤ 0.25 BW cumple, ≤ 0.50 aviso, > 0.50 **no cumple** (umbrales sin cambios); NaN no cumple | desajustes deliberados en memoria sobre FITS reales: 0.40 → aviso; 0.65 y 15.43 → rechazo; D3+D6 (≈50 BW) → rechazo |
| **SC-11** FINAST (baja) | corregido | FINAST ≥ 2 solo avisaba | FINAST 0 cumple, 1 aviso (solución parcial), ≥ 2 o ausente no cumple. Columna «verificación»: S6/S7/C6/C7 son «garantía del archivo» (IRSA solo publica L2DQA = PASS y FINAST = 0, suplemento §3.2.12); el resto «efectiva» | `test_finast_is_enforced` (0/1/2/5), `finast_status` |
| **SC-06** FLAGS (baja) | corregido | las cabeceras reales definen hasta el bit 28: SATELLITE_HALO (29) se contaba como válido; los bits sin definir nunca se enmascaraban | se fusionan cabecera (prioritaria; conflictos registrados) y documentación; un bit activo sin definición se enmascara como artefacto y aparece en el censo como `UNDEFINED_BIT_n` | bits 29, 30, 31 y 3 sintéticos; cabeceras reales con bit 29 añadido. En los 91 FITS de la caché no hay bits 29 ni sin definir activos: **no cambia ningún resultado** |
| **SC-03** reintentos HTTP (media) | corregido | 400/404 se reintentaban 6 veces; 502 en `/SIA/capabilities` no; esperas de hasta 195 s, también tras el último intento; WCS-WAVE solo reintentaba 503; todo se mostraba como «IRSA ocupado» | `archive.http_get` y `_with_retries`: solo se reintentan tiempo agotado, error de conexión, 408/425/429 y 5xx; 4 intentos, esperas 4-8-16 s (máx. 30 s, respetando `Retry-After`), ninguna tras el último, límite total de 240 s; tiempo de espera (15 s, 90 s). El constructor SIA2 está dentro de los reintentos. Errores `ArchiveTransientError` / `ArchivePermanentError` / `CorruptFitsError` con mensajes distintos en la app | 502/503/404/400/401/403/410, timeouts, `Retry-After`, límite total, SIA2 502→OK y 400 permanente; app con error transitorio y permanente |
| **SC-04** FITS truncado (media) | corregido | bastaba con que empezara por `SIMPLE`; un archivo truncado se guardaba y se reutilizaba | `validate_fits_bytes`: longitud múltiplo de 2880, lectura sin avisos de truncado, tamaño igual al declarado por las cabeceras, extensiones IMAGE, FLAGS, VARIANCE, ZODI y WCS-WAVE. Nada incompleto entra en la caché; un archivo de caché dañado se aparta (`*.corrupt-…`, no se borra) y se descarga de nuevo; un archivo de `data/reference` nunca se modifica (error). SHA-256 distinto del informe en la caché → se aparta y se descarga una vez | truncados sintéticos y reales (1.33 MB, alineado a bloque, último bloque), descarga parcial reintentada, caché dañada, referencia dañada intacta, `redownload` |
| **SC-05** descargas parciales (media-baja) | corregido | `retrieval_failures` no se mostraba | el informe lleva `retrieval` (`n_requested`, `n_failed`, `complete`, `n_transient`) y cada fallo su tipo; la app avisa «Descarga incompleta: N de M…» y lista los recortes | `test_failed_cutouts_are_counted_and_classified`, `test_partial_download_is_reported` |
| **SC-08** coordenadas (baja) | corregido | `?ra=nan` llegaba a la consulta; `?ra=400&dec=-95` se acotaba en silencio | `targets.validate_coordinates` / `validate_fov_deg`: error claro, sin acotar, antes de cualquier consulta (app y `find_sequence`); RA < 360° en el formulario | 10 entradas no válidas, bordes válidos, `find_sequence` sin consulta, app con 4 URL no válidas |
| **SC-07** teclado (baja) | corregido | el atajo global actuaba además del control enfocado (deslizador + flecha = 2 pasos; velocidad + flecha = cambio y paso; Repetir + espacio = reproducción) | función pura `shortcutAction`: con el foco en un control (input, select, botón, editable) o con modificadores, la tecla solo hace lo nativo | Node (13 casos) y navegador real (deslizador, velocidad y Repetir no avanzan ni reproducen; en la página, flecha y espacio sí) |
| **SC-10** precisión (baja) | corregido | «geometría exacta» exageraba: en pantalla se redondea al píxel de pantalla | etiquetas «geometría WCS … sin remuestreo de valores»; cada fotograma indica la escala de pantalla (p. ej. ≈0.9″/px a 6′) y la leyenda separa WCS, pantalla, instrumento (píxel 6.15″, PSF del encabezado) y remuestreo. Sin procesamiento añadido | `test_screen_scale_is_reported`; navegador |
| **SC-09** ejemplos sin red (media) | corregido | los ejemplos dependían de IRSA; `data/reference` no existía | `bundle_reference.py` comprueba estructura y SHA-256, no sobrescribe nunca y escribe `data/reference/MANIFEST.json` (procedencia, URL, archivo Level-2, liberación, DOI). 6 FITS, 24.0 MB, en un commit local **separado** | `test_examples_offline`: con la red bloqueada y la caché vacía, los dos ejemplos se abren desde `data/reference` con SHA-256 = informe = manifiesto |

## Corrección puntual: SIA2 sin `/SIA/capabilities` (14-11-2026)
- **Problema demostrado:** una búsqueda real falló tras 4 intentos con `ArchiveTransientError: SIA2 capabilities` (HTTP 502 Proxy Error en `https://irsa.ipac.caltech.edu/SIA/capabilities`): el constructor de `pyvo.dal.SIA2Service` consulta capabilities y ese fallo bloqueaba la búsqueda.
- **Corrección (`archive.sia2_service`):** un solo intento por capabilities; si falla, se usa directamente el endpoint de consulta documentado `https://irsa.ipac.caltech.edu/SIA` con `check_baseurl=False` (sin petición previa). La consulta es idéntica (mismas colecciones, posición y radio) y sigue con los reintentos y la clasificación transitorio/permanente. `archive.last_sia2_route` indica la ruta usada. No cambian criterios, resultados ni descargas FITS.
- **Pruebas:** `test_capabilities_502_but_direct_query_works` (capabilities 502 → ruta directa, sin esperas, consulta idéntica a la ruta normal) y `test_direct_query_failures_keep_their_classification` (502 transitorio reintentado; 502 persistente → `ArchiveTransientError`; 400 → `ArchivePermanentError`). 124 pruebas en verde.
- **Verificación real: NO concluyente.** Durante la corrección, IRSA devolvía 502 Proxy Error tanto en `/SIA/capabilities` como en la consulta directa `/SIA?POS=…&COLLECTION=…` (la portada de IRSA respondía 200): la caída era del servicio SIA, no solo de capabilities. Con IRSA así, la app informa correctamente de indisponibilidad temporal. Queda pendiente comprobar con IRSA operativo que la ruta directa devuelve las mismas filas que la ruta por capabilities (`scratchpad/sia_direct.py` hace esa comparación acotada: 2 consultas por ruta).

## Resultados científicos que cambian
- **WISE 0855:** las coordenadas del enunciado son la posición de la época 2010.40 (a 0.34″ de la trayectoria de SIMBAD), no J2000.0. En las fechas SPHEREx (abril-mayo de 2026) el objeto está a **≈130″ (≈21 px)** de ellas. Los informes antiguos `sequence_wise0855`, `sequence_wise0855_mwir` y `pair_wise0855` siguen siendo admisibles (el objetivo queda dentro del campo de 6′), pero están descentrados: se han anotado (`target.centre.propagated = false`) y reevaluados con `scripts/reevaluate_results.py`, que conserva la evaluación anterior en `previous_evaluation`. λ en el objetivo pasa de 4.8234–4.8261 a 4.8214–4.8250 µm (D6), de 2.1564–2.1585 a 2.1536–2.1569 µm (D3) y de 4.3702 a 4.3688–4.3691 µm (pareja); ningún criterio de las secuencias seleccionadas cambia.
- **Nuevo ejemplo validado de WISE 0855** (`sequence_wise0855_pm`, una búsqueda: 7 recortes, 58 s), centrado en la posición propagada a 2025.9: DR1 D6, **2 épocas**, 05-05-2025 y 09-05-2026 (368.4 d), λ 4.8599/4.8597 µm (0.01 BW), cobertura común 95.1 %, 9/9 cumplen. Posición calculada a 4–5″ del centro; se desplaza **8.2″ (≈1.3 px)** entre las dos épocas. La opción de 3 épocas se descartó por S9 (saturación 0.11 %, aviso). Sustituye a `sequence_wise0855_mwir` como acceso rápido; este último sigue entre los resultados guardados.
- **SC-02 en opciones guardadas:** 5 opciones no seleccionadas de los informes de WISE con dispersión 0.51–0.53 BW pasan de aviso a **no cumple** (`status_after_audit`). Las secuencias seleccionadas no cambian (dispersión ≤ 0.24 BW).
- **M101:** sin cambios (4 épocas, 9/9; galaxia sin movimiento propio).
- SC-06 y SC-11 no cambian ningún resultado actual (ningún bit 29 o sin definir activo; FINAST = 0 en todos los FITS).

## Terminado y verificado
| Componente | Verificación |
|---|---|
| Entorno: Python 3.11 en `.venv`; `requirements.txt` (solo runtime, versiones fijadas) y `requirements-dev.txt` (pytest) | instalado y en uso |
| Consulta SIA2 a `spherex_dr1` y `spherex_qr3`, con caché JSON de 12 h; reintentos solo de errores transitorios | pruebas reales y simuladas |
| Recortes IBE: integridad FITS antes de guardar, caché intacta con SHA-256, escritura atómica, una descarga por URL, 3 en paralelo, `data/reference/` de solo lectura y prioritario | pruebas unitarias y reales |
| Lectura MEF con WCS celeste y espectral; FLAGS de MSKN + documentación oficial; bits sin definir enmascarados | pruebas reales y sintéticas |
| Astrometría por época (SIMBAD + Astropy), búsqueda centrada y marcadores por época | pruebas y navegador |
| Estimación de λ sin descargar (homografía `s_region` + WCS-WAVE) | λ estimada = λ del FITS |
| Parejas (C1–C9) y secuencias de N épocas (S1–S9 globales) con rechazo espectral y FINAST efectivos; regla de selección sin cambios | pruebas |
| Geometría WCS (por defecto): píxeles nativos en su posición WCS, sin remuestreo de valores; rejilla común (vecino más próximo) para las métricas, etiquetada «REMUESTREADO» | pruebas reales |
| HALO: siempre enmascarado en las métricas; modo exploratorio en cobre. SATELLITE_HALO siempre enmascarado | pruebas |
| FOV de 3′–30′ (3′, 6′, 12′, 18′ u otro); valores de URL no válidos se rechazan con un mensaje | AppTest y búsquedas reales |
| Búsqueda con progreso; mensajes distintos para fallos transitorios, permanentes y FITS dañados; aviso de descarga incompleta | AppTest |
| Dibujo seguro con varias sesiones (`render.RENDER_LOCK`, `Figure`) | prueba de 4 hilos |
| Reproductor: reproducción, pausa, velocidad, repetición, paso, deslizador, blink y teclado que respeta el control enfocado | Node y navegador real |

## Medidas anteriores (datos reales, siguen vigentes)
- Vecino más próximo en `sequence_m101`: hasta 0.70 px (≈4.3″) en la rejilla común; la geometría WCS lo elimina (< 0.01″).
- HALO solo: 0.4–1.4 % del campo por época en M101.
- FOV 18′ (M101, D2): 113 s, 2 épocas, 93.5 %. FOV 30′ (WISE, D5–D6): 148 s, pico 206 MB. Servidor: 224 MB (pico 264 MB).

## Secuencias de referencia (informes en `results/`)
| Campo | Épocas | Fechas (UTC) | λ en el objetivo | Cobertura común | Criterios | Centro |
|---|---|---|---|---|---|---|
| M101 (`sequence_m101`), QR3 D2 — **ejemplo validado** | 4 | 17-05, 22-05, 19-06 y 22-06-2026 (36.4 d) | 1.4151–1.4206 µm | 94.0 % | 9/9 | catálogo |
| WISE 0855 (`sequence_wise0855_pm`), DR1 D6 — **ejemplo validado** | 2 | 05-05-2025 y 09-05-2026 (368.4 d) | 4.8597–4.8599 µm | 95.1 % | 9/9 | posición propagada (2025.9) |
| WISE 0855 (`sequence_wise0855_mwir`), DR1 D6 | 3 | 26-04, 30-04 y 08-05-2026 (12.9 d) | 4.8214–4.8250 µm | 88.0 % | 9/9 | enunciado (2010.4): objetivo a ≈130″ |
| WISE 0855 (`sequence_wise0855`), DR1 D3 | 3 | las mismas | 2.1536–2.1569 µm | 86.8 % | 9/9 | enunciado (2010.4): objetivo a ≈130″ |

## Pruebas
```
.venv\Scripts\python -m pytest -q                 # 123 passed, 14-11-2026 (59 anteriores + 64 nuevas)
.venv\Scripts\python -m pytest -m "not network"   # 65 sin red (incluye Node y la apertura de ejemplos sin red)
```
Nuevas: `tests/test_audit_offline.py` (39), `tests/test_audit_live.py` (15, FITS reales modificados solo en memoria; SHA-256 comprobado al final), `tests/test_examples_offline.py` (2), `test_app.py` (+7: fallo transitorio/permanente, 4 URL no válidas, descarga incompleta, objetivo en movimiento) y `test_sequence_offline.py` (+1, teclado con Node). Pruebas existentes ajustadas sin relajar su intención: la fuente de las definiciones de FLAGS ahora es «cabecera + documentación (bit 29)»; los dos simuladores de descarga usan un FITS sintético completo (los bytes «SIMPLE…» ya se rechazan, como debe ser); el mensaje de fallo de IRSA depende del tipo de error; el ejemplo de WISE tiene 2 épocas.
Navegador real (servidor reiniciado): URL `?ra=400&dec=-95` → error claro sin consulta; ejemplo WISE con nota «Objetivo en movimiento… calculada… no es una detección», leyenda con «CALCULADA» y escala de pantalla 0.9″/px; teclado según SC-07.

## Despliegue en Streamlit Community Cloud (preparado; **no desplegado**)
- `app.py` en la raíz; `requirements.txt` solo con dependencias de ejecución; `.streamlit/config.toml`. No hacen falta `packages.txt` ni secretos. Python recomendado: 3.11.
- Con `data/reference/` en el repositorio, los dos ejemplos se abren sin IRSA. El disco de la nube no es persistente: las búsquedas nuevas vuelven a descargar.
- La resolución por nombre usa SIMBAD (salida HTTPS a `simbad.cds.unistra.fr` o `simbad.harvard.edu`).

## Decisiones pendientes (usuario)
1. **¿Publicar los FITS de los ejemplos?** Están en un commit local separado («Datos de referencia…», 6 FITS, 24 MB, idénticos a IRSA, con `MANIFEST.json`). No se ha hecho push. Si no se quieren en el historial, basta con descartar ese commit antes del push (`git reset --hard HEAD~1` si es el último; el código funciona sin ellos descargando de IRSA).
2. Autorización para hacer push de estos commits y para desplegar.

## API para Codex (`skyclues.sequence`, `skyclues.player`, `skyclues.targets`)
```python
from skyclues.targets import resolve_name, PRESETS, validate_coordinates
astro, warnings = resolve_name("WISE 0855-0714")         # SIMBAD; Astrometry + avisos
seq, report = find_sequence(ra, dec, field_deg=0.1, astrometry=astro,   # centra en la posición propagada
                            progress=lambda stage, frac, msg: ...)
seq = load_sequence("results/sequence_wise0855_pm.json")   # recupera la astrometría del informe
seq.target_position(i)       # posición CALCULADA del objetivo en la fecha de la época i (no es una detección)
seq.target_moves             # True si hay movimiento propio
report["retrieval"]          # n_requested, n_failed, complete, n_transient
html = player.build_player(seq, geometry="exact" | "nearest", show_halo=False)
player.screen_scale_arcsec(seq), player.precision_note(seq)
```
Reglas nuevas: no presentar nunca `target_position` como detección; mostrar `report["retrieval"]` si `complete` es falso; los errores de `archive` se distinguen por clase (`ArchiveTransientError`, `ArchivePermanentError`, `CorruptFitsError`), no por el texto; las coordenadas y el FOV se validan con `targets.validate_*` (no se acotan en silencio); los atajos de teclado usan `shortcutAction`. Siguen vigentes: una única `sequence_norm`, `MASK_COLOR` para NaN, «nearest» etiquetado como remuestreado, HALO solo en modo exploratorio, figuras `Figure` con `@render.serialized`.

## Problemas abiertos
1. No hay vista con el norte arriba: los ejes son los del detector de la época 1.
2. La λ por píxel tiene precisión de visualización (WCS-WAVE); CWAVE/CBAND no están implementados.
3. RW Aur, R Dra, Barnard y ε Ind B no se han ejecutado en SPHEREx (la propagación ya está probada con sus datos de SIMBAD).
4. `find_pair` (camino antiguo de parejas, solo CLI) no centra por movimiento propio; la app usa siempre secuencias. `evaluate_pair` sí acepta `astrometry`.
5. El extremo TAP de SIMBAD en CDS (`simbad.cds.unistra.fr/simbad/sim-tap`) devolvió 404 el 14-11-2026; se usa el espejo de Harvard automáticamente. Sin SIMBAD, la búsqueda por nombre usa Sesame sin movimiento propio y lo avisa.
6. No se aplica aberración: se asume que el WCS de SPHEREx está ajustado a posiciones astrométricas (catálogo). Efecto en todo caso común a todo el campo.
7. Con 8 épocas y un FOV de 30′, el HTML del reproductor rondaría los 2.4 MB.
8. Streamlit no recarga `skyclues/`: hay que reiniciar el servidor tras editarlo.
9. No se ha probado con Python 3.12 (sí con 3.11 y en una instalación limpia con 3.14, antes de esta auditoría).

## Commits locales de esta sesión (sin push)
1. «Corrección de la auditoría independiente (SC-01 a SC-11)»: código, pruebas, informes reevaluados, nuevo ejemplo de WISE 0855, STATE y CONTEXT.
2. «Datos de referencia de los ejemplos validados (data/reference)»: 6 FITS + `MANIFEST.json` (separado para poder descartarlo).
3. Posteriores (14-11-2026): referencias Gaia/WISE, correcciones de auditoría y SIA2, y la integración `bee8fa8` + `47e7bd7` (fusiones `cb0354b`, `d836b82`, corrección `a2a6881` y documentación). Ninguno publicado.

## Siguiente tarea prioritaria
- **Usuario:** decisiones pendientes 1 y 2.
- **Claude A:** ejecutar Barnard y ε Ind B con la búsqueda por nombre (posición propagada) y documentar si el desplazamiento es visible entre épocas; objetos variables (RW Aur, R Dra).
- **Codex:** refinamiento visual y accesibilidad, respetando las reglas nuevas de la API.
- **Claude B:** Spectrum Explorer (ver CONTEXT).

## Relevo Spectrum Explorer (Claude B → Codex, 14-11-2026; trabajo interrumpido por límite de uso)

### Implementado (sin pruebas automáticas propias todavía)
- `skyclues/spectral_cube.py`: motor del cubo SPHEREx DR1 All-Sky (doi:10.26131/IRSA679), teselas HiPS orden 5 en `CUBE_DATA_URL` (config.py). Lectura por **rangos HTTP** (FITS sin comprimir): máx. 64 rangos/petición (con ~100+ IRSA devuelve el archivo entero, 320 MB); una respuesta 200 nunca se lee (`RangeNotHonoured`); se verifican Content-Range, tamaño y ETag (`FileChangedError`). Caché verbatim de rangos en `data/cache/cube/` (tope 200 MB) y de cabeceras en `data/cache/meta/cube_o5_<ipix>.json` (12 h). HEALPix NESTED en numpy (`healpix_nest`, verificado: tutorial (60.8109955, 51.3404038) → tesela 445) y comprobado contra NPIX/WCS de cada tesela. Canal n = plano n−1 = 17·(det−1)+sub; canales 51 y 52 (BLANKCH D3:17, D4:01) sin datos, nunca interpolados. λ desde la tabla SPECTRAL_CHANNELS del FITS. Espectro exploratorio = método del tutorial oficial (apertura circular con 5×5 subpíxeles, anillo con sigma_clipped_stats 3σ/10 it., flujo mJy = neto × Ω × 1e9, Ω = 3.9011e-9 sr); sin valor si hay NaN en la apertura o fondo < max(10, 50 %) de píxeles. También brillo del píxel (MJy/sr). Sin incertidumbres inventadas. Propagación de movimiento propio a la época media de la tesela (`cube_epoch_position`).
- `skyclues/spectral_view.py`: mapa de canal en geometría exacta (pcolormesh de cada píxel nativo, sin remuestreo), gráfico Altair interactivo (clic = posición del espectro), gráfico del espectro (puntos por canal, barras = ancho de banda, marcas rosas = canales sin valor, huecos = OVERFLOW/OUTLIER), barra de color.
- `skyclues/spectrum_page.py`: página Streamlit (región compartida con Time Explorer, RA/Dec, campos predefinidos, SIMBAD; selector de canal; capas IMAGE/NHITS; apertura configurable; CSV con procedencia; procedencia y limitaciones; enlace a la herramienta oficial de espectrofotometría de IRSA, que no tiene API).
- `app.py`: selector de explorador en la barra lateral, botón «Ver esta región en Spectrum Explorer», `shared_region` en session_state, query params `explorer=espectral&canal=`.
- `config.py`: bloque de constantes del cubo.

### Verificado en vivo (IRSA, 14-11-2026)
- Posición del tutorial: pico PAH en el canal 63 (3.293 µm), 355 mJy frente a 45–61 mJy en los vecinos; canales 51/52 con estado «blank».
- Recursos: cabecera ≈ 80 KB/4 peticiones; mapa de canal de 6′ ≈ 283 KB; espectro ≈ 6.7 MB/6 peticiones; pico tracemalloc ≈ 28 MB.
- Navegador (puerto 8502): mapa, clic → espectro, canal 51 con aviso, traspaso Time → Spectrum con WISE 0855 (posición propagada a 2025-11-08, 8.3″), canal 94 (4.704 µm). Sin errores en consola ni servidor.
- AppTest sin interfaz: canal 51 avisa y los query params se actualizan.
- Estado de IRSA: SIA2 `/SIA/capabilities` seguía en 502; HiPS e IBE (rangos) funcionaban.
- `pytest -m "not network"`: 66 passed (Time Explorer intacto).
- Último cambio sin verificar en navegador: ticks de la barra de color equiespaciados en el espacio estirado (`colorbar_png`), porque con asinh se solapaban.

### Pendiente (en este orden)
1. `tests/test_spectral_offline.py`: cubo sintético pequeño servido por un lector de rangos falso (monkeypatch de `spectral_cube._request_ranges` o `requests`). Cubrir: lectura de cabeceras, fórmula de canal, canales en blanco → NaN y estado «blank», guarda de 200 (el cuerpo no se lee), cambio de ETag, reintentos solo transitorios, parseo multipart, apertura que recupera un flujo inyectado conocido en mJy, NaN en la apertura → sin valor, `healpix_nest` = 445, Ω = ángulo sólido local del WCS. Fixture `tmp_store` de `tests/conftest.py` para aislar la caché.
2. `tests/test_spectral_live.py` (marcar `network`; pocas peticiones): λ de SPECTRAL_CHANNELS = `data_cube_crval3_arr` de HiPS properties; planos 50/51 todo NaN con NHITS 0; NaN ⇔ NHITS = 0; NPIX = `healpix_nest` en varias posiciones (incl. polos); campo estable entre canales; espectro PAH; bytes/memoria.
3. `tests/test_app.py`: AppTest de Spectrum Explorer por query params, aviso del canal 51, botón de traspaso Time → Spectrum y mensajes de fallo de IRSA (monkeypatch).
4. Actualizar PROJECT_CONTEXT.md (Spectrum Explorer implementado; decisiones estables: lectura por rangos, límite de 64, nunca leer un 200) y README breve.
5. Commit local. Sin push, sin despliegue.

### Siguiente prioridad después de lo anterior (no iniciada)
- Validación cruzada del espectro exploratorio con photutils o con la herramienta oficial de IRSA en 2–3 posiciones.
