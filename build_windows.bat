@echo off
REM Build Windows portable app (run on Windows 10/11 with Python 3.10+)
setlocal
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1
python scripts/collect_licenses.py
if errorlevel 1 exit /b 1
python -m PyInstaller --noconfirm polar.spec
if errorlevel 1 exit /b 1

echo.
echo Build complete: dist\PolarH10Monitor\PolarH10Monitor.exe
echo Double-click PolarH10Monitor.exe to run. Logs save next to the exe.
pause
