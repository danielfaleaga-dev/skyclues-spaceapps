# SkyClues — contexto estable del proyecto

Referencia de entrada para cualquier agente. Recoge lo que **no cambia** de una sesión a otra. El estado de avance está en [`PROJECT_STATE.md`](PROJECT_STATE.md). Antes de modificar la interfaz es obligatorio leer [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md), según [`AGENTS.md`](AGENTS.md) y petición del usuario.

## Qué es

Aplicación web de ciencia ciudadana para el desafío **Planet X and SPHEREx** de NASA Space Apps Challenge 2026 (dificultad avanzada). Permite explorar observaciones infrarrojas auténticas de SPHEREx entre fechas con **Time Explorer**, y por longitud de onda con **Spectrum Explorer**. Ambas modalidades comparten regiones RA/Dec y FOV, pero conservan la distinción entre exposiciones individuales y el cubo combinado.

- Desafío: https://www.spaceappschallenge.org/2026/challenges/planet-x-and-spherex/
- Lo central del desafío es buscar por coordenadas, recuperar las imágenes de esa región y ver una secuencia temporal tipo vídeo para detectar objetos que cambian.
- Objetos de prueba citados por NASA: Barnard's Star, Epsilon Indi B, WISE 0855−0714 (RA 08h55m10.831s, Dec −07°14′42.53″), RW Aurigae y R Draconis. No se garantiza que ninguno muestre un cambio detectable. Las coordenadas del enunciado para WISE 0855 corresponden a la época ≈2010.4 (era WISE), no a J2000.0: con la astrometría de SIMBAD, en 2026 el objeto está a ≈2′ de ellas.
- El enunciado sugiere además datos actualizados, espectros, sumas y restas de imágenes, campo configurable, Gaia/WISE, URL con coordenadas, metadatos de calidad y Aladin. Son ideas de diseño, no requisitos.

## Decisiones aprobadas

| Ámbito | Decisión |
|---|---|
| Arquitectura | Python 3.11 + Streamlit + Astropy + PyVO. Nada de microservicios, base de datos ni autenticación. No migrar a React/Next sin un problema material. |
| Datos | NASA/IPAC IRSA. Campos fijos: SIA2 (`https://irsa.ipac.caltech.edu/SIA`) en `spherex_dr1` y `spherex_qr3`. Objetos móviles conocidos: MOST `catalog=spherex`, identidad JPL y trayectoria desde SPHEREx; preferir DR1. Recortes IBE: `<access_url>?center=ra,dec&size=deg`. |
| Repositorio | Único y canónico: `github.com/danielfaleaga-dev/SkyClues`. No se cambia su visibilidad, no se despliega y no se envía nada a NASA sin autorización del usuario. |
| Genealogía | El código se escribe desde cero durante el evento. **No se copia código, cachés ni resultados de SkyCluesLab** (el prototipo previo). Sus lecciones científicas sí se aplican. |
| Identidad visual | Diseño unificado de Claude B: blanco, tinta casi negra, líneas finas y acento terracota. Newsreader para títulos, IBM Plex Sans para interfaz e IBM Plex Mono para cifras. Detalles y cargas en DESIGN_SYSTEM.md. El visor científico es el protagonista. |

## Integridad científica (no negociable)

