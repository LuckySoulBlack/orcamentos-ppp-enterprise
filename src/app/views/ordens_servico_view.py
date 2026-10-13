from pathlib import Path
import os
import shutil
import webbrowser

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import *

from core.database import conn
from core.ui_helpers import mensagem_operacional, aplicar_botoes_semanticos
from services import auth_service
from services import ordem_servico_service as os_service
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar
from views.os_acompanhamento_view import KanbanExecucoesView


class OsSelectorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Abrir Ordem de Serviço")
        self.resize(980, 620)
        self.ordem_id = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        filtro = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar por número, cliente, objeto, executor ou status")
        self.btn_atualizar = QPushButton("Atualizar")
        self.btn_abrir = QPushButton("Abrir OS selecionada")
        self.btn_abrir.setMinimumHeight(38)
        self.btn_atualizar.setMinimumHeight(38)
        filtro.addWidget(self.busca, 1)
        filtro.addWidget(self.btn_atualizar)
        filtro.addWidget(self.btn_abrir)
        layout.addLayout(filtro)

        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(["ID", "OS", "Status", "Cliente", "Resumo"])
        configurar_tabela_responsiva(self.tabela, stretch_columns=[4], hidden_columns=[0])
        self.tabela.setMinimumHeight(470)
        layout.addWidget(self.tabela, 1)

        self.busca.textChanged.connect(self.carregar)
        self.btn_atualizar.clicked.connect(self.carregar)
        self.btn_abrir.clicked.connect(self.abrir)
        self.tabela.cellDoubleClicked.connect(lambda *_: self.abrir())
        self.carregar()

    def carregar(self):
        termo = self.busca.text().strip().lower()
        rows = []
        for r in os_service.listar_ordens():
            texto = " ".join(str(r[k] or "") for k in ["numero", "status", "cliente_nome", "objeto", "executor", "importado_codigo"]).lower()
            if termo and termo not in texto:
                continue
            resumo = r["objeto"] or r["executor"] or r["importado_codigo"] or ""
            rows.append([r["id"], r["numero"], r["status"], r["cliente_nome"] or "Cliente não informado", resumo])
        self.tabela.setRowCount(0)
        for row_idx, row in enumerate(rows):
            self.tabela.insertRow(row_idx)
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                if col_idx == 0:
                    item.setData(Qt.UserRole, value)
                self.tabela.setItem(row_idx, col_idx, item)
        ajustar_tabela_apos_carregar(self.tabela)

    def abrir(self):
        row = self.tabela.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Abrir OS", "Selecione uma Ordem de Serviço.")
            return
        self.ordem_id = self.tabela.item(row, 0).data(Qt.UserRole)
        self.accept()


class SinapiOsSearchDialog(QDialog):
    def __init__(self, parent=None, termo_inicial=""):
        super().__init__(parent)
        self.setWindowTitle("Buscar item SINAPI")
        self.resize(980, 620)
        self.item_selecionado = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        busca = QHBoxLayout()
        self.termo = QLineEdit()
        self.termo.setPlaceholderText("Código ou descrição do item SINAPI")
        self.termo.setText(termo_inicial or "")
        self.btn_pesquisar = QPushButton("Pesquisar")
        self.btn_usar = QPushButton("Usar item")
        busca.addWidget(self.termo, 1)
        busca.addWidget(self.btn_pesquisar)
        busca.addWidget(self.btn_usar)
        layout.addLayout(busca)

        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(["Código", "Descrição", "Unidade", "Fonte"])
        configurar_tabela_responsiva(self.tabela, stretch_columns=[1])
        layout.addWidget(self.tabela, 1)

        self.btn_pesquisar.clicked.connect(self.pesquisar)
        self.btn_usar.clicked.connect(self.usar)
        self.termo.returnPressed.connect(self.pesquisar)
        self.tabela.cellDoubleClicked.connect(lambda *_: self.usar())
        if self.termo.text().strip():
            self.pesquisar()

    def pesquisar(self):
        termo = self.termo.text().strip()
        if len(termo) < 2:
            QMessageBox.warning(self, "SINAPI", "Digite pelo menos 2 caracteres.")
            return
        palavras = [p for p in termo.replace("-", " ").split() if p]
        params = [f"%{termo}%"]
        where = ["codigo LIKE ?"]
        if palavras:
            partes = []
            for p in palavras:
                partes.append("UPPER(descricao) LIKE UPPER(?)")
                params.append(f"%{p}%")
            where.append("(" + " AND ".join(partes) + ")")
        params.extend([termo, f"{termo}%", f"%{termo}%"])
        with conn() as c:
            rows = c.execute(
                f"""
                SELECT codigo, descricao, unidade, fonte
                FROM sinapi
                WHERE {' OR '.join(where)}
                ORDER BY CASE
                    WHEN codigo=? THEN 0
                    WHEN codigo LIKE ? THEN 1
                    WHEN UPPER(descricao) LIKE UPPER(?) THEN 2
                    ELSE 3
                END, descricao
                LIMIT 250
                """,
                params,
            ).fetchall()
        self.tabela.setRowCount(0)
        for row_idx, row in enumerate(rows):
            self.tabela.insertRow(row_idx)
            values = [row["codigo"], row["descricao"], row["unidade"], row["fonte"]]
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem("" if value is None else str(value))
                item.setData(Qt.UserRole, dict(row))
                self.tabela.setItem(row_idx, col_idx, item)
        ajustar_tabela_apos_carregar(self.tabela)
        if not rows:
            QMessageBox.information(self, "SINAPI", "Nenhum item encontrado.")

    def usar(self):
        row = self.tabela.currentRow()
        if row < 0:
            QMessageBox.warning(self, "SINAPI", "Selecione um item.")
            return
        self.item_selecionado = self.tabela.item(row, 0).data(Qt.UserRole)
        self.accept()


