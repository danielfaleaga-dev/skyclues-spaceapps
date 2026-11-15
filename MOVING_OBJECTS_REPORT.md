# Objetos móviles conocidos en Time Explorer

Actividad `SKYCLUES_3I_ATLAS_TEMPORAL_VALIDATION_AND_INTEGRATION_01`, ampliada por el usuario a un motor universal. Trabajo local, sin push ni despliegue. Base de recuperación: commit `2cb02af`.

## Relevo de Claude Code B (15-11-2026): movimiento medido

Actividad `SKYCLUES_NONSIDEREAL_CODEX_RECOVERY_02`. El trabajo de Codex estaba preparado en el índice pero sin confirmar; se preservó intacto en el commit `819d242` antes de tocar nada. Esta sección **sustituye** las afirmaciones posteriores de que «no se ha demostrado movimiento observado»: se conservan debajo como historial de la primera validación.

**Resultado:** el movimiento de 3I/ATLAS se mide en las observaciones auténticas de SPHEREx recuperadas con MOST, en agosto y en diciembre de 2025, y el mismo código lo mide en Plutón y en el asteroide 3 Juno. Ningún paso contiene condiciones por nombre de objeto.

| Caso (informe en `results/moving/`) | Fechas UTC | Detector · λ (µm) | Posiciones medidas | Desplazamiento | Intervalo | Ritmo | Significación | Estrellas de control | Medido − previsto |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| 3I/ATLAS `atlas_aug_motion_d1` | 2025-08-09 08:25 → 10:04 | D1 · 0,96–1,11 | 7 de 7 | 165,8″ ± 2,7″ | 99 min | 100,3″/h | 61,5σ | 16 (≤ 0,67″) | 2,0″ |
| 3I/ATLAS `atlas_aug_motion_co2` | 2025-08-08 12:49 → 14:35 | D5 · 4,13–4,39 | 2 de 7 | 156,1″ ± 4,4″ | 95 min | 98,9″/h | 35,1σ | 16 (≤ 0,93″) | 0,8″ |
| 3I/ATLAS `atlas_dec_motion_d2` | 2025-12-14 04:27 → 06:08 | D2 · 1,22–1,44 | 8 de 8 | 293,9″ ± 4,4″ | 101 min | 174,8″/h | 67,1σ | 15 (≤ 0,56″) | 1,7″ |
| 3I/ATLAS `atlas_dec_motion_co2` | 2025-12-14 04:27 → 06:08 | D5 · 3,97–4,21 | 8 de 8 | 293,9″ ± 4,4″ | 101 min | 174,8″/h | 67,1σ | 6 (≤ 0,53″) | 1,0″ |
| Plutón `pluto_motion` | 2025-10-06 → 10-12 | D1 · 0,76–1,08 | 8 de 8 | 50,2″ ± 4,9″ | 148,3 h | 0,34″/h | 10,2σ | 16 (≤ 2,31″) | 0,2″ |
| Plutón `pluto_motion_d3` | 2025-09-25 → 10-07 | D3 · 1,64–2,31 | 6 de 8 | 247,0″ ± 4,4″ | 265,7 h | 0,93″/h | 55,7σ | 16 (≤ 0,87″) | 1,6″ |
| 3 Juno `juno_motion` | 2025-07-13 02:37 → 07-14 03:02 | D1 · 0,75–0,96 | 7 de 8 | 214,8″ ± 8,7″ | 24,4 h | 8,8″/h | 24,6σ | 16 (≤ 0,55″) | 0,2″ |
| 3I/ATLAS `atlas_aug_motion_d2` | 2025-08-08 12:49 → 14:37 | D2 · 1,36–1,64 | 2 de 8 | — | — | — | — | — | **No demostrado:** las dos posiciones medidas están a menos de tres píxeles. |
| 4 Vesta `vesta_motion`, `vesta_motion_d2` | 2025-07-08 y 2025-06-28/29 | D1 y D2 | 0 | — | — | — | — | — | **No evaluable:** núcleo saturado con desbordamiento; el ajuste con las alas no es fiable (χ² reducido 300–1400). |
| Control M101 `stationary_m101` | 2026-05/06 | D2 | 4 de 4 | — | — | — | — | — | **Sin movimiento:** misma posición en todas las fechas. |
| Control: predicciones desplazadas (6 ensayos sobre las mismas imágenes de agosto) | — | D1 y D5 | 0–1 | — | — | — | — | — | **Sin movimiento** en los seis. |

