"""
PDF of a report (REPORT.md / README.md + SVG images).

The Markdown is turned into a print-styled HTML page and printed by Microsoft Edge (or Chrome) in headless mode.
Edge is part of every Windows 10/11, so nothing extra has to be installed or bundled, and the SVG images stay
vector graphics in the PDF (sharp at any zoom, text can be searched).

Page layout (A4 landscape):
- every VI starts on a new page;
- the overview image (whole diagram, A and B) is fitted to the page;
- the detail images (crops around the changes, see svgrender) are printed at about 1:1, so the diagram is readable
  even when the overview of a large VI is tiny.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from . import mdlite

PRINT_CSS = """
@page { size: A4 landscape; margin: 11mm 12mm 12mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Segoe UI", Arial, "DejaVu Sans", sans-serif; font-size: 9.5pt; color: #1c2128; margin: 0; line-height: 1.4; }
h1 { font-size: 17pt; margin: 0 0 6pt; }
h2 { font-size: 13pt; margin: 14pt 0 6pt; border-bottom: 1px solid #d0d7de; padding-bottom: 3pt; break-after: avoid; }
h3 { font-size: 12pt; margin: 8pt 0 4pt; break-after: avoid; }
a.pg + h3 { break-before: page; margin-top: 0; }   /* a VI with images starts on a new page */
h4 { break-after: avoid; }
p { margin: 4pt 0; }
code { font-family: Consolas, "DejaVu Sans Mono", monospace; font-size: 8.5pt; background: #f2f4f7; padding: 0 3px; border-radius: 3px; }
a { color: #0b57d0; text-decoration: none; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 8pt; }
th, td { border: 1px solid #d0d7de; padding: 3pt 6pt; vertical-align: top; text-align: left; }
th { background: #f2f4f7; }
tr { break-inside: avoid; }
ul, ol { margin: 3pt 0 6pt; padding-left: 20pt; }
li { margin: 1pt 0; break-inside: avoid; }
hr { display: none; }
blockquote { margin: 4pt 0; padding: 4pt 8pt; border-left: 3px solid #d97706; background: #fff8eb; }
pre.diff { font: 8pt Consolas, monospace; background: #f6f8fa; padding: 6pt; white-space: pre-wrap; break-inside: avoid; }
pre.diff .add { color: #1a7f37; } pre.diff .del { color: #cf222e; } pre.diff .hunk { color: #8250df; }
details > summary { font-weight: 600; margin: 4pt 0; list-style: none; }
/* images: never split, never wider than the page; the overview is fitted, details keep their 1:1 size */
p:has(img) { margin: 2pt 0 8pt; break-inside: avoid; }
.fig { break-inside: avoid; }
img { display: block; max-width: 100%; max-height: 168mm; object-fit: contain; object-position: left top; break-inside: avoid; }
p:has(> i:only-child) { break-after: avoid; color: #57606a; }
.cover-note { color: #57606a; font-size: 8.5pt; }
"""


def find_browser():
    """Edge or Chrome (VICHECK_BROWSER overrides). Returns the executable or None."""
    env = os.environ.get("VICHECK_BROWSER")
    if env and os.path.exists(env):
        return env
    cands = []
    if os.name == "nt":
        for var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                          os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    elif sys.platform == "darwin":
        cands += ["/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for c in cands:
        if os.path.exists(c):
            return c
    for name in ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium", "chromium-browser"):
        p = shutil.which(name)
        if p:
            return p
    return None


def build_html(md, title, lang="en"):
    body = mdlite.render(md, "")
    body = body.replace(' loading="lazy"', "")   # lazy images may not be loaded before printing
    # VI sections with images start on a new page; short text-only sections just follow each other
    parts = re.split(r'(<a id="vi-[A-Za-z0-9_-]+"></a>)', body)
    for k in range(1, len(parts), 2):
        if "<img" in parts[k + 1]:
            parts[k] = parts[k].replace("<a ", '<a class="pg" ', 1)
    body = "".join(parts)
    # a caption ("View 1 …", "Detail 2 …") and its image stay together on one page
    body = re.sub(r"(<p><i>[^<]*(?:<[^>]+>[^<]*)*?</i></p>)\s*(<p>(?:<a [^>]*>)?<img [^>]*>(?:</a>)?</p>)",
                  r'<div class="fig">\1\2</div>', body)
    # drop the hint meant for the browser preview ("click to open it full size…")
    body = re.sub(r"<p><i>(The image is an SVG|Resim SVG)[^<]*</i></p>", "", body)
    return ('<!doctype html><html lang="%s"><head><meta charset="utf-8"><title>%s</title><style>%s</style></head>'
            '<body>%s</body></html>' % (lang, html.escape(title), PRINT_CSS, body))


def make_pdf(md, out_dir, pdf_name, title, lang="en", timeout=600):
    """Writes <out_dir>/<pdf_name> from Markdown whose image paths are relative to out_dir. Returns the path."""
    exe = find_browser()
    if not exe:
        raise RuntimeError("PDF needs Microsoft Edge or Google Chrome")
    html_path = os.path.join(out_dir, "_print.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(md, title, lang))
    pdf_path = os.path.join(out_dir, pdf_name)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    url = "file:///" + os.path.abspath(html_path).replace(os.sep, "/").lstrip("/")
    # a private profile: otherwise a running Edge would take over the command and no PDF would be written
    profile = tempfile.mkdtemp(prefix="vicheck-pdf-")
    args = [exe, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--allow-file-access-from-files", "--user-data-dir=" + profile,
            "--no-pdf-header-footer", "--print-to-pdf-no-header", "--print-to-pdf=" + pdf_path, url]
    if not sys.platform.startswith("win") and hasattr(os, "geteuid") and os.geteuid() == 0:
        args.insert(1, "--no-sandbox")
    flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
    try:
        r = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, creationflags=flags)
        # Edge can return before the file is closed
        for _ in range(50):
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                break
            time.sleep(0.1)
        if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
            err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            raise RuntimeError("the browser did not write the PDF" + (": " + err[-1] if err else ""))
    finally:
        shutil.rmtree(profile, ignore_errors=True)
        try:
            os.remove(html_path)
        except OSError:
            pass
    return pdf_path
