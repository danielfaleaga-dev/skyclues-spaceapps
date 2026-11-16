# SkyClues — evaluación final de experiencia real

Fecha: 15-11-2026 · Versión evaluada: `SkyClues-ux`, rama `ux/redesign-v1`, commit `c66d176`, servida en local (puerto 8524) con servicios reales de IRSA, Horizons y SIMBAD.
Modalidad: visita directa en navegador, sin cambiar código. La perspectiva del principiante es una **evaluación heurística**, no una prueba con personas externas.

**Recorrido realizado**

- **Región:** portada; búsqueda de «nebulosa de Orión» (M42) y de «3I/ATLAS»; atlas.
- **Tiempo:**
  - M42: secuencia, «Calidad» en los dos niveles y «Movimiento»;
  - 3I/ATLAS: búsqueda de observaciones a lo largo de su trayectoria y movimiento medido;
  - ejemplo M101 y «Mejora infrarroja».
- **Espectro:** M42 y M101 («Un canal», punto elegido, espectro, intérprete y RGB).
- **Niveles:** Sencillo y Científico, con cambios de nivel durante la visita.
- **Pantalla estrecha:** portada a 375 px.

**No comprobado:**
- funciones que dependen de Gaia (ESA Gaia no respondía hoy);
- Vesta;
- comparación A/B;
- «Procedencia» y «Compartir»;
- Tiempo y Espectro en móvil.

---

## A. Primera impresión

La portada se entiende en pocos segundos:
- un titular claro («¿Qué zona del cielo quieres investigar?»);
- una frase que dice qué es (observaciones infrarrojas reales de SPHEREx, de la NASA);
- tres pasos numerados: buscar, ver si algo cambia, ver qué luz emite.

El buscador acepta nombres en español («nebulosa de Orión») y el atlas da contexto visual inmediato. Un aviso aclara que el mapa de referencia «no son datos SPHEREx», y eso transmite rigor desde el primer momento.

**Sensación general:** parece una aplicación terminada, con identidad propia. No parece una colección de componentes.

**Lo que no transmite la portada:** el mejor resultado del proyecto. Los dos ejemplos son M101 y WISE 0855; ninguno enseña algo que se mueva de forma espectacular. Que SkyClues mide el movimiento de un cometa interestelar real (3I/ATLAS) en datos de SPHEREx no aparece en ningún sitio hasta que alguien lo busca por su nombre.

## B. Experiencia de una persona casual

**Lo que funciona especialmente bien**

- **Textos de Sencillo.** Son cortos, con un lenguaje cercano y casi siempre correctos. Ejemplos: «No hay imágenes inventadas entre medias», «Un parpadeo no basta», «las marcas rosas son colores sin datos, no luz cero».
- **Navegación.** Región → Tiempo → Espectro es evidente, y la región se conserva al cambiar de vista y de nivel. El punto elegido también se conservó al pasar de Científico a Sencillo.
- **3I/ATLAS en Tiempo.** Es la experiencia más memorable:
  - busca 160 exposiciones a lo largo de la trayectoria;
  - muestra «Movimiento observado: 166″ ± 3″ en 99 min» con 16 estrellas de control;
  - al pasar de la imagen 1 a la 5 se ve cómo el círculo cruza el campo.
- **RGB.** Explica en lenguaje llano que es falso color y que «hay zonas demasiado brillantes para el detector».

**Lo que cuesta entender o bloquea**

1. **En Espectro (Sencillo) no se puede elegir otro punto.** El texto dice «Pulsa la imagen para elegir un punto», pero el clic no hace nada. Lo comprobé seis veces, en dos regiones y en una sesión recién abierta; en Científico el mismo clic sí funciona. El visitante queda atado al centro de la región.
2. **Los objetos famosos y brillantes salen vacíos sin explicación.**
   - M42 en Tiempo: el núcleo es una gran mancha rosa con la leyenda «Rosa: sin datos». «Calidad», en Sencillo, solo dice «Consulta el modo Científico para conocer los motivos».
   - M42 en Espectro: el punto por defecto da un espectro vacío, con 100 de 102 colores sin datos y el mensaje «no hay nada que interpretar».
   - En ningún caso se le dice al visitante que la nebulosa es *demasiado brillante* (saturación) ni que pruebe otro punto. Por el punto 1, en Sencillo además no podría hacerlo.
