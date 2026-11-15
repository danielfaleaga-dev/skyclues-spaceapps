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
