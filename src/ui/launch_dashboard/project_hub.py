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

        # Path to save
        self.selected_db_path = None
        self.project_name = None
        self.is_new_project = False

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 24)

        header_title = QLabel("Language Workspace")
        header_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #111111;")
        header_subtitle = QLabel("Create a new standalone project or open an existing file.")
        header_subtitle.setStyleSheet("color: #666666; font-size: 13px; margin-bottom: 12px;")
        
        main_layout.addWidget(header_title)
        main_layout.addWidget(header_subtitle)

        # New Project Form
        self.stack = QStackedWidget()

        # Start Menu
        menu_widget = QWidget()
        menu_layout = QVBoxLayout(menu_widget)
        menu_layout.setSpacing(12)

        btn_new = QPushButton("+ Create New Language Project")
        btn_new.setStyleSheet("""
            QPushButton {
                background-color: #007acc; color: #ffffff; font-weight: bold;
                font-size: 14px; padding: 12px; border-radius: 6px; border: none;
            }
            QPushButton:hover { background-color: #005999; }
        """)
        btn_new.clicked.connect(lambda: self.stack.setCurrentIndex(1))

        btn_open = QPushButton(" Open Existing Project (.db)")
        btn_open.setStyleSheet("""
            QPushButton {
                background-color: #ffffff; color: #333333; font-weight: bold;
                font-size: 14px; padding: 12px; border-radius: 6px; border: 1px solid #cccccc;
            }
            QPushButton:hover { background-color: #f0f0f0; }
        """)
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
        lbl_name.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.input_name = QLineEdit()
        self.input_name.setPlaceholderText("e.g., Nepal Bhasa, Quenya, Limbu")

        lbl_path = QLabel("Save Location:")
        lbl_path.setStyleSheet("font-weight: bold; font-size: 13px; margin-top: 6px;")
        
        path_layout = QHBoxLayout()
        self.input_path = QLineEdit()
        self.input_path.setReadOnly(True)
        self.input_path.setPlaceholderText("No file location selected...")
        
        btn_browse = QPushButton("Browse...")
        btn_browse.clicked.connect(self._browse_save_location)

        path_layout.addWidget(self.input_path)
        path_layout.addWidget(btn_browse)

        btn_box = QHBoxLayout()
        btn_back = QPushButton("Back")
        btn_back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        
        btn_create = QPushButton("Create Project")
        btn_create.setStyleSheet("background-color: #28a745; color: #ffffff; font-weight: bold; padding: 6px 16px;")
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

    def _browse_save_location(self):
        suggested_name = self.input_name.text().strip().lower().replace(" ", "_") or "untitled_language"
        default_file = f"{suggested_name}.db"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Select Project File Location", default_file, "SQLite Database (*.db)"
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
            QMessageBox.warning(self, "Validation Error", "Please choose a save location for your database file.")
            return

        self.project_name = name
        self.selected_db_path = path
        self.is_new_project = True
        self.accept()

    def _handle_open_existing(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Language Project Database", "", "SQLite Database (*.db)"
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