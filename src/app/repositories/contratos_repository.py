from core.database import conn


class ContratosRepository:
    def listar_clientes(self):
        with conn() as c:
            return c.execute("""
                SELECT id, nome, uf, municipio, orgao_setor, responsavel
                FROM clientes
                ORDER BY nome
            """).fetchall()

    def obter_cliente(self, cliente_id):
        if not cliente_id:
            return None
        with conn() as c:
            return c.execute("""
                SELECT id, nome, uf, municipio, orgao_setor, responsavel
                FROM clientes
                WHERE id=?
            """, (cliente_id,)).fetchone()

    def listar_segmentos(self):
        with conn() as c:
            return c.execute("SELECT id, nome FROM segmentos ORDER BY id").fetchall()

    def adicionar_segmento(self, nome):
        nome = str(nome or "").strip()
        if not nome:
            raise ValueError("Informe o nome da opção.")
        with conn() as c:
            c.execute("INSERT OR IGNORE INTO segmentos(nome) VALUES(?)", (nome,))
            row = c.execute("SELECT id FROM segmentos WHERE nome=?", (nome,)).fetchone()
            c.commit()
            return row["id"] if row else None

    def listar_contratos(self, termo=""):
        termo = f"%{termo.strip()}%"
        with conn() as c:
            return c.execute(
                """
                SELECT
                    co.id,
                    cl.nome AS cliente,
                    co.nome,
                    co.numero,
                    co.municipio,
                    co.status,
                    co.valor_global,
                    COALESCE(GROUP_CONCAT(s.nome, ', '), co.segmentos, '') AS segmentos,
                    COUNT(DISTINCT a.id) AS total_aditivos
                FROM contratos co
                LEFT JOIN clientes cl ON cl.id=co.cliente_id
                LEFT JOIN contrato_segmentos cs ON cs.contrato_id=co.id
                LEFT JOIN segmentos s ON s.id=cs.segmento_id
                LEFT JOIN aditivos a ON a.contrato_id=co.id
                WHERE co.nome LIKE ?OR co.numero LIKE ?OR co.municipio LIKE ?OR COALESCE(cl.nome,'') LIKE ?
                GROUP BY co.id
                ORDER BY co.id DESC
                """,
                (termo, termo, termo, termo),
            ).fetchall()

    def obter_contrato(self, contrato_id):
        with conn() as c:
            contrato = c.execute("SELECT * FROM contratos WHERE id=?", (contrato_id,)).fetchone()
            segmentos = c.execute(
                "SELECT segmento_id FROM contrato_segmentos WHERE contrato_id=?",
                (contrato_id,),
            ).fetchall()
            return contrato, {r["segmento_id"] for r in segmentos}

    def salvar_contrato(self, dados, segmentos_ids, contrato_id=None):
        seg_text = dados.get("segmentos_texto", "")
        with conn() as c:
            if contrato_id:
                c.execute(
                    """
                    UPDATE contratos
                    SET cliente_id=?, nome=?, numero=?, objeto=?, municipio=?, valor_global=?,
                        inicio=?, fim=?, status=?, indice_reajuste=?, segmentos=?, observacao=?
                    WHERE id=?
                    """,
                    (
                        dados.get("cliente_id"), dados.get("nome"), dados.get("numero"),
                        dados.get("objeto"), dados.get("municipio"), dados.get("valor_global"),
                        dados.get("inicio"), dados.get("fim"), dados.get("status"),
                        dados.get("indice_reajuste"), seg_text, dados.get("observacao"), contrato_id,
                    ),
                )
                c.execute("DELETE FROM contrato_segmentos WHERE contrato_id=?", (contrato_id,))
                novo_id = contrato_id
            else:
                cur = c.execute(
                    """
                    INSERT INTO contratos(
                        cliente_id, nome, numero, objeto, municipio, valor_global,
                        inicio, fim, status, indice_reajuste, segmentos, observacao
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        dados.get("cliente_id"), dados.get("nome"), dados.get("numero"),
                        dados.get("objeto"), dados.get("municipio"), dados.get("valor_global"),
                        dados.get("inicio"), dados.get("fim"), dados.get("status"),
                        dados.get("indice_reajuste"), seg_text, dados.get("observacao"),
                    ),
                )
                novo_id = cur.lastrowid

            for segmento_id in segmentos_ids:
                c.execute(
                    "INSERT OR IGNORE INTO contrato_segmentos(contrato_id, segmento_id) VALUES(?,?)",
                    (novo_id, segmento_id),
                )
            c.commit()
            return novo_id

    def listar_aditivos(self, contrato_id):
        with conn() as c:
            return c.execute(
                """
                SELECT a.*, s.nome AS segmento
                FROM aditivos a
                LEFT JOIN segmentos s ON s.id=a.segmento_id
                WHERE a.contrato_id=?
                ORDER BY a.id DESC
                """,
                (contrato_id,),
            ).fetchall()

    def salvar_aditivo(self, dados, aditivo_id=None):
        with conn() as c:
            if aditivo_id:
                c.execute(
                    """
                    UPDATE aditivos
                    SET contrato_id=?, segmento_id=?, numero_aditivo=?, objeto=?, valor=?, prazo=?, status=?, observacao=?
                    WHERE id=?
                    """,
                    (
                        dados.get("contrato_id"), dados.get("segmento_id"), dados.get("numero_aditivo"),
                        dados.get("objeto"), dados.get("valor"), dados.get("prazo"), dados.get("status"),
                        dados.get("observacao"), aditivo_id,
                    ),
                )
                novo_id = aditivo_id
            else:
                cur = c.execute(
                    """
                    INSERT INTO aditivos(contrato_id, segmento_id, numero_aditivo, objeto, valor, prazo, status, observacao)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        dados.get("contrato_id"), dados.get("segmento_id"), dados.get("numero_aditivo"),
                        dados.get("objeto"), dados.get("valor"), dados.get("prazo"), dados.get("status"),
                        dados.get("observacao"),
                    ),
                )
                novo_id = cur.lastrowid
            c.commit()
            return novo_id

    def excluir_aditivo(self, aditivo_id):
        with conn() as c:
            c.execute("DELETE FROM aditivos WHERE id=?", (aditivo_id,))
            c.commit()

    def consolidado_segmentos(self, contrato_id):
        with conn() as c:
            return c.execute(
                """
                SELECT
                    s.nome AS segmento,
                    COUNT(DISTINCT a.id) AS total_aditivos,
                    COUNT(DISTINCT o.id) AS total_orcamentos,
                    COALESCE(SUM(i.quantidade*i.custo_unit*(1+i.bdi/100.0)*(1+i.margem/100.0)),0) AS total_capex,
                    COALESCE((
                        SELECT SUM(op.qtd_mensal*op.custo_unit*(1+COALESCE(op.bdi,0)/100.0)*(1+COALESCE(op.margem,0)/100.0))
                        FROM opex op
                        JOIN orcamentos oo ON oo.id=op.orcamento_id
                        WHERE oo.contrato_id=?AND oo.segmento_id=s.id
                    ),0) AS total_opex
                FROM segmentos s
                LEFT JOIN aditivos a ON a.segmento_id=s.id AND a.contrato_id=?
                LEFT JOIN orcamentos o ON o.segmento_id=s.id AND o.contrato_id=?
                LEFT JOIN itens i ON i.orcamento_id=o.id AND i.capex_opex='CAPEX'
                WHERE s.id IN (SELECT segmento_id FROM contrato_segmentos WHERE contrato_id=?)
                   OR a.id IS NOT NULL
                   OR o.id IS NOT NULL
                GROUP BY s.id, s.nome
                ORDER BY s.nome
                """,
                (contrato_id, contrato_id, contrato_id, contrato_id),
            ).fetchall()
