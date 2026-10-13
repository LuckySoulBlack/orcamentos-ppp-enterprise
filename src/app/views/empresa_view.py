from pathlib import Path
import os
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import *

from core import database
from core.database import conn
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar


class EmpresaView(QWidget):
    """Cadastro enterprise da concessionária.

    Pacote 1 - Governança PPP/TCE:
    - mantém compatibilidade com os campos antigos da tabela empresa;
    - adiciona responsáveis técnicos, gestor/fiscal do contrato e múltiplos representantes legais;
    - não apaga dados existentes.
    """

    def __init__(self):
        super().__init__()
        self.selected_rep_id = None
        self._build()
        self.carregar()
        self.carregar_representantes()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        title = QLabel("Cadastro da Empresa / Concessionária")
        title.setObjectName("Title")
        root.addWidget(title)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._aba_institucional(), "Dados institucionais")
        self.tabs.addTab(self._aba_representantes(), "Representantes legais")
        self.tabs.addTab(self._aba_tecnico(), "Responsável técnico")
        self.tabs.addTab(self._aba_gestao_contrato(), "Gestor / Fiscal")
        self.tabs.addTab(self._aba_assinaturas(), "Assinaturas e arquivos")
        root.addWidget(self.tabs)

        row = QHBoxLayout()
        row.addStretch()
        self.btn_salvar = QPushButton("Salvar cadastro da empresa")
        self.btn_salvar.setMinimumHeight(42)
        self.btn_salvar.clicked.connect(self.salvar)
        row.addWidget(self.btn_salvar)
        root.addLayout(row)

    def _line(self, placeholder=""):
        w = QLineEdit()
        w.setMinimumHeight(36)
        if placeholder:
            w.setPlaceholderText(placeholder)
        return w

    def _file_row(self, line_edit, title, filter_="Arquivos (*.*)"):
        row = QHBoxLayout()
        btn = QPushButton("Selecionar")
        btn.setObjectName("Secondary")
        btn.clicked.connect(lambda: self._selecionar_arquivo(line_edit, title, filter_))
        row.addWidget(line_edit, 1)
        row.addWidget(btn)
        return row

    def _aba_institucional(self):
        page = QWidget(); form = QFormLayout(page)
        form.setVerticalSpacing(10)
        self.razao = self._line()
        self.fantasia = self._line()
        self.cnpj = self._line()
        self.endereco = self._line()
        self.municipio = self._line()
        self.uf = self._line()
        self.telefone = self._line()
        self.email = self._line()
        self.site = self._line()
        self.inscricao_municipal = self._line()
        self.observacao_institucional = QTextEdit(); self.observacao_institucional.setMinimumHeight(90)
        self.logo_path = self._line()

        for label, widget in [
            ("Razão Social", self.razao),
            ("Nome Fantasia", self.fantasia),
            ("CNPJ", self.cnpj),
            ("Endereço", self.endereco),
            ("Município", self.municipio),
            ("UF", self.uf),
            ("Telefone", self.telefone),
            ("E-mail", self.email),
            ("Site", self.site),
            ("Inscrição Municipal", self.inscricao_municipal),
        ]:
            form.addRow(label, widget)
        form.addRow("Logo", self._file_row(self.logo_path, "Selecionar logo", "Imagens (*.png *.jpg *.jpeg *.bmp)"))
        form.addRow("Observação institucional", self.observacao_institucional)
        return page

    def _aba_representantes(self):
        page = QWidget(); layout = QVBoxLayout(page)
        info = QLabel("Cadastre múltiplos representantes legais/autorizados para assinatura. Útil para empresas S/A.")
        info.setStyleSheet("color:#64748B;font-weight:700;")
        layout.addWidget(info)

        box = QGroupBox("Representante legal / assinante autorizado")
        form = QGridLayout(box)
        self.rep_nome = self._line()
        self.rep_cargo = self._line()
        self.rep_cpf = self._line()
        self.rep_email = self._line()
        self.rep_telefone = self._line()
        self.rep_assinatura_path = self._line()
        self.rep_observacao = QTextEdit(); self.rep_observacao.setMinimumHeight(62)
        self.rep_ativo = QCheckBox("Ativo para assinatura")
        self.rep_ativo.setChecked(True)

        campos = [
            ("Nome", self.rep_nome), ("Cargo", self.rep_cargo),
            ("CPF", self.rep_cpf), ("E-mail", self.rep_email),
            ("Telefone", self.rep_telefone),
        ]
        for i, (label, widget) in enumerate(campos):
            form.addWidget(QLabel(label), (i // 2) * 2, i % 2)
            form.addWidget(widget, (i // 2) * 2 + 1, i % 2)
        row_file = self._file_row(self.rep_assinatura_path, "Selecionar assinatura", "Imagens (*.png *.jpg *.jpeg *.bmp)")
        form.addWidget(QLabel("Assinatura PNG/JPG"), 6, 0, 1, 2)
        form.addLayout(row_file, 7, 0, 1, 2)
        form.addWidget(self.rep_ativo, 8, 0)
        form.addWidget(QLabel("Observação"), 9, 0, 1, 2)
        form.addWidget(self.rep_observacao, 10, 0, 1, 2)

        btns = QHBoxLayout()
        self.btn_rep_add = QPushButton("Adicionar / Atualizar representante")
        self.btn_rep_limpar = QPushButton("Limpar")
        self.btn_rep_excluir = QPushButton("Excluir representante")
        self.btn_rep_excluir.setObjectName("Danger")
        self.btn_rep_add.clicked.connect(self.salvar_representante)
        self.btn_rep_limpar.clicked.connect(self.limpar_representante)
        self.btn_rep_excluir.clicked.connect(self.excluir_representante)
        btns.addWidget(self.btn_rep_add, 2)
        btns.addWidget(self.btn_rep_limpar, 1)
        btns.addWidget(self.btn_rep_excluir, 1)
        form.addLayout(btns, 11, 0, 1, 2)
        layout.addWidget(box)

        self.tabela_representantes = QTableWidget(0, 7)
        self.tabela_representantes.setHorizontalHeaderLabels(["ID", "Nome", "Cargo", "CPF", "E-mail", "Telefone", "Ativo"])
        configurar_tabela_responsiva(self.tabela_representantes, stretch_columns=[1, 4], hidden_columns=[0])
        self.tabela_representantes.cellClicked.connect(self.selecionar_representante)
        layout.addWidget(self.tabela_representantes)
        return page

    def _aba_tecnico(self):
        page = QWidget(); form = QFormLayout(page)
        form.setVerticalSpacing(10)
        self.responsavel_tecnico = self._line()
        self.registro_tecnico = self._line("CREA / CAU / CFT")
        self.responsavel_tecnico_cpf = self._line()
        self.responsavel_tecnico_cargo = self._line()
        self.responsavel_tecnico_especialidade = self._line()
        self.responsavel_tecnico_email = self._line()
        self.responsavel_tecnico_telefone = self._line()
        self.responsavel_tecnico_art = self._line("ART/RRT padrão, quando aplicável")
        self.responsavel_tecnico_assinatura_path = self._line()
        self.responsavel_tecnico_rubrica_path = self._line()
        for label, widget in [
            ("Nome", self.responsavel_tecnico),
            ("Registro técnico", self.registro_tecnico),
            ("CPF", self.responsavel_tecnico_cpf),
            ("Cargo", self.responsavel_tecnico_cargo),
            ("Especialidade", self.responsavel_tecnico_especialidade),
            ("E-mail", self.responsavel_tecnico_email),
            ("Telefone", self.responsavel_tecnico_telefone),
            ("Nº ART/RRT padrão", self.responsavel_tecnico_art),
        ]:
            form.addRow(label, widget)
        form.addRow("Assinatura", self._file_row(self.responsavel_tecnico_assinatura_path, "Selecionar assinatura", "Imagens (*.png *.jpg *.jpeg *.bmp)"))
        form.addRow("Rubrica", self._file_row(self.responsavel_tecnico_rubrica_path, "Selecionar rubrica", "Imagens (*.png *.jpg *.jpeg *.bmp)"))
        return page

    def _aba_gestao_contrato(self):
        page = QWidget(); form = QFormLayout(page)
        form.setVerticalSpacing(10)
        self.gestor_contrato_nome = self._line()
        self.gestor_contrato_cargo = self._line()
        self.gestor_contrato_cpf = self._line()
        self.gestor_contrato_email = self._line()
        self.gestor_contrato_telefone = self._line()
        self.gestor_contrato_assinatura_path = self._line()
        self.fiscal_contrato_nome = self._line()
        self.fiscal_contrato_setor = self._line()
        self.fiscal_contrato_cargo = self._line()
        self.fiscal_contrato_email = self._line()
        self.fiscal_contrato_telefone = self._line()
        sep1 = QLabel("Gestor do contrato")
        sep1.setStyleSheet("font-weight:900;color:#0B3B75;")
        form.addRow(sep1)
        for label, widget in [
            ("Nome", self.gestor_contrato_nome),
            ("Cargo", self.gestor_contrato_cargo),
            ("CPF", self.gestor_contrato_cpf),
            ("E-mail", self.gestor_contrato_email),
            ("Telefone", self.gestor_contrato_telefone),
        ]:
            form.addRow(label, widget)
        form.addRow("Assinatura", self._file_row(self.gestor_contrato_assinatura_path, "Selecionar assinatura", "Imagens (*.png *.jpg *.jpeg *.bmp)"))
        sep2 = QLabel("Fiscal do contrato / fiscalização")
        sep2.setStyleSheet("font-weight:900;color:#0B3B75;")
        form.addRow(sep2)
        for label, widget in [
            ("Nome", self.fiscal_contrato_nome),
            ("Setor", self.fiscal_contrato_setor),
            ("Cargo", self.fiscal_contrato_cargo),
            ("E-mail", self.fiscal_contrato_email),
            ("Telefone", self.fiscal_contrato_telefone),
        ]:
            form.addRow(label, widget)
        return page

    def _aba_assinaturas(self):
        page = QWidget(); layout = QVBoxLayout(page)
        texto = QLabel(
            "As assinaturas cadastradas aqui serão utilizadas pelos relatórios oficiais. "
            "O orçamento poderá sobrescrever o responsável técnico/gestor em casos específicos."
        )
        texto.setWordWrap(True)
        texto.setStyleSheet("color:#64748B;font-weight:700;")
        layout.addWidget(texto)

        box_contrato = QGroupBox("Contrato de concessao / contrato principal")
        form = QVBoxLayout(box_contrato)
        orientacao = QLabel(
            "Anexe aqui o contrato principal da concessao ou o documento institucional que deve ficar "
            "disponivel para consultas e relatorios. O arquivo sera copiado para a pasta de anexos "
            "do workspace compartilhado quando houver Google Drive configurado."
        )
        orientacao.setWordWrap(True)
        orientacao.setStyleSheet("color:#64748B;font-weight:700;")
        form.addWidget(orientacao)

        self.contrato_concessao_path = self._line()
        self.contrato_concessao_path.setReadOnly(True)
        linha = QHBoxLayout()
        linha.addWidget(self.contrato_concessao_path, 1)
        self.btn_contrato_selecionar = QPushButton("Anexar contrato")
        self.btn_contrato_abrir = QPushButton("Abrir contrato")
        self.btn_contrato_limpar = QPushButton("Remover anexo")
        self.btn_contrato_limpar.setObjectName("Danger")
        self.btn_contrato_selecionar.clicked.connect(self.selecionar_contrato_concessao)
        self.btn_contrato_abrir.clicked.connect(self.abrir_contrato_concessao)
        self.btn_contrato_limpar.clicked.connect(self.limpar_contrato_concessao)
        linha.addWidget(self.btn_contrato_selecionar)
        linha.addWidget(self.btn_contrato_abrir)
        linha.addWidget(self.btn_contrato_limpar)
        form.addLayout(linha)
        layout.addWidget(box_contrato)
        layout.addStretch()
        return page

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _selecionar_arquivo(self, target, titulo, filtro):
        path, _ = QFileDialog.getOpenFileName(self, titulo, "", filtro)
        if not path:
            return
        try:
            origem = Path(path)
            pasta = Path.cwd() / "app" / "assets" / "empresa"
            pasta.mkdir(parents=True, exist_ok=True)
            destino = pasta / origem.name
            shutil.copy2(origem, destino)
            target.setText(str(destino.resolve()))
            QMessageBox.information(self, "Arquivo", "Arquivo copiado para a pasta interna do sistema.")
        except Exception as e:
            target.setText(path)
            QMessageBox.warning(self, "Arquivo", f"Não foi possível copiar para a pasta interna. O caminho original será mantido.\n\n{e}")

    def _pasta_empresa_anexos(self):
        base = database.get_shared_workspace_path() or database.DATA_DIR
        pasta = Path(base) / "anexos" / "empresa"
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def selecionar_contrato_concessao(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Anexar contrato de concessao",
            "",
            "Documentos (*.pdf *.doc *.docx *.xls *.xlsx *.png *.jpg *.jpeg);;Arquivos (*.*)",
        )
        if not path:
            return
        try:
            origem = Path(path)
            destino = self._pasta_empresa_anexos() / origem.name
            if origem.resolve() != destino.resolve():
                shutil.copy2(origem, destino)
            self.contrato_concessao_path.setText(str(destino.resolve()))
            QMessageBox.information(self, "Contrato anexado", "Contrato copiado para os anexos da empresa. Clique em Salvar cadastro da empresa para gravar.")
        except Exception as e:
            self.contrato_concessao_path.setText(path)
            QMessageBox.warning(self, "Contrato anexado", f"Nao foi possivel copiar o arquivo. O caminho original sera mantido.\n\n{e}")

    def abrir_contrato_concessao(self):
        caminho = self.contrato_concessao_path.text().strip()
        if not caminho:
            QMessageBox.warning(self, "Contrato anexado", "Nenhum contrato anexado.")
            return
        if not Path(caminho).exists():
            QMessageBox.warning(self, "Contrato anexado", "Arquivo nao encontrado. Verifique se o Google Drive esta sincronizado nesta maquina.")
            return
        os.startfile(caminho)

    def limpar_contrato_concessao(self):
        self.contrato_concessao_path.clear()

    def _campos_empresa(self):
        return [
            "razao", "fantasia", "cnpj", "endereco", "municipio", "uf", "telefone", "email",
            "site", "inscricao_municipal", "observacao_institucional",
            "responsavel_tecnico", "registro_tecnico", "responsavel_tecnico_cpf", "responsavel_tecnico_cargo",
            "responsavel_tecnico_especialidade", "responsavel_tecnico_email", "responsavel_tecnico_telefone",
            "responsavel_tecnico_art", "responsavel_tecnico_assinatura_path", "responsavel_tecnico_rubrica_path",
            "gestor_contrato_nome", "gestor_contrato_cargo", "gestor_contrato_cpf", "gestor_contrato_email",
            "gestor_contrato_telefone", "gestor_contrato_assinatura_path",
            "fiscal_contrato_nome", "fiscal_contrato_setor", "fiscal_contrato_cargo", "fiscal_contrato_email",
            "fiscal_contrato_telefone", "logo_path", "contrato_concessao_path",
        ]

    def _valor_widget(self, nome):
        widget = getattr(self, nome)
        if isinstance(widget, QTextEdit):
            return widget.toPlainText()
        return widget.text()

    def _set_widget(self, nome, valor):
        widget = getattr(self, nome)
        if isinstance(widget, QTextEdit):
            widget.setPlainText(str(valor or ""))
        else:
            widget.setText(str(valor or ""))

    # ------------------------------------------------------------------
    # Empresa
    # ------------------------------------------------------------------
    def carregar(self):
        with conn() as c:
            item = c.execute("SELECT * FROM empresa WHERE id=1").fetchone()
        if not item:
            return
        keys = set(item.keys())
        for nome in self._campos_empresa():
            if nome in keys and hasattr(self, nome):
                self._set_widget(nome, item[nome])
        # Compatibilidade: campos antigos de representante legal principal.
        if "representante" in keys and item["representante"]:
            self.rep_nome.setText(str(item["representante"] or ""))
        if "cargo_representante" in keys and item["cargo_representante"]:
            self.rep_cargo.setText(str(item["cargo_representante"] or ""))

    def salvar(self):
        campos = self._campos_empresa()
        sets = ", ".join([f"{c}=?" for c in campos])
        vals = [self._valor_widget(c) for c in campos]
        with conn() as c:
            c.execute(f"UPDATE empresa SET {sets} WHERE id=1", vals)
            c.commit()
        QMessageBox.information(self, "Empresa", "Cadastro da empresa salvo com sucesso.")

    # ------------------------------------------------------------------
    # Representantes legais múltiplos
    # ------------------------------------------------------------------
    def carregar_representantes(self):
        try:
            with conn() as c:
                rows = c.execute("SELECT * FROM empresa_representantes ORDER BY ativo DESC, ordem, nome").fetchall()
        except Exception:
            rows = []
        self.tabela_representantes.setRowCount(len(rows))
        for r, row in enumerate(rows):
            vals = [row["id"], row["nome"], row["cargo"], row["cpf"], row["email"], row["telefone"], "Sim" if row["ativo"] else "Não"]
            for cidx, val in enumerate(vals):
                item = QTableWidgetItem(str(val or ""))
                self.tabela_representantes.setItem(r, cidx, item)
        ajustar_tabela_apos_carregar(self.tabela_representantes)

    def limpar_representante(self):
        self.selected_rep_id = None
        self.rep_nome.clear(); self.rep_cargo.clear(); self.rep_cpf.clear(); self.rep_email.clear(); self.rep_telefone.clear()
        self.rep_assinatura_path.clear(); self.rep_observacao.clear(); self.rep_ativo.setChecked(True)

    def selecionar_representante(self, row, col):
        item = self.tabela_representantes.item(row, 0)
        if not item:
            return
        self.selected_rep_id = int(item.text())
        with conn() as c:
            r = c.execute("SELECT * FROM empresa_representantes WHERE id=?", (self.selected_rep_id,)).fetchone()
        if not r:
            return
        self.rep_nome.setText(r["nome"] or "")
        self.rep_cargo.setText(r["cargo"] or "")
        self.rep_cpf.setText(r["cpf"] or "")
        self.rep_email.setText(r["email"] or "")
        self.rep_telefone.setText(r["telefone"] or "")
        self.rep_assinatura_path.setText(r["assinatura_path"] or "")
        self.rep_observacao.setPlainText(r["observacao"] or "")
        self.rep_ativo.setChecked(bool(r["ativo"]))

    def salvar_representante(self):
        nome = self.rep_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Representante", "Informe o nome do representante legal.")
            return
        dados = (
            nome,
            self.rep_cargo.text().strip(),
            self.rep_cpf.text().strip(),
            self.rep_email.text().strip(),
            self.rep_telefone.text().strip(),
            self.rep_assinatura_path.text().strip(),
            1 if self.rep_ativo.isChecked() else 0,
            self.rep_observacao.toPlainText().strip(),
        )
        with conn() as c:
            if self.selected_rep_id:
                c.execute(
                    """UPDATE empresa_representantes
                       SET nome=?, cargo=?, cpf=?, email=?, telefone=?, assinatura_path=?, ativo=?, observacao=?
                       WHERE id=?""",
                    dados + (self.selected_rep_id,)
                )
            else:
                c.execute(
                    """INSERT INTO empresa_representantes(nome, cargo, cpf, email, telefone, assinatura_path, ativo, observacao)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    dados
                )
            c.commit()
        self.limpar_representante()
        self.carregar_representantes()
        QMessageBox.information(self, "Representante", "Representante legal salvo com sucesso.")

    def excluir_representante(self):
        if not self.selected_rep_id:
            QMessageBox.warning(self, "Representante", "Selecione um representante para excluir.")
            return
        resp = QMessageBox.question(self, "Excluir representante", "Deseja excluir o representante selecionado?", QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes:
            return
        with conn() as c:
            c.execute("DELETE FROM empresa_representantes WHERE id=?", (self.selected_rep_id,))
            c.commit()
        self.limpar_representante()
        self.carregar_representantes()
