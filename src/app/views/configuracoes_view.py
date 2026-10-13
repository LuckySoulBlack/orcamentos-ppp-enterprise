from pathlib import Path
import os
import webbrowser

from PySide6.QtWidgets import *

import core.database as database
from services.backup_service import gerar_backup_banco, importar_backup_banco, abrir_pasta_backups


def _parece_url(valor):
    texto = str(valor or "").strip().lower()
    return texto.startswith(("http://", "https://"))


class ConfiguracoesView(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("ConfiguracoesView")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        titulo = QLabel("Configurações")
        titulo.setStyleSheet("font-size:26px;font-weight:950;color:#071A33;")
        layout.addWidget(titulo)

        subtitulo = QLabel(
            "Configure dados do rodapé, geração de arquivos e a pasta compartilhada para banco de dados e anexos."
        )
        subtitulo.setWordWrap(True)
        subtitulo.setStyleSheet("color:#64748B;font-weight:700;")
        layout.addWidget(subtitulo)

        box = QGroupBox("Configurações gerais do sistema")
        form = QFormLayout(box)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(14)

        self.nome_usuario = QLineEdit()
        self.cnpj_usuario = QLineEdit()
        self.pasta_local = QLineEdit()
        self.pasta_local.setPlaceholderText("Opcional. Se vazio, usa o workspace compartilhado > gerados.")

        linha_pasta = QHBoxLayout()
        linha_pasta.addWidget(self.pasta_local, 1)
        btn_pasta = QPushButton("Selecionar")
        btn_pasta.clicked.connect(self.selecionar_pasta_relatorios)
        linha_pasta.addWidget(btn_pasta)

        form.addRow("Nome no rodapé", self.nome_usuario)
        form.addRow("CNPJ no rodapé", self.cnpj_usuario)
        form.addRow("Pasta local relatórios", linha_pasta)
        layout.addWidget(box)

        workspace_box = QGroupBox("Banco de dados e anexos compartilhados")
        workspace_layout = QVBoxLayout(workspace_box)
        workspace_layout.setSpacing(10)

        info = QLabel(
            "Cole o link da pasta do Google Drive e selecione a pasta sincronizada no computador. "
            "O sistema cria a estrutura app.db, anexos, gerados e backups nesse local. "
            "Assim, ao trocar de computador ou atualizar o EXE, os dados e anexos não ficam presos na máquina antiga."
        )
        info.setWordWrap(True)
        info.setStyleSheet(
            "background:#F8FAFC;border:1px solid #DBE4EF;border-radius:10px;"
            "padding:10px;color:#334155;font-weight:700;"
        )
        workspace_layout.addWidget(info)

        form_workspace = QFormLayout()
        form_workspace.setVerticalSpacing(10)
        form_workspace.setHorizontalSpacing(14)

        self.drive = QLineEdit()
        self.drive.setPlaceholderText("Cole aqui o link da pasta do Google Drive compartilhado")
        self.portal_executor = QLineEdit()
        self.portal_executor.setPlaceholderText("Ex.: https://seu-portal-de-os.com")

        self.workspace = QLineEdit()
        self.workspace.setPlaceholderText("Ex.: G:\\Meu Drive\\Orcamentos_PPP_Enterprise ou pasta de rede compartilhada")

        linha_drive = QHBoxLayout()
        linha_drive.addWidget(self.drive, 1)
        btn_abrir_drive = QPushButton("Abrir link")
        btn_abrir_drive.clicked.connect(self.abrir_link_drive)
        linha_drive.addWidget(btn_abrir_drive)

        linha_workspace = QHBoxLayout()
        linha_workspace.addWidget(self.workspace, 1)
        btn_workspace = QPushButton("Selecionar pasta")
        btn_workspace.clicked.connect(self.selecionar_workspace)
        linha_workspace.addWidget(btn_workspace)
        btn_abrir_workspace = QPushButton("Abrir pasta")
        btn_abrir_workspace.clicked.connect(self.abrir_workspace)
        linha_workspace.addWidget(btn_abrir_workspace)

        form_workspace.addRow("Link Google Drive", linha_drive)
        form_workspace.addRow("URL Portal Executor", self.portal_executor)
        form_workspace.addRow("Pasta Drive sincronizada", linha_workspace)
        workspace_layout.addLayout(form_workspace)

        status = QLabel()
        status.setWordWrap(True)
        status.setObjectName("WorkspaceStatus")
        status.setStyleSheet("color:#0B3B75;font-weight:850;")
        self.status_workspace = status
        workspace_layout.addWidget(status)

        botoes_workspace = QHBoxLayout()
        self.btn_ativar_workspace = QPushButton("Criar / ativar banco compartilhado")
        self.btn_ativar_workspace.setMinimumHeight(42)
        self.btn_ativar_workspace.clicked.connect(self.ativar_workspace)
        botoes_workspace.addWidget(self.btn_ativar_workspace)

        self.btn_salvar = QPushButton("Salvar configurações")
        self.btn_salvar.setMinimumHeight(42)
        self.btn_salvar.clicked.connect(self.salvar)
        botoes_workspace.addWidget(self.btn_salvar)
        workspace_layout.addLayout(botoes_workspace)

        layout.addWidget(workspace_box)

        backup_box = QGroupBox("Backup manual do banco de dados")
        backup_layout = QVBoxLayout(backup_box)

        info_backup = QLabel(
            "Use backup manual para congelar uma versão do banco antes de mudanças importantes. "
            "Com workspace compartilhado ativo, o backup será feito a partir do banco em uso."
        )
        info_backup.setWordWrap(True)
        info_backup.setStyleSheet("color:#64748B;font-weight:700;")
        backup_layout.addWidget(info_backup)

        linha_backup = QHBoxLayout()
        self.btn_gerar_backup = QPushButton("Gerar backup do banco")
        self.btn_importar_backup = QPushButton("Importar backup baixado")
        self.btn_abrir_backups = QPushButton("Abrir pasta de backups")
        self.btn_gerar_backup.clicked.connect(self.gerar_backup)
        self.btn_importar_backup.clicked.connect(self.importar_backup)
        self.btn_abrir_backups.clicked.connect(self.abrir_pasta_backup)
        for b in [self.btn_gerar_backup, self.btn_importar_backup, self.btn_abrir_backups]:
            b.setMinimumHeight(38)
            linha_backup.addWidget(b)
        backup_layout.addLayout(linha_backup)
        layout.addWidget(backup_box)

        layout.addStretch()
        self.load_data()

    def selecionar_pasta_relatorios(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta local para relatórios")
        if pasta:
            self.pasta_local.setText(pasta)

    def selecionar_workspace(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta sincronizada do Google Drive ou rede")
        if pasta:
            self.workspace.setText(pasta)

    def abrir_link_drive(self):
        link = self.drive.text().strip()
        if not link:
            QMessageBox.warning(self, "Google Drive", "Cole o link da pasta do Google Drive antes de abrir.")
            return
        webbrowser.open(link)

    def abrir_workspace(self):
        pasta = self.workspace.text().strip()
        if not pasta:
            QMessageBox.warning(self, "Pasta compartilhada", "Informe ou selecione a pasta compartilhada.")
            return
        if _parece_url(pasta):
            if not self.drive.text().strip():
                self.drive.setText(pasta)
            QMessageBox.warning(
                self,
                "Pasta compartilhada",
                "Este campo precisa receber uma pasta local sincronizada, não o link do Drive.\n\n"
                "Cole o link no campo Link Google Drive e clique em Selecionar pasta para apontar "
                "para a pasta do Google Drive para computador ou uma pasta de rede."
            )
            return
        try:
            Path(pasta).mkdir(parents=True, exist_ok=True)
            os.startfile(str(Path(pasta)))
        except Exception:
            webbrowser.open(str(Path(pasta)))

    def _validar_workspace_informado(self):
        pasta = self.workspace.text().strip().strip('"')
        if not pasta:
            QMessageBox.warning(
                self,
                "Banco compartilhado",
                "Selecione a pasta sincronizada do Google Drive ou uma pasta de rede.\n\n"
                "O link do Drive sozinho não ? um caminho de gravação para o Windows."
            )
            return None

        if _parece_url(pasta):
            if not self.drive.text().strip():
                self.drive.setText(pasta)
            self.workspace.clear()
            QMessageBox.warning(
                self,
                "Banco compartilhado",
                "Você colou o link do Google Drive no campo Pasta Drive sincronizada.\n\n"
                "O link deve ficar no campo Link Google Drive. No campo Pasta Drive sincronizada, "
                "selecione a pasta local criada pelo Google Drive para computador, por exemplo:\n"
                "G:\\Meu Drive\\Orcamentos_PPP_Enterprise"
            )
            return None

        caminho = Path(pasta).expanduser()
        if caminho.suffix.lower() == ".db":
            QMessageBox.warning(
                self,
                "Banco compartilhado",
                "Selecione a pasta compartilhada/sincronizada, não o arquivo app.db."
            )
            return None
        return str(caminho)

    def _salvar_campos_basicos(self):
        workspace_atual = self.workspace.text().strip()
        if _parece_url(workspace_atual):
            if not self.drive.text().strip():
                self.drive.setText(workspace_atual)
            self.workspace.clear()
            workspace_atual = ""
            QMessageBox.warning(
                self,
                "Pasta compartilhada",
                "O link do Drive foi movido para o campo Link Google Drive.\n\n"
                "Para ativar o banco compartilhado, selecione também a pasta local sincronizada."
            )

        dados = {
            "nome_usuario": self.nome_usuario.text().strip(),
            "cnpj_usuario": self.cnpj_usuario.text().strip(),
            "google_drive": self.drive.text().strip(),
            "google_drive_link": self.drive.text().strip(),
            "portal_executor_url": self.portal_executor.text().strip(),
            "shared_workspace": workspace_atual,
            "pasta_local": self.pasta_local.text().strip(),
        }

        pasta_relatorios = dados.get("pasta_local", "")
        if pasta_relatorios:
            try:
                Path(pasta_relatorios).mkdir(parents=True, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Pasta local",
                    f"Não foi possível criar/acessar a pasta informada:\n{pasta_relatorios}\n\nErro: {e}",
                )
                return False

        for chave, valor in dados.items():
            database.set_config(chave, valor)
        database.update_runtime_config(google_drive_link=dados["google_drive_link"])
        return True

    def salvar(self):
        if not self._salvar_campos_basicos():
            return
        QMessageBox.information(
            self,
            "Configurações",
            "Configurações salvas com sucesso."
        )
        self.load_data()

    def ativar_workspace(self):
        pasta = self._validar_workspace_informado()
        link = self.drive.text().strip()

        if not pasta:
            return

        resp = QMessageBox.question(
            self,
            "Ativar banco compartilhado",
            "O sistema vai criar/ativar a pasta compartilhada e usar app.db, anexos, gerados e backups nesse local.\n\n"
            "Se ainda não existir app.db nessa pasta, o banco atual será copiado para lá.\n\n"
            "Deseja continuar?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return

        try:
            pasta_final, banco = database.set_shared_workspace(
                pasta,
                drive_link=link,
                copiar_banco_atual=True,
            )
            database.init_db()

            # Persiste também dentro do banco recém-ativado.
            database.set_config("google_drive", link)
            database.set_config("google_drive_link", link)
            database.set_config("portal_executor_url", self.portal_executor.text().strip())
            database.set_config("shared_workspace", str(pasta_final))
            database.set_config("pasta_local", self.pasta_local.text().strip())
            database.set_config("nome_usuario", self.nome_usuario.text().strip())
            database.set_config("cnpj_usuario", self.cnpj_usuario.text().strip())

            QMessageBox.information(
                self,
                "Banco compartilhado ativo",
                "Workspace ativado com sucesso.\n\n"
                f"Pasta: {pasta_final}\n"
                f"Banco: {banco}\n\n"
                "Reinicie o sistema nos outros computadores e selecione a mesma pasta para todos usarem a mesma base."
            )
            self.load_data()
        except Exception as e:
            QMessageBox.critical(self, "Banco compartilhado", f"Erro ao ativar workspace:\n{e}")

    def gerar_backup(self):
        pasta = QFileDialog.getExistingDirectory(self, "Selecionar pasta para salvar o backup")
        if not pasta:
            return
        try:
            arquivo = gerar_backup_banco(
                destino_pasta=pasta,
                usuario=self.nome_usuario.text(),
                observacao="Backup manual gerado pela tela de Configurações"
            )
            QMessageBox.information(self, "Backup", f"Backup gerado com sucesso:\n{arquivo}")
        except Exception as e:
            QMessageBox.critical(self, "Backup", f"Erro ao gerar backup:\n{e}")

    def importar_backup(self):
        arquivo, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar backup do banco",
            "",
            "Backup ZIP (*.zip)"
        )
        if not arquivo:
            return

        resp = QMessageBox.question(
            self,
            "Importar backup",
            "A importação substituirá o banco atual pelo banco do backup selecionado.\n\n"
            "Antes de substituir, o sistema fará uma cópia de segurança do banco atual.\n\n"
            "Deseja continuar?",
            QMessageBox.Yes | QMessageBox.No
        )
        if resp != QMessageBox.Yes:
            return

        try:
            destino, copia = importar_backup_banco(arquivo)
            msg = f"Backup importado com sucesso:\n{destino}"
            if copia:
                msg += f"\n\nCópia do banco anterior:\n{copia}"
            QMessageBox.information(self, "Importar backup", msg)
        except Exception as e:
            QMessageBox.critical(self, "Importar backup", f"Erro ao importar backup:\n{e}")

    def abrir_pasta_backup(self):
        pasta = abrir_pasta_backups()
        try:
            os.startfile(str(pasta))
        except Exception:
            webbrowser.open(str(pasta))

    def load_data(self):
        try:
            with database.conn() as c:
                dados = c.execute("SELECT chave, valor FROM config").fetchall()
            mapa = {item["chave"]: item["valor"] or "" for item in dados}
        except Exception:
            mapa = {}

        runtime = database.get_runtime_config()
        self.nome_usuario.setText(mapa.get("nome_usuario", "Lucas Henrique"))
        self.cnpj_usuario.setText(mapa.get("cnpj_usuario", ""))
        self.drive.setText(
            mapa.get("google_drive_link")
            or mapa.get("google_drive")
            or runtime.get("google_drive_link", "")
        )
        self.workspace.setText(
            mapa.get("shared_workspace")
            or runtime.get("shared_workspace", "")
        )
        self.portal_executor.setText(mapa.get("portal_executor_url", ""))
        self.pasta_local.setText(mapa.get("pasta_local", ""))

        workspace_label = self.workspace.text().strip() or "Não configurado"
        banco_atual = str(database.DB_PATH)
        self.status_workspace.setText(
            f"Banco em uso: {banco_atual}\n"
            f"Workspace configurado: {workspace_label}"
        )

