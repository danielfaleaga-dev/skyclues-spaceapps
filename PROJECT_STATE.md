# SkyClues — estado del proyecto

Última actualización: integración científica del 15-11-2026 (Claude Code A, rama `integration/science-v1`, copia `C:\Users\danie\Documents\SkyClues-integrated`). El contexto estable está en [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md); las reglas visuales obligatorias están en [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md). La primera sección prevalece sobre el historial conservado debajo.

## RGB «Mismo contraste» y fondo estelar — 15-11-2026 (rama `ux/redesign-v1`)

- **Problema:** el panel RGB aparecía vacío (sin imagen ni círculo y sin marcas verticales) aunque los tres canales tenían datos.
- **Causa comprobada:** era un fallo de renderizado, no de contraste. El dominio vertical era `[-R·height/width, R·height/width]`. Si el gráfico se creaba con la columna sin anchura, el dominio salía infinito y no se recalculaba. Se reprodujo en el navegador ocultando la columna durante el redibujado: 1,1 % de píxeles no blancos, frente al 81 % normal.
- **Corrección:** gráfico cuadrado y fijo, con dominio ±R″ en ambos ejes. Después de corregirlo, la misma prueba da el 62 % en todas las alternancias.
- **Física:** el diagnóstico con datos reales (`scripts/diagnose_rgb_contrast.py`, 14 casos, canales 88/47/21 y otras combinaciones) da como máximo un 0,2 % de píxeles blancos y un 3 % recortados a negro. La fracción casi negra va del 0 al 47 %, y llega al 89 % en campos tenues. La oscuridad es la consecuencia correcta de la escala común, que se conserva. Se añade `Composite.display_stats()` (solo de presentación) y el aviso de poco contraste en ambos niveles.
- **Fondo:** la retícula se sustituye por un campo estelar en negativo, estilizado y tenue (ver `DESIGN_SYSTEM.md`).
- **Comprobado en navegador** (puerto 8524, datos reales):
  - Científico a 1400 px;
  - Sencillo con el aviso en el campo tenue (268,22°, +4,53°);
  - 375 px, sin desplazamiento horizontal de la página, con el gráfico desplazable en su caja;
  - fondo en Región y Espectro.
  
  Evidencias en `results/rgb_contrast/`.
- **Vista «Un canal»:** tenía el mismo fallo en `field_chart` y en `_field_chart_ab`, y se corrige igual: gráfico cuadrado y fijo, desplazable dentro de su caja en pantallas estrechas. El clic para elegir posición no cambia.
- **Pruebas:**
  - 3 nuevas en `tests/test_multiband.py` y 1 en `tests/test_spectral_app.py`; las de regresión fallan con el código anterior;
  - se actualiza `test_spectrum_analysis_app.py` a los colores de marcador «negro / cobrizo» que pidió el usuario;
  - regresión completa: **644 superadas y 1 fallida** (681 s). La fallida es `test_motion_app.py::test_real_eps_ind_b_d3_reproduces_from_cached_originals`, porque ESA Gaia no responde (ConnectTimeout, también al repetirla sola). Es el mismo fallo externo ya registrado y no guarda relación con estos cambios. La regresión empezó antes de los últimos ajustes de CSS del interruptor y de la opacidad, que se comprobaron en el navegador.
- **Interruptor de nivel:** antes no respondía al pulsar la palanca, porque el centro no pertenecía a ningún botón y la zona ampliada quedaba recortada. Ahora el botón de la opción no activa ocupa también la pista. Comprobado en navegador con clics reales en el centro de la palanca: Sencillo → Científico → Sencillo, a 1400 px y a 375 px.
- **Fondo:** se baja la opacidad de las estrellas de 0,72 a 0,45, a petición del usuario.
- **Limitación:** en el móvil hay que desplazar los mapas de campo dentro de su caja para verlos enteros.

## Integración científica — 15-11-2026 (Claude Code A, rama `integration/science-v1`)

Dictamen **`PASS_WITH_LIMITATIONS`**. Informe: [`INTEGRATION_REPORT.md`](INTEGRATION_REPORT.md). Local, sin push ni despliegue.

- **Qué reúne:** Spectrum Explorer (`f321c7c`), intérprete físico V1 (`0da1702`), mejora infrarroja S/N (`02347c6`) y detector no sideral (`d01917e`, antepasado común). Fusión en `ac85e6b`.
- **Cómo:** sin conflictos de código; 176 archivos coinciden blob a blob con su rama de origen. Los únicos conflictos fueron `DESIGN_SYSTEM.md` y este archivo. No se cambió ningún módulo de la aplicación.
- **Originales intactos:** `SkyClues` (Claude B, con su trabajo sin confirmar), `SkyClues-spectra`, `SkyClues-snr-A` y `SkyClues-interpreter`.
- **Coherencia científica:** `scripts/integration_verify.py`, 15 de 15 con datos reales. El movimiento de 3I/ATLAS (165,775″ ± 2,694″) es idéntico antes y después de combinar sus exposiciones; las exposiciones no cambian (SHA-256); 102 canales con la causa de cada canal sin dato; el intérprete da veredictos, no probabilidades.
- **Regresión global:** 628 superadas y 1 fallida, por la caída externa de ESA Gaia (`test_real_eps_ind_b_d3_reproduces_from_cached_originals`). Pruebas nuevas de integración, ejecutadas aparte: 12 superadas.
- **Navegador** (puerto 8521, servicios reales): búsqueda, atlas, navegación entre vistas, Tiempo en vivo (Arp 220 y M101), detector no sideral (3I/ATLAS, 166″ ± 3″), S/N (activar, comparar y desactivar), clic sobre el gráfico espectral, A/B, intérprete y los dos niveles; 420 px sin desplazamiento horizontal. Capturas en `results/integration_v1/capturas/`.
- **No comprobado:** movimiento estelar con Gaia (servicio caído), la ruta S/N de banda ancha en navegador, RGB y la consola.
- **Sin empezar, fuera de alcance:** rediseño de Sencillo, ampliación de la biblioteca del intérprete y deslizador automático de canales.

