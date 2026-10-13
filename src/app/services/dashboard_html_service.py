from pathlib import Path
from html import escape
from datetime import datetime
import base64
import mimetypes
from collections import defaultdict

from core.database import conn, get_pasta_local_relatorios


def moeda(valor):
    try:
        valor = float(valor or 0)
    except Exception:
        valor = 0
    return f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def numero(valor):
    try:
        return float(valor or 0)
    except Exception:
        return 0.0


def texto(valor):
    return escape(str(valor or ''))


def campo(row, *nomes, padrao=None):
    try:
        keys = row.keys()
    except Exception:
        keys = []
    for nome in nomes:
        try:
            if nome in keys and row[nome] is not None:
                return row[nome]
        except Exception:
            pass
    return padrao


def safe_codigo(codigo):
    codigo = str(codigo or 'ORCAMENTO').strip() or 'ORCAMENTO'
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        codigo = codigo.replace(ch, '-')
    return codigo


def pasta_orcamento(codigo):
    base = get_pasta_local_relatorios()
    pasta = base / safe_codigo(codigo)
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def _buscar_dados(orcamento_id):
    with conn() as c:
        orc = c.execute('''
            SELECT o.*, cli.nome AS cliente_nome, cli.municipio AS cliente_municipio, cli.uf AS cliente_uf,
                   cli.responsavel AS cliente_responsavel, cli.cargo AS cliente_cargo,
                   con.nome AS contrato_nome, con.numero AS contrato_numero,
                   seg.nome AS segmento_nome, emp.logo_path AS empresa_logo_path, emp.razao AS empresa_razao,
                   emp.responsavel_tecnico AS empresa_responsavel_tecnico, emp.registro_tecnico AS empresa_registro_tecnico, emp.responsavel_tecnico_cargo AS empresa_responsavel_tecnico_cargo, emp.responsavel_tecnico_especialidade AS empresa_responsavel_tecnico_especialidade, emp.gestor_contrato_nome AS empresa_gestor_contrato_nome, emp.gestor_contrato_cargo AS empresa_gestor_contrato_cargo
            FROM orcamentos o
            LEFT JOIN clientes cli ON cli.id=o.cliente_id
            LEFT JOIN contratos con ON con.id=o.contrato_id
            LEFT JOIN segmentos seg ON seg.id=o.segmento_id
            LEFT JOIN empresa emp ON emp.id=1
            WHERE o.id=?
        ''', (orcamento_id,)).fetchone()
        itens = c.execute('SELECT * FROM itens WHERE orcamento_id=?ORDER BY etapa, id', (orcamento_id,)).fetchall()
        opex = c.execute('SELECT * FROM opex WHERE orcamento_id=?ORDER BY categoria, id', (orcamento_id,)).fetchall()
        anexos = []
        try:
            anexos = c.execute('SELECT * FROM documentos WHERE orcamento_id=?ORDER BY id DESC', (orcamento_id,)).fetchall()
        except Exception:
            pass
        cron = []
        try:
            cron = c.execute('SELECT * FROM cronograma_parcelas WHERE orcamento_id=?ORDER BY parcela', (orcamento_id,)).fetchall()
        except Exception:
            pass
    return orc, itens, opex, cron, anexos


def _total_item(item):
    qtd = numero(campo(item, 'quantidade', 'qtd', padrao=1))
    custo = numero(campo(item, 'custo_unit', 'custo_unitario', 'valor_unitario', padrao=0))
    return qtd * custo * (1 + numero(campo(item, 'bdi', padrao=0)) / 100) * (1 + numero(campo(item, 'margem', padrao=0)) / 100)


def _total_opex(item):
    qtd = numero(campo(item, 'qtd_mensal', 'quantidade', 'qtd', padrao=1))
    custo = numero(campo(item, 'custo_unit', 'custo_unitario', 'valor_unitario', padrao=0))
    return qtd * custo * (1 + numero(campo(item, 'bdi', padrao=0)) / 100) * (1 + numero(campo(item, 'margem', padrao=0)) / 100)


