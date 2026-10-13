import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QVBoxLayout, QLabel

from core.theme import APP_NAME, QSS
from core.database import init_db
from core import session
from core.ui_helpers import aplicar_botoes_semanticos, mostrar_boas_vindas_uma_vez
from services import auth_service
from services.backup_service import gerar_backup_diario_se_necessario
from widgets.sidebar import Sidebar
from views.login_view import LoginView
from views.dashboard_view import DashboardView
from views.empresa_view import EmpresaView
from views.clientes_view import ClientesView
from views.contratos_view import ContratosView
from views.sinapi_view import SinapiView
from views.orcamentos_view import OrcamentosView
from views.configuracoes_view import ConfiguracoesView
from views.meus_orcamentos_view import MeusOrcamentosView
from views.relatorios_view import RelatoriosView
from views.ordens_servico_view import OrdensServicoView
from views.usuarios_view import UsuariosView
from views.os_acompanhamento_view import MapaExecucoesView, KanbanExecucoesView
from views.splash_screen import ModernSplash


def resource_path(relative_path):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative_path


def app_icon():
    icon_path = resource_path("assets/icons/app.ico")
    return QIcon(str(icon_path)) if icon_path.exists() else QIcon()


class Placeholder(QWidget):
    def __init__(self, title, subtitle="Módulo em fechamento para o beta."):
        super().__init__()
        lay = QVBoxLayout(self)
        lbl = QLabel(title)
        lbl.setObjectName("Title")
        lbl.setAlignment(Qt.AlignCenter)
        sub = QLabel(subtitle)
        sub.setObjectName("SubTitle")
        sub.setAlignment(Qt.AlignCenter)
        lay.addStretch(); lay.addWidget(lbl); lay.addWidget(sub); lay.addStretch()


class MainWindow(QMainWindow):
    def __init__(self, usuario_atual):
        super().__init__()
        self.usuario_atual = dict(usuario_atual)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.ajustar_tamanho_inicial()

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget()
        self.pages = {
            "dashboard": DashboardView(),
            "orcamentos": OrcamentosView(),
            "contratos": ContratosView(),
            "clientes": ClientesView(),
            "empresa": EmpresaView(),
            "sinapi": SinapiView(),
            "config": ConfiguracoesView(),
            "meus_orcamentos": MeusOrcamentosView(self.abrir_orcamento_direto),
            "ordens_servico": OrdensServicoView(self.abrir_orcamento_direto, modo="admin"),
            "os_mapa": MapaExecucoesView(),
            "os_kanban": KanbanExecucoesView(),
            "usuarios": UsuariosView(),
            "relatorios": RelatoriosView(),
        }
        self.sidebar = Sidebar(self.navigate)
        root.addWidget(self.sidebar)
        root.addWidget(self.stack, 1)
        for p in self.pages.values():
            self.stack.addWidget(p)
        aplicar_botoes_semanticos(self)
        self.allowed_keys = self._allowed_keys()
        self.sidebar.set_allowed_keys(self.allowed_keys)
        self.navigate(self.allowed_keys[0] if self.allowed_keys else "dashboard")

    def _allowed_keys(self):
        if str(self.usuario_atual.get("perfil") or "").upper() == "ADMIN":
            return list(self.pages.keys())
        permissoes = set(auth_service.permissoes_usuario(self.usuario_atual))
        if "*" in permissoes:
            return list(self.pages.keys())
        ordem = [
            "dashboard", "orcamentos", "meus_orcamentos", "ordens_servico",
            "os_mapa", "os_kanban", "usuarios", "contratos", "clientes",
            "empresa", "sinapi", "relatorios", "config",
        ]
        return [key for key in ordem if key in self.pages and key in permissoes]

    def ajustar_tamanho_inicial(self):
        """Abre a janela em tamanho proporcional ao monitor e permite redimensionar."""
        screen = QApplication.primaryScreen().availableGeometry()
        largura = min(1440, int(screen.width() * 0.90))
        altura = min(860, int(screen.height() * 0.88))
        largura = max(1120, min(largura, screen.width() - 70))
        altura = max(700, min(altura, screen.height() - 70))
        self.resize(largura, altura)
        self.setMinimumSize(1040, 650)
        frame = self.frameGeometry()
        frame.moveCenter(screen.center())
        self.move(frame.topLeft())

    def navigate(self, key):
        if key not in self.pages or key not in getattr(self, "allowed_keys", []):
            return
        page = self.pages[key]
        if hasattr(page, "refresh"):
            page.refresh()
        self.stack.setCurrentWidget(page)
        self.sidebar.set_active(key)
        aplicar_botoes_semanticos(page)

    def abrir_orcamento_direto(self, orcamento_id):
        pagina = self.pages.get("orcamentos")
        if not pagina:
            return

        if orcamento_id in (0, None):
            if hasattr(pagina, "novo_orcamento"):
                pagina.novo_orcamento()
            elif hasattr(pagina, "limpar_tela"):
                pagina.limpar_tela()
            self.navigate("orcamentos")
            return

        for metodo in ["carregar_orcamento", "abrir_orcamento", "load_orcamento"]:
            if hasattr(pagina, metodo):
                getattr(pagina, metodo)(orcamento_id)
                self.navigate("orcamentos")
                return

        pagina.orcamento_id = orcamento_id
        for metodo in [
            "carregar_dados_orcamento",
            "carregar_etapas",
            "carregar_itens",
            "carregar_opex",
            "carregar_cronograma",
            "carregar_anexos",
        ]:
            if hasattr(pagina, metodo):
                try:
                    getattr(pagina, metodo)()
                except Exception:
                    pass
        self.navigate("orcamentos")


def start():
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    icone = app_icon()
    if not icone.isNull():
        app.setWindowIcon(icone)

    splash = ModernSplash()
    splash.show()
    app.splash = splash
    app.processEvents()

    def carregar_banco():
        splash.set_message("Inicializando banco compartilhado...", 25)
        try:
            init_db()
            auth_service.garantir_admin_recuperacao()
            try:
                gerar_backup_diario_se_necessario()
            except Exception:
                # O backup não deve impedir a abertura para diagnóstico.
                pass
            splash.set_message("Carregando interface executiva...", 65)
        except Exception as e:
            splash.set_message(f"Falha ao iniciar banco: {e}", 65)
        QTimer.singleShot(900, preparar_login)

    def preparar_login():
        splash.set_message("Preparando tela de login...", 92)
        app.login = LoginView(open_main)
        QTimer.singleShot(650, mostrar_login)

    def mostrar_login():
        splash.finish_splash()
        app.login.show()

    def open_main(usuario):
        session.set_usuario(usuario)
        win = MainWindow(usuario)
        win.showNormal()
        app.main_window = win
        if getattr(app, "login", None):
            app.login.close()
        QTimer.singleShot(450, lambda: mostrar_boas_vindas_uma_vez(win, "OrcamentosPPP"))

    QTimer.singleShot(180, carregar_banco)
    sys.exit(app.exec())


if __name__ == "__main__":
    start()
