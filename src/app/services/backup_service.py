from datetime import datetime, timedelta
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

import core.database as database


def _backup_dir():
    pasta = database.DATA_DIR / "backups"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def gerar_backup_banco(destino_pasta=None, usuario="", observacao=""):
    """Gera um ZIP contendo app.db e manifesto.

    Se o workspace compartilhado estiver ativo, o backup usa o banco em uso
    na pasta compartilhada. Se destino_pasta não for informado, salva em
    workspace/backups ou app/data/backups.
    """
    destino = Path(destino_pasta) if destino_pasta else _backup_dir()
    destino.mkdir(parents=True, exist_ok=True)

    db_path = database.DB_PATH
    if not db_path.exists():
        raise FileNotFoundError(f"Banco de dados não encontrado: {db_path}")

    nome = f"backup_orcamentos_ppp_{_timestamp()}.zip"
    zip_path = destino / nome

    manifesto = {
        "sistema": "Orçamentos PPP Enterprise",
        "tipo": "backup_sqlite",
        "arquivo_banco": "app.db",
        "data_hora": datetime.now().isoformat(timespec="seconds"),
        "usuario": usuario or "",
        "observacao": observacao or "",
        "origem": str(db_path),
        "workspace": str(database.DATA_DIR),
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        copia_db = Path(tmp_dir) / "app.db"
        database.copiar_banco_para(copia_db)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copia_db, arcname="app.db")
            z.writestr("manifesto_backup.json", json.dumps(manifesto, ensure_ascii=False, indent=2))

    return zip_path


def gerar_backup_diario_se_necessario(retencao_dias=35):
    """Cria automaticamente um backup diário íntegro do banco em uso.

    A rotina é idempotente por data: se já existir um backup diário de hoje,
    não gera outro. Backups manuais e de recuperação nunca são removidos.
    """
    destino = _backup_dir()
    hoje = datetime.now()
    prefixo = f"backup_diario_{hoje:%Y%m%d}_"
    existentes = list(destino.glob(f"{prefixo}*.zip"))
    if existentes:
        return existentes[0]

    temporario = gerar_backup_banco(
        destino_pasta=destino,
        usuario="sistema",
        observacao="Backup diário automático",
    )
    diario = destino / f"{prefixo}{hoje:%H%M%S}.zip"
    temporario.replace(diario)

    limite = hoje - timedelta(days=max(7, int(retencao_dias)))
    for arquivo in destino.glob("backup_diario_*.zip"):
        try:
            if datetime.fromtimestamp(arquivo.stat().st_mtime) < limite:
                arquivo.unlink()
        except OSError:
            pass
    return diario


def importar_backup_banco(zip_backup):
    """Importa backup ZIP substituindo o app.db atual.

    Antes de substituir, gera cópia de segurança do banco atual em backups/pre_importacao.
    """
    zip_backup = Path(zip_backup)

    if not zip_backup.exists():
        raise FileNotFoundError(f"Backup não encontrado: {zip_backup}")

    pre_dir = _backup_dir() / "pre_importacao"
    pre_dir.mkdir(parents=True, exist_ok=True)

    db_path = database.DB_PATH
    if db_path.exists():
        copia_atual = pre_dir / f"app_antes_importacao_{_timestamp()}.db"
        database.copiar_banco_para(copia_atual)
    else:
        copia_atual = None

    with zipfile.ZipFile(zip_backup, "r") as z:
        nomes = z.namelist()
        if "app.db" not in nomes:
            raise ValueError("Backup inválido: o ZIP não contém app.db.")
        tmp = db_path.with_suffix(".importando.db")
        with z.open("app.db") as origem, open(tmp, "wb") as destino:
            shutil.copyfileobj(origem, destino)

    shutil.move(str(tmp), str(db_path))
    for extra in (db_path.with_name(db_path.name + "-wal"), db_path.with_name(db_path.name + "-shm")):
        try:
            extra.unlink(missing_ok=True)
        except Exception:
            pass
    return db_path, copia_atual


def abrir_pasta_backups():
    return _backup_dir()
