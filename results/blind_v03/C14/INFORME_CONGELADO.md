# C14 · informe congelado (fase ciega V03)

Sin consulta de publicaciones ni resolución de nombres en esta fase. Datos en `resultados.json`; figuras `espectro.png` (espectro completo) y `campo.png`.

## Datos de partida

- **Posición** (ICRS, nominal fijada en la preselección): RA 202.469583°, Dec +47.195278° (13h29m52.7s +47d11m43s). FOV 4′. No se ha desplazado.
- **Producto SPHEREx:** cubo DR1 HiPS orden 5, teselas 2756 (`hips_20261026`, DOI 10.26131/IRSA679).
- **Apertura:** 2 px (25.8″; 12.40 px efectivos). **Anillo de fondo:** 4–7 px (107 px), media con recorte 3σ.
- **Método:** `skyclues-features 1.0 (2026-11-14)`, huellas del código idénticas a las de V02 (`huellas_metodo.json`).
- **Cobertura del campo:** ≥ 99.3% de píxeles válidos; NHITS mediano 8–26.

## Canales y calidad

- **Con valor: 100 de 102.** Sin valor: 51–52 (canal sin datos en DR1 (BLANKCH)).
- **OVERFLOW/OUTLIER en la apertura:** 2 canales (34, 36).
- **Rango del flujo en apertura:** 187.1–772.3 mJy; canales con flujo ≤ 0: 0.
- **Dispersión mediana del anillo:** 0.3727 MJy/sr.

## Resultado del analizador (parámetros congelados)

**Características etiquetadas: 1.**

| Tipo | Clase | λ del extremo (µm) | Media altura (µm) | Canales | Contraste (mJy) | Relativo | Contraste/dispersión | Detectores |
|---|---|---|---|---|---|---|---|---|
| pico · estrecha | Visible | 3.293 | 3.242–3.342 | 63–63 | +60.65 | +17.9% | 5.1 | D4 |

- **3.293 µm** — continuo local 338.1 mJy; dispersión de referencia = máx(entorno 7.37, detector 6.73, fondo 8.02); entorno canales 58–60 y 66–68. Un solo canal: cada canal equivale a un elemento de resolución, así que no se distingue de un valor atípico del mosaico.

**Anomalías por debajo del criterio** (de 2,5 a 5 veces la dispersión):

| Canal | λ (µm) | Tipo | Intervalo | Contraste (mJy) | Relativo | Contraste/dispersión |
|---|---|---|---|---|---|---|
| 9 | 0.910 | pico | 7–11 | +63.29 | +18.1% | 3.00 |
| 14 | 1.025 | pico | 12–16 | +58.01 | +13.9% | 2.52 |
| 25 | 1.315 | pico | 22–28 | +46.15 | +8.1% | 3.25 |
| 30 | 1.481 | valle | 26–34 | -122.9 | -16.3% | 3.46 |
| 35 | 1.656 | pico | 31–39 | +146.9 | +23.5% | 2.94 |
| 60 | 3.033 | valle | 57–63 | -49.64 | -12.5% | 3.13 |
| 66 | 3.570 | valle | 64–68 | -51.12 | -13.7% | 2.60 |

**No evaluables (14):** 1–3, 48–55, 100–102.

## Conclusión registrada

Resultado descriptivo del analizador: pico visible en 3.293 µm (5.1×). Ninguna es una detección: el cubo no tiene incertidumbres. No se atribuye ninguna molécula ni se interpreta físicamente en esta fase.
