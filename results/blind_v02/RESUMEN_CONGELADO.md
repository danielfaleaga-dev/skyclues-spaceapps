# Validación ciega V02 · resumen congelado (antes de cualquier consulta externa)

Protocolo: PROTOCOLO.md (commit e3331de). Método: skyclues-features 1.0 (2026-11-14) con las huellas de huellas_metodo.json, idénticas en los tres objetivos. Ninguna posición se ha desplazado. No se ha usado comparación A/B.

| Prueba | Canales con valor | Características etiquetadas | Anomalías bajo criterio | Estado registrado |
|---|---|---|---|---|
| T01 | 37/102 (casi nada por encima de 1,9 µm) | ninguna | ninguna | No evaluable: saturación y píxeles perdidos |
| T02 | 65/102 (hueco en 1,55–3,77 µm) | pico estrecho **visible** en 4,669 µm (+47 %, 5,8×), con OVERFLOW | 1,284 µm (3,95×); 4,076 µm (3,73×, OVERFLOW) | Parcialmente evaluable; saturación generalizada |
| T03 | 50/102 (nada por encima de unos 2,3 µm, salvo el canal 81) | ninguna | 0,955 µm (2,5×); 1,995 µm (3,1×, OVERFLOW) | Solo es evaluable 0,75–2,3 µm |

## Huellas SHA-256

- T01/resultados.json: 06b8c356c37331dd23a658208dceb4c55b5bc4ee8da5c7c0727d7dbbe04899e0
- T01/INFORME_CONGELADO.md: 3dfdc5e09d3ce30955d4cf7cddf7740907b55a550738ec00d394097e9419763d
- T01/espectro.png: 1b4923b4f32ce95c259ce91098ae1bf85ebf04490040f4ab5108013225218a04
- T01/campo.png: 252a54e5dfbfa23eba3a5179c51822cf535c453806ba79af2c5141cc54deb93b
- T02/resultados.json: 75b77b750ebab749007e16e04bcd9a07bb6b681b092c244206d45c61eb4706aa
- T02/INFORME_CONGELADO.md: 619826e2ae558aff538569d29cf0b94d368aea3ebfc3d63dff29fdb1e98db69b
- T02/espectro.png: d754629257a4feab7abf6aae403f30d344f9bc601238b1bbc1047fc6f332e683
- T02/campo.png: 649c95dda36b90b9ed3f8aae47b0817dfddf90d3014f3a3bdf95744badeed5b8
- T03/resultados.json: 8e1220b1b17cc41bba8bc2aad8552a047b011093cf1391c1eb1c79efce3e885b
- T03/INFORME_CONGELADO.md: c5c2d23c79f108e8e5419d18cef8f69845d26458141aee0b63b03b2acd24b8e3
- T03/espectro.png: 782c3ddf056150d33415c770ab0b56ab1671783962d0c72952e8aeef4d6e6d78
- T03/campo.png: 7d854e123ef56dc356134862cc40ab900ed1f5062b75da6c484e59b816418aec
