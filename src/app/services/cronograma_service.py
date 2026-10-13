from repositories.orcamentos_repository import OrcamentosRepository


class CronogramaService:
    def __init__(self):
        self.repo = OrcamentosRepository()

    @staticmethod
    def validar_percentuais(percentuais):
        soma = sum(float(p or 0) for p in percentuais)
        return abs(soma - 100) < 0.01, soma

    def salvar_distribuicao_etapa(self, orcamento_id, etapa_id, valor_etapa, percentuais):
        ok, soma = self.validar_percentuais(percentuais)
        resultados = []
        for idx, percentual in enumerate(percentuais, start=1):
            percentual = float(percentual or 0)
            valor = float(valor_etapa or 0) * (percentual / 100.0)
            self.repo.salvar_cronograma_parcela(orcamento_id, etapa_id, idx, percentual, valor)
            resultados.append({"parcela": idx, "percentual": percentual, "valor": valor})
        return {"ok": ok, "soma_percentual": soma, "parcelas": resultados}

    def carregar_distribuicao(self, orcamento_id):
        return self.repo.listar_cronograma(orcamento_id)
