# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

from pathlib import Path

project_root = Path.cwd()
version_path = project_root / 'build' / 'app_version_info_os.txt'
version_path.parent.mkdir(exist_ok=True)
version_path.write_text("""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=(2, 2, 0, 0),
    prodvers=(2, 2, 0, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', 'OS PPP'),
         StringStruct('FileDescription', 'OS PPP'),
         StringStruct('FileVersion', '2.2.0'),
         StringStruct('InternalName', 'OS_PPP'),
         StringStruct('OriginalFilename', 'OS_PPP.exe'),
         StringStruct('ProductName', 'OS PPP'),
         StringStruct('ProductVersion', '2.2.0')]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
""", encoding='utf-8')

a = Analysis(
    ['app/main_os.py'],
    pathex=[str(project_root / 'app')],
    binaries=[],
    datas=[
        ('app/assets', 'assets'),
        # Dados operacionais locais nunca devem integrar o instalador.
    ],
    hiddenimports=[
        'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'reportlab', 'openpyxl', 'docx', 'PIL'
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
    name='OS_PPP',
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
    icon='app/assets/icons/app.ico',
    version=str(version_path),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OS_PPP',
)
