"""Explicit, reviewed product profiles. Adding an ID is a compatibility decision."""
from . import config

# Deep collections are known IDs but remain opt-in/disabled until a live sample
# and the L2 extension/calibration contract have been checked for this release.
COLLECTIONS = {
    "spherex_dr1": {"enabled": True, "profile": "spherex-l2b", "doi": "10.26131/IRSA678"},
    "spherex_qr3": {"enabled": True, "profile": "spherex-l2b"},
    "spherex_dr1_deep": {"enabled": False, "profile": "unverified"},
    "spherex_qr3_deep": {"enabled": False, "profile": "unverified"},
}
CUBE_RELEASES = {"dr1-hips_20261026": {"doi": config.CUBE_DOI, "data_url": config.CUBE_DATA_URL,
    "hips_url": config.CUBE_HIPS_URL, "order": 5, "planes": 102, "profile": "dr1-mef-102"}}
ACTIVE_CUBE = "dr1-hips_20261026"


def validate_collections(collections):
    values = tuple(dict.fromkeys(collections))
    if not values or any(not COLLECTIONS.get(c, {}).get("enabled") for c in values):
        raise ValueError("Collection not enabled: it requires verifying the format and calibration before use.")
    return values


def reconcile_products(records):
    """Deduplicate a physical exposure/detector, retain rejected provenance.

    Versioned L2 filenames supply exposure IDs. Never infer identity solely
    from rounded dates/coordinates. Unknown identities remain distinct.
    Prefer DR1 over QR3, then version/date within that release. Selection of
    different epochs subsequently requires a common collection and version.
    """
    from .archive import _FILE_RE
    groups = {}
    for r in records:
        m = _FILE_RE.search(r.file_name)
        identity = (m.group("obsid"), r.detector) if m else (r.obs_id, r.detector, r.collection, r.access_url)
        groups.setdefault(identity, []).append(r)
    selected, removed = [], []
    for group in groups.values():
        def rank(r):
            return (r.collection.startswith("spherex_dr1"), int(r.l2b_version or -1), r.processing_date, r.access_url)
        winner = max(group, key=rank)
        selected.append(winner)
        for r in group:
            if r is not winner:
                removed.append({"kept": winner.to_dict(), "excluded": r.to_dict(),
                                "reason": "same exposure/detector; preferred release/version/processing date"})
    return selected, removed


def configure_cube_release(release_id=ACTIVE_CUBE):
    """Startup-only selection. Restart required; unknown profiles cannot activate.

    A new entry requires real FITS/Range/WCS tests first. Use a separate disk
    cache for another published product so old tile IDs cannot cross releases.
    """
    if release_id not in CUBE_RELEASES:
        raise ValueError('Unverified cube version')
    p=CUBE_RELEASES[release_id]
    if (p['profile'],p['order'],p['planes']) != ('dr1-mef-102',5,102):
        raise ValueError('Incompatible cube format: it requires another validated adapter')
    config.CUBE_DATA_URL=p['data_url'];config.CUBE_HIPS_URL=p['hips_url'];config.CUBE_DOI=p['doi']
    config.CUBE_RELEASE_ID=release_id
    if release_id!=ACTIVE_CUBE:
        config.CACHE_DIR=config.ROOT/'data'/'cache'/release_id
    return release_id
