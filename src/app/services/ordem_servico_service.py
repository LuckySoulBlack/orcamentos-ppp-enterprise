from datetime import datetime
from pathlib import Path
import shutil
import json
import html
import zipfile
import base64
import re

from core import database
from core.database import conn, get_os_dir, get_anexos_dir, get_pasta_local_relatorios


FOTO_CATEGORIAS = ["Antes", "Durante", "Depois", "Pendencia", "Correcao"]
STATUS_OS = ["RASCUNHO", "AGUARDANDO_APROVACAO", "APROVADA_INICIO", "EM_EXECUCAO", "CONCLUIDA", "IMPORTADA_ORCAMENTO", "CANCELADA"]
STATUS_ETAPA = ["PLANEJADA", "LIBERADA", "EM_EXECUCAO", "CONCLUIDA", "PENDENTE", "CORRIGIDA"]
STATUS_OS_BLOQUEIA_EXCLUSAO = {"APROVADA_INICIO", "EM_EXECUCAO", "CONCLUIDA", "IMPORTADA_ORCAMENTO"}


def _safe_filename(nome):
    texto = str(nome or "arquivo").strip() or "arquivo"
    return "".join(ch if ch.isalnum() or ch in " ._-()" else "_" for ch in texto).strip() or "arquivo"


def _unique_path(destino_dir, nome):
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / _safe_filename(Path(nome).name)
    if not destino.exists():
        return destino
    stem, suffix = destino.stem, destino.suffix
    contador = 2
    while True:
        candidato = destino_dir / f"{stem}_{contador}{suffix}"
        if not candidato.exists():
            return candidato
        contador += 1


def gerar_numero_os():
    ano = datetime.now().year
    prefixo = f"OS-{ano}-"
    with conn() as c:
        row = c.execute(
            "SELECT numero FROM ordens_servico WHERE numero LIKE ?ORDER BY numero DESC LIMIT 1",
            (prefixo + "%",),
        ).fetchone()
    if not row:
        return prefixo + "001"
    try:
        prox = int(str(row["numero"]).split("-")[-1]) + 1
    except Exception:
        prox = 1
    return prefixo + f"{prox:03d}"


def listar_ordens():
    with conn() as c:
        return c.execute(
            """
            SELECT os.*,
                   cli.nome AS cliente_nome,
                   ct.nome AS contrato_nome,
                   s.nome AS segmento_nome,
                   o.codigo AS orcamento_codigo,
                   imp.codigo AS importado_codigo
            FROM ordens_servico os
            LEFT JOIN clientes cli ON cli.id=os.cliente_id
            LEFT JOIN contratos ct ON ct.id=os.contrato_id
            LEFT JOIN segmentos s ON s.id=os.segmento_id
            LEFT JOIN orcamentos o ON o.id=os.orcamento_id
            LEFT JOIN orcamentos imp ON imp.id=os.importada_orcamento_id
            ORDER BY os.id DESC
            """
        ).fetchall()


def obter_ordem(ordem_id):
    with conn() as c:
        return c.execute("SELECT * FROM ordens_servico WHERE id=?", (ordem_id,)).fetchone()


def ordem_travada(ordem_id):
    row = obter_ordem(ordem_id)
    return bool(row and int(row["travada"] or 0))


def ordem_permite_edicao_basica(ordem_id):
    row = obter_ordem(ordem_id)
    if not row:
        return True
    status = str(row["status"] or "").upper()
    return not bool(row["travada"]) and status not in {"IMPORTADA_ORCAMENTO"}


def ordem_permite_exclusao(ordem_id):
    row = obter_ordem(ordem_id)
    if not row:
        return False
    status = str(row["status"] or "").upper()
    if bool(row["travada"]) or int(row["aprovada_inicio"] or 0):
        return False
    return status not in STATUS_OS_BLOQUEIA_EXCLUSAO


def atualizar_status_ordem(ordem_id, status):
    status = str(status or "").strip().upper()
    if status not in STATUS_OS:
        raise ValueError("Status de OS invalido.")
    with conn() as c:
        c.execute(
            "UPDATE ordens_servico SET status=?, data_atualizacao=datetime('now') WHERE id=?",
            (status, ordem_id),
        )
        c.commit()
    return status


def destravar_ordem(ordem_id):
    """Libera uma OS importada para edição e nova transformação."""
    with conn() as c:
        row = c.execute(
            "SELECT id, status, aprovada_inicio, importada_orcamento_id FROM ordens_servico WHERE id=?",
            (ordem_id,),
        ).fetchone()
        if not row:
            raise ValueError("OS não localizada.")

        orcamento_id = row["importada_orcamento_id"]
        novo_status = row["status"]
        if str(novo_status or "").upper() == "IMPORTADA_ORCAMENTO":
            novo_status = "APROVADA_INICIO" if int(row["aprovada_inicio"] or 0) else "AGUARDANDO_APROVACAO"

        c.execute(
            """
            UPDATE ordens_servico
            SET travada=0, importada_orcamento_id=NULL, status=?,
                data_atualizacao=datetime('now')
            WHERE id=?
            """,
            (novo_status, ordem_id),
        )
        if orcamento_id:
            c.execute(
                "UPDATE orcamentos SET ordem_servico_id=NULL WHERE id=? AND ordem_servico_id=?",
                (orcamento_id, ordem_id),
            )
        c.commit()
    return novo_status


def salvar_ordem(dados, ordem_id=None):
    if ordem_id and ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada. Duplique ou crie uma nova OS para alterar.")
    if ordem_id and not ordem_permite_edicao_basica(ordem_id):
        raise ValueError("Esta OS nao permite alteracao direta. Crie uma nova OS para substituir o registro.")

    numero = str(dados.get("numero") or "").strip() or gerar_numero_os()
    campos = [
        "numero", "orcamento_id", "contrato_id", "cliente_id", "segmento_id", "objeto",
        "local_execucao", "municipio", "solicitante", "executor", "responsavel_tecnico",
        "fiscal_cliente", "gestor", "data_emissao", "data_prevista_inicio",
        "data_prevista_fim", "status", "observacao", "latitude", "longitude", "executor_id",
    ]
    valores = {campo: dados.get(campo) for campo in campos}
    valores["numero"] = numero
    valores["status"] = valores.get("status") or "RASCUNHO"

    with conn() as c:
        if ordem_id:
            sets = ", ".join([f"{campo}=?" for campo in campos])
            c.execute(
                f"UPDATE ordens_servico SET {sets}, data_atualizacao=datetime('now') WHERE id=?",
                [valores[campo] for campo in campos] + [ordem_id],
            )
        else:
            cols = ", ".join(campos)
            qs = ", ".join(["?"] * len(campos))
            cur = c.execute(
                f"INSERT INTO ordens_servico({cols}) VALUES({qs})",
                [valores[campo] for campo in campos],
            )
            ordem_id = cur.lastrowid
        c.commit()
    get_os_dir(ordem_id)
    return ordem_id


def excluir_ordem(ordem_id):
    if not ordem_permite_exclusao(ordem_id):
        raise ValueError("Esta OS nao pode ser excluida porque ja foi aprovada, executada, importada para orcamento ou travada.")
    with conn() as c:
        c.execute("DELETE FROM ordens_servico WHERE id=?", (ordem_id,))
        c.commit()


def aprovar_inicio(ordem_id, usuario="Admin/Gestor"):
    with conn() as c:
        c.execute(
            """
            UPDATE ordens_servico
            SET status='APROVADA_INICIO', aprovada_inicio=1, aprovada_por=?,
                aprovada_em=datetime('now'), data_atualizacao=datetime('now')
            WHERE id=?
            """,
            (usuario, ordem_id),
        )
        c.commit()


def travar_ordem(ordem_id):
    with conn() as c:
        c.execute(
            "UPDATE ordens_servico SET travada=1, data_atualizacao=datetime('now') WHERE id=?",
            (ordem_id,),
        )
        c.commit()


def salvar_etapa(ordem_id, dados, etapa_id=None):
    if ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada.")
    with conn() as c:
        if etapa_id:
            c.execute(
                """
                UPDATE os_etapas
                SET nome=?, descricao=?, status=?, percentual_execucao=?, observacao=?
                WHERE id=?AND ordem_servico_id=?
                """,
                (
                    dados.get("nome"), dados.get("descricao"), dados.get("status"),
                    dados.get("percentual_execucao") or 0, dados.get("observacao"),
                    etapa_id, ordem_id,
                ),
            )
        else:
            ordem = c.execute(
                "SELECT COALESCE(MAX(ordem),0)+1 FROM os_etapas WHERE ordem_servico_id=?",
                (ordem_id,),
            ).fetchone()[0]
            cur = c.execute(
                """
                INSERT INTO os_etapas(ordem_servico_id,nome,descricao,ordem,status,percentual_execucao,observacao)
                VALUES(?,?,?,?,?,?,?)
                """,
                (
                    ordem_id, dados.get("nome"), dados.get("descricao"), ordem,
                    dados.get("status") or "PLANEJADA", dados.get("percentual_execucao") or 0,
                    dados.get("observacao"),
                ),
            )
            etapa_id = cur.lastrowid
        c.commit()
    return etapa_id


def listar_etapas(ordem_id):
    with conn() as c:
        return c.execute(
            "SELECT * FROM os_etapas WHERE ordem_servico_id=?ORDER BY ordem, id",
            (ordem_id,),
        ).fetchall()


def excluir_etapa(ordem_id, etapa_id):
    if ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada.")
    with conn() as c:
        c.execute("DELETE FROM os_etapas WHERE id=?AND ordem_servico_id=?", (etapa_id, ordem_id))
        c.commit()


def proximo_codigo_item(ordem_id, prefixo="OS"):
    prefixo = "".join(ch for ch in str(prefixo or "OS").upper() if ch.isalnum()) or "OS"
    base = f"{prefixo}-"
    with conn() as c:
        rows = c.execute(
            "SELECT codigo FROM os_itens WHERE ordem_servico_id=?AND UPPER(COALESCE(codigo,'')) LIKE ?",
            (ordem_id, base + "%"),
        ).fetchall()
    maior = 0
    for row in rows:
        try:
            maior = max(maior, int(str(row["codigo"]).split("-")[-1]))
        except Exception:
            continue
    return f"{base}{maior + 1:03d}"


