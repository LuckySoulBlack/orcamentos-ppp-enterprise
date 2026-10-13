from pathlib import Path

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QLineEdit,
    QPushButton, QCheckBox, QSizePolicy, QGraphicsDropShadowEffect
)

from core import session
from core.theme import APP_VERSION
from core.ui_helpers import mensagem_operacional
from services.auth_service import autenticar
from widgets.lottie_widget import LottieWidget


def _asset(nome):
    return Path(__file__).resolve().parents[1] / "assets" / nome


def _shadow(widget, blur=34, y=12, alpha=36):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(QColor(15, 23, 42, alpha))
    widget.setGraphicsEffect(effect)


class LoginView(QWidget):
    def __init__(self, on_login):
        super().__init__()
        self.on_login = on_login
        self.settings = QSettings("OrcamentosPPP", "OrcamentosPPP")
        self.setWindowTitle("Orçamentos PPP")
        self.resize(1120, 660)
        self.setMinimumSize(900, 560)
        self.setStyleSheet("background:#EEF3FA;")

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)

        shell = QFrame()
        shell.setObjectName("LoginShell")
        shell.setStyleSheet("""
            QFrame#LoginShell {
                background:white;
                border:1px solid #DCE6F2;
                border-radius:22px;
            }
        """)
        _shadow(shell)
        root.addWidget(shell, 1)

        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._hero_panel(), 5)
        layout.addWidget(self._form_panel(), 5)
        self._carregar_lembrado()

    def _logo(self, max_w=96, max_h=88):
        logo = QLabel()
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background:transparent;border:none;")
        logo_path = _asset("logo_symbol.png")
        if logo_path.exists():
            pix = QPixmap(str(logo_path))
            logo.setPixmap(pix.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            logo.setText("Orçamentos PPP")
            logo.setStyleSheet("font-size:24px;font-weight:900;color:#071A33;")
        return logo

    def _brand(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        name = QLabel("Orçamentos PPP")
        name.setStyleSheet("background:transparent;color:white;font-size:28px;font-weight:900;letter-spacing:0px;")
        version = QLabel("Gestão de orçamentos")
        version.setStyleSheet("background:transparent;color:white;font-size:13px;font-weight:900;letter-spacing:1px;")
        texts.addWidget(name)
        texts.addWidget(version)
        row.addLayout(texts)
        row.addStretch(1)
        return row

    def _hero_panel(self):
        hero = QFrame()
        hero.setMinimumWidth(420)
        hero.setObjectName("HeroPanel")
        hero.setStyleSheet("""
            QFrame#HeroPanel {
                background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #071A33, stop:1 #123E70);
                border-top-left-radius:22px;
                border-bottom-left-radius:22px;
            }
        """)
        lay = QVBoxLayout(hero)
        lay.setContentsMargins(48, 38, 48, 38)
        lay.setSpacing(12)

        lay.addLayout(self._brand())

        lottie = LottieWidget(_asset("lottie/business_plan.json"), framed=False)
        lottie.setFixedHeight(315)
        lay.addStretch(1)
        lay.addWidget(lottie, 0)

        title = QLabel("Gestão executiva de orçamentos PPP")
        title.setWordWrap(True)
        title.setStyleSheet("background:transparent;border:none;color:white;font-size:21px;font-weight:900;letter-spacing:0px;")
        sub = QLabel("Controle orçamentos, contratos, aditivos e documentos oficiais com rastreabilidade.")
        sub.setWordWrap(True)
        sub.setStyleSheet("background:transparent;border:none;color:#DCEBFF;font-size:12px;font-weight:650;line-height:1.25;")
        lay.addWidget(title)
        lay.addWidget(sub)

        tags = QHBoxLayout()
        tags.setSpacing(8)
        for texto in ["Contratos PPP", "CAPEX / OPEX", "PDF - Word - Excel"]:
            tag = QLabel(texto)
            tag.setAlignment(Qt.AlignCenter)
            tag.setStyleSheet("""
                background:rgba(255,255,255,0.10);
                color:#EAF2FF;
                border:1px solid rgba(255,255,255,0.18);
                border-radius:12px;
                padding:7px 10px;
                font-size:11px;
                font-weight:800;
            """)
            tags.addWidget(tag)
        lay.addLayout(tags)

        version = QLabel(f"Versão {APP_VERSION}")
        version.setStyleSheet("background:transparent;color:#BFD7FF;font-size:11px;font-weight:700;")
        lay.addWidget(version)
        return hero

    def _field_label(self, texto):
        label = QLabel(texto)
        label.setStyleSheet("color:#334155;font-weight:800;font-size:12px;")
        return label

    def _form_panel(self):
        panel = QFrame()
        panel.setStyleSheet("background:white;border-top-right-radius:22px;border-bottom-right-radius:22px;")
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        root = QVBoxLayout(panel)
        root.setContentsMargins(64, 54, 64, 42)

        card = QFrame()
        card.setFixedWidth(430)
        card.setStyleSheet("background:white;")
        form = QVBoxLayout(card)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(11)

        logo = self._logo(84, 76)
        title = QLabel("Entrar no sistema")
        title.setAlignment(Qt.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet("color:#071A33;font-size:24px;font-weight:900;")
        desc = QLabel("Use sua conta autorizada para acessar o sistema.")
        desc.setAlignment(Qt.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color:#64748B;font-size:12px;font-weight:650;")

        self.user = QLineEdit()
        self.user.setPlaceholderText("E-mail ou usuário")
        self.user.setMinimumHeight(46)
        self.password = QLineEdit()
        self.password.setPlaceholderText("Senha")
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setMinimumHeight(46)
        self.password.returnPressed.connect(self._login)

        self.btn_ver_senha = QPushButton("Ver")
        self.btn_ver_senha.setFixedWidth(64)
        self.btn_ver_senha.setMinimumHeight(46)
        self.btn_ver_senha.setToolTip("Mostrar ou ocultar senha")
        self.btn_ver_senha.clicked.connect(self._alternar_senha)
        senha_linha = QHBoxLayout()
        senha_linha.setContentsMargins(0, 0, 0, 0)
        senha_linha.setSpacing(8)
        senha_linha.addWidget(self.password, 1)
        senha_linha.addWidget(self.btn_ver_senha)

        self.remember = QCheckBox("Lembrar-me neste computador")
        self.remember.setStyleSheet("color:#334155;font-weight:650;font-size:12px;")

        self.btn_entrar = QPushButton("Entrar")
        self.btn_entrar.setMinimumHeight(48)
        self.btn_entrar.clicked.connect(self._login)

        for widget in [logo, title, desc]:
            form.addWidget(widget)
        form.addSpacing(10)
        for widget in [self._field_label("Usuário ou e-mail"), self.user, self._field_label("Senha")]:
            form.addWidget(widget)
        form.addLayout(senha_linha)
        form.addWidget(self.remember)
        form.addSpacing(8)
        form.addWidget(self.btn_entrar)

        card.setStyleSheet("""
            QLineEdit {
                background:#F8FAFC;
                border:1px solid #D7E2EF;
                border-radius:11px;
                padding:0 13px;
                font-size:13px;
            }
            QLineEdit:focus { border:1px solid #0B3B75; background:white; }
            QPushButton {
                background:#0B3B75;
                color:white;
                border:none;
                border-radius:11px;
                font-weight:850;
                padding:9px 14px;
            }
            QPushButton:hover { background:#1456A0; }
            QPushButton:disabled { background:#CBD5E1;color:#64748B; }
        """)
        self.btn_entrar.setStyleSheet("""
            QPushButton {
                background:#F5B21B;
                color:#071A33;
                border:none;
                border-radius:11px;
                font-size:14px;
                font-weight:900;
                padding:12px 18px;
            }
            QPushButton:hover { background:#FFD05A; }
        """)

        root.addStretch(1)
        root.addWidget(card, 0, Qt.AlignHCenter)
        root.addStretch(1)
        return panel

    def _login(self):
        if not self.user.text().strip() or not self.password.text().strip():
            mensagem_operacional(self, "Login", "informe usuário/e-mail e senha para entrar.", "alerta")
            return
        row = autenticar(self.user.text(), self.password.text(), sistema="orcamentos")
        if not row:
            mensagem_operacional(
                self,
                "Login",
                "não consegui liberar o acesso ao Orçamentos PPP. Confira a senha, se o usuário está ativo e se a tela Orçamentos PPP foi liberada no cadastro de usuários.",
                "alerta",
            )
            return
        self._salvar_lembrado()
        session.set_usuario(row)
        self.on_login(row)

    def _alternar_senha(self):
        visivel = self.password.echoMode() == QLineEdit.Normal
        self.password.setEchoMode(QLineEdit.Password if visivel else QLineEdit.Normal)
        self.btn_ver_senha.setText("Ver" if visivel else "Ocultar")

    def _carregar_lembrado(self):
        lembrar = self.settings.value("login/lembrar", False, type=bool)
        usuario = self.settings.value("login/usuario", "", type=str)
        self.remember.setChecked(lembrar)
        if lembrar and usuario:
            self.user.setText(usuario)

    def _salvar_lembrado(self):
        if self.remember.isChecked():
            self.settings.setValue("login/lembrar", True)
            self.settings.setValue("login/usuario", self.user.text().strip())
        else:
            self.settings.setValue("login/lembrar", False)
            self.settings.remove("login/usuario")
