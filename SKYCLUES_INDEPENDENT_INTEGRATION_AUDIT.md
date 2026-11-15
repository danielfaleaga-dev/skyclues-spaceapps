# SkyClues — Auditoría independiente de la integración científica

Fecha: 15-11-2026 · Auditor: Claude B · Alcance: verificación, sin desarrollo ni modificación del producto.

## Dictamen: `INDEPENDENT_PASS_WITH_LIMITATIONS`

No he encontrado ningún defecto material interno. Las limitaciones son externas (Gaia sin servicio; IRSA con picos de lentitud/errores 5xx) o ya documentadas por Claude A. **No existe impedimento técnico ni científico para iniciar la mejora de experiencia del modo Sencillo.**

## 1. Identidad Git verificada

| | |
|---|---|
| Producto | `C:\Users\danie\Documents\SkyClues-integrated` (no modificado) |
| Copia de auditoría | `C:\Users\danie\Documents\SkyClues-audit-B` (clon `--no-hardlinks`; caché `data/cache` copiada para no escribir en el original) |
| Rama / HEAD | `integration/science-v1` · `55e8898` |
| Fusión | `ac85e6b` (padres `0da1702` y `02347c6`) |
| Ancestros comprobados con `merge-base --is-ancestor` | `f321c7c`, `0da1702`, `02347c6`, `d01917e`, `561e195`, `9954956`: todos presentes |

## 2. Integridad de los componentes (comparación blob a blob)

| Componente | Resultado |
|---|---|
| Detector no sideral: `motion.py`, `non_sidereal.py`, `sequence.py`, `moving_sources.py` | Idénticos a `d01917e` |
| Mejora S/N: `enhance.py`, `enhance_page.py`, `enhance_view.py`, `time_page.py` | Idénticos a `02347c6` |
| Espectro + intérprete V1 | Todo `skyclues/` y `app.py` igual a `0da1702`, salvo los cuatro archivos de la rama S/N. `git diff --stat 0da1702 HEAD` solo muestra esos cuatro (1726 inserciones, 22 supresiones, todas en `time_page.py`) |
| Algoritmos eliminados o alterados | Ninguno. Las diferencias frente a `f321c7c` (`spectral_view`, `spectrum_analysis`) son las del propio `0da1702` |

Cambio de `time_page.py`: añade la opción `enhance` (por defecto apagada), el interruptor «Mejora infrarroja» y extrae el reproductor a `_sequence_player` sin cambiar su contenido. Con el interruptor apagado el flujo es el anterior.

Independencia por importaciones (re-ejecutada): movimiento y secuencias no importan S/N; Espectro no importa Tiempo ni S/N; S/N no importa Espectro. `enhance.combine` trabaja sobre matrices copiadas (`placed`), no sobre `image.image`.

## 3. Comprobaciones funcionales pendientes

Servidor propio en el puerto 8522 sobre la copia de auditoría, navegador integrado, datos reales.

### A. Composición RGB (Espectro, M101, 210,8024 / +54,3488, campo 6′)
- Navegador: modo «Composición multibanda (RGB)» funciona en Científico. Selección por defecto R = canal 88 (4,500 µm), G = canal 47 (2,189 µm), B = canal 21 (1,195 µm); la tabla de asignación, los tres paneles y la procedencia coinciden con esa selección. 610 de 610 píxeles con datos en los tres canales. Avisos presentes: «Convención de visualización, no color real», «no mejora la relación señal/ruido: no suma ni promedia canales».
- Script `scripts/independent_audit_rgb.py` (resultados en `results/independent_audit/rgb_check.json`), **10 de 10**:
  - cada rol usa el plano `canal − 1` y la λ de la tabla del FITS;
  - los píxeles de la composición son idénticos a los de una lectura separada del mismo plano (sin remuestreo);
  - intercambiar R y B intercambia exactamente los canales mostrados;
  - el canal 51 (sin datos en DR1) se rechaza antes de leer;
  - sin dato en algún canal → NaN en los tres (nunca color parcial);
  - la procedencia no declara promedio ni suma.
- Limitación: la «lectura separada» usa el mismo lector de teselas del proyecto, no un lector externo.

### B. Combinación S/N de banda ancha (Tiempo, M101, D2)
- «Qué combinar» → «Exposiciones próximas al 2026-06-22 · banda ancha D2»: estado «Disponible» con explicación y botón explícito; al pulsarlo, carga con indicador, y resultado **7 exposiciones, 1,42–1,52 µm, intervalo 4,8 d, ganancia S/N ×2,76 (√N = 2,65)**.
- Presentación: insignias «Imagen mejorada · Banda ancha»; en Científico la nota «sirve para detectar y situar fuentes, no para medir brillo monocromático ni compararlo entre fechas» y un aviso aparte; en Sencillo, «mezcla colores infrarrojos vecinos… no para comparar su brillo entre fechas». El panel indica «banda ancha» en lugar de una λ única, y la etiqueta de la imagen de comparación muestra la fecha de su exposición. No se presenta como observación monocromática.
- Compatibilidad: solo exposiciones del mismo detector (D2) a ≤ 7 días de la fecha elegida, como máximo 12; cada fecha se combina por separado.
- Modo «mismo canal» (4 fechas): ×1,88, idéntico al valor de Claude A.
- La nota «Esta imagen no interviene en la medida de movimiento» está en ambos niveles.

