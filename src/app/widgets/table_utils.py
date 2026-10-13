from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QAbstractItemView, QHeaderView


def configurar_tabela_responsiva(table, stretch_columns=None, hidden_columns=None):
    """Aplica o comportamento padrao das tabelas operacionais do sistema."""
    stretch_columns = set(stretch_columns or [])
    hidden_columns = set(hidden_columns or [])

    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.ElideRight)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)

    header = table.horizontalHeader()
    header.setSectionsMovable(True)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(70)
    header.setDefaultSectionSize(140)
    header.setSectionResizeMode(QHeaderView.ResizeToContents)

    for col in hidden_columns:
        table.setColumnHidden(col, True)
    for col in stretch_columns:
        if 0 <= col < table.columnCount():
            header.setSectionResizeMode(col, QHeaderView.Stretch)

    table.verticalHeader().setVisible(False)

    if not table.property("_tooltip_auto_instalado"):
        table.itemChanged.connect(lambda item: item.setToolTip(item.text()) if item else None)
        table.setProperty("_tooltip_auto_instalado", True)


def ajustar_tabela_apos_carregar(table, max_width=420):
    """Recalcula larguras, limita colunas enormes e cria tooltip com o texto completo."""
    for row in range(table.rowCount()):
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                item.setToolTip(item.text())

    table.resizeColumnsToContents()
    header = table.horizontalHeader()
    for col in range(table.columnCount()):
        if table.isColumnHidden(col) or header.sectionResizeMode(col) == QHeaderView.Stretch:
            continue
        table.setColumnWidth(col, min(max(table.columnWidth(col), 80), max_width))


def ajustar_tabela_depois_do_layout(table):
    QTimer.singleShot(0, lambda: ajustar_tabela_apos_carregar(table))
