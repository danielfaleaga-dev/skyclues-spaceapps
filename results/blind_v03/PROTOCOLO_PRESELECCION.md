# V03 · protocolo de preselección instrumental (registrado antes de medir)

Actividad `SKYCLUES_SPECTRAL_V02_DIAGNOSIS_AND_BLIND_V03`, partes B y C. Se confirma antes de extraer ningún espectro de los candidatos.

## Candidatos

14 regiones, elegidas por su tipo físico y por tener referencias espectroscópicas independientes potencialmente disponibles. No se elige por lo que muestre su espectro. Se excluyen M101, NGC 7023, NGC 7027, M82 y Elias 29. Las posiciones son las nominales de cada objeto y no se ajustan nunca.

**Declaración de ceguera.** Soy un modelo con conocimiento astronómico general: conozco la identidad de los candidatos y sé qué rasgos suelen tener. La ceguera de V03 es procedimental:

- selección solo con criterios instrumentales, fijados aquí;
- analizador, umbrales y apertura congelados;
- ninguna publicación consultada antes de congelar las mediciones;
- ningún dato de los candidatos observado antes de este protocolo.

## Medida de preselección (sin analizador de picos)

Por candidato, solo `extract_spectrum` con parámetros por defecto (apertura de 2 px, anillo de 4–7 px). **No se ejecuta `analyse` ni se cuenta ningún pico.**

Un canal es **utilizable** si cumple las tres condiciones:
- estado «medido»;
- sin OVERFLOW ni OUTLIER en la apertura;
- flujo > 0.

## Criterios de aceptación (todos, fijados antes de medir)

| | Criterio | Motivo |
|---|---|---|
| A | ≥ 60 canales utilizables de los 100 con datos en DR1 | Cobertura general |
| B | Tramo continuo más largo de canales consecutivos utilizables ≥ 15 | Continuo local y entorno del analizador |
| C | ≥ 4 detectores con ≥ 8 canales utilizables cada uno | Cobertura repartida en 0,75–5 µm |
| D | Mediana, sobre los canales utilizables, de (dispersión del anillo) / (brillo superficial de la apertura) ≤ 0,2 | Fondo razonable frente a la señal |

También se registran el número de canales con OVERFLOW/OUTLIER, los canales no medidos y su causa, los saltos de continuidad (número de tramos) y los flujos negativos. No se usa ningún criterio basado en la forma del espectro.

## Selección final (regla fijada)

1. Se ordenan los candidatos aceptados por el número de canales utilizables.
2. Se toma el mejor de cada grupo físico (el grupo del que depende cada candidato está en la tabla de candidatos, fijado ya), hasta 4.
3. Se completa hasta 5 con los mejores aceptados restantes.
4. Si hay menos de 5 aceptados, se ejecutan solo esos. **No se fuerzan pruebas no evaluables.** Si hay menos de 2, se informa y no se ejecuta la fase ciega.

Los grupos son: G1, formación estelar/PDR; G2, nebulosa (reflexión, planetaria o remanente); G3, estrella evolucionada o joven con disco; G4, galaxia.

## Después

- Selección y resultados de la preselección, en `PRESELECCION.md`, se confirman en Git antes de analizar características.
- La fase ciega usa `scripts/blind_v03.py` con el mismo método y huellas que V02.