«Medido − previsto» compara el desplazamiento medido con el de la efeméride entre las mismas dos exposiciones; se calcula al final y no interviene en la medida ni en la decisión. Los dos detectores de diciembre observaron a la vez: son dos medidas independientes del mismo desplazamiento y coinciden en 0,03″. Los dos conjuntos de Plutón abarcan intervalos distintos alrededor de su punto estacionario, por eso sus ritmos medios difieren.

### Por qué la primera validación no encontró movimiento

1. **El objeto estaba enmascarado.** La cadena oficial marca `OUTLIER` («Pixel flagged by Detect Outliers») las fuentes compactas que no están en su catálogo de referencia (`SOURCE` = «Pixel mapped to a known source»). Un cuerpo en movimiento es exactamente eso. En la imagen D1 del 9 de agosto la fuente tiene S/N ≈ 18 por píxel en la posición prevista, con 4–7 píxeles `OUTLIER` en su núcleo y 0–2 `SOURCE`; la máscara estricta eliminaba el propio cometa y el análisis informaba «Posición prevista». Lo mismo ocurre en diciembre y en Juno.
2. **Se exigía la misma longitud de onda para medir una posición.** Esa condición es necesaria para comparar brillo o apilar, no para astrometría. Como el filtro variable cambia de canal en cada exposición, las únicas parejas «compatibles» estaban separadas por días.
3. **Las parejas elegidas no compartían cielo.** Entre el 9 y el 14 de agosto el cometa recorre 3,36°: no hay estrellas comunes ni forma de comprobar que la fuente no es una estrella. Las mismas tablas de MOST contienen visitas separadas por ~95 minutos en el mismo detector, con el cometa desplazado ~160″ dentro de un mismo recorte de 15′.

### Método añadido (`non_sidereal.py`, versión 1.1)

- **Posición medida en cada exposición** con la ePSF oficial (el mismo ajuste del detector estelar, sin modificarlo), partiendo de la posición prevista y con libertad de hasta 2,5 píxeles. Exige S/N ≥ 8, convergencia y `FINAST = 0`. Error mínimo de 0,3 píxeles (compacta), 0,5 (extensa, χ² > 3) o 1 píxel cuando el núcleo está saturado o enmascarado y se mide con las alas (solo si S/N ≥ 30).
- **Máscara del objeto:** solo en la apertura del objeto se admiten píxeles `OUTLIER`; se cuenta cuántos se usan (`outlier_pixels_in_core`). Fondo, anillos, posiciones de control y estrellas de registro conservan la máscara estricta. No se relaja ninguna otra bandera ni se rellena ningún píxel.
- **Prueba de aparición y desaparición:** en dos exposiciones del mismo detector, la fuente debe estar en su posición y haber desaparecido de esa misma posición del cielo en la otra (menos de la mitad del flujo, a 3σ), en los dos sentidos. Si persiste, se informa posible contaminación estelar. Las posiciones a menos de tres píxeles no se consideran distinguibles de una fuente fija.
- **Registro con estrellas comunes** a ambas imágenes, medidas con el mismo ajuste; se rechaza si su dispersión supera dos píxeles y se exigen al menos cuatro.
- **Decisión «Movimiento observado»:** desplazamiento ≥ 5σ, mayor que tres veces la dispersión de las estrellas de control y de al menos dos píxeles nativos. La afirmación nunca descansa en precisión subpíxel.
- **Selección universal** (`moving_sources.motion_groups`): exposiciones del mismo detector cuyas posiciones previstas distan entre 20″ y 0,35 veces el contexto descargado (5,25′), con el objeto a más de 12 píxeles del borde; se ordenan por detector (PSF más estrecha primero), número de imágenes y separación. Encuentra 6 conjuntos para 3I/ATLAS en agosto, 10 en diciembre, 20 para Plutón, 16 para Vesta y 24 para Juno.
- La predicción solo sitúa la búsqueda y elige qué exposiciones leer. Tres desplazamientos deliberados de la predicción (90″ N, 120″ O, 75″ E/75″ S) sobre las mismas imágenes de agosto no producen movimiento observado en ninguno de los seis ensayos.

