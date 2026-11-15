# SkyClues — continuidad del rediseño y validación

Fecha local: 14 de noviembre de 2026. Trabajo sobre `redesign/unified-region`, recibido limpio en `6acf0e8` (rediseño unificado de Claude B). Se confirmó acceso local a archivos, Git, Python 3.11, pruebas y navegador. Se conserva la aplicación existente y su identidad visual. No se hizo push, despliegue ni publicación.

## Recuperación y estado recibido

- Existe `C:\Users\danie\Backups\SKYCLUES_BACKUP_PRE_REDESIGN_20261114`. Se consultaron su manifiesto SHA-256 y `VERIFICATION.json`: 51.425 archivos en tres árboles, sin diferencias en la verificación histórica. Se verificó su bundle con `git bundle verify`. No se volvió a calcular el hash de los 3,13 GB ni se modificó el respaldo.
- Punto de recuperación adicional: `data/recovery/pre-continuity-6acf0e8.bundle`, verificado. Se conservaron además instantáneas locales antes de la integración Gaia. `data/recovery/` queda fuera de Git.
- La primera ejecución sobre el rediseño recibido dio **276 pruebas correctas y 46 fallos**. Se adaptaron las pruebas de interfaz a la región única y a los controles actuales; no se eliminaron las comprobaciones científicas para ocultar fallos.
- Los otros árboles de trabajo no se modificaron. El trabajo continúa en la misma rama del rediseño.

## Búsqueda universal

Se mantiene una sola entrada por nombre. Messier se resuelve dinámicamente mediante SIMBAD: M1–M110, con normalización de `M001`, `M 1` y `Messier 1`. M102 se presenta como identificación ambigua, con NGC 5866 y M101 como elecciones explícitas. NGC e IC admiten formas con y sin espacio y ceros iniciales. El índice local ofrece sugerencias, no limita la cobertura del buscador.

