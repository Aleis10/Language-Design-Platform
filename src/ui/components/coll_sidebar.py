import os
from PySide6.QtWidgets import QFrame, QVBoxLayout, QPushButton
from .coll_buttons import nav_button 

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ICON_DIR = os.path.join(BASE_DIR, "assets", "icons")


def get_icon(name: str) -> str:
    path = os.path.join(ICON_DIR, name)
    return path if os.path.exists(path) else ""


class Sidebar(QFrame):
    def __init__(self, on_page_changed_callback):
        super().__init__()
        self.is_collapsed = False
        self.on_page_changed = on_page_changed_callback
        self.buttons = []

        self.setFixedWidth(200)
        self.setStyleSheet("background-color: #f8f9fa; border-right: 1px solid #e0e0e0;")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 8, 8, 8)
        self.layout.setSpacing(6)

        #Button (Hamburger mennu)
        self.btn_toggle = QPushButton("≡")
        self.btn_toggle.setFixedSize(40, 40)
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                font-size: 20px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                color:black;
            }
            QPushButton:hover { background-color: #e5e5e5; }
        """)
        self.btn_toggle.clicked.connect(self.toggle_sidebar)
        self.layout.addWidget(self.btn_toggle)

        nav_items = [
            (get_icon("overview.svg"), "Dashboard"),
            (get_icon("overview.svg"), "Language Overview"),
            (get_icon("logogram.svg"), "Logograms"),
            (get_icon("keyboard.svg"), "Keyboard"),
            (get_icon("lexicon.svg"), "Lexicon"),
            (get_icon("grammar.svg"), "Grammar"),
            (get_icon("settings.svg"), "Settings")
        ]

        for index, (icon_path, label) in enumerate(nav_items):
            btn = nav_button(icon_path, label)
            btn.clicked.connect(lambda checked, idx=index: self.select_button(idx))
            self.layout.addWidget(btn)
            self.buttons.append(btn)

        self.layout.addStretch()

        if self.buttons:
            self.buttons[0].setChecked(True)

    def select_button(self, selected_idx: int):
        for idx, btn in enumerate(self.buttons):
            btn.setChecked(idx == selected_idx)
        if self.on_page_changed:
            self.on_page_changed(selected_idx)

    def toggle_sidebar(self):
        self.is_collapsed = not self.is_collapsed
        self.setFixedWidth(60 if self.is_collapsed else 200)
        for btn in self.buttons:
            btn.set_collapsed(self.is_collapsed)