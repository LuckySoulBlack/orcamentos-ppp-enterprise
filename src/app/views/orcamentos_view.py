from PySide6.QtCore import Qt, QSignalBlocker, QTimer
import webbrowser
import traceback
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QTextEdit,
    QPushButton, QComboBox, QDoubleSpinBox, QGroupBox, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFrame, QSizePolicy, QFileDialog,
    QDialog, QAbstractItemView,QCheckBox
)

from core.database import conn, STATUS_ORCAMENTO, get_anexos_dir
from core.ui_helpers import aplicar_estilo_botao, aplicar_botoes_semanticos
from services.documentos_service import gerar_pacote_revisao, gerar_pacote_final, gerar_pacote_orcamento_simples
from services.dashboard_html_service import gerar_dashboard_html
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar



class SinapiSearchDialog(QDialog):
    """Janela modal para pesquisar SINAPI sem travar a digitação no formulário."""

    def __init__(self, parent=None, termo_inicial=""):
        super().__init__(parent)
        self.setWindowTitle("Buscar item SINAPI")
        self.resize(980, 620)
        self.item_selecionado = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        info = QLabel("Digite código ou parte da descrição e clique em Pesquisar. Depois selecione o item desejado.")
        info.setStyleSheet("font-weight:800;color:#334155;")
        layout.addWidget(info)

        row = QHBoxLayout()
        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Ex.: poste, cabo cobre, luminária, 97611...")
        self.busca.setText(termo_inicial or "")
        self.btn_pesquisar = QPushButton("Pesquisar")
        self.btn_usar = QPushButton("Usar item selecionado")
        self.btn_pesquisar.setMinimumHeight(38)
        self.btn_usar.setMinimumHeight(38)
        row.addWidget(self.busca, 1)
        row.addWidget(self.btn_pesquisar)
        row.addWidget(self.btn_usar)
        layout.addLayout(row)

        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(["Código", "Descrição", "UN", "Custo", "Tipo", "Fonte"])
        configurar_tabela_responsiva(self.tabela, stretch_columns=[1])
        self.tabela.setMinimumHeight(430)
        layout.addWidget(self.tabela)

        self.btn_pesquisar.clicked.connect(self.pesquisar)
        self.btn_usar.clicked.connect(self.usar_item)
        self.busca.returnPressed.connect(self.pesquisar)
        self.tabela.cellDoubleClicked.connect(lambda *_: self.usar_item())

        if termo_inicial:
            self.pesquisar()

    def pesquisar(self):
        termo = self.busca.text().strip()
        if len(termo) < 2:
            QMessageBox.warning(self, "SINAPI", "Digite pelo menos 2 caracteres para pesquisar.")
            return

        palavras = [p.strip() for p in termo.replace("-", " ").split() if p.strip()]
        params = []
        where_parts = ["codigo LIKE ?"]
        params.append(f"%{termo}%")

        if palavras:
            desc_parts = []
            for p in palavras:
                desc_parts.append("UPPER(descricao) LIKE UPPER(?)")
                params.append(f"%{p}%")
            where_parts.append("(" + " AND ".join(desc_parts) + ")")

        sql = f"""
            SELECT codigo, descricao, unidade, custo, tipo, fonte, classificacao
            FROM sinapi
            WHERE {' OR '.join(where_parts)}
            ORDER BY
                CASE
                    WHEN codigo = ?THEN 0
                    WHEN codigo LIKE ?THEN 1
                    WHEN UPPER(descricao) LIKE UPPER(?) THEN 2
                    ELSE 3
                END,
                tipo,
                descricao
            LIMIT 300
        """
        params.extend([termo, f"{termo}%", f"%{termo}%"])

        with conn() as c:
            dados = c.execute(sql, params).fetchall()

        self.tabela.setRowCount(len(dados))
        for r, row in enumerate(dados):
            valores = [
                row["codigo"],
                row["descricao"],
                row["unidade"],
                f"R$ {float(row['custo'] or 0):,.4f}".replace(",", "X").replace(".", ",").replace("X", "."),
                row["tipo"],
                row["fonte"],
            ]
            for cidx, val in enumerate(valores):
                item = QTableWidgetItem(str(val or ""))
                item.setData(Qt.UserRole, dict(row))
                self.tabela.setItem(r, cidx, item)

        if not dados:
            QMessageBox.information(self, "SINAPI", "Nenhum item encontrado para a busca.")

    def usar_item(self):
        row = self.tabela.currentRow()
        if row < 0:
            QMessageBox.warning(self, "SINAPI", "Selecione um item da tabela.")
            return
        item = self.tabela.item(row, 0)
        self.item_selecionado = item.data(Qt.UserRole) if item else None
        if not self.item_selecionado:
            return
        self.accept()



