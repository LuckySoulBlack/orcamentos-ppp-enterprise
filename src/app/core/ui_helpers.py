from datetime import date
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget, QGraphicsDropShadowEffect
)

from core import session
from widgets.lottie_widget import LottieWidget


COR_PRIMARIA = "#0B3B75"
COR_PRIMARIA_HOVER = "#1456A0"
COR_ADICIONAR = "#16A34A"
COR_ADICIONAR_HOVER = "#15803D"
COR_EXCLUIR = "#DC2626"
COR_EXCLUIR_HOVER = "#B91C1C"
COR_DOCUMENTO = "#7C3AED"
COR_DOCUMENTO_HOVER = "#6D28D9"
COR_SECUNDARIA = "#EAF2FF"


def _asset(nome):
    return Path(__file__).resolve().parents[1] / "assets" / nome


def _normalizar(texto):
    return str(texto or "").strip().lower()


def tipo_botao(texto):
    t = _normalizar(texto)
    if any(p in t for p in ["excluir", "remover", "inativar", "apagar"]):
        return "danger"
    if any(p in t for p in ["adicionar", "anexar", "importar pacote do executor"]):
        return "success"
    if any(p in t for p in [
        "gerar pdf", "gerar word", "gerar excel", "gerar relatório", "gerar relatorio",
        "gerar planilha", "gerar pacote", "dashboard executivo", "orçamento simples", "orcamento simples"
    ]):
        return "document"
    if t.startswith("abrir") or "selecionar" in t or "limpar" in t or "atualizar" in t:
        return "secondary"
    return "primary"


def aplicar_estilo_botao(botao):
    if not isinstance(botao, QPushButton):
        return
    kind = tipo_botao(botao.text())
    if kind == "danger":
        bg, hover, fg, border = COR_EXCLUIR, COR_EXCLUIR_HOVER, "white", "none"
    elif kind == "success":
        bg, hover, fg, border = COR_ADICIONAR, COR_ADICIONAR_HOVER, "white", "none"
    elif kind == "document":
        bg, hover, fg, border = COR_DOCUMENTO, COR_DOCUMENTO_HOVER, "white", "none"
    elif kind == "secondary":
        bg, hover, fg, border = COR_SECUNDARIA, "#DCEBFF", COR_PRIMARIA, "1px solid #BFD7FF"
    else:
        bg, hover, fg, border = COR_PRIMARIA, COR_PRIMARIA_HOVER, "white", "none"
    botao.setProperty("actionKind", kind)
    botao.setStyleSheet(f"""
        QPushButton {{
            background:{bg};
            color:{fg};
            border:{border};
            border-radius:8px;
            font-weight:850;
            padding:9px 14px;
        }}
        QPushButton:hover {{ background:{hover}; }}
        QPushButton:disabled {{ background:#CBD5E1; color:#64748B; border:none; }}
    """)


def aplicar_botoes_semanticos(root=None):
    app = QApplication.instance()
    widgets = root.findChildren(QPushButton) if isinstance(root, QWidget) else (app.allWidgets() if app else [])
    for botao in widgets:
        aplicar_estilo_botao(botao)


def mensagem_operacional(parent, titulo, texto, tipo="info"):
    from PySide6.QtWidgets import QMessageBox

    nome = session.nome_usuario("tudo bem")
    corpo = f"{nome}, {texto}"
    if tipo == "erro":
        corpo += (
            "\n\nComo resolver: salve o cadastro aberto, aguarde a sincronização do Google Drive e tente novamente. "
            "Se continuar, envie uma imagem da tela para suporte."
        )
        QMessageBox.critical(parent, titulo, corpo)
    elif tipo == "alerta":
        corpo += "\n\nPróximo passo: revise o campo indicado, salve o cadastro e tente seguir o processo novamente."
        QMessageBox.warning(parent, titulo, corpo)
    else:
        QMessageBox.information(parent, titulo, corpo)


def _shadow(widget):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(32)
    effect.setOffset(0, 12)
    effect.setColor(QColor(15, 23, 42, 42))
    widget.setGraphicsEffect(effect)


