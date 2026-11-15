# SkyClues — Intérprete físico de espectros V1

Actividad `SKYCLUES_SPECTRAL_PHYSICAL_INTERPRETER_V1`.

- **Rama:** `feature/spectral-physical-interpreter-v1`, creada desde `f321c7c` (`feature/spectrum-compare`), en el clon aislado `SkyClues-interpreter`.
- **Sin integrar:** sin fusión con la rama principal ni con la de Claude B; sin push ni despliegue.
- **Versiones:** motor `skyclues-interprete 1.0 (2026-11-15)`; biblioteca `skyclues-referencias 1.0 (2026-11-15)`.

## 1. Qué hace y qué no hace

Para cada pico o valle que ya señaló el analizador de Espectro (`skyclues-features 1.0`), el intérprete pregunta si cae donde caería alguna de seis referencias espectroscópicas documentadas. Para responder tiene en cuenta:

- el tipo del rasgo (emisión o absorción);
- la resolución del canal;
- el desplazamiento al rojo conocido;
- la calidad de los datos.

La respuesta es siempre uno de estos cinco veredictos:

| Veredicto | Significado |
|---|---|
| Referencia compatible | Una sola referencia coincide en posición y tipo, con datos sin reservas. **No es una identificación.** |
| Varias referencias compatibles | Varias coinciden y SPHEREx no las separa. Se conservan todas como hipótesis. |
| Coincidencia insuficientemente respaldada | Alguna coincide, pero la señal o los datos no bastan para sostenerla. |
| Ninguna referencia compatible | Ninguna de la biblioteca coincide. No excluye otras sustancias ni procesos. |
| No evaluable | Los datos de ese intervalo no permiten valorar ninguna referencia. |

**No hace:**

- identificación química;
- probabilidades o puntuaciones (no hay un modelo calibrado);
- estimar z a partir de una coincidencia;
- extraer de nuevo el espectro o detectar picos por su cuenta;
- usar IA generativa, servicios de inferencia ni clasificadores aprendidos.

Las razones del analizador (contraste frente a la dispersión de referencia) son descriptivas: el intérprete nunca las presenta como significación estadística.

## 2. Arquitectura

| Capa | Archivo | Responsabilidad |
|---|---|---|
| Registro | `skyclues/spectral_references.py` | Biblioteca versionada de referencias, fuentes, error del centro de banda por detector y tabla curada de desplazamientos al rojo. Estructuras `Reference`, `Source`, `Galaxy` y `Redshift` inmutables y serializables. |
| Motor | `skyclues/spectral_interpreter.py` | Tres pasos separados: A. Observación (`observe`), B. Compatibilidad (`_window`, `_evaluate`) y C. Interpretación (`interpret`). Lee los resultados del analizador y no los modifica. `survey` informa de la cobertura de cada referencia aunque no haya rasgo. Es puro y determinista, con versión y códigos en `to_dict()`. |
| Presentación | `skyclues/spectrum_interpretation.py` | Sección «¿Qué podría indicar este espectro?» en los dos niveles, más las marcas de referencia en el gráfico. |
| Integración | `skyclues/spectrum_analysis.py` (+7 líneas), `skyclues/spectral_view.py` (+capas punteadas) | Construye el contexto con los mismos pares (serie, análisis) que ya usa la página, pasa las marcas al gráfico y renderiza la sección antes de la calidad de los canales. |

No se han modificado:

- `spectral_features.py` ni los umbrales del analizador;
- `spectral_cube.py` ni el método fotométrico, ni las máscaras;
- `spectral_quality.py`;
- los resultados congelados V01–V03;
- Time Explorer ni S/N.

## 3. Biblioteca de referencias (V1)

Cada referencia guarda estos campos:

- identificador estable;
- transición o portador;
- λ en reposo (y su intervalo, si la literatura lo da);
- naturaleza y forma (banda o línea);
- anchura, solo si está documentada;
- condiciones de observación;
- confusiones posibles;
- textos llano y científico;
- fuentes.