### Interfaz

Sin explorador ni botones nuevos. El selector existente pasa a llamarse «Qué comparar» y su primera opción, cuando el archivo lo permite, es «Movimiento · fechas próximas sobre el mismo cielo»; las bandas siguen disponibles para comparar brillo. Al preparar las imágenes se muestran desplazamiento, intervalo, ritmo y estrellas de control. El anillo blanco marca la posición medida y la cruz terracota la prevista; dentro del anillo se dibujan los píxeles del objeto. Científico añade posiciones, pruebas y la comparación con la efeméride.

### Verificación de este relevo

- Sintéticas (`tests/test_non_sidereal.py`, 42 pruebas, 17 nuevas): objeto marcado `OUTLIER` medido y contado; la máscara estricta sola lo oculta; movimiento con estrellas estrictas; longitudes de onda distintas admitidas para posición y rechazadas para apilar; detectores distintos no comparados; desplazamientos de 0–2 píxeles nunca observados; fuente débil, señal en una sola época, menos de cuatro estrellas comunes y registro incoherente bloquean la afirmación; núcleo saturado medido con las alas y suelo de un píxel; reglas de selección. Validan el método, no una detección astronómica.
- Reales: `python scripts/validate_motion.py` reproduce la tabla desde los manifiestos de MOST y guarda informes, figuras y `motion_validation_summary.json`.
- Regresión completa y navegador: véase `PROJECT_STATE.md`.

### Límites que siguen vigentes

- Con una sola visita, o con visitas que no comparten cielo, no se puede demostrar el movimiento: el resultado es candidato o no evaluable, con su causa.
- Los cuerpos muy brillantes (Vesta) saturan y no se miden. Los muy débiles necesitarían combinar exposiciones; el apilamiento sigue siendo exploratorio y no entra en la decisión.
- El centro de una coma extensa se mide con el ajuste de la PSF y un error mínimo mayor; no es astrometría de precisión del núcleo. En CO₂ de agosto solo dos de siete exposiciones caen dentro de la banda con señal suficiente.
- La prueba de desaparición compara flujos del mismo detector a longitudes de onda distintas; una estrella de color extremo podría variar más de un factor dos, pero también fallaría el desplazamiento respecto a las estrellas de control.
- MOST no publica covarianzas orbitales; las diferencias de 0,2–2,0″ con la efeméride son empíricas.

## Historial: primera validación de Codex (14-11-2026)

### Resultado y alcance

La identidad del buscador existente activa la búsqueda de exposiciones a lo largo de la trayectoria mediante NASA/IPAC IRSA MOST. El análisis no contiene condiciones por nombre de objeto: admite identidades JPL de cometas, asteroides, planetas, satélites y cuerpos interestelares que el servicio pueda calcular y para los que exista cobertura. La tabla especial de 3I/ATLAS es un adaptador opcional de posiciones publicadas, asociado por identificador de exposición y detector; no es una dependencia del motor.

Se comprobaron **12 FITS DR1 originales**, seleccionados antes de descargar, de 3I/ATLAS (agosto y diciembre), Vesta, Plutón y 29P/Schwassmann-Wachmann 1. Se conserva cada recorte servido por IRSA byte a byte, URL, SHA-256, WCS, fechas, detector, λ local, ancho de banda, calibración y predicción. Los identificadores y horas exactas están en [la tabla de observaciones](results/moving/OBSERVATIONS.md), y los informes completos en `results/moving/`.

**No se ha demostrado movimiento observado en los subconjuntos astronómicos evaluados.** Sí se encuentran excesos candidatos, particularmente una estructura extendida en imágenes de 3I/ATLAS cerca del CO₂. El resultado del control real M101 también puede contener señal de fuentes estacionarias, pero no se declara movimiento. «Señal candidata» significa un exceso estadístico en la posición examinada, no identificación confirmada del cuerpo ni movimiento.

## Diagnóstico del problema original

