"""Central configuration: archive endpoints, collections and comparability thresholds.

Every threshold used to accept or reject a comparison lives here so that the
scientific criteria are explicit and easy to audit.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
RESULTS_DIR = ROOT / "results"

# NASA/IPAC IRSA, IVOA Simple Image Access v2 (verified 2026-11-14).
SIA_URL = "https://irsa.ipac.caltech.edu/SIA"
# Current SPHEREx spectral-image collections (QR2 is no longer searchable).
WIDE_COLLECTIONS = ("spherex_dr1", "spherex_qr3")
DEEP_COLLECTIONS = ("spherex_dr1_deep", "spherex_qr3_deep")

HTTP_HEADERS = {"User-Agent": "SkyClues/0.1 (NASA Space Apps 2026 prototype; astropy/pyvo)"}
HTTP_TIMEOUT_S = 180
HTTP_RETRIES = 6

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
