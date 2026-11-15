# SkyClues

SkyClues explora observaciones infrarrojas **auténticas** del telescopio espacial SPHEREx, obtenidas de NASA/IPAC IRSA, mediante Time Explorer y Spectrum Explorer. Es un proyecto para NASA Space Apps Challenge 2026, desafío *Planet X and SPHEREx*.

Para cualquier región del cielo y un campo de visión elegido por el usuario (3′–30′), busca observaciones SPHEREx de fechas distintas que sean científicamente comparables: mismo detector, mismo canal LVF efectivo, cobertura común válida y calidad oficial. Después las reproduce sin alterar los datos: cada píxel nativo se dibuja en su posición real del cielo, sin remuestreo.

```bash
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\streamlit run app.py
```

## Uso de Spectrum Explorer

Abra un ejemplo o región en Time Explorer y pulse **Ver esta región en Spectrum Explorer**, o elija Spectrum Explorer en la barra lateral e introduzca RA/Dec en grados y un diámetro en minutos de arco. Cambie el canal, consulte IMAGE (MJy/sr) o NHITS y haga clic sobre un píxel para seleccionar su posición. Pulse **Obtener el espectro en esta posición** para actualizar la extracción; mientras tanto se identifica el espectro anterior. La tabla permite descargar CSV con procedencia. **Abrir esta región en Time Explorer** conserva el centro y FOV para una búsqueda nueva.

El cubo DR1 combina distintas fechas: sus 102 canales no son una secuencia temporal. Las longitudes de onda vienen del FITS oficial y los canales 51/52 permanecen vacíos. Se leen rangos HTTP, sin descargar teselas completas (~320 MB); si IRSA ignora Range, se rechaza la respuesta sin leer su cuerpo.