1. **Coordenadas y selección:** el camino anterior de Time Explorer recibía una única coordenada del buscador solar, frecuentemente la posición geocéntrica actual, y consultaba imágenes de ese campo fijo. No seguía las posiciones históricas por exposición. `build_candidates` además exigía que todo el campo estuviera dentro del detector y el selector general separaba épocas al menos un día. El detector estelar modelaba fuentes puntuales y temporadas; esas condiciones no describen necesariamente un cometa.
2. **FOV:** la tabla de agosto recuperada por MOST contiene 160 productos. Incluso usando la posición correcta de cada exposición, la condición anterior de campo completo admite 157 a 3′, 151 a 6′ y solo 131 a 30′. Esto es un rechazo geométrico, no ausencia de observación ni de señal. La nueva ruta conserva cobertura parcial y diferencia lila fuera de cobertura de rosa enmascarado. Descarga contexto de al menos 15′ para el fondo; el FOV mostrado y compartido no cambia.
3. **Movimiento:** el par comparable D1 a 1,00905/1,01022 µm (9 y 14 de agosto) tiene una separación **prevista** de 3,35794°. Sus recortes de 6′ carecen de cielo común. No puede producirse una comparación sideral de esas dos imágenes; se ofrece revisión con seguimiento calculado. Las posiciones no se convierten en centroides medidos.
4. **Ruido y calidad:** en la primera imagen de ese par, 6 de los 14 píxeles centrales a 12″ están marcados `OUTLIER`. Se mantienen excluidos. Hay estrellas Gaia a 7,80″ y 6,46″ de las predicciones de las dos exposiciones, respectivamente. La señal intensa en la segunda imagen no queda identificada como cometa por ese hecho. Los anillos y controles muestran que el fondo y la confusión no son uniformes. No se suavizaron ni rellenaron esos píxeles.
5. **Bandas:** las exposiciones consecutivas suelen cambiar de canal LVF. Las imágenes D5 seleccionadas de agosto tienen λ=4,23622 y 4,26080 µm: se inspeccionan por separado, pues su diferencia excede el límite de comparabilidad. No se apilan como si fueran el mismo canal.

Evidencia cuantitativa: `fov_diagnosis.json`, informes `atlas_aug_*`, consultas Gaia registradas y originales con hashes. Un fallo de descarga o de transformación se comunica como «No evaluable», separado de cobertura nula y de señal insuficiente. Se corrigió una divergencia WCS/SIP real al comparar los campos distantes de 29P; las soluciones divergentes no se dibujan como píxeles válidos.

## Fuentes y selección científica

