from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QScrollArea,
    QListWidget,
    QListWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QInputDialog,
    QTabWidget,
    QSizePolicy,
)

from repositories.contratos_repository import ContratosRepository
from core.database import conn
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar


class ContratosView(QWidget):
    def __init__(self):
        super().__init__()
        self.repo = ContratosRepository()
        self.contrato_id = None
        self.aditivo_id = None
        self.segmentos_cache = []
        self._carregando_tela = False
        self._carregando_contrato = False

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Contratos PPP")
        title.setStyleSheet("font-size:26px;font-weight:950;color:#071A33;")
        subtitle = QLabel("Contrato principal → segmentos → aditivos → orçamentos")
        subtitle.setStyleSheet("color:#64748B;font-size:12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Buscar contrato, número, município ou cliente")
        self.busca.setMinimumHeight(40)
        btn_buscar = self._button("Pesquisar", "#0B3B75")
        btn_buscar.clicked.connect(self.load_data)

        top.addLayout(title_box)
        top.addStretch()
        top.addWidget(self.busca, 2)
        top.addWidget(btn_buscar)
        root.addLayout(top)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._aba_contrato(), "Contrato principal")
        self.tabs.addTab(self._aba_aditivos(), "Aditivos")
        self.tabs.addTab(self._aba_consolidado(), "Consolidado por segmento")
        root.addWidget(self.tabs)

        self.cliente.currentIndexChanged.connect(self.preencher_dados_cliente)
        self.atualizar_tela()

    def showEvent(self, event):
        super().showEvent(event)
        self.atualizar_tela()

    def atualizar_tela(self):
        """Recarrega dados automaticamente sempre que a tela abre/volta a aparecer."""
        if self._carregando_tela:
            return
        self._carregando_tela = True
        try:
            contrato_aberto = self.contrato_id
            self.carregar_clientes()
            self.carregar_segmentos()
            self.load_data()
            if contrato_aberto:
                self.contrato_id = contrato_aberto
                self.carregar_contrato_por_id(contrato_aberto)
            else:
                self.carregar_aditivos()
                self.carregar_consolidado()
        finally:
            self._carregando_tela = False

    def _button(self, text, color="#0B3B75"):
        btn = QPushButton(text)
        btn.setMinimumHeight(40)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setStyleSheet(f"""
            QPushButton {{
                background:{color};
                color:white;
                border-radius:8px;
                font-weight:800;
                padding:8px 14px;
            }}
            QPushButton:hover {{ background:#082B63; }}
        """)
        return btn

    def _money(self, value):
        try:
            value = float(value or 0)
        except Exception:
            value = 0
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _aba_contrato(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)

        box = QGroupBox("Cadastro do contrato principal")
        form = QGridLayout(box)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.cliente = QComboBox()
        self.nome = QLineEdit()
        self.numero = QLineEdit()
        self.objeto = QTextEdit(); self.objeto.setMinimumHeight(80)
        self.municipio = QLineEdit()
        self.municipio.setReadOnly(True)
        self.municipio.setPlaceholderText("Preenchido automaticamente pelo cadastro do cliente")
        self.valor = QDoubleSpinBox(); self.valor.setMaximum(999999999999); self.valor.setDecimals(2)
        self.inicio = QLineEdit(); self.inicio.setPlaceholderText("dd/mm/aaaa")
        self.fim = QLineEdit(); self.fim.setPlaceholderText("dd/mm/aaaa")
        self.status = QComboBox(); self.status.addItems(["ATIVO", "EM REVISÃO", "ENCERRADO", "SUSPENSO"])
        self.reajuste = QLineEdit()
        self.observacao = QTextEdit(); self.observacao.setMinimumHeight(90)

        line_fields = [
            ("Cliente", self.cliente, 0, 0),
            ("Nome do contrato", self.nome, 0, 2),
            ("Número", self.numero, 1, 0),
            ("Município", self.municipio, 1, 2),
            ("Valor global", self.valor, 2, 0),
            ("Início", self.inicio, 2, 2),
            ("Fim", self.fim, 3, 0),
            ("Status", self.status, 3, 2),
            ("Índice reajuste", self.reajuste, 4, 0),
        ]
        for label, widget, row, col in line_fields:
            form.addWidget(QLabel(label), row, col)
            widget.setMinimumHeight(38)
            form.addWidget(widget, row, col + 1)

        form.addWidget(QLabel("Objeto contratual"), 5, 0)
        form.addWidget(self.objeto, 5, 1, 1, 3)

        form.addWidget(QLabel("Segmentos vinculados"), 6, 0)
        self.segmentos_lista = QListWidget()
        self.segmentos_lista.setMinimumHeight(150)
        self.segmentos_lista.setAlternatingRowColors(True)
        self.segmentos_lista.setToolTip("Selecione um ou mais segmentos/linhas contratuais vinculadas a este contrato.")
        segmentos_box = QVBoxLayout()
        segmentos_box.setContentsMargins(0, 0, 0, 0)
        segmentos_box.setSpacing(8)
        segmentos_box.addWidget(self.segmentos_lista)
        linha_segmentos = QHBoxLayout()
        self.btn_adicionar_segmento = self._button("Adicionar opção", "#2563EB")
        self.btn_adicionar_segmento.clicked.connect(self.adicionar_segmento)
        dica_segmentos = QLabel("Marque uma ou mais opções vinculadas ao contrato.")
        dica_segmentos.setStyleSheet("color:#64748B;font-size:11px;")
        linha_segmentos.addWidget(dica_segmentos, 1)
        linha_segmentos.addWidget(self.btn_adicionar_segmento)
        segmentos_box.addLayout(linha_segmentos)
        form.addLayout(segmentos_box, 6, 1, 1, 3)

        form.addWidget(QLabel("Observação"), 7, 0)
        form.addWidget(self.observacao, 7, 1, 1, 3)

        btns = QHBoxLayout()
        self.btn_salvar = self._button("Salvar contrato", "#0B3B75")
        self.btn_novo = self._button("Novo / Limpar", "#2563EB")
        self.btn_duplicar_contrato = self._button("Duplicar contrato", "#16A34A")
        self.btn_excluir_contrato = self._button("Excluir contrato", "#DC2626")
        self.btn_salvar.clicked.connect(self.salvar_contrato)
        self.btn_novo.clicked.connect(self.limpar_contrato)
        self.btn_duplicar_contrato.clicked.connect(self.duplicar_contrato)
        self.btn_excluir_contrato.clicked.connect(self.excluir_contrato)
        btns.addWidget(self.btn_salvar, 2)
        btns.addWidget(self.btn_novo, 1)
        btns.addWidget(self.btn_duplicar_contrato, 1)
        btns.addWidget(self.btn_excluir_contrato, 1)
        form.addLayout(btns, 8, 1, 1, 3)
        layout.addWidget(box)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "ID", "Cliente", "Contrato", "Número", "Município", "Status", "Valor", "Segmentos", "Aditivos"
        ])
        configurar_tabela_responsiva(self.table, stretch_columns=[2, 7], hidden_columns=[0])
        self.table.setMinimumHeight(320)
        self.table.cellClicked.connect(self.abrir_contrato_linha)
        self.table.cellDoubleClicked.connect(self.abrir_contrato_linha)
        layout.addWidget(self.table)
        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _aba_aditivos(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(12)

        info = QLabel("Selecione um contrato na aba Contrato principal para cadastrar ou visualizar seus aditivos.")
        info.setStyleSheet("color:#64748B;font-weight:700;")
        layout.addWidget(info)

        box = QGroupBox("Cadastro de aditivo vinculado ao contrato selecionado")
        form = QGridLayout(box)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.ad_numero = QLineEdit()
        self.ad_segmento = QComboBox()
        self.ad_objeto = QTextEdit(); self.ad_objeto.setMinimumHeight(85)
        self.ad_valor = QDoubleSpinBox(); self.ad_valor.setMaximum(999999999999); self.ad_valor.setDecimals(2)
        self.ad_prazo = QLineEdit(); self.ad_prazo.setPlaceholderText("Ex.: 90 dias / 12 meses / sem alteração")
        self.ad_status = QComboBox(); self.ad_status.addItems(["ATIVO", "EM REVISÃO", "ENCERRADO", "SUSPENSO"])
        self.ad_observacao = QTextEdit(); self.ad_observacao.setMinimumHeight(80)

        fields = [
            ("Número do aditivo", self.ad_numero, 0, 0),
            ("Segmento impactado", self.ad_segmento, 0, 2),
            ("Valor", self.ad_valor, 1, 0),
            ("Prazo", self.ad_prazo, 1, 2),
            ("Status", self.ad_status, 2, 0),
        ]
        for label, widget, row, col in fields:
            form.addWidget(QLabel(label), row, col)
            widget.setMinimumHeight(38)
            form.addWidget(widget, row, col + 1)

        form.addWidget(QLabel("Objeto do aditivo"), 3, 0)
        form.addWidget(self.ad_objeto, 3, 1, 1, 3)
        form.addWidget(QLabel("Observação"), 4, 0)
        form.addWidget(self.ad_observacao, 4, 1, 1, 3)

        btns = QHBoxLayout()
        self.btn_salvar_aditivo = self._button("Salvar aditivo", "#0B3B75")
        self.btn_limpar_aditivo = self._button("Limpar", "#2563EB")
        self.btn_excluir_aditivo = self._button("Excluir aditivo", "#DC2626")
        self.btn_salvar_aditivo.clicked.connect(self.salvar_aditivo)
        self.btn_limpar_aditivo.clicked.connect(self.limpar_aditivo)
        self.btn_excluir_aditivo.clicked.connect(self.excluir_aditivo)
        btns.addWidget(self.btn_salvar_aditivo, 2)
        btns.addWidget(self.btn_limpar_aditivo, 1)
        btns.addWidget(self.btn_excluir_aditivo, 1)
        form.addLayout(btns, 5, 1, 1, 3)
        layout.addWidget(box)

        self.table_aditivos = QTableWidget(0, 7)
        self.table_aditivos.setHorizontalHeaderLabels([
            "ID", "Número", "Segmento", "Objeto", "Valor", "Prazo", "Status"
        ])
        configurar_tabela_responsiva(self.table_aditivos, stretch_columns=[3], hidden_columns=[0])
        self.table_aditivos.setMinimumHeight(300)
        self.table_aditivos.cellClicked.connect(self.abrir_aditivo_linha)
        self.table_aditivos.cellDoubleClicked.connect(self.abrir_aditivo_linha)
        layout.addWidget(self.table_aditivos)
        layout.addStretch()
        scroll.setWidget(content)
        return scroll

    def _aba_consolidado(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)

        title = QLabel("Consolidado por segmento do contrato selecionado")
        title.setStyleSheet("font-size:16px;font-weight:900;color:#071A33;")
        layout.addWidget(title)

        self.table_consolidado = QTableWidget(0, 5)
        self.table_consolidado.setHorizontalHeaderLabels([
            "Segmento", "Aditivos", "Orçamentos", "CAPEX", "OPEX mensal"
        ])
        configurar_tabela_responsiva(self.table_consolidado, stretch_columns=[0])
        self.table_consolidado.setMinimumHeight(420)
        layout.addWidget(self.table_consolidado)
        return widget

    def carregar_clientes(self):
        atual = self.cliente.currentData()
        self.cliente.blockSignals(True)
        self.cliente.clear()
        self.cliente.addItem("Selecione o cliente", None)
        for item in self.repo.listar_clientes():
            uf = item["uf"] or ""
            self.cliente.addItem(f"{item['nome']} - {uf}", item["id"])
        if atual:
            idx = self.cliente.findData(atual)
            if idx >= 0:
                self.cliente.setCurrentIndex(idx)
        self.cliente.blockSignals(False)

    def carregar_segmentos(self):
        selecionados = self.segmentos_selecionados_ids()
        ad_segmento_atual = self.ad_segmento.currentData() if hasattr(self, "ad_segmento") else None
        self.segmentos_cache = self.repo.listar_segmentos()

        self.segmentos_lista.clear()
        self.ad_segmento.clear()
        self.ad_segmento.addItem("Selecione", None)

        for item in self.segmentos_cache:
            opt = QListWidgetItem(item["nome"])
            opt.setData(Qt.UserRole, item["id"])
            opt.setFlags(opt.flags() | Qt.ItemIsUserCheckable)
            opt.setCheckState(Qt.Checked if item["id"] in selecionados else Qt.Unchecked)
            self.segmentos_lista.addItem(opt)
            self.ad_segmento.addItem(item["nome"], item["id"])

        if ad_segmento_atual:
            idx = self.ad_segmento.findData(ad_segmento_atual)
            if idx >= 0:
                self.ad_segmento.setCurrentIndex(idx)

    def segmentos_selecionados_ids(self):
        if not hasattr(self, "segmentos_lista"):
            return set()
        ids = set()
        for i in range(self.segmentos_lista.count()):
            item = self.segmentos_lista.item(i)
            if item.checkState() == Qt.Checked:
                ids.add(item.data(Qt.UserRole))
        return ids

    def segmentos_selecionados_nomes(self):
        if not hasattr(self, "segmentos_lista"):
            return []
        nomes = []
        for i in range(self.segmentos_lista.count()):
            item = self.segmentos_lista.item(i)
            if item.checkState() == Qt.Checked:
                nomes.append(item.text())
        return nomes

    def selecionar_segmentos(self, segmentos_ids, segmentos_texto=""):
        segmentos_ids = set(segmentos_ids or [])
        texto = str(segmentos_texto or "")
        for i in range(self.segmentos_lista.count()):
            item = self.segmentos_lista.item(i)
            marcado = item.data(Qt.UserRole) in segmentos_ids or (texto and item.text() in texto)
            item.setCheckState(Qt.Checked if marcado else Qt.Unchecked)

    def adicionar_segmento(self):
        nome, ok = QInputDialog.getText(
            self,
            "Adicionar opção",
            "Nome do novo segmento/linha contratual:",
        )
        if not ok:
            return
        nome = nome.strip()
        if not nome:
            QMessageBox.warning(self, "Segmentos", "Informe o nome da nova opção.")
            return
        try:
            selecionados = self.segmentos_selecionados_ids()
            novo_id = self.repo.adicionar_segmento(nome)
            self.carregar_segmentos()
            selecionados.add(novo_id)
            self.selecionar_segmentos(selecionados)
            QMessageBox.information(self, "Segmentos", "Opção adicionada à lista.")
        except Exception as e:
            QMessageBox.critical(self, "Segmentos", f"Erro ao adicionar opção:\n{e}")

    def preencher_dados_cliente(self):
        """Cliente é a fonte oficial de município/UF no contrato.
        Evita digitação livre e divergências em relatórios/dashboard.
        """
        if self._carregando_tela or self._carregando_contrato:
            return
        cliente_id = self.cliente.currentData()
        if not cliente_id:
            self.municipio.clear()
            return

        item = self.repo.obter_cliente(cliente_id)
        if not item:
            return

        municipio = item["municipio"] or ""
        uf = item["uf"] or ""
        self.municipio.setText(f"{municipio}/{uf}" if municipio and uf else municipio)

        if not self.observacao.toPlainText().strip():
            partes = []
            if item["orgao_setor"]:
                partes.append(f"Órgão/Setor: {item['orgao_setor']}")
            if item["responsavel"]:
                partes.append(f"Responsável: {item['responsavel']}")
            if partes:
                self.observacao.setPlainText("\n".join(partes))

    def limpar_contrato(self):
        self.contrato_id = None
        self.aditivo_id = None
        for w in [self.nome, self.numero, self.municipio, self.inicio, self.fim, self.reajuste]:
            w.clear()
        self.objeto.clear()
        self.observacao.clear()
        self.valor.setValue(0)
        self.status.setCurrentText("ATIVO")
        self.selecionar_segmentos(set())
        self.limpar_aditivo()
        self.table_aditivos.setRowCount(0)
        self.table_consolidado.setRowCount(0)

    def salvar_contrato(self):
        if not self.nome.text().strip():
            QMessageBox.warning(self, "Contrato", "Informe o nome do contrato.")
            return
        segmentos_ids = list(self.segmentos_selecionados_ids())
        segmentos_texto = ", ".join(self.segmentos_selecionados_nomes())
        dados = {
            "cliente_id": self.cliente.currentData(),
            "nome": self.nome.text().strip(),
            "numero": self.numero.text().strip(),
            "objeto": self.objeto.toPlainText().strip(),
            "municipio": self.municipio.text().strip(),
            "valor_global": self.valor.value(),
            "inicio": self.inicio.text().strip(),
            "fim": self.fim.text().strip(),
            "status": self.status.currentText(),
            "indice_reajuste": self.reajuste.text().strip(),
            "segmentos_texto": segmentos_texto,
            "observacao": self.observacao.toPlainText().strip(),
        }
        self.contrato_id = self.repo.salvar_contrato(dados, segmentos_ids, self.contrato_id)
        self.load_data()
        self.carregar_aditivos()
        self.carregar_consolidado()
        QMessageBox.information(self, "Contrato", "Contrato salvo com sucesso.")

    def load_data(self):
        dados = self.repo.listar_contratos(self.busca.text())
        self.table.setRowCount(len(dados))
        for row, item in enumerate(dados):
            vals = [
                item["id"], item["cliente"], item["nome"], item["numero"], item["municipio"],
                item["status"], self._money(item["valor_global"]), item["segmentos"], item["total_aditivos"],
            ]
            for col, val in enumerate(vals):
                self.table.setItem(row, col, QTableWidgetItem(str(val or "")))
        ajustar_tabela_apos_carregar(self.table)

    def abrir_contrato_linha(self, row, col):
        item = self.table.item(row, 0)
        if not item:
            return
        self.carregar_contrato_por_id(int(item.text()))

    def carregar_contrato_por_id(self, contrato_id):
        self._carregando_contrato = True
        try:
            self.contrato_id = contrato_id
            contrato, segs = self.repo.obter_contrato(self.contrato_id)
            if not contrato:
                return
            self.nome.setText(contrato["nome"] or "")
            self.numero.setText(contrato["numero"] or "")
            self.objeto.setPlainText(contrato["objeto"] or "")
            self.municipio.setText(contrato["municipio"] or "")
            self.valor.setValue(float(contrato["valor_global"] or 0))
            self.inicio.setText(contrato["inicio"] or "")
            self.fim.setText(contrato["fim"] or "")
            self.status.setCurrentText(contrato["status"] or "ATIVO")
            self.reajuste.setText(contrato["indice_reajuste"] or "")
            self.observacao.setPlainText(contrato["observacao"] or "")
            if contrato["cliente_id"]:
                idx = self.cliente.findData(contrato["cliente_id"])
                if idx >= 0:
                    self.cliente.setCurrentIndex(idx)
                cliente = self.repo.obter_cliente(contrato["cliente_id"])
                if cliente:
                    municipio = cliente["municipio"] or ""
                    uf = cliente["uf"] or ""
                    self.municipio.setText(f"{municipio}/{uf}" if municipio and uf else municipio)
            self.selecionar_segmentos(segs, contrato["segmentos"])
            self.carregar_aditivos()
            self.carregar_consolidado()
        finally:
            self._carregando_contrato = False


    def _contar_vinculos_contrato(self, contrato_id):
        """Conta vínculos que impedem exclusão acidental do contrato."""
        contagens = {"orcamentos": 0, "aditivos": 0, "documentos": 0}
        try:
            with conn() as c:
                contagens["orcamentos"] = c.execute(
                    "SELECT COUNT(*) qtd FROM orcamentos WHERE contrato_id=?",
                    (contrato_id,)
                ).fetchone()["qtd"]
                contagens["aditivos"] = c.execute(
                    "SELECT COUNT(*) qtd FROM aditivos WHERE contrato_id=?",
                    (contrato_id,)
                ).fetchone()["qtd"]
                contagens["documentos"] = c.execute(
                    "SELECT COUNT(*) qtd FROM documentos WHERE contrato_id=?",
                    (contrato_id,)
                ).fetchone()["qtd"]
        except Exception:
            pass
        return contagens

    def excluir_contrato(self):
        """Exclui contrato somente se não houver vínculos críticos."""
        if not self.contrato_id:
            QMessageBox.warning(self, "Contrato", "Selecione um contrato para excluir.")
            return

        vinculos = self._contar_vinculos_contrato(self.contrato_id)
        bloqueios = []
        if vinculos.get("orcamentos", 0):
            bloqueios.append(f"{vinculos['orcamentos']} orçamento(s) vinculado(s)")
        if vinculos.get("aditivos", 0):
            bloqueios.append(f"{vinculos['aditivos']} aditivo(s) vinculado(s)")
        if vinculos.get("documentos", 0):
            bloqueios.append(f"{vinculos['documentos']} documento(s) vinculado(s)")

        if bloqueios:
            QMessageBox.warning(
                self,
                "Exclusão bloqueada",
                "Este contrato não pode ser excluído para evitar perda acidental de dados.\n\n"
                "Vínculos encontrados:\n- " + "\n- ".join(bloqueios) +
                "\n\nPara excluir este contrato, remova ou realoque primeiro os vínculos acima."
            )
            return

        resp = QMessageBox.question(
            self,
            "Excluir contrato",
            "Deseja realmente excluir este contrato?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        try:
            with conn() as c:
                c.execute("DELETE FROM contrato_segmentos WHERE contrato_id=?", (self.contrato_id,))
                c.execute("DELETE FROM contratos WHERE id=?", (self.contrato_id,))
                c.commit()
            QMessageBox.information(self, "Contrato", "Contrato excluído com sucesso.")
            self.limpar_contrato()
            self.load_data()
            self.carregar_consolidado()
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao excluir contrato:\n{str(e)}")

    def duplicar_contrato(self):
        """Duplica o contrato principal para facilitar segmentação da mesma empresa."""
        if not self.contrato_id:
            QMessageBox.warning(self, "Contrato", "Selecione um contrato para duplicar.")
            return

        contrato, segs = self.repo.obter_contrato(self.contrato_id)
        if not contrato:
            QMessageBox.warning(self, "Contrato", "Contrato selecionado não localizado.")
            return

        resp = QMessageBox.question(
            self,
            "Duplicar contrato",
            "Deseja duplicar este contrato?\n\n"
            "Serão copiados cliente, município, objeto, vigência, reajuste, observações e segmentos.\n"
            "Não serão copiados orçamentos, anexos nem aditivos.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        dados = {
            "cliente_id": contrato["cliente_id"],
            "nome": f"{contrato['nome'] or 'Contrato'} - Cópia",
            "numero": f"{contrato['numero'] or ''} - CÓPIA".strip(),
            "objeto": contrato["objeto"] or "",
            "municipio": contrato["municipio"] or "",
            "valor_global": float(contrato["valor_global"] or 0),
            "inicio": contrato["inicio"] or "",
            "fim": contrato["fim"] or "",
            "status": "EM REVISÃO",
            "indice_reajuste": contrato["indice_reajuste"] or "",
            "segmentos_texto": contrato["segmentos"] or "",
            "observacao": (contrato["observacao"] or "") + "\n\nContrato duplicado para segmentação/revisão.",
        }

        try:
            novo_id = self.repo.salvar_contrato(dados, list(segs), None)
            self.contrato_id = novo_id
            self.load_data()
            self.carregar_contrato_por_id(novo_id)
            QMessageBox.information(self, "Contrato", "Contrato duplicado com sucesso.")
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao duplicar contrato:\n{str(e)}")

    def limpar_aditivo(self):
        self.aditivo_id = None
        self.ad_numero.clear()
        self.ad_objeto.clear()
        self.ad_valor.setValue(0)
        self.ad_prazo.clear()
        self.ad_status.setCurrentText("ATIVO")
        self.ad_observacao.clear()
        if self.ad_segmento.count() > 0:
            self.ad_segmento.setCurrentIndex(0)

    def salvar_aditivo(self):
        if not self.contrato_id:
            QMessageBox.warning(self, "Aditivo", "Selecione ou salve um contrato antes de cadastrar aditivo.")
            return
        if not self.ad_numero.text().strip():
            QMessageBox.warning(self, "Aditivo", "Informe o número do aditivo.")
            return
        dados = {
            "contrato_id": self.contrato_id,
            "segmento_id": self.ad_segmento.currentData(),
            "numero_aditivo": self.ad_numero.text().strip(),
            "objeto": self.ad_objeto.toPlainText().strip(),
            "valor": self.ad_valor.value(),
            "prazo": self.ad_prazo.text().strip(),
            "status": self.ad_status.currentText(),
            "observacao": self.ad_observacao.toPlainText().strip(),
        }
        self.aditivo_id = self.repo.salvar_aditivo(dados, self.aditivo_id)
        self.carregar_aditivos()
        self.carregar_consolidado()
        self.load_data()
        QMessageBox.information(self, "Aditivo", "Aditivo salvo com sucesso.")

    def carregar_aditivos(self):
        if not self.contrato_id:
            self.table_aditivos.setRowCount(0)
            return
        dados = self.repo.listar_aditivos(self.contrato_id)
        self.table_aditivos.setRowCount(len(dados))
        for row, item in enumerate(dados):
            vals = [
                item["id"], item["numero_aditivo"], item["segmento"], item["objeto"],
                self._money(item["valor"]), item["prazo"], item["status"],
            ]
            for col, val in enumerate(vals):
                self.table_aditivos.setItem(row, col, QTableWidgetItem(str(val or "")))
        ajustar_tabela_apos_carregar(self.table_aditivos)

    def abrir_aditivo_linha(self, row, col):
        item = self.table_aditivos.item(row, 0)
        if not item:
            return
        self.aditivo_id = int(item.text())
        aditivos = self.repo.listar_aditivos(self.contrato_id)
        selecionado = None
        for ad in aditivos:
            if ad["id"] == self.aditivo_id:
                selecionado = ad
                break
        if not selecionado:
            return
        self.ad_numero.setText(selecionado["numero_aditivo"] or "")
        idx = self.ad_segmento.findData(selecionado["segmento_id"])
        self.ad_segmento.setCurrentIndex(idx if idx >= 0 else 0)
        self.ad_objeto.setPlainText(selecionado["objeto"] or "")
        self.ad_valor.setValue(float(selecionado["valor"] or 0))
        self.ad_prazo.setText(selecionado["prazo"] or "")
        self.ad_status.setCurrentText(selecionado["status"] or "ATIVO")
        self.ad_observacao.setPlainText(selecionado["observacao"] or "")

    def excluir_aditivo(self):
        if not self.aditivo_id:
            QMessageBox.warning(self, "Aditivo", "Selecione um aditivo para excluir.")
            return
        resp = QMessageBox.question(
            self,
            "Excluir aditivo",
            "Deseja realmente excluir este aditivo?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        self.repo.excluir_aditivo(self.aditivo_id)
        self.limpar_aditivo()
        self.carregar_aditivos()
        self.carregar_consolidado()
        self.load_data()

    def carregar_consolidado(self):
        if not self.contrato_id:
            self.table_consolidado.setRowCount(0)
            return
        dados = self.repo.consolidado_segmentos(self.contrato_id)
        self.table_consolidado.setRowCount(len(dados))
        for row, item in enumerate(dados):
            vals = [
                item["segmento"],
                item["total_aditivos"],
                item["total_orcamentos"],
                self._money(item["total_capex"]),
                self._money(item["total_opex"]),
            ]
            for col, val in enumerate(vals):
                self.table_consolidado.setItem(row, col, QTableWidgetItem(str(val or "")))
        ajustar_tabela_apos_carregar(self.table_consolidado)
