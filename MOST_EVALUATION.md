# Decisión técnica: IRSA MOST como descubridor principal

Evaluación experimental local del 14 de noviembre de 2026 (consultas guardadas el 15 en UTC). **Se adopta MOST para descubrir exposiciones de objetos conocidos.** SkyClues conserva sus funciones propias de calidad, WCS, selección espectral, detección y visualización. No se desarrolla un segundo buscador orbital ni se sustituye el detector estelar.

## Resultados reproducibles

Consultas públicas `catalog=spherex`, `input_type=naifid_input`, identificadores del buscador JPL existente. Se midió una petición nueva por caso; estos tiempos no son un SLA ni un promedio de carga del servicio.

| Objeto / intervalo UTC | Paso solicitado | Productos | Tiempo de red y lectura |
|---|---:|---:|---:|
| 3I/ATLAS, 1–16 agosto 2025 | Predeterminado, 0,25 d | 160 | 2,33 s |
| Mismo intervalo | 0,02 d | 160 | 2,42 s |
| Mismo intervalo | 0,005 d | 160 | 2,80 s |
| Vesta, 1–31 agosto 2025 | Predeterminado | 8 | 1,83 s |
| Mismo intervalo | 0,02 d | 8 | 2,09 s |
| 3I/ATLAS, 1–20 diciembre 2025 | 0,02 d | 104 | 7,01 s |
| Plutón, 10 abril 2025–10 abril 2026 | 0,02 d | 119 | 21,03 s |

Repetición local con caché y SHA-256: **0,016 s** para la consulta de agosto. Un producto es aquí una exposición-detector; dos detectores simultáneos no son dos instantes diferentes. La respuesta de agosto ocupa unos 210 kB. Solo se recuperan recortes de las imágenes seleccionadas, nunca todos los FITS del resultado.

La salida contiene `observationid`, inicio/fin UTC y MJD, duración, `ra_obj/dec_obj`, cuatro esquinas y `uri`. La URI se convierte en un enlace IRSA IBE verificable; detector, versión y liberación proceden del producto, no de suponer que `instrument` contiene D1–D6 (en la salida real contiene SPHEREx). Los **12 productos DR1 L2b v27** empleados en la validación científica se recuperaron mediante esos enlaces y se comprobaron contra sus cabeceras, WCS y SHA-256. Véase [observaciones y resultados](results/moving/OBSERVATIONS.md).

## Contraste con la tabla oficial de 3I/ATLAS

La [tabla IRSA](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/obscore_3I_Atlas.vot), publicada junto a [su documentación](https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html), tiene 161 filas de agosto y 98 de diciembre, con posiciones específicas de cada exposición.

- **Agosto:** MOST coincide por `(obs_id, detector)` en **160/161**; ninguna fila adicional. Falta `2025W32_2D_0091_2 / D6`. Una comprobación SIA2 en su posición encuentra D3 de esa exposición, pero no D6 DR1/QR3; el DataLink QR2 de la tabla también devuelve una tabla vacía. Esto apunta a disponibilidad/indexación del producto, pero no demuestra por qué falta. No se inventó una contraparte ni se dedujo un fallo de efemérides.
- **Diciembre:** MOST recupera **98/98** filas de referencia más seis productos. Son candidatos de cobertura, no seis detecciones nuevas. Sus identificadores están en `most_evaluation.json`; requieren la misma comprobación FITS que cualquier producto seleccionado.
- En los 160 resultados de agosto, la separación entre posiciones de la tabla de coincidencias MOST y la referencia tiene mediana **2,38″**, percentil 95 **3,11″**, máximo **3,20″**. Fue idéntica al variar el paso solicitado en esos tres ensayos.
- En una muestra estratificada de **diez exposiciones** de agosto/diciembre, evaluar la trayectoria oficial al punto medio produce diferencias de **0,28–3,16″**, mediana **1,59″**, frente a la referencia. No todas mejoran: cambiar el instante no elimina diferencias de solución orbital, marco o convención temporal. Esta dispersión empírica no se presenta como covarianza orbital ni garantía universal.

Se conserva la tabla publicada como referencia opcional de esas exposiciones exactas. El algoritmo no necesita el nombre 3I/ATLAS ni esa tabla para funcionar con otros cuerpos.

## Observador, tiempos y resolución

