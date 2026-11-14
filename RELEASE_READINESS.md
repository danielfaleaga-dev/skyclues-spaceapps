# SkyClues: entrega aislada de actualización, navegación y búsqueda

Base: `2ec4881`. Worktree `SkyClues-release`, rama `feature/release-readiness`.
El historial oficial PROJECT_STATE/PROJECT_CONTEXT y el worktree principal no se modifican. Sin merge, push ni despliegue.

## Actualización de SPHEREx

`Actualizar observaciones` funciona en búsquedas nuevas y ejemplos guardados. Fuerza `query_images(max_age_s=0)`; una búsqueda normal reutiliza metadatos durante 12 horas. Cada resultado lleva origen (IRSA/caché), fecha UTC de verificación, endpoint, colecciones y conteos. Las cachés antiguas sin fecha se verifican una vez de nuevo. Un fallo de refresco no se presenta como consulta reciente: conserva los datos históricos y muestra el error. Los ejemplos FITS locales siguen disponibles.

La consulta sigue siendo SIA2 y no hay vigilancia ni descarga masiva. Un producto nuevo que SIA2 publique entra en el siguiente refresco, sujeto a las reglas de cobertura, fechas, detector y longitud de onda. IRSA documenta ingestión semanal y un posible retraso de aproximadamente un día entre directorios y SIA2: refrescar no puede adelantar esa publicación.

Fuentes y evidencia: `results/release_services.json`, `scripts/verify_release_services.py` y https://caltech-ipac.github.io/spherex-archive-documentation/spherex-data-access/ .

- `spherex_dr1` y `spherex_qr3`: respuestas reales con `calib_level=2`, `dataproduct_subtype=science`, imágenes FITS y URLs versionadas L2b.
- `spherex_dr1_deep`: 502 y timeout; `spherex_qr3_deep`: respuesta vacía en M101 y timeout al pedir una muestra sin región. Ambas están documentadas oficialmente, pero permanecen **deshabilitadas** hasta verificar una muestra compatible. No se interpreta una consulta vacía como colección inexistente.
- El perfil admite los nombres reales `l2b-vNN` y `l2b_retry-vNN`. Se verificó un recorte retry de 3,965,760 bytes, 29×29 píxeles, VERSION 7.0.5; SHA-256 y URL en el informe. Un formato desconocido o nivel distinto se rechaza, sin adaptadores especulativos.
- Identidad física: ID de exposición y detector extraídos del nombre oficial. Se eliminan representaciones duplicadas, prefiriendo DR1 y luego versión/fecha de procesamiento; se conserva la procedencia de las alternativas excluidas. Identidades desconocidas no se unen por cercanía o fecha redondeada.
- Las propuestas temporales requieren la misma colección y versión L2b; S8 comprueba además VERSION de las cabeceras y rechaza mezcla. Es una política conservadora, aunque DR1/QR3 comparten mejoras de calibración: no se ha validado aquí una comparación cruzada.
- Los informes incorporan ID publicado, nivel, versión, fecha de procesamiento, URL de recorte y SHA-256. Guardar otra búsqueda con el mismo nombre crea un archivo nuevo, nunca sobrescribe el anterior. Las versiones con URLs distintas tienen cachés distintas; no se garantiza detectar una sustitución de bytes en una URL idéntica sin cambio de metadatos. La carga histórica sí verifica su SHA-256.

`skyclues/releases.py` es la lista controlada de colecciones/perfiles. Para añadir una colección hay que verificar muestras SIA2, estructura FITS, WCS y calibración, y ejecutar regresión antes de habilitarla. El cubo publicado es `dr1-hips_20261026`, DOI 10.26131/IRSA679. Se identifica en la interfaz. `SKYCLUES_CUBE_RELEASE` permite seleccionar al arrancar un perfil registrado compatible (actualmente solo DR1). Una nueva entrada exige validación real; otro formato se rechaza. Reiniciar es obligatorio al cambiar producto, con caché separada para otra versión. El refresco SIA2 no actualiza el cubo.

## Buscador principal

«Buscar un objeto o región del cielo» ofrece coincidencias locales inmediatas y consultas SIMBAD tras 650 ms de pausa, mínimo 3 caracteres. No ejecuta búsquedas SPHEREx al escribir. Hasta 18 filas remotas, 8 sugerencias por proveedor, límite 1 MiB, timeout 4/6 s por espejo. Caché positiva de una hora, máximo 128 consultas; los fallos no se cachean. Elegir un candidato o pulsar Buscar/Enter resuelve el nombre completo. No hay coincidencias aproximadas que sustituyan silenciosamente un objeto.

