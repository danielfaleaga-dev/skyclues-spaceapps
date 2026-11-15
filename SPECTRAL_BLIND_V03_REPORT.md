# SkyClues â€” ValidaciÃ³n espectral ciega V03

Actividad `SKYCLUES_SPECTRAL_V02_DIAGNOSIS_AND_BLIND_V03`. Rama `feature/spectrum-compare`, solo commits locales. El cÃ³digo cientÃ­fico (`spectral_features.py`, `spectral_cube.py`, `geometry.py`) no se modificÃ³; `scripts/v03_verify.py` lo comprueba con las huellas de V02.

## 1. Resumen

| Prueba | Objeto | CaracterÃ­sticas encontradas | Referencias evaluables | Coincidencias | Dictamen |
|---|---|---|---|---|---|
| C05 | Arp 220 | Pico Â«visibleÂ» en 3,293 Âµm (+42 %, 5,6Ã—); valle Â«visibleÂ» de un canal en 1,949 Âµm | PAH 3,3 Âµm (detectada desde tierra; 3,35 Âµm observado) | PAH 3,3 Âµm: canal y signo compatibles; sin comparar intensidad | **RECUPERACIÃ“N PARCIAL** |
| C12 | TW Hya | Tres picos Â«visiblesÂ»: 3,833 Âµm (salto entre detectores), 4,040 Âµm y 4,635 Âµm | BrÎ± 4,052 Âµm (la Ãºnica con seÃ±al esperable sobre el criterio) | BrÎ± cae en el canal del pico de 4,040 Âµm, pero con OVERFLOW y junto a un salto entre detectores; 4,635 Âµm discrepa | **NO EVALUABLE** |
| C14 | NÃºcleo de M51 | Pico Â«visibleÂ» de un canal en 3,293 Âµm (+18 %, 5,05Ã—) | PAH 3,3 Âµm en los ~0,8â€³ centrales (3,296 Âµm observado) | Canal y signo compatibles; aperturas no comparables | **RECUPERACIÃ“N PARCIAL** |

Ninguna caracterÃ­stica llegÃ³ a Â«cuantificableÂ». Los tres objetos tienen entre 99 y 100 de 102 canales con valor.

**Dictamen de generalizaciÃ³n: favorable pero limitado.**

- **A favor:**
  - con datos utilizables, el analizador seÃ±ala la longitud de onda de la banda de PAH de 3,3 Âµm en las dos galaxias donde cabe esperarla (C05 y C14);
  - no marca nada en ese canal en la estrella de control (TW Hya);
  - en C12 no confunde un salto entre detectores con un resultado limpio: lo avisa en sus propias advertencias.
- **LÃ­mites:**
  - tres objetos en total, de los cuales dos son galaxias;
  - nada cuantificable;
  - no se pudo comparar ninguna intensidad;
  - sin incertidumbres en el cubo.

Con V01 y NGC 7023, esto indica que el analizador funciona de forma conservadora y consistente con datos limpios, pero estas pruebas no demuestran una sensibilidad cuantitativa general.

## 2. DiagnÃ³stico de V02 (parte A)

Detalle en `SPECTRAL_V02_DIAGNOSIS.md` (commit `4403eaf`).

- Los canales sin valor de NGC 7027, M82 y Elias 29 vienen de pÃ­xeles de la apertura que en el propio FITS DR1 son NaN con NHITS = 0, marcados BLOOM (casi siempre con TRANSIENT y SUR_ERROR). No es saturaciÃ³n OVERFLOW, como escribÃ­ en V02.
- SkyClues invalida el canal entero con un solo pÃ­xel sin dato. Esa regla es deliberada y estÃ¡ documentada.
- Dictamen: **limitaciÃ³n del producto y de la extracciÃ³n en los tres** (en Elias 29 predomina el producto). No se encontrÃ³ ningÃºn defecto de cÃ³digo.

## 3. PreselecciÃ³n (parte B)