## Espectro: «¿Qué podría indicar este espectro?» (intérprete físico V1) — 15-11-2026 (Claude Code A, rama `feature/spectral-physical-interpreter-v1`)

- **Qué hace:** compara cada pico o valle ya señalado por el analizador con seis referencias documentadas:
  - H₂O hielo 3,0 µm;
  - PAH 3,3 µm;
  - H I Pfund δ 3,297 µm;
  - H I Brackett α 4,052 µm;
  - CO₂ hielo 4,27 µm;
  - CO hielo 4,67 µm.
  
  Usa la resolución de cada canal, el error del centro de banda (Hui et al. 2026), el tipo (emisión o absorción), la calidad y un z trazable (NED, dentro de la isofota D25). Devuelve uno de cinco veredictos: compatible, varias, insuficiente, ninguna o no evaluable.
- **Qué no hace:** identificar sustancias, dar probabilidades ni estimar z.
- **Archivos:** registro `spectral_references.py`, motor `spectral_interpreter.py`, presentación `spectrum_interpretation.py` e integración mínima en `spectrum_analysis.py` y `spectral_view.py`. Informe completo: [`SPECTRAL_INTERPRETER_V1_REPORT.md`](SPECTRAL_INTERPRETER_V1_REPORT.md).
- **Sin cambios en resultados:** analizador, umbrales, fotometría, máscaras, V01–V03, Time y S/N.
- **Corrección de presentación:** las insignias de Espectro usaban las clases `ok`/`warn`, que el tema no define; ahora usan `sc-ok`/`sc-warn`.
- **Resultados reales:**
  - NGC 5461 (M101): 3,3 µm «Varias referencias compatibles» (PAH y Pfδ, no confirmado); 4,08 µm «Referencia compatible» (Brα).
  - Arp 220: z = 0,018398 aplicado; 3,3 µm insuficientemente respaldada.
  - M51: z distinto para M51a y M51b.
  - TW Hya: no evaluable por el escalón D4/D5 y OVERFLOW.
  - NGC 7027 y M82: sin datos en 3,3 µm, no evaluable.
- **Pruebas:**
  - batería de Espectro: 143 superadas;
  - con el código definitivo: 42 superadas;
  - 26 pruebas nuevas del motor y 5 de integración.
- **Navegador:** servidor local del clon (puerto 8521), Edge sin interfaz. Se comprobó:
  - NGC 5461, Arp 220, TW Hya, NGC 7027 y M82, en Sencillo y Científico;
  - 420 px sin desplazamiento horizontal;
  - selección e interruptor conservados al cambiar de nivel.
  
  No se comprobaron los fallos de red ni la consola. Capturas en `results/interpreter_v1/capturas/`.
- **Pendiente para V2:**
  - respuesta espectral completa;
  - continuo y τ para hielos;
  - más líneas de H I (Paα, Pfβ…);
  - z del usuario;
  - coherencia entre rasgos del mismo espectro.

## Espectro: inspector A/B y validación ciega en NGC 7023 — 15-11-2026 (Claude Code A, rama `feature/spectrum-compare`)

- **Inspector A/B** (`74cfd6b`): el tipo y el centro solo se muestran para características clasificadas, con «Intervalo examinado» común a A y B; las unidades quedan protegidas en mayúsculas (`theme.unit`); las notas de los gráficos de Espectro se ven a opacidad completa. Sin cambios en los algoritmos. Detalle en `SPECTRUM_COMPARE_REPORT.md`.
- **Validación ciega NGC 7023:** protocolo, resultados congelados, comparación y dictamen («RECUPERACIÓN PARCIAL») en `results/blind_ngc7023/`. Aprendizaje para futuras pruebas:
  - la regla morfológica debe excluir fuentes puntuales catalogadas;
  - la fotometría con anillo local reduce la sensibilidad a la emisión extensa.
- **Validación ciega V02:** T01 (NGC 7027), T02 (núcleo de M82) y T03 (Elias 29) resultan **NO EVALUABLE**. Las tres fuentes saturan o pierden píxeles del cubo DR1 justo donde están sus rasgos de referencia; el analizador no etiquetó nada cuantificable. Detalle en `results/blind_v02/INFORME_FINAL.md`.
- **Diagnóstico V02 y validación ciega V03:** los canales sin valor de V02 son píxeles NaN/NHITS=0 con bandera BLOOM en el propio FITS, ampliados por la regla de apertura (sin defecto de código; \SPECTRAL_V02_DIAGNOSIS.md\). V03 ejecutó 3 de 14 candidatos que pasaron los criterios instrumentales: Arp 220 y núcleo de M51 PARCIAL (PAH 3,3 µm en el canal esperado), TW Hya NO EVALUABLE (OVERFLOW y salto entre detectores). Informe en \SPECTRAL_BLIND_V03_REPORT.md\.

## Espectro: diagnóstico universal de calidad — 15-11-2026 (Claude Code A, rama `feature/spectrum-compare`)

- **Qué hace:** explica por qué un canal no es evaluable, sin cambiar el método. La extracción (`spectral_cube.extract_spectrum`) añade a cada fila contadores `ap_*` (píxeles de la apertura, sin datos, NaN, NHITS = 0, BLOOM, OVERFLOW y peso perdido), calculados con los datos que ya leía. `spectral_quality.py` los traduce en causas coexistentes, y el inspector y una sección plegable las muestran en Sencillo y Científico.
- **Sin cambios en resultados:** fotometría, continuo, picos y valles, umbrales, canales 51/52 y resultados congelados V01–V03. `scripts/quality_verify.py` lo comprueba con NGC 7027, M82, Elias 29 y M101 (filas antiguas idénticas con el código anterior y con los resultados congelados; contadores iguales a una lectura independiente del FITS).
- **Aviso para la integración:** `spectral_cube.py` ya no coincide con la huella de V02, así que la línea «método intacto: spectral_cube.py» de `scripts/v03_verify.py` fallará. Es esperado: el cambio es solo aditivo.
- **No incluye:** fotometría de aperturas parcialmente válidas, interpolación ni reconstrucción de píxeles.

