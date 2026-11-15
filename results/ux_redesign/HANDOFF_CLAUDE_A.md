# Traspaso del rediseño UX/UI de SkyClues → Claude A

Clon: `C:\Users\danie\Documents\SkyClues-ux` · rama `ux/redesign-v1` (desde `55e8898`) · servidor de desarrollo en el puerto 8522.
Python/Streamlit: `C:\Users\danie\Documents\SkyClues\.venv\Scripts\python.exe` / `streamlit.exe`.

## Referencias visuales del usuario

En `results/ux_redesign/referencias/`:
- `referencia_4.png` … `referencia_8.png`: el estilo **deseado**. Son landings monocromas con fondos abstractos suaves (manchas grises difuminadas, ondas de líneas finas, curvas blancas) y tipografía grande y limpia. Los botones son rectangulares negros o de contorno fino, y hay muy pocos recuadros.
- `rechazado_1.png` (la píldora «Comparable»), `rechazado_2.png` (el selector Sencillo/Científico en cápsula gris) y `rechazado_3.png` (el interruptor con marco de píldora): estilos **rechazados**.
- `antes/`: capturas del estado previo al rediseño.

## Decisiones del usuario (por orden; las más recientes prevalecen)

1. Paleta: **nada de verdes ni azules**. Se usan cobre, grises y negro.
2. «No tienen que ser solo botones con diseño bonito, sino algo **sobrio y profesional**».
   - Pide un efecto de **placa astronómica** en el fondo.
   - Botones sobrios.
   - **Pantallas de carga transparentes y vidriosas** (cristal esmerilado con backdrop-filter).
3. «**Evita este tipo de botones**»: nada de insignias en píldora con fondo tintado y punto (`.sc-badge`).
4. «Evita **recuadros aparte para cada cosa**, eso se ve genérico». Hay que **reducir los recuadros a lo estrictamente necesario**.
5. Los interruptores (selector de nivel y toggles) deben tener **una animación suave** y el mismo diseño en todos.
6. «Decide si usar una página blanco y negro o aplicarle algún color». **Decisión tomada (Claude B):**
   - **Monocromo** (papel blanco/gris cálido, tinta negra, grises).
   - **Un único acento cobre/brasa `#c4411c`**, usado con mucha moderación: selección, anillo del FOV, estado activo y marcadores de veredicto.
   - Se eliminan los acentos de área en color fuerte. Las áreas se distinguen por glifo y motivo, no por color.

## Qué hacer (en orden)

1. Reescribir `skyclues/theme.css`, que es la fuente de los estilos compartidos y usa los tokens `@@X@@` rellenados por `theme.py`.
   - **Fondo:**
     - Aplicar a `.stApp` una placa astronómica sutil: grano fino (SVG feTurbulence en data URI a muy baja opacidad), una retícula o graticula fina casi invisible, manchas grises difuminadas como en las referencias y viñeteado suave.
     - Debe ser decorativo y nunca parecer datos: nada de estrellas que puedan confundirse con fuentes reales.
   - **Menos recuadros:**
     - `.sc-facts`: cifras en línea separadas por filetes finos, sin tarjetas.
     - `.sc-read`: columnas de texto sin caja.
     - `.sc-strip`: una línea con filete inferior, sin tarjeta blanca.
     - `.sc-hero`: sin caja; texto grande sobre el fondo con el motivo.
     - `.sc-note` y `.sc-result`: solo un filete izquierdo fino, sin fondo.
     - Expanders: solo filete superior e inferior.
     - Solo conservan contenedor el mapa, las imágenes, el reproductor y las gráficas.
   - **Estados** (sustituyen a `.sc-badge`): texto en versalitas pequeñas con un cuadradito o filete de color. Sin píldora y sin fondo tintado.
   - **Botones:**
     - Rectangulares, con radio de 2 a 4 px.
     - Primario negro plano; secundario con contorno fino de 1 px.
     - Sin degradados ni sombras.
     - La navegación pasa a ser texto con subrayado o filete en la pestaña activa, no píldoras.
   - **Selector Sencillo/Científico y `stToggle`:**
     - Un mismo lenguaje: interruptor fino y sobrio con un indicador que **se desliza suavemente** (transition de 200 a 250 ms, ease).
     - Sin marco de píldora alrededor del toggle.
     - Respetar `prefers-reduced-motion`.
   - **Carga** (`[class*="st-key-sc_loading_"] [data-testid="stSpinner"]`):
     - Cristal translúcido: `background: rgba(255,255,255,.45)`, `backdrop-filter: blur(14px) saturate(1.1)`, borde de 1 px semitransparente.
     - Spinner fino en negro o cobre.
   - `.sc-steps`: quitar las píldoras y dejar una secuencia numerada en texto.
