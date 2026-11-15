# Observaciones reales evaluadas

Productos SPHEREx DR1 L2b v27. Las coordenadas son predicciones por exposición, no detecciones. Cada informe conserva URL original/recorte, SHA-256, WCS y calidad. Ningún caso demuestra movimiento observado.

| Caso | Exposición | Fecha media UTC | Detector | λ (µm) | Estado por imagen |
|---|---|---|---:|---:|---|
| [atlas_aug_continuum](atlas_aug_continuum.json) | 2025W32_2D_0343_3 | 2025-08-09T08:29:46.957 | 1 | 1.00905 | Posición prevista |
| [atlas_aug_continuum](atlas_aug_continuum.json) | 2025W33_1B_0642_1 | 2025-08-14T10:42:00.393 | 1 | 1.01022 | Señal candidata |
| [atlas_aug_co2_a](atlas_aug_co2_a.json) | 2025W32_2D_0189_4 | 2025-08-08T12:56:01.565 | 5 | 4.23622 | Señal candidata |
| [atlas_aug_co2_b](atlas_aug_co2_b.json) | 2025W33_1B_0599_1 | 2025-08-14T05:48:27.524 | 5 | 4.26080 | Señal candidata |
| [atlas_dec_continuum](atlas_dec_continuum.json) | 2025W50_2A_0698_1 | 2025-12-14T06:02:09.050 | 2 | 1.33618 | Posición prevista |
| [atlas_dec_co2](atlas_dec_co2.json) | 2025W50_2A_0712_1 | 2025-12-14T07:40:55.263 | 5 | 4.24744 | Posición prevista |
| [atlas_dec_repeat](atlas_dec_repeat.json) | 2025W50_1A_0002_1 | 2025-12-08T00:07:26.147 | 4 | 2.44069 | Señal candidata |
| [atlas_dec_repeat](atlas_dec_repeat.json) | 2025W50_1A_0002_2 | 2025-12-08T00:09:35.079 | 4 | 2.44070 | Señal candidata |
| [vesta_real](vesta_real.json) | 2025W32_1A_0225_1 | 2025-08-05T00:07:59.490 | 3 | 1.95478 | Posición prevista |
| [pluto_real](pluto_real.json) | 2025W41_1A_0019_1 | 2025-10-06T02:02:34.756 | 3 | 1.92000 | Señal candidata |
| [comet_29p_real](comet_29p_real.json) | 2025W17_4B_0411_4 | 2025-04-27T11:29:41.071 | 4 | 2.66280 | Posición prevista |
| [comet_29p_real](comet_29p_real.json) | 2025W50_1A_0148_4 | 2025-12-08T14:55:29.871 | 4 | 2.66501 | Posición prevista |
| [stationary_m101](stationary_m101.json) | 2026W20_2A_0464_1 | 2026-05-17T10:54:42.815 | 2 | 1.42020 | Señal candidata |
| [stationary_m101](stationary_m101.json) | 2026W21_2A_0081_1 | 2026-05-22T00:06:14.504 | 2 | 1.41513 | Señal candidata |
| [stationary_m101](stationary_m101.json) | 2026W25_2A_0170_1 | 2026-06-19T07:39:37.150 | 2 | 1.41509 | Señal candidata |
| [stationary_m101](stationary_m101.json) | 2026W26_1A_0178_1 | 2026-06-22T20:22:30.749 | 2 | 1.42058 | Señal candidata |

M101 es un campo estacionario real de control: una señal candidata en él no identifica un cuerpo móvil. Los FITS de ese control ya formaban parte de las referencias del proyecto.

Las imágenes de CO₂ de agosto se analizan por separado porque no cumplen la compatibilidad espectral. La corrección temporal de MOST se aplicó nuevamente a Vesta, Plutón y 29P; se preservan los informes finales de esa repetición.

## Movimiento medido (15-11-2026)

Secuencias elegidas por `moving_sources.motion_groups`: mismo detector, horas o días de diferencia, cielo común. Cada informe guarda las posiciones medidas, las pruebas de aparición/desaparición, las estrellas de control y la comparación final con la efeméride. Figuras `*_first.png` y `*_second.png`: las dos imágenes de la medida sobre el mismo fondo estelar.

| Informe | Objeto | Exposiciones | Resultado |
|---|---|---|---|
| [atlas_aug_motion_d1](atlas_aug_motion_d1.json) | 3I/ATLAS | 2025W32_2D_0343_1–4, 0355_1–3 (D1) | Movimiento observado: 165,8″ ± 2,7″ en 99 min |
| [atlas_aug_motion_co2](atlas_aug_motion_co2.json) | 3I/ATLAS | 2025W32_2D_0189_1–4, 0201_1–3 (D5) | Movimiento observado: 156,1″ ± 4,4″ en 95 min |
| [atlas_aug_motion_d2](atlas_aug_motion_d2.json) | 3I/ATLAS | 2025W32_2D_0189_1–4, 0201_1–4 (D2) | No demostrado: posiciones a menos de tres píxeles |
| [atlas_dec_motion_d2](atlas_dec_motion_d2.json) | 3I/ATLAS | 2025W50_2A_0685_1–4, 0698_1–4 (D2) | Movimiento observado: 293,9″ ± 4,4″ en 101 min |
| [atlas_dec_motion_co2](atlas_dec_motion_co2.json) | 3I/ATLAS | las mismas exposiciones, D5 | Movimiento observado: 293,9″ ± 4,4″ en 101 min |
| [pluto_motion](pluto_motion.json) | Plutón | 2025-10-06 → 10-12 (D1) | Movimiento observado: 50,2″ ± 4,9″ en 148,3 h |
| [pluto_motion_d3](pluto_motion_d3.json) | Plutón | 2025-09-25 → 10-07 (D3) | Movimiento observado: 247,0″ ± 4,4″ en 265,7 h |
| [juno_motion](juno_motion.json) | 3 Juno | 2025-07-13 → 07-14 (D1) | Movimiento observado: 214,8″ ± 8,7″ en 24,4 h |
| [vesta_motion](vesta_motion.json), [vesta_motion_d2](vesta_motion_d2.json) | 4 Vesta | 2025-07-08 (D1), 2025-06-28/29 (D2) | No evaluable: núcleo saturado |
| [stationary_m101](stationary_m101.json) | Control M101 | cuatro épocas de referencia | Sin movimiento |

Resumen completo, con los seis controles de predicción desplazada: [motion_validation_summary.json](motion_validation_summary.json). Las filas de la tabla superior conservan los informes de la primera validación, hechos con la máscara estricta y parejas de la misma longitud de onda.
