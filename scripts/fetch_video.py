"""Download brand-supplied marketing video for the homepage hero.

Holly Import is an authorized MG dealer. The hero video is sourced from
the MG Trinidad & Tobago dealer site (mgmotortt.com) which serves the
same brand-supplied marketing content.

Run:  python scripts/fetch_video.py            # download hero.mp4
      python scripts/fetch_video.py --force    # re-download
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "static" / "video"

SOURCES = {
    "hero.mp4": "https://mgmotortt.com/wp-content/uploads/2025/07/Homepage-video2.mp4",
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ok = bad = skipped = 0
    for name, url in SOURCES.items():
        dest = OUT_DIR / name
        if dest.exists() and not args.force:
            print(f"  =  {name}: already have ({dest.stat().st_size} bytes)")
            skipped += 1
            continue
        print(f"  >  {name}: {url}")
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
