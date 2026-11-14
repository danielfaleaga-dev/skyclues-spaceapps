"""Small app integration points: share link and archive-discovery status.

Object search, coordinates and the Atlas live together in ``region_ui`` (one region selector).
"""
import streamlit as st

from . import navigation, releases  # noqa: F401 - ``releases`` is configured from app.py

SHARE = st.components.v2.component(
    'sky_share_region',
    html='<label for="sc-share">Enlace de esta región</label><div class="row"><input id="sc-share" readonly '
         'aria-label="Enlace compartible"><button type="button">Copiar</button></div><span role="status"></span>',
    css='label{display:block;font-size:11.5px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:#5b6470;'
        'margin-bottom:6px}.row{display:flex;gap:8px}input{flex:1;min-width:0;padding:8px 10px;box-sizing:border-box;'
        'border:1px solid #e3e6ea;border-radius:6px;font:13px "IBM Plex Mono",ui-monospace,Consolas,monospace;color:#14171c}'
        'button{padding:7px 14px;border:1px solid #14171c;border-radius:6px;background:#fff;color:#14171c;font:inherit;'
        'cursor:pointer;transition:background-color .14s ease,color .14s ease}button:hover{background:#14171c;color:#fff}'
        'button:focus-visible,input:focus-visible{outline:2px solid #14171c;outline-offset:2px}'
        'span{display:block;font-size:12.5px;color:#5b6470;min-height:1.2em;margin-top:4px}',
    js="""export default function(c){const p=c.parentElement,u=new URL(window.location.href);u.search=c.data.query;u.hash='';const i=p.querySelector('input');i.value=u.href;p.querySelector('button').onclick=async()=>{i.select();try{await navigator.clipboard.writeText(i.value);p.querySelector('span').textContent='Copiado'}catch(e){p.querySelector('span').textContent='Seleccione el enlace y copie con Ctrl+C'}}}""")


def share(ra, dec, fov, explorer='temporal', canal=63):
    with st.expander('Compartir esta región'):
        SHARE(data={'query': navigation.region_query(ra, dec, fov, explorer, canal)}, key='share_region')
        st.caption('El enlace conserva el centro y el campo (en grados), no una detección ni todos los datos de la '
                   'sesión. No vuelve a resolver nombres; los objetos móviles quedan en estas coordenadas fijas.')


def discovery(report):
    d = report.get('discovery') or {}
    if d.get('queried_utc'):
        st.caption(f"Observaciones: {d['origin']} · verificadas en IRSA {d['queried_utc']} · {d['selected_count']} "
                   f"productos ({d['raw_count']} representaciones).")
    else:
        st.caption('Resultado histórico: fecha de consulta a IRSA no registrada. No equivale a una verificación actual.')
    if d.get('replacements'):
        with st.expander('Productos duplicados o sustituidos'):
            st.json(d['replacements'])