## Mejora infrarroja S/N — 15-11-2026 (Claude Code B; cierre de Claude Code A; rama `handoff/snr-finish-A`)

Actividades `SKYCLUES_SPHEREX_INFRARED_SNR_ENHANCEMENT_01` y `SKYCLUES_SNR_HANDOFF_AND_COMPLETION_01`. Local, sin push ni despliegue.

- **Relevo.** Claude B agotó su cuota con todo el trabajo sin confirmar en `SkyClues`. Esos 50 archivos se copiaron sin cambios a una copia independiente y se confirmaron tal cual (`561e195`). La comprobación se hizo blob a blob: 0 diferencias. El inventario con SHA-256, el parche binario y el registro de la validación final están en `results/handoff_snr/`. La carpeta de B no se modificó.
- **Implementación** (B). Está en `skyclues/enhance.py`, `enhance_page.py` y `enhance_view.py`, y en el interruptor «Mejora infrarroja» de `time_page.py`. Método, cifras y límites en [`INFRARED_SNR_REPORT.md`](INFRARED_SNR_REPORT.md), escrito en el relevo porque README y CONTEXT ya lo citaban.
- **Correcciones del relevo** (A):
  - «Qué combinar» ya no arrastra la fecha elegida a otra región.
  - Los círculos no se llaman «fuentes» cuando la imagen nula tiene tantos picos espurios como fuentes nuevas (M101 de banda ancha: 3 y 3).
  - Frase sobre qué significa la ganancia en los dos niveles.
  - Concordancia «1 fuente brillante».
  - 2 pruebas nuevas.
- **Resultados reales.** M101 en secuencia ×1,88; M101 D2 de banda ancha, diciembre de 2025, ×2,91; WISE 0855 en noviembre de 2025 ×3,49 (S/N del objetivo 12,6; 29 de 29 fuentes nuevas con contrapartida en AllWISE). M101 en secuencia y WISE en noviembre se recalcularon en el relevo y dieron resultados **idénticos**. El ×3,44 comunicado antes corresponde a otro grupo de M101 (12 exposiciones en 210 días); el código final lo reproduce exactamente, pero el producto solo combina a ±7 días.
- **Pruebas** (copia, 15-11-2026):
  - `test_enhance.py` y `test_enhance_app.py`: **33 superadas**.
  - Regresión fuera de línea (`-m "not network"`, sin las de S/N): **439 superadas**.
  - Pruebas de aplicación de Tiempo, Movimiento, Objetos móviles y Referencias: **22 superadas, 1 fallida**. La fallida es `test_motion_app.py::test_real_eps_ind_b_d3_reproduces_from_cached_originals`, porque ESA Gaia no respondió (ConnectTimeout, también al reintentar y en una consulta directa). Es el mismo fallo externo registrado por B; `motion.py` y `non_sidereal.py` son idénticos a `d01917e`.
- **Navegador** (servidor de la copia, puerto 8521, navegador integrado):
  - M101 en Científico: «Imagen mejorada», mismo canal.
  - M101 a ±7 días del 22-5-2026: 12 exposiciones D2 de 1,10 a 1,64 µm, banda ancha, ×3,17. Este paso había fallado en el script de B por un selector, no por la aplicación.
  - WISE 0855 en secuencia: «No disponible», el objetivo se desplaza 8,2″.
  - WISE a ±7 días del 9-5-2026: 5 exposiciones, ×2,27, objetivo S/N 1,9 → 4,7; flujo 1,003 y PSF ×1,08 (una sola fuente brillante).
  - Sencillo con el mismo producto; 420 px sin desplazamiento horizontal.
- **Integración:** hecha en `integration/science-v1` (ver la primera sección). Las instrucciones originales del relevo siguen en [`SKYCLUES_SNR_HANDOFF_FINAL.md`](SKYCLUES_SNR_HANDOFF_FINAL.md).

## Movimiento medido de objetos conocidos — 15-11-2026 (Claude Code B)

Actividad `SKYCLUES_NONSIDEREAL_CODEX_RECOVERY_02`. Local, sin push ni despliegue. No se tocó `SkyClues-spectra` (Claude Code A).

