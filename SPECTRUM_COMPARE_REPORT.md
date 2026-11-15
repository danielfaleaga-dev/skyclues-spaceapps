# SkyClues — Fase S1: comparación de espectros y análisis de picos y valles

Claude Code A · 14/15-11-2026 · rama `feature/spectrum-compare`, carpeta propia `C:\Users\danie\Documents\SkyClues-spectra`. Sin push, despliegue ni publicación. Ningún FITS original modificado. No se tocó la carpeta principal ni el trabajo de Codex / Claude Code B.

## 1. Estado Git inicial y coordinación

- La carpeta principal `SkyClues` estaba en `redesign/unified-region` (`6acf0e8`, rediseño unificado) con cambios sin confirmar de Codex y edición activa (archivos modificados en el último minuto, `pytest` y servidores 8506–8508 en marcha). Esta sesión también tenía su raíz allí: se avisó al usuario y **no se escribió nada en esa carpeta**.
- Se creó un worktree y una rama propios. Como la base efectiva incluía trabajo ajeno sin confirmar, se tomó una **instantánea de solo lectura** con un índice temporal (`49c23a8`, rotulada como tal; ni el árbol ni el índice originales se tocaron) y la rama parte de ella.
- Línea base en esa instantánea, antes de cualquier cambio propio: **416 pruebas correctas y 2 fallos heredados** (`test_moving_target_is_shown_as_a_calculated_position`, `test_time_transfer_keeps_wise_region_not_expected_marker`: textos que dependen del nivel de presentación; ajenos a esta fase).
- La copia de seguridad `C:\Users\danie\Backups\SKYCLUES_BACKUP_PRE_REDESIGN_20261114` no se abrió ni modificó.

## 2. Archivos

Nuevos:

- `skyclues/spectral_features.py` — núcleo numérico (sin Streamlit, sin red).
- `skyclues/spectrum_analysis.py` — integración en la página (presentación; ningún cálculo propio).
- `scripts/validate_spectral_features.py` → `results/spectral_features_validation.json`.
- `tests/test_spectral_features.py` (41, sintéticas), `tests/test_spectrum_analysis_app.py` (9, interfaz), `tests/test_spectral_features_live.py` (3, datos reales).
- Capturas: `results/spectrum-compare-m101.jpg`, `-sencillo.jpg`, `-imagen.jpg`.

Modificados (cambios mínimos):

- `skyclues/spectral_view.py` — el gráfico existente admite una segunda curva, marcas, banda de selección y selección interactiva; nueva función `derived_chart` (A − B, A/B); la imagen admite el punto B. Sin esos argumentos, el gráfico de una posición es el de antes. Las marcas de «canal sin datos» se colocan ahora sobre el eje del área del gráfico (antes quedaban por debajo de la leyenda).
- `skyclues/spectrum_page.py` — cinco puntos: importación, destino del clic, punto B y control junto a la imagen, título, y la llamada al gráfico.

No se modificaron el lector del cubo, la extracción, las máscaras, el modo de un canal, RGB ni la navegación.

## 3. Comparación A/B

- Junto a la imagen: **«Punto A | Punto B»**. El clic coloca el punto activo. A conserva su flujo existente; B se extrae al colocarlo. «Quitar el punto B» vuelve a una sola posición sin tocar A. Una región nueva empieza solo con A.
- En la imagen, con dos puntos: A rombo azul, B cuadrado naranja, con su letra (la identidad no depende solo del color), apertura en línea continua y anillo discontinuo. La geometría de la imagen no cambia al añadir B.
- **Misma extracción en ambos**: B usa siempre la apertura, el anillo y el submuestreo de A (prueba `test_b_uses_the_aperture_of_a_never_its_own`). Antes de operar se comprueban unidad, tabla de canales, ángulo sólido y radios; si algo difiere, A − B y A/B **no se calculan** y se dice por qué.
- Avisos que no bloquean: aperturas solapadas, cada apertura dentro del anillo de fondo de la otra (contaminación mutua), misma posición, teselas distintas.
- Gráfico: las dos curvas en los mismos ejes, sin líneas ni interpolación (un punto por canal real). Debajo, alineado en λ, **A − B** o **A/B** a elección.
- **A − B**: solo donde ambos tienen valor. **A/B**: solo donde A > 0, B > 0 (más allá de la precisión numérica) y B ≥ 3 veces la dispersión del anillo de fondo propagada a la apertura. En el resto no hay valor y se marca sobre el eje con su motivo (rosa: falta A o B; gris: fuera del dominio). Los canales 51 y 52 quedan vacíos.
- Resumen (los mismos números en ambos niveles): canales con ambos, mediana de A − B, fracción con A > B, mediana y dispersión robusta de A/B. Tabla por canal y CSV con procedencia en Científico.
- No se interpreta una diferencia como composición distinta; el texto lo dice.

## 4. Picos y valles

