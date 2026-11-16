# SkyClues — corrección de los bloqueos de la evaluación final

**Dictamen: `CRITICAL_FIXES_PASS`**

- **Rama y commit:** `ux/redesign-v1` (versión rediseñada evaluada), commit local «Corrige los tres bloqueos de la evaluación final» (el último de la rama; ver `git log -1`). Sin push ni despliegue.
- **Archivos modificados:** `skyclues/spectrum_page.py`, `skyclues/multiband_page.py`, `skyclues/time_page.py`, `app.py`, `skyclues/theme.css`, `.streamlit/config.toml`, `tests/test_spectral_app.py`, `PROJECT_STATE.md`; se añaden este informe y `SKYCLUES_FINAL_USER_AND_JUDGE_REVIEW.md`.

## Correcciones

1. **Selección de punto en Espectro/Sencillo.**
   - Causa: en cada ejecución `render` guarda y restaura `sx_pick_ra/dec`; la copia guardada (anterior) pisaba el valor fijado por el callback del clic.
   - Corrección: el callback `_set_pick_from_chart` escribe también la copia guardada (`multiband_page.set_kept`). No se tocan la extracción ni la conservación entre vistas.
   - Test nuevo: `test_chart_click_survives_the_restore_of_kept_widget_state`; falló antes de la corrección y pasa después.
2. **Tiempo › Calidad.** `def render(level)` tapaba el módulo `render`. El módulo se importa como `figures` y se actualizan sus dos usos. Sin cambios en cálculos ni indicadores.
3. **Errores públicos.**
   - `[client] showErrorDetails = "none"`; los valores admitidos se comprobaron contra Streamlit 1.67.0, la versión fijada.
   - Una regla de `theme.css` oculta los enlaces «Ask Google / Ask ChatGPT».
   - Los errores siguen en el registro del servidor.
4. **Indicador de carga (adicional).** Al cambiar de vista la página vuelve arriba, donde está el indicador (`app.py`).

## Comprobaciones (navegador, puerto 8524, datos reales)

- **Selección en Sencillo (M101):**
  - dos clics distintos mueven el marcador;
  - la coordenada elegida (210,750549 / 54,331914) coincide con la selección interna de Vega;
  - el espectro cambia respecto al del centro (máximo ≈ 14 mJy frente a ≈ 190 mJy), como corresponde a un punto a 60″.
- **Paso a Científico:** conserva exactamente esas coordenadas, un clic nuevo las cambia (210,841955 / 54,379902), y la vuelta a Sencillo mantiene el punto.
- **Tras recargar:** dos clics seguidos mueven el marcador (la región nueva reinicia el punto al centro, como antes).
- **Calidad (M101, Científico):** «Cobertura y longitud de onda» muestra sus dos mapas y la tabla, sin excepción; Secuencia, Movimiento, Calidad y Procedencia sin excepciones. En Sencillo no hay excepción.
- **Error controlado:** en una app mínima con la misma configuración, el visitante ve el mensaje genérico, sin traza ni ruta ni enlaces externos, y el log del servidor guarda la excepción completa.
- **Indicador:** desde Región desplazada 422 px, al abrir Tiempo (M42) la página queda arriba y el indicador es visible a los 5 s.
- **Tests relacionados:** `test_spectral_app`, `test_spectrum_analysis_app`, `test_multiband` y `test_spectral_interpreter_app`: 67 superados. No se repitió la regresión global.

## Limitaciones pendientes

- El mensaje genérico de Streamlit para errores imprevistos está en inglés y no se puede traducir con la configuración.
- No se comprobó «Calidad» en Tiempo con una secuencia en vivo distinta de M101 ni en pantalla estrecha.
- No se tocaron los demás puntos del informe de evaluación (3I/ATLAS en portada, saturación sin explicar en Sencillo, etc.).
