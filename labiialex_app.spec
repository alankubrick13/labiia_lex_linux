# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
icon_path = Path('assets/icon.ico')
icon_value = str(icon_path) if icon_path.exists() else None

similitude_hiddenimports = collect_submodules('src.analysis.similitude')
semantic_hiddenimports = (
    collect_submodules('sklearn.feature_extraction')
    + collect_submodules('sklearn.decomposition')
    + collect_submodules('sklearn.utils')
    + collect_submodules('yake')
)
datas = [
    ('Rscripts', 'Rscripts'),
    ('dictionaries', 'dictionaries'),
    ('src', 'src'),
    ('assets', 'assets'),
    ('docs', 'docs'),
    ('VERSION', '.'),
    ('config.json', '.'),
    ('resources/gephi_runner', 'resources/gephi_runner'),
    ('resources/jre17', 'resources/jre17'),
] + collect_data_files('yake')

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=similitude_hiddenimports + semantic_hiddenimports + [
        'customtkinter',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'pdfplumber',
        'pdfminer',
        'pdfminer.high_level',
        'pdfminer.layout',
        'docx',
        'docx.api',
        'docx.opc.package',
        'docx.oxml',
        'docx.parts.document',
        'lxml',
        'lxml.etree',
        'openpyxl',
        'openpyxl.workbook.workbook',
        'chardet',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.messagebox',
        'src.core',
        'src.importers',
        'src.analysis',
        'src.ui',
        'src.ui.dialogs',
        'src.ui.widgets',
        'src.utils',
        'src.visualization',
        'src.visualization.r_integration',
        'community',
        'adjustText',
        'networkx',
        'numpy',
        'scipy',
        'matplotlib',
        'pandas',
        'cleantext',
        'tkinterweb',
        'nltk',
        'spacy',
        'unidecode',
        'tqdm',
        'sqlite3',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'psycopg2', 'pymysql', 'pyarrow', 'sqlalchemy',
        'statsmodels', 'seaborn',
        'html5lib', 'xlrd', 'xlwt',
        'yaml', 'jsonschema',
        'pytest', 'hypothesis', 'coverage',
        'IPython', 'notebook', 'jupyter',
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
    [],
    exclude_binaries=True,
    name='LabiiaLex',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_value,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='LabiiaLex',
)