- [IRSA: observaciones de 3I/ATLAS](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html) y su [VOTable](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/obscore_3I_Atlas.vot): posiciones por exposición y advertencia de extensión espacial/baja señal. Se usan las posiciones publicadas incluso cuando se sustituye el producto QR2 referido por su contraparte DR1 del mismo identificador y tiempo.
- [Acceso SPHEREx](https://irsa.ipac.caltech.edu/spherex-archive-documentation/spherex-data-access/): se prefieren los productos reprocesados. Todas las imágenes de esta validación son DR1, L2b v27. Las versiones/fechas de proceso permanecen explícitas y no se combinan liberaciones diferentes.
- [Publicación de agosto](https://arxiv.org/html/2512.07318v1): justifica investigar el continuo de 1,0–1,5 µm y la emisión extendida de CO₂. Su combinación de muchas bandas del continuo y sustracción de fuentes mediante un modelo del campo no se ha reproducido aquí. Se ensayaron canales individualmente comparables para no fabricar señal mezclando bandas.
- [Publicación de diciembre](https://arxiv.org/abs/2601.06759): motivó comprobar también la respuesta extendida posterior al perihelio. Sus conclusiones físicas no se atribuyen a nuestro análisis exploratorio.
- [MOST: API](https://irsa.ipac.caltech.edu/applications/MOST/MOSTProgramInterface.html) y [tutorial oficial](https://caltech-ipac.github.io/irsa-tutorials/most-queries/): búsqueda por identidad NAIF y fechas, posiciones calculadas para SPHEREx y productos que intersectan la trayectoria. No se realiza una consulta de catálogo por cada marcador dibujado.

La [evaluación experimental de MOST](MOST_EVALUATION.md) confirma su adopción como servicio principal y corrige una suposición inicial: las posiciones de coincidencia no cambian al reducir el paso en los casos ensayados, pero se refieren al **inicio** de las exposiciones SPHEREx. Para las imágenes seleccionadas sin referencia publicada se evalúa ahora la trayectoria oficial de un segundo en el punto medio UTC, con interpolación vectorial identificada y sin extrapolación. El registro confirma observador espacial NAIF −453 y cobertura orbital hasta octubre de 2026 en la respuesta consultada. Se conserva el marco J2000 y **no se sustituye por Horizons geocéntrico**. La covarianza orbital es desconocida. Diez contrastes con la tabla oficial difieren 0,28–3,16″; no se promete precisión subpíxel. La referencia publicada sigue siendo preferida para esas exposiciones exactas.

## Método y límites de interpretación

- Datos nativos `IMAGE − ZODI`, `VARIANCE`, máscaras estrictas de píxeles inutilizables/artefactos y calidad oficial. La geometría final, detector y fecha se verifican contra el FITS. La escala visual es robusta y común a todas las imágenes.
- Morfología compacta: amplitud adaptada a la ePSF instrumental, con fondo local plano inclinado. Si no existe EPSF se identifica la aproximación gaussiana por PSF_FWHM. Las medidas de posición solo pasan si el ajuste compacto es adecuado; nunca se ajusta la coma extensa como astrometría estelar por defecto.
- Morfología extendida: aperturas de 12, 24, 48 y 96″ con fondo local robusto. Se verifica cobertura del fondo y la apertura, y variación espectral dentro de ella. Un anillo puede sustraer parte de una coma mayor: no es fotometría total ni una medida de producción de gas.
- La incertidumbre combina VARIANCE, dispersión local y covarianza del plano de fondo. Ocho posiciones de control por escala usan el mismo estadístico. La regla candidata exige al menos cuatro controles válidos, respuesta ≥6 y superior al máximo de controles por dos unidades de señal/ruido. Estos umbrales conservadores **no equivalen a una tasa global de falsos positivos calibrada**.
- Gaia identifica posibles confusores próximos (con movimiento angular desde J2016.0); no convierte magnitud óptica en flujo infrarrojo. Un campo sin fuente Gaia no garantiza ausencia de contaminantes.
- «Movimiento observado» requiere dos posiciones compactas obtenidas de los píxeles, bandas/calibraciones compatibles, al menos cuatro estrellas comunes para registro independiente, control de dispersión, rechazo de persistencia en las posiciones anteriores y desplazamiento significativo. La incertidumbre tiene un suelo conservador de un píxel nativo. Las efemérides no suministran el desplazamiento medido. El movimiento de fuentes difusas permanece candidato: no hay una astrometría de coma validada.
- Las representaciones nativas no interpolan valores. Los apilamientos diagnósticos sí se remuestrean por vecino más próximo, mantienen NaN y mapas de contribuciones, restan un fondo exterior y combinan por varianza con rechazo robusto cuando hay al menos tres imágenes. Se exige mismo detector/liberación/versión, compatibilidad espectral por pares y separación ≤7 días. Con dos imágenes no se puede rechazar un valor atípico de forma robusta.
- Para señales débiles también existe una combinación de respuestas **sobre píxeles nativos**, sin introducir covarianza de remuestreo: al menos tres exposiciones compatibles, ponderación por errores y rechazo robusto, con ocho trayectorias de control desplazadas y un suelo empírico de dispersión. Solo puede producir señal candidata, nunca movimiento. Su prueba sintética recupera señal conjunta que no supera el umbral individual y rechaza trayectorias sin señal. Los subconjuntos reales seleccionados aquí no reúnen tres imágenes compatibles; no se atribuye esa mejora a 3I/ATLAS.
- Se guardan apilamientos siguiendo el objeto y controles de fondo fijo (`*_stacks.npz/png`). En el par de agosto las contribuciones del control no son equivalentes, y en el par repetido de diciembre el centro queda enmascarado. **No se acredita una mejora científica de S/N ni una detección a partir de esos apilamientos.** La varianza diagonal no incluye toda la covarianza de remuestreo/fondo; por ello no entra en la decisión de detección. Para objetos más débiles queda pendiente validar esa inferencia conjunta antes de promover el apilamiento a detector confirmatorio.

## Reproducción

En la aplicación local: buscar `3I/ATLAS` → Tiempo → fechas de agosto de 2025 → Buscar observaciones. Elegir el continuo para comprobar el par del 9/14 de agosto, o **CO₂ · 4,23–4,28 µm**, imagen del **8 de agosto**, para examinar la estructura extendida. El selector conserva originales y fechas; no anima canales incompatibles. Para diciembre usar 1–20 de diciembre de 2025. «Todas las bandas» permite revisar la pareja repetida D4 del 8 de diciembre (2,4407 µm), sin afirmar movimiento.

`python scripts/validate_moving.py` reproduce el análisis de los subconjuntos seleccionados a partir de los manifiestos `*_discovery.json`, vuelve a verificar los FITS y guarda informes/figuras. Los manifiestos incluyen identidad, intervalo y URL exacta de consulta para repetir también el descubrimiento. Para Vesta se usó agosto; para Plutón y 29P se amplió a 2025-04-10–2026-04-10 después de documentar la respuesta vacía de agosto. Se encontraron 8, 119 y 165 exposiciones, respectivamente, pero solo se descargaron 1, 1 y 2 para esta validación inicial.

La búsqueda es acotada a un año y ocho imágenes por secuencia. No es un barrido ciego de objetos desconocidos ni una prueba exhaustiva de detectabilidad de todas las clases admitidas. El catálogo de MOST, su cobertura orbital y el muestreo de descubrimiento limitan la completitud para cuerpos muy rápidos o intervalos sin órbita disponible.

## Verificación y archivos

- Regresión completa: **472 pruebas satisfactorias**, 476,00 s; dos avisos Astropy ya conocidos (año dudoso sintético y NaN recortados en el tutorial). Registro local `data/recovery/moving_full_regression.txt`.
- Ensayos nuevos: geometría y WCS, predicción fuera de campo, cobertura parcial/nula, NaN/varianza/máscaras, fondo variable, mezcla de bandas/calibraciones, señal débil, movimiento sintético conocido, fuente estacionaria, error de alineación, contaminación persistente, apilamiento con desplazamiento conocido y divergencia SIP. Los sintéticos validan el método, no una detección astronómica.
- AppTest: vacío frente a fallo, rutas solar/estelar separadas, conservación del FOV, fechas/navegación/niveles y recuperación de errores de FITS. Comprobación final después de la corrección temporal MOST: **48 pruebas satisfactorias** (algoritmo nuevo, integración, secuencia offline y aplicación/reproductor, 18,12 s). Registro `data/recovery/moving_final_checks.txt`. Es una ejecución distinta de la regresión completa, no cifras sumables.
- La regresión incluye reproducción real de ε Indi B con originales y comparación de SHA-256. Se repitieron además Barnard D1, WISE 0855 D6 y el control M101 D2: mismo resultado previo y diferencia de desplazamiento **0,0″** en los tres. Registro `stellar_regression.json`.
- Navegador real del mismo árbol de trabajo: búsqueda existente de 3I/ATLAS, descubrimiento y preparación, continuo y CO₂, modos Sencillo/Científico, navegación Región→Tiempo conservando selección y campo de 6′. Ventana de 420 px sin desbordamiento horizontal global. Capturas `browser_simple.jpg`, `browser_scientific.png` y `browser_narrow.png`; las pruebas de vacío/fallo/reintento se simulan en AppTest y no se presentan como caídas reales de IRSA.
- Nuevos módulos: `moving_sources.py` (servicios/adaptadores), `non_sidereal.py` (análisis), `moving_view.py` (dibujado), `moving_page.py` (integración). Cambios pequeños en `time_page.py`, texto de `region_ui.py` y transporte compartido de `player.py`. El motor estelar `motion.py`, `sequence.py`, Spectrum, catálogos, máscaras y FITS originales no se modifican.
- Las decisiones visuales nuevas están en `DESIGN_SYSTEM.md`, de lectura obligatoria por `AGENTS.md`.

## Pendientes materiales

No se entrega una detección confirmada de 3I/ATLAS ni una medición de su movimiento. Quedan pendientes una sustracción de campo estelar validada, calibración empírica de falsos positivos/covarianzas del apilamiento, incertidumbres orbitales cuando el proveedor las facilite y astrometría de fuentes difusas. Ninguno de estos límites se oculta con filtros de suavizado, fotogramas inventados o máscaras relajadas.