Para el Sistema Solar se incorporan [Horizons Lookup](https://ssd-api.jpl.nasa.gov/doc/horizons_lookup.html) y [Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html), sin descargar catálogos masivos. Hay alias españoles y designaciones cometarias. Las coincidencias ambiguas requieren elegir identidad. La selección conserva el FOV y actualiza la región compartida.

Las efemérides indican identidad, UTC, observador geocéntrico `500@399`, coordenadas ICRF astrométricas y procedencia. Se puede cambiar la fecha. No se presentan como posiciones observadas desde SPHEREx. Tiempo y Espectro trabajan sobre el campo fijo, sin seguimiento orbital. SkyBoT no se añadió: el alcance implementado es identificación por nombre y no búsqueda de cuerpos menores por región/fecha.

### 3I/ATLAS

Se verificaron tanto `3I/ATLAS` como `C/2025 N1 (ATLAS)`. La [tabla oficial de IRSA](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html) consultada contiene **259 exposiciones**, colección `spherex_qr2`, MJD 60888.33344–61024.00074. La interfaz permite elegir una exposición, abrir su DataLink y centrar el Atlas en su predicción `comet_ra/comet_dec`, conservando la fecha de la exposición y la procedencia.

Esta integración es de metadatos y posiciones históricas. El motor actual de secuencias DR1/QR3 no se amplió a QR2; no se transforma la tabla en una detección ni se atribuye al cometa un espectro del cubo combinado. La documentación oficial advierte señal/ruido baja en muchas longitudes de onda.

## Constelaciones

Las 88 constelaciones se integran en las capas del Atlas existente mediante las primitivas nativas de Aladin Lite. Hay 89 figuras porque Serpens tiene dos partes. Coordenadas J2000, nombres y procedencia están en `data/constellations.json`, con licencia BSD de [D3-Celestial / Olaf Frohn](https://github.com/ofrohn/d3-celestial).

Son figuras tradicionales, **no límites oficiales IAU**. Se ocultan por debajo de 3° de vista. «Orientación» abre una vista de 60° sin modificar el círculo científico ni el FOV; «Encuadrar» vuelve al campo. Se comprobaron visualmente Orión, Andrómeda, Escorpio, Cruz del Sur y Osa Mayor; también zoom y cambio de ventana a 800 × 800 y vuelta al tamaño original.

## Selección Gaia DR3 y carga del Atlas

- Clic en un marcador azul: selecciona el registro recuperado, conserva `source_id` como texto de 64 bits, coloca `Gaia DR3 <source_id>` en el buscador, actualiza RA/Dec y centra el mapa. No se resuelve el nombre ni se consulta Gaia por cada marcador.
- Si varios marcadores coinciden, se elige el más próximo al clic entre los objetos señalados por Aladin. El clic general del mapa no sobrescribe después las coordenadas exactas de la fuente.
- El identificador y la astrometría persisten al pasar a Tiempo/Espectro. El FOV se conserva, incluido un cambio reciente aún pendiente del debounce.
- El alias opcional se obtiene solo para la fuente seleccionada, mediante coincidencia exacta del identificador Gaia en SIMBAD. No sustituye el identificador ni la astrometría Gaia; una caída de SIMBAD no impide seleccionar.
- Se distinguen catálogo ICRS J2016.0, posición calculada para fechas de exploradores y observaciones SPHEREx. La interfaz dice explícitamente que seleccionar una fuente no demuestra su detección por SPHEREx.
- Gaia se consulta en segundo plano con trabajadores y cola acotados, caché TTL y sondeo mediante un fragmento Streamlit. El indicador indeterminado está dentro del Atlas; el mapa mantiene zoom y arrastre. Desaparece al llegar el resultado, informa de campo vacío y ofrece «Reintentar» solo tras error.
- La respuesta pertenece a una región concreta: un cambio local oculta resultados antiguos incluso antes de que el movimiento llegue al servidor. Las respuestas de caché no añaden una espera artificial.

**Comprobación real:** se cargaron automáticamente 76 fuentes en el campo RA 323.201930°, Dec −21.785755°, FOV 6′. Se pulsó `Gaia DR3 6828226663169972736`: RA **323.1753958943283°**, Dec **−21.789512486045215°**, J2016.0. Buscador y campos mostraron esa fuente y el FOV permaneció en **6′**. Se verificó el alias SIMBAD `WISE J213242.07-214721.8`. La identidad se conservó en Espectro, Tiempo y al regresar a Región. Espectro cargó imagen y gráfico; se comprobó la actividad durante la búsqueda temporal, sin afirmar que esa fuente tuviera una secuencia detectada.

Evidencia: `results/gaia_selection_verification.json`, `results/gaia-selection.jpg` y `results/loading-verification.jpg`.

## Controles y esperas

El reproductor conserva su lógica y sus imágenes, con controles en IBM Plex, negro, blanco, grises y acento terracota de la página. Botones de transporte en una fila, Blink sin caja pesada, tabla de épocas legible y desplazamiento horizontal acotado. Se verificaron reproducir, pausa y Blink sobre la secuencia real M101 de cuatro épocas. Captura: `results/player-controls.jpg`.

Las operaciones largas muestran actividad y tiempo transcurrido: resolución por nombre, inicio del Atlas, Gaia, búsqueda temporal, descarga/verificación de FITS, preparación de fotogramas, investigación de movimiento, lectura de cabeceras y canales, espectro, RGB, referencias y consultas de fecha/exposiciones del Sistema Solar. Las fases temporales se actualizan con mensajes del proceso. Se eliminó la barra global de porcentajes ponderados; solo se mantiene progreso cuantificado cuando hay un número real de archivos terminados sobre el total. Las operaciones rápidas de caché no tienen demora añadida.

## Espectro, RGB y ciencia preservada

El selector visible «Imagen infrarroja» alterna Un canal / Composición multibanda (RGB), conservando región, canal, posición y parámetros. RGB sigue siendo falso color de canales infrarrojos reales, con asignación de longitudes de onda y normalización originales.

Monocanal: rosa/morado significa valor no finito o NHITS = 0. RGB: rosa/morado **con rayado blanco** indica falta de dato utilizable en al menos una banda; un tono morado sin rayado puede ser un color válido. Negro puede ser señal válida débil. No se rellenan píxeles ni se modifican máscaras.

No se alteraron `motion.py`, `sequence.py`, `spectral_cube.py`, `multiband.py`, `astrometry.py` ni los FITS de referencia. La lógica JavaScript del reproductor no cambió. Las pruebas científicas conservan la comprobación de ePSF, desplazamientos sintéticos, controles estacionarios, errores, valores oficiales del cubo, canales ausentes, alineación, máscaras y SHA-256 de FITS originales.

Otros defectos corregidos: retorno temprano ante parámetros espectrales inválidos; referencias accesibles aunque no exista una secuencia admisible; cancelación de animaciones obsoletas al editar RA/Dec rápidamente; un campo de coordenadas sin cambios ya no bloquea el inicio de un arrastre al perder el foco.

## Validación ejecutada

- Pruebas completas: resultado final en `data/recovery/continuity-clean.txt`.
- Pruebas Gaia controladas: consulta lenta, respuesta vacía, timeout, reintento, cambio de región durante carga, caché, identificadores contiguos de 19 dígitos y persistencia entre exploradores. Se ejecuta el componente JS real con dobles de DOM/Aladin y eventos; estos casos de fallo no se presentan como caídas provocadas en el servicio público.
- Regresión JS adicional: dos ediciones rápidas de coordenadas no permiten que la animación antigua restaure el centro anterior; perder foco sin cambiar el valor no inicia otra animación.
- Servicios reales: M1, M13, M31, M42, M57, M101, M110, M102 ambiguo, NGC 224/891/7000, IC 1396, objeto inexistente; Marte, Júpiter, Europa, Titán, Ceres, Vesta, Plutón, Bennu, Apophis, Halley, 67P y las dos designaciones de 3I/ATLAS. Resultados y procedencia en `results/continuity_services.json`; script reproducible `scripts/verify_continuity_services.py`.
- Navegador: región única, nombres, Gaia, coordenadas/FOV, constelaciones, Tiempo con secuencia real, Espectro con imagen/gráfico y actividad visible durante consultas. Las verificaciones automatizadas cubren también persistencia monocanal/RGB y errores sin imagen.
- `compileall` y `git diff --check` ejecutados.

## Uso y límites

Servidor local actualizado de verificación: `http://127.0.0.1:8508`, ejecutado desde este mismo árbol de trabajo. No es una segunda aplicación ni un despliegue. El servidor anterior del usuario no se detuvo.

Gaia está limitado a 500 fuentes por campo, con aviso de truncado. Los nombres adicionales dependen de que SIMBAD tenga equivalencia exacta. Los enlaces compartidos conservan región, no identidad ni efeméride completa. Los mapas de contexto siguen dependiendo de WebGL2, Aladin e IRSA. Las nuevas funciones no demuestran detecciones SPHEREx por sí solas.
