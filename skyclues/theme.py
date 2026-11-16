"""SkyClues visual identity: tokens, global styles, logo and the small presentation helpers.

Presentation only. Nothing in this module reads or changes observations, parameters or results.

Identity in one paragraph: a black-and-white page with ONE copper accent (``EMBER``, the colour of the
field-of-view ring on the sky) used sparingly for selection, the active state and verdict marks. No
greens, no blues. The page sits on a decorative "astronomical plate": a faint, invented negative star
field (dark points on light paper, as in printed sky surveys), grain and soft grey washes; it never
carries values and every data view keeps its own opaque background. Few boxes: only the map, images, player and plots
keep a container; everything else is text separated by hairlines. The three areas share the same
graphite tone and are told apart by glyph and motif, not by colour. Headings and interface in IBM
Plex Sans, every number in IBM Plex Mono. Styles live in ``theme.css``.
The symbol is the field-of-view ring with two points in it: where something was and where it is.
"""
from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager

import streamlit as st

INK, MUTED, FAINT, LINE, SURFACE, EMBER = "#141414", "#5a5a5a", "#8c8c8c", "#dcdcda", "#eeeeec", "#c4411c"
#: Primary action colour (black). The three areas share one graphite tone: glyph and motif tell them apart.
PETROL, AREA = "#161616", {"region": "#4a4a4a", "time": "#4a4a4a", "spectrum": "#4a4a4a"}
PAPER = "#f7f7f6"


def unit(text: str) -> str:
    """A unit or symbol inside a label set in capitals (µ and λ must never become M and Λ)."""
    return f'<span class="sc-unit">{text}</span>'
BRAND_DIR = Path(__file__).resolve().parent.parent / "assets" / "brand"
LEVELS = {"Simple": "simple", "Scientific": "scientific"}
NAV = {"Region": "region", "Time": "time", "Spectrum": "spectrum"}
NAV_LABEL = {v: k for k, v in NAV.items()}


