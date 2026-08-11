from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QLabel
from PySide6.QtCore import Qt   
from .components.coll_sidebar import Sidebar

class MainWindow(QMainWindow): # Changed to CamelCase
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Lexicography & Language Software")
        self.resize(1400, 950)

        # Main Layout Container
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Stacked Pages
        self.pages = QStackedWidget()
        self.pages.addWidget(QLabel("Overview Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Lexicon Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Grammar Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Logograms Canvas Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Settings Page", alignment=Qt.AlignmentFlag.AlignCenter))

        # Add Sidebar
        self.sidebar = Sidebar(on_page_changed_callback=self.pages.setCurrentIndex)

        # Assemble
        main_layout.addWidget(self.sidebar, stretch=0)
        main_layout.addWidget(self.pages, stretch=1)

        self.setCentralWidget(central_widget)