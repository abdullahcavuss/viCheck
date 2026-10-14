@echo off
REM viCheck - builds dist\viCheck\viCheck.exe (Windows, Python 3.9+ required only for building)
setlocal
cd /d "%~dp0"
if not exist "third_party\pylabview\pylabview\readRSRC.py" (
    echo Fetching pylabview ^(git submodule^)...
    git submodule update --init || (echo pylabview is missing. Clone with: git clone --recursive https://github.com/abdullahcavuss/viCheck.git & pause & exit /b 1)
)
if not exist ".venv\Scripts\python.exe" (
    echo Creating the build environment...
    python -m venv .venv || (echo Python not found. Install Python 3.9+ from https://www.python.org & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller || (pause & exit /b 1)
".venv\Scripts\python.exe" -m PyInstaller vicheck.spec --noconfirm --clean || (pause & exit /b 1)
echo Zipping dist\viCheck-win64.zip ...
powershell -NoProfile -Command "Compress-Archive -Path 'dist\viCheck' -DestinationPath 'dist\viCheck-win64.zip' -Force" || echo Could not create the zip ^(the folder is still usable^).
echo.
echo ============================================================
echo  Done:  %~dp0dist\viCheck\viCheck.exe
echo  On another PC: copy the whole dist\viCheck folder, or unzip dist\viCheck-win64.zip
echo ============================================================
pause
