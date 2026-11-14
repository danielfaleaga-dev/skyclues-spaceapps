# SkyClues

SkyClues es un explorador temporal de observaciones infrarrojas **auténticas** del telescopio espacial SPHEREx, obtenidas de NASA/IPAC IRSA. Es un proyecto para NASA Space Apps Challenge 2026, desafío *Planet X and SPHEREx*.

Para cualquier región del cielo y un campo de visión elegido por el usuario (3′–30′), busca observaciones SPHEREx de fechas distintas que sean científicamente comparables: mismo detector, mismo canal LVF efectivo, cobertura común válida y calidad oficial. Después las reproduce sin alterar los datos: cada píxel nativo se dibuja en su posición real del cielo, sin remuestreo.

```bash
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\streamlit run app.py
```

Pruebas: `.venv\Scripts\python -m pytest` (las marcadas `network` usan los FITS de la caché local o los descargan de IRSA). La prueba de la máquina de estados del reproductor necesita Node.js.

Para buscar una secuencia reproducible de N épocas comparables:

```bash
.venv\Scripts\python scripts\find_sequence.py --ra 210.802429 --dec 54.34875 --field 0.1 --name sequence_m101
```

## Despliegue (Streamlit Community Cloud) — preparado, no publicado

- Punto de entrada: `app.py` en la raíz. Dependencias de ejecución: `requirements.txt` (solo runtime; las de desarrollo están en `requirements-dev.txt`). Configuración: `.streamlit/config.toml`.
- Versión de Python: se elige en *Advanced settings* al desplegar. Se recomienda 3.11, la versión de desarrollo. También se ha probado una instalación limpia con 3.14.
- La app escribe en `data/cache/` (FITS de IRSA, sin modificar) y en `results/search_*.json`. En Community Cloud ese disco no es persistente: tras un reinicio, los recortes se vuelven a descargar.
- Opcional: `python scripts/bundle_reference.py` copia a `data/reference/` los FITS de los ejemplos validados (~28 MB, SHA-256 verificado), para que se abran sin depender de IRSA. Versionarlos es una decisión del repositorio.

Datos: NASA/IPAC Infrared Science Archive, SPHEREx DR1 (doi:10.26131/IRSA678) y QR3.

Contexto y estado del proyecto: [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) · [`PROJECT_STATE.md`](PROJECT_STATE.md).
