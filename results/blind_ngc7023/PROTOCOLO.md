# Validación espectral ciega — NGC 7023 · protocolo previo

Actividad: `SKYCLUES_SPECTRAL_BLIND_VALIDATION_01`. Este documento se confirma (commit local) **antes** de extraer ningún espectro de NGC 7023 y antes de consultar literatura sobre el objeto.

## Estado congelado

- Código: rama `feature/spectrum-compare`, commit `74cfd6b`. No se modifica `skyclues/spectral_features.py` (método `skyclues-features 1.0 (2026-11-14)`), `skyclues/spectral_cube.py` ni sus umbrales durante esta actividad. El script `scripts/blind_ngc7023.py` registra sus huellas SHA-256.
- Umbrales: visible ≥ 5, cuantificable ≥ 7 veces la dispersión de referencia; contraste relativo mínimo 1 %; continuo local de grado 2 con 3 canales válidos por lado; barrido de 1 a 9 canales en dos pasadas.
- Extracción: apertura por defecto de la aplicación: radio 2 px (25,8″), anillo de fondo 4–7 px (51,5″–90,2″), media con recorte 3σ, magnitud «flujo en apertura» (mJy). Mismos radios en A y B.

## Declaración sobre la ceguera

No se ha consultado ninguna publicación, tabla de líneas ni identificación química de NGC 7023 para esta prueba. Sin embargo, el agente que la ejecuta es un modelo de lenguaje con conocimiento general previo de astronomía: sabe que NGC 7023 es una nebulosa de reflexión iluminada por la estrella HD 200775. La ceguera garantizada por el protocolo es, por tanto, **procedimental**:

- el algoritmo y los umbrales están congelados;
- las posiciones se eligen con una regla morfológica fijada aquí;
- el detector no tiene intervención manual;
- los resultados se confirman antes de la consulta.

## Regla de selección de A y B (fijada antes de ver los espectros)

1. **Imagen de referencia.** Mediana, píxel a píxel, de los 17 canales del detector 1 (0,75–1,09 µm) del cubo DR1, en un campo de 6′ centrado en (315,4038°, +68,1633°). Es luz de continuo de longitud de onda corta. La mediana sobre 17 canales suprime cualquier línea aislada. No se usa ningún canal ni contraste espectral de 1,1–5 µm para elegir.
2. **Estrella central.** Píxel más brillante de la referencia a menos de 30″ de las coordenadas nominales.
3. **Estructura.** Para cada píxel se calcula su exceso relativo respecto de la mediana azimutal del brillo a la misma distancia de la estrella (anillos de 1 px), promediado sobre un disco del tamaño de la apertura (radio 2 px). Así se resaltan filamentos y bordes, no el gradiente radial.
4. **Punto A (zona estructurada).** Centro del píxel con mayor exceso relativo a una distancia de la estrella entre 60″ y 150″. El borde de la apertura queda a ≥ 34″ (≥ 2,6 px) de la estrella.
5. **Punto B (comparación).** A la misma distancia de la estrella que A (±1 px), el píxel con menor exceso relativo (zona menos estructurada a igual iluminación geométrica), con separación A–B ≥ 9 px (116″ = radio de apertura + radio exterior del anillo). Así ninguna apertura cae dentro del anillo de fondo de la otra.
6. **Validez.** Si A o B tienen canales sin datos fuera de los 51/52, se registra tal cual. No se recoloca ninguna posición por el aspecto de su espectro.

## Ejecución

- **Extracción.** `scripts/blind_ngc7023.py select` escribe la imagen y las posiciones; `scripts/blind_ngc7023.py extract` extrae los espectros con `spectral_cube.extract_spectrum`.
- **Análisis.** Se ejecutan `spectral_features.analyse` y `compare` sobre A y B, y cada característica de un espectro se mide en el mismo intervalo del otro con `measure_interval`.
- **Registro.** Se guardan todas las características (cuantificables, visibles y los canales no evaluables), los espectros completos, la figura y las huellas.
- **Congelación.** Los resultados se confirman en un commit antes de cualquier consulta externa. La comparación con la literatura se añade después en un documento separado, sin tocar los resultados congelados.
