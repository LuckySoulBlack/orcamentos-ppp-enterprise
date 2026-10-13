from datetime import date
import html
import json

from PySide6.QtCore import Qt, QMimeData, QPoint, QRectF, QUrl
from PySide6.QtGui import QColor, QDrag, QPainter, QPen, QBrush, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QGroupBox, QScrollArea,
    QFrame, QDialog, QTextEdit, QMessageBox, QSizePolicy, QTabWidget
)

from services import ordem_servico_service as os_service
from core.ui_helpers import aplicar_botoes_semanticos
from widgets.table_utils import configurar_tabela_responsiva, ajustar_tabela_apos_carregar


STATUS_CORES = {
    "RASCUNHO": "#64748B",
    "AGUARDANDO_APROVACAO": "#F97316",
    "APROVADA_INICIO": "#2563EB",
    "EM_EXECUCAO": "#0B3B75",
    "CONCLUIDA": "#16A34A",
    "IMPORTADA_ORCAMENTO": "#7C3AED",
    "CANCELADA": "#DC2626",
}

STATUS_COLUNAS = {
    "RASCUNHO": ("#64748B", "#F8FAFC", "#FFFFFF"),
    "AGUARDANDO_APROVACAO": ("#F97316", "#FFF7ED", "#FFFCF8"),
    "APROVADA_INICIO": ("#2563EB", "#EFF6FF", "#FBFDFF"),
    "EM_EXECUCAO": ("#0B3B75", "#EFF6FC", "#FBFDFF"),
    "CONCLUIDA": ("#16A34A", "#F0FDF4", "#FCFFFD"),
    "IMPORTADA_ORCAMENTO": ("#7C3AED", "#F5F3FF", "#FDFCFF"),
    "CANCELADA": ("#DC2626", "#FEF2F2", "#FFFCFC"),
}

STATUS_KANBAN = [
    "AGUARDANDO_APROVACAO",
    "APROVADA_INICIO",
    "EM_EXECUCAO",
    "CONCLUIDA",
    "IMPORTADA_ORCAMENTO",
]

STATUS_KANBAN_LABELS = {
    "AGUARDANDO_APROVACAO": "Aguardando",
    "APROVADA_INICIO": "Aprovada",
    "EM_EXECUCAO": "Em execução",
    "CONCLUIDA": "Concluída",
    "IMPORTADA_ORCAMENTO": "Importada",
}


def _dias_ate(valor):
    try:
        ano, mes, dia = [int(p) for p in str(valor or "").split("-")[:3]]
        return (date(ano, mes, dia) - date.today()).days
    except Exception:
        return None


def _status_label(status):
    return str(status or "").replace("_", " ").title()


def _coordenada_brasil(lat, lng, municipio=""):
    """Normaliza coordenadas digitadas sem sinal para uso operacional no Brasil."""
    municipio_txt = str(municipio or "").lower()
    brasil_provavel = True
    if brasil_provavel and lat > 0:
        lat = -lat
    if brasil_provavel and lng > 0:
        lng = -lng
    return lat, lng


class MapaPinosWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.dados = []
        self.setMinimumHeight(360)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.web = None
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self.web = QWebEngineView(self)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self.web)
        except Exception:
            self.web = None

    def set_dados(self, dados):
        self.dados = dados
        if self.web:
            self.web.setHtml(self._html_mapa(), QUrl("https://sistema-ppp.local/mapa/"))
        else:
            self.update()

    def _pontos(self):
        pontos = []
        for row in self.dados:
            try:
                lat = float(str(row["latitude"] or "").replace(",", "."))
                lng = float(str(row["longitude"] or "").replace(",", "."))
                lat, lng = _coordenada_brasil(lat, lng, row["municipio"])
                pontos.append({
                    "numero": str(row["numero"] or "OS"),
                    "status": str(row["status"] or ""),
                    "municipio": str(row["municipio"] or ""),
                    "local": str(row["local_execucao"] or ""),
                    "objeto": str(row["objeto"] or ""),
                    "lat": lat,
                    "lng": lng,
                    "cor": STATUS_CORES.get(row["status"], "#64748B"),
                })
            except Exception:
                continue
        return pontos

    def _html_mapa(self):
        pontos = self._pontos()
        centro = [-20.5576, -48.5678]
        zoom = 13
        if pontos:
            centro = [pontos[0]["lat"], pontos[0]["lng"]]
            zoom = 14 if len(pontos) == 1 else 12
        payload = json.dumps(pontos, ensure_ascii=False)
        return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    html, body, #map {{ height:100%; margin:0; background:#EAF2FF; font-family:Segoe UI,Arial,sans-serif; }}
    .leaflet-container {{ background:#EAF2FF; }}
    .os-marker {{
      width:18px;height:18px;border-radius:50%;border:3px solid white;
      box-shadow:0 3px 10px rgba(15,23,42,.35);
    }}
    .empty {{
      height:100%;display:flex;align-items:center;justify-content:center;text-align:center;
      color:#0B3B75;font-weight:800;padding:24px;
    }}
    .popup-title {{ font-weight:900;color:#0B3B75;margin-bottom:4px; }}
    .popup-line {{ color:#334155;font-weight:600; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const pontos = {payload};
    const mapEl = document.getElementById('map');
    if (!window.L) {{
      mapEl.innerHTML = '<div class="empty">Não consegui carregar o mapa online. Confira a internet desta máquina e tente atualizar.</div>';
    }} else {{
      const map = L.map('map', {{ scrollWheelZoom:true }}).setView([{centro[0]}, {centro[1]}], {zoom});
      L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }}).addTo(map);
      if (!pontos.length) {{
        L.popup().setLatLng([{centro[0]}, {centro[1]}]).setContent('Preencha Latitude e Longitude na OS para posicionar os pinos no mapa.').openOn(map);
      }} else {{
        const bounds = [];
        pontos.forEach(p => {{
          const icon = L.divIcon({{
            className: '',
            html: `<div class="os-marker" style="background:${{p.cor}}"></div>`,
            iconSize: [24,24],
            iconAnchor: [12,12]
          }});
          const safe = s => String(s || '').replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
          L.marker([p.lat, p.lng], {{icon}}).addTo(map).bindPopup(
            `<div class="popup-title">${{safe(p.numero)}} | ${{safe(p.status)}}</div>` +
            `<div class="popup-line">${{safe(p.objeto)}}</div>` +
            `<div class="popup-line">${{safe(p.local)}}</div>` +
            `<div class="popup-line">${{safe(p.municipio)}}</div>`
          );
          bounds.push([p.lat, p.lng]);
        }});
        if (bounds.length > 1) map.fitBounds(bounds, {{padding:[42,42]}});
      }}
    }}
  </script>
</body>
</html>"""

    def paintEvent(self, event):
        if self.web:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(rect, QColor("#EEF4FB"))
        painter.setPen(QPen(QColor("#D4E2F2"), 1))
        for i in range(1, 6):
            x = rect.left() + rect.width() * i / 6
            y = rect.top() + rect.height() * i / 6
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))
        painter.setPen(QPen(QColor("#BFD0E4"), 2))
        painter.drawRoundedRect(rect, 10, 10)

        pontos = []
        for row in self.dados:
            try:
                lat = float(str(row["latitude"] or "").replace(",", "."))
                lng = float(str(row["longitude"] or "").replace(",", "."))
                lat, lng = _coordenada_brasil(lat, lng, row["municipio"])
                pontos.append((row, lat, lng))
            except Exception:
                continue

        if not pontos:
            painter.setPen(QColor("#64748B"))
            painter.setFont(QFont("Arial", 13, QFont.Bold))
            painter.drawText(rect, Qt.AlignCenter, "Nenhuma OS com Latitude/Longitude preenchidas.")
            painter.end()
            return

        lats = [p[1] for p in pontos]
        lngs = [p[2] for p in pontos]
        min_lat, max_lat = min(lats), max(lats)
        min_lng, max_lng = min(lngs), max(lngs)
        if min_lat == max_lat:
            min_lat -= 0.005
            max_lat += 0.005
        if min_lng == max_lng:
            min_lng -= 0.005
            max_lng += 0.005

        margem = 34
        area = rect.adjusted(margem, margem, -margem, -margem)
        painter.setFont(QFont("Arial", 8, QFont.Bold))
        for row, lat, lng in pontos:
            x = area.left() + (lng - min_lng) / (max_lng - min_lng) * area.width()
            y = area.bottom() - (lat - min_lat) / (max_lat - min_lat) * area.height()
            cor = QColor(STATUS_CORES.get(row["status"], "#64748B"))
            painter.setBrush(QBrush(cor))
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
            painter.drawEllipse(QPoint(int(x), int(y)), 9, 9)
            painter.setPen(QPen(cor.darker(130), 2))
            painter.drawLine(int(x), int(y) + 9, int(x), int(y) + 20)
            label = str(row["numero"] or "OS")
            label_rect = QRectF(x + 12, y - 13, 120, 24)
            painter.fillRect(label_rect, QColor(255, 255, 255, 220))
            painter.setPen(QColor("#0B3B75"))
            painter.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, label)
        painter.end()


class MapaExecucoesView(QWidget):
    def __init__(self):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        titulo = QLabel("Mapa de execucoes")
        titulo.setStyleSheet("font-size:24px;font-weight:950;color:#071A33;")
        sub = QLabel("Visao operacional por municipio, local e coordenadas. As cores indicam o status da OS.")
        sub.setStyleSheet("color:#64748B;font-weight:700;")
        sub.setWordWrap(True)
        root.addWidget(titulo)
        root.addWidget(sub)

        top = QHBoxLayout()
        self.filtro = QComboBox()
        self.filtro.addItems(["Todos os status"] + os_service.STATUS_OS)
        self.btn = QPushButton("Atualizar")
        self.filtro.currentIndexChanged.connect(self.carregar)
        self.btn.clicked.connect(self.carregar)
        top.addWidget(QLabel("Filtro"))
        top.addWidget(self.filtro, 1)
        top.addWidget(self.btn)
        root.addLayout(top)

        self.mapa = MapaPinosWidget()
        root.addWidget(self.mapa, 2)

        self.info_mapa = QLabel("Preencha Latitude e Longitude na OS para posicionar os pinos no mapa operacional.")
        self.info_mapa.setWordWrap(True)
        self.info_mapa.setStyleSheet("color:#64748B;font-weight:700;")
        root.addWidget(self.info_mapa)

        self.tabela = QTableWidget(0, 8)
        self.tabela.setHorizontalHeaderLabels(["ID", "Cor", "OS", "Status", "Municipio", "Local", "Latitude", "Longitude"])
        configurar_tabela_responsiva(self.tabela, stretch_columns=[5], hidden_columns=[0])
        root.addWidget(self.tabela, 1)
        self.carregar()

    def carregar(self):
        filtro = self.filtro.currentText() if hasattr(self, "filtro") else "Todos os status"
        dados = [r for r in os_service.listar_ordens() if filtro == "Todos os status" or r["status"] == filtro]
        self.mapa.set_dados(dados)
        com_coord = 0
        for row in dados:
            try:
                float(str(row["latitude"] or "").replace(",", "."))
                float(str(row["longitude"] or "").replace(",", "."))
                com_coord += 1
            except Exception:
                pass
        self.info_mapa.setText(f"{com_coord} de {len(dados)} OS com coordenadas posicionadas no mapa.")
        self.tabela.setRowCount(len(dados))
        for r, row in enumerate(dados):
            cor = STATUS_CORES.get(row["status"], "#64748B")
            valores = [row["id"], "●", row["numero"], row["status"], row["municipio"], row["local_execucao"], row["latitude"], row["longitude"]]
            for c, valor in enumerate(valores):
                item = QTableWidgetItem(str(valor or ""))
                item.setData(Qt.UserRole, row["id"])
                if c == 1:
                    item.setForeground(Qt.GlobalColor.white)
                    item.setBackground(QColor(cor))
                    item.setTextAlignment(Qt.AlignCenter)
                self.tabela.setItem(r, c, item)
        ajustar_tabela_apos_carregar(self.tabela)

    def refresh(self):
        self.carregar()


class KanbanCard(QFrame):
    def __init__(self, row, parent_view):
        super().__init__()
        self.row_data = row
        self.parent_view = parent_view
        self.drag_start = QPoint()
        self.setObjectName("KanbanCard")
        self.setCursor(Qt.OpenHandCursor)
        cor = STATUS_CORES.get(row["status"], "#64748B")
        _cor_coluna, _fundo_coluna, fundo_card = STATUS_COLUNAS.get(row["status"], ("#64748B", "#F8FAFC", "#FFFFFF"))
        self.setStyleSheet(f"""
            QFrame#KanbanCard {{
                background:{fundo_card};
                border:1px solid #D7E2EF;
                border-left:5px solid {cor};
                border-radius:8px;
            }}
            QFrame#KanbanCard:hover {{
                border:1px solid #8FB5E8;
                border-left:5px solid {cor};
                background:#FFFFFF;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 9, 10, 9)
        lay.setSpacing(7)

        numero = QLabel(row["numero"] or "OS")
        numero.setStyleSheet("font-weight:950;color:#0B3B75;font-size:14px;")
        lay.addWidget(numero)

        objeto = QLabel(row["objeto"] or "Objeto nao informado")
        objeto.setWordWrap(True)
        objeto.setStyleSheet("font-weight:800;color:#142033;")
        lay.addWidget(objeto)

        info = QLabel(
            f"Executor: {row['executor'] or 'nao informado'}\n"
            f"Inicio: {row['data_prevista_inicio'] or '-'} | Fim: {row['data_prevista_fim'] or '-'}"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#52627A;font-weight:700;font-size:12px;")
        lay.addWidget(info)

        dias = _dias_ate(row["data_prevista_fim"])
        prazo = QLabel("Sem prazo")
        if dias is not None:
            prazo.setText(f"{dias} dia(s) para entrega" if dias >= 0 else f"{abs(dias)} dia(s) em atraso")
        prazo.setStyleSheet("color:#B45309;font-weight:900;font-size:12px;")
        lay.addWidget(prazo)

        actions = QHBoxLayout()
        btn_abrir = QPushButton("Abrir OS")
        btn_abrir.clicked.connect(lambda: self.parent_view.abrir_os(row["id"]))
        btn_detalhes = QPushButton("Detalhes")
        btn_detalhes.clicked.connect(lambda: self.parent_view.detalhar(row["id"]))
        actions.addWidget(btn_abrir)
        actions.addWidget(btn_detalhes)
        lay.addLayout(actions)

        status_row = QHBoxLayout()
        self.status_combo = QComboBox()
        for status in STATUS_KANBAN:
            self.status_combo.addItem(STATUS_KANBAN_LABELS.get(status, _status_label(status)), status)
        atual = row["status"] if row["status"] in STATUS_KANBAN else STATUS_KANBAN[0]
        idx = self.status_combo.findData(atual)
        self.status_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.status_combo.setMinimumWidth(120)
        btn_status = QPushButton("Mover")
        btn_status.clicked.connect(lambda: self.parent_view.mover_status(row["id"], self.status_combo.currentData()))
        status_row.addWidget(self.status_combo, 1)
        status_row.addWidget(btn_status)
        lay.addLayout(status_row)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.LeftButton):
            return
        if (event.position().toPoint() - self.drag_start).manhattanLength() < 10:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(self.row_data["id"]))
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def mouseDoubleClickEvent(self, event):
        self.parent_view.abrir_os(self.row_data["id"])
        super().mouseDoubleClickEvent(event)