La [API oficial](https://irsa.ipac.caltech.edu/applications/MOST/MOSTProgramInterface.html) documenta el paso predeterminado de 0,25 días. El registro real Full de Vesta confirma **`observer_type=1 (spacecraft)`**, **NAIF −453** y el archivo de órbita de SPHEREx. La trayectoria exportada distingue columnas `RA_obs/Dec_obs` y `RA_geoc/Dec_geoc`: se usan las primeras.

La cobertura orbital anunciada en esa respuesta es **2025-04-09 08:32:59.998 → 2026-10-16 12:00:00.002 UTC**. El rango administrativo del catálogo hasta 2040 no equivale a disponibilidad de observaciones u órbita. Una consulta de noviembre de 2026 falla en el cálculo de efemérides; SkyClues comunica ese límite como fallo/no evaluable, no como ausencia física de señal. Este límite es una instantánea del servicio, no una fecha fija impuesta por la aplicación.

La comprobación de `orbital_path.tbl` confirma 61, 751 y 3001 muestras en los quince días de agosto: pasos reales de **6 h, 28,8 min y 7,2 min**. Por tanto el parámetro sí actúa. Sin embargo, las posiciones de las coincidencias se calculan para sus propias fechas y no cambian en este ensayo. No se garantiza completitud para cuerpos muy rápidos a partir de esos dos objetos.

**Corrección importante de integración:** la tabla final de MOST para SPHEREx usa el **inicio** de la exposición (`mjd_start`), aunque la ayuda genérica describe un punto medio. Se verificó en la salida Full de Vesta del 5 de agosto: 00:07:01.931 frente al punto medio FITS 00:07:59. Un `ephem_step=1 s` no cambia ese instante de la tabla.

La ruta general ahora consulta un intervalo corto alrededor de cada exposición seleccionada, recupera la trayectoria oficial con paso de un segundo y evalúa la posición en el punto medio UTC mediante los dos vectores unitarios contiguos. Se registra el intervalo real entre muestras y el método. Se rechaza extrapolación, saltos de segmento o huecos superiores a dos segundos; el ángulo RA se trata correctamente al cruzar 0°. Se contrasta el punto medio contra `MJD-AVG` del FITS. Esto interpola una efeméride oficial, no píxeles ni cobertura.

Una consulta independiente a [Horizons](https://ssd-api.jpl.nasa.gov/doc/horizons.html) con `CENTER=500@-453` no encuentra ese observador en el servicio público consultado. El geocentro sí responde, pero **no se usa como sustituto silencioso** de SPHEREx. MOST ofrece aquí una ventaja concreta: acceso a la órbita de la nave y cruce con las exposiciones en el mismo servicio.

## Decisión y alternativas

1. **MOST principal:** identidad NAIF inequívoca, intervalo acotado, paso de descubrimiento explícito 0,02 d y caché de respuesta original con hash. La verificación a pasos más finos es necesaria cuando rapidez/curvatura o bordes de cobertura lo justifiquen; 0,02 d no es una garantía universal. Para cada imagen elegida se usa la efeméride fina independiente del paso de descubrimiento.
2. **Apoyos ya integrados:** caché para repetir consultas, reintento explícito, referencia publicada por exposición cuando existe y recuperación IBE con controles FITS. Si expira la URL temporal de la trayectoria, se regenera únicamente esa consulta corta. Un error queda separado de una búsqueda vacía.
3. **Respaldo de descubrimiento:** SIA2 más posiciones oficiales verificadas es apropiado para contrastar una exposición concreta o una tabla publicada; así se investigó la fila ausente. No se implementa ahora un segundo barrido orbital automático. Ante una caída de MOST sin respuesta almacenada o tabla verificable, se informa y se permite reintentar.
4. **Otros proveedores:** Horizons/SkyBoT pueden alimentar un futuro adaptador cuando su observador, escala temporal, cobertura e incertidumbres sean adecuados y estén validados. La prueba de Horizons −453 impide prometer hoy un reemplazo equivalente. No se escribe un integrador orbital propio ni una búsqueda ciega.

Las limitaciones detectadas justifican controles y adaptadores de respaldo; **no justifican duplicar MOST**. Las tareas propias de SkyClues —máscaras, calibración, PSF, aperturas, controles, apilamiento, WCS y evidencia de movimiento— continúan separadas del proveedor.

## Evidencia y reproducción

- `python scripts/evaluate_most.py`: repite las consultas acotadas, métricas de referencia, trayectoria y contraste de épocas; sin descargar FITS completos. El servicio puede actualizar sus órbitas/productos y cambiar los resultados.
- [most_evaluation.json](results/moving/most_evaluation.json): tiempos, URLs, hashes, filas faltantes/adicionales y las diez predicciones contrastadas.
- `most_observer_response.html`, `most_orbital_path.tbl`, `most_debug_most.txt`: respuestas públicas del servicio, guardadas sin ejecutar HTML ni scripts.
- `most_missing_reference_check.json`, `most_missing_datalink.xml`, `most_outside_orbit.json`, `horizons_timecheck_*.json`: límites y consultas de contraste.
- La corrección temporal se volvió a aplicar a los cuatro FITS de Vesta, Plutón y 29P; se preservaron los casos de 3I/ATLAS que ya usaban su referencia publicada. Vesta y 29P no superan los controles candidatos finales; Plutón conserva una señal candidata. **Ninguno demuestra movimiento observado.** El informe general recoge también las regresiones y la interfaz.
