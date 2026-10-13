@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d %~dp0

REM ============================================================
REM BUILD EXE - Configuração do nome do aplicativo e logo/ícone
REM ============================================================
REM Ajuste aqui se quiser mudar o nome final do executável:
set "APP_EXE_NAME=Orcamentos_PPP_Enterprise"
set "APP_DISPLAY_NAME=Orçamentos PPP Enterprise"
set "APP_VERSION=1.0.0"
set "COMPANY_NAME=DA SAFRA"

REM Arquivo principal usado somente se o .spec não existir:
set "MAIN_SCRIPT=app.py"

REM Arquivo spec atual do projeto:
set "SPEC_FILE=Orcamentos_PPP_Enterprise.spec"

REM Locais aceitos para logo/ícone. Preferência: .ico.
REM Também aceita .png/.jpg/.jpeg e converte para .ico automaticamente.
set "ICON_CANDIDATES=assets\logo.ico;logo.ico;assets\app.ico;app.ico;assets\logo.png;logo.png;assets\logo.jpg;logo.jpg;assets\logo.jpeg;logo.jpeg"

if not exist .venv (
  py -3.12 -m venv .venv
)

call .venv\Scripts\activate
if errorlevel 1 (
  echo [ERRO] Não foi possível ativar o ambiente virtual.
  pause
  exit /b 1
)

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller pillow

set "PREP_SCRIPT=%TEMP%\prepare_pyinstaller_build_%RANDOM%.py"
set "BUILD_ENV_FILE=%TEMP%\pyinstaller_build_env_%RANDOM%.bat"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$code = @'
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()
APP_EXE_NAME = os.environ.get('APP_EXE_NAME', 'Orcamentos_PPP_Enterprise').strip() or 'Orcamentos_PPP_Enterprise'
APP_DISPLAY_NAME = os.environ.get('APP_DISPLAY_NAME', APP_EXE_NAME).strip() or APP_EXE_NAME
APP_VERSION = os.environ.get('APP_VERSION', '1.0.0').strip() or '1.0.0'
COMPANY_NAME = os.environ.get('COMPANY_NAME', '').strip()
SPEC_FILE = os.environ.get('SPEC_FILE', '').strip()
MAIN_SCRIPT = os.environ.get('MAIN_SCRIPT', 'app.py').strip() or 'app.py'
ICON_CANDIDATES = [x.strip() for x in os.environ.get('ICON_CANDIDATES', '').split(';') if x.strip()]
BUILD_ENV_FILE = Path(os.environ.get('BUILD_ENV_FILE', str(ROOT / '_build_env.bat')))

BUILD_DIR = ROOT / 'build'
BUILD_DIR.mkdir(exist_ok=True)


def win_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace('\\', '/')
    except Exception:
        return str(path.resolve()).replace('\\', '/')


def version_tuple(version: str):
    parts = []
    for item in re.split(r'[^0-9]+', version):
        if item != '':
            parts.append(int(item[:5]))
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts[:4])


def find_icon():
    for candidate in ICON_CANDIDATES:
        path = ROOT / candidate
        if path.exists() and path.is_file():
            return path
    return None


