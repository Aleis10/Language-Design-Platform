from PySide6.QtWidgets import QPushButton

#collapsable button
class nav_button(QPushButton):
    
    def __init__(self,icon_str:str,text:str):
        super.__init__()

        self.icon_str = icon_str
        self.Full_text = text

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
        if collapsed():
            self.setText(self.Full_text)
            self.setToolTip(self.Full_texttext)
        else:
            self.setText(f"{self.icon_str} {self.Full_text}")
            self.setToolTip("")