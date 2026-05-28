# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['reporte_gui\\main.py'],
    pathex=['.\\reporte_gui'],
    binaries=[],
    datas=[('img', 'img')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dependencias de desarrollo/pruebas
        'pytest',
        '_pytest',
        'pygments',
        'pluggy',
        'iniconfig',
        # Backends cientificos/opcionales no usados por la app de escritorio
        'matplotlib',
        'scipy',
        'pandas',
        'pyarrow',
        'polars',
        'numba',
        'skimage',
        'IPython',
        'notebook',
        'jupyter',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ReporteDocente',
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
    icon=['img\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ReporteDocente',
)
