Orcamentos PPP Enterprise - ajuste de criterio financeiro dos documentos

Problema corrigido:
- A proposta tecnica usava texto generico no quadro "Referencia financeira do orcamento", como "Implantacao das estruturas".
- Esse tipo de texto foi substituido por criterio tecnico gerado automaticamente.

Nova logica:
- CAPEX: descreve investimento vinculado ao contrato/aditivo, fornecimento, implantacao, servicos tecnicos, materiais, equipamentos, instalacao, configuracao, testes e comissionamento.
- O criterio cita as principais etapas CAPEX cadastradas e as fontes de formacao do valor.
- Parcelamento CAPEX: informa condicao vinculada a cronograma fisico-financeiro, medicao, aceite/atesto e regras contratuais/administrativas.
- OPEX: trata valor recorrente mensal separadamente do CAPEX, com medicao e faturamento recorrente.

Tambem corrigido:
- Sanitizacao para evitar saida "Contrato no Contrato de Concessao...".
- Remocao da frase fixa "Implantacao das estruturas" nos geradores.

Formatos validados:
- PDF da proposta tecnica.
- Word da proposta tecnica.
- Excel da proposta tecnica.

Referencia de entrega:
- Aplicativo administrativo: Orcamentos PPP.
- Aplicativo operacional: OS PPP.
- Pasta local padrao: C:\Orcamentos_PPP.
- Guia de instalacao e atualizacao: README_INSTALACAO_CLIENTE.txt.

Regra para cliente:
- Ajuste somente de texto/layout pode ser entregue trocando apenas o EXE correspondente.
- Mudanca de relatorio, tela, funcao, dependencia ou estrutura de banco exige atualizar a pasta completa preservando o app.db real do cliente.
