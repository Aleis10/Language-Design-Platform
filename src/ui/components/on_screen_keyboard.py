from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QPushButton, QLabel, QToolButton,
    QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from digital_keyboard import (
    glyph_character, register_language_font, has_ppua, track_conlang_widget,
)


QWERTY_ROWS = [
    ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'"],
    ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/"],
    [" "],
]

_TEXT_WIDGETS = (QLineEdit, QTextEdit, QPlainTextEdit)


# --------------------------------------------------------------------------
# Shared helpers (also used by MainWindow for physical-keyboard typing)
# --------------------------------------------------------------------------

def resolve_text_target(w: Optional[QWidget]) -> Optional[QWidget]:
    """Map a focus widget to the widget that really holds text."""
    if w is None:
        return None
    if isinstance(w, QComboBox) and w.isEditable():
        return w.lineEdit()
    if isinstance(w, _TEXT_WIDGETS) and not getattr(w, "isReadOnly", lambda: False)():
        return w
    return None


def insert_into_widget(w: QWidget, text: str) -> bool:
    target = resolve_text_target(w)
    if target is None or not text:
        return False
    if isinstance(target, QLineEdit):
        target.insert(text)                      # replaces selection, moves caret
    else:                                        # QTextEdit / QPlainTextEdit
        target.textCursor().insertText(text)
        target.ensureCursorVisible()
    return True


def backspace_in_widget(w: QWidget) -> bool:
    target = resolve_text_target(w)
    if target is None:
        return False
    if isinstance(target, QLineEdit):
        target.backspace()
    else:
        cur = target.textCursor()
        if cur.hasSelection():
            cur.removeSelectedText()
        else:
            cur.deletePreviousChar()
    return True


