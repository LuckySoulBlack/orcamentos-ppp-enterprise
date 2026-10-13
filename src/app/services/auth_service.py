import json

from core.database import conn


RECOVERY_USER = "admin"
RECOVERY_EMAIL = "admin@local"
RECOVERY_PASSWORD = "admin"

ADMIN_PERMISSOES = [
    "dashboard", "orcamentos", "meus_orcamentos", "ordens_servico", "usuarios",
    "contratos", "clientes", "empresa", "sinapi", "relatorios", "config",
]

OS_PERMISSOES = ["os_execucao", "os_config", "os_executores", "os_mapa", "os_kanban"]


def _permissoes_padrao(perfil, acesso_orcamentos=False, acesso_os=True):
    perfil = str(perfil or "OPERACIONAL").upper()
    if perfil == "ADMIN":
        return "*"
    if perfil == "GESTOR":
        perms = ["dashboard", "orcamentos", "meus_orcamentos", "ordens_servico", "contratos", "clientes", "relatorios"]
        if acesso_os:
            perms += OS_PERMISSOES
        return json.dumps(sorted(set(perms)), ensure_ascii=False)
    perms = []
    if acesso_orcamentos:
        perms += ["dashboard", "meus_orcamentos"]
    if acesso_os:
        perms += ["os_execucao", "os_mapa", "os_kanban"]
    return json.dumps(sorted(set(perms)), ensure_ascii=False)


def normalizar_permissoes(valor):
    if valor in (None, ""):
        return []
    if str(valor).strip() == "*":
        return ["*"]
    try:
        dados = json.loads(valor)
        return [str(p) for p in dados] if isinstance(dados, list) else []
    except Exception:
        return [p.strip() for p in str(valor).split(",") if p.strip()]


def usuario_tem_permissao(usuario_row, permissao):
    if not usuario_row:
        return False
    if str(usuario_row["perfil"] or "").upper() == "ADMIN":
        return True
    perms = normalizar_permissoes(usuario_row["permissoes"])
    return "*" in perms or permissao in perms


def permissoes_usuario(usuario_row):
    if not usuario_row:
        return []
    if str(usuario_row["perfil"] or "").upper() == "ADMIN":
        return ["*"]
    return normalizar_permissoes(usuario_row["permissoes"])


def autenticar(usuario, senha, exigir_ativo=True, sistema=None):
    usuario = str(usuario or "").strip().lower()
    senha = str(senha or "").strip()
    if not usuario or not senha:
        return None
    with conn() as c:
        row = c.execute(
            """
            SELECT * FROM usuarios_app
            WHERE (LOWER(usuario)=?OR LOWER(COALESCE(email,''))=?) AND senha=?
            """,
            (usuario, usuario, senha),
        ).fetchone()
    if not row:
        return None
    if exigir_ativo and not int(row["ativo"] or 0):
        return None
    if sistema == "orcamentos" and not int(row["acesso_orcamentos"] or 0):
        return None
    if sistema == "os" and not int(row["acesso_os"] or 0):
        return None
    return row


def listar_usuarios():
    with conn() as c:
        return c.execute(
            """
            SELECT id,nome,usuario,email,senha,perfil,acesso_orcamentos,acesso_os,permissoes,ativo,criado_em
            FROM usuarios_app
            ORDER BY perfil,nome
            """
        ).fetchall()


