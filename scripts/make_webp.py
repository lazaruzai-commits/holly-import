#!/usr/bin/env python3
"""Generate WebP siblings for the site's bitmap images.

For every .png / .jpg under the image folders listed below this writes a
`<same name>.webp` next to it, resized down to a sensible maximum width:

  * card / hero cutouts (PNG with alpha)  -> max 1000 px wide, quality 82
  * photos (JPG galleries, banners)        -> max 1400 px wide, quality 80

`static_v()` in app.py serves the .webp automatically whenever one exists, so
the JSON data and templates keep pointing at the original file names.

Run after adding or replacing any image:

    python scripts/make_webp.py            # everything
    python scripts/make_webp.py --force    # regenerate even if up to date

Requires Pillow (in requirements.txt).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = ["static/img/models", "static/img/inventory", "static/img/importados", "static/img/brand",
           "static/video/posters"]
# Working/source files that no page references — no point converting them.
SKIP = {"holly-import-logo-source.png", "HollyRed2Logo.png",
        "holly_with_car_behind_facing_left_8f68640f_f711_416d_9aed_e15f.png"}
PNG_MAX_W, PNG_Q = 1000, 82
JPG_MAX_W, JPG_Q = 1400, 80


def convert(src: Path, force: bool) -> tuple[int, int] | None:
    dst = src.with_suffix(".webp")
    if not force and dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return None
    im = Image.open(src)
    is_png = src.suffix.lower() == ".png"
    max_w, q = (PNG_MAX_W, PNG_Q) if is_png else (JPG_MAX_W, JPG_Q)
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    im = im.convert("RGBA" if is_png else "RGB")
    im.save(dst, "WEBP", quality=q, method=6)
    return src.stat().st_size, dst.stat().st_size


def main() -> None:
    force = "--force" in sys.argv
    before = after = 0
    for folder in FOLDERS:
        for src in sorted((ROOT / folder).glob("*")):
            if src.suffix.lower() not in {".png", ".jpg", ".jpeg"} or src.name in SKIP:
                continue
            r = convert(src, force)
            if r:
                before += r[0]; after += r[1]
                print(f"{r[0] // 1024:6d} KB -> {r[1] // 1024:5d} KB  {src.relative_to(ROOT)}")
    if before:
        print(f"\ntotal {before // 1024 // 1024} MB -> {after // 1024 // 1024} MB ({after * 100 // before}%)")
    else:
        print("all .webp files already up to date")


if __name__ == "__main__":
    main()
