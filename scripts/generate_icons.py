"""Derive Promptya's web + PWA icon set from the provided brand master.

The brand mark is a purple → blue → cyan "P" ribbon that ships as a transparent
PNG in ``static/icons/source/``. That source bleeds to the edges of its canvas,
which is fine for a page favicon but wrong for a home-screen icon: Android
paints ``any`` icons over the launcher's own background, so transparent corners
turn into stray white, and a ``maskable`` icon must keep its content inside the
inner 80% safe circle or the launcher crops the mark.

So every icon this script emits is fully opaque and is composed from the same
two ingredients the design system already uses:

    background  the app's dark canvas (#0a0a0f) — the same value as the
                manifest ``theme_color``/``background_color`` and the dark
                ``<meta name="theme-color">``
    content     the master mark, trimmed to its alpha bounding box and
                re-centred, at a per-purpose scale:

                  purpose "any"       0.82  (breathing room, no cropping)
                  purpose "maskable"  0.56  (square inscribed in the 80% circle)
                  apple-touch-icon    0.78

Run it after replacing the master:

    python scripts/generate_icons.py

``static/icons/favicon.ico`` is *not* generated — it is the purpose-built
multi-resolution ICO (16→256px) supplied with the brand assets and is used
verbatim.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "static" / "icons"
MASTER = ICONS / "source" / "mark-512.png"

# Must stay in sync with --bg in static/css/app.css, the two <meta
# name="theme-color"> tags in templates/web/base.html and the manifest.
CANVAS = (10, 10, 15, 255)


def load_mark() -> Image.Image:
    """The master mark, trimmed to its visible bounds and squared up."""
    mark = Image.open(MASTER).convert("RGBA")
    bbox = mark.getbbox()
    if bbox:
        mark = mark.crop(bbox)
    # Centre inside a square so scaling never distorts the ribbon.
    side = max(mark.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(mark, ((side - mark.width) // 2, (side - mark.height) // 2), mark)
    return square


def compose(size: int, ratio: float, mark: Image.Image) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), CANVAS)
    inner = max(1, round(size * ratio))
    # LANCZOS keeps the ribbon's soft gradient from banding when downscaled.
    scaled = mark.resize((inner, inner), Image.LANCZOS)
    offset = (size - inner) // 2
    canvas.alpha_composite(scaled, (offset, offset))
    return canvas


def write(canvas: Image.Image, path: Path, size: int) -> None:
    canvas.convert("RGB").save(path, "PNG", optimize=True)
    print(f"  {path.relative_to(ROOT)}  {size}x{size}")


def main() -> None:
    if not MASTER.exists():
        raise SystemExit(f"Missing brand master: {MASTER}")
    mark = load_mark()
    print("Generating Promptya icons from", MASTER.relative_to(ROOT))
    for size in (192, 512):
        write(compose(size, 0.82, mark), ICONS / f"icon-{size}.png", size)
        write(compose(size, 0.56, mark), ICONS / f"icon-maskable-{size}.png", size)
    write(compose(180, 0.78, mark), ICONS / "apple-touch-icon.png", 180)
    print("Done. favicon.ico is used as supplied.")


if __name__ == "__main__":
    main()
