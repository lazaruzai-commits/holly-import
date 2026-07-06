#!/usr/bin/env python3
"""Render a DoorDash receipt email (raw HTML) to PDF via headless Chromium.

Usage: render_pdf.py input.html output.pdf [more pairs...]
       render_pdf.py --dir receipts_html/ out_pdfs/

The HTML is rendered exactly as received — receipts must not be altered.
Chromium is located from $CHROMIUM_BIN, /opt/pw-browsers (Claude Code cloud
environments), or PATH.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_chromium() -> str:
    cand = os.environ.get("CHROMIUM_BIN")
    if cand and Path(cand).exists():
        return cand
    for pattern in ("/opt/pw-browsers/chromium-*/chrome-linux/chrome",):
        import glob
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    for name in ("chromium", "chromium-browser", "google-chrome"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("error: no Chromium binary found (set CHROMIUM_BIN)")


def render(chromium: str, html_path: Path, pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as profile:
        cmd = [
            chromium,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            "--virtual-time-budget=8000",
            html_path.resolve().as_uri(),
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        raise RuntimeError(f"suspiciously small or missing PDF: {pdf_path}")


def main(argv: list[str]) -> None:
    chromium = find_chromium()
    if argv and argv[0] == "--dir":
        src, dst = Path(argv[1]), Path(argv[2])
        pairs = [(p, dst / (p.stem + ".pdf")) for p in sorted(src.glob("*.html"))]
    else:
        if len(argv) % 2:
            sys.exit(__doc__)
        pairs = [(Path(argv[i]), Path(argv[i + 1])) for i in range(0, len(argv), 2)]
    for html_path, pdf_path in pairs:
        render(chromium, html_path, pdf_path)
        print(f"rendered {html_path} -> {pdf_path} ({pdf_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main(sys.argv[1:])