3. **Esperas largas sin orientación.** Al pulsar «Ver en el tiempo» la vista se queda a media página, sobre la Región atenuada, y el indicador de carga queda fuera de la pantalla, arriba. La búsqueda de M42 tardó unos 55 s.
4. **El intérprete casi nunca dice nada.** En M42 y en el núcleo de M101 responde «no hay nada que interpretar». Si se pulsa el punto más alto de la curva de M101, contesta que «no destaca sobre los colores vecinos». Es correcto, porque es un máximo ancho del continuo y no una línea, pero un principiante no lo entiende.
5. **Detalles que piden conocimiento previo:**
   - flujo negativo en el espectro de M42, sin explicación;
   - segundos de arco (″) y «″/h» sin explicar en Sencillo;
   - «IMAGE − ZODI [MJy/sr]» en los ejes del reproductor de Tiempo, también en Sencillo.

**Respuesta a la pregunta principal:** con un objeto «agradecido» (M101, 3I/ATLAS) sí, un visitante explora, disfruta y se lleva algo verdadero. Con un objeto brillante y famoso (M42), que es justo lo que muchos buscarán primero, se encuentra manchas rosas, un espectro vacío y ninguna salida en Sencillo.

## C. Perspectiva del especialista

**Convincente:**
- distingue sistemáticamente catálogo, predicción y observación («La cruz marca una posición calculada, no una detección»; atlas «no son datos SPHEREx»);
- muestra la procedencia: DR1, calibración v27, detector, λ efectiva y estrellas de control;
- usa veredictos cualitativos y no probabilidades;
- reconoce lo que no puede medir.

**El caso de 3I/ATLAS es sólido:**
- desplazamiento con su incertidumbre;
- registro con estrellas estacionarias (≤ 0,7″);
- un aviso explícito de que las imágenes tienen λ distintas, así que la posición es comparable pero el brillo no.

**El caso de la estrella de Barnard demuestra honestidad.** El resultado guardado da «Evidencia insuficiente» por núcleo saturado y posible confusión, aunque el ajuste alcanza 20σ, y lo explica. Un investigador lo valora.

**El espectro de M101 es físicamente correcto:** el máximo cerca de 1,6 µm corresponde a la población estelar vieja. Los datos sin precaución y los OVERFLOW se marcan aparte.

**Dudas o presentaciones mejorables (ninguna invalida el producto):**
- **Flujo negativo.** En M42 la apertura da unos −500 mJy en 0,8–1,7 µm, porque el anillo de fondo es más brillante que la apertura en emisión extendida. Es esperable, pero no se advierte en ningún nivel.
- **Cifras no validadas con tipografía de titular.** «Desplazamiento aparente (no validado) 15,13″» y «20,4σ» aparecen con el mismo tamaño que un resultado válido; el descargo va en texto pequeño.
- **M42 tratado como objeto en movimiento.** En Científico, M42 aparece como «Objetivo en movimiento (0,00″/año)», con URL y fecha ISO en línea. Es inofensivo, pero chirría para una nebulosa.
- **Paso entre detectores.** Hay un pequeño escalón de flujo entre D3 y D4 (≈ 2,4 µm) en el espectro de M101. Es propio de la extracción entre detectores; podría mencionarse en Científico.

**Veredicto del especialista:** dentro de su alcance es una herramienta seria y honesta. La medida de movimiento con controles es lo de mayor valor; los espectros son exploratorios, y la aplicación lo dice.

## D. Perspectiva del juez de NASA Space Apps

**Qué se entiende rápido:** es un explorador de datos reales de SPHEREx, con tiempo, espectro y una identidad cuidada.

**Qué lo distingue de un visualizador:**
- mide movimiento con incertidumbres y controles;
- busca observaciones a lo largo de la trayectoria de un cuerpo del sistema solar;
- distingue observación de predicción;
- dice cuándo no se puede concluir.

**Qué debilita la presentación hoy:**
- **El resultado estrella está escondido.** 3I/ATLAS, conectado con *Planet X*, no aparece en la portada ni en los ejemplos.
- **Los primeros intentos naturales pueden decepcionar.** Un objeto brillante da manchas rosas y un espectro vacío, y el intérprete casi nunca encuentra nada.
- **Un fallo visible en Científico.** La pestaña «Calidad» muestra una traza de Python con rutas locales y enlaces «Ask Google / Ask ChatGPT». Un juez que la abra se lleva una impresión de producto inacabado.

