"""Write the SkyClues brand files (assets/brand): vector logo variants and the raster favicon.

The symbol is drawn from the same geometry as ``skyclues.theme.symbol_svg`` (32-unit grid): the
field-of-view ring, a hollow point (an earlier position) and a filled ember point (the present one).
The wordmark is set in Newsreader Medium; the SVG keeps it as text with a serif fallback.

Run:  python scripts/build_brand.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

INK, EMBER, PAPER, NIGHT = "#14171c", "#c4411c", "#ffffff", "#0d0f12"
EMBER_ON_DARK = "#ff8a3d"
OUT = Path(__file__).resolve().parents[1] / "assets" / "brand"
FONT = "Newsreader, 'Iowan Old Style', 'Palatino Linotype', Georgia, serif"


def symbol(ink: str, accent: str, x: float = 0, y: float = 0, scale: float = 1.0) -> str:
    return (f'<g transform="translate({x} {y}) scale({scale})" fill="none">'
            f'<circle cx="16" cy="16" r="12.5" stroke="{ink}" stroke-width="2"/>'
            f'<circle cx="12" cy="19.4" r="2.1" stroke="{ink}" stroke-width="1.6"/>'
            f'<circle cx="20.2" cy="12.4" r="3" fill="{accent}"/></g>')


def svg(width: int, height: int, body: str, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{title}"><title>{title}</title>{body}</svg>\n')


def wordmark(ink: str, accent: str, background: str | None = None) -> str:
    bg = f'<rect width="196" height="48" fill="{background}"/>' if background else ""
    return svg(196, 48, bg + symbol(ink, accent, 4, 8) +
               f'<text x="46" y="33" font-family="{FONT}" font-size="27" font-weight="500" letter-spacing="-0.5" '
               f'fill="{ink}">SkyClues</text>', "SkyClues")


def tile(background: str, ink: str, accent: str) -> str:
    return svg(64, 64, f'<rect width="64" height="64" rx="14" fill="{background}"/>' + symbol(ink, accent, 8, 8, 1.5),
               "SkyClues")


def favicon_png(size: int, background: str, ink: str, accent: str) -> Image.Image:
    s = 8                                   # supersampling for clean edges
    n = size * s
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * 0.22), fill=background)
    u = n / 64                              # the 64-unit tile grid (symbol at 8,8 scaled 1.5)
    def pt(x, y):
        return (8 + 1.5 * x) * u, (8 + 1.5 * y) * u
    def ring(cx, cy, r, width, colour):
        x, y = pt(cx, cy)
        rr = 1.5 * r * u
        d.ellipse([x - rr, y - rr, x + rr, y + rr], outline=colour, width=max(1, round(1.5 * width * u)))
    def dot(cx, cy, r, colour):
        x, y = pt(cx, cy)
        rr = 1.5 * r * u
        d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=colour)
    ring(16, 16, 13.5, 2, ink)
    ring(12, 19.4, 2.9, 1.6, ink)
    dot(20.2, 12.4, 3, accent)
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "skyclues-logo.svg": wordmark(INK, EMBER),                          # primary, light surfaces
        "skyclues-logo-dark.svg": wordmark(PAPER, EMBER_ON_DARK),           # primary, dark surfaces (transparent)
        "skyclues-symbol.svg": svg(32, 32, symbol(INK, EMBER), "SkyClues"),
        "skyclues-symbol-dark.svg": svg(32, 32, symbol(PAPER, EMBER_ON_DARK), "SkyClues"),
        "skyclues-compact.svg": tile(INK, PAPER, EMBER_ON_DARK),            # app icon / avatar
        "skyclues-compact-light.svg": tile(PAPER, INK, EMBER),
        "favicon.svg": tile(INK, PAPER, EMBER_ON_DARK),
    }
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8")
    favicon_png(64, INK, PAPER, EMBER_ON_DARK).save(OUT / "favicon.png")
    favicon_png(256, INK, PAPER, EMBER_ON_DARK).save(OUT / "skyclues-icon-256.png")
    print(f"{len(files) + 2} files in {OUT}")


if __name__ == "__main__":
    main()