def salvar_usuario(
    nome, usuario, email, senha, perfil="OPERACIONAL", ativo=True, usuario_id=None,
    acesso_orcamentos=False, acesso_os=True, permissoes=None,
):
    nome = str(nome or "").strip()
    usuario = str(usuario or "").strip()
    email = str(email or "").strip().lower()
    senha = str(senha or "").strip()
    perfil = str(perfil or "OPERACIONAL").strip().upper()
    if not nome or not usuario or not email or (not usuario_id and not senha):
        raise ValueError("Informe nome, usuário, e-mail e senha.")
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ValueError("Informe um e-mail válido para login.")
    if perfil not in ("ADMIN", "GESTOR", "OPERACIONAL"):
        perfil = "OPERACIONAL"
    acesso_orcamentos = bool(acesso_orcamentos)
    acesso_os = bool(acesso_os)
    if perfil == "ADMIN":
        acesso_orcamentos = True
        acesso_os = True
        permissoes_txt = "*"
    else:
        if not acesso_orcamentos and not acesso_os:
            raise ValueError("Libere pelo menos um sistema para o usuário.")
        if permissoes is None:
            permissoes_txt = _permissoes_padrao(perfil, acesso_orcamentos, acesso_os)
        else:
            permissoes_txt = json.dumps(sorted(set(permissoes)), ensure_ascii=False)

    with conn() as c:
        if usuario_id:
            existente = c.execute("SELECT usuario FROM usuarios_app WHERE id=?", (usuario_id,)).fetchone()
            if existente and str(existente["usuario"]).lower() == RECOVERY_USER:
                nome = "Administrador"
                usuario = RECOVERY_USER
                email = RECOVERY_EMAIL
                senha = RECOVERY_PASSWORD
                perfil = "ADMIN"
                ativo = True
                acesso_orcamentos = True
                acesso_os = True
                permissoes_txt = "*"
        duplicado = c.execute(
            """
            SELECT id FROM usuarios_app
            WHERE (LOWER(usuario)=LOWER(?) OR LOWER(COALESCE(email,''))=LOWER(?))
              AND (?IS NULL OR id<>?)
            LIMIT 1
            """,
            (usuario, email, usuario_id, usuario_id),
        ).fetchone()
        if duplicado:
            raise ValueError("Já existe usuário com este login ou e-mail.")
        if usuario_id:
            if senha:
                c.execute(
                    """
                    UPDATE usuarios_app
                    SET nome=?, usuario=?, email=?, senha=?, perfil=?, acesso_orcamentos=?,
                        acesso_os=?, permissoes=?, ativo=?
                    WHERE id=?
                    """,
                    (nome, usuario, email, senha, perfil, 1 if acesso_orcamentos else 0,
                     1 if acesso_os else 0, permissoes_txt, 1 if ativo else 0, usuario_id),
                )
            else:
                c.execute(
                    """
                    UPDATE usuarios_app
                    SET nome=?, usuario=?, email=?, perfil=?, acesso_orcamentos=?,
                        acesso_os=?, permissoes=?, ativo=?
                    WHERE id=?
                    """,
                    (nome, usuario, email, perfil, 1 if acesso_orcamentos else 0,
                     1 if acesso_os else 0, permissoes_txt, 1 if ativo else 0, usuario_id),
                )
        else:
            c.execute(
                """
                INSERT INTO usuarios_app(nome,usuario,email,senha,perfil,acesso_orcamentos,acesso_os,permissoes,ativo)
                VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (nome, usuario, email, senha, perfil, 1 if acesso_orcamentos else 0,
                 1 if acesso_os else 0, permissoes_txt, 1 if ativo else 0),
            )
        c.commit()


def remover_usuario(usuario_id):
    with conn() as c:
        c.execute("DELETE FROM usuarios_app WHERE id=?AND usuario <> 'admin'", (usuario_id,))
        c.commit()


def garantir_admin_recuperacao():
    with conn() as c:
        row = c.execute("SELECT id FROM usuarios_app WHERE usuario=?", (RECOVERY_USER,)).fetchone()
        if row:
            c.execute(
                """
                UPDATE usuarios_app
                SET nome=COALESCE(NULLIF(nome,''),'Administrador'),
                    email=?, senha=?, perfil='ADMIN', acesso_orcamentos=1, acesso_os=1,
                    permissoes='*', ativo=1
                WHERE usuario=?
                """,
                (RECOVERY_EMAIL, RECOVERY_PASSWORD, RECOVERY_USER),
            )
        else:
            c.execute(
                """
                INSERT INTO usuarios_app(nome,usuario,email,senha,perfil,acesso_orcamentos,acesso_os,permissoes,ativo)
                VALUES('Administrador',?,?,?,?,1,1,'*',1)
                """,
                (RECOVERY_USER, RECOVERY_EMAIL, RECOVERY_PASSWORD, "ADMIN"),
            )
        c.commit()
