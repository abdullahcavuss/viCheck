# PyInstaller spec for viCheck  —  build with build.bat (or: pyinstaller vicheck.spec --noconfirm)
# One-folder build: viCheck.exe starts itself again for every VI it parses (pylabview runs
# in its own process), and a one-folder build starts those child processes instantly.
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

HERE = os.path.abspath(SPECPATH)
TP = os.path.join(HERE, "third_party", "pylabview")   # git submodule: our pylabview fork (repo root)
if not os.path.isfile(os.path.join(TP, "pylabview", "readRSRC.py")):
    raise SystemExit("third_party/pylabview is empty - run: git submodule update --init")

hidden = collect_submodules("engine") + ["waitress", "flask", "jinja2", "PIL.ImageFont", "tkinter", "tkinter.filedialog"]
import sys
sys.path.insert(0, TP)
hidden += collect_submodules("pylabview")
try:
    hidden += collect_submodules("webview")
except Exception:
    pass

datas = [
    (os.path.join(HERE, "templates"), "templates"),
    (os.path.join(HERE, "static"), "static"),
    (os.path.join(TP, "pylabview", "assets"), os.path.join("pylabview", "assets")),
    (os.path.join(TP, "LICENSE"), os.path.join("third_party", "pylabview")),
    (os.path.join(HERE, "LICENSE"), "."),
    (os.path.join(HERE, "THIRD_PARTY_NOTICES.md"), "."),
]
try:
    datas += collect_data_files("webview")
except Exception:
    pass

a = Analysis(
    ["vicheck.py"],
    pathex=[HERE, TP],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    excludes=["matplotlib", "numpy", "pandas", "scipy", "PyQt5", "PyQt6", "PySide2", "PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="viCheck",
    icon=os.path.join(HERE, "static", "icon.ico"),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="viCheck")
