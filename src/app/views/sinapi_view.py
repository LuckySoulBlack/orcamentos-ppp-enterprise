
from PySide6.QtWidgets import *

from core.database import conn
from services.sinapi_importer import importar_sinapi_excel, UFS
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar


class SinapiView(QWidget):

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)

        titulo = QLabel("Base SINAPI")
        titulo.setStyleSheet("font-size:24px;font-weight:bold;")
        layout.addWidget(titulo)

        filtros = QHBoxLayout()

        self.busca = QLineEdit()
        self.busca.setPlaceholderText("Código ou descrição")

        self.uf = QComboBox()
        self.uf.addItems(["TODAS"] + UFS)
        self.uf.setCurrentText("SP")

        self.tipo = QComboBox()
        self.tipo.addItems(["TODOS", "INSUMO", "COMPOSICAO"])

        self.chk_limpar = QCheckBox("Limpar base antes de importar")
        self.chk_limpar.setChecked(False)

        self.chk_insumos = QCheckBox("Insumos")
        self.chk_insumos.setChecked(True)

        self.chk_composicoes = QCheckBox("Composições")
        self.chk_composicoes.setChecked(True)

        btn_filtrar = QPushButton("Filtrar")
        btn_filtrar.clicked.connect(self.load_data)

        btn_importar = QPushButton("Importar Excel SINAPI")
        btn_importar.clicked.connect(self.importar_excel)

        filtros.addWidget(self.busca)
        filtros.addWidget(QLabel("UF"))
        filtros.addWidget(self.uf)
        filtros.addWidget(QLabel("Tipo"))
        filtros.addWidget(self.tipo)
        filtros.addWidget(btn_filtrar)
        filtros.addWidget(btn_importar)

        layout.addLayout(filtros)

        opcoes = QHBoxLayout()
        opcoes.addWidget(self.chk_limpar)
        opcoes.addWidget(self.chk_insumos)
        opcoes.addWidget(self.chk_composicoes)
        opcoes.addStretch()
        layout.addLayout(opcoes)

        aviso = QLabel(
            "Importação PPP Smart: por padrão importa apenas a UF selecionada para evitar travamento. "
            "Use TODAS somente se quiser carregar todos os estados."
        )
        aviso.setStyleSheet("color:#64748B;")
        layout.addWidget(aviso)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "ID",
            "Código",
            "Descrição",
            "UN",
            "Custo",
            "UF",
            "Competência",
            "Tipo",
            "Classificação",
            "Fonte"
        ])

        configurar_tabela_responsiva(self.table, stretch_columns=[2], hidden_columns=[0])
        layout.addWidget(self.table)

        self.load_data()

    def importar_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Importar planilha SINAPI",
            "",
            "Planilhas Excel (*.xlsx *.xlsm *.xls)"
        )

        if not path:
            return

        uf = self.uf.currentText()

        if uf == "TODAS":
            resp = QMessageBox.question(
                self,
                "Importar todas as UFs",
                "Importar TODAS as UFs pode demorar e deixar a base grande.\n\nDeseja continuar?",
                QMessageBox.Yes | QMessageBox.No
            )
            if resp != QMessageBox.Yes:
                return

        try:
            total, diagnostico = importar_sinapi_excel(
                path,
                uf_alvo=uf,
                limpar_base=self.chk_limpar.isChecked(),
                incluir_insumos=self.chk_insumos.isChecked(),
                incluir_composicoes=self.chk_composicoes.isChecked()
            )

            msg = f"Importação concluída com sucesso.\n\nRegistros importados: {total}\n\n"
            msg += "\n".join(diagnostico[:12])

            QMessageBox.information(self, "SINAPI", msg)

            self.load_data()

        except Exception as e:
            QMessageBox.critical(
                self,
                "Erro ao importar SINAPI",
                str(e)
            )

    def load_data(self):
        termo = self.busca.text().strip()

        sql = """
            SELECT
                id,
                codigo,
                descricao,
                unidade,
                custo,
                uf,
                competencia,
                tipo,
                classificacao,
                fonte
            FROM sinapi
            WHERE (codigo LIKE ?OR descricao LIKE ?)
        """

        params = [
            f"%{termo}%",
            f"%{termo}%"
        ]

        if self.uf.currentText() != "TODAS":
            sql += " AND uf=?"
            params.append(self.uf.currentText())

        if self.tipo.currentText() != "TODOS":
            sql += " AND tipo=?"
            params.append(self.tipo.currentText())

        sql += " ORDER BY tipo, codigo, uf LIMIT 3000"

        with conn() as c:
            dados = c.execute(sql, tuple(params)).fetchall()

        self.table.setRowCount(len(dados))

        for row, item in enumerate(dados):
            valores = [
                item["id"],
                item["codigo"],
                item["descricao"],
                item["unidade"],
                self.moeda(item["custo"]),
                item["uf"],
                item["competencia"],
                item["tipo"],
                item["classificacao"],
                item["fonte"],
            ]

            for col, valor in enumerate(valores):
                self.table.setItem(
                    row,
                    col,
                    QTableWidgetItem(str(valor or ""))
                )

        ajustar_tabela_apos_carregar(self.table)

    def moeda(self, valor):
        try:
            valor = float(valor or 0)
        except Exception:
            valor = 0

        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
