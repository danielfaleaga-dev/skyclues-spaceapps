"""Compact verified aliases + bounded SIMBAD identifier-prefix search."""
import json, re, unicodedata
import requests
from . import config
from .astrometry import Astrometry, SIMBAD_TAP_URLS
from .targets import resolve_name

INDEX = json.loads((config.ROOT / "data/popular_objects.json").read_text(encoding="utf8"))["objects"]

def normalize(text):
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).casefold()
    return re.sub(r"\s+", " ", re.sub(r"\b(m|ngc|ic|hd|hip)\s*(?=\d)", r"\1 ", text)).strip()

def validate_name(text):
    if any(ord(c)<32 for c in text):raise ValueError("Caracter de control invalido")
    text = text.strip()
    if not 1 <= len(text) <= 100 or any(ord(c)<32 for c in text) or any(c in text for c in "%_\\;<>"):
        raise ValueError("Nombre invalido: 1-100 caracteres, sin comodines SQL ni controles.")
    return text

def local_suggestions(text):
    q=normalize(text)
    if not q:return []
    return [x for x in INDEX if any(q in normalize(a) for a in [x["id"],*x["aliases"]])][:8]

def resolve(text):
    text=validate_name(text)
    text = canonical_name(text)
    if normalize(text) == 'm 102':
        raise ValueError('M102 tiene una identificación histórica ambigua: seleccione NGC 5866 o M101 explícitamente.')
    exact=[x for x in INDEX if normalize(text) in [normalize(a) for a in [x['id'],*x['aliases']]]]
    if len(exact)==1:
        item=exact[0];a=Astrometry.from_dict(item['astrometry'])
        return a,a.warnings(),item['extended']
    a,w=resolve_name(text)
    return a,w,False


def canonical_name(text):
    """Normalize catalogue notation without restricting resolution to the small suggestion index."""
    text = re.sub(r'^messier\s*', 'M ', text.strip(), flags=re.I)
    text = re.sub(r'^(M|NGC|IC)\s*0*(\d+)', lambda m: m[1].upper()+' '+str(int(m[2])), text, flags=re.I)
    if re.fullmatch(r'M \d+', text) and not 1 <= int(text[2:]) <= 110:
        raise ValueError('Los identificadores Messier van de M1 a M110.')
    return text

def remote_suggestions(text):
    text=validate_name(text)
    if len(text)<3:return [],"Escriba al menos 3 caracteres para SIMBAD."
    # Explicit aliases are not guessed; remote results are always user-selectable.
    prefix=re.sub(r"^([a-z]+) (?=\d)", lambda m:m.group(1).upper()+" ", normalize(text))
    prefix=re.sub(r'^gaia\s+dr([123])\s*',lambda m:'Gaia DR'+m.group(1)+' ',prefix,flags=re.I)
    prefix=re.sub(r'^2mass\s*','2MASS ',prefix,flags=re.I)
    prefix=re.sub(r'^wise(a?)\s*',lambda m:'WISE'+m.group(1).upper()+' ',prefix,flags=re.I)
    query=("SELECT TOP 18 main_id,otype,id FROM ident JOIN basic ON ident.oidref=basic.oid "
           "WHERE ident.id LIKE '"+prefix.replace("'","''")+"%'")
    errors=[]
    for base in reversed(SIMBAD_TAP_URLS):  # Harvard operational; Strasbourg returned 404 in verification
        try:
            with requests.get(base+'/sync',params={'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'json','QUERY':query},
                              timeout=(4,6),stream=True) as r:
                r.raise_for_status();raw=b''
                for part in r.iter_content(32768):
                    raw+=part
                    if len(raw)>1024*1024:raise ValueError('Respuesta demasiado grande')
            j=json.loads(raw);names=[x['name'] for x in j['metadata']];out={}
            for row in j['data'][:18]:
                d=dict(zip(names,row));out.setdefault(d['main_id'],{'id':d['main_id'],'type':d['otype'],'aliases':[],'source':base})['aliases'].append(d['id'])
            return list(out.values())[:8],base
        except (requests.RequestException,ValueError,KeyError,TypeError) as e:errors.append(type(e).__name__)
    return [],"Sugerencias remotas no disponibles; indice local y busqueda por nombre completo disponibles. " + '/'.join(errors)