def salvar_item(ordem_id, dados, item_id=None):
    if ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada.")
    if not item_id and not str(dados.get("codigo") or "").strip():
        fonte = str(dados.get("fonte") or "").lower()
        prefixo = "COMP" if "compos" in fonte else "OS"
        dados["codigo"] = proximo_codigo_item(ordem_id, prefixo)
    with conn() as c:
        if item_id:
            c.execute(
                """
                UPDATE os_itens
                SET etapa_id=?, descricao=?, unidade=?, quantidade_prevista=?, quantidade_executada=?,
                    fonte=?, codigo=?, observacao=?, importar_orcamento=?
                WHERE id=?AND ordem_servico_id=?
                """,
                (
                    dados.get("etapa_id"), dados.get("descricao"), dados.get("unidade"),
                    dados.get("quantidade_prevista") or 0, dados.get("quantidade_executada") or 0,
                    dados.get("fonte"), dados.get("codigo"), dados.get("observacao"),
                    1 if dados.get("importar_orcamento", True) else 0, item_id, ordem_id,
                ),
            )
        else:
            cur = c.execute(
                """
                INSERT INTO os_itens(ordem_servico_id,etapa_id,descricao,unidade,quantidade_prevista,
                                     quantidade_executada,fonte,codigo,observacao,importar_orcamento)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ordem_id, dados.get("etapa_id"), dados.get("descricao"), dados.get("unidade"),
                    dados.get("quantidade_prevista") or 0, dados.get("quantidade_executada") or 0,
                    dados.get("fonte"), dados.get("codigo"), dados.get("observacao"),
                    1 if dados.get("importar_orcamento", True) else 0,
                ),
            )
            item_id = cur.lastrowid
        c.commit()
    return item_id


def listar_itens(ordem_id):
    with conn() as c:
        return c.execute(
            """
            SELECT i.*, e.nome AS etapa_nome
            FROM os_itens i
            LEFT JOIN os_etapas e ON e.id=i.etapa_id
            WHERE i.ordem_servico_id=?
            ORDER BY e.ordem, i.id
            """,
            (ordem_id,),
        ).fetchall()


def excluir_item(ordem_id, item_id):
    if ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada.")
    with conn() as c:
        c.execute("DELETE FROM os_itens WHERE id=?AND ordem_servico_id=?", (item_id, ordem_id))
        c.commit()


def copiar_para_os(ordem_id, origem, subpasta):
    origem = Path(origem)
    if not origem.exists() or not origem.is_file():
        raise FileNotFoundError(f"Arquivo nao encontrado: {origem}")
    destino_dir = get_os_dir(ordem_id) / subpasta
    destino = _unique_path(destino_dir, origem.name)
    shutil.copy2(origem, destino)
    return destino


def adicionar_foto(ordem_id, origem, etapa_id, categoria, legenda="", usuario="", observacao=""):
    if ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada.")
    categoria = categoria if categoria in FOTO_CATEGORIAS else "Durante"
    destino = copiar_para_os(ordem_id, origem, "fotos")
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO os_fotos(ordem_servico_id,etapa_id,categoria,legenda,caminho,nome_arquivo,usuario,observacao)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (ordem_id, etapa_id, categoria, legenda, str(destino), destino.name, usuario, observacao),
        )
        c.commit()
        return cur.lastrowid


def listar_fotos(ordem_id):
    with conn() as c:
        return c.execute(
            """
            SELECT f.*, e.nome AS etapa_nome
            FROM os_fotos f
            LEFT JOIN os_etapas e ON e.id=f.etapa_id
            WHERE f.ordem_servico_id=?
            ORDER BY e.ordem, f.categoria, f.id
            """,
            (ordem_id,),
        ).fetchall()


def _normalizar_chave(texto):
    import unicodedata
    texto = unicodedata.normalize("NFD", str(texto or ""))
    texto = "".join(ch for ch in texto if unicodedata.category(ch) != "Mn")
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in texto).strip("_")


def importar_pacote_executor(arquivo_zip, ordem_id=None, usuario="Importação executor"):
    arquivo_zip = Path(arquivo_zip)
    if not arquivo_zip.exists():
        raise FileNotFoundError(f"Pacote nao encontrado: {arquivo_zip}")
    if arquivo_zip.suffix.lower() != ".zip":
        raise ValueError("Selecione o pacote ZIP enviado pelo executor.")

    temp_dir = get_os_dir(ordem_id or "") / "_importacao_executor_tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)

    fotos_importadas = 0
    resumo_importado = None
    with zipfile.ZipFile(arquivo_zip, "r") as zf:
        zf.extractall(temp_dir)

    resumo_files = list(temp_dir.rglob("*_resumo_execucao.txt"))
    if resumo_files:
        resumo_importado = resumo_files[0].read_text(encoding="utf-8", errors="ignore")
        if not ordem_id:
            for line in resumo_importado.splitlines():
                if line.upper().startswith("OS:"):
                    numero = line.split(":", 1)[1].strip()
                    with conn() as c:
                        row = c.execute("SELECT id FROM ordens_servico WHERE numero=?", (numero,)).fetchone()
                    if row:
                        ordem_id = row["id"]
                    break
    if not ordem_id:
        raise ValueError("Nao foi possivel identificar a OS pelo pacote. Abra a OS correta e importe novamente.")

    etapas = listar_etapas(ordem_id)
    etapa_por_chave = {_normalizar_chave(e["nome"]): e["id"] for e in etapas}
    categorias_por_chave = {_normalizar_chave(cat): cat for cat in FOTO_CATEGORIAS}
    extensoes = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    for foto in temp_dir.rglob("*"):
        if not foto.is_file() or foto.suffix.lower() not in extensoes:
            continue
        partes = [_normalizar_chave(p) for p in foto.relative_to(temp_dir).parts]
        etapa_id = None
        categoria = None
        for parte in partes:
            if etapa_id is None and parte in etapa_por_chave:
                etapa_id = etapa_por_chave[parte]
            if categoria is None and parte in categorias_por_chave:
                categoria = categorias_por_chave[parte]
        if categoria is None:
            nome = _normalizar_chave(foto.stem)
            for chave, cat in categorias_por_chave.items():
                if chave in nome:
                    categoria = cat
                    break
        categoria = categoria or "Durante"
        legenda = f"Importado do pacote do executor - {foto.name}"
        adicionar_foto(ordem_id, foto, etapa_id, categoria, legenda, usuario, resumo_importado or "")
        fotos_importadas += 1

    shutil.rmtree(temp_dir, ignore_errors=True)
    return {"ordem_id": ordem_id, "fotos": fotos_importadas, "resumo": bool(resumo_importado)}


def excluir_foto(ordem_id, foto_id):
    if ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada.")
    with conn() as c:
        c.execute("DELETE FROM os_fotos WHERE id=?AND ordem_servico_id=?", (foto_id, ordem_id))
        c.commit()


def adicionar_anexo(ordem_id, origem, etapa_id=None, tipo="Orcamento de terceiro", observacao="", usuario="", importar=True):
    if ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada.")
    destino = copiar_para_os(ordem_id, origem, "anexos")
    with conn() as c:
        cur = c.execute(
            """
            INSERT INTO os_anexos(ordem_servico_id,etapa_id,tipo,nome_arquivo,caminho,usuario,observacao,importar_orcamento)
            VALUES(?,?,?,?,?,?,?,?)
            """,
            (ordem_id, etapa_id, tipo, destino.name, str(destino), usuario, observacao, 1 if importar else 0),
        )
        c.commit()
        return cur.lastrowid


def listar_anexos(ordem_id):
    with conn() as c:
        return c.execute(
            """
            SELECT a.*, e.nome AS etapa_nome
            FROM os_anexos a
            LEFT JOIN os_etapas e ON e.id=a.etapa_id
            WHERE a.ordem_servico_id=?
            ORDER BY a.id DESC
            """,
            (ordem_id,),
        ).fetchall()


def excluir_anexo(ordem_id, anexo_id):
    if ordem_travada(ordem_id):
        raise ValueError("Esta OS esta travada.")
    with conn() as c:
        c.execute("DELETE FROM os_anexos WHERE id=?AND ordem_servico_id=?", (anexo_id, ordem_id))
        c.commit()


def _gerar_codigo_orcamento():
    ano = datetime.now().year
    prefixo = f"ORC-{ano}-"
    with conn() as c:
        rows = c.execute(
            "SELECT codigo FROM orcamentos WHERE codigo LIKE ?",
            (prefixo + "%",),
        ).fetchall()
    numeros = []
    padrao = re.compile(rf"^{re.escape(prefixo)}(\d{{3}})$")
    for row in rows:
        match = padrao.fullmatch(str(row["codigo"] or ""))
        if match:
            numeros.append(int(match.group(1)))
    prox = max(numeros, default=0) + 1
    return prefixo + f"{prox:03d}"


def _sincronizar_anexos_os_no_orcamento(ordem_id, orcamento_id, anexos):
    """Copia anexos marcados uma unica vez, preservando o uso pela OS."""
    destino_orc = get_anexos_dir(orcamento_id)
    copiados = 0
    with conn() as c:
        for anexo in anexos:
            identificacao = " ".join(
                str(anexo[chave] or "")
                for chave in ("tipo", "nome_arquivo", "observacao")
            ).lower()
            eh_oficio = "oficio" in identificacao or "ofício" in identificacao
            # Ofício é comprovante obrigatório. Comparativos e demais anexos
            # permanecem sob inclusão manual no orçamento.
            if not eh_oficio:
                continue
            origem = Path(anexo["caminho"] or "")
            if not origem.exists() or not origem.is_file():
                continue
            ja_importado = c.execute(
                """
                SELECT id
                FROM documentos
                WHERE orcamento_id=? AND ordem_servico_id=? AND nome_arquivo=?
                LIMIT 1
                """,
                (orcamento_id, ordem_id, anexo["nome_arquivo"] or origem.name),
            ).fetchone()
            if ja_importado:
                continue
            destino = _unique_path(destino_orc, origem.name)
            shutil.copy2(origem, destino)
            c.execute(
                """
                INSERT INTO documentos(orcamento_id,ordem_servico_id,tipo,nome_arquivo,caminho,data_upload,usuario,observacao)
                VALUES(?,?,?,?,?,datetime('now'),?,?)
                """,
                (
                    orcamento_id, ordem_id, anexo["tipo"] or "Orcamento de terceiro",
                    destino.name, str(destino), anexo["usuario"], anexo["observacao"],
                ),
            )
            copiados += 1
        c.commit()
    return copiados


def _completar_estrutura_orcamento_vazia(ordem_id, orcamento_id):
    """Importa a estrutura da OS somente quando o orçamento ainda não tem itens."""
    etapas = listar_etapas(ordem_id)
    itens = listar_itens(ordem_id)
    with conn() as c:
        qtd_itens = c.execute(
            "SELECT COUNT(*) FROM itens WHERE orcamento_id=?",
            (orcamento_id,),
        ).fetchone()[0]
        if qtd_itens:
            return False

        etapas_existentes = c.execute(
            "SELECT id,nome FROM etapas_orcamento WHERE orcamento_id=?",
            (orcamento_id,),
        ).fetchall()
        por_nome = {
            str(etapa["nome"] or "").strip().casefold(): etapa["id"]
            for etapa in etapas_existentes
        }
        mapa_etapas = {}
        for etapa in etapas:
            chave = str(etapa["nome"] or "").strip().casefold()
            etapa_orc_id = por_nome.get(chave)
            if not etapa_orc_id:
                cur = c.execute(
                    """
                    INSERT INTO etapas_orcamento(orcamento_id,nome,descricao,ordem)
                    VALUES(?,?,?,?)
                    """,
                    (orcamento_id, etapa["nome"], etapa["descricao"], etapa["ordem"]),
                )
                etapa_orc_id = cur.lastrowid
                por_nome[chave] = etapa_orc_id
            mapa_etapas[etapa["id"]] = etapa_orc_id

        for item in itens:
            if not int(item["importar_orcamento"] or 0):
                continue
            qtd = float(item["quantidade_executada"] or item["quantidade_prevista"] or 0)
            c.execute(
                """
                INSERT INTO itens(orcamento_id,etapa_id,etapa,fonte,codigo,descricao,unidade,
                                  quantidade,custo_unit,bdi,margem,capex_opex,classificacao,observacao)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    orcamento_id, mapa_etapas.get(item["etapa_id"]), item["etapa_nome"],
                    item["fonte"] or "OS", item["codigo"], item["descricao"],
                    item["unidade"] or "UN", qtd, 0, 0, 18, "CAPEX",
                    "Importado da OS", item["observacao"],
                ),
            )
        c.commit()
    return True