1. Los FITS originales se conservan byte a byte (`data/cache`, con SHA-256 en los informes) y no se modifican nunca.
2. Prohibido inventar fuentes, rellenar píxeles enmascarados, interpolar como si hubiera datos o «mejorar» la resolución. Los píxeles sin datos válidos se muestran con un color de máscara identificado.
3. Las transformaciones de visualización (escala, estiramiento, pseudocolor) deben estar identificadas. Las épocas que se comparan comparten la misma normalización.
4. **LVF:** en SPHEREx la longitud de onda depende de la posición en el detector. Dos fechas solo se comparan si coinciden detector, canal efectivo (Δλ pequeño respecto al ancho de banda), cobertura común, FLAGS y calidad. Una diferencia espectral, geométrica o instrumental no es variabilidad.
5. El fondo zodiacal (extensión ZODI) cambia con la fecha y **no está restado** en IMAGE.
6. Hay artefactos que parecen moverse porque están fijos en el detector y el apuntado cambia. Nunca se declara un asteroide, un movimiento o un descubrimiento sin pruebas suficientes. Decir «la evidencia es insuficiente» es un resultado válido.
7. Las posiciones de catálogo dependen de la época (Barnard ≈ 10.4″/año). La posición del objetivo se calcula para la fecha de cada observación (Astropy: movimiento propio, paralaje y velocidad radial de SIMBAD cuando existen) y la búsqueda se centra en ella. Una posición propagada no es una detección, y se avisa cuando faltan parámetros.
8. El cubo HiPS global de DR1 es un **producto combinado**: sirve para explorar el espectro, nunca como secuencia temporal.
9. Los detectores automáticos de movimiento y variabilidad de SkyCluesLab fueron experimentales y de baja sensibilidad. No se reconstruyen en el núcleo. «Buscar algo que se mueve» es código nuevo y distinto: mide una fuente elegida por el usuario con controles estacionarios; no es un detector automático ni usa IA/ML.
10. Las métricas de comparabilidad usan siempre la máscara estricta. Cualquier vista exploratoria (por ejemplo, píxeles HALO visibles) identifica los píxeles afectados y no modifica las métricas. Un producto remuestreado se etiqueta como tal.
11. Spectrum Explorer lee los 102 planos auténticos del FITS DR1; λ, intervalos y R proceden de SPECTRAL_CHANNELS. Canal = 17·(detector−1)+subcanal; plano = canal−1. Los canales 51/52 permanecen sin datos. IMAGE está en MJy/sr y ya tiene el modelo zodiacal restado; NHITS describe las contribuciones al mosaico.
12. Lectura parcial: máximo 64 rangos por petición, 48 MiB por llamada y 3 trabajadores. HTTP 200 no se consume; se validan Content-Range, tamaño, ETag y cierre multipart. Caché verbatim acotada a 200 MiB con SHA-256 por rango; las entradas antiguas sin digest se recuperan de nuevo. No se modifican FITS originales.
13. El espectro es exploratorio: apertura circular **sobre el cielo**, fracciones 5×5, fondo de anillo con media recortada 3σ/10 iteraciones y conversión a mJy con el área HEALPix. Es una adaptación del tutorial, que usa círculos en coordenadas de píxel y Photutils con solapamiento exacto: no se promete igualdad numérica. No hay incertidumbres del flujo ni corrección de apertura; la dispersión del fondo no es un error fotométrico. Sin cobertura en apertura/fondo no se asigna flujo.
14. Un cubo no tiene una sola época efectiva. Para objetos con movimiento propio se identifica la época del catálogo, el intervalo MJD-BEG/END y una posición **esperada** calculada en su punto medio, nunca una detección. Si faltan fechas válidas se conserva la posición de catálogo con aviso. Transferir una región desde Time Explorer mantiene su centro exacto; la posición esperada se muestra por separado.

## Funcionalidades y continuidad

