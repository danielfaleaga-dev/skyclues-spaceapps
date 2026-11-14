# SkyClues

SkyClues es un explorador temporal de observaciones infrarrojas **auténticas** del telescopio espacial SPHEREx, obtenidas de NASA/IPAC IRSA. Es un proyecto para NASA Space Apps Challenge 2026, desafío *Planet X and SPHEREx*.

Para cualquier región del cielo, busca observaciones SPHEREx de fechas distintas que sean científicamente comparables: mismo detector, mismo canal LVF efectivo, cobertura común válida y calidad oficial. Después las muestra sin alterar los datos.

```bash
py -3.11 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```

Pruebas: `.venv\Scripts\python -m pytest` (las marcadas `network` consultan IRSA).

Datos: NASA/IPAC Infrared Science Archive, SPHEREx DR1 (doi:10.26131/IRSA678) y QR3.

Contexto y estado del proyecto: [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) · [`PROJECT_STATE.md`](PROJECT_STATE.md).
