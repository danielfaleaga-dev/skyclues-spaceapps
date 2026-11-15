# NGC 7023 · comparación con la literatura (posterior a la congelación)

La consulta empezó después del commit `a73c0ef`, que congela `RESULTADOS_CONGELADOS.md`. Nada de lo congelado se ha modificado, y el algoritmo tampoco.

## Fuentes consultadas

1. **Pilleri et al. 2015, A&A, doi:10.1051/0004-6361/201425590** — espectroimagen AKARI/IRC de 2,5–5 µm de la PDR noroeste ([arXiv:1502.04941](https://arxiv.org/abs/1502.04941)).
   - Resolución de unos 0,02 µm.
   - Posiciones representativas a [−29″, 24″] … [−43″, 41″] de HD 200775.
   - Bandas ajustadas:
     - 3,29 µm, aromática, FWHM ≈ 0,03 µm;
     - 3,40 µm, alifática, FWHM ≈ 0,03 µm;
     - meseta de 3,45 µm, FWHM ≈ 0,1 µm.
   - I₃.₄/I₃.₃ = 0,03–0,13; la meseta vale aproximadamente 0,5–0,7 veces I₃.₃.
   - La banda de 3,3 µm domina el complejo 3,2–3,6 µm en todas sus posiciones.
2. **Croiset et al. 2016, A&A, doi:10.1051/0004-6361/201527714** — imágenes SOFIA/FLITECAM a 3,3 µm y FORCAST a 11,2 µm de un campo de 3,2′ × 3,4′ ([arXiv:1603.02577](https://arxiv.org/abs/1603.02577); [página de IRSA](https://irsa.ipac.caltech.edu/data/SOFIA/docs/multimedia/image-galleries/ngc-7023-33-μm/index.html)).
   - La emisión de 3,3 µm traza las PDR noroeste y sur.
   - Los PAH más pequeños se concentran en la superficie de esas PDR.
   - Lo consultado no da la emisión de 3,3 µm en posiciones concretas a unos 100″ de la estrella.
3. **2MASS PSC (IRSA, búsqueda por cono; comprobación posterior de fuentes puntuales):**
   - **A:** 2MASS J21013754+6811309 a 8,0″, con J = 11,27, H = 10,26 y Ks = 9,68 (calidad AAA), dentro de la apertura de 25,8″. Su Ks equivale a unos 89 mJy a 2,2 µm, del orden del flujo medido en A (unos 120 mJy). A está dominado por esta estrella de campo, enrojecida (J − Ks = 1,59).
   - **B:** solo fuentes débiles (Ks ≥ 15,3) a menos de 25″. Una de Ks = 12,4 está a 28″, en el borde de la apertura.

SIMBAD no respondía durante la consulta. No se encontró en lo consultado un espectro de SOFIA en 1–5 µm; SOFIA aporta solo la imagen de 3,3 µm.

## Comparación

| Aspecto | SkyClues (congelado) | Literatura | Dictamen |
|---|---|---|---|
| Longitud de onda, B | Exceso de un canal en 3,293 µm (canal 63, ancho ≈ 0,09 µm), +137 %, 3,4 × dispersión, **no etiquetado** | Banda aromática a 3,29 µm, FWHM 0,03 µm: cabe en un canal de SPHEREx | **Coincidencia en λ y anchura, por debajo del umbral**. El método no la recupera como característica. |
| Longitud de onda, A | Pico ancho «visible», extremo en 3,383 µm (centroide 3,379), media altura 3,24–3,53 µm | Complejo 3,29 + 3,40 + meseta de 3,45 µm (3,2–3,6 µm), con 3,29 dominante | **Coincidencia parcial.** El intervalo cubre el complejo, pero el máximo está en el canal de 3,38 y no en el de 3,29. Con I₃.₄/I₃.₃ ≤ 0,13 y la meseta ≤ 0,7, en una PDR típica cabría esperar el canal 63 por encima del 64. En A ocurre lo contrario (126 frente a 149 mJy). **Discrepancia de perfil.** |
| Signo | Emisión (positivo) en A y en B | Bandas en emisión | **Coincide.** |
| Presencia en zonas comparables | A y B están a unos 105–115″ de la estrella, fuera de las posiciones de AKARI (unos 40–60″ al NW) | AKARI cubre solo la PDR NW. SOFIA traza la emisión en las PDR NW y S, pero lo consultado no da valores a unos 100″ | **No evaluable** posición a posición. |
| Diferencias entre regiones | A/B mínimo en 3,29 µm (1,4, frente a una mediana de 2,25): en ese canal, B gana peso respecto a A | En la literatura, la emisión de 3,3 µm sigue a las PDR y no a las estrellas de campo | **Compatible** en cuanto a que B, el más nebular, destaca en 3,29 µm. A está contaminado por una estrella. |
| Resolución | R ≈ 40 en D4: 3,29 y 3,40 µm caen en canales contiguos (63 y 64), y la meseta en el 64–65 | Bandas separadas solo con R ≳ 100 | Las bandas no se separan; ningún resultado de SkyClues puede atribuirse a una banda concreta. |
| Fondo y apertura | Anillo de 51–90″ con media recortada. En B, el anillo contiene estructura nebular que también emite en 3,29 µm (su dispersión se dobla en ese canal) | AKARI usa una rendija de unos 3″; SOFIA, imagen de 2,7″ | **Limitación grave:** la resta del anillo elimina parte de la emisión extensa y eleva la dispersión de referencia. Por eso B no se etiqueta. |

## Lo que no se interpreta

- La estrella 2MASS de A está enrojecida (J − Ks = 1,59). Puede ser un objeto de fondo extinguido o una estrella joven. Sin espectro propio, no se atribuye el pico de 3,38 µm ni a la estrella ni a la nebulosa.
- La coincidencia en longitud de onda **no** identifica PAH ni enlaces C–H alifáticos.
