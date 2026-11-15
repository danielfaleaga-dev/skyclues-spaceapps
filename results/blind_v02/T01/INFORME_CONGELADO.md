# T01 · informe congelado (fase ciega)

Sin identificar el objeto y sin consultas externas. Datos en `resultados.json`; figuras en `espectro.png` (espectro completo) y `campo.png` (imagen y geometría).

## Datos de partida

- **Posición** (ICRS, dada en el encargo): `21h07m01.572s +42°14′10.47″` = RA 316,756550°, Dec +42,236242°. FOV de 4′. No se ha desplazado.
- **Producto SPHEREx:** cubo DR1 HiPS de orden 5, tesela 3498 (`hips_20261026`, DOI 10.26131/IRSA679).
- **Apertura:** 2 px (25,8″; 12,52 px efectivos).
- **Fondo:** anillo de 4–7 px con 103 px; media con recorte 3σ. La dispersión mediana del anillo es 0,081 MJy/sr.
- **Cobertura del campo:**
  - píxeles válidos ≥ 94,5 % en todos los canales con datos;
  - NHITS mediano de 8 a 17.

## Canales y calidad

**Canales con valor: 37 de 102** (1–10, 12–15, 17–23, 25–30, 32–39, 42 y 86).

**Canales sin valor: 65.**
- 63 por «apertura con píxeles sin datos (NHITS = 0)». Afecta a casi todo lo que hay por encima de unos 1,9 µm y a canales sueltos (11, 16, 24, 31, 40, 41).
- 2 son los canales 51 y 52, sin datos en DR1.

En el centro, la imagen del campo muestra píxeles sin datos en muchos canales: es la firma de una fuente intensa. La apertura tiene los indicadores SOURCE en 100 canales y BLOOM, TRANSIENT y SUR_ERROR en unos 60.

**Saturación (OVERFLOW): 21 canales**, entre ellos 1–8, 10, 12, 15, 17–19, 21, 22, 26, 38 y 86.

Los canales con OVERFLOW dan flujos de 410–930 mJy; los vecinos sin él, 160–470 mJy. El espectro es dentado entre canales contiguos.

**Rango del flujo:** 160–8256 mJy. El canal 86 (4,4 µm) está aislado y saturado.

## Resultado del analizador (parámetros congelados)

- **Características etiquetadas: ninguna.**
- **Anomalías por debajo del criterio** (≥ 2,5 veces la dispersión): ninguna.
- **No evaluables:** 95 canales. Hay dos causas:
  - canales sin valor en el intervalo examinado (65);
  - entorno insuficiente: faltan 3 canales válidos por lado (17 en cada dirección).

## Contaminación y limitaciones

- **Saturación.** La fuente central está saturada o ha perdido píxeles en la mayor parte del intervalo de 1,9–5 µm. Lo que queda por debajo de 1,9 µm alterna canales con y sin OVERFLOW, así que el continuo local no es fiable.
- **Geometría.** La apertura de 25,8″ es mayor que la región central perdida.

## Conclusión registrada

**No evaluable** por la calidad de los datos en la posición fijada. El analizador no etiqueta nada y no hay ningún intervalo evaluable por encima de unos 1,9 µm.
