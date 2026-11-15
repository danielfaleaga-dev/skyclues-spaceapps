"""Non-blocking, bounded catalogue jobs shared by Atlas sessions. No Streamlit in workers."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic
import json
import re

import requests

from . import references
from .astrometry import SIMBAD_TAP_URLS


class Jobs:
    """Poll without waiting; share in-flight requests and successful TTL results.

    Failures stay visible until explicit retry. At most four network jobs run/queue,
    and finished entries are bounded. A caller only receives its exact key's result.
    """
    def __init__(self, fetch, ttl=43200, capacity=64, workers=3):
        self.fetch, self.ttl, self.capacity = fetch, ttl, capacity
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='gaia-atlas')
        self.lock, self.entries = Lock(), OrderedDict()

    def poll(self, key, retry=False):
        with self.lock:
            item = self.entries.get(key)
            if item and item[0].done() and (retry or monotonic() - item[1] > self.ttl):
                del self.entries[key]
                item = None
            if item is None:
                if sum(not f.done() for f, _ in self.entries.values()) >= 4:
                    return {'state': 'loading'}
                item = (self.pool.submit(self.fetch, *key), monotonic())
                self.entries[key] = item
            self.entries.move_to_end(key)
            for old in list(self.entries):
                if len(self.entries) <= self.capacity:
                    break
                if old != key and self.entries[old][0].done():
                    del self.entries[old]
            future = item[0]
            if not future.done():
                return {'state': 'loading'}
            try:
                return {'state': 'ready', 'result': future.result()}
            except Exception:
                return {'state': 'error', 'message': 'Gaia DR3 no disponible. Puede reintentar.'}


def verified_alias(source_id):
    """One optional exact-identifier SIMBAD match for the selected source, never a positional guess."""
    if not re.fullmatch(r'[0-9]{1,19}', source_id):
        raise ValueError('source_id inválido')
    query = ("SELECT TOP 2 basic.main_id FROM basic JOIN ident ON ident.oidref=basic.oid "
             f"WHERE ident.id = 'Gaia DR3 {source_id}'")
    base = SIMBAD_TAP_URLS[-1]
    with requests.get(base+'/sync', params={'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'json','QUERY':query},
                      timeout=(3, 5), stream=True) as r:
        r.raise_for_status()
        raw = bytearray()
        for chunk in r.iter_content(8192):
            raw.extend(chunk)
            if len(raw) > 32768:
                raise ValueError('Respuesta SIMBAD demasiado grande')
    data = json.loads(raw)['data']
    if len(data) == 1 and data[0][0] and str(data[0][0]).strip() != f'Gaia DR3 {source_id}':
        return {'name': str(data[0][0]).strip(), 'source': base, 'identifier': f'Gaia DR3 {source_id}'}
    return None


CATALOGUE = Jobs(references.fetch_gaia)
ALIASES = Jobs(verified_alias, ttl=86400, capacity=128, workers=1)