- **Recuperación:** el trabajo de Codex (MOST, detector no sideral, informes) estaba en el índice sin confirmar. Se preservó tal cual en `819d242` antes de modificar nada. MOST, la corrección al punto medio de la exposición, la cobertura parcial del FOV, la integración en Tiempo y las pruebas de señal ya funcionaban y no se rehicieron.
- **Pendiente real que dejó Codex:** ninguna medida de movimiento. Causas encontradas en los píxeles: (1) la máscara estricta eliminaba el propio objeto, porque la cadena oficial marca `OUTLIER` las fuentes compactas ausentes de su catálogo; (2) se exigía la misma longitud de onda para medir una posición; (3) las parejas elegidas distaban días y no compartían cielo.
- **Corrección** (`non_sidereal.py` 1.1, `moving_sources.motion_groups`, `moving_page.py`, `moving_view.py`): posición ajustada en cada exposición con la ePSF oficial; `OUTLIER` admitido solo en la apertura del objeto y contado; prueba de aparición/desaparición en el mismo detector; registro con ≥ 4 estrellas comunes; decisión con ≥ 5σ, > 3 veces la dispersión de las estrellas y ≥ 2 píxeles. Selección universal de exposiciones del mismo detector con cielo común. El motor estelar `motion.py`, `sequence.py`, Spectrum, catálogos y FITS originales no se modificaron.
- **Resultados reales** (`results/moving/motion_validation_summary.json`, tabla en [`MOVING_OBJECTS_REPORT.md`](MOVING_OBJECTS_REPORT.md)): 3I/ATLAS 165,8″ ± 2,7″ en 99 min el 9-8-2025 (D1, 61,5σ) y 156,1″ ± 4,4″ en 95 min el 8-8-2025 (D5, banda de CO₂); 293,9″ ± 4,4″ en 101 min el 14-12-2025, medido por separado en D2 y D5 con 0,03″ de diferencia. Plutón 50,2″ ± 4,9″ en 148 h y 247,0″ ± 4,4″ en 266 h. 3 Juno 214,8″ ± 8,7″ en 24,4 h. Diferencia con la efeméride 0,2–2,0″ (comparación final, no interviene).
- **No demostrado o no evaluable, con su causa:** 3I/ATLAS en D2 del 8-8-2025 (posiciones a menos de tres píxeles); Vesta (núcleo saturado, ajuste con las alas no fiable). **Controles negativos:** M101 estacionario sin movimiento; seis ensayos con la predicción desplazada sobre las mismas imágenes, ninguno con movimiento.
- **Pruebas:** Regresión completa: **499 superadas** tras el cambio científico (533,95 s). Dos repeticiones posteriores, ya con los últimos ajustes de presentación (texto de un mensaje, anillo, centrado de la vista fija y una prueba más): 496 y **497 superadas, 3 fallidas**, las mismas tres en ambas y todas por servicios externos caídos en ese momento (IRSA SIA2 respondía 502 y ESA Gaia no conectaba): `test_live.py::test_sia2_query_returns_spherex_images`, `test_live.py::test_s_region_corner_convention_matches_fits_wcs` y `test_motion_app.py::test_real_eps_ind_b_d3_reproduces_from_cached_originals`. Las tres habían pasado en la primera ejecución; `motion.py` no se ha tocado. Registro local en `data/recovery/motion_relay_full_regression_final.txt`. `tests/test_non_sidereal.py` y `tests/test_moving_app.py`: 46 satisfactorias con el código final (17 nuevas, sintéticas).
- **Navegador** (servidor local del mismo árbol, puerto 8520): buscador existente → 3I/ATLAS → Tiempo → Buscar observaciones (160) → secuencia por defecto «Movimiento · D1 · 9-8-2025» → Preparar imágenes → «Movimiento observado», 166″ ± 3″, 99 min, 100″/h, 16 estrellas. Comprobado en Sencillo y Científico (mismo resultado, selección y FOV 6′ conservados), al ir a Región y volver, y a 420 px sin desbordamiento horizontal. Sin errores de consola. No se guardaron capturas nuevas en disco; las figuras `results/moving/*_first.png` y `*_second.png` las genera el script de validación.
- **Reproducción:** `python scripts/validate_motion.py` (desde los manifiestos de MOST; los recortes se leen de la caché o de IRSA).
- **Límites:** hace falta al menos una pareja del mismo detector con cielo común; los cuerpos saturados no se miden; los débiles no se detectan en una exposición y el apilamiento sigue siendo exploratorio; el centro de una coma extensa lleva un error mínimo mayor; MOST no publica covarianzas orbitales y su órbita del observador terminaba en octubre de 2026 en la consulta de Codex.

## Historial: objetos móviles conocidos y evaluación de MOST — 14-11-2026 (Codex)

*Sustituido en lo relativo al movimiento por la sección anterior: las frases «ningún subconjunto demuestra movimiento observado» describen la primera validación.*

Implementación local sobre `redesign/unified-region`, base preservada `2cb02af`. Encargo ampliado a motor universal; **MOST es el descubridor principal**, sin nuevo buscador/explorador ni integrador orbital propio. No hubo push ni despliegue.

- Rutas nuevas `moving_sources.py`, `non_sidereal.py`, `moving_view.py`, `moving_page.py`: identidad JPL existente → exposiciones a lo largo de la trayectoria → selección compatible → imágenes originales y análisis conservador. Time conserva la ruta estelar; Spectrum, catálogos, Atlas, máscaras y FITS originales no se alteran.
- MOST real: 160/161 exposiciones de referencia de agosto de 3I/ATLAS; 98/98 de diciembre más seis productos; Vesta 8, Plutón 119. Latencias medidas 1,83–7,01 s en consultas de semanas, 21,03 s en la anual de Plutón, 0,016 s en caché. La única fila de agosto ausente tampoco apareció en SIA2 DR1/QR3 ni en su DataLink QR2. Informe completo: [`MOST_EVALUATION.md`](MOST_EVALUATION.md).
- Observador confirmado por el registro MOST: nave NAIF −453, órbita disponible 2025-04-09→2026-10-16 en la consulta realizada. El paso de 0,25/0,02/0,005 d sí cambia la trayectoria generada, pero no las 160 coincidencias de la prueba. Corrección: la coincidencia SPHEREx usa el inicio; se evalúa la trayectoria fina oficial al punto medio para imágenes seleccionadas. No se sustituye por geocentro. Diez contrastes de posición frente a la tabla oficial: 0,28–3,16″, incertidumbre orbital no publicada.
- Validación astronómica: **12 productos DR1 L2b v27** de 3I/ATLAS agosto/diciembre, Vesta, Plutón y 29P, más control estacionario M101. Todos los informes conservan URL/hash/fechas/WCS/calibración. Hay señales candidatas, pero **ningún subconjunto demuestra movimiento observado**. Tras corregir la época MOST, Vesta y 29P no superan los controles candidatos finales. No se atribuye mejora real de S/N a los apilamientos.
- Causas originales: búsqueda en una posición fija actual, rechazo de FOV parcialmente cubierto, campos que no solapan, cambios de canal LVF, píxeles OUTLIER y confusión estelar. Evidencias, observaciones y reproducción en [`MOVING_OBJECTS_REPORT.md`](MOVING_OBJECTS_REPORT.md) y `results/moving/OBSERVATIONS.md`.
- Pruebas: regresión completa **472 satisfactorias**; comprobación final posterior a la corrección MOST **48 satisfactorias** (ejecuciones distintas). Reproducciones reales Barnard, WISE 0855 y M101 sin cambio de resultado ni desplazamiento; ε Indi B incluido en la regresión completa. Pruebas nuevas cubren señal débil conjunta, movimiento sintético, estacionario, error de alineación, contaminación, máscaras, coberturas, incompatibilidades, WCS/SIP, época y cruce RA=0, sin extrapolar efemérides.
- Navegador: Sencillo/Científico, selección continuo/CO₂, Región→Tiempo con identidad/selección/FOV 6′ conservados; ventana 420 px sin desbordamiento de página. Capturas reales en `results/moving/browser_*`. Fallos/vacíos/reintento ensayados de forma controlada en AppTest. Diseño obligatorio actualizado en `DESIGN_SYSTEM.md`.
- Pendientes materiales: astrometría de coma, sustracción validada de fuentes de fondo, covarianzas/tasa global de falsas alarmas y demostración astronómica de movimiento. MOST fuera de su órbita disponible no permite concluir ausencia de datos. No se promete detección de todas las clases ni completitud para objetos muy rápidos.

