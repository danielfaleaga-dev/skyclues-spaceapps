# T02 · informe congelado (fase ciega)

Sin identificar el objeto y sin consultas externas. Datos en `resultados.json`; figuras en `espectro.png` (espectro completo) y `campo.png`.

## Datos de partida

- **Posición** (ICRS, dada en el encargo): `09h55m52.430s +69°40′46.93″`, es decir, RA 148,968458° y Dec +69,679703°. FOV de 12′. La posición no se ha desplazado.
- **Producto SPHEREx:** cubo DR1 HiPS de orden 5, teselas 1901 y 1903.
- **Apertura:** 2 px (25,8″; 12,64 px efectivos).
- **Fondo:** anillo de 4–7 px (97 px). La dispersión mediana del anillo es 0,401 MJy/sr.
- **Cobertura del campo:** ≥ 99,6 % de píxeles válidos en los canales con datos.
- **Morfología** (imágenes de 0,75–1,09 y 4,4–5,0 µm): fuente extensa y alargada de noreste a suroeste, de varios minutos de arco. El anillo de fondo (51–90″) queda dentro de esa emisión extensa.

## Canales y calidad

- **Con valor: 65 de 102.** Son los canales 1–31 y 69–102.
- **Sin valor: 37.**
  - 35 tienen la apertura con píxeles sin datos (NHITS = 0) en 1,55–3,77 µm.
  - Los otros dos son los canales 51 y 52, sin datos en DR1.
- **Saturación:** OVERFLOW u OUTLIER en 75 canales, que son casi todos los de 1,0–1,5 µm y de 3,8–5,0 µm.
- **Otros indicadores en la apertura:** SOURCE (100), BLOOM (35), TRANSIENT (33), SUR_ERROR (27), HALO (4) y PERSIST (3).
- **Flujo:** de 508 mJy (0,75 µm) a unos 3000–3700 mJy en 3,8–5 µm.

## Resultado del analizador (parámetros congelados)

**Características etiquetadas: una.**

| Tipo | Clase | λ (µm) | Canales | Valor | Continuo | Contraste | Relativo | Contraste/dispersión | Detector |
|---|---|---|---|---|---|---|---|---|---|
| Pico estrecho | **Visible** | 4,669 (4,649–4,688) | 93 | 4284 mJy | 2906 mJy | +1378 mJy | +47,4 % | 5,8 | D6 |

- **Dispersión de referencia** (la mayor de las tres): 126,9 mJy, la del detector. Las otras son 65,0 (entorno) y 5,7 (fondo).
- **Limitaciones registradas por el método:**
  - OVERFLOW u OUTLIER en los canales 89–97, incluido el propio canal 93;
  - el entorno también está afectado;
  - es un solo canal, que no se distingue de un valor atípico del mosaico.

**Anomalías por debajo del criterio** (de 2,5 a 5 veces la dispersión):

| Canal | λ (µm) | Tipo | Intervalo | Contraste | Relativo | Contraste/dispersión |
|---|---|---|---|---|---|---|
| 24 | 1,284 | pico | 20–28 | +1157 mJy | +92 % | 3,95 |
| 76 | 4,076 | pico | 76 | +2131 mJy | +71 % | 3,73 |

- El canal 76 es el valor máximo del espectro (5150 mJy) y tiene OVERFLOW.
- Junto a él, el canal 75 (4,040 µm) tiene un valor bajo aislado (2475 mJy), el único de esa zona sin indicador de saturación.

**No evaluables: 53 canales.**
- 37 no tienen valor en el intervalo.
- 16 no tienen entorno suficiente (8 por cada lado), por estar en un borde o junto a un hueco.

## Contaminación y limitaciones

- **Saturación generalizada.** La pendiente de 1–1,5 µm y todo el tramo de 3,8–5 µm están marcados con OVERFLOW.
- **Fuente extensa.** El anillo de fondo resta la propia emisión del objeto.
- **Hueco en 1,55–3,77 µm:** no se puede evaluar nada ahí.

## Conclusión registrada

Un pico **visible** de un solo canal en 4,669 µm, sobre canales saturados. Dos excesos por debajo del criterio, en 1,284 µm y 4,076 µm. Nada cuantificable. La mayor parte del intervalo de 1,5–3,8 µm no es evaluable.