| id | Referencia | λ en reposo | Naturaleza · forma | Anchura documentada | Fuentes |
|---|---|---|---|---|---|
| `h2o_hielo_3p0` | H₂O hielo, estiramiento O–H | 3,0 µm (3,0–3,05) | absorción · banda | FWHM ≈ 390 cm⁻¹ ≈ 0,35 µm | Boogert+ 2015; Hora+ 2026 |
| `pah_3p3` | PAH, estiramiento C–H aromático | 3,29 µm (3,28–3,30) | emisión · banda | no se fija (perfil variable) | van Diedenhoven+ 2004; Tielens 2008; Hora+ 2026 |
| `hi_pfund_delta` | H I Pfund δ (n = 9→5) | 3,296991 µm | emisión · línea | no resuelta | NIST ASD |
| `hi_brackett_alpha` | H I Brackett α (n = 5→4) | 4,052269 µm | emisión · línea | no resuelta | NIST ASD |
| `co2_hielo_4p27` | CO₂ hielo, estiramiento asimétrico | 4,27 µm | absorción · banda | FWHM ≈ 20 cm⁻¹ ≈ 0,036 µm | Boogert+ 2015; Hora+ 2026 |
| `co_hielo_4p67` | CO hielo | 4,67 µm | absorción · banda | FWHM 3–9 cm⁻¹ (≤ 0,020 µm) | Boogert+ 2015; Hora+ 2026; Vacca y Sandell 2011 (confusiones: Pfβ 4,6538 y Hu ε 4,6727 µm) |

**Fuentes verificadas:**

- NIST ASD (v5): longitudes de Ritz en el vacío; una prueba recalcula Pfδ y Brα con la fórmula de Rydberg.
- Boogert, Gerakines y Whittet 2015, ARA&A 53, 541 (doi:10.1146/annurev-astro-082214-122348).
- Hora et al. 2026, arXiv:2603.12390.
- van Diedenhoven et al. 2004, ApJ 611, 928.
- Tielens 2008, ARA&A 46, 289 (doi:10.1146/annurev.astro.46.060407.145211).
- Vacca y Sandell 2011, arXiv:1102.0535: solo el preprint; no se pudo verificar la referencia de revista y no se cita.
- Hui et al. 2026, ApJS 284, 10 (doi:10.3847/1538-4365/ae522c).
- NED y RC3 para los z y las isofotas D25.
- Tabla `SPECTRAL_CHANNELS` del cubo DR1 (doi:10.26131/IRSA679).

PAH 3,3 y Pfδ se conservan **siempre** como hipótesis simultáneas: a R ≈ 35–43, SPHEREx no las separa.

## 4. Método de compatibilidad (aproximación conservadora declarada)

No se dispone de la respuesta espectral completa de cada canal en el producto. Por eso el motor no usa una tolerancia fija en µm, sino esta ventana:

1. **Ventana observada:** la unión de los intervalos WL_MIN–WL_MAX de los canales a media altura del rasgo (o del intervalo examinado, si no está etiquetado), ampliada con el error documentado del centro de banda. Ese error es de 1 nm en D1–D4 y de 10 nm en D5–D6 (Hui et al. 2026).
2. **Posición esperada:** λ_obs = λ_rest (1 + z), solo con un z trazable. Si z es desconocido, se compara en reposo y se informa del intervalo de z para el que la coincidencia se mantiene. Ese intervalo se da **solo** para coincidencias, nunca para casi-coincidencias.
3. **Contigua:** una referencia a menos de un elemento de resolución (λ/R) fuera de la ventana es «No compatible: canal contiguo», nunca compatible.
4. **Naturaleza:** un pico solo es compatible con emisión y un valle solo con absorción. Si no coinciden: «No compatible: tipo opuesto».
5. **Anchura:** una banda documentada de ≥ 3 elementos de resolución (el hielo de H₂O, unos 4 canales) exige un rasgo que el analizador clasifique como «amplio». Las líneas estrechas no tienen que estar resueltas.
6. **Hielos:** como máximo «insuficientemente respaldada». V1 no ajusta un continuo para medir τ (Hora et al. 2026 lo exige), así que un mínimo aislado nunca se presenta como hielo.
7. **Calidad:**
   - Impiden evaluar: rasgo o entorno en varios detectores, datos no evaluables y ausencia de rasgo.
   - Limitan a «insuficiente»: señal «visible» (no «cuantificable»), canales con OVERFLOW/OUTLIER en la apertura, precaución del entorno y BLOOM.

