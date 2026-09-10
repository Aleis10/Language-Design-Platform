import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QFileDialog, QMessageBox, QStackedWidget, QWidget
)
from PySide6.QtCore import Qt


class ProjectHub(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Language Project Workspace")
        self.setFixedSize(500, 380)
        self.setModal(True)

        self.setObjectName("ProjectHubDialog")

        # Path to save
        self.selected_db_path = None
        self.project_name = None
        self.is_new_project = False

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)

        header_title = QLabel("Language Workspace")
        header_title.setObjectName("HubHeaderTitle")
        header_subtitle = QLabel("Create a new standalone project or open an existing file.")
        header_subtitle.setObjectName("HubHeaderSubtitle")
        
        main_layout.addWidget(header_title)
        main_layout.addWidget(header_subtitle)

        # New Project Form
        self.stack = QStackedWidget()

        # Start Menu
        menu_widget = QWidget()
        menu_layout = QVBoxLayout(menu_widget)
        menu_layout.setSpacing(12)

        btn_new = QPushButton("+ Create New Language Project")
        btn_new.setObjectName("BtnNewProject")
        btn_new.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        btn_open = QPushButton(" Open Existing Project (.langarc / .db)")
        btn_open.setObjectName("BtnOpenProject")
        btn_open.clicked.connect(self._handle_open_existing)

        menu_layout.addStretch()
        menu_layout.addWidget(btn_new)
        menu_layout.addWidget(btn_open)
        menu_layout.addStretch()

        # New project layout
        form_widget = QWidget()
        form_layout = QVBoxLayout(form_widget)
        form_layout.setSpacing(8)

        lbl_name = QLabel("Language / Project Name:")
        lbl_name.setObjectName("LblProjectName")
        self.input_name = QLineEdit()
        self.input_name.setObjectName("InputProjectName")
        self.input_name.setPlaceholderText("e.g., Nepal Bhasa, Quenya, Limbu")

        lbl_path = QLabel("Save Location:")
        lbl_path.setObjectName("LblSaveLocation")
        
        path_layout = QHBoxLayout()
        self.input_path = QLineEdit()
        self.input_path.setObjectName("InputProjectPath")
        self.input_path.setReadOnly(True)
        self.input_path.setPlaceholderText("No file location selected...")
        
        btn_browse = QPushButton("Browse...")
        btn_browse.setObjectName("BtnBrowseLocation")
        btn_browse.clicked.connect(self._browse_save_location)

        path_layout.addWidget(self.input_path)
        path_layout.addWidget(btn_browse)

        btn_box = QHBoxLayout()
        btn_back = QPushButton("Back")
        btn_back.setObjectName("BtnBack")
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        
        btn_create = QPushButton("Create Project")
        btn_create.setObjectName("BtnCreateProject")
        btn_create.clicked.connect(self._handle_create_project)

        btn_box.addWidget(btn_back)
        btn_box.addStretch()
        btn_box.addWidget(btn_create)

        form_layout.addWidget(lbl_name)
        form_layout.addWidget(self.input_name)
        form_layout.addWidget(lbl_path)
        form_layout.addLayout(path_layout)
        form_layout.addSpacing(16)
        form_layout.addLayout(btn_box)

        # Add both views to stack
        self.stack.addWidget(menu_widget)
        self.stack.addWidget(form_widget)

        main_layout.addWidget(self.stack)

        # Load QSS Stylesheet
        self._load_stylesheet()

    def _load_stylesheet(self):
        style_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "project_hub.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _browse_save_location(self):
        suggested_name = self.input_name.text().strip().lower().replace(" ", "_") or "untitled_language"
        default_file = f"{suggested_name}.langarc"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Select Project Archive Location", default_file, "Language Archive (*.langarc);;Zip Archive (*.zip);;SQLite Database (*.db)"
        )
        if file_path:
            self.input_path.setText(file_path)

    def _handle_create_project(self):
        name = self.input_name.text().strip()
        path = self.input_path.text().strip()

        if not name:
            QMessageBox.warning(self, "Validation Error", "Please enter a Language or Project Name.")
            return
        if not path:
            QMessageBox.warning(self, "Validation Error", "Please choose a save location for your project archive.")
            return

        self.project_name = name
        self.selected_db_path = path
        self.is_new_project = True
        self.accept()

    def _handle_open_existing(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Language Project Archive", "", "Language Archive (*.langarc *.zip);;SQLite Database (*.db);;All Files (*)"
        )
        if file_path:
            self.selected_db_path = file_path
            self.project_name = os.path.splitext(os.path.basename(file_path))[0].replace("_", " ").title()
            self.is_new_project = False
            self.accept()

#Launches Project hub
def run_project_hub():
    dialog = ProjectHub()
    if dialog.exec() == QDialog.Accepted and dialog.selected_db_path:
        return dialog.selected_db_path, dialog.project_name, dialog.is_new_project
    return None