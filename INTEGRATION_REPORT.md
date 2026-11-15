# SkyClues — Integración científica: informe final

Fecha: 15-11-2026. Responsable: Claude Code A. Integración **local**: sin push, despliegue ni publicación.

## Dictamen: `PASS_WITH_LIMITATIONS`

La versión integrada funciona, conserva los algoritmos de sus tres fuentes y supera la regresión global salvo una prueba que depende de un servicio externo caído (ESA Gaia). Las limitaciones están en el apartado 7; ninguna procede de la integración.

## 1. Identificación

| | |
|---|---|
| Carpeta | `C:\Users\danie\Documents\SkyClues-integrated` (clon independiente) |
| Rama | `integration/science-v1` |
| Commit de fusión | `ac85e6b` |
| Commit de verificación e informe | el que contiene este archivo (`git log -1`) |
| Antepasado común | `d01917e` (detector no sideral) |

Componentes integrados:

| Componente | Rama de origen | Commit |
|---|---|---|
| Spectrum Explorer (análisis, A/B, calidad, validaciones ciegas) | `feature/spectrum-compare` | `f321c7c` |
| Intérprete físico V1 | `feature/spectral-physical-interpreter-v1` | `0da1702` |
| Mejora infrarroja S/N | `handoff/snr-finish-A` | `02347c6` |
| Detector no sideral | `redesign/unified-region` | `d01917e` (ya en las dos líneas) |

## 2. Inspección inicial

- **Genealogía real:** `d01917e` es antepasado de las dos líneas. La de Espectro (`f321c7c` → `0da1702`) y la de S/N (`561e195` → `9954956` → `02347c6`) divergen desde ahí. No estaban integradas entre sí.
- **Carpeta de Claude B** (`SkyClues`, rama `redesign/unified-region`): sigue con su trabajo sin confirmar. Su árbol de trabajo coincide con lo preservado en `561e195`; la única diferencia son los archivos de inventario del relevo, que solo existen en la copia. No se modificó: solo se leyó con `git --no-optional-locks`.
- **Originales:** `SkyClues-spectra`, `SkyClues-snr-A` y `SkyClues-interpreter` quedan intactos y sin cambios pendientes. La integración se hizo en un clon nuevo, con los tres como remotos de solo lectura (push desactivado).

## 3. Integración

- Fusión de `02347c6` en `0da1702` (`git merge --no-ff`).
- **Código, pruebas, scripts y resultados: sin conflictos.** 176 archivos comprobados blob a blob contra su rama de origen, 0 diferencias.
- `motion.py`, `non_sidereal.py`, `sequence.py` y `moving_sources.py` son idénticos a `d01917e` en las dos ramas y en el resultado.
- **Conflictos:** solo en `DESIGN_SYSTEM.md` y `PROJECT_STATE.md`. Se conservan las secciones de las dos ramas.
- **Incompatibilidades buscadas y no encontradas:**
  - claves de estado de Streamlit: S/N usa `enhance*` y `time_*`; Espectro usa `sx_*`; sin colisiones;
  - `theme.py`: los cambios de Espectro son aditivos y el código S/N usa funciones que siguen existiendo;
  - importaciones cruzadas: ninguna entre Tiempo/S/N y Espectro.
- La navegación sigue siendo Región / Tiempo / Espectro, con los niveles Sencillo y Científico. El interruptor «Mejora infrarroja» es el de la rama S/N, sin reimplementar.
- **Cambios de código en la integración: ninguno** en módulos de la aplicación. Se añaden un verificador (`scripts/integration_verify.py`), una batería de pruebas (`tests/test_integration_science.py`) y documentación.

## 4. Coherencia científica

`scripts/integration_verify.py` lo comprueba con datos reales de la caché local. Resultado: **15 de 15** (`results/integration_v1/verificacion_cientifica.json`).

