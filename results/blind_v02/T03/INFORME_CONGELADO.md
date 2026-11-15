# T03 · informe congelado (fase ciega)

Sin identificar el objeto y sin consultas externas. Datos en `resultados.json`; figuras en `espectro.png` (espectro completo) y `campo.png`.

## Datos de partida

- **Posición** (ICRS, dada en el encargo): `16h27m09.43s −24°37′18.5″`, es decir, RA 246,789292° y Dec −24,621806°. FOV de 4′. La posición no se ha desplazado.
- **Producto SPHEREx:** cubo DR1 HiPS de orden 5, tesela 10745.
- **Apertura:** radio de 2 px (25,8″; 12,48 px efectivos).
- **Fondo:** anillo de 4–7 px (102 px). La dispersión mediana del anillo es 0,024 MJy/sr.
- **Cobertura del campo:** ≥ 92,5 % de píxeles válidos en los canales con datos.
- **Morfología:**
  - **0,75–1,09 µm:** campo casi uniforme, sin fuente central apreciable.
  - **4,4–5,0 µm:** fuente central compacta muy brillante.

  Es una fuente extremadamente roja.

## Canales y calidad

**Con valor: 50 de 102** (1–49 y 81).

**Sin valor: 52.** De ellos, 50 tienen la apertura con píxeles sin datos (NHITS = 0) desde unos 2,3 µm; los canales 51 y 52 no tienen datos en DR1.

**Indicadores:**
- OVERFLOW/OUTLIER en los canales 39–43 (1,8–2,0 µm);
- en la apertura, BLOOM, TRANSIENT y SUR_ERROR en 50 canales, y PERSIST en 5.

**Flujo:**
- por debajo de 1,3 µm: −0,6 a unos 3 mJy, compatible con cero;
- crece de forma continua hasta unos 365 mJy en 2,0 µm;
- 190–250 mJy en 2,05–2,3 µm;
- el canal 81 (unos 4,26 µm) tiene un valor aislado de 1703 mJy, con los vecinos sin datos.

## Resultado del analizador (parámetros congelados)

**Características etiquetadas: ninguna.**

**Anomalías por debajo del criterio:**

| Canal | λ (µm) | Tipo | Intervalo | Contraste | Relativo | Contraste/dispersión |
|---|---|---|---|---|---|---|
| 11 | 0,955 | pico | 7–15 | +0,89 mJy | — (continuo ≈ 0) | 2,51 |
| 43 | 1,995 | pico | 43 | +113,9 mJy | +45 % | 3,07 |

El canal 43 tiene OVERFLOW/OUTLIER. En 1,8–2,0 µm hay un máximo con saturación parcial, seguido de un descenso a 2,05 µm.

**No evaluables: 60 canales.** Hay dos causas: 52 canales sin valor en el intervalo, y 8 sin entorno suficiente.

## Contaminación y limitaciones

- **Saturación.** Por encima de unos 2,3 µm la apertura pierde píxeles en todos los canales salvo el 81, así que esa región del espectro no puede evaluarse.
- **Rango de 1,8–2,0 µm:** parcialmente saturado.
- **Por debajo de 1,3 µm:** la señal es compatible con cero; no hay continuo con el que comparar.

## Conclusión registrada

**Sin características etiquetadas.** Solo es evaluable el tramo de 0,75–2,3 µm, que corresponde a un continuo rojo creciente. El tramo de 2,3–5 µm no es evaluable por saturación o pérdida de píxeles.
