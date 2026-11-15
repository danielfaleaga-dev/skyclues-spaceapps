# SkyClues — Validación espectral ciega V03

Actividad `SKYCLUES_SPECTRAL_V02_DIAGNOSIS_AND_BLIND_V03`. Rama `feature/spectrum-compare`, solo commits locales. El código científico (`spectral_features.py`, `spectral_cube.py`, `geometry.py`) no se modificó; `scripts/v03_verify.py` lo comprueba con las huellas de V02.

## 1. Resumen

| Prueba | Objeto | Características encontradas | Referencias evaluables | Coincidencias | Dictamen |
|---|---|---|---|---|---|
| C05 | Arp 220 | Pico «visible» en 3,293 µm (+42 %, 5,6×); valle «visible» de un canal en 1,949 µm | PAH 3,3 µm (detectada desde tierra; 3,35 µm observado) | PAH 3,3 µm: canal y signo compatibles; sin comparar intensidad | **RECUPERACIÓN PARCIAL** |
| C12 | TW Hya | Tres picos «visibles»: 3,833 µm (salto entre detectores), 4,040 µm y 4,635 µm | Brα 4,052 µm (la única con señal esperable sobre el criterio) | Brα cae en el canal del pico de 4,040 µm, pero con OVERFLOW y junto a un salto entre detectores; 4,635 µm discrepa | **NO EVALUABLE** |
| C14 | Núcleo de M51 | Pico «visible» de un canal en 3,293 µm (+18 %, 5,05×) | PAH 3,3 µm en los ~0,8″ centrales (3,296 µm observado) | Canal y signo compatibles; aperturas no comparables | **RECUPERACIÓN PARCIAL** |

Ninguna característica llegó a «cuantificable». Los tres objetos tienen entre 99 y 100 de 102 canales con valor.

**Dictamen de generalización: favorable pero limitado.**

- **A favor:**
  - con datos utilizables, el analizador señala la longitud de onda de la banda de PAH de 3,3 µm en las dos galaxias donde cabe esperarla (C05 y C14);
  - no marca nada en ese canal en la estrella de control (TW Hya);
  - en C12 no confunde un salto entre detectores con un resultado limpio: lo avisa en sus propias advertencias.
- **Límites:**
  - tres objetos en total, de los cuales dos son galaxias;
  - nada cuantificable;
  - no se pudo comparar ninguna intensidad;
  - sin incertidumbres en el cubo.

Con V01 y NGC 7023, esto indica que el analizador funciona de forma conservadora y consistente con datos limpios, pero estas pruebas no demuestran una sensibilidad cuantitativa general.

## 2. Diagnóstico de V02 (parte A)

Detalle en `SPECTRAL_V02_DIAGNOSIS.md` (commit `4403eaf`).

- Los canales sin valor de NGC 7027, M82 y Elias 29 vienen de píxeles de la apertura que en el propio FITS DR1 son NaN con NHITS = 0, marcados BLOOM (casi siempre con TRANSIENT y SUR_ERROR). No es saturación OVERFLOW, como escribí en V02.
- SkyClues invalida el canal entero con un solo píxel sin dato. Esa regla es deliberada y está documentada.
- Dictamen: **limitación del producto y de la extracción en los tres** (en Elias 29 predomina el producto). No se encontró ningún defecto de código.

## 3. Preselección (parte B)

Detalle en `results/blind_v03/PRESELECCION.md`, registrado antes de medir (`18a7e79`, `155d9e5`). Criterios: ≥ 60 canales utilizables, tramo continuo ≥ 15, ≥ 4 detectores con ≥ 8 canales y fondo/señal ≤ 0,2. No se ejecutó el analizador de picos.

| Id | Objeto | Utilizables | Decisión |
|---|---|---|---|
| C01 | Orion Bar | 3 | Rechazado: pocos canales (píxeles perdidos) |
| C02 | NGC 2023 | 66 | Rechazado: fondo/señal 0,37 |
| C03 | NGC 1333 | 49 | Rechazado: < 60 canales y solo 3 detectores |
| C04 | IC 63 | 100 | Rechazado: fondo/señal 0,66 |
| **C05** | **Arp 220** | 97 | **Aceptado** |
| C06 | NGC 1068 | 12 | Rechazado: pocos canales |
| C07 | Red Rectangle | 1 | Rechazado: casi sin datos |
| C08 | CRL 2688 | 17 | Rechazado: pocos canales |
| C09 | NGC 6543 | 29 | Rechazado: pocos canales |
| C10 | Cas A | 70 | Rechazado: fondo/señal 0,31 |
| C11 | Mrk 231 | 37 | Rechazado: < 60 canales y solo 3 detectores |
| **C12** | **TW Hya** | 77 | **Aceptado** |
| C13 | NGC 7293 | 7 | Rechazado: pocos canales y fondo 0,32 |
| **C14** | **Núcleo de M51** | 98 | **Aceptado** |

Se seleccionan los tres aceptados. No se forzaron cinco pruebas. Quedó sin cubrir la formación estelar y las nebulosas (G1 y G2), porque las regiones elegidas no pasaron los criterios de fondo.

## 4. Fase ciega y congelación (parte C)

