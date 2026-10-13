APP_NAME = "Orçamentos PPP"
APP_VERSION = "2.2.0"

COLORS = {
    "navy": "#071A33",
    "blue": "#0B3B75",
    "blue2": "#1456A0",
    "gold": "#F5B21B",
    "green": "#16A34A",
    "orange": "#F97316",
    "red": "#DC2626",
    "bg": "#F4F7FB",
    "border": "#DBE4EF",
    "muted": "#64748B",
    "text": "#172033",
}

QSS = """
QMainWindow { background:#F4F7FB; }
QWidget { font-family:'Segoe UI'; font-size:13px; color:#172033; }
QFrame#Sidebar { background:#071A33; border-right:1px solid #10294D; }
QFrame#Card, QGroupBox { background:white; border:1px solid #DBE4EF; border-radius:12px; }
QGroupBox { margin-top:16px; padding:14px; font-weight:800; color:#0B3B75; }
QGroupBox::title { subcontrol-origin: margin; left:12px; padding:0 6px; background:white; }
QLabel#Title { font-size:24px; font-weight:900; color:#071A33; }
QLabel#SubTitle { color:#64748B; font-size:12px; }
QPushButton { background:#0B3B75; color:white; border:none; border-radius:7px; padding:9px 14px; font-weight:700; }
QPushButton:hover { background:#1456A0; }
QPushButton:disabled { background:#CBD5E1; color:#64748B; }
QPushButton#Secondary { background:#EAF2FF; color:#0B3B75; border:1px solid #BFD7FF; }
QPushButton#Secondary:hover { background:#DCEBFF; }
QPushButton#Danger { background:#DC2626; color:white; }
QPushButton#Success { background:#16A34A; color:white; }
QPushButton#MenuButton { background:transparent; color:white; text-align:left; border-radius:8px; padding:10px 12px; }
QPushButton#MenuButton:hover { background:#10294D; }
QPushButton#MenuButton[active="true"] { background:#0B3B75; color:white; }
QLineEdit,QComboBox,QTextEdit,QDoubleSpinBox,QSpinBox,QDateEdit { background:white; border:1px solid #D8E0EA; border-radius:7px; padding:7px; }
QLineEdit:focus,QComboBox:focus,QTextEdit:focus,QDoubleSpinBox:focus,QDateEdit:focus { border:1px solid #0B3B75; }
QComboBox QAbstractItemView {
    background:#FFFFFF;
    color:#142033;
    border:1px solid #BFD0E4;
    selection-background-color:#DCEBFF;
    selection-color:#0B3B75;
    outline:0;
    padding:4px;
}
QTableWidget { background:white; border:1px solid #DBE4EF; border-radius:10px; gridline-color:#EDF2F7; selection-background-color:#DBEAFE; selection-color:#071A33; }
QHeaderView::section { background:#EAF2FF; color:#0B3B75; padding:8px; font-weight:800; border:none; border-right:1px solid #DBE4EF; }
QTabWidget::pane { border:1px solid #DBE4EF; background:white; border-radius:10px; }
QTabBar::tab { background:#F8FAFC; color:#64748B; padding:10px 18px; border-top-left-radius:8px; border-top-right-radius:8px; margin-right:2px; }
QTabBar::tab:selected { background:white; color:#0B3B75; border-bottom:3px solid #0B3B75; font-weight:800; }
"""