def _registrar_documento_gerado(orcamento_id, ordem_id, tipo, arquivo, observacao):
    arquivo = Path(arquivo)
    with conn() as c:
        existente = c.execute(
            """
            SELECT id FROM documentos
            WHERE orcamento_id=? AND ordem_servico_id=? AND tipo=?
            LIMIT 1
            """,
            (orcamento_id, ordem_id, tipo),
        ).fetchone()
        if existente:
            c.execute(
                """
                UPDATE documentos
                SET nome_arquivo=?, caminho=?, data_upload=datetime('now'), observacao=?
                WHERE id=?
                """,
                (arquivo.name, str(arquivo), observacao, existente["id"]),
            )
        else:
            c.execute(
                """
                INSERT INTO documentos(orcamento_id,ordem_servico_id,tipo,nome_arquivo,caminho,data_upload,usuario,observacao)
                VALUES(?,?,?,?,?,datetime('now'),?,?)
                """,
                (
                    orcamento_id, ordem_id, tipo, arquivo.name, str(arquivo),
                    "Sistema", observacao,
                ),
            )
        c.commit()


def _gerar_tabela_sinapi_utilizada(ordem_id, orcamento_id):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    destino = get_anexos_dir(orcamento_id) / "Tabela_SINAPI_Utilizada.xlsx"
    with conn() as c:
        itens = c.execute(
            """
            SELECT COALESCE(e.nome,i.etapa,'') AS etapa, i.codigo, i.descricao, i.unidade,
                   i.quantidade, i.custo_unit, i.bdi, i.margem, i.classificacao,
                   (SELECT s.descricao FROM sinapi s WHERE s.codigo=i.codigo
                    ORDER BY s.competencia DESC, s.id DESC LIMIT 1) AS descricao_sinapi,
                   (SELECT s.unidade FROM sinapi s WHERE s.codigo=i.codigo
                    ORDER BY s.competencia DESC, s.id DESC LIMIT 1) AS unidade_sinapi,
                   (SELECT s.custo FROM sinapi s WHERE s.codigo=i.codigo
                    ORDER BY s.competencia DESC, s.id DESC LIMIT 1) AS custo_sinapi,
                   (SELECT s.competencia FROM sinapi s WHERE s.codigo=i.codigo
                    ORDER BY s.competencia DESC, s.id DESC LIMIT 1) AS competencia_sinapi,
                   (SELECT s.uf FROM sinapi s WHERE s.codigo=i.codigo
                    ORDER BY s.competencia DESC, s.id DESC LIMIT 1) AS uf_sinapi,
                   (SELECT s.fonte FROM sinapi s WHERE s.codigo=i.codigo
                    ORDER BY s.competencia DESC, s.id DESC LIMIT 1) AS fonte_sinapi
            FROM itens i
            LEFT JOIN etapas_orcamento e
                   ON e.id=i.etapa_id AND e.orcamento_id=i.orcamento_id
            WHERE i.orcamento_id=?
              AND UPPER(TRIM(COALESCE(i.fonte,'')))='SINAPI'
            ORDER BY COALESCE(e.ordem,9999), i.id
            """,
            (orcamento_id,),
        ).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "SINAPI utilizada"
    ws.append([
        "Etapa", "Código SINAPI", "Descrição do orçamento", "UN", "Quantidade",
        "Custo unitário usado", "BDI %", "Margem %", "Classificação",
        "Descrição na base SINAPI", "UN SINAPI", "Custo na base SINAPI",
        "Mês/ano de referência", "UF", "Fonte oficial",
    ])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="0B3B75")
    for item in itens:
        ws.append([
            item["etapa"], item["codigo"], item["descricao"], item["unidade"],
            item["quantidade"], item["custo_unit"], item["bdi"], item["margem"],
            item["classificacao"], item["descricao_sinapi"], item["unidade_sinapi"],
            item["custo_sinapi"], item["competencia_sinapi"], item["uf_sinapi"],
            item["fonte_sinapi"],
        ])
    obs = wb.create_sheet("Observações para conferência")
    obs.append(["ORIENTAÇÕES DE RASTREABILIDADE E CONFERÊNCIA - TCU"])
    obs.append([
        "Esta planilha registra os itens SINAPI efetivamente utilizados no orçamento, "
        "com código, descrição, unidade, custo e mês/ano de referência da base oficial."
    ])
    obs.append([
        "Para conferência, validar código, competência, UF, regime/tipo da referência, "
        "unidade, custo unitário e compatibilidade entre a descrição SINAPI e o serviço orçado."
    ])
    obs.append([
        "Eventuais equivalências, adaptações, composições próprias, diferenças de produtividade "
        "ou preços de mercado devem permanecer justificadas no item e acompanhadas da memória "
        "de cálculo e dos documentos comprobatórios aplicáveis."
    ])
    obs.append([
        "A rastreabilidade deve preservar a tabela oficial utilizada, a data da consulta, "
        "os quantitativos, BDI, margem, orçamento, OS, ofício e evidências da execução, "
        "permitindo reexecução dos cálculos e fiscalização pelos controles interno e externo."
    ])
    obs.column_dimensions["A"].width = 125
    for linha in obs.iter_rows():
        linha[0].alignment = Alignment(wrap_text=True, vertical="top")
    for coluna in ws.columns:
        letra = get_column_letter(coluna[0].column)
        ws.column_dimensions[letra].width = min(
            60, max(12, max(len(str(celula.value or "")) for celula in coluna) + 2)
        )
    wb.save(destino)
    _registrar_documento_gerado(
        orcamento_id, ordem_id, "Tabela SINAPI utilizada", destino,
        "Cópia das referências SINAPI efetivamente utilizadas no orçamento.",
    )
    return destino


def _garantir_documentos_comprobatorios(ordem_id, orcamento_id, anexos):
    _sincronizar_anexos_os_no_orcamento(ordem_id, orcamento_id, anexos)
    relatorio = gerar_pdf_relatorio(ordem_id, get_anexos_dir(orcamento_id))
    _registrar_documento_gerado(
        orcamento_id, ordem_id, "OS completa - comprovação da execução", relatorio,
        "Relatório completo da OS com etapas, execução, fotos, anexos e dados de entrega.",
    )
    _gerar_tabela_sinapi_utilizada(ordem_id, orcamento_id)


