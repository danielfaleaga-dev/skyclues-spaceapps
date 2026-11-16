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
    if any(ord(c)<32 for c in text):raise ValueError("Invalid control character")
    text = text.strip()
    if not 1 <= len(text) <= 100 or any(ord(c)<32 for c in text) or any(c in text for c in "%_\\;<>"):
        raise ValueError("Invalid name: 1-100 characters, no SQL wildcards or control characters.")
    return text

def local_suggestions(text):
    q=normalize(text)
    if not q:return []
    return [x for x in INDEX if any(q in normalize(a) for a in [x["id"],*x["aliases"]])][:8]

def resolve(text):
    text=validate_name(text)
    text = canonical_name(text)
    if normalize(text) == 'm 102':
        raise ValueError('M102 has an ambiguous historical identification: select NGC 5866 or M101 explicitly.')
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
        raise ValueError('Messier identifiers run from M1 to M110.')
    return text

def catalogue_prefix(text):
    """A catalogue prefix is useful even before the general three-character threshold."""
    q = re.sub(r'^messier\b', 'm', normalize(text))
    return re.fullmatch(r'(m|ngc|ic|hd|hip)\s*(\d*)', q)


def can_suggest(text):
    return bool(catalogue_prefix(text)) or len(text.strip()) >= 3


def suggestion_patterns(text):
    # SIMBAD identifiers are case-sensitive and have padded numbers, e.g. 'NGC     8'.
    # Match their documented catalogue notation without downloading an entire catalogue.
    cat = catalogue_prefix(text)
    if cat:
        prefix, number = cat.groups()
        prefix = prefix.upper()
        if not number:
            return [prefix + ' %']
        number = str(int(number))
        return [prefix + ' ' * n + number + '%' for n in range(1, 7)]
    prefix=normalize(text)
    prefix=re.sub(r'^gaia\s+dr([123])\s*',lambda m:'Gaia DR'+m.group(1)+' ',prefix,flags=re.I)
    prefix=re.sub(r'^2mass\s*','2MASS ',prefix,flags=re.I)
    prefix=re.sub(r'^wise(a?)\s*',lambda m:'WISE'+m.group(1).upper()+' ',prefix,flags=re.I)
    return list(dict.fromkeys(p + '%' for p in [prefix, prefix.upper(), prefix.title(), 'NAME ' + prefix.title()]))


def remote_suggestions(text):
    text=validate_name(text)
    if not can_suggest(text):return [],"Type at least 3 characters or a catalogue."
    where = ' OR '.join("ident.id LIKE '" + p.replace("'", "''") + "'" for p in suggestion_patterns(text))
    cat = catalogue_prefix(text)
    exact_where = None
    if cat and cat[2]:
        ids = [cat[1].upper() + ' ' * n + str(int(cat[2])) for n in range(1, 7)]
        exact_where = 'ident.id IN (' + ','.join("'" + x + "'" for x in ids) + ')'
    # No remote ORDER BY: prefix-index scans stay fast even in the large ident table.
    select = "SELECT TOP 24 main_id,otype,id FROM ident JOIN basic ON ident.oidref=basic.oid WHERE "
    errors=[]
    for base in reversed(SIMBAD_TAP_URLS):  # Harvard operational; Strasbourg returned 404 in verification
        try:
            out={}
            # An exact identifier must not disappear behind the first page of prefix matches.
            for clause in ([exact_where, where] if exact_where else [where]):
                with requests.get(base+'/sync',params={'REQUEST':'doQuery','LANG':'ADQL','FORMAT':'json','QUERY':select + clause},
                                  timeout=(4,6),stream=True) as r:
                    r.raise_for_status();raw=b''
                    for part in r.iter_content(32768):
                        raw+=part
                        if len(raw)>1024*1024:raise ValueError('Response too large')
                j=json.loads(raw);names=[x['name'] for x in j['metadata']]
                for row in j['data'][:24]:
                    d=dict(zip(names,row))
                    # NGC 869 member stars are not additional entries of the NGC catalogue.
                    if cat and not re.fullmatch(cat[1].upper() + r'\s+\d+[A-Za-z]?', d['id']):
                        continue
                    out.setdefault(d['main_id'],{'id':d['main_id'], 'label':' '.join(d['id'].split()),
                        'type':d['otype'],'aliases':[d['main_id']],'source':base})['aliases'].append(d['id'])
            rows = list(out.values())
            if cat:
                rows.sort(key=lambda x: tuple(int(v) if v.isdigit() else v for v in re.split(r'(\d+)', x['label'])))
            return rows[:12],base
        except (requests.RequestException,ValueError,KeyError,TypeError) as e:errors.append(type(e).__name__)
    return [],"Remote suggestions not available; local index and full-name search available. " + '/'.join(errors)
