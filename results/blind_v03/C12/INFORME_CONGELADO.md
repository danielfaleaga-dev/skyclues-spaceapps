# C12 · informe congelado (fase ciega V03)

Sin consulta de publicaciones ni resolución de nombres en esta fase. Datos en `resultados.json`; figuras `espectro.png` (espectro completo) y `campo.png`.

## Datos de partida

- **Posición** (ICRS, nominal fijada en la preselección): RA 165.466250°, Dec -34.704722° (11h01m51.9s -34d42m17s). FOV 4′. No se ha desplazado.
- **Producto SPHEREx:** cubo DR1 HiPS orden 5, teselas 9595 (`hips_20261026`, DOI 10.26131/IRSA679).
- **Apertura:** 2 px (25.8″; 12.44 px efectivos). **Anillo de fondo:** 4–7 px (105 px), media con recorte 3σ.
- **Método:** `skyclues-features 1.0 (2026-11-14)`, huellas del código idénticas a las de V02 (`huellas_metodo.json`).
- **Cobertura del campo:** ≥ 99.6% de píxeles válidos; NHITS mediano 8–21.

## Canales y calidad

- **Con valor: 99 de 102.** Sin valor: 32, 51–52 (apertura con píxeles sin datos (NHITS = 0); canal sin datos en DR1 (BLANKCH)).
- **OVERFLOW/OUTLIER en la apertura:** 22 canales (1–5, 53–61, 69–73, 75–77).
- **Rango del flujo en apertura:** 53.2–575.0 mJy; canales con flujo ≤ 0: 0.
- **Dispersión mediana del anillo:** 0.01285 MJy/sr.

## Resultado del analizador (parámetros congelados)

**Características etiquetadas: 3.**

| Tipo | Clase | λ del extremo (µm) | Media altura (µm) | Canales | Contraste (mJy) | Relativo | Contraste/dispersión | Detectores |
|---|---|---|---|---|---|---|---|---|
| pico · amplia | Visible | 3.833 | 3.814–3.919 | 69–71 | +154 | +56.8% | 7.4 | D4, D5 |
| pico · amplia | Visible | 4.040 | 3.985–4.095 | 74–76 | +206.2 | +95.2% | 6.1 | D4, D5 |
| pico · estrecha | Visible | 4.635 | 4.615–4.653 | 92–92 | +119.8 | +46.0% | 6.8 | D6 |

- **3.833 µm** — continuo local 271.2 mJy; dispersión de referencia = máx(entorno 8.46, detector 14.1, fondo 0.217); entorno canales 62–64 y 74–76. Píxeles de entrada con OVERFLOW u OUTLIER en los canales 69, 70, 71, 72, 73: el valor puede no ser fiable. El intervalo y su entorno abarcan los detectores D4, D5: calibración y resolución distintas pueden producir un escalón. Algún canal del entorno tiene OVERFLOW u OUTLIER: el continuo puede estar afectado. Característica ancha: si se extiende más allá del intervalo, el entorno la incluye y el contraste queda subestimado.
- **4.040 µm** — continuo local 216.5 mJy; dispersión de referencia = máx(entorno 27.8, detector 14.1, fondo 0.223); entorno canales 66–68 y 77–79. Píxeles de entrada con OVERFLOW u OUTLIER en los canales 75, 76: el valor puede no ser fiable. El intervalo y su entorno abarcan los detectores D4, D5: calibración y resolución distintas pueden producir un escalón. Algún canal del entorno tiene OVERFLOW u OUTLIER: el continuo puede estar afectado.
- **4.635 µm** — continuo local 260.3 mJy; dispersión de referencia = máx(entorno 11.5, detector 14.3, fondo 0.332); entorno canales 89–91 y 93–95. Un solo canal: cada canal equivale a un elemento de resolución, así que no se distingue de un valor atípico del mosaico.

**Anomalías por debajo del criterio** (de 2,5 a 5 veces la dispersión):

| Canal | λ (µm) | Tipo | Intervalo | Contraste (mJy) | Relativo | Contraste/dispersión |
|---|---|---|---|---|---|---|
| 38 | 1.775 | valle | 37–39 | -33.89 | -38.9% | 4.29 |
| 39 | 1.818 | pico | 38–40 | +23.02 | +33.6% | 2.55 |
| 77 | 4.112 | valle | 76–78 | -75.13 | -18.9% | 2.56 |
| 80 | 4.220 | valle | 76–84 | -164.1 | -35.1% | 2.69 |
| 86 | 4.435 | pico | 82–90 | +72.59 | +29.5% | 3.02 |

**No evaluables (25):** 1–3, 29–35, 48–55, 66–67, 78–79, 100–102.

## Conclusión registrada

Resultado descriptivo del analizador: pico visible en 3.833 µm (7.4×), pico visible en 4.040 µm (6.1×), pico visible en 4.635 µm (6.8×). Ninguna es una detección: el cubo no tiene incertidumbres. No se atribuye ninguna molécula ni se interpreta físicamente en esta fase.
