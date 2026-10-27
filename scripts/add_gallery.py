#!/usr/bin/env python3
"""Install gallery photos for a model and wire them into data/models.json.

    python scripts/add_gallery.py <model-id> --exterior a.jpg b.jpg --interior c.jpg [--replace]

Each source image is copied to static/img/models/<model-id>-ext-N.jpg (or -int-N),
downsized to at most 1800 px wide, saved as JPEG q88, then the model's
`gallery.exterior` / `gallery.interior` lists in data/models.json are extended
(or replaced with --replace). Finally scripts/make_webp.py runs so the site serves
the WebP twins.

Several model ids may share one photo set (e.g. T60 4x2 and 4x4): pass them
comma-separated — `maxus-t60-dc-4x2,maxus-t60-dc-4x4` — and the files are
written once per id.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "models.json"
IMG_DIR = ROOT / "static" / "img" / "models"
MAX_W, QUALITY = 1800, 88


def install(src: Path, dst: Path) -> None:
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    if im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=QUALITY, optimize=True, progressive=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model_ids", help="model id, or several comma-separated ids sharing the same photos")
    ap.add_argument("--exterior", nargs="*", default=[])
    ap.add_argument("--interior", nargs="*", default=[])
    ap.add_argument("--replace", action="store_true", help="replace existing lists instead of appending")
    a = ap.parse_args()

    data = json.loads(DATA.read_text(encoding="utf-8"))
    by_id = {m["id"]: m for m in data["models"]}
    ids = [i.strip() for i in a.model_ids.split(",") if i.strip()]
    missing = [i for i in ids if i not in by_id]
    if missing:
        sys.exit(f"unknown model id(s): {missing}")

    for mid in ids:
        m = by_id[mid]
        gallery = m.setdefault("gallery", {})
        for kind, key, files in (("ext", "exterior", a.exterior), ("int", "interior", a.interior)):
            if not files:
                continue
            existing = [] if a.replace else list(gallery.get(key, []))
            n = len(existing)
            for f in files:
                n += 1
                dst = IMG_DIR / f"{mid}-{kind}-{n}.jpg"
                install(Path(f), dst)
                existing.append(dst.relative_to(ROOT).as_posix())
                print(f"  {dst.relative_to(ROOT)}  <-  {Path(f).name}")
            gallery[key] = existing
        print(f"{mid}: exterior={len(gallery.get('exterior', []))} interior={len(gallery.get('interior', []))}")

    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "make_webp.py")], check=True)


if __name__ == "__main__":
    main()