## Historial: continuidad unificada de catálogos, Gaia y presentación

- Se conserva el rediseño de Claude B. No hay segunda aplicación, cambios en motores científicos, push ni despliegue. Respaldos originales intactos y bundle adicional verificado en `data/recovery/`.
- **Catálogos:** buscador único con Messier completo por resolución dinámica, M102 explícitamente ambiguo, NGC/IC y JPL Lookup/Horizons para cuerpos del Sistema Solar. Los casos requeridos se consultaron contra servicios reales; evidencia en `results/continuity_services.json`. 3I/ATLAS incluye metadatos oficiales de 259 exposiciones QR2 y sus posiciones históricas, sin convertirlos en detecciones ni ampliar el motor DR1/QR3 a QR2.
- **Autocompletado corregido tras la captura del usuario:** el desplegable ya consulta SIMBAD con mayúsculas/espacios válidos e incluye JPL. `ngc` muestra resultados NGC reales; `atlas` incluye 3I/ATLAS y distingue el satélite y los otros cometas. Consultas en segundo plano, caché, mensajes de actividad y resultados acotados. Verificación en navegador y `results/autocomplete_services.json`; 175 pruebas de catálogos/Gaia/búsqueda satisfactorias tras la corrección.
- **Gaia:** clic exacto en source_id, nombre y RA/Dec sincronizados, FOV conservado e identidad persistente entre exploradores. Alias solo por coincidencia comprobada del identificador. Consulta en segundo plano, caché, estados vacío/error/reintento y descarte de respuestas de regiones anteriores.
- **Atlas:** 88 constelaciones; zoom de orientación independiente del FOV. Se corrigieron animaciones obsoletas al editar coordenadas y el mapa vacío tras sustituirse su DOM durante una actualización de código.
- **Presentación:** vidrio esmerilado en la carga de Gaia, con el cielo visible y desenfocado, sin fondo gris uniforme ni bloqueo del mapa. Tarjetas de actividad para productos principales, esperas compactas para acciones secundarias y sin porcentajes inventados. Reproductor integrado en la paleta.
- **Sencillo:** menos texto técnico en Región, Tiempo, Movimiento, Espectro y RGB. Científico conserva los controles avanzados, tablas, métodos y procedencia. Los parámetros ocultos conservan sus valores al cambiar de nivel.
- **Verificación:** 442 pruebas completas satisfactorias antes del último ajuste de presentación; después 130 de las áreas afectadas y una regresión final de 194 de búsqueda/Gaia/Tiempo. Tras los últimos ajustes visuales, 33 pruebas RGB y 19 del reproductor satisfactorias. Son ejecuciones distintas, no cifras acumulables. Casos de fallo/lentitud/caché simulados de forma controlada; servicios y recorridos normales verificados también en navegador real. Detalle y límites en [`CONTINUITY_REPORT.md`](CONTINUITY_REPORT.md).
- Aplicación local del usuario: `http://127.0.0.1:8507`. El puerto 8508 se usa solo para comprobaciones temporales del mismo árbol de trabajo.

Antes de continuar: leer AGENTS.md y DESIGN_SYSTEM.md. No restaurar la arquitectura antigua de tres selectores de localización que describe el historial siguiente. Conservar la distinción catálogo/predicción/observación.

## Atlas astronómico e investigación «Buscar algo que se mueve» (14-11-2026)

Rama `feature/atlas-motion`, creada desde la base integrada `781070e` (`main`, con `bee8fa8` y `47e7bd7`) y publicada en `origin/feature/atlas-motion` a petición del usuario («ve aplicando todo a guithub»). `main` no se ha tocado; sin despliegue, publicación ni envío a NASA. FITS de `data/reference` sin cambios (SHA-256 comprobado por prueba).

### A. Atlas

- **Arquitectura:** el Atlas no es un tercer explorador. Encima de los dos exploradores hay un selector «Localizar una región del cielo: **Por nombre | Coordenadas | Atlas**». Los tres escriben el mismo estado común: parámetros `ra/dec/fov` de la URL y `st.session_state["sky_region"]` (`navigation.current_region`, `set_region`, `open_region`). Al cambiar de región se vacían los campos de coordenadas de ambos exploradores para que se reinicialicen con ella.
- **Visor:** Aladin Lite 3.8.1 (el mismo paquete fijado de `references.ALADIN_JS`), componente `st.components.v2` (`atlas.py` + `atlas_component.js`) con una única instancia por montaje. Arrastrar, rueda o botones de zoom, clic para centrar, pantalla completa. Muestra el centro ICRS en grados y sexagesimal, el tamaño de la vista y la región en un círculo amarillo. Python solo recentra el mapa cuando envía un `nonce` nuevo, así que tras una selección se conserva la vista del usuario.
- **FOV:** preajustes 3/6/12/18/30′ (límites de los exploradores). Si la vista supera 30′ aparece un aviso explícito y «Ajustar al zoom» propone el máximo admitido (30′) indicándolo («no se recorta en silencio»). Una selección fuera de límites se rechaza con un error visible y no cambia la región.
- **Capas** (HiPS oficiales servidos por NASA/IPAC IRSA, propiedades comprobadas HTTP 200): 2MASS J·H·K color, AllWISE W4·W2·W1 color, AllWISE W1, AllWISE W2, DSS2 color. Cada capa muestra misión, identificador IVOA, bandas y época, y lleva la nota de que no son datos SPHEREx. **Gaia DR3** se superpone como catálogo con la consulta ESA ya existente (servidor, J2016.0, máximo 500 fuentes) para el círculo seleccionado; si Gaia falla, el atlas sigue funcionando con un aviso.
- **SPHEREx en el Atlas:** IRSA publica el HiPS combinado `ivo://IPAC/P/SPHEREx/DR1/cube` (versión 2026-11-01, cubo de 102 planos PNG). Sus teselas por plano no siguen la ruta HiPS estándar que carga Aladin Lite 3.8.1, por lo que **no se ofrece como capa**: se documenta en «Procedencia de las capas» y el cubo se sigue explorando en Spectrum Explorer. Ningún mapa del atlas es una secuencia temporal. No se compara entre misiones ni se infiere movimiento de esas diferencias.
- **Integración con el nombre:** tras resolver un nombre, «Ver en Atlas» centra el mapa en la posición **calculada para hoy** y coloca un marcador con una nota. Si la región se selecciona sobre el marcador (a menos de 1″), al abrirla se conserva la astrometría de catálogo. Time Explorer calcula entonces la posición por fecha y Spectrum aplica su regla de época del cubo. Si el centro se movió, se abre como coordenadas fijas.
- **Coordenadas:** RA/Dec en grados ICRS y diámetro en minutos de arco, con «Ver en Atlas», «Abrir en Time Explorer» y «Abrir en Spectrum Explorer». Las mismas validaciones (`targets.validate_*`).