def symbol_svg(size: int = 28, ink: str = INK, accent: str = EMBER) -> str:
    """The SkyClues symbol (inline SVG): field-of-view ring, an earlier position and a present one."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 32 32" fill="none" '
            f'role="img" aria-label="SkyClues"><circle cx="16" cy="16" r="12.5" stroke="{ink}" stroke-width="2"/>'
            f'<circle cx="12" cy="19.4" r="2.1" stroke="{ink}" stroke-width="1.6"/>'
            f'<circle cx="20.2" cy="12.4" r="3" fill="{accent}"/></svg>')


def _uri(svg: str) -> str:
    from urllib.parse import quote
    return "url(\"data:image/svg+xml," + quote(svg, safe="=:/ ,'") + "\")"


#: Area glyphs (navigation and headers). Pictograms, never data.
ICON = {
    "region": _uri("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='black' stroke-width='1.6' "
                   "stroke-linecap='round'><circle cx='8' cy='8' r='5.2'/><path d='M8 .9v3.2M8 11.9v3.2M.9 8h3.2M11.9 8h3.2'/>"
                   "<circle cx='8' cy='8' r='1' fill='black' stroke='none'/></svg>"),
    "time": _uri("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='black'><rect x='.8' y='4' width='4' "
                 "height='8' rx='1' opacity='.35'/><rect x='6' y='3' width='4' height='10' rx='1' opacity='.65'/>"
                 "<rect x='11.2' y='2' width='4' height='12' rx='1'/></svg>"),
    "spectrum": _uri("<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16' fill='none' stroke='black' "
                     "stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'><path d='M1 12.5c1.6 0 1.8-3 3.2-3"
                     "s1.6 2.6 3 2.6 1.6-9.6 3.2-9.6 1.4 7.7 2.8 7.7 1 .6 1.8.6'/></svg>"),
}

#: Decorative backgrounds of the area headers. Abstract motifs (no axes, values or stars): they must
#: never be mistaken for observations.
MOTIF = {
    "region": _uri("<svg xmlns='http://www.w3.org/2000/svg' width='520' height='220' viewBox='0 0 520 220' fill='none' "
                   "stroke='#141414' stroke-width='1'><g opacity='.16'><ellipse cx='400' cy='110' rx='190' ry='190'/>"
                   "<ellipse cx='400' cy='110' rx='120' ry='190'/><ellipse cx='400' cy='110' rx='55' ry='190'/>"
                   "<path d='M400-80v380'/><path d='M210 110h380'/><path d='M222 40c110 22 246 22 356 0M222 180c110-22 246-22 356 0'/>"
                   "</g><circle cx='400' cy='110' r='34' stroke='#c4411c' stroke-width='1.4' opacity='.85'/></svg>"),
    "time": _uri("<svg xmlns='http://www.w3.org/2000/svg' width='520' height='220' viewBox='0 0 520 220' fill='none'>"
                 "<g stroke='#141414' stroke-width='1'><rect x='190' y='62' width='72' height='96' rx='2' opacity='.06'/>"
                 "<rect x='270' y='56' width='76' height='108' rx='2' opacity='.10'/><rect x='354' y='50' width='80' "
                 "height='120' rx='2' opacity='.16'/><rect x='442' y='44' width='84' height='132' rx='2' opacity='.24'/></g>"
                 "<g fill='#141414'><circle cx='222' cy='118' r='2.4' opacity='.18'/><circle cx='305' cy='108' r='2.4' "
                 "opacity='.28'/><circle cx='392' cy='98' r='2.8' opacity='.4'/></g><circle cx='482' cy='88' r='3.6' "
                 "fill='#c4411c'/><path d='M190 196h330' stroke='#141414' stroke-dasharray='2 8' opacity='.16'/></svg>"),
    "spectrum": _uri("<svg xmlns='http://www.w3.org/2000/svg' width='520' height='220' viewBox='0 0 520 220'>"
                     "<defs><linearGradient id='g' x1='0' x2='1'><stop offset='0' stop-color='#141414' stop-opacity='0'/>"
                     "<stop offset='.5' stop-color='#141414' stop-opacity='.07'/><stop offset='1' stop-color='#141414' "
                     "stop-opacity='.02'/></linearGradient></defs><rect x='120' y='70' width='400' height='80' "
                     "fill='url(#g)'/><g stroke='#141414' opacity='.14'>"
                     "<path d='M236 64v92M262 64v92M331 64v92M342 64v92M418 64v92M470 64v92'/></g>"
                     "<path d='M418 64v92' stroke='#c4411c' opacity='.8'/></svg>"),
}

def _plate_stars(seed: int = 5461) -> str:
    """A stylised NEGATIVE photographic plate (dark stars on light paper), as in printed sky surveys.

    Deterministic (fixed seed) and invented: it is not any real region of the sky and never carries
    information. Kept very faint so it reads as texture: many tiny points, a few medium ones, a handful
    of bright stars with a soft halo and a thin ring, and one loose cluster with a diffuse glow."""
    import math
    import random

    rnd = random.Random(seed)
    W, H = 1600, 1000
    dots = []

    def dot(x, y, r, a):
        dots.append(f"<circle cx='{x:.0f}' cy='{y:.0f}' r='{r:.2f}' opacity='{a:.2f}'/>")

    for _ in range(620):                                    # faint field stars
        dot(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(.6, 1.0), rnd.uniform(.2, .36))
    for _ in range(110):                                    # medium stars
        dot(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(1.1, 1.7), rnd.uniform(.32, .5))
    # A loose cluster, low on the left: away from the header motif and its copper field-of-view ring,
    # so it never looks like something "inside the field".
    cx, cy = 300, 780
    for _ in range(170):
        d, t = abs(rnd.gauss(0, 95)), rnd.uniform(0, 2 * math.pi)
        dot(cx + d * math.cos(t) * 1.25, cy + d * math.sin(t), rnd.uniform(.5, 1.35) * (1.25 if d < 60 else 1),
            rnd.uniform(.2, .45))
    bright = []
    for x, y, r in ((210, 160, 2.6), (300, 690, 2.2), (760, 120, 1.9), (930, 820, 2.4), (1450, 640, 2.0),
                    (1320, 905, 1.8), (560, 430, 1.7), (95, 905, 1.9)):
        bright.append(f"<circle cx='{x}' cy='{y}' r='{r * 5.5:.1f}' fill='url(#h)'/>"
                      f"<circle cx='{x}' cy='{y}' r='{r * 3.2:.1f}' fill='none' stroke='#141414' stroke-width='.7' "
                      f"opacity='.10'/><circle cx='{x}' cy='{y}' r='{r}' opacity='.55'/>")
    svg = ("<svg xmlns='http://www.w3.org/2000/svg' width='1600' height='1000' viewBox='0 0 1600 1000' "
           "preserveAspectRatio='xMidYMid slice'><defs>"
           "<radialGradient id='h'><stop offset='0' stop-color='#141414' stop-opacity='.16'/>"
           "<stop offset='1' stop-color='#141414' stop-opacity='0'/></radialGradient>"
           "<radialGradient id='c'><stop offset='0' stop-color='#141414' stop-opacity='.05'/>"
           "<stop offset='1' stop-color='#141414' stop-opacity='0'/></radialGradient></defs>"
           f"<ellipse cx='{cx}' cy='{cy}' rx='330' ry='260' fill='url(#c)'/>"
           f"<g fill='#141414' opacity='.45'>{''.join(dots)}{''.join(bright)}</g></svg>")
    return _uri(svg)


#: The "astronomical plate" behind the page: a stylised negative star field (invented, see
#: ``_plate_stars``) and film grain. Purely decorative: it never carries information, and every map,
#: image and plot keeps its own opaque background so it can never be mistaken for data.
PLATE_ARCS = _plate_stars()
PLATE_GRAIN = _uri(
    "<svg xmlns='http://www.w3.org/2000/svg' width='240' height='240'><filter id='n' x='0' y='0' width='100%' height='100%'>"
    "<feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/>"
    "<feColorMatrix values='0 0 0 0 .08  0 0 0 0 .08  0 0 0 0 .08  0 0 0 .55 0'/></filter>"
    "<rect width='240' height='240' filter='url(#n)' opacity='.07'/></svg>")


def _css() -> str:
    tokens = {"INK": INK, "MUTED": MUTED, "FAINT": FAINT, "LINE": LINE, "SURFACE": SURFACE, "EMBER": EMBER,
              "PAPER": PAPER, "PETROL": PETROL, "P_ARCS": PLATE_ARCS, "P_GRAIN": PLATE_GRAIN}
    for k, v in AREA.items():
        tokens[f"A_{k.upper()}"] = v
        tokens[f"I_{k.upper()}"] = ICON[k]
        tokens[f"M_{k.upper()}"] = MOTIF[k]
    text = (Path(__file__).with_name("theme.css")).read_text(encoding="utf-8")
    for k, v in tokens.items():
        text = text.replace(f"@@{k}@@", v)
    return "<style>" + text + "</style>"


CSS = _css()


def inject() -> None:
    st.html(CSS)


@contextmanager
def loading(text: str, key: str):
    """Prominent inline wait for a main data product; cached/brief work never flashes a card."""
    with st.container(key=f"sc_loading_{key}"):
        with st.spinner(text, show_time=True, width="stretch"):
            yield


def brand_html() -> str:
    return (f'<a class="sc-brand" href="?" target="_self" aria-label="SkyClues, home">{symbol_svg(30)}'
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
    """A state mark: plain text with a small square (never a pill). ``kind`` = "sc-ok", "sc-warn", "sc-fail"
    or "" (neutral); it only chooses the square's treatment. The class keeps its historical name."""
    return f'<span class="sc-badge {kind}">{text}</span>'


