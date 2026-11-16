# SkyClues — decisiones de diseño que deben conservarse

Actualizado: 14-11-2026. Lectura obligatoria para cualquier agente antes de modificar la interfaz, según `AGENTS.md` y petición expresa del usuario. Este documento recoge el diseño existente de Claude B y las correcciones solicitadas después; no autoriza un rediseño integral.

## Identidad y estructura

- Página clara, fondo blanco, tinta casi negra, líneas finas y espacio suficiente. Mantener logotipo y recursos de `assets/brand/`.
- Fondo de página (decisión del usuario, 15-11-2026): placa astronómica en negativo y estilizada, con estrellas oscuras sobre papel claro, como en los atlas fotográficos impresos. Generada de forma determinista en `theme._plate_stars`. Es inventada y no representa ninguna región real. Se compone de puntos finos, algunas estrellas medianas, pocas brillantes con halo y anillo tenues y un cúmulo suave abajo a la izquierda, lejos del motivo del encabezado y su anillo cobrizo. Debe seguir siendo textura, nunca protagonista: el usuario pidió bajar su opacidad, y el grupo de estrellas usa 0,45. Mapas, imágenes y gráficos conservan su propio fondo opaco para que no se confunda con datos.
- Selector de nivel (decisión del usuario, 15-11-2026): es un interruptor de verdad, «Sencillo ⟷ Científico». Pulsar la palanca alterna el nivel, y pulsar el texto de la otra opción también. La pista forma parte del botón de la opción no activa; no puede ser un pseudoelemento, porque el componente solo acepta la pulsación dentro del rectángulo del botón.
- Tipografía: **Newsreader** en títulos; **IBM Plex Sans** en interfaz y texto; **IBM Plex Mono** en coordenadas, cifras y tablas. Los iframes deben usar las mismas fuentes y alternativas.
- Paleta compartida (`skyclues/theme.py`): tinta `#14171c`, texto secundario `#5b6470`, auxiliar `#8a929c`, líneas `#e3e6ea`, superficie `#f6f7f8`, acento terracota `#c4411c`.
- En etiquetas en mayúsculas (`sc-eyebrow`, `sc-facts dt`), unidades y símbolos van en `theme.unit(...)` (clase `sc-unit`): «µm» y «λ» nunca se convierten en «MM» o «Λ».
- Diagnóstico de calidad por canal (Espectro): vive en el inspector del intervalo examinado y en una sección plegable («¿Por qué faltan algunos colores?» en Sencillo; «Calidad de los canales: cobertura de la apertura y máscaras» en Científico), nunca en el gráfico. Las causas (sin datos, BLOOM, OVERFLOW, apertura incompleta…) pueden coexistir y no se presentan como categorías excluyentes. Sencillo usa una frase corta, sin términos de máscara; Científico, una tabla con anchos fijos (sin columnas cortadas).
- Las notas bajo los gráficos de Espectro se muestran con el gris secundario a opacidad completa (Streamlit atenúa `st.caption` al 60 %). Ámbito: contenedores `sx_points`, `sx_analysis` y `sx_notes_*`; no es un cambio global.
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
- Mapas de campo de Espectro, «Un canal» (incluida la comparación A/B) y la composición RGB (15-11-2026): son cuadrados de tamaño fijo, con la misma extensión ±R″ en ambos ejes.
  - Nunca derivar un dominio de `height/width` del navegador. Si el gráfico se crea con la columna sin anchura, ese dominio sale infinito y el panel queda vacío.
  - En pantallas estrechas el gráfico se desplaza dentro de su propia caja (`st-key-sx_field_box`, `st-key-mb_field_box`) y no se escala. Así los tooltips y el clic siguen señalando el píxel correcto.
- RGB, «Mismo contraste»: conserva una única escala física para los tres canales y nunca se sustituye por escalas independientes. Si al menos la mitad del campo queda casi negra (los tres colores por debajo del 10 % de la escala), se avisa de que es la consecuencia física de la escala común, no un fallo ni falta de datos, y se remite a «Resaltar cada color». En Sencillo con una frase llana; en Científico con la fracción y los límites en MJy/sr.
- Resultados vacíos o no concluyentes deben seguir siendo distinguibles de detecciones. Simplificar la prosa no modifica la ciencia.

## Objetos conocidos en movimiento: Time Explorer

