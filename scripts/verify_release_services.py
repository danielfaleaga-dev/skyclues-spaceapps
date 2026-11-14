"""Bounded official-service evidence, no scientific image downloads."""
import requests,json,io,sys
from pathlib import Path
from datetime import datetime,timezone
from astropy.table import Table
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from skyclues.astrometry import SIMBAD_TAP_URLS
ROOT=Path(__file__).resolve().parents[1]
NAMES=['M 31','M 101','GJ 699','WISE J085510.83-071442.5','eps Ind','eps Ind B','M 42','M 45','HD 209458','R Dra','RW Aur']
def check(c):
    try:
        r=requests.get('https://irsa.ipac.caltech.edu/SIA',params={'POS':'CIRCLE 210.802429 54.34875 0.000278','COLLECTION':c,'MAXREC':2},timeout=(8,25))
        r.raise_for_status();t=Table.read(io.BytesIO(r.content),format='votable',use_names_over_ids=True)
        rows=[{k:str(row[k]) for k in t.colnames} for row in t[:2]]
        return {'collection':c,'status':r.status_code,'count':len(t),'sample':rows}
    except Exception as e:return {'collection':c,'error':str(e)[:200]}
def main():
    out={'checked_utc':datetime.now(timezone.utc).isoformat()}
    with ThreadPoolExecutor(max_workers=2) as pool:out['collections']=list(pool.map(check,['spherex_dr1','spherex_qr3','spherex_dr1_deep','spherex_qr3_deep']))
    q="SELECT main_id,otype,ra,dec,pmra,pmdec,plx_value,rvz_radvel,coo_bibcode,ident.id FROM basic JOIN ident ON ident.oidref=basic.oid WHERE ident.id IN ("+','.join("'"+n+"'" for n in NAMES)+")"
    out['simbad']=[]
    for base in SIMBAD_TAP_URLS:
        try:
            r=requests.get(base+'/sync',params={'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'json','QUERY':q},timeout=(8,15));r.raise_for_status()
            data=r.json();out['simbad'].append({'endpoint':base,'response':data})
        except Exception as e:out['simbad'].append({'endpoint':base,'error':str(e)[:200]})
    (ROOT/'results/release_services.json').write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(out,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
