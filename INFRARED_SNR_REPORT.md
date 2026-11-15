# Mejora infrarroja de S/N: método, validación real y límites

Actividad `SKYCLUES_SPHEREX_INFRARED_SNR_ENHANCEMENT_01`, desarrollada por Claude Code B. Claude Code A la cerró en el relevo `SKYCLUES_SNR_HANDOFF_AND_COMPLETION_01`. Método `infrared-snr 1.0 (2026-11-15)` (`skyclues/enhance.py`). Trabajo local, sin push ni despliegue.

## Qué hace

La función combina varias exposiciones auténticas de nivel 2 de SPHEREx, todas del **mismo detector**, que cubren el mismo cielo. Usa una media ponderada por la varianza inversa de cada exposición. No es un filtro estético:

- **Colocación.** Cada píxel de salida copia el valor del píxel nativo que contiene su centro, según el WCS de cada exposición. No interpola, no rellena y no suaviza.
- **Máscara.** Se aplica la máscara estricta oficial: solo entran píxeles finitos, con varianza > 0 y sin banderas inutilizables ni de artefacto. Un píxel sin ninguna exposición válida queda NaN.
- **Nivel de cielo.** Cada exposición recibe una constante aditiva de cielo, la mediana de su diferencia con la referencia; el conjunto de constantes suma cero. Esa constante no puede crear ni borrar una fuente.
- **Sin recorte sigma.** El único valor que se descarta además de la máscara oficial es el negativo no físico: un píxel más de 5σ por debajo de su cielo local y, a la vez, de las demás exposiciones. El número de descartes se informa.
- **Peso por exposición, no por píxel.** La varianza oficial incluye el ruido fotónico de la propia fuente, así que un peso por píxel infravaloraba las fuentes brillantes (−5 % medido en M101).
- **Errores.** Se propagan de forma exacta a través de la colocación (`linear_stat`): un píxel nativo copiado en varios de salida se cuenta una sola vez. Después se contrastan con una **imagen nula**, (mitad A − mitad B)/2, y se multiplican por su factor empírico cuando es mayor que 1. Nunca se reducen.

## Dos productos y tres objetivos separados

| Producto | Exposiciones | Qué representa |
|---|---|---|
| Mismo canal | Las fechas de la secuencia de Time Explorer, con el mismo canal LVF (dispersión ≤ `SPECTRAL_WARN_BW`) | Brillo monocromático comparable |
| Banda ancha | Exposiciones del mismo detector a ±7 días de una fecha, como máximo 12 | Sirve para detectar y situar fuentes. **No** vale para medir brillo monocromático ni para compararlo entre fechas. Se rotula «banda ancha» en los dos niveles |

- **Cielo estacionario.** Es el único producto que se muestra en la interfaz. Si el objetivo se mueve más de 0,5 píxeles entre la primera y la última fecha, la combinación se rechaza.
- **Objeto móvil.** Combinación que sigue la efeméride, solo en `scripts/validate_enhance.py`. Admite píxeles `OUTLIER` únicamente en la apertura del objeto y se controla con trayectorias desplazadas. **No se adopta para medir movimiento.**
- **Comparación entre épocas.** Cada fecha se combina por separado. `motion.py` y `non_sidereal.py` no usan este módulo y no cambian respecto a `d01917e`.

## Cómo se mide la mejora

- **Ganancia S/N.** Cociente entre la S/N de la **misma fuente**, con la misma apertura (1,5 px nativos menos un anillo de 3–6 px), en la combinación y en cada exposición sobre la misma rejilla. Se toma la mediana de las fuentes con S/N individual > 3, y se calcula también frente a la mejor exposición. No se confunde con la reducción del ruido por píxel, que se informa aparte.
- **Comprobación sin modelo (repetibilidad).** Compara la dispersión del flujo de apertura entre dos exposiciones con la de dos mitades independientes, sin usar ningún modelo de varianza.
- **Controles de aceptación** (`enhance.verdict`):
  - ganancia ≥ 1,2, también frente a la mejor exposición;
  - picos espurios en la imagen nula y en la imagen invertida ≤ máx(1, 5 % de las detecciones);
  - PSF ensanchada ≤ 25 %;
  - desplazamiento del centroide ≤ ¼ de píxel;
  - flujo de fuentes brillantes dentro de ±5 %.

  Una combinación que no supera estos controles se muestra como «No disponible para estas observaciones», con el motivo.

