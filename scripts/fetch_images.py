"""Download model images from mgvzla.com and maxusve.com to static/img/models/.

Holly Import is an authorized dealer of MG and Maxus, so using brand imagery
to merchandise its inventory is standard practice. We self-host (vs. hot-link)
so the site is fast and not dependent on third-party uptime.

Run:
    python scripts/fetch_images.py            # download everything
    python scripts/fetch_images.py --force    # re-download even if file exists
    python scripts/fetch_images.py --only mg-zs maxus-t60   # subset

The script keeps a manifest at static/img/models/_manifest.json mapping
model_id -> source URL + downloaded filename so we can audit attribution.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "img" / "models"

# Source URLs for each model. The image candidates are tried in order; the
# first that downloads cleanly wins. These are the canonical hero images
# from the Venezuelan brand sites at the time of writing — if a model
# changes its hero shot, edit this map.
SOURCES: dict[str, list[str]] = {
    # MG
    "mg-3":            ["https://mgvzla.com/wp-content/uploads/2024/06/MG3-2024-rojo-frente.png"],
    "mg-3-hybrid":     ["https://mgvzla.com/wp-content/uploads/2024/12/MG3-Hybrid-rojo-frente.png"],
    "mg-5":            ["https://mgvzla.com/wp-content/uploads/2024/06/MG5-2024-blanco-frente.png"],
    "mg-gt":           ["https://mgvzla.com/wp-content/uploads/2024/06/MG-GT-rojo.png"],
    "mg-zs":           ["https://mgvzla.com/wp-content/uploads/2025/01/MG-ZS-2025.png"],
    "mg-zs-ev":        ["https://mgvzla.com/wp-content/uploads/2024/06/MG-ZSEV-blanco.png"],
    "mg-rx5":          ["https://mgvzla.com/wp-content/uploads/2024/06/MG-RX5-blanco.png"],
    "mg-rx8":          ["https://mgvzla.com/wp-content/uploads/2024/06/MG-RX8-negro.png"],
    "mg-rx9":          ["https://mgvzla.com/wp-content/uploads/2024/12/MG-RX9-azul.png"],
    "mg-cyberster":    ["https://mgvzla.com/wp-content/uploads/2024/12/Cyberster-rojo.png"],
    # Maxus
    "maxus-d60":       ["https://maxusve.com/wp-content/uploads/2025/05/D60_DSC_3609-200x167_2.png"],
    "maxus-d90":       ["https://maxusve.com/wp-content/uploads/2025/05/DSC_0191_250X154.png"],
    "maxus-t60":       ["https://maxusve.com/wp-content/uploads/2025/05/T60_2025.png",
                        "https://maxusve.com/wp-content/uploads/2025/05/MENU_DSC_7470_t60.png"],
    "maxus-t90":       ["https://maxusve.com/wp-content/uploads/2024/07/T90-MENU.png"],
    "maxus-g10":       ["https://maxusve.com/wp-content/uploads/2024/07/G10-MENU.png"],
    "maxus-v80":       ["https://maxusve.com/wp-content/uploads/2024/07/V80-MENU.png"],
    "maxus-serie-c":   ["https://maxusve.com/wp-content/uploads/2024/07/Serie-C100-MENU.png"],
    "maxus-serie-s":   ["https://maxusve.com/wp-content/uploads/2024/07/Serie-S-MENU.png"],
    "maxus-serie-h":   ["https://maxusve.com/wp-content/uploads/2024/07/Serie-H-MENU.png"],
}

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


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download even if file exists")
    ap.add_argument("--only", nargs="*", help="only fetch these model ids")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / "_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try: manifest = json.loads(manifest_path.read_text())
        except Exception: pass

    targets = args.only or list(SOURCES.keys())
    ok = bad = skipped = 0
    for mid in targets:
        urls = SOURCES.get(mid)
        if not urls:
            print(f"  ?  {mid}: no source configured")
            bad += 1
            continue
        # Pick extension from first candidate
        dest = OUT_DIR / f"{mid}{ext_from_url(urls[0])}"
        if dest.exists() and not args.force:
            print(f"  =  {mid}: already have {dest.name}")
            skipped += 1
            continue

        for url in urls:
            print(f"  ↓  {mid}: {url}")
            success, info = download(url, dest)
            if success:
                manifest[mid] = {"source": url, "file": dest.name}
                print(f"      → saved {dest.name} ({info})")
                ok += 1
                break
            else:
                print(f"      ! {info}")
        else:
            print(f"  X  {mid}: no candidate URL worked")
            bad += 1
        time.sleep(0.4)  # be polite

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nDone: {ok} ok, {bad} failed, {skipped} skipped")
    print(f"Manifest: {manifest_path}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
