from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient, QFont
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QApplication


class AnimatedLogo(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)
        self.angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(28)

    def tick(self):
        self.angle = (self.angle + 4) % 360
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(12, 12, self.width() - 24, self.height() - 24)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawEllipse(rect)

        pen_back = QPen(QColor(255, 255, 255, 50), 8)
        pen_back.setCapStyle(Qt.RoundCap)
        painter.setPen(pen_back)
        painter.drawArc(rect, 0, 360 * 16)

        pen = QPen(QColor("#F5B21B"), 8)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, int(self.angle * 16), 120 * 16)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#DBEAFE"))
        painter.drawRoundedRect(49, 62, 52, 48, 10, 10)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRoundedRect(57, 72, 36, 5, 2, 2)
        painter.drawRoundedRect(57, 84, 29, 5, 2, 2)
        painter.drawRoundedRect(57, 96, 22, 5, 2, 2)

        painter.setBrush(QColor("#F5B21B"))
        painter.drawEllipse(94, 47, 20, 20)
        painter.setBrush(QColor("#16A34A"))
        painter.drawEllipse(38, 96, 18, 18)

        painter.setPen(QColor("#071A33"))
        painter.setFont(QFont("Segoe UI", 16, QFont.Black))
        painter.drawText(self.rect(), Qt.AlignCenter, "PPP")


class ModernSplash(QDialog):
    messages = [
        "Carregando contratos...",
        "Sincronizando orçamentos...",
        "Validando CAPEX/OPEX...",
        "Preparando anexos compartilhados...",
        "Montando dashboard executivo...",
    ]

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Dialog)
        self.setModal(False)
        self.setFixedSize(520, 420)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.step = 0

        self.container = QLabel(self)
        self.container.setGeometry(0, 0, 520, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(42, 34, 42, 34)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignCenter)

        self.logo = AnimatedLogo()
        layout.addWidget(self.logo, 0, Qt.AlignCenter)

        title = QLabel("Orçamentos PPP Enterprise")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:24px;font-weight:950;color:white;")
        layout.addWidget(title)

        subtitle = QLabel("Preparando ambiente executivo")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:13px;font-weight:750;color:#CFE3FF;")
        layout.addWidget(subtitle)

        self.message = QLabel(self.messages[0])
        self.message.setAlignment(Qt.AlignCenter)
        self.message.setStyleSheet("font-size:13px;font-weight:800;color:#F5B21B;")
        layout.addWidget(self.message)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(12)
        self.progress.setStyleSheet("""
            QProgressBar { background:rgba(255,255,255,35); border:none; border-radius:6px; }
            QProgressBar::chunk { background:#F5B21B; border-radius:6px; }
        """)
        layout.addWidget(self.progress)

        footer = QLabel("IP Barretos • Cidade Inteligente")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("font-size:11px;font-weight:700;color:rgba(255,255,255,150);")
        layout.addWidget(footer)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(260)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor("#071A33"))
        grad.setColorAt(0.55, QColor("#0B3B75"))
        grad.setColorAt(1, QColor("#1456A0"))
        painter.setBrush(QBrush(grad))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 24, 24)

        painter.setBrush(QColor(255, 255, 255, 18))
        painter.drawEllipse(-60, -70, 190, 190)
        painter.drawEllipse(390, 285, 190, 190)

    def advance(self):
        self.step = min(self.step + 9, 96)
        self.progress.setValue(self.step)
        idx = min(len(self.messages) - 1, (self.step // 20))
        self.message.setText(self.messages[idx])
        QApplication.processEvents()

    def set_message(self, text, value=None):
        self.message.setText(text)
        if value is not None:
            self.progress.setValue(int(value))
        QApplication.processEvents()

    def finish_splash(self):
        self.progress.setValue(100)
        self.message.setText("Tudo pronto.")
        QApplication.processEvents()
        self.close()
