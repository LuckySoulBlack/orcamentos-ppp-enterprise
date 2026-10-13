from core.database import conn


def listar_executores(apenas_ativos=False):
    where = "WHERE ativo=1" if apenas_ativos else ""
    with conn() as c:
        return c.execute(
            f"SELECT * FROM executores_os {where} ORDER BY ativo DESC, nome"
        ).fetchall()


def salvar_executor(dados, executor_id=None):
    nome = str(dados.get("nome") or "").strip()
    if not nome:
        raise ValueError("Informe o nome do executor.")
    empresa = str(dados.get("empresa") or "").strip()
    if not empresa:
        raise ValueError("Informe se o executor pertence à empresa cadastrada ou é terceiro.")
    empresa_tipo = str(dados.get("empresa_tipo") or "TERCEIRO").strip().upper()
    if empresa_tipo not in {"CADASTRADA", "TERCEIRO"}:
        empresa_tipo = "TERCEIRO"
    campos = ["nome", "documento", "telefone", "email", "funcao", "empresa", "empresa_tipo", "empresa_id", "ativo", "observacao"]
    valores = {
        "nome": nome,
        "documento": dados.get("documento"),
        "telefone": dados.get("telefone"),
        "email": dados.get("email"),
        "funcao": dados.get("funcao"),
        "empresa": empresa,
        "empresa_tipo": empresa_tipo,
        "empresa_id": dados.get("empresa_id") if empresa_tipo == "CADASTRADA" else None,
        "ativo": 1 if dados.get("ativo", True) else 0,
        "observacao": dados.get("observacao"),
    }
    with conn() as c:
        if executor_id:
            sets = ", ".join(f"{campo}=?" for campo in campos)
            c.execute(f"UPDATE executores_os SET {sets} WHERE id=?", [valores[campo] for campo in campos] + [executor_id])
        else:
            cols = ", ".join(campos)
            qs = ", ".join("?" for _ in campos)
            c.execute(f"INSERT INTO executores_os({cols}) VALUES({qs})", [valores[campo] for campo in campos])
        c.commit()


def excluir_executor(executor_id):
    with conn() as c:
        c.execute("UPDATE executores_os SET ativo=0 WHERE id=?", (executor_id,))
        c.commit()