- **Time Explorer** (núcleo): búsqueda por RA/Dec o nombre, secuencia cronológica animada con pausa y navegación por fechas, comparación A/B y blink, campo de visión (FOV) seleccionable por el usuario (recomendación oficial del desafío; es la región consultada, no un zoom), URL compartible, metadatos de calidad.
- **Objetos móviles conocidos en Tiempo:** motor universal separado del estelar, activado por la identidad del buscador. MOST descubre exposiciones a lo largo de la trayectoria; posiciones por exposición, WCS, cobertura, máscaras, ePSF/aperturas multiescala, controles y apilamiento compatible. Una posición prevista o señal candidata no confirma identificación ni movimiento. Sin búsqueda ciega. La tabla de 3I/ATLAS es un adaptador opcional, no una condición del algoritmo. Decisión y límites de observador/época en `MOST_EVALUATION.md`; validación real en `MOVING_OBJECTS_REPORT.md`. El movimiento se mide en los píxeles (posición por exposición, aparición/desaparición en el mismo detector, registro con estrellas comunes); solo en la apertura del objeto se admiten píxeles OUTLIER, porque la cadena oficial marca así las fuentes compactas no catalogadas. La efeméride sitúa la búsqueda y se compara al final; nunca aporta el desplazamiento.
- **Mejora infrarroja (S/N) en Tiempo:** combinación ponderada por varianza inversa de exposiciones auténticas del **mismo detector** sobre el mismo cielo (`skyclues/enhance.py`), como interruptor de la pestaña «Secuencia». Sin interpolación, relleno ni suavizado; máscara estricta; errores propagados de forma exacta y contrastados con una imagen nula. Dos productos: mismo canal (las fechas de la secuencia) y banda ancha del detector (exposiciones a ±7 días de una fecha, identificada como tal y no válida para brillo monocromático). Solo se presenta como «Imagen mejorada» si la ganancia medida supera sus controles. No interviene en ninguna decisión de movimiento; los detectores `motion.py` y `non_sidereal.py` no la usan. Validación real y límites en `INFRARED_SNR_REPORT.md`.
- **Spectrum Explorer** implementado: selector de canal, IMAGE/NHITS, selección por clic o coordenadas, extracción exploratoria de posición, CSV con procedencia y transferencia de regiones. Las pruebas y limitaciones concretas están en STATE.
- **Análisis del espectro** (`spectral_features.py`, `spectral_quality.py`, `spectrum_analysis.py`): picos y valles frente a un continuo local con umbrales descriptivos (no son significación estadística, porque el cubo no tiene incertidumbres), inspector por clic o intervalo, comparación A/B y causa de cada canal sin valor. Validaciones ciegas V01–V03 con resultados congelados en `results/blind_*`.
- **Intérprete físico V1** (`spectral_references.py`, `spectral_interpreter.py`, `spectrum_interpretation.py`): compara cada característica con seis referencias documentadas y devuelve uno de cinco veredictos de compatibilidad. No identifica sustancias, no da probabilidades y no estima z. Método, fuentes y límites en `SPECTRAL_INTERPRETER_V1_REPORT.md`.
- **Composición multibanda RGB** en Spectrum Explorer: tres canales auténticos del cubo DR1 en falso color, normalización por canal identificada y máscara común; solo visualización, sin combinación fotométrica ni restas.
- **Buscador, enlaces y actualización**: autocompletado (índice local verificado + SIMBAD), enlaces `ra/dec/fov/explorer/canal`, «Actualizar observaciones» bajo demanda (SIA2, sin vigilancia) e identificación del cubo publicado. Detalle en `RELEASE_READINESS.md`.
- **Región unificada:** nombre, coordenadas, FOV y Atlas comparten una sola pantalla y el estado `region` de `navigation.py` (compatibilidad `sky_region`, URL `ra/dec/fov`). La navegación es Región / Tiempo / Espectro. El Atlas (Aladin Lite 3.8.1, HiPS de IRSA: 2MASS, AllWISE, DSS2; Gaia DR3 seleccionable y constelaciones) sirve para orientarse y elegir centro; no es un tercer explorador ni muestra observaciones SPHEREx. El zoom no cambia el FOV científico.
- **Buscador universal:** Messier M1–M110 mediante SIMBAD (M102 ambiguo), NGC/IC y nombres equivalentes; Sistema Solar mediante JPL Lookup/Horizons, con fecha y observador explícitos. No hay botones por catálogo ni descargas masivas. Gaia usa los registros ya recuperados; un alias opcional no sustituye su source_id. La selección no demuestra una detección SPHEREx.
- **Dos niveles:** Sencillo prioriza imagen, acción y resultado; Científico conserva parámetros, métodos, tablas y procedencia. Cambiar de nivel no reinicia ajustes ni cambia cálculos.
- **«Buscar algo que se mueve»** (pestaña de Time Explorer, `skyclues/motion.py`): medición astrométrica de una fuente elegida por el usuario en imágenes L2 originales (ePSF oficial, registro con estrellas Gaia estacionarias, ajuste conjunto por temporada, control estacionario). Resultados: Movimiento medido, Evidencia insuficiente, Observaciones incompatibles, Datos insuficientes. Una predicción de catálogo nunca es una detección.
- Terminar y validar funcionalidades antes del refinamiento visual final.
- **Referencias Gaia/WISE implementadas**: fragmento común en Time y Spectrum, mismo centro/FOV. Gaia DR3 desde ESA (máximo 500 fuentes, selección circular en J2016.0); AllWISE W1/W2 HiPS desde IRSA en Aladin Lite 3.8.1. Capas independientes, sin modificar imágenes ni FITS SPHEREx. Gaia de catálogo y posiciones calculadas se distinguen; estas últimas usan solo movimiento propio angular y no constituyen astrometría aparente de precisión. No hay asociaciones automáticas ni comparación fotométrica entre misiones. Límites y validación en STATE y README.

## Organización de agentes

La asignación de esta actividad es puntual; los nombres siguientes documentan la colaboración histórica, no responsabilidades permanentes ni autorización para delegar.

- **Claude Code A**: motor científico (IRSA, FITS, WCS, calidad y selección de observaciones comparables).
- **Codex**: interfaz, animación temporal, integración, pruebas y apoyo al despliegue.
- **Claude Code B**: capacidades espectrales y multibanda (Spectrum Explorer) y problemas científicos especializados.
- Los agentes no editan los mismos archivos a la vez. Cada uno lee este archivo y `PROJECT_STATE.md` al empezar y actualiza el STATE al terminar.

## Fuentes oficiales

- Archivo SPHEREx: https://irsa.ipac.caltech.edu/Missions/spherex.html
- Documentación: https://caltech-ipac.github.io/spherex-archive-documentation/ (releases, data-products, data-access)
- Tutoriales: https://caltech-ipac.github.io/irsa-tutorials/spherex/ (intro, cutouts, hipscube)
- Recortes IBE: https://irsa.ipac.caltech.edu/ibe/cutouts.html
- Suplemento explicativo: https://irsa.ipac.caltech.edu/data/SPHEREx/docs/SPHEREx_Expsupp.pdf (tabla 16 de FLAGS)
- MOST (objetos del sistema solar): https://irsa.ipac.caltech.edu/applications/MOST/
- Citas: SPHEREx DR1 Spectral Images doi:10.26131/IRSA678 · DR1 All-Sky Cube doi:10.26131/IRSA679

## Calendario

Inicio: sábado 14-11-2026 a las 09:00 (UTC−5). Entrega: domingo 15-11-2026 a las 23:59.
Hitos: 1 Fundación · 2 Motor científico · 3 Visor temporal · 4 Experiencia de usuario · 5 Exploración infrarroja · 6 Integración y validación · 7 Presentación y entrega.