## Resultados con datos reales

Datos en `results/enhance/` (un JSON por caso, con URL y SHA-256 de cada recorte, figuras y `enhance_validation_summary.json`). Las cifras se generaron con el código final el 15-11-2026 a las 16:21 UTC. En el relevo, M101 · secuencia y WISE 0855 · noviembre de 2025 se recalcularon desde la caché con resultado **idéntico** en todos los campos.

| Caso | N | Detector · λ (µm) | Intervalo | Ganancia S/N (p16–p84) · frente a la mejor · √N | Flujo | PSF | Imagen nula: espurias | Resultado |
|---|---:|---|---:|---|---:|---:|---:|---|
| M101 · secuencia (mismo canal) | 4 | D2 · 1,415–1,421 | 36,4 d | **1,88** (1,79–1,94) · 1,87 · 2,00 | 1,000 | ×1,09 | 0 | Aceptado |
| M101 · D2 · dic. 2025 (banda ancha) | 12 | D2 · 1,13–1,61 | 2,8 d | **2,91** (2,81–3,02) · 3,13 · 3,46 | 1,002 | ×1,12 | 3 (límite 3,85) | Aceptado |
| WISE 0855−0714 · D6 · nov. 2025 | 12 | D6 · 4,42–4,77 | 4,2 d | **3,49** (3,37–3,58) · 3,08 · 3,46 | 1,018 | ×1,12 | 0 | Aceptado |
| WISE 0855−0714 · D6 · dic. 2025 | 3 | D6 · 4,63–4,74 | 0,8 d | **1,69** · 1,67 · 1,73 | 0,974 | ×1,07 | 0 | Aceptado |
| WISE 0855−0714 · D6 · abr.–may. 2026 | 10 | D6 · 4,75–4,93 | 13,8 d | **3,07** · 2,81 · 3,16 | 1,005 | ×1,04 | 0 | Aceptado |
| WISE 0855−0714 · D6 · may. 2025 | 2 | D6 · 4,86–4,97 | 0,1 d | 1,41 | 1,001 | — | 0 | **Rechazado**: 2 detecciones en la imagen invertida |
| 3I/ATLAS · D1 · siguiendo la efeméride | 7 | D1 · 0,96–1,11 | 1,7 h | objeto: S/N 39,5 frente a 16 (mediana), ganancia 2,39 | — | — | trayectorias desplazadas: −4,0 / −3,1 / 3,1 | No adoptado: el movimiento ya se mide en cada exposición |
| 3 Juno · D1 | 8 | D1 · 0,75–0,96 | 1,0 d | — | — | — | — | No adoptado: núcleo saturado en 7 de 8 |
| 4 Vesta · D1 | 5 | D1 · 0,83–1,10 | 0,2 d | — | — | — | — | No evaluable: núcleo saturado en 5 de 5 |

**Medidas astronómicas que mejoran (WISE 0855, objeto débil):**
- **Noviembre de 2025.** La S/N del objetivo pasa de ≤ 5,4 por exposición (no medible en 4 de 12) a **12,6** en la combinación. La combinación detecta 29 fuentes nuevas ≥ 5σ y las 29 tienen contrapartida en AllWISE; por azar se esperaría un 16 %.
- **Abril–mayo de 2026.** 19 de 20 fuentes nuevas tienen contrapartida en AllWISE.
- **Posiciones frente al catálogo.** La mediana de la diferencia con AllWISE pasa de 0,87″ por exposición a 0,77″ en la combinación (noviembre de 2025). Ese 0,87″ es una mediana sobre los ajustes individuales posibles, solo 144 de 444. La mejora es pequeña.
- **M101 de banda ancha.** Frente a 2MASS ocurre lo contrario: 0,94″ en la combinación y 0,70″ por exposición. La combinación no mejora la astrometría de fuentes brillantes, y no se usa para medir posiciones ni movimiento.

