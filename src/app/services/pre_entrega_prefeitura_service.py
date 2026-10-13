from pathlib import Path
from datetime import datetime

try:
    from core.database import get_pasta_local_relatorios
except Exception:
    def get_pasta_local_relatorios():
        return Path("app/generated")

def texto_ppp(valor: str) -> str:
    s = str(valor or "")
    for a, b in {
        "padrão licitação": "PPP",
        "Padrão licitação": "PPP",
        "licitação": "PPP",
        "Licitação": "PPP",
        "documento licitatório": "documento PPP",
        "processo licitatório": "processo PPP",
    }.items():
        s = s.replace(a, b)
    return s

def validar_pre_entrega(dados: dict) -> list[str]:
    alertas = []
    if not dados.get("cronograma_ok"):
        alertas.append("Revisar cronograma físico-financeiro: total por parcela e acumulado inferior.")
    if not dados.get("memorial_ok"):
        alertas.append("Revisar memorial descritivo PPP: escopo, execução, materiais, mão de obra e aceite.")
    if not dados.get("proposta_ok"):
        alertas.append("Revisar proposta técnica PPP: objeto, justificativa, CAPEX/OPEX, prazo e validade.")
    if not dados.get("dashboard_ok"):
        alertas.append("Usar dashboard cliente apenas como apoio executivo, não como documento técnico obrigatório.")
    return alertas

def gerar_checklist_pre_entrega(nome_arquivo="Checklist_Pre_Entrega_Prefeitura.html"):
    pasta = get_pasta_local_relatorios() / "00_Checklist_Pre_Entrega"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / nome_arquivo
    html = f'''<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8">
<title>Checklist Pré-Entrega Prefeitura — PPP</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;background:#f3f7fb;color:#071a33;margin:0}}
.hero{{background:#0b3b75;color:#fff;padding:32px 42px}}
.wrap{{padding:26px 42px}}
.card{{background:#fff;border:1px solid #dbe4ef;border-radius:18px;padding:18px;margin-bottom:14px}}
h1{{margin:0 0 8px;font-size:30px}} h2{{margin:0 0 10px;color:#0b3b75}}
li{{margin:8px 0;line-height:1.45}}
</style></head><body>
<section class="hero"><h1>Checklist Pré-Entrega Prefeitura — PPP</h1><p>Use este checklist antes de enviar orçamento gerado pelo sistema.</p></section>
<main class="wrap">
<div class="card"><h2>1. Cronograma físico-financeiro</h2><ul><li>Conferir total por parcela.</li><li>Conferir acumulado inferior.</li><li>Conferir se o PDF/Excel não cortou laterais.</li></ul></div>
<div class="card"><h2>2. Memorial descritivo PPP</h2><ul><li>Conferir objeto, local, município e UF.</li><li>Conferir escopo técnico, materiais, mão de obra, instalação, testes e aceite.</li></ul></div>
<div class="card"><h2>3. Proposta técnica PPP</h2><ul><li>Conferir validade, responsável, cliente e contrato/aditivo.</li><li>Conferir CAPEX/OPEX e totais.</li></ul></div>
<div class="card"><h2>4. Dashboard executivo cliente</h2><ul><li>Usar como apoio visual/executivo.</li><li>Não substituir cronograma, planilha, memorial e proposta.</li><li>Não exibir margem interna na versão cliente.</li></ul></div>
<p>Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}.</p>
</main></body></html>'''
    arquivo.write_text(html, encoding="utf-8")
    return arquivo
