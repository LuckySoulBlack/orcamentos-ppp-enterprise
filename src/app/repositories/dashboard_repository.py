from core.database import conn


class DashboardRepository:
    def indicadores_gerais(self):
        with conn() as c:
            return c.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM contratos) AS total_contratos,
                    (SELECT COUNT(*) FROM aditivos) AS total_aditivos,
                    (SELECT COUNT(*) FROM orcamentos) AS total_orcamentos,
                    COALESCE((
                        SELECT SUM(quantidade*custo_unit*(1+bdi/100.0)*(1+margem/100.0))
                        FROM itens
                        WHERE capex_opex='CAPEX'
                    ),0) AS total_capex,
                    COALESCE((
                        SELECT SUM(qtd_mensal*custo_unit*(1+bdi/100.0)*(1+margem/100.0))
                        FROM opex
                    ),0) AS total_opex
                """
            ).fetchone()

    def orcamentos_por_status(self):
        with conn() as c:
            return c.execute(
                """
                SELECT status, COUNT(*) AS total
                FROM orcamentos
                GROUP BY status
                ORDER BY total DESC
                """
            ).fetchall()

    def aditivos_por_segmento(self):
        with conn() as c:
            return c.execute(
                """
                SELECT COALESCE(s.nome, 'Sem segmento') AS segmento, COUNT(a.id) AS total
                FROM aditivos a
                LEFT JOIN segmentos s ON s.id=a.segmento_id
                GROUP BY s.nome
                ORDER BY total DESC
                """
            ).fetchall()

    def pendencias(self):
        with conn() as c:
            return c.execute(
                """
                SELECT 'Orçamentos sem cronograma' AS tipo, COUNT(*) AS total
                FROM orcamentos o
                WHERE NOT EXISTS (SELECT 1 FROM cronograma_parcelas cp WHERE cp.orcamento_id=o.id)
                UNION ALL
                SELECT 'Orçamentos sem anexos' AS tipo, COUNT(*) AS total
                FROM orcamentos o
                WHERE NOT EXISTS (SELECT 1 FROM documentos d WHERE d.orcamento_id=o.id)
                UNION ALL
                SELECT 'Aditivos sem orçamento' AS tipo, COUNT(*) AS total
                FROM aditivos a
                WHERE NOT EXISTS (SELECT 1 FROM orcamentos o WHERE o.aditivo_id=a.id)
                """
            ).fetchall()
