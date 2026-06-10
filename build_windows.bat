@echo off
REM Build Windows portable app (run on Windows 10/11 with Python 3.10+)
setlocal
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm polar.spec

echo.
echo Build complete: dist\PolarH10Monitor\PolarH10Monitor.exe
echo Double-click PolarH10Monitor.exe to run. Logs save next to the exe.
pause
