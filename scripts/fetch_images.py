"""Download + normalize model images for the Holly Import vehicle gallery.

Sources are the official MG (mgvzla.com) and Maxus (maxusve.com) Venezuelan
brand sites. Holly Import is an authorized dealer, so using brand imagery
to merchandise its inventory is standard practice. We self-host (vs.
hot-link) for speed and to be independent of third-party uptime.

After download, every image is **normalized** to a uniform 1200x750 JPEG
on the site's dark card background (#18181c) so every card on the gallery
looks the same size, same aspect, same backdrop. Source aspect ratios
vary; we scale-to-fit and pad with the dark fill rather than crop.

Run:
    python scripts/fetch_images.py            # full refresh
    python scripts/fetch_images.py --force    # re-download even if cached
    python scripts/fetch_images.py --only mg-zs maxus-t60   # subset
    python scripts/fetch_images.py --no-normalize           # skip post-process

The manifest at static/img/models/_manifest.json records source URL +
filename per model for attribution / audit.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "img" / "models"

# Source URLs for each model. The image candidates are tried in order; the
# first that downloads cleanly wins. These are the canonical hero images
# from the Venezuelan brand sites at the time of writing — if a model
# changes its hero shot, edit this map.
SOURCES: dict[str, list[str]] = {
    # MG (mgvzla.com hero shots)
    "mg-3":            ["https://mgvzla.com/wp-content/uploads/2025/07/MG3_HIBRIDO-2025.png"],
    "mg-3-hybrid":     ["https://mgvzla.com/wp-content/uploads/2025/07/mg3_hibri-1024x602.png"],
    "mg-5":            ["https://mgvzla.com/wp-content/uploads/2026/02/DSC_3160_MG5-1024x403.png"],
    "mg-gt":           ["https://mgvzla.com/wp-content/uploads/2024/07/mg-gt-Blanco_00.png",
                        "https://mgvzla.com/wp-content/uploads/2024/07/MGGT_blanco.jpg"],
    "mg-zs":           ["https://mgvzla.com/wp-content/uploads/2025/07/MG_ZS-frente_25-1024x683.png"],
    "mg-zs-ev":        ["https://mgvzla.com/wp-content/uploads/2024/10/MG-EV-GRIS.png",
                        "https://mgvzla.com/wp-content/uploads/2024/12/IMG_EV.jpg"],
    "mg-rx5":          ["https://mgvzla.com/wp-content/uploads/2024/12/RX5_GRIS.png",
                        "https://mgvzla.com/wp-content/uploads/2024/12/MG_RX5_0000_DSC_0045.jpg"],
    "mg-rx8":          ["https://mgvzla.com/wp-content/uploads/2024/07/mg-rx8-Blanco.png",
                        "https://mgvzla.com/wp-content/uploads/2024/07/MG-RX8-WEB-1.jpg"],
    # mg-rx9 is a hand-processed cutout (rembg-segmented from the official MGS9
    # EU press kit studio shot) committed at static/img/models/mg-rx9.jpg.
    # Do NOT auto-refresh — the cutout is the source of truth.
    "mg-cyberster":    ["https://mgvzla.com/wp-content/uploads/2025/08/cyberster_3-1024x505.png"],
    # Maxus (maxusve.com — full-resolution product images, not menu thumbnails)
    "maxus-d60":       ["https://maxusve.com/wp-content/uploads/2025/05/D60_DSC_3609-2-1-1024x683.png"],
    "maxus-d90":       ["https://maxusve.com/wp-content/uploads/2025/05/DSC_0191_D90-1-1024x604.png"],
    "maxus-t60":       ["https://maxusve.com/wp-content/uploads/2025/06/T60_DSC_7509.png",
                        "https://maxusve.com/wp-content/uploads/2024/07/T60_ELITE.png"],
    "maxus-t90":       ["https://maxusve.com/wp-content/uploads/2024/07/maxus-10-1.png",
                        "https://maxusve.com/wp-content/uploads/2024/07/t90.png"],
    "maxus-g10":       ["https://maxusve.com/wp-content/uploads/2024/07/Maxus-G10.png"],
    "maxus-v80":       ["https://maxusve.com/wp-content/uploads/2024/07/V80.png"],
    "maxus-serie-c":   ["https://maxusve.com/wp-content/uploads/2024/07/Maxus-C100.png",
                        "https://maxusve.com/wp-content/uploads/2024/07/C_100.png"],
    "maxus-serie-s":   ["https://maxusve.com/wp-content/uploads/2024/07/S50.png"],
    "maxus-serie-h":   ["https://maxusve.com/wp-content/uploads/2024/07/SERIE__H4.png",
                        "https://maxusve.com/wp-content/uploads/2024/07/SERIE__H6.png",
                        "https://maxusve.com/wp-content/uploads/2024/07/SERIE__H-1.png"],
}

# Normalization target — every gallery image lands at this exact size + backdrop.
TARGET_W, TARGET_H = 1200, 750
BG_RGB = (24, 24, 28)   # site card colour (#18181c) so cards look seamless

UA = "Mozilla/5.0 (compatible; HollyImportFetcher/1.0)"


def download(url: str, dest: Path) -> tuple[bool, str]:
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=20) as r:
            if r.status != 200:
                return False, f"HTTP {r.status}"
            data = r.read()
            if len(data) < 2000:
                return False, f"too small ({len(data)} bytes)"
            dest.write_bytes(data)
            return True, f"{len(data)} bytes"
    except Exception as e:
        return False, str(e)


def ext_from_url(url: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    return suffix if suffix in (".jpg", ".jpeg", ".png", ".webp") else ".png"


def normalize_image(path: Path) -> tuple[bool, str]:
    """Resize + pad an image to TARGET_W x TARGET_H on the site backdrop.

    Scale-to-fit (never crop, never upscale beyond source); centre on a solid
    #18181c canvas. Output is JPEG so all gallery images end up the same
    format and roughly the same byte size, which makes the page network
    cost predictable.

    On success the file is replaced in-place with a .jpg suffix.
    """
    if not HAS_PIL:
        return False, "Pillow not installed (pip install Pillow)"
    try:
        img = Image.open(path).convert("RGBA")
    except Exception as e:
        return False, f"open: {e}"

    src_w, src_h = img.size
    scale = min(TARGET_W / src_w, TARGET_H / src_h, 1.0)
    new_w = max(1, round(src_w * scale))
    new_h = max(1, round(src_h * scale))
    if (new_w, new_h) != (src_w, src_h):
        img = img.resize((new_w, new_h), Image.LANCZOS)

    canvas = Image.new("RGB", (TARGET_W, TARGET_H), BG_RGB)
    offset = ((TARGET_W - new_w) // 2, (TARGET_H - new_h) // 2)
    if img.mode == "RGBA":
        # Alpha-composite so transparent areas pick up the dark backdrop.
        canvas.paste(img, offset, img.split()[3])
    else:
        canvas.paste(img, offset)

    out_path = path.with_suffix(".jpg")
    canvas.save(out_path, "JPEG", quality=86, optimize=True, progressive=True)
    if out_path != path and path.exists():
        path.unlink()  # remove the original (PNG) so we don't keep two copies
    return True, f"{out_path.name} ({TARGET_W}x{TARGET_H}, {out_path.stat().st_size} bytes)"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download even if file exists")
    ap.add_argument("--only", nargs="*", help="only fetch these model ids")
    ap.add_argument("--no-normalize", action="store_true",
                    help="skip the post-download resize/pad step")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / "_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try: manifest = json.loads(manifest_path.read_text())
        except Exception: pass

    do_norm = not args.no_normalize
    if do_norm and not HAS_PIL:
        print("WARN: Pillow not installed — normalization disabled. Run: pip install Pillow")
        do_norm = False

    # When normalizing, the canonical filename is always <id>.jpg. With the
    # --force flag we always re-download; otherwise we skip work if the
    # final .jpg is already on disk.
    targets = args.only or list(SOURCES.keys())
    ok = bad = skipped = 0
    for mid in targets:
        urls = SOURCES.get(mid)
        if not urls:
            print(f"  ?  {mid}: no source configured")
            bad += 1
            continue

        final_jpg = OUT_DIR / f"{mid}.jpg"
        if final_jpg.exists() and not args.force:
            print(f"  =  {mid}: already have {final_jpg.name}")
            skipped += 1
            continue

        # Download into a temp file with the source extension; normalization
        # converts to the canonical .jpg afterwards.
        raw = OUT_DIR / f"{mid}{ext_from_url(urls[0])}"
        downloaded = False
        for url in urls:
            print(f"  >  {mid}: {url}")
            success, info = download(url, raw)
            if success:
                manifest[mid] = {"source": url, "file": final_jpg.name}
                print(f"     -> raw {raw.name} ({info})")
                downloaded = True
                break
            else:
                print(f"     ! {info}")
        if not downloaded:
            print(f"  X  {mid}: no candidate URL worked")
            bad += 1
            continue

        if do_norm:
            success, info = normalize_image(raw)
            if success:
                print(f"     -> normalized {info}")
                ok += 1
            else:
                print(f"     ! normalize: {info}")
                bad += 1
        else:
            ok += 1

        time.sleep(0.4)  # be polite to the source server

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nDone: {ok} ok, {bad} failed, {skipped} skipped")
    print(f"Manifest: {manifest_path}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
