"""Discovery adapters for KNOWN moving objects; no detection or object-specific algorithm.

MOST supplies SPHEREx intersections and spacecraft-orbit predictions. A published
per-exposure table can override predictions by exact exposure+detector identity.
Raw replies are cached verbatim. No geocentric fallback is silently substituted.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import numpy as np
import requests
from astropy.table import Table
from astropy.time import Time

from . import archive, config, solar_system
from .geometry import FootprintMap, bilinear_lookup
from .pairing import wave_table_from_url

MOST = 'https://irsa.ipac.caltech.edu/cgi-bin/MOST/nph-most'
CACHE = config.CACHE_DIR / 'moving'
METHOD = 'known-moving 1.1'


def _request(url, params=None, refresh=False, ttl=86400):
    key = hashlib.sha256((url + json.dumps(params, sort_keys=True)).encode()).hexdigest()
    path = CACHE / (key + '.bin')
    meta = CACHE / (key + '.json')
    if not refresh and path.exists() and meta.exists() and time.time()-path.stat().st_mtime < ttl:
        b = path.read_bytes()
        p = json.loads(meta.read_text())
        if hashlib.sha256(b).hexdigest() == p['sha256']:
            return b, {**p, 'cache': True}
    try:
        with requests.get(url, params=params, timeout=(10, 90), stream=True,
                          headers=config.HTTP_HEADERS) as r:
            if r.status_code != 200:
                raise solar_system.ServiceError(f'IRSA respondió HTTP {r.status_code}: {r.text[:200]}')
            parts, size = [], 0
            for block in r.iter_content(65536):
                size += len(block)
                if size > 16*1024*1024:
                    raise solar_system.ServiceError('Consulta demasiado grande. Reduzca el intervalo de fechas.')
                parts.append(block)
            b = b''.join(parts)
            p = {'url': r.url, 'queried_utc': datetime.now(timezone.utc).isoformat(),
                 'sha256': hashlib.sha256(b).hexdigest(), 'cache': False}
    except requests.RequestException as e:
        raise solar_system.ServiceError('IRSA no respondió. Puede reintentar la consulta.') from e
    archive.atomic_write(path, b)
    archive.atomic_write(meta, json.dumps(p))
    return b, p


def parse_most(blob):
    text = blob.decode('utf-8')
    if '|    ra_obj' not in text and 'ra_obj|' not in text:
        if re.search(r'ephem_step reset to the time range:\s*-',text):
            raise solar_system.ServiceError('MOST no pudo calcular la efeméride en ese intervalo. '
                'Puede quedar fuera de la cobertura orbital del observador; pruebe otras fechas.')
        if re.search(r'no (?:records|images|matches|data).*found|no matching', text, re.I):
            return Table()
        raise solar_system.ServiceError('MOST no devolvió una tabla de exposiciones: ' + text[:180])
    return Table.read(text, format='ascii.ipac')


def discover(identity, start, end, *, refresh=False, step_days=0.02):
    """Bounded metadata-only search along a trajectory. Dates are UTC, at most 366 days.

    Discovery coordinates are provisional: MOST's SPHEREx match uses exposure start.
    Selected predictions are evaluated at exposure midpoint before downloads.
    """
    a, b = Time(start), Time(end)
    if not 0 < b.mjd-a.mjd <= 366:
        raise ValueError('El intervalo debe abarcar entre un instante y 366 días.')
    if not np.isfinite(step_days) or not 0 < step_days <= .25:
        raise ValueError('Paso de efemérides inválido (0 < días ≤ 0,25).')
    sid = str(identity['spkid'])
    if not re.fullmatch(r'\d{1,12}', sid):
        raise ValueError('Identificador JPL inválido')
    params = {'catalog': 'spherex', 'input_type': 'naifid_input', 'obj_naifid': sid,
              'obs_begin': a.strftime('%Y %m %d %H:%M:%S'),
              'obs_end': b.strftime('%Y %m %d %H:%M:%S'),
              'output_mode': 'Brief', 'ephem_step': str(step_days)}
    raw, provenance = _request(MOST, params, refresh)
    tab = parse_most(raw)
    rows, excluded = [], []
    for r in tab:
        url = urljoin('https://irsa.ipac.caltech.edu/', str(r['uri']))
        m = archive._FILE_RE.search(url)
        release = re.search(r'/spherex/(dr1|qr3|qr2)/level2/', url)
        if not m or not release or urlparse(url).hostname != 'irsa.ipac.caltech.edu':
            excluded.append(str(r['uri'])); continue
        obs = str(r['observationid'])
        if m['obsid'] != obs:
            raise solar_system.ServiceError('Identidad de exposición inconsistente en MOST.')
        ra, dec = float(r['ra_obj']), float(r['dec_obj'])
        if not (np.isfinite(ra) and np.isfinite(dec) and -90 <= dec <= 90):
            continue
        poly = 'POLYGON ICRS ' + ' '.join(str(r[f'{k}{i}']) for i in range(1, 5) for k in ('ra', 'dec'))
        rows.append({'obs_id': obs, 'detector': int(m['det']), 'collection': 'spherex_'+release[1],
                     'version': m['ver'], 'processing_date': m['pdate'], 'url': url,
                     'mjd_start': float(r['mjd_start']), 'mjd_end': float(r['mjd_end']),
                     'mjd': (float(r['mjd_start'])+float(r['mjd_end']))/2,
                     'exptime_s': float(r['exposure_time']), 's_region': poly,
                     'prediction': {'ra': ra, 'dec': dec, 'source': MOST, 'frame': 'J2000 (MOST)',
                         'observer': 'MOST/SPHEREx (NAIF -453)', 'uncertainty_arcsec': None,
                         'mjd': float(r['mjd_start']), 'time_basis': 'inicio de exposición (MOST)',
                         'requested_time_sampling_s': step_days*86400, 'refined': False},
                     'discovery': provenance})
    # Deterministic version choice. Keep distinct releases explicit, prefer DR1 counterpart.
    by_id = {}
    for r in rows:
        key = (r['obs_id'], r['detector'])
        rank = lambda x: (x['collection']=='spherex_dr1', int(x['version']), x['processing_date'])
        if key not in by_id or rank(r) > rank(by_id[key]):
            by_id[key] = r
    return {'identity': identity, 'start': a.isot, 'end': b.isot,
            'rows': sorted(by_id.values(), key=lambda x: (x['mjd'], x['detector'])),
            'provenance': provenance, 'excluded_products': excluded,
            'workspace_url': tab.meta.get('keywords',{}).get('output_url',{}).get('value')}


def published_predictions(url, *, ra_column='comet_ra', dec_column='comet_dec', refresh=False):
    """Optional reference adapter, independent of target name or detection algorithm."""
    raw, p = _request(url, refresh=refresh)
    tab = Table.read(io.BytesIO(raw), format='votable')
    out = {}
    for r in tab:
        out[(str(r['obs_id']), int(str(r['spherex_detector']).lstrip('D')))] = {
            'ra': float(r[ra_column]), 'dec': float(r[dec_column]), 'source': url,
            'frame': 'ICRS (tabla IRSA)', 'observer': 'predicción por exposición publicada por IRSA',
            'uncertainty_arcsec': None, 'refined': True,
            'mjd_start': float(r['t_min']), 'mjd_end': float(r['t_max']),
            'original_product': str(r['access_url']), 'provenance': p}
    return out


# Optional published references are data registration, never analysis branches.
REFERENCE_TABLES = {'1004083': solar_system.ATLAS_TABLE}


def attach_reference(discovery, refresh=False):
    url = REFERENCE_TABLES.get(str(discovery['identity']['spkid']))
    if url:
        predictions = published_predictions(url, refresh=refresh)
        for row in discovery['rows']:
            p = predictions.get((row['obs_id'], row['detector']))
            if p and abs(p['mjd_start']-row['mjd_start'])*86400 < 1:
                row['prediction'] = p
    return discovery


def track_position(tab, mjd):
    """Interpolate two OFFICIAL observer samples, never extrapolate or fill a gap.

    MOST's JD column is rounded to 1e-6 d; use the accompanying UTC date instead.
    Unit-vector interpolation handles RA wrapping and polar tracks.
    """
    required={'Date','RA_obs','Dec_obs','segment'}
    if not required <= set(tab.colnames) or len(tab)<2:
        raise solar_system.ServiceError('MOST no devolvió una trayectoria temporal utilizable.')
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    times=np.array([Time(datetime.strptime(str(x),'%Y-%b-%d %H:%M:%S.%f')).mjd for x in tab['Date']])
    if not np.all(np.diff(times)>0):
        raise solar_system.ServiceError('Efeméride MOST con tiempos no ordenados.')
    i=int(np.clip(np.searchsorted(times,mjd)-1,0,len(times)-2))
    gap=(times[i+1]-times[i])*86400
    if not times[i]<=mjd<=times[i+1] or gap>2 or tab['segment'][i]!=tab['segment'][i+1]:
        raise solar_system.ServiceError('La efeméride fina no cubre el instante de esta exposición.')
    coords=SkyCoord(np.asarray(tab['RA_obs'][i:i+2],float)*u.deg,
                    np.asarray(tab['Dec_obs'][i:i+2],float)*u.deg)
    frac=(mjd-times[i])/(times[i+1]-times[i])
    v=coords.cartesian.xyz.value @ np.array([1-frac,frac])
    pos=SkyCoord(x=v[0],y=v[1],z=v[2],representation_type='cartesian').spherical
    return {'ra':float(pos.lon.deg),'dec':float(pos.lat.deg),'mjd':float(mjd),
            'sample_gap_s':float(gap),'interpolation':'vector unitario entre muestras MOST ≤2 s'}


def refine_prediction(identity, row):
    if row['prediction'].get('refined'):
        return row
    # Reuse MOST's spacecraft ephemeris, not its match-at-exposure-start coordinates.
    # A finer ephem_step alone does NOT change the timestamp of the match table.
    for refresh in (False,True):
        out = discover(identity, Time(row['mjd_start']-120/86400, format='mjd'),
                       Time(row['mjd_end']+120/86400, format='mjd'), step_days=1/86400,refresh=refresh)
        url=out.get('workspace_url') or ''
        parsed=urlparse(url)
        if parsed.scheme!='https' or parsed.hostname!='irsa.ipac.caltech.edu' or not parsed.path.startswith('/workspace/'):
            raise solar_system.ServiceError('MOST no proporcionó una efeméride espacial verificable.')
        try:
            raw,provenance=_request(url.rstrip('/')+'/orbital_path.tbl',refresh=refresh)
            track=Table.read(raw.decode(),format='ascii.ipac')
            predicted=track_position(track,row['mjd'])
            break
        except (solar_system.ServiceError,ValueError):
            if refresh: raise
            # Workspace URLs expire; regenerate only this bounded metadata query.
    return {**row, 'prediction': {**row['prediction'], **predicted, 'refined': True,
             'observer':'MOST/SPHEREx (NAIF -453)',
             'time_basis':'punto medio de exposición UTC', 'source':provenance['url'],
             'requested_time_sampling_s':1.,'provenance':provenance,
             'discovery_provenance':out['provenance'],
             'limitation': 'Sin covarianza orbital publicada por MOST; interpolación temporal identificada.'}}


def estimate_bands(rows):
    """Only tiny calibration tables, no image download. Final wavelengths use FITS WCS."""
    tables = {}
    for r in rows:
        key = (r['detector'],r['collection'],r['version'],r['processing_date'])
        if key not in tables:
            tables[key] = wave_table_from_url(r['url'])
        t = tables[key]
        x,y = FootprintMap(r['s_region']).sky_to_pixel(r['prediction']['ra'],r['prediction']['dec'])
        lam,bw = bilinear_lookup(t['X'],t['Y'],t['VALUES'],x,y)
        r.update(lambda_um=float(lam), bandwidth_um=float(bw),
                 margin_px=float(min(x-.5,y-.5,2040.5-x,2040.5-y)))
    return rows


def compatible(a, b, limit=.25):
    return (all(a[k]==b[k] for k in ('detector','collection','version')) and
            np.isfinite(a['lambda_um']+b['lambda_um']) and
            abs(a['lambda_um']-b['lambda_um']) <= limit*min(a['bandwidth_um'],b['bandwidth_um']))


def groups(rows, low=1.0, high=1.5, max_frames=8):
    """Pairwise spectral compatibility, no mandatory one-day spacing or whole-FOV test."""
    eligible = [r for r in rows if low <= r.get('lambda_um',-1) <= high and r.get('margin_px',0)>0]
    seen, out = set(), []
    for seed in eligible:
        group = [seed]
        for r in sorted(eligible, key=lambda x: abs(x['lambda_um']-seed['lambda_um'])):
            if r is not seed and all(compatible(r,g) for g in group) and len(group)<max_frames:
                group.append(r)
        group.sort(key=lambda r:r['mjd'])
        key = tuple(r['url'] for r in group)
        if key not in seen:
            out.append(group); seen.add(key)
    return sorted(out, key=lambda g:(-len(g),-min(r['margin_px'] for r in g),g[0]['mjd']))


def stellar_context(row):
    """A single cached cone per exposure, not one request per drawn source."""
    from . import references
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    p=row['prediction']
    query=references.gaia_query(p['ra'],p['dec'],.1,500)
    blob,provenance=_request(references.GAIA_TAP,
        {'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'csv','QUERY':query})
    stars,truncated=references.parse_gaia(blob,500)
    target=SkyCoord(p['ra']*u.deg,p['dec']*u.deg)
    nearby=[]
    for star in stars:
        expected=references.expected_position(star,float(Time(row['mjd'],format='mjd').jyear))
        ra,dec=expected or (star['ra'],star['dec'])
        sep=target.separation(SkyCoord(ra*u.deg,dec*u.deg)).arcsec
        if sep<36:
            nearby.append({'source_id':star['source_id'],'separation_arcsec':float(sep),
                           'G':star['phot_g_mean_mag'],'proper_motion_available':expected is not None})
    return {'nearby':sorted(nearby,key=lambda x:x['separation_arcsec']), 'truncated':truncated,
            'provenance':provenance,'note':'Gaia DR3, movimiento angular propagado desde J2016.0; '
            'sin paralaje ni comparación fotométrica con infrarrojo. No excluye fuentes ausentes de Gaia.'}


def _separation_deg(a, b):
    from .geometry import separation_deg
    return float(separation_deg(a['prediction']['ra'], a['prediction']['dec'],
                                b['prediction']['ra'], b['prediction']['dec']))


def motion_groups(rows, context_deg=.25, max_frames=8, min_margin_px=12.):
    """Exposures suited to MEASURING a displacement, for any body and at any wavelength.

    Same detector; predicted positions far enough apart to be told from one stationary source
    (at least 20 arcsec) yet close enough for every exposure to contain the sky where the body
    was in the others (0.35 of the downloaded context), so the appear/disappear test and the
    registration with common stars are possible. Spectral compatibility is NOT required: a
    position is not a brightness. Predictions only choose which exposures to read.
    """
    limit = .35 * context_deg
    out, used = [], set()
    by_detector = {}
    for r in rows:
        if r.get('margin_px', 0) >= min_margin_px:
            by_detector.setdefault(r['detector'], []).append(r)
    for detector, members in by_detector.items():
        members.sort(key=lambda r: r['mjd'])
        for i, seed in enumerate(members):
            if seed['url'] in used:
                continue
            group = [seed] + [r for r in members[i+1:] if _separation_deg(seed, r) <= limit]
            if len(group) < 2 or _separation_deg(group[0], group[-1]) * 3600 < 20:
                continue
            if len(group) > max_frames:            # keep both ends of the time baseline
                head = max_frames // 2
                group = group[:head] + group[-(max_frames - head):]
            used.update(r['url'] for r in group)
            out.append(group)
    # Shorter wavelengths first: the PSF is sharper there, so positions are better defined and faint
    # neighbours blend less. Then more exposures and a longer displacement. Nothing is object-specific.
    return sorted(out, key=lambda g: (g[0]['detector'], -len(g), -_separation_deg(g[0], g[-1]), g[0]['mjd']))
