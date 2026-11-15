# C05 · informe congelado (fase ciega V03)

Sin consulta de publicaciones ni resolución de nombres en esta fase. Datos en `resultados.json`; figuras `espectro.png` (espectro completo) y `campo.png`.

## Datos de partida

- **Posición** (ICRS, nominal fijada en la preselección): RA 233.737917°, Dec +23.503056° (15h34m57.1s +23d30m11s). FOV 4′. No se ha desplazado.
- **Producto SPHEREx:** cubo DR1 HiPS orden 5, teselas 2168 (`hips_20261026`, DOI 10.26131/IRSA679).
- **Apertura:** 2 px (25.8″; 12.52 px efectivos). **Anillo de fondo:** 4–7 px (105 px), media con recorte 3σ.
- **Método:** `skyclues-features 1.0 (2026-11-14)`, huellas del código idénticas a las de V02 (`huellas_metodo.json`).
- **Cobertura del campo:** ≥ 98.9% de píxeles válidos; NHITS mediano 7–17.

## Canales y calidad

- **Con valor: 100 de 102.** Sin valor: 51–52 (canal sin datos en DR1 (BLANKCH)).
- **OVERFLOW/OUTLIER en la apertura:** 3 canales (19, 21, 30).
- **Rango del flujo en apertura:** 24.6–79.5 mJy; canales con flujo ≤ 0: 0.
- **Dispersión mediana del anillo:** 0.01053 MJy/sr.

## Resultado del analizador (parámetros congelados)

**Características etiquetadas: 2.**

| Tipo | Clase | λ del extremo (µm) | Media altura (µm) | Canales | Contraste (mJy) | Relativo | Contraste/dispersión | Detectores |
|---|---|---|---|---|---|---|---|---|
| valle · estrecha | Visible | 1.949 | 1.925–1.973 | 42–42 | -7.195 | -9.5% | 6.1 | D3 |
| pico · estrecha | Visible | 3.293 | 3.242–3.434 | 63–64 | +15.74 | +42.3% | 5.6 | D4 |

- **1.949 µm** — continuo local 75.37 mJy; dispersión de referencia = máx(entorno 0.623, detector 0.972, fondo 0.152); entorno canales 39–41 y 43–45. Un solo canal: cada canal equivale a un elemento de resolución, así que no se distingue de un valor atípico del mosaico.
- **3.293 µm** — continuo local 37.17 mJy; dispersión de referencia = máx(entorno 1.75, detector 1.88, fondo 0.129); entorno canales 58–60 y 66–68. 

**Anomalías por debajo del criterio** (de 2,5 a 5 veces la dispersión):

| Canal | λ (µm) | Tipo | Intervalo | Contraste (mJy) | Relativo | Contraste/dispersión |
|---|---|---|---|---|---|---|
| 36 | 1.695 | pico | 34–38 | +4.15 | +5.6% | 2.92 |
| 60 | 3.033 | valle | 56–64 | -9.958 | -20.6% | 2.69 |
| 88 | 4.500 | pico | 84–92 | +13 | +44.4% | 3.07 |
| 96 | 4.773 | pico | 95–97 | +15.97 | +47.7% | 4.73 |

**No evaluables (14):** 1–3, 48–55, 100–102.

## Conclusión registrada

Resultado descriptivo del analizador: valle visible en 1.949 µm (6.1×), pico visible en 3.293 µm (5.6×). Ninguna es una detección: el cubo no tiene incertidumbres. No se atribuye ninguna molécula ni se interpreta físicamente en esta fase.