**Desplazamiento al rojo:** tabla curada de cinco galaxias (Arp 220, M51a, M51b, M101 y M82), con z de NED. La apertura solo hereda el z si su centro cae dentro de la elipse D25 (RC3: diámetro, b/a y PA; sin PA, el círculo del semieje menor). Se suma ±300 km/s por movimientos internos, como hipótesis declarada. Fuera de la tabla, z es «desconocido» y así se dice.

**Cobertura:** si el canal previsto no tiene datos, no se concluye ni presencia ni ausencia. Cuando hay datos pero no hay rasgo, el motor no lo toma como prueba de ausencia.

## 5. Interfaz

Una sección «¿Qué podría indicar este espectro?» dentro de Espectro. Los datos y los veredictos son los mismos en los dos niveles; ver `DESIGN_SYSTEM.md`.

- **Sin selección:** una fila por pico o valle, con su veredicto y el botón «Examinar», que fija el mismo intervalo que el inspector.
- **Sencillo:** qué observamos, qué podría representar (siempre en condicional y con las alternativas), por qué y qué impide estar seguros. Ejemplo real de NGC 5461: «Detectamos un exceso de emisión cerca de 3,3 µm. Podría relacionarse con compuestos aromáticos de carbono (PAH), aunque otras emisiones cercanas, como la del hidrógeno ionizado (línea Pfund δ), también pueden contribuir».
- **Científico:**
  - cifras: λ observada, detector y R con su elemento de resolución, z con su fuente e incertidumbre, y clase del dato con su cociente descriptivo;
  - tabla por referencia: λ en reposo y esperada, canal previsto, compatibilidad, z para la que se mantiene y motivo;
  - «Qué impide la certeza» siempre visible;
  - plegables con condiciones, confusiones y bibliografía; con la biblioteca, el método y la tabla de galaxias; y con la cobertura de cada referencia.
- **Gráfico:** interruptor de marcas de referencia, apagado por defecto y persistente entre niveles. Cada marca es una regla punteada fina; se resaltan las referencias que coinciden con la selección, con una única etiqueta combinada (p. ej. «PAH 3,3 · Pfδ»).
- **A y B** se interpretan por separado. Nunca se interpreta su diferencia.

## 6. Resultados en casos reales

Los resultados proceden del motor sobre los espectros congelados de V02/V03 (sin modificarlos) y de M101 desde la caché local del cubo. Todos están cubiertos por pruebas.