def _parcelas_ativas(cron):
    return sorted({
        int(numero(campo(r, 'parcela', padrao=0)) or 0)
        for r in (cron or [])
        if int(numero(campo(r, 'parcela', padrao=0)) or 0) > 0
        and (numero(campo(r, 'percentual', padrao=0)) > 0 or numero(campo(r, 'valor', padrao=0)) > 0)
    })


def _logo_base64(path):
    if not path:
        return ''
    try:
        p = Path(str(path).strip().strip('"'))
        if not p.exists() or not p.is_file():
            return ''
        mime = mimetypes.guess_type(str(p))[0] or 'image/png'
        data = base64.b64encode(p.read_bytes()).decode('ascii')
        return f'<img class="logo" src="data:{mime};base64,{data}" alt="Logo">'
    except Exception:
        return ''


def _contrato_ref(orc):
    import re
    numero = str(campo(orc, 'contrato_numero', padrao='') or '').strip()
    nome = str(campo(orc, 'contrato_nome', padrao='') or '').strip()
    partes = []
    if numero:
        numero_limpo = re.sub(r'^(contrato\s*)?(n[º°o]?\.?\s*)+', '', numero, flags=re.I).strip(' -–—')
        partes.append(f'Contrato nº {numero_limpo}' if numero_limpo else numero)
        if numero_limpo and nome:
            nome = re.sub(rf'^(contrato\s*)?(n[º°o]?\.?\s*)?{re.escape(numero_limpo)}\s*[-–—]?\s*', '', nome, flags=re.I).strip()
    if nome:
        partes.append(nome)
    return ' - '.join(partes) or 'Contrato/aditivo não informado'


def _status_versao(status):
    s = str(status or '').strip().upper()
    if s == 'APROVADO':
        return 'Aprovado'
    if s == 'ENVIADO':
        return 'Enviado'
    if 'REVIS' in s:
        return 'Em revisão'
    if 'ELAB' in s or 'RASC' in s:
        return 'Em elaboração'
    return str(status or 'Em elaboração')


