"""SkyClues visual identity: tokens, global styles, logo and the small presentation helpers.

Presentation only. Nothing in this module reads or changes observations, parameters or results.

Identity in one paragraph: white page, near-black ink, hairline rules instead of boxes, one warm
accent ("ember", the colour used for the field-of-view ring on the sky). Headings in Newsreader
(editorial serif), interface in IBM Plex Sans, every number that can be copied in IBM Plex Mono.
The symbol is the field-of-view ring with two points in it: where something was and where it is.
"""
from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager

import streamlit as st

INK, MUTED, FAINT, LINE, SURFACE, EMBER = "#14171c", "#5b6470", "#8a929c", "#e3e6ea", "#f6f7f8", "#c4411c"
def unit(text: str) -> str:
    """A unit or symbol inside a label set in capitals (µ and λ must never become M and Λ)."""
    return f'<span class="sc-unit">{text}</span>'
BRAND_DIR = Path(__file__).resolve().parent.parent / "assets" / "brand"
LEVELS = {"Sencillo": "simple", "Científico": "scientific"}
NAV = {"Región": "region", "Tiempo": "time", "Espectro": "spectrum"}
NAV_LABEL = {v: k for k, v in NAV.items()}


def symbol_svg(size: int = 28, ink: str = INK, accent: str = EMBER) -> str:
    """The SkyClues symbol (inline SVG): field-of-view ring, an earlier position and a present one."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 32 32" fill="none" '
            f'role="img" aria-label="SkyClues"><circle cx="16" cy="16" r="12.5" stroke="{ink}" stroke-width="2"/>'
            f'<circle cx="12" cy="19.4" r="2.1" stroke="{ink}" stroke-width="1.6"/>'
            f'<circle cx="20.2" cy="12.4" r="3" fill="{accent}"/></svg>')


CSS = f"""
<style>
:root{{--sc-ink:{INK};--sc-muted:{MUTED};--sc-faint:{FAINT};--sc-line:{LINE};--sc-surface:{SURFACE};--sc-ember:{EMBER};
  --sc-mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Consolas,monospace;
  --sc-serif:"Newsreader","Iowan Old Style","Palatino Linotype",Georgia,serif}}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stExpandSidebarButton"]{{display:none!important}}
[data-testid="stHeader"]{{background:transparent;height:0;min-height:0}}
[data-testid="stToolbar"]{{top:.4rem}}
.block-container,[data-testid="stMainBlockContainer"]{{padding-top:1.1rem;padding-bottom:4rem;max-width:1320px}}
h1,h2,h3,h4{{font-family:var(--sc-serif);font-weight:500;letter-spacing:-.015em;color:var(--sc-ink)}}
h1{{font-size:2.05rem;line-height:1.12}} h2{{font-size:1.5rem}} h3{{font-size:1.22rem}} h4{{font-size:1.05rem}}
[data-testid="stHeadingWithActionElements"] a{{display:none}}

/* header */
.st-key-sc_header{{border-bottom:1px solid var(--sc-line);padding-bottom:.7rem;margin-bottom:.4rem;align-items:center;row-gap:.5rem}}
.sc-brand{{display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--sc-ink)}}
.sc-brand span{{font-family:var(--sc-serif);font-size:1.5rem;font-weight:500;letter-spacing:-.02em;line-height:1}}
.sc-brand small{{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--sc-faint);margin-left:4px;
  padding-left:12px;border-left:1px solid var(--sc-line)}}
.st-key-nav [data-testid="stButtonGroup"],.st-key-level [data-testid="stButtonGroup"]{{gap:0}}
.st-key-nav button{{border:0!important;background:transparent!important;border-radius:0!important;padding:.35rem .95rem!important;
  color:var(--sc-muted)!important;font-weight:500;box-shadow:inset 0 -2px 0 transparent;transition:color .16s ease,box-shadow .16s ease}}
.st-key-nav button:hover{{color:var(--sc-ink)!important}}
.st-key-nav button[kind="segmented_controlActive"],.st-key-nav button[aria-checked="true"],.st-key-nav button[aria-pressed="true"]{{
  color:var(--sc-ink)!important;box-shadow:inset 0 -2px 0 var(--sc-ember)}}
.st-key-level button{{font-size:.8rem!important;padding:.2rem .7rem!important;min-height:0!important;transition:background-color .16s ease,color .16s ease}}
.st-key-level p,.st-key-nav p{{font-size:inherit}}

/* shared pieces */
[data-testid="stSpinner"]{{border-left:2px solid var(--sc-ember);padding:.6rem .85rem;background:var(--sc-surface);
  border-radius:0 6px 6px 0;color:var(--sc-ink);margin:.4rem 0}}
