"""Sky geometry helpers that work from archive metadata alone.

SIA2 ``s_region`` polygons for SPHEREx Level-2 images list the four detector
corners in the order of full-detector 1-based pixels
(0.5, 0.5), (2040.5, 0.5), (2040.5, 2040.5), (0.5, 2040.5).
This was verified against the FITS WCS of a real cutout (2026-11-14) and is
re-checked by the network test-suite.

Because gnomonic projections from different tangent points are related by a
projective transform, a homography fitted to those four corners maps sky
positions to detector pixels with an error dominated by the small SIP
distortion (~1 px). That is accurate enough to pre-select images; final
decisions always use the FITS WCS.
"""

from __future__ import annotations

import numpy as np

from .config import DETECTOR_NPIX

CORNER_PIXELS_1BASED = np.array([
    [0.5, 0.5],
    [DETECTOR_NPIX + 0.5, 0.5],
    [DETECTOR_NPIX + 0.5, DETECTOR_NPIX + 0.5],
    [0.5, DETECTOR_NPIX + 0.5],
])


def parse_s_region(s_region: str) -> np.ndarray:
    """Return an (N, 2) array of (ra, dec) degrees from 'POLYGON [ICRS] ...'."""
    tokens = s_region.replace(",", " ").split()
    if not tokens or tokens[0].upper() != "POLYGON":
        raise ValueError(f"Unsupported s_region: {s_region[:40]}")
    nums = []
    for t in tokens[1:]:
        try:
            nums.append(float(t))
        except ValueError:
            continue  # frame name such as ICRS
    pts = np.array(nums, dtype=float).reshape(-1, 2)
    if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    return pts


def gnomonic(ra, dec, ra0, dec0):
    """Project (ra, dec) [deg] onto the tangent plane at (ra0, dec0) [deg]."""
    ra, dec = np.radians(ra), np.radians(dec)
    ra0, dec0 = np.radians(ra0), np.radians(dec0)
    cosc = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    xi = np.cos(dec) * np.sin(ra - ra0) / cosc
    eta = (np.cos(dec0) * np.sin(dec) - np.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / cosc
    return np.degrees(xi), np.degrees(eta)


def fit_homography(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Exact 3x3 homography from 4 point correspondences (DLT)."""
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        b.append(u)
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b.append(v)
    h = np.linalg.solve(np.array(a, float), np.array(b, float))
    return np.append(h, 1.0).reshape(3, 3)


def apply_homography(h: np.ndarray, x, y):
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    w = h[2, 0] * x + h[2, 1] * y + h[2, 2]
    u = (h[0, 0] * x + h[0, 1] * y + h[0, 2]) / w
    v = (h[1, 0] * x + h[1, 1] * y + h[1, 2]) / w
    return u, v


class FootprintMap:
    """Approximate sky -> full-detector pixel map built from an s_region polygon."""

    def __init__(self, s_region: str):
        self.corners = parse_s_region(s_region)
        if len(self.corners) != 4:
            raise ValueError("Expected a 4-corner detector polygon")
        self.ra0 = float(np.mean(self.corners[:, 0]))
        self.dec0 = float(np.mean(self.corners[:, 1]))
        xi, eta = gnomonic(self.corners[:, 0], self.corners[:, 1], self.ra0, self.dec0)
        self.h = fit_homography(np.column_stack([xi, eta]), CORNER_PIXELS_1BASED)

    def sky_to_pixel(self, ra, dec):
        """Full-detector 1-based pixel coordinates (x, y)."""
        xi, eta = gnomonic(ra, dec, self.ra0, self.dec0)
        return apply_homography(self.h, xi, eta)

    def field_margin_px(self, ra: float, dec: float, radius_deg: float, n: int = 24) -> float:
        """Smallest distance (px) from a circular field to the detector edge.

        Negative values mean part of the field falls outside the detector.
        """
        ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
        cosd = np.cos(np.radians(dec))
        ras = ra + radius_deg * np.cos(ang) / max(cosd, 1e-6)
        decs = dec + radius_deg * np.sin(ang)
        x, y = self.sky_to_pixel(np.append(ras, ra), np.append(decs, dec))
        lo, hi = 0.5, DETECTOR_NPIX + 0.5
        return float(np.min(np.minimum.reduce([x - lo, hi - x, y - lo, hi - y])))


def bilinear_lookup(xs: np.ndarray, ys: np.ndarray, values: np.ndarray, x: float, y: float) -> np.ndarray:
    """Bilinear interpolation of a WCS-WAVE style table.

    ``values`` has shape (len(ys), len(xs), k); returns the k interpolated
    quantities at full-detector 1-based pixel (x, y).
    """
    x = float(np.clip(x, xs[0], xs[-1]))
    y = float(np.clip(y, ys[0], ys[-1]))
    i = int(np.clip(np.searchsorted(xs, x) - 1, 0, len(xs) - 2))
    j = int(np.clip(np.searchsorted(ys, y) - 1, 0, len(ys) - 2))
    tx = (x - xs[i]) / (xs[i + 1] - xs[i])
    ty = (y - ys[j]) / (ys[j + 1] - ys[j])
    v00, v10 = values[j, i], values[j, i + 1]
    v01, v11 = values[j + 1, i], values[j + 1, i + 1]
    return (1 - tx) * (1 - ty) * v00 + tx * (1 - ty) * v10 + (1 - tx) * ty * v01 + tx * ty * v11


def separation_deg(ra1, dec1, ra2, dec2):
    ra1, dec1, ra2, dec2 = map(np.radians, (ra1, dec1, ra2, dec2))
    s = np.sin((dec2 - dec1) / 2) ** 2 + np.cos(dec1) * np.cos(dec2) * np.sin((ra2 - ra1) / 2) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(s, 0, 1))))
