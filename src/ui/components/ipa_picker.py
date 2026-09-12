from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QGridLayout, QPushButton, QLabel, QLineEdit, QScrollArea
)
from PySide6.QtCore import Qt, Signal

IPA_CATEGORIES = {
    "Vowels": [
        "i", "y", "ɨ", "ʉ", "ɯ", "u",
        "ɪ", "ʏ", "ʊ",
        "e", "ø", "ɘ", "ɵ", "ɤ", "o",
        "ə", "ɛ", "œ", "ɜ", "ɞ", "ʌ", "ɔ",
        "æ", "ɐ", "a", "ɶ", "ɑ", "ɒ"
    ],
    "Consonants": [
        "p", "b", "t", "d", "ʈ", "ɖ", "c", "ɟ", "k", "ɡ", "q", "ɢ", "ʔ",
        "m", "ɱ", "n", "ɳ", "ɲ", "ŋ", "ɴ",
        "ɸ", "β", "f", "v", "θ", "ð", "s", "z", "ʃ", "ʒ", "ʂ", "ʐ", "ç", "ʝ", "x", "ɣ", "χ", "ʁ", "ħ", "ʕ", "h", "ɦ",
        "ʋ", "ɹ", "ɻ", "j", "ɰ", "l", "ɭ", "ʎ", "ʟ",
        "r", "ɾ", "ɽ", "ʙ", "ʀ", "ɬ", "ɮ"
    ],
    "Special & Clicks": [
        "ʘ", "ǀ", "ǃ", "ǂ", "ǁ",
        "ɓ", "ɗ", "ʄ", "ɠ", "ʛ",
        "t͡s", "t͡ʃ", "d͡z", "d͡ʒ", "k͡p", "ɡ͡b"
    ],
    "Tones & Diacritics": [
        "ˈ", "ˌ", "ː", "ˑ", "˘", ".",
        "˥", "˦", "˧", "˨", "˩", "̂", "̌",
        "̃", "̥", "̬", "ʰ", "ʷ", "ʲ", "ˠ", "ˤ", "ⁿ", "ˡ"
    ]
}

class IPAPickerDialog(QDialog):
    character_selected = Signal(str)

    def __init__(self, target_line_edit: QLineEdit = None, parent=None):
        super().__init__(parent)
        self.target_line_edit = target_line_edit
        self.setWindowTitle("IPA Phonetic Helper")
        self.resize(520, 380)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        header = QLabel("Click any phonetic symbol to insert into reading:")
        header.setStyleSheet("font-weight: bold; font-size: 13px; color: #2c3e50;")
        main_layout.addWidget(header)

        self.tabs = QTabWidget()
        for cat_name, symbols in IPA_CATEGORIES.items():
            self.tabs.addTab(self._create_grid_tab(symbols), cat_name)
        main_layout.addWidget(self.tabs)

        bottom_box = QHBoxLayout()
        btn_close = QPushButton("Done")
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #007acc;
                color: white;
                font-weight: bold;
                padding: 6px 18px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover { background-color: #005999; }
        """)
        btn_close.clicked.connect(self.accept)
        bottom_box.addStretch()
        bottom_box.addWidget(btn_close)
        main_layout.addLayout(bottom_box)

    def _create_grid_tab(self, symbols: list) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(6)

        cols = 8
        for i, sym in enumerate(symbols):
            btn = QPushButton(sym)
            btn.setFixedSize(48, 38)
            btn.setStyleSheet("""
                QPushButton {
                    font-size: 16px;
                    font-family: 'DejaVu Sans', 'Segoe UI', 'Noto Sans', sans-serif;
                    background-color: #ffffff;
                    border: 1px solid #dcdcdc;
                    border-radius: 4px;
                    color: #111111;
                }
                QPushButton:hover {
                    background-color: #e3f2fd;
                    border-color: #2196f3;
                    font-weight: bold;
                }
            """)
            btn.clicked.connect(lambda _, s=sym: self._on_symbol_clicked(s))
            grid.addWidget(btn, i // cols, i % cols)

        container.setLayout(grid)
        scroll.setWidget(container)
        return scroll

    def _on_symbol_clicked(self, symbol: str):
        if self.target_line_edit is not None:
            self.target_line_edit.insert(symbol)
            self.target_line_edit.setFocus()
        self.character_selected.emit(symbol)
