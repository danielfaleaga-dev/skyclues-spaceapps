# NGC 7023 · resultados congelados antes de consultar la literatura

Actividad `SKYCLUES_SPECTRAL_BLIND_VALIDATION_01`. Protocolo: `PROTOCOLO.md` (commit `10828a0`). Posiciones: commit `c392f91`. Este documento se confirma **antes** de buscar o leer cualquier estudio sobre NGC 7023. Su contenido no se modifica después; la comparación con la literatura va en `COMPARACION_LITERATURA.md`.

## Posiciones (regla morfológica, `seleccion.json`)

| | RA (°) | Dec (°) | Distancia a la estrella | PA (E de N) | Brillo de referencia (0,75–1,09 µm) | Exceso relativo |
|---|---|---|---|---|---|---|
| Estrella (píxel más brillante) | 315,402579 | +68,164703 | — (a 5,3″ de las coordenadas nominales) | — | 32,7 MJy/sr | — |
| **A** (zona estructurada) | 315,403109 | +68,193782 | 104,7″ | 0,4° | 3,50 MJy/sr | +198 % |
| **B** (comparación) | 315,337145 | +68,144347 | 114,3″ | 230,1° | 0,32 MJy/sr | −28 % |

- **Separación A–B:** 198,7″ (15,4 px). Ninguna apertura cae en el anillo de fondo de la otra.
- **Extracción:**
  - Apertura de 2 px (25,8″), con 12,84 px efectivos.
  - Anillo de 4–7 px (51,5″–90,2″), con 112 px y media con recorte 3σ.
  - Mismos radios en A y B; magnitud: flujo en apertura (mJy).
  - Resultado: 100 de 102 canales con valor en ambos; los 51 y 52 no tienen datos en DR1.
- **Lectura del cubo:** 16,4 s, 12 peticiones, 13,9 MB por rangos de bytes.

**Observaciones sobre la geometría** (registradas antes de ver la literatura):

- **A coincide con un nudo compacto** de la imagen de referencia (exceso de +198 % en un disco de 2 px). Puede ser una estructura nebular o una fuente puntual dentro de la apertura. El indicador SOURCE del cubo aparece en los 100 canales de A, pero también en los 100 de B, así que no permite distinguirlo. La regla no se cambió.
- **B tiene flujo neto ≤ 0 en 39 canales**, todos por debajo de ~2,6 µm: es más débil que su propio anillo de fondo. El anillo contiene parte de una cresta brillante situada al sur de la estrella (visible en `seleccion.png`). Por tanto, en esa zona B mide «más débil que su entorno», no un brillo absoluto.

## Características encontradas por el detector (sin intervención)

| Espectro | Tipo | Clase | λ del extremo (µm) | Media altura | Contraste | Relativo | Contraste/dispersión | Detectores |
|---|---|---|---|---|---|---|---|---|
| A | pico · amplia | **Visible** | 3,383 (centroide 3,379) | canales 63–65 · 3,242–3,528 µm | +82,75 mJy | +124,9 % | 6,3 | D4, D5 |
| B | — | ninguna | — | — | — | — | — | — |

No hay ninguna característica cuantificable en A ni en B.

**Por qué A es «visible» y no «cuantificable».** Su intervalo de prueba (canales 60–68) y el entorno (57–59 y 69–71) abarcan dos detectores (D4 y D5), y el canal 67 tiene píxeles OVERFLOW/OUTLIER. Además, al ser ancha, el contraste puede estar subestimado.

- Dispersión de referencia de A: 6,12 mJy, fijada por el fondo; la del entorno es 3,39 y la del detector, 5,03.

**Medidas cruzadas** (el mismo intervalo, en el otro espectro). El intervalo 60–68 de A, medido en B, da:

- clase «Sin característica»;
- contraste de +52,6 mJy (+124 %);
- 1,9 veces la dispersión de referencia.

**Canales no evaluables:**

- A: 1–3, 48–55, 57–59, 69, 71 y 100–102. Los 57–59, 69 y 71 lo son porque forman el entorno de la característica de A o están junto a ella.
- B: 1–3, 48–55 y 100–102.

**Comparación canal a canal:**

- A > B en los 100 canales con valor en ambos.
- A/B solo es válido en 45 canales: donde B > 0 y supera tres veces el ruido del fondo.
- La mediana de A/B es 2,25. A/B se aparta de su mediana sobre todo en 2,87–3,12 µm (4,9 a 4,0) y en 3,29 µm (1,4, el mínimo).

## Diagnóstico registrado (`diagnostico.json`; funciones públicas, sin cambiar parámetros)

**B, canal 63 (3,293 µm).**

- **Valores:** el flujo sube de unos 38–43 mJy (canales 62 y 64) a 95,2 mJy en el canal 63. Con canal único:
  - contraste de +55,1 mJy (+137 %) sobre el continuo local;
  - 3,4 veces la dispersión de referencia, por debajo de 5, así que no se etiqueta.
- **Por qué no llega al umbral:** la dispersión del anillo de fondo en ese canal es 0,889 MJy/sr, frente a 0,38–0,63 en los canales 60–66. Ese fondo fija la referencia (13,1 mJy en apertura).
- **Interpretación (no comprobada):** el anillo de B contiene emisión estructurada que también aumenta en ese canal.

**A, canales 62–65.** Todos remiten a la misma característica: intervalo 60–68, 6,3 veces la dispersión.

## Resultado registrado antes de la literatura

1. **A:** exceso ancho, clase «visible», centrado en 3,38 µm (media altura 3,24–3,53 µm). Es el único rasgo que supera los criterios en ninguno de los dos espectros.
2. **B:** exceso de un solo canal en 3,293 µm, +137 % sobre el continuo local pero solo 3,4 veces la dispersión de referencia. **No etiquetado**: el criterio congelado lo clasifica como «sin característica» porque el fondo es estructurado en ese mismo canal.
3. No se etiquetan picos ni valles en ninguna otra longitud de onda. No se afirma ninguna identificación molecular.

## Huellas SHA-256

- `resultados.json`: `872eae2bd28740c5a04f288619810c5d9dcb0462cc2f37d35a8a0c9294c3829c`
- `diagnostico.json`: `9d97e9e1755a77f5e513830494f3e3dfb7f43d9ade802df13558a956a215cadd`
- `seleccion.json`: `9fb74fbcd853a53a2632fe9060ce22a8a1dbaca5e0ab83072ac4b3f8afacd0cf`
- Código del método: las huellas están en `resultados.json` → `huellas_sha256`, iguales a las de la selección.