Detalle en `results/blind_v03/PRESELECCION.md`, registrado antes de medir (`18a7e79`, `155d9e5`). Criterios: â‰¥ 60 canales utilizables, tramo continuo â‰¥ 15, â‰¥ 4 detectores con â‰¥ 8 canales y fondo/seÃ±al â‰¤ 0,2. No se ejecutÃ³ el analizador de picos.

| Id | Objeto | Utilizables | DecisiÃ³n |
|---|---|---|---|
| C01 | Orion Bar | 3 | Rechazado: pocos canales (pÃ­xeles perdidos) |
| C02 | NGC 2023 | 66 | Rechazado: fondo/seÃ±al 0,37 |
| C03 | NGC 1333 | 49 | Rechazado: < 60 canales y solo 3 detectores |
| C04 | IC 63 | 100 | Rechazado: fondo/seÃ±al 0,66 |
| **C05** | **Arp 220** | 97 | **Aceptado** |
| C06 | NGC 1068 | 12 | Rechazado: pocos canales |
| C07 | Red Rectangle | 1 | Rechazado: casi sin datos |
| C08 | CRL 2688 | 17 | Rechazado: pocos canales |
| C09 | NGC 6543 | 29 | Rechazado: pocos canales |
| C10 | Cas A | 70 | Rechazado: fondo/seÃ±al 0,31 |
| C11 | Mrk 231 | 37 | Rechazado: < 60 canales y solo 3 detectores |
| **C12** | **TW Hya** | 77 | **Aceptado** |
| C13 | NGC 7293 | 7 | Rechazado: pocos canales y fondo 0,32 |
| **C14** | **NÃºcleo de M51** | 98 | **Aceptado** |

Se seleccionan los tres aceptados. No se forzaron cinco pruebas. QuedÃ³ sin cubrir la formaciÃ³n estelar y las nebulosas (G1 y G2), porque las regiones elegidas no pasaron los criterios de fondo.

## 4. Fase ciega y congelaciÃ³n (parte C)

- **Congelado** en `1d29ed3`: informes `C05/C12/C14/INFORME_CONGELADO.md`, `resultados.json`, figuras `espectro.png` y `campo.png`, y huellas SHA-256 en `RESUMEN_CONGELADO.md`.
- **ParÃ¡metros:** apertura de 2 px, anillo de 4â€“7 px, mÃ©todo `skyclues-features 1.0 (2026-11-14)`, sin comparaciÃ³n A/B (ninguna posiciÃ³n B tenÃ­a justificaciÃ³n independiente).
- **Ceguera procedimental.** Conozco la identidad de los candidatos por mi conocimiento general. La ceguera es de procedimiento: selecciÃ³n solo con criterios instrumentales fijados antes, sin publicaciones consultadas antes de congelar y sin ajustes de posiciÃ³n, fondo ni umbrales.

## 5. CaracterÃ­sticas encontradas (congeladas)

| Prueba | Î» (Âµm) | Tipo | Clase | Contraste | Contraste/dispersiÃ³n |
|---|---|---|---|---|---|
| C05 | 1,949 | valle, un canal | Visible | âˆ’7,2 mJy (âˆ’9,5 %) | 6,1 |
| C05 | 3,293 | pico, canales 63â€“64 | Visible | +15,7 mJy (+42 %) | 5,6 |
| C12 | 3,833 | pico ancho, canales 69â€“71 | Visible | +154 mJy (+57 %) | 7,4 |
| C12 | 4,040 | pico ancho, canales 74â€“76 | Visible | +206 mJy (+95 %) | 6,1 |
| C12 | 4,635 | pico, un canal | Visible | +120 mJy (+46 %) | 6,8 |
| C14 | 3,293 | pico, un canal | Visible | +60,7 mJy (+18 %) | 5,05 |

Se conservan tambiÃ©n 4, 5 y 7 anomalÃ­as por debajo del criterio (C05, C12 y C14) en los informes congelados.

## 6. ComparaciÃ³n con la literatura

Detalle y fuentes en `results/blind_v03/COMPARACION_LITERATURA.md`.