class OrcamentosView(QWidget):
    def __init__(self):
        super().__init__()
        self.orcamento_id = None
        self.selected_capex_item_id = None
        self.selected_opex_id = None
        self.selected_documento_id = None
        self.selected_etapa_id = None
        self._ultima_margem_global = 18
        self._carregando_combos = False
        self._build()
        self.contrato.currentIndexChanged.connect(self.atualizar_vinculos_contrato)
        self.cliente.currentIndexChanged.connect(self.preencher_dados_cliente)
        self.aditivo.currentIndexChanged.connect(self.preencher_segmento_por_aditivo)
        self.carregar_combos()
        self.carregar_orcamentos()
        aplicar_botoes_semanticos(self)

    def showEvent(self, event):
        super().showEvent(event)
        # Atualiza automaticamente quando voltar para a tela, sem precisar clicar em botão.
        self.carregar_combos(preservar=True)
        self.carregar_orcamentos()

        aplicar_botoes_semanticos(self)

    # ------------------------- UI HELPERS -------------------------
    def botao(self, texto, cor="#0B3B75"):
        btn = QPushButton(texto)
        btn.setMinimumHeight(42)
        btn.setCursor(Qt.PointingHandCursor)
        aplicar_estilo_botao(btn)
        return btn

    def moeda(self, valor):
        try:
            valor = float(valor or 0)
        except Exception:
            valor = 0
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def total_item(self, qtd, custo, bdi, margem):
        return float(qtd or 0) * float(custo or 0) * (1 + float(bdi or 0) / 100) * (1 + float(margem or 0) / 100)

    def _set_table(self, table, rows):
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(str(val or "")))

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Orçamentos PPP")
        title.setStyleSheet("font-size:26px;font-weight:950;color:#071A33;")
        self.cbo_orcamentos = QComboBox(); self.cbo_orcamentos.setMinimumHeight(40)
        self.btn_abrir = self.botao("Abrir", "#EAF2FF"); self.btn_abrir.setStyleSheet("QPushButton{background:#EAF2FF;color:#0B3B75;border:1px solid #9CC2FF;border-radius:8px;font-weight:850;}")
        self.btn_novo = self.botao("Novo orçamento")
        self.btn_abrir.clicked.connect(lambda checked=False: self.abrir_orcamento())
        self.btn_novo.clicked.connect(self.novo_orcamento)
        top.addWidget(title)
        top.addWidget(QLabel("Orçamento:"))
        top.addWidget(self.cbo_orcamentos, 1)
        top.addWidget(self.btn_abrir)
        top.addWidget(self.btn_novo)
        root.addLayout(top)

        self.tabs = QComboBox()  # dummy only to keep previous references from crashing if any external code checks
        from PySide6.QtWidgets import QTabWidget
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.aba_dados(), "Dados Gerais")
        self.tab_widget.addTab(self.aba_capex(), "CAPEX")
        self.tab_widget.addTab(self.aba_opex(), "OPEX")
        self.tab_widget.addTab(self.aba_cronograma(), "Cronograma físico-financeiro")
        self.tab_widget.addTab(self.aba_anexos(), "Documentos / Anexos")
        self.tab_widget.addTab(self.aba_geracao(), "Geração")
        root.addWidget(self.tab_widget)

    def _scroll_page(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget(); layout = QVBoxLayout(content); layout.setContentsMargins(10, 10, 10, 10); layout.setSpacing(14)
        scroll.setWidget(content)
        return scroll, layout

    # ------------------------- DADOS -------------------------
    def aba_dados(self):
        scroll, layout = self._scroll_page()
        box = QGroupBox("Dados gerais do orçamento")
        grid = QGridLayout(box); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(10)
        self.codigo = QLineEdit()
        self.cliente = QComboBox(); self.contrato = QComboBox(); self.aditivo = QComboBox(); self.segmento = QComboBox()
        self.objeto = QLineEdit(); self.municipio = QLineEdit(); self.validade = QLineEdit("60 dias")
        self.status = QComboBox(); self.status.addItems(STATUS_ORCAMENTO)
        self.texto_proposta = QTextEdit(); self.texto_proposta.setMinimumHeight(100)
        self.usar_rt_especifico = QCheckBox("Usar responsável técnico específico neste orçamento")
        self.rt_nome = QLineEdit(); self.rt_registro = QLineEdit(); self.rt_cpf = QLineEdit(); self.rt_cargo = QLineEdit(); self.rt_especialidade = QLineEdit(); self.rt_email = QLineEdit(); self.rt_telefone = QLineEdit(); self.rt_art = QLineEdit(); self.rt_assinatura_path = QLineEdit()
        self.gestor_contrato_nome = QLineEdit(); self.gestor_contrato_cargo = QLineEdit(); self.gestor_contrato_cpf = QLineEdit(); self.gestor_contrato_email = QLineEdit(); self.gestor_contrato_telefone = QLineEdit()
        self.fiscal_contrato_nome = QLineEdit(); self.fiscal_contrato_cargo = QLineEdit(); self.fiscal_contrato_setor = QLineEdit(); self.fiscal_contrato_email = QLineEdit(); self.fiscal_contrato_telefone = QLineEdit()
        self.representante_legal_id = QComboBox(); self.representante_legal_id.setMinimumHeight(38)
        self.bdi = QDoubleSpinBox(); self.bdi.setRange(0, 100); self.bdi.setDecimals(4); self.bdi.setSuffix(" %")
        self.margem = QDoubleSpinBox(); self.margem.setRange(0, 300); self.margem.setDecimals(4); self.margem.setSuffix(" %"); self.margem.setValue(18); self.margem.editingFinished.connect(self.aplicar_margem_global_opcional)
        campos = [("Código", self.codigo), ("Cliente", self.cliente), ("Contrato PPP", self.contrato), ("Aditivo", self.aditivo), ("Segmento", self.segmento), ("Objeto", self.objeto), ("Município", self.municipio), ("Validade", self.validade), ("Status", self.status), ("BDI Global", self.bdi), ("Margem Global", self.margem)]
        for i, (label, widget) in enumerate(campos):
            grid.addWidget(QLabel(label), i, 0)
            widget.setMinimumHeight(38)
            grid.addWidget(widget, i, 1)
        grid.addWidget(QLabel("Texto da proposta"), len(campos), 0)
        grid.addWidget(self.texto_proposta, len(campos), 1)

        governanca = QGroupBox("Governança, responsáveis e assinaturas do orçamento")
        gov = QGridLayout(governanca); gov.setHorizontalSpacing(10); gov.setVerticalSpacing(8)
        gov.addWidget(self.usar_rt_especifico, 0, 0, 1, 2)
        campos_rt = [
            ("RT específico", self.rt_nome), ("Registro", self.rt_registro), ("CPF", self.rt_cpf),
            ("Cargo", self.rt_cargo), ("Especialidade", self.rt_especialidade), ("E-mail", self.rt_email),
            ("Telefone", self.rt_telefone), ("ART/RRT", self.rt_art), ("Assinatura", self.rt_assinatura_path),
        ]
        for i, (lbl, w) in enumerate(campos_rt, start=1):
            gov.addWidget(QLabel(lbl), i, 0); w.setMinimumHeight(34); gov.addWidget(w, i, 1)
        offset = len(campos_rt) + 1
        gov.addWidget(QLabel("Representante legal para assinatura"), offset, 0); gov.addWidget(self.representante_legal_id, offset, 1)
        offset += 1
        campos_gestor = [
            ("Gestor do contrato", self.gestor_contrato_nome), ("Cargo gestor", self.gestor_contrato_cargo),
            ("CPF gestor", self.gestor_contrato_cpf), ("E-mail gestor", self.gestor_contrato_email), ("Telefone gestor", self.gestor_contrato_telefone),
            ("Fiscal", self.fiscal_contrato_nome), ("Cargo fiscal", self.fiscal_contrato_cargo), ("Setor fiscal", self.fiscal_contrato_setor),
            ("E-mail fiscal", self.fiscal_contrato_email), ("Telefone fiscal", self.fiscal_contrato_telefone),
        ]
        for j, (lbl, w) in enumerate(campos_gestor, start=offset):
            gov.addWidget(QLabel(lbl), j, 0); w.setMinimumHeight(34); gov.addWidget(w, j, 1)
        grid.addWidget(governanca, len(campos)+1, 0, 1, 2)

        btn = self.botao("Salvar dados gerais")
        btn.clicked.connect(self.salvar_orcamento)
        grid.addWidget(btn, len(campos)+2, 1)
        layout.addWidget(box)
        layout.addStretch()
        return scroll

    # ------------------------- CAPEX -------------------------
    def aba_capex(self):
        scroll, layout = self._scroll_page()

        box_etapa = QGroupBox("1. Etapas de execução")
        et_layout = QVBoxLayout(box_etapa); et_layout.setSpacing(10)
        row = QHBoxLayout()
        self.etapa_nome = QLineEdit(); self.etapa_nome.setPlaceholderText("Digite a etapa. Ex.: Demarcação e escavação / Instalação dos postes / Instalação elétrica")
        self.etapa_nome.setMinimumHeight(40)
        self.btn_add_etapa = self.botao("Adicionar etapa")
        self.btn_atualizar_etapa = self.botao("Atualizar etapa selecionada", "#2563EB")
        self.btn_excluir_etapa = self.botao("Excluir etapa selecionada", "#DC2626")
        self.btn_add_etapa.clicked.connect(self.adicionar_etapa)
        self.btn_atualizar_etapa.clicked.connect(self.atualizar_etapa)
        self.btn_excluir_etapa.clicked.connect(self.excluir_etapa)
        row.addWidget(self.etapa_nome, 1); row.addWidget(self.btn_add_etapa); row.addWidget(self.btn_atualizar_etapa); row.addWidget(self.btn_excluir_etapa)
        et_layout.addLayout(row)
        self.tabela_etapas = QTableWidget(0, 4)
        self.tabela_etapas.setHorizontalHeaderLabels(["ID interno", "Etapa", "Descrição", "Total CAPEX"])
        configurar_tabela_responsiva(self.tabela_etapas, stretch_columns=[1, 2], hidden_columns=[0])
        self.tabela_etapas.setMinimumHeight(150); self.tabela_etapas.setMaximumHeight(210)
        self.tabela_etapas.cellClicked.connect(self.selecionar_etapa)
        et_layout.addWidget(self.tabela_etapas)
        layout.addWidget(box_etapa)

        box_item = QGroupBox("2. Item da etapa selecionada")
        item_layout = QVBoxLayout(box_item); item_layout.setSpacing(10)
        self.etapa_item = QComboBox(); self.etapa_item.setMinimumHeight(38)
        self.etapa_item.currentIndexChanged.connect(lambda *_: self.atualizar_titulo_itens())
        linha1 = QGridLayout(); linha1.setHorizontalSpacing(12)
        self.fonte = QComboBox(); self.fonte.addItems(["SINAPI", "Composição Própria", "Cotação"]); self.fonte.setMinimumHeight(38); self.fonte.currentTextChanged.connect(self.aplicar_modo_fonte_capex); self.fonte.currentTextChanged.connect(self.aplicar_modo_fonte_capex)
        self.codigo_sinapi = QComboBox(); self.codigo_sinapi.setEditable(True); self.codigo_sinapi.setMinimumHeight(38)
        self.btn_buscar_sinapi_capex = self.botao("Buscar SINAPI", "#2563EB")
        self.btn_buscar_sinapi_capex.clicked.connect(self.abrir_busca_sinapi_capex)
        linha1.addWidget(QLabel("Etapa selecionada"), 0, 0)
        linha1.addWidget(QLabel("Fonte"), 0, 1)
        linha1.addWidget(QLabel("Código / Item SINAPI"), 2, 0, 1, 2)
        linha1.addWidget(self.etapa_item, 1, 0)
        linha1.addWidget(self.fonte, 1, 1)
        linha1.addWidget(self.codigo_sinapi, 3, 0)
        linha1.addWidget(self.btn_buscar_sinapi_capex, 3, 1)
        item_layout.addLayout(linha1)

        item_layout.addWidget(QLabel("Descrição do item"))
        self.descricao = QTextEdit(); self.descricao.setMinimumHeight(72); self.descricao.setPlaceholderText("Descrição do material/serviço. Ao selecionar SINAPI, este campo será preenchido automaticamente.")
        item_layout.addWidget(self.descricao)

        linha3 = QGridLayout(); linha3.setHorizontalSpacing(12); linha3.setVerticalSpacing(6)
        self.unidade = QLineEdit(); self.quantidade = QDoubleSpinBox(); self.custo_unit = QDoubleSpinBox()
        self.bdi_item = QDoubleSpinBox(); self.margem_item = QDoubleSpinBox(); self.classificacao = QComboBox()
        self.quantidade.setRange(0, 999999999); self.quantidade.setDecimals(4); self.quantidade.setValue(1)
        self.custo_unit.setRange(0, 999999999); self.custo_unit.setDecimals(4)
        self.bdi_item.setRange(0, 100); self.bdi_item.setDecimals(4); self.bdi_item.setSuffix(" %")
        self.margem_item.setRange(0, 300); self.margem_item.setDecimals(4); self.margem_item.setSuffix(" %"); self.margem_item.setValue(18)
        self.classificacao.addItems(["Material", "Mão de Obra", "Serviço", "Equipamento", "Composição"])
        widgets = [("UN", self.unidade), ("Quantidade", self.quantidade), ("Custo Unit. (R$)", self.custo_unit), ("BDI (%)", self.bdi_item), ("Margem (%)", self.margem_item), ("Classificação", self.classificacao)]
        for col, (label, widget) in enumerate(widgets):
            linha3.addWidget(QLabel(label), 0, col)
            widget.setMinimumHeight(38)
            linha3.addWidget(widget, 1, col)
        item_layout.addLayout(linha3)

        item_layout.addWidget(QLabel("Observação"))
        self.obs_item = QTextEdit(); self.obs_item.setMinimumHeight(90); self.obs_item.setPlaceholderText("Observações técnicas, premissas, composição, fornecedor, cotações ou justificativa do item.")
        item_layout.addWidget(self.obs_item)

        botoes = QHBoxLayout(); botoes.setSpacing(12)
        self.btn_add_item = self.botao("Adicionar item CAPEX")
        self.btn_update_item_seguro = self.botao("Atualizar item sem alterar etapa", "#16A34A")
        self.btn_limpar_item = self.botao("Limpar campos", "#2563EB")
        self.btn_excluir_item = self.botao("Excluir item selecionado", "#DC2626")
        self.btn_cancelar_edicao_item = self.botao("Cancelar edição", "#64748B")
        self.btn_add_item.clicked.connect(self.adicionar_item)
        self.btn_update_item_seguro.clicked.connect(self.atualizar_item_sem_alterar_etapa)
        self.btn_limpar_item.clicked.connect(self.limpar_item_capex)
        self.btn_excluir_item.clicked.connect(self.excluir_item_capex)
        self.btn_cancelar_edicao_item.clicked.connect(self.limpar_item_capex)
        botoes.addWidget(self.btn_add_item, 2); botoes.addWidget(self.btn_update_item_seguro, 2); botoes.addWidget(self.btn_limpar_item, 1); botoes.addWidget(self.btn_excluir_item, 1); botoes.addWidget(self.btn_cancelar_edicao_item, 1)
        item_layout.addLayout(botoes)
        layout.addWidget(box_item)

        box_itens = QGroupBox("3. Itens do orçamento")
        itens_layout = QVBoxLayout(box_itens)
        self.tabela_itens = QTableWidget(0, 13)
        self.tabela_itens.setHorizontalHeaderLabels(["ID", "Etapa", "Fonte", "Código", "Descrição", "UN", "Qtd", "Custo Unit.", "Custo Total", "BDI %", "Margem %", "Preço Total", "Classificação"])
        configurar_tabela_responsiva(self.tabela_itens, stretch_columns=[4], hidden_columns=[0])
        self.tabela_itens.setMinimumHeight(310)
        self.tabela_itens.cellClicked.connect(self.selecionar_item_capex)
        itens_layout.addWidget(self.tabela_itens)
        self.lbl_resumo_capex = QLabel("CAPEX: R$ 0,00 | Itens: 0")
        self.lbl_resumo_capex.setStyleSheet("background:#F1F5F9;padding:12px;border-radius:8px;font-weight:900;color:#0B3B75;")
        itens_layout.addWidget(self.lbl_resumo_capex)
        layout.addWidget(box_itens)

        layout.addWidget(self._resumo_box())
        layout.addStretch()
        self.carregar_sinapi_lista()
        self.aplicar_modo_fonte_capex()
        return scroll

    def _resumo_box(self):
        box = QGroupBox("4. Resumo financeiro do orçamento")
        lay = QHBoxLayout(box)
        self.card_capex = QLabel("Total CAPEX\nR$ 0,00")
        self.card_opex = QLabel("Total OPEX Mensal\nR$ 0,00")
        self.card_margem = QLabel("Margem Média\n0,00%")
        self.card_itens = QLabel("Orçamento ativo\n0 itens")
        for c in [self.card_capex, self.card_opex, self.card_margem, self.card_itens]:
            c.setAlignment(Qt.AlignCenter); c.setMinimumHeight(70)
            c.setStyleSheet("background:white;border:1px solid #DBE4EF;border-radius:10px;padding:10px;font-weight:800;color:#0B3B75;")
            lay.addWidget(c)
        return box

    # ------------------------- OPEX -------------------------
    def aba_opex(self):
        scroll, layout = self._scroll_page()
        box = QGroupBox("Lançamento OPEX — custos mensais recorrentes")
        lay = QVBoxLayout(box); lay.setSpacing(10)
        grid = QGridLayout(); grid.setHorizontalSpacing(12)
        self.opex_fonte = QComboBox(); self.opex_fonte.addItems(["SINAPI", "Composição Própria", "Cotação"]); self.opex_fonte.currentTextChanged.connect(self.aplicar_modo_fonte_opex); self.opex_fonte.currentTextChanged.connect(self.aplicar_modo_fonte_opex)
        self.opex_codigo = QComboBox(); self.opex_codigo.setEditable(True)
        self.btn_buscar_sinapi_opex = QPushButton("Buscar SINAPI")
        self.btn_buscar_sinapi_opex.setMinimumHeight(38)
        self.btn_buscar_sinapi_opex.clicked.connect(self.abrir_busca_sinapi_opex)
        self.opex_categoria = QLineEdit(); self.opex_categoria.setPlaceholderText("Ex.: Manutenção, operação, plantão, software, conectividade")
        self.opex_descricao = QTextEdit(); self.opex_descricao.setMinimumHeight(80)
        self.opex_unidade = QLineEdit("MÊS")
        self.opex_qtd = QDoubleSpinBox(); self.opex_qtd.setRange(0,999999); self.opex_qtd.setDecimals(4); self.opex_qtd.setValue(1)
        self.opex_custo = QDoubleSpinBox(); self.opex_custo.setRange(0,999999999); self.opex_custo.setDecimals(4)
        self.opex_bdi = QDoubleSpinBox(); self.opex_bdi.setRange(0,100); self.opex_bdi.setDecimals(4); self.opex_bdi.setSuffix(" %")
        self.opex_margem = QDoubleSpinBox(); self.opex_margem.setRange(0,300); self.opex_margem.setDecimals(4); self.opex_margem.setSuffix(" %"); self.opex_margem.setValue(18)
        fields = [("Fonte", self.opex_fonte), ("Código SINAPI", self.opex_codigo), ("Categoria", self.opex_categoria), ("UN", self.opex_unidade), ("Qtd mensal", self.opex_qtd), ("Custo unit.", self.opex_custo), ("BDI", self.opex_bdi), ("Margem", self.opex_margem)]
        for i,(l,w) in enumerate(fields):
            grid.addWidget(QLabel(l), (i//2)*2, i%2)
            w.setMinimumHeight(38)
            grid.addWidget(w, (i//2)*2+1, i%2)
        grid.addWidget(self.btn_buscar_sinapi_opex, 1, 2)
        lay.addLayout(grid)
        lay.addWidget(QLabel("Descrição / observação")); lay.addWidget(self.opex_descricao)
        btns = QHBoxLayout()
        self.btn_add_opex = self.botao("Adicionar OPEX")
        self.btn_limpar_opex = self.botao("Limpar", "#2563EB")
        self.btn_excluir_opex = self.botao("Excluir selecionado", "#DC2626")
        self.btn_cancelar_opex = self.botao("Cancelar edição", "#64748B")
        self.btn_add_opex.clicked.connect(self.adicionar_opex); self.btn_limpar_opex.clicked.connect(self.limpar_opex); self.btn_excluir_opex.clicked.connect(self.excluir_opex); self.btn_cancelar_opex.clicked.connect(self.limpar_opex)
        btns.addWidget(self.btn_add_opex,2); btns.addWidget(self.btn_limpar_opex,1); btns.addWidget(self.btn_excluir_opex,1); btns.addWidget(self.btn_cancelar_opex,1)
        lay.addLayout(btns)
        layout.addWidget(box)
        self.tabela_opex = QTableWidget(0, 12)
        self.tabela_opex.setHorizontalHeaderLabels(["ID", "Categoria", "Fonte", "Código", "Descrição", "UN", "Qtd", "Custo Unit.", "Custo Total", "BDI %", "Margem %", "Total Mensal"])
        configurar_tabela_responsiva(self.tabela_opex, stretch_columns=[4], hidden_columns=[0])
        self.tabela_opex.setMinimumHeight(300)
        self.tabela_opex.cellClicked.connect(self.selecionar_opex)
        layout.addWidget(self.tabela_opex)
        layout.addStretch()

        # Recarrega a lista SINAPI agora que o combo OPEX já existe.
        self.carregar_sinapi_lista()
        self.aplicar_modo_fonte_opex()

        return scroll

    # ------------------------- CRONOGRAMA -------------------------
    def aba_cronograma(self):
        scroll, layout = self._scroll_page()
        top = QHBoxLayout()
        self.btn_atualizar_crono = self.botao("Atualizar etapas")
        self.btn_parcela_unica = self.botao("Parcela única", "#2563EB")
        self.btn_validar_crono = self.botao("Validar / Salvar", "#16A34A")
        self.btn_atualizar_crono.clicked.connect(self.gerar_cronograma_automatico)
        self.btn_parcela_unica.clicked.connect(self.aplicar_parcela_unica)
        self.btn_validar_crono.clicked.connect(self.validar_cronograma)
        top.addWidget(QLabel("Cronograma físico-financeiro por etapa")); top.addStretch(); top.addWidget(self.btn_atualizar_crono); top.addWidget(self.btn_parcela_unica); top.addWidget(self.btn_validar_crono)
        layout.addLayout(top)
        self.resumo_cronograma = QLabel("Total CAPEX: R$ 0,00 | Total distribuído: R$ 0,00 | Status: aguardando")
        self.resumo_cronograma.setStyleSheet("background:#EAF2FF;padding:12px;border-radius:8px;font-weight:900;color:#0B3B75;")
        layout.addWidget(self.resumo_cronograma)
        self.tabela_cronograma = QTableWidget(0, 29)
        headers = ["Etapa", "Valor Etapa"]
        for i in range(1,13): headers += [f"P{i} %", f"P{i} R$"]
        headers += ["% Total", "Valor Distribuído", "Status"]
        self.tabela_cronograma.setHorizontalHeaderLabels(headers)
        configurar_tabela_responsiva(self.tabela_cronograma, stretch_columns=[0])
        self.tabela_cronograma.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.EditKeyPressed
            | QAbstractItemView.AnyKeyPressed
            | QAbstractItemView.SelectedClicked
        )
        self.tabela_cronograma.setMinimumHeight(430)
        layout.addWidget(self.tabela_cronograma)
        return scroll

    # ------------------------- DOCUMENTOS / ANEXOS -------------------------
    def aba_anexos(self):
        scroll, layout = self._scroll_page()

        box = QGroupBox("Documentos e anexos do orçamento")
        lay = QVBoxLayout(box)
        lay.setSpacing(10)

        info = QLabel("Anexe fotos, OS, cotações, propostas de fornecedor, PDFs SINAPI, aceite, ART/RRT e demais documentos complementares. Ao adicionar, o arquivo será copiado para a pasta de anexos do sistema/workspace compartilhado.")
        info.setStyleSheet("color:#64748B;font-weight:700;")
        lay.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        self.doc_tipo = QComboBox()
        self.doc_tipo.addItems([
            "Cotação",
            "Proposta de fornecedor",
            "PDF SINAPI",
            "Foto",
            "OS / Ordem de Serviço",
            "Documento de aceite",
            "ART / RRT",
            "Contrato / Aditivo",
            "Memorial / Descritivo",
            "Outro",
        ])
        self.doc_tipo.setMinimumHeight(38)

        self.doc_caminho = QLineEdit()
        self.doc_caminho.setReadOnly(True)
        self.doc_caminho.setMinimumHeight(38)
        self.doc_caminho.setPlaceholderText("Selecione um arquivo para anexar ao orçamento")

        self.doc_obs = QTextEdit()
        self.doc_obs.setMinimumHeight(80)
        self.doc_obs.setPlaceholderText("Observação do anexo, referência, fornecedor, número da OS ou justificativa técnica.")

        self.btn_doc_selecionar = self.botao("Selecionar arquivo", "#2563EB")
        self.btn_doc_adicionar = self.botao("Adicionar anexo", "#0B3B75")
        self.btn_doc_excluir = self.botao("Excluir anexo selecionado", "#DC2626")

        self.btn_doc_selecionar.clicked.connect(self.selecionar_arquivo_anexo)
        self.btn_doc_adicionar.clicked.connect(self.adicionar_anexo)
        self.btn_doc_excluir.clicked.connect(self.excluir_anexo)

        grid.addWidget(QLabel("Tipo"), 0, 0)
        grid.addWidget(QLabel("Arquivo"), 0, 1)
        grid.addWidget(self.doc_tipo, 1, 0)
        grid.addWidget(self.doc_caminho, 1, 1)
        grid.addWidget(self.btn_doc_selecionar, 1, 2)
        grid.addWidget(QLabel("Observação"), 2, 0, 1, 3)
        grid.addWidget(self.doc_obs, 3, 0, 1, 3)

        botoes = QHBoxLayout()
        botoes.addWidget(self.btn_doc_adicionar, 2)
        botoes.addWidget(self.btn_doc_excluir, 1)

        lay.addLayout(grid)
        lay.addLayout(botoes)
        layout.addWidget(box)

        self.tabela_anexos = QTableWidget(0, 6)
        self.tabela_anexos.setHorizontalHeaderLabels(["ID", "Tipo", "Nome do arquivo", "Caminho", "Data", "Observação"])
        configurar_tabela_responsiva(self.tabela_anexos, stretch_columns=[2, 5], hidden_columns=[0])
        self.tabela_anexos.setMinimumHeight(360)
        self.tabela_anexos.cellClicked.connect(self.selecionar_anexo)
        layout.addWidget(self.tabela_anexos)

        layout.addStretch()
        return scroll

    # ------------------------- GERAÇÃO -------------------------
    def aba_geracao(self):
        scroll, layout = self._scroll_page()

        info = QLabel(
            "Geração separada por finalidade: pacote gerencial interno e documentos finais para Prefeitura."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#64748B;font-weight:750;margin-bottom:6px;")
        layout.addWidget(info)

        row = QHBoxLayout()
        row.setSpacing(14)

        box1 = QGroupBox("Gerencial / Interno")
        bl1 = QVBoxLayout(box1)
        bl1.setSpacing(10)

        btn_revisao = self.botao("Gerar pacote gerencial")
        btn_dashboard = self.botao("Gerar Dashboard Executivo")

        btn_revisao.clicked.connect(self.gerar_revisao)
        btn_dashboard.clicked.connect(self.gerar_html)

        bl1.addWidget(btn_revisao)
        bl1.addWidget(btn_dashboard)
        bl1.addStretch()

        row.addWidget(box1)

        box2 = QGroupBox("Final / Prefeitura")
        bl2 = QVBoxLayout(box2)
        bl2.setSpacing(10)

        btn_pdf = self.botao("Gerar PDF", "#DC2626")
        btn_word = self.botao("Gerar Word", "#2563EB")
        btn_excel = self.botao("Gerar Excel", "#16A34A")
        btn_completo = self.botao("Gerar Pacote Completo", "#0B3B75")
        btn_simples = self.botao("Orçamento simples para terceiros", "#0F766E")

        btn_pdf.clicked.connect(self.gerar_pdf)
        btn_word.clicked.connect(self.gerar_word)
        btn_excel.clicked.connect(self.gerar_excel)
        btn_completo.clicked.connect(self.gerar_pacote_completo)
        btn_simples.clicked.connect(self.gerar_orcamento_simples)

        bl2.addWidget(btn_pdf)
        bl2.addWidget(btn_word)
        bl2.addWidget(btn_excel)
        bl2.addWidget(btn_completo)
        bl2.addWidget(btn_simples)
        bl2.addStretch()

        row.addWidget(box2)

        layout.addLayout(row)
        layout.addStretch()

        return scroll

    # ------------------------- DATA LOAD -------------------------
    def _set_combo_data(self, combo, value):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def carregar_representantes_legais_combo(self, preservar=None):
        if not hasattr(self, "representante_legal_id"):
            return
        atual = preservar if preservar is not None else self.representante_legal_id.currentData()
        self.representante_legal_id.clear()
        self.representante_legal_id.addItem("Usar representante padrão da empresa", None)
        try:
            with conn() as c:
                rows = c.execute("SELECT id, nome, cargo FROM empresa_representantes WHERE ativo=1 ORDER BY ordem, nome").fetchall()
            for r in rows:
                rotulo = r["nome"] or "Representante"
                if r["cargo"]:
                    rotulo += f" | {r['cargo']}"
                self.representante_legal_id.addItem(rotulo, r["id"])
        except Exception:
            pass
        self._set_combo_data(self.representante_legal_id, atual)


    def gerar_proximo_codigo_orcamento(self):
        from datetime import datetime
        ano = datetime.now().year
        prefixo = f"ORC-{ano}-"
        with conn() as c:
            codigos = c.execute("SELECT codigo FROM orcamentos WHERE codigo LIKE ?", (prefixo + "%",)).fetchall()
        maior = 0
        for r in codigos:
            codigo = str(r["codigo"] or "")
            try:
                maior = max(maior, int(codigo.replace(prefixo, "").split()[0].strip()))
            except Exception:
                pass
        return f"{prefixo}{maior + 1:03d}"

    def aplicar_margem_global_opcional(self):
        if getattr(self, "_carregando_combos", False): return
        nova = float(self.margem.value() or 0)
        antiga = float(getattr(self, "_ultima_margem_global", nova) or 0)
        if abs(nova - antiga) < 0.001: return
        self.margem_item.setValue(nova)
        if hasattr(self, "opex_margem"): self.opex_margem.setValue(nova)
        if not self.orcamento_id:
            self._ultima_margem_global = nova; return
        resp = QMessageBox.question(self, "Margem global", "Deseja aplicar a nova margem global em todos os itens CAPEX e OPEX deste orçamento?\n\nSim = atualiza todos os itens já lançados.\nNão = aplica somente nos próximos itens.", QMessageBox.Yes | QMessageBox.No)
        if resp == QMessageBox.Yes:
            with conn() as c:
                c.execute("UPDATE itens SET margem=?WHERE orcamento_id=?", (nova, self.orcamento_id))
                c.execute("UPDATE opex SET margem=?WHERE orcamento_id=?", (nova, self.orcamento_id))
                c.commit()
            self.carregar_itens(); self.carregar_opex(); self.carregar_etapas(); self.gerar_cronograma_automatico(); self.atualizar_resumos()
        self._ultima_margem_global = nova

    def carregar_combos(self, preservar=False):
        cliente_atual = self.cliente.currentData() if preservar and hasattr(self, "cliente") else None
        contrato_atual = self.contrato.currentData() if preservar and hasattr(self, "contrato") else None
        aditivo_atual = self.aditivo.currentData() if preservar and hasattr(self, "aditivo") else None
        segmento_atual = self.segmento.currentData() if preservar and hasattr(self, "segmento") else None

        self._carregando_combos = True
        with conn() as c:
            clientes = c.execute("SELECT id,nome,uf FROM clientes ORDER BY nome").fetchall()

        self.cliente.clear()
        self.contrato.clear()
        self.aditivo.clear()
        self.segmento.clear()

        self.cliente.addItem("Selecione o cliente", None)
        self.contrato.addItem("Selecione o contrato PPP", None)
        self.aditivo.addItem("Sem aditivo", None)
        self.segmento.addItem("Selecione o segmento", None)

        for r in clientes:
            self.cliente.addItem(f"{r['nome']} - {r['uf'] or ''}", r['id'])

        self._set_combo_data(self.cliente, cliente_atual)
        self._carregando_combos = False

        self.carregar_contratos_cliente(preservar_contrato=contrato_atual)
        self.atualizar_vinculos_contrato(
            preservar_aditivo=aditivo_atual,
            preservar_segmento=segmento_atual,
        )
        self.carregar_representantes_legais_combo()

    def carregar_contratos_cliente(self, preservar_contrato=None):
        """Carrega somente contratos do cliente selecionado."""
        if self._carregando_combos:
            return

        cliente_id = self.cliente.currentData()

        self._carregando_combos = True
        self.contrato.clear()
        self.contrato.addItem("Selecione o contrato PPP", None)
        self.aditivo.clear()
        self.aditivo.addItem("Sem aditivo", None)
        self.segmento.clear()
        self.segmento.addItem("Selecione o segmento", None)

        if cliente_id:
            with conn() as c:
                contratos = c.execute("""
                    SELECT co.id, co.nome, co.numero, co.municipio, cl.nome AS cliente
                    FROM contratos co
                    LEFT JOIN clientes cl ON cl.id=co.cliente_id
                    WHERE co.cliente_id=?
                    ORDER BY co.nome
                """, (cliente_id,)).fetchall()

            for r in contratos:
                rotulo = f"{r['nome'] or 'Contrato'}"
                if r['numero']:
                    rotulo += f" | Nº {r['numero']}"
                if r['cliente']:
                    rotulo += f" | {r['cliente']}"
                self.contrato.addItem(rotulo, r['id'])

        self._set_combo_data(self.contrato, preservar_contrato)
        self._carregando_combos = False
    def atualizar_vinculos_contrato(self, *args, preservar_aditivo=None, preservar_segmento=None):
        if self._carregando_combos:
            return

        contrato_id = self.contrato.currentData()

        self._carregando_combos = True
        self.aditivo.clear(); self.segmento.clear()
        self.aditivo.addItem("Sem aditivo", None)
        self.segmento.addItem("Selecione o segmento", None)

        with conn() as c:
            contrato = None
            aditivos = []
            segmentos = []

            if contrato_id:
                contrato = c.execute("SELECT * FROM contratos WHERE id=?", (contrato_id,)).fetchone()
                aditivos = c.execute("""
                    SELECT a.id, a.numero_aditivo, a.objeto, a.segmento_id, s.nome AS segmento
                    FROM aditivos a
                    LEFT JOIN segmentos s ON s.id=a.segmento_id
                    WHERE a.contrato_id=?
                    ORDER BY a.id DESC
                """, (contrato_id,)).fetchall()
                segmentos = c.execute("""
                    SELECT s.id, s.nome
                    FROM segmentos s
                    INNER JOIN contrato_segmentos cs ON cs.segmento_id=s.id
                    WHERE cs.contrato_id=?
                    ORDER BY s.id
                """, (contrato_id,)).fetchall()

            else:
                segmentos = []

        if contrato:
            if contrato['cliente_id']:
                self._set_combo_data(self.cliente, contrato['cliente_id'])
            if contrato['municipio'] and not self.municipio.text().strip():
                self.municipio.setText(contrato['municipio'])

        for r in aditivos:
            rotulo = f"{r['numero_aditivo'] or r['id']}"
            if r['segmento']:
                rotulo += f" | {r['segmento']}"
            if r['objeto']:
                rotulo += f" - {r['objeto']}"
            self.aditivo.addItem(rotulo, r['id'])

        for r in segmentos:
            self.segmento.addItem(r['nome'], r['id'])

        self._set_combo_data(self.aditivo, preservar_aditivo)
        self._set_combo_data(self.segmento, preservar_segmento)
        self._carregando_combos = False

    def preencher_dados_cliente(self):
        if self._carregando_combos:
            return
        cliente_id = self.cliente.currentData()
        if not cliente_id:
            self.municipio.clear()
            self.carregar_contratos_cliente()
            return

        with conn() as c:
            cliente = c.execute("SELECT municipio, uf FROM clientes WHERE id=?", (cliente_id,)).fetchone()

        if cliente:
            municipio = cliente['municipio'] or ''
            uf = cliente['uf'] or ''
            self.municipio.setText(f"{municipio}/{uf}" if municipio and uf else municipio)

        self.carregar_contratos_cliente()
        self.atualizar_vinculos_contrato()

    def preencher_segmento_por_aditivo(self):
        if self._carregando_combos:
            return
        aditivo_id = self.aditivo.currentData()
        if not aditivo_id:
            return
        with conn() as c:
            aditivo = c.execute("SELECT segmento_id FROM aditivos WHERE id=?", (aditivo_id,)).fetchone()
        if aditivo and aditivo['segmento_id']:
            self._set_combo_data(self.segmento, aditivo['segmento_id'])

    def carregar_orcamentos(self):
        orcamento_ativo = self.orcamento_id or self.cbo_orcamentos.currentData()
        bloqueio = QSignalBlocker(self.cbo_orcamentos)
        self.cbo_orcamentos.clear()
        with conn() as c:
            dados = c.execute("SELECT id,codigo,status,objeto FROM orcamentos ORDER BY id DESC").fetchall()
        for r in dados:
            self.cbo_orcamentos.addItem(f"{r['codigo']} | {r['status'] or ''} | {r['objeto'] or ''}", r['id'])
        if orcamento_ativo:
            idx = self.cbo_orcamentos.findData(orcamento_ativo)
            if idx >= 0:
                self.cbo_orcamentos.setCurrentIndex(idx)
        del bloqueio

    def _proximo_codigo_interno(self, prefixo, tabela="itens"):
        """Gera código sequencial para composição própria, sem depender de SINAPI."""
        try:
            with conn() as c:
                rows = c.execute(
                    f"SELECT codigo FROM {tabela} WHERE codigo LIKE ?ORDER BY id DESC",
                    (prefixo + "%",)
                ).fetchall()
            maior = 0
            for r in rows:
                cod = str(r["codigo"] or "")
                try:
                    maior = max(maior, int(cod.replace(prefixo, "").strip()))
                except Exception:
                    pass
            return f"{prefixo}{maior + 1:03d}"
        except Exception:
            return f"{prefixo}001"

    def aplicar_modo_fonte_capex(self):
        if not hasattr(self, "codigo_sinapi"):
            return
        fonte = self.fonte.currentText()
        combo = self.codigo_sinapi
        combo.setEditable(True)

        if fonte == "SINAPI":
            combo.lineEdit().setPlaceholderText("Clique em Buscar SINAPI para pesquisar sem travar")
            if hasattr(self, "btn_buscar_sinapi_capex"):
                self.btn_buscar_sinapi_capex.setEnabled(True)
        elif fonte == "Composição Própria":
            combo.clear()
            combo.lineEdit().setPlaceholderText("Código automático da composição própria")
            combo.setCurrentText(self._proximo_codigo_interno("COMP-MAT-"))
            if hasattr(self, "btn_buscar_sinapi_capex"):
                self.btn_buscar_sinapi_capex.setEnabled(False)
        else:
            combo.clear()
            combo.lineEdit().setPlaceholderText("Digite o código/referência do fornecedor ou cotação")
            combo.setCurrentText("")
            if hasattr(self, "btn_buscar_sinapi_capex"):
                self.btn_buscar_sinapi_capex.setEnabled(False)


    def aplicar_modo_fonte_opex(self):
        if not hasattr(self, "opex_codigo"):
            return
        fonte = self.opex_fonte.currentText()
        combo = self.opex_codigo
        combo.setEditable(True)

        if fonte == "SINAPI":
            combo.lineEdit().setPlaceholderText("Clique em Buscar SINAPI para pesquisar sem travar")
            if hasattr(self, "btn_buscar_sinapi_opex"):
                self.btn_buscar_sinapi_opex.setEnabled(True)
        elif fonte == "Composição Própria":
            combo.clear()
            combo.lineEdit().setPlaceholderText("Código automático da composição própria OPEX")
            combo.setCurrentText(self._proximo_codigo_interno("COMP-OPEX-", tabela="opex"))
            if hasattr(self, "btn_buscar_sinapi_opex"):
                self.btn_buscar_sinapi_opex.setEnabled(False)
        else:
            combo.clear()
            combo.lineEdit().setPlaceholderText("Digite o código/referência do fornecedor ou cotação")
            combo.setCurrentText("")
            if hasattr(self, "btn_buscar_sinapi_opex"):
                self.btn_buscar_sinapi_opex.setEnabled(False)


    def _configurar_combo_sinapi(self, combo):
        """Configura o combo SINAPI para busca digitável, sem depender de rolar lista gigante."""
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMaxVisibleItems(20)
        combo.setMinimumContentsLength(30)
        if combo.lineEdit():
            combo.lineEdit().setPlaceholderText("Digite código ou parte da descrição. Ex.: defletor, cabo cobre, poste...")

    def _garantir_indices_sinapi(self):
        try:
            with conn() as c:
                c.execute("CREATE INDEX IF NOT EXISTS idx_sinapi_codigo ON sinapi(codigo)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_sinapi_descricao ON sinapi(descricao)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_sinapi_uf ON sinapi(uf)")
                c.commit()
        except Exception:
            pass

    def _pesquisar_sinapi(self, termo, limite=80):
        termo = str(termo or "").strip()
        if len(termo) < 2:
            return []

        palavras = [p.strip() for p in termo.replace("-", " ").split() if p.strip()]
        params = []
        where_parts = []

        # Código direto ou trecho de código
        where_parts.append("codigo LIKE ?")
        params.append(f"%{termo}%")

        # Descrição contém todas as palavras digitadas, mesmo fora de ordem.
        if palavras:
            desc_parts = []
            for p in palavras:
                desc_parts.append("UPPER(descricao) LIKE UPPER(?)")
                params.append(f"%{p}%")
            where_parts.append("(" + " AND ".join(desc_parts) + ")")

        sql = f"""
            SELECT codigo, descricao, unidade, custo, classificacao
            FROM sinapi
            WHERE {' OR '.join(where_parts)}
            ORDER BY
                CASE
                    WHEN codigo = ?THEN 0
                    WHEN codigo LIKE ?THEN 1
                    WHEN UPPER(descricao) LIKE UPPER(?) THEN 2
                    ELSE 3
                END,
                descricao
            LIMIT ?
        """
        params.extend([termo, f"{termo}%", f"%{termo}%", limite])

        with conn() as c:
            return c.execute(sql, params).fetchall()

    def _atualizar_combo_sinapi(self, combo, termo):
        """Filtra SINAPI enquanto digita, sem selecionar automaticamente nenhum item."""
        termo = str(termo or "").strip()

        if len(termo) < 2:
            bloqueio = QSignalBlocker(combo)
            combo.clear()
            del bloqueio
            if combo.lineEdit():
                combo.lineEdit().setText(termo)
                combo.lineEdit().setCursorPosition(len(termo))
            return

        dados = self._pesquisar_sinapi(termo)

        bloqueio = QSignalBlocker(combo)
        combo.clear()

        for r in dados:
            txt = f"{r['codigo']} - {r['descricao']}"
            combo.addItem(txt, r['codigo'])

        if termo and not dados:
            combo.addItem("Nenhum item SINAPI encontrado para a busca digitada", None)

        try:
            combo.setCurrentIndex(-1)
        except Exception:
            pass

        del bloqueio

        if combo.lineEdit():
            combo.lineEdit().setText(termo)
            combo.lineEdit().setCursorPosition(len(termo))

        if dados:
            try:
                combo.view().setMinimumWidth(combo.width())
            except Exception:
                pass
            QTimer.singleShot(0, combo.showPopup)


    def pesquisar_sinapi_capex(self, termo):
        if self.fonte.currentText() == 'SINAPI':
            self._atualizar_combo_sinapi(self.codigo_sinapi, termo)

    def pesquisar_sinapi_opex(self, termo):
        if self.opex_fonte.currentText() == 'SINAPI':
            self._atualizar_combo_sinapi(self.opex_codigo, termo)

    def _selecionar_primeiro_sinapi(self, combo, preencher_fn):
        termo = combo.currentText().strip()
        if not termo or termo.startswith("Nenhum item"):
            return

        # Se já está no formato "código - descrição", usa a seleção atual.
        if " - " in termo and combo.currentData():
            preencher_fn()
            return

        dados = self._pesquisar_sinapi(termo, limite=1)
        if not dados:
            return

        r = dados[0]
        texto_item = f"{r['codigo']} - {r['descricao']}"

        bloqueio = QSignalBlocker(combo)
        combo.clear()
        combo.addItem(texto_item, r['codigo'])
        combo.setCurrentIndex(0)
        del bloqueio

        preencher_fn()

    def selecionar_primeiro_sinapi_capex(self):
        pass


    def selecionar_primeiro_sinapi_opex(self):
        pass


    def carregar_sinapi_lista(self):
        """A busca SINAPI agora usa janela com tabela para não travar a digitação."""
        self._garantir_indices_sinapi()



    def garantir_orcamento(self):
        if not self.orcamento_id:
            self.salvar_orcamento(silencioso=True)
        return self.orcamento_id

    def salvar_orcamento(self, silencioso=False):
        if not self.codigo.text().strip():
            self.codigo.setText(self.gerar_proximo_codigo_orcamento())
        with conn() as c:
            if self.orcamento_id:
                c.execute("""
                    UPDATE orcamentos SET codigo=?, cliente_id=?, contrato_id=?, aditivo_id=?, segmento_id=?, objeto=?, municipio=?, validade=?, texto_proposta=?, bdi_global=?, margem_global=?, status=?,
                    usar_rt_especifico=?, rt_nome=?, rt_registro=?, rt_cpf=?, rt_cargo=?, rt_especialidade=?, rt_email=?, rt_telefone=?, rt_art=?, rt_assinatura_path=?,
                    gestor_contrato_nome=?, gestor_contrato_cargo=?, gestor_contrato_cpf=?, gestor_contrato_email=?, gestor_contrato_telefone=?,
                    fiscal_contrato_nome=?, fiscal_contrato_cargo=?, fiscal_contrato_setor=?, fiscal_contrato_email=?, fiscal_contrato_telefone=?, representante_legal_id=?,
                    data_atualizacao=datetime('now') WHERE id=?
                """, (self.codigo.text(), self.cliente.currentData(), self.contrato.currentData(), self.aditivo.currentData(), self.segmento.currentData(), self.objeto.text(), self.municipio.text(), self.validade.text(), self.texto_proposta.toPlainText(), self.bdi.value(), self.margem.value(), self.status.currentText(),
                      1 if self.usar_rt_especifico.isChecked() else 0, self.rt_nome.text(), self.rt_registro.text(), self.rt_cpf.text(), self.rt_cargo.text(), self.rt_especialidade.text(), self.rt_email.text(), self.rt_telefone.text(), self.rt_art.text(), self.rt_assinatura_path.text(),
                      self.gestor_contrato_nome.text(), self.gestor_contrato_cargo.text(), self.gestor_contrato_cpf.text(), self.gestor_contrato_email.text(), self.gestor_contrato_telefone.text(),
                      self.fiscal_contrato_nome.text(), self.fiscal_contrato_cargo.text(), self.fiscal_contrato_setor.text(), self.fiscal_contrato_email.text(), self.fiscal_contrato_telefone.text(), self.representante_legal_id.currentData(), self.orcamento_id))
            else:
                cur = c.execute("""
                    INSERT INTO orcamentos(codigo, cliente_id, contrato_id, aditivo_id, segmento_id, objeto, municipio, validade, texto_proposta, bdi_global, margem_global, status,
                    usar_rt_especifico, rt_nome, rt_registro, rt_cpf, rt_cargo, rt_especialidade, rt_email, rt_telefone, rt_art, rt_assinatura_path,
                    gestor_contrato_nome, gestor_contrato_cargo, gestor_contrato_cpf, gestor_contrato_email, gestor_contrato_telefone,
                    fiscal_contrato_nome, fiscal_contrato_cargo, fiscal_contrato_setor, fiscal_contrato_email, fiscal_contrato_telefone, representante_legal_id,
                    data_criacao, data_atualizacao)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
                """, (self.codigo.text(), self.cliente.currentData(), self.contrato.currentData(), self.aditivo.currentData(), self.segmento.currentData(), self.objeto.text(), self.municipio.text(), self.validade.text(), self.texto_proposta.toPlainText(), self.bdi.value(), self.margem.value(), self.status.currentText(),
                      1 if self.usar_rt_especifico.isChecked() else 0, self.rt_nome.text(), self.rt_registro.text(), self.rt_cpf.text(), self.rt_cargo.text(), self.rt_especialidade.text(), self.rt_email.text(), self.rt_telefone.text(), self.rt_art.text(), self.rt_assinatura_path.text(),
                      self.gestor_contrato_nome.text(), self.gestor_contrato_cargo.text(), self.gestor_contrato_cpf.text(), self.gestor_contrato_email.text(), self.gestor_contrato_telefone.text(),
                      self.fiscal_contrato_nome.text(), self.fiscal_contrato_cargo.text(), self.fiscal_contrato_setor.text(), self.fiscal_contrato_email.text(), self.fiscal_contrato_telefone.text(), self.representante_legal_id.currentData()))
                self.orcamento_id = cur.lastrowid
            c.commit()
        self.carregar_orcamentos()
        if not silencioso: QMessageBox.information(self, "Orçamento", "Orçamento salvo.")

    def abrir_orcamento(self, orcamento_id=None):
        """Abre orçamento pelo combo da tela ou por ID vindo de Meus Orçamentos.

        Observação: o sinal clicked do QPushButton envia um booleano (checked=False).
        Quando o botão Abrir é clicado, esse False não pode ser tratado como ID.
        """
        if isinstance(orcamento_id, bool) or orcamento_id is None:
            oid = self.cbo_orcamentos.currentData()
        else:
            oid = orcamento_id

        try:
            oid = int(oid)
        except (TypeError, ValueError):
            QMessageBox.warning(self, "Orçamento", "Selecione um orçamento para abrir.")
            return

        self.orcamento_id = oid

        with conn() as c:
            o = c.execute("SELECT * FROM orcamentos WHERE id=?", (oid,)).fetchone()

        if not o:
            QMessageBox.warning(self, "Orçamento", "Orçamento não encontrado no banco de dados.")
            return

        self._carregando_combos = True
        try:
            self.codigo.setText(o['codigo'] or '')
            self.carregar_combos(preservar=False)
            self._set_combo_data(self.cliente, o['cliente_id'])
            self.carregar_contratos_cliente()
            self._set_combo_data(self.contrato, o['contrato_id'])
            self.atualizar_vinculos_contrato(preservar_aditivo=o['aditivo_id'], preservar_segmento=o['segmento_id'])
            self._set_combo_data(self.aditivo, o['aditivo_id'])
            self._set_combo_data(self.segmento, o['segmento_id'])
        finally:
            self._carregando_combos = False

        self.objeto.setText(o['objeto'] or '')
        self.municipio.setText(o['municipio'] or '')
        self.validade.setText(o['validade'] or '')
        self.texto_proposta.setPlainText(o['texto_proposta'] or '')
        self.bdi.setValue(float(o['bdi_global'] or 0))
        self.bdi_item.setValue(float(o['bdi_global'] or 0))
        self.margem.setValue(float(o['margem_global'] or 18))
        self._ultima_margem_global = float(o['margem_global'] or 18)
        self.margem_item.setValue(float(o['margem_global'] or 18))
        self.status.setCurrentText(o['status'] or 'RASCUNHO')
        keys = set(o.keys())
        self.usar_rt_especifico.setChecked(bool(o['usar_rt_especifico']) if 'usar_rt_especifico' in keys else False)
        for nome in ['rt_nome','rt_registro','rt_cpf','rt_cargo','rt_especialidade','rt_email','rt_telefone','rt_art','rt_assinatura_path','gestor_contrato_nome','gestor_contrato_cargo','gestor_contrato_cpf','gestor_contrato_email','gestor_contrato_telefone','fiscal_contrato_nome','fiscal_contrato_cargo','fiscal_contrato_setor','fiscal_contrato_email','fiscal_contrato_telefone']:
            if nome in keys and hasattr(self, nome):
                getattr(self, nome).setText(str(o[nome] or ''))
        self.carregar_representantes_legais_combo(o['representante_legal_id'] if 'representante_legal_id' in keys else None)

        idx = self.cbo_orcamentos.findData(oid)
        if idx >= 0:
            self.cbo_orcamentos.setCurrentIndex(idx)

        self.carregar_etapas()
        self.carregar_itens()
        self.carregar_opex()
        self.carregar_anexos()
        self.gerar_cronograma_automatico()
        self.atualizar_resumos()

    def novo_orcamento(self):
        self.orcamento_id = None; self.selected_capex_item_id = None; self.selected_opex_id = None; self.selected_etapa_id = None
        self.carregar_combos(preservar=False)
        self.codigo.setText(self.gerar_proximo_codigo_orcamento())
        self.objeto.clear(); self.municipio.clear(); self.validade.setText("60 dias"); self.texto_proposta.clear(); self.status.setCurrentText("RASCUNHO")
        self.usar_rt_especifico.setChecked(False)
        for nome in ['rt_nome','rt_registro','rt_cpf','rt_cargo','rt_especialidade','rt_email','rt_telefone','rt_art','rt_assinatura_path','gestor_contrato_nome','gestor_contrato_cargo','gestor_contrato_cpf','gestor_contrato_email','gestor_contrato_telefone','fiscal_contrato_nome','fiscal_contrato_cargo','fiscal_contrato_setor','fiscal_contrato_email','fiscal_contrato_telefone']:
            if hasattr(self, nome): getattr(self, nome).clear()
        self.carregar_representantes_legais_combo()
        self.bdi.setValue(0); self.margem.setValue(18); self._ultima_margem_global = 18
        self.bdi_item.setValue(0); self.margem_item.setValue(18)
        if hasattr(self, "opex_bdi"):
            self.opex_bdi.setValue(0); self.opex_margem.setValue(18)
        self.etapa_nome.clear(); self.tabela_etapas.setRowCount(0); self.tabela_itens.setRowCount(0); self.tabela_opex.setRowCount(0); self.tabela_cronograma.setRowCount(0)
        self.carregar_anexos(); self.etapa_item.clear(); self.atualizar_resumos()

    def adicionar_etapa(self):
        if not self.garantir_orcamento(): return
        nome = self.etapa_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Etapa", "Informe o nome da etapa."); return
        with conn() as c:
            ordem = c.execute("SELECT COALESCE(MAX(ordem),0)+1 FROM etapas_orcamento WHERE orcamento_id=?", (self.orcamento_id,)).fetchone()[0]
            cur = c.execute("INSERT INTO etapas_orcamento(orcamento_id,nome,descricao,ordem) VALUES(?,?,?,?)", (self.orcamento_id,nome,'',ordem))
            etapa_id = cur.lastrowid; c.commit()
        self.etapa_nome.clear(); self.carregar_etapas(); idx = self.etapa_item.findData(etapa_id)
        if idx >= 0: self.etapa_item.setCurrentIndex(idx)

    def carregar_etapas(self):
        self.etapa_item.clear()
        if not self.orcamento_id: return
        with conn() as c:
            dados = c.execute("""
                SELECT e.id,e.ordem,e.nome,COALESCE(SUM(i.quantidade*i.custo_unit*(1+COALESCE(i.bdi,0)/100.0)*(1+COALESCE(i.margem,0)/100.0)),0) total
                FROM etapas_orcamento e LEFT JOIN itens i ON i.etapa_id=e.id AND i.orcamento_id=e.orcamento_id AND i.capex_opex='CAPEX'
                WHERE e.orcamento_id=?GROUP BY e.id ORDER BY e.ordem, e.id
            """, (self.orcamento_id,)).fetchall()
        rows=[]
        for pos,r in enumerate(dados,start=1):
            rotulo=f"Etapa {pos}"
            rows.append([r['id'], rotulo, r['nome'], self.moeda(r['total'])])
            self.etapa_item.addItem(f"{rotulo} - {r['nome']}", r['id'])
        self._set_table(self.tabela_etapas, rows)
        try: self.tabela_etapas.setColumnHidden(0, True)
        except Exception: pass

    def selecionar_etapa(self, row, col):
        item = self.tabela_etapas.item(row,0)
        if item:
            self.selected_etapa_id = int(item.text())
            idx = self.etapa_item.findData(self.selected_etapa_id)
            if idx >= 0:
                self.etapa_item.setCurrentIndex(idx)

            # Carrega a descrição/nome da etapa no campo superior para permitir edição.
            desc_item = self.tabela_etapas.item(row, 2)
            if desc_item:
                self.etapa_nome.setText(desc_item.text())

    def atualizar_etapa(self):
        """Edita a etapa selecionada e aplica o novo nome aos itens vinculados."""
        if not self.orcamento_id:
            QMessageBox.warning(self, "Etapa", "Abra ou salve um orçamento antes de editar a etapa.")
            return

        etapa_id = self.etapa_item.currentData() or self.selected_etapa_id
        if not etapa_id:
            QMessageBox.warning(self, "Etapa", "Selecione uma etapa para editar.")
            return

        novo_nome = self.etapa_nome.text().strip()
        if not novo_nome:
            QMessageBox.warning(self, "Etapa", "Informe o novo nome/descrição da etapa.")
            return

        with conn() as c:
            etapa = c.execute("SELECT nome FROM etapas_orcamento WHERE id=?AND orcamento_id=?", (etapa_id, self.orcamento_id)).fetchone()
            if not etapa:
                QMessageBox.warning(self, "Etapa", "Etapa não localizada neste orçamento.")
                return

            nome_antigo = etapa["nome"] or ""

        if novo_nome == nome_antigo:
            QMessageBox.information(self, "Etapa", "Nenhuma alteração identificada.")
            return

        resp = QMessageBox.question(
            self,
            "Atualizar etapa",
            "Deseja atualizar esta etapa e aplicar o novo nome aos itens CAPEX vinculados a ela?\n\n"
            f"De: {nome_antigo}\n"
            f"Para: {novo_nome}",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        with conn() as c:
            c.execute("UPDATE etapas_orcamento SET nome=?WHERE id=?AND orcamento_id=?", (novo_nome, etapa_id, self.orcamento_id))
            # Mantém compatibilidade com relatórios/telas que ainda leem o campo texto 'etapa' nos itens.
            c.execute("UPDATE itens SET etapa=?WHERE orcamento_id=?AND etapa_id=?", (novo_nome, self.orcamento_id, etapa_id))
            c.commit()

        self.selected_etapa_id = etapa_id
        self.carregar_etapas()
        idx = self.etapa_item.findData(etapa_id)
        if idx >= 0:
            self.etapa_item.setCurrentIndex(idx)
        self.carregar_itens()
        self.gerar_cronograma_automatico()
        self.atualizar_resumos()
        QMessageBox.information(self, "Etapa", "Etapa atualizada e aplicada aos itens vinculados.")

    def excluir_etapa(self):
        etapa_id = self.etapa_item.currentData() or self.selected_etapa_id
        if not etapa_id:
            QMessageBox.warning(self, "Etapa", "Selecione uma etapa para excluir."); return
        with conn() as c:
            etapa = c.execute("SELECT nome FROM etapas_orcamento WHERE id=?", (etapa_id,)).fetchone()
            itens = c.execute("SELECT COUNT(*) qtd FROM itens WHERE etapa_id=?", (etapa_id,)).fetchone()["qtd"]
        if not etapa:
            QMessageBox.warning(self, "Etapa", "Etapa não localizada."); return
        msg = f"Deseja realmente excluir esta etapa?\n\n{etapa['nome']}"
        if itens: msg += f"\n\nEsta etapa possui {itens} item(ns) CAPEX vinculados. Ao confirmar, os itens também serão excluídos."
        resp = QMessageBox.question(self, "Excluir etapa", msg, QMessageBox.Yes | QMessageBox.No)
        if resp != QMessageBox.Yes: return
        with conn() as c:
            c.execute("DELETE FROM itens WHERE etapa_id=?", (etapa_id,))
            c.execute("DELETE FROM cronograma_parcelas WHERE etapa_id=?", (etapa_id,))
            c.execute("DELETE FROM etapas_orcamento WHERE id=?", (etapa_id,))
            restantes = c.execute("SELECT id FROM etapas_orcamento WHERE orcamento_id=?ORDER BY ordem, id", (self.orcamento_id,)).fetchall()
            for ordem,r in enumerate(restantes,start=1): c.execute("UPDATE etapas_orcamento SET ordem=?WHERE id=?", (ordem,r['id']))
            c.commit()
        self.selected_etapa_id=None; self.carregar_etapas(); self.carregar_itens(); self.gerar_cronograma_automatico(); self.atualizar_resumos()
        QMessageBox.information(self, "Etapa", "Etapa excluída com sucesso.")

    def abrir_busca_sinapi_capex(self):
        if self.fonte.currentText() != "SINAPI":
            QMessageBox.information(self, "SINAPI", "Selecione a fonte SINAPI para pesquisar na base oficial.")
            return
        dlg = SinapiSearchDialog(self, self.codigo_sinapi.currentText())
        if dlg.exec() == QDialog.Accepted and dlg.item_selecionado:
            self.aplicar_item_sinapi_capex(dlg.item_selecionado)

    def aplicar_item_sinapi_capex(self, row):
        self.codigo_sinapi.setCurrentText(str(row.get("codigo") or ""))
        self.descricao.setPlainText(row.get("descricao") or "")
        self.unidade.setText(row.get("unidade") or "")
        self.custo_unit.setValue(float(row.get("custo") or 0))
        classificacao = row.get("classificacao") or row.get("tipo") or ""
        if classificacao:
            idx = self.classificacao.findText(str(classificacao))
            if idx >= 0:
                self.classificacao.setCurrentIndex(idx)

    def abrir_busca_sinapi_opex(self):
        if self.opex_fonte.currentText() != "SINAPI":
            QMessageBox.information(self, "SINAPI", "Selecione a fonte SINAPI para pesquisar na base oficial.")
            return
        dlg = SinapiSearchDialog(self, self.opex_codigo.currentText())
        if dlg.exec() == QDialog.Accepted and dlg.item_selecionado:
            self.aplicar_item_sinapi_opex(dlg.item_selecionado)

    def aplicar_item_sinapi_opex(self, row):
        self.opex_codigo.setCurrentText(str(row.get("codigo") or ""))
        self.opex_descricao.setPlainText(row.get("descricao") or "")
        self.opex_unidade.setText(row.get("unidade") or "MÊS")
        self.opex_custo.setValue(float(row.get("custo") or 0))


    def buscar_sinapi_capex(self):
        """Preenche CAPEX somente quando o usuário escolhe um item SINAPI da lista."""
        if self.fonte.currentText() != 'SINAPI':
            return

        codigo_data = self.codigo_sinapi.currentData()
        if not codigo_data:
            return

        codigo = str(codigo_data).strip()
        if not codigo:
            return

        with conn() as c:
            r = c.execute(
                "SELECT descricao, unidade, custo, classificacao FROM sinapi WHERE codigo=?LIMIT 1",
                (codigo,)
            ).fetchone()

        if r:
            bloqueio = QSignalBlocker(self.codigo_sinapi)
            self.codigo_sinapi.setCurrentText(codigo)
            del bloqueio

            self.descricao.setPlainText(r['descricao'] or '')
            self.unidade.setText(r['unidade'] or '')
            self.custo_unit.setValue(float(r['custo'] or 0))
            if r['classificacao']:
                idx = self.classificacao.findText(str(r['classificacao']))
                if idx >= 0:
                    self.classificacao.setCurrentIndex(idx)


    def adicionar_item(self):
        if not self.garantir_orcamento(): return
        etapa_id = self.etapa_item.currentData()
        if not etapa_id: QMessageBox.warning(self,"CAPEX","Selecione ou crie uma etapa."); return
        desc = self.descricao.toPlainText().strip()
        if not desc: QMessageBox.warning(self,"CAPEX","Informe a descrição do item."); return
        if self.fonte.currentText() != "SINAPI" and not self.obs_item.toPlainText().strip():
            QMessageBox.warning(self, "CAPEX", "Itens fora de base SINAPI devem conter observação técnica/justificativa para rastreabilidade TCE/TCU."); return
        texto = self.codigo_sinapi.currentText(); codigo = texto.split(" - ")[0].strip() if " - " in texto else texto.strip()
        with conn() as c:
            etapa = c.execute("SELECT nome FROM etapas_orcamento WHERE id=?", (etapa_id,)).fetchone()
            dados = (self.orcamento_id, etapa_id, etapa['nome'] if etapa else '', self.fonte.currentText(), codigo, desc, self.unidade.text(), self.quantidade.value(), self.custo_unit.value(), self.bdi_item.value(), self.margem_item.value(), 'CAPEX', self.classificacao.currentText(), self.obs_item.toPlainText())
            if self.selected_capex_item_id:
                c.execute("""UPDATE itens SET orcamento_id=?,etapa_id=?,etapa=?,fonte=?,codigo=?,descricao=?,unidade=?,quantidade=?,custo_unit=?,bdi=?,margem=?,capex_opex=?,classificacao=?,observacao=?WHERE id=?AND orcamento_id=?""", dados+(self.selected_capex_item_id, self.orcamento_id))
            else:
                c.execute("""INSERT INTO itens(orcamento_id,etapa_id,etapa,fonte,codigo,descricao,unidade,quantidade,custo_unit,bdi,margem,capex_opex,classificacao,observacao) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", dados)
            c.commit()
        self.limpar_item_capex(); self.carregar_itens(); self.carregar_etapas(); self.gerar_cronograma_automatico(); self.atualizar_resumos()

    def carregar_itens(self):
        if not self.orcamento_id: return
        with conn() as c:
            dados = c.execute("""SELECT i.*, e.ordem AS etapa_ordem, e.nome AS etapa_nome FROM itens i LEFT JOIN etapas_orcamento e ON e.id=i.etapa_id AND e.orcamento_id=i.orcamento_id WHERE i.orcamento_id=?AND i.capex_opex='CAPEX' ORDER BY COALESCE(e.ordem,9999), i.id""", (self.orcamento_id,)).fetchall()
        rows=[]; total=0
        for r in dados:
            custo_total=float(r['quantidade'] or 0)*float(r['custo_unit'] or 0); t=self.total_item(r['quantidade'],r['custo_unit'],r['bdi'],r['margem']); total+=t
            etapa_label=f"Etapa {r['etapa_ordem']} - {r['etapa_nome'] or r['etapa'] or ''}" if r['etapa_ordem'] else (r['etapa'] or '')
            rows.append([r['id'], etapa_label, r['fonte'], r['codigo'], r['descricao'], r['unidade'], r['quantidade'], self.moeda(r['custo_unit']), self.moeda(custo_total), f"{float(r['bdi'] or 0):.2f}%", f"{float(r['margem'] or 0):.2f}%", self.moeda(t), r['classificacao']])
        self._set_table(self.tabela_itens, rows); self.lbl_resumo_capex.setText(f"CAPEX: {self.moeda(total)} | Itens: {len(rows)}")

    def selecionar_item_capex(self, row, col):
        item = self.tabela_itens.item(row,0); self.selected_capex_item_id = int(item.text()) if item else None
        if not self.selected_capex_item_id: return
        with conn() as c: r = c.execute("SELECT * FROM itens WHERE id=?", (self.selected_capex_item_id,)).fetchone()
        if not r: return
        idx=self.etapa_item.findData(r['etapa_id'])
        if idx>=0: self.etapa_item.setCurrentIndex(idx)
        idx=self.fonte.findText(r['fonte'] or '')
        if idx>=0: self.fonte.setCurrentIndex(idx)
        self.codigo_sinapi.setCurrentText(r['codigo'] or ''); self.descricao.setPlainText(r['descricao'] or ''); self.unidade.setText(r['unidade'] or '')
        self.quantidade.setValue(float(r['quantidade'] or 0)); self.custo_unit.setValue(float(r['custo_unit'] or 0)); self.bdi_item.setValue(float(r['bdi'] or 0)); self.margem_item.setValue(float(self.margem.value() if r['margem'] is None else r['margem']))
        idx=self.classificacao.findText(r['classificacao'] or '')
        if idx>=0: self.classificacao.setCurrentIndex(idx)
        self.obs_item.setPlainText(r['observacao'] or ''); self.btn_add_item.setText("Atualizar item CAPEX / pode mover etapa")

    def atualizar_item_sem_alterar_etapa(self):
        """Atualiza somente os dados do item selecionado, mantendo a etapa original do item."""
        if not self.orcamento_id:
            QMessageBox.warning(self, "CAPEX", "Abra ou salve um orçamento antes de atualizar o item.")
            return

        if not self.selected_capex_item_id:
            QMessageBox.warning(self, "CAPEX", "Selecione um item CAPEX na tabela antes de atualizar.")
            return

        desc = self.descricao.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "CAPEX", "Informe a descrição do item.")
            return
        if self.fonte.currentText() != "SINAPI" and not self.obs_item.toPlainText().strip():
            QMessageBox.warning(self, "CAPEX", "Itens fora de base SINAPI devem conter observação técnica/justificativa para rastreabilidade TCE/TCU.")
            return

        texto_codigo = self.codigo_sinapi.currentText()
        codigo = texto_codigo.split(" - ")[0].strip() if " - " in texto_codigo else texto_codigo.strip()

        with conn() as c:
            atual = c.execute(
                "SELECT id, etapa_id, etapa, descricao FROM itens WHERE id=?AND orcamento_id=?AND capex_opex='CAPEX'",
                (self.selected_capex_item_id, self.orcamento_id)
            ).fetchone()

        if not atual:
            QMessageBox.warning(self, "CAPEX", "Item selecionado não foi localizado neste orçamento.")
            return

        etapa_nome = atual["etapa"] or ""
        resp = QMessageBox.question(
            self,
            "Atualizar item sem alterar etapa",
            "Confirma atualizar este item mantendo a etapa original?\n\n"
            f"Etapa preservada: {etapa_nome}\n"
            f"Item atual: {atual['descricao'] or ''}\n\n"
            "Este comando NÃO move o item para outra etapa.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        with conn() as c:
            c.execute(
                """
                UPDATE itens
                SET fonte=?,
                    codigo=?,
                    descricao=?,
                    unidade=?,
                    quantidade=?,
                    custo_unit=?,
                    bdi=?,
                    margem=?,
                    classificacao=?,
                    observacao=?
                WHERE id=?AND orcamento_id=?AND capex_opex='CAPEX'
                """,
                (
                    self.fonte.currentText(),
                    codigo,
                    desc,
                    self.unidade.text(),
                    self.quantidade.value(),
                    self.custo_unit.value(),
                    self.bdi_item.value(),
                    self.margem_item.value(),
                    self.classificacao.currentText(),
                    self.obs_item.toPlainText(),
                    self.selected_capex_item_id,
                    self.orcamento_id,
                )
            )
            c.commit()

        self.carregar_itens()
        self.carregar_etapas()
        self.gerar_cronograma_automatico()
        self.atualizar_resumos()
        QMessageBox.information(self, "CAPEX", "Item atualizado sem alterar a etapa original.")

    def excluir_item_capex(self):
        if not self.selected_capex_item_id: return
        with conn() as c:
            c.execute("DELETE FROM itens WHERE id=?AND orcamento_id=?", (self.selected_capex_item_id, self.orcamento_id)); c.commit()
        self.selected_capex_item_id=None; self.carregar_itens(); self.carregar_etapas(); self.atualizar_resumos()

    def limpar_item_capex(self):
        self.selected_capex_item_id = None
        self.descricao.clear(); self.unidade.clear(); self.quantidade.setValue(1); self.custo_unit.setValue(0); self.bdi_item.setValue(self.bdi.value()); self.margem_item.setValue(self.margem.value()); self.obs_item.clear(); self.btn_add_item.setText("Adicionar item CAPEX"); self.aplicar_modo_fonte_capex()

    def atualizar_titulo_itens(self):
        pass

    # ------------------------- OPEX LOGIC -------------------------
    def buscar_sinapi_opex(self):
        """Preenche OPEX somente quando o usuário escolhe um item SINAPI da lista."""
        if self.opex_fonte.currentText() != 'SINAPI':
            return

        codigo_data = self.opex_codigo.currentData()
        if not codigo_data:
            return

        codigo = str(codigo_data).strip()
        if not codigo:
            return

        with conn() as c:
            r = c.execute(
                "SELECT descricao, unidade, custo FROM sinapi WHERE codigo=?LIMIT 1",
                (codigo,)
            ).fetchone()

        if r:
            bloqueio = QSignalBlocker(self.opex_codigo)
            self.opex_codigo.setCurrentText(codigo)
            del bloqueio

            self.opex_descricao.setPlainText(r['descricao'] or '')
            self.opex_unidade.setText(r['unidade'] or 'MÊS')
            self.opex_custo.setValue(float(r['custo'] or 0))


    def adicionar_opex(self):
        if not self.garantir_orcamento(): return
        desc = self.opex_descricao.toPlainText().strip()
        if not desc: QMessageBox.warning(self,"OPEX","Informe a descrição do OPEX."); return
        texto = self.opex_codigo.currentText(); codigo = texto.split(" - ")[0].strip() if " - " in texto else texto.strip()
        dados=(self.orcamento_id,self.opex_categoria.text(),'',self.opex_fonte.currentText(),codigo,desc,self.opex_unidade.text(),self.opex_qtd.value(),self.opex_custo.value(),self.opex_bdi.value(),self.opex_margem.value(),desc)
        with conn() as c:
            if self.selected_opex_id:
                c.execute("""UPDATE opex SET orcamento_id=?,categoria=?,centro_custo=?,fonte=?,codigo=?,descricao=?,unidade=?,qtd_mensal=?,custo_unit=?,bdi=?,margem=?,observacao=?WHERE id=?AND orcamento_id=?""", dados+(self.selected_opex_id, self.orcamento_id))
            else:
                c.execute("""INSERT INTO opex(orcamento_id,categoria,centro_custo,fonte,codigo,descricao,unidade,qtd_mensal,custo_unit,bdi,margem,observacao) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", dados)
            c.commit()
        self.limpar_opex(); self.carregar_opex(); self.atualizar_resumos()

    def carregar_opex(self):
        if not self.orcamento_id: return
        with conn() as c: dados = c.execute("SELECT * FROM opex WHERE orcamento_id=?ORDER BY id", (self.orcamento_id,)).fetchall()
        rows=[]
        for r in dados:
            custo_total=float(r['qtd_mensal'] or 0)*float(r['custo_unit'] or 0); total=self.total_item(r['qtd_mensal'],r['custo_unit'],r['bdi'],r['margem'])
            rows.append([r['id'],r['categoria'],r['fonte'],r['codigo'],r['descricao'],r['unidade'],r['qtd_mensal'],self.moeda(r['custo_unit']),self.moeda(custo_total),f"{float(r['bdi'] or 0):.2f}%",f"{float(r['margem'] or 0):.2f}%",self.moeda(total)])
        self._set_table(self.tabela_opex, rows)

    def selecionar_opex(self, row, col):
        item = self.tabela_opex.item(row,0); self.selected_opex_id = int(item.text()) if item else None
        if not self.selected_opex_id: return
        with conn() as c: r = c.execute("SELECT * FROM opex WHERE id=?", (self.selected_opex_id,)).fetchone()
        if not r: return
        idx=self.opex_fonte.findText(r['fonte'] or '')
        if idx>=0: self.opex_fonte.setCurrentIndex(idx)
        self.opex_codigo.setCurrentText(r['codigo'] or ''); self.opex_categoria.setText(r['categoria'] or ''); self.opex_descricao.setPlainText(r['descricao'] or ''); self.opex_unidade.setText(r['unidade'] or 'MÊS')
        self.opex_qtd.setValue(float(r['qtd_mensal'] or 0)); self.opex_custo.setValue(float(r['custo_unit'] or 0)); self.opex_bdi.setValue(float(r['bdi'] or 0)); self.opex_margem.setValue(float(self.margem.value() if r['margem'] is None else r['margem'])); self.btn_add_opex.setText("Atualizar OPEX")

    def limpar_opex(self):
        self.selected_opex_id = None
        self.opex_categoria.clear(); self.opex_descricao.clear(); self.opex_unidade.setText('MÊS'); self.opex_qtd.setValue(1); self.opex_custo.setValue(0); self.opex_bdi.setValue(self.bdi.value()); self.opex_margem.setValue(self.margem.value()); self.btn_add_opex.setText("Adicionar OPEX"); self.aplicar_modo_fonte_opex()

    def excluir_opex(self):
        if not self.selected_opex_id: return
        with conn() as c: c.execute("DELETE FROM opex WHERE id=?AND orcamento_id=?", (self.selected_opex_id, self.orcamento_id)); c.commit()
        self.selected_opex_id=None; self.carregar_opex(); self.atualizar_resumos()

    # ------------------------- ANEXOS LOGIC -------------------------
    def selecionar_arquivo_anexo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar documento/anexo",
            "",
            "Todos os arquivos (*.*);;PDF (*.pdf);;Imagens (*.png *.jpg *.jpeg);;Planilhas (*.xlsx *.xlsm *.xls);;Word (*.docx *.doc)"
        )
        if path:
            self.doc_caminho.setText(path)

    def _nome_anexo_unico(self, destino_dir, nome_arquivo):
        origem_nome = Path(nome_arquivo).name or "anexo"
        seguro = "".join(ch if ch.isalnum() or ch in " ._-()" else "_" for ch in origem_nome).strip() or "anexo"
        destino = destino_dir / seguro
        if not destino.exists():
            return destino

        stem = destino.stem
        suffix = destino.suffix
        contador = 2
        while True:
            candidato = destino_dir / f"{stem}_{contador}{suffix}"
            if not candidato.exists():
                return candidato
            contador += 1

    def adicionar_anexo(self):
        if not self.garantir_orcamento():
            return

        caminho = self.doc_caminho.text().strip()
        if not caminho:
            QMessageBox.warning(self, "Anexos", "Selecione um arquivo antes de adicionar.")
            return

        origem = Path(caminho)
        if not origem.exists() or not origem.is_file():
            QMessageBox.warning(self, "Anexos", f"Arquivo não encontrado:\n{origem}")
            return

        try:
            destino_dir = get_anexos_dir(self.orcamento_id)
            destino = self._nome_anexo_unico(destino_dir, origem.name)
            shutil.copy2(origem, destino)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Anexos",
                "Não foi possível copiar o anexo para a pasta do sistema/workspace compartilhado.\n\n"
                f"Arquivo: {origem}\nErro: {e}"
            )
            return

        nome_arquivo = destino.name
        caminho_registro = str(destino)

        with conn() as c:
            c.execute("""
                INSERT INTO documentos(orcamento_id, tipo, nome_arquivo, caminho, data_upload, usuario, observacao)
                VALUES(?,?,?,?,datetime('now'),?,?)
            """, (
                self.orcamento_id,
                self.doc_tipo.currentText(),
                nome_arquivo,
                caminho_registro,
                "Lucas Henrique",
                self.doc_obs.toPlainText(),
            ))
            c.commit()

        self.doc_caminho.clear()
        self.doc_obs.clear()
        self.carregar_anexos()
        QMessageBox.information(
            self,
            "Anexos",
            "Anexo copiado e vinculado ao orçamento com sucesso.\n\n"
            f"Destino:\n{caminho_registro}"
        )

    def carregar_anexos(self):
        if not hasattr(self, "tabela_anexos"):
            return

        if not self.orcamento_id:
            self.tabela_anexos.setRowCount(0)
            return

        with conn() as c:
            dados = c.execute("""
                SELECT id, tipo, nome_arquivo, caminho, data_upload, observacao
                FROM documentos
                WHERE orcamento_id=?
                ORDER BY id DESC
            """, (self.orcamento_id,)).fetchall()

        rows = []
        for r in dados:
            rows.append([
                r["id"],
                r["tipo"],
                r["nome_arquivo"],
                r["caminho"],
                r["data_upload"],
                r["observacao"],
            ])

        self._set_table(self.tabela_anexos, rows)

    def selecionar_anexo(self, row, col):
        item = self.tabela_anexos.item(row, 0)
        self.selected_documento_id = int(item.text()) if item else None

    def excluir_anexo(self):
        if not self.selected_documento_id:
            QMessageBox.warning(self, "Anexos", "Selecione um anexo para excluir.")
            return

        resp = QMessageBox.question(
            self,
            "Excluir anexo",
            "Deseja remover este anexo do orçamento?\n\nO arquivo original não será apagado, apenas o vínculo será removido.",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        with conn() as c:
            c.execute("DELETE FROM documentos WHERE id=?", (self.selected_documento_id,))
            c.commit()

        self.selected_documento_id = None
        self.selected_etapa_id = None
        self._ultima_margem_global = 18
        self.carregar_anexos()

    # ------------------------- CRONOGRAMA LOGIC -------------------------
    def obter_etapas_capex(self):
        if not self.orcamento_id: return []
        with conn() as c:
            return c.execute("""
                SELECT e.id, e.nome etapa, COALESCE(SUM(i.quantidade*i.custo_unit*(1+i.bdi/100.0)*(1+i.margem/100.0)),0) total
                FROM etapas_orcamento e LEFT JOIN itens i ON i.etapa_id=e.id AND i.orcamento_id=e.orcamento_id AND i.capex_opex='CAPEX'
                WHERE e.orcamento_id=?GROUP BY e.id ORDER BY e.ordem
            """, (self.orcamento_id,)).fetchall()

    def garantir_tabela_cronograma(self):
        # Hotfix defensivo: garante a tabela mesmo em bancos antigos.
        with conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS cronograma_parcelas(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    orcamento_id INTEGER NOT NULL,
                    etapa_id INTEGER,
                    parcela INTEGER NOT NULL,
                    percentual REAL DEFAULT 0,
                    valor REAL DEFAULT 0,
                    UNIQUE(orcamento_id, etapa_id, parcela)
                )
            """)
            c.commit()

    def _coluna_percentual_cronograma(self, col):
        return 2 <= col <= 24 and col % 2 == 0

    def _aplicar_edicao_cronograma(self):
        total_linhas_etapas = getattr(self, 'cronograma_total_etapas_count', 0)
        for row in range(self.tabela_cronograma.rowCount()):
            for col in range(self.tabela_cronograma.columnCount()):
                item = self.tabela_cronograma.item(row, col)
                if not item:
                    continue
                flags = item.flags() | Qt.ItemIsEnabled | Qt.ItemIsSelectable
                if row < total_linhas_etapas and self._coluna_percentual_cronograma(col):
                    item.setFlags(flags | Qt.ItemIsEditable)
                else:
                    item.setFlags(flags & ~Qt.ItemIsEditable)

    def gerar_cronograma_automatico(self):
        self.garantir_tabela_cronograma(); etapas = self.obter_etapas_capex(); self.cronograma_row_etapas = {}; self.cronograma_total_etapas_count = len(etapas)
        salvos = {}
        if self.orcamento_id:
            with conn() as c: dados = c.execute("SELECT etapa_id, parcela, percentual FROM cronograma_parcelas WHERE orcamento_id=?", (self.orcamento_id,)).fetchall()
            for item in dados: salvos[(item['etapa_id'], item['parcela'])] = float(item['percentual'] or 0)
        self.tabela_cronograma.setRowCount(len(etapas)+4); total_capex=0; total_distribuido=0; tudo_ok=True; total_mes=[0.0]*12
        for row,r in enumerate(etapas):
            etapa_id=r['id']; self.cronograma_row_etapas[row]=etapa_id; valor=float(r['total'] or 0); total_capex+=valor
            self.tabela_cronograma.setItem(row,0,QTableWidgetItem(r['etapa'])); self.tabela_cronograma.setItem(row,1,QTableWidgetItem(self.moeda(valor)))
            soma_pct=0; soma_valor=0
            for p in range(1,13):
                pct=salvos.get((etapa_id,p),0); valor_parcela=valor*pct/100; total_mes[p-1]+=valor_parcela; col_pct=2+(p-1)*2; col_valor=col_pct+1
                self.tabela_cronograma.setItem(row,col_pct,QTableWidgetItem('' if pct==0 else str(pct).replace('.',','))); self.tabela_cronograma.setItem(row,col_valor,QTableWidgetItem(self.moeda(valor_parcela)))
                soma_pct+=pct; soma_valor+=valor_parcela
            status='OK' if abs(soma_pct-100)<0.01 else ('ERRO' if soma_pct>100 else 'AJUSTAR'); tudo_ok = tudo_ok and status=='OK'
            self.tabela_cronograma.setItem(row,26,QTableWidgetItem(f"{soma_pct:.2f}%".replace('.',','))); self.tabela_cronograma.setItem(row,27,QTableWidgetItem(self.moeda(soma_valor))); self.tabela_cronograma.setItem(row,28,QTableWidgetItem(status)); total_distribuido+=soma_valor
        self.preencher_linhas_totais_cronograma(total_capex,total_mes)
        self._aplicar_edicao_cronograma()
        status_geral='OK' if tudo_ok and len(etapas)>0 else 'aguardando'
        self.resumo_cronograma.setText(f"Total CAPEX: {self.moeda(total_capex)} | Total distribuído: {self.moeda(total_distribuido)} | Status: {status_geral}")

    def preencher_linhas_totais_cronograma(self, total_capex, total_mes):
        base = getattr(self, 'cronograma_total_etapas_count', 0)
        labels = ['TOTAL DO MÊS (R$)', '% DO MÊS', 'ACUMULADO (R$)', '% ACUMULADO']
        acumulado = 0.0
        for i,label in enumerate(labels):
            row=base+i; self.tabela_cronograma.setItem(row,0,QTableWidgetItem(label)); self.tabela_cronograma.setItem(row,1,QTableWidgetItem(''))
        for p in range(1,13):
            val_mes=float(total_mes[p-1] or 0); pct_mes=(val_mes/total_capex*100) if total_capex else 0; acumulado += val_mes; pct_acum=(acumulado/total_capex*100) if total_capex else 0; col_pct=2+(p-1)*2; col_val=col_pct+1
            self.tabela_cronograma.setItem(base+0,col_pct,QTableWidgetItem('')); self.tabela_cronograma.setItem(base+0,col_val,QTableWidgetItem(self.moeda(val_mes)))
            self.tabela_cronograma.setItem(base+1,col_pct,QTableWidgetItem(f"{pct_mes:.2f}%".replace('.',','))); self.tabela_cronograma.setItem(base+1,col_val,QTableWidgetItem(''))
            self.tabela_cronograma.setItem(base+2,col_pct,QTableWidgetItem('')); self.tabela_cronograma.setItem(base+2,col_val,QTableWidgetItem(self.moeda(acumulado)))
            self.tabela_cronograma.setItem(base+3,col_pct,QTableWidgetItem(f"{pct_acum:.2f}%".replace('.',','))); self.tabela_cronograma.setItem(base+3,col_val,QTableWidgetItem(''))
        for r in range(base, base+4):
            for c in range(self.tabela_cronograma.columnCount()):
                item=self.tabela_cronograma.item(r,c)
                if item: item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.tabela_cronograma.setItem(r,28,QTableWidgetItem('AUTO'))
        self._aplicar_edicao_cronograma()

    def aplicar_parcela_unica(self):
        total_linhas_etapas = getattr(self, 'cronograma_total_etapas_count', self.tabela_cronograma.rowCount())
        for row in range(total_linhas_etapas):
            self.tabela_cronograma.setItem(row,2,QTableWidgetItem('100'))
            for p in range(2,13): self.tabela_cronograma.setItem(row,2+(p-1)*2,QTableWidgetItem('0'))
        self.validar_cronograma()

    def _pct(self, text):
        try: return float(str(text).replace('%','').replace(',','.').strip() or 0)
        except Exception: return 0

    def _money(self, text):
        try: return float(str(text).replace('R$','').replace('.','').replace(',','.').strip() or 0)
        except Exception: return 0

    def validar_cronograma(self):
        if not self.orcamento_id:
            QMessageBox.warning(self, "Cronograma", "Salve o orçamento antes de salvar o cronograma."); return
        self.garantir_tabela_cronograma(); total_capex=0; total_dist=0; ok=True; linhas_para_salvar=[]; total_mes=[0.0]*12; total_linhas_etapas=getattr(self,'cronograma_total_etapas_count',self.tabela_cronograma.rowCount())
        for row in range(total_linhas_etapas):
            etapa_id=getattr(self,'cronograma_row_etapas',{}).get(row); valor=self._money(self.tabela_cronograma.item(row,1).text() if self.tabela_cronograma.item(row,1) else '0'); total_capex+=valor; soma_pct=0; soma_valor=0
            for p in range(1,13):
                col=2+(p-1)*2; pct=self._pct(self.tabela_cronograma.item(row,col).text() if self.tabela_cronograma.item(row,col) else '0'); val=valor*pct/100; total_mes[p-1]+=val; soma_pct+=pct; soma_valor+=val; self.tabela_cronograma.setItem(row,col+1,QTableWidgetItem(self.moeda(val)))
                if pct > 0 or val > 0:
                    linhas_para_salvar.append((self.orcamento_id, etapa_id, p, pct, val))
            status='OK' if abs(soma_pct-100)<0.01 else ('ERRO' if soma_pct>100 else 'AJUSTAR'); ok=ok and status=='OK'; self.tabela_cronograma.setItem(row,26,QTableWidgetItem(f"{soma_pct:.2f}%".replace('.',','))); self.tabela_cronograma.setItem(row,27,QTableWidgetItem(self.moeda(soma_valor))); self.tabela_cronograma.setItem(row,28,QTableWidgetItem(status)); total_dist+=soma_valor
        with conn() as c:
            c.execute("DELETE FROM cronograma_parcelas WHERE orcamento_id=?", (self.orcamento_id,)); c.executemany("""INSERT INTO cronograma_parcelas(orcamento_id, etapa_id, parcela, percentual, valor) VALUES(?,?,?,?,?)""", linhas_para_salvar); c.commit()
        self.preencher_linhas_totais_cronograma(total_capex,total_mes); self.resumo_cronograma.setText(f"Total CAPEX: {self.moeda(total_capex)} | Total distribuído: {self.moeda(total_dist)} | Status: {'OK' if ok else 'AJUSTAR/ERRO'}"); QMessageBox.information(self,"Cronograma",f"Cronograma validado e salvo. Status: {'OK' if ok else 'AJUSTAR/ERRO'}")

    def atualizar_resumos(self):
        if not self.orcamento_id:
            capex=opex=0; itens=0
        else:
            with conn() as c:
                capex=c.execute("SELECT COALESCE(SUM(quantidade*custo_unit*(1+bdi/100.0)*(1+margem/100.0)),0) t FROM itens WHERE orcamento_id=?AND capex_opex='CAPEX'",(self.orcamento_id,)).fetchone()['t']
                opex=c.execute("SELECT COALESCE(SUM(qtd_mensal*custo_unit*(1+COALESCE(bdi,0)/100.0)*(1+COALESCE(margem,0)/100.0)),0) t FROM opex WHERE orcamento_id=?",(self.orcamento_id,)).fetchone()['t']
                itens=c.execute("SELECT COUNT(*) c FROM itens WHERE orcamento_id=?AND capex_opex='CAPEX'",(self.orcamento_id,)).fetchone()['c']
        self.card_capex.setText(f"Total CAPEX\n{self.moeda(capex)}")
        self.card_opex.setText(f"Total OPEX Mensal\n{self.moeda(opex)}")
        self.card_margem.setText(f"Margem Média\n{self.margem.value():.2f}%".replace('.',','))
        self.card_itens.setText(f"Orçamento ativo\n{itens} itens")

    def gerar_revisao(self):
        if not self.orcamento_id:
            QMessageBox.warning(self, "Geração", "Salve o orçamento antes.")
            return
        arquivos = gerar_pacote_revisao(self.orcamento_id)
        QMessageBox.information(
            self,
            "Pacote gerencial",
            "Arquivos gerados:\n" + "\n".join(str(a) for a in arquivos)
        )

    def gerar_final(self):
        self.gerar_pdf()

    def gerar_pdf(self):
        if not self.orcamento_id:
            QMessageBox.warning(self, "PDF", "Salve ou abra um orçamento.")
            return

        arquivos = gerar_pacote_final(self.orcamento_id, formatos=["pdf"])
        QMessageBox.information(
            self,
            "PDF",
            "Arquivos gerados:\n\n" + "\n".join(str(a) for a in arquivos)
        )

    def gerar_word(self):
        if not self.orcamento_id:
            QMessageBox.warning(self, "WORD", "Salve ou abra um orçamento.")
            return

        arquivos = gerar_pacote_final(self.orcamento_id, formatos=["docx"])
        QMessageBox.information(
            self,
            "WORD",
            "Arquivos gerados:\n\n" + "\n".join(str(a) for a in arquivos)
        )

    def gerar_excel(self):
        if not self.orcamento_id:
            QMessageBox.warning(self, "EXCEL", "Salve ou abra um orçamento.")
            return

        arquivos = gerar_pacote_final(self.orcamento_id, formatos=["xlsx"])
        QMessageBox.information(
            self,
            "EXCEL",
            "Arquivos gerados:\n\n" + "\n".join(str(a) for a in arquivos)
        )

    def gerar_orcamento_simples(self):
        if not self.orcamento_id:
            QMessageBox.warning(self, "ORÇAMENTO SIMPLES", "Salve ou abra um orçamento.")
            return
        try:
            arquivos = gerar_pacote_orcamento_simples(self.orcamento_id)
            QMessageBox.information(
                self,
                "ORÇAMENTO SIMPLES",
                "Arquivos gerados:\n\n" + "\n".join(str(a) for a in arquivos)
            )
        except Exception as e:
            QMessageBox.critical(self, "ORÇAMENTO SIMPLES", f"Erro ao gerar orçamento simples:\n{e}")

    def gerar_pacote_completo(self):
        if not self.orcamento_id:
            QMessageBox.warning(self, "PACOTE", "Salve ou abra um orçamento.")
            return

        arquivos = gerar_pacote_final(
            self.orcamento_id,
            formatos=["pdf", "docx", "xlsx", "html"]
        )
        QMessageBox.information(
            self,
            "PACOTE COMPLETO",
            "Arquivos gerados:\n\n" + "\n".join(str(a) for a in arquivos)
        )

    # Compatibilidade com botões/atalhos antigos.
    def gerar_pacote_word(self):
        self.gerar_word()

    def gerar_pacote_excel(self):
        self.gerar_excel()

    def gerar_pacote_office(self):
        self.gerar_pacote_completo()

    def gerar_html(self):
        # Pacote 10.2: gera o Dashboard Executivo pelo orçamento ativo ou pelo combo selecionado.
        oid = self.orcamento_id
        try:
            combo_id = self.cbo_orcamentos.currentData()
            if combo_id:
                oid = int(combo_id)
        except Exception:
            pass
        if not oid:
            QMessageBox.warning(self, "Geração", "Salve ou abra um orçamento antes de gerar o dashboard.")
            return
        self.orcamento_id = oid
        try:
            arquivo = gerar_dashboard_html(oid, interno=True)
            try:
                caminho = Path(str(arquivo)).resolve()
                webbrowser.open(caminho.as_uri())
            except Exception:
                pass
            QMessageBox.information(self, "Dashboard Executivo", f"Dashboard gerado com sucesso:\n{arquivo}")
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Dashboard Executivo", f"Não foi possível gerar o dashboard:\n{e}")