2. En `skyclues/theme.py`, ajustar `AREA` o los motivos a la escala de grises con el cobre como único acento.
3. En `.streamlit/config.toml`, poner `baseRadius` pequeño (por ejemplo 0.2rem).
4. Componente Región:
   - Aplicar el mismo lenguaje en `skyclues/region_component.css`: CTAs Tiempo/Espectro sin degradados, panel sin tarjeta pesada, inputs sobrios.
   - **Reiniciar el servidor tras cambiar este CSS**, porque se queda en caché.
5. Reproductor: llevar el CSS del iframe en `skyclues/player.py` (`_CSS`) al mismo estilo.
6. Verificar en el navegador:
   - Región, Tiempo (M101) y Espectro.
   - Ambos niveles, a 1600 px y 420 px.
   - Búsqueda, CTAs, navegación, cambio de nivel, resultado de movimiento, toggle S/N, clic en el espectro y RGB.
   - Consola, y estados vacío y de error.
   - Guardar las capturas en `results/ux_redesign/despues/`.
7. Tests con el venv: `tests/test_integration_science.py`, `tests/test_enhance_app.py`, los tests de app de región/tiempo/espectro y `test_motion_app.py`. Revisar los asserts de texto afectados por los cambios de redacción.
8. Documentar:
   - Actualizar `DESIGN_SYSTEM.md` con la nueva identidad y `PROJECT_STATE.md`.
   - Escribir `UX_REDESIGN_REPORT.md` con: sistema visual, paleta, problemas de comprensión corregidos, limitaciones (el motor de movimiento no distingue «sin movimiento significativo» de «no confirmado»; ambos son INSUFFICIENT_EVIDENCE) y comprobaciones reales hechas.
   - Indicar que fue una **revisión heurística, sin pruebas con usuarios reales**.
9. Hacer un commit local en `ux/redesign-v1`. **Sin push, publicación ni despliegue.**

## Ya hecho por Claude B (no rehacer)

- **Redacción del modo Sencillo:**
  - Región: «¿Qué zona del cielo quieres investigar?», RA/Dec explicadas como opcionales, «Tamaño de la región», «Mapa de referencia (no SPHEREx)» y CTAs diferenciados.
  - Tiempo: veredictos claros («Movimiento detectado», «no confirmado», que no demuestra que esté quieto, «No evaluable», «Datos insuficientes»), etiqueta mismo canal / banda ancha y guía de lectura.
  - Espectro: introducción y explicación de ejes, picos y valles; RGB ≠ color visible.
- **Texto exacto para cuando no hay coincidencias:** «Sin coincidencias en la biblioteca actual (N referencias). Esto no descarta otras características físicas conocidas.»
- **Series de las gráficas:** negra y cobre, con marcadores A/B y halo blanco.
- **Helpers de `theme.py`:** `hero`, `region_strip`, `result`, `area_flag`, `reading_guide` y `facts`. Conservar sus firmas y cambiar solo el CSS.

## Restricciones (no negociables)

- No tocar algoritmos, fotometría, combinación S/N, interpretación, consultas, máscaras, validación, datos ni resultados verificados.
- No añadir funciones científicas, Intérprete V2, reconstrucción de píxeles, modos nuevos, gamificación, autoplayer de canales ni dependencias pesadas.
- Hay 102 canales (no 107).
- No tocar los repositorios `SkyClues`, `SkyClues-spectra`, `SkyClues-snr-A`, `SkyClues-interpreter` ni `SkyClues-integrated`.
- Puertos 8501–8508: son del usuario.
- Escribir en español.
- Commit con identidad tomada de `git config` de `C:\Users\danie\Documents\SkyClues` (`git -c user.name=... -c user.email=...`).
