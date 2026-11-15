# Validación ciega V02 · informe final

Actividad `SKYCLUES_SPECTRAL_BLIND_VALIDATION_02`. Rama `feature/spectrum-compare`, commits locales sin push.

## Cronología

| Commit | Paso |
|---|---|
| `e3331de` | Protocolo y script registrados antes de leer datos |
| `a6bd9d4` | T01–T03 analizados y congelados (informes individuales, JSON, gráficos y huellas en `RESUMEN_CONGELADO.md`), sin identificar los objetos |
| (siguiente) | Identificación, comparación (`COMPARACION_LITERATURA.md`) y este informe |

## Método

- **Versión:** `skyclues-features 1.0 (2026-11-14)`, sin cambios. Las huellas SHA-256 del código (`huellas_metodo.json`) son idénticas en los tres objetivos.
- **Extracción:**
  - apertura de 2 px (25,8″), anillo de 4–7 px;
  - flujo en apertura;
  - posiciones exactamente las del encargo.
- **Comparación A/B:** no se usó, porque ninguna posición B podía defenderse sin conocer la morfología.

## Resultado

| Prueba | Características encontradas | Características de referencia evaluables | Coincidencias | Resultado |
|---|---|---|---|---|
| T01 · NGC 7027 | Ninguna. Solo 37/102 canales con valor; nada por encima de 1,95 µm salvo un canal saturado | **Ninguna.** [S III] 0,953, He I 1,083, Paβ, Paα y todas las líneas de 2–5 µm caen en canales sin valor | — | **NO EVALUABLE** |
| T02 · M82 (núcleo) | 1 pico visible en 4,669 µm (5,8×, OVERFLOW). Por debajo del criterio: 1,284 µm (3,95×) y 4,076 µm (3,73×) | Paβ, Brα y Pfβ, todas en canales con OVERFLOW. PAH 3,3, Brγ, Paα y Brβ caen en el hueco de 1,55–3,77 µm | Pfβ y Paβ coinciden en λ pero en canales saturados; Brα **no** (su canal es un mínimo) | **NO EVALUABLE** (coincidencias no concluyentes) |
| T03 · Elias 29 | Ninguna. Por debajo del criterio: 0,955 µm (2,5×) y 1,995 µm (3,1×, OVERFLOW) | **Ninguna.** H₂O 3,07, CO₂ 4,27 y CO 4,67 µm caen en canales sin valor o sin vecinos | — | **NO EVALUABLE** |

## Conclusión

**Qué limitó las tres pruebas.** Los tres objetivos están entre las fuentes infrarrojas más brillantes y compactas del cielo. En el cubo DR1 combinado:

- pierden píxeles de la apertura (NHITS = 0) o se marcan con OVERFLOW precisamente en los intervalos donde están sus características de referencia;
- la cobertura evaluable queda reducida a 0,75–2 µm (T01, T03) o a tramos saturados (T02).

**Por qué no es un fallo del analizador.** Ninguna de estas características es físicamente evaluable con estos datos, así que no se clasifica como fallo del algoritmo. Ver el punto 8 del encargo.

**Cómo se comportó el analizador:**

- No etiquetó como «cuantificable» ningún rasgo en datos saturados.
- Marcó todos los canales sin datos como no evaluables, sin interpolar.
- La única marca «visible» (T02, 4,669 µm) lleva sus advertencias de saturación y de canal único.
- Sus coincidencias aparentes con Paβ y Pfβ son internamente incoherentes con la ausencia de Brα, por lo que no se aceptan como recuperación.

**Respuesta al objetivo final.** Estas tres pruebas **no permiten medir** la capacidad de recuperación de Spectrum Explorer: lo que limita es el régimen de saturación de SPHEREx, no el analizador. Lo que sí muestran:

- el sistema es **conservador** ante datos degradados (no inventa detecciones cuantificables);
- informa de forma explícita de las causas de cada canal no evaluable.

**Para que una prueba futura sea evaluable** hacen falta objetivos con rasgos fuertes pero flujos por debajo de la saturación del cubo, como las regiones extensas y moderadamente brillantes (V01, NGC 7023), donde sí hubo datos completos.

**Observaciones posteriores, no atribuidas al analizador ni verificadas:**

- en T01, los canales perdidos coinciden con las líneas más intensas esperables;
- en T03, el único canal superviviente por encima de 2,3 µm coincide con la absorción de hielo de CO₂.

## Bloqueos registrados

- SIMBAD respondió HTTP 404 durante la identificación; se usó NED.
- No se obtuvieron flujos de línea publicados de M82 y NGC 7027 en aperturas comparables. No afectan al dictamen, porque los canales implicados están saturados o sin datos.
