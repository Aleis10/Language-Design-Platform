import os
import sys
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QLabel,
    QMessageBox, QFileDialog
)
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtCore import Qt
from .components.coll_sidebar import Sidebar
from .pages.overview import Overview_Page
from .pages.glyphs_page import Glyphs_Page
from .pages.lexicon_page import LexiconPage
from .pages.keyboard_page import KeyboardPage

try:
    from database.glyph_db import GlyphRepository
    from database.lexicon_db import LexiconRepository
    from database.keyboard_db import KeyboardRepository
    from database.archive_manager import ProjectArchiveManager
except (ImportError, ValueError):
    from ..database.glyph_db import GlyphRepository
    from ..database.lexicon_db import LexiconRepository
    from ..database.keyboard_db import KeyboardRepository
    from ..database.archive_manager import ProjectArchiveManager


class MainWindow(QMainWindow):
    def __init__(
        self,
        db_manager=None,
        overview_repo=None,
        glyph_repo=None,
        lexicon_repo=None,
        keyboard_repo=None,
        language_id=None,
        db_path=None,
        project_name=None,
        archive_path=None,
        session_dir=None,
        archive_manager=None,
        parent=None
    ):
        super().__init__(parent)

        self.db_manager = db_manager
        self.overview_repo = overview_repo
        self.glyph_repo = glyph_repo or (GlyphRepository(self.db_manager) if self.db_manager else None)
        self.lexicon_repo = lexicon_repo or (LexiconRepository(self.db_manager) if self.db_manager else None)
        self.keyboard_repo = keyboard_repo or (KeyboardRepository(self.db_manager) if self.db_manager else None)
        self.language_id = language_id
        self.db_path = db_path
        self.project_name = project_name
        self.archive_path = archive_path
        self.session_dir = session_dir
        self.archive_manager = archive_manager or ProjectArchiveManager

        self._update_window_title()
        self.resize(1400, 950)

        # 1. Top Desktop File Menu Bar
        self._setup_menu_bar()

        # 2. Main Front Layout
        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 3. Stacked Pages
        self.overview_page = Overview_Page(
            overview_repo=self.overview_repo,
            language_id=self.language_id,
        )
        self.glyphs_page = Glyphs_Page(
            glyph_repo=self.glyph_repo,
            language_id=self.language_id,
            db_path=self.db_path,
            session_dir=self.session_dir,
        )
        self.lexicon_page = LexiconPage(
            lexicon_repo=self.lexicon_repo,
            language_id=self.language_id,
            session_dir=self.session_dir,
        )
        self.keyboard_page = KeyboardPage(
            keyboard_repo=self.keyboard_repo,
            glyph_repo=self.glyph_repo,
            language_id=self.language_id,
        )

        self.pages = QStackedWidget()
        self.pages.addWidget(QLabel("Dashboard", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(self.overview_page)
        self.pages.addWidget(self.glyphs_page)
        self.pages.addWidget(self.keyboard_page)
        self.pages.addWidget(self.lexicon_page)
        self.pages.addWidget(QLabel("Grammar Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Settings Page", alignment=Qt.AlignmentFlag.AlignCenter))

        # Sidebar
        self.sidebar = Sidebar(on_page_changed_callback=self.pages.setCurrentIndex)

        # Assemble
        main_layout.addWidget(self.sidebar, stretch=0)
        main_layout.addWidget(self.pages, stretch=1)

        self.setCentralWidget(central_widget)

    def _update_window_title(self):
        title_suffix = f" - {self.project_name}" if self.project_name else ""
        arc_suffix = f" [{os.path.basename(self.archive_path)}]" if self.archive_path else ""
        self.setWindowTitle(f"Lexicography & Language Software{title_suffix}{arc_suffix}")

    def _setup_menu_bar(self):
        self.menu_bar = self.menuBar()
        file_menu = self.menu_bar.addMenu("File")

        action_new = QAction("New Language Project...", self)
        action_new.setShortcut(QKeySequence("Ctrl+N"))
        action_new.triggered.connect(self.action_new_project)

        action_open = QAction("Open Archive...", self)
        action_open.setShortcut(QKeySequence("Ctrl+O"))
        action_open.triggered.connect(self.action_open_project)

        action_save = QAction("Save Archive", self)
        action_save.setShortcut(QKeySequence("Ctrl+S"))
        action_save.triggered.connect(lambda: self.action_save_project(notify=True))

        action_save_as = QAction("Save Copy As...", self)
        action_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        action_save_as.triggered.connect(self.action_save_as)

        file_menu.addAction(action_new)
        file_menu.addAction(action_open)
        file_menu.addSeparator()
        file_menu.addAction(action_save)
        file_menu.addAction(action_save_as)
        file_menu.addSeparator()
        action_exit = QAction("Exit", self)
        action_exit.setShortcut(QKeySequence("Ctrl+Q"))
        action_exit.triggered.connect(self.close)
        file_menu.addAction(action_exit)

    def action_save_project(self, notify: bool = False):
        """Flushes active page edits and packs the working session into the .langarc archive."""
        # 1. Commit active page edits
        if hasattr(self, "overview_page") and hasattr(self.overview_page, "save_data"):
            self.overview_page.save_data()
        if hasattr(self, "glyphs_page") and hasattr(self.glyphs_page, "save_active_glyph"):
            self.glyphs_page.save_active_glyph(notify=False)

        # 2. Pack session into .langarc
        if self.archive_path and self.session_dir and self.archive_manager:
            try:
                self.archive_manager.save_archive(
                    self.session_dir, self.archive_path, self.project_name
                )
                if notify:
                    QMessageBox.information(self, "Saved", "Project saved to archive.")
            except Exception as e:
                if notify:
                    QMessageBox.critical(self, "Save Error", f"Failed to save project:\n{e}")
        elif self.db_path:
            if notify:
                QMessageBox.information(self, "Saved", "Database changes saved.")

    def action_save_as(self):
        """Packs a copy of the current project to a new .langarc destination."""
        clean_name = self.project_name.lower().replace(" ", "_") if self.project_name else "language"
        default_file = f"{clean_name}.langarc"
        dialog = QFileDialog(self, "Save Copy As", default_file, "Language Archive (*.langarc);;Zip Archive (*.zip);;All Files (*)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setStyleSheet("QFileDialog { background: #fafafa; } QWidget { color: #222; }")
        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            new_path = dialog.selectedFiles()[0]
            try:
                self.archive_manager.save_archive(
                    self.session_dir, new_path, self.project_name
                )
                self.archive_path = new_path
                self._update_window_title()
                QMessageBox.information(self, "Saved", f"Copy saved to:\n{new_path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"Failed to save copy:\n{e}")

    def action_new_project(self):
        """Prompt to create a new project and restart application context."""
        reply = QMessageBox.question(
            self, "New Project",
            "Do you want to save current changes and open the Project Hub to create a new language?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.action_save_project(notify=False)
            try:
                from ui.launch_dashboard.project_hub import run_project_hub
                hub_result = run_project_hub()
                if hub_result:
                    self._reload_project(*hub_result)
            except ImportError:
                from .launch_dashboard.project_hub import run_project_hub
                hub_result = run_project_hub()
                if hub_result:
                    self._reload_project(*hub_result)

    def action_open_project(self):
        """Open an existing .langarc, .zip, or .db project archive."""
        dialog = QFileDialog(self, "Open Language Archive", "",
            "Language Archive (*.langarc *.zip);;SQLite Database (*.db);;All Files (*)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setStyleSheet("QFileDialog { background: #fafafa; } QWidget { color: #222; }")
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return
        file_path = dialog.selectedFiles()[0]
        if not file_path:
            return

        reply = QMessageBox.question(
            self, "Open Project",
            "Do you want to save current changes before opening?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        if reply == QMessageBox.Cancel:
            return
        if reply == QMessageBox.Yes:
            self.action_save_project(notify=False)

        project_name = os.path.splitext(os.path.basename(file_path))[0].replace("_", " ").title()
        self._reload_project(file_path, project_name, False)

    def _reload_project(self, archive_or_db_path, project_name, is_new_project):
        """Tears down current session and boots a new project context."""
        try:
            from database.db_Manager import Database_Manager
            from database.overview_db import LanguageOverviewRepository
        except ImportError:
            from ..database.db_Manager import Database_Manager
            from ..database.overview_db import LanguageOverviewRepository

        if not project_name:
            project_name = (
                os.path.splitext(os.path.basename(archive_or_db_path))[0]
                .replace("_", " ").title() or "Untitled Language"
            )

        if archive_or_db_path.endswith(".langarc") or archive_or_db_path.endswith(".zip"):
            self.archive_path = archive_or_db_path
            if is_new_project:
                session_dir, db_path = self.archive_manager.create_new_archive(
                    archive_or_db_path, project_name
                )
                self.db_manager = Database_Manager(db_path)
                self.overview_repo = LanguageOverviewRepository(self.db_manager)
                self.glyph_repo = GlyphRepository(self.db_manager)
                self.lexicon_repo = LexiconRepository(self.db_manager)
                self.keyboard_repo = KeyboardRepository(self.db_manager)
                self.language_id = self.overview_repo.create_initial_language(project_name)
                self.session_dir = session_dir
                self.archive_manager.save_archive(session_dir, archive_or_db_path, project_name)
            else:
                session_dir, db_path, stored_name = self.archive_manager.open_archive(archive_or_db_path)
                if stored_name:
                    project_name = stored_name
                self.session_dir = session_dir
                self.db_manager = Database_Manager(db_path)
                self.overview_repo = LanguageOverviewRepository(self.db_manager)
                self.glyph_repo = GlyphRepository(self.db_manager)
                self.lexicon_repo = LexiconRepository(self.db_manager)
                self.keyboard_repo = KeyboardRepository(self.db_manager)
                self.language_id = self.overview_repo.get_primary_language_id()
                if not self.language_id:
                    self.language_id = self.overview_repo.create_initial_language(project_name)
        else:
            self.archive_path = None
            self.db_path = archive_or_db_path
            self.session_dir = os.path.dirname(self.db_path)
            self.db_manager = Database_Manager(self.db_path)
            self.overview_repo = LanguageOverviewRepository(self.db_manager)
            self.glyph_repo = GlyphRepository(self.db_manager)
            self.lexicon_repo = LexiconRepository(self.db_manager)
            self.keyboard_repo = KeyboardRepository(self.db_manager)
            if is_new_project:
                self.language_id = self.overview_repo.create_initial_language(project_name)
            else:
                self.language_id = self.overview_repo.get_primary_language_id()
                if not self.language_id:
                    self.language_id = self.overview_repo.create_initial_language(project_name)

        self.project_name = project_name
        self.db_path = db_path if "db_path" in locals() else archive_or_db_path
        self._update_window_title()
        self._rebuild_pages()

    def _rebuild_pages(self):
        """Rebuild the stacked pages against freshly loaded repositories."""
        layout = self.pages if getattr(self, "pages", None) else None
        while self.pages.count():
            self.pages.removeWidget(self.pages.widget(0))
        self.overview_page = Overview_Page(
            overview_repo=self.overview_repo, language_id=self.language_id
        )
        self.glyphs_page = Glyphs_Page(
            glyph_repo=self.glyph_repo,
            language_id=self.language_id,
            db_path=self.db_path,
            session_dir=self.session_dir,
        )
        self.lexicon_page = LexiconPage(
            lexicon_repo=self.lexicon_repo,
            language_id=self.language_id,
            session_dir=self.session_dir,
        )
        self.keyboard_page = KeyboardPage(
            keyboard_repo=self.keyboard_repo,
            glyph_repo=self.glyph_repo,
            language_id=self.language_id,
        )
        self.pages.addWidget(QLabel("Dashboard", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(self.overview_page)
        self.pages.addWidget(self.glyphs_page)
        self.pages.addWidget(self.keyboard_page)
        self.pages.addWidget(self.lexicon_page)
        self.pages.addWidget(QLabel("Grammar Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.pages.addWidget(QLabel("Settings Page", alignment=Qt.AlignmentFlag.AlignCenter))
        self.statusBar().showMessage(f"Loaded: {self.project_name}", 4000)

    def closeEvent(self, event):
        """Auto-save changes into .langarc archive upon exiting."""
        if self.archive_path and self.session_dir and self.archive_manager:
            try:
                self.archive_manager.save_archive(
                    self.session_dir, self.archive_path, self.project_name
                )
            except Exception:
                pass
        super().closeEvent(event)