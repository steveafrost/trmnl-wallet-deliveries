#!/usr/bin/env python3
"""Build the TRMNL recipe assets: icon + one screenshot per layout.

Requires full-resolution panel renders (see scripts/screenshot-layouts.sh) at
exact sizes, then writes:

    images/icon.png   512x512 recipe icon, resized from assets/icon-source.png
    images/f.png      full           800x480
    images/h.png      half_horizontal 800x240
    images/v.png      half_vertical   400x480
    images/q.png      quadrant        400x240

Usage:
    python3 scripts/make-images.py <render-dir> [out-dir]
"""
import pathlib
import sys

from PIL import Image

# layout key -> (source filename, (width, height))
LAYOUTS = {
    "f": ("full.png", (800, 480)),
    "h": ("half_horizontal.png", (800, 240)),
    "v": ("half_vertical.png", (400, 480)),
    "q": ("quadrant.png", (400, 240)),
}


def make_screenshots(render_dir: pathlib.Path, out_dir: pathlib.Path) -> None:
    for key, (filename, size) in LAYOUTS.items():
        src = render_dir / filename
        if not src.exists():
            raise SystemExit(f"missing render: {src}")
        image = Image.open(src).convert("L")
        if image.size != size:
            raise SystemExit(f"{src} is {image.size}, expected {size}")
        # 1-bit friendly: keep pure black/white, no antialiased gray haze
        image = image.point(lambda px: 255 if px > 160 else 0)
        target = out_dir / f"{key}.png"
        image.convert("L").save(target, optimize=True)
        print(f"wrote {target} ({image.size[0]}x{image.size[1]})")


def make_icon(out_dir: pathlib.Path, source: pathlib.Path, size: int = 512) -> None:
    """The recipe icon, resized from the committed artwork.

    The art is Microsoft's Fluent Emoji "Delivery truck" (MIT), kept in assets/
    so a rebuild is reproducible and the licence travels with the repo. Drawing
    the glyph here instead would let a routine image rebuild silently replace the
    icon the recipe shipped with.
    """
    if not source.exists():
        raise SystemExit(f"missing icon artwork: {source}")
    img = Image.open(source).convert("RGBA").resize((size, size), Image.LANCZOS)
    target = out_dir / "icon.png"
    img.save(target)
    print(f"wrote {target} ({size}x{size}) from {source.name}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    render_dir = pathlib.Path(sys.argv[1])
    repo = pathlib.Path(__file__).resolve().parent.parent
    out_dir = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else repo / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    make_screenshots(render_dir, out_dir)
    make_icon(out_dir, repo / "assets" / "icon-source.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
