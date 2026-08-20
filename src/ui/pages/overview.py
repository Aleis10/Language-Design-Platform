from PySide6.QtWidgets import (
    QWidget,QTextEdit,QComboBox,QLineEdit,QVBoxLayout,QHBoxLayout,QFrame,QPushButton,
    QLabel,QScrollArea,QFormLayout,QMessageBox,QDialog,QListWidget,QListWidgetItem
)
from PySide6.QtCore import Qt

class overview_page(QWidget):
    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0,0,0,0)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("OverviewScrollArea")
        scroll_area.setWidgetResizable(True)

        self.content_widget = QWidget()
        self.cards_layout = QVBoxLayout(self.content_widget)
        self.cards_layout.setContentsMargins(24, 20, 24, 24)
        self.cards_layout.setSpacing(16)

        #Top Bar
        top_bar = QHBoxLayout()

        status_label = QLabel("Project Status:")
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("StatusCombo")
        self.status_combo.setEditable(True)
        self.status_combo.addItems(["Drafting", "Active / In Development", "Stable / Complete", "Archived"])

        self.btn_add_section = QPushButton("+ Add Custom Section")
        self.btn_add_section.setObjectName("BtnAddSection")
        self.btn_add_section.clicked.connect(self.prompt_add_section)

        top_bar.addWidget(status_label)
        top_bar.addWidget(self.status_combo)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_add_section)
        self.cards_layout.addLayout(top_bar)

        #SECTION 1: Language Details
        details_card = QFrame()
        details_card.setProperty("class", "overview-card")
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(16, 16, 16, 16)

        sec1_title = QLabel("[icon:details] Language Details")
        sec1_title.setProperty("class", "section-title")
        details_layout.addWidget(sec1_title)
