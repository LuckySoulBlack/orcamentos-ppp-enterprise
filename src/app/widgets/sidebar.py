from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget, QSizePolicy


class Sidebar(QFrame):
    def __init__(self, navigate_callback):
        super().__init__()
        self.navigate_callback = navigate_callback
        self.expanded = True
        self.active_key = None
        self.setObjectName("Sidebar")
        self.setFixedWidth(232)
        self.setStyleSheet("""
            QFrame#Sidebar {
                background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #06152C, stop:1 #082653);
                border:none;
            }
        """)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 16, 14, 14)
        self.layout.setSpacing(7)

        self._build_header()
        self.layout.addSpacing(8)

        self.buttons = []
        self.menu = [
            ("home", "Dashboard", "dashboard"),
            ("file", "Orçamentos", "orcamentos"),
            ("list", "Meus Orçamentos", "meus_orcamentos"),
            ("service", "Ordens de Serviço", "ordens_servico"),
            ("map", "Mapa de Execuções", "os_mapa"),
            ("users", "Usuários", "usuarios"),
            ("contract", "Contratos PPP", "contratos"),
            ("users", "Clientes", "clientes"),
            ("building", "Empresa", "empresa"),
            ("chart", "SINAPI", "sinapi"),
            ("report", "Relatórios", "relatorios"),
            ("settings", "Configurações", "config"),
        ]

        for icon_key, text, key in self.menu:
            btn = QPushButton(text)
            btn.setObjectName("MenuItem")
            btn.setIcon(self._icon(icon_key))
            btn.setIconSize(QSize(18, 18))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(42)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.clicked.connect(lambda checked=False, k=key: self._go(k))
            self.layout.addWidget(btn)
            self.buttons.append((btn, icon_key, text, key))

        self.layout.addStretch()

        self.toggle = QPushButton("«  Recolher menu")
        self.toggle.setObjectName("SidebarToggle")
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setMinimumHeight(34)
        self.toggle.clicked.connect(self.toggle_sidebar)
        self.toggle.setStyleSheet("""
            QPushButton#SidebarToggle {
                background:transparent;
                color:#DCEBFF;
                text-align:left;
                border:none;
                font-weight:800;
                padding:7px 12px;
            }
            QPushButton#SidebarToggle:hover { color:#F5B21B; }
        """)
        self.layout.addWidget(self.toggle)

        self.footer = QLabel(self._footer_text())
        self.footer.setAlignment(Qt.AlignCenter)
        self.footer.setWordWrap(True)
        self.footer.setStyleSheet("""
            QLabel {
                color:#BFD7FF;
                font-size:9px;
                line-height:132%;
                background:rgba(255,255,255,0.04);
                border:none;
                border-radius:10px;
                padding:8px;
            }
        """)
        self.layout.addWidget(self.footer)
        self.set_active("dashboard")

    def _footer_text(self):
        return "Lucas Henrique de Oliveira\nCNPJ 49.560.970/0001-30\nVersão 2.0.0"

    def _build_header(self):
        self.header = QWidget()
        self.header.setObjectName("SidebarHeader")
        self.header.setStyleSheet("""
            QWidget#SidebarHeader {
                background:transparent;
                border:none;
            }
        """)

        h = QHBoxLayout(self.header)
        h.setContentsMargins(4, 4, 4, 4)
        h.setSpacing(10)

        icons_dir = Path(__file__).resolve().parents[1] / "assets" / "icons"
        icon_path = icons_dir / "app_icon_256.png"

        self.logo = QLabel()
        self.logo.setFixedSize(50, 50)
        self.logo.setAlignment(Qt.AlignCenter)
        self.logo.setStyleSheet("background:transparent;border:none;")

        if icon_path.exists():
            pix = QPixmap(str(icon_path))
            if not pix.isNull():
                self.logo.setPixmap(
                    pix.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        else:
            self.logo.setText("PPP")
            self.logo.setStyleSheet("color:#F5B21B;font-size:18px;font-weight:950;background:transparent;border:none;")

        self.brand = QWidget()
        self.brand.setStyleSheet("background:transparent;border:none;")
        b = QVBoxLayout(self.brand)
        b.setContentsMargins(0, 0, 0, 0)
        b.setSpacing(0)

        self.title = QLabel("Orçamentos PPP")
        self.title.setStyleSheet("color:white;font-size:15px;font-weight:950;background:transparent;border:none;")
        self.version = QLabel("Enterprise")
        self.version.setStyleSheet("color:#F5B21B;font-size:10px;font-weight:950;letter-spacing:1px;background:transparent;border:none;")

        b.addWidget(self.title)
        b.addWidget(self.version)

        h.addWidget(self.logo)
        h.addWidget(self.brand, 1)
        self.layout.addWidget(self.header)

    def _icon(self, key):
        icons_dir = Path(__file__).resolve().parents[1] / "assets" / "icons"
        mapping = {
            "home": "home.svg",
            "file": "file-text.svg",
            "list": "folder.svg",
            "service": "clipboard.svg",
            "map": "map.svg",
            "kanban": "columns.svg",
            "contract": "clipboard.svg",
            "users": "users.svg",
            "building": "building.svg",
            "chart": "bar-chart.svg",
            "report": "folder.svg",
            "settings": "settings.svg",
        }
        path = icons_dir / mapping.get(key, "file-text.svg")
        return QIcon(str(path)) if path.exists() else QIcon()

    def _style_button(self, active=False):
        if active:
            return """
                QPushButton#MenuItem {
                    background:#1D5FC2;
                    color:white;
                    text-align:left;
                    padding:10px 14px;
                    border-radius:12px;
                    font-size:13px;
                    font-weight:900;
                    border:none;
                }
            """
        return """
            QPushButton#MenuItem {
                background:transparent;
                color:#EAF2FF;
                text-align:left;
                padding:10px 14px;
                border-radius:12px;
                font-size:13px;
                font-weight:800;
                border:none;
            }
            QPushButton#MenuItem:hover { background:rgba(255,255,255,0.08); }
        """

    def _go(self, key):
        self.set_active(key)
        self.navigate_callback(key)

    def set_active(self, key):
        self.active_key = key
        for btn, icon_key, text, k in self.buttons:
            btn.setStyleSheet(self._style_button(k == key))

    def set_allowed_keys(self, allowed_keys):
        allowed = set(allowed_keys or [])
        for btn, _icon_key, _text, key in self.buttons:
            btn.setVisible(key in allowed)

    def toggle_sidebar(self):
        self.expanded = not self.expanded
        self.setFixedWidth(232 if self.expanded else 70)
        self.brand.setVisible(self.expanded)
        self.footer.setVisible(self.expanded)
        self.toggle.setText("«  Recolher menu" if self.expanded else "»")
        for btn, icon_key, text, key in self.buttons:
            btn.setText(text if self.expanded else "")
