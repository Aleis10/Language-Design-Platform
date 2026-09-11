import sys
import os
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.launch_dashboard.project_hub import run_project_hub
from ui.frontend_main import MainWindow
from database.db_Manager import Database_Manager
from database.overview_db import LanguageOverviewRepository
from database.glyph_db import GlyphRepository
from database.lexicon_db import LexiconRepository
from database.keyboard_db import KeyboardRepository
from database.grammar_db import GrammarRepository
from database.archive_manager import ProjectArchiveManager


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

    # Launch project dashboard / hub
    hub_result = run_project_hub()
    if not hub_result:
        sys.exit(0)

    archive_or_db_path, project_name, is_new_project = hub_result
    
    if not project_name:
        project_name = os.path.splitext(os.path.basename(archive_or_db_path))[0].replace("_", " ").title() or "Untitled Language"

    # Route between .langarc/.zip archive packages and legacy .db files
    if archive_or_db_path.endswith(".langarc") or archive_or_db_path.endswith(".zip"):
        archive_path = archive_or_db_path
        if is_new_project:
            session_dir, db_path = ProjectArchiveManager.create_new_archive(archive_path, project_name)
            db_manager = Database_Manager(db_path)
            overview_repo = LanguageOverviewRepository(db_manager)
            glyph_repo = GlyphRepository(db_manager)
            lexicon_repo = LexiconRepository(db_manager)
            keyboard_repo = KeyboardRepository(db_manager)
            grammar_repo = GrammarRepository(db_manager)
            language_id = overview_repo.create_initial_language(project_name)
            # Create initial packaged .langarc
            ProjectArchiveManager.save_archive(session_dir, archive_path, project_name)
        else:
            session_dir, db_path, stored_name = ProjectArchiveManager.open_archive(archive_path)
            if stored_name:
                project_name = stored_name
            db_manager = Database_Manager(db_path)
            overview_repo = LanguageOverviewRepository(db_manager)
            glyph_repo = GlyphRepository(db_manager)
            lexicon_repo = LexiconRepository(db_manager)
            keyboard_repo = KeyboardRepository(db_manager)
            grammar_repo = GrammarRepository(db_manager)
            language_id = overview_repo.get_primary_language_id()
            if not language_id:
                language_id = overview_repo.create_initial_language(project_name)
    else:
        # Direct raw .db file fallback
        archive_path = None
        db_path = archive_or_db_path
        session_dir = os.path.dirname(db_path)
        db_manager = Database_Manager(db_path)
        overview_repo = LanguageOverviewRepository(db_manager)
        glyph_repo = GlyphRepository(db_manager)
        lexicon_repo = LexiconRepository(db_manager)
        keyboard_repo = KeyboardRepository(db_manager)
        grammar_repo = GrammarRepository(db_manager)

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
        glyph_repo=glyph_repo,
        lexicon_repo=lexicon_repo,
        keyboard_repo=keyboard_repo,
        grammar_repo=grammar_repo,
        language_id=language_id,
        db_path=db_path,
        project_name=project_name,
        archive_path=archive_path,
        session_dir=session_dir,
        archive_manager=ProjectArchiveManager
    )
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()