### C. Consola del navegador
- Sin errores de JavaScript en todo el recorrido. Solo avisos informativos: carga de fuentes de Google («slow network») y dos avisos de Vega-Lite («Conflicting scale property» en el gráfico de la imagen de Espectro, capas con dominios distintos): son de la biblioteca de gráficos, la escala resultante es la unión de ambas y no afectan a datos ni estados. No los trato como defectos funcionales.

## 4. Incidencia Gaia — clasificación: **externa**

- Reproducción: la prueba `test_real_eps_ind_b_d3_reproduces_from_cached_originals` falla en `references.fetch_gaia` con `ReferenceError: Gaia DR3 no disponible: ConnectTimeout`. Antes de ese punto, las 12 exposiciones originales se releen de la caché y su SHA-256 coincide con el guardado.
- Disponibilidad: `gea.esac.esa.int` resuelve por DNS (193.147.152.106) pero la conexión TCP/HTTPS agota el tiempo con `curl` (15 s) tanto en `/tap-server/tap/availability` como en `/`; en el mismo momento IRSA y SIMBAD responden. Un solo reintento, sin bucles.
- Manejo interno (revisado y ejercido): `fetch_gaia` usa una sola petición acotada, con tiempos 8 s / 25 s, convierte cualquier `RequestException` en un mensaje comprensible y no devuelve datos parciales.
- Sin fabricar mediciones (`scripts/independent_audit_gaia.py`, `results/independent_audit/gaia_offline.json`): con los originales reales de ε Ind B D3 y de WISE 0855 D6 y `gaia=None`, `motion.investigate` devuelve `INSUFFICIENT_EVIDENCE`, sin desplazamiento, con la razón «Gaia DR3 no disponible: sin estrellas estacionarias no se pueden registrar las imágenes ni controlar falsos positivos», en lugar del `MOTION_MEASURED` guardado.
- No verificado: el movimiento estelar medido con Gaia en navegador, ni la reproducción numérica de ε Ind B con una consulta nueva. Los resultados guardados siguen en `results/` con su procedencia (consulta, fecha y SHA-256 de Gaia).
- Los archivos `data/cache/gaia-*.json` son de otro campo (radio 0,05°) y no sirven para una reproducción exacta; no los usé.
- Registro de Claude A: 629 pruebas, 1 fallo (esa), 0 errores, 0 omitidas, coherente con lo que reproduzco.
- Estado de IRSA durante la auditoría: la búsqueda en vivo SIA2 de M101 en «Tiempo» falló con «IRSA no está disponible temporalmente» (502 en consulta directa) y la aplicación mostró el error, ningún dato parcial y «Reintentar»; minutos después la ruta de banda ancha, que también consulta SIA2, se completó. Es el comportamiento transitorio ya descrito por A.

## 5. Pruebas ejecutadas

No repetí las 628 pruebas. Ejecuté:

| Ejecución | Resultado |
|---|---|
| `scripts/integration_verify.py` en la copia de auditoría | **15 de 15** (reproduce a A: 3I/ATLAS D1 sin cambios antes/después de combinar; M101 sin movimiento; 102 canales; intérprete sin probabilidades; referencias sin cobertura = «ni presencia ni ausencia») |
| `tests/test_integration_science.py`, `tests/test_enhance.py`, `tests/test_enhance_app.py` | **45 superadas** en 70 s (`results/independent_audit/pruebas_especificas.xml`) |
| `test_real_eps_ind_b_d3…` | 1 fallo, externo (§4) |
| `scripts/independent_audit_rgb.py` | 10 de 10 |
| `scripts/independent_audit_gaia.py` | Confirma `INSUFFICIENT_EVIDENCE` sin Gaia |
| Navegador | RGB, S/N «mismo canal» y banda ancha, Sencillo/Científico, consola |

## 6. Defectos materiales

Ninguno. Observaciones menores, no materiales:
- La URL conserva `nivel=cientifico` tras cambiar a Sencillo en la interfaz (el nivel funciona; solo el enlace no se reescribe en ese momento). No lo he investigado más.
- En la ruta de banda ancha, la imagen «Una exposición» lleva la fecha de la mejor exposición del conjunto (2026-06-24), distinta de la fecha pedida (2026-06-22). Está etiquetada, pero un usuario Sencillo podría extrañarse.

## 7. Limitaciones externas y comprobaciones no disponibles

- Gaia (ESA) sin servicio: no se pudo medir movimiento estelar ni en script ni en navegador.
- IRSA SIA2 intermitente durante la sesión.
- No comprobados por mí: el detector no sideral con 3I/ATLAS en navegador (solo la reproducción numérica 15/15 vía el verificador), A/B de Espectro y la ventana estrecha: acepto la evidencia de A porque el código es idéntico al de los commits originales y las pruebas de aplicación pasan.
- Las limitaciones científicas ya documentadas (Espectro exploratorio, intérprete V1 de seis referencias, banda ancha no monocromática, objetos con movimiento propio no combinables entre años) no se alteran.

## 8. Siguiente fase

No hay impedimento técnico ni científico para iniciar la mejora de experiencia del modo Sencillo. Sugerencias para esa fase, sin ampliarla ahora: las dos observaciones menores del apartado 6, y repetir la comprobación del movimiento estelar con Gaia cuando el servicio responda.

## 9. Reproducción

```
cd C:\Users\danie\Documents\SkyClues-audit-B
python scripts/integration_verify.py
python -m pytest -q tests/test_integration_science.py tests/test_enhance.py tests/test_enhance_app.py
python scripts/independent_audit_rgb.py
python scripts/independent_audit_gaia.py
```
