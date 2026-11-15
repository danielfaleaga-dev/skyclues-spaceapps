# V03 · identificación y comparación con la literatura (posterior a la congelación)

Fase ciega cerrada en el commit `1d29ed3`. Desde entonces no se ha modificado ningún resultado congelado ni el código (`scripts/v03_verify.py` lo comprueba).

## Identificación

| Id | Objeto | Cómo se identificó |
|---|---|---|
| C05 | **Arp 220** (ULIRG, z ≈ 0,0182) | NED: «ARP 220:[SDC94] 04» a 0,1″ de la posición |
| C12 | **TW Hya** (estrella T Tauri con disco) | NED devuelve 2MASS J11015191−3442170 a 0,2″. El nombre TW Hya procede de la elección del candidato, no de la etiqueta de NED |
| C14 | **M51a (NGC 5194), núcleo** (Seyfert 2/LINER, z = 0,001745) | NED: «MESSIER 051a» a 0,3″ |

## Referencias realmente consultadas

- **C05.**
  - Spoon et al. 2004, [arXiv:astro-ph/0310721](https://arxiv.org/abs/astro-ph/0310721), texto completo leído. Sobre 2,4–5 µm dice solo que la emisión de PAH se detecta en el espectro de 3 µm desde tierra (CGS4 con rendija de 1,2″, Imanishi y Dudley 2000), sin dar su intensidad. Da cz = 5450 km/s, es decir, z ≈ 0,0182.
  - Imanishi et al. 2008 ([arXiv:0808.0363](https://arxiv.org/abs/0808.0363)) y Imanishi et al. 2010 ([arXiv:1408.5975](https://arxiv.org/abs/1408.5975)). Son estudios de AKARI de 2,5–5 µm; leídos, **no incluyen Arp 220**.
  - No recuperé intensidades publicadas del hielo de H₂O de 3,05 µm, de la absorción de 3,4 µm ni de las bandas de CO₂ y CO de Arp 220. Quedan sin referencia.
- **C12.** Vacca y Sandell 2011, [arXiv:1102.0535](https://arxiv.org/abs/1102.0535), texto completo leído. Espectro SpeX de 0,8–5 µm (R ≈ 2000–2500, rendija de 0,3″). Flujos de línea en su Tabla 2, en unidades de 10⁻¹⁷ W m⁻²:
  - Pfγ 3,7404 µm: 7,70;
  - Brα 4,0523 µm: 62,38;
  - Pfβ 4,6538 µm: 12,57;
  - Huε 4,6727 µm: 1,46.

  No menciona PAH, hielos ni la banda fundamental de CO. Veiling de ~12 % entre 3 y 4 µm.
- **C14.** Asmus et al. 2014, [arXiv:1310.2770](https://arxiv.org/abs/1310.2770), vía resumen de búsqueda. Describe M51a como Seyfert 2 (a veces LINER) y cita la detección de PAH 3,3 µm en los ~0,8″ centrales (~31 pc) por Oi, Imanishi e Imase 2010 ([arXiv:1010.2756](https://arxiv.org/abs/1010.2756)). **No leí ese segundo artículo ni obtuve una anchura equivalente.**

## C05 · Arp 220

| Referencia evaluable | Dato SPHEREx | Evaluación |
|---|---|---|
| PAH 3,3 µm en emisión (detectada desde tierra). Con z = 0,0182 cae en 3,35 µm | Pico «visible» con extremo en el canal 63 (3,293 µm), media altura en los canales 63–64 (3,242–3,434 µm), +42 %, 5,6 veces la dispersión | **Compatible en longitud de onda y signo.** El valor esperado (3,35 µm) cae en el límite de los canales 63 (3,242–3,342) y 64 (3,330–3,434), y la media altura abarca ambos. No se puede comparar la intensidad: la referencia no la da |
| Hielo de H₂O 3,05 µm y absorción de 3,4 µm | Valle bajo el criterio en el canal 60 (3,033 µm), −21 %, 2,7× | **No evaluable:** sin referencia cuantificada y por debajo del criterio |
| CO₂ 4,26 µm y CO 4,67 µm | Sin rasgo | **No evaluable:** sin referencia |
| — | Valle «visible» de un solo canal en 1,949 µm (−9,5 %, 6,1×) | **Sin referencia.** Es un solo canal y el analizador avisa de que no se distingue de un valor atípico. No se interpreta |

- **Comparabilidad espacial.** La referencia es una rendija de 1,2″ (la región nuclear compacta). La apertura de SPHEREx tiene 25,8″ (unos 9 kpc a 73 Mpc), así que incluye toda la región circunnuclear. Son aperturas muy distintas.
- **Resolución.** R ≈ 35–40 en D4 (canales de ~0,09 µm). No separa 3,3 de 3,4 µm.
- **Dictamen: RECUPERACIÓN PARCIAL.** Se recupera el único elemento de referencia evaluable (PAH 3,3 µm), pero sin comparar intensidad; el resto no es evaluable por falta de referencias.

## C12 · TW Hya

Estimaciones de lo que añadiría cada línea de Vacca y Sandell en un canal de SPHEREx, con ΔFν ≈ F·λ²/(c·Δλ) (anchura del canal en la tabla; el perfil real de SPHEREx no es rectangular, así que son órdenes de magnitud):

| Línea | Flujo publicado | Canal SPHEREx | Exceso esperado |
|---|---|---|---|
| Pfγ 3,7404 µm | 7,7×10⁻¹⁷ W m⁻² | 68 (3,707–3,827) | ~3 mJy |
| Brα 4,0523 µm | 6,24×10⁻¹⁶ W m⁻² | 75 (4,020–4,059) | **~88 mJy** |
| Pfβ 4,6538 µm | 1,26×10⁻¹⁶ W m⁻² | 93 (4,649–4,688), al borde del 92 | ~24 mJy |

Dispersión de referencia del analizador: unos 14 mJy (detector).

| Dato SPHEREx | Evaluación |
|---|---|
| Pico «visible» de 3,985–4,095 µm (canales 74–76; extremo en 4,040 µm), contraste de +206 mJy sobre un continuo local de 216 mJy | **Brα cae dentro del canal 75, pero el contraste no es fiable.** El continuo local usa canales de D4 (129–184 mJy, 3,57–3,77 µm) y de D5 (320–330 mJy), así que está sesgado por el salto entre detectores. Dentro de D5, el flujo sube de 386 (canal 74) a 423 y 430 mJy (canales 75 y 76, ambos con OVERFLOW u OUTLIER) y baja a 323 mJy (canal 77, también con OVERFLOW). El aumento de unos 40 mJy es la mitad de lo esperado para Brα, pero no distingue una línea de una meseta |
| Pico «visible» ancho en 3,833 µm (canales 69–71) | **Coincide con el salto entre D4 y D5** (el flujo pasa de ~130 a ~425 mJy entre los canales 68 y 69; todos con OVERFLOW). No corresponde a ninguna línea de la lista. El analizador ya avisa de un posible escalón entre detectores |
| Pico «visible» de un solo canal en 4,635 µm (canal 92, +120 mJy) | **Discrepancia.** Pfβ (4,654 µm) caería en el canal 93 y aportaría ~24 mJy, no ~120. Sin explicación en la referencia |

- **Comparabilidad.** Se trata de una fuente puntual; las diferencias de apertura casi no importan. Pero la acreción de TW Hya varía con el tiempo y la referencia es de otra época.
- **Resolución.** Las líneas de H I están sin resolver en SPHEREx (R ≈ 110–130 en 4–4,7 µm).
- **Dictamen: NO EVALUABLE.** Brα es la única línea de referencia con señal esperable por encima del criterio, y su canal tiene OVERFLOW y queda pegado a un salto entre detectores. Con esos datos no se puede decir si se recupera.

## C14 · M51a, núcleo

| Referencia | Dato SPHEREx | Evaluación |
|---|---|---|
| PAH 3,3 µm detectada en los ~0,8″ centrales. Con z = 0,001745 cae en 3,296 µm | Pico «visible» de un solo canal: canal 63 (3,293 µm; 3,242–3,342), +18 %, 5,05 veces la dispersión | **Compatible en longitud de onda y signo** |
| Otros rasgos de la referencia | Sin referencia en lo consultado | **No evaluable** |

- **Comparabilidad espacial.** La referencia son ~0,8″ (31 pc) y la apertura de SPHEREx es de 25,8″ (unos 1,0 kpc), así que incluye mucha más región de formación estelar. No tengo una referencia que cuantifique el PAH a esa escala.
- **Intensidad.** No se compara: no recuperé la anchura equivalente publicada.
- **Fragilidad.** Está justo por encima del umbral de «visible» (5,05 frente a 5) y hay siete anomalías por debajo del criterio de entre 2,5 y 3,5 veces, así que otras fluctuaciones del mismo tamaño no son raras.
- **Dictamen: RECUPERACIÓN PARCIAL** (la más favorable de las tres): el único elemento evaluable coincide en canal y signo, pero no se compara intensidad y las aperturas no son comparables.

## Comprobación posterior: ¿es el canal 63 un artefacto común?

Cuatro espectros (M101 B, NGC 7023 B, C05 y C14) muestran un exceso en el canal 63 (3,293 µm), el mismo canal donde V01 recuperó la característica de M101. Para descartar un artefacto del canal medí ese canal aislado en todos los espectros congelados con datos de PAH esperable más una estrella (`control_canal63.json`; contraste frente al continuo local, sin cambiar el analizador):

| Espectro | Contraste relativo en el canal 63 | Contraste/dispersión |
|---|---|---|
| M101 A (núcleo) | +3,8 % | 0,55 |
| M101 B (NGC 5461) | +124 % | 3,39 |
| NGC 7023 A | +6,6 % | 0,32 |
| NGC 7023 B | +137 % | 3,42 |
| C05 (Arp 220) | +22 % | 2,84 |
| C14 (M51a) | +9,5 % | 3,53 |
| **C12 (TW Hya, estrella; control sin PAH esperable)** | **+1,4 %** | **0,02** |

La estrella, sin PAH esperable, no muestra nada en ese canal. Los excesos aparecen donde la emisión de PAH es esperable. Esto descarta un artefacto común del canal 63, pero no identifica ninguna molécula. Medido como canal aislado, ningún valor cruza el umbral de 5; la clasificación del analizador (que elige el intervalo y el entorno) es la que se informa en cada prueba.
