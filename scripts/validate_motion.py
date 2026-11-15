"""REAL-FITS validation of the measured motion of known moving bodies (universal detector).

Run with the .venv Python from the repository root:

    python scripts/validate_motion.py

For each case the exposures are chosen by ``moving_sources.motion_groups`` (same detector, hours
apart, common sky) from the saved MOST discovery, the original cutouts are fetched (or read from the
verbatim cache), and ``non_sidereal.assess`` decides. Nothing here is specific to one object.

Negative controls on the SAME real images: the predictions are displaced to empty sky (the detector
must then find nothing that moves), and a stationary field (M101) is run through the same code.
"""
import json
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from astropy.time import Time

from skyclues import moving_sources as s, moving_view as v, non_sidereal as n, render

ROOT = Path(__file__).resolve().parents[1] / 'results' / 'moving'
FOV = .1


def discovery(name, identity=None, start=None, end=None):
    """Saved MOST discovery; queried (metadata only) and saved when it does not exist yet."""
    path = ROOT / (name + '_discovery.json')
    if path.exists():
        d = json.loads(path.read_text(encoding='utf-8'))
    else:
        d = s.discover(identity, start, end)
        try:
            s.attach_reference(d)
        except (RuntimeError, ValueError, OSError) as e:
            d['reference_warning'] = str(e)
        path.write_text(json.dumps(d, indent=1, default=str), encoding='utf-8')
    s.estimate_bands(d['rows'])
    return d


def pick(groups, detector=None, first=None):
    for g in groups:
        if (detector is None or g[0]['detector'] == detector) and (first is None or g[0]['obs_id'].endswith(first)):
            return g
    return None


def summary(report):
    m = report['motion']
    out = {'status': report['status'], 'observed_motion': report['observed_motion'], 'reason': m['reason'],
           'positions_measured': sum(p['measured'] for p in m['positions']), 'frames': len(report['frames'])}
    for k in ('displacement_arcsec', 'error_arcsec', 'significance', 'interval_hours', 'rate_arcsec_per_hour',
              'position_angle_deg', 'control_stars', 'control_radius_arcsec'):
        if k in m:
            out[k] = round(float(m[k]), 3)
    if 'catalogue_comparison' in m:
        out['measured_minus_predicted_arcsec'] = round(m['catalogue_comparison']['difference_arcsec'], 2)
    out['snr'] = [None if not p['measured'] else round(p['snr'], 1) for p in m['positions']]
    out['offset_from_prediction_arcsec'] = [None if not p['measured'] else
                                            [round(x, 2) for x in p['offset_from_prediction_arcsec']]
                                            for p in m['positions']]
    out['outlier_pixels_in_core'] = [p.get('outlier_pixels_in_core') for p in m['positions']]
    return out


def run(label, d, rows, figures=True):
    frames, failures = n.fetch_frames(d['identity'], rows, FOV, lambda msg: None)
    report = n.assess(frames, FOV)
    report['failures'] = failures
    report['identity'] = d['identity']
    report['selection'] = {'rule': 'moving_sources.motion_groups', 'obs_ids': [r['obs_id'] for r in rows],
                           'detector': rows[0]['detector']}
    (ROOT / (label + '.json')).write_text(json.dumps(report, indent=1, default=str), encoding='utf-8')
    if figures and frames:
        arrays, _, _ = n.aligned(frames, FOV, False)
        norm = render.shared_norm(arrays, lo=5, hi=99)
        p0 = frames[0].prediction
        pair = report['motion'].get('pair') or {'first': 0, 'second': len(frames) - 1}
        for tag, i in (('first', pair['first']), ('second', pair['second'])):
            png = v.frame_png(frames[i], FOV, norm, n.track_centre(frames), report['motion']['positions'][i])
            (ROOT / f'{label}_{tag}.png').write_bytes(png)
    out = {'label': label, 'object': d['identity'].get('name'), 'detector': rows[0]['detector'],
           'first_utc': Time(rows[0]['mjd'], format='mjd').isot[:19], 'last_utc': Time(rows[-1]['mjd'], format='mjd').isot[:19],
           'lambda_um': [round(min(r['lambda_um'] for r in rows), 3), round(max(r['lambda_um'] for r in rows), 3)],
           **summary(report)}
    return out, frames


def displaced_control(label, d, frames, east_arcsec, north_arcsec):
    """Same real images, predictions moved to nearby sky where the body is not."""
    moved = []
    for f in frames:
        row = deepcopy(f.row)
        p = row['prediction']
        p['dec'] += north_arcsec / 3600
        p['ra'] += east_arcsec / 3600 / np.cos(np.radians(p['dec']))
        p['source'] = 'CONTROL NEGATIVO: predicción desplazada a propósito'
        moved.append(n.MovingFrame(row, f.image, f.path, f.cutout_url, f.sha256))
    report = n.assess(moved, FOV)
    return {'label': label, 'offset_arcsec': [east_arcsec, north_arcsec], **summary(report)}


