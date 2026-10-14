# Third-party notices

viCheck is licensed under the MIT License (see `LICENSE`). It uses the following third-party software.

## Included as a git submodule

### pylabview — `third_party/pylabview/`

- Source: https://github.com/abdullahcavuss/pylabview (branch `heap-descriptions`), a fork of
  https://github.com/mefistotelis/pylabview
- License: MIT — full text in `third_party/pylabview/LICENSE`
- Copyright (C) 2013 Jessica Creighton; Copyright (C) 2019-2020 Mefistotelis
- The fork adds heap value descriptions, the `--tolerant` option and two crash fixes; see its README.

### Tom Thumb font — `third_party/pylabview/pylabview/assets/tom-thumb.*`

- Author: Robey Pointer
- License: MIT (may also be used under CC0 or CC-BY 3.0) — see `third_party/pylabview/pylabview/assets/tom-thumb.txt`

## Installed separately (via `pip install -r requirements.txt`, not redistributed here)

| Package | License |
|---|---|
| Flask (and its dependencies Werkzeug, Jinja2, MarkupSafe, itsdangerous, click, blinker) | BSD-3-Clause |
| Pillow | MIT-CMU (HPND) |
| waitress | ZPL 2.1 |
| pywebview | BSD-3-Clause |
| PyInstaller (only for building the exe) | GPL-2.0 with bootloader exception |

## Not included

viCheck does not contain or redistribute any National Instruments software or files. Primitive names are read at
run time from the function palettes of the LabVIEW installation on the user's own computer and stored only in the
user's local data folder (`%LOCALAPPDATA%\viCheck`).

The test VIs used during development (JKI State Machine, NI LabVIEW Icon Editor) are not part of the repository.