class OrdensServicoView(QWidget):
    def __init__(self, abrir_orcamento_callback=None, modo="admin", usuario_atual=None):
        super().__init__()
        self.abrir_orcamento_callback = abrir_orcamento_callback
        self.modo = modo
        self.usuario_atual = usuario_atual or {"nome": "Admin/Gestor", "perfil": "ADMIN"}
        self.is_admin = str(self.modo).lower() == "admin"
        permissoes = set(auth_service.permissoes_usuario(self.usuario_atual))
        self.pode_ver_kanban = self.is_admin or "*" in permissoes or "os_kanban" in permissoes
        self.ordem_id = None
        self.selected_etapa_id = None
        self.selected_item_id = None
        self.selected_foto_id = None
        self.selected_anexo_id = None
        self.setObjectName("OrdensServicoView")

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        topo = QGridLayout()
        topo.setHorizontalSpacing(10)
        topo.setVerticalSpacing(8)
        titulos = QVBoxLayout()
        titulo = QLabel("Ordens de Serviço")
        titulo.setStyleSheet("font-size:26px;font-weight:950;color:#071A33;")
        subtitulo = QLabel("Crie OS, aprove o início, registre etapas, itens, fotos, anexos e gere o relatório pós-obra.")
        subtitulo.setWordWrap(True)
        subtitulo.setStyleSheet("color:#64748B;font-weight:700;")
        titulos.addWidget(titulo)
        titulos.addWidget(subtitulo)
        topo.addLayout(titulos, 0, 0, 2, 1)
        self.btn_abrir_os = QPushButton("Abrir OS")
        self.btn_nova = QPushButton("Nova OS")
        self.btn_editar_os = QPushButton("Editar OS")
        self.btn_salvar = QPushButton("Salvar OS")
        self.btn_excluir_os = QPushButton("Excluir OS")
        self.btn_destravar_os = QPushButton("Destravar OS")
        self.btn_aprovar = QPushButton("Aprovar início")
        self.btn_importar = QPushButton("Transformar em orçamento")
        self.btn_link_executor = QPushButton("Link do executor")
        self.btn_gerar = QPushButton("Gerar PDF / Word / Excel")
        botoes_topo = [self.btn_abrir_os, self.btn_nova, self.btn_editar_os, self.btn_salvar, self.btn_excluir_os, self.btn_destravar_os, self.btn_aprovar, self.btn_importar, self.btn_link_executor, self.btn_gerar]
        for btn in botoes_topo:
            btn.setMinimumHeight(38)
            btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        topo.addWidget(self.btn_abrir_os, 0, 1)
        topo.addWidget(self.btn_nova, 0, 2)
        topo.addWidget(self.btn_editar_os, 0, 3)
        topo.addWidget(self.btn_salvar, 0, 4)
        topo.addWidget(self.btn_excluir_os, 0, 5)
        topo.addWidget(self.btn_aprovar, 1, 1)
        topo.addWidget(self.btn_importar, 1, 2)
        topo.addWidget(self.btn_link_executor, 1, 3)
        topo.addWidget(self.btn_gerar, 1, 4)
        topo.addWidget(self.btn_destravar_os, 1, 5)
        topo.setColumnStretch(0, 1)
        root.addLayout(topo)

        self.btn_aprovar.setVisible(self.is_admin)
        self.btn_importar.setVisible(self.is_admin)
        self.btn_destravar_os.setVisible(self.is_admin)

        self.btn_abrir_os.clicked.connect(self.abrir_seletor_os)
        self.btn_nova.clicked.connect(self.nova_os)
        self.btn_editar_os.clicked.connect(self.editar_dados_os)
        self.btn_salvar.clicked.connect(self.salvar_os)
        self.btn_excluir_os.clicked.connect(self.excluir_os)
        self.btn_destravar_os.clicked.connect(self.destravar_os)
        self.btn_aprovar.clicked.connect(self.aprovar_inicio)
        self.btn_importar.clicked.connect(self.importar_orcamento)
        self.btn_link_executor.clicked.connect(self.gerar_link_executor)
        self.btn_gerar.clicked.connect(self.gerar_documentos)

        main = QSplitter(Qt.Horizontal)
        main.setChildrenCollapsible(False)
        main.setHandleWidth(8)
        root.addWidget(main, 1)

        esquerda = QWidget()
        esquerda.setMinimumWidth(340)
        esquerda.setMaximumWidth(520)
        left = QVBoxLayout(esquerda)
        left.setContentsMargins(0, 0, 8, 0)
        filtro = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar OS, cliente, objeto ou status")
        self.btn_atualizar = QPushButton("Atualizar")
        filtro.addWidget(self.busca, 1)
        filtro.addWidget(self.btn_atualizar)
        left.addLayout(filtro)
        self.tabela_os = QTableWidget(0, 4)
        self.tabela_os.setHorizontalHeaderLabels(["ID", "OS", "Status", "Resumo"])
        configurar_tabela_responsiva(self.tabela_os, stretch_columns=[3], hidden_columns=[0])
        self.tabela_os.setColumnWidth(1, 105)
        self.tabela_os.setColumnWidth(2, 118)
        self.tabela_os.setWordWrap(True)
        left.addWidget(self.tabela_os, 1)
        main.addWidget(esquerda)
        esquerda.setVisible(False)
        esquerda.setMinimumWidth(0)
        esquerda.setMaximumWidth(0)

        self.busca.textChanged.connect(self.carregar_ordens)
        self.btn_atualizar.clicked.connect(self.carregar_ordens)
        self.tabela_os.cellClicked.connect(lambda *_: self.abrir_os_selecionada())
        self.tabela_os.cellDoubleClicked.connect(lambda *_: self.abrir_os_selecionada())

        direita = QWidget()
        direita.setMinimumWidth(760)
        right = QVBoxLayout(direita)
        right.setContentsMargins(8, 0, 0, 0)
        self.status_label = QLabel("OS não selecionada")
        self.status_label.setStyleSheet("color:#0B3B75;font-weight:900;")
        right.addWidget(self.status_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._aba_dados(), "Dados")
        self.tabs.addTab(self._aba_etapas_itens(), "Etapas e itens")
        self.tabs.addTab(self._aba_fotos(), "Fotos")
        self.tabs.addTab(self._aba_anexos(), "Anexos")
        self.tabs.addTab(self._aba_geracao(), "Geração")
        self.kanban_view = None
        if self.pode_ver_kanban:
            self.kanban_view = KanbanExecucoesView(
                abrir_os_callback=self.abrir_os_por_id,
                abrir_orcamento_callback=self.abrir_orcamento_callback,
            )
            self.tabs.addTab(self.kanban_view, "Kanban de obras")
        right.addWidget(self.tabs, 1)
        main.addWidget(direita)
        main.setStretchFactor(0, 0)
        main.setStretchFactor(1, 1)
        main.setSizes([0, 1680])

        self.carregar_combos()
        self.carregar_ordens()
        self.nova_os()
        aplicar_botoes_semanticos(self)

    def refresh(self):
        self.carregar_ordens()
        if self.kanban_view and hasattr(self.kanban_view, "refresh"):
            self.kanban_view.refresh()
        aplicar_botoes_semanticos(self)

    def _line(self, placeholder=""):
        w = QLineEdit()
        w.setMinimumHeight(34)
        w.setPlaceholderText(placeholder)
        return w

    def _date(self):
        w = QDateEdit()
        w.setCalendarPopup(True)
        w.setDisplayFormat("yyyy-MM-dd")
        w.setDate(QDate.currentDate())
        w.setMinimumHeight(34)
        return w

    def _scrollable(self, widget):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(widget)
        return area

    def _aba_dados(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        box = QGroupBox("Cabeçalho da OS")
        form = QGridLayout(box)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self.numero = self._line()
        self.status = QComboBox()
        self.status.addItems(os_service.STATUS_OS)
        self.cliente = QComboBox()
        self.contrato = QComboBox()
        self.segmento = QComboBox()
        self.orcamento_origem = QComboBox()
        self.objeto = self._line("Objeto resumido da OS")
        self.local_execucao = self._line("Endereço, bairro, ponto ou referência")
        self.municipio = self._line()
        self.latitude = self._line("Latitude")
        self.longitude = self._line("Longitude")
        self.solicitante = self._line()
        self.executor = self._line()
        self.responsavel_tecnico = self._line()
        self.fiscal_cliente = self._line()
        self.gestor = self._line()
        self.data_emissao = self._date()
        self.data_inicio = self._date()
        self.data_fim = self._date()
        self.observacao = QTextEdit()
        self.observacao.setMinimumHeight(80)

        campos = [
            ("Número", self.numero), ("Status", self.status),
            ("Cliente", self.cliente), ("Contrato", self.contrato),
            ("Segmento", self.segmento), ("Orçamento origem", self.orcamento_origem),
            ("Objeto", self.objeto), ("Local execução", self.local_execucao),
            ("Município", self.municipio), ("Latitude", self.latitude),
            ("Longitude", self.longitude), ("Solicitante", self.solicitante),
            ("Executor", self.executor), ("Responsável técnico", self.responsavel_tecnico),
            ("Fiscal/cliente", self.fiscal_cliente), ("Gestor", self.gestor),
            ("Emissão", self.data_emissao), ("Início previsto", self.data_inicio),
            ("Fim previsto", self.data_fim),
        ]
        for idx, (label, widget) in enumerate(campos):
            row = idx // 2
            col = (idx % 2) * 2
            form.addWidget(QLabel(label), row, col)
            form.addWidget(widget, row, col + 1)
        row = (len(campos) + 1) // 2
        form.addWidget(QLabel("Observação"), row, 0)
        form.addWidget(self.observacao, row, 1, 1, 3)
        resumo_box = QGroupBox("Resumo da OS")
        resumo_layout = QVBoxLayout(resumo_box)
        self.resumo_dados_os = QLabel("Nenhuma OS carregada.")
        self.resumo_dados_os.setWordWrap(True)
        self.resumo_dados_os.setStyleSheet("color:#334155;font-size:14px;font-weight:700;")
        self.btn_editar_dados_aba = QPushButton("Editar dados da OS")
        self.btn_editar_dados_aba.setMinimumHeight(40)
        self.btn_editar_dados_aba.clicked.connect(self.editar_dados_os)
        resumo_layout.addWidget(self.resumo_dados_os)
        resumo_layout.addWidget(self.btn_editar_dados_aba)
        layout.addWidget(resumo_box)
        box.setVisible(False)
        layout.addWidget(box)
        layout.addStretch()
        return self._scrollable(w)

    def _aba_etapas_itens(self):
        w = QWidget()
        layout = QVBoxLayout(w)

        box_etapa = QGroupBox("Etapas da execução")
        etapa_lay = QVBoxLayout(box_etapa)
        grid = QGridLayout()
        self.etapa_nome = self._line("Nome da etapa")
        self.etapa_status = QComboBox()
        self.etapa_status.addItems(os_service.STATUS_ETAPA)
        self.etapa_percentual = QDoubleSpinBox()
        self.etapa_percentual.setRange(0, 100)
        self.etapa_percentual.setSuffix(" %")
        self.etapa_desc = QTextEdit()
        self.etapa_desc.setMinimumHeight(58)
        self.etapa_obs = QTextEdit()
        self.etapa_obs.setMinimumHeight(58)
        self.btn_etapa_salvar = QPushButton("Adicionar / atualizar etapa")
        self.btn_etapa_limpar = QPushButton("Limpar etapa")
        self.btn_etapa_excluir = QPushButton("Excluir etapa")
        grid.addWidget(QLabel("Nome"), 0, 0)
        grid.addWidget(self.etapa_nome, 1, 0)
        grid.addWidget(QLabel("Status"), 0, 1)
        grid.addWidget(self.etapa_status, 1, 1)
        grid.addWidget(QLabel("Execução"), 0, 2)
        grid.addWidget(self.etapa_percentual, 1, 2)
        grid.addWidget(QLabel("Descrição"), 2, 0)
        grid.addWidget(QLabel("Observação"), 2, 1)
        grid.addWidget(self.etapa_desc, 3, 0)
        grid.addWidget(self.etapa_obs, 3, 1, 1, 2)
        botoes = QHBoxLayout()
        botoes.addWidget(self.btn_etapa_salvar, 2)
        botoes.addWidget(self.btn_etapa_limpar)
        botoes.addWidget(self.btn_etapa_excluir)
        etapa_acoes = QHBoxLayout()
        self.btn_etapa_nova_popup = QPushButton("Nova etapa")
        self.btn_etapa_editar_popup = QPushButton("Editar etapa selecionada")
        self.btn_etapa_excluir_popup = QPushButton("Excluir etapa")
        for btn in [self.btn_etapa_nova_popup, self.btn_etapa_editar_popup, self.btn_etapa_excluir_popup]:
            btn.setMinimumHeight(38)
        etapa_acoes.addWidget(self.btn_etapa_nova_popup)
        etapa_acoes.addWidget(self.btn_etapa_editar_popup)
        etapa_acoes.addWidget(self.btn_etapa_excluir_popup)
        etapa_acoes.addStretch(1)
        etapa_lay.addLayout(etapa_acoes)
        self.tabela_etapas = QTableWidget(0, 6)
        self.tabela_etapas.setHorizontalHeaderLabels(["ID", "Ordem", "Etapa", "Status", "%", "Observação"])
        configurar_tabela_responsiva(self.tabela_etapas, stretch_columns=[2, 5], hidden_columns=[0])
        self.tabela_etapas.setEditTriggers(QAbstractItemView.NoEditTriggers)
        etapa_lay.addWidget(self.tabela_etapas)
        layout.addWidget(box_etapa, 1)

        box_item = QGroupBox("Itens por etapa")
        item_lay = QVBoxLayout(box_item)
        grid_item = QGridLayout()
        self.item_etapa = QComboBox()
        self.item_desc = QTextEdit()
        self.item_desc.setMinimumHeight(60)
        self.item_unidade = self._line("UN")
        self.item_qtd_prev = QDoubleSpinBox()
        self.item_qtd_prev.setRange(0, 999999999)
        self.item_qtd_prev.setDecimals(4)
        self.item_qtd_exec = QDoubleSpinBox()
        self.item_qtd_exec.setRange(0, 999999999)
        self.item_qtd_exec.setDecimals(4)
        self.item_fonte = self._line("OS / Terceiro / SINAPI")
        self.item_codigo = self._line()
        self.item_importar = QCheckBox("Importar para orçamento")
        self.item_importar.setChecked(True)
        self.item_obs = self._line()
        self.btn_item_salvar = QPushButton("Adicionar / atualizar item")
        self.btn_item_limpar = QPushButton("Limpar item")
        self.btn_item_excluir = QPushButton("Excluir item")
        labels_widgets = [
            ("Etapa", self.item_etapa), ("Un.", self.item_unidade),
            ("Qtd prevista", self.item_qtd_prev), ("Qtd executada", self.item_qtd_exec),
            ("Fonte", self.item_fonte), ("Código", self.item_codigo),
        ]
        for idx, (label, widget) in enumerate(labels_widgets):
            grid_item.addWidget(QLabel(label), 0, idx)
            grid_item.addWidget(widget, 1, idx)
        grid_item.addWidget(QLabel("Descrição"), 2, 0, 1, 3)
        grid_item.addWidget(QLabel("Observação"), 2, 3, 1, 3)
        grid_item.addWidget(self.item_desc, 3, 0, 1, 3)
        grid_item.addWidget(self.item_obs, 3, 3, 1, 3)
        grid_item.addWidget(self.item_importar, 4, 0)
        item_acoes = QHBoxLayout()
        self.btn_item_novo_popup = QPushButton("Novo item da etapa")
        self.btn_item_editar_popup = QPushButton("Editar item selecionado")
        self.btn_item_excluir_popup = QPushButton("Excluir item")
        self.btn_item_sinapi_popup = QPushButton("Buscar SINAPI")
        for btn in [self.btn_item_novo_popup, self.btn_item_editar_popup, self.btn_item_excluir_popup, self.btn_item_sinapi_popup]:
            btn.setMinimumHeight(38)
        item_acoes.addWidget(self.btn_item_novo_popup)
        item_acoes.addWidget(self.btn_item_editar_popup)
        item_acoes.addWidget(self.btn_item_excluir_popup)
        item_acoes.addWidget(self.btn_item_sinapi_popup)
        item_acoes.addStretch(1)
        item_lay.addLayout(item_acoes)
        botoes_item = QHBoxLayout()
        botoes_item.addWidget(self.btn_item_salvar, 2)
        botoes_item.addWidget(self.btn_item_limpar)
        botoes_item.addWidget(self.btn_item_excluir)
        item_lay.addLayout(botoes_item)
        self.tabela_itens = QTableWidget(0, 8)
        self.tabela_itens.setHorizontalHeaderLabels(["ID", "Etapa", "Descrição", "Un.", "Prev.", "Exec.", "Fonte", "Importa"])
        configurar_tabela_responsiva(self.tabela_itens, stretch_columns=[2], hidden_columns=[0])
        self.tabela_itens.setEditTriggers(QAbstractItemView.NoEditTriggers)
        item_lay.addWidget(self.tabela_itens)
        layout.addWidget(box_item, 1)

        self.btn_etapa_salvar.clicked.connect(self.salvar_etapa)
        self.btn_etapa_limpar.clicked.connect(self.limpar_etapa)
        self.btn_etapa_excluir.clicked.connect(self.excluir_etapa)
        self.btn_etapa_nova_popup.clicked.connect(lambda: self.abrir_dialog_etapa(False))
        self.btn_etapa_editar_popup.clicked.connect(lambda: self.abrir_dialog_etapa(True))
        self.btn_etapa_excluir_popup.clicked.connect(self.excluir_etapa)
        self.tabela_etapas.cellClicked.connect(self.selecionar_etapa)
        self.btn_item_salvar.clicked.connect(self.salvar_item)
        self.btn_item_limpar.clicked.connect(self.limpar_item)
        self.btn_item_excluir.clicked.connect(self.excluir_item)
        self.btn_item_novo_popup.clicked.connect(lambda: self.abrir_dialog_item(False))
        self.btn_item_editar_popup.clicked.connect(lambda: self.abrir_dialog_item(True))
        self.btn_item_excluir_popup.clicked.connect(self.excluir_item)
        self.btn_item_sinapi_popup.clicked.connect(lambda: self.abrir_dialog_item(False, "SINAPI"))
        self.tabela_itens.cellClicked.connect(self.selecionar_item)
        return self._scrollable(w)

    def _aba_fotos(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        box = QGroupBox("Fotos da execução")
        lay = QGridLayout(box)
        self.foto_etapa = QComboBox()
        self.foto_categoria = QComboBox()
        self.foto_categoria.addItems(os_service.FOTO_CATEGORIAS)
        self.foto_caminho = self._line("Selecione uma foto")
        self.foto_caminho.setReadOnly(True)
        self.foto_legenda = self._line("Legenda que aparecerá no relatório")
        self.foto_obs = self._line()
        self.btn_foto_sel = QPushButton("Selecionar foto")
        self.btn_foto_add = QPushButton("Adicionar foto")
        self.btn_foto_del = QPushButton("Excluir foto")
        self.btn_importar_pacote_executor = QPushButton("Importar pacote do executor")
        lay.addWidget(QLabel("Etapa"), 0, 0)
        lay.addWidget(QLabel("Categoria"), 0, 1)
        lay.addWidget(QLabel("Arquivo"), 0, 2)
        lay.addWidget(self.foto_etapa, 1, 0)
        lay.addWidget(self.foto_categoria, 1, 1)
        lay.addWidget(self.foto_caminho, 1, 2)
        lay.addWidget(self.btn_foto_sel, 1, 3)
        lay.addWidget(QLabel("Legenda"), 2, 0)
        lay.addWidget(self.foto_legenda, 3, 0, 1, 2)
        lay.addWidget(QLabel("Observação"), 2, 2)
        lay.addWidget(self.foto_obs, 3, 2, 1, 2)
        lay.addWidget(self.btn_foto_add, 4, 0)
        lay.addWidget(self.btn_foto_del, 4, 1)
        lay.addWidget(self.btn_importar_pacote_executor, 4, 2, 1, 2)
        layout.addWidget(box)
        self.tabela_fotos = QTableWidget(0, 7)
        self.tabela_fotos.setHorizontalHeaderLabels(["ID", "Etapa", "Categoria", "Arquivo", "Legenda", "Data", "Caminho"])
        configurar_tabela_responsiva(self.tabela_fotos, stretch_columns=[3, 4, 6], hidden_columns=[0])
        self.tabela_fotos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tabela_fotos, 1)
        self.btn_foto_sel.clicked.connect(self.selecionar_foto_arquivo)
        self.btn_foto_add.clicked.connect(self.adicionar_foto)
        self.btn_foto_del.clicked.connect(self.excluir_foto)
        self.btn_importar_pacote_executor.clicked.connect(self.importar_pacote_executor)
        self.tabela_fotos.cellClicked.connect(self.selecionar_foto)
        return self._scrollable(w)

    def _aba_anexos(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        box = QGroupBox("Anexos preservados na OS")
        lay = QGridLayout(box)
        self.anexo_etapa = QComboBox()
        self.anexo_tipo = QComboBox()
        self.anexo_tipo.addItems(["Orçamento de terceiro", "Proposta fornecedor", "Documento de aceite", "ART/RRT", "Nota/medição", "Outro"])
        self.anexo_caminho = self._line("Selecione um arquivo")
        self.anexo_caminho.setReadOnly(True)
        self.anexo_obs = self._line()
        self.anexo_importar = QCheckBox("Copiar para orçamento ao importar")
        self.anexo_importar.setChecked(True)
        self.btn_anexo_sel = QPushButton("Selecionar")
        self.btn_anexo_add = QPushButton("Adicionar anexo")
        self.btn_anexo_del = QPushButton("Excluir anexo")
        self.btn_anexo_abrir = QPushButton("Abrir anexo")
        self.btn_anexo_baixar = QPushButton("Baixar cópia")
        lay.addWidget(QLabel("Etapa"), 0, 0)
        lay.addWidget(QLabel("Tipo"), 0, 1)
        lay.addWidget(QLabel("Arquivo"), 0, 2)
        lay.addWidget(self.anexo_etapa, 1, 0)
        lay.addWidget(self.anexo_tipo, 1, 1)
        lay.addWidget(self.anexo_caminho, 1, 2)
        lay.addWidget(self.btn_anexo_sel, 1, 3)
        lay.addWidget(QLabel("Observação"), 2, 0, 1, 4)
        lay.addWidget(self.anexo_obs, 3, 0, 1, 3)
        lay.addWidget(self.anexo_importar, 3, 3)
        lay.addWidget(self.btn_anexo_add, 4, 0)
        lay.addWidget(self.btn_anexo_abrir, 4, 1)
        lay.addWidget(self.btn_anexo_baixar, 4, 2)
        lay.addWidget(self.btn_anexo_del, 4, 3)
        layout.addWidget(box)
        self.tabela_anexos = QTableWidget(0, 7)
        self.tabela_anexos.setHorizontalHeaderLabels(["ID", "Etapa", "Tipo", "Arquivo", "Importa", "Data", "Caminho"])
        configurar_tabela_responsiva(self.tabela_anexos, stretch_columns=[3, 6], hidden_columns=[0])
        self.tabela_anexos.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tabela_anexos, 1)
        self.btn_anexo_sel.clicked.connect(self.selecionar_anexo_arquivo)
        self.btn_anexo_add.clicked.connect(self.adicionar_anexo)
        self.btn_anexo_del.clicked.connect(self.excluir_anexo)
        self.btn_anexo_abrir.clicked.connect(self.abrir_anexo)
        self.btn_anexo_baixar.clicked.connect(self.baixar_anexo)
        self.tabela_anexos.cellClicked.connect(self.selecionar_anexo)
        return self._scrollable(w)

    def _aba_geracao(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        box = QGroupBox("Importação e documentos")
        lay = QGridLayout(box)
        self.orcamento_destino = QComboBox()
        self.orcamento_destino.addItem("Criar novo orçamento", None)
        self.btn_importar_aba = QPushButton("Transformar OS em orçamento")
        self.btn_pasta = QPushButton("Abrir pasta da OS")
        self.btn_pdf = QPushButton("Gerar relatório PDF")
        self.btn_word = QPushButton("Gerar relatório Word")
        self.btn_excel = QPushButton("Gerar planilha Excel")
        self.info_geracao = QLabel("A importação copia anexos e fotos para o orçamento, mas mantém os originais preservados na OS.")
        self.info_geracao.setWordWrap(True)
        self.info_geracao.setStyleSheet("color:#64748B;font-weight:700;")
        lay.addWidget(self.info_geracao, 0, 0, 1, 3)
        self.lbl_orcamento_destino = QLabel("Orçamento destino")
        lay.addWidget(self.lbl_orcamento_destino, 1, 0)
        lay.addWidget(self.orcamento_destino, 1, 1, 1, 2)
        lay.addWidget(self.btn_importar_aba, 2, 0)
        lay.addWidget(self.btn_pasta, 2, 1)
        lay.addWidget(self.btn_pdf, 3, 0)
        lay.addWidget(self.btn_word, 3, 1)
        lay.addWidget(self.btn_excel, 3, 2)
        layout.addWidget(box)
        layout.addStretch()
        self.btn_importar_aba.clicked.connect(self.importar_orcamento)
        self.btn_pasta.clicked.connect(self.abrir_pasta_os)
        self.btn_pdf.clicked.connect(lambda: self._gerar_um(os_service.gerar_pdf_relatorio))
        self.btn_word.clicked.connect(lambda: self._gerar_um(os_service.gerar_word_relatorio))
        self.btn_excel.clicked.connect(lambda: self._gerar_um(os_service.gerar_excel_medicao))
        self.orcamento_destino.setVisible(self.is_admin)
        self.lbl_orcamento_destino.setVisible(self.is_admin)
        self.btn_importar_aba.setVisible(self.is_admin)
        if not self.is_admin:
            self.info_geracao.setText("Gere os documentos da execução. Aprovação e transformação em orçamento são feitas no app Admin.")
        return self._scrollable(w)

    def _aba_autorizacoes(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        box = QGroupBox("Usuários autorizados no app de execução")
        form = QGridLayout(box)
        self.user_nome = self._line("Nome do usuário")
        self.user_login = self._line("Login")
        self.user_email = self._line("E-mail de login")
        self.user_senha = self._line("Senha")
        self.user_perfil = QComboBox()
        self.user_perfil.addItems(["OPERACIONAL", "GESTOR", "ADMIN"])
        self.user_ativo = QCheckBox("Ativo")
        self.user_ativo.setChecked(True)
        self.btn_user_salvar = QPushButton("Salvar autorização")
        self.btn_user_limpar = QPushButton("Limpar")
        self.btn_user_excluir = QPushButton("Excluir")
        form.addWidget(QLabel("Nome"), 0, 0)
        form.addWidget(self.user_nome, 1, 0)
        form.addWidget(QLabel("Usuário"), 0, 1)
        form.addWidget(self.user_login, 1, 1)
        form.addWidget(QLabel("E-mail de login"), 0, 2)
        form.addWidget(self.user_email, 1, 2)
        form.addWidget(QLabel("Senha"), 0, 3)
        form.addWidget(self.user_senha, 1, 3)
        form.addWidget(QLabel("Perfil"), 0, 4)
        form.addWidget(self.user_perfil, 1, 4)
        form.addWidget(self.user_ativo, 1, 5)
        form.addWidget(self.btn_user_salvar, 2, 0, 1, 2)
        form.addWidget(self.btn_user_limpar, 2, 2)
        form.addWidget(self.btn_user_excluir, 2, 3, 1, 3)
        layout.addWidget(box)
        self.tabela_usuarios = QTableWidget(0, 7)
        self.tabela_usuarios.setHorizontalHeaderLabels(["ID", "Nome", "Usuário", "E-mail", "Perfil", "Ativo", "Criado em"])
        configurar_tabela_responsiva(self.tabela_usuarios, stretch_columns=[1, 3], hidden_columns=[0])
        self.tabela_usuarios.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.tabela_usuarios, 1)
        self.btn_user_salvar.clicked.connect(self.salvar_usuario)
        self.btn_user_limpar.clicked.connect(self.limpar_usuario)
        self.btn_user_excluir.clicked.connect(self.excluir_usuario)
        self.tabela_usuarios.cellClicked.connect(self.selecionar_usuario)
        return self._scrollable(w)

    def _set_table(self, table, rows):
        table.setRowCount(0)
        for r_idx, row in enumerate(rows):
            table.insertRow(r_idx)
            for c_idx, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                if c_idx == 0:
                    item.setData(Qt.UserRole, value)
                table.setItem(r_idx, c_idx, item)
        table.resizeRowsToContents()
        ajustar_tabela_apos_carregar(table)

    def _current_id(self, table):
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _copiar_combo(self, origem, destino, current_data=None):
        destino.clear()
        for idx in range(origem.count()):
            destino.addItem(origem.itemText(idx), origem.itemData(idx))
        self._set_combo(destino, current_data if current_data is not None else origem.currentData())

    def atualizar_resumo_dados(self):
        if not hasattr(self, "resumo_dados_os"):
            return
        numero = self.numero.text().strip() or "OS ainda não salva"
        partes = [
            f"<b>{numero}</b> | {self.status.currentText()}",
            f"Objeto: {self.objeto.text().strip() or 'Não informado'}",
            f"Cliente: {self.cliente.currentText()} | Contrato: {self.contrato.currentText()} | Segmento: {self.segmento.currentText()}",
            f"Local: {self.local_execucao.text().strip() or self.municipio.text().strip() or 'Não informado'}",
            f"Executor: {self.executor.text().strip() or 'Não informado'} | Responsável técnico: {self.responsavel_tecnico.text().strip() or 'Não informado'}",
            f"Prazo: {self.data_inicio.date().toString('dd/MM/yyyy')} a {self.data_fim.date().toString('dd/MM/yyyy')}",
        ]
        self.resumo_dados_os.setText("<br>".join(partes))

    def abrir_seletor_os(self):
        dlg = OsSelectorDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.ordem_id:
            self.carregar_ordens()
            self.abrir_os_por_id(dlg.ordem_id)

    def editar_dados_os(self):
        travada = bool(self.ordem_id and not os_service.ordem_permite_edicao_basica(self.ordem_id))
        if travada:
            QMessageBox.warning(self, "Editar OS", "Esta OS está travada ou já foi importada para orçamento.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Editar dados da OS")
        dlg.resize(1040, 720)
        layout = QVBoxLayout(dlg)
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        numero = self._line()
        numero.setText(self.numero.text())
        status = QComboBox()
        status.addItems(os_service.STATUS_OS)
        status.setCurrentText(self.status.currentText())
        cliente = QComboBox()
        contrato = QComboBox()
        segmento = QComboBox()
        orcamento_origem = QComboBox()
        self._copiar_combo(self.cliente, cliente)
        self._copiar_combo(self.contrato, contrato)
        self._copiar_combo(self.segmento, segmento)
        self._copiar_combo(self.orcamento_origem, orcamento_origem)
        objeto = self._line("Objeto resumido da OS")
        objeto.setText(self.objeto.text())
        local_execucao = self._line("Endereço, bairro, ponto ou referência")
        local_execucao.setText(self.local_execucao.text())
        municipio = self._line()
        municipio.setText(self.municipio.text())
        latitude = self._line("Latitude")
        latitude.setText(self.latitude.text())
        longitude = self._line("Longitude")
        longitude.setText(self.longitude.text())
        solicitante = self._line()
        solicitante.setText(self.solicitante.text())
        executor = self._line()
        executor.setText(self.executor.text())
        responsavel_tecnico = self._line()
        responsavel_tecnico.setText(self.responsavel_tecnico.text())
        fiscal_cliente = self._line()
        fiscal_cliente.setText(self.fiscal_cliente.text())
        gestor = self._line()
        gestor.setText(self.gestor.text())
        data_emissao = self._date()
        data_emissao.setDate(self.data_emissao.date())
        data_inicio = self._date()
        data_inicio.setDate(self.data_inicio.date())
        data_fim = self._date()
        data_fim.setDate(self.data_fim.date())
        observacao = QTextEdit()
        observacao.setMinimumHeight(100)
        observacao.setPlainText(self.observacao.toPlainText())

        campos = [
            ("Número", numero), ("Status", status),
            ("Cliente", cliente), ("Contrato", contrato),
            ("Segmento", segmento), ("Orçamento origem", orcamento_origem),
            ("Objeto", objeto), ("Local execução", local_execucao),
            ("Município", municipio), ("Latitude", latitude),
            ("Longitude", longitude), ("Solicitante", solicitante),
            ("Executor", executor), ("Responsável técnico", responsavel_tecnico),
            ("Fiscal/cliente", fiscal_cliente), ("Gestor", gestor),
            ("Emissão", data_emissao), ("Início previsto", data_inicio),
            ("Fim previsto", data_fim),
        ]
        for idx, (label, widget) in enumerate(campos):
            row = idx // 2
            col = (idx % 2) * 2
            form.addWidget(QLabel(label), row, col)
            form.addWidget(widget, row, col + 1)
        row = (len(campos) + 1) // 2
        form.addWidget(QLabel("Observação"), row, 0)
        form.addWidget(observacao, row, 1, 1, 3)
        layout.addLayout(form)

        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Save).setText("Salvar dados")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        layout.addWidget(botoes)
        botoes.accepted.connect(dlg.accept)
        botoes.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return

        self.numero.setText(numero.text().strip())
        self.status.setCurrentText(status.currentText())
        self._set_combo(self.cliente, cliente.currentData())
        self._set_combo(self.contrato, contrato.currentData())
        self._set_combo(self.segmento, segmento.currentData())
        self._set_combo(self.orcamento_origem, orcamento_origem.currentData())
        self.objeto.setText(objeto.text().strip())
        self.local_execucao.setText(local_execucao.text().strip())
        self.municipio.setText(municipio.text().strip())
        self.latitude.setText(latitude.text().strip())
        self.longitude.setText(longitude.text().strip())
        self.solicitante.setText(solicitante.text().strip())
        self.executor.setText(executor.text().strip())
        self.responsavel_tecnico.setText(responsavel_tecnico.text().strip())
        self.fiscal_cliente.setText(fiscal_cliente.text().strip())
        self.gestor.setText(gestor.text().strip())
        self.data_emissao.setDate(data_emissao.date())
        self.data_inicio.setDate(data_inicio.date())
        self.data_fim.setDate(data_fim.date())
        self.observacao.setPlainText(observacao.toPlainText())
        self.salvar_os()

    def excluir_os(self):
        if not self.ordem_id:
            QMessageBox.warning(self, "Excluir OS", "Abra uma OS antes de excluir.")
            return
        if not os_service.ordem_permite_exclusao(self.ordem_id):
            QMessageBox.warning(self, "Excluir OS", "Esta OS não pode ser excluída porque já foi aprovada, executada, importada para orçamento ou travada.")
            return
        if QMessageBox.question(self, "Excluir OS", "Excluir esta OS e seus itens, fotos e anexos vinculados?") != QMessageBox.Yes:
            return
        try:
            os_service.excluir_ordem(self.ordem_id)
            self.carregar_ordens()
            self.nova_os()
            QMessageBox.information(self, "Excluir OS", "OS excluída.")
        except Exception as e:
            QMessageBox.critical(self, "Excluir OS", str(e))

    def carregar_combos(self):
        with conn() as c:
            clientes = c.execute("SELECT id,nome FROM clientes ORDER BY nome").fetchall()
            contratos = c.execute("SELECT id,nome,cliente_id FROM contratos ORDER BY nome").fetchall()
            segmentos = c.execute("SELECT id,nome FROM segmentos ORDER BY nome").fetchall()
            orcamentos = c.execute("SELECT id,codigo,objeto FROM orcamentos ORDER BY id DESC").fetchall()
        for combo in [self.cliente]:
            atual = combo.currentData()
            combo.clear()
            combo.addItem("Não vinculado", None)
            for r in clientes:
                combo.addItem(r["nome"], r["id"])
            self._set_combo(combo, atual)
        self.contrato.clear()
        self.contrato.addItem("Não vinculado", None)
        for r in contratos:
            self.contrato.addItem(r["nome"], r["id"])
        self.segmento.clear()
        self.segmento.addItem("Não vinculado", None)
        for r in segmentos:
            self.segmento.addItem(r["nome"], r["id"])
        for combo in [self.orcamento_origem, self.orcamento_destino]:
            keep = combo.currentData() if combo.count() else None
            combo.clear()
            combo.addItem("Criar novo orçamento" if combo is self.orcamento_destino else "Não vinculado", None)
            for r in orcamentos:
                label = f"{r['codigo'] or 'ORC'} - {r['objeto'] or ''}"
                combo.addItem(label[:120], r["id"])
            self._set_combo(combo, keep)

    def carregar_usuarios(self):
        if not hasattr(self, "tabela_usuarios"):
            return
        rows = []
        for r in auth_service.listar_usuarios():
            rows.append([r["id"], r["nome"], r["usuario"], r["email"], r["perfil"], "Sim" if r["ativo"] else "Não", r["criado_em"]])
        self._set_table(self.tabela_usuarios, rows)

    def limpar_usuario(self):
        self.selected_usuario_id = None
        for w in [self.user_nome, self.user_login, self.user_email, self.user_senha]:
            w.clear()
        self.user_perfil.setCurrentText("OPERACIONAL")
        self.user_ativo.setChecked(True)

    def selecionar_usuario(self, row, col):
        self.selected_usuario_id = self.tabela_usuarios.item(row, 0).data(Qt.UserRole)
        self.user_nome.setText(self.tabela_usuarios.item(row, 1).text())
        self.user_login.setText(self.tabela_usuarios.item(row, 2).text())
        self.user_email.setText(self.tabela_usuarios.item(row, 3).text())
        self.user_senha.clear()
        self.user_perfil.setCurrentText(self.tabela_usuarios.item(row, 4).text())
        self.user_ativo.setChecked(self.tabela_usuarios.item(row, 5).text() == "Sim")

    def salvar_usuario(self):
        try:
            auth_service.salvar_usuario(
                self.user_nome.text(),
                self.user_login.text(),
                self.user_email.text(),
                self.user_senha.text(),
                self.user_perfil.currentText(),
                self.user_ativo.isChecked(),
                self.selected_usuario_id,
            )
            self.limpar_usuario()
            self.carregar_usuarios()
            QMessageBox.information(self, "Autorizações", "Usuário autorizado salvo.")
        except Exception as e:
            QMessageBox.critical(self, "Autorizações", f"Erro ao salvar usuário:\n{e}")

    def excluir_usuario(self):
        if not self.selected_usuario_id:
            return
        if QMessageBox.question(self, "Autorizações", "Excluir este usuário autorizado?") != QMessageBox.Yes:
            return
        try:
            auth_service.remover_usuario(self.selected_usuario_id)
            self.limpar_usuario()
            self.carregar_usuarios()
        except Exception as e:
            QMessageBox.critical(self, "Autorizações", f"Erro ao excluir usuário:\n{e}")

    def _set_combo(self, combo, value):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def carregar_ordens(self):
        termo = self.busca.text().strip().lower() if hasattr(self, "busca") else ""
        rows = []
        for r in os_service.listar_ordens():
            texto = " ".join(str(r[k] or "") for k in ["numero", "status", "cliente_nome", "objeto", "executor", "importado_codigo"]).lower()
            if termo and termo not in texto:
                continue
            partes = [
                r["cliente_nome"] or "Cliente não informado",
                r["objeto"] or "Objeto não informado",
                f"Executor: {r['executor']}" if r["executor"] else "",
                f"Orçamento: {r['importado_codigo']}" if r["importado_codigo"] else "",
            ]
            resumo = "\n".join([p for p in partes if p])
            rows.append([r["id"], r["numero"], r["status"], resumo])
        self._set_table(self.tabela_os, rows)

    def nova_os(self):
        self.ordem_id = None
        self.selected_etapa_id = None
        self.selected_item_id = None
        self.numero.setText(os_service.gerar_numero_os())
        self.status.setCurrentText("RASCUNHO")
        for combo in [self.cliente, self.contrato, self.segmento, self.orcamento_origem]:
            combo.setCurrentIndex(0)
        for w in [self.objeto, self.local_execucao, self.municipio, self.latitude, self.longitude, self.solicitante, self.executor, self.responsavel_tecnico, self.fiscal_cliente, self.gestor]:
            w.clear()
        self.observacao.clear()
        for d in [self.data_emissao, self.data_inicio, self.data_fim]:
            d.setDate(QDate.currentDate())
        self.carregar_relacionados()
        self.status_label.setText("Nova OS em edição")
        self._set_travada(False)
        self.atualizar_resumo_dados()

    def salvar_os(self):
        dados = {
            "numero": self.numero.text().strip(),
            "status": self.status.currentText(),
            "cliente_id": self.cliente.currentData(),
            "contrato_id": self.contrato.currentData(),
            "segmento_id": self.segmento.currentData(),
            "orcamento_id": self.orcamento_origem.currentData(),
            "objeto": self.objeto.text().strip(),
            "local_execucao": self.local_execucao.text().strip(),
            "municipio": self.municipio.text().strip(),
            "latitude": self.latitude.text().strip(),
            "longitude": self.longitude.text().strip(),
            "solicitante": self.solicitante.text().strip(),
            "executor": self.executor.text().strip(),
            "responsavel_tecnico": self.responsavel_tecnico.text().strip(),
            "fiscal_cliente": self.fiscal_cliente.text().strip(),
            "gestor": self.gestor.text().strip(),
            "data_emissao": self.data_emissao.date().toString("yyyy-MM-dd"),
            "data_prevista_inicio": self.data_inicio.date().toString("yyyy-MM-dd"),
            "data_prevista_fim": self.data_fim.date().toString("yyyy-MM-dd"),
            "observacao": self.observacao.toPlainText(),
        }
        if not dados["objeto"]:
            QMessageBox.warning(self, "OS", "Informe o objeto da Ordem de Serviço.")
            return
        try:
            self.ordem_id = os_service.salvar_ordem(dados, self.ordem_id)
            self.carregar_ordens()
            self.carregar_relacionados()
            self.atualizar_resumo_dados()
            QMessageBox.information(self, "OS", "Ordem de Serviço salva.")
        except Exception as e:
            QMessageBox.critical(self, "OS", f"Erro ao salvar OS:\n{e}")

    def abrir_os_selecionada(self):
        oid = self._current_id(self.tabela_os)
        if not oid:
            return
        row = os_service.obter_ordem(oid)
        if not row:
            return
        self.ordem_id = oid
        self.numero.setText(row["numero"] or "")
        self.status.setCurrentText(row["status"] or "RASCUNHO")
        self._set_combo(self.cliente, row["cliente_id"])
        self._set_combo(self.contrato, row["contrato_id"])
        self._set_combo(self.segmento, row["segmento_id"])
        self._set_combo(self.orcamento_origem, row["orcamento_id"])
        self.objeto.setText(row["objeto"] or "")
        self.local_execucao.setText(row["local_execucao"] or "")
        self.municipio.setText(row["municipio"] or "")
        self.latitude.setText(row["latitude"] or "")
        self.longitude.setText(row["longitude"] or "")
        self.solicitante.setText(row["solicitante"] or "")
        self.executor.setText(row["executor"] or "")
        self.responsavel_tecnico.setText(row["responsavel_tecnico"] or "")
        self.fiscal_cliente.setText(row["fiscal_cliente"] or "")
        self.gestor.setText(row["gestor"] or "")
        for widget, key in [(self.data_emissao, "data_emissao"), (self.data_inicio, "data_prevista_inicio"), (self.data_fim, "data_prevista_fim")]:
            try:
                widget.setDate(QDate.fromString(row[key] or "", "yyyy-MM-dd") or QDate.currentDate())
            except Exception:
                widget.setDate(QDate.currentDate())
        self.observacao.setPlainText(row["observacao"] or "")
        self.carregar_relacionados()
        travada = bool(row["travada"])
        self._set_travada(travada)
        self.status_label.setText(f"OS {row['numero']} | {row['status']} | {'TRAVADA' if travada else 'Editável'}")
        self.atualizar_resumo_dados()

    def _set_travada(self, travada):
        edit_buttons = [
            self.btn_editar_os, self.btn_salvar, self.btn_etapa_salvar, self.btn_etapa_excluir,
            self.btn_item_salvar, self.btn_item_excluir, self.btn_foto_add,
            self.btn_foto_del, self.btn_anexo_add, self.btn_anexo_del,
        ]
        for name in ["btn_etapa_nova_popup", "btn_etapa_editar_popup", "btn_etapa_excluir_popup", "btn_item_novo_popup", "btn_item_editar_popup", "btn_item_excluir_popup", "btn_item_sinapi_popup", "btn_editar_dados_aba", "btn_importar_pacote_executor"]:
            if hasattr(self, name):
                edit_buttons.append(getattr(self, name))
        for btn in edit_buttons:
            btn.setDisabled(travada)
        self.btn_excluir_os.setDisabled(bool((not self.ordem_id) or not os_service.ordem_permite_exclusao(self.ordem_id)))
        self.btn_importar.setDisabled(travada)
        self.btn_importar_aba.setDisabled(travada)

    def garantir_os(self):
        if not self.ordem_id:
            self.salvar_os()
        return self.ordem_id

    def carregar_relacionados(self):
        self.carregar_etapas()
        self.carregar_itens()
        self.carregar_fotos()
        self.carregar_anexos()

    def carregar_etapas(self):
        for combo in [self.item_etapa, self.foto_etapa, self.anexo_etapa]:
            combo.clear()
            combo.addItem("Sem etapa", None)
        if not self.ordem_id:
            self._set_table(self.tabela_etapas, [])
            return
        rows = []
        for r in os_service.listar_etapas(self.ordem_id):
            rows.append([r["id"], r["ordem"], r["nome"], r["status"], r["percentual_execucao"], r["observacao"]])
            for combo in [self.item_etapa, self.foto_etapa, self.anexo_etapa]:
                combo.addItem(r["nome"], r["id"])
        self._set_table(self.tabela_etapas, rows)

    def salvar_etapa(self):
        if not self.garantir_os():
            return
        if not self.etapa_nome.text().strip():
            QMessageBox.warning(self, "Etapa", "Informe o nome da etapa.")
            return
        dados = {
            "nome": self.etapa_nome.text().strip(),
            "descricao": self.etapa_desc.toPlainText(),
            "status": self.etapa_status.currentText(),
            "percentual_execucao": self.etapa_percentual.value(),
            "observacao": self.etapa_obs.toPlainText(),
        }
        try:
            os_service.salvar_etapa(self.ordem_id, dados, self.selected_etapa_id)
            self.limpar_etapa()
            self.carregar_etapas()
        except Exception as e:
            QMessageBox.critical(self, "Etapa", str(e))

    def selecionar_etapa(self, row, col):
        self.selected_etapa_id = self.tabela_etapas.item(row, 0).data(Qt.UserRole)
        etapas = {r["id"]: r for r in os_service.listar_etapas(self.ordem_id)}
        r = etapas.get(self.selected_etapa_id)
        if not r:
            return
        self.etapa_nome.setText(r["nome"] or "")
        self.etapa_status.setCurrentText(r["status"] or "PLANEJADA")
        self.etapa_percentual.setValue(float(r["percentual_execucao"] or 0))
        self.etapa_desc.setPlainText(r["descricao"] or "")
        self.etapa_obs.setPlainText(r["observacao"] or "")

    def limpar_etapa(self):
        self.selected_etapa_id = None
        self.etapa_nome.clear()
        self.etapa_desc.clear()
        self.etapa_obs.clear()
        self.etapa_percentual.setValue(0)
        self.etapa_status.setCurrentText("PLANEJADA")

    def excluir_etapa(self):
        if not self.selected_etapa_id:
            return
        if QMessageBox.question(self, "Etapa", "Excluir etapa e seus itens/fotos vinculados?") != QMessageBox.Yes:
            return
        try:
            os_service.excluir_etapa(self.ordem_id, self.selected_etapa_id)
            self.limpar_etapa()
            self.carregar_relacionados()
        except Exception as e:
            QMessageBox.critical(self, "Etapa", str(e))

    def abrir_dialog_etapa(self, editar=False):
        if not self.garantir_os():
            return
        if editar and not self.selected_etapa_id:
            QMessageBox.warning(self, "Etapa", "Selecione uma etapa na tabela.")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Editar etapa" if editar else "Nova etapa")
        dlg.resize(760, 420)
        layout = QVBoxLayout(dlg)
        grid = QGridLayout()
        nome = self._line("Nome da etapa")
        status = QComboBox()
        status.addItems(os_service.STATUS_ETAPA)
        percentual = QDoubleSpinBox()
        percentual.setRange(0, 100)
        percentual.setSuffix(" %")
        descricao = QTextEdit()
        descricao.setMinimumHeight(90)
        observacao = QTextEdit()
        observacao.setMinimumHeight(90)
        if editar:
            self.selecionar_etapa(self.tabela_etapas.currentRow(), 0)
        nome.setText(self.etapa_nome.text())
        status.setCurrentText(self.etapa_status.currentText())
        percentual.setValue(self.etapa_percentual.value())
        descricao.setPlainText(self.etapa_desc.toPlainText())
        observacao.setPlainText(self.etapa_obs.toPlainText())
        grid.addWidget(QLabel("Nome"), 0, 0)
        grid.addWidget(nome, 1, 0, 1, 2)
        grid.addWidget(QLabel("Status"), 0, 2)
        grid.addWidget(status, 1, 2)
        grid.addWidget(QLabel("Execução"), 0, 3)
        grid.addWidget(percentual, 1, 3)
        grid.addWidget(QLabel("Descrição"), 2, 0, 1, 2)
        grid.addWidget(QLabel("Observação"), 2, 2, 1, 2)
        grid.addWidget(descricao, 3, 0, 1, 2)
        grid.addWidget(observacao, 3, 2, 1, 2)
        layout.addLayout(grid)
        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Save).setText("Salvar etapa")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        layout.addWidget(botoes)
        botoes.accepted.connect(dlg.accept)
        botoes.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return
        self.etapa_nome.setText(nome.text().strip())
        self.etapa_status.setCurrentText(status.currentText())
        self.etapa_percentual.setValue(percentual.value())
        self.etapa_desc.setPlainText(descricao.toPlainText())
        self.etapa_obs.setPlainText(observacao.toPlainText())
        self.salvar_etapa()

    def carregar_itens(self):
        if not self.ordem_id:
            self._set_table(self.tabela_itens, [])
            return
        rows = []
        for r in os_service.listar_itens(self.ordem_id):
            rows.append([r["id"], r["etapa_nome"], r["descricao"], r["unidade"], r["quantidade_prevista"], r["quantidade_executada"], r["fonte"], "Sim" if r["importar_orcamento"] else "Não"])
        self._set_table(self.tabela_itens, rows)

    def salvar_item(self):
        if not self.garantir_os():
            return
        if not self.item_desc.toPlainText().strip():
            QMessageBox.warning(self, "Item", "Informe a descrição do item.")
            return
        dados = {
            "etapa_id": self.item_etapa.currentData(),
            "descricao": self.item_desc.toPlainText(),
            "unidade": self.item_unidade.text().strip() or "UN",
            "quantidade_prevista": self.item_qtd_prev.value(),
            "quantidade_executada": self.item_qtd_exec.value(),
            "fonte": self.item_fonte.text().strip(),
            "codigo": self.item_codigo.text().strip(),
            "observacao": self.item_obs.text().strip(),
            "importar_orcamento": self.item_importar.isChecked(),
        }
        try:
            os_service.salvar_item(self.ordem_id, dados, self.selected_item_id)
            self.limpar_item()
            self.carregar_itens()
        except Exception as e:
            QMessageBox.critical(self, "Item", str(e))

    def selecionar_item(self, row, col):
        self.selected_item_id = self.tabela_itens.item(row, 0).data(Qt.UserRole)
        itens = {r["id"]: r for r in os_service.listar_itens(self.ordem_id)}
        r = itens.get(self.selected_item_id)
        if not r:
            return
        self._set_combo(self.item_etapa, r["etapa_id"])
        self.item_desc.setPlainText(r["descricao"] or "")
        self.item_unidade.setText(r["unidade"] or "UN")
        self.item_qtd_prev.setValue(float(r["quantidade_prevista"] or 0))
        self.item_qtd_exec.setValue(float(r["quantidade_executada"] or 0))
        self.item_fonte.setText(r["fonte"] or "")
        self.item_codigo.setText(r["codigo"] or "")
        self.item_obs.setText(r["observacao"] or "")
        self.item_importar.setChecked(bool(r["importar_orcamento"]))

    def limpar_item(self):
        self.selected_item_id = None
        self.item_desc.clear()
        self.item_unidade.setText("UN")
        self.item_qtd_prev.setValue(0)
        self.item_qtd_exec.setValue(0)
        self.item_fonte.clear()
        self.item_codigo.clear()
        self.item_obs.clear()
        self.item_importar.setChecked(True)

    def excluir_item(self):
        if not self.selected_item_id:
            return
        try:
            os_service.excluir_item(self.ordem_id, self.selected_item_id)
            self.limpar_item()
            self.carregar_itens()
        except Exception as e:
            QMessageBox.critical(self, "Item", str(e))

    def abrir_dialog_item(self, editar=False, fonte_inicial=None):
        if not self.garantir_os():
            return
        if editar and not self.selected_item_id:
            QMessageBox.warning(self, "Item", "Selecione um item na tabela.")
            return
        if editar:
            self.selecionar_item(self.tabela_itens.currentRow(), 0)

        dlg = QDialog(self)
        dlg.setWindowTitle("Editar item" if editar else "Novo item da etapa")
        dlg.resize(980, 600)
        layout = QVBoxLayout(dlg)
        grid = QGridLayout()
        etapa = QComboBox()
        self._copiar_combo(self.item_etapa, etapa)
        fonte = QComboBox()
        fonte.addItems(["OS sequencial", "SINAPI", "Composição própria", "Orçamento de terceiro"])
        if fonte_inicial:
            fonte.setCurrentText(fonte_inicial)
        elif self.item_fonte.text().strip():
            idx = fonte.findText(self.item_fonte.text().strip())
            fonte.setCurrentIndex(idx if idx >= 0 else 0)
        codigo = self._line("Automático se ficar vazio")
        codigo.setText(self.item_codigo.text())
        descricao = QTextEdit()
        descricao.setMinimumHeight(120)
        descricao.setPlainText(self.item_desc.toPlainText())
        unidade = self._line("UN")
        unidade.setText(self.item_unidade.text() or "UN")
        qtd_prev = QDoubleSpinBox()
        qtd_prev.setRange(0, 999999999)
        qtd_prev.setDecimals(4)
        qtd_prev.setValue(self.item_qtd_prev.value())
        qtd_exec = QDoubleSpinBox()
        qtd_exec.setRange(0, 999999999)
        qtd_exec.setDecimals(4)
        qtd_exec.setValue(self.item_qtd_exec.value())
        importar = QCheckBox("Importar este item para orçamento")
        importar.setChecked(self.item_importar.isChecked())
        observacao = QTextEdit()
        observacao.setMinimumHeight(80)
        observacao.setPlainText(self.item_obs.text())
        btn_sinapi = QPushButton("Pesquisar na base SINAPI")
        btn_sinapi.setMinimumHeight(38)

        def buscar_sinapi():
            dlg_busca = SinapiOsSearchDialog(dlg, codigo.text() or descricao.toPlainText())
            if dlg_busca.exec() == QDialog.Accepted and dlg_busca.item_selecionado:
                row = dlg_busca.item_selecionado
                fonte.setCurrentText("SINAPI")
                codigo.setText(str(row.get("codigo") or ""))
                descricao.setPlainText(row.get("descricao") or "")
                unidade.setText(row.get("unidade") or "UN")

        btn_sinapi.clicked.connect(buscar_sinapi)
        grid.addWidget(QLabel("Etapa"), 0, 0)
        grid.addWidget(etapa, 1, 0)
        grid.addWidget(QLabel("Origem do item"), 0, 1)
        grid.addWidget(fonte, 1, 1)
        grid.addWidget(QLabel("Código"), 0, 2)
        grid.addWidget(codigo, 1, 2)
        grid.addWidget(btn_sinapi, 1, 3)
        grid.addWidget(QLabel("Descrição"), 2, 0, 1, 4)
        grid.addWidget(descricao, 3, 0, 1, 4)
        grid.addWidget(QLabel("Unidade"), 4, 0)
        grid.addWidget(unidade, 5, 0)
        grid.addWidget(QLabel("Qtd prevista"), 4, 1)
        grid.addWidget(qtd_prev, 5, 1)
        grid.addWidget(QLabel("Qtd executada"), 4, 2)
        grid.addWidget(qtd_exec, 5, 2)
        grid.addWidget(importar, 5, 3)
        grid.addWidget(QLabel("Observação técnica do item"), 6, 0, 1, 4)
        grid.addWidget(observacao, 7, 0, 1, 4)
        layout.addLayout(grid)
        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.button(QDialogButtonBox.Save).setText("Salvar item")
        botoes.button(QDialogButtonBox.Cancel).setText("Cancelar")
        layout.addWidget(botoes)
        botoes.accepted.connect(dlg.accept)
        botoes.rejected.connect(dlg.reject)
        if dlg.exec() != QDialog.Accepted:
            return

        self._set_combo(self.item_etapa, etapa.currentData())
        self.item_fonte.setText(fonte.currentText())
        self.item_codigo.setText(codigo.text().strip())
        self.item_desc.setPlainText(descricao.toPlainText())
        self.item_unidade.setText(unidade.text().strip() or "UN")
        self.item_qtd_prev.setValue(qtd_prev.value())
        self.item_qtd_exec.setValue(qtd_exec.value())
        self.item_importar.setChecked(importar.isChecked())
        self.item_obs.setText(observacao.toPlainText().strip())
        self.salvar_item()

    def importar_pacote_executor(self):
        path, _ = QFileDialog.getOpenFileName(self, "Importar pacote do executor", "", "Pacote ZIP (*.zip);;Todos (*.*)")
        if not path:
            return
        try:
            resultado = os_service.importar_pacote_executor(
                path,
                self.ordem_id,
                self.usuario_atual.get("nome") or self.executor.text() or "Importação executor",
            )
            if not self.ordem_id:
                self.carregar_ordens()
                self.abrir_os_por_id(resultado["ordem_id"])
            self.carregar_fotos()
            QMessageBox.information(
                self,
                "Pacote do executor",
                f"Importação concluída.\n\nFotos importadas: {resultado['fotos']}\nResumo recebido: {'Sim' if resultado['resumo'] else 'Não'}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Pacote do executor", f"Erro ao importar pacote:\n{e}")

    def selecionar_foto_arquivo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar foto", "", "Imagens (*.png *.jpg *.jpeg *.bmp);;Todos (*.*)")
        if path:
            self.foto_caminho.setText(path)

    def adicionar_foto(self):
        if not self.garantir_os():
            return
        if not self.foto_caminho.text().strip():
            QMessageBox.warning(self, "Fotos", "Selecione uma foto.")
            return
        try:
            os_service.adicionar_foto(
                self.ordem_id, self.foto_caminho.text(), self.foto_etapa.currentData(),
                self.foto_categoria.currentText(), self.foto_legenda.text(), self.usuario_atual.get("nome") or self.executor.text(),
                self.foto_obs.text(),
            )
            self.foto_caminho.clear()
            self.foto_legenda.clear()
            self.foto_obs.clear()
            self.carregar_fotos()
        except Exception as e:
            QMessageBox.critical(self, "Fotos", str(e))

    def carregar_fotos(self):
        if not self.ordem_id:
            self._set_table(self.tabela_fotos, [])
            return
        rows = []
        for r in os_service.listar_fotos(self.ordem_id):
            rows.append([r["id"], r["etapa_nome"], r["categoria"], r["nome_arquivo"], r["legenda"], r["data_registro"], r["caminho"]])
        self._set_table(self.tabela_fotos, rows)

    def selecionar_foto(self, row, col):
        self.selected_foto_id = self.tabela_fotos.item(row, 0).data(Qt.UserRole)

    def excluir_foto(self):
        if not self.selected_foto_id:
            return
        try:
            os_service.excluir_foto(self.ordem_id, self.selected_foto_id)
            self.selected_foto_id = None
            self.carregar_fotos()
        except Exception as e:
            QMessageBox.critical(self, "Fotos", str(e))

    def selecionar_anexo_arquivo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar anexo", "", "Todos os arquivos (*.*)")
        if path:
            self.anexo_caminho.setText(path)

    def adicionar_anexo(self):
        if not self.garantir_os():
            return
        if not self.anexo_caminho.text().strip():
            QMessageBox.warning(self, "Anexos", "Selecione um anexo.")
            return
        try:
            os_service.adicionar_anexo(
                self.ordem_id, self.anexo_caminho.text(), self.anexo_etapa.currentData(),
                self.anexo_tipo.currentText(), self.anexo_obs.text(), self.usuario_atual.get("nome") or self.executor.text(),
                self.anexo_importar.isChecked(),
            )
            self.anexo_caminho.clear()
            self.anexo_obs.clear()
            self.carregar_anexos()
        except Exception as e:
            QMessageBox.critical(self, "Anexos", str(e))

    def carregar_anexos(self):
        if not self.ordem_id:
            self._set_table(self.tabela_anexos, [])
            return
        rows = []
        for r in os_service.listar_anexos(self.ordem_id):
            rows.append([r["id"], r["etapa_nome"], r["tipo"], r["nome_arquivo"], "Sim" if r["importar_orcamento"] else "Não", r["data_upload"], r["caminho"]])
        self._set_table(self.tabela_anexos, rows)

    def selecionar_anexo(self, row, col):
        self.selected_anexo_id = self.tabela_anexos.item(row, 0).data(Qt.UserRole)

    def excluir_anexo(self):
        if not self.selected_anexo_id:
            return
        try:
            os_service.excluir_anexo(self.ordem_id, self.selected_anexo_id)
            self.selected_anexo_id = None
            self.carregar_anexos()
        except Exception as e:
            QMessageBox.critical(self, "Anexos", str(e))

    def _caminho_anexo_selecionado(self):
        if not self.selected_anexo_id:
            return None
        for row in range(self.tabela_anexos.rowCount()):
            item_id = self.tabela_anexos.item(row, 0)
            if item_id and item_id.data(Qt.UserRole) == self.selected_anexo_id:
                item_path = self.tabela_anexos.item(row, 6)
                return Path(item_path.text()) if item_path and item_path.text() else None
        return None

    def abrir_anexo(self):
        caminho = self._caminho_anexo_selecionado()
        if not caminho or not caminho.exists():
            QMessageBox.warning(self, "Anexos", "Selecione um anexo disponível.")
            return
        os.startfile(str(caminho))

    def baixar_anexo(self):
        caminho = self._caminho_anexo_selecionado()
        if not caminho or not caminho.exists():
            QMessageBox.warning(self, "Anexos", "Selecione um anexo disponível.")
            return
        destino, _ = QFileDialog.getSaveFileName(
            self,
            "Salvar cópia do anexo",
            caminho.name,
            f"Arquivo (*{caminho.suffix});;Todos (*.*)",
        )
        if destino:
            shutil.copy2(caminho, destino)
            QMessageBox.information(self, "Anexos", "Cópia do anexo salva com sucesso.")

    def destravar_os(self):
        if not self.is_admin or not self.garantir_os():
            return
        resposta = QMessageBox.question(
            self,
            "Destravar OS",
            "Liberar esta OS para edição e permitir uma nova transformação em orçamento?\n\n"
            "O orçamento já criado não será apagado.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resposta != QMessageBox.Yes:
            return
        try:
            os_service.destravar_ordem(self.ordem_id)
            self.abrir_os_por_id(self.ordem_id)
            QMessageBox.information(self, "Destravar OS", "OS liberada para edição.")
        except Exception as e:
            QMessageBox.critical(self, "Destravar OS", str(e))

    def aprovar_inicio(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Aprovação", "A aprovação de início é feita somente no app Admin.")
            return
        if not self.garantir_os():
            return
        if QMessageBox.question(self, "Aprovar início", "Confirmar aprovação do início da execução desta OS?") != QMessageBox.Yes:
            return
        os_service.aprovar_inicio(self.ordem_id, self.gestor.text() or self.usuario_atual.get("nome") or "Admin/Gestor")
        QMessageBox.information(self, "OS", "Início aprovado. A OS pode ser executada e importada para orçamento quando necessário.")
        self.carregar_ordens()
        self.abrir_os_por_id(self.ordem_id)

    def abrir_os_por_id(self, ordem_id):
        for row in range(self.tabela_os.rowCount()):
            if self.tabela_os.item(row, 0).data(Qt.UserRole) == ordem_id:
                self.tabela_os.selectRow(row)
                self.abrir_os_selecionada()
                return
        self.busca.clear()
        self.carregar_ordens()
        for row in range(self.tabela_os.rowCount()):
            if self.tabela_os.item(row, 0).data(Qt.UserRole) == ordem_id:
                self.tabela_os.selectRow(row)
                self.abrir_os_selecionada()
                return

    def importar_orcamento(self):
        if not self.is_admin:
            QMessageBox.warning(self, "Orçamento", "A transformação em orçamento é feita somente no app Admin.")
            return
        if not self.garantir_os():
            return
        # O vínculo informado no cadastro da OS tem prioridade. O seletor da
        # aba Geração só é usado quando a OS não possui orçamento de origem.
        origem = self.orcamento_origem.currentData()
        destino = origem if origem else self.orcamento_destino.currentData()
        if origem:
            mensagem = (
                "Vincular esta OS ao orçamento já indicado no cadastro?\n\n"
                "Nenhum novo orçamento será criado e os itens existentes não serão duplicados."
            )
        else:
            mensagem = "Importar etapas, itens, fotos e anexos para orçamento e travar a OS?"
        if QMessageBox.question(self, "Transformar em orçamento", mensagem) != QMessageBox.Yes:
            return
        try:
            orcamento_id = os_service.importar_para_orcamento(self.ordem_id, destino)
            acao = "vinculada ao orçamento" if origem else "importada para o orçamento"
            QMessageBox.information(self, "Orçamento", f"OS {acao} ID {orcamento_id}. A OS foi travada.")
            self.carregar_combos()
            self.carregar_ordens()
            self.abrir_os_por_id(self.ordem_id)
            if self.abrir_orcamento_callback and QMessageBox.question(self, "Abrir orçamento", "Deseja abrir o orçamento gerado agora?") == QMessageBox.Yes:
                self.abrir_orcamento_callback(orcamento_id)
        except Exception as e:
            mensagem_operacional(self, "Orçamento", f"não consegui transformar esta OS em orçamento agora. Detalhe técnico: {e}", "erro")

    def _gerar_um(self, func):
        if not self.ordem_id:
            QMessageBox.warning(self, "Documentos", "Selecione ou salve uma OS.")
            return
        pasta = QFileDialog.getExistingDirectory(self, "Escolha onde salvar o documento")
        if not pasta:
            return
        try:
            arquivo = func(self.ordem_id, Path(pasta))
            QMessageBox.information(self, "Documentos", f"Arquivo gerado:\n{arquivo}")
        except Exception as e:
            mensagem_operacional(self, "Documentos", f"não consegui gerar o arquivo no local escolhido. Detalhe técnico: {e}", "erro")

    def gerar_documentos(self):
        if not self.ordem_id:
            QMessageBox.warning(self, "Documentos", "Selecione ou salve uma OS.")
            return
        pasta = QFileDialog.getExistingDirectory(self, "Escolha onde salvar os documentos")
        if not pasta:
            return
        try:
            arquivos = os_service.gerar_pacote_os(self.ordem_id, Path(pasta))
            QMessageBox.information(self, "Documentos", "Arquivos gerados:\n" + "\n".join(str(a) for a in arquivos))
        except Exception as e:
            mensagem_operacional(self, "Documentos", f"não consegui gerar o pacote no local escolhido. Detalhe técnico: {e}", "erro")

    def gerar_link_executor(self):
        if not self.garantir_os():
            return
        try:
            link = os_service.gerar_link_executor(self.ordem_id)
            if link["tipo"] == "web":
                url = link["url"]
                mensagem = (
                    f"OS {self.numero.text().strip()}\n\n"
                    "Acesse o Portal do Executor para tirar/selecionar as fotos e preencher a execução:\n"
                    f"{url}\n\n"
                    "No final, clique em Encaminhar fotos da OS e envie o ZIP gerado para importação no OS PPP."
                )
                QApplication.clipboard().setText(mensagem)
                QMessageBox.information(
                    self,
                    "Portal do executor",
                    "Link web copiado para colar no WhatsApp.\n\n"
                    "O WhatsApp deve reconhecer este endereço como link clicável."
                )
                webbrowser.open(url)
                return

            arquivo = link["arquivo"]
            mensagem = (
                f"OS {self.numero.text().strip()}\n\n"
                "Portal web ainda não configurado. Anexe este arquivo HTML no WhatsApp para o executor preencher:\n"
                f"{arquivo}\n\n"
                "Depois clique em Encaminhar fotos da OS. O sistema vai gerar um unico ZIP. "
                "Envie esse ZIP de volta pelo WhatsApp, e-mail ou Drive para importar no OS PPP."
            )
            QApplication.clipboard().setText(mensagem)
            QMessageBox.information(
                self,
                "Link do executor",
                "HTML localizado e mensagem copiada para colar no WhatsApp.\n\n"
                f"Arquivo: {arquivo}\n\n"
                "Para mandar como link clicável, configure a URL do Portal Executor em Configurações.\n\n"
                "Ao receber o retorno, importe o ZIP pela aba Fotos > Importar pacote do executor."
            )
            try:
                os.startfile(str(Path(arquivo).parent))
            except Exception:
                webbrowser.open(str(Path(arquivo).parent))
        except Exception as e:
            mensagem_operacional(self, "Link do executor", f"não consegui preparar o arquivo HTML do executor. Detalhe técnico: {e}", "erro")
    def abrir_pasta_os(self):
        if not self.ordem_id:
            return
        pasta = os_service.get_os_dir(self.ordem_id)
        try:
            os.startfile(str(pasta))
        except Exception:
            webbrowser.open(str(pasta))