def stationary_control():
    from skyclues import archive, sequence
    seq = sequence.load_sequence(ROOT.parent / 'sequence_m101.json')
    frames = []
    for f in seq.frames:
        row = {'obs_id': f.obs_id, 'detector': f.detector, 'collection': f.record['collection'],
               'version': archive._FILE_RE.search(f.cutout_url)['ver'], 'mjd': f.mjd,
               'lambda_um': f.lambda_target_um, 'bandwidth_um': f.bandwidth_target_um,
               'prediction': {'ra': seq.ra, 'dec': seq.dec, 'refined': True,
                              'source': 'CONTROL ESTACIONARIO M101; sin efeméride'}}
        frames.append(n.MovingFrame(row, f.image, f.path, f.cutout_url, f.sha256))
    report = n.assess(frames, seq.field_deg)
    report['validation_role'] = 'Campo estacionario auténtico; no es un objeto móvil simulado'
    (ROOT / 'stationary_m101.json').write_text(json.dumps(report, indent=1, default=str), encoding='utf-8')
    return {'label': 'stationary_m101', **summary(report)}


CASES = [  # label, discovery, detector, last characters of the first exposure id
    ('atlas_aug_motion_d1', 'atlas_aug', 1, '0343_1'),
    ('atlas_aug_motion_co2', 'atlas_aug', 5, '0189_1'),
    ('atlas_aug_motion_d2', 'atlas_aug', 2, '0189_1'),
    ('atlas_dec_motion_d2', 'atlas_dec', 2, '0685_1'),
    ('atlas_dec_motion_co2', 'atlas_dec', 5, '0685_1'),
    ('pluto_motion', 'pluto_year', None, None),
    ('pluto_motion_d3', 'pluto_year', 3, None),
    ('juno_motion', 'juno_year', None, None),
    ('vesta_motion', 'vesta_year', None, None),
    ('vesta_motion_d2', 'vesta_year', 2, None),
]
EXTRA_DISCOVERIES = {'vesta_year': ('vesta', '2025-04-10', '2026-04-10')}
#: Bodies found through the same JPL lookup the application's search box uses (no stored coordinates).
LOOKUPS = {'juno_year': ('Juno', '20000003', '2025-04-10', '2026-04-10')}


if __name__ == '__main__':
    only = set(sys.argv[1:])
    results = []
    for label, name, detector, first in CASES:
        if only and label not in only:
            continue
        try:
            if name in LOOKUPS and not (ROOT / (name + '_discovery.json')).exists():
                from skyclues import solar_system
                text, spkid, start, end = LOOKUPS[name]
                identity = next(x for x in solar_system.lookup(text) if x['spkid'] == spkid)
                d = discovery(name, identity, start, end)
            elif name in EXTRA_DISCOVERIES and not (ROOT / (name + '_discovery.json')).exists():
                base, start, end = EXTRA_DISCOVERIES[name]
                identity = json.loads((ROOT / (base + '_discovery.json')).read_text(encoding='utf-8'))['identity']
                d = discovery(name, identity, start, end)
            else:
                d = discovery(name)
            groups = s.motion_groups(d['rows'])
            rows = pick(groups, detector, first)
            if rows is None:
                results.append({'label': label, 'status': 'unevaluable', 'exposures': len(d['rows']),
                                'reason': 'No hay exposiciones del mismo detector lo bastante próximas para medir un desplazamiento.'})
                print(results[-1], flush=True)
                continue
            out, frames = run(label, d, rows)
            out['motion_sets_available'] = len(groups)
            results.append(out)
            print(json.dumps(out, ensure_ascii=False), flush=True)
            if label in ('atlas_aug_motion_d1', 'atlas_aug_motion_co2'):
                for k, (e, nn) in enumerate([(0, 90), (-120, 0), (75, -75)]):
                    c = displaced_control(f'{label}_displaced_{k + 1}', d, frames, e, nn)
                    results.append(c)
                    print(json.dumps(c, ensure_ascii=False), flush=True)
        except Exception as e:  # noqa: BLE001 - a failed case is reported, never hidden
            results.append({'label': label, 'error': f'{type(e).__name__}: {e}'})
            print(results[-1], flush=True)
    if not only or 'stationary_m101' in only:
        results.append(stationary_control())
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    if not only:
        (ROOT / 'motion_validation_summary.json').write_text(json.dumps(results, indent=1, ensure_ascii=False),
                                                             encoding='utf-8')