[data-testid="stStatusWidget"]{{border:1px solid var(--sc-line);border-radius:6px;background:#fff}}
[class*="st-key-sc_loading_"] [data-testid="stSpinner"]{{position:relative;isolation:isolate;min-height:215px;
  display:flex;flex-direction:column;justify-content:center;align-items:center;gap:16px;text-align:center;
  padding:28px;border:1px solid #e6e8eb;border-radius:14px;background:linear-gradient(135deg,rgba(246,247,248,.92),rgba(255,255,255,.86));
  backdrop-filter:blur(7px);box-shadow:0 8px 30px rgba(20,23,28,.045);font-size:1.12rem;line-height:1.5}}
[class*="st-key-sc_loading_"] [data-testid="stSpinner"]::before{{content:"";width:42px;height:42px;flex-shrink:0;
  border:2px solid #e2d9d4;border-top-color:var(--sc-ember);border-right-color:var(--sc-ember);border-radius:50%;animation:sc-loading 1s linear infinite}}
[class*="st-key-sc_loading_"] [data-testid="stSpinner"] p{{font-size:1.12rem;font-weight:500;max-width:45ch}}
[class*="st-key-sc_loading_"] [data-testid="stSpinner"]>div{{justify-content:center;width:100%}}
[class*="st-key-sc_loading_"] [data-testid="stSpinner"]>div>span{{display:none}}
[class*="st-key-sc_loading_"] [data-testid="stSpinner"]>div>div{{display:flex;flex-direction:column;align-items:center;gap:6px;width:100%}}
[class*="st-key-sc_loading_"] [data-testid="stSpinner"]>div>div>span{{font-family:var(--sc-mono);font-size:.78rem;color:var(--sc-muted)}}
@keyframes sc-loading{{to{{transform:rotate(360deg)}}}}
.sc-eyebrow{{font-size:.72rem;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--sc-muted);margin:0 0 .25rem}}
.sc-unit{{text-transform:none!important;letter-spacing:normal}}
/* Notes under the spectrum plots: Streamlit draws captions at 60 % opacity; here they keep the full secondary tone. */
.st-key-sx_points [data-testid="stCaptionContainer"],.st-key-sx_analysis [data-testid="stCaptionContainer"],
[class*="st-key-sx_notes_"] [data-testid="stCaptionContainer"]{{opacity:1}}
.sc-lede{{color:var(--sc-muted);font-size:1rem;max-width:68ch;margin:.1rem 0 0}}
.sc-sub{{color:var(--sc-muted);font-size:.95rem}}
.sc-strip{{display:flex;flex-wrap:wrap;align-items:baseline;gap:.35rem 1.4rem;padding:.7rem 0;border-bottom:1px solid var(--sc-line);
  animation:sc-in .18s ease}}
.sc-strip .sc-name{{font-family:var(--sc-serif);font-size:1.45rem;font-weight:500;letter-spacing:-.015em;margin-right:.4rem}}
.sc-strip dl{{display:flex;flex-wrap:wrap;gap:.3rem 1.4rem;margin:0}}
.sc-strip dt{{font-size:.68rem;letter-spacing:.09em;text-transform:uppercase;color:var(--sc-faint);font-weight:600}}
.sc-strip dd{{margin:0;font-family:var(--sc-mono);font-size:.9rem;font-variant-numeric:tabular-nums}}
.sc-badge{{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font-size:.8rem;font-weight:600;
  border:1px solid var(--sc-line);background:#fff;color:var(--sc-ink);white-space:nowrap}}
.sc-badge::before{{content:"";width:7px;height:7px;border-radius:50%;background:var(--sc-faint)}}
.sc-ok{{border-color:#b9d8c0;color:#1d5c2b}} .sc-ok::before{{background:#2e8b47}}
.sc-warn{{border-color:#ecd08a;color:#7a5300}} .sc-warn::before{{background:#d39a13}}
.sc-fail{{border-color:#efb3ad;color:#8f2118}} .sc-fail::before{{background:#c4372b}}
.sc-note{{border-left:2px solid var(--sc-ink);padding:.15rem 0 .15rem .95rem;color:var(--sc-ink);font-size:.92rem;margin:.6rem 0;max-width:86ch}}
.sc-note b{{font-weight:600}}
.sc-read{{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.9rem 1.6rem;border-top:1px solid var(--sc-line);
  border-bottom:1px solid var(--sc-line);padding:.9rem 0;margin:.4rem 0 .8rem}}
.sc-read div{{font-size:.9rem;color:var(--sc-muted)}}
.sc-read b{{display:block;font-size:.7rem;letter-spacing:.09em;text-transform:uppercase;color:var(--sc-ink);font-weight:600;margin-bottom:.2rem}}
.sc-facts{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.9rem 1.6rem;margin:.9rem 0}}
.sc-facts div{{border-top:1px solid var(--sc-line);padding-top:.5rem}}
.sc-facts dt{{font-size:.68rem;letter-spacing:.09em;text-transform:uppercase;color:var(--sc-faint);font-weight:600}}
.sc-facts dd{{margin:.15rem 0 0;font-family:var(--sc-serif);font-size:1.5rem;letter-spacing:-.01em;line-height:1.15}}
.sc-facts small{{display:block;font-family:var(--sc-mono);font-size:.74rem;color:var(--sc-muted);margin-top:.15rem}}
.sc-empty{{border:1px dashed var(--sc-line);border-radius:10px;padding:1.6rem 1.4rem;color:var(--sc-muted);max-width:74ch}}
.sc-empty b{{color:var(--sc-ink)}}

/* Streamlit widgets, quieter */
[data-testid="stMetricValue"]{{font-family:var(--sc-serif);font-weight:500;letter-spacing:-.01em}}
[data-testid="stMetricLabel"] p{{font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;color:var(--sc-faint);font-weight:600}}
[data-testid="stExpander"] details{{border:0;border-top:1px solid var(--sc-line);border-radius:0}}
[data-testid="stExpander"] summary{{padding-left:0;font-weight:500}}
[data-testid="stTabs"] [data-baseweb="tab-list"]{{gap:1.4rem}}
[data-testid="stTabs"] button[role="tab"]{{padding-left:0;padding-right:0}}
.stButton button,.stDownloadButton button{{transition:background-color .14s ease,border-color .14s ease,color .14s ease,transform .12s ease}}
.stButton button:active{{transform:scale(.985)}}
[data-testid="stCaptionContainer"]{{color:var(--sc-muted)}}
[data-testid="stElementContainer"] iframe{{border-radius:8px}}
@keyframes sc-in{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
.sc-view{{animation:sc-in .2s ease}}
@media (max-width:760px){{
  .block-container,[data-testid="stMainBlockContainer"]{{padding-left:1rem;padding-right:1rem}}
  .sc-brand small{{display:none}}
  h1{{font-size:1.7rem}}
}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important;transition:none!important}}}}
</style>
"""


def inject() -> None:
    st.html(CSS)


@contextmanager
def loading(text: str, key: str):
    """Prominent inline wait for a main data product; cached/brief work never flashes a card."""
    with st.container(key=f"sc_loading_{key}"):
        with st.spinner(text, show_time=True, width="stretch"):
            yield


def brand_html() -> str:
    return (f'<a class="sc-brand" href="?" target="_self" aria-label="SkyClues, inicio">{symbol_svg(30)}'
            '<span>SkyClues</span><small>SPHEREx · IRSA</small></a>')


def level() -> str:
    """Presentation level: "simple" or "scientific". Never an input of any calculation."""
    return LEVELS.get(st.session_state.get("level"), "simple")


def scientific() -> bool:
    return level() == "scientific"


def eyebrow(text: str) -> None:
    st.html(f'<p class="sc-eyebrow">{text}</p>')


def note(html: str) -> None:
    st.html(f'<div class="sc-note">{html}</div>')


def badge(text: str, kind: str = "") -> str:
    return f'<span class="sc-badge {kind}">{text}</span>'


def facts(items: list[tuple[str, str, str]]) -> None:
    """Key figures as a quiet definition grid: (label, value, detail)."""
    st.html('<dl class="sc-facts">' + "".join(
        f"<div><dt>{k}</dt><dd>{v}{f'<small>{d}</small>' if d else ''}</dd></div>" for k, v, d in items) + "</dl>")


def region_strip(name: str, ra: float, dec: float, fov: float, extra: str = "") -> None:
    """The active region, as the explorer is using it. One line; the same in both explorers."""
    st.html(
        f'<div class="sc-strip"><span class="sc-name">{name}</span><dl>'
        f'<div><dt>RA</dt><dd>{ra:.6f}°</dd></div><div><dt>Dec</dt><dd>{dec:+.6f}°</dd></div>'
        f'<div><dt>Campo</dt><dd>{fov * 60:.1f}′</dd></div></dl>{extra}</div>')


def reading_guide(items: list[tuple[str, str]]) -> None:
    """Short contextual explanations placed next to what they explain (never a tutorial)."""
    st.html('<div class="sc-read">' + "".join(f"<div><b>{k}</b>{v}</div>" for k, v in items) + "</div>")


def persistent(name: str, default):
    """Value of an option that must survive while its widget is not drawn (another view or level)."""
    return st.session_state.setdefault(f"opt_{name}", default)


def bind(name: str, default) -> str:
    """Widget key for a persistent option: gives the stored value to the widget before it is created
    and copies changes back, so hiding a control never resets what the user chose."""
    key, store = f"w_{name}", f"opt_{name}"
    st.session_state.setdefault(store, default)
    st.session_state[key] = st.session_state[store]
    return key


def keep(name: str) -> None:
    st.session_state[f"opt_{name}"] = st.session_state[f"w_{name}"]


__all__ = ["inject", "brand_html", "symbol_svg", "level", "scientific", "eyebrow", "note", "badge", "facts",
           "region_strip", "reading_guide", "persistent", "bind", "keep", "LEVELS", "NAV", "NAV_LABEL"]
