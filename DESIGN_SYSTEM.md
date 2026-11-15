# SkyClues — decisiones de diseño que deben conservarse

Actualizado: 14-11-2026. Lectura obligatoria para cualquier agente antes de modificar la interfaz, según `AGENTS.md` y petición expresa del usuario. Este documento recoge el diseño existente de Claude B y las correcciones solicitadas después; no autoriza un rediseño integral.

## Identidad y estructura

- Página clara, fondo blanco, tinta casi negra, líneas finas y espacio suficiente. Mantener logotipo y recursos de `assets/brand/`.
- Tipografía: **Newsreader** en títulos; **IBM Plex Sans** en interfaz y texto; **IBM Plex Mono** en coordenadas, cifras y tablas. Los iframes deben usar las mismas fuentes y alternativas.
- Paleta compartida (`skyclues/theme.py`): tinta `#14171c`, texto secundario `#5b6470`, auxiliar `#8a929c`, líneas `#e3e6ea`, superficie `#f6f7f8`, acento terracota `#c4411c`.
- Acción principal negra; secundarias blancas con borde fino. Terracota para selección, actividad y pequeños acentos. Evitar el azul genérico de botones del navegador.
- El azul de los marcadores Gaia y el naranja del campo son códigos del mapa, no una nueva paleta global. Los colores científicos de datos/máscaras se conservan con sus significados.
- Navegación: **Región / Tiempo / Espectro**. Región integra nombre, RA/Dec, FOV y Atlas. Tiempo y Espectro son los dos exploradores. RGB es una representación dentro de Espectro, nunca otra página.
- Un único buscador universal. No añadir selectores por catálogo, paneles permanentes ni confirmaciones para acciones ordinarias.
- El desplegable consulta los catálogos mientras se escribe; el índice local solo ofrece coincidencias inmediatas. Mostrar el identificador que coincide con la búsqueda y distinguir homónimos (por ejemplo, cometa 3I/ATLAS y satélite Atlas). La espera de sugerencias es compacta junto al campo, nunca un velo sobre toda la página. No dejar el mensaje de espera visible después de seleccionar.

## Sencillo y Científico

La petición del usuario es reducir el lenguaje científico y el texto pequeño en **Sencillo**, no trasladar párrafos largos a un montón de desplegables.

**Sencillo**:

- Priorizar imagen, acción y resultado. Una instrucción breve cerca del control cuando haga falta.
- Decir «fecha», «imagen», «brillo», «zona del cielo» o «colores infrarrojos» cuando basten.
- Evitar fórmulas, detalles FITS/WCS, siglas internas, ETag, SHA-256, métodos de extracción, tablas de calidad y explicaciones repetidas de rigor.
- Reservar el texto pequeño para etiquetas y una procedencia corta; no usarlo para largos bloques de lectura.
- Conservar avisos esenciales, en lenguaje corriente: falta de datos, falso color, resultados no concluyentes y que una posición de catálogo no confirma una detección SPHEREx.
- No ocultar unidades necesarias de una medición ni volver engañosos los gráficos por simplificarlos.

**Científico**:

- Presentar época y sistema de coordenadas, procedencia, unidades, parámetros, métodos, máscaras, limitaciones, tablas y descargas reproducibles.
- Mantener accesible todo el rigor que se retire de Sencillo.
- Cambiar de nivel solo cambia presentación. Conservar selección, FOV, canal, posición, apertura, escala, datos y resultados. Los controles avanzados ocultos conservan su valor; no reiniciarlos ni usar otro cálculo.

## Cargas: dos intensidades, según el contexto

No aplicar una pantalla opaca a absolutamente todo. Decisión explícita del usuario: elegir dónde ayuda.

1. **Consulta Gaia y arranque del Atlas**: cubrir el área del mapa con vidrio esmerilado, indicador grande centrado y tarjeta pulida. El cielo debe seguir reconociéndose detrás, desenfocado: **no sustituirlo por un fondo gris uniforme**. Usar desenfoque y una película casi transparente (no un velo de alta opacidad). Los controles siguen disponibles; `pointer-events: none` conserva desplazamiento y zoom. Desaparece automáticamente al terminar.
2. **Preparación de productos principales** (imagen, espectro, RGB, secuencia/investigación): usar `theme.loading(...)`, una tarjeta amplia de actividad en el área de trabajo. No cubrir toda la navegación. Mantener visibles las fases útiles del proceso.
3. **Acciones breves o secundarias** (nombre, alias, fecha, referencias y ajustes): indicador compacto. Sin velos para cada clic o cambio de control.

- Actividad indeterminada cuando no existe progreso medible. Nunca inventar porcentajes.
- Tiempo transcurrido real; fases reales. Progreso por archivos solo si se conoce terminados/total.
- Evitar parpadeo en caché: respetar el retraso breve del spinner nativo; no añadir esperas para mostrar la animación.
- Al cambiar de región, ignorar resultados antiguos. Un campo vacío se comunica como vacío; un fallo permite reintentar sin convertirlo en una nueva pantalla.
- Respetar `prefers-reduced-motion`. No esconder la actividad si se desactiva el giro: texto y estado deben bastar.

## Controles, mapas y ciencia

- El reproductor mantiene una fila clara Anterior / Reproducir / Siguiente, deslizador terracota, Blink integrado y tabla contenida. No volver a cajas grises pesadas ni controles azules.
- El círculo del Atlas es el FOV científico. Zoom, orientación y redimensionamiento no lo cambian. Nombre, coordenadas, URL y selección tienen una sola fuente de estado.
- Gaia: conservar el `source_id` como texto. Un alias comprobado acompaña al identificador, no lo reemplaza. J2016.0 y predicciones por fecha no son observaciones SPHEREx.
- Constelaciones: figuras tradicionales y nombres, ocultas a escalas pequeñas; no llamarlas límites IAU.
- RGB: falso color, con asignación de canales. Rosa/morado rayado indica que falta dato en alguna banda; morado sin rayado puede ser un color válido. No interpolar ni cambiar máscaras para que la imagen parezca más bonita.
- Resultados vacíos o no concluyentes deben seguir siendo distinguibles de detecciones. Simplificar la prosa no modifica la ciencia.

## Implementación y comprobación

Puntos compartidos: `theme.py`, `region_component.css`, `region_component.js`, `player.py`. Reutilizar antes de crear variantes. Los iframes necesitan estilos propios coherentes porque no heredan el tema.

Antes de entregar una modificación visual:

- Revisar la zona en navegador, en Sencillo y Científico, y en anchura reducida si cambia la disposición.
- Verificar que no aparece desplazamiento horizontal de toda la página ni se recortan acciones importantes.
- Comprobar las transiciones de carga, listo, vacío y fallo afectadas, sin pedir tráfico remoto por cada marcador.
- Ejecutar las pruebas relevantes, incluyendo conservación de estado al cambiar de nivel. No reemplazar las pruebas científicas con comprobaciones solo visuales.
- Guardar evidencia visual y actualizar el estado del proyecto. No afirmar comprobaciones no ejecutadas.
