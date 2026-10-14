# viCheck — LabVIEW VI / folder comparison

**English** · [Türkçe](README.tr.md)

Compares two VIs or two folders. Block diagrams are parsed **without LabVIEW** and drawn side by side as **SVG**.
The engine (pylabview + diff + drawing) is the same as in the VIVER project; viCheck only compares — no repositories or commits.

## Installation — building the exe

pylabview is included as a **git submodule** (see [pylabview](#pylabview)); clone the repository with it:

```
git clone --recursive https://github.com/abdullahcavuss/viCheck.git
```

(If you cloned without `--recursive`, run `git submodule update --init`; `build.bat` / `run.bat` also do this when it is missing.)

1. Double-click **`build.bat`** in this folder (Python 3.9+ is needed only for building).
2. Result: **`dist\viCheck\viCheck.exe`**, and the same folder zipped as **`dist\viCheck-win64.zip`**.

To try it without building: `run.bat`.

### Running on another computer

Copy the whole `dist\viCheck` folder (or `viCheck-win64.zip` and unzip it) and start `viCheck.exe`. Nothing has to be
installed: Python, Flask and pylabview are inside the folder, and **LabVIEW is not needed**.

- Windows 10 or 11, 64-bit.
- The window uses Microsoft Edge WebView2, which is part of Windows 11 and of an up-to-date Windows 10. Without it
  viCheck opens in an Edge/Chrome window or the default browser instead.
- PDF reports are printed by Microsoft Edge (or Google Chrome).
- The exe is not signed, so Windows SmartScreen may warn on the first start: *More info → Run anyway*.
- The `.exe` alone does not work: it needs the `_internal` folder next to it.
- Settings and cache are kept per user in `%LOCALAPPDATA%\viCheck`; primitive names are read from LabVIEW's
  palettes only if LabVIEW is installed on that computer.

## Usage

- Choose a VI or a folder for **A** (old) and **B** (new): *Choose VI… / Choose folder…*, paste a path, or drop the file/folder
  on its box (drop two items at once to fill A and B). **Compare**.
- **Two VIs** → block diagram diff: list of changes, diagrams side by side, added/removed/modified items in color.
  `j`/`k` move through the changes.
- **Two folders** → files are matched by relative path: modified, only in A, only in B, moved, and identical files.
  A summary for every VI (content / visual-layout / re-saved only). Text diff for text files.
- **SVG**
  - Right-click → **Inspect** in the window to look at the SVG elements, or **↗ Open in browser** and use F12.
  - **⬇ Save view as SVG**: saves the A + B view exactly as shown, as one SVG file.
  - **🖼 Export SVG**: draws the A and B diagrams with numbered change markers into SVG files (+ README.md).
  - In a folder comparison, **📄 Report with SVG images…**: a Markdown report with SVGs for every changed VI (also as ZIP).
- **PDF**: **📄 PDF** in a VI comparison, *Also make a PDF* in a folder report. The PDF is printed by Microsoft Edge,
  which comes with Windows; the SVGs stay vector graphics (sharp when zoomed, text can be searched). For every VI:
  - the list of changes and the whole A and B diagram in one image (side by side or one above the other, whichever
    is drawn larger on the page);
  - **detail views**: nearby changes are grouped and each group is cropped from the same area of A and B and printed
    at about 1:1 (LabVIEW's 100 % size), so changes stay readable even when the overview of a large VI is small;
  - Stacked Sequences are shown frame by frame in the PDF by default (unfolded they get very wide and shrink on the
    page); *Stacked Sequence → Flat* is an option.
- **Sidebar**: in a VI comparison the file details at the top fold away with **▴ Hide**, giving the change list more room.
- **Primitive names**: if LabVIEW is installed, primitive names are read from its palettes on first start.
- **Language**: the interface is in English and Turkish; switch with **EN / TR** at the top right, the choice is saved.
  On first start the Windows language is used. Reports and SVG exports are written in the chosen language;
  LabVIEW's own terms (Value Change, Case Structure…) stay in English, as in LabVIEW.

### Command line / calling from LabVIEW

```
viCheck.exe "C:\old\Main.vi" "C:\new\Main.vi"
viCheck.exe "C:\project_v1" "C:\project_v2"
viCheck.exe --browser            (opens in the default browser instead of the window)
```

The same command can be run from LabVIEW with *System Exec.vi*.

## What it can read

On top of what pylabview extracts, viCheck decodes (details and evidence: `docs/reverse-engineering.md`):
property and method names of Property/Invoke Nodes, targets of reference constants, event names of Event Structure
frames (`"OK": Value Change`, `<This VI>: Panel Close?`, `Timeout`), Event Data Node fields, contents of
cluster/array/path constants, keyboard shortcuts of controls (Enter/Esc/F1) and text format changes. Event codes that
cannot be identified with certainty are shown with candidate names, e.g. `Mouse Down/Up (#8)`.

## pylabview

The library that reads VI files comes from the `heap-descriptions` branch of the
[abdullahcavuss/pylabview](https://github.com/abdullahcavuss/pylabview) fork, as a submodule (`third_party/pylabview`).
The fork adds to the original [mefistotelis/pylabview](https://github.com/mefistotelis/pylabview):

- the `--tolerant` option — VIs with inconsistent data are still read, with warnings; viCheck always uses it
- two crash fixes
- event and keyboard shortcut descriptions in extracted heap XML (as comments)

viCheck's own decoding (property/method names, event frame names, cluster values, diff) is not in pylabview but in
`engine/`. To update the fork:

```
cd third_party/pylabview
git pull
cd ../..
git add third_party/pylabview
git commit -m "Update pylabview"
```

## Test data

The VIs used during development belong to the JKI State Machine project and are not in the repository.
`python tools/make_testdata.py` downloads them into `testdata/`; expected results are in `testdata/README.md` (Turkish).

## Safety

Compared files are only read. Every VI is first copied to a private temporary folder, the copy is checked against the
hash taken at comparison time, and pylabview reads the copy in a separate process. Cache, exports and primitive names
are kept in `%LOCALAPPDATA%\viCheck` (change with the `VICHECK_DATA` environment variable).

## Window

viCheck opens in its own window using Windows' built-in **Microsoft Edge WebView2** (pywebview); the interface is the
same as in a browser. Without WebView2 it opens as an Edge/Chrome app window, or else in the default browser.

Why not Electron: the engine that reads VIs is written in Python, and Electron would still need Python bundled next to
it. This way the exe is much smaller and the interface is still Chromium based.

## Structure

```
vicheck.py        launcher: window, command line, --pylabview / --pick helper modes
app.py            web application (Flask): comparison, diff, SVG export, report
i18n.py           interface languages (English source + Turkish translation; rules for engine texts)
engine/           files.py (scan, hash, registry), lvtypes.py (type table + value decoder), vi_parser, vi_diff, render, svgrender (SVG + detail crops), changelog (report), pdfout (PDF) ...
docs/             reverse-engineering.md — fields decoded from the VI format, with evidence (Turkish)
tools/re/         format research scripts (event codes, shortcuts, heap diff, bulk regression)
tools/make_testdata.py  downloads the test VIs from the JKI repository
tools/check_i18n.py     checks that every interface text has a translation
static/, templates/   interface (diagram.js SVG renderer, vidiff.js, vicheck.js)
third_party/pylabview pylabview fork (git submodule, MIT)
testdata/         test VIs — not in the repository, created with tools/make_testdata.py
vicheck.spec, build.bat   exe packaging (PyInstaller, one folder)
```

License: MIT. pylabview (MIT) is used as a submodule; see THIRD_PARTY_NOTICES.md. LabVIEW is a trademark of National
Instruments Corporation.