class KanbanColumn(QFrame):
    def __init__(self, status, parent_view):
        super().__init__()
        self.status = status
        self.parent_view = parent_view
        # Mantém espaço suficiente para ler os dados e usar os botões.
        # Quando as cinco colunas não couberem, o quadro externo rola
        # horizontalmente em vez de comprimir os cartões.
        self.setMinimumWidth(330)
        self.setAcceptDrops(True)
        self.setObjectName("KanbanColumn")
        cor, fundo, _fundo_card = STATUS_COLUNAS.get(status, ("#64748B", "#F8FAFC", "#FFFFFF"))
        self.setStyleSheet(f"""
            QFrame#KanbanColumn {{
                background:{fundo};
                border:1px solid {cor};
                border-radius:10px;
            }}
        """)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(10, 10, 10, 10)
        self.outer.setSpacing(10)

        self.header = QLabel(STATUS_KANBAN_LABELS.get(status, _status_label(status)))
        self.header.setAlignment(Qt.AlignCenter)
        self.header.setMinimumHeight(46)
        self.header.setStyleSheet(
            f"background:{cor};color:white;font-weight:950;border-radius:8px;"
            "padding:10px 12px;font-size:13px;"
        )
        self.outer.addWidget(self.header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setAcceptDrops(True)
        self.body.setStyleSheet("background:transparent;")
        self.lay = QVBoxLayout(self.body)
        self.lay.setContentsMargins(2, 2, 2, 2)
        self.lay.setSpacing(10)
        self.scroll.setWidget(self.body)
        self.outer.addWidget(self.scroll, 1)

    def add_card(self, card):
        self.lay.addWidget(card)

    def finish(self, count):
        vazio = QLabel("Sem obras neste status.")
        vazio.setAlignment(Qt.AlignCenter)
        vazio.setStyleSheet("color:#64748B;font-weight:900;padding:18px;background:rgba(255,255,255,155);border-radius:8px;")
        if count == 0:
            self.lay.addWidget(vazio)
        self.lay.addStretch()
        self.header.setText(f"{STATUS_KANBAN_LABELS.get(self.status, _status_label(self.status))} ({count})")

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event):
        try:
            ordem_id = int(event.mimeData().text())
            self.parent_view.mover_status(ordem_id, self.status)
            event.acceptProposedAction()
        except Exception as exc:
            QMessageBox.critical(self, "Kanban", f"Erro ao mover OS:\n{exc}")


