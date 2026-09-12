import os
import sys
from typing import Dict, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QLabel,
    QMessageBox, QFileDialog, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
    QApplication,
)
from PySide6.QtGui import QAction, QKeySequence, QFont, QShortcut, QKeyEvent
from PySide6.QtCore import Qt, QEvent, QObject, Signal, QTimer
from .components.coll_sidebar import Sidebar
from .components.floating_keyboard import FloatingKeyboardButton
from .components.on_screen_keyboard import OnScreenKeyboard
from .pages.overview import Overview_Page
from .pages.glyphs_page import Glyphs_Page
from .pages.lexicon_page import LexiconPage
from .pages.keyboard_page import KeyboardPage
from .pages.grammar_page import GrammarPage

try:
    from database.glyph_db import GlyphRepository
    from database.lexicon_db import LexiconRepository
    from database.keyboard_db import KeyboardRepository
    from database.grammar_db import GrammarRepository
    from database.archive_manager import ProjectArchiveManager
except (ImportError, ValueError):
    from ..database.glyph_db import GlyphRepository
    from ..database.lexicon_db import LexiconRepository
    from ..database.keyboard_db import KeyboardRepository
    from ..database.grammar_db import GrammarRepository
    from ..database.archive_manager import ProjectArchiveManager

class _ConlangFontFilter(QObject):

    def __init__(self, data_dir: str = "", parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        self._family = None
        self._registered = False
        self._queued = set() 

    def refresh_family(self):
        if self._registered:
            return self._family
        self._registered = True
        self._family = None
        if not self.data_dir:
            return None
        try:
            from font_tools.font_registry import register_language_font
            self._family = register_language_font(self.data_dir)
        except Exception:
            self._family = None
        return self._family

    def eventFilter(self, obj, event):
 
        if event.type() in (QEvent.Type.Polish, QEvent.Type.ChildAdded):
            self._defer_apply(obj)
        return super().eventFilter(obj, event)

    def _defer_apply(self, w):
        if not isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox)):
            return
        if id(w) in self._queued:
            return
        self._queued.add(id(w))
        QTimer.singleShot(0, lambda: self._apply_to(w))

    def _apply_to(self, w):
        if not isinstance(w, (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox)):
            return
        family = self.refresh_family()
        if not family:
            return
        try:
            cur = w.font().family()
            if cur == family:
                return  
            w.setFont(QFont(family, w.font().pointSize() or 12))
        except Exception:
            pass

class _ConlangModeController(QObject):

    mode_changed = Signal(bool)
    key_pressed = Signal(str)  

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active = False
        self.key_to_glyph: Dict[str, Dict] = {} 

    @property
    def active(self) -> bool:
        return self._active

    def set_active(self, on: bool):
        if on != self._active:
            self._active = on
            self.mode_changed.emit(on)

    def set_mappings(self, mappings: Dict[str, Dict]):
        self.key_to_glyph = mappings

    def glyph_for_key(self, key_code: str) -> Optional[str]:

        m = self.key_to_glyph.get(key_code)
        if not m:
            return None
        char = m.get("char")
        if char:
            return char
        ppua = m.get("ppua") or ""
        if ppua and not ppua.startswith("U+"):
            return ppua
        return None