- Marcas sobre la propia curva: ▼ pico, ▲ valle; relleno = *cuantificable*, hueco = *visible*.
- **Selección en el gráfico**: clic en un punto (ese canal, o la característica que lo contiene) o arrastre sobre un intervalo de λ. Se dibuja la banda y debajo aparece la caracterización **del mismo intervalo en A y en B**: λ del extremo y centroide, intervalo a media altura, canales, valor, continuo local, contraste, contraste relativo, razón contraste/dispersión de referencia, canales del entorno, detectores, NHITS, motivos y limitaciones. «Quitar» o doble clic deshacen la selección.
- Sencillo dice lo mismo en una frase («pico: un 191 % más brillante que los colores vecinos. Se distingue con claridad.») y recuerda que un pico no identifica un material.

## 5. Procedimientos numéricos (`skyclues-features 1.0`)

1. **Continuo local**: polinomio de grado 2 por mínimos cuadrados en los 3 canales con valor a cada lado del intervalo, contiguos a él. Un canal sin valor corta el entorno: no se puentea. La característica, y las ya encontradas, quedan fuera del ajuste. Se ajusta ln(valor) frente a ln(λ) si el entorno es positivo (una ley de potencia se reproduce exactamente; un cuerpo negro de 800–5800 K con error ≤ 0,51 % en el intervalo más ancho y ≤ 0,2 % hasta 5 canales); con valores ≤ 0 se ajusta en lineal y se avisa.
2. **Contraste** = valor original − continuo, en el canal extremo. **Sin suavizado**: los valores no se filtran ni se sustituyen.
3. **Dispersión de referencia** = la mayor de: (a) residuo del entorno respecto a su ajuste; (b) dispersión robusta (recorte 3σ, iniciada con MAD) de los residuos «dejando uno fuera» de todo el detector, en términos absolutos y relativos; (c) dispersión del anillo de fondo propagada a la apertura, σ_anillo·√(N_ap + N_ap²/N_anillo)·Ω. El contraste se compara con σ_ref·√(1 + palanca del ajuste).
4. **Barrido**: intervalos de prueba de 1, 3, 5, 7 y 9 canales centrados en cada canal; se toma la escala más estrecha dentro del 10 % de la mejor razón; se acepta el candidato más fuerte, se excluyen sus canales de los entornos siguientes y se repite. Segunda pasada con los canales de los candidatos fuera de la dispersión del detector, para que una línea no oculte a otra.
5. Por debajo del **1 % del continuo** no se señala nada (el polinomio local no distingue una característica de la curvatura de un espectro suave).

## 6. Criterios de calidad

| Clase | Condición |
|---|---|
| **Cuantificable** | razón ≥ 7, entorno válido a ambos lados, un solo detector, sin OVERFLOW/OUTLIER en la característica, NHITS estable (cambio < ×2) |
| **Visible** | razón ≥ 5, pero falla alguna de las condiciones anteriores o no llega a 7 |
| **No evaluable** | canales sin valor en el intervalo, o sin 3 canales de entorno a un lado (borde del intervalo espectral, junto a los canales 51/52) |
| **Sin característica** | razón < 5: oscilación que no se etiqueta (se cuenta, no se marca) |

Se añaden como limitaciones: un solo canal (no se distingue de un valor atípico), entorno con OVERFLOW/OUTLIER, continuo ≤ 0, característica ancha (contraste subestimado), y el canal de 1,083 µm (rayado documentado por He I del resplandor atmosférico: aviso de posible artefacto, no una identificación).

**La dispersión de referencia y los umbrales son criterios descriptivos. No son incertidumbres fotométricas ni significación estadística**: el cubo no tiene varianza, el ruido del mosaico está correlacionado y (c) ignora la propia fuente. Ninguna clase es una «detección».

## 7. Pruebas sintéticas (41, rotuladas como simuladas)

Sobre la rejilla real de 102 canales: espectros idénticos; diferencia y relación conocidas (exactas); canales vacíos, NaN e ∞ nunca rellenados; valores negativos y cero sin división (`np.errstate(all="raise")`); relación retenida con denominador dentro de la dispersión; extracciones o unidades distintas bloquean la operación; solapamiento y contaminación avisados; pico y valle de amplitud conocida (contraste exacto a 1e-9); característica amplia; línea de dos canales; valle en pendiente que no es mínimo local; espectros suaves sin ninguna marca (leyes de potencia, cuerpos negros, plano, cero); un pico fuerte no crea valles falsos; bordes y vecindad de canales sin datos → no evaluable; cruce de detectores, banderas y cambio de cobertura → como mucho *visible*; selección manual igual al barrido; intervalos > 15 canales rechazados; entradas no modificadas.

**Tasas medidas con ruido gaussiano puro (300 espectros por caso):**

| Caso | Falsas «visible» por espectro | Falsas «cuantificable» por espectro |
|---|---|---|
| Con referencia de fondo disponible (el caso normal en la aplicación) | 0 | 0 |
| Sin ella (solo dispersión del propio espectro) | 0,09–0,15 | 0,01–0,03 |

Un pico de un canal necesita ≈ 8,6 σ_ref para ser *cuantificable* y ≈ 6,1 para *visible*. Con 12 σ se recupera en ≥ 95 % de los casos, sin sesgo apreciable; un bulto de 3 σ nunca sale como cuantificable.