| Caso | Rasgo | z (fuente) | Veredicto | Lectura |
|---|---|---|---|---|
| NGC 5461 (región H II de M101) | pico 3,293 µm, ch63, cuantificable | 0,000804 (M101, NED, dentro de D25) | **Varias referencias compatibles** | PAH 3,3 y Pfδ caen en el canal 63; no se separan. Compatible, **no confirmado**. |
| NGC 5461 | pico 4,076 µm, ch76 | ídem | **Referencia compatible** | Brα esperada en 4,0555 µm. |
| NGC 5461 | picos 1,861 µm (ch40) y 4,669 µm (ch93) | ídem | Ninguna referencia compatible | Fuera de la biblioteca V1 (ver §8). El de 4,67 es emisión, opuesta al hielo de CO. |
| NGC 5461 | picos 0,955 µm (ch11) y 1,102 µm (ch17), «visibles» | ídem | No evaluable | El entorno que usa el analizador incluye canales de D2 (canales 19 y 20 para el de 0,955 µm). |
| Núcleo de M101 | sin rasgo en 3,3 µm | 0,000804 | No evaluable | Nada señalado en el canal 63. |
| Arp 220 (C05) | pico ch63, media altura 63–64 | **0,018398** (NED) | Coincidencia insuficientemente respaldada | Con z aplicado, PAH (3,3505 µm) y Pfδ (3,3576 µm) caen en el canal 64, dentro del intervalo. La señal limita el veredicto. Se advierte que la apertura (radio 26″) mezcla toda la luz de esa zona. |
| Núcleo de M51 (C14) | pico ch63 | 0,001745 (M51a) | Coincidencia insuficientemente respaldada | Una apertura en M51b recibe su propio z (0,001518): las aperturas no se confunden. |
| TW Hya (C12) | ch69 y ch75 | desconocido | No evaluable | Escalón D4/D5 y OVERFLOW. Brα cae en el canal 75 pero queda como «insuficiente», sin conclusión. |
| TW Hya (C12) | ch92 | desconocido | Ninguna referencia compatible | — |
| NGC 7027 (T01), M82 (T02) | 3,3 µm | — / 0,000897 | No evaluable | Canales sin datos (BLOOM/NHITS = 0): ni presencia ni ausencia. |
| M82 (T02) | pico 4,669 µm, ch93 | 0,000897 | Ninguna referencia compatible | El hielo de CO es absorción: tipo opuesto. |

## 7. Pruebas

- `tests/test_spectral_interpreter.py`: 26 pruebas.
  - Registro: versiones y fuentes, Rydberg, conversiones de anchura, asociación de z, elipses e isofota.
  - Casos sintéticos sobre la rejilla real de canales: varias, visible, Brα, z conocido, z no estimado, anchura del H₂O, tipo opuesto, CO₂, fuera de la biblioteca, canales NaN, escalón de detector, precaución del entorno, sin rasgos, R estimada y determinismo.
  - Casos reales congelados: Arp 220, M51, TW Hya, NGC 7027, M82 y M101/NGC 5461 desde la caché, con la red bloqueada.
- `tests/test_spectral_interpreter_app.py`: 5 pruebas de integración con AppTest.
  - La sección aparece en los dos niveles.
  - «Examinar» explica el rasgo con el mismo resultado en ambos niveles y conserva la selección.
  - El interruptor de marcas persiste al cambiar de nivel.
  - A y B se interpretan por separado.
  - El gráfico solo añade la regla punteada y una etiqueta.
  - La insignia usa una clase que el tema estiliza.
- Resultados de las ejecuciones, en el apartado 9.

## 8. Limitaciones científicas

- **La biblioteca V1 tiene seis referencias.** «Ninguna referencia compatible» no excluye otras sustancias ni procesos. En NGC 5461, los picos de 1,86 µm y 4,67 µm quedan sin referencia: líneas de H I como Paα (1,8756 µm) o Pfβ (4,6538 µm) no están en V1. Lo dejo como candidatas para ampliar la biblioteca, no como identificación.
- **Respuesta espectral:** se aproxima con los límites WL_MIN–WL_MAX y el error del centro de banda. La respuesta real no es gaussiana y es asimétrica cerca del dicroico (Hui et al. 2026).
- **Hielos:** sin modelo de continuo ni medida de τ, nunca pasan de «insuficientemente respaldada».
- **Desplazamiento al rojo:** solo cinco galaxias curadas. El resto de posiciones se compara en reposo (z «desconocido»). No hay entrada de z por el usuario en la interfaz, aunque `user_redshift` existe en el registro.
- **Datos:** el cubo no tiene incertidumbres. Los cocientes del analizador son descriptivos.
- **Apertura:** mezcla toda la luz dentro de su radio; no es un objeto concreto.
- **Rasgos que tocan dos detectores:** no se interpretan, aunque el rasgo esté dentro de uno solo (caso de 0,955 µm en NGC 5461). Es conservador a propósito.
- **Bandeado del mosaico:** Hora et al. 2026 describen un efecto de bandeado en el centro de la banda PAH. V1 no lo modela.
- **Nomenclatura:** Hora et al. 2026 llaman «Pfγ» a la línea de 3,297 µm. Según NIST es Pfδ (n = 9→5), y así se usa aquí.

