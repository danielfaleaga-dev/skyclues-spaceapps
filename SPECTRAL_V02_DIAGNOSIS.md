# SkyClues — Diagnóstico de los canales inutilizables de V02

Actividad `SKYCLUES_SPECTRAL_V02_DIAGNOSIS_AND_BLIND_V03`, parte A. Rama `feature/spectrum-compare`, sobre `dfdf3af`. Solo lectura: `scripts/v02_diagnosis.py` lee el FITS DR1 con la misma geometría que `extract_spectrum` y no importa nada del analizador. Datos completos canal a canal: `results/v02_diagnosis/diagnostico.json`.

## Conclusión corta

En los tres objetos, todos los canales sin valor (excepto el 51 y el 52, vacíos en DR1) se deben a **píxeles de la apertura que en el propio cubo DR1 no tienen dato** (IMAGE = NaN y NHITS = 0) y que llevan la bandera **BLOOM** (casi siempre con TRANSIENT y SUR_ERROR). Esos huecos están en el núcleo de la apertura (peso 1), nunca solo en su borde.

SkyClues los convierte en canal entero sin valor por una regla de diseño: un solo píxel sin dato en la apertura invalida el canal, sin rellenar ni ponderar. Es una decisión del software que amplifica una limitación real del producto.

El anillo de fondo está completo (0 píxeles NaN o con NHITS = 0) en todos los canales con datos.

**Corrección de V02.** Mis informes de V02 hablaban de «saturación o píxeles perdidos». Ese texto era impreciso: la pérdida es sobre todo BLOOM (píxeles enmascarados por el pipeline junto a una fuente brillante), no OVERFLOW. OVERFLOW aparece en 2 canales invalidados de NGC 7027, en 21 de M82 y en ninguno de Elias 29. Los resultados congelados de V02 no cambian; solo la explicación de su causa.

## Qué se contrastó

| Pregunta | Método | Resultado |
|---|---|---|
| Valores y máscaras originales | IMAGE, NHITS y FLAGS de cada plano en la apertura (peso > 0) y el anillo | En todo canal invalidado, los píxeles malos son a la vez NaN y NHITS = 0 (63/63, 35/35, 50/50) |
| Banderas y saturación | OR de bits en los píxeles de la apertura | El número de píxeles BLOOM coincide con el de píxeles sin dato en 63/63, 35/35 y 50/50 canales |
| Píxeles descartados por la extracción | Mismos píxeles que descarta `extract_spectrum` (`~isfinite` o `NHITS ≤ 0`) | Coinciden con los del FITS: la extracción no descarta ningún píxel que tenga dato |
| Pérdidas por apertura y anillo | Píxeles malos en el núcleo (peso ≥ 0,999) frente al borde; píxeles NaN o con NHITS = 0 en el anillo | Núcleo en todos los casos; borde solo: 0. Anillo: 0 píxeles malos |
| Otras restricciones del código | Mínimo de anillo válido (50 %); canales BLANKCH; entorno de 3 canales por lado del analizador | Solo BLANKCH (51 y 52) y la regla de píxeles de apertura intervienen; el anillo nunca falla. La falta de entorno es un segundo filtro del analizador, no de la extracción |

La apertura de 2 px contiene solo 18–19 píxeles (12,5 de peso efectivo). Cada píxel sin dato pesa por tanto entre el 5 % y el 8 % de la apertura.

## Diagnóstico por objetivo

### NGC 7027 (T01) — **Ambas** (producto y extracción)

- **Producto:** 63 canales con entre 1 y 15 píxeles de la apertura sin dato en el FITS (BLOOM + TRANSIENT + SUR_ERROR). Afecta a 10 de 16 canales del detector 3 y a casi todos los de los detectores 4–6. OVERFLOW en solo 2.
- **Extracción:** la regla descarta el canal entero aunque solo falte parte del peso: en 47 canales se perdería ≤ 25 % del peso de la apertura (21 con ≤ 10 %); en 10, entre 25 y 50 %; en 6 (canales 62–65, 88, 89), más del 50 %.
- **No determinable:** si un flujo calculado con los píxeles restantes sería fiable. Un píxel con BLOOM junto a una fuente brillante indica que sus vecinos también pueden estar contaminados.

### M82, núcleo (T02) — **Ambas**

- **Producto:** 35 canales (detectores 2–4; 1,55–3,77 µm) con 1–11 píxeles sin dato, todos BLOOM. Además hay OVERFLOW en 21 canales (también los que sí tienen valor en 1,0–1,5 µm y 3,8–5,0 µm).
- **Extracción:** pérdida de peso ≤ 10 % en 4 canales, 10–25 % en 12, 25–50 % en 15 y > 50 % en 4 (63–65, 68).
- **No determinable:** igual que arriba. Además, la emisión extensa de M82 llena el anillo, así que un flujo parcial tampoco tendría un fondo limpio.

### Elias 29 (T03) — **Ambas, con predominio del producto**

- **Producto:** 50 canales, todos de los detectores 3–6 (más de 2,3 µm), con 1–17 píxeles sin dato por canal. Es el patrón de una fuente muy roja y brillante en esos detectores. No hay OVERFLOW.
- **Extracción:** 43 de 50 canales perderían entre el 25 y el 50 % del peso; 6 (63–68), más del 50 %; solo 1, ≤ 10 %. Una regla menos estricta recuperaría poco aquí.
- **No determinable:** como en los demás.

## ¿Defecto de SkyClues?

No encontré ninguno. La regla de la apertura está documentada en el docstring de `extract_spectrum` («un canal con cualquier píxel de la apertura sin dato no recibe valor; nunca se rellena») y se comporta como describe. No hay reproducción mínima porque no hay discrepancia entre el código y su especificación. Las alternativas (ponderar solo los píxeles con dato, ampliar la apertura, reconstruir) son métodos nuevos con efecto sobre los resultados existentes; no se han implementado ni probado.

Tampoco se ha investigado la recuperación mediante exposiciones Level-2 individuales, según el encargo.

## Consecuencia para V03

Un objeto es utilizable si el cubo DR1 tiene datos reales en la apertura de 2 px, no solo si es débil. Las fuentes compactas y brillantes en el infrarrojo medio pierden píxeles por BLOOM y quedan inútiles con esta apertura. La preselección de V03 se basa en ese criterio, medido directamente sobre el cubo.
