from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QFrame,
    QDialog,
    QMessageBox,
    QHeaderView,
    QSizePolicy,
)

from core.database import conn
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar


STATUS_PADRAO = [
    "TODOS",
    "RASCUNHO",
    "EM ELABORAÇÃO",
    "EM REVISÃO",
    "APROVADO",
    "ENVIADO",
    "CANCELADO",
]


class StatCard(QFrame):
    def __init__(self, titulo: str, valor: str = "0", cor: str = "#0B3B75"):
        super().__init__()
        self.setObjectName("StatCard")
        self.setMinimumHeight(92)
        self.setStyleSheet(
            f"""
            QFrame#StatCard {{
                background:white;
                border:1px solid #DBE4EF;
                border-radius:14px;
            }}
            QLabel#titulo {{
                color:#64748B;
                font-size:12px;
                font-weight:800;
            }}
            QLabel#valor {{
                color:{cor};
                font-size:24px;
                font-weight:900;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setObjectName("titulo")

        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setObjectName("valor")

        layout.addWidget(self.lbl_titulo)
        layout.addWidget(self.lbl_valor)
        layout.addStretch()

    def set_valor(self, valor: Any):
        self.lbl_valor.setText(str(valor))


class OrcamentoDetalheDialog(QDialog):
    def __init__(self, parent, dados: dict[str, Any]):
        super().__init__(parent)
        self.setWindowTitle("Detalhes do orçamento")
        self.resize(760, 520)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        titulo = QLabel(str(dados.get("codigo") or "Orçamento"))
        titulo.setStyleSheet("font-size:22px;font-weight:950;color:#071A33;")
        root.addWidget(titulo)

        card = QFrame()
        card.setObjectName("DetalheCard")
        card.setStyleSheet("""
            QFrame#DetalheCard { background:white; border:1px solid #DBE4EF; border-radius:16px; }
            QLabel#Label { color:#64748B; font-weight:900; font-size:12px; }
            QLabel#Value { color:#172033; font-weight:750; font-size:13px; }
        """)
        grid = QGridLayout(card)
        grid.setContentsMargins(16, 16, 16, 16)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        campos = [
            ("Cliente", dados.get("cliente")),
            ("Contrato", dados.get("contrato")),
            ("Segmento", dados.get("segmento")),
            ("Município", dados.get("municipio")),
            ("Status", dados.get("status")),
            ("Atualização", dados.get("atualizado")),
            ("CAPEX", dados.get("total_capex")),
            ("OPEX", dados.get("total_opex")),
            ("Objeto", dados.get("objeto")),
        ]
        for idx, (label, value) in enumerate(campos):
            r = idx // 2
            c = (idx % 2) * 2
            l = QLabel(label)
            l.setObjectName("Label")
            v = QLabel(str(value or "-"))
            v.setObjectName("Value")
            v.setWordWrap(True)
            grid.addWidget(l, r, c)
            grid.addWidget(v, r, c + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        root.addWidget(card, 1)

        footer = QHBoxLayout()
        footer.addStretch()
        btn = QPushButton("Fechar")
        btn.setMinimumHeight(38)
        btn.setStyleSheet("QPushButton{background:#0B3B75;color:white;border:none;border-radius:10px;font-weight:900;padding:8px 16px;}")
        btn.clicked.connect(self.close)
        footer.addWidget(btn)
        root.addLayout(footer)


class MeusOrcamentosView(QWidget):
    """
    Central operacional de orçamentos.

    Esta view é intencionalmente desacoplada da OrcamentosView.
    Para abrir um orçamento, passe on_open_orcamento no construtor.
    Exemplo no main.py:
        "meus_orcamentos": MeusOrcamentosView(self.abrir_orcamento)
    """

    def __init__(self, on_open_orcamento: Optional[Callable[[int], None]] = None):
        super().__init__()
        self.on_open_orcamento = on_open_orcamento
        self.orcamento_id_selecionado: Optional[int] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(13)

        topo = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(3)

        titulo = QLabel("Meus Orçamentos")
        titulo.setStyleSheet("font-size:27px;font-weight:950;color:#071A33;")

        subtitulo = QLabel("Pesquisa e gestão operacional dos orçamentos. A tela mostra o essencial; detalhes completos ficam no pop-up.")
        subtitulo.setStyleSheet("font-size:13px;color:#64748B;font-weight:700;")
        subtitulo.setWordWrap(True)

        title_box.addWidget(titulo)
        title_box.addWidget(subtitulo)

        self.btn_atualizar = self._btn("Atualizar", "#0B3B75")
        self.btn_atualizar.clicked.connect(self.carregar_tudo)

        self.btn_novo = self._btn("Novo orçamento", "#2563EB")
        self.btn_novo.clicked.connect(self.novo_orcamento)

        topo.addLayout(title_box, 1)
        topo.addWidget(self.btn_atualizar)
        topo.addWidget(self.btn_novo)
        root.addLayout(topo)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_total = StatCard("Total", "0")
        self.card_andamento = StatCard("Em andamento", "0", "#2563EB")
        self.card_pendencias = StatCard("Pendências", "0", "#DC2626")
        for card in [self.card_total, self.card_andamento, self.card_pendencias]:
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            cards.addWidget(card)
        root.addLayout(cards)

        box_filtros = QFrame()
        box_filtros.setObjectName("BoxFiltros")
        box_filtros.setStyleSheet(
            """
            QFrame#BoxFiltros {
                background:white;
                border:1px solid #DBE4EF;
                border-radius:16px;
            }
            QLabel {
                color:#334155;
                font-weight:900;
                font-size:12px;
            }
            QLineEdit, QComboBox {
                min-height:38px;
                border:1px solid #CBD5E1;
                border-radius:10px;
                padding:7px 10px;
                background:#FFFFFF;
            }
            QLineEdit:focus, QComboBox:focus { border:1px solid #0B3B75; }
            """
        )

        filtros = QGridLayout(box_filtros)
        filtros.setContentsMargins(14, 14, 14, 14)
        filtros.setHorizontalSpacing(12)
        filtros.setVerticalSpacing(8)

        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar por código, objeto, cliente, contrato ou município")

        self.combo_cliente = QComboBox()
        self.combo_contrato = QComboBox()
        self.combo_segmento = QComboBox()
        self.combo_status = QComboBox()
        self.combo_status.addItems(STATUS_PADRAO)

        filtros.addWidget(QLabel("Buscar"), 0, 0)
        filtros.addWidget(QLabel("Cliente"), 0, 1)
        filtros.addWidget(QLabel("Contrato"), 0, 2)
        filtros.addWidget(QLabel("Segmento"), 0, 3)
        filtros.addWidget(QLabel("Status"), 0, 4)

        filtros.addWidget(self.busca, 1, 0)
        filtros.addWidget(self.combo_cliente, 1, 1)
        filtros.addWidget(self.combo_contrato, 1, 2)
        filtros.addWidget(self.combo_segmento, 1, 3)
        filtros.addWidget(self.combo_status, 1, 4)

        filtros.setColumnStretch(0, 3)
        filtros.setColumnStretch(1, 2)
        filtros.setColumnStretch(2, 2)
        filtros.setColumnStretch(3, 2)
        filtros.setColumnStretch(4, 1)

        root.addWidget(box_filtros)

        self.busca.textChanged.connect(self.carregar_orcamentos)
        self.combo_cliente.currentIndexChanged.connect(self.carregar_orcamentos)
        self.combo_contrato.currentIndexChanged.connect(self.carregar_orcamentos)
        self.combo_segmento.currentIndexChanged.connect(self.carregar_orcamentos)
        self.combo_status.currentIndexChanged.connect(self.carregar_orcamentos)

        box_lista = QFrame()
        box_lista.setObjectName("BoxLista")
        box_lista.setStyleSheet(
            """
            QFrame#BoxLista { background:white; border:1px solid #DBE4EF; border-radius:16px; }
            QLabel#ListaTitle { color:#071A33; font-size:15px; font-weight:950; }
            QLabel#ListaSub { color:#64748B; font-size:12px; font-weight:700; }
            """
        )
        lista_layout = QVBoxLayout(box_lista)
        lista_layout.setContentsMargins(14, 12, 14, 14)
        lista_layout.setSpacing(10)
        lista_head = QHBoxLayout()
        lista_titles = QVBoxLayout()
        lista_title = QLabel("Lista operacional")
        lista_title.setObjectName("ListaTitle")
        lista_sub = QLabel("Colunas ajustáveis. Dê duplo clique para abrir o orçamento.")
        lista_sub.setObjectName("ListaSub")
        lista_titles.addWidget(lista_title)
        lista_titles.addWidget(lista_sub)
        lista_head.addLayout(lista_titles, 1)
        self.btn_detalhes_topo = self._btn("Ver detalhes", "#0B3B75")
        self.btn_detalhes_topo.clicked.connect(self.ver_detalhes_orcamento)
        lista_head.addWidget(self.btn_detalhes_topo)
        lista_layout.addLayout(lista_head)

        self.tabela = QTableWidget()
        self.tabela.setColumnCount(8)
        self.tabela.setHorizontalHeaderLabels(["ID", "Código", "Cliente", "Segmento", "Status", "CAPEX", "OPEX", "Atualização"])
        configurar_tabela_responsiva(self.tabela, stretch_columns=[2], hidden_columns=[0])
        self.tabela.setMinimumHeight(340)
        self.tabela.cellClicked.connect(self._selecionar_linha)
        self.tabela.cellDoubleClicked.connect(lambda *_: self.abrir_orcamento())

        self.tabela.setStyleSheet(
            """
            QTableWidget {
                background:white;
                border:1px solid #E2E8F0;
                border-radius:12px;
                gridline-color:#EDF2F7;
            }
            QHeaderView::section {
                background:#EAF2FF;
                color:#0B3B75;
                font-weight:950;
                padding:9px;
                border:0;
                border-right:1px solid #DBE4EF;
            }
            QTableWidget::item { padding:7px; }
            QTableWidget::item:selected { background:#DBEAFE; color:#0F172A; }
            """
        )

        lista_layout.addWidget(self.tabela, 1)
        root.addWidget(box_lista, 1)

        acoes = QHBoxLayout()
        acoes.setSpacing(10)

        self.btn_abrir = self._btn("Abrir orçamento", "#0B3B75")
        self.btn_detalhes = self._btn("Detalhes", "#2563EB")
        self.btn_duplicar = self._btn("Duplicar", "#2563EB")
        self.btn_status = self._btn("Alterar status", "#7C3AED")
        self.btn_gerar = self._btn("Gerar pacote", "#16A34A")
        self.btn_arquivar = self._btn("Arquivar", "#64748B")
        self.btn_excluir = self._btn("Excluir", "#DC2626")

        self.btn_abrir.clicked.connect(self.abrir_orcamento)
        self.btn_detalhes.clicked.connect(self.ver_detalhes_orcamento)
        self.btn_duplicar.clicked.connect(self.duplicar_orcamento)
        self.btn_status.clicked.connect(self.alterar_status)
        self.btn_gerar.clicked.connect(self.gerar_pacote)
        self.btn_arquivar.clicked.connect(self.arquivar_orcamento)
        self.btn_excluir.clicked.connect(self.excluir_orcamento)

        for b in [self.btn_abrir, self.btn_detalhes, self.btn_duplicar, self.btn_status, self.btn_gerar, self.btn_arquivar, self.btn_excluir]:
            acoes.addWidget(b)

        acoes.addStretch()
        root.addLayout(acoes)

        self.carregar_tudo()

    def showEvent(self, event):
        super().showEvent(event)
        self.carregar_tudo()

    def _btn(self, texto: str, cor: str) -> QPushButton:
        btn = QPushButton(texto)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(40)
        btn.setStyleSheet(
            f"""
            QPushButton {{
                background:{cor};
                color:white;
                border-radius:9px;
                padding:8px 14px;
                font-size:13px;
                font-weight:800;
            }}
            QPushButton:hover {{
                background:{cor};
            }}
            """
        )
        return btn

    def _moeda(self, valor: Any) -> str:
        try:
            valor = float(valor or 0)
        except Exception:
            valor = 0
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _colunas(self, tabela: str) -> set[str]:
        try:
            with conn() as c:
                rows = c.execute(f"PRAGMA table_info({tabela})").fetchall()
            return {r["name"] if isinstance(r, sqlite3.Row) else r[1] for r in rows}
        except Exception:
            return set()


    def _num_expr(self, alias: str, cols: set[str], candidatos: list[str], padrao: str = "0") -> str:
        existentes = [f"{alias}.{col}" for col in candidatos if col in cols]
        if not existentes:
            return padrao
        return "COALESCE(" + ", ".join(existentes + [padrao]) + ")"

    def _texto_expr(self, alias: str, cols: set[str], candidatos: list[str], padrao: str = "''") -> str:
        existentes = [f"{alias}.{col}" for col in candidatos if col in cols]
        if not existentes:
            return padrao
        return "COALESCE(" + ", ".join(existentes + [padrao]) + ")"

    def carregar_tudo(self):
        self._carregar_combos()
        self.carregar_orcamentos()
        self.carregar_cards()

    def _carregar_combos(self):
        self._carregar_combo_clientes()
        self._carregar_combo_contratos()
        self._carregar_combo_segmentos()

    def _carregar_combo_clientes(self):
        atual = self.combo_cliente.currentData()
        self.combo_cliente.blockSignals(True)
        self.combo_cliente.clear()
        self.combo_cliente.addItem("Todos", None)

        try:
            with conn() as c:
                dados = c.execute("SELECT id, nome FROM clientes ORDER BY nome").fetchall()
            for row in dados:
                self.combo_cliente.addItem(str(row["nome"]), row["id"])
        except Exception:
            pass

        idx = self.combo_cliente.findData(atual)
        if idx >= 0:
            self.combo_cliente.setCurrentIndex(idx)
        self.combo_cliente.blockSignals(False)

    def _carregar_combo_contratos(self):
        atual = self.combo_contrato.currentData()
        self.combo_contrato.blockSignals(True)
        self.combo_contrato.clear()
        self.combo_contrato.addItem("Todos", None)

        try:
            with conn() as c:
                dados = c.execute("SELECT id, nome FROM contratos ORDER BY nome").fetchall()
            for row in dados:
                self.combo_contrato.addItem(str(row["nome"]), row["id"])
        except Exception:
            pass

        idx = self.combo_contrato.findData(atual)
        if idx >= 0:
            self.combo_contrato.setCurrentIndex(idx)
        self.combo_contrato.blockSignals(False)

    def _carregar_combo_segmentos(self):
        atual = self.combo_segmento.currentData()
        self.combo_segmento.blockSignals(True)
        self.combo_segmento.clear()
        self.combo_segmento.addItem("Todos", None)

        try:
            cols = self._colunas("segmentos")
            if cols:
                nome_col = "nome" if "nome" in cols else list(cols)[0]
                with conn() as c:
                    dados = c.execute(f"SELECT id, {nome_col} AS nome FROM segmentos ORDER BY nome").fetchall()
                for row in dados:
                    self.combo_segmento.addItem(str(row["nome"]), row["id"])
        except Exception:
            pass

        idx = self.combo_segmento.findData(atual)
        if idx >= 0:
            self.combo_segmento.setCurrentIndex(idx)
        self.combo_segmento.blockSignals(False)

    def _expr_cliente(self) -> str:
        return "COALESCE(cli.nome, '')"

    def _expr_contrato(self) -> str:
        return "COALESCE(ct.nome, ct.numero, '')"

    def _expr_segmento(self) -> str:
        cols = self._colunas("orcamentos")
        if "segmento" in cols:
            return "COALESCE(seg.nome, o.segmento, '')"
        return "COALESCE(seg.nome, '')"

    def carregar_orcamentos(self):
        termo = self.busca.text().strip()
        cliente_id = self.combo_cliente.currentData()
        contrato_id = self.combo_contrato.currentData()
        segmento_id = self.combo_segmento.currentData()
        status = self.combo_status.currentText()

        orc_cols = self._colunas("orcamentos")
        tem_segmento_id = "segmento_id" in orc_cols
        tem_aditivo_id = "aditivo_id" in orc_cols
        tem_municipio = "municipio" in orc_cols
        tem_data_atualizacao = "data_atualizacao" in orc_cols or "updated_at" in orc_cols

        data_expr = "o.data_atualizacao" if "data_atualizacao" in orc_cols else ("o.updated_at" if "updated_at" in orc_cols else "o.data_criacao")
        municipio_expr = "COALESCE(o.municipio, cli.municipio, ct.municipio, '')" if tem_municipio else "COALESCE(cli.municipio, ct.municipio, '')"

        if "objeto" in orc_cols and "descricao" in orc_cols:
            objeto_expr = "COALESCE(o.objeto, o.descricao, '')"
            busca_objeto = "OR o.objeto LIKE ?OR o.descricao LIKE ?"
            busca_objeto_params = 2
        elif "objeto" in orc_cols:
            objeto_expr = "COALESCE(o.objeto, '')"
            busca_objeto = "OR o.objeto LIKE ?"
            busca_objeto_params = 1
        elif "descricao" in orc_cols:
            objeto_expr = "COALESCE(o.descricao, '')"
            busca_objeto = "OR o.descricao LIKE ?"
            busca_objeto_params = 1
        else:
            objeto_expr = "''"
            busca_objeto = ""
            busca_objeto_params = 0

        seg_join = "LEFT JOIN segmentos seg ON seg.id = o.segmento_id" if tem_segmento_id else "LEFT JOIN segmentos seg ON 1=0"

        # Compatibilidade com bancos criados em pacotes anteriores:
        # algumas bases usam custo_unit, outras custo_unitario, e a tabela opex pode não ter quantidade.
        itens_cols = self._colunas("itens")
        opex_cols = self._colunas("opex")

        if itens_cols and "orcamento_id" in itens_cols:
            i_qtd = self._num_expr("i", itens_cols, ["quantidade", "qtd", "qtde"], "1")
            i_custo = self._num_expr("i", itens_cols, ["custo_unit", "custo_unitario", "valor_unitario", "preco_unitario", "custo", "valor"], "0")
            i_bdi = self._num_expr("i", itens_cols, ["bdi", "bdi_percentual", "bdi_percent"], "0")
            i_margem = self._num_expr("i", itens_cols, ["margem", "margem_interna", "margem_percentual", "margem_percent"], "0")
            if "capex_opex" in itens_cols:
                filtro_capex = "AND UPPER(COALESCE(i.capex_opex,''))='CAPEX'"
            elif "tipo_custo" in itens_cols:
                filtro_capex = "AND UPPER(COALESCE(i.tipo_custo,''))='CAPEX'"
            else:
                filtro_capex = ""
            total_capex_expr = f"""
                COALESCE((
                    SELECT SUM(({i_qtd})*({i_custo})*(1+({i_bdi})/100.0)*(1+({i_margem})/100.0))
                    FROM itens i
                    WHERE i.orcamento_id=o.id {filtro_capex}
                ),0)
            """
        else:
            total_capex_expr = "0"

        if opex_cols and "orcamento_id" in opex_cols:
            # HOTFIX 07.4: montagem 100% compatível com bancos antigos.
            # Nunca referencia op.quantidade se essa coluna não existir.
            qtd_cols = [col for col in ["quantidade", "qtd", "qtde"] if col in opex_cols]
            custo_cols = [col for col in ["custo_unit", "custo_unitario", "valor_unitario", "preco_unitario", "custo", "valor", "valor_mensal", "mensal", "total"] if col in opex_cols]
            margem_cols = [col for col in ["margem", "margem_interna", "margem_percentual", "margem_percent"] if col in opex_cols]

            op_qtd = "COALESCE(" + ", ".join([f"op.{c}" for c in qtd_cols] + ["1"]) + ")" if qtd_cols else "1"
            op_custo = "COALESCE(" + ", ".join([f"op.{c}" for c in custo_cols] + ["0"]) + ")" if custo_cols else "0"
            op_margem = "COALESCE(" + ", ".join([f"op.{c}" for c in margem_cols] + ["0"]) + ")" if margem_cols else "0"

            total_opex_expr = f"""
                COALESCE((
                    SELECT SUM(({op_qtd})*({op_custo})*(1+({op_margem})/100.0))
                    FROM opex op
                    WHERE op.orcamento_id=o.id
                ),0)
            """
        else:
            total_opex_expr = "0"

        sql = f"""
            SELECT
                o.id,
                COALESCE(o.codigo, 'ORC-' || o.id) AS codigo,
                {self._expr_cliente()} AS cliente,
                {self._expr_contrato()} AS contrato,
                {self._expr_segmento()} AS segmento,
                {objeto_expr} AS objeto,
                COALESCE(o.status, 'EM ELABORAÇÃO') AS status,
                {total_capex_expr} AS total_capex,
                {total_opex_expr} AS total_opex,
                COALESCE({data_expr}, '') AS atualizado,
                {municipio_expr} AS municipio
            FROM orcamentos o
            LEFT JOIN clientes cli ON cli.id = o.cliente_id
            LEFT JOIN contratos ct ON ct.id = o.contrato_id
            {seg_join}
            WHERE 1=1
        """

        params: list[Any] = []

        if termo:
            sql += f"""
                AND (
                    o.codigo LIKE ?
                    {busca_objeto}
                    OR cli.nome LIKE ?
                    OR ct.nome LIKE ?
                    OR ct.numero LIKE ?
                    OR cli.municipio LIKE ?
                    OR ct.municipio LIKE ?
                )
            """
            like = f"%{termo}%"
            params.extend([like] * (1 + busca_objeto_params + 5))

        if cliente_id:
            sql += " AND o.cliente_id=?"
            params.append(cliente_id)

        if contrato_id:
            sql += " AND o.contrato_id=?"
            params.append(contrato_id)

        if segmento_id and tem_segmento_id:
            sql += " AND o.segmento_id=?"
            params.append(segmento_id)

        if status and status != "TODOS":
            sql += " AND UPPER(COALESCE(o.status,''))=?"
            params.append(status.upper())

        sql += " ORDER BY o.id DESC LIMIT 1000"

        try:
            with conn() as c:
                dados = c.execute(sql, tuple(params)).fetchall()
        except Exception as e:
            QMessageBox.warning(self, "Meus Orçamentos", f"Erro ao carregar orçamentos (hotfix 07.4):\n{e}")
            dados = []

        self.tabela.setRowCount(len(dados))

        for row, item in enumerate(dados):
            valores = [
                item["id"],
                item["codigo"],
                item["cliente"],
                item["segmento"],
                item["status"],
                self._moeda(item["total_capex"]),
                self._moeda(item["total_opex"]),
                item["atualizado"],
            ]

            for col, valor in enumerate(valores):
                cell = QTableWidgetItem(str(valor or ""))
                if col == 0:
                    cell.setTextAlignment(Qt.AlignCenter)
                if col in [5, 6]:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if col == 4:
                    self._pintar_status(cell, str(valor or ""))
                self.tabela.setItem(row, col, cell)

        self._ajustar_colunas_lista()

    def _pintar_status(self, item: QTableWidgetItem, status: str):
        st = status.upper()
        if "APROV" in st:
            item.setBackground(QColor("#DCFCE7"))
        elif "REVIS" in st:
            item.setBackground(QColor("#EDE9FE"))
        elif "CANCEL" in st or "REPROV" in st:
            item.setBackground(QColor("#FEE2E2"))
        elif "ELAB" in st:
            item.setBackground(QColor("#DBEAFE"))
        else:
            item.setBackground(QColor("#F1F5F9"))

    def carregar_cards(self):
        try:
            with conn() as c:
                total = c.execute("SELECT COUNT(*) AS n FROM orcamentos").fetchone()["n"]
                andamento = c.execute("""
                    SELECT COUNT(*) AS n
                    FROM orcamentos
                    WHERE UPPER(COALESCE(status,'EM ELABORAÇÃO')) IN ('RASCUNHO','EM ELABORAÇÃO','EM REVISÃO')
                """).fetchone()["n"]
                sem_crono = c.execute("SELECT COUNT(*) AS n FROM orcamentos o WHERE NOT EXISTS (SELECT 1 FROM cronograma_parcelas cp WHERE cp.orcamento_id=o.id)").fetchone()["n"]
                sem_anexo = c.execute("SELECT COUNT(*) AS n FROM orcamentos o WHERE NOT EXISTS (SELECT 1 FROM documentos d WHERE d.orcamento_id=o.id)").fetchone()["n"]
        except Exception:
            total = 0
            andamento = 0
            sem_crono = 0
            sem_anexo = 0

        self.card_total.set_valor(total)
        self.card_andamento.set_valor(andamento)
        self.card_pendencias.set_valor(int(sem_crono or 0) + int(sem_anexo or 0))

    def _ajustar_colunas_lista(self):
        try:
            ajustar_tabela_apos_carregar(self.tabela)
        except Exception:
            pass

    def _selecionar_linha(self, row: int, col: int):
        item = self.tabela.item(row, 0)
        if item:
            try:
                self.orcamento_id_selecionado = int(item.text())
            except Exception:
                self.orcamento_id_selecionado = None

    def _obter_id_selecionado(self) -> Optional[int]:
        if self.orcamento_id_selecionado:
            return self.orcamento_id_selecionado

        row = self.tabela.currentRow()
        if row >= 0:
            item = self.tabela.item(row, 0)
            if item:
                try:
                    return int(item.text())
                except Exception:
                    return None
        return None

    def _achar_view_orcamentos(self):
        """
        Compatibilidade com diferentes versões do main.py.
        Procura a tela OrcamentosView dentro da janela principal, mesmo quando
        esta view foi criada sem callback on_open_orcamento.
        """
        janela = self.window()
        candidatos = []

        for attr in ["orcamentos_view", "view_orcamentos", "tela_orcamentos"]:
            obj = getattr(janela, attr, None)
            if obj:
                candidatos.append(obj)

        for attr in ["views", "pages", "telas"]:
            mapa = getattr(janela, attr, None)
            if isinstance(mapa, dict):
                for chave in ["orcamentos", "orcamento", "orcamentos_view", "Orçamentos", "Orcamentos"]:
                    obj = mapa.get(chave)
                    if obj:
                        candidatos.append(obj)

        try:
            from views.orcamentos_view import OrcamentosView
            encontrados = janela.findChildren(OrcamentosView)
            candidatos.extend(encontrados)
        except Exception:
            pass

        for obj in candidatos:
            if obj is not None:
                return obj
        return None

    def _navegar_para_orcamentos(self, view_orcamentos=None):
        janela = self.window()

        for metodo in [
            "abrir_tela_orcamentos",
            "mostrar_orcamentos",
            "show_orcamentos",
            "ir_para_orcamentos",
        ]:
            fn = getattr(janela, metodo, None)
            if callable(fn):
                try:
                    fn()
                    return True
                except TypeError:
                    pass
                except Exception:
                    pass

        for metodo in ["show_view", "mostrar_view", "navegar_para", "set_page", "abrir_view"]:
            fn = getattr(janela, metodo, None)
            if callable(fn):
                for chave in ["orcamentos", "orcamento", "Orçamentos", "Orcamentos"]:
                    try:
                        fn(chave)
                        return True
                    except Exception:
                        continue

        for attr in ["stack", "stacked_widget", "stacked", "conteudo", "pages_stack"]:
            stack = getattr(janela, attr, None)
            if stack and hasattr(stack, "setCurrentWidget") and view_orcamentos is not None:
                try:
                    stack.setCurrentWidget(view_orcamentos)
                    return True
                except Exception:
                    pass

        return False

    def _carregar_orcamento_na_view(self, view_orcamentos, orc_id: int) -> bool:
        if view_orcamentos is None:
            return False

        for metodo in [
            "carregar_orcamento",
            "abrir_orcamento",
            "editar_orcamento",
            "carregar_por_id",
            "load_orcamento",
            "selecionar_orcamento",
            "set_orcamento_id",
        ]:
            fn = getattr(view_orcamentos, metodo, None)
            if callable(fn):
                try:
                    fn(orc_id)
                    return True
                except TypeError:
                    continue
                except Exception:
                    continue

        # Fallback: grava o ID em atributos comuns para a tela de orçamento usar.
        try:
            view_orcamentos.orcamento_id_atual = orc_id
            view_orcamentos.orcamento_id = orc_id
            return True
        except Exception:
            return False

    def _dados_orcamento_selecionado(self) -> dict[str, Any] | None:
        row = self.tabela.currentRow()
        orc_id = self._obter_id_selecionado()
        if not orc_id:
            return None

        try:
            with conn() as c:
                orc_cols = self._colunas("orcamentos")
                data_expr = "o.data_atualizacao" if "data_atualizacao" in orc_cols else ("o.updated_at" if "updated_at" in orc_cols else "o.data_criacao")
                objeto_expr = "COALESCE(o.objeto, o.descricao, '')" if "objeto" in orc_cols and "descricao" in orc_cols else ("COALESCE(o.objeto, '')" if "objeto" in orc_cols else ("COALESCE(o.descricao, '')" if "descricao" in orc_cols else "''"))
                municipio_expr = "COALESCE(o.municipio, cli.municipio, ct.municipio, '')" if "municipio" in orc_cols else "COALESCE(cli.municipio, ct.municipio, '')"
                seg_join = "LEFT JOIN segmentos seg ON seg.id = o.segmento_id" if "segmento_id" in orc_cols else "LEFT JOIN segmentos seg ON 1=0"
                dados = c.execute(f"""
                    SELECT
                        o.id,
                        COALESCE(o.codigo, 'ORC-' || o.id) AS codigo,
                        COALESCE(cli.nome, '') AS cliente,
                        COALESCE(ct.nome, ct.numero, '') AS contrato,
                        COALESCE(seg.nome, '') AS segmento,
                        {objeto_expr} AS objeto,
                        COALESCE(o.status, 'EM ELABORAÇÃO') AS status,
                        COALESCE({data_expr}, '') AS atualizado,
                        {municipio_expr} AS municipio
                    FROM orcamentos o
                    LEFT JOIN clientes cli ON cli.id = o.cliente_id
                    LEFT JOIN contratos ct ON ct.id = o.contrato_id
                    {seg_join}
                    WHERE o.id=?
                """, (orc_id,)).fetchone()
            if not dados:
                return None
            d = dict(dados)
        except Exception:
            d = {}

        if row >= 0:
            def cell(col):
                item = self.tabela.item(row, col)
                return item.text() if item else ""
            d.setdefault("codigo", cell(1))
            d.setdefault("cliente", cell(2))
            d.setdefault("segmento", cell(3))
            d.setdefault("status", cell(4))
            d["total_capex"] = cell(5)
            d["total_opex"] = cell(6)
            d.setdefault("atualizado", cell(7))
        return d

    def ver_detalhes_orcamento(self):
        dados = self._dados_orcamento_selecionado()
        if not dados:
            QMessageBox.warning(self, "Detalhes", "Selecione um orçamento na lista.")
            return
        OrcamentoDetalheDialog(self, dados).exec()

    def abrir_orcamento(self):
        orc_id = self._obter_id_selecionado()
        if not orc_id:
            QMessageBox.warning(self, "Abrir orçamento", "Selecione um orçamento na tabela.")
            return

        if self.on_open_orcamento:
            self.on_open_orcamento(orc_id)
            return

        view_orcamentos = self._achar_view_orcamentos()
        navegou = self._navegar_para_orcamentos(view_orcamentos)
        carregou = self._carregar_orcamento_na_view(view_orcamentos, orc_id)

        if navegou or carregou:
            return

        QMessageBox.information(
            self,
            "Abrir orçamento",
            f"Orçamento selecionado: {orc_id}\n\n"
            "Não encontrei automaticamente a tela Orçamentos no main.py. "
            "Me envie o arquivo app/main.py para eu conectar 100% este botão.",
        )

    def novo_orcamento(self):
        if self.on_open_orcamento:
            self.on_open_orcamento(0)
        else:
            QMessageBox.information(self, "Novo orçamento", "Use a tela Orçamentos para criar um novo orçamento.")

    def duplicar_orcamento(self):
        orc_id = self._obter_id_selecionado()
        if not orc_id:
            QMessageBox.warning(self, "Duplicar orçamento", "Selecione um orçamento para duplicar.")
            return

        resp = QMessageBox.question(
            self,
            "Duplicar orçamento",
            "Deseja duplicar este orçamento com CAPEX, OPEX e cronograma?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if resp != QMessageBox.Yes:
            return

        try:
            novo_id = self._duplicar_orcamento_db(orc_id)
            QMessageBox.information(self, "Duplicar orçamento", f"Orçamento duplicado com sucesso.\nNovo ID: {novo_id}")
            self.carregar_tudo()
        except Exception as e:
            QMessageBox.critical(self, "Duplicar orçamento", f"Erro ao duplicar orçamento:\n{e}")

    def _duplicar_orcamento_db(self, orc_id: int) -> int:
        with conn() as c:
            old = c.execute("SELECT * FROM orcamentos WHERE id=?", (orc_id,)).fetchone()
            if not old:
                raise ValueError("Orçamento não encontrado.")

            cols = [r["name"] for r in c.execute("PRAGMA table_info(orcamentos)").fetchall()]
            insert_cols = [col for col in cols if col != "id"]

            valores = {}
            for col in insert_cols:
                valores[col] = old[col]

            if "codigo" in valores:
                valores["codigo"] = f"{old['codigo']}-CÓPIA-{datetime.now().strftime('%H%M%S')}" if old["codigo"] else None
            if "status" in valores:
                valores["status"] = "RASCUNHO"
            if "data_criacao" in valores:
                valores["data_criacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if "data_atualizacao" in valores:
                valores["data_atualizacao"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            placeholders = ",".join(["?"] * len(insert_cols))
            sql = f"INSERT INTO orcamentos({','.join(insert_cols)}) VALUES({placeholders})"
            cur = c.execute(sql, [valores[col] for col in insert_cols])
            novo_id = cur.lastrowid

            self._duplicar_filhos(c, "etapas_orcamento", orc_id, novo_id)
            self._duplicar_filhos(c, "itens", orc_id, novo_id)
            self._duplicar_filhos(c, "opex", orc_id, novo_id)
            self._duplicar_filhos(c, "cronograma", orc_id, novo_id)

            # As etapas recebem novos IDs na duplicação. Reaponta os itens
            # copiados para as etapas do novo orçamento.
            etapas_origem = c.execute(
                "SELECT id,nome,ordem FROM etapas_orcamento WHERE orcamento_id=?",
                (orc_id,),
            ).fetchall()
            etapas_novas = c.execute(
                "SELECT id,nome,ordem FROM etapas_orcamento WHERE orcamento_id=?",
                (novo_id,),
            ).fetchall()
            novas_por_chave = {
                (str(e["nome"] or "").strip(), int(e["ordem"] or 0)): e["id"]
                for e in etapas_novas
            }
            mapa_etapas = {
                e["id"]: novas_por_chave.get(
                    (str(e["nome"] or "").strip(), int(e["ordem"] or 0))
                )
                for e in etapas_origem
            }
            for etapa_antiga, etapa_nova in mapa_etapas.items():
                if etapa_nova:
                    c.execute(
                        "UPDATE itens SET etapa_id=?WHERE orcamento_id=?AND etapa_id=?",
                        (etapa_nova, novo_id, etapa_antiga),
                    )

            # Copia o cronograma vigente já usando os novos IDs de etapa.
            try:
                parcelas = c.execute(
                    "SELECT etapa_id,parcela,percentual,valor FROM cronograma_parcelas WHERE orcamento_id=?",
                    (orc_id,),
                ).fetchall()
                for parcela in parcelas:
                    etapa_nova = mapa_etapas.get(parcela["etapa_id"])
                    if etapa_nova:
                        c.execute(
                            """
                            INSERT INTO cronograma_parcelas(orcamento_id,etapa_id,parcela,percentual,valor)
                            VALUES(?,?,?,?,?)
                            """,
                            (
                                novo_id, etapa_nova, parcela["parcela"],
                                parcela["percentual"], parcela["valor"],
                            ),
                        )
            except Exception:
                pass

            c.commit()
            return int(novo_id)

    def _duplicar_filhos(self, c, tabela: str, orc_id: int, novo_id: int):
        try:
            cols_info = c.execute(f"PRAGMA table_info({tabela})").fetchall()
            if not cols_info:
                return

            cols = [r["name"] for r in cols_info]
            if "orcamento_id" not in cols:
                return

            rows = c.execute(f"SELECT * FROM {tabela} WHERE orcamento_id=?", (orc_id,)).fetchall()

            insert_cols = [col for col in cols if col != "id"]
            placeholders = ",".join(["?"] * len(insert_cols))

            for row in rows:
                valores = []
                for col in insert_cols:
                    valores.append(novo_id if col == "orcamento_id" else row[col])
                c.execute(f"INSERT INTO {tabela}({','.join(insert_cols)}) VALUES({placeholders})", valores)
        except Exception:
            # Se uma tabela não existir no banco do usuário, não bloqueia a duplicação do orçamento.
            return

    def alterar_status(self):
        orc_id = self._obter_id_selecionado()
        if not orc_id:
            QMessageBox.warning(self, "Alterar status", "Selecione um orçamento.")
            return

        status_atual = ""
        row = self.tabela.currentRow()
        if row >= 0 and self.tabela.item(row, 4):
            status_atual = self.tabela.item(row, 4).text()

        prox = {
            "RASCUNHO": "EM ELABORAÇÃO",
            "EM ELABORAÇÃO": "EM REVISÃO",
            "EM REVISÃO": "APROVADO",
            "APROVADO": "ENVIADO",
        }.get(status_atual.upper(), "EM ELABORAÇÃO")

        resp = QMessageBox.question(
            self,
            "Alterar status",
            f"Alterar status para: {prox}?",
            QMessageBox.Yes | QMessageBox.No,
        )

        if resp != QMessageBox.Yes:
            return

        try:
            with conn() as c:
                cols = self._colunas("orcamentos")
                if "data_atualizacao" in cols:
                    c.execute("UPDATE orcamentos SET status=?, data_atualizacao=datetime('now') WHERE id=?", (prox, orc_id))
                else:
                    c.execute("UPDATE orcamentos SET status=?WHERE id=?", (prox, orc_id))
                c.commit()
            self.carregar_tudo()
        except Exception as e:
            QMessageBox.critical(self, "Alterar status", str(e))

    def gerar_pacote(self):
        orc_id = self._obter_id_selecionado()
        if not orc_id:
            QMessageBox.warning(self, "Gerar pacote", "Selecione um orçamento.")
            return

        try:
            from services.documentos_service import gerar_pacote_revisao

            arquivos = gerar_pacote_revisao(orc_id)
            QMessageBox.information(self, "Gerar pacote", "Arquivos gerados:\n" + "\n".join(str(a) for a in arquivos))
        except Exception as e:
            QMessageBox.critical(self, "Gerar pacote", f"Erro ao gerar pacote:\n{e}")

    def arquivar_orcamento(self):
        orc_id = self._obter_id_selecionado()
        if not orc_id:
            QMessageBox.warning(self, "Arquivar", "Selecione um orçamento.")
            return

        resp = QMessageBox.question(
            self,
            "Arquivar orçamento",
            "Arquivar este orçamento? Ele será marcado como CANCELADO/ARQUIVADO.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if resp != QMessageBox.Yes:
            return

        try:
            with conn() as c:
                c.execute("UPDATE orcamentos SET status=?WHERE id=?", ("CANCELADO", orc_id))
                c.commit()
            self.carregar_tudo()
        except Exception as e:
            QMessageBox.critical(self, "Arquivar", str(e))

    def excluir_orcamento(self):
        orc_id = self._obter_id_selecionado()
        if not orc_id:
            QMessageBox.warning(self, "Excluir", "Selecione um orçamento.")
            return

        resp = QMessageBox.question(
            self,
            "Excluir orçamento",
            "Excluir definitivamente este orçamento e seus dados vinculados?\n\nAção irreversível.",
            QMessageBox.Yes | QMessageBox.No,
        )

        if resp != QMessageBox.Yes:
            return

        try:
            with conn() as c:
                # Se o orçamento nasceu de uma OS, a exclusão deve liberar a
                # OS para que ela possa ser transformada novamente.
                ordens_liberadas = c.execute(
                    """
                    SELECT id FROM ordens_servico
                    WHERE importada_orcamento_id=?
                       OR id=(SELECT ordem_servico_id FROM orcamentos WHERE id=?)
                    """,
                    (orc_id, orc_id),
                ).fetchall()
                c.execute(
                    """
                    UPDATE ordens_servico
                    SET importada_orcamento_id=NULL,
                        travada=0,
                        status=CASE
                            WHEN COALESCE(aprovada_inicio,0)=1 THEN 'APROVADA_INICIO'
                            ELSE 'AGUARDANDO_APROVACAO'
                        END,
                        data_atualizacao=datetime('now')
                    WHERE importada_orcamento_id=?
                       OR id=(SELECT ordem_servico_id FROM orcamentos WHERE id=?)
                    """,
                    (orc_id, orc_id),
                )
                c.execute(
                    "UPDATE ordens_servico SET orcamento_id=NULL WHERE orcamento_id=?",
                    (orc_id,),
                )
                for tabela in ["cronograma", "opex", "itens", "etapas_orcamento", "documentos", "anexos"]:
                    try:
                        c.execute(f"DELETE FROM {tabela} WHERE orcamento_id=?", (orc_id,))
                    except Exception:
                        pass
                c.execute("DELETE FROM orcamentos WHERE id=?", (orc_id,))
                c.commit()
            self.orcamento_id_selecionado = None
            self.carregar_tudo()
            if ordens_liberadas:
                QMessageBox.information(
                    self,
                    "Orçamento excluído",
                    "O orçamento foi excluído e a OS vinculada foi liberada para uma nova transformação.",
                )
        except Exception as e:
            QMessageBox.critical(self, "Excluir", str(e))