- **C05 Arp 220:** la PAH de 3,3 Âµm (3,35 Âµm observado, en el lÃ­mite de los canales 63 y 64) es compatible. Las bandas de hielo y COâ‚‚ no tienen referencia recuperada. Los estudios de AKARI de 2,5â€“5 Âµm que leÃ­ no incluyen Arp 220.
- **C12 TW Hya:** con los flujos de lÃ­nea de Vacca y Sandell 2011, BrÎ± aportarÃ­a unos 88 mJy en el canal 75; PfÎ², unos 24 mJy; PfÎ³, unos 3 mJy. El pico de 3,833 Âµm coincide con un salto de unos 130 a 425 mJy entre detectores (canales 68 y 69), y el de 4,635 Âµm es unas cinco veces mayor que lo que da PfÎ².
- **C14 M51a:** PAH de 3,3 Âµm detectada en los ~0,8â€³ centrales segÃºn Asmus et al. (que cita a Oi et al. 2010, que no leÃ­); la apertura de SPHEREx es 32 veces mayor.
- **ComprobaciÃ³n del canal 63:** exceso en cuatro espectros con PAH esperable y +1,4 % en la estrella de control. No es un artefacto comÃºn del canal (`control_canal63.json`).

## 7. Limitaciones

- **Muestra pequeÃ±a:** tres objetos, dos galaxias y una estrella. Faltan formaciÃ³n estelar y nebulosas.
- **Â«VisibleÂ», no Â«cuantificableÂ»:** el cubo no tiene incertidumbres. Una caracterÃ­stica en 5,05 veces la dispersiÃ³n estÃ¡ justo en el umbral.
- **Sin comparaciÃ³n de intensidades.** Las referencias que pude recuperar dan detecciÃ³n, no intensidad.
- **Aperturas:** muy distintas a las de las referencias (1,2â€³, 0,8â€³, 0,3â€³ frente a 25,8â€³).
- **ResoluciÃ³n R â‰ˆ 35â€“130:** el analizador no separa 3,3 de 3,4 Âµm ni resuelve lÃ­neas de H I.
- **Referencias incompletas.** Quedan sin referencia el hielo y el COâ‚‚ de Arp 220, la intensidad del PAH de M51a y la banda de CO de TW Hya. La bÃºsqueda de bibliografÃ­a fue limitada para conservar cuota.
- **Salto entre detectores en C12:** no investigado; puede deberse a OVERFLOW u otra calibraciÃ³n, sin determinar.
- **SIMBAD no se usÃ³** (fuera de servicio en V02); la identificaciÃ³n se hizo con NED.

## 8. Verificaciones

`scripts/v03_verify.py`, 27 comprobaciones, todas correctas:

- las huellas de `spectral_features.py`, `spectral_cube.py` y `geometry.py` coinciden con las de V02;
- los resultados congelados coinciden con sus huellas;
- los productos proceden de IRSA/SPHEREx DR1 (teselas 2168, 9595 y 2756), con la apertura por defecto;
- una reextracciÃ³n reproduce los espectros congelados.

Las referencias son artÃ­culos reales cuyas pÃ¡ginas se leyeron (Spoon et al. 2004, Vacca y Sandell 2011, Imanishi et al. 2008 y 2010) o cuyos resÃºmenes se obtuvieron por bÃºsqueda (Asmus et al. 2014 y Oi et al. 2010); ambos casos estÃ¡n diferenciados arriba.

No se repitiÃ³ la regresiÃ³n completa.

## 9. Archivos

`SPECTRAL_V02_DIAGNOSIS.md`, este informe, y en `results/blind_v03/`: `PROTOCOLO_PRESELECCION.md`, `PRESELECCION.md`, `preseleccion.json`, `C05/`, `C12/`, `C14/`, `RESUMEN_CONGELADO.md`, `COMPARACION_LITERATURA.md` y `control_canal63.json`. Scripts: `v02_diagnosis.py`, `v03_preselect.py`, `blind_v03.py`, `v03_frozen_reports.py` y `v03_verify.py`.
