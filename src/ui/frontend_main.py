import os
import sys
from typing import Dict, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QStackedWidget, QLabel,
    QMessageBox, QFileDialog, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
    QPushButton, QTableWidget, QTableView, QApplication, QDialog,
)
from PySide6.QtGui import QAction, QKeySequence, QFont, QShortcut, QKeyEvent, QInputMethodEvent, QTextCharFormat, QGuiApplication
from PySide6.QtCore import Qt, QEvent, QObject, Signal, QTimer
from .components.coll_sidebar import Sidebar
from .components.dark_file_dialog import open_dark_dialog
from .components.floating_keyboard import FloatingKeyboardButton
from .components.on_screen_keyboard import OnScreenKeyboard, insert_into_widget, resolve_text_target
from .pages.overview import Overview_Page
from .pages.glyphs_page import Glyphs_Page
from .pages.lexicon_page import LexiconPage
from .pages.keyboard_page import KeyboardPage
from .pages.grammar_page import GrammarPage
from .pages.transcribe_page import TranscribePage

try:
    from database.glyph_db import GlyphRepository
    from database.lexicon_db import LexiconRepository
    from database.keyboard_db import KeyboardRepository
    from database.grammar_db import GrammarRepository
    from database.transcribe_db import TranscribeSettingsRepository
    from database.archive_manager import ProjectArchiveManager
