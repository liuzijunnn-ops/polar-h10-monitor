# PyInstaller spec — build on Windows: pyinstaller polar.spec
# Output: dist/PolarH10Monitor/PolarH10Monitor.exe

import sys
from pathlib import Path

block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)],
    binaries=[],
    datas=[],
    hiddenimports=[
        'bleak',
        'bleak.backends.winrt',
        'bleak.backends.corebluetooth',
        'bleak.backends.bluezdbus',
        'polar_python',
        'polar_python.parsers',
        'polar_python.parsers.polar',
        'polar_python.parsers.hr',
        'polar_python.parsers.compression',
        'polar_python.models',
        'polar_python.models.hr_data',
        'polar_python.models.ecg_data',
        'polar_python.models.acc_data',
        'polar_python.device',
        'scipy',
        'scipy.signal',
        'numpy',
        'pyqtgraph',
        'pyqtgraph.graphicsItems',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'paths',
        'hrv',
        'recorder',
        'device_worker',
        'gui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PolarH10Monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PolarH10Monitor',
)