def gerar_dashboard_html(orcamento_id, interno=True):
    orc, itens, opex, cron, anexos = _buscar_dados(orcamento_id)
    if not orc:
        raise Exception('Orçamento não localizado.')

    total_capex = sum(_total_item(i) for i in itens if str(campo(i, 'capex_opex', padrao='')).upper() == 'CAPEX')
    total_opex = sum(_total_item(i) for i in itens if str(campo(i, 'capex_opex', padrao='')).upper() != 'CAPEX') + sum(_total_opex(i) for i in opex)
    qtd_itens = len(itens) + len(opex)
    qtd_anexos = len(anexos or [])
    parcelas = _parcelas_ativas(cron)
    qtd_parcelas = len(parcelas)
    valor_parcela = total_capex / qtd_parcelas if qtd_parcelas else 0

    por_etapa = defaultdict(float)
    fontes = set()
    sem_obs_nao_sinapi = 0
    for item in itens:
        etapa = str(campo(item, 'etapa', padrao='Sem etapa') or 'Sem etapa')
        valor = _total_item(item)
        por_etapa[etapa] += valor
        fonte = str(campo(item, 'fonte', padrao='') or '')
        if fonte:
            fontes.add(fonte)
        obs = str(campo(item, 'observacao', padrao='') or '').strip()
        if 'sinapi' not in fonte.lower() and not obs:
            sem_obs_nao_sinapi += 1
    for row in opex:
        fonte = str(campo(row, 'fonte', padrao='') or '')
        if fonte:
            fontes.add(fonte)

    top_etapas = sorted(por_etapa.items(), key=lambda x: x[1], reverse=True)[:10]

    pasta = pasta_orcamento(campo(orc, 'codigo', padrao='ORCAMENTO')) / ('00_Revisao_Interna' if interno else '01_Cliente_Final')
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / ('Dashboard_Executivo_Interno.html' if interno else 'Dashboard_Executivo_Cliente.html')

    logo_html = _logo_base64(campo(orc, 'empresa_logo_path', padrao=''))

    status = str(campo(orc, 'status', padrao='Em elaboração') or 'Em elaboração')
    versao = _status_versao(status)
    municipio = campo(orc, 'cliente_municipio', 'municipio', padrao='') or ''
    uf = campo(orc, 'cliente_uf', padrao='') or ''
    municipio_uf = f'{municipio}/{uf}' if municipio and uf else municipio or uf or '-'
    contrato = _contrato_ref(orc)

    margem_card = ''
    if interno:
        margem_card = f'''<article class="card alert"><span>Uso interno</span><h3>Margem global</h3><strong>{texto(campo(orc, 'margem_global', padrao=0))}%</strong><p>Indicador gerencial. Não utilizar na versão enviada ao poder concedente.</p></article>'''
    else:
        margem_card = f'''<article class="card"><span>Status documental</span><h3>Versão</h3><strong>{texto(versao)}</strong><p>Status conforme cadastro do orçamento.</p></article>'''

    barras = ''
    for nome, valor in top_etapas:
        pct = (valor / total_capex * 100) if total_capex else 0
        barras += f'''
        <div class="bar-row">
            <div class="bar-label"><b>{texto(nome)}</b><span>{moeda(valor)} • {pct:.2f}%</span></div>
            <div class="bar"><i style="width:{max(2, min(100, pct)):.2f}%"></i></div>
        </div>'''
    if not barras:
        barras = "<p class='muted'>Nenhuma etapa CAPEX lançada ainda.</p>"

    pendencias = []
    if sem_obs_nao_sinapi:
        pendencias.append(f'{sem_obs_nao_sinapi} item(ns) não SINAPI sem observação técnica')
    if qtd_anexos == 0:
        pendencias.append('nenhum anexo vinculado')
    if not campo(orc, 'rt_nome', 'empresa_responsavel_tecnico', padrao=''):
        pendencias.append('responsável técnico não identificado')
    pendencias_html = (''.join(f'<li>{texto(p)}</li>' for p in pendencias) if interno else '<li>Governança documental conforme dados cadastrados.</li>') or '<li>Sem pendências críticas identificadas no dashboard.</li>'

    html = f'''<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard Executivo PPP — {texto(campo(orc, 'codigo', padrao=''))}</title>
<style>
:root{{--bg:#06101f;--panel:#0b1f3a;--line:rgba(255,255,255,.14);--text:#eef6ff;--muted:#a9bfd8;--blue:#62a8ff;--gold:#f7c948;--green:#45d483}}
*{{box-sizing:border-box}}body{{margin:0;font-family:Segoe UI,Arial,sans-serif;background:radial-gradient(circle at top left,#1b5f98 0,#071427 36%,#020713 100%);color:var(--text)}}
.hero{{padding:36px 44px 28px;border-bottom:1px solid var(--line);background:linear-gradient(135deg,rgba(11,59,117,.82),rgba(7,20,39,.76))}}.logo{{max-height:64px;max-width:190px;object-fit:contain;display:block;margin:0 0 18px 0}}.kicker{{letter-spacing:.18em;text-transform:uppercase;color:var(--gold);font-size:12px;font-weight:900}}h1{{margin:8px 0 10px;font-size:39px;line-height:1.05}}.sub{{max-width:1100px;color:var(--muted);font-size:16px;line-height:1.5}}.meta{{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}}.pill{{border:1px solid var(--line);background:rgba(255,255,255,.08);border-radius:999px;padding:8px 12px;color:#dcecff}}
.wrap{{padding:28px 44px 44px}}.grid{{display:grid;grid-template-columns:repeat(4,minmax(180px,1fr));gap:16px}}.card{{background:linear-gradient(180deg,rgba(255,255,255,.11),rgba(255,255,255,.055));border:1px solid var(--line);box-shadow:0 18px 45px rgba(0,0,0,.22);border-radius:22px;padding:20px}}.card span{{font-size:12px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);font-weight:800}}.card h3{{margin:10px 0 6px;font-size:16px;color:#fff}}.card strong{{display:block;font-size:25px;color:var(--blue);line-height:1.15}}.card p{{color:var(--muted);margin:8px 0 0;line-height:1.45}}.alert strong{{color:var(--gold)}}
.two{{display:grid;grid-template-columns:1.15fr .85fr;gap:16px;margin-top:16px}}.panel{{background:rgba(255,255,255,.07);border:1px solid var(--line);border-radius:22px;padding:22px;box-shadow:0 18px 45px rgba(0,0,0,.20)}}.panel h2{{margin:0 0 16px;font-size:22px}}.bar-row{{margin:14px 0}}.bar-label{{display:flex;justify-content:space-between;gap:18px;color:#eaf4ff;font-size:14px;margin-bottom:7px}}.bar-label span{{color:var(--muted)}}.bar{{height:12px;background:rgba(255,255,255,.11);border-radius:999px;overflow:hidden}}.bar i{{display:block;height:100%;background:linear-gradient(90deg,var(--blue),var(--green));border-radius:999px}}.muted{{color:var(--muted)}}.footer{{padding:18px 44px 28px;color:var(--muted);font-size:12px;border-top:1px solid var(--line)}}li{{margin:7px 0;color:var(--muted)}}
@media(max-width:980px){{.grid,.two{{grid-template-columns:1fr}}.hero,.wrap,.footer{{padding-left:22px;padding-right:22px}}h1{{font-size:30px}}}}
</style></head><body>
<header class="hero">{logo_html}<div class="kicker">Dashboard Executivo PPP • Enterprise</div><h1>{texto(campo(orc, 'codigo', padrao=''))} — {texto(campo(orc, 'cliente_nome', padrao=''))}</h1><div class="sub">{texto(campo(orc, 'objeto', padrao='Objeto não informado no orçamento.'))}</div><div class="meta"><span class="pill">Status: {texto(status)}</span><span class="pill">Município: {texto(municipio_uf)}</span><span class="pill">Segmento: {texto(campo(orc, 'segmento_nome', padrao='-'))}</span><span class="pill">Contrato: {texto(contrato)}</span></div></header>
<main class="wrap"><section class="grid"><article class="card"><span>Investimento</span><h3>CAPEX</h3><strong>{moeda(total_capex)}</strong><p>Base do cronograma físico-financeiro.</p></article><article class="card"><span>Recorrente</span><h3>OPEX mensal</h3><strong>{moeda(total_opex)}</strong><p>Valor mensal separado do CAPEX.</p></article><article class="card"><span>Parcelamento</span><h3>CAPEX</h3><strong>{qtd_parcelas or '—'}x</strong><p>{moeda(valor_parcela) if qtd_parcelas else 'Cronograma não preenchido'} por parcela.</p></article>{margem_card}</section><section class="two"><div class="panel"><h2>Distribuição CAPEX por etapa</h2>{barras}</div><div class="panel"><h2>Resumo executivo</h2><p class="muted"><b>Itens lançados:</b> {qtd_itens}</p><p class="muted"><b>Anexos vinculados:</b> {qtd_anexos}</p><p class="muted"><b>Fontes cadastradas:</b> {texto(' • '.join(sorted(fontes)) or 'Conforme cadastro dos itens')}</p><p class="muted"><b>Parcelas ativas:</b> {qtd_parcelas or 'não informado'}</p><h2 style="margin-top:18px">Alertas documentais</h2><ul>{pendencias_html}</ul><p class="muted">Arquivo gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}.</p></div></section></main><footer class="footer">Painel executivo consolidado para apoio à análise técnica, administrativa, financeira e contratual do orçamento.</footer></body></html>'''
    arquivo.write_text(html, encoding='utf-8')
    return arquivo
