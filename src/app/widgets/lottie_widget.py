from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout


class LottieWidget(QFrame):
    def __init__(self, json_path, parent=None, framed=True):
        super().__init__(parent)
        self.json_path = Path(json_path)
        self.setObjectName("LottieWidget")
        if framed:
            self.setStyleSheet("""
                QFrame#LottieWidget {
                    background:rgba(255,255,255,0.92);
                    border:1px solid rgba(215,226,239,0.95);
                    border-radius:18px;
                }
            """)
            margins = (8, 8, 8, 8)
        else:
            self.setStyleSheet("""
                QFrame#LottieWidget {
                    background:transparent;
                    border:none;
                }
            """)
            margins = (0, 0, 0, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(*margins)
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView

            web = QWebEngineView(self)
            web.setContextMenuPolicy(Qt.NoContextMenu)
            web.page().setBackgroundColor(QColor(0, 0, 0, 0))
            web.setAttribute(Qt.WA_TranslucentBackground, True)
            web.setStyleSheet("background:transparent;border:none;")
            web.setHtml(self._html(), QUrl.fromLocalFile(str(self.json_path.parent)))
            layout.addWidget(web)
            self.web = web
        except Exception:
            fallback = QLabel("Animação indisponível")
            fallback.setStyleSheet("color:#64748B;font-weight:700;")
            fallback.setMinimumHeight(180)
            fallback.setContentsMargins(16, 16, 16, 16)
            layout.addWidget(fallback)

    def _html(self):
        vendor = Path(__file__).resolve().parents[1] / "assets" / "vendor" / "lottie.min.js"
        data = self.json_path.read_text(encoding="utf-8")
        js_src = vendor.as_uri()
        return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
html, body {{
    margin:0;
    width:100%;
    height:100%;
    overflow:hidden;
    background:transparent;
}}
#anim {{
    width:100%;
    height:100%;
}}
</style>
</head>
<body>
<div id="anim"></div>
<script src="{js_src}"></script>
<script>
const animationData = {data};
lottie.loadAnimation({{
  container: document.getElementById('anim'),
  renderer: 'svg',
  loop: true,
  autoplay: true,
  animationData
}});
</script>
</body>
</html>"""
