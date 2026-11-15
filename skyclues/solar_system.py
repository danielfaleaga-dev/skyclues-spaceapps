"""Bounded JPL identity/ephemeris requests; never a SPHEREx detection or stellar astrometry."""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone

import requests
from astropy.time import Time

LOOKUP = "https://ssd.jpl.nasa.gov/api/horizons_lookup.api"
HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
ATLAS_DOC = "https://irsa.ipac.caltech.edu/data/SPHEREx/docs/comet3iatlas/index.html"
ATLAS_TABLE = ATLAS_DOC.rsplit('/', 1)[0] + "/obscore_3I_Atlas.vot"
ALIASES = {"marte": "Mars", "jupiter": "Jupiter", "mercurio": "Mercury", "tierra": "Earth",
           "saturno": "Saturn", "urano": "Uranus", "neptuno": "Neptune", "pluton": "Pluto",
           "luna": "Moon", "sol": "Sun", "titan": "Titan", "3i/atlas": "3I",
           "c/2025 n1 (atlas)": "C/2025 N1", "1i/oumuamua": "1I", "2i/borisov": "2I"}


class ServiceError(RuntimeError):
    pass


def read_bytes(url, params=None, limit=2 * 1024 * 1024):
    try:
        with requests.get(url, params=params, timeout=(4, 15), stream=True) as r:
            r.raise_for_status()
            parts, size = [], 0
            for p in r.iter_content(32768):
                size += len(p)
                if size > limit:
                    raise ServiceError("Respuesta demasiado grande; acote la búsqueda.")
                parts.append(p)
            return b''.join(parts)
    except requests.RequestException as e:
        raise ServiceError("Servicio astronómico no disponible; vuelva a intentarlo.") from e


def request_json(url, params):
    try:
        j = json.loads(read_bytes(url, params))
        if j.get('error'):
            raise ServiceError(str(j['error'])[:250])
        return j
    except (ValueError, TypeError) as e:
        raise ServiceError("Respuesta astronómica no válida.") from e


def lookup(text):
    from .object_search import normalize, validate_name
    q = ALIASES.get(normalize(text), validate_name(text))
    j = request_json(LOOKUP, {'sstr': q, 'format': 'json'})
    out = []
    for x in j.get('result', []):
        if x['type'] in ('spacecraft', 'barycenter'):
            continue
        out.append({'id': 'JPL:' + x['spkid'], 'name': x['name'], 'type': x['type'],
                    'spkid': x['spkid'], 'pdes': x.get('pdes'), 'aliases': x.get('alias') or [], 'source': LOOKUP})
    # Exact name/designation first, but don't silently choose among genuinely ambiguous matches.
    out.sort(key=lambda x: normalize(q) not in [normalize(v) for v in
                  [x['name'], x.get('pdes') or '', *x['aliases']]])
    return out[:12]


def ephemeris(identity, utc):
    """Astrometric ICRF RA/Dec, light-time corrected, geocentre, single UTC instant."""
    if not re.fullmatch(r'\d{1,12}', identity['spkid']):
        raise ValueError("Identificador JPL inválido")
    try:
        t = Time(utc, scale='utc')
        if not t.isscalar or not 1900 <= t.datetime.year <= 2100:
            raise ValueError()
    except Exception as e:
        raise ValueError("Fecha UTC inválida (1900–2100, AAAA-MM-DD HH:MM:SS).") from e
    command = identity['spkid']
    if 'asteroid' in identity['type'] or 'comet' in identity['type']:
        command = 'DES=' + identity['spkid'] + ';'
    if 'comet' in identity['type'] and identity.get('pdes'):
        if not re.fullmatch(r'[A-Za-z0-9/ -]+', identity['pdes']):
            raise ValueError('Designación cometaria inválida')
        command = 'DES=' + identity['pdes'] + ';CAP'
    params = {'format': 'json', 'COMMAND': "'" + command + "'", 'OBJ_DATA': "'NO'",
              'MAKE_EPHEM': "'YES'", 'EPHEM_TYPE': "'OBSERVER'", 'CENTER': "'500@399'",
              'TLIST': "'" + str(t.jd) + "'", 'QUANTITIES': "'1'", 'ANG_FORMAT': "'DEG'",
              'CSV_FORMAT': "'YES'", 'REF_SYSTEM': "'ICRF'", 'EXTRA_PREC': "'YES'"}
    j = request_json(HORIZONS, params)
    raw = j.get('result', '')
    try:
        lines = raw.split('$$SOE')[1].split('$$EOE')[0].strip().splitlines()
        if len(lines) != 1:
            raise ValueError()
        row = next(csv.reader(lines))
        from .targets import validate_coordinates
        ra, dec = validate_coordinates(float(row[3]), float(row[4]))
    except (ValueError, IndexError) as e:
        raise ServiceError("Horizons no devolvió una efeméride única para esta fecha.") from e
    return {'identity': identity, 'ra': ra, 'dec': dec, 'utc': t.isot, 'observer': '500@399',
            'observer_label': 'geocentro terrestre', 'frame': 'ICRF astrométrico', 'source': HORIZONS,
            'retrieved_utc': datetime.now(timezone.utc).isoformat(), 'kind': 'ephemeris', 'command': command}


def atlas_observations():
    """Official small metadata table only. No image download or scientific engine changes."""
    from astropy.table import Table
    t = Table.read(io.BytesIO(read_bytes(ATLAS_TABLE)), format='votable')
    required = {'comet_ra', 'comet_dec', 'access_url', 't_min'}
    if not required <= set(t.colnames):
        raise ServiceError("La tabla oficial de 3I/ATLAS cambió de formato.")
    return t
