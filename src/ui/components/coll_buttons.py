from PySide6.QtWidgets import QPushButton
from PySide6.QtGui import QIcon
from PySide6.QtCore import QSize

class nav_button(QPushButton):
    
    def __init__(self,icon_path:str,text:str):
        super().__init__()

        self.full_text = text

        self.setIcon(QIcon(icon_path))
        self.setIconSize(QSize(24, 24))

        self.setFlat(True)
        self.setCheckable(True)
        self.set_collapsed(False)

        self.setStyleSheet("""
            QPushButton {
                text-align: left;
                padding: 10px 14px;
                font-size: 14px;
                border: none;
                border-radius: 6px;
                color: #333333;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
            }
            QPushButton:checked {
                background-color: #007acc;
                color: white;
                font-weight: bold;
            }
        """)

    def set_collapsed(self,collapsed:bool):
        if collapsed:
            self.setText("")
            self.setToolTip(self.full_text)
        else:
            self.setText(f"{self.full_text}")
            self.setToolTip("")
