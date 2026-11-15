# SkyClues: transferencia final de la mejora infrarroja S/N (Claude A → Claude B)

Actividad `SKYCLUES_SNR_HANDOFF_AND_COMPLETION_01`, 15-11-2026. Trabajo local; sin push, despliegue ni publicación.

## 1. Ubicación del nuevo repositorio

`C:\Users\danie\Documents\SkyClues-snr-A`

Es un clon independiente (`git clone --no-hardlinks`) del repositorio de `C:\Users\danie\Documents\SkyClues`:
- su remoto `origin` apunta a esa carpeta para lectura;
- el envío está desactivado: `pushurl = DISABLED-no-push-from-handoff`.

La caché de FITS de B (`data/cache`, sin el cubo espectral; 1771 archivos, 2,3 GB) se copió a `data/cache` del clon. Esa ruta está ignorada por git; el origen no se tocó.

## 2. Rama y commit final

- Rama: `handoff/snr-finish-A`
- Commits sobre la base:
  - `561e195`: trabajo de B sin confirmar, preservado **sin cambios**.
  - Commit de cierre del relevo con las correcciones y la documentación. Su hash lo da `git log -1 handoff/snr-finish-A`; el mensaje empieza por «Mejora infrarroja S/N: cierre del relevo».
- No se modificó `feature/spectrum-compare` ni `redesign/unified-region`.

## 3. Referencia base

`d01917e` (`redesign/unified-region`, «Detector no sideral: movimiento medido de objetos conocidos»).

Es también la base común con `feature/spectrum-compare` (`f321c7c`).

## 4. Archivos

**Preservados de B tal cual** (`561e195`, 50 archivos; inventario con SHA-256 y blob en `results/handoff_snr/INVENTARIO_B.json`):

| Tipo | Archivos |
|---|---|
| Código nuevo | `skyclues/enhance.py`, `skyclues/enhance_page.py`, `skyclues/enhance_view.py` |
| Integración | `skyclues/time_page.py` (interruptor «Mejora infrarroja»; el reproductor pasa a `_sequence_player` sin cambios) |
| Pruebas y validación | `tests/test_enhance.py`, `tests/test_enhance_app.py`, `scripts/validate_enhance.py` |
| Evidencias | `results/enhance/`: 40 archivos con JSON por caso, figuras, resumen y capturas |
| Documentación | `DESIGN_SYSTEM.md`, `PROJECT_CONTEXT.md`, `README.md` |

La preservación se verificó blob a blob contra la carpeta de B: 50 de 50 idénticos. `results/handoff_snr/cambios_B_sin_confirmar.patch` es el parche binario equivalente. `results/handoff_snr/evidencia_B/` guarda el registro de la validación final de B y su script de navegador.

**Modificados o añadidos en el cierre:**

| Archivo | Cambio |
|---|---|
| `skyclues/enhance_page.py` | «Qué combinar» se reinicia al cambiar de región o de secuencia. Los círculos no se llaman «fuentes» si la imagen nula tiene tantos picos espurios como fuentes nuevas. Frase sobre qué significa la ganancia. Concordancia «1 fuente brillante» |
| `tests/test_enhance_app.py` | 2 pruebas nuevas |
| `INFRARED_SNR_REPORT.md` | Nuevo; README y CONTEXT ya lo citaban, pero no existía |
| `DESIGN_SYSTEM.md`, `PROJECT_STATE.md` | Decisiones y estado |
| `results/handoff_snr/` | Inventario, parche y registros de regresión |

**Sin cambios respecto a `d01917e`:** `enhance.py` y el apilamiento (el método no se tocó), `motion.py`, `non_sidereal.py`, `moving_*`, `sequence.py`, Spectrum Explorer, comparación A/B, analizador de características y diagnóstico de calidad.

## 5. Estado de las pruebas

Todas se ejecutaron en el clon con el intérprete `.venv` de `SkyClues`.

| Conjunto | Resultado |
|---|---|
| `tests/test_enhance.py` + `tests/test_enhance_app.py` | **33 superadas** (24 sintéticas, 9 de aplicación; 2 nuevas) |
| Regresión fuera de línea `-m "not network"` (sin S/N) | **439 superadas**, 61 de red no seleccionadas |
| `test_app`, `test_motion_app`, `test_moving_app`, `test_reference_app` | **22 superadas, 1 fallida** |
| Árbol fusionado con `f321c7c` (worktree temporal): `test_enhance`, `test_spectral_quality`, `test_spectral_offline`, `test_spectral_features`, `test_offline` | **121 superadas**; importan `time_page`, `spectrum_page`, `enhance_page` y `spectral_quality` |

**La prueba fallida** es `test_motion_app.py::test_real_eps_ind_b_d3_reproduces_from_cached_originals`. ESA Gaia (`gea.esac.esa.int`) no respondió: ConnectTimeout en la prueba, en el reintento y en una consulta directa. Es el mismo fallo externo que B registró en `d01917e`, y `motion.py` no cambió.

Los registros están en `results/handoff_snr/regresion_offline.txt` y `results/handoff_snr/regresion_apps_tiempo.txt`.

**Navegador** (servidor del clon en el puerto 8521, navegador integrado):
- M101 en Científico.
- M101, «Exposiciones próximas al 2026-05-22»: Disponible → Procesando → Imagen mejorada. Es el paso donde falló el script de B; la causa era su selector, no la aplicación.
- WISE 0855 en secuencia: «No disponible», el objetivo se mueve.
- WISE 0855 a ±7 días del 9-5-2026.
- Sencillo y Científico con el mismo producto.
- 420 px de ancho sin desplazamiento horizontal.

