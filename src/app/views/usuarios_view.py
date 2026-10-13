from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QGroupBox, QTableWidget,
    QTableWidgetItem, QMessageBox, QAbstractItemView, QTabWidget, QHeaderView,
    QDialog, QDialogButtonBox,
)

from services import auth_service
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar


ADMIN_TELAS = [
    ("dashboard", "Dashboard"),
    ("orcamentos", "Criar/editar orçamentos"),
    ("meus_orcamentos", "Meus orçamentos"),
    ("ordens_servico", "Ordens de serviço"),
    ("usuarios", "Usuários e permissões"),
    ("contratos", "Contratos PPP"),
    ("clientes", "Clientes"),
    ("empresa", "Empresa"),
    ("sinapi", "SINAPI"),
    ("relatorios", "Relatórios"),
    ("config", "Configurações"),
]

OS_TELAS = [
    ("os_execucao", "Ordens de serviço"),
    ("os_config", "Configurações do banco"),
    ("os_executores", "Cadastro de executores"),
    ("os_mapa", "Mapa de execuções"),
    ("os_kanban", "Kanban de obras"),
]


class PermissoesDialog(QDialog):
    def __init__(self, permissoes, acesso_orcamentos, acesso_os, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Permissões por tela")
        self.resize(760, 520)
        self.checks = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        titulo = QLabel("Permissões por tela")
        titulo.setStyleSheet("font-size:22px;font-weight:950;color:#071A33;")
        sub = QLabel("Marque somente as telas que este usuário poderá acessar.")
        sub.setStyleSheet("color:#64748B;font-weight:700;")
        root.addWidget(titulo)
        root.addWidget(sub)

        cols = QHBoxLayout()
        cols.setSpacing(14)
        cols.addWidget(self._grupo("Orçamentos PPP", ADMIN_TELAS, acesso_orcamentos), 1)
        cols.addWidget(self._grupo("OS PPP", OS_TELAS, acesso_os), 1)
        root.addLayout(cols, 1)

        permissoes = set(permissoes or [])
        if "*" in permissoes:
            permissoes = set(self.checks)
        for key, chk in self.checks.items():
            chk.setChecked(key in permissoes)

        botoes = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        root.addWidget(botoes)

    def _grupo(self, titulo, telas, ativo):
        box = QGroupBox(titulo)
        layout = QVBoxLayout(box)
        layout.setSpacing(8)
        for key, label in telas:
            chk = QCheckBox(label)
            chk.setEnabled(bool(ativo))
            self.checks[key] = chk
            layout.addWidget(chk)
        layout.addStretch()
        return box

    def selecionadas(self):
        return [key for key, chk in self.checks.items() if chk.isChecked() and chk.isEnabled()]


class UsuariosView(QWidget):
    def __init__(self):
        super().__init__()
        self.usuario_id = None
        self.permissoes_atual = set()

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        titulo = QLabel("Usuários e permissões")
        titulo.setStyleSheet("font-size:26px;font-weight:950;color:#071A33;")
        sub = QLabel("Cadastre usuários, defina os sistemas liberados e ajuste permissões em popup quando necessário.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#64748B;font-weight:700;")
        root.addWidget(titulo)
        root.addWidget(sub)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border:1px solid #D7E2EF;
                border-radius:10px;
                background:white;
            }
            QTabBar::tab {
                background:#F8FBFF;
                color:#435674;
                border:1px solid #E4ECF7;
                padding:11px 18px;
                min-width:170px;
                font-weight:800;
            }
            QTabBar::tab:selected {
                background:white;
                color:#0B3B75;
                border-bottom:3px solid #0B3B75;
            }
        """)
        root.addWidget(self.tabs, 1)

        self._montar_aba_cadastro()
        self._montar_aba_lista()
        self.limpar()
        self.carregar()

    def _montar_aba_cadastro(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        box = QGroupBox("Cadastro de usuário")
        grid = QGridLayout(box)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self.nome = QLineEdit()
        self.usuario = QLineEdit()
        self.email = QLineEdit()
        self.senha = QLineEdit()
        self.senha.setEchoMode(QLineEdit.Password)
        self.btn_ver_senha = QPushButton("Ver")
        self.btn_ver_senha.setFixedWidth(76)
        self.btn_ver_senha.setToolTip("Mostrar/ocultar senha")
        self.btn_ver_senha.clicked.connect(self.alternar_senha)

        self.perfil = QComboBox()
        self.perfil.addItems(["ADMIN", "GESTOR", "OPERACIONAL"])
        self.perfil.currentTextChanged.connect(self.aplicar_preset_perfil)
        self.ativo = QCheckBox("Usuário ativo")
        self.ativo.setChecked(True)
        self.acesso_orcamentos = QCheckBox("Acessa Orçamentos PPP")
        self.acesso_os = QCheckBox("Acessa OS PPP")
        self.acesso_orcamentos.toggled.connect(self.atualizar_acessos)
        self.acesso_os.toggled.connect(self.atualizar_acessos)

        senha_linha = QHBoxLayout()
        senha_linha.setContentsMargins(0, 0, 0, 0)
        senha_linha.setSpacing(6)
        senha_linha.addWidget(self.senha, 1)
        senha_linha.addWidget(self.btn_ver_senha)

        grid.addWidget(QLabel("Nome"), 0, 0)
        grid.addWidget(self.nome, 0, 1)
        grid.addWidget(QLabel("Usuário"), 0, 2)
        grid.addWidget(self.usuario, 0, 3)
        grid.addWidget(QLabel("E-mail de login"), 1, 0)
        grid.addWidget(self.email, 1, 1)
        grid.addWidget(QLabel("Senha"), 1, 2)
        grid.addLayout(senha_linha, 1, 3)
        grid.addWidget(QLabel("Perfil"), 2, 0)
        grid.addWidget(self.perfil, 2, 1)
        grid.addWidget(self.ativo, 2, 2)

        sistemas = QHBoxLayout()
        sistemas.setSpacing(18)
        sistemas.addWidget(self.acesso_orcamentos)
        sistemas.addWidget(self.acesso_os)
        sistemas.addStretch()
        grid.addLayout(sistemas, 3, 0, 1, 4)
        layout.addWidget(box)

        perm_box = QGroupBox("Acessos e permissões")
        perm_layout = QVBoxLayout(perm_box)
        self.permissoes_resumo = QLabel()
        self.permissoes_resumo.setWordWrap(True)
        self.permissoes_resumo.setStyleSheet("""
            QLabel {
                color:#334155;
                background:#F8FBFF;
                border:1px solid #E4ECF7;
                border-radius:8px;
                padding:10px;
                font-weight:700;
            }
        """)
        self.btn_permissoes = QPushButton("Ajustar permissões por tela")
        self.btn_permissoes.setObjectName("Secondary")
        self.btn_permissoes.clicked.connect(self.abrir_permissoes)
        perm_layout.addWidget(self.permissoes_resumo)
        perm_layout.addWidget(self.btn_permissoes, 0, Qt.AlignRight)
        layout.addWidget(perm_box)

        botoes = QHBoxLayout()
        self.btn_salvar = QPushButton("Salvar usuário")
        self.btn_limpar = QPushButton("Novo / limpar")
        self.btn_excluir = QPushButton("Excluir usuário")
        self.btn_excluir.setObjectName("Danger")
        self.btn_salvar.clicked.connect(self.salvar)
        self.btn_limpar.clicked.connect(self.limpar)
        self.btn_excluir.clicked.connect(self.excluir)
        botoes.addWidget(self.btn_salvar, 2)
        botoes.addWidget(self.btn_limpar)
        botoes.addWidget(self.btn_excluir)
        layout.addLayout(botoes)
        layout.addStretch()

        self.tabs.addTab(tab, "Cadastro")

    def _montar_aba_lista(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        self.lista_status = QLabel("Usuários cadastrados")
        self.lista_status.setStyleSheet("font-size:15px;font-weight:900;color:#071A33;")
        self.btn_atualizar = QPushButton("Atualizar lista")
        self.btn_editar = QPushButton("Editar selecionado")
        self.btn_atualizar.clicked.connect(self.carregar)
        self.btn_editar.clicked.connect(self.editar_selecionado)
        top.addWidget(self.lista_status, 1)
        top.addWidget(self.btn_atualizar)
        top.addWidget(self.btn_editar)
        layout.addLayout(top)

        self.tabela = QTableWidget(0, 9)
        self.tabela.setHorizontalHeaderLabels([
            "ID", "Nome", "Usuário", "E-mail", "Perfil", "Orçamentos", "OS", "Ativo", "Criado em",
        ])
        configurar_tabela_responsiva(self.tabela, stretch_columns=[1, 3], hidden_columns=[0])
        self.tabela.setMinimumHeight(420)
        self.tabela.verticalHeader().setDefaultSectionSize(38)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.cellClicked.connect(self.selecionar)
        self.tabela.cellDoubleClicked.connect(lambda _row, _col: self.editar_selecionado())
        layout.addWidget(self.tabela, 1)

        self.tabs.addTab(tab, "Usuários cadastrados")

    def _todos_keys(self):
        return {key for key, _ in ADMIN_TELAS + OS_TELAS}

    def _admin_keys(self):
        return {key for key, _ in ADMIN_TELAS}

    def _os_keys(self):
        return {key for key, _ in OS_TELAS}

    def _permissoes_marcadas(self):
        return sorted(self._permissoes_filtradas())

    def _permissoes_filtradas(self):
        permissoes = set(self.permissoes_atual)
        if self.acesso_orcamentos.isChecked():
            permitidas = set(self._admin_keys())
        else:
            permitidas = set()
        if self.acesso_os.isChecked():
            permitidas |= self._os_keys()
        return permissoes & permitidas

    def _set_permissoes(self, permissoes):
        permissoes = set(permissoes or [])
        if "*" in permissoes:
            permissoes = self._todos_keys()
        self.permissoes_atual = permissoes & self._todos_keys()
        self.atualizar_acessos()

    def aplicar_preset_perfil(self):
        perfil = self.perfil.currentText()
        if perfil == "ADMIN":
            self.acesso_orcamentos.setChecked(True)
            self.acesso_os.setChecked(True)
            self._set_permissoes(["*"])
            return
        if perfil == "GESTOR":
            self.acesso_orcamentos.setChecked(True)
            self.acesso_os.setChecked(True)
            self._set_permissoes([
                "dashboard", "orcamentos", "meus_orcamentos", "ordens_servico",
                "contratos", "clientes", "relatorios", "os_execucao",
                "os_mapa", "os_kanban",
            ])
            return
        self.acesso_orcamentos.setChecked(False)
        self.acesso_os.setChecked(True)
        self._set_permissoes(["os_execucao", "os_mapa", "os_kanban"])

    def atualizar_acessos(self):
        self.permissoes_atual = self._permissoes_filtradas()
        self.atualizar_resumo_permissoes()

    def atualizar_resumo_permissoes(self):
        permissoes = self._permissoes_filtradas()
        admin_count = len(permissoes & self._admin_keys())
        os_count = len(permissoes & self._os_keys())
        sistemas = []
        if self.acesso_orcamentos.isChecked():
            sistemas.append(f"Orçamentos PPP: {admin_count} tela(s)")
        if self.acesso_os.isChecked():
            sistemas.append(f"OS PPP: {os_count} tela(s)")
        if not sistemas:
            texto = "Nenhum sistema liberado. Libere pelo menos um sistema antes de salvar."
        else:
            texto = " | ".join(sistemas)
        self.permissoes_resumo.setText(texto)

    def abrir_permissoes(self):
        if not self.acesso_orcamentos.isChecked() and not self.acesso_os.isChecked():
            QMessageBox.information(self, "Permissões", "Libere pelo menos um sistema antes de ajustar as telas.")
            return
        dialog = PermissoesDialog(
            self._permissoes_filtradas(),
            self.acesso_orcamentos.isChecked(),
            self.acesso_os.isChecked(),
            self,
        )
        if dialog.exec() == QDialog.Accepted:
            self.permissoes_atual = set(dialog.selecionadas())
            self.atualizar_resumo_permissoes()

    def carregar(self):
        rows = auth_service.listar_usuarios()
        self.lista_status.setText(f"Usuários cadastrados: {len(rows)}")
        self.tabela.setRowCount(len(rows))
        for r, row in enumerate(rows):
            valores = [
                row["id"], row["nome"], row["usuario"], row["email"], row["perfil"],
                "Sim" if row["acesso_orcamentos"] else "Não",
                "Sim" if row["acesso_os"] else "Não",
                "Sim" if row["ativo"] else "Não",
                row["criado_em"],
            ]
            for c, valor in enumerate(valores):
                item = QTableWidgetItem(str(valor or ""))
                item.setData(Qt.UserRole, row["id"])
                item.setData(Qt.UserRole + 1, row["senha"] or "")
                item.setData(Qt.UserRole + 2, dict(row))
                self.tabela.setItem(r, c, item)
        ajustar_tabela_apos_carregar(self.tabela)
        self._ajustar_colunas_lista()

    def _ajustar_colunas_lista(self):
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        larguras = {2: 130, 4: 120, 5: 110, 6: 90, 7: 90, 8: 160}
        for col, width in larguras.items():
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            self.tabela.setColumnWidth(col, max(self.tabela.columnWidth(col), width))

    def limpar(self):
        self.usuario_id = None
        for w in [self.nome, self.usuario, self.email, self.senha]:
            w.clear()
        self.perfil.setCurrentText("OPERACIONAL")
        self.ativo.setChecked(True)
        self.aplicar_preset_perfil()
        self.tabela.clearSelection()

    def selecionar(self, row, _col):
        item = self.tabela.item(row, 0)
        if not item:
            return
        dados = item.data(Qt.UserRole + 2)
        self.usuario_id = dados["id"]
        self.nome.setText(dados["nome"] or "")
        self.usuario.setText(dados["usuario"] or "")
        self.email.setText(dados["email"] or "")
        self.senha.setText(dados["senha"] or "")
        self.perfil.blockSignals(True)
        self.perfil.setCurrentText(dados["perfil"] or "OPERACIONAL")
        self.perfil.blockSignals(False)
        self.acesso_orcamentos.setChecked(bool(dados["acesso_orcamentos"]))
        self.acesso_os.setChecked(bool(dados["acesso_os"]))
        self.ativo.setChecked(bool(dados["ativo"]))
        self._set_permissoes(auth_service.normalizar_permissoes(dados["permissoes"]))

    def editar_selecionado(self):
        row = self.tabela.currentRow()
        if row < 0:
            QMessageBox.information(self, "Usuários", "Selecione um usuário na lista.")
            return
        self.selecionar(row, 0)
        self.tabs.setCurrentIndex(0)

    def alternar_senha(self):
        visivel = self.senha.echoMode() == QLineEdit.Normal
        self.senha.setEchoMode(QLineEdit.Password if visivel else QLineEdit.Normal)
        self.btn_ver_senha.setText("Ver" if visivel else "Ocultar")

    def salvar(self):
        try:
            auth_service.salvar_usuario(
                self.nome.text(), self.usuario.text(), self.email.text(),
                self.senha.text(), self.perfil.currentText(), self.ativo.isChecked(),
                self.usuario_id, self.acesso_orcamentos.isChecked(), self.acesso_os.isChecked(),
                self._permissoes_marcadas(),
            )
            self.limpar()
            self.carregar()
            self.tabs.setCurrentIndex(1)
            QMessageBox.information(self, "Usuários", "Usuário e permissões salvos com sucesso.")
        except Exception as e:
            QMessageBox.critical(self, "Usuários", f"Erro ao salvar usuário:\n{e}")

    def excluir(self):
        if not self.usuario_id:
            return
        if QMessageBox.question(self, "Usuários", "Excluir este usuário?") != QMessageBox.Yes:
            return
        try:
            auth_service.remover_usuario(self.usuario_id)
            self.limpar()
            self.carregar()
            self.tabs.setCurrentIndex(1)
        except Exception as e:
            QMessageBox.critical(self, "Usuários", f"Erro ao excluir usuário:\n{e}")

    def refresh(self):
        self.carregar()