def facts(items: list[tuple[str, str, str]]) -> None:
    """Key figures as a quiet definition grid: (label, value, detail)."""
    st.html('<dl class="sc-facts">' + "".join(
        f"<div><dt>{k}</dt><dd>{v}{f'<small>{d}</small>' if d else ''}</dd></div>" for k, v, d in items) + "</dl>")


def region_strip(name: str, ra: float, dec: float, fov: float, extra: str = "") -> None:
    """The active region, as the explorer is using it. One bar; the same in both explorers."""
    sci = scientific()
    st.html(
        f'<div class="sc-strip"><span class="sc-name"><small>{"Active region" if sci else "Area you are exploring"}</small>{name}</span><dl>'
        f'<div><dt>RA</dt><dd>{ra:.6f}°</dd></div><div><dt>Dec</dt><dd>{dec:+.6f}°</dd></div>'
        f'<div><dt>{"Field" if sci else "Size"}</dt><dd>{fov * 60:.1f}′</dd></div></dl>{extra}</div>')


def area_flag(view: str) -> None:
    """Marks the visible area so the shared styles take its accent (presentation only)."""
    st.html(f'<span class="sc-flag" data-view="{view}"></span>')


def hero(view: str, kicker: str, title: str, lede: str = "", extra: str = "") -> None:
    """Header of an area: what this screen is for. The motif behind it is decorative, never data."""
    st.html(f'<header class="sc-hero" data-view="{view}"><p class="sc-kicker">{kicker}</p><h1>{title}</h1>'
            + (f'<p class="sc-lede">{lede}</p>' if lede else "") + extra + "</header>")


def result(kind: str, label: str, text: str, more: str = "") -> None:
    """A scientific verdict in plain words: badge with the outcome, what it means, what it does not mean.

    ``kind`` is "ok", "warn", "fail" or "" (neutral); it only chooses the tone."""
    st.html(f'<div class="sc-result" data-kind="{kind}">{badge(label, f"sc-{kind}" if kind else "")}'
            f'<p>{text}</p>' + (f'<p class="sc-more">{more}</p>' if more else "") + "</div>")


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
           "region_strip", "reading_guide", "persistent", "bind", "keep", "LEVELS", "NAV", "NAV_LABEL",
           "area_flag", "hero", "result", "AREA", "PETROL"]