class KanbanExecucoesView(QWidget):
    def __init__(self, abrir_os_callback=None, abrir_orcamento_callback=None):
        super().__init__()
        self.abrir_os_callback = abrir_os_callback
        self.abrir_orcamento_callback = abrir_orcamento_callback
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 20, 18, 18)
        root.setSpacing(12)

        top = QHBoxLayout()
        title_box = QVBoxLayout()
        titulo = QLabel("Kanban de obras")
        titulo.setStyleSheet("font-size:24px;font-weight:950;color:#071A33;")
        sub = QLabel("Acompanhamento visual por status, prazo e responsável.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:#64748B;font-weight:700;")
        title_box.addWidget(titulo)
        title_box.addWidget(sub)
        top.addLayout(title_box, 1)
        self.filtro = QComboBox()
        self.filtro.addItems(["Todas as obras", "Somente atrasadas", "Proximas entregas"])
        self.filtro.currentIndexChanged.connect(self.carregar)
        self.filtro.setMinimumWidth(210)
        top.addWidget(self.filtro)
        self.btn_atualizar = QPushButton("Atualizar")
        self.btn_atualizar.clicked.connect(self.carregar)
        top.addWidget(self.btn_atualizar)
        root.addLayout(top)

        self.board_frame = QFrame()
        self.board_frame.setObjectName("KanbanBoard")
        self.board_frame.setStyleSheet("""
            QFrame#KanbanBoard {
                background:#FFFFFF;
                border:1px solid #DBE4EF;
                border-radius:10px;
            }
        """)
        board = QVBoxLayout(self.board_frame)
        board.setContentsMargins(14, 14, 14, 14)
        board.setSpacing(10)

        self.board_scroll = QScrollArea()
        self.board_scroll.setWidgetResizable(True)
        self.board_scroll.setFrameShape(QFrame.NoFrame)
        self.board_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.board_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.content = QWidget()
        self.content.setStyleSheet("background:#FFFFFF;")
        largura_coluna = 330
        self.content.setMinimumWidth(
            len(STATUS_KANBAN) * largura_coluna + (len(STATUS_KANBAN) - 1) * 12
        )
        self.grid = QGridLayout(self.content)
        self.grid.setSpacing(12)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.board_scroll.setWidget(self.content)
        self.board_scroll.horizontalScrollBar().setSingleStep(largura_coluna + 12)
        board.addWidget(self.board_scroll, 1)
        root.addWidget(self.board_frame, 1)
        self.carregar()

    def _limpar_header(self):
        return

    def _limpar_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _dados_filtrados(self):
        filtro = self.filtro.currentText() if hasattr(self, "filtro") else "Todas as obras"
        dados = os_service.listar_ordens()
        if filtro == "Somente atrasadas":
            return [r for r in dados if (_dias_ate(r["data_prevista_fim"]) or 9999) < 0]
        if filtro == "Proximas entregas":
            return [r for r in dados if 0 <= (_dias_ate(r["data_prevista_fim"]) or 9999) <= 15]
        return dados

    def carregar(self):
        self._limpar_grid()
        dados = self._dados_filtrados()
        for col, status in enumerate(STATUS_KANBAN):
            coluna = KanbanColumn(status, self)
            cards = [r for r in dados if r["status"] == status]
            for row in cards:
                coluna.add_card(KanbanCard(row, self))
            coluna.finish(len(cards))
            self.grid.addWidget(coluna, 0, col)
            self.grid.setColumnStretch(col, 1)
        aplicar_botoes_semanticos(self)

    def mover_status(self, ordem_id, status):
        os_service.atualizar_status_ordem(ordem_id, status)
        self.carregar()

    def abrir_os(self, ordem_id):
        if self.abrir_os_callback:
            self.abrir_os_callback(ordem_id)
        else:
            self.detalhar(ordem_id)

    def detalhar(self, ordem_id):
        ordem = os_service.obter_ordem(ordem_id)
        etapas = os_service.listar_etapas(ordem_id)
        itens = os_service.listar_itens(ordem_id)
        anexos = os_service.listar_anexos(ordem_id)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Detalhamento da obra - {ordem['numero'] if ordem else ''}")
        dialog.resize(980, 640)
        lay = QVBoxLayout(dialog)

        header = QLabel(
            f"<b>{ordem['numero'] if ordem else ''}</b> | {_status_label(ordem['status'] if ordem else '')}<br>"
            f"{ordem['objeto'] if ordem else ''}"
        )
        header.setWordWrap(True)
        header.setStyleSheet("color:#071A33;font-size:15px;")
        lay.addWidget(header)

        tabs = QTabWidget()

        etapas_txt = QTextEdit()
        etapas_txt.setReadOnly(True)
        linhas = []
        for idx, etapa in enumerate(etapas, start=1):
            linhas.append(f"{idx}. {etapa['nome']} | {etapa['status']} | {etapa['percentual_execucao'] or 0}%")
            linhas.append(f"   Inicio: {etapa['data_inicio'] or '-'} | Fim: {etapa['data_fim'] or '-'}")
            linhas.append(f"   Observacao: {etapa['observacao'] or '-'}")
            etapa_itens = [i for i in itens if i["etapa_id"] == etapa["id"]]
            for item in etapa_itens:
                linhas.append(f"   - {item['codigo'] or ''} {item['descricao'] or ''} | {item['unidade'] or ''} | Prev.: {item['quantidade_prevista'] or 0} | Exec.: {item['quantidade_executada'] or 0}")
            linhas.append("")
        etapas_txt.setPlainText("\n".join(linhas) if linhas else "Nenhuma etapa cadastrada.")
        tabs.addTab(etapas_txt, "Etapas e itens")

        tabela_anexos = QTableWidget(0, 5)
        tabela_anexos.setHorizontalHeaderLabels(["Tipo", "Etapa", "Arquivo", "Importa", "Caminho"])
        tabela_anexos.setRowCount(len(anexos))
        for r, anexo in enumerate(anexos):
            vals = [
                anexo["tipo"] or "",
                anexo["etapa_nome"] or "",
                anexo["nome_arquivo"] or "",
                "Sim" if int(anexo["importar_orcamento"] or 0) else "Nao",
                anexo["caminho"] or "",
            ]
            for c, val in enumerate(vals):
                tabela_anexos.setItem(r, c, QTableWidgetItem(str(val)))
        configurar_tabela_responsiva(tabela_anexos, stretch_columns=[4])
        ajustar_tabela_apos_carregar(tabela_anexos)
        tabs.addTab(tabela_anexos, f"Anexos ({len(anexos)})")

        lay.addWidget(tabs, 1)
        botoes = QHBoxLayout()
        btn_abrir = QPushButton("Abrir OS para edicao")
        btn_abrir.clicked.connect(lambda: (dialog.accept(), self.abrir_os(ordem_id)))
        botoes.addWidget(btn_abrir)
        if ordem and ordem["importada_orcamento_id"] and self.abrir_orcamento_callback:
            btn_orc = QPushButton("Abrir orcamento")
            btn_orc.clicked.connect(lambda: (dialog.accept(), self.abrir_orcamento_callback(ordem["importada_orcamento_id"])))
            botoes.addWidget(btn_orc)
        botoes.addStretch()
        btn_fechar = QPushButton("Fechar")
        btn_fechar.clicked.connect(dialog.accept)
        botoes.addWidget(btn_fechar)
        lay.addLayout(botoes)
        dialog.exec()

    def refresh(self):
        self.carregar()