| Punto | Comprobación | Resultado |
|---|---|---|
| S/N no altera el movimiento | 3I/ATLAS (D1, 9-8-2025, 7 exposiciones): movimiento medido, combinación S/N siguiendo al objeto y con apilado fijo, y movimiento medido de nuevo | Idéntico antes y después: 165,775″ ± 2,694″. Coincide con el resultado guardado. |
| | SHA-256 de píxeles, varianza, banderas, zodiacal y λ de las exposiciones antes y después de combinarlas | Idénticos |
| | M101 (campo estacionario, 4 exposiciones): secuencia, métricas y resultado «sin movimiento» | Idénticos; combinación aceptada, ganancia ×1,88 |
| | En la rejilla nativa, la imagen de referencia de la combinación | Son sus píxeles originales |
| Independencia | El código de movimiento y secuencias no importa S/N; Espectro y Tiempo no se importan entre sí | Correcto |
| Máscaras y exclusiones | NGC 5461 y NGC 7027: 102 canales; canales 51 y 52 «sin datos en DR1»; canales con apertura sin datos sin valor asignado | Correcto. NGC 7027: 37 con valor, 63 con apertura sin datos y 2 vacíos en DR1 |
| Interpretación | Veredictos de compatibilidad; sin claves ni textos de probabilidad o identificación; «no identifica una sustancia» siempre presente | Correcto |
| Cobertura | Una referencia sobre canales sin dato | «Ni presencia ni ausencia» |

Los 102 canales del cubo y la ausencia de datos en canales concretos se mantienen distintos: el producto siempre tiene 102 filas, y cada fila sin valor conserva su causa (canal vacío en DR1 frente a apertura sin datos).

## 5. Regresión global

Versión integrada completa, incluidas las pruebas con red (`results/integration_v1/regresion_completa.txt`):

- **628 superadas, 1 fallida**, en 808 s.
- **Fallida:** `test_motion_app.py::test_real_eps_ind_b_d3_reproduces_from_cached_originals`. Causa externa: ESA Gaia no acepta conexiones (`ConnectTimeout` a `gea.esac.esa.int`). Una consulta directa al servicio, fuera de la aplicación, falló igual en ese momento. Es el mismo fallo externo registrado en el relevo S/N; `motion.py` no ha cambiado.
- **Pruebas nuevas de integración** (`tests/test_integration_science.py`, ejecutadas aparte tras la regresión): **12 superadas**. Cubren independencia de módulos, que combinar no modifica las exposiciones, textos sin probabilidades y un recorrido Tiempo → Espectro → Tiempo con las opciones de ambos exploradores y la región conservadas.

Son ejecuciones distintas; las cifras no se suman.

## 6. Comprobación en navegador

Servidor local del clon integrado (puerto 8521), con datos y servicios reales. Capturas y textos en `results/integration_v1/capturas/`.

| Área | Qué se comprobó | Resultado |
|---|---|---|
| Búsqueda | «Arp 220» + Intro resuelve la región (233,738433; +23,503225). «atlas» sugiere 3I/ATLAS y otros cuerpos (JPL). | Correcto |
| Atlas | Mapa 2MASS con el círculo del campo de 6′. | Correcto |
| Navegación | Región → Espectro → Tiempo conserva RA, Dec y campo en la URL y en la cabecera. | Correcto |
| Time Explorer | Búsqueda en vivo de Arp 220 (región nueva): 3 épocas en D3. M101: 4 épocas. | Correcto. El primer intento de Arp 220 falló por lentitud de IRSA: ver abajo. |
| Detector de movimiento | M101, «Investigar movimiento»: «Evidencia insuficiente», porque Gaia no responde. | Degradación correcta ante un servicio externo caído |
| Detector no sideral | 3I/ATLAS: 160 exposiciones (MOST) → 166″ ± 3″ en 99 min, 16 estrellas de control. | Correcto; igual al resultado guardado |
| S/N | M101: activar («Imagen mejorada», ×1,88), comparar las dos imágenes, desactivar (vuelve el reproductor). Arp 220, secuencia recién descargada: ×1,66 y 2 fuentes nuevas con 0 picos en la imagen nula. | Correcto |
| S/N y movimiento | Con S/N activada, investigar movimiento y volver: el producto no cambia (×1,88). | Correcto |
| Spectrum Explorer | Arp 220: espectro, picos y valles. | Correcto |
| Clic sobre el gráfico | Un clic físico sobre el punto de 3,3 µm selecciona «3,293 µm (canales 63–64)». | Correcto |
| A/B | Punto B con un clic sobre la imagen: dos espectros, diferencia, y cada uno interpretado por separado. B, fuera de la galaxia, queda con z «desconocido». | Correcto |
| Intérprete V1 | Arp 220: «Coincidencia insuficientemente respaldada», z = 0,018398 con su fuente, y «Qué impide la certeza». | Correcto |
| Niveles | Sencillo y Científico en Tiempo (S/N) y Espectro (intérprete): mismo producto, selección y opciones conservadas. | Correcto |
| Opciones cruzadas | Tiempo con S/N → Espectro → Tiempo: la opción S/N sigue activa y muestra la misma combinación. | Correcto |
| Ventana estrecha | 420 px en Tiempo con S/N y en Espectro: sin desplazamiento horizontal. | Correcto |

