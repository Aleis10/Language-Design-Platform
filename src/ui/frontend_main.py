from PySide6.QtWidgets import QMainWindow,QLabel
from PySide6.QtCore import Qt   

class main_window(QMainWindow):
    def __init__ (self):
        super().__init__()

        self.setWindowTitle("Lexicography & Language Software")
        self.resize(1400,950)


