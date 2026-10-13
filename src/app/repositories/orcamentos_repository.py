from core.database import conn


class OrcamentosRepository:
    def listar_orcamentos(self):
        with conn() as c:
            return c.execute(
                """
                SELECT
                    o.id,
                    o.codigo,
                    o.objeto,
                    o.status,
                    o.municipio,
                    o.validade,
                    o.data_criacao,
                    c.nome AS cliente,
                    ct.nome AS contrato,
                    s.nome AS segmento,
                    a.numero_aditivo AS aditivo,
                    COALESCE((
                        SELECT SUM(i.quantidade * i.custo_unit * (1+i.bdi/100.0) * (1+i.margem/100.0))
                        FROM itens i
                        WHERE i.orcamento_id=o.id AND i.capex_opex='CAPEX'
                    ),0) AS total_capex,
                    COALESCE((
                        SELECT SUM(op.qtd_mensal * op.custo_unit * (1+op.bdi/100.0) * (1+op.margem/100.0))
                        FROM opex op
                        WHERE op.orcamento_id=o.id
                    ),0) AS total_opex
                FROM orcamentos o
                LEFT JOIN clientes c ON c.id=o.cliente_id
                LEFT JOIN contratos ct ON ct.id=o.contrato_id
                LEFT JOIN segmentos s ON s.id=o.segmento_id
                LEFT JOIN aditivos a ON a.id=o.aditivo_id
                ORDER BY o.id DESC
                """
            ).fetchall()

    def buscar_orcamento(self, orcamento_id):
        with conn() as c:
            return c.execute("SELECT * FROM orcamentos WHERE id=?", (orcamento_id,)).fetchone()

    def listar_etapas(self, orcamento_id):
        with conn() as c:
            return c.execute(
                """
                SELECT e.*,
                       COALESCE(SUM(i.quantidade*i.custo_unit*(1+i.bdi/100.0)*(1+i.margem/100.0)),0) AS total
                FROM etapas_orcamento e
                LEFT JOIN itens i ON i.etapa_id=e.id AND i.capex_opex='CAPEX'
                WHERE e.orcamento_id=?
                GROUP BY e.id
                ORDER BY e.ordem, e.id
                """,
                (orcamento_id,),
            ).fetchall()

    def listar_itens_capex(self, orcamento_id):
        with conn() as c:
            return c.execute(
                """
                SELECT * FROM itens
                WHERE orcamento_id=?AND capex_opex='CAPEX'
                ORDER BY etapa, id
                """,
                (orcamento_id,),
            ).fetchall()

    def listar_opex(self, orcamento_id):
        with conn() as c:
            return c.execute(
                """
                SELECT * FROM opex
                WHERE orcamento_id=?
                ORDER BY id
                """,
                (orcamento_id,),
            ).fetchall()

    def totais_orcamento(self, orcamento_id):
        with conn() as c:
            return c.execute(
                """
                SELECT
                    COALESCE((
                        SELECT SUM(i.quantidade*i.custo_unit*(1+i.bdi/100.0)*(1+i.margem/100.0))
                        FROM itens i
                        WHERE i.orcamento_id=?AND i.capex_opex='CAPEX'
                    ),0) AS total_capex,
                    COALESCE((
                        SELECT SUM(op.qtd_mensal*op.custo_unit*(1+op.bdi/100.0)*(1+op.margem/100.0))
                        FROM opex op
                        WHERE op.orcamento_id=?
                    ),0) AS total_opex
                """,
                (orcamento_id, orcamento_id),
            ).fetchone()

    def salvar_cronograma_parcela(self, orcamento_id, etapa_id, parcela, percentual, valor):
        with conn() as c:
            c.execute(
                """
                INSERT INTO cronograma_parcelas(orcamento_id, etapa_id, parcela, percentual, valor)
                VALUES(?,?,?,?,?)
                ON CONFLICT(orcamento_id, etapa_id, parcela)
                DO UPDATE SET percentual=excluded.percentual, valor=excluded.valor
                """,
                (orcamento_id, etapa_id, parcela, percentual, valor),
            )
            c.commit()

    def listar_cronograma(self, orcamento_id):
        with conn() as c:
            return c.execute(
                """
                SELECT cp.*, e.nome AS etapa
                FROM cronograma_parcelas cp
                LEFT JOIN etapas_orcamento e ON e.id=cp.etapa_id
                WHERE cp.orcamento_id=?
                ORDER BY e.ordem, cp.parcela
                """,
                (orcamento_id,),
            ).fetchall()