class MainWindow(QMainWindow):
    def __init__(
        self,
        db_manager=None,
        overview_repo=None,
        glyph_repo=None,
        lexicon_repo=None,
        keyboard_repo=None,
        grammar_repo=None,
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
        self.grammar_repo = grammar_repo or (GrammarRepository(self.db_manager) if self.db_manager else None)
        self.language_id = language_id
        self.db_path = db_path
        self.project_name = project_name
        self.archive_path = archive_path
        self.session_dir = session_dir
        self.archive_manager = archive_manager or ProjectArchiveManager

        if self.session_dir:
            try:
                from font_tools.font_registry import register_language_font
                register_language_font(self.session_dir)
            except Exception:
                pass

        self._update_window_title()
        self.resize(1400, 950)

        self._setup_menu_bar()

        central_widget = QWidget()
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

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
            data_dir=self.session_dir or "",
        )
        self.keyboard_page.on_saved = self._reload_conlang_mappings
        self.grammar_page = GrammarPage(
            grammar_repo=self.grammar_repo,
            language_id=self.language_id,
        )

        self.pages = QStackedWidget()
        self.pages.addWidget(self.overview_page)
        self.pages.addWidget(self.glyphs_page)
        self.pages.addWidget(self.keyboard_page)
        self.pages.addWidget(self.lexicon_page)
        self.pages.addWidget(self.grammar_page)

        self.sidebar = Sidebar(on_page_changed_callback=self.pages.setCurrentIndex)

        main_layout.addWidget(self.sidebar, stretch=0)
        main_layout.addWidget(self.pages, stretch=1)

        self.setCentralWidget(central_widget)

 # digital-keyboard 
        self.osk = None
        self.kbd_button = FloatingKeyboardButton()
        self.kbd_button.toggled_on.connect(self._toggle_osk)
        self._install_floating_kbd()

        self.conlang_font_filter = _ConlangFontFilter(data_dir=self.session_dir or "", parent=self)
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.installEventFilter(self.conlang_font_filter)
        self.conlang_font_filter.refresh_family()

        self.conlang_mode = _ConlangModeController(parent=self)
        self.conlang_mode.mode_changed.connect(self._on_conlang_mode_changed)
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.installEventFilter(self)
        self._reload_conlang_mappings()
        self._setup_conlang_hotkey()
        self._setup_conlang_indicator()

    def _update_window_title(self):
        title_suffix = f" - {self.project_name}" if self.project_name else ""
        arc_suffix = f" [{os.path.basename(self.archive_path)}]" if self.archive_path else ""
        self.setWindowTitle(f"Lexicography & Language Software{title_suffix}{arc_suffix}")

 # Digital keyboard 

    def _install_floating_kbd(self):
        try:
            self.kbd_button.setParent(self)
            self.kbd_button.show()
            self._pin_kbd_button()
        except Exception:
            pass

    def _pin_kbd_button(self):
        try:
            status_h = self.statusBar().height() if self.statusBar() else 0
            margin = 16
            self.kbd_button.move(
                self.width() - self.kbd_button.width() - margin,
                self.height() - self.kbd_button.height() - margin - (status_h if status_h else 0),
            )
            self.kbd_button.raise_()
        except Exception:
            pass

    def _toggle_osk(self):
        if self.osk is not None:
            self._close_osk()
            return
        if not self.keyboard_repo or not self.language_id:
            self.kbd_button.setChecked(False)
            return
        self.osk = OnScreenKeyboard(
            keyboard_repo=self.keyboard_repo,
            language_id=self.language_id,
            session_dir=self.session_dir or "",
            parent=self,
        )
        self.osk.closed.connect(self._on_osk_closed)
        self.conlang_mode.key_pressed.connect(self.osk.highlight_key)
        self.osk.conlang_toggle_requested.connect(self.toggle_conlang_mode)
        self.osk.set_conlang_mode(self.conlang_mode.active)
        self.osk.show()
        self._position_osk()

    def _position_osk(self):
        if self.osk is None:
            return
        parent_pos = self.mapToGlobal(self.rect().bottomRight())
        x = parent_pos.x() - self.osk.width() - 24
        y = parent_pos.y() - self.osk.height() - 76
        self.osk.move(x, y)

    def _close_osk(self):
        if self.osk is not None:
            try:
                self.osk.close()
            except Exception:
                pass
            self.osk = None
        if self.kbd_button:
            self.kbd_button.setChecked(False)

    def _on_osk_closed(self):
        self.osk = None
        if self.kbd_button:
            self.kbd_button.setChecked(False)

    def _setup_conlang_hotkey(self):
 # Ctrl+Shift+Space toggles 
        try:
            self._conlang_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Space"), self)
            self._conlang_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            self._conlang_shortcut.activated.connect(self.toggle_conlang_mode)
        except Exception:
            self._conlang_shortcut = None

    def _setup_conlang_indicator(self):
        try:
            self.conlang_indicator = QLabel("CONLANG: OFF")
            self.conlang_indicator.setToolTip("Conlang mode — press Ctrl+Shift+Space to toggle")
            self.statusBar().addPermanentWidget(self.conlang_indicator)
            self._style_conlang_indicator(False)
        except Exception:
            self.conlang_indicator = None

    def _style_conlang_indicator(self, on: bool):
        if not getattr(self, "conlang_indicator", None):
            return
        if on:
            self.conlang_indicator.setText("CONLANG: ON")
            self.conlang_indicator.setStyleSheet(
                "background:#007acc; color:white; padding:2px 10px; border-radius:9px; font-weight:bold;"
            )
        else:
            self.conlang_indicator.setText("CONLANG: OFF")
            self.conlang_indicator.setStyleSheet(
                "background:#e0e0e0; color:#666; padding:2px 10px; border-radius:9px;"
            )

    def toggle_conlang_mode(self):
        self.conlang_mode.set_active(not self.conlang_mode.active)

    def _on_conlang_mode_changed(self, on: bool):
        self._style_conlang_indicator(on)
        if self.osk is not None and hasattr(self.osk, "set_conlang_mode"):
            self.osk.set_conlang_mode(on)
        try:
            self.statusBar().showMessage(
                f"Conlang mode {'ON — physical keys type glyphs' if on else 'OFF — normal typing'}", 3000
            )
        except Exception:
            pass

    def _reload_conlang_mappings(self):
        mappings: Dict[str, Dict] = {}
        if self.keyboard_repo and self.language_id:
            try:
                from font_tools.font_registry import glyph_character
                for m in self.keyboard_repo.all_mappings_for_language(self.language_id):
                    key_code = m.get("key_code")
                    if not key_code:
                        continue
                    char = m.get("assignment") or ""
                    if m.get("glyph_id") and self.session_dir:
                        gchar = glyph_character(self.session_dir, m["glyph_id"])
                        if gchar:
                            char = gchar
                    mappings[key_code] = {"char": char, "glyph_id": m.get("glyph_id"), "ppua": m.get("ppua") or ""}
            except Exception:
                mappings = {}
        self.conlang_mode.set_mappings(mappings)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and self.conlang_mode.active \
                and not event.isAutoRepeat():
            key_code = self._qkey_to_key_code(event)
            if key_code:
                glyph = self.conlang_mode.glyph_for_key(key_code)
                if glyph:
                    self.conlang_mode.key_pressed.emit(key_code)
                    self._insert_into_focus(glyph)
                    return True  # swallow the original key
        return super().eventFilter(obj, event)

    @staticmethod
    def _qkey_to_key_code(event) -> Optional[str]:
        key = event.key()
        text = event.text()
        if text and len(text) == 1 and text.isprintable() and text in "`1234567890-=qwertyuiop[]\\asdfghjkl;'zxcvbnm,./":
            return text
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return chr(ord('a') + (key - Qt.Key.Key_A))
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(ord('0') + (key - Qt.Key.Key_0))
        return None

    def _insert_into_focus(self, text: str):
        w = QApplication.focusWidget()
        if w is None:
            return
        for meth in ("insert", "insertPlainText"):
            fn = getattr(w, meth, None)
            if callable(fn):
                try:
                    fn(text)
                    return
                except Exception:
                    pass
        setter = getattr(w, "setText", None)
        getter = getattr(w, "text", None)
        if callable(setter) and callable(getter):
            try:
                setter(str(getter()) + text)
            except Exception:
                pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._pin_kbd_button()

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
        if hasattr(self, "overview_page") and hasattr(self.overview_page, "save_data"):
            self.overview_page.save_data()
        if hasattr(self, "glyphs_page") and hasattr(self.glyphs_page, "save_active_glyph"):
            self.glyphs_page.save_active_glyph(notify=False)

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
        clean_name = self.project_name.lower().replace(" ", "_") if self.project_name else "language"
        default_file = f"{clean_name}.langarc"
        dialog = QFileDialog(self, "Save Copy As", default_file, "Language Archive (*.langarc);;Zip Archive (*.zip);;All Files (*)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
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
        dialog = QFileDialog(self, "Open Language Archive", "",
            "Language Archive (*.langarc *.zip);;SQLite Database (*.db);;All Files (*)")
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
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
                self.grammar_repo = GrammarRepository(self.db_manager)
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
                self.grammar_repo = GrammarRepository(self.db_manager)
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
            self.grammar_repo = GrammarRepository(self.db_manager)
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
        if self.session_dir:
            try:
                from font_tools.font_registry import register_language_font
                register_language_font(self.session_dir)
            except Exception:
                pass

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
            data_dir=self.session_dir or "",
        )
        self.keyboard_page.on_saved = self._reload_conlang_mappings
        self.grammar_page = GrammarPage(
            grammar_repo=self.grammar_repo,
            language_id=self.language_id,
        )
        self.pages.addWidget(self.overview_page)
        self.pages.addWidget(self.glyphs_page)
        self.pages.addWidget(self.keyboard_page)
        self.pages.addWidget(self.lexicon_page)
        self.pages.addWidget(self.grammar_page)
        self.statusBar().showMessage(f"Loaded: {self.project_name}", 4000)

    def closeEvent(self, event):
        if self.archive_path and self.session_dir and self.archive_manager:
            try:
                self.archive_manager.save_archive(
                    self.session_dir, self.archive_path, self.project_name
                )
            except Exception:
                pass
        super().closeEvent(event)