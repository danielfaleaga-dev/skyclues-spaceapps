# Validación ciega V02 · identificación y comparación (posterior a la congelación)

Fase ciega cerrada en el commit `a6bd9d4`. A partir de ahí no se modificó ningún resultado ni el algoritmo.

**Servicios externos.** SIMBAD devolvió HTTP 404 en dos intentos y queda registrado como bloqueo. La identificación se hizo con NED (IPAC): búsqueda por posición y resolución de nombres.

## Identificación

| Prueba | Objeto (NED) | Separación respecto de la posición dada | Tipo |
|---|---|---|---|
| T01 | **NGC 7027** | 0,8″ | Nebulosa planetaria joven, compacta (unos 10″) y muy brillante en el infrarrojo |
| T02 | **M82** (Messier 082), región nuclear | unos 2,6″ del centro de NED | Galaxia con brote de formación estelar, extensa (varios minutos de arco) |
| T03 | **Elias 29** (2MASS J16270943−2437187) | 0,3″ | Protoestrella de clase I en ρ Oph, muy enrojecida |

## Publicaciones usadas

- **T01**
  - Bernard-Salas et al. 2001, A&A 367, 949: espectro ISO-SWS de NGC 7027 ([resumen](https://ui.adsabs.harvard.edu/abs/2001A%26A...367..949B/abstract)). Abundantes líneas de H y He en 2,4–5,5 µm.
  - Cox et al. 2002: espectroimagen de H₂ 2,12 µm, Brγ y He I 2,11 µm ([PDF](https://www.aanda.org/articles/aa/pdf/2002/11/aa1784.pdf)).
- **T02**
  - Sturm et al. 2000, A&A 358, 481: ISO-SWS de 2,4–45 µm ([arXiv:astro-ph/0002195](https://arxiv.org/abs/astro-ph/0002195)).
  - Yamagishi et al. 2012 y 2013: AKARI/IRC de 2,5–5 µm, R ≈ 120. Detectan PAH 3,3 µm, rasgos de 3,4–3,6 µm, Brα 4,05 µm, Brβ 2,63 µm y hielos de H₂O y CO₂, este último concentrado cerca del centro ([arXiv:1203.2794](https://arxiv.org/abs/1203.2794), [arXiv:1308.2041](https://arxiv.org/abs/1308.2041)).
- **T03**
  - Boogert et al. 2000, A&A: espectro ISO-SWS de 1–200 µm, con apertura de unos 25″ ([arXiv:astro-ph/0005030](https://arxiv.org/abs/astro-ph/0005030)). Bandas medidas:
    - H₂O hielo 3,07 µm (τ = 1,85);
    - ala de 3,47 µm (τ = 0,06);
    - CO₂ hielo 4,27 µm;
    - CO hielo 4,673 µm;
    - CO gaseoso 4,4–5,0 µm;
    - Pfβ 4,653 µm en emisión.

No se consultaron los valores numéricos de flujo de línea de M82 ni de NGC 7027 dentro de una apertura de 25,8″. Ninguna de las comparaciones siguientes depende de esos valores.

## T01 · NGC 7027

| Característica de referencia | Canal SPHEREx (intervalo) | Dato SPHEREx | Evaluación |
|---|---|---|---|
| H y He en 2,4–5 µm (Brα, Pfund, He I) y bandas de PAH | 44–102 | Sin valor (NHITS = 0 en la apertura), salvo el canal 86, saturado | **No evaluable** |
| [S III] 0,953 / Paε 0,955 µm | 11 (0,942–0,967) | Sin valor | **No evaluable** |
| He I 1,083 µm / Paγ 1,094 µm | 16 (1,061–1,090) | Sin valor | **No evaluable** |
| Paβ 1,282 µm | 24 (1,267–1,300) | Sin valor | **No evaluable** |
| Paα 1,875 µm | 40–41 (1,838–1,928) | Sin valor | **No evaluable** |

- **Observación posterior.** Los canales sueltos sin valor por debajo de 2 µm coinciden con las longitudes de onda de las líneas de emisión más intensas esperables en una nebulosa planetaria. Es compatible con que la saturación ocurra precisamente en esas líneas.
- **Lo que no se afirma.** No es una recuperación por el analizador. Tampoco se ha verificado píxel a píxel que la causa sea la línea.
- **Resultado:** **NO EVALUABLE.** La fuente satura el cubo DR1 en la apertura en casi todos los canales donde están sus rasgos.

## T02 · M82, núcleo

| Referencia | Canal SPHEREx | Dato SPHEREx | Evaluación |
|---|---|---|---|
| Paα 1,875, Brγ 2,166, Brβ 2,626, PAH 3,3 y rasgos de 3,4–3,6 µm, hielo de H₂O | 39–68 (1,55–3,77 µm) | Sin valor | **No evaluable** |
| Paβ 1,282 µm (y [Fe II] 1,257 µm en el canal 23) | 24 (1,267–1,300) | Exceso de +92 % y 3,95× (por debajo de 5), con OVERFLOW | Signo y λ compatibles, **no etiquetado**; canal saturado |
| Brα 4,052 µm | 75 (4,020–4,059) | **Mínimo aislado** (2475 mJy, el único canal sin OVERFLOW de la zona) | **Discrepancia**: se esperaba emisión |
| — | 76 (4,055–4,095) | Exceso de +71 % y 3,73×, con OVERFLOW | No corresponde a Brα, que cae en el canal 75 |
| Pfβ 4,654 µm | 93 (4,649–4,688), en su borde azul | Pico **visible**, +47 % y 5,8×, con OVERFLOW en los canales 89–97 | Coincidencia en λ, **no concluyente** |
| Hielo de CO₂ 4,27 µm (absorción, centro) | 81–82 | Sin rasgo etiquetado; con OVERFLOW | No evaluable con datos saturados |

**Por qué no se aceptan las coincidencias:**

1. Todos los canales coincidentes llevan OVERFLOW.
2. Brα es normalmente más intensa que Pfβ y no aparece; su canal es incluso un mínimo.
3. Junto a ella (canal 76) hay un exceso de magnitud parecida que no corresponde a ninguna línea de referencia.

El patrón es más compatible con artefactos de saturación que con las líneas.

**Comparabilidad:** el anillo de fondo (51–90″) queda dentro del disco de M82, así que la resta elimina parte de la emisión extensa. ISO-SWS (unos 14″ × 20″) y las rendijas de AKARI no son aperturas comparables.

**Resultado:** **NO EVALUABLE.** Hay coincidencias de longitud de onda (Paβ por debajo del criterio y Pfβ «visible»), pero todas están en canales saturados y son incoherentes con la ausencia de Brα. No se cuenta como recuperación ni como fallo del algoritmo.

## T03 · Elias 29

| Referencia (Boogert et al. 2000) | Canal SPHEREx | Dato SPHEREx | Evaluación |
|---|---|---|---|
| Hielo de H₂O 3,07 µm (τ = 1,85) y ala de 3,47 µm | 57–66 | Sin valor (NHITS = 0) | **No evaluable** |
| Hielo de CO₂ 4,27 µm | 81 (4,235–4,277) | Único canal con valor por encima de 2,3 µm (1703 mJy), sin vecinos | **No evaluable**: no hay continuo local |
| Hielo de CO 4,673 µm, CO gaseoso 4,4–5,0 µm y Pfβ 4,653 µm | 86–102 | Sin valor | **No evaluable** |
| Continuo muy rojo (protoestrella enrojecida) | 1–49 | Flujo ≈ 0 por debajo de 1,3 µm, que sube hasta unos 365 mJy en 2,0 µm | Compatible con el carácter enrojecido descrito; no es una característica |

- **Observación posterior.** El único canal que conserva valor por encima de 2,3 µm es justo el que contiene la absorción de CO₂. Es compatible con que la absorción reduzca el flujo por debajo de la saturación. No se ha verificado y no es una recuperación del analizador.
- **Resultado:** **NO EVALUABLE.** Todas las bandas de referencia de 1–5 µm caen en canales sin valor.
