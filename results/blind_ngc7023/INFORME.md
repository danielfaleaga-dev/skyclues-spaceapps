# Validación espectral ciega — NGC 7023 (nebulosa Iris) · informe

Actividad `SKYCLUES_SPECTRAL_BLIND_VALIDATION_01`. Rama `feature/spectrum-compare`, carpeta `SkyClues-spectra`. Commits locales sin push.

## Cronología

| Commit | Contenido |
|---|---|
| `74cfd6b` | Método congelado (corrección previa del inspector, solo presentación) |
| `10828a0` | Protocolo y regla de selección registrados, sin ningún espectro extraído |
| `c392f91` | Imagen de referencia y posiciones A/B |
| `a73c0ef` | Espectros, características, diagnóstico y figuras congelados, antes de buscar literatura |
| (siguiente) | Comparación con la literatura, este informe y el dictamen |

## 1. Objetivo y coordenadas

- **Coordenadas nominales:** RA 315,4038°, Dec +68,1633°, campo de 6′. El píxel más brillante del continuo (HD 200775) está a 5,3″.
- **A** (zona estructurada): RA 315,403109°, Dec +68,193782°. Está a 104,7″ de la estrella, con PA 0,4°.
- **B** (comparación): RA 315,337145°, Dec +68,144347°. Está a 114,3″ de la estrella, con PA 230,1°.
- **Separación A–B:** 198,7″.
- **Apertura:** 2 px (25,8″), anillo de 4–7 px (51,5″–90,2″). Las mismas en A y B, sin solapamiento.

## 2. Método y parámetros congelados

- **Método:**
  - Versión `skyclues-features 1.0 (2026-11-14)`.
  - Continuo local de grado 2 en ln–ln, con 3 canales válidos por lado.
  - Clase «visible» desde 5 veces la dispersión de referencia y «cuantificable» desde 7, con contraste relativo mínimo del 1 %.
  - Barrido de 1–9 canales en dos pasadas.
  - Dispersión de referencia: la mayor entre la del entorno, la del detector y la del fondo.
- **Huellas SHA-256** del código: en `resultados.json`. Son idénticas en la selección y en la extracción, y el script lo verifica.
- **Selección:** regla morfológica sobre la mediana del detector 1 (0,75–1,09 µm).
  - A: máximo exceso relativo respecto de la mediana azimutal, a 60–150″ de la estrella.
  - B: mínimo exceso a la misma distancia y a ≥ 116″ de A.

## 3. Espectros A/B

Figuras: `espectros.png` (A/B y A/B) y `seleccion.png` (posiciones). Datos completos en `resultados.json`.

- **A:**
  - 25–150 mJy, creciente hasta unos 1,7 µm y casi plano después.
  - Ningún canal negativo.
- **B:**
  - Flujo neto ≤ 0 en 39 canales por debajo de unos 2,6 µm: es más débil que su anillo de fondo.
  - Unos 40 mJy a partir de 3,2 µm.
- **Comparación:** A > B en los 100 canales con valor en ambos; mediana de A/B = 2,25 (45 canales válidos).

## 4. Características encontradas antes de consultar la literatura

| Espectro | Tipo | Clase | λ (µm) | Media altura | Contraste | Relativo | Cont./disp. | Detectores |
|---|---|---|---|---|---|---|---|---|
| A | pico · amplia | Visible | 3,383 | 63–65 (3,24–3,53 µm) | +82,75 mJy | +124,9 % | 6,3 | D4, D5 |
| B | — | — | — | — | — | — | — | — |

- **No etiquetado, pero registrado:** en B, el canal 63 (3,293 µm) da +55,1 mJy (+137 %), 3,4 veces la dispersión. La dispersión del anillo de B se dobla en ese canal.
- **No evaluables:**
  - A: canales 1–3, 48–55, 57–59, 69, 71 y 100–102.
  - B: canales 1–3, 48–55 y 100–102.

## 5. Comparación con publicaciones independientes

Detalle en `COMPARACION_LITERATURA.md`.