## 9. Comprobación en navegador

Servidor local del clon en el puerto 8521. Edge sin interfaz controlado por el protocolo de depuración (CDP), porque el panel del navegador integrado medía unos 38 px de alto y no permitía capturas útiles. Capturas en `results/interpreter_v1/capturas/`.

Datos reales del cubo DR1 a través de la aplicación. Las páginas se cargan desde la URL compartible `?explorer=espectral&ra=…&dec=…&fov=0.1&canal=…`.

| Captura | Caso | Nivel · anchura | Qué muestra |
|---|---|---|---|
| `01_ngc5461_sencillo_resumen` | NGC 5461 | Sencillo · 1280 | Lista de los seis picos con su veredicto y «Examinar». |
| `02_ngc5461_sencillo_33_grafico` | NGC 5461 | Sencillo · 1280 | Marcas de referencia punteadas; la única etiqueta, «PAH 3,3 · Pfδ», va sobre el pico examinado. |
| `03_ngc5461_sencillo_33_interpretacion` | NGC 5461 | Sencillo · 1280 | Qué observamos, qué podría ser, por qué y qué impide estar seguros. |
| `04_ngc5461_cientifico_33` | NGC 5461 | Científico · 1280 | Cifras, tabla PAH/Pfδ (canal 63, compatibles) y «Qué impide la certeza». |
| `05_ngc5461_cientifico_420` / `06_ngc5461_sencillo_420` | NGC 5461 | 420 px | Disposición estrecha. |
| `07_ngc5461_cientifico_resumen` | NGC 5461 | Científico · 1280 | Lista en Científico: λ y canal de cada rasgo. |
| `08_ngc5461_cientifico_bralpha` | NGC 5461 | Científico · 1280 | Brα «Referencia compatible»: λ esperada 4,0555 µm, canales 75 y 76. |
| `09_arp220_cientifico_grafico_z` | Arp 220 | Científico · 1280 | Marcas desplazadas con z = 0,018398. |
| `10_arp220_cientifico_33_z` / `11_arp220_sencillo_33` | Arp 220 | ambos · 1280 | z aplicado (canal previsto 64) e «insuficientemente respaldada» por señal «visible». |
| `12_twhya_cientifico_resumen` / `13_twhya_cientifico_bralpha_no_evaluable` | TW Hya | Científico · 1280 | Brα cae en el canal 75, pero D4/D5 y OVERFLOW impiden concluir. |
| `14_ngc7027_cientifico_cobertura` | NGC 7027 | Científico · 1280 | Sin rasgos. Las seis referencias quedan «sin cobertura válida», con la causa en palabras (NHITS = 0). |
| `15_m82_cientifico_cobertura` / `16_m82_cientifico_47_tipo_opuesto` | M82 | Científico · 1280 | Cobertura, y el pico de 4,67 µm «No compatible: tipo opuesto» frente al hielo de CO. |

Los textos completos de cada página están junto a las capturas (`*.txt`).

**Comprobado:**

- **Sin desplazamiento horizontal de la página a 420 px** en los dos niveles: `scrollWidth = clientWidth = 420`; ver `desbordamiento_*.json`. Las tablas se desplazan dentro de su marco.
- **Selección conservada entre niveles:** el pico de 3,3 µm sigue seleccionado de Sencillo a Científico y de vuelta.
- **Interruptor de marcas conservado entre niveles.**
- **Estado vacío:** NGC 7027 sin rasgos y sin cobertura.
- **Carga:** la sección aparece solo cuando el espectro ya está extraído.

**No comprobado en navegador:**

- Fallos de red: la sección no hace consultas propias y reutiliza el espectro ya extraído.
- Los mensajes de la consola del navegador.
- Un punto B real: A y B por separado se comprueban con AppTest.