**Calidad frente a opciones de premio.** El producto tiene calidad real y rigor poco habitual en un hackathon. Sus opciones dependen de que la presentación (vídeo y portada) lleve directamente a 3I/ATLAS. No he visto otras candidaturas, así que no comparo.

## E. Diseño y experiencia global

- **Identidad:**
  - paleta monocroma con un único acento cobre;
  - IBM Plex;
  - el anillo cobre como motivo, que reaparece en el atlas, en los gráficos y en la cabecera;
  - fondo de placa estelar en negativo, discreto.

  Tiene personalidad propia y aspecto científico profesional.
- **Jerarquía:** clara. Las cabeceras de sección, las cifras clave en tarjetas y las tres columnas «Qué estás viendo / Cómo compararlas / ¿Algo se mueve?» funcionan muy bien.
- **Coherencia:** Región, Tiempo y Espectro comparten cabecera, franja de región y tipografía. La excepción es el reproductor de movimiento de 3I/ATLAS:
  - va en un marco con desplazamiento propio;
  - tiene los controles debajo de la imagen y media pantalla vacía a la derecha;
  - por eso no se parece al reproductor principal, que lleva los controles al lado.
- **Visualizaciones:** son correctas y legibles. El rosa de «sin datos» es muy llamativo y domina las imágenes saturadas (M42). Cumple su función de aviso, pero choca con la paleta sobria.
- **Interacción:**
  - la rueda del ratón sobre el atlas acerca el mapa en lugar de desplazar la página, y el atlas ocupa media pantalla;
  - el interruptor Sencillo/Científico funciona y conserva el estado.
- **Pantalla estrecha:** la portada se ve bien a 375 px, sin desplazamiento horizontal.

**Conclusión:** se siente como un producto terminado y atractivo, salvo por los dos fallos funcionales de la sección F.

## F. Problemas encontrados

### Imprescindible corregir

1. **Espectro, Sencillo: el clic sobre la imagen no elige el punto.**
   - **Qué pasa:** Vega registra la selección (comprobado en la página), pero la posición no cambia. En Científico funciona.
   - **Causa probable:** `skyclues/spectrum_page.py:259`. `multiband_page.restore(SINGLE_STATE_KEYS)` repone en cada ejecución la copia guardada de `sx_pick_ra/dec`, que en Sencillo se vuelve a guardar en la línea 261. Así machaca la posición que acaba de fijar el clic.
   - **Impacto:** en el nivel pensado para el público solo se puede ver el espectro del centro. Con objetos saturados (M42) eso significa quedarse con un espectro vacío sin salida.
2. **Tiempo › Calidad, Científico: falla «Cobertura y longitud de onda».**
   - **Qué pasa:** aparece `AttributeError: 'function' object has no attribute 'figure_png'`.
   - **Causa confirmada:** en `skyclues/time_page.py:235`, `def render(level)` tapa el módulo `render` importado en la línea 17, y la línea 455 lo usa.
   - **Impacto:** ocurre con cualquier secuencia (visto con M42).
3. **Las trazas de error son visibles para el público.**
   - **Qué pasa:** `.streamlit/config.toml` no define `[client] showErrorDetails`. Cualquier excepción muestra la traza con rutas locales (`C:\Users\…`) y enlaces externos.
   - **Impacto:** en una demostración pública expone detalles internos y da impresión de producto inacabado.

### Conveniente mejorar

4. **3I/ATLAS no es visible.**
   - No figura en la portada ni en los ejemplos.
   - El buscador lo muestra como «ATLAS (C/2025 N1)» y pierde la designación «3I» por la que se le conoce.
   - Sencillo no dice qué es (un cometa interestelar).
5. **Saturación sin explicar en Tiempo y en Espectro (Sencillo).**
   - El rosa del núcleo de M42 y el espectro vacío no dicen «demasiado brillante para el detector», ni sugieren elegir otro punto u otro color.
   - El RGB sí lo explica: falta coherencia entre vistas.