**Fallos reproducibles registrados:**

| Fallo | Clasificación | Evidencia |
|---|---|---|
| Gaia DR3 no disponible (movimiento estelar sin registro) | Externo | `gea.esac.esa.int` no conecta desde fuera de la aplicación |
| Primera búsqueda de Arp 220 en Tiempo: «IRSA no está disponible temporalmente» (dos intentos) | Externo y transitorio | Una consulta mínima directa a IRSA SIA tardó 20,8 s; a la vez corría la regresión con pruebas en vivo. Minutos después la misma búsqueda terminó bien. La aplicación no mostró datos parciales y ofreció reintentar. |

No se encontró ningún fallo interno.

**No comprobado en navegador:**

- movimiento estelar medido con Gaia (WISE 0855, ε Ind B), por la caída de Gaia;
- la ruta S/N de «exposiciones próximas» (banda ancha): cubierta por pruebas, no repetida hoy en el navegador;
- la composición RGB;
- la consola del navegador.

## 7. Defectos corregidos y limitaciones restantes

**Defectos corregidos en la integración:** ninguno de código; no hizo falta. Los conflictos fueron solo de documentación.

**Corrección heredada del intérprete V1 (`0da1702`):** las insignias de Espectro usaban clases que el tema no define y se veían sin tono.

**Limitaciones restantes:**

- **Servicios externos:** Gaia (ESA) estaba caída durante la verificación. La medida de movimiento estelar depende de ella y hoy no se pudo reproducir. IRSA SIA2 respondió con lentitud.
- **Espectro:** exploratorio, sin incertidumbres ni corrección de apertura.
- **Intérprete V1:** seis referencias; hielos sin modelo de continuo; z solo para cinco galaxias; respuesta espectral aproximada. Detalle en `SPECTRAL_INTERPRETER_V1_REPORT.md`.
- **S/N:** la ruta de banda ancha no sirve para comparar brillo monocromático; los objetos con movimiento propio no se combinan entre años. Detalle en `INFRARED_SNR_REPORT.md`.
- **Movimiento no sideral:** necesita una pareja del mismo detector con cielo común; cuerpos saturados o muy débiles no se miden. Detalle en `MOVING_OBJECTS_REPORT.md`.
- **Aviso heredado:** `scripts/v03_verify.py` compara la huella de `spectral_cube.py` con la de V02 y marcará esa línea como distinta. Es esperado: `f321c7c` añadió contadores de calidad sin cambiar la fotometría.
- **Buscador:** al resolver «Arp 220», el campo muestra el nombre canónico de SIMBAD («IC 1127»). Comportamiento previo, no de la integración.

Fuera de alcance, sin empezar: rediseño del modo Sencillo, ampliación de la biblioteca del intérprete y deslizador automático de los 102 canales.

## 8. Reproducción

```
python -m pytest -q
python -m pytest -q tests/test_integration_science.py
python scripts/integration_verify.py
streamlit run app.py
```

El verificador usa la caché local (`data/cache`, no versionada). Sin caché necesita IRSA.
