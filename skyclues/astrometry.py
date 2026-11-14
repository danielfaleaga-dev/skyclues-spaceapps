"""Epoch-dependent target positions (proper motion, parallax, radial velocity).

Catalogue coordinates refer to an epoch. A high-proper-motion object is far
from its catalogue position at SPHEREx epochs (WISE 0855: 8.15 arcsec/yr,
about 215 arcsec between J2000.0 and 2026). This module computes the
*expected* position of a target at a given date:

1. space motion from the catalogue epoch (``SkyCoord.apply_space_motion``,
   proper motion + radial velocity + distance from the parallax);
2. geocentric parallax: the direction from the Earth (SPHEREx is in low
   Earth orbit; the 700 km offset is negligible) to the propagated position.
   Aberration is not applied: SPHEREx WCS are fitted to astrometric catalogue
   positions, so image coordinates are astrometric (ICRS) directions.

An expected position is a calculation, never a detection.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import asdict, dataclass

import numpy as np

SIMBAD_TAP_URLS = (
    "https://simbad.cds.unistra.fr/simbad/sim-tap",
    "https://simbad.harvard.edu/simbad/sim-tap",      # official mirror
)


@dataclass(frozen=True)
class Astrometry:
    """Catalogue astrometry of a target (ICRS)."""

    name: str
    ra_deg: float                  # at epoch_jyear
    dec_deg: float
    epoch_jyear: float = 2000.0
    pmra_masyr: float | None = None    # mu_alpha* = mu_alpha cos(delta)
    pmdec_masyr: float | None = None
    parallax_mas: float | None = None
    rv_kms: float | None = None
    source: str = ""

    # -- properties -------------------------------------------------------
    @property
    def has_proper_motion(self) -> bool:
        return _ok(self.pmra_masyr) and _ok(self.pmdec_masyr)

    @property
    def has_parallax(self) -> bool:
        return _ok(self.parallax_mas) and self.parallax_mas > 0

    @property
    def total_pm_arcsec_yr(self) -> float:
        if not self.has_proper_motion:
            return 0.0
        return math.hypot(self.pmra_masyr, self.pmdec_masyr) / 1000.0

    def warnings(self) -> list[str]:
        """Limitations of the available astrometry, in plain language."""
        out = []
        if not self.has_proper_motion:
            out.append("Sin movimiento propio en el catálogo: se usa la posición de catálogo para todas las fechas "
                       "(correcto para objetos lejanos; incorrecto si el objeto se mueve).")
        else:
            if not self.has_parallax:
                out.append("Sin paralaje: la posición se propaga solo con el movimiento propio (sin efecto de "
                           "paralaje anual).")
            if not _ok(self.rv_kms):
                out.append("Sin velocidad radial: se desprecia la aceleración de perspectiva "
                           "(efecto mínimo en pocas décadas).")
        return out

    # -- positions --------------------------------------------------------
    def position_at(self, when) -> tuple[float, float]:
        """Expected astrometric (geocentric) ICRS position at ``when``.

        ``when`` is an astropy Time, an MJD (float) or a Julian year (float
        > 3000 is treated as MJD). Without proper motion the catalogue
        position is returned unchanged.
        """
        if not self.has_proper_motion:
            return float(self.ra_deg), float(self.dec_deg)
        t = to_time(when)
        moved = self._propagated(t)
        if not self.has_parallax:
            return float(moved.ra.deg), float(moved.dec.deg)
        return _geocentric_direction(moved, t)

    def offset_arcsec(self, when, ra: float, dec: float) -> float:
        """Separation between the expected position at ``when`` and (ra, dec)."""
        r, d = self.position_at(when)
        return _sep_arcsec(r, d, ra, dec)

    def _propagated(self, t):
        import astropy.units as u
        from astropy.coordinates import Distance, SkyCoord
        from astropy.time import Time

        dist = Distance(parallax=self.parallax_mas * u.mas) if self.has_parallax else 1e6 * u.pc
        c = SkyCoord(ra=self.ra_deg * u.deg, dec=self.dec_deg * u.deg, distance=dist,
                     pm_ra_cosdec=self.pmra_masyr * u.mas / u.yr, pm_dec=self.pmdec_masyr * u.mas / u.yr,
                     radial_velocity=(self.rv_kms if _ok(self.rv_kms) else 0.0) * u.km / u.s,
                     obstime=Time(self.epoch_jyear, format="jyear", scale="tdb"), frame="icrs")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")          # ERFA notes on large distances
            return c.apply_space_motion(new_obstime=t)

    # -- persistence ------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Astrometry | None":
        if not d:
            return None
        keys = cls.__dataclass_fields__.keys()
        return cls(**{k: d[k] for k in keys if k in d})


def _ok(v) -> bool:
    return v is not None and isinstance(v, (int, float, np.floating)) and math.isfinite(float(v))


def to_time(when):
    from astropy.time import Time

    if isinstance(when, Time):
        return when
    v = float(when)
    return Time(v, format="mjd", scale="tdb") if v > 3000 else Time(v, format="jyear", scale="tdb")


def _geocentric_direction(coord, t) -> tuple[float, float]:
    import astropy.units as u
    from astropy.coordinates import get_body_barycentric

    star = coord.cartesian.xyz.to(u.au).value
    earth = get_body_barycentric("earth", t).xyz.to(u.au).value
    x, y, z = star - earth
    ra = math.degrees(math.atan2(y, x)) % 360.0
    dec = math.degrees(math.atan2(z, math.hypot(x, y)))
    return ra, dec


def _sep_arcsec(ra1, dec1, ra2, dec2) -> float:
    from .geometry import separation_deg

    return float(separation_deg(ra1, dec1, ra2, dec2)) * 3600.0


# --------------------------------------------------------------------- SIMBAD
def query_simbad(name: str, timeout: float = 30.0) -> Astrometry:
    """Astrometry of ``name`` from SIMBAD (TAP; CDS, then the Harvard mirror).

    SIMBAD positions are ICRS at epoch J2000.0; proper motion, parallax and
    radial velocity come with their bibcodes. Raises LookupError if the name
    is unknown and RuntimeError if no SIMBAD service answers.
    """
    import pyvo

    from .archive import _timeout_session

    adql =("SELECT main_id, ra, dec, pmra, pmdec, plx_value, rvz_radvel, coo_bibcode, pm_bibcode, plx_bibcode "
            "FROM basic JOIN ident ON ident.oidref = basic.oid WHERE ident.id = '{}'")
    errors = []
    for url in SIMBAD_TAP_URLS:
        try:
            svc = pyvo.dal.TAPService(url, session=_timeout_session((10, timeout)))
            tab = svc.run_sync(adql.format(name.strip().replace("'", "''"))).to_table()
        except Exception as err:            # service down / blocked: try the mirror
            errors.append(f"{url}: {type(err).__name__}: {str(err)[:120]}")
            continue
        if len(tab) == 0:
            raise LookupError(f"SIMBAD no conoce el objeto «{name}»")
        r = tab[0]

        def val(col):
            v = r[col]
            if np.ma.is_masked(v):
                return None
            try:
                v = float(v)
            except (TypeError, ValueError):
                return None
            return v if math.isfinite(v) else None

        refs = sorted({str(r[c]).strip() for c in ("coo_bibcode", "pm_bibcode", "plx_bibcode")
                       if str(r[c]).strip() and not np.ma.is_masked(r[c])})
        from astropy.time import Time

        return Astrometry(
            name=str(r["main_id"]).strip(), ra_deg=val("ra"), dec_deg=val("dec"), epoch_jyear=2000.0,
            pmra_masyr=val("pmra"), pmdec_masyr=val("pmdec"), parallax_mas=val("plx_value"),
            rv_kms=val("rvz_radvel"),
            source=f"SIMBAD ({url.split('/')[2]}, {Time.now().isot[:10]}); refs: {', '.join(refs) or '—'}")
    raise RuntimeError("SIMBAD no responde: " + " | ".join(errors))


__all__ = ["Astrometry", "query_simbad", "to_time", "SIMBAD_TAP_URLS"]