def importar_para_orcamento(ordem_id, orcamento_id=None):
    os_row = obter_ordem(ordem_id)
    if not os_row:
        raise ValueError("OS nao localizada.")
    if not int(os_row["aprovada_inicio"] or 0):
        raise ValueError("A OS precisa estar aprovada para inicio antes de virar orcamento.")

    # Quando a OS já aponta um orçamento de origem, o usuário quer apenas
    # consolidar o vínculo, sem gerar outro orçamento nem duplicar seus itens.
    orcamento_origem_id = os_row["orcamento_id"]
    if orcamento_id and orcamento_origem_id and int(orcamento_id) == int(orcamento_origem_id):
        anexos = listar_anexos(ordem_id)
        with conn() as c:
            existente = c.execute(
                "SELECT * FROM orcamentos WHERE id=?",
                (orcamento_id,),
            ).fetchone()
            if not existente:
                raise ValueError("O orçamento indicado no cadastro da OS não foi localizado.")
            c.execute(
                """
                UPDATE orcamentos
                SET ordem_servico_id=?,
                    cliente_id=COALESCE(cliente_id, ?),
                    contrato_id=COALESCE(contrato_id, ?),
                    segmento_id=COALESCE(segmento_id, ?),
                    objeto=COALESCE(NULLIF(TRIM(objeto), ''), NULLIF(TRIM(?), ''), objeto),
                    municipio=COALESCE(NULLIF(TRIM(municipio), ''), NULLIF(TRIM(?), ''), municipio),
                    texto_proposta=COALESCE(NULLIF(TRIM(texto_proposta), ''), NULLIF(TRIM(?), ''), texto_proposta),
                    observacoes=COALESCE(NULLIF(TRIM(observacoes), ''), NULLIF(TRIM(?), ''), observacoes),
                    data_atualizacao=datetime('now')
                WHERE id=?
                """,
                (
                    ordem_id, os_row["cliente_id"], os_row["contrato_id"],
                    os_row["segmento_id"], os_row["objeto"], os_row["municipio"],
                    os_row["observacao"], os_row["observacao"], orcamento_id,
                ),
            )
            c.commit()
        _completar_estrutura_orcamento_vazia(ordem_id, orcamento_id)
        _garantir_documentos_comprobatorios(ordem_id, orcamento_id, anexos)
        with conn() as c:
            c.execute(
                """
                UPDATE ordens_servico
                SET status='IMPORTADA_ORCAMENTO', travada=1,
                    importada_orcamento_id=?, data_atualizacao=datetime('now')
                WHERE id=?
                """,
                (orcamento_id, ordem_id),
            )
            c.commit()
        return orcamento_id

    etapas = listar_etapas(ordem_id)
    itens = listar_itens(ordem_id)
    anexos = listar_anexos(ordem_id)
    fotos = listar_fotos(ordem_id)

    with conn() as c:
        if not orcamento_id:
            cur = c.execute(
                """
                INSERT INTO orcamentos(codigo, cliente_id, contrato_id, segmento_id, objeto, municipio,
                                       validade, texto_proposta, bdi_global, margem_global, status,
                                       ordem_servico_id, data_criacao, data_atualizacao)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
                """,
                (
                    _gerar_codigo_orcamento(), os_row["cliente_id"], os_row["contrato_id"],
                    os_row["segmento_id"], os_row["objeto"], os_row["municipio"], "60 dias",
                    "Orcamento gerado a partir de Ordem de Servico aprovada.",
                    0, 18, "RASCUNHO", ordem_id,
                ),
            )
            orcamento_id = cur.lastrowid
        else:
            c.execute(
                "UPDATE orcamentos SET ordem_servico_id=?, data_atualizacao=datetime('now') WHERE id=?",
                (ordem_id, orcamento_id),
            )

        mapa_etapas = {}
        for etapa in etapas:
            cur = c.execute(
                """
                INSERT INTO etapas_orcamento(orcamento_id,nome,descricao,ordem)
                VALUES(?,?,?,?)
                """,
                (orcamento_id, etapa["nome"], etapa["descricao"], etapa["ordem"]),
            )
            mapa_etapas[etapa["id"]] = cur.lastrowid

        for item in itens:
            if not int(item["importar_orcamento"] or 0):
                continue
            qtd = float(item["quantidade_executada"] or item["quantidade_prevista"] or 0)
            etapa_orc_id = mapa_etapas.get(item["etapa_id"])
            c.execute(
                """
                INSERT INTO itens(orcamento_id, etapa_id, etapa, fonte, codigo, descricao, unidade,
                                  quantidade, custo_unit, bdi, margem, capex_opex, classificacao, observacao)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    orcamento_id, etapa_orc_id, item["etapa_nome"], item["fonte"] or "OS",
                    item["codigo"], item["descricao"], item["unidade"] or "UN", qtd,
                    0, 0, 18, "CAPEX", "Importado da OS", item["observacao"],
                ),
            )
        c.commit()

    destino_orc = get_anexos_dir(orcamento_id)
    _garantir_documentos_comprobatorios(ordem_id, orcamento_id, anexos)
    with conn() as c:
        for foto in fotos:
            origem = Path(foto["caminho"] or "")
            if origem.exists():
                destino = _unique_path(destino_orc, origem.name)
                shutil.copy2(origem, destino)
                c.execute(
                    """
                    INSERT INTO documentos(orcamento_id,ordem_servico_id,tipo,nome_arquivo,caminho,data_upload,usuario,observacao)
                    VALUES(?,?,?,?,?,datetime('now'),?,?)
                    """,
                    (
                        orcamento_id, ordem_id, f"Foto execucao - {foto['categoria']}",
                        destino.name, str(destino), foto["usuario"],
                        f"{foto['etapa_nome'] or ''} - {foto['legenda'] or ''}".strip(" -"),
                    ),
                )
        c.execute(
            """
            UPDATE ordens_servico
            SET status='IMPORTADA_ORCAMENTO', travada=1, importada_orcamento_id=?,
                data_atualizacao=datetime('now')
            WHERE id=?
            """,
            (orcamento_id, ordem_id),
        )
        c.commit()

    return orcamento_id


def _ordem_contexto(ordem_id):
    with conn() as c:
        ordem = c.execute(
            """
            SELECT os.*, cli.nome AS cliente_nome, ct.nome AS contrato_nome, s.nome AS segmento_nome,
                   emp.razao AS empresa_razao, emp.fantasia AS empresa_fantasia,
                   emp.cnpj AS empresa_cnpj, emp.logo_path, emp.endereco AS empresa_endereco,
                   emp.municipio AS empresa_municipio, emp.uf AS empresa_uf,
                   emp.telefone AS empresa_telefone, emp.email AS empresa_email,
                   emp.site AS empresa_site
            FROM ordens_servico os
            LEFT JOIN clientes cli ON cli.id=os.cliente_id
            LEFT JOIN contratos ct ON ct.id=os.contrato_id
            LEFT JOIN segmentos s ON s.id=os.segmento_id
            LEFT JOIN empresa emp ON emp.id=1
            WHERE os.id=?
            """,
            (ordem_id,),
        ).fetchone()
    if not ordem:
        raise ValueError("OS nao localizada.")
    return {
        "ordem": ordem,
        "etapas": listar_etapas(ordem_id),
        "itens": listar_itens(ordem_id),
        "fotos": listar_fotos(ordem_id),
        "anexos": listar_anexos(ordem_id),
    }


def _rodape_profissional_os(ordem):
    from reportlab.lib import colors

    empresa = ordem["empresa_razao"] or ordem["empresa_fantasia"] or "Fornecedor"
    contato = " | ".join(x for x in (
        ordem["empresa_endereco"],
        "/".join(x for x in (ordem["empresa_municipio"], ordem["empresa_uf"]) if x),
        ordem["empresa_telefone"], ordem["empresa_email"], ordem["empresa_site"],
    ) if x)

    def desenhar(canvas, doc):
        largura, _ = canvas._pagesize
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#0B3B75"))
        canvas.line(18, 22, largura - 18, 22)
        canvas.setFillColor(colors.HexColor("#526276"))
        canvas.setFont("Helvetica-Bold", 5.8)
        canvas.drawCentredString(
            largura / 2, 14,
            f"DOCUMENTO EMITIDO POR {empresa} | CNPJ: {ordem['empresa_cnpj'] or '-'}",
        )
        canvas.setFont("Helvetica", 5.4)
        canvas.drawCentredString(largura / 2, 7, contato)
        canvas.drawRightString(largura - 18, 14, f"Página {doc.page}")
        canvas.restoreState()
    return desenhar


def _payload_portal_executor(ctx):
    itens_por_etapa = {}
    for item in ctx["itens"]:
        chave = str(item["etapa_id"] if item["etapa_id"] is not None else "geral")
        itens_por_etapa.setdefault(chave, []).append({
            "codigo": item["codigo"] or "",
            "descricao": item["descricao"] or "",
            "unidade": item["unidade"] or "",
            "quantidade": item["quantidade_prevista"] or "",
            "origem": item["fonte"] or "",
        })
    etapas = []
    for etapa in ctx["etapas"]:
        chave = str(etapa["id"])
        etapas.append({
            "id": chave,
            "nome": etapa["nome"] or "Etapa",
            "descricao": etapa["descricao"] or "",
            "itens": itens_por_etapa.get(chave, []),
        })
    if not etapas:
        etapas.append({
            "id": "geral",
            "nome": "Registro fotográfico",
            "descricao": "",
            "itens": itens_por_etapa.get("geral", []),
        })
    ordem = ctx["ordem"]
    return {
        "numero": ordem["numero"] or "OS",
        "cliente": ordem["cliente_nome"] or "",
        "objeto": ordem["objeto"] or "",
        "local": ordem["local_execucao"] or ordem["municipio"] or "",
        "executor": ordem["executor"] or "",
        "etapas": etapas,
    }


def _base64url_json(dados):
    bruto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii").rstrip("=")


def gerar_url_portal_executor(ordem_id):
    base_url = database.get_config("portal_executor_url", "").strip()
    if not base_url:
        return ""
    ctx = _ordem_contexto(ordem_id)
    token = _base64url_json(_payload_portal_executor(ctx))
    separador = "&" if "?" in base_url else "?"
    return f"{base_url.rstrip('/')}{separador}d={token}"


def gerar_link_executor(ordem_id):
    url = gerar_url_portal_executor(ordem_id)
    if url:
        return {"tipo": "web", "url": url, "arquivo": None}
    arquivo = gerar_html_executor(ordem_id)
    return {"tipo": "arquivo", "url": "", "arquivo": arquivo}


def pasta_saida_os(ordem, pasta_destino=None):
    if pasta_destino:
        base = Path(pasta_destino) / _safe_filename(ordem["numero"] or f"OS_{ordem['id']}")
    else:
        base = get_pasta_local_relatorios() / "Ordens_de_Servico" / _safe_filename(ordem["numero"] or f"OS_{ordem['id']}")
    base.mkdir(parents=True, exist_ok=True)
    return base


def _texto_base_controle():
    return (
        "Documento preparado para apoiar a fiscalizacao, a medicao e o recebimento "
        "da execucao. O registro consolida autorizacao de inicio, etapas, quantitativos, "
        "evidencias fotograficas, anexos preservados, pendencias/correcoes e assinaturas, "
        "em linha com a Lei 14.133/2021, especialmente os arts. 117 e 140, e com boas "
        "praticas do TCU para medicao, comprovacao e recebimento do objeto."
    )


def _etapa_por_id(etapas):
    return {etapa["id"]: etapa for etapa in etapas}


def _linhas_resumo_ordem(ordem):
    return [
        ("Numero da OS", ordem["numero"]),
        ("Status", ordem["status"]),
        ("Cliente", ordem["cliente_nome"]),
        ("Contrato", ordem["contrato_nome"]),
        ("Objeto", ordem["objeto"]),
        ("Local", ordem["local_execucao"]),
        ("Municipio", ordem["municipio"]),
        ("Solicitante", ordem["solicitante"]),
        ("Executor", ordem["executor"]),
        ("Responsavel tecnico", ordem["responsavel_tecnico"]),
        ("Fiscal/Cliente", ordem["fiscal_cliente"]),
        ("Gestor", ordem["gestor"]),
        ("Emissao", ordem["data_emissao"]),
        ("Inicio previsto", ordem["data_prevista_inicio"]),
        ("Fim previsto", ordem["data_prevista_fim"]),
        ("Aprovacao de inicio", "Sim" if int(ordem["aprovada_inicio"] or 0) else "Nao"),
        ("Aprovada por", ordem["aprovada_por"]),
        ("Aprovada em", ordem["aprovada_em"]),
        ("Observacoes", ordem["observacao"]),
    ]


def _linhas_etapas_itens(ctx):
    etapa_map = _etapa_por_id(ctx["etapas"])
    linhas = []
    etapas_sem_item = {etapa["id"] for etapa in ctx["etapas"]}
    for item in ctx["itens"]:
        etapa = etapa_map.get(item["etapa_id"])
        if etapa:
            etapas_sem_item.discard(etapa["id"])
        linhas.append({
            "etapa": etapa["nome"] if etapa else item["etapa_nome"],
            "status": etapa["status"] if etapa else "",
            "percentual": etapa["percentual_execucao"] if etapa else "",
            "item": item["descricao"],
            "unidade": item["unidade"],
            "prevista": item["quantidade_prevista"],
            "executada": item["quantidade_executada"],
            "observacao": item["observacao"],
        })
    for etapa in ctx["etapas"]:
        if etapa["id"] in etapas_sem_item:
            linhas.append({
                "etapa": etapa["nome"],
                "status": etapa["status"],
                "percentual": etapa["percentual_execucao"],
                "item": etapa["descricao"] or "Etapa sem item lancado",
                "unidade": "",
                "prevista": "",
                "executada": "",
                "observacao": etapa["observacao"],
            })
    return linhas


def _foto_legenda(foto):
    partes = [
        foto["legenda"] or foto["nome_arquivo"] or "",
        f"Usuario: {foto['usuario']}" if foto["usuario"] else "",
        f"Data: {foto['data_registro']}" if foto["data_registro"] else "",
        f"Localizacao: {foto['latitude']}, {foto['longitude']}" if foto["latitude"] or foto["longitude"] else "",
    ]
    return " | ".join([p for p in partes if p])


def _logo_path_ordem(ordem):
    caminho = Path(ordem["logo_path"] or "")
    return caminho if caminho.exists() else None


def _empresa_nome(ordem):
    return ordem["empresa_fantasia"] or ordem["empresa_razao"] or "Orçamentos PPP"


def _empresa_cnpj(ordem):
    return ordem["empresa_cnpj"] or ""


def _texto_html(texto):
    return html.escape(str(texto or "")).replace("\n", "<br/>")


def _celula_pdf(valor, estilo):
    """Célula ReportLab com quebra automática dentro da largura disponível."""
    from reportlab.platypus import Paragraph
    return Paragraph(_texto_html(valor), estilo)


def _linhas_pdf(linhas, estilo):
    return [[_celula_pdf(valor, estilo) for valor in linha] for linha in linhas]


def _observacoes_executor(ctx):
    textos = []
    vistos = set()
    for foto in ctx["fotos"]:
        obs = str(foto["observacao"] or "").strip()
        if "OBSERVACOES POR ETAPA" not in obs or obs in vistos:
            continue
        vistos.add(obs)
        textos.append(obs)
    registros = []
    for texto in textos:
        atual = None
        for bruto in texto.splitlines():
            linha = bruto.strip()
            if not linha:
                continue
            chave = linha.lower()
            if chave.startswith("etapa:"):
                if atual:
                    registros.append(atual)
                atual = {"etapa": linha.split(":", 1)[1].strip(), "materiais": "", "custos": "", "observacao": ""}
            elif atual and chave.startswith("materiais/ferramentas:"):
                atual["materiais"] = linha.split(":", 1)[1].strip()
            elif atual and (chave.startswith("ocorrencias/despesas") or chave.startswith("ocorrências/despesas")):
                atual["custos"] = linha.split(":", 1)[1].strip()
            elif atual and (chave.startswith("observacao:") or chave.startswith("observação:")):
                atual["observacao"] = linha.split(":", 1)[1].strip()
        if atual:
            registros.append(atual)
    unicos = []
    vistos = set()
    for r in registros:
        key = (r["etapa"], r["materiais"], r["custos"], r["observacao"])
        if key not in vistos:
            vistos.add(key)
            unicos.append(r)
    return unicos


def gerar_pdf_relatorio(ordem_id, pasta_destino=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from PIL import Image as PILImage

    ctx = _ordem_contexto(ordem_id)
    ordem = ctx["ordem"]
    arquivo = pasta_saida_os(ordem, pasta_destino) / "Relatorio_Execucao_Pos_Obra.pdf"
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TextoOS", parent=styles["Normal"], fontSize=8.5, leading=11, wordWrap="CJK", splitLongWords=True))
    styles.add(ParagraphStyle(name="SecaoOS", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#0B3B75")))
    doc = SimpleDocTemplate(str(arquivo), pagesize=A4, rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    story = []
    logo = _logo_path_ordem(ordem)
    empresa = _empresa_nome(ordem)
    cnpj = _empresa_cnpj(ordem)
    cabecalho = []
    if logo:
        cabecalho.append(Image(str(logo), width=3.0*cm, height=1.5*cm))
    cabecalho.append(Paragraph(
        f"<b>{_texto_html(empresa)}</b><br/>CNPJ: {_texto_html(cnpj)} | "
        f"{_texto_html(ordem['empresa_endereco'])} - {_texto_html(ordem['empresa_municipio'])}/{_texto_html(ordem['empresa_uf'])}<br/>"
        f"Tel.: {_texto_html(ordem['empresa_telefone'])} | {_texto_html(ordem['empresa_email'])} | {_texto_html(ordem['empresa_site'])}<br/>"
        f"RELATÓRIO COMPLETO DE EXECUÇÃO E ENTREGA<br/>OS: {_texto_html(ordem['numero'])} | Status: {_texto_html(ordem['status'])}",
        styles["TextoOS"],
    ))
    story.append(Table([cabecalho], colWidths=[3.3*cm, 13*cm] if logo else [16.3*cm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F7FC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9D7E8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ])))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Base de controle e rastreabilidade", styles["SecaoOS"]))
    story.append(Paragraph(_texto_base_controle(), styles["TextoOS"]))
    story.append(Spacer(1, 8))

    resumo = [["Campo", "Informacao"]] + _linhas_pdf(
        [[k, v or ""] for k, v in _linhas_resumo_ordem(ordem)], styles["TextoOS"]
    )
    story.append(Table(resumo, repeatRows=1, splitByRow=1, splitInRow=1, colWidths=[4*cm, 12*cm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3B75")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ])))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Etapas e itens executados", styles["SecaoOS"]))
    data = [["Etapa", "Status", "%", "Item/servico", "Un.", "Qtd prev.", "Qtd exec."]]
    for linha in _linhas_etapas_itens(ctx):
        data.append([
            linha["etapa"] or "", linha["status"] or "", linha["percentual"] or "",
            linha["item"] or "", linha["unidade"] or "", linha["prevista"] or "", linha["executada"] or "",
        ])
    story.append(Table(data, repeatRows=1, colWidths=[2.6*cm, 1.9*cm, 0.9*cm, 5.3*cm, 1.2*cm, 1.7*cm, 1.7*cm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3B75")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])))

    obs_executor = _observacoes_executor(ctx)
    story.append(Spacer(1, 10))
    story.append(Paragraph("Registros informados pelo executor", styles["SecaoOS"]))
    if obs_executor:
        obs_data = [["Etapa", "Materiais/Ferramentas", "Ocorrências/Despesas sem valor", "Observação"]]
        for obs in obs_executor:
            obs_data.append([
                Paragraph(_texto_html(obs["etapa"]), styles["TextoOS"]),
                Paragraph(_texto_html(obs["materiais"] or "-"), styles["TextoOS"]),
                Paragraph(_texto_html(obs["custos"] or "-"), styles["TextoOS"]),
                Paragraph(_texto_html(obs["observacao"] or "-"), styles["TextoOS"]),
            ])
        story.append(Table(obs_data, repeatRows=1, colWidths=[3.3*cm, 4.2*cm, 4.2*cm, 4.3*cm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3B75")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ])))
    else:
        story.append(Paragraph("Nenhuma observação de campo importada do pacote do executor.", styles["TextoOS"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Anexos e orcamentos de terceiros preservados", styles["SecaoOS"]))
    anexos_data = [["Tipo", "Etapa", "Arquivo", "Importa", "Observacao"]]
    for anexo in ctx["anexos"]:
        anexos_data.append([
            anexo["tipo"] or "", anexo["etapa_nome"] or "", anexo["nome_arquivo"] or "",
            "Sim" if int(anexo["importar_orcamento"] or 0) else "Nao", anexo["observacao"] or "",
        ])
    if len(anexos_data) == 1:
        anexos_data.append(["Sem anexos registrados", "", "", "", ""])
    story.append(Table(anexos_data, repeatRows=1, colWidths=[3*cm, 3*cm, 4.5*cm, 1.5*cm, 4*cm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3B75")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])))

    story.append(PageBreak())
    story.append(Paragraph("Registro fotografico por etapa e categoria", styles["SecaoOS"]))
    tem_foto = False
    for etapa in ctx["etapas"]:
        fotos_etapa = [f for f in ctx["fotos"] if f["etapa_id"] == etapa["id"]]
        if not fotos_etapa:
            continue
        story.append(Paragraph(f"Etapa: {etapa['nome']}", styles["Heading3"]))
        for cat in FOTO_CATEGORIAS:
            fotos_cat = [f for f in fotos_etapa if f["categoria"] == cat]
            if not fotos_cat:
                continue
            tem_foto = True
            story.append(Paragraph(cat, styles["Heading4"]))
            for foto in fotos_cat:
                caminho = Path(foto["caminho"] or "")
                if caminho.exists():
                    try:
                        with PILImage.open(caminho) as im:
                            w, h = im.size
                        escala = min(8*cm / max(w, 1), 5.5*cm / max(h, 1))
                        story.append(Image(str(caminho), width=w*escala, height=h*escala))
                    except Exception:
                        pass
                story.append(Paragraph(_foto_legenda(foto), styles["TextoOS"]))
                story.append(Spacer(1, 6))
    if not tem_foto:
        story.append(Paragraph("Nenhuma foto registrada nesta OS.", styles["TextoOS"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Conclusao e ateste de entrega", styles["SecaoOS"]))
    story.append(Paragraph(
        "As partes abaixo declaram ciencia das evidencias apresentadas. A assinatura nao elimina "
        "a necessidade de conferencia tecnica, medicao, saneamento de pendencias e recebimento "
        "formal quando aplicavel ao contrato.",
        styles["TextoOS"],
    ))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Assinaturas", styles["SecaoOS"]))
    assinaturas = [["Executor", "Responsavel tecnico"], ["\n\n____________________________", "\n\n____________________________"], ["Fiscal/Cliente", "Gestor"], ["\n\n____________________________", "\n\n____________________________"]]
    story.append(Table(assinaturas, colWidths=[8*cm, 8*cm], style=TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ])))
    rodape = _rodape_profissional_os(ordem)
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    return arquivo


def gerar_pdf_gerencial(ordem_id, pasta_destino=None):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image

    ctx = _ordem_contexto(ordem_id)
    ordem = ctx["ordem"]
    arquivo = pasta_saida_os(ordem, pasta_destino) / "Relatorio_Gerencial_OS.pdf"
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TextoOS", parent=styles["Normal"], fontSize=8.5, leading=11, wordWrap="CJK", splitLongWords=True))
    styles.add(ParagraphStyle(name="SecaoOS", parent=styles["Heading2"], fontSize=12, textColor=colors.HexColor("#0B3B75")))
    doc = SimpleDocTemplate(str(arquivo), pagesize=A4, rightMargin=1.2*cm, leftMargin=1.2*cm, topMargin=1.2*cm, bottomMargin=1.2*cm)
    story = []

    logo = _logo_path_ordem(ordem)
    empresa = _empresa_nome(ordem)
    cnpj = _empresa_cnpj(ordem)
    cabecalho = []
    if logo:
        cabecalho.append(Image(str(logo), width=3.0*cm, height=1.5*cm))
    cabecalho.append(Paragraph(
        f"<b>{_texto_html(empresa)}</b><br/>CNPJ: {_texto_html(cnpj)} | "
        f"{_texto_html(ordem['empresa_endereco'])} - {_texto_html(ordem['empresa_municipio'])}/{_texto_html(ordem['empresa_uf'])}<br/>"
        f"Tel.: {_texto_html(ordem['empresa_telefone'])} | {_texto_html(ordem['empresa_email'])} | {_texto_html(ordem['empresa_site'])}<br/>"
        f"RELATÓRIO GERENCIAL DE EXECUÇÃO<br/>OS: {_texto_html(ordem['numero'])} | Status: {_texto_html(ordem['status'])}",
        styles["TextoOS"],
    ))
    story.append(Table([cabecalho], colWidths=[3.3*cm, 13*cm] if logo else [16.3*cm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F7FC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9D7E8")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ])))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Síntese da Ordem de Serviço", styles["SecaoOS"]))
    resumo = [["Campo", "Informação"]] + _linhas_pdf(
        [[k, v or ""] for k, v in _linhas_resumo_ordem(ordem)], styles["TextoOS"]
    )
    story.append(Table(resumo, repeatRows=1, splitByRow=1, splitInRow=1, colWidths=[4*cm, 12*cm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3B75")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ])))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Etapas, itens e quantitativos", styles["SecaoOS"]))
    data = [["Etapa", "Status", "%", "Item/serviço", "Un.", "Qtd prev.", "Qtd exec."]]
    for linha in _linhas_etapas_itens(ctx):
        data.append([
            linha["etapa"] or "", linha["status"] or "", linha["percentual"] or "",
            linha["item"] or "", linha["unidade"] or "", linha["prevista"] or "", linha["executada"] or "",
        ])
    story.append(Table(data, repeatRows=1, colWidths=[2.6*cm, 1.9*cm, 0.9*cm, 5.3*cm, 1.2*cm, 1.7*cm, 1.7*cm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3B75")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 6.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Registros informados pelo executor", styles["SecaoOS"]))
    obs_executor = _observacoes_executor(ctx)
    if obs_executor:
        obs_data = [["Etapa", "Materiais/Ferramentas", "Ocorrências/Despesas sem valor", "Observação"]]
        for obs in obs_executor:
            obs_data.append([obs["etapa"], obs["materiais"] or "-", obs["custos"] or "-", obs["observacao"] or "-"])
        story.append(Table(obs_data, repeatRows=1, colWidths=[3.3*cm, 4.2*cm, 4.2*cm, 4.3*cm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B3B75")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
        ])))
    else:
        story.append(Paragraph("Nenhuma observação de campo importada do pacote do executor.", styles["TextoOS"]))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Resumo de evidências", styles["SecaoOS"]))
    qtd_fotos = len(ctx["fotos"])
    qtd_anexos = len(ctx["anexos"])
    story.append(Paragraph(f"Fotos vinculadas: {qtd_fotos}. Anexos preservados: {qtd_anexos}.", styles["TextoOS"]))
    rodape = _rodape_profissional_os(ordem)
    doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
    return arquivo


def gerar_word_relatorio(ordem_id, pasta_destino=None):
    from docx import Document
    from docx.shared import Cm, Pt

    ctx = _ordem_contexto(ordem_id)
    ordem = ctx["ordem"]
    arquivo = pasta_saida_os(ordem, pasta_destino) / "Relatorio_Execucao_Pos_Obra.docx"
    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(1.2)
        section.bottom_margin = Cm(1.2)
        section.left_margin = Cm(1.2)
        section.right_margin = Cm(1.2)
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(9)
    logo = _logo_path_ordem(ordem)
    if logo:
        try:
            doc.add_picture(str(logo), width=Cm(4))
        except Exception:
            pass
    doc.add_heading("Relatório Completo de Execução e Entrega de Serviço", 0)
    doc.add_paragraph(_empresa_nome(ordem))
    doc.add_paragraph(f"CNPJ: {_empresa_cnpj(ordem)}")
    doc.add_paragraph(f"OS: {ordem['numero']} | Status: {ordem['status']}")
    doc.add_heading("Base de controle e rastreabilidade", 1)
    doc.add_paragraph(_texto_base_controle())
    dados = _linhas_resumo_ordem(ordem)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Campo"
    table.rows[0].cells[1].text = "Informacao"
    for k, v in dados:
        cells = table.add_row().cells
        cells[0].text = str(k)
        cells[1].text = str(v or "")

    doc.add_heading("Etapas e itens", 1)
    t = doc.add_table(rows=1, cols=7)
    t.style = "Table Grid"
    for idx, head in enumerate(["Etapa", "Status", "%", "Item", "Un.", "Qtd prevista", "Qtd executada"]):
        t.rows[0].cells[idx].text = head
    for linha in _linhas_etapas_itens(ctx):
        cells = t.add_row().cells
        cells[0].text = str(linha["etapa"] or "")
        cells[1].text = str(linha["status"] or "")
        cells[2].text = str(linha["percentual"] or "")
        cells[3].text = str(linha["item"] or "")
        cells[4].text = str(linha["unidade"] or "")
        cells[5].text = str(linha["prevista"] or "")
        cells[6].text = str(linha["executada"] or "")

    doc.add_heading("Registros informados pelo executor", 1)
    obs_executor = _observacoes_executor(ctx)
    if obs_executor:
        tobs = doc.add_table(rows=1, cols=4)
        tobs.style = "Table Grid"
        for idx, head in enumerate(["Etapa", "Materiais/Ferramentas", "Ocorrências/Despesas sem valor", "Observação"]):
            tobs.rows[0].cells[idx].text = head
        for obs in obs_executor:
            cells = tobs.add_row().cells
            cells[0].text = str(obs["etapa"] or "")
            cells[1].text = str(obs["materiais"] or "-")
            cells[2].text = str(obs["custos"] or "-")
            cells[3].text = str(obs["observacao"] or "-")
    else:
        doc.add_paragraph("Nenhuma observação de campo importada do pacote do executor.")

    doc.add_heading("Anexos e orcamentos de terceiros preservados", 1)
    ta = doc.add_table(rows=1, cols=5)
    ta.style = "Table Grid"
    for idx, head in enumerate(["Tipo", "Etapa", "Arquivo", "Importa", "Observacao"]):
        ta.rows[0].cells[idx].text = head
    if ctx["anexos"]:
        for anexo in ctx["anexos"]:
            cells = ta.add_row().cells
            cells[0].text = str(anexo["tipo"] or "")
            cells[1].text = str(anexo["etapa_nome"] or "")
            cells[2].text = str(anexo["nome_arquivo"] or "")
            cells[3].text = "Sim" if int(anexo["importar_orcamento"] or 0) else "Nao"
            cells[4].text = str(anexo["observacao"] or "")
    else:
        cells = ta.add_row().cells
        cells[0].text = "Sem anexos registrados"

    doc.add_page_break()
    doc.add_heading("Registro fotografico", 1)
    tem_foto = False
    for etapa in ctx["etapas"]:
        fotos_etapa = [f for f in ctx["fotos"] if f["etapa_id"] == etapa["id"]]
        if not fotos_etapa:
            continue
        doc.add_heading(str(etapa["nome"] or "Etapa"), 2)
        for cat in FOTO_CATEGORIAS:
            fotos_cat = [f for f in fotos_etapa if f["categoria"] == cat]
            if not fotos_cat:
                continue
            tem_foto = True
            doc.add_heading(cat, 3)
            for foto in fotos_cat:
                caminho = Path(foto["caminho"] or "")
                if caminho.exists():
                    try:
                        doc.add_picture(str(caminho), width=Cm(9))
                    except Exception:
                        pass
                doc.add_paragraph(_foto_legenda(foto))
    if not tem_foto:
        doc.add_paragraph("Nenhuma foto registrada nesta OS.")

    doc.add_heading("Conclusao e ateste de entrega", 1)
    doc.add_paragraph(
        "As partes abaixo declaram ciencia das evidencias apresentadas. A assinatura nao elimina "
        "a necessidade de conferencia tecnica, medicao, saneamento de pendencias e recebimento "
        "formal quando aplicavel ao contrato."
    )
    doc.add_heading("Assinaturas", 1)
    doc.add_paragraph("Executor: ____________________________")
    doc.add_paragraph("Responsavel tecnico: ____________________________")
    doc.add_paragraph("Fiscal/Cliente: ____________________________")
    doc.add_paragraph("Gestor: ____________________________")
    doc.save(arquivo)
    return arquivo


def gerar_excel_medicao(ordem_id, pasta_destino=None):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    ctx = _ordem_contexto(ordem_id)
    ordem = ctx["ordem"]
    arquivo = pasta_saida_os(ordem, pasta_destino) / "Planilha_Medicao_OS.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Medicao OS"
    ws.append([f"OS {ordem['numero']} - {ordem['objeto'] or ''}"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)
    ws["A1"].font = Font(bold=True, color="FFFFFF", size=14)
    ws["A1"].fill = PatternFill("solid", fgColor="0B3B75")
    ws["A1"].alignment = Alignment(horizontal="center")
    ws.append([])
    ws.append(["Base de controle", _texto_base_controle()])
    ws.merge_cells(start_row=3, start_column=2, end_row=3, end_column=8)
    ws.append([])
    ws.append(["Etapa", "Status", "% exec.", "Item", "Un.", "Qtd prevista", "Qtd executada", "Observacao"])
    for cell in ws[5]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1456A0")
    for linha in _linhas_etapas_itens(ctx):
        ws.append([
            linha["etapa"], linha["status"], linha["percentual"], linha["item"], linha["unidade"],
            linha["prevista"], linha["executada"], linha["observacao"],
        ])
    ws_anexos = wb.create_sheet("Anexos")
    ws_anexos.append(["Tipo", "Etapa", "Arquivo", "Importa para orcamento", "Usuario", "Observacao", "Caminho preservado"])
    for cell in ws_anexos[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1456A0")
    for anexo in ctx["anexos"]:
        ws_anexos.append([
            anexo["tipo"], anexo["etapa_nome"], anexo["nome_arquivo"],
            "Sim" if int(anexo["importar_orcamento"] or 0) else "Nao",
            anexo["usuario"], anexo["observacao"], anexo["caminho"],
        ])
    ws_fotos = wb.create_sheet("Fotos")
    ws_fotos.append(["Etapa", "Categoria", "Legenda", "Usuario", "Data", "Latitude", "Longitude", "Caminho preservado"])
    for cell in ws_fotos[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1456A0")
    for foto in ctx["fotos"]:
        ws_fotos.append([
            foto["etapa_nome"], foto["categoria"], foto["legenda"], foto["usuario"],
            foto["data_registro"], foto["latitude"], foto["longitude"], foto["caminho"],
        ])
    ws_obs = wb.create_sheet("Registros Executor")
    ws_obs.append(["Etapa", "Materiais/Ferramentas", "Ocorrencias/Despesas sem valor", "Observacao"])
    for cell in ws_obs[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1456A0")
    for obs in _observacoes_executor(ctx):
        ws_obs.append([obs["etapa"], obs["materiais"], obs["custos"], obs["observacao"]])
    for col in ws.columns:
        letter = get_column_letter(col[0].column)
        ws.column_dimensions[letter].width = min(45, max(12, max(len(str(c.value or "")) for c in col) + 2))
    for folha in [ws_anexos, ws_fotos, ws_obs]:
        for col in folha.columns:
            letter = get_column_letter(col[0].column)
            folha.column_dimensions[letter].width = min(55, max(12, max(len(str(c.value or "")) for c in col) + 2))
    wb.save(arquivo)
    return arquivo


def gerar_pacote_os(ordem_id, pasta_destino=None):
    return [
        gerar_pdf_gerencial(ordem_id, pasta_destino),
        gerar_pdf_relatorio(ordem_id, pasta_destino),
        gerar_word_relatorio(ordem_id, pasta_destino),
        gerar_excel_medicao(ordem_id, pasta_destino),
    ]


def gerar_html_executor(ordem_id):
    ctx = _ordem_contexto(ordem_id)
    ordem = ctx["ordem"]
    pasta = database.DATA_DIR
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{_safe_filename(ordem['numero'] or 'OS')}_link_executor.html"
    if arquivo.exists():
        return arquivo

    etapas = list(ctx["etapas"]) or [{"id": "geral", "nome": "Registro fotográfico", "descricao": ""}]
    itens_por_etapa = {}
    for item in ctx["itens"]:
        chave = item["etapa_id"] if item["etapa_id"] is not None else "geral"
        itens_por_etapa.setdefault(chave, []).append(item)

    botoes_fotos = [
        ("Antes", "Início da obra"),
        ("Durante", "Durante a execução"),
        ("Depois", "Final / entrega"),
    ]
    etapas_html = []
    for etapa in etapas:
        etapa_id = etapa["id"] if hasattr(etapa, "keys") and "id" in etapa.keys() else "geral"
        etapa_nome = etapa["nome"] or "Sem etapa"
        itens = itens_por_etapa.get(etapa_id, [])
        if not itens and etapa_id != "geral":
            itens = itens_por_etapa.get("geral", [])
        linhas_itens = "".join(
            "<tr>"
            f"<td>{html.escape(str(item['codigo'] or ''))}</td>"
            f"<td>{html.escape(str(item['descricao'] or ''))}</td>"
            f"<td>{html.escape(str(item['unidade'] or ''))}</td>"
            f"<td>{html.escape(str(item['quantidade_prevista'] or ''))}</td>"
            f"<td>{html.escape(str(item['fonte'] or ''))}</td>"
            "</tr>"
            for item in itens
        ) or "<tr><td colspan='5'>Sem materiais ou itens cadastrados para esta etapa.</td></tr>"
        controles = []
        for categoria, rotulo in botoes_fotos:
            base = f"etapa_{_safe_filename(str(etapa_id))}_{_safe_filename(categoria)}"
            controles.append(f"""
            <div class="foto-card">
              <strong>{html.escape(rotulo)}</strong>
              <span class="contador" id="contador_{base}">0 foto(s)</span>
              <div class="foto-actions">
                <button type="button" onclick="abrirInput('{base}_camera')">Tirar fotos</button>
                <button type="button" onclick="abrirInput('{base}_galeria')">Galeria do celular</button>
              </div>
              <input id="{base}_camera" hidden type="file" accept="image/*" capture="environment" multiple onchange="registrarFotos(event, '{html.escape(str(etapa_id))}', '{html.escape(str(etapa_nome))}', '{html.escape(categoria)}', 'contador_{base}')">
              <input id="{base}_galeria" hidden type="file" accept="image/*" multiple onchange="registrarFotos(event, '{html.escape(str(etapa_id))}', '{html.escape(str(etapa_nome))}', '{html.escape(categoria)}', 'contador_{base}')">
            </div>
            """)
        etapas_html.append(f"""
        <section class="etapa" data-etapa="{html.escape(str(etapa_id))}">
          <h2>{html.escape(str(etapa_nome))}</h2>
          <p>{html.escape(str(etapa['descricao'] or ''))}</p>
          <h3>Materiais, serviços e itens previstos</h3>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Código</th><th>Descrição</th><th>Un.</th><th>Qtd.</th><th>Origem</th></tr></thead>
              <tbody>{linhas_itens}</tbody>
            </table>
          </div>
          <h3>Fotos da etapa</h3>
          <div class="foto-grid">{''.join(controles)}</div>
          <label>Materiais e ferramentas usados</label>
          <textarea data-campo="materiais" data-etapa="{html.escape(str(etapa_id))}" placeholder="Ex.: cabos, conectores, escada, EPIs, máquina, veículo..."></textarea>
          <label>Ocorrências ou despesas adicionais sem valor</label>
          <textarea data-campo="custos" data-etapa="{html.escape(str(etapa_id))}" placeholder="Ex.: deslocamento extra, compra emergencial, apoio adicional, sem informar preço..."></textarea>
          <label>Observação da execução</label>
          <textarea data-campo="observacao" data-etapa="{html.escape(str(etapa_id))}" placeholder="Descreva algo importante para comprovar a execução."></textarea>
        </section>
        """)

    html_saida = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OS PPP - {ordem['numero']}</title>
  <style>
    * {{ box-sizing:border-box; }}
    body {{ font-family: Arial, Segoe UI, sans-serif; margin:0; background:#f2f6fb; color:#142033; font-size:16px; }}
    header {{ background:#071A33; color:white; padding:18px; position:sticky; top:0; z-index:5; }}
    header h1 {{ font-size:22px; margin:0 0 4px; }}
    header p {{ margin:0; opacity:.9; }}
    main {{ padding:12px; max-width:980px; margin:auto; padding-bottom:132px; }}
    section,.meta,.finalizar {{ background:white; border:1px solid #d7e2ef; border-radius:8px; padding:14px; margin:12px 0; }}
    h2 {{ margin:0 0 8px; font-size:21px; color:#071A33; }}
    h3 {{ margin:16px 0 8px; font-size:17px; color:#0B3B75; }}
    .meta {{ display:grid; grid-template-columns:110px 1fr; gap:8px; }}
    .table-wrap {{ overflow:auto; border:1px solid #e3ebf5; border-radius:6px; }}
    table {{ width:100%; border-collapse:collapse; min-width:680px; }}
    th,td {{ border-bottom:1px solid #e3ebf5; padding:8px; text-align:left; vertical-align:top; }}
    th {{ background:#eaf2ff; color:#0B3B75; }}
    .foto-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }}
    .foto-card {{ border:1px solid #d7e2ef; border-radius:8px; padding:12px; background:#f8fbff; }}
    .foto-card strong {{ display:block; margin-bottom:6px; }}
    .contador {{ color:#0B3B75; font-weight:700; font-size:14px; }}
    .foto-actions {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:10px; }}
    button {{ border:0; border-radius:7px; padding:12px 10px; font-weight:800; font-size:15px; background:#0B3B75; color:white; }}
    button.sec {{ background:#2563EB; }}
    button.ok {{ background:#16A34A; }}
    label {{ display:block; margin:12px 0 6px; font-weight:800; color:#071A33; }}
    textarea {{ width:100%; min-height:76px; border:1px solid #cdd9e8; border-radius:7px; padding:10px; font:inherit; resize:vertical; }}
    .finalizar {{ position:fixed; left:0; right:0; bottom:0; margin:0; border-radius:0; box-shadow:0 -8px 24px rgba(15,23,42,.14); }}
    .finalizar-inner {{ max-width:980px; margin:auto; display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    .aviso {{ color:#52627a; font-size:14px; margin:8px auto 0; max-width:980px; }}
    @media (max-width:680px) {{
      main {{ padding:10px; padding-bottom:158px; }}
      .meta {{ grid-template-columns:1fr; }}
      .finalizar-inner {{ grid-template-columns:1fr; }}
      .foto-actions {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <header><h1>Coleta de fotos - {html.escape(str(ordem['numero'] or 'OS'))}</h1><p>Use os botões abaixo para tirar fotos ou escolher da galeria.</p></header>
  <main>
    <div class="meta">
      <strong>Cliente</strong><span>{html.escape(str(ordem['cliente_nome'] or ''))}</span>
      <strong>Objeto</strong><span>{html.escape(str(ordem['objeto'] or ''))}</span>
      <strong>Local</strong><span>{html.escape(str(ordem['local_execucao'] or ordem['municipio'] or ''))}</span>
      <strong>Executor</strong><span>{html.escape(str(ordem['executor'] or ''))}</span>
    </div>
    {''.join(etapas_html)}
  </main>
  <div class="finalizar">
    <div class="finalizar-inner">
      <button class="ok" type="button" onclick="encaminhar()">Encaminhar fotos da OS</button>
      <button class="sec" type="button" onclick="baixarResumo()">Baixar resumo</button>
    </div>
    <div class="aviso">O botão Encaminhar gera um único ZIP da OS para enviar por WhatsApp, e-mail ou Drive. Esse ZIP deve ser importado no OS PPP.</div>
  </div>
  <script>
    const numeroOS = {json.dumps(str(ordem["numero"] or "OS"), ensure_ascii=False)};
    const selecionadas = [];
    function limparNome(txt) {{
      return String(txt || 'registro').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/[^a-zA-Z0-9_-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60) || 'registro';
    }}
    function abrirInput(id) {{
      const input = document.getElementById(id);
      if (input) input.click();
    }}
    function registrarFotos(event, etapaId, etapaNome, categoria, contadorId) {{
      const files = Array.from(event.target.files || []);
      files.forEach((file) => selecionadas.push({{ file, etapaId, etapaNome, categoria }}));
      const total = selecionadas.filter(f => f.etapaId === etapaId && f.categoria === categoria).length;
      const contador = document.getElementById(contadorId);
      if (contador) contador.textContent = total + ' foto(s)';
      event.target.value = '';
    }}
    function coletarObservacoes() {{
      const dados = [];
      document.querySelectorAll('section.etapa').forEach(sec => {{
        const etapa = sec.dataset.etapa;
        const titulo = sec.querySelector('h2')?.textContent || etapa;
        const obj = {{ etapa, titulo, materiais:'', custos:'', observacao:'' }};
        sec.querySelectorAll('textarea').forEach(t => obj[t.dataset.campo] = t.value || '');
        dados.push(obj);
      }});
      return dados;
    }}
    function resumoTexto() {{
      const linhas = ['OS: ' + numeroOS, 'Gerado em: ' + new Date().toLocaleString('pt-BR'), '', 'FOTOS SELECIONADAS'];
      if (!selecionadas.length) linhas.push('Nenhuma foto selecionada.');
      selecionadas.forEach((f, idx) => linhas.push((idx+1) + '. ' + f.categoria + ' | ' + f.etapaNome + ' | ' + f.file.name));
      linhas.push('', 'OBSERVACOES POR ETAPA');
      coletarObservacoes().forEach(o => {{
        linhas.push('', 'Etapa: ' + o.titulo);
        linhas.push('Materiais/ferramentas: ' + (o.materiais || '-'));
        linhas.push('Ocorrencias/despesas sem valor: ' + (o.custos || '-'));
        linhas.push('Observacao: ' + (o.observacao || '-'));
      }});
      return linhas.join('\\n');
    }}
    function arquivosRenomeados() {{
      const arquivos = selecionadas.map((f, idx) => {{
        const ext = (f.file.name.split('.').pop() || 'jpg').toLowerCase();
        const nome = [numeroOS, limparNome(f.etapaNome), limparNome(f.categoria), String(idx+1).padStart(3,'0')].join('_') + '.' + ext;
        const caminho = numeroOS + '/' + limparNome(f.etapaNome) + '/' + limparNome(f.categoria) + '/' + nome;
        return {{ file: new File([f.file], nome, {{ type: f.file.type || 'image/jpeg' }}), path: caminho }};
      }});
      arquivos.push({{ file: new File([resumoTexto()], numeroOS + '_resumo_execucao.txt', {{ type:'text/plain' }}), path: numeroOS + '/' + numeroOS + '_resumo_execucao.txt' }});
      return arquivos;
    }}
    function crc32(buf) {{
      let table = crc32.table;
      if (!table) {{
        table = crc32.table = Array.from({{length:256}}, (_, n) => {{
          let c = n;
          for (let k=0; k<8; k++) c = ((c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1));
          return c >>> 0;
        }});
      }}
      let crc = -1;
      const arr = new Uint8Array(buf);
      for (let i=0; i<arr.length; i++) crc = (crc >>> 8) ^ table[(crc ^ arr[i]) & 0xFF];
      return (crc ^ -1) >>> 0;
    }}
    function u16(v) {{ return [v & 255, (v >>> 8) & 255]; }}
    function u32(v) {{ return [v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255]; }}
    async function gerarZip() {{
      const enc = new TextEncoder();
      const entradas = [];
      const centrais = [];
      let offset = 0;
      for (const item of arquivosRenomeados()) {{
        const data = await item.file.arrayBuffer();
        const nameBytes = enc.encode(item.path);
        const crc = crc32(data);
        const local = new Uint8Array([
          ...u32(0x04034b50), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0),
          ...u32(crc), ...u32(data.byteLength), ...u32(data.byteLength), ...u16(nameBytes.length), ...u16(0),
          ...nameBytes
        ]);
        entradas.push(local, new Uint8Array(data));
        const central = new Uint8Array([
          ...u32(0x02014b50), ...u16(20), ...u16(20), ...u16(0), ...u16(0), ...u16(0), ...u16(0),
          ...u32(crc), ...u32(data.byteLength), ...u32(data.byteLength), ...u16(nameBytes.length), ...u16(0), ...u16(0),
          ...u16(0), ...u16(0), ...u32(0), ...u32(offset), ...nameBytes
        ]);
        centrais.push(central);
        offset += local.byteLength + data.byteLength;
      }}
      const centralSize = centrais.reduce((s, a) => s + a.byteLength, 0);
      const fim = new Uint8Array([
        ...u32(0x06054b50), ...u16(0), ...u16(0), ...u16(centrais.length), ...u16(centrais.length),
        ...u32(centralSize), ...u32(offset), ...u16(0)
      ]);
      return new File([...entradas, ...centrais, fim], numeroOS + '_pacote_executor.zip', {{ type:'application/zip' }});
    }}
    async function encaminhar() {{
      if (!selecionadas.length) {{
        alert('Selecione ou tire pelo menos uma foto antes de encaminhar.');
        return;
      }}
      const zip = await gerarZip();
      const files = [zip];
      if (navigator.canShare && navigator.canShare({{ files }}) && navigator.share) {{
        try {{
          await navigator.share({{ title: numeroOS + ' - pacote executor', text: 'Pacote ZIP de fotos e resumo da ' + numeroOS, files }});
          alert('Pacote ZIP encaminhado. Importe esse arquivo no OS PPP.');
          return;
        }} catch (err) {{
          if (err && err.name === 'AbortError') return;
        }}
      }}
      baixarArquivo(zip);
      alert('O navegador não permitiu compartilhar direto. O ZIP foi baixado; envie esse arquivo pelo WhatsApp, e-mail ou Drive.');
    }}
    function baixarArquivo(file) {{
      const a = document.createElement('a');
      a.href = URL.createObjectURL(file);
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }}
    function baixarResumo() {{
      const blob = new Blob([resumoTexto()], {{ type:'text/plain;charset=utf-8' }});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = numeroOS + '_resumo_execucao.txt';
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    }}
  </script>
</body>
</html>"""
    arquivo.write_text(html_saida, encoding="utf-8")
    return arquivo