Recorridos en navegador real (servidor local):
- Aladin se inicia con WebGL2 y carga 2MASS.
- Desplazamiento a Orión con vista de 1.50°: aparece el aviso; «Ajustar al zoom» propone 30′ y dice que es el máximo.
- Selección de 12′: URL `?ra=83.822100&dec=-5.391100&fov=0.2`. El mapa conserva la vista tras recargar el script.
- «Abrir región en Time Explorer»: Nueva búsqueda, Coordenadas RA/Dec, RA 83.822100, Dec −5.391100, 12′ (0.200°).
- Nombre «Barnard» → Ver en Atlas: centro RA 269.445972°, Dec +4.770782° (hoy) con la nota del marcador.
- Abrir en Spectrum: el centro se recalcula con la regla de época del cubo (269.44627, +4.76820; canal 33).
- Gaia en el atlas, campo de Barnard de 6′: 500 fuentes dibujadas sobre 2MASS, con el aviso de truncado por magnitud G. Captura: `results/atlas_browser.jpg`.
- Al cambiar el tamaño de la ventana, Aladin no redibujaba el círculo ni Gaia hasta mover el mapa. Se corrigió con un `ResizeObserver` y se comprobó tras redimensionar.

Pruebas: `tests/test_atlas.py`, 20 pruebas, todas satisfactorias:
- estado común: prioridad URL → secuencia → M101, validación, reinicio de campos y procedencia del centro;
- capas: oficiales IRSA, con misión, producto, bandas y época, y sin SPHEREx como capa;
- AppTest: tres métodos con el atlas fuera del selector de exploradores; selección (evento del componente **simulado**) que abre Time y Spectrum con las coordenadas exactas; FOV de 1.5° rechazado sin recortar; astrometría conservada solo sobre el marcador; caída de Gaia **simulada** que mantiene el atlas usable; panel de coordenadas hacia ambos exploradores y hacia el atlas.

Límites del Atlas:
- Requiere WebGL2 y acceso del navegador a jsDelivr e IRSA. Si falla, aparece un mensaje a los 30 s y siguen disponibles «Por nombre» y «Coordenadas».
- Gaia solo se consulta para la región seleccionada, no para la vista libre (la vista ilimitada no se consulta en masa). Los HiPS JPEG son contexto visual, sin fotometría.
- El enlace compartible no guarda la capa ni la vista libre, solo la región.

### B. Investigación «Buscar algo que se mueve»

**Módulo:** `skyclues/motion.py` (`METHOD_VERSION = "skyclues-motion 1.0 (2026-11-14)"`). Trabaja solo con imágenes L2 individuales originales: IMAGE − ZODI, VARIANCE, FLAGS, la extensión **EPSF** oficial (441 zonas, ×5) y el WCS de cada archivo. Nunca usa el cubo, capturas, RGB ni productos remuestreados. No usa IA ni ML. Los pasos:

1. Ajuste PSF ponderado con la ePSF de la zona del detector (flujo y fondo libres, máscara estricta, saturación OVERFLOW/NONLINEAR identificada).
2. Registro con estrellas Gaia DR3 estacionarias:
   - selección: G ≤ 19, aisladas 15″, a más de 25″ del objetivo, S/N ≥ 8, residuo ≤ 3″;
   - se aplica su movimiento propio y cada estrella tiene un punto cero libre;
   - el desplazamiento de cada imagen se resuelve de forma conjunta, con recorte 4σ.
3. Una posición por temporada (separación > 10 d) ajustada conjuntamente a todas sus exposiciones (verosimilitud perfilada), con errores:
   - del hessiano, escalados por el χ² local;
   - más el error del registro;
   - inflados por la dispersión de ajustes individuales.
   Si una temporada no se puede ajustar, se registra con su motivo.
4. Desplazamiento entre la primera y la última temporada con detección ≥ 10σ, con significación de Mahalanobis.
5. Control estacionario: cada estrella de referencia, con registro *leave-one-out*, pasa por la misma cadena. Calibra los errores (factor ≥ 1) y fija el máximo alcanzado por una fuente fija.
6. **MOTION_MEASURED** solo si se cumplen todas estas condiciones:
   - S ≥ 5σ tras calibrar;
   - S por encima del máximo del control;
   - ≥ 3 estrellas de control;
   - sin confusión;
   - si el núcleo está saturado, ≥ 3 ajustes individuales por temporada.
   Si no, **INSUFFICIENT_EVIDENCE**; con detectores mezclados, **INCOMPATIBLE_OBSERVATIONS**; con menos de dos temporadas, **INSUFFICIENT_DATA**. Sin Gaia, o si ninguna imagen se puede registrar, no se supone estacionariedad: evidencia insuficiente.