No se guardaron capturas nuevas; las de B siguen en `results/enhance/browser_*.png`.

## 6. Resultados científicos comprobados

| Caso | Referencia comunicada | Comprobado |
|---|---|---|
| M101 D2, mismo canal, 4 exposiciones | ×1,88 | **×1,88**, recalculado en el relevo con resultado idéntico en todos los campos |
| M101 D2, banda ancha, 12 exposiciones | ×3,44 | El ×3,44 era un **grupo exploratorio distinto** (12 exposiciones DR1 en 210 días); el código final lo reproduce **exactamente** (3,44 en 80 fuentes). El producto final solo combina a ±7 días: diciembre de 2025, 12 exposiciones en 2,8 días → **×2,91** (frente a la mejor 3,13; √N 3,46; repetibilidad sin modelo 2,44 frente a 2,45 ideal) |
| WISE 0855 D6, 12 exposiciones | ×3,49 | **×3,49**, recalculado con resultado idéntico. Objetivo: S/N ≤ 5,4 por exposición → 12,6. 29 de 29 fuentes nuevas con contrapartida en AllWISE (16 % por azar) |
| Flujo / PSF / centroides | — | En los casos aceptados: flujo 0,974–1,018, PSF ×1,04–1,12 (límite 1,25), centroide 0,07–0,32″ (píxel 6,15″) |
| Controles negativos | — | Imagen nula, imagen invertida y trayectorias desplazadas. WISE de mayo de 2025 (2 exposiciones) se **rechaza** por estructura negativa |

**Respuesta a la comprobación adicional del usuario:**
1. **Flujo y resolución.** Cubiertos por los controles de cada combinación. En el caso de 5 exposiciones que se vio, flujo ×1,003 y PSF ×1,08, pero con una sola fuente brillante. La evidencia robusta son los casos validados de la tabla.
2. **Ganancia real.** Sale de mediciones comparables: la misma apertura y las mismas fuentes en la combinación y en cada exposición, con errores propagados y escalados por la imagen nula. No es suavizado: no se interpola ni se filtra. Hay una comprobación sin modelo (repetibilidad). En WISE de noviembre da 1,95 frente a 2,45 esperado: la ganancia real en fuentes débiles de ese grupo podría ser un 20 % menor.
3. **Círculos.** Marcan picos ≥ 5σ en la combinación que ninguna exposición individual detecta. Ahora solo se llaman «fuentes» cuando la imagen nula tiene menos picos espurios. En M101 de banda ancha (3 nuevas, 0 de 3 con 2MASS, 3 en la imagen nula) el texto dice que no se distinguen del ruido. En WISE, 29 de 29 nuevas tienen contrapartida en AllWISE.
4. **Interfaz.** La ganancia S/N se muestra junto a la comparación, con una frase sobre su significado. La S/N individual y la combinada del objetivo de la región aparecen cuando es fiable (objetivo débil, S/N < 30 por exposición).

## 7. Limitaciones y advertencias

- El producto de banda ancha no sirve para brillo monocromático ni para comparar fechas; se rotula así en los dos niveles.
- La combinación no mejora la astrometría de fuentes brillantes. En M101 de banda ancha, frente a 2MASS, da 0,94″ en la combinación y 0,70″ por exposición. No se usa para medir posiciones ni movimiento, y no interviene en «Movimiento».
- La combinación que sigue la trayectoria (3I/ATLAS, Juno, Vesta) solo existe en el script de validación, no se adopta y no cambia ninguna medida del detector no sideral.
- La ruta de banda ancha consulta SIA2 y descarga hasta 12 recortes al pulsar el botón; tarda alrededor de un minuto. Si IRSA falla, la interfaz ofrece reintentar.
- `PROJECT_STATE.md` y `DESIGN_SYSTEM.md` se fusionan sin conflicto con `f321c7c`, pero el orden de las secciones de estado debe revisarse al integrar: las dos ramas añaden una primera sección.
- El clon no contiene el cubo espectral en caché (`data/cache/cube`). No hace falta para S/N.

## 8. Instrucciones mínimas para que B integre con `f321c7c`

Desde la carpeta de integración (por ejemplo, `SkyClues` en `redesign/unified-region`, con el árbol limpio):

```
git fetch C:/Users/danie/Documents/SkyClues-snr-A handoff/snr-finish-A:handoff/snr-finish-A
git merge --no-ff handoff/snr-finish-A                 # avance sobre d01917e, sin conflictos
git merge --no-ff feature/spectrum-compare             # f321c7c; fusión de prueba sin conflictos (árbol dc02048)
python -m pytest tests/test_enhance.py tests/test_enhance_app.py tests/test_spectral_quality.py -q
python -m pytest -m "not network" -q
```

Antes del primer `merge`, la carpeta de B tiene todavía sin confirmar los mismos 50 archivos que contiene `561e195`. Hay dos opciones:
- descartarlos solo después de comprobar que son idénticos (`results/handoff_snr/INVENTARIO_B.json` da el SHA-256 de cada uno);
- o integrar en otra carpeta.

En ningún caso conviene sobrescribirlos sin verificar.

Después de fusionar, conviene:
- reordenar la primera sección de `PROJECT_STATE.md`;
- abrir Tiempo → «Mejora infrarroja» en M101 y WISE 0855 en los dos niveles.

`scripts/v03_verify.py` de la rama espectral fallará en la huella de `spectral_cube.py`. Es esperado y está documentado en esa rama.