- **Congelado** en `1d29ed3`: informes `C05/C12/C14/INFORME_CONGELADO.md`, `resultados.json`, figuras `espectro.png` y `campo.png`, y huellas SHA-256 en `RESUMEN_CONGELADO.md`.
- **Parámetros:** apertura de 2 px, anillo de 4–7 px, método `skyclues-features 1.0 (2026-11-14)`, sin comparación A/B (ninguna posición B tenía justificación independiente).
- **Ceguera procedimental.** Conozco la identidad de los candidatos por mi conocimiento general. La ceguera es de procedimiento: selección solo con criterios instrumentales fijados antes, sin publicaciones consultadas antes de congelar y sin ajustes de posición, fondo ni umbrales.

## 5. Características encontradas (congeladas)

| Prueba | λ (µm) | Tipo | Clase | Contraste | Contraste/dispersión |
|---|---|---|---|---|---|
| C05 | 1,949 | valle, un canal | Visible | −7,2 mJy (−9,5 %) | 6,1 |
| C05 | 3,293 | pico, canales 63–64 | Visible | +15,7 mJy (+42 %) | 5,6 |
| C12 | 3,833 | pico ancho, canales 69–71 | Visible | +154 mJy (+57 %) | 7,4 |
| C12 | 4,040 | pico ancho, canales 74–76 | Visible | +206 mJy (+95 %) | 6,1 |
| C12 | 4,635 | pico, un canal | Visible | +120 mJy (+46 %) | 6,8 |
| C14 | 3,293 | pico, un canal | Visible | +60,7 mJy (+18 %) | 5,05 |

Se conservan también 4, 5 y 7 anomalías por debajo del criterio (C05, C12 y C14) en los informes congelados.

## 6. Comparación con la literatura

Detalle y fuentes en `results/blind_v03/COMPARACION_LITERATURA.md`.

- **C05 Arp 220:** la PAH de 3,3 µm (3,35 µm observado, en el límite de los canales 63 y 64) es compatible. Las bandas de hielo y CO₂ no tienen referencia recuperada. Los estudios de AKARI de 2,5–5 µm que leí no incluyen Arp 220.
- **C12 TW Hya:** con los flujos de línea de Vacca y Sandell 2011, Brα aportaría unos 88 mJy en el canal 75; Pfβ, unos 24 mJy; Pfγ, unos 3 mJy. El pico de 3,833 µm coincide con un salto de unos 130 a 425 mJy entre detectores (canales 68 y 69), y el de 4,635 µm es unas cinco veces mayor que lo que da Pfβ.
- **C14 M51a:** PAH de 3,3 µm detectada en los ~0,8″ centrales según Asmus et al. (que cita a Oi et al. 2010, que no leí); la apertura de SPHEREx es 32 veces mayor.
- **Comprobación del canal 63:** exceso en cuatro espectros con PAH esperable y +1,4 % en la estrella de control. No es un artefacto común del canal (`control_canal63.json`).

## 7. Limitaciones

- **Muestra pequeña:** tres objetos, dos galaxias y una estrella. Faltan formación estelar y nebulosas.
- **«Visible», no «cuantificable»:** el cubo no tiene incertidumbres. Una característica en 5,05 veces la dispersión está justo en el umbral.
- **Sin comparación de intensidades.** Las referencias que pude recuperar dan detección, no intensidad.
- **Aperturas:** muy distintas a las de las referencias (1,2″, 0,8″, 0,3″ frente a 25,8″).
- **Resolución R ≈ 35–130:** el analizador no separa 3,3 de 3,4 µm ni resuelve líneas de H I.
- **Referencias incompletas.** Quedan sin referencia el hielo y el CO₂ de Arp 220, la intensidad del PAH de M51a y la banda de CO de TW Hya. La búsqueda de bibliografía fue limitada para conservar cuota.
- **Salto entre detectores en C12:** no investigado; puede deberse a OVERFLOW u otra calibración, sin determinar.
- **SIMBAD no se usó** (fuera de servicio en V02); la identificación se hizo con NED.

## 8. Verificaciones

`scripts/v03_verify.py`, 27 comprobaciones, todas correctas:

- las huellas de `spectral_features.py`, `spectral_cube.py` y `geometry.py` coinciden con las de V02;
- los resultados congelados coinciden con sus huellas;
- los productos proceden de IRSA/SPHEREx DR1 (teselas 2168, 9595 y 2756), con la apertura por defecto;
- una reextracción reproduce los espectros congelados.

Las referencias son artículos reales cuyas páginas se leyeron (Spoon et al. 2004, Vacca y Sandell 2011, Imanishi et al. 2008 y 2010) o cuyos resúmenes se obtuvieron por búsqueda (Asmus et al. 2014 y Oi et al. 2010); ambos casos están diferenciados arriba.

No se repitió la regresión completa.

## 9. Archivos

`SPECTRAL_V02_DIAGNOSIS.md`, este informe, y en `results/blind_v03/`: `PROTOCOLO_PRESELECCION.md`, `PRESELECCION.md`, `preseleccion.json`, `C05/`, `C12/`, `C14/`, `RESUMEN_CONGELADO.md`, `COMPARACION_LITERATURA.md` y `control_canal63.json`. Scripts: `v02_diagnosis.py`, `v03_preselect.py`, `blind_v03.py`, `v03_frozen_reports.py` y `v03_verify.py`.