class BoasVindasDialog(QDialog):
    def __init__(self, parent=None, sistema="sistema"):
        super().__init__(parent)
        self.setWindowTitle("Guia rápido")
        self.resize(760, 430)
        self.setMinimumSize(680, 400)
        self.setStyleSheet("background:#EEF3FA;")
        self.indice = 0
        self.slides = [
            (
                "Confira a base",
                "Antes de gerar documentos, revise cliente, contrato, executor, prazo e local.",
                ["Cliente/contrato", "Executor", "Prazo"],
                "#0B3B75",
                "lottie/business_plan.json",
            ),
            (
                "Registre a execução",
                "Inclua etapas, itens, quantidades e fotos por categoria durante a obra.",
                ["Etapas", "Itens", "Fotos"],
                "#16A34A",
                "lottie/construction.json",
            ),
            (
                "Salve e gere",
                "Depois de salvar, gere PDF, Word, Excel ou pacote de importação.",
                ["Salvar", "Gerar", "Conferir"],
                "#7C3AED",
                "lottie/business_analysis.json",
            ),
        ]

        shell = QFrame()
        shell.setObjectName("GuideShell")
        shell.setStyleSheet("""
            QFrame#GuideShell {
                background:white;
                border:1px solid #DCE6F2;
                border-radius:18px;
            }
        """)
        _shadow(shell)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.addWidget(shell)

        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.visual = QFrame()
        self.visual.setMinimumWidth(300)
        self.visual.setStyleSheet("""
            background:qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #071A33, stop:1 #123E70);
            border-top-left-radius:18px;
            border-bottom-left-radius:18px;
        """)
        self.visual_layout = QVBoxLayout(self.visual)
        self.visual_layout.setContentsMargins(24, 24, 24, 24)
        self.visual_layout.setSpacing(12)

        self.progress = QLabel("1 de 3")
        self.progress.setAlignment(Qt.AlignCenter)
        self.progress.setStyleSheet("""
            color:white;
            background:rgba(255,255,255,0.12);
            border:1px solid rgba(255,255,255,0.18);
            border-radius:12px;
            padding:8px 12px;
            font-size:13px;
            font-weight:850;
        """)
        self.visual_layout.addWidget(self.progress, 0, Qt.AlignLeft)

        self.lottie_box = QVBoxLayout()
        self.visual_layout.addLayout(self.lottie_box, 1)
        self.visual_note = QLabel("Fluxo guiado para reduzir erros de preenchimento.")
        self.visual_note.setWordWrap(True)
        self.visual_note.setStyleSheet("color:#DCEBFF;font-size:12px;font-weight:650;")
        self.visual_layout.addWidget(self.visual_note)

        content = QFrame()
        content.setStyleSheet("background:white;border-top-right-radius:18px;border-bottom-right-radius:18px;")
        right = QVBoxLayout(content)
        right.setContentsMargins(34, 30, 34, 24)
        right.setSpacing(11)

        self.eyebrow = QLabel("GUIA RÁPIDO")
        self.eyebrow.setStyleSheet("color:#0B3B75;font-size:10px;font-weight:900;letter-spacing:1px;")
        self.titulo = QLabel()
        self.titulo.setWordWrap(True)
        self.titulo.setTextFormat(Qt.RichText)
        self.titulo.setStyleSheet("font-size:22px;font-weight:900;color:#071A33;")
        self.texto = QLabel()
        self.texto.setWordWrap(True)
        self.texto.setStyleSheet("font-size:13px;color:#334155;font-weight:650;")
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(10)

        buttons = QHBoxLayout()
        self.btn_ant = QPushButton("Voltar")
        self.btn_prox = QPushButton("Próximo")
        self.btn_fechar = QPushButton("Entendi")
        self.btn_ant.clicked.connect(self.anterior)
        self.btn_prox.clicked.connect(self.proximo)
        self.btn_fechar.clicked.connect(self.accept)
        buttons.addWidget(self.btn_ant)
        buttons.addStretch()
        buttons.addWidget(self.btn_prox)
        buttons.addWidget(self.btn_fechar)

        right.addWidget(self.eyebrow)
        right.addWidget(self.titulo)
        right.addWidget(self.texto)
        right.addSpacing(8)
        right.addLayout(self.grid)
        right.addStretch()
        right.addLayout(buttons)

        layout.addWidget(self.visual, 4)
        layout.addWidget(content, 6)
        aplicar_botoes_semanticos(self)
        self._render()

    def _limpar_lottie(self):
        while self.lottie_box.count():
            item = self.lottie_box.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _render(self):
        saudacao = session.saudacao_atual()
        nome = session.nome_usuario("usuário")
        titulo, texto, passos, cor, animacao = self.slides[self.indice]
        self.titulo.setText(
            f'{saudacao}, <span style="color:#C2410C;font-size:24px;">{nome}</span><br>{titulo}'
        )
        self.texto.setText(texto)
        self.progress.setText(f"{self.indice + 1} de {len(self.slides)}")

        self._limpar_lottie()
        lottie = LottieWidget(_asset(animacao))
        lottie.setMinimumHeight(190)
        self.lottie_box.addWidget(lottie)

        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        for i, passo in enumerate(passos):
            item = QLabel(passo)
            item.setAlignment(Qt.AlignCenter)
            item.setWordWrap(True)
            item.setMinimumHeight(52)
            item.setStyleSheet(f"""
                background:#F8FAFC;
                color:#071A33;
                border:1px solid #D7E2EF;
                border-top:3px solid {cor};
                border-radius:10px;
                padding:8px;
                font-size:12px;
                font-weight:800;
            """)
            self.grid.addWidget(item, 0, i)
        self.btn_ant.setEnabled(self.indice > 0)
        self.btn_prox.setEnabled(self.indice < len(self.slides) - 1)

    def anterior(self):
        self.indice = max(0, self.indice - 1)
        self._render()

    def proximo(self):
        self.indice = min(len(self.slides) - 1, self.indice + 1)
        self._render()


def mostrar_boas_vindas_uma_vez(parent, sistema):
    nome = session.nome_usuario("usuario")
    chave = f"boas_vindas/{sistema}/{nome}/{date.today().isoformat()}"
    settings = QSettings("OrcamentosPPP", sistema)
    if settings.value(chave, False, type=bool):
        return
    settings.setValue(chave, True)
    BoasVindasDialog(parent, sistema).exec()
