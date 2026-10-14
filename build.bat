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
REM --- installer (Inno Setup 6; skipped when it is not installed)
for /f "usebackq delims=" %%v in (`.venv\Scripts\python.exe -c "import re;print(re.search('^VERSION = .(.+?).$',open('app.py',encoding='utf-8').read(),re.M).group(1))"`) do set VER=%%v
set ISCC=
for %%p in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do if exist %%p set ISCC=%%p
if defined ISCC (
    echo Building the installer ^(viCheck %VER%^)...
    %ISCC% /Q /DAppVersion=%VER% installer\viCheck.iss && set SETUP=dist\viCheck-Setup-%VER%.exe
) else (
    echo Inno Setup 6 not found - no installer. Install it with:  winget install JRSoftware.InnoSetup
)
echo.
echo ============================================================
echo  Done:  %~dp0dist\viCheck\viCheck.exe
echo  On another PC: copy the whole dist\viCheck folder, or unzip dist\viCheck-win64.zip
if defined SETUP echo  Installer:     %~dp0%SETUP%
echo ============================================================
pause