## 8. Datos reales SPHEREx (`results/spectral_features_validation.json`)

M101 (objetivo del tutorial oficial de recortes de IRSA; tesela 2858), apertura 2 px, anillo 4–7 px:

- **A** = núcleo (210.802429, +54.34875). **B** = región H II gigante NGC 5461 (210.923546, +54.319916), a 275″.
- 100 de 102 canales con valor en ambos; A > B en los 100; A − B mediana +77,2 mJy; A/B mediana 8,25. Diferencia y relación recalculadas con NumPy: idénticas.
- **Fotometría independiente (Photutils, círculos en píxeles)**: producción difiere un 1,6 % (mediana) en A y un 8,1 % en B. Causa: círculo definido sobre el cielo con 5×5 submuestras frente a círculo en coordenadas de píxel; B es compacta y la forma de la apertura pesa más. No se fuerza la coincidencia.
- **A: ninguna característica señalada. B: cuatro picos cuantificables**:

| Canal | λ (µm) | Contraste | Relativo | Razón | Contraste con Photutils |
|---|---|---|---|---|---|
| 40–41 | 1,861 | +14,4 mJy | +129 % | 7,6 | +13,9 mJy |
| 63 | 3,293 | +26,5 mJy | +191 % | 14,0 | +24,1 mJy |
| 75–76 | 4,076 | +27,1 mJy | +180 % | 22,9 | +26,2 mJy |
| 92–93 | 4,669 | +12,7 mJy | +76 % | 9,7 | +12,3 mJy |

  más dos *visibles* junto al límite D1/D2 (0,955 y 1,102 µm). El continuo de cada una, reajustado con `numpy.polyfit`, coincide a 1e-6.
- **En torno a 3,3 µm**: el mismo intervalo medido en A da +5,2 mJy (+7 %), razón 1,2 → sin característica. La diferencia entre las dos posiciones es real en los datos.
- Los intervalos de esos cuatro picos contienen longitudes de onda que el gráfico del tutorial oficial marca (Paα, PAH 3,3, Brα, CO 4,67). **Es una coincidencia de posición; no se afirma ninguna identificación**: no forma parte de esta fase.
- **Posición del tutorial oficial del cubo** (60.8109955, +51.3404038), donde el propio tutorial informa de emisión intensa en 3,3 µm: pico en el canal 63, +233 % con apertura 5/15/20 px (*cuantificable*, razón 10) y +274 % con 2/4/7 px (*visible*, razón 5,9: el anillo cercano está dentro de la nebulosa y su dispersión es alta). Con los radios del tutorial (5/40/60 px, fotometría independiente) el contraste es +124 %: la diferencia se debe al anillo de fondo, no al método.

## 9. Regresiones

Ver la sección «Regresión final» al pie (se rellena con la última ejecución).

## 10. Rendimiento (medido en frío, caché vacía)

- Extracción de A: 10–12 s, 10 peticiones, 7,6 MB por rangos. B después de A: 7–10 s, 6 peticiones, 7,3 MB (son otras filas del cubo; la cabecera no se vuelve a leer; **ninguna tesela se descarga entera**). Repetición: 0 peticiones.
- Memoria Python pico: 12,8 MB.
- Análisis de picos y valles: 0,13–0,3 s por espectro, en caché por espectro (no se recalcula al cambiar de nivel o de selección).

## 11. Navegador real (servidor propio, puerto 8521)

Comprobado con M101 en Científico y Sencillo: control A/B, B colocado en NGC 5461, dos curvas, panel A − B, marcas, selección del canal de 3,29 µm con su inspector, «Quitar el punto B», geometría de la imagen idéntica con y sin B, ancho de 480 px sin desplazamiento horizontal.

Límite de la comprobación: el panel del navegador estaba oculto y los clics sintéticos no llegan al lienzo de Vega; la selección se accionó a través de la señal de selección del propio gráfico (el mismo camino que recorre un clic real desde Vega hasta Streamlit). **El gesto físico de clic y de arrastre con ratón no se ha probado a mano.**

## 12. Limitaciones científicas

- Espectros exploratorios del cubo combinado: sin incertidumbres, sin corrección de apertura, mezcla de fechas. No es espectrofotometría calibrada.
- Las clases no son detecciones. Sin referencia de fondo, 1–3 de cada 100 espectros de ruido puro tendrían una marca «cuantificable» falsa.
- Canales a menos de 3 de un borde o de los canales 51/52 no son evaluables (12 de 102).
- Una característica que cruza dos detectores nunca pasa de «visible».
- Características más anchas que ~9 canales no se buscan (a esa escala es la forma del espectro).
- A conserva el botón «Obtener el espectro»; B se extrae al colocarlo. Es una asimetría heredada del flujo existente, no rediseñada aquí.
- El enlace compartible no guarda B ni la selección.
- Fuera de alcance, según la orden: identificación de moléculas, biblioteca de bandas, SPLICES, mapas PAH o de hielos, densidades de columna.

## 13. Commits locales

`git log --oneline feature/spectrum-compare` (sin push).
