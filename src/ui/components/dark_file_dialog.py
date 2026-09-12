import os
from typing import Optional

from PySide6.QtCore import QFileInfo, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFileIconProvider,   # PySide6 6.11: QtWidgets, NOT QtGui
    QFileSystemModel,
)


class WhiteFileIconProvider(QFileIconProvider):
    """Renders every file/folder icon as a white silhouette."""

    def __init__(self):
        super().__init__()
        self._base = QFileIconProvider()
        self._cache = {}

    def icon(self, arg):
        base_icon = self._base.icon(arg)  # accepts QFileInfo or IconType
        key = base_icon.cacheKey()
        if key in self._cache:
            return self._cache[key]
        white = self._whiten(base_icon)
        self._cache[key] = white
        return white

    def _whiten(self, icon: QIcon) -> QIcon:
        px = QPixmap(64, 64)
        px.fill(QColor(0, 0, 0, 0))  # transparent
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        icon.paint(painter, 0, 0, 64, 64)
        # Keep alpha, force RGB to white
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceIn
        )
        painter.fillRect(px.rect(), QColor("#ffffff"))
        painter.end()
        return QIcon(px)


DARK_QSS = """
QFileDialog {
    background-color: #1e1e1e;
    color: #ffffff;
}
QFileDialog QLabel, QFileDialog QComboBox { color: #ffffff; }
QFileDialog QLineEdit {
    background-color: #121212; color: #ffffff;
    border: 1px solid #444444; border-radius: 4px; padding: 4px 8px;
    selection-background-color: #005999; selection-color: #ffffff;
}
QFileDialog QTreeView, QFileDialog QListView, QFileDialog QTableView {
    background-color: #1a1a1a; color: #ffffff;
    alternate-background-color: #1e1e1e;
    selection-background-color: #005999; selection-color: #ffffff;
    border: 1px solid #333333; border-radius: 4px;
}
QFileDialog QTreeView::item, QFileDialog QListView::item, QFileDialog QTableView::item {
    color: #ffffff;
}
QFileDialog QTreeView::item:hover, QFileDialog QListView::item:hover, QFileDialog QTableView::item:hover {
    background-color: #2a2a2a;
}
QFileDialog QHeaderView::section {
    background-color: #242424; color: #ffffff;
    border: none; border-bottom: 1px solid #333333;
    padding: 4px 8px; font-weight: bold;
}
QFileDialog QComboBox {
    background-color: #2a2a2a; color: #ffffff;
    border: 1px solid #444444; border-radius: 4px; padding: 4px 8px;
}
QFileDialog QComboBox QAbstractItemView {
    background-color: #2a2a2a; color: #ffffff;
    border: 1px solid #444444;
    selection-background-color: #005999; selection-color: #ffffff;
}
QFileDialog QPushButton {
    background-color: #2a2a2a; color: #ffffff;
    border: 1px solid #444444; border-radius: 4px; padding: 5px 12px;
}
QFileDialog QPushButton:hover { background-color: #3a3a3a; border-color: #666666; }
QFileDialog QPushButton:default {
    background-color: #007acc; border: 1px solid #007acc; font-weight: bold;
}
QFileDialog QToolBar { background-color: #1e1e1e; border: none; spacing: 6px; }
QFileDialog QToolButton {
    background-color: transparent; color: #ffffff;
    border: none; border-radius: 4px; padding: 4px;
}
QFileDialog QToolButton:hover { background-color: #333333; }
QFileDialog QStatusBar { background-color: #1e1e1e; color: #bbbbbb; }
QFileDialog QScrollBar:vertical {
    background: #1a1a1a; width: 10px; margin: 0;
}
QFileDialog QScrollBar::handle:vertical {
    background: #444444; border-radius: 5px; min-height: 24px;
}
QFileDialog QScrollBar:horizontal {
    background: #1a1a1a; height: 10px; margin: 0;
}
QFileDialog QScrollBar::handle:horizontal {
    background: #444444; border-radius: 5px; min-width: 24px;
}
QFileDialog QScrollBar::add-line, QFileDialog QScrollBar::sub-line {
    width: 0; height: 0;
}
"""


def apply_dark_palette(dialog: QFileDialog) -> None:
    """Dark palette so style-drawn chrome (toolbar icons, disabled text) renders light."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
    pal.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Base, QColor("#121212"))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#1a1a1a"))
    pal.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Button, QColor("#2a2a2a"))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#005999"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2a2a2a"))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#888888"))
    pal.setColor(QPalette.ColorRole.Link, QColor("#4da3ff"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#777777"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#777777"))
    dialog.setPalette(pal)


def open_dark_dialog(
    parent,
    caption: str,
    directory: str = "",
    filters: str = "All Files (*)",
    save_mode: bool = False,
) -> str:
    """Black file dialog (white text + white icons). Returns path, or '' on cancel."""
    dlg = QFileDialog(parent, caption, directory or "", filters)
    dlg.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dlg.setAcceptMode(
        QFileDialog.AcceptMode.AcceptSave if save_mode else QFileDialog.AcceptMode.AcceptOpen
    )
    apply_dark_palette(dlg)
    dlg.setStyleSheet(DARK_QSS)
    model = dlg.findChild(QFileSystemModel)
    if model is not None:
        try:
            model.setIconProvider(WhiteFileIconProvider())  # MUST be before exec()
        except Exception as e:
            print(f"[dark_file_dialog] icon provider note: {e}")
    if dlg.exec() != QFileDialog.DialogCode.Accepted:
        return ""
    paths = dlg.selectedFiles()
    return paths[0] if paths else ""