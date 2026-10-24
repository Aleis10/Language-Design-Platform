from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QPushButton, QLabel, QToolButton,
    QVBoxLayout, QHBoxLayout, QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QListView,
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QPointF, QEvent
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QPen, QColor, QPolygonF

from digital_keyboard import (
    glyph_character, register_language_font, has_ppua, track_conlang_widget, track_conlang_combo,
)


QWERTY_ROWS = [
    ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="],
    ["Tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
    ["Caps", "a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'"],
    ["Shift", "z", "x", "c", "v", "b", "n", "m", ",", ".", "/"],
    ["Alt", " "],
]

# keys that only act when they are mapped (or used in a dead key combination)
SPECIAL_KEYS = ("Tab", "Caps", "Shift", "Alt")

# key sizes (bigger keys make the keyboard easier to hit and the glyphs easier to read)
KEY_HEIGHT = 48
KEY_WIDTH = 54
SPECIAL_KEY_WIDTH = 74
GLYPH_POINT_SIZE = 22
TEXT_POINT_SIZE = 13


def _backspace_icon(size: int = 30) -> QIcon:
    # drawn with QPainter so it does not depend on a font having the backspace symbol
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    k = size / 30.0
    pen = QPen(QColor("#333333"))
    pen.setWidthF(2.2 * k)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawPolygon(QPolygonF([QPointF(3 * k, 15 * k), QPointF(10 * k, 5 * k), QPointF(27 * k, 5 * k),
                             QPointF(27 * k, 25 * k), QPointF(10 * k, 25 * k)]))
    p.drawLine(QPointF(15 * k, 11 * k), QPointF(21 * k, 19 * k))
    p.drawLine(QPointF(21 * k, 11 * k), QPointF(15 * k, 19 * k))
    p.end()
    return QIcon(pm)

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
    preset_changed = Signal(str)   # user picked another preset in the dropdown
    layout_changed = Signal()      # size changed (minimized / restored); the owner re-docks it

    def __init__(
        self,
        keyboard_repo=None,
        language_id="",
        session_dir="",
        parent=None,
        mappings: Optional[Dict[str, Dict[str, Any]]] = None,
        embedded: bool = True,
    ):
        # embedded: a panel inside the parent window (can always be docked bottom-right, even on
        # Wayland where apps cannot place their own windows). Not embedded: a separate window,
        # used only over a popup dialog, which would be clipped to the dialog's small size.
        super().__init__(parent)
        self._embedded = embedded
        self._collapsed = False
        self._user_moved = False
        self._drag_start = None

        self.keyboard_repo = keyboard_repo
        self.language_id = language_id
        self.session_dir = session_dir
        self._mappings: Dict[str, Dict[str, Any]] = dict(mappings or {})
        self._key_buttons: Dict[str, QPushButton] = {}
        self._last_target: Optional[QWidget] = None   # last text field the user was in
        self.key_handler = None                       # MainWindow sets this: handles dead keys
        self._pending_dead_key: Optional[str] = None  # a "once" key waiting for its partner (amber)
        self._active_keys: set = set()                # held / toggled trigger keys (green)
        self._overlay: Dict[str, str] = {}            # key -> character typed in the active layer

        if not embedded:
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
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
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
        char = self._overlay.get(key) or (mapping or {}).get("char", "")
        if char:
            return char, char
        return key, key

    def _style_key(self, btn: QPushButton, key: str):
        """Set text, insert payload and the right font for one key."""
        display, insert = self._get_key_text(key)
        btn.setText("Space" if key == " " and display == " " else display)
        btn.setProperty("insert_text", insert)
        if has_ppua(insert):
            btn.setProperty("cl_tracked", True)
            track_conlang_widget(btn, GLYPH_POINT_SIZE)   # conlang first, UI fallback; follows font rebuilds
        elif btn.property("cl_tracked"):
            track_conlang_widget(btn, TEXT_POINT_SIZE)    # was a glyph key: keep the font guard, plain size
        else:
            f = QFont(self.font())
            f.setPointSize(TEXT_POINT_SIZE)
            btn.setFont(f)
        if key == self._pending_dead_key:
            btn.setStyleSheet("background: #e6a100; color: black;")
        elif key in self._active_keys:
            btn.setStyleSheet("background: #2e9d4f; color: white;")
        else:
            btn.setStyleSheet("")

    def _build_ui(self):
        self.setObjectName("OSKRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self._header = QWidget()
        self._header.setObjectName("OSKHeader")
        header = QHBoxLayout(self._header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        self._title = QLabel("On-Screen Keyboard")
        self._title.setObjectName("OSKTitle")
        header.addWidget(self._title)
        header.addStretch()
        self.combo_presets = QComboBox()
        self.combo_presets.setObjectName("OSKPresets")
        self.combo_presets.setView(QListView())          # a list view so the row height can be styled
        self.combo_presets.setMinimumWidth(230)
        self.combo_presets.setMaxVisibleItems(15)
        self.combo_presets.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # do not steal focus from the field
        self.combo_presets.setToolTip("Keyboard preset")
        track_conlang_combo(self.combo_presets, 12)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_picked)
        header.addWidget(self.combo_presets)
        if self._embedded:
            # the panel has no window title bar, so it carries its own minimize and close buttons
            self.btn_min = QToolButton()
            self.btn_min.setObjectName("OSKMin")
            self.btn_min.setText("–")
            self.btn_min.setToolTip("Minimize")
            self.btn_min.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.btn_min.clicked.connect(lambda: self.set_collapsed(not self._collapsed))
            header.addWidget(self.btn_min)
            self.btn_close = QToolButton()
            self.btn_close.setObjectName("OSKClose")
            self.btn_close.setText("✕")
            self.btn_close.setToolTip("Close")
            self.btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.btn_close.clicked.connect(self.close)
            header.addWidget(self.btn_close)
            # drag the panel by its title bar
            self._header.setCursor(Qt.CursorShape.SizeAllCursor)
            self._header.installEventFilter(self)
            self._title.installEventFilter(self)
        root.addWidget(self._header)

        self._body = QWidget()
        body = QVBoxLayout(self._body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)

        hint = QLabel("Click to insert mapped characters into focused field.")
        hint.setObjectName("OSKHint")
        hint.setWordWrap(True)
        body.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        row = 0
        total_cols = max(len(r) for r in QWERTY_ROWS)
        for keys in QWERTY_ROWS:
            for col, key in enumerate(keys):
                btn = QPushButton()
                btn.setObjectName(f"Key_{key}")
                btn.setMinimumHeight(KEY_HEIGHT)
                btn.setMinimumWidth(SPECIAL_KEY_WIDTH if key in SPECIAL_KEYS else KEY_WIDTH)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                btn.clicked.connect(lambda _checked=False, b=btn: self._insert_from_button(b))
                self._style_key(btn, key)
                if key == " ":
                    grid.addWidget(btn, row, col, 1, total_cols - col)   # space bar fills the rest of the row
                else:
                    grid.addWidget(btn, row, col)
                self._key_buttons[key] = btn
            row += 1

        # Backspace sits right after the "=" key, same size as the other keys
        backspace_btn = QPushButton()
        backspace_btn.setObjectName("Key_Backspace")
        backspace_btn.setIcon(_backspace_icon(30))
        backspace_btn.setIconSize(QSize(30, 30))
        backspace_btn.setToolTip("Backspace")
        backspace_btn.setMinimumHeight(KEY_HEIGHT)
        backspace_btn.setMinimumWidth(KEY_WIDTH)
        backspace_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        backspace_btn.clicked.connect(self._backspace)
        grid.addWidget(backspace_btn, 0, len(QWERTY_ROWS[0]))
        self._key_buttons["Backspace"] = backspace_btn

        body.addLayout(grid)
        root.addWidget(self._body)
        root.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)
        self.setStyleSheet(self._qss())

    # ---- panel behaviour (embedded mode) ---------------------------------

    @property
    def user_moved(self) -> bool:
        return self._user_moved

    def isMinimized(self) -> bool:
        # for the panel, "minimized" means only the title bar is shown
        return self._collapsed if self._embedded else super().isMinimized()

    def showNormal(self):
        if self._embedded:
            self.set_collapsed(False)
            self.show()
            self.raise_()
        else:
            super().showNormal()

    def set_collapsed(self, collapsed: bool):
        if not self._embedded:
            return
        self._collapsed = collapsed
        self._body.setVisible(not collapsed)
        self.btn_min.setText("□" if collapsed else "–")
        self.btn_min.setToolTip("Restore" if collapsed else "Minimize")
        self.layout().activate()
        self.adjustSize()
        self.layout_changed.emit()

    def eventFilter(self, obj, event):
        # drag the panel by its title bar, kept inside the parent window
        if self._embedded and obj in (self._header, self._title):
            t = event.type()
            if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_start = (event.globalPosition().toPoint(), self.pos())
                return True
            if t == QEvent.Type.MouseMove and self._drag_start is not None:
                start_global, start_pos = self._drag_start
                new = start_pos + (event.globalPosition().toPoint() - start_global)
                parent = self.parentWidget()
                if parent is not None:
                    new.setX(max(0, min(new.x(), parent.width() - self.width())))
                    new.setY(max(0, min(new.y(), parent.height() - self.height())))
                self.move(new)
                self._user_moved = True
                return True
            if t == QEvent.Type.MouseButtonRelease and self._drag_start is not None:
                self._drag_start = None
                return True
        return super().eventFilter(obj, event)

    def set_presets(self, presets, current_id: Optional[str]):
        # presets: [(id, name)]; refreshes the dropdown without firing preset_changed
        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        for pid, name in presets:
            self.combo_presets.addItem(name, pid)
        idx = self.combo_presets.findData(current_id) if current_id else -1
        if idx >= 0:
            self.combo_presets.setCurrentIndex(idx)
        self.combo_presets.blockSignals(False)
        # the dropdown list is at least as wide as the combo and fits the longest preset name
        fm = self.combo_presets.fontMetrics()
        widest = max((fm.horizontalAdvance(name) for _pid, name in presets), default=0)
        self.combo_presets.view().setMinimumWidth(max(self.combo_presets.minimumWidth(), widest + 60))

    def _on_preset_picked(self, _index: int):
        pid = self.combo_presets.currentData()
        if pid:
            self.preset_changed.emit(str(pid))

    def set_layer_state(self, overlay: Dict[str, str], active_keys, pending: Optional[str]):
        # overlay: what each key types in the active layer; active_keys: held / toggled triggers (green);
        # pending: a "once" key waiting for the next key (amber)
        self._overlay = dict(overlay or {})
        self._active_keys = set(active_keys or ())
        self._pending_dead_key = pending
        for key, btn in self._key_buttons.items():
            if key != "Backspace":
                self._style_key(btn, key)

    def highlight_key(self, key_code: str):
        btn = self._key_buttons.get(key_code)
        if btn:
            btn.setStyleSheet("background: #007acc; color: white;")
            QTimer.singleShot(150, lambda: self._style_key(btn, key_code))

    # ---- typing ----------------------------------------------------------

    def _target(self) -> Optional[QWidget]:
        return resolve_text_target(QApplication.focusWidget()) or self._last_target

    def _key_code_of(self, button: QPushButton) -> Optional[str]:
        for key, b in self._key_buttons.items():
            if b is button:
                return key
        return None

    def _insert_from_button(self, button: QPushButton):
        key_code = self._key_code_of(button)
        if self.key_handler is not None and key_code and key_code != "Backspace":
            target = self._target()
            if target is not None:
                target.setFocus()

            if self.key_handler(key_code, target):
                return
            if key_code in SPECIAL_KEYS:
                return   # an unmapped Tab / Shift / Alt types nothing
        text = button.property("insert_text")
        if text is None:
            text = button.text()
        target = self._target()
        if target is not None:
            insert_into_widget(target, str(text))
            target.setFocus()

    def _backspace(self):
        # a waiting dead key is cancelled first, like on other keyboards
        if self._pending_dead_key is not None and self.key_handler is not None \
                and self.key_handler("Backspace", None):
            return
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
        QToolButton#OSKMin, QToolButton#OSKClose {
            border: none; background: transparent; color: #555555;
            font-size: 15px; font-weight: bold; padding: 2px 8px;
        }
        QToolButton#OSKMin:hover { background: #e4e4e4; border-radius: 4px; }
        QToolButton#OSKClose:hover { background: #e5534b; color: white; border-radius: 4px; }
        QLabel#OSKHint { font-size: 10px; color: #888888; }
        QPushButton {
            background: #ffffff;
            border: 1px solid #c8c8c8;
            border-radius: 5px;
            color: #333333;
            padding: 2px;
        }
        QPushButton:hover { background: #eef4fd; border-color: #007acc; }
        QComboBox#OSKPresets {
            background: #ffffff; color: #111111; min-height: 28px;
            border: 1px solid #c8c8c8; border-radius: 5px; padding: 2px 8px;
        }
        QComboBox#OSKPresets QAbstractItemView {
            background: #ffffff; color: #111111; outline: none;
            selection-background-color: #007acc; selection-color: #ffffff;
        }
        QComboBox#OSKPresets QAbstractItemView::item { min-height: 32px; padding: 2px 8px; }
        """
