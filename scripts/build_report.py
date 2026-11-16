#!/usr/bin/env python3
"""Render docs/report/report.md to report.pdf (Markdown -> HTML -> headless Chrome/Edge)."""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

CSS = """
@page { size: A4; margin: 16mm 16mm 16mm 16mm; }
body { font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 10pt; line-height: 1.38; color: #111; }
h1 { font-size: 17pt; margin: 0 0 2pt 0; }
h2 { font-size: 12.5pt; margin: 12pt 0 4pt 0; border-bottom: 1px solid #bbb; padding-bottom: 2pt; }
h3 { font-size: 10.5pt; margin: 8pt 0 3pt 0; }
p { margin: 3pt 0 5pt 0; text-align: justify; }
ul, ol { margin: 2pt 0 5pt 0; padding-left: 18pt; }
li { margin: 1pt 0; }
table { border-collapse: collapse; margin: 5pt auto 7pt auto; font-size: 8.6pt; }
th, td { border: 1px solid #999; padding: 1.5pt 5pt; text-align: right; }
th { background: #eee; }
td:first-child, th:first-child { text-align: left; }
code { font-family: Consolas, "Courier New", monospace; font-size: 8.8pt; }
pre { background: #f5f5f5; padding: 4pt 6pt; font-size: 8.3pt; line-height: 1.25; white-space: pre-wrap; }
img { display: block; margin: 4pt auto; }
.figs { display: flex; gap: 6pt; justify-content: center; }
.figs img { width: 49%; }
.cap { text-align: center; font-size: 8.6pt; color: #333; margin-top: 0; }
.subtitle { color: #333; margin-bottom: 8pt; }
"""

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "google-chrome", "chromium", "chromium-browser", "microsoft-edge",
]


def find_browser():
    for b in BROWSERS:
        if Path(b).is_file() or shutil.which(b):
            return b
    sys.exit('No Chrome/Edge/Chromium found for PDF printing')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input', type=Path, default=Path('docs/report/report.md'))
    ap.add_argument('--output', type=Path, default=Path('report.pdf'))
    a = ap.parse_args()
    import markdown

    body = markdown.markdown(a.input.read_text(encoding='utf-8'), extensions=['tables', 'fenced_code', 'md_in_html'])
    html = f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Crazy Taxi – Phase 1</title><style>{CSS}</style></head><body>{body}</body></html>'
    with tempfile.TemporaryDirectory() as tmp:
        # keep relative image paths working by writing next to the markdown file
        page = a.input.parent / '_report.html'
        page.write_text(html, encoding='utf-8')
        try:
            out = a.output.resolve()
            subprocess.run([find_browser(), '--headless', '--disable-gpu', '--no-pdf-header-footer',
                            f'--user-data-dir={tmp}', f'--print-to-pdf={out}', page.resolve().as_uri()],
                           check=True, capture_output=True, timeout=120)
        finally:
            page.unlink(missing_ok=True)
    print(f'Wrote {a.output}')


if __name__ == '__main__':
    main()