El índice compacto `data/popular_objects.json` contiene 11 objetos reales verificados en SIMBAD (fecha, endpoint, bibcode, coordenadas, época y astrometría), con alias curados: M31/Andrómeda/NGC224, M101, Barnard/GJ699, WISE0855, Epsilon Indi y B, M42, M45, HD209458, R Dra y RW Aur. Los alias NGC224/5457/1976 se contrastaron con SIMBAD. Los tipos son los códigos del catálogo, no una clasificación de SkyClues. Epsilon Indi y Epsilon Indi B aparecen separados.

Estrasburgo devuelve 404 en la comprobación actual; Harvard está operativo, incluido el prefijo HD20945 (IDs distintos visibles con procedencia). Si fallan los espejos, se mantiene el índice local, la búsqueda por nombre completo con el resolvedor SIMBAD/Sesame existente y la entrada RA/Dec. No se inventan sugerencias. Los nombres completos usan la misma astrometría y cálculo de época que los exploradores existentes; objetos extensos se etiquetan como centros catalogados y el FOV puede mostrar solo parte del objeto.

## Enlaces compartibles

«Compartir esta región» genera un enlace absoluto con el origen/ruta de la instancia abierta, copiable desde el navegador. No hay dominio fijo ni sesiones almacenadas.

- `ra`, `dec`: grados ICRS, finitos, RA [0,360), Dec [-90,90].
- `fov`: **diámetro en grados**, 0.05–0.5 (3–30 minutos de arco). `fov=6` es inválido; 6′ se codifica como `fov=0.1`.
- `explorer`: `temporal` o `espectral` (se conserva el valor anterior `espectral`).
- `canal`: entero 1–102 en Spectrum.

Ejemplo local: `http://localhost:8505/?ra=210.802429&dec=54.34875&fov=0.1&explorer=espectral&canal=63`.
El host/puerto es solo el usado en la validación, no un despliegue. Un enlace temporal restaura la región y espera la búsqueda explícita. Spectrum recupera el canal. Los enlaces conservan el centro fijo, no la astrometría completa del objeto ni datos científicos; esto se avisa al compartir un objeto móvil.

Se abrió un enlace generado por la app en una sesión independiente: M31 RA 10.684708°, Dec 41.268750°, FOV 0.1°, Spectrum, canal 33. Restauración correcta sin estado previo. El navegador también verificó sugerencias locales al teclear Andrómeda, selección, apertura en ambos exploradores y sugerencias remotas HD20945.

Community Cloud documenta iframe para aplicaciones públicas con `embed=true`: https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app/embed-your-app . No se ha probado el alojamiento final: comprobar allí cabeceras CSP/X-Frame-Options, autenticación y navegador anfitrión. No se cambia ninguna protección; los enlaces directos funcionan independientemente de iframe.

## Instalación y operación

Instalación limpia realizada con Python **3.11.9**, nuevo `.venv`, `pip install -r requirements-dev.txt` y `pip check` sin conflictos. La ejecución necesita solo `requirements.txt`; pruebas científicas usan dependencias de desarrollo y Node.js para las pruebas JavaScript. No se copiaron paquetes privados ni configuraciones globales. Rutas de código derivadas del directorio del repositorio. Los resultados históricos pueden citar rutas antiguas, pero los lectores usan nombres/cache de la instancia.

