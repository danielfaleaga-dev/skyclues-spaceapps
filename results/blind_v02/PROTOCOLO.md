# Validación ciega V02 · protocolo previo (T01, T02, T03)

Actividad `SKYCLUES_SPECTRAL_BLIND_VALIDATION_02`. Este documento se confirma **antes** de leer ningún dato de los tres objetivos.

## Estado congelado

- Código: rama `feature/spectrum-compare`, commit `490c135`.
- Archivos congelados (no se modifican): `skyclues/spectral_features.py` (versión `skyclues-features 1.0 (2026-11-14)`), `skyclues/spectral_cube.py` y `skyclues/geometry.py`.
- `scripts/blind_v02.py` registra sus huellas SHA-256 y se niega a continuar si cambian entre objetivos.
- Umbrales del analizador, sin ajustar:
  - Visible: ≥ 5 veces la dispersión de referencia.
  - Cuantificable: ≥ 7 veces la dispersión de referencia.
  - Contraste relativo mínimo: 1 %.
  - Continuo local: polinomio de grado 2 con 3 canales válidos por lado.
  - Búsqueda: de 1 a 9 canales, en dos pasadas.
- Parámetros de extracción (por defecto de la aplicación):
  - Apertura: radio de 2 px (25,8″).
  - Anillo de fondo: 4–7 px (51,5″–90,2″).
  - Fondo: media con recorte 3σ.
  - Magnitud: flujo en apertura (mJy).

## Ceguera

- **Durante la fase ciega no se hace:**
  - resolver nombres;
  - consultar SIMBAD, catálogos externos o publicaciones;
  - usar espectros externos.
- **Única fuente:** el cubo SPHEREx DR1 de IRSA (imágenes, NHITS, FLAGS y tabla de canales).
- **Contaminación:** se evalúa solo con los propios datos SPHEREx:
  - indicadores OVERFLOW, OUTLIER y SOURCE;
  - imagen del campo;
  - dispersión del anillo.
- **Declaración:** el agente es un modelo con conocimiento astronómico general y podría reconocer coordenadas de objetos célebres. No se usará ese conocimiento:
  - las posiciones están fijadas por el encargo;
  - el analizador no tiene parámetros que elegir;
  - no se seleccionan longitudes de onda.

  La ceguera es, por tanto, procedimental, como en V01.

## Procedimiento fijo por objetivo (secuencial: T01 → T02 → T03)

1. **Coordenadas:** se convierten de sexagesimal ICRS a grados.
2. **Cobertura y calidad:** se calculan sobre el FOV indicado, con `channel_map` en todos los canales, registrando:
   - fracción de píxeles válidos;
   - NHITS (mediana y mínimo);
   - píxeles con OVERFLOW, OUTLIER o SOURCE;
   - teselas HEALPix (identificador y URL del producto).
3. **Imagen del campo:** mediana del detector 1 (0,75–1,09 µm) y del detector 6 (4,4–5,0 µm), con la apertura y el anillo superpuestos.
4. **Extracción:** `extract_spectrum` en la posición indicada, sin desplazarla.
5. **Análisis:**
   - `analyse` registra todas las características (cuantificables y visibles);
   - `inspect_channel` revisa canal por canal y registra:
     - los canales no evaluables, con su causa;
     - las «anomalías aparentes» por debajo del criterio, con |contraste| ≥ 2,5 veces la dispersión de referencia sin llegar a 5. Es el umbral provisional `Q_PROVISIONAL` del propio método.
6. **Registro:** gráfico completo del espectro (todos los canales, con marcas) y datos numéricos en JSON.

## Comparación A/B

**No se usa.** Ninguna posición B puede defenderse sin conocer la morfología física del objeto: una B geométrica podría caer sobre el propio objeto o en su halo. La comparación local ya la hace el anillo de fondo del procedimiento. Se analiza el espectro único de cada posición.

## Congelación

- **Antes de ninguna consulta externa:**
  - `T0x/INFORME_CONGELADO.md` por objetivo;
  - un resumen con las huellas SHA-256 de cada resultado;
  - un commit local.
- **Después:** identificación de los objetos y comparación con la literatura, en documentos separados. Los resultados congelados no se tocan.