7. La predicción de catálogo (SIMBAD) solo se **compara al final** y no interviene en la búsqueda, el ajuste ni la decisión (verificado por prueba).

**Selección de imágenes** (`select_epochs`):
- mismo detector, recortes de 12′;
- temporadas con ≥ 3 imágenes y la base temporal más larga (primera, intermedia y última);
- las imágenes más alejadas del borde del detector.

La λ varía dentro de un detector (LVF). Las posiciones no dependen de λ a primer orden y cada imagen usa su propia ePSF. Esto no es la comparabilidad fotométrica S1–S9 de Time Explorer, que es más estricta.

**Interfaz:** en Time Explorer, pestaña «Buscar algo que se mueve».
- Fuente: el objetivo del catálogo, una fuente detectada en la época 1 (filtro adaptado) o RA/Dec, con un radio de búsqueda.
- Imágenes: las épocas de la secuencia, o «Ampliar la base temporal», mismo detector, con 2–8 imágenes por temporada.
- Lista de investigaciones reales guardadas.
- Insignia de resultado y motivos; métricas, comparación con el catálogo, tabla por temporada, imágenes con SHA-256 y URL, control y JSON reproducible.
- Las cifras de un resultado no validado se rotulan «Desplazamiento aparente (no validado)».

**Casos reales** (todos en `results/motion_*.json`, generados con `scripts/investigate_motion.py`, recortes en caché, nunca modificados):

| Caso | Det. | λ (µm) | Imágenes / temporadas | Resultado | Medida (calibrada) | Control | Catálogo (solo comparación) |
|---|---|---|---|---|---|---|---|
| ε Ind B | D2 | 1.26–1.37 | 12 / 3 | **MOTION_MEASURED** | 6.92 ± 0.32″ en 522 d, 22.5σ | 40 estrellas, máx 4.0σ | 6.55″ previsto, diferencia 1.2σ |
| ε Ind B | D3 | 1.69–2.07 | 12 / 3 | **MOTION_MEASURED** | 6.22 ± 0.15″ en 516 d, 43.4σ | 43 estrellas, máx 6.2σ | 6.47″ previsto, diferencia 1.7σ |
| WISE 0855 | D6 | 4.61–4.90 | 15 / 3 (6 por temporada) | **MOTION_MEASURED** (marginal) | 4.43 ± 0.76″ en 174 d, 5.8σ | 7 estrellas, máx 3.1σ | 4.73″ previsto, diferencia 2.0σ |
| WISE 0855 (misma llamada que la app, 4 por temporada; `motion_wise0855_d6_app_4per.json`) | D6 | 4.61–4.90 | 11 / 3 (2 con ≥ 10σ; 2025-11 da 7.6σ) | INSUFFICIENT_EVIDENCE | 4.53 ± 1.08″ en 144 d, 4.4σ | 7 estrellas, máx 1.5σ | 3.99″ previsto, 2.8σ |
| Barnard | D6 | 4.60–4.89 | 12 / 3 (2026-08 sin ajuste: núcleo saturado, χ² sin mínimo definido) | INSUFFICIENT_EVIDENCE (núcleo saturado) | 4.97 ± 3.77″ en 254 d, 1.5σ | 28 estrellas, máx 3.4σ | — |
| Barnard | D1 | 0.88–0.99 | 12 / 3 | INSUFFICIENT_EVIDENCE (confusión + núcleo saturado) | ajuste aparente 15.1″, **no validado** | 40 estrellas, máx 2.4σ | 10.3″ previsto: el ajuste no es compatible (18σ) |
| Control M101 (estrella Gaia con μ < 20 mas/año) | D2 | 1.28–1.39 | 12 / 3 | INSUFFICIENT_EVIDENCE (correcto) | 0.14 ± 0.08″ en 381 d, 1.7σ | 20 estrellas, máx 2.9σ | — |

Interpretación:
- **ε Ind B** se mide con dos detectores independientes. Las medidas concuerdan entre sí (diferencias en Δξ y Δη de 1.6σ y 1.2σ) y con el catálogo.
- En D3, una de las 43 estrellas de control llegó a 6.2σ. La tasa de falsos positivos del control a 5σ no es nula (1/43), y por eso la decisión exige superar el máximo del control.
- **WISE 0855** está en el límite: unas 5σ por exposición. Con 6 exposiciones por temporada se mide a 5.8σ. Con la selección por defecto de 4, la temporada de 2025-11 no llega a 10σ, la base se acorta a 144 d y el resultado es evidencia insuficiente. Ambos resultados son honestos y dependen de las exposiciones usadas, que quedan registradas.
- **Barnard** (J ≈ 5) satura el núcleo en todas las temporadas. En D1 el ajuste salta a otra fuente: hay confusión. La regla lo rechaza, aunque la cifra aparente es de 20σ y no coincide con el catálogo: es un ejemplo de falso positivo evitado.
- **M101** (campo de 6′ de la secuencia) no puede registrarse: hay 3 referencias Gaia aisladas y la luz de la galaxia da χ² de 28–79. El resultado es evidencia insuficiente con ese motivo. El control en 12′ no da falso positivo.

**Experimentos sintéticos** (`tests/test_motion.py`, 24 pruebas, rotuladas SIMULADO). Usan imágenes con la ePSF oficial de un FITS real de `data/reference` (solo lectura), ruido gaussiano conocido, 14 estrellas Gaia simuladas y errores de WCS por imagen. Resultados:
- se recupera un desplazamiento de (6, −4)″ dentro de 3σ;
- 6 objetivos estacionarios con semillas distintas: ningún falso positivo;
- *pulls* de 8 realizaciones con desviación < 1.6 y media < 1;
- errores de WCS de σ = 1″ (más de 3 veces el máximo real de 0.32″) eliminados, residuo < 0.2″;
- con σ = 2″, las imágenes con WCS desviado más de 3″ pierden las referencias y el método degrada de forma conservadora;
- sin Gaia, evidencia insuficiente; con flujo de 5 (2–3σ por imagen), nunca medido; con flujo de 60, medido con errores honestos;
- una temporada o una imagen dan datos insuficientes; detectores mezclados, incompatibles;
- se informa la saturación;
- una predicción de catálogo errónea no cambia la decisión;
- una temporada sin ajuste se informa con su motivo;
- selección de épocas, agrupación por temporadas, validación de entradas e integridad del FITS de referencia.

