import sys
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QLabel

from core import session
from core.database import init_db
from core.theme import QSS
from core.ui_helpers import aplicar_botoes_semanticos, mostrar_boas_vindas_uma_vez
from services import auth_service
from services.backup_service import gerar_backup_diario_se_necessario
from views.configuracoes_view import ConfiguracoesView
from views.executores_view import ExecutoresView
from views.login_operacional_view import LoginOperacionalView
from views.ordens_servico_view import OrdensServicoView
from views.os_acompanhamento_view import MapaExecucoesView


def resource_path(relative_path):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


def app_icon():
    icon_path = resource_path("assets/icons/app.ico")
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


class OsWindow(QMainWindow):
    def __init__(self, usuario):
        super().__init__()
        self.setWindowTitle("OS PPP")
        self.setWindowIcon(app_icon())
        self.resize(1440, 860)
        self.setMinimumSize(1180, 720)

        self.tabs = QTabWidget()
        permissoes = set(auth_service.permissoes_usuario(usuario))
        if "*" in permissoes or "os_execucao" in permissoes:
            self.tabs.addTab(OrdensServicoView(modo="operacional", usuario_atual=dict(usuario)), "Ordens de serviço")
        if "*" in permissoes or "os_config" in permissoes:
            self.tabs.addTab(ConfiguracoesView(), "Configurações")
        if "*" in permissoes or "os_executores" in permissoes:
            self.tabs.addTab(ExecutoresView(), "Executores")
        if "*" in permissoes or "os_mapa" in permissoes:
            self.tabs.addTab(MapaExecucoesView(), "Mapa")
        if self.tabs.count() == 0:
            label = QLabel("Usuário sem telas liberadas no OS PPP. Revise o cadastro no Orçamentos PPP.")
            label.setStyleSheet("font-size:18px;font-weight:800;color:#0B3B75;padding:30px;")
            self.tabs.addTab(label, "Acesso")
        aplicar_botoes_semanticos(self)
        self.tabs.currentChanged.connect(lambda idx: self._refresh_tab(self.tabs.widget(idx)))
        self.setCentralWidget(self.tabs)

    def _refresh_tab(self, widget):
        if hasattr(widget, "refresh"):
            widget.refresh()
        aplicar_botoes_semanticos(self)

    def changeEvent(self, event):
        """Recarrega a tela ao voltar para o OS PPP.

        Assim, alterações salvas no Orçamentos PPP aparecem no OS PPP
        quando o usuário alterna entre os dois aplicativos.
        """
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow() and hasattr(self, "tabs"):
            self._refresh_tab(self.tabs.currentWidget())


def start():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    icon = app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    init_db()
    auth_service.garantir_admin_recuperacao()
    try:
        gerar_backup_diario_se_necessario()
    except Exception:
        # O backup não deve bloquear o login operacional.
        pass

    def abrir_os(usuario):
        session.set_usuario(usuario)
        win = OsWindow(usuario)
        app.main_window = win
        win.show()
        app.login.close()
        QTimer.singleShot(450, lambda: mostrar_boas_vindas_uma_vez(win, "OSPPP"))

    app.login = LoginOperacionalView(abrir_os)
    app.login.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    start()
