import json
import os
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]


def _runtime_base_dir():
    """Pasta persistente do usuário, fora do executável.

    Mantém a configuração do workspace mesmo quando o EXE é atualizado
    ou quando o sistema é executado em outra pasta.
    """
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base) / "Orcamentos_PPP_Enterprise"
    return Path.home() / ".orcamentos_ppp_enterprise"


RUNTIME_DIR = _runtime_base_dir()
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
RUNTIME_CONFIG_PATH = RUNTIME_DIR / "runtime_config.json"


def _load_runtime_config():
    try:
        if RUNTIME_CONFIG_PATH.exists():
            return json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_runtime_config(dados):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_CONFIG_PATH.write_text(
        json.dumps(dados or {}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_runtime_config():
    return dict(_load_runtime_config())


def update_runtime_config(**kwargs):
    dados = _load_runtime_config()
    dados.update({k: str(v or "") for k, v in kwargs.items()})
    _save_runtime_config(dados)
    return dados


def _parece_url(valor):
    texto = str(valor or "").strip().lower()
    return texto.startswith(("http://", "https://"))


def _normalizar_pasta_workspace(caminho):
    texto = str(caminho or "").strip().strip('"')
    if not texto:
        raise ValueError("Informe a pasta compartilhada/sincronizada.")
    if _parece_url(texto):
        raise ValueError(
            "O campo Pasta Drive sincronizada precisa ser uma pasta local do Windows, "
            "não o link do Google Drive. Abra o Google Drive para computador e selecione "
            "a pasta sincronizada, por exemplo G:\\Meu Drive\\Orcamentos_PPP_Enterprise."
        )

    pasta = Path(texto).expanduser()
    if pasta.suffix.lower() == ".db":
        raise ValueError("Selecione a pasta compartilhada, não o arquivo app.db.")
    return pasta


def _resolve_data_dir():
    cfg = _load_runtime_config()
    workspace = str(cfg.get("shared_workspace") or "").strip()
    if workspace:
        try:
            pasta = _normalizar_pasta_workspace(workspace)
            pasta.mkdir(parents=True, exist_ok=True)
            return pasta
        except Exception:
            # Se o Drive não estiver montado ou a unidade não existir,
            # o sistema continua abrindo com o banco local.
            pass
    for base in [APP_DIR, *APP_DIR.parents]:
        candidato = base / "banco de dados"
        if candidato.exists():
            candidato.mkdir(parents=True, exist_ok=True)
            return candidato
    local = APP_DIR / "data"
    local.mkdir(parents=True, exist_ok=True)
    return local


DATA_DIR = _resolve_data_dir()
DB_PATH = DATA_DIR / "app.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_shared_workspace_path():
    cfg = _load_runtime_config()
    caminho = str(cfg.get("shared_workspace") or "").strip()
    if not caminho:
        return None
    try:
        return _normalizar_pasta_workspace(caminho)
    except Exception:
        return None


def workspace_ativo():
    cfg = _load_runtime_config()
    caminho = str(cfg.get("shared_workspace") or "").strip()
    try:
        return bool(caminho and DATA_DIR == _normalizar_pasta_workspace(caminho))
    except Exception:
        return False


def _copiar_banco_sqlite(origem, destino):
    destino.parent.mkdir(parents=True, exist_ok=True)
    if origem.resolve() == destino.resolve():
        return

    try:
        with closing(sqlite3.connect(origem, timeout=30)) as src:
            with closing(sqlite3.connect(destino, timeout=30)) as dst:
                src.backup(dst)
                dst.commit()
    except sqlite3.DatabaseError:
        shutil.copy2(origem, destino)


def set_shared_workspace(caminho, drive_link="", copiar_banco_atual=True):
    """Ativa uma pasta compartilhada/sincronizada como base do sistema.

    Uso prático: selecionar uma pasta do Google Drive para Desktop,
    OneDrive, rede local ou servidor. O app cria app.db, anexos, gerados
    e backups nesse local. O link do Drive fica salvo como referência/atalho.
    """
    global DATA_DIR, DB_PATH

    antigo_db = DB_PATH
    pasta = _normalizar_pasta_workspace(caminho)
    pasta.mkdir(parents=True, exist_ok=True)
    for sub in ["anexos", "gerados", "backups"]:
        (pasta / sub).mkdir(parents=True, exist_ok=True)

    novo_db = pasta / "app.db"
    if copiar_banco_atual and antigo_db.exists() and not novo_db.exists():
        _copiar_banco_sqlite(antigo_db, novo_db)

    update_runtime_config(
        shared_workspace=str(pasta),
        google_drive_link=drive_link or _load_runtime_config().get("google_drive_link", "")
    )

    DATA_DIR = pasta
    DB_PATH = novo_db
    return pasta, novo_db


def copiar_banco_para(destino):
    destino = Path(destino)
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Banco de dados nao encontrado: {DB_PATH}")
    _copiar_banco_sqlite(DB_PATH, destino)
    return destino


def get_anexos_dir(orcamento_id=None):
    pasta = DATA_DIR / "anexos"
    if orcamento_id not in (None, ""):
        pasta = pasta / f"orcamento_{orcamento_id}"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def get_gerados_dir():
    pasta = DATA_DIR / "gerados"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def get_os_dir(ordem_id=None):
    pasta = DATA_DIR / "ordens_servico"
    if ordem_id not in (None, ""):
        pasta = pasta / f"os_{ordem_id}"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta

SEGMENTOS_PADRAO = [
    "Iluminação Pública",
    "CCO",
    "Videomonitoramento",
    "LPR",
    "Telecomunicações",
    "Energia Solar",
    "Serviços avulsos / contratos de terceiros",
]

STATUS_ORCAMENTO = [
    "RASCUNHO",
    "EM ELABORAÇÃO",
    "EM REVISÃO",
    "APROVADO",
    "ENVIADO",
    "CANCELADO",
]

STATUS_CONTRATO = [
    "ATIVO",
    "EM REVISÃO",
    "ENCERRADO",
    "SUSPENSO",
]


def conn():
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 30000")
    c.execute("PRAGMA foreign_keys = ON")
    try:
        if workspace_ativo():
            c.execute("PRAGMA journal_mode = DELETE")
            c.execute("PRAGMA synchronous = FULL")
        else:
            c.execute("PRAGMA journal_mode = WAL")
            c.execute("PRAGMA synchronous = NORMAL")
    except sqlite3.DatabaseError:
        pass
    return c


def execute(sql, params=()):
    with conn() as c:
        cur = c.execute(sql, params)
        c.commit()
        return cur.lastrowid


def query(sql, params=()):
    with conn() as c:
        return c.execute(sql, params).fetchall()


def one(sql, params=()):
    with conn() as c:
        return c.execute(sql, params).fetchone()


def _columns(c, table):
    return {row[1] for row in c.execute(f"PRAGMA table_info({table})").fetchall()}


def _add_column(c, table, column, definition):
    if column not in _columns(c, table):
        c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    """Inicializa e migra o banco local sem apagar dados existentes."""
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS empresa(
            id INTEGER PRIMARY KEY CHECK(id=1),
            razao TEXT,
            fantasia TEXT,
            cnpj TEXT,
            endereco TEXT,
            municipio TEXT,
            uf TEXT,
            telefone TEXT,
            email TEXT,
            representante TEXT,
            cargo_representante TEXT,
            responsavel_tecnico TEXT,
            registro_tecnico TEXT,
            responsavel_tecnico_cpf TEXT,
            responsavel_tecnico_cargo TEXT,
            responsavel_tecnico_especialidade TEXT,
            responsavel_tecnico_email TEXT,
            responsavel_tecnico_telefone TEXT,
            responsavel_tecnico_art TEXT,
            responsavel_tecnico_assinatura_path TEXT,
            responsavel_tecnico_rubrica_path TEXT,
            gestor_contrato_nome TEXT,
            gestor_contrato_cargo TEXT,
            gestor_contrato_cpf TEXT,
            gestor_contrato_email TEXT,
            gestor_contrato_telefone TEXT,
            gestor_contrato_assinatura_path TEXT,
            fiscal_contrato_nome TEXT,
            fiscal_contrato_setor TEXT,
            fiscal_contrato_cargo TEXT,
            fiscal_contrato_email TEXT,
            fiscal_contrato_telefone TEXT,
            representante_assinatura_path TEXT,
            site TEXT,
            inscricao_municipal TEXT,
            observacao_institucional TEXT,
            logo_path TEXT,
            contrato_concessao_path TEXT
        );

        INSERT OR IGNORE INTO empresa(
            id, razao, fantasia, cnpj, municipio, uf
        ) VALUES(
            1,
            'IP BARRETOS CONCESSIONÁRIA DE CIDADE INTELIGENTE S/A',
            'Barretos Inteligente',
            '49.023.977/0001-13',
            'Barretos',
            'SP'
        );

        CREATE TABLE IF NOT EXISTS clientes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            cnpj TEXT,
            tipo TEXT,
            endereco TEXT,
            municipio TEXT,
            uf TEXT,
            orgao_setor TEXT,
            responsavel TEXT,
            cargo TEXT,
            email TEXT,
            telefone TEXT
        );

        CREATE TABLE IF NOT EXISTS segmentos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contratos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            nome TEXT,
            numero TEXT,
            objeto TEXT,
            municipio TEXT,
            valor_global REAL DEFAULT 0,
            inicio TEXT,
            fim TEXT,
            status TEXT DEFAULT 'ATIVO',
            segmentos TEXT,
            indice_reajuste TEXT,
            observacao TEXT,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id)
        );

        CREATE TABLE IF NOT EXISTS contrato_segmentos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contrato_id INTEGER NOT NULL,
            segmento_id INTEGER NOT NULL,
            UNIQUE(contrato_id, segmento_id),
            FOREIGN KEY(contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
            FOREIGN KEY(segmento_id) REFERENCES segmentos(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS aditivos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contrato_id INTEGER NOT NULL,
            segmento_id INTEGER,
            numero_aditivo TEXT,
            objeto TEXT,
            valor REAL DEFAULT 0,
            prazo TEXT,
            status TEXT DEFAULT 'ATIVO',
            observacao TEXT,
            FOREIGN KEY(contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
            FOREIGN KEY(segmento_id) REFERENCES segmentos(id)
        );

        CREATE TABLE IF NOT EXISTS sinapi(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            descricao TEXT,
            unidade TEXT,
            custo REAL,
            uf TEXT,
            competencia TEXT,
            tipo TEXT,
            fonte TEXT,
            data_atualizacao TEXT,
            classificacao TEXT
        );

        CREATE TABLE IF NOT EXISTS orcamentos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            cliente_id INTEGER,
            contrato_id INTEGER,
            aditivo_id INTEGER,
            segmento_id INTEGER,
            objeto TEXT,
            municipio TEXT,
            validade TEXT,
            texto_proposta TEXT,
            bdi_global REAL DEFAULT 0,
            margem_global REAL DEFAULT 18,
            status TEXT DEFAULT 'RASCUNHO',
            data_criacao TEXT,
            data_atualizacao TEXT,
            FOREIGN KEY(cliente_id) REFERENCES clientes(id),
            FOREIGN KEY(contrato_id) REFERENCES contratos(id),
            FOREIGN KEY(aditivo_id) REFERENCES aditivos(id),
            FOREIGN KEY(segmento_id) REFERENCES segmentos(id)
        );

        CREATE TABLE IF NOT EXISTS etapas_orcamento(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER NOT NULL,
            nome TEXT,
            descricao TEXT,
            ordem INTEGER,
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS itens(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER NOT NULL,
            etapa_id INTEGER,
            etapa TEXT,
            fonte TEXT,
            codigo TEXT,
            descricao TEXT,
            unidade TEXT,
            quantidade REAL DEFAULT 0,
            custo_unit REAL DEFAULT 0,
            bdi REAL DEFAULT 0,
            margem REAL DEFAULT 0,
            capex_opex TEXT,
            classificacao TEXT,
            observacao TEXT,
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE,
            FOREIGN KEY(etapa_id) REFERENCES etapas_orcamento(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS opex(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER NOT NULL,
            categoria TEXT,
            centro_custo TEXT,
            fonte TEXT,
            codigo TEXT,
            descricao TEXT,
            unidade TEXT,
            qtd_mensal REAL DEFAULT 0,
            custo_unit REAL DEFAULT 0,
            bdi REAL DEFAULT 0,
            margem REAL DEFAULT 0,
            observacao TEXT,
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS cronograma_parcelas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER NOT NULL,
            etapa_id INTEGER,
            parcela INTEGER NOT NULL,
            percentual REAL DEFAULT 0,
            valor REAL DEFAULT 0,
            UNIQUE(orcamento_id, etapa_id, parcela),
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE,
            FOREIGN KEY(etapa_id) REFERENCES etapas_orcamento(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS documentos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER,
            contrato_id INTEGER,
            aditivo_id INTEGER,
            ordem_servico_id INTEGER,
            nome_arquivo TEXT,
            tipo TEXT,
            caminho TEXT,
            data_upload TEXT,
            usuario TEXT,
            observacao TEXT,
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE,
            FOREIGN KEY(contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
            FOREIGN KEY(aditivo_id) REFERENCES aditivos(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS ordens_servico(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT UNIQUE,
            orcamento_id INTEGER,
            contrato_id INTEGER,
            cliente_id INTEGER,
            segmento_id INTEGER,
            objeto TEXT,
            local_execucao TEXT,
            municipio TEXT,
            solicitante TEXT,
            executor TEXT,
            responsavel_tecnico TEXT,
            fiscal_cliente TEXT,
            gestor TEXT,
            data_emissao TEXT,
            data_prevista_inicio TEXT,
            data_prevista_fim TEXT,
            status TEXT DEFAULT 'RASCUNHO',
            travada INTEGER DEFAULT 0,
            aprovada_inicio INTEGER DEFAULT 0,
            aprovada_por TEXT,
            aprovada_em TEXT,
            importada_orcamento_id INTEGER,
            observacao TEXT,
            data_criacao TEXT DEFAULT (datetime('now')),
            data_atualizacao TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id),
            FOREIGN KEY(contrato_id) REFERENCES contratos(id),
            FOREIGN KEY(cliente_id) REFERENCES clientes(id),
            FOREIGN KEY(segmento_id) REFERENCES segmentos(id)
        );

        CREATE TABLE IF NOT EXISTS os_etapas(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem_servico_id INTEGER NOT NULL,
            nome TEXT,
            descricao TEXT,
            ordem INTEGER,
            status TEXT DEFAULT 'PLANEJADA',
            percentual_execucao REAL DEFAULT 0,
            observacao TEXT,
            FOREIGN KEY(ordem_servico_id) REFERENCES ordens_servico(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS os_itens(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem_servico_id INTEGER NOT NULL,
            etapa_id INTEGER,
            descricao TEXT,
            unidade TEXT,
            quantidade_prevista REAL DEFAULT 0,
            quantidade_executada REAL DEFAULT 0,
            fonte TEXT,
            codigo TEXT,
            observacao TEXT,
            importar_orcamento INTEGER DEFAULT 1,
            FOREIGN KEY(ordem_servico_id) REFERENCES ordens_servico(id) ON DELETE CASCADE,
            FOREIGN KEY(etapa_id) REFERENCES os_etapas(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS os_fotos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem_servico_id INTEGER NOT NULL,
            etapa_id INTEGER,
            categoria TEXT,
            legenda TEXT,
            caminho TEXT,
            nome_arquivo TEXT,
            data_registro TEXT DEFAULT (datetime('now')),
            usuario TEXT,
            latitude TEXT,
            longitude TEXT,
            observacao TEXT,
            FOREIGN KEY(ordem_servico_id) REFERENCES ordens_servico(id) ON DELETE CASCADE,
            FOREIGN KEY(etapa_id) REFERENCES os_etapas(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS os_anexos(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ordem_servico_id INTEGER NOT NULL,
            etapa_id INTEGER,
            tipo TEXT,
            nome_arquivo TEXT,
            caminho TEXT,
            data_upload TEXT DEFAULT (datetime('now')),
            usuario TEXT,
            observacao TEXT,
            importar_orcamento INTEGER DEFAULT 1,
            FOREIGN KEY(ordem_servico_id) REFERENCES ordens_servico(id) ON DELETE CASCADE,
            FOREIGN KEY(etapa_id) REFERENCES os_etapas(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS empresa_representantes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            cargo TEXT,
            cpf TEXT,
            email TEXT,
            telefone TEXT,
            assinatura_path TEXT,
            ativo INTEGER DEFAULT 1,
            observacao TEXT,
            ordem INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS logs_orcamento(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            orcamento_id INTEGER,
            modulo TEXT,
            acao TEXT,
            descricao TEXT,
            valor_anterior TEXT,
            valor_novo TEXT,
            usuario TEXT,
            data_hora TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(orcamento_id) REFERENCES orcamentos(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS config(
            chave TEXT PRIMARY KEY,
            valor TEXT
        );

        CREATE TABLE IF NOT EXISTS logs_sistema(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT,
            acao TEXT,
            descricao TEXT,
            data_hora TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS usuarios_app(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            usuario TEXT UNIQUE,
            email TEXT,
            senha TEXT,
            perfil TEXT DEFAULT 'OPERACIONAL',
            acesso_orcamentos INTEGER DEFAULT 0,
            acesso_os INTEGER DEFAULT 1,
            permissoes TEXT,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS executores_os(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            documento TEXT,
            telefone TEXT,
            email TEXT,
            funcao TEXT,
            empresa TEXT,
            empresa_tipo TEXT DEFAULT 'TERCEIRO',
            empresa_id INTEGER,
            ativo INTEGER DEFAULT 1,
            observacao TEXT,
            criado_em TEXT DEFAULT (datetime('now'))
        );

        INSERT OR IGNORE INTO config(chave,valor) VALUES('google_drive','');
        INSERT OR IGNORE INTO config(chave,valor) VALUES('google_drive_link','');
        INSERT OR IGNORE INTO config(chave,valor) VALUES('portal_executor_url','');
        INSERT OR IGNORE INTO config(chave,valor) VALUES('shared_workspace','');
        INSERT OR IGNORE INTO config(chave,valor) VALUES('pasta_local','');
        INSERT OR IGNORE INTO config(chave,valor) VALUES('nome_usuario','Lucas Henrique');
        INSERT OR IGNORE INTO config(chave,valor) VALUES('cnpj_usuario','');
        INSERT OR IGNORE INTO usuarios_app(nome,usuario,senha,perfil,ativo)
        VALUES('Administrador','admin','admin','ADMIN',1);
        INSERT OR IGNORE INTO usuarios_app(nome,usuario,senha,perfil,ativo)
        VALUES('Operador OS','operador','1234','OPERACIONAL',1);
        """)

        # Migrações seguras para bancos já existentes.
        for table, columns in {
            "empresa": {
                "endereco": "TEXT",
                "telefone": "TEXT",
                "email": "TEXT",
                "representante": "TEXT",
                "cargo_representante": "TEXT",
                "responsavel_tecnico": "TEXT",
                "registro_tecnico": "TEXT",
                "responsavel_tecnico_cpf": "TEXT",
                "responsavel_tecnico_cargo": "TEXT",
                "responsavel_tecnico_especialidade": "TEXT",
                "responsavel_tecnico_email": "TEXT",
                "responsavel_tecnico_telefone": "TEXT",
                "responsavel_tecnico_art": "TEXT",
                "responsavel_tecnico_assinatura_path": "TEXT",
                "responsavel_tecnico_rubrica_path": "TEXT",
                "gestor_contrato_nome": "TEXT",
                "gestor_contrato_cargo": "TEXT",
                "gestor_contrato_cpf": "TEXT",
                "gestor_contrato_email": "TEXT",
                "gestor_contrato_telefone": "TEXT",
                "gestor_contrato_assinatura_path": "TEXT",
                "fiscal_contrato_nome": "TEXT",
                "fiscal_contrato_setor": "TEXT",
                "fiscal_contrato_cargo": "TEXT",
                "fiscal_contrato_email": "TEXT",
                "fiscal_contrato_telefone": "TEXT",
                "representante_assinatura_path": "TEXT",
                "site": "TEXT",
                "inscricao_municipal": "TEXT",
                "observacao_institucional": "TEXT",
                "logo_path": "TEXT",
                "contrato_concessao_path": "TEXT",
            },
            "clientes": {
                "tipo": "TEXT",
                "endereco": "TEXT",
                "telefone": "TEXT",
            },
            "contratos": {
                "cliente_id": "INTEGER",
                "objeto": "TEXT",
                "valor_global": "REAL DEFAULT 0",
                "inicio": "TEXT",
                "fim": "TEXT",
                "status": "TEXT DEFAULT 'ATIVO'",
                "observacao": "TEXT",
            },
            "orcamentos": {
                "aditivo_id": "INTEGER",
                "segmento_id": "INTEGER",
                "data_atualizacao": "TEXT",
                "usar_rt_especifico": "INTEGER DEFAULT 0",
                "rt_nome": "TEXT",
                "rt_registro": "TEXT",
                "rt_cpf": "TEXT",
                "rt_cargo": "TEXT",
                "rt_especialidade": "TEXT",
                "rt_email": "TEXT",
                "rt_telefone": "TEXT",
                "rt_art": "TEXT",
                "rt_assinatura_path": "TEXT",
                "gestor_contrato_nome": "TEXT",
                "gestor_contrato_cargo": "TEXT",
                "gestor_contrato_cpf": "TEXT",
                "gestor_contrato_email": "TEXT",
                "gestor_contrato_telefone": "TEXT",
                "fiscal_contrato_nome": "TEXT",
                "fiscal_contrato_cargo": "TEXT",
                "fiscal_contrato_setor": "TEXT",
                "fiscal_contrato_email": "TEXT",
                "fiscal_contrato_telefone": "TEXT",
                "representante_legal_id": "INTEGER",
                "bloqueado": "INTEGER DEFAULT 0",
                "versao_revisao": "INTEGER DEFAULT 0",
                "orcamento_origem_id": "INTEGER",
                "ordem_servico_id": "INTEGER",
            },
            "itens": {
                "observacao": "TEXT",
            },
            "opex": {
                "fonte": "TEXT",
                "codigo": "TEXT",
                "bdi": "REAL DEFAULT 0",
                "margem": "REAL DEFAULT 0",
                "observacao": "TEXT",
            },
            "documentos": {
                "contrato_id": "INTEGER",
                "aditivo_id": "INTEGER",
                "ordem_servico_id": "INTEGER",
                "usuario": "TEXT",
                "observacao": "TEXT",
                "item_id": "INTEGER",
                "opex_id": "INTEGER",
                "etapa_id": "INTEGER",
                "tipo_vinculo": "TEXT",
            },
            "ordens_servico": {
                "orcamento_id": "INTEGER",
                "contrato_id": "INTEGER",
                "cliente_id": "INTEGER",
                "segmento_id": "INTEGER",
                "objeto": "TEXT",
                "local_execucao": "TEXT",
                "municipio": "TEXT",
                "solicitante": "TEXT",
                "executor": "TEXT",
                "responsavel_tecnico": "TEXT",
                "fiscal_cliente": "TEXT",
                "gestor": "TEXT",
                "travada": "INTEGER DEFAULT 0",
                "aprovada_inicio": "INTEGER DEFAULT 0",
                "aprovada_por": "TEXT",
                "aprovada_em": "TEXT",
                "importada_orcamento_id": "INTEGER",
                "observacao": "TEXT",
                "data_atualizacao": "TEXT",
                "latitude": "TEXT",
                "longitude": "TEXT",
                "executor_id": "INTEGER",
            },
            "os_itens": {
                "fonte": "TEXT",
                "codigo": "TEXT",
                "importar_orcamento": "INTEGER DEFAULT 1",
            },
            "os_fotos": {
                "latitude": "TEXT",
                "longitude": "TEXT",
                "observacao": "TEXT",
            },
            "os_anexos": {
                "etapa_id": "INTEGER",
                "importar_orcamento": "INTEGER DEFAULT 1",
            },
            "usuarios_app": {
                "nome": "TEXT",
                "email": "TEXT",
                "senha": "TEXT",
                "perfil": "TEXT DEFAULT 'OPERACIONAL'",
                "acesso_orcamentos": "INTEGER DEFAULT 0",
                "acesso_os": "INTEGER DEFAULT 1",
                "permissoes": "TEXT",
                "ativo": "INTEGER DEFAULT 1",
                "criado_em": "TEXT",
            },
            "executores_os": {
                "documento": "TEXT",
                "telefone": "TEXT",
                "email": "TEXT",
                "funcao": "TEXT",
                "empresa": "TEXT",
                "empresa_tipo": "TEXT DEFAULT 'TERCEIRO'",
                "empresa_id": "INTEGER",
                "ativo": "INTEGER DEFAULT 1",
                "observacao": "TEXT",
                "criado_em": "TEXT",
            },
        }.items():
            for col, definition in columns.items():
                _add_column(c, table, col, definition)

        for nome in SEGMENTOS_PADRAO:
            c.execute("INSERT OR IGNORE INTO segmentos(nome) VALUES(?)", (nome,))

        c.execute("UPDATE usuarios_app SET nome='Administrador', email='admin@local', senha='admin', perfil='ADMIN', acesso_orcamentos=1, acesso_os=1, permissoes='*', ativo=1 WHERE usuario='admin'")
        c.execute("UPDATE usuarios_app SET email='operador@local', acesso_orcamentos=0, acesso_os=1 WHERE usuario='operador' AND COALESCE(email,'')=''")
        c.execute("UPDATE usuarios_app SET permissoes='*', acesso_orcamentos=1, acesso_os=1 WHERE perfil='ADMIN'")
        c.execute("UPDATE usuarios_app SET acesso_os=1 WHERE perfil='OPERACIONAL' AND acesso_orcamentos=0")
        c.execute("UPDATE usuarios_app SET permissoes='[\"os_execucao\", \"os_kanban\", \"os_mapa\"]' WHERE perfil='OPERACIONAL' AND acesso_os=1 AND COALESCE(permissoes,'')=''")
        c.execute("UPDATE usuarios_app SET permissoes='[\"clientes\", \"contratos\", \"dashboard\", \"meus_orcamentos\", \"orcamentos\", \"ordens_servico\", \"os_execucao\", \"os_kanban\", \"os_mapa\", \"relatorios\"]' WHERE perfil='GESTOR' AND COALESCE(permissoes,'')=''")

        c.commit()


def get_config(chave, padrao=""):
    """Retorna uma configuração salva no banco local."""
    try:
        with conn() as c:
            row = c.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        if row and row["valor"] not in (None, ""):
            return row["valor"]
    except Exception:
        pass
    return padrao


def set_config(chave, valor):
    """Grava/atualiza uma configuração no banco local."""
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO config(chave, valor) VALUES(?, ?)", (chave, valor or ""))
        c.commit()


def get_pasta_local_relatorios():
    """Pasta base onde relatórios e dashboards devem ser gerados.

    Prioridade:
    1) Configurações > Pasta local relatórios;
    2) Workspace compartilhado > gerados;
    3) app/generated como fallback local.
    """
    candidatos = []
    caminho = str(get_config("pasta_local", "") or "").strip().strip('"')
    if caminho:
        candidatos.append(Path(caminho).expanduser())
    if workspace_ativo():
        candidatos.append(get_gerados_dir())
    candidatos.append(APP_DIR / "generated")

    for base in candidatos:
        try:
            base.mkdir(parents=True, exist_ok=True)
            teste = base / ".write_test"
            teste.write_text("ok", encoding="utf-8")
            teste.unlink(missing_ok=True)
            return base
        except Exception:
            continue

    base = Path.home() / "Documents" / "Orcamentos_PPP_Gerados"
    base.mkdir(parents=True, exist_ok=True)
    return base
