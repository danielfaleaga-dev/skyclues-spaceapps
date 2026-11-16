# SkyClues

**NASA Space Apps Challenge 2026 · Challenge: *Planet X and SPHEREx***
Team **SkyClues** · Daniel Aleaga

SkyClues opens **real infrared observations from NASA's SPHEREx space telescope** for anyone. Choose a region of the sky by name, by coordinates or by moving the sky atlas, set the field of view (3′–30′), and explore it in two ways:

- **Time:** real SPHEREx images of the same region taken on different dates, played like a video (play, step, blink), with quality, provenance and measured motion. Only scientifically comparable images are compared: same detector, same infrared colour, valid common coverage and official quality flags.
- **Spectrum:** the light of any point in SPHEREx's 102 infrared colours (0.75–5 µm), with peaks and valleys, comparison of two points and a false-colour RGB composite.

Two presentation levels, **Simple** and **Scientific**, show exactly the same data and results.

- **Live app:** https://skyclues-spherex.streamlit.app
- **Slides:** https://claude.ai/artifact/K34viKuUcGcf4vW6oDJYGF

## Highlight: interstellar comet 3I/ATLAS

In the app, press **«Follow 3I/ATLAS across the sky»**, then **Find SPHEREx observations** and **Prepare images**. SkyClues measures the comet's position in each authentic SPHEREx exposure and registers it against stars that do not move.

| SPHEREx exposures | Measured displacement | Interval | Control stars |
|---|---|---|---|
| 9 Aug 2025, detector D1 | **166″ ± 3″** | 99 min | 16 (≤ 0.7″) |
| 14 Dec 2025, detectors D2 and D5 | **294″ ± 4″** | 101 min | 15 and 6 |

The same code measures Pluto and asteroid 3 Juno. Controls (galaxy M101 and deliberately shifted predictions) show no motion, and saturated Vesta is reported as not evaluable. The predicted position only tells the software where to look: it is never presented as a detection. Method and limits: [`MOVING_OBJECTS_REPORT.md`](MOVING_OBJECTS_REPORT.md).

## Scientific integrity

- Every image is an authentic SPHEREx file from NASA/IPAC IRSA, kept byte for byte with its SHA-256. Nothing is interpolated, filled or invented; masked pixels are shown in a labelled colour.
- Comparisons use the official FLAGS masks, wavelengths and quality keywords of each file.
- Spectra from the DR1 all-sky cube are exploratory: the cube combines many dates and is never used as a time sequence.
- "Not enough evidence" is a valid result.

## Data and technology

- **NASA SPHEREx** spectral images and the DR1 all-sky spectral cube, via **NASA/IPAC IRSA** ([doi:10.26131/IRSA678](https://doi.org/10.26131/IRSA678), [doi:10.26131/IRSA679](https://doi.org/10.26131/IRSA679)).
- **IRSA MOST** and **JPL Horizons** to locate moving Solar System bodies in the archive.
- **ESA Gaia DR3**, **2MASS** and **AllWISE** as reference maps (other missions and epochs, never mixed with SPHEREx measurements).
- Open source: Python, Astropy, PyVO, Aladin Lite and Streamlit.

## Run locally

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
.venv/bin/streamlit run app.py
```

Tests: `pip install -r requirements-dev.txt`, then `python -m pytest -m "not network" -q` (offline) or `python -m pytest -q` (uses IRSA).

## More documentation

Project state and methods (mostly in Spanish): [`PROJECT_STATE.md`](PROJECT_STATE.md), [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md), [`INTEGRATION_REPORT.md`](INTEGRATION_REPORT.md), [`SPECTRUM_COMPARE_REPORT.md`](SPECTRUM_COMPARE_REPORT.md), [`INFRARED_SNR_REPORT.md`](INFRARED_SNR_REPORT.md), [`DESIGN_SYSTEM.md`](DESIGN_SYSTEM.md).
