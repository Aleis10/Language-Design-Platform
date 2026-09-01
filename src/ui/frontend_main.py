from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QLabel
from PySide6.QtCore import Qt   
from .components.coll_sidebar import Sidebar
from .pages.overview import Overview_Page


class MainWindow(QMainWindow): 
    def __init__(self, db_manager=None, db_path=None, project_name=None, parent=None):
        super().__init__(parent)

        self.db_manager = db_manager
        self.db_path = db_path
        self.project_name = project_name

        title_suffix = f" - {project_name}" if project_name else ""
        self.setWindowTitle(f"Lexicography & Language Software{title_suffix}")
        self.resize(1400, 950)

        # Main Front Layout
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Pages 
        self.pages = QStackedWidget()
        self.pages.addWidget(QLabel("Dashboard", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(Overview_Page())
        self.pages.addWidget(QLabel("Logograms Canvas Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Keyboard", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Lexicon Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Grammar Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Settings Page", alignment=Qt.AlignmentFlag.AlignCenter))

        # Add Sidebar
        self.sidebar = Sidebar(on_page_changed_callback=self.pages.setCurrentIndex)

        # Assemble
        main_layout.addWidget(self.sidebar, stretch=0)
        main_layout.addWidget(self.pages, stretch=1)

        self.setCentralWidget(central_widget)