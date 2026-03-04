# synopticon.spec
# PyInstaller spec for Synopticon
# Run: pyinstaller synopticon.spec

import os
block_cipher = None

a = Analysis(
    ['synopticon.py'],
    pathex=[],
    binaries=[
        # Bundle ffmpeg.exe if present next to the spec file
        *([('ffmpeg.exe', '.')] if os.path.isfile('ffmpeg.exe') else []),
    ],
    datas=[
        # Bundle the skins folder
        ('skins', 'skins'),
        # Bundle the icon
        ('synopticon.ico', '.'),
    ],
    hiddenimports=[
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.ImageDraw',
        'PIL.ImageFont',
        'PIL._tkinter_finder',
        'tkinter',
        'tkinter.filedialog',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'pandas', 'scipy',
        'PyQt5', 'PyQt6', 'wx', 'gi',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    console=False,          # No console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='synopticon.ico',
    version_file=None,
)
