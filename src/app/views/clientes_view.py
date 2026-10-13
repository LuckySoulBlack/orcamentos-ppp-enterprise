from PySide6.QtWidgets import *
from core.database import conn
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar

class ClientesView(QWidget):
    def __init__(self):
        super().__init__()
        self.cliente_id = None
        layout = QVBoxLayout(self)
        top = QHBoxLayout(); title = QLabel("Clientes / Órgãos"); title.setObjectName("Title")
        self.busca = QLineEdit(); self.busca.setPlaceholderText("Buscar por nome, CNPJ, município ou responsável")
        btn_buscar = QPushButton("Pesquisar"); btn_buscar.clicked.connect(self.load_data)
        top.addWidget(title); top.addStretch(); top.addWidget(self.busca, 2); top.addWidget(btn_buscar); layout.addLayout(top)
        box = QGroupBox("Cadastro do cliente")
        form = QFormLayout(box)
        self.nome = QLineEdit(); self.cnpj = QLineEdit(); self.municipio = QLineEdit(); self.uf = QLineEdit(); self.uf.setMaxLength(2)
        self.orgao = QLineEdit(); self.responsavel = QLineEdit(); self.cargo = QLineEdit(); self.email = QLineEdit(); self.telefone = QLineEdit(); self.obs = QTextEdit(); self.obs.setMaximumHeight(70)
        for label, widget in [("Nome/Razão", self.nome),("CNPJ", self.cnpj),("Município", self.municipio),("UF", self.uf),("Órgão/Setor", self.orgao),("Responsável", self.responsavel),("Cargo", self.cargo),("E-mail", self.email),("Telefone", self.telefone),("Observações", self.obs)]: form.addRow(label, widget)
        actions = QHBoxLayout(); self.btn_salvar = QPushButton("Salvar cliente"); self.btn_salvar.clicked.connect(self.salvar)
        btn_novo = QPushButton("Novo/Limpar"); btn_novo.setObjectName("Secondary"); btn_novo.clicked.connect(self.limpar)
        self.btn_duplicar = QPushButton("Duplicar cliente"); self.btn_duplicar.clicked.connect(self.duplicar_cliente)
        self.btn_excluir = QPushButton("Excluir cliente"); self.btn_excluir.clicked.connect(self.excluir_cliente)
        self.btn_excluir.setStyleSheet("background:#DC2626;color:white;font-weight:800;padding:8px;border-radius:6px;")
        actions.addWidget(self.btn_salvar); actions.addWidget(btn_novo); actions.addWidget(self.btn_duplicar); actions.addWidget(self.btn_excluir); form.addRow(actions)
        layout.addWidget(box)
        self.table = QTableWidget(); self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(["ID","Nome","CNPJ","Município","UF","Responsável","E-mail"])
        configurar_tabela_responsiva(self.table, stretch_columns=[6], hidden_columns=[0])
        self.table.cellClicked.connect(self.carregar_linha)
        self.table.cellDoubleClicked.connect(self.carregar_linha)
        layout.addWidget(self.table, 1)
        self.load_data()

    def refresh(self): self.load_data()
    def limpar(self):
        self.cliente_id = None
        for w in [self.nome,self.cnpj,self.municipio,self.uf,self.orgao,self.responsavel,self.cargo,self.email,self.telefone]: w.clear()
        self.obs.clear(); self.nome.setFocus()
    def salvar(self):
        if not self.nome.text().strip(): QMessageBox.warning(self,"Clientes","Informe o nome do cliente."); return
        dados = (self.nome.text(), self.cnpj.text(), self.municipio.text(), self.uf.text().upper(), self.orgao.text(), self.responsavel.text(), self.cargo.text(), self.email.text(), self.telefone.text(), self.obs.toPlainText())
        with conn() as c:
            if self.cliente_id:
                c.execute("""UPDATE clientes SET nome=?,cnpj=?,municipio=?,uf=?,orgao_setor=?,responsavel=?,cargo=?,email=?,telefone=?,observacoes=?WHERE id=?""", dados+(self.cliente_id,))
            else:
                c.execute("""INSERT INTO clientes(nome,cnpj,municipio,uf,orgao_setor,responsavel,cargo,email,telefone,observacoes) VALUES(?,?,?,?,?,?,?,?,?,?)""", dados)
            c.commit()
        self.load_data(); QMessageBox.information(self,"Clientes","Cliente salvo com sucesso.")
    def load_data(self):
        termo = f"%{self.busca.text().strip()}%"
        with conn() as c:
            dados = c.execute("""SELECT id,nome,cnpj,municipio,uf,responsavel,email FROM clientes WHERE ativo=1 AND (nome LIKE ?OR cnpj LIKE ?OR municipio LIKE ?OR responsavel LIKE ?) ORDER BY nome""", (termo,termo,termo,termo)).fetchall()
        self.table.setRowCount(len(dados))
        for r,item in enumerate(dados):
            for col,val in enumerate(item): self.table.setItem(r,col,QTableWidgetItem(str(val or "")))
        ajustar_tabela_apos_carregar(self.table)
    def carregar_linha(self, row, col):
        item_id = self.table.item(row,0)
        if not item_id: return
        with conn() as c: item = c.execute("SELECT * FROM clientes WHERE id=?", (item_id.text(),)).fetchone()
        if not item: return
        self.cliente_id = item["id"]
        for attr,col in [("nome","nome"),("cnpj","cnpj"),("municipio","municipio"),("uf","uf"),("orgao","orgao_setor"),("responsavel","responsavel"),("cargo","cargo"),("email","email"),("telefone","telefone")]: getattr(self, attr).setText(str(item[col] or ""))
        self.obs.setPlainText(str(item["observacoes"] or ""))


    def duplicar_cliente(self):
        if not self.cliente_id:
            QMessageBox.warning(self, "Clientes", "Selecione um cliente para duplicar.")
            return
        with conn() as c:
            item = c.execute("SELECT * FROM clientes WHERE id=?", (self.cliente_id,)).fetchone()
            if not item:
                QMessageBox.warning(self, "Clientes", "Cliente selecionado não localizado.")
                return
            c.execute("""
                INSERT INTO clientes(nome,cnpj,municipio,uf,orgao_setor,responsavel,cargo,email,telefone,observacoes,ativo)
                VALUES(?,?,?,?,?,?,?,?,?,?,1)
            """, (
                f"{item['nome'] or 'Cliente'} - Cópia", item["cnpj"], item["municipio"], item["uf"], item["orgao_setor"], item["responsavel"], item["cargo"], item["email"], item["telefone"], (item["observacoes"] or "") + "\n\nCliente duplicado para novo cadastro/segmentação."
            ))
            c.commit()
        self.load_data()
        QMessageBox.information(self, "Clientes", "Cliente duplicado com sucesso.")

    def excluir_cliente(self):
        if not self.cliente_id:
            QMessageBox.warning(self, "Clientes", "Selecione um cliente para excluir.")
            return
        with conn() as c:
            contratos = c.execute("SELECT COUNT(*) qtd FROM contratos WHERE cliente_id=?", (self.cliente_id,)).fetchone()["qtd"]
            orcamentos = c.execute("SELECT COUNT(*) qtd FROM orcamentos WHERE cliente_id=?", (self.cliente_id,)).fetchone()["qtd"]
        bloqueios = []
        if contratos: bloqueios.append(f"{contratos} contrato(s) vinculado(s)")
        if orcamentos: bloqueios.append(f"{orcamentos} orçamento(s) vinculado(s)")
        if bloqueios:
            QMessageBox.warning(self, "Exclusão bloqueada", "Este cliente/órgão não pode ser excluído para evitar perda acidental de dados.\n\nVínculos encontrados:\n- " + "\n- ".join(bloqueios) + "\n\nRemova ou realoque os vínculos antes de excluir.")
            return
        resp = QMessageBox.question(self, "Excluir cliente", "Deseja realmente excluir este cliente/órgão?", QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes: return
        with conn() as c:
            try: c.execute("UPDATE clientes SET ativo=0 WHERE id=?", (self.cliente_id,))
            except Exception: c.execute("DELETE FROM clientes WHERE id=?", (self.cliente_id,))
            c.commit()
        self.limpar(); self.load_data(); QMessageBox.information(self, "Clientes", "Cliente excluído com sucesso.")