**Conservación de flujo y resolución.** En los casos aceptados, el cociente de flujo combinación / media de exposiciones queda entre 0,974 y 1,018. La PSF se ensancha entre ×1,04 y ×1,12, por debajo del límite de 1,25. La causa es la colocación por vecino más próximo, con un error de registro rms propio de unos 0,5″. El desplazamiento del centroide es de 0,07–0,32″, con píxeles de 6,15″.

**Sobre la cifra ×3,44 de M101 comunicada antes.** Correspondía a un grupo exploratorio distinto: 12 exposiciones DR1 de M101 en D2 repartidas a lo largo de **210 días**, 80 fuentes. En el relevo, el código final reproduce exactamente **3,44** sobre ese grupo. El producto final no lo usa, porque solo combina exposiciones a ±7 días de una fecha y no presupone estabilidad del cielo durante meses. El caso equivalente validado (diciembre de 2025, 12 exposiciones en 2,8 días) da **2,91**. En ese grupo la imagen nula muestra un exceso de ruido de ×1,38 sobre el error formal, y los errores se escalan por ese factor. La comprobación sin modelo coincide con la ideal (2,44 frente a 2,45).

## Interfaz (Time Explorer, pestaña «Secuencia»)

Interruptor **«Mejora infrarroja»** y selector «Qué combinar». Estados: *Disponible*, *Procesando*, **Imagen mejorada** y **No disponible para estas observaciones**. La interfaz muestra una exposición y la combinación con la misma escala de brillo. Las decisiones visuales están en `DESIGN_SYSTEM.md`.

Correcciones del relevo:
- Al cambiar de región, «Qué combinar» vuelve a las fechas de la nueva secuencia. Antes conservaba el índice de una fecha de la región anterior.
- Los círculos no se presentan como fuentes cuando la imagen nula, que solo contiene ruido, da tantos picos como fuentes nuevas hay. Es el caso de M101 de banda ancha: 3 nuevas, 0 de 3 con contrapartida en 2MASS y 3 picos en la imagen nula.
- Se añade una frase breve sobre qué significa la ganancia en cada nivel.

La S/N individual y la combinada del objetivo de la región solo se muestran cuando el objetivo es débil (S/N < 30 por exposición). En una fuente brillante, la S/N de apertura depende de la fase del píxel y no describe la mejora.

## Límites

- **Banda ancha.** Mezcla longitudes de onda de un detector y no sirve para brillo monocromático. No se combinan detectores distintos ni colecciones o versiones de software distintas.
- **Repetibilidad en WISE 0855 (noviembre de 2025).** Es de 1,95 frente a 2,45 esperado. La comprobación sin modelo sugiere que la ganancia real en fuentes débiles de ese grupo podría ser alrededor de un 20 % menor que la medida con errores propagados (3,49).
- **Pocas fuentes brillantes.** Con pocas fuentes, los controles de flujo y PSF descansan en una o dos fuentes (por ejemplo, WISE a ±7 días del 9-5-2026 en la interfaz: 1 fuente). La evidencia robusta de conservación es la de los casos validados.
- **Coste.** La ruta de banda ancha descarga hasta 12 recortes de IRSA (unos 4 MB cada uno) al pulsar «Buscar y combinar»; tarda alrededor de un minuto.
- **Saturación.** La combinación no recupera píxeles saturados.
- **Objetos móviles.** La combinación que sigue la trayectoria hereda la efeméride y no es una medida de posición ni de movimiento.

## Reproducción

```
python scripts/validate_enhance.py                       # todos los casos
python scripts/validate_enhance.py wise0855_d6_nov2025   # un caso
python -m pytest tests/test_enhance.py tests/test_enhance_app.py
```
