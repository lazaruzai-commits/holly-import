"""Process locally-supplied vehicle photos into the gallery.

Workflow:
  1. Drop your own car photos into  static/img/models/_source/
     Name each file after the model id, with any image extension:
         mg-3.jpg
         mg-zs.png
         maxus-t60.webp
         ...
     (Run this script with --list to see every model id we expect.)

  2. Run:  python scripts/process_local_images.py
     - cuts the background using rembg (ML segmentation) if the source
       image still has its own background
     - resizes + pads to 1200x750 on the site's dark backdrop (#18181c)
     - writes the result to static/img/models/<id>.jpg

  3. The gallery picks the new image up automatically — no model-data
     edits needed.

Tips for a uniform showroom look:
  - Pick the SAME color across every model where possible (white or
    silver is easiest to source).
  - 3/4 front quarter angle reads best on cards.
  - Avoid outdoor lifestyle shots; clean studio or transparent PNG is
    ideal.
  - Larger source images give you headroom; the script downscales to
    1200x750.

Flags:
  --list                 print every model id + whether a source file is
                         already in the drop folder, then exit
  --no-bg-remove         skip the rembg step (keeps whatever background
                         the source image already has — fine if you've
                         already cut them out yourself)
  --only ID [ID ...]     only process these model ids
  --bg-color #RRGGBB     override the backdrop colour (default #18181c)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "static" / "img" / "models" / "_source"
OUT_DIR = ROOT / "static" / "img" / "models"
DATA_FILE = ROOT / "data" / "models.json"

TARGET_W, TARGET_H = 1200, 750
DEFAULT_BG = (24, 24, 28)   # #18181c
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def parse_hex_colour(s: str) -> tuple[int, int, int]:
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise argparse.ArgumentTypeError(f"need #RRGGBB, got {s!r}")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def model_ids() -> list[str]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return [m["id"] for m in data["models"]]


def find_source(model_id: str) -> Path | None:
    """Return the first matching source file for a model id, or None."""
    for ext in SUPPORTED_EXTS:
        p = SOURCE_DIR / f"{model_id}{ext}"
        if p.exists():
            return p
    return None


def remove_background(img: Image.Image) -> Image.Image:
    """Cut the background out using rembg's u2net model."""
    try:
        from rembg import remove, new_session
    except ImportError:
        raise RuntimeError(
            "rembg not installed. Either run with --no-bg-remove, "
            "or install:  pip install rembg onnxruntime"
        )
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    session = new_session("u2net")
    cutout_bytes = remove(buf.getvalue(), session=session)
    return Image.open(io.BytesIO(cutout_bytes)).convert("RGBA")


def normalize(img: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    """Scale-to-fit + centre on a TARGET_W x TARGET_H canvas filled with bg."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    sw, sh = img.size
    scale = min(TARGET_W / sw, TARGET_H / sh, 1.0)
    nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
    if (nw, nh) != (sw, sh):
        img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (TARGET_W, TARGET_H), bg)
    canvas.paste(img, ((TARGET_W - nw) // 2, (TARGET_H - nh) // 2), img.split()[3])
    return canvas


def process(model_id: str, source: Path, out: Path,
            bg: tuple[int, int, int], do_bg_remove: bool) -> None:
    img = Image.open(source).convert("RGBA")
    if do_bg_remove:
        img = remove_background(img)
    final = normalize(img, bg)
    final.save(out, "JPEG", quality=88, optimize=True, progressive=True)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Process drop-folder images into the gallery.")
    ap.add_argument("--list", action="store_true",
                    help="show all model ids and source-file status, then exit")
    ap.add_argument("--no-bg-remove", action="store_true",
                    help="skip ML background removal (use if the source images are already clean cutouts)")
    ap.add_argument("--only", nargs="*", help="only process these model ids")
    ap.add_argument("--bg-color", type=parse_hex_colour, default=DEFAULT_BG,
                    help="hex backdrop colour, e.g. #18181c (default matches the site)")
    args = ap.parse_args(argv)

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    ids = model_ids()
    if args.list:
        print(f"Drop folder: {SOURCE_DIR}")
        print(f"{'model id':<22} {'source file':<40} status")
        print("-" * 75)
        for mid in ids:
            src = find_source(mid)
            status = f"OK ({src.name})" if src else "MISSING"
            src_name = src.name if src else "-"
            print(f"  {mid:<20} {src_name:<40} {status}")
        return 0

    targets = args.only or ids
    do_bg_remove = not args.no_bg_remove

    ok = missing = bad = 0
    for mid in targets:
        if mid not in ids:
            print(f"  ?  {mid}: not a known model id — see scripts/process_local_images.py --list")
            bad += 1
            continue
        src = find_source(mid)
        if not src:
            print(f"  -  {mid}: no source file in drop folder")
            missing += 1
            continue
        out = OUT_DIR / f"{mid}.jpg"
        try:
            print(f"  >  {mid}: {src.name}")
            process(mid, src, out, args.bg_color, do_bg_remove)
            print(f"     -> {out.name} ({out.stat().st_size} bytes)")
            ok += 1
        except Exception as e:
            print(f"     ! {e}")
            bad += 1

    print(f"\nDone: {ok} processed, {missing} missing source, {bad} failed")
    if missing:
        print("Drop the missing files into:", SOURCE_DIR)
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
