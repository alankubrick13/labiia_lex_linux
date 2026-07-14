# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('/home/alankubrick/Documentos/lab/labiia_lex/src', 'src'), ('/home/alankubrick/Documentos/lab/labiia_lex/Rscripts', 'Rscripts'), ('/home/alankubrick/Documentos/lab/labiia_lex/resources', 'resources'), ('/home/alankubrick/Documentos/lab/labiia_lex/dictionaries', 'dictionaries'), ('/home/alankubrick/Documentos/lab/labiia_lex/docs', 'docs')]
binaries = []
hiddenimports = ['customtkinter', 'PIL', 'networkx']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['/home/alankubrick/Documentos/lab/labiia_lex/main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='labiia_lex',
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
    name='labiia_lex',
)
