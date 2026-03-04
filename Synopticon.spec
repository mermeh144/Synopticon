# -*- mode: python ; coding: utf-8 -*-
"""
Synopticon – PyInstaller spec file
===================================
Usage:
    pyinstaller Synopticon.spec

Produces a single Synopticon.exe in the dist/ folder.
"""

import os

block_cipher = None

# ── Paths ────────────────────────────────────────────────────────────────────
SCRIPT = 'synopticon.py'

# Bundle optional data files if they exist next to the script
datas = []

# Bundle skins/ folder if present
if os.path.isdir('skins'):
    for root, dirs, files in os.walk('skins'):
        for f in files:
            src = os.path.join(root, f)
            dst = root  # preserve folder structure
            datas.append((src, dst))

# Bundle icon if present
if os.path.isfile('synopticon.ico'):
    datas.append(('synopticon.ico', '.'))

# ── Analysis ─────────────────────────────────────────────────────────────────
a = Analysis(
    [SCRIPT],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'PIL.ImageFont',
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

# Try to add tkinterdnd2 as a hidden import (optional dependency)
try:
    import tkinterdnd2
    a.hiddenimports.append('tkinterdnd2')
except ImportError:
    pass

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── Single-file EXE ─────────────────────────────────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Synopticon',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,              # windowed (no terminal)
    disable_windowed_traceback=False,
    icon='synopticon.ico' if os.path.isfile('synopticon.ico') else None,
)
