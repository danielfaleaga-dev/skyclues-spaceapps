"""Explicit bounded live checks. Records successes AND failures; downloads metadata only."""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skyclues import object_search, solar_system

out = {'utc': datetime.now(timezone.utc).isoformat(), 'catalogues': {}, 'solar': {}}
path = Path('results/continuity_services.json')


def save():
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf8')


for name in ['M1', 'Messier 13', 'M31', 'M42', 'M57', 'M101', 'M110', 'M102', 'NGC224',
             'NGC 891', 'NGC7000', 'IC1396', 'skyCluesThisObjectDoesNotExist824921']:
    try:
        a, w, ext = object_search.resolve(name)
        out['catalogues'][name] = {'astrometry': a.to_dict(), 'warnings': w}
    except Exception as e:
        out['catalogues'][name] = {'error': str(e)}
    save()
for name in ['Marte', 'Júpiter', 'Europa', 'Titán', 'Ceres', 'Vesta', 'Plutón', 'Bennu', 'Apophis',
             'Halley', '67P', '3I/ATLAS', 'C/2025 N1 (ATLAS)']:
    try:
        rows = solar_system.lookup(name)
        out['solar'][name] = {'identities': rows, 'position': solar_system.ephemeris(rows[0], '2026-11-14T12:00:00')}
    except Exception as e:
        out['solar'][name] = {'error': str(e)}
    save()
try:
    t = solar_system.atlas_observations()
    out['3I_table'] = {'count': len(t), 'columns': t.colnames, 'mjd_min': float(min(t['t_min'])),
                       'mjd_max': float(max(t['t_max'])), 'collections': sorted(set(map(str, t['obs_collection'])))}
except Exception as e:
    out['3I_table'] = {'error': str(e)}
save()
print('Recorded', path)
