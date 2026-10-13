from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGridLayout,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QDialog,
    QMessageBox,
    QLineEdit,
    QAbstractItemView,
    QScrollArea,
)
import webbrowser
from pathlib import Path
from datetime import datetime
from html import escape

from core.database import conn, get_pasta_local_relatorios
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar


BTN_PRIMARY = """
    QPushButton { background:#0B3B75;color:white;border:none;border-radius:11px;font-weight:900;padding:9px 16px; }
    QPushButton:hover { background:#1456A0; }
"""
BTN_SECONDARY = """
    QPushButton { background:#EAF2FF;color:#0B3B75;border:1px solid #BFD7FF;border-radius:11px;font-weight:900;padding:9px 16px; }
    QPushButton:hover { background:#DBEAFE; }
"""


class MetricCard(QFrame):
    def __init__(self, title, value="0", subtitle="", accent="#0B3B75"):
        super().__init__()
        self.setObjectName("MetricCard")
        self.setMinimumHeight(104)
        self.setStyleSheet(f"""
            QFrame#MetricCard {{
                background:white;
                border:1px solid #DBE4EF;
                border-radius:18px;
            }}
            QLabel#MetricTitle {{ color:#64748B; font-size:12px; font-weight:900; }}
            QLabel#MetricValue {{ color:{accent}; font-size:24px; font-weight:950; }}
            QLabel#MetricSub {{ color:#64748B; font-size:11px; font-weight:650; }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 13, 16, 13)
        lay.setSpacing(4)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("MetricTitle")
        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("MetricValue")
        self.value_lbl.setWordWrap(True)
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("MetricSub")
        self.sub_lbl.setWordWrap(True)
        lay.addWidget(self.title_lbl)
        lay.addWidget(self.value_lbl)
        lay.addWidget(self.sub_lbl)
        lay.addStretch()

    def update_value(self, value, subtitle=""):
        self.value_lbl.setText(str(value))
        if subtitle:
            self.sub_lbl.setText(str(subtitle))


class ActionTile(QFrame):
    def __init__(self, title, subtitle, value, button_text="Ver detalhes", callback=None, accent="#0B3B75"):
        super().__init__()
        self.callback = callback
        self.setObjectName("ActionTile")
        self.setMinimumHeight(145)
        self.setStyleSheet(f"""
            QFrame#ActionTile {{
                background:white;
                border:1px solid #DBE4EF;
                border-radius:18px;
            }}
            QLabel#TileTitle {{ font-size:15px; font-weight:950; color:#071A33; }}
            QLabel#TileSub {{ font-size:12px; color:#64748B; font-weight:700; }}
            QLabel#TileValue {{ font-size:22px; font-weight:950; color:{accent}; }}
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(7)
        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("TileTitle")
        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setObjectName("TileSub")
        self.sub_lbl.setWordWrap(True)
        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("TileValue")
        self.value_lbl.setWordWrap(True)
        self.btn = QPushButton(button_text)
        self.btn.setMinimumHeight(34)
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.setStyleSheet(BTN_SECONDARY)
        if callback:
            self.btn.clicked.connect(callback)
        root.addWidget(self.title_lbl)
        root.addWidget(self.sub_lbl)
        root.addStretch()
        bottom = QHBoxLayout()
        bottom.addWidget(self.value_lbl, 1)
        bottom.addWidget(self.btn)
        root.addLayout(bottom)

    def update_value(self, value, subtitle=None):
        self.value_lbl.setText(str(value))
        if subtitle is not None:
            self.sub_lbl.setText(str(subtitle))


