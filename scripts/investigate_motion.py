"""Reproducible «Buscar algo que se mueve» investigation on original SPHEREx images.

    python scripts/investigate_motion.py --object "Barnard's star" --detector 4 --name motion_barnard
    python scripts/investigate_motion.py --object "M101" --detector 2 --control --name motion_m101_control

Selects one detector and the longest baseline (first / middle / last season, a few images
each), downloads 12′ cutouts (cached, never modified), queries Gaia DR3 for stationary
references and writes results/<name>.json (never overwrites an existing report).
``--control`` investigates a stationary Gaia star of the field instead of the named
object (expected outcome: no motion).
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from skyclues import archive, config, motion, references  # noqa: E402
from skyclues.targets import resolve_name  # noqa: E402


def control_star(gaia, ra, dec, first_mjd):
    """Brightest isolated Gaia star near the centre with negligible proper motion."""
    refs = motion._gaia_references(gaia, ra, dec, (ra, dec + 1.0))   # no exclusion around the centre
    cands = [s for s in refs if math.hypot(s["pmra"], s["pmdec"]) < 20 and
             motion._sep(s["ra"], s["dec"], ra, dec) < 180 and s["phot_g_mean_mag"] > 12]
    if not cands:
        raise SystemExit("Sin estrella de control adecuada en el campo.")
    star = sorted(cands, key=lambda s: s["phot_g_mean_mag"])[0]
    jy = 2000 + (first_mjd - 51544.5) / 365.25
    return star, references.expected_position(star, jy)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--object", required=True)
    ap.add_argument("--detector", type=int, required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--per-season", type=int, default=motion.PER_SEASON)
    ap.add_argument("--max-seasons", type=int, default=motion.MAX_SEASONS)
    ap.add_argument("--control", action="store_true", help="measure a stationary Gaia star of the field")
    args = ap.parse_args()
    astro, warns = resolve_name(args.object)
    recs = archive.query_images(astro.ra_deg, astro.dec_deg)
    # Cutout centre: the catalogue track at the median archive date, fixed for every image.
    mid = sorted(r.mjd_mid for r in recs)[len(recs) // 2] if recs else None
    ra, dec = astro.position_at(mid) if (mid and astro.has_proper_motion) else (astro.ra_deg, astro.dec_deg)
    recs = archive.query_images(ra, dec)
    sel = motion.select_epochs(recs, ra, dec, args.detector, per_season=args.per_season, max_seasons=args.max_seasons)
    print(f"{astro.name}: {len(recs)} imágenes; D{args.detector}: {sel['candidates']} candidatas, "
          f"{sel['seasons_available']} temporadas {sel['season_dates']}; seleccionadas {len(sel['selected'])}")
    frames = motion.fetch_frames(sel, ra, dec)
    gaia = references.fetch_gaia(ra, dec, sel["field_deg"])
    first_mjd = min(f.image.meta["MJD-AVG"] for f in frames)
    if args.control:
        star, source = control_star(gaia, ra, dec, first_mjd)
        label = (f"Control estacionario: Gaia DR3 {star['source_id']} (G {star['phot_g_mean_mag']:.2f}, "
                 f"μ {math.hypot(star['pmra'], star['pmdec']):.1f} mas/año) en el campo de {astro.name}")
        used_astro = None
    else:
        # Where the object is expected in the first image: this only defines the 20″ search circle;
        # the fit and the decision never use the prediction.
        source = astro.position_at(first_mjd) if astro.has_proper_motion else (ra, dec)
        label, used_astro = astro.name, astro
    inv = motion.investigate(frames, source, gaia=gaia, astrometry=used_astro, source_label=label)
    out = motion.to_jsonable(inv)
    out.update(created_utc=datetime.now(timezone.utc).isoformat(), object=args.object, astrometry=astro.to_dict(),
               astrometry_warnings=warns, selection={k: v for k, v in sel.items() if k != "selected"},
               cutout_centre={"ra": ra, "dec": dec}, control_mode=args.control,
               files=[{"file": Path(f.path).name, "sha256": f.sha256, "cutout_url": f.cutout_url,
                       "collection": f.record.get("collection"), "obs_id": f.record.get("obs_id")} for f in frames])
    path = config.RESULTS_DIR / f"{args.name}.json"
    if path.exists():
        path = config.RESULTS_DIR / f"{args.name}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Informe: {path}")
    print(f"RESULTADO: {out['outcome']} — {out['outcome_label']}")
    for r in out["reasons"]:
        print("  ·", r)
    for s in out.get("seasons", []):
        print(f"  temporada {s['date_utc']}: n={s['n_images']} detección={s['significance']:.1f}σ "
              f"ξ={s['xi']:.2f}±{s['err_xi']:.2f}″ η={s['eta']:.2f}±{s['err_eta']:.2f}″ "
              f"(ajuste {s['err_fit'][0]:.2f}/{s['err_fit'][1]:.2f}, registro {s['err_registration'][0]:.2f}/"
              f"{s['err_registration'][1]:.2f}, χ²int {s['internal_chi2_red'] or float('nan'):.2f} con "
              f"{s['n_single_fits']}){' SAT' if s['saturated_core'] else ''}{' CONF' if s['confusion'] else ''}")
    d = out.get("displacement")
    if d:
        print(f"  Δ = ({d['dxi']:.2f}, {d['deta']:.2f})″ ± ({d['err_dxi_calibrated']:.2f}, "
              f"{d['err_deta_calibrated']:.2f}) en {d['delta_t_days']:.0f} d · {d['significance_calibrated']:.1f}σ")
    c = out.get("control") or {}
    print(f"  control: {c.get('n')} estrellas, factor {c.get('calibration_factor')}, "
          f"máx {c.get('max_significance_calibrated')}")
    if out.get("catalogue_comparison"):
        cc = out["catalogue_comparison"]
        print(f"  catálogo: Δ previsto ({cc['predicted_dxi']:.2f}, {cc['predicted_deta']:.2f})″ · "
              f"diferencia {cc['difference_sigma']:.1f}σ")
    for im in out["images"]:
        print(f"   {im['date_utc'][:10]} {im['obs_id']:<20} λ={im['lambda_um'] or 0:.3f} S/N={im.get('snr') or 0:6.1f} "
              f"refs={im['n_refs']:2d} {'✔' if im['usable'] else '✖'} {'; '.join(im['warnings'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
