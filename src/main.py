import sys
import os
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.launch_dashboard.project_hub import run_project_hub
from ui.frontend_main import MainWindow
from database.db_Manager import Database_Manager


def load_stylesheet(app: QApplication, filepath: str) -> None:
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())


def main():
    app = QApplication(sys.argv)

    # QSS Stylesheet
    base_dir = os.path.dirname(os.path.abspath(__file__))
    qss_path = os.path.join(base_dir, "ui", "pages", "style", "overview_page.qss")
    load_stylesheet(app, qss_path)

    # Launch project dahbopard 
    hub_result = run_project_hub()
    if not hub_result:
        sys.exit(0)

    db_path, project_name, is_new_project = hub_result

    # creates .db file
    db_manager = Database_Manager(db_path)

    # Launch Main Window
    window = MainWindow(
        db_manager=db_manager,
        db_path=db_path,
        project_name=project_name
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()