# Traducción al inglés de SkyClues — cierre

Carpeta `C:\Users\danie\Documents\SkyClues-ux`, rama `ux/redesign-v1`. Local, sin push ni despliegue.

## Qué está en inglés
- Toda la interfaz Python (Region, Time, Spectrum, Simple, Scientific): textos, ayudas, cargas, errores, explicaciones científicas e intérprete.
- `region_component.js`, `reference_view.html` y los componentes heredados (`atlas_component.js`, `search_component.js`).
- Cabeceras de las tablas de datos de Spectrum (solo la etiqueta visible; los identificadores y los CSV/JSON no cambian).
- Textos en español guardados en `results/*.json` (criterios, motivos, notas, estados de movimiento): se traducen **al cargar**, en memoria, con `skyclues/saved_text.py`. Los archivos no se modifican.
- Valores internos mostrados al usuario (`pico`/`valle`, `estrecha`/`amplia`): correspondencia de visualización en `spectral_view.py`; los valores son contratos y no cambian.
- Decimales con punto.

## Contratos internos conservados
No se renombraron claves, columnas, parámetros de URL (`explorer=espectral`, `canal`, `nivel`), identificadores de estado ni nombres de archivos. No se tocó ningún algoritmo ni resultado científico.

## Comprobación en navegador (puerto 8522)
Region (búsqueda con sugerencias, mapa), Time (M101 y WISE 0855, pestañas Sequence/Motion/Quality/Provenance, mejora infrarroja, movimiento de 3I/ATLAS en la versión integrada anterior), Spectrum (espectro real, intérprete, referencias, RGB, plegables), ambos niveles. Detector automático de español sobre el texto renderizado: sin residuos en estos recorridos. 420 px sin desplazamiento horizontal. Capturas en `results/i18n/capturas/`.

## Pruebas
- Última ejecución completa offline antes de los últimos ajustes: 505 superadas, 69 fallidas (todas por texto esperado en español o etiquetas antiguas).
- Tras actualizar tests: los archivos que fallaban pasan a 276 superadas y 33 fallidas; con el último arreglo, 32.
- Tests científicos de movimiento, mejora S/N y no sideral: 128 superadas y 1 fallida (espera «cobertura orbital»).
- **Los 32 fallos restantes son solo de idioma** (esperan frases españolas antiguas: `test_spectral_quality`, `test_spectrum_analysis_app`, `test_spectral_interpreter*`, `test_spectral_app` (URL no válida), `test_multiband` (varias teselas), `test_moving_app`, `test_non_sidereal` (orbital), `test_autocomplete`, y dos harness `.cjs` de referencias). No se han relajado criterios científicos. Quedan por actualizar.
- Las pruebas con red no se ejecutaron en esta pasada.

## Residuos conocidos
- Claves de JSON y CSV descargables y vistas JSON de procedencia siguen en español (contratos de datos).
- Comentarios y docstrings del código, informes y documentación histórica no se tradujeron.
- Los textos guardados que no coinciden con la tabla de `saved_text.py` (resultados no cargados por la interfaz) se muestran sin traducir.
- Fallos externos conocidos (Gaia, IRSA) siguen afectando a las comprobaciones en vivo.