class OnScreenKeyboard(QWidget):
    """On-screen keyboard that inserts mapped characters/glyphs."""

    closed = Signal()

    def __init__(
        self,
        keyboard_repo=None,
        language_id="",
        session_dir="",
        parent=None,
        mappings: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        super().__init__(parent)

        self.keyboard_repo = keyboard_repo
        self.language_id = language_id
        self.session_dir = session_dir
        self._mappings: Dict[str, Dict[str, Any]] = dict(mappings or {})
        self._key_buttons: Dict[str, QPushButton] = {}
        self._last_target: Optional[QWidget] = None   # last text field the user was in

        # title bar with minimize + close only (no maximize), always on top
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setWindowTitle("On-Screen Keyboard")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Make sure the CURRENT font build is registered before any button uses it.
        if self.session_dir:
            try:
                register_language_font(self.session_dir)
            except Exception as exc:
                print(f"[OSK] font registration failed: {exc}")

        if not self._mappings and self.keyboard_repo and self.language_id:
            self._load_mappings()

        self._build_ui()

        # Clicking a tool window can steal focus; remember the field we came from.
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._on_focus_changed)
            self._on_focus_changed(None, QApplication.focusWidget())

    # ---- lifecycle -------------------------------------------------------

    def closeEvent(self, event):
        app = QApplication.instance()
        if app is not None:
            try:
                app.focusChanged.disconnect(self._on_focus_changed)
            except (TypeError, RuntimeError):
                pass
        self.closed.emit()
        super().closeEvent(event)

    def _on_focus_changed(self, _old, new):
        if new is None or self.isAncestorOf(new) or new is self:
            return
        if resolve_text_target(new) is not None:
            self._last_target = resolve_text_target(new)

    # ---- mappings --------------------------------------------------------

    def _load_mappings(self):
        """Fallback loader (used only if MainWindow did not pass mappings)."""
        self._mappings = {}
        try:
            presets = self.keyboard_repo.get_presets(self.language_id)
            rows = self.keyboard_repo.get_all_mappings(presets[0]["id"]) if presets else []
        except Exception as exc:
            print(f"[OSK] failed to load mappings: {exc}")
            return
        for m in rows:
            key_code = m.get("key_code")
            if not key_code:
                continue
            char = m.get("assignment") or ""
            if m.get("glyph_id") and self.session_dir:
                gchar = glyph_character(self.session_dir, str(m["glyph_id"]))
                if gchar:
                    char = gchar
            self._mappings[key_code] = {
                "char": char, "glyph_id": m.get("glyph_id"), "ppua": m.get("ppua") or "",
            }

    def set_mappings(self, mappings: Dict[str, Dict[str, Any]]):
        """Call when the keyboard preset / font changes; refreshes every key."""
        self._mappings = dict(mappings or {})
        if self.session_dir:
            try:
                register_language_font(self.session_dir)
            except Exception:
                pass
        for key, btn in self._key_buttons.items():
            if key != "Backspace":
                self._style_key(btn, key)

    # ---- UI --------------------------------------------------------------

    def _get_key_text(self, key: str) -> tuple[str, str]:
        mapping = self._mappings.get(key)
        char = (mapping or {}).get("char", "")
        if char:
            return char, char
        return key, key

    def _style_key(self, btn: QPushButton, key: str):
        """Set text, insert payload and the right font for one key."""
        display, insert = self._get_key_text(key)
        btn.setText("Space" if key == " " and display == " " else display)
        btn.setProperty("insert_text", insert)
        if has_ppua(insert):
            track_conlang_widget(btn, 16)   # conlang first, UI fallback; follows font rebuilds
        else:
            f = QFont(self.font())
            f.setPointSize(10)
            btn.setFont(f)

    def _build_ui(self):
        self.setObjectName("OSKRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        lbl = QLabel("On-Screen Keyboard")
        lbl.setObjectName("OSKTitle")
        header.addWidget(lbl)
        header.addStretch()
        root.addLayout(header)

        hint = QLabel("Click to insert mapped characters into focused field.")
        hint.setObjectName("OSKHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        row = 0
        for keys in QWERTY_ROWS:
            for col, key in enumerate(keys):
                btn = QPushButton()
                btn.setObjectName(f"Key_{key}")
                btn.setMinimumHeight(34)
                btn.setMinimumWidth(40)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.clicked.connect(lambda _checked=False, b=btn: self._insert_from_button(b))
                self._style_key(btn, key)
                if key == " ":
                    grid.addWidget(btn, row, 0, 1, 8)
                else:
                    grid.addWidget(btn, row, col)
                self._key_buttons[key] = btn
            row += 1

        backspace_btn = QPushButton("⌫ Backspace")
        backspace_btn.setObjectName("Key_Backspace")
        backspace_btn.setMinimumHeight(34)
        backspace_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        backspace_btn.clicked.connect(self._backspace)
        grid.addWidget(backspace_btn, row, 0, 1, 4)
        self._key_buttons["Backspace"] = backspace_btn

        root.addLayout(grid)
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        self.setStyleSheet(self._qss())

    def highlight_key(self, key_code: str):
        btn = self._key_buttons.get(key_code)
        if btn:
            btn.setStyleSheet("background: #007acc; color: white;")
            QTimer.singleShot(150, lambda: btn.setStyleSheet(""))

    # ---- typing ----------------------------------------------------------

    def _target(self) -> Optional[QWidget]:
        return resolve_text_target(QApplication.focusWidget()) or self._last_target

    def _insert_from_button(self, button: QPushButton):
        text = button.property("insert_text")
        if text is None:
            text = button.text()
        target = self._target()
        if target is not None:
            insert_into_widget(target, str(text))
            target.setFocus()

    def _backspace(self):
        target = self._target()
        if target is not None:
            backspace_in_widget(target)
            target.setFocus()

    # ---- style -----------------------------------------------------------
    # NOTE: no `font-size` / `font-family` on QPushButton here. A stylesheet
    # font property overrides setFont() and would undo the conlang font.

    def _qss(self) -> str:
        return """
        QWidget#OSKRoot {
            background-color: #f7f7f7;
            border: 1px solid #c8c8c8;
            border-radius: 10px;
        }
        QLabel#OSKTitle { font-size: 13px; font-weight: bold; color: #111111; }
        QLabel#OSKHint { font-size: 10px; color: #888888; }
        QPushButton {
            background: #ffffff;
            border: 1px solid #c8c8c8;
            border-radius: 5px;
            color: #333333;
            padding: 2px;
        }
        QPushButton:hover { background: #eef4fd; border-color: #007acc; }
        """
