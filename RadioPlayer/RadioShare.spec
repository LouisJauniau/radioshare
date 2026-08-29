# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
hiddenimports += collect_submodules('vlc')


a = Analysis(
    ['C:/Users/Louis/RadioShare/RadioPlayer/app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Louis/RadioShare/RadioPlayer/donnees/stations.json', 'donnees')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5.QtWebEngineWidgets', 'PyQt5.QtWebEngine', 'PyQt5.QtWebEngineCore', 'PyQt5.QtQml', 'PyQt5.QtQuick', 'PyQt5.QtQuick3D', 'PyQt5.QtMultimedia', 'PyQt5.QtBluetooth', 'PyQt5.QtNfc', 'PyQt5.QtPositioning', 'PyQt5.QtSql', 'PyQt5.QtTest', 'PyQt5.QtDesigner', 'PyQt5.QtHelp', 'PyQt5.Qt3DCore', 'PyQt5.QtCharts', 'PyQt5.QtDataVisualization', 'tkinter', 'matplotlib', 'numpy', 'pandas', 'PIL', 'scipy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RadioShare',
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RadioShare',
)