Arranque:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m streamlit run app.py
```

Referencias FITS incluidas: **23,996,160 bytes**, 6 archivos. Solo Time/M101/WISE0855 puede demostrarse sin Internet; búsquedas SIA2, cubo no cacheado, SIMBAD remoto, Gaia y HiPS requieren sus servicios. Aladin Lite 3.8.1 requiere WebGL2 y jsDelivr; el buscador nuevo no añade un CDN ni paquetes runtime. Cachés en `data/cache`, resultados de usuario en `results/search_*.json`: se necesita escritura para persistirlos; sin escritura de metadatos se devuelve la consulta viva, sin prometer persistencia. Almacenamiento efímero implica volver a consultar/descargar tras reinicios. No se borra ninguna referencia científica.

Recursos: 3 trabajadores para descargas y los límites previos de rangos/caché del cubo se mantienen. En la sesión de validación con dos sesiones independientes y M31 en Spectrum, proceso servidor: working set **247,664,640 bytes**, pico **271,769,600 bytes**. Es una muestra de escritorio, no un test de carga del hosting. Las consultas mantienen procedencia por objeto de resultado (no una variable global compartida por usuarios); escrituras de caché atómicas. No se ha dimensionado concurrencia masiva. Revisión acotada de patrones de claves privadas/AWS/GitHub en archivos de texto versionados: sin coincidencias; no sustituye una auditoría completa de secretos.

## Demostración de 5 minutos

1. Abrir M101 con el botón de ejemplo: datos locales, cuatro épocas reales. Explicar canal LVF y máscaras.
2. Abrir WISE0855: dos épocas locales y marcador **calculado**, no descubrimiento. Mostrar la época y el movimiento propio.
3. Escribir Andrómeda o Barnard: sugerencias locales; seleccionar y abrir el explorador. Mostrar centro y límites del campo. HD20945 demuestra sugerencias remotas si Harvard responde.
4. Pasar a Spectrum (Internet o caché), recorrer canales y explicar cubo combinado/espectro exploratorio, sin incertidumbres calibradas.
5. Abrir Gaia y WISE (Internet), separar catálogo, cálculo e imagen; seleccionar una fuente, W1/W2 y sus límites.
6. Compartir la región y abrir el enlace en otra sesión. En Time, «Actualizar observaciones» consulta SIA2 de nuevo; si falla, explicar el estado externo y volver a los ejemplos locales.

## Integración con multibanda

No se modifican `spectrum_page.py`, `spectral_cube.py`, `spectral_view.py` ni módulos RGB. El único archivo UI compartido es **app.py**: importación de release_ui, buscador antes del selector, validación adicional de URL, identificador de cubo y compartir después de render Spectrum, botones de refresco y procedencia/compartir en Time. Revisar esos puntos al integrar, especialmente dónde termina la función render de Spectrum y cómo RGB amplía los parámetros de estado; los enlaces actuales comparten el canal individual, no una composición RGB.

Otros archivos comunes tocados: `archive.py` (metadatos versionados/procedencia/deduplicación/perfil) y `sequence.py` (refresh, metadatos de informe, versiones compatibles, guardado sin sobrescritura). Integrar después de revisar el diff y ejecutar la suite combinada. No aplicar migraciones destructivas ni fusionar esta rama automáticamente.


## Resultado de pruebas y archivos

- Línea base aislada: **201 passed, 1 warning**, 289.93 s (primera pasada sin la caché de trabajo previa).
- Regresión de la rama en el entorno limpio: **239 passed, 1 warning**, 87.28 s. Son las 201 anteriores y 38 nuevas.
- Después de los ajustes finales de prefijos/entrada y rechazo de VERSION ausente: **55 passed**, 6.89 s (pruebas nuevas más secuencias offline/live). No se relajó ninguna prueba anterior.
- Aviso conocido: Astropy descarta NaN del anillo en el verificador de Spectrum; no se rellenan datos.
- Pruebas nuevas: aparición de nueva observación tras refresh, TTL caducado, sustitución/duplicado/retirada, caída sin falsear caché, rechazo de mezclas de calibración, informes sin sobrescritura, URL inválida y sesiones independientes, alias reales, autocompletado local/remoto con caída controlada y caché positiva, propagación del estado astrométrico, botón de refresco, perfil l2b_retry y cubo desconocido.
- Navegador con instalación limpia: M101 y WISE0855 locales, posición calculada por época, M31 por nombre en ambos exploradores, canal/espectro del cubo, enlace en segunda sesión, sugerencias HD remotas, Gaia (69 fuentes en WISE0855), AllWISE W1/W2. Captura: `results/release_browser.jpg`.

Archivos de la entrega:

```
app.py
skyclues/archive.py
skyclues/sequence.py
skyclues/releases.py
skyclues/navigation.py
skyclues/object_search.py
skyclues/release_ui.py
skyclues/search_component.js
data/popular_objects.json
scripts/verify_release_services.py
tests/test_release.py
results/release_services.json
results/release_environment.json
results/release_browser.jpg
RELEASE_READINESS.md
```

El hash exacto de la entrega se obtiene con `git log -1 --oneline` en esta rama. Revisar con `git diff 2ec4881..feature/release-readiness`. No hay publicaciones ni fusiones. Los servidores de prueba locales se cierran al entregar. Pendientes externos: muestra deep compatible y comprobación real del alojamiento final/iframe, así como dimensionamiento de carga. Las fuentes operativas, sus errores observados y las limitaciones científicas están descritas arriba.
