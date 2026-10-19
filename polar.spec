# PyInstaller spec — build on Windows: pyinstaller polar.spec
# Output: dist/PolarH10Monitor/PolarH10Monitor.exe

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = Path(SPECPATH)


def safe_collect_submodules(package):
    try:
        return collect_submodules(package)
    except Exception:
        return []


hiddenimports = sorted(set([
    'bleak',
    'bleak.backends.winrt',
    'bleak.backends.winrt.client',
    'bleak.backends.winrt.scanner',
    'bleak.backends.winrt.util',
    'bleak.backends.corebluetooth',
    'bleak.backends.bluezdbus',
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
    'polar_ble',
    'hrv',
    'recorder',
    'device_worker',
    'gui',
] + safe_collect_submodules('bleak.backends.winrt')
  + safe_collect_submodules('winrt')
  + safe_collect_submodules('bleak_winrt')))

notices = root / 'build' / 'dependency-licenses'
if not (notices / 'INDEX.json').is_file():
    raise SystemExit('Run python scripts/collect_licenses.py before PyInstaller.')
package_data = [
    (str(root / 'README.md'), '.'),
    (str(root / 'LICENSE'), '.'),
    (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
    (str(root / 'licenses'), 'licenses'),
    (str(root / 'docs'), 'docs'),
    (str(notices), 'dependency-licenses'),
]

a = Analysis(
    [str(root / 'main.py')],
    pathex=[str(root)],
    binaries=[],
    datas=package_data,
    hiddenimports=hiddenimports,
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
