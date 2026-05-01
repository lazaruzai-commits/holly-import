"""Download brand-supplied colour visualizer videos for the per-model pages.

Holly Import is an authorized MG dealer; mgmotor.me's CDN at
media-hub-prod.mgmotor.me/visualiser/<model><colour>.mp4 hosts the
360-degree turntable clips that go on each model's "Find your style"
section. We self-host so the page is fast and not dependent on the
third party's uptime.

Run:
    python scripts/fetch_visualizer.py            # download all
    python scripts/fetch_visualizer.py --force    # re-download
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "video" / "visualizer"

# (model_id, colour_slug, source_filename)
SOURCES = [
    ("mg-zs",  "black",  "zsblack.mp4"),
    ("mg-zs",  "white",  "zswhite.mp4"),
    ("mg-zs",  "red",    "zsred.mp4"),
    ("mg-zs",  "silver", "zssilver.mp4"),
    ("mg-zs",  "grey",   "zsgrey.mp4"),
    ("mg-rx9", "black",  "rx9black.mp4"),
    ("mg-rx9", "white",  "rx9white.mp4"),
    ("mg-rx9", "silver", "rx9silver.mp4"),
    ("mg-rx9", "grey",   "rx9grey.mp4"),
    ("mg-rx9", "green",  "rx9green.mp4"),
]
BASE = "https://media-hub-prod.mgmotor.me/visualiser/"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = bad = skipped = 0
    for model_id, colour, source_name in SOURCES:
        dest = OUT_DIR / f"{model_id}-{colour}.mp4"
        if dest.exists() and not args.force:
            print(f"  =  {dest.name}: already have ({dest.stat().st_size} bytes)")
            skipped += 1
            continue
        url = BASE + source_name
        print(f"  >  {dest.name}: {url}")
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (HollyImport)"})
            with urlopen(req, timeout=120) as r:
                data = r.read()
            dest.write_bytes(data)
            print(f"     -> {len(data)} bytes")
            ok += 1
        except Exception as e:
            print(f"     ! {e}")
            bad += 1

    print(f"\nDone: {ok} ok, {bad} failed, {skipped} skipped")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