| Elemento | Resultado |
|---|---|
| Banda de 3,29 µm (AKARI: FWHM 0,03 µm, dominante) | **Coincidencia en λ en B, no recuperada:** 3,4 × < 5 |
| Complejo 3,29/3,40/3,45 µm | **Coincidencia parcial en A:** intervalo correcto, máximo desplazado a 3,38 µm (discrepancia de perfil) |
| Signo | Coincide: emisión |
| Diferencias entre regiones | Compatible: A/B mínimo en 3,29 µm. A está dominado por una estrella de campo 2MASS (Ks = 9,68 a 8″) |
| Presencia a unos 100″ de la estrella | No evaluable: las fuentes consultadas no cubren esas posiciones con valores |
| Separación 3,3 / 3,4 µm | No evaluable con R ≈ 40 |

## 6. Limitaciones

1. **La regla de selección eligió una estrella de campo para A.** El «nudo compacto» de mayor exceso es 2MASS J21013754+6811309. La regla no excluía fuentes puntuales. No se corrigió a posteriori, como exige el protocolo; queda como defecto del diseño de la prueba.
2. **La resta del fondo anular perjudica la emisión extensa.** En una nebulosa más grande que el anillo (90″), el fondo contiene la propia emisión: reduce el contraste y eleva la dispersión de referencia. Esto explica que la señal más limpia, la de B en 3,29 µm, quede por debajo del umbral.
3. **R ≈ 40:** 3,29, 3,40 y 3,45 µm se mezclan en los canales 63–65.
4. **Límite entre D4 y D5** (canales 68/69): el entorno derecho de la característica de A está en otro detector, así que no puede ser «cuantificable».
5. **Sin incertidumbres:** el cubo no tiene varianza. La dispersión de referencia es descriptiva.
6. **Literatura:**
   - AKARI cubre posiciones a unos 40–60″ al NW, no las de A/B.
   - El mapa de SOFIA no se consultó en valores; solo su descripción.
   - SIMBAD no estaba disponible.
7. **Ceguera:** procedimental. El modelo tenía conocimiento general previo de que NGC 7023 es una nebulosa de reflexión; ver `PROTOCOLO.md`.

## 7. Conclusión científica y dictamen

**Dictamen: RECUPERACIÓN PARCIAL.**

**A favor:**

- La única característica que el detector congelado etiqueta, en ambos espectros, cae en el intervalo del complejo 3,2–3,6 µm conocido en NGC 7023, con el signo correcto (emisión).
- No hay falsos positivos en ninguna otra longitud de onda (100 canales por espectro).
- En la posición nebular B, los datos muestran un exceso de un canal exactamente en el canal que contiene 3,29 µm. Su anchura es compatible con la banda (FWHM 0,03 µm, menor que un canal).
- La relación A/B tiene su mínimo en ese canal.

**Por qué no es «compatible»:**

1. Ninguna característica alcanza la clase «cuantificable».
2. La señal que mejor coincide con la literatura (B, 3,29 µm) **no** fue etiquetada (3,4 × < 5): el criterio conservador, con un fondo estructurado, no la recupera.
3. El rasgo etiquetado en A tiene su máximo en 3,38 µm y no en 3,29 µm. Además, A está dominado por una estrella de campo enrojecida, así que no puede atribuirse a la nebulosa.
4. La comparación posición a posición con AKARI/SOFIA no es evaluable con lo consultado.

**Lo que muestra sobre la generalización:**

- Spectrum Explorer **no inventa** características: con criterios congelados, el único rasgo etiquetado está en el sitio esperable.
- Su sensibilidad a emisión extensa queda limitada por la fotometría con anillo de fondo local. Ese anillo sustrae parte de la emisión nebular y fija la dispersión de referencia.
- El diseño de la prueba enseña que una regla morfológica debe excluir fuentes puntuales catalogadas antes de elegir A. Es una lección para la próxima prueba ciega, **no un cambio aplicado a esta**.

**Sin cambios:** no se han modificado los algoritmos científicos, los umbrales ni la extracción. Tampoco se ha añadido ninguna funcionalidad.
