#!/bin/bash
# Build macOS app bundle (run on macOS)
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm polar.spec

echo ""
echo "Build complete: dist/PolarH10Monitor/PolarH10Monitor"
echo "Logs save next to the executable."