Los espectros son **solo exploratorios**, sin incertidumbres ni corrección de apertura. SkyClues adapta la suma con fondo del [tutorial oficial de IRSA](https://caltech-ipac.github.io/irsa-tutorials/spherex-hipscube/): usa círculos sobre el cielo con subpíxeles; el tutorial usa círculos sobre la rejilla y Photutils. Sus valores pueden diferir. Para resultados científicos se remite a la [herramienta de espectrofotometría de IRSA](https://irsa.ipac.caltech.edu/applications/spherex/tool-spectrophotometry). Una posición propagada de WISE 0855 u otro objeto móvil es una predicción, nunca una detección en el cubo.

En **Composición multibanda (RGB)** se eligen tres canales del cubo para los canales rojo, verde y azul. Es falso color de visualización: cada canal tiene su propia normalización y solo se colorean los píxeles con datos válidos en los tres. No es una medida fotométrica.

Buscador con sugerencias, enlaces compartibles y actualización de observaciones: ver [`RELEASE_READINESS.md`](RELEASE_READINESS.md).

## Localizar una región: Por nombre, Coordenadas o Atlas

Encima de los exploradores, **Localizar una región del cielo** ofrece tres métodos que comparten la misma región (`ra/dec/fov` de la URL) con Time Explorer y Spectrum Explorer. El **Atlas** usa Aladin Lite 3.8.1 con mapas HiPS oficiales servidos por NASA/IPAC IRSA: 2MASS, AllWISE color, W1, W2 y DSS2, cada uno con misión, producto, bandas y época. Arrastre, haga zoom, elija el diámetro (3–30′, círculo amarillo) y pulse **Seleccionar esta región**. Después, **Abrir región en Time/Spectrum Explorer** conserva las coordenadas exactas. Si la vista supera 30′, se avisa y «Ajustar al zoom» propone el máximo, sin recortar en silencio. Gaia DR3 puede superponerse para la región seleccionada. Los mapas son de otras misiones y épocas: no son datos SPHEREx ni una secuencia temporal. El HiPS combinado de SPHEREx DR1 se documenta, pero no se ofrece como capa (ver `PROJECT_STATE.md`).

## Buscar algo que se mueve

Pestaña de Time Explorer. Elija la fuente (objetivo del catálogo, fuente detectada en la época 1 o RA/Dec) y las imágenes: las épocas de la secuencia, o **Ampliar la base temporal** con el mismo detector y 2–8 imágenes por temporada. SkyClues mide la posición de la fuente en cada exposición original con la ePSF oficial y registra cada imagen con estrellas Gaia DR3 estacionarias. Después ajusta una posición por temporada y compara la primera con la última, con incertidumbres calibradas por un control estacionario. Resultados posibles: *Movimiento medido*, *Evidencia insuficiente*, *Observaciones incompatibles* o *Datos insuficientes*. La predicción del catálogo solo se compara al final. Las investigaciones reales (ε Ind B, WISE 0855, Barnard y un control en M101) están en `results/motion_*.json` y se reproducen así:

```bash
.venv\Scripts\python scripts\investigate_motion.py --object "eps Ind B" --detector 3 --name motion_eps_ind_b_d3
```

## Mejora infrarroja

En Time Explorer, pestaña «Secuencia», el interruptor **Mejora infrarroja** combina varias exposiciones reales de SPHEREx del mismo detector para reducir el ruido y distinguir fuentes más débiles. «Qué combinar» ofrece las fechas de la secuencia (misma longitud de onda) o las exposiciones tomadas hasta 7 días antes o después de una de ellas (banda ancha del detector; se descargan de IRSA al pulsar el botón). La pantalla muestra una exposición junto a la combinación, con la misma escala, y la ganancia de señal/ruido **medida** en las fuentes del campo. No es un filtro: no se interpola, rellena ni suaviza nada, y si la combinación no supera sus controles se indica «No disponible para estas observaciones» con el motivo.

Método, resultados con datos reales (M101, WISE 0855−0714, 3I/ATLAS, Juno, Vesta) y límites: [`INFRARED_SNR_REPORT.md`](INFRARED_SNR_REPORT.md). Reproducción:

```
python scripts/validate_enhance.py
```

## Referencias Gaia y AllWISE

En ambos exploradores, abra **Referencias astronómicas · Gaia / WISE** y active el visor. Conserva el centro ICRS y el FOV del explorador; no tiene navegación independiente. **Consultar Gaia DR3** recupera hasta 500 fuentes del archivo ESA (círculo del FOV en J2016.0, orden por magnitud G). Puede pulsar un marcador o elegir su identificador para ver parámetros y unidades. Gaia, posiciones calculadas y AllWISE tienen interruptores independientes dentro del visor; no reconstruyen la imagen SPHEREx. La consulta y la época se actualizan dentro de un fragmento Streamlit.

Los círculos Gaia representan **J2016.0**. Las cruces opcionales corresponden a una posición aproximada para el año juliano TCB elegido (2000–2050), calculada solo con RA/Dec, época y movimiento propio; sin paralaje, velocidad radial, aceleración perspectiva ni incertidumbre propagada. Las fuentes sin movimiento propio no se propagan. La selección no incorpora fuentes que entren en el campo desde fuera después de 2016 y puede truncarse en regiones densas. Ningún marcador constituye una detección o asociación SPHEREx.

AllWISE [W1, ≈3.4 µm](https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/W1/properties) y [W2, ≈4.6 µm](https://irsa.ipac.caltech.edu/data/hips/CDS/AllWISE/W2/properties) son imágenes HiPS auténticas de NASA/IPAC IRSA, distribuidas por CDS, de la era WISE 2010–2011. El suplemento AllWISE describe la combinación de fases criogénica y poscriogénica; las propiedades de estos HiPS incluyen texto temporal genérico de All-Sky y no permiten asignar una época local fiable. Los JPEG son contexto visual, no datos para fotometría. Resolución, bandas y épocas difieren de SPHEREx; no inferir variabilidad por apariencia ni restar imágenes entre misiones. La ausencia en Gaia no descarta una fuente infrarroja (en particular, no se identifica WISE 0855 por proximidad).

El visor usa [Aladin Lite 3.8.1, paquete oficial CDS](https://github.com/cds-astro/aladin-lite/releases/tag/v3.8.1), fijado en jsDelivr, y requiere WebGL2 e Internet en el navegador. La ruta histórica `/AladinLite/api/v3/latest/aladin.js` devolvió 404 durante esta validación. Gaia se consulta en el servidor y se almacena en memoria hasta 12 h, con un máximo de 32 campos; una caída no se interpreta como un catálogo vacío y WISE sigue disponible. Si Aladin falla, se conserva la tabla Gaia. Los servicios externos pueden fallar independientemente; el mensaje de tesela central recibida no garantiza la carga de todas las teselas del mosaico.

## Pruebas

```bash
.venv\Scripts\python -m pytest -m "not network" -q
.venv\Scripts\python -m pytest -q
.venv\Scripts\python scripts\validate_spectrum.py
.venv\Scripts\python scripts\validate_references.py
.venv\Scripts\python scripts\validate_multiband.py
```

`tests/test_motion.py` contiene experimentos **sintéticos**, identificados como tales, del método de movimiento; tarda unos 5 minutos. `tests/test_motion_app.py` incluye una reproducción real marcada `network`.

Las pruebas `network` usan FITS locales o NASA/IPAC IRSA y requieren que el servicio correspondiente esté disponible. Las offline aíslan la caché y usan cubos sintéticos identificados como pruebas. `requirements-dev.txt` incorpora Photutils y astropy-healpix como verificadores independientes, sin añadirlos al runtime. La prueba del reproductor requiere Node.js. El script reproduce la extracción del tutorial (apertura 5 px, anillo 40–60 px), contrasta valores y metadatos, comprueba recursos y escribe `results/spectrum_validation.json`.

Para buscar una secuencia reproducible de N épocas comparables:

```bash
.venv\Scripts\python scripts\find_sequence.py --ra 210.802429 --dec 54.34875 --field 0.1 --name sequence_m101
```

## Despliegue (Streamlit Community Cloud) — preparado, no publicado

- Punto de entrada: `app.py` en la raíz. Dependencias de ejecución: `requirements.txt` (solo runtime; las de desarrollo están en `requirements-dev.txt`). Configuración: `.streamlit/config.toml`.
- Versión de Python: se elige en *Advanced settings* al desplegar. Se recomienda 3.11, la versión de desarrollo. También se ha probado una instalación limpia con 3.14.
- La app escribe en `data/cache/` (FITS de IRSA, sin modificar) y en `results/search_*.json`. En Community Cloud ese disco no es persistente: tras un reinicio, los recortes se vuelven a descargar.
- `data/reference/` contiene los FITS de los ejemplos validados (6 archivos, 24 MB, idénticos a los recortes de IRSA; procedencia y SHA-256 en `data/reference/MANIFEST.json`), para que se abran sin depender de IRSA. `python scripts/bundle_reference.py` los regenera desde la caché o IRSA y nunca sobrescribe un archivo existente.

Datos: [NASA/IPAC IRSA](https://irsa.ipac.caltech.edu/Missions/spherex.html), SPHEREx DR1 Spectral Images ([doi:10.26131/IRSA678](https://doi.org/10.26131/IRSA678)), DR1 All-Sky Cube ([doi:10.26131/IRSA679](https://doi.org/10.26131/IRSA679)) y QR3. [Documentación del archivo](https://caltech-ipac.github.io/spherex-archive-documentation/).

Contexto y estado del proyecto: [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) · [`PROJECT_STATE.md`](PROJECT_STATE.md).