- El buscador existente conserva la identidad del cuerpo. Tiempo adapta su búsqueda a la trayectoria; no crear un explorador ni un buscador nuevos. El Atlas y Espectro conservan su región. El centro de referencia del buscador no se reescribe al avanzar cada fotograma; las posiciones previstas por exposición se identifican aparte.
- Usar el reproductor, controles y paleta compartidos. Cuando las imágenes están preparadas, fechas y selección quedan en «Observaciones y fechas»; la imagen y el resultado ocupan el área principal. Si solo hay una representación válida, no dibujar un selector sin alternativas.
- Cruz terracota = posición prevista; **anillo blanco = posición medida en los píxeles** (nunca se dibuja sin medida); rosa = píxel enmascarado; lila = fuera de cobertura. Dentro del anillo se muestran los píxeles del propio objeto, que la cadena oficial marca como atípicos por no estar en su catálogo; fuera se conserva la máscara estricta. Los píxeles originales se dibujan mediante WCS; una región sin cobertura no es una observación negra. Los apilamientos se identifican como remuestreados.
- Un solo selector «Qué comparar»: *Movimiento* (imágenes del mismo detector con horas de diferencia sobre el mismo cielo; primera opción cuando el archivo lo permite) o una banda (misma longitud de onda, para comparar brillo). No añadir botones técnicos para medir: la medición se hace al preparar las imágenes.
- Con movimiento medido se muestran cuatro cifras (desplazamiento ± error, intervalo, ritmo, estrellas de control) con `theme.facts` y una frase llana en Sencillo; Científico añade posiciones, pruebas y comparación con la efeméride. En la secuencia de movimiento la vista inicial es «Fondo estelar fijo» y se avisa de que el brillo entre longitudes de onda distintas no es comparable.
- No presentar una animación cuando alguna imagen carece de señal candidata o de posición medida: conservar revisión Anterior / Siguiente. «Seguir al objeto» describe el centrado calculado, nunca movimiento medido. Sin solapamiento suficiente, no ofrecer un fondo fijo engañoso.
- Sencillo conserva el estado, fechas y avisos esenciales de confusión/cobertura. Científico añade λ, detector, calibración, fondo, máscaras, controles, originales y reporte. Las advertencias de la misma selección se agrupan, no se convierten en múltiples paneles permanentes.
- Cargas con `theme.loading`, fases reales y sin porcentajes inventados. Cachés de análisis/render incluyen la versión del código dependiente para evitar resultados obsoletos después de cambios de implementación. Conservar filtros, fechas y resultados al cambiar de nivel o navegar.

## Espectro: «¿Qué podría indicar este espectro?»

- Una sola sección dentro de Espectro, después del análisis de picos y valles y antes de la calidad de los canales. No es un explorador nuevo. Mismos datos, veredicto y referencias en los dos niveles: el nivel solo cambia cuánto se explica.
- Cinco veredictos fijos, con `theme.badge`:
  - «Referencia compatible»;
  - «Varias referencias compatibles»;
  - «Coincidencia insuficientemente respaldada»;
  - «Ninguna referencia compatible»;
  - «No evaluable».
  
  Tonos del tema: `sc-ok` para los dos primeros, `sc-warn` para la coincidencia insuficiente y neutro para los otros dos. No hay porcentajes ni puntuaciones, porque no existe un modelo calibrado que los respalde.
- Sin selección, una fila por pico o valle con su veredicto y un botón «Examinar» que fija el mismo intervalo que el inspector. Con selección, cada espectro (A y B) se explica por separado, nunca su diferencia.
- **Sencillo:** tres frases, en este orden:
  1. qué observamos («Detectamos un exceso de emisión cerca de 3,3 µm»);
  2. qué podría representar, siempre en condicional y nombrando las alternativas;
  3. «Qué impide estar seguros».
  
  Nunca escribir «hemos encontrado X». Sin tablas.
- **Científico:** `theme.facts` con λ observada, detector y R, z con su fuente, y la clase del dato. Debajo, una tabla con estas columnas: Referencia, Tipo, λ en reposo, λ esperada, Canal previsto, Compatibilidad, z para la que se mantiene, Motivo. «Qué impide la certeza» se muestra siempre. Condiciones, confusiones, bibliografía, método y biblioteca van en plegables.
- Marcas de referencia en el gráfico: interruptor apagado por defecto y persistente entre niveles (`opt_sx_refs`).
  - Cada marca es una regla vertical punteada, fina y gris; se resaltan en terracota las referencias que coinciden con la selección.
  - Solo esas llevan una etiqueta, que es única y combinada (p. ej. «PAH 3,3 · Pfδ»). Las demás muestran su nombre solo en el tooltip.
  - No se dibujan bandas ni perfiles inventados.
