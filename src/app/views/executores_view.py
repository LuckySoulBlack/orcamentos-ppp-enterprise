from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QTextEdit, QPushButton, QCheckBox, QGroupBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QAbstractItemView, QComboBox
)

from core.database import conn
from services import executor_service
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar


class ExecutoresView(QWidget):
    def __init__(self):
        super().__init__()
        self.executor_id = None
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        titulo = QLabel("Cadastro de executores")
        titulo.setStyleSheet("font-size:24px;font-weight:950;color:#071A33;")
        sub = QLabel("Cadastre equipes, técnicos ou terceiros responsáveis por registrar a execução das ordens de serviço.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#64748B;font-weight:700;")
        root.addWidget(titulo)
        root.addWidget(sub)

        box = QGroupBox("Executor")
        grid = QGridLayout(box)
        self.nome = QLineEdit()
        self.documento = QLineEdit()
        self.telefone = QLineEdit()
        self.email = QLineEdit()
        self.funcao = QLineEdit()
        self.empresa_tipo = QComboBox()
        self.empresa_tipo.addItem("Empresa cadastrada", "CADASTRADA")
        self.empresa_tipo.addItem("Terceiro", "TERCEIRO")
        self.empresa_cadastrada = QComboBox()
        self.empresa_terceiro = QLineEdit()
        self.empresa_terceiro.setPlaceholderText("Nome da empresa terceira")
        self.ativo = QCheckBox("Ativo")
        self.ativo.setChecked(True)
        self.obs = QTextEdit()
        self.obs.setMinimumHeight(70)
        campos = [
            ("Nome", self.nome), ("CPF/CNPJ ou matrícula", self.documento),
            ("Telefone", self.telefone), ("E-mail", self.email),
            ("Função", self.funcao), ("Vínculo obrigatório", self.empresa_tipo),
            ("Empresa cadastrada", self.empresa_cadastrada), ("Empresa terceira", self.empresa_terceiro),
        ]
        for i, (label, widget) in enumerate(campos):
            row = i // 2
            col = (i % 2) * 2
            grid.addWidget(QLabel(label), row, col)
            grid.addWidget(widget, row, col + 1)
        grid.addWidget(self.ativo, 3, 1)
        grid.addWidget(QLabel("Observação"), 4, 0)
        grid.addWidget(self.obs, 4, 1, 1, 3)
        root.addWidget(box)

        botoes = QHBoxLayout()
        self.btn_salvar = QPushButton("Salvar executor")
        self.btn_limpar = QPushButton("Novo / limpar")
        self.btn_excluir = QPushButton("Inativar executor")
        self.btn_excluir.setObjectName("Danger")
        self.btn_salvar.clicked.connect(self.salvar)
        self.btn_limpar.clicked.connect(self.limpar)
        self.btn_excluir.clicked.connect(self.excluir)
        botoes.addWidget(self.btn_salvar, 2)
        botoes.addWidget(self.btn_limpar)
        botoes.addWidget(self.btn_excluir)
        root.addLayout(botoes)

        self.tabela = QTableWidget(0, 8)
        self.tabela.setHorizontalHeaderLabels(["ID", "Nome", "Função", "Empresa", "Telefone", "E-mail", "Ativo", "Observação"])
        configurar_tabela_responsiva(self.tabela, stretch_columns=[1, 7], hidden_columns=[0])
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.cellClicked.connect(self.selecionar)
        root.addWidget(self.tabela, 1)
        self.empresa_tipo.currentIndexChanged.connect(self._atualizar_empresa_visivel)
        self.carregar_empresas()
        self._atualizar_empresa_visivel()
        self.carregar()

    def carregar_empresas(self):
        atual = self.empresa_cadastrada.currentData()
        self.empresa_cadastrada.clear()
        with conn() as c:
            rows = c.execute("SELECT id, razao, fantasia FROM empresa ORDER BY id").fetchall()
        for row in rows:
            nome = row["fantasia"] or row["razao"] or f"Empresa {row['id']}"
            self.empresa_cadastrada.addItem(nome, row["id"])
        if atual is not None:
            idx = self.empresa_cadastrada.findData(atual)
            if idx >= 0:
                self.empresa_cadastrada.setCurrentIndex(idx)

    def _atualizar_empresa_visivel(self):
        cadastrada = self.empresa_tipo.currentData() == "CADASTRADA"
        self.empresa_cadastrada.setEnabled(cadastrada)
        self.empresa_terceiro.setEnabled(not cadastrada)

    def carregar(self):
        rows = executor_service.listar_executores()
        self.tabela.setRowCount(len(rows))
        for r, row in enumerate(rows):
            valores = [row["id"], row["nome"], row["funcao"], row["empresa"], row["telefone"], row["email"], "Sim" if row["ativo"] else "Não", row["observacao"]]
            for c, valor in enumerate(valores):
                item = QTableWidgetItem(str(valor or ""))
                item.setData(Qt.UserRole, row["id"])
                self.tabela.setItem(r, c, item)
        ajustar_tabela_apos_carregar(self.tabela)

    def limpar(self):
        self.executor_id = None
        for w in [self.nome, self.documento, self.telefone, self.email, self.funcao, self.empresa_terceiro]:
            w.clear()
        self.empresa_tipo.setCurrentIndex(0)
        self._atualizar_empresa_visivel()
        self.obs.clear()
        self.ativo.setChecked(True)

    def selecionar(self, row, _col):
        self.executor_id = self.tabela.item(row, 0).data(Qt.UserRole)
        dados = {r["id"]: r for r in executor_service.listar_executores()}.get(self.executor_id)
        if not dados:
            return
        self.nome.setText(dados["nome"] or "")
        self.documento.setText(dados["documento"] or "")
        self.telefone.setText(dados["telefone"] or "")
        self.email.setText(dados["email"] or "")
        self.funcao.setText(dados["funcao"] or "")
        tipo = dados["empresa_tipo"] or ("CADASTRADA" if dados["empresa_id"] else "TERCEIRO")
        idx_tipo = self.empresa_tipo.findData(tipo)
        self.empresa_tipo.setCurrentIndex(idx_tipo if idx_tipo >= 0 else 1)
        idx_empresa = self.empresa_cadastrada.findData(dados["empresa_id"])
        if idx_empresa >= 0:
            self.empresa_cadastrada.setCurrentIndex(idx_empresa)
        self.empresa_terceiro.setText(dados["empresa"] or "")
        self._atualizar_empresa_visivel()
        self.obs.setPlainText(dados["observacao"] or "")
        self.ativo.setChecked(bool(dados["ativo"]))

    def salvar(self):
        try:
            empresa_tipo = self.empresa_tipo.currentData()
            if empresa_tipo == "CADASTRADA":
                empresa_nome = self.empresa_cadastrada.currentText().strip()
                empresa_id = self.empresa_cadastrada.currentData()
            else:
                empresa_nome = self.empresa_terceiro.text().strip()
                empresa_id = None
            executor_service.salvar_executor({
                "nome": self.nome.text(), "documento": self.documento.text(),
                "telefone": self.telefone.text(), "email": self.email.text(),
                "funcao": self.funcao.text(), "empresa": empresa_nome,
                "empresa_tipo": empresa_tipo, "empresa_id": empresa_id,
                "ativo": self.ativo.isChecked(), "observacao": self.obs.toPlainText(),
            }, self.executor_id)
            self.limpar()
            self.carregar()
            QMessageBox.information(self, "Executores", "Executor salvo.")
        except Exception as e:
            QMessageBox.critical(self, "Executores", f"Erro ao salvar executor:\n{e}")

    def excluir(self):
        if not self.executor_id:
            return
        executor_service.excluir_executor(self.executor_id)
        self.limpar()
        self.carregar()

    def refresh(self):
        self.carregar()