except (ImportError, ValueError):
    from ..database.glyph_db import GlyphRepository
    from ..database.lexicon_db import LexiconRepository
    from ..database.keyboard_db import KeyboardRepository
    from ..database.grammar_db import GrammarRepository
    from ..database.transcribe_db import TranscribeSettingsRepository
    from ..database.archive_manager import ProjectArchiveManager



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
        self.transcribe_repo = TranscribeSettingsRepository(self.db_manager) if self.db_manager else None
        self.language_id = language_id
        self.db_path = db_path
        self.project_name = project_name
        self.archive_path = archive_path
        self.session_dir = session_dir
        self.archive_manager = archive_manager or ProjectArchiveManager

        if self.session_dir:
            try:
                from digital_keyboard import register_language_font
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
        self.transcribe_page = TranscribePage(
            lexicon_repo=self.lexicon_repo,
            grammar_repo=self.grammar_repo,
            settings_repo=self.transcribe_repo,
            language_id=self.language_id,
            session_dir=self.session_dir,
        )

        self.pages = QStackedWidget()
        self.pages.addWidget(self.overview_page)
        self.pages.addWidget(self.glyphs_page)
        self.pages.addWidget(self.keyboard_page)
        self.pages.addWidget(self.lexicon_page)
        self.pages.addWidget(self.grammar_page)
        self.pages.addWidget(self.transcribe_page)

        self.sidebar = Sidebar(on_page_changed_callback=self.pages.setCurrentIndex)

        main_layout.addWidget(self.sidebar, stretch=0)
        main_layout.addWidget(self.pages, stretch=1)

        self.setCentralWidget(central_widget)

        self.osk = None
        self.kbd_button = FloatingKeyboardButton()
        self.kbd_button.toggled.connect(self._on_kbd_button_toggled)
        self._install_floating_kbd()

        self._reload_conlang_mappings()
        self._osk_shortcut = None
        
        # Install event filter for physical keyboard glyph typing
        QApplication.instance().installEventFilter(self)

    def _update_window_title(self):
        title_suffix = f" - {self.project_name}" if self.project_name else ""
        arc_suffix = f" [{os.path.basename(self.archive_path)}]" if self.archive_path else ""
        self.setWindowTitle(f"Lexicography & Language Software{title_suffix}{arc_suffix}")

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

    def _set_kbd_button_checked(self, checked: bool):
        # update the button without re-triggering its toggled handler
        if not self.kbd_button:
            return
        self.kbd_button.blockSignals(True)
        self.kbd_button.setChecked(checked)
        self.kbd_button.blockSignals(False)
        self.kbd_button._update_style()

    def _on_kbd_button_toggled(self, checked: bool):
        if checked and self.osk is None:
            self._open_osk()
        elif not checked and self.osk is not None:
            if self.osk.isMinimized():
                # minimized keyboard: bring it back instead of closing
                self.osk.showNormal()
                self.osk.raise_()
                self._set_kbd_button_checked(True)
            else:
                self._close_osk()

    def _toggle_osk(self):
        if self.osk is not None:
            if self.osk.isMinimized():
                self.osk.showNormal()
                self.osk.raise_()
            else:
                self._close_osk()
            return
        self._open_osk()

    def _open_osk(self):
        # never silently fail — show why if we can't open
        if not self.keyboard_repo:
            self.statusBar().showMessage("Keyboard repo missing; cannot open OSK", 3000)
            self._set_kbd_button_checked(False)
            return
        if not self.language_id:
            self.statusBar().showMessage("No language loaded; cannot open OSK", 3000)
            self._set_kbd_button_checked(False)
            return
        # normally the keyboard is a panel inside the main window, docked bottom-right (apps cannot
        # place their own windows on Wayland). Over a modal popup it becomes a separate window
        # parented to the popup, so the popup does not block it and it is not clipped to the popup.
        modal = QApplication.activeModalWidget()
        embedded = modal is None
        self.osk = OnScreenKeyboard(
            keyboard_repo=self.keyboard_repo,
            language_id=self.language_id,
            session_dir=self.session_dir or "",
            parent=self if embedded else modal,
            mappings=getattr(self, '_glyph_mappings', {}),
            embedded=embedded,
        )
        self.osk.closed.connect(self._on_osk_closed)
        self.osk.destroyed.connect(self._on_osk_destroyed)
        self.osk.layout_changed.connect(self._position_osk)
        self.osk.key_handler = self._on_osk_key_clicked
        self.osk.preset_changed.connect(self._on_osk_preset_selected)
        self._clear_layer_state()
        self._sync_osk_presets()
        self._set_kbd_button_checked(True)
        self.osk.adjustSize()
        self._position_osk()
        self.osk.show()
        self.osk.raise_()
        QTimer.singleShot(0, self._position_osk)   # again once the layout has its final size

    def _position_osk(self):
        # the panel sits in the bottom-right corner of its parent window; once the user has dragged
        # it, it only stays inside the parent. A separate window (over a popup) is left to the WM.
        osk = self.osk
        if osk is None or not getattr(osk, "_embedded", False):
            return
        parent = osk.parentWidget()
        if parent is None:
            return
        w, h = osk.width(), osk.height()
        if osk.user_moved:
            x, y = osk.x(), osk.y()
        else:
            margin = 14
            bar = self.statusBar() if parent is self else None
            bottom = margin + (bar.height() if bar is not None and bar.isVisible() else 0)
            x = parent.width() - w - margin
            y = parent.height() - h - bottom
        x = max(0, min(x, parent.width() - w))
        y = max(0, min(y, parent.height() - h))
        osk.move(x, y)

    def _sync_osk_presets(self):
        # keep the keyboard's preset dropdown in step with the Keyboard page
        if self.osk is None or not self.keyboard_repo or not self.language_id:
            return
        try:
            presets = self.keyboard_repo.get_presets(self.language_id)
        except Exception:
            return
        page = getattr(self, "keyboard_page", None)
        current = getattr(page, "_current_preset_id", None) or (presets[0]["id"] if presets else None)
        self.osk.set_presets([(p["id"], p["name"]) for p in presets], current)

    def _on_osk_preset_selected(self, preset_id: str):
        page = getattr(self, "keyboard_page", None)
        if page is None:
            return
        idx = page.combo_presets.findData(preset_id)
        if idx >= 0 and idx != page.combo_presets.currentIndex():
            page.combo_presets.setCurrentIndex(idx)   # page reloads and calls _reload_conlang_mappings
        else:
            self._reload_conlang_mappings()

    def _close_osk(self):
        osk = self.osk
        self.osk = None
        self._clear_layer_state()
        if osk is not None:
            try:
                osk.close()
            except Exception:
                pass
        self._set_kbd_button_checked(False)

    def _on_osk_closed(self):
        self.osk = None
        self._clear_layer_state()
        self._set_kbd_button_checked(False)

    def _on_osk_destroyed(self, *_):
        # keyboard was deleted together with the popup it was parented to
        self.osk = None
        self._set_kbd_button_checked(False)

    # trigger key state. The lists are never changed in place, always replaced.
    _pending_dead: Optional[str] = None            # "once" key waiting for its partner
    _held_keys: list = []                          # "hold" keys currently pressed
    _toggled_keys: list = []                       # "toggle" keys currently switched on
    _trigger_modes: Dict[str, str] = {}            # trigger key -> once | hold | toggle
    _dead_combos: Dict[str, Dict[str, str]] = {}   # trigger key -> {key: result character}
    _preedit_widget = None

    def _reload_conlang_mappings(self):
        mappings: Dict[str, Dict] = {}
        dead_combos: Dict[str, Dict[str, str]] = {}
        trigger_modes: Dict[str, str] = {}
        self._reset_layers()
        if self.keyboard_repo and self.language_id:
            try:
                from digital_keyboard import glyph_character, register_language_font
                if self.session_dir:
                    register_language_font(self.session_dir)
                # Get the active preset from KeyboardPage
                active_preset = None
                presets = []
                if hasattr(self, 'keyboard_page') and hasattr(self.keyboard_page, '_current_preset_id'):
                    active_preset = self.keyboard_page._current_preset_id
                
                # Load only the active preset's mappings
                if active_preset:
                    rows = self.keyboard_repo.get_all_mappings(active_preset)
                else:
                    # Fallback: load the first available preset
                    presets = self.keyboard_repo.get_presets(self.language_id)
                    if presets:
                        rows = self.keyboard_repo.get_all_mappings(presets[0]["id"])
                    else:
                        rows = []
                
                for m in rows:
                    key_code = m.get("key_code")
                    if not key_code:
                        continue
                    char = m.get("assignment") or ""
                    if m.get("glyph_id") and self.session_dir:
                        gchar = glyph_character(self.session_dir, m["glyph_id"])
                        if gchar:
                            char = gchar
                        else:
                            print(f"[DEBUG-kbd2] glyph_character returned empty for glyph_id={m['glyph_id']}")
                    mappings[key_code] = {"char": char, "glyph_id": m.get("glyph_id"), "ppua": m.get("ppua") or ""}

                # dead key combinations resolved to their font characters
                preset_for_combos = active_preset or (presets[0]["id"] if not active_preset and presets else None)
                if preset_for_combos:
                    for c in self.keyboard_repo.get_dead_combos(preset_for_combos):
                        # a trigger key even if its glyph is not built yet; one mode per trigger
                        trigger_modes.setdefault(c["dead_key_code"], c.get("mode") or "once")
                        gid = c.get("result_glyph_id")
                        gchar = glyph_character(self.session_dir, gid) if gid and self.session_dir else ""
                        if gchar:
                            dead_combos.setdefault(c["dead_key_code"], {})[c["base_key_code"]] = gchar
            except Exception as exc:
                print(f"[DEBUG-kbd2] Failed to reload conlang mappings: {exc}")
                mappings = {}
        self._glyph_mappings = mappings
        self._dead_combos = dead_combos
        self._trigger_modes = trigger_modes
        print(f"[DEBUG-kbd2] Reloaded {len(mappings)} key mappings, {sum(len(v) for v in dead_combos.values())} dead combinations")
        if getattr(self, 'osk', None) is not None:
            self.osk.set_mappings(mappings)
            self._refresh_osk_layer()
            self._sync_osk_presets()

    def _glyph_for_key(self, key_code: str) -> Optional[str]:
        m = self._glyph_mappings.get(key_code)
        if not m:
            return None
        char = m.get("char")
        if char:
            return char
        ppua = m.get("ppua") or ""
        if ppua and not ppua.startswith("U+"):
            return ppua
        return None

    def eventFilter(self, obj, event):
        et = event.type()
        # Ctrl+Shift+Enter / Ctrl+Shift+Space toggles the keyboard, even over popups
        if et == QEvent.Type.KeyPress and not event.isAutoRepeat():
            mods = event.modifiers()
            want = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
            if (mods & want) == want and not (mods & (Qt.KeyboardModifier.AltModifier
                                                      | Qt.KeyboardModifier.MetaModifier)) \
                    and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self._toggle_osk()
                return True
        # a modal popup opening closes the keyboard so nothing is left stuck on top
        if et == QEvent.Type.Show and self.osk is not None \
                and isinstance(obj, QDialog) and obj.isModal() \
                and obj is not self.osk and not self.osk.isAncestorOf(obj):
            self._close_osk()
        if et == QEvent.Type.Resize and self.osk is not None and getattr(self.osk, "_embedded", False) \
                and obj is self.osk.parentWidget():
            self._position_osk()
        # a held key must not stay "down" when the app loses focus (its release goes elsewhere)
        if et == QEvent.Type.ApplicationDeactivate and self._held_keys:
            self._held_keys = []
            self._refresh_osk_layer()
        if et in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease) and self.osk is not None:
            key_code = self._qkey_to_key_code(event)
            is_trigger = bool(key_code) and key_code in self._trigger_modes
            if et == QEvent.Type.KeyRelease:
                if is_trigger and not event.isAutoRepeat() and self._release_layer_key(key_code):
                    return True
            else:
                mods = event.modifiers()
                ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
                meta = bool(mods & Qt.KeyboardModifier.MetaModifier)
                alt = bool(mods & Qt.KeyboardModifier.AltModifier)
                # the Alt key press itself, or a key typed while Alt is a held trigger, carries Alt
                if alt and (key_code == "Alt" or "Alt" in self._held_keys):
                    alt = False
                if not (ctrl or meta or alt):
                    if event.isAutoRepeat() and is_trigger:
                        return True   # holding a trigger key must not repeat it
                    if self._pending_dead is not None and self._cancel_or_flush_dead(event):
                        return True
                    if key_code and self._handle_conlang_key(key_code):
                        return True  # swallow the original key
        return super().eventFilter(obj, event)

    def _set_pending_dead(self, key_code: Optional[str], target=None):
        # the waiting "once" key: lit on the OSK, and its glyph (if any) shown underlined in the field
        self._clear_preedit()
        self._pending_dead = key_code
        self._refresh_osk_layer()
        if key_code and self._trigger_modes.get(key_code, "once") == "once":
            own = self._glyph_for_key(key_code)
            if own:
                self._show_preedit(own, target)

    def _clear_layer_state(self):
        # forget every waiting, held and toggled trigger (no OSK refresh; used when it closes)
        self._clear_preedit()
        self._pending_dead = None
        self._held_keys = []
        self._toggled_keys = []

    def _reset_layers(self):
        self._clear_layer_state()
        self._refresh_osk_layer()

    def _layer_triggers(self) -> list:
        # active triggers, strongest first: waiting once key, held keys, toggled keys (latest first)
        out = [self._pending_dead] if self._pending_dead else []
        out += list(reversed(self._held_keys))
        out += list(reversed(self._toggled_keys))
        return out

    def _refresh_osk_layer(self):
        # the OSK relabels its keys with the active layer and lights the active triggers
        osk = getattr(self, 'osk', None)
        if osk is None or not hasattr(osk, 'set_layer_state'):
            return
        overlay: Dict[str, str] = {}
        for trigger in reversed(self._layer_triggers()):
            overlay.update(self._dead_combos.get(trigger, {}))
        osk.set_layer_state(overlay, set(self._held_keys) | set(self._toggled_keys), self._pending_dead)

    def _press_layer_key(self, key_code: str, mode: str, osk_click: bool, target=None):
        if mode == "toggle":
            if key_code in self._toggled_keys:
                self._toggled_keys = [k for k in self._toggled_keys if k != key_code]
            else:
                self._toggled_keys = self._toggled_keys + [key_code]
            self._refresh_osk_layer()
        elif osk_click:
            # a mouse click cannot keep a key down: the layer applies to the next key only
            self._set_pending_dead(None if self._pending_dead == key_code else key_code, target)
        else:
            if key_code not in self._held_keys:
                self._held_keys = self._held_keys + [key_code]
            self._refresh_osk_layer()

    def _release_layer_key(self, key_code: str) -> bool:
        # True when this key is a trigger: its press was consumed, so its release is consumed too
        if key_code not in self._trigger_modes:
            return False
        if key_code in self._held_keys:
            self._held_keys = [k for k in self._held_keys if k != key_code]
            self._refresh_osk_layer()
        return True

    def _show_preedit(self, text: str, target=None):
        widget = resolve_text_target(target or QApplication.focusWidget())
        if widget is None or not text:
            return
        try:
            fmt = QTextCharFormat()
            fmt.setFontUnderline(True)
            attr = QInputMethodEvent.Attribute(
                QInputMethodEvent.AttributeType.TextFormat, 0, len(text), fmt)
            QApplication.sendEvent(widget, QInputMethodEvent(text, [attr]))
            self._preedit_widget = widget
        except Exception as exc:
            print(f"[DEBUG-kbd2] dead key preview failed: {exc}")

    def _clear_preedit(self):
        widget = self._preedit_widget
        self._preedit_widget = None
        if widget is None:
            return
        try:
            QApplication.sendEvent(widget, QInputMethodEvent("", []))
        except RuntimeError:
            pass   # the field was deleted meanwhile

    def _cancel_or_flush_dead(self, event) -> bool:
        # keys that are not mapped letters while a dead key is waiting
        key = event.key()
        if key in (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
                   Qt.Key.Key_CapsLock, Qt.Key.Key_AltGr):
            return False   # modifier presses do not affect a pending dead key
        if key in (Qt.Key.Key_Escape, Qt.Key.Key_Backspace):
            self._set_pending_dead(None)   # cancel, nothing typed
            return True
        if key == Qt.Key.Key_Space:
            dead = self._pending_dead
            self._set_pending_dead(None)
            own = self._glyph_for_key(dead) if dead else None
            if own:
                self._insert_into_focus(own)
            return True    # space itself is consumed, like on other keyboards
        if self._qkey_to_key_code(event) is None:
            self._set_pending_dead(None)   # Enter, arrows, Tab ... just drop the pending key
        return False

    def _handle_conlang_key(self, key_code: str, target=None, osk_click: bool = False) -> bool:
        # returns True when the key was consumed (typed a glyph, or changed a layer)
        def insert(text):
            insert_into_widget(target or QApplication.focusWidget(), text)

        def flash():
            if self.osk is not None and hasattr(self.osk, 'highlight_key'):
                self.osk.highlight_key(key_code)

        pending = self._pending_dead
        mode = self._trigger_modes.get(key_code)
        if key_code == "Backspace":
            if pending is None:
                return False
            self._set_pending_dead(None)   # cancel the waiting key, nothing typed
            return True

        partner = pending is not None and key_code in self._dead_combos.get(pending, {})

        # hold and toggle keys switch a layer and type nothing themselves
        if mode in ("hold", "toggle") and not partner:
            self._press_layer_key(key_code, mode, osk_click, target)
            return True

        if pending is not None:
            if key_code in ("Shift", "Alt", "Caps") and not partner and mode is None:
                return False   # a modifier pressed for the next key does not cancel the waiting key
            self._set_pending_dead(None)   # also removes the underlined preview
            combo = self._dead_combos.get(pending, {}).get(key_code)
            if combo:
                flash()
                insert(combo)
                return True
            own = self._glyph_for_key(pending)
            if own:
                insert(own)
            if key_code == pending or key_code == " ":
                return True    # same key twice, or Space: own glyph typed once
            # no combination: own glyph already typed, now handle this key normally

        if mode == "once":
            self._set_pending_dead(key_code, target)
            return True

        # held and toggled layers change what a key types
        for trigger in self._layer_triggers():
            combo = self._dead_combos.get(trigger, {}).get(key_code)
            if combo:
                flash()
                insert(combo)
                return True

        glyph = self._glyph_for_key(key_code)
        if glyph:
            flash()
            insert(glyph)
            return True
        return False

    def _on_osk_key_clicked(self, key_code: str, target=None) -> bool:
        # called by the on-screen keyboard; True means the click was handled here
        return self._handle_conlang_key(key_code, target, osk_click=True)

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
        if key == Qt.Key.Key_Tab:
            return "Tab"
        if key == Qt.Key.Key_CapsLock:
            return "Caps"
        if key == Qt.Key.Key_Shift:
            return "Shift"
        if key in (Qt.Key.Key_Alt, Qt.Key.Key_AltGr):
            return "Alt"
        return None

    def _insert_into_focus(self, text: str):
        insert_into_widget(QApplication.focusWidget(), text)

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
        new_path = open_dark_dialog(
            self,
            "Save Copy As",
            default_file,
            "Language Archive (*.langarc);;Zip Archive (*.zip);;All Files (*)",
            save_mode=True,
        )
        if new_path:
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
        file_path = open_dark_dialog(
            self,
            "Open Language Archive",
            "",
            "Language Archive (*.langarc *.zip);;SQLite Database (*.db);;All Files (*)",
        )
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
        self.transcribe_repo = TranscribeSettingsRepository(self.db_manager) if self.db_manager else None
        if self.session_dir:
            try:
                from digital_keyboard import register_language_font
                register_language_font(self.session_dir)
            except Exception:
                pass

        old_transcribe = getattr(self, "transcribe_page", None)
        if old_transcribe is not None:
            old_transcribe.shutdown()
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
        self.transcribe_page = TranscribePage(
            lexicon_repo=self.lexicon_repo,
            grammar_repo=self.grammar_repo,
            settings_repo=self.transcribe_repo,
            language_id=self.language_id,
            session_dir=self.session_dir,
        )
        self.pages.addWidget(self.overview_page)
        self.pages.addWidget(self.glyphs_page)
        self.pages.addWidget(self.keyboard_page)
        self.pages.addWidget(self.lexicon_page)
        self.pages.addWidget(self.grammar_page)
        self.pages.addWidget(self.transcribe_page)
        self.statusBar().showMessage(f"Loaded: {self.project_name}", 4000)

    def closeEvent(self, event):
        page = getattr(self, "transcribe_page", None)
        if page is not None:
            page.shutdown()
        if self.archive_path and self.session_dir and self.archive_manager:
            try:
                self.archive_manager.save_archive(
                    self.session_dir, self.archive_path, self.project_name
                )
            except Exception:
                pass
        super().closeEvent(event)
