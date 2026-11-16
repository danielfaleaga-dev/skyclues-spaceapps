"""Central configuration: archive endpoints, collections and comparability thresholds.

Every threshold used to accept or reject a comparison lives here so that the
scientific criteria are explicit and easy to audit.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
REFERENCE_DIR = ROOT / "data" / "reference"   # optional read-only copies of the validated examples' FITS
RESULTS_DIR = ROOT / "results"

# Field of view (FOV): diameter of the sky region searched, downloaded and compared.
# It is NOT a screen zoom. Below FOV_MIN_DEG the field holds too few pixels for
# S5 (MIN_COMMON_VALID_PIXELS); above FOV_MAX_DEG alignment, evaluation and the
# player grow beyond what a small shared server (Community Cloud) handles comfortably.
FOV_PRESETS_ARCMIN = (3.0, 6.0, 12.0, 18.0)
FOV_MIN_DEG = 0.05
FOV_MAX_DEG = 0.5
FOV_SLOW_DEG = 0.2            # warn about longer processing above this

# Validated example sequences offered as quick access in the app (results/<name>.json).
VALIDATED_EXAMPLES = {
    "sequence_m101": "M101 · 4 epochs · 1.42 µm",
    # Centred on the position propagated with SIMBAD proper motion (audit SC-01).
    # sequence_wise0855_mwir (centred on the challenge coordinates, epoch ~2010.4,
    # ~130 arcsec from the 2026 position) stays among the saved results.
    "sequence_wise0855_pm": "WISE 0855 · 2 epochs · 4.86 µm · Δt 1 year",
}

# NASA/IPAC IRSA, IVOA Simple Image Access v2 (verified 2026-11-14).
SIA_URL = "https://irsa.ipac.caltech.edu/SIA"
# Current SPHEREx spectral-image collections (QR2 is no longer searchable).
WIDE_COLLECTIONS = ("spherex_dr1", "spherex_qr3")
DEEP_COLLECTIONS = ("spherex_dr1_deep", "spherex_qr3_deep")

HTTP_HEADERS = {"User-Agent": "SkyClues/0.1 (NASA Space Apps 2026 prototype; astropy/pyvo)"}
# (connect, read) timeouts per request. A 4 MB cutout takes a few seconds; IRSA
# can take ~1 min to start answering a cutout under load.
HTTP_TIMEOUT_S = (15, 90)
# Attempts per request. Only transient failures are retried (timeouts,
# connection errors, HTTP 408/425/429 and 5xx); other 4xx fail at once.
HTTP_RETRIES = 4
HTTP_BACKOFF_S = 4.0          # 4, 8, 16 s between attempts (never after the last one)
HTTP_BACKOFF_MAX_S = 30.0     # cap, also for a server Retry-After
HTTP_DEADLINE_S = 240.0       # total time budget per URL, attempts and waits included

# SPHEREx Level-2 geometry.
DETECTOR_NPIX = 2040
NOMINAL_PIXEL_SCALE_ARCSEC = 6.15

# Instrument bands (approximate, from IRSA documentation).
BANDS_UM = {
    1: (0.75, 1.09),
    2: (1.10, 1.62),
    3: (1.63, 2.41),
    4: (2.42, 3.82),
    5: (3.83, 4.41),
    6: (4.42, 5.00),
}

# ---- Comparability thresholds -------------------------------------------
# Spectral: SPHEREx LVF filters make wavelength depend on detector position.
# Mismatch is expressed in units of the local spectral bandwidth (one
# resolution element). <= PASS: same effective channel; <= WARN: partial overlap.
SPECTRAL_PASS_BW = 0.25
SPECTRAL_WARN_BW = 0.50
# Pre-selection tolerance on the metadata-only wavelength estimate (slightly
# looser than PASS to absorb estimation error; final decision uses the FITS).
SPECTRAL_PRESELECT_BW = 0.35

MIN_TIME_SEPARATION_DAYS = 1.0  # different observation dates

# Fraction of the comparison field (circle of diameter = field size) where
# both observations have valid, unmasked pixels.
COVERAGE_PASS = 0.60
COVERAGE_WARN = 0.30
MIN_COMMON_VALID_PIXELS = 300

# Saturation-related pixels (OVERFLOW / NONLINEAR) allowed in the field
# before a warning is raised.
SATURATION_WARN_FRACTION = 0.001

DEFAULT_FIELD_DEG = 0.1
MAX_PAIRS_TO_DOWNLOAD = 4

# ---- Temporal sequences --------------------------------------------------
# A sequence with more epochs is preferred only if its common valid coverage
# is within this tolerance of the best admissible option (pair included), so
# the number of dates never automatically outweighs comparable sky area.
SEQUENCE_COVERAGE_TOLERANCE = 0.15
MAX_SEQUENCE_FRAMES = 8
MAX_SEQUENCE_CANDIDATES = 3

# ---- Performance -----------------------------------------------------------
METADATA_CACHE_MAX_AGE_S = 12 * 3600   # SIA2 results and WCS-WAVE tables
DOWNLOAD_WORKERS = 3

# ---- Spectrum Explorer: SPHEREx DR1 All-Sky spectral cube (doi:10.26131/IRSA679) -------
# Official access (IRSA tutorial "Using SPHEREx HiPS All-Sky Mosaic Cubes", 2026-11-04):
# HiPS (PNG, visualization only) and the underlying FITS cubes, one per HEALPix
# order-5 tile: <CUBE_DATA_URL>/Norder5/Dir<10000*floor(ipix/10000)>/Npix<ipix>_cube.fits
# Each tile is a ~320 MB MEF (IMAGE / NHITS / FLAGS cubes of 102 x 512 x 512).
CUBE_HIPS_URL = "https://irsa.ipac.caltech.edu/data/hips/SPHEREx/spherex_allsky_cube"
CUBE_DATA_URL = "https://irsa.ipac.caltech.edu/ibe/data/spherex/dr1/hips5_cube/hips_20261026"
CUBE_ORDER = 5
CUBE_DOI = "10.26131/IRSA679"
CUBE_TUTORIAL_URL = "https://caltech-ipac.github.io/irsa-tutorials/spherex-hipscube/"
SPECTROPHOTOMETRY_TOOL_URL = "https://irsa.ipac.caltech.edu/applications/spherex/tool-spectrophotometry"
# SkyClues never downloads a whole tile: it reads only the rows it needs with
# HTTP Range requests. IRSA (nginx) answers a request with more than ~100 ranges
# with the WHOLE file (HTTP 200, 320 MB; verified 2026-11-14 with 128 ranges),
# so requests carry at most this many ranges and a 200 answer is never read.
CUBE_MAX_RANGES_PER_REQUEST = 64
CUBE_MAX_BYTES_PER_CALL = 48 * 2**20      # refuse any single read larger than this
CUBE_CACHE_MAX_MB = 200                   # verbatim byte ranges kept on disk (no new writes beyond)
CUBE_FIELD_MAX_DEG = FOV_MAX_DEG          # same field-of-view limits as Time Explorer
# Exploratory aperture photometry (official tutorial method). Radii in mosaic
# pixels (12.9 arcsec). Defaults chosen by SkyClues for compact sources; the
# tutorial example used 5 / 40-60 px for an extended cloud.
CUBE_APERTURE_DEFAULT_PX = (2.0, 4.0, 7.0)   # aperture radius, annulus inner, annulus outer
CUBE_APERTURE_MAX_PX = (5.0, 15.0, 20.0)
CUBE_ANNULUS_MIN_VALID = 0.5               # fraction of annulus pixels that must hold data