def convert_to_ico(source: Path) -> Path:
    suffix = source.suffix.lower()
    if suffix == '.ico':
        return source
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError('Pillow não está instalado para converter a logo em .ico.') from exc

    ico_path = BUILD_DIR / 'app_icon.ico'
    img = Image.open(source).convert('RGBA')
    img.save(ico_path, format='ICO', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return ico_path


def write_version_file() -> Path:
    vt = version_tuple(APP_VERSION)
    safe_company = COMPANY_NAME or APP_DISPLAY_NAME
    version_file = BUILD_DIR / 'app_version_info.txt'
    version_file.write_text(f'''# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={vt},
    prodvers={vt},
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
        [StringStruct('CompanyName', {safe_company!r}),
         StringStruct('FileDescription', {APP_DISPLAY_NAME!r}),
         StringStruct('FileVersion', {APP_VERSION!r}),
         StringStruct('InternalName', {APP_EXE_NAME!r}),
         StringStruct('OriginalFilename', {APP_EXE_NAME + '.exe'!r}),
         StringStruct('ProductName', {APP_DISPLAY_NAME!r}),
         StringStruct('ProductVersion', {APP_VERSION!r})]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
''', encoding='utf-8')
    return version_file


def find_matching_paren(text: str, open_paren_index: int) -> int:
    depth = 0
    quote = None
    triple = False
    escape = False
    i = open_paren_index
    while i < len(text):
        ch = text[i]
        nxt3 = text[i:i+3]
        if quote:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif triple and nxt3 == quote * 3:
                quote = None
                triple = False
                i += 2
            elif not triple and ch == quote:
                quote = None
        else:
            if nxt3 in ("'''", '"""'):
                quote = ch
                triple = True
                i += 2
            elif ch in ("'", '"'):
                quote = ch
                triple = False
            elif ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return -1


def replace_or_add_kw(call_text: str, key: str, value_repr: str) -> str:
    # Substitui valores comuns em spec: strings, None, True/False, números ou nomes simples.
    # Evita criar keyword duplicada quando o .spec já possui icon=None, version=None etc.
    pattern = re.compile(
        r'(?<![A-Za-z0-9_])' + re.escape(key) +
        r'\s*=\s*(?:r?([\'\"]).*?\1|None|True|False|[0-9]+|[A-Za-z_][A-Za-z0-9_\.]*)',
        re.S
    )
    if pattern.search(call_text):
        return pattern.sub(f'{key}={value_repr}', call_text, count=1)

    stripped = call_text.rstrip()
    comma = '' if stripped.endswith(',') else ','
    return stripped + f'{comma}\n    {key}={value_repr}\n'


def patch_spec(spec_path: Path, icon_path: Path | None, version_file: Path):
    text = spec_path.read_text(encoding='utf-8', errors='ignore')
    marker = 'EXE('
    start = text.find(marker)
    if start == -1:
        print('[AVISO] Não encontrei EXE(...) no .spec. O build vai continuar sem ajuste automático do .spec.')
        return

    open_idx = text.find('(', start)
    close_idx = find_matching_paren(text, open_idx)
    if close_idx == -1:
        print('[AVISO] Não consegui fechar o bloco EXE(...) no .spec. O build vai continuar sem ajuste automático do .spec.')
        return

    before = text[:open_idx + 1]
    call = text[open_idx + 1:close_idx]
    after = text[close_idx:]

    call = replace_or_add_kw(call, 'name', repr(APP_EXE_NAME))
    call = replace_or_add_kw(call, 'version', repr(win_rel(version_file)))
    if icon_path:
        call = replace_or_add_kw(call, 'icon', repr(win_rel(icon_path)))

    patched = before + call + after

    # Também ajusta o nome do COLLECT(...), quando existir build em pasta.
    patched = re.sub(r'(COLLECT\([^\)]*?name\s*=\s*)(r?)([\'\"])(.*?)(\3)',
                     lambda m: m.group(1) + repr(APP_EXE_NAME),
                     patched,
                     count=1,
                     flags=re.S)

    backup = spec_path.with_suffix(spec_path.suffix + '.bak')
    if not backup.exists():
        shutil.copy2(spec_path, backup)
    spec_path.write_text(patched, encoding='utf-8')
    print(f'[OK] .spec ajustado: {spec_path.name}')
    print(f'[OK] Backup criado/mantido: {backup.name}')


def write_env(icon_path: Path | None, version_file: Path, use_spec: bool):
    lines = [
        '@echo off',
        f'set "BUILD_USE_SPEC={1 if use_spec else 0}"',
        f'set "RESOLVED_VERSION_FILE={win_rel(version_file)}"',
        f'set "APP_EXE_NAME={APP_EXE_NAME}"',
        f'set "MAIN_SCRIPT={MAIN_SCRIPT}"',
    ]
    if icon_path:
        lines.append(f'set "RESOLVED_ICON={win_rel(icon_path)}"')
    else:
        lines.append('set "RESOLVED_ICON="')
    BUILD_ENV_FILE.write_text('\r\n'.join(lines) + '\r\n', encoding='utf-8')


def main():
    icon_source = find_icon()
    icon_path = None
    if icon_source:
        icon_path = convert_to_ico(icon_source)
        print(f'[OK] Ícone/logo aplicado: {win_rel(icon_path)}')
    else:
        print('[AVISO] Nenhum logo/ícone encontrado. Coloque um arquivo em assets\\logo.ico ou logo.ico para sair no executável.')

    version_file = write_version_file()
    print(f'[OK] Metadados do executável gerados: {win_rel(version_file)}')

    spec_path = ROOT / SPEC_FILE if SPEC_FILE else Path('')
    use_spec = bool(SPEC_FILE and spec_path.exists())

    if use_spec:
        patch_spec(spec_path, icon_path, version_file)
    else:
        main_path = ROOT / MAIN_SCRIPT
        if not main_path.exists():
            print(f'[ERRO] Não encontrei {MAIN_SCRIPT} e também não encontrei {SPEC_FILE}.')
            sys.exit(1)

    write_env(icon_path, version_file, use_spec)

if __name__ == '__main__':
    main()
'@; Set-Content -Path $env:PREP_SCRIPT -Value $code -Encoding UTF8"

python "%PREP_SCRIPT%"
if errorlevel 1 (
  echo [ERRO] Falha ao preparar nome/logo/metadados do executável.
  pause
  exit /b 1
)

call "%BUILD_ENV_FILE%"

rmdir /s /q build_temp 2>nul

if "%BUILD_USE_SPEC%"=="1" (
  pyinstaller --noconfirm --clean "%SPEC_FILE%"
) else (
  if defined RESOLVED_ICON (
    pyinstaller --noconfirm --clean --onefile --windowed --name "%APP_EXE_NAME%" --icon "%RESOLVED_ICON%" --version-file "%RESOLVED_VERSION_FILE%" "%MAIN_SCRIPT%"
  ) else (
    pyinstaller --noconfirm --clean --onefile --windowed --name "%APP_EXE_NAME%" --version-file "%RESOLVED_VERSION_FILE%" "%MAIN_SCRIPT%"
  )
)

if errorlevel 1 (
  echo.
  echo [ERRO] O PyInstaller não conseguiu gerar o executável.
  pause
  exit /b 1
)

echo.
echo [OK] Build concluído.
echo [OK] Saída gerada na pasta: dist
echo [OK] Nome do app: %APP_DISPLAY_NAME%
echo [OK] Nome do executável: %APP_EXE_NAME%.exe
echo.
echo Para trocar a logo, coloque o arquivo em assets\logo.ico ou logo.ico e execute este build novamente.

pause