**Ajustes de presentación tras revisar las capturas:**

- Insignias sin tono: clases del tema.
- Doble paréntesis en «Por qué».
- Registro: Científico mantiene el usted del resto de Espectro en ese nivel («Pulse…», «haga clic…») y Sencillo, el tú.
- Código interno `no_data_aperture` en la tabla de cobertura: ahora se describe la causa.
- Con veredicto «Ninguna», «Qué impide la certeza» recuerda el límite de la biblioteca en lugar de «coincidir no identifica».

**Ejecuciones de pruebas** (son ejecuciones distintas; las cifras no se suman):

1. **Batería de Espectro: 143 superadas** (207 s). Incluye `test_spectral_interpreter`, `test_spectral_interpreter_app`, `test_spectral_features`, `test_spectral_quality`, `test_spectral_offline`, `test_spectral_app` y `test_spectrum_analysis_app`. Se ejecutó tras todos los cambios de código menos el último, que solo cambia el texto de una frase de Científico y no lo cubre ninguna prueba.
2. **Con el código definitivo: 42 superadas** (`test_spectral_interpreter`, `test_spectral_interpreter_app` y `test_spectrum_analysis_app`).

No se ejecutó la regresión completa del proyecto: el cambio no toca otros exploradores.

## 10. Capacidades realizadas y futuras

**Realizadas en V1:**

- registro versionado con fuentes;
- motor de observación, compatibilidad e interpretación con ventana instrumental, naturaleza, anchura, calidad, cobertura y z trazable;
- cinco veredictos;
- interfaz en los dos niveles;
- marcas en el gráfico;
- pruebas sintéticas y reales.

**Futuras (no implementadas):**

- respuesta espectral completa por canal y píxel (Hui et al. 2026);
- modelo de continuo y τ para hielos;
- más líneas de H I (Paα, Brβ, Pfβ, Pfγ, Humphreys) y otras bandas (alifáticas 3,4 µm, CH₃OH, OCN⁻, CO gas);
- z introducido por el usuario o desde catálogos amplios, con trazabilidad;
- coherencia entre varios rasgos del mismo espectro (p. ej. Brα y Pfδ juntas);
- incertidumbres al usar productos con varianza (espectrofotometría oficial de IRSA);
- probabilidades solo con un modelo calibrado y validado.

## 11. Defectos encontrados en otros módulos

- **Insignias de Espectro sin tono:** `spectrum_analysis.BADGE` usaba las clases `ok` y `warn`, pero `theme.py` define `sc-ok` y `sc-warn`. Las insignias «cuantificable» y «visible» se veían siempre neutras. Corregido en esta rama (una línea, solo presentación); el intérprete usa las mismas clases.
- **Aviso de integración heredado** (ya documentado en `PROJECT_STATE.md`): `scripts/v03_verify.py` comprueba la huella de `spectral_cube.py`, que cambió de forma aditiva en `f321c7c`.

## 12. Integración mínima (cuando se autorice)

1. Añadir `spectral_references.py`, `spectral_interpreter.py` y `spectrum_interpretation.py`.
2. Aplicar los cambios de `spectral_view.py`: parámetro opcional `references` y la función `_reference_layers`.
3. Aplicar los cambios de `spectrum_analysis.py`: importación, `sxi.build`, `references=sxi.chart_marks(...)`, `sxi.render(...)` y las clases de `BADGE`.
4. Copiar las dos pruebas nuevas. Requieren los resultados congelados `results/blind_v02` y `results/blind_v03` (ya en la rama base). La de M101 se omite sola si no hay caché del cubo.
5. Ejecutar las pruebas de Espectro y comprobar la sección en los dos niveles y a 420 px.

No requiere cambios en el analizador, el cubo, las máscaras ni otros exploradores. Claves de estado nuevas: `opt_sx_refs` y `w_sx_refs`, además de los botones `sx_interp_<A|B>_<canal>`.
