import sys
import os
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.launch_dashboard.project_hub import run_project_hub
from ui.frontend_main import MainWindow
from database.db_Manager import Database_Manager
from database.overview_db import LanguageOverviewRepository

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
    
    # Fallback project name from file name if None
    if not project_name:
        project_name = os.path.splitext(os.path.basename(db_path))[0].replace("_", " ").title() or "Untitled Language"

    # Initialize Database Manager
    db_manager = Database_Manager(db_path)
    overview_repo = LanguageOverviewRepository(db_manager)

    # Get or Create main Language Record
    if is_new_project:
        language_id = overview_repo.create_initial_language(project_name)
    else:
        language_id = overview_repo.get_primary_language_id()
        if language_id:
            stored_name = overview_repo.get_language_name(language_id)
            if stored_name:
                project_name = stored_name
        else:
            language_id = overview_repo.create_initial_language(project_name)

    # Launch Main Window
    window = MainWindow(
        db_manager=db_manager,
        overview_repo=overview_repo,
        language_id=language_id,
        db_path=db_path,
        project_name=project_name
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()