6. **Indicador de carga fuera de la vista.** Al pasar de Región a Tiempo la vista no sube al indicador. Durante ~55 s se ve la Región atenuada, y parece que la aplicación no responde.
7. **El intérprete apenas habla.** Ni en M42 ni en M101 señala nada. Al pulsar el máximo ancho de M101 responde «no destaca», sin explicar qué es un continuo. Bastaría con una frase sobre picos anchos frente a estrechos.
8. **Flujo negativo** en el espectro (M42) sin una nota que lo explique.
9. **Reproductor de 3I/ATLAS:**
   - desplazamiento dentro de otro desplazamiento;
   - controles bajo la imagen;
   - disposición distinta del reproductor principal.
10. **«Investigaciones reales guardadas»:**
    - nombres internos (`barnard_d1`, `eps_ind_b_d2`) y la ruta `results/motion_*.json`;
    - cifras no validadas con tipografía de titular.

### Detalle menor

11. La rueda del ratón sobre el atlas hace zoom en lugar de desplazar la página.
12. El texto del marcador dice «rombo naranja» (Sencillo) y «rombo ámbar» (Científico); el marcador se dibuja negro con anillos cobre.
13. Mezcla de «tú» y «usted» en Sencillo (por ejemplo, «repita la búsqueda más tarde» junto a «Busca un nombre»).
14. En Sencillo, «La cruz marca una posición calculada» aparece en M42 sin que el visitante sepa a qué cruz se refiere.
15. «Mejora infrarroja» en M101: «×1,9» de mejora, pero «7 puntos distinguibles, 7 en una sola imagen». No se explica por qué no aparecen puntos nuevos.

## G. Valoración final

| Aspecto | Nota | Justificación |
|---|---|---|
| Facilidad de uso para principiantes | **6/10** | Textos y navegación excelentes. Pero en Espectro no se puede elegir punto en Sencillo, los objetos brillantes salen vacíos sin explicación y las esperas son largas. |
| Claridad científica | **8,5/10** | Separa con rigor observación, predicción e interpretación; la procedencia está completa y las limitaciones se reconocen. Faltan notas sobre flujo negativo y saturación. |
| Diseño e identidad visual | **8/10** | Identidad propia, coherente y profesional. El reproductor de movimiento y el rosa dominante desentonan. |
| Utilidad e interés del producto | **7,5/10** | Medir el movimiento de 3I/ATLAS en datos reales es valioso y poco común. El espectro aporta menos de lo que promete al visitante. |
| Impresión como candidatura NASA Space Apps | **7/10** | Hoy. Con los tres arreglos de abajo y 3I/ATLAS al frente, subiría con claridad. |

**1. ¿Está listo para mostrarse públicamente como producto terminado?**
Todavía no. Los fallos 1–3 son visibles en un recorrido normal: el visitante no puede elegir punto en Sencillo, y Científico muestra una traza de Python. Son correcciones acotadas.

**2. ¿Una persona casual puede utilizarlo y comprender sus resultados?**
Sí con objetos favorables (M101, los ejemplos, 3I/ATLAS), donde los textos de Sencillo están entre lo mejor del producto. No con objetos brillantes, en los que hoy se queda sin explicación y sin salida.

**3. ¿Un especialista en SPHEREx consideraría que ofrece valor científico real?**
Sí, dentro de su alcance:
- la medida de movimiento con registro y controles estacionarios;
- la procedencia exhaustiva;
- la negativa a concluir sin evidencia.

Los espectros son exploratorios, y la aplicación lo declara.

**4. ¿Tiene calidad suficiente para competir seriamente en NASA Space Apps?**
Sí, en rigor y en diseño. Competirá de verdad si la presentación lleva al jurado directamente a 3I/ATLAS y si los fallos visibles quedan corregidos antes.

**5. Las tres correcciones prioritarias:**
1. **El clic de Espectro en Sencillo** (`spectrum_page.py:259`). Es la interacción central del nivel pensado para el público y hoy no funciona.
2. **El fallo de «Calidad» y la ocultación de trazas** (`time_page.py:235`, más `showErrorDetails = false` en `.streamlit/config.toml`). Una traza con rutas locales delante de un juez resta más credibilidad que cualquier limitación declarada.
3. **3I/ATLAS en la portada,** como ejemplo destacado, con una frase en Sencillo sobre qué es un cometa interestelar. Es el resultado más fuerte y hoy solo lo encuentra quien ya sabe que existe.