class DetailDialog(QDialog):
    def __init__(self, parent, title, headers, rows):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(1080, 650)
        self.all_rows = [list(r) for r in rows]
        self.headers = headers

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size:22px;font-weight:950;color:#071A33;")
        header.addWidget(title_lbl, 1)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar nos detalhes...")
        self.search.setMinimumHeight(38)
        self.search.setStyleSheet("QLineEdit{border:1px solid #CBD5E1;border-radius:10px;padding:8px 12px;background:white;}")
        header.addWidget(self.search)
        layout.addLayout(header)

        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        configurar_tabela_responsiva(self.table, stretch_columns=[len(headers) - 1])
        self.table.setStyleSheet("""
            QTableWidget { background:white; border:1px solid #DBE4EF; border-radius:14px; gridline-color:#EDF2F7; }
            QHeaderView::section { background:#EAF2FF; color:#0B3B75; padding:9px; font-weight:900; border:none; border-right:1px solid #DBE4EF; }
            QTableWidget::item { padding:7px; }
            QTableWidget::item:selected { background:#DBEAFE;color:#071A33; }
        """)
        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color:#64748B;font-weight:850;")
        footer.addWidget(self.count_lbl, 1)
        btn_auto = QPushButton("Ajustar colunas")
        btn_auto.setStyleSheet(BTN_SECONDARY)
        btn_auto.clicked.connect(self.auto_resize)
        btn_close = QPushButton("Fechar")
        btn_close.setMinimumHeight(38)
        btn_close.setStyleSheet(BTN_PRIMARY)
        btn_close.clicked.connect(self.close)
        footer.addWidget(btn_auto)
        footer.addWidget(btn_close)
        layout.addLayout(footer)

        self.search.textChanged.connect(self.apply_filter)
        self.apply_filter()
        self.auto_resize()

    def apply_filter(self):
        termo = self.search.text().strip().lower()
        rows = self.all_rows
        if termo:
            rows = [r for r in rows if termo in " ".join(str(x or "") for x in r).lower()]

        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                item = QTableWidgetItem(str(val or ""))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)
        ajustar_tabela_apos_carregar(self.table)
        self.count_lbl.setText(f"{len(rows)} registro(s) exibido(s) de {len(self.all_rows)}")

    def auto_resize(self):
        self.table.resizeColumnsToContents()
        for i in range(self.table.columnCount()):
            largura = self.table.columnWidth(i)
            self.table.setColumnWidth(i, min(max(largura + 28, 130), 420))


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        self._loading = False
        self.status_rows = []
        self.seg_rows = []
        self.capex_segmento_rows = []
        self.opex_categoria_rows = []
        self.alertas_rows = []
        self.checklist_rows = []
        self.orcamentos_rows = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:#F4F7FB;border:none;}")
        self.page = QWidget()
        self.root = QVBoxLayout(self.page)
        self.root.setContentsMargins(20, 18, 20, 20)
        self.root.setSpacing(14)
        self.scroll.setWidget(self.page)
        outer.addWidget(self.scroll)

        self._build()
        self.load_data()

    def showEvent(self, event):
        super().showEvent(event)
        self.load_data()

    def _build(self):
        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title = QLabel("Dashboard Executivo")
        title.setStyleSheet("font-size:28px;font-weight:950;color:#071A33;")
        subtitle = QLabel("Resumo objetivo da PPP com indicadores, alertas e detalhes em pop-ups.")
        subtitle.setStyleSheet("color:#64748B;font-weight:750;")
        subtitle.setWordWrap(True)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        top.addLayout(title_box, 1)

        self.btn_atualizar = QPushButton("Atualizar dados")
        self.btn_orcamentos = QPushButton("Ver orçamentos")
        self.btn_html = QPushButton("Gerar Dashboard HTML")
        for btn in [self.btn_atualizar, self.btn_orcamentos, self.btn_html]:
            btn.setMinimumHeight(42)
            btn.setCursor(Qt.PointingHandCursor)
        self.btn_atualizar.setStyleSheet(BTN_SECONDARY)
        self.btn_orcamentos.setStyleSheet("QPushButton{background:#2563EB;color:white;border:none;border-radius:11px;font-weight:900;padding:9px 16px;} QPushButton:hover{background:#1D4ED8;}")
        self.btn_html.setStyleSheet(BTN_PRIMARY)
        top.addWidget(self.btn_atualizar)
        top.addWidget(self.btn_orcamentos)
        top.addWidget(self.btn_html)
        self.root.addLayout(top)

        self.btn_atualizar.clicked.connect(self.load_data)
        self.btn_orcamentos.clicked.connect(self.show_orcamentos)
        self.btn_html.clicked.connect(self.gerar_dashboard_html_exec)

        self.cards_grid = QGridLayout()
        self.cards_grid.setSpacing(12)
        self.card_contratos = MetricCard("Contratos", "0", "Contratos cadastrados")
        self.card_aditivos = MetricCard("Aditivos", "0", "Total vinculado a contratos")
        self.card_orcamentos = MetricCard("Orçamentos", "0", "Total de orçamentos")
        self.card_capex = MetricCard("CAPEX consolidado", "R$ 0,00", "Investimento")
        self.card_opex = MetricCard("OPEX mensal", "R$ 0,00", "Recorrente")
        self.card_margem = MetricCard("Margem média", "0,00%", "Média global")
        cards = [self.card_contratos, self.card_aditivos, self.card_orcamentos, self.card_capex, self.card_opex, self.card_margem]
        for idx, card in enumerate(cards):
            self.cards_grid.addWidget(card, idx // 3, idx % 3)
        self.root.addLayout(self.cards_grid)

        section = QLabel("Painéis executivos")
        section.setStyleSheet("font-size:18px;font-weight:950;color:#071A33;margin-top:4px;")
        self.root.addWidget(section)

        grid = QGridLayout()
        grid.setSpacing(12)
        self.tile_status = ActionTile("Orçamentos por status", "Distribuição por fase de aprovação.", "0 fase(s)", callback=lambda: self._show_detail("Orçamentos por status", ["Status", "Quantidade"], self.status_rows))
        self.tile_capex = ActionTile("CAPEX por segmento", "Ranking financeiro consolidado.", "R$ 0,00", callback=lambda: self._show_detail("CAPEX por segmento", ["Segmento", "CAPEX"], [[a, self.moeda(b)] for a, b in self.capex_segmento_rows]))
        self.tile_opex = ActionTile("OPEX por categoria", "Recorrência mensal agrupada.", "R$ 0,00", callback=lambda: self._show_detail("OPEX por categoria", ["Categoria", "OPEX mensal"], [[a, self.moeda(b)] for a, b in self.opex_categoria_rows]))
        self.tile_alertas = ActionTile("Alertas críticos", "Pendências que travam o pacote final.", "0 pendência(s)", callback=lambda: self._show_detail("Alertas críticos", ["Alerta", "Quantidade"], self.alertas_rows), accent="#DC2626")
        self.tile_checklist = ActionTile("Checklist PPP / TCU-TCE", "Premissas de entrega final monitoradas.", "0 item(ns)", "Ver checklist", callback=lambda: self._show_detail("Checklist PPP / TCU-TCE", ["Premissa", "Status"], self.checklist_rows), accent="#16A34A")
        tiles = [self.tile_status, self.tile_capex, self.tile_opex, self.tile_alertas, self.tile_checklist]
        for idx, tile in enumerate(tiles):
            grid.addWidget(tile, idx // 3, idx % 3)
        self.root.addLayout(grid)

        insight = QFrame()
        insight.setObjectName("InsightPanel")
        insight.setStyleSheet("QFrame#InsightPanel{background:white;border:1px solid #DBE4EF;border-radius:18px;}")
        il = QHBoxLayout(insight)
        il.setContentsMargins(16, 14, 16, 14)
        il.setSpacing(16)
        self.insight_label = QLabel("Carregando leitura executiva...")
        self.insight_label.setWordWrap(True)
        self.insight_label.setStyleSheet("color:#334155;font-size:13px;font-weight:800;")
        btn_check = QPushButton("Abrir checklist")
        btn_check.setMinimumHeight(36)
        btn_check.setCursor(Qt.PointingHandCursor)
        btn_check.setStyleSheet(BTN_PRIMARY)
        btn_check.clicked.connect(lambda: self._show_detail("Checklist PPP / TCU-TCE", ["Premissa", "Status"], self.checklist_rows))
        il.addWidget(self.insight_label, 1)
        il.addWidget(btn_check)
        self.root.addWidget(insight)
        self.root.addStretch()

    def moeda(self, valor):
        try:
            valor = float(valor or 0)
        except Exception:
            valor = 0
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _show_detail(self, title, headers, rows):
        dlg = DetailDialog(self, title, headers, rows)
        dlg.exec()

    def show_orcamentos(self):
        headers = ["Código", "Cliente", "Contrato", "Segmento", "Status", "CAPEX", "OPEX", "Margem"]
        rows = []
        for r in self.orcamentos_rows:
            rows.append([
                r["codigo"], r["cliente"], r["contrato"], r["segmento"], r["status"],
                self.moeda(r["capex"]), self.moeda(r["opex"]), f"{float(r['margem'] or 0):.2f}%".replace(".", ",")
            ])
        self._show_detail("Base de orçamentos", headers, rows)

    def load_data(self):
        if self._loading:
            return
        self._loading = True
        try:
            with conn() as c:
                contrato = c.execute("SELECT COUNT(*) qtd FROM contratos").fetchone()["qtd"]
                aditivos = c.execute("SELECT COUNT(*) qtd FROM aditivos").fetchone()["qtd"]
                orcs = c.execute("SELECT COUNT(*) qtd FROM orcamentos").fetchone()["qtd"]
                capex = c.execute("""
                    SELECT COALESCE(SUM(quantidade*custo_unit*(1+COALESCE(bdi,0)/100.0)*(1+COALESCE(margem,0)/100.0)),0) total
                    FROM itens WHERE capex_opex='CAPEX'
                """).fetchone()["total"]
                opex = c.execute("""
                    SELECT COALESCE(SUM(qtd_mensal*custo_unit*(1+COALESCE(bdi,0)/100.0)*(1+COALESCE(margem,0)/100.0)),0) total
                    FROM opex
                """).fetchone()["total"]
                margem = c.execute("SELECT COALESCE(AVG(margem_global),0) media FROM orcamentos").fetchone()["media"]
                status_rows = c.execute("""
                    SELECT COALESCE(status,'SEM STATUS') status, COUNT(*) qtd
                    FROM orcamentos
                    GROUP BY COALESCE(status,'SEM STATUS')
                    ORDER BY qtd DESC
                """).fetchall()
                capex_segmento_rows = c.execute("""
                    SELECT COALESCE(s.nome,'Sem segmento') segmento,
                           COALESCE(SUM(i.quantidade*i.custo_unit*(1+COALESCE(i.bdi,0)/100.0)*(1+COALESCE(i.margem,0)/100.0)),0) total
                    FROM itens i
                    JOIN orcamentos o ON o.id=i.orcamento_id
                    LEFT JOIN segmentos s ON s.id=o.segmento_id
                    WHERE i.capex_opex='CAPEX'
                    GROUP BY COALESCE(s.nome,'Sem segmento')
                    ORDER BY total DESC
                    LIMIT 12
                """).fetchall()
                opex_categoria_rows = c.execute("""
                    SELECT COALESCE(categoria,'Sem categoria') categoria,
                           COALESCE(SUM(qtd_mensal*custo_unit*(1+COALESCE(bdi,0)/100.0)*(1+COALESCE(margem,0)/100.0)),0) total
                    FROM opex
                    GROUP BY COALESCE(categoria,'Sem categoria')
                    ORDER BY total DESC
                    LIMIT 12
                """).fetchall()
                seg_rows = c.execute("""
                    SELECT s.nome, COUNT(a.id) qtd
                    FROM segmentos s
                    LEFT JOIN aditivos a ON a.segmento_id=s.id
                    GROUP BY s.id, s.nome
                    ORDER BY qtd DESC, s.nome
                """).fetchall()
                orcamentos_rows = c.execute("""
                    SELECT o.codigo, cl.nome cliente, co.nome contrato, s.nome segmento, o.status, o.margem_global margem,
                           COALESCE(SUM(CASE WHEN i.capex_opex='CAPEX' THEN i.quantidade*i.custo_unit*(1+COALESCE(i.bdi,0)/100.0)*(1+COALESCE(i.margem,0)/100.0) ELSE 0 END),0) capex,
                           COALESCE((SELECT SUM(op.qtd_mensal*op.custo_unit*(1+COALESCE(op.bdi,0)/100.0)*(1+COALESCE(op.margem,0)/100.0)) FROM opex op WHERE op.orcamento_id=o.id),0) opex
                    FROM orcamentos o
                    LEFT JOIN clientes cl ON cl.id=o.cliente_id
                    LEFT JOIN contratos co ON co.id=o.contrato_id
                    LEFT JOIN segmentos s ON s.id=o.segmento_id
                    LEFT JOIN itens i ON i.orcamento_id=o.id
                    GROUP BY o.id
                    ORDER BY o.id DESC
                """).fetchall()
                sem_segmento = c.execute("SELECT COUNT(*) qtd FROM contratos WHERE COALESCE(segmentos,'')='' AND id NOT IN (SELECT contrato_id FROM contrato_segmentos)").fetchone()["qtd"]
                sem_crono = c.execute("SELECT COUNT(*) qtd FROM orcamentos o WHERE NOT EXISTS (SELECT 1 FROM cronograma_parcelas cp WHERE cp.orcamento_id=o.id)").fetchone()["qtd"]
                sem_anexo = c.execute("SELECT COUNT(*) qtd FROM orcamentos o WHERE NOT EXISTS (SELECT 1 FROM documentos d WHERE d.orcamento_id=o.id)").fetchone()["qtd"]

            self.card_contratos.update_value(str(contrato), "Contratos cadastrados")
            self.card_aditivos.update_value(str(aditivos), "Total vinculado a contratos")
            self.card_orcamentos.update_value(str(orcs), "Total de orçamentos")
            self.card_capex.update_value(self.moeda(capex), "Investimento")
            self.card_opex.update_value(self.moeda(opex), "Recorrente")
            self.card_margem.update_value(f"{float(margem or 0):.2f}%".replace(".", ","), "Média global")

            self.status_rows = [[r["status"], r["qtd"]] for r in status_rows]
            self.seg_rows = [[r["nome"], r["qtd"]] for r in seg_rows]
            self.capex_segmento_rows = [[r["segmento"], r["total"]] for r in capex_segmento_rows]
            self.opex_categoria_rows = [[r["categoria"], r["total"]] for r in opex_categoria_rows]
            self.orcamentos_rows = orcamentos_rows

            self.alertas_rows = []
            if sem_segmento:
                self.alertas_rows.append(["Contrato sem segmento", sem_segmento])
            if sem_crono:
                self.alertas_rows.append(["Orçamento sem cronograma", sem_crono])
            if sem_anexo:
                self.alertas_rows.append(["Orçamento sem anexos", sem_anexo])
            if not self.alertas_rows:
                self.alertas_rows.append(["Sem alertas críticos", 0])

            self.checklist_rows = [
                ["CAPEX separado de OPEX", "OK"],
                ["Orçamento vinculado a contrato/aditivo/segmento", "Verificar por orçamento"],
                ["Cronograma físico-financeiro preenchido", "Ver alertas"],
                ["Memorial e anexos disponíveis para pacote final", "Ver alertas"],
                ["BDI e margem tratados internamente", "OK"],
            ]
            pendencias = sum(int(r[1] or 0) for r in self.alertas_rows if str(r[0]) != "Sem alertas críticos")
            status_count = len(self.status_rows)
            total_capex_segmentos = sum(float(r[1] or 0) for r in self.capex_segmento_rows)
            total_opex_categorias = sum(float(r[1] or 0) for r in self.opex_categoria_rows)
            principal_status = self.status_rows[0][0] if self.status_rows else "Sem status"
            principal_segmento = self.capex_segmento_rows[0][0] if self.capex_segmento_rows else "Sem CAPEX"

            self.tile_status.update_value(f"{status_count} fase(s)", f"Principal fase: {principal_status}")
            self.tile_capex.update_value(self.moeda(total_capex_segmentos), f"Principal segmento: {principal_segmento}")
            self.tile_opex.update_value(self.moeda(total_opex_categorias), "Categorias OPEX monitoradas")
            self.tile_alertas.update_value(f"{pendencias} pendência(s)", "Abrir detalhes antes do pacote final")
            self.tile_checklist.update_value(f"{len(self.checklist_rows)} premissas", "Checklist de conformidade da entrega")
            self.insight_label.setText(
                f"Leitura executiva: {orcs} orçamento(s), {aditivos} aditivo(s), CAPEX de {self.moeda(capex)} e {pendencias} pendência(s) crítica(s) para tratar antes da geração final."
            )
        except Exception as e:
            QMessageBox.warning(self, "Dashboard Executivo", f"Não foi possível carregar o dashboard:\n{e}")
        finally:
            self._loading = False

    def gerar_dashboard_html_exec(self):
        try:
            pasta = get_pasta_local_relatorios() / "Dashboard_Executivo"
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo = pasta / f"dashboard_executivo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

            status_rows = "".join(
                f"<tr><td>{escape(str(r[0]))}</td><td>{escape(str(r[1]))}</td></tr>" for r in self.status_rows
            )
            capex_rows = "".join(
                f"<tr><td>{escape(str(r[0]))}</td><td>{self.moeda(r[1])}</td></tr>" for r in self.capex_segmento_rows
            )
            opex_rows = "".join(
                f"<tr><td>{escape(str(r[0]))}</td><td>{self.moeda(r[1])}</td></tr>" for r in self.opex_categoria_rows
            )
            alertas_rows = "".join(
                f"<tr><td>{escape(str(r[0]))}</td><td>{escape(str(r[1]))}</td></tr>" for r in self.alertas_rows
            )

            html = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard Executivo PPP</title>
<style>
body{{margin:0;font-family:Segoe UI,Arial;background:#F4F7FB;color:#172033}}.hero{{background:linear-gradient(135deg,#071A33,#0B3B75);color:white;padding:34px}}
h1{{margin:0;font-size:34px}}.sub{{opacity:.84;margin-top:8px}}.wrap{{padding:24px;display:grid;gap:18px}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}}
.card,.panel{{background:white;border:1px solid #DBE4EF;border-radius:18px;padding:18px;box-shadow:0 10px 30px rgba(7,26,51,.06)}}.card span{{color:#64748B;font-weight:800}}.card strong{{display:block;color:#0B3B75;font-size:26px;margin-top:6px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}h2{{margin:0 0 12px;color:#071A33}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px;border-bottom:1px solid #E5EAF1;text-align:left}}th{{background:#EAF2FF;color:#0B3B75}}@media(max-width:900px){{.cards,.grid{{grid-template-columns:1fr}}}}
</style></head><body><section class="hero"><h1>Dashboard Executivo PPP</h1><div class="sub">Gerado em {datetime.now().strftime('%d/%m/%Y às %H:%M')}</div></section>
<main class="wrap"><section class="cards">
<article class="card"><span>Contratos</span><strong>{self.card_contratos.value_lbl.text()}</strong></article>
<article class="card"><span>Aditivos</span><strong>{self.card_aditivos.value_lbl.text()}</strong></article>
<article class="card"><span>Orçamentos</span><strong>{self.card_orcamentos.value_lbl.text()}</strong></article>
<article class="card"><span>CAPEX</span><strong>{self.card_capex.value_lbl.text()}</strong></article>
<article class="card"><span>OPEX mensal</span><strong>{self.card_opex.value_lbl.text()}</strong></article>
<article class="card"><span>Margem média</span><strong>{self.card_margem.value_lbl.text()}</strong></article>
</section><section class="grid">
<div class="panel"><h2>Orçamentos por status</h2><table><tr><th>Status</th><th>Quantidade</th></tr>{status_rows}</table></div>
<div class="panel"><h2>CAPEX por segmento</h2><table><tr><th>Segmento</th><th>Valor</th></tr>{capex_rows}</table></div>
<div class="panel"><h2>OPEX por categoria</h2><table><tr><th>Categoria</th><th>Valor</th></tr>{opex_rows}</table></div>
<div class="panel"><h2>Alertas críticos</h2><table><tr><th>Alerta</th><th>Quantidade</th></tr>{alertas_rows}</table></div>
</section></main></body></html>"""
            arquivo.write_text(html, encoding="utf-8")
            webbrowser.open(Path(arquivo).resolve().as_uri())
            QMessageBox.information(self, "Dashboard Executivo", f"Dashboard HTML gerado com sucesso:\n{arquivo}")
        except Exception as e:
            QMessageBox.critical(self, "Dashboard Executivo", f"Erro ao gerar dashboard HTML:\n{e}")
