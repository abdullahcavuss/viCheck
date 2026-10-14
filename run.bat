@echo off
REM viCheck - run from source without building the exe
cd /d "%~dp0"
if not exist "third_party\pylabview\pylabview\readRSRC.py" (
    echo Fetching pylabview ^(git submodule^)...
    git submodule update --init || (echo pylabview is missing. Clone with: git clone --recursive https://github.com/abdullahcavuss/viCheck.git & pause & exit /b 1)
)
if not exist ".venv\Scripts\python.exe" (
    echo First run: creating the virtual environment...
    python -m venv .venv || (echo Python not found. Install Python 3.9+ from https://www.python.org & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (pause & exit /b 1)
)
start "" ".venv\Scripts\pythonw.exe" vicheck.py %*
