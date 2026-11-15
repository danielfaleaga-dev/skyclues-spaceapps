# V03 · preselección instrumental (resultados congelados antes de la fase ciega)

Protocolo: PROTOCOLO_PRESELECCION.md (commit 18a7e79). Datos: preseleccion.json. Medida: extract_spectrum con apertura de 2 px y anillo de 4–7 px; **no se ejecutó el analizador de picos**. Criterios: A ≥ 60 canales utilizables; B tramo continuo ≥ 15; C ≥ 4 detectores con ≥ 8 canales; D fondo/señal mediana ≤ 0,2.

| Id | Objeto | Grupo | Medidos | Utilizables | Con OVERFLOW/OUTLIER | Tramo más largo | Detectores que cumplen | Fondo/señal | Decisión |
|---|---|---|---|---|---|---|---|---|---|
| C01 | Orion Bar | G1 | 33 | 3 | 30 | 2 | 0 | 4.46 | rechazado: A: 3 canales utilizables < 60; B: tramo continuo más largo 2 < 15; C: 0 detectores con ≥ 8 canales < 4; D: fondo/señal mediana 4.46 > 0.2 |
| C02 | NGC 2023 | G2 | 72 | 66 | 6 | 28 | 4 | 0.372 | rechazado: D: fondo/señal mediana 0.372 > 0.2 |
| C03 | NGC 1333 | G1 | 100 | 49 | 0 | 40 | 3 | 0.185 | rechazado: A: 49 canales utilizables < 60; C: 3 detectores con ≥ 8 canales < 4 |
| C04 | IC 63 | G1 | 100 | 100 | 0 | 50 | 6 | 0.655 | rechazado: D: fondo/señal mediana 0.655 > 0.2 |
| C05 | Arp 220 | G4 | 100 | 97 | 3 | 50 | 6 | 0.0108 | **ACEPTADO** |
| C06 | NGC 1068 | G4 | 44 | 12 | 32 | 2 | 0 | 0.0235 | rechazado: A: 12 canales utilizables < 60; B: tramo continuo más largo 2 < 15; C: 0 detectores con ≥ 8 canales < 4 |
| C07 | Red Rectangle | G3 | 1 | 1 | 0 | 1 | 0 | 0.0252 | rechazado: A: 1 canales utilizables < 60; B: tramo continuo más largo 1 < 15; C: 0 detectores con ≥ 8 canales < 4 |
| C08 | CRL 2688 | G3 | 65 | 17 | 48 | 6 | 1 | 0.0105 | rechazado: A: 17 canales utilizables < 60; B: tramo continuo más largo 6 < 15; C: 1 detectores con ≥ 8 canales < 4 |
| C09 | NGC 6543 | G2 | 34 | 29 | 5 | 10 | 2 | 0.00141 | rechazado: A: 29 canales utilizables < 60; B: tramo continuo más largo 10 < 15; C: 2 detectores con ≥ 8 canales < 4 |
| C10 | Cas A | G2 | 100 | 70 | 0 | 50 | 4 | 0.306 | rechazado: D: fondo/señal mediana 0.306 > 0.2 |
| C11 | Mrk 231 | G4 | 99 | 37 | 62 | 15 | 3 | 0.00311 | rechazado: A: 37 canales utilizables < 60; C: 3 detectores con ≥ 8 canales < 4 |
| C12 | TW Hya | G3 | 99 | 77 | 22 | 26 | 5 | 0.00401 | **ACEPTADO** |
| C13 | NGC 7293 (Helix) | G2 | 100 | 7 | 92 | 1 | 0 | 0.323 | rechazado: A: 7 canales utilizables < 60; B: tramo continuo más largo 1 < 15; C: 0 detectores con ≥ 8 canales < 4; D: fondo/señal mediana 0.323 > 0.2 |
| C14 | M51 nucleus | G4 | 100 | 98 | 2 | 50 | 6 | 0.0476 | **ACEPTADO** |

## Selección final (regla del protocolo)

Aceptados: C05 (Arp 220), C12 (TW Hya), C14 (M51 nucleus). Con la regla (mejor de cada grupo y, después, hasta 5), se seleccionan **todos los aceptados**:

- **C05** · grupo G4 · posición nominal RA 233.737917°, Dec +23.503056° · 97 canales utilizables, tramo de 50, 6 detectores.
- **C12** · grupo G3 · posición nominal RA 165.466250°, Dec -34.704722° · 77 canales utilizables, tramo de 26, 5 detectores.
- **C14** · grupo G4 · posición nominal RA 202.469583°, Dec +47.195278° · 98 canales utilizables, tramo de 50, 6 detectores.

Solo se ejecutan tres pruebas: no se fuerzan pruebas no evaluables y el resto de candidatos no alcanzó los criterios instrumentales. Dos de los tres están en el grupo G4 (galaxias) porque no hubo aceptados en G1 ni G2.

## Observaciones sobre los rechazados (solo instrumentales)

- **Compactos y brillantes (C01, C06, C07, C08, C09, C13):** pocos canales utilizables, por saturación o píxeles perdidos, como en V02. C07 y C01 mantienen apenas 1–3 canales.
- **C04 (IC 63):** 100 canales utilizables, pero el anillo de fondo varía mucho frente a la señal (0,66): la estructura del anillo no permite un fondo razonable.
- **C02 y C10:** cumplen A–C, pero fallan D (0,37 y 0,31): el anillo es muy estructurado.
- **C03 y C11:** menos de 60 canales utilizables y solo 3 detectores con datos.

Las posiciones nominales son aproximadas y no se ajustan. Ceguera procedimental: ver el protocolo.