- Un desplazamiento al rojo solo se muestra con su fuente (NED y la galaxia cuya isofota contiene la apertura). Si no se conoce, se dice «desconocido» y se compara en reposo.

## Mejora infrarroja: Time Explorer

Propuesta por el usuario (actividad `SKYCLUES_SPHEREX_INFRARED_SNR_ENHANCEMENT_01`). No es un explorador ni una pestaña: es un interruptor **«Mejora infrarroja»** en la pestaña «Secuencia», junto a las opciones existentes y visible en los dos niveles. Apagado, la secuencia y el reproductor quedan exactamente como estaban.

- Encendido, el área del reproductor muestra dos imágenes con la misma rejilla y la **misma escala de brillo**: «Una exposición» y «Combinación · N exposiciones». Rosa = sin dato válido, como en el resto de la aplicación. Los círculos terracota señalan las fuentes que solo se detectan en la combinación.
- Un único selector **«Qué combinar»**: las fechas de la secuencia (mismo canal; inmediato) o las exposiciones próximas a una de sus fechas (mismo detector, ±7 días; banda ancha; requiere pulsar «Buscar y combinar»). No añadir controles de método, pesos ni umbrales.
- Cuatro estados, con `theme.badge`: *Disponible*, *Procesando* (`theme.loading`, sin porcentajes), **Imagen mejorada** y **No disponible para estas observaciones**, siempre con el motivo. Una combinación que no supera sus controles nunca se presenta como mejora; en Científico su imagen queda en un desplegable de diagnóstico.
- Sencillo: tres cifras (imágenes combinadas, mejora de la señal, puntos distinguibles) y dos frases llanas; avisa de que una imagen de banda ancha no sirve para comparar brillo. Científico: exposiciones, detector y λ, intervalo, ganancia S/N medida, ruido por píxel, tabla de exposiciones con procedencia, controles (imagen nula, resolución, posiciones, flujo) e informe JSON.
- La cifra del objetivo solo aparece cuando es débil en una exposición (S/N < 30): en fuentes brillantes no describe la mejora.
- El nivel no cambia el producto: ambos leen la misma combinación en caché. La opción y la selección se conservan al cambiar de nivel o navegar. La imagen combinada no interviene en «Movimiento».
- Al cambiar de región o de secuencia, «Qué combinar» vuelve a las fechas de la nueva secuencia: una fecha elegida en otra región nunca se arrastra.
- Los círculos solo se llaman «fuentes» cuando la imagen nula tiene menos picos espurios que fuentes nuevas hay; si tiene tantos o más, el texto dice que no se distinguen del ruido y que no son detecciones. Junto a la ganancia, una frase breve explica qué significa: en Sencillo, cuántas veces más destacan los mismos objetos sobre el ruido; en Científico, a cuántas veces más tiempo de exposición equivale.

## Implementación y comprobación

Puntos compartidos: `theme.py`, `region_component.css`, `region_component.js`, `player.py`. Reutilizar antes de crear variantes. Los iframes necesitan estilos propios coherentes porque no heredan el tema.

Antes de entregar una modificación visual:

- Revisar la zona en navegador, en Sencillo y Científico, y en anchura reducida si cambia la disposición.
- Verificar que no aparece desplazamiento horizontal de toda la página ni se recortan acciones importantes.
- Comprobar las transiciones de carga, listo, vacío y fallo afectadas, sin pedir tráfico remoto por cada marcador.
- Ejecutar las pruebas relevantes, incluyendo conservación de estado al cambiar de nivel. No reemplazar las pruebas científicas con comprobaciones solo visuales.
- Guardar evidencia visual y actualizar el estado del proyecto. No afirmar comprobaciones no ejecutadas.

## Ejemplo destacado y explicaciones de saturación (16-11-2026)

- **Ejemplo destacado (3I/ATLAS):** una sola fila bajo la cabecera de Región, con filete fino arriba y abajo, texto y un botón primario negro. Sin tarjeta, sin insignia en píldora. Es el resultado más fuerte del proyecto y debe verse sin desplazarse. En Sencillo explica en una frase qué es (cometa que viene de fuera del Sistema Solar); en Científico, qué mide.
- **Saturación:** se explica solo cuando una medida lo respalda (píxeles BLOOM/OVERFLOW/NONLINEAR). Nota sobria (`theme.note`) justo bajo el gráfico o el resumen, con la salida práctica («press another point», «move the map»). Nunca se afirma saturación sin esa medida, ni se rellenan píxeles.
- **Indicador de carga:** `sc_loading_*` es pegajoso arriba y abajo; una espera larga siempre queda a la vista.
- **Todo el texto visible de la versión final es inglés.**