**Estado:** **MEASUREMENT_SUPPORTED**, para fuentes no saturadas y aisladas, con ≥ 3 estrellas Gaia de referencia y ≥ 2 temporadas con detección ≥ 10σ:
- desplazamientos de ≳ 1″ (≥ 5σ) en fuentes brillantes;
- de varios segundos de arco en fuentes cercanas al límite.

En el resto de casos (saturación, confusión, campos sin referencias, una temporada) el método solo permite inspección y lo dice. Incertidumbres:
- errores de ajuste de 0.02–1.1″ por temporada;
- registro de 0.01–0.03″ por temporada;
- factor de calibración 1.00–1.15.

La tasa media es aparente: incluye paralaje y la geometría de las fechas, y no es un ajuste de movimiento propio.

Pruebas de la pestaña (`tests/test_motion_app.py`, 4):
- las investigaciones guardadas son reales, con SHA-256 y URL de IRSA;
- la pestaña se dibuja y una caída **simulada** de Gaia se explica sin fingir medida;
- la base temporal ampliada ofrece el número de imágenes por temporada;
- **red:** se reproduce ε Ind B D3 desde los 12 originales en caché y una consulta Gaia nueva (MOTION_MEASURED, diferencia < 0.05″, SHA-256 iguales antes y después).

Recorrido en navegador real:
- la pestaña aparece en Time Explorer;
- la lista de 6 investigaciones guardadas muestra los resultados de la tabla;
- en la secuencia WISE 0855 (2 imágenes) el resultado es evidencia insuficiente (la época de 2026 da 7.6σ, por debajo de 10σ);
- con la base temporal ampliada, el resultado es el de la fila «app» de la tabla.

### C. Integración

- **Commits** en `feature/atlas-motion`:
  - `5eb4a8e`: módulo de medida y casos iniciales;
  - `83fa795`: Atlas, estado común, pestaña, pruebas y casos reales;
  - el siguiente: motivos de temporadas fallidas, imágenes por temporada y documentación (`git log` da el hash).
  Las ramas anteriores se conservan.
- **Archivos nuevos:**
  - `skyclues/atlas.py`, `skyclues/atlas_component.js`, `skyclues/motion.py`, `skyclues/motion_page.py`;
  - `scripts/investigate_motion.py`;
  - `tests/test_atlas.py`, `tests/test_motion.py`, `tests/test_motion_app.py`;
  - `results/motion_*.json`.
- **Archivos modificados:** `app.py` (selector de localización y pestaña), `skyclues/navigation.py` (estado común) y `skyclues/release_ui.py` (selector y panel de coordenadas). Los informes de búsqueda de Barnard y ε Ind B se renombraron a `results/motion_search_*.json` para que no se tomen como secuencia por defecto.
- **Regresión** (`.venv\Scripts\python -m pytest -q`, red disponible): 298 pruebas satisfactorias sin `tests/test_motion.py` (3 min 14 s), más 24 sintéticas (4 min 30 s). En total **322 satisfactorias, 0 fallidas**, 1 aviso conocido de Astropy. Las 274 anteriores siguen pasando.
- **Rendimiento:**
  - una investigación con 12 recortes de 12′ tarda 2–7 min en el portátil de desarrollo, la mayor parte en el control *leave-one-out*;
  - unos 4 MB por recorte, en caché y reutilizados;
  - con las épocas de la secuencia, unos 6 s;
  - las pruebas sintéticas tardan unos 4–5 min.
- **Defectos corregidos durante la actividad:**
  - el centro por defecto del atlas tomaba un informe nuevo;
  - motivo erróneo en M101 («no se detecta» en lugar de «no se puede registrar»);
  - cifras de resultados rechazados rotuladas como «medido»;
  - temporada descartada sin motivo en Barnard D6.
  - el círculo y Gaia del atlas no se redibujaban tras redimensionar.
- **API para Codex** (detalle en el código):

```python
from skyclues import motion, navigation, atlas
sel = motion.select_epochs(records, ra, dec, detector, per_season=4)      # dict: selected, season_dates, rule…
frames = motion.fetch_frames(sel, ra, dec)                                # MotionFrame(image, record, cutout_url, path, sha256)
inv = motion.investigate(frames, (ra_sel, dec_sel), gaia=references.fetch_gaia(ra, dec, 0.2),
                         astrometry=astro_or_None, search_radius_arcsec=20)
inv.outcome, inv.label, inv.reasons                                       # MOTION_MEASURED | INSUFFICIENT_EVIDENCE | …
result = motion.to_jsonable(inv)   # displacement, seasons, seasons_failed, images, registration, control, catalogue_comparison
navigation.current_region(st.session_state, st.query_params)              # {ra, dec, fov[, source, astrometry]}
navigation.set_region(state, params, ra, dec, fov, source="Atlas")         # valida; ValueError si no
navigation.open_region("temporal" | "espectral")                          # callback de botón
```

Reglas:
- no mostrar nunca `displacement` sin `outcome`; si `outcome != MOTION_MEASURED`, las cifras son «aparentes (no validadas)»;
- `catalogue_comparison` es contexto, no evidencia;
- las capas del atlas no son datos SPHEREx.

Pendiente o fuera de alcance:
- `main` no se ha actualizado con esta rama (decisión del usuario);
- no hay vista del atlas con capa SPHEREx;
- no hay ajuste de movimiento propio y paralaje;
- fuentes saturadas o en campos densos sin un modelo más completo de las alas.

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

Sin push, despliegue, publicación ni envío a NASA. Ramas y worktrees originales conservados. (La investigación de movimiento se inició después; ver la primera sección.)

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
3. RW Aur y R Dra no se han ejecutado en SPHEREx. Barnard, ε Ind B y WISE 0855 tienen investigaciones de movimiento reales (primera sección).
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
