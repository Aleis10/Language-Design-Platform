
import os
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QPushButton, QLabel, QToolButton,
    QVBoxLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap

try:
    from database.keyboard_db import KeyboardRepository
    from digital_keyboard import glyph_character, conlang_font
except (ImportError, ValueError):
    from ..database.keyboard_db import KeyboardRepository
    from ...digital_keyboard import glyph_character, conlang_font

QWERTY_ROWS = [
    ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "BS"],
    ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/", "Tab"],
    ["Space"],
]
FILTER_KEYS = {"BS": ("⌫ Backspace", 2, "Backspace"), "Tab": ("⇥ Tab", 2, "Tab"), "Space": ("Space", 8, "Space")}

KEY_CODES = {k for row in QWERTY_ROWS for k in row}

def _render_glyph_icon(svg_data: str, size: int = 24):
    if not svg_data or not svg_data.strip():
        return None
    try:
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import Qt as _Qt
        renderer = QSvgRenderer(svg_data.encode("utf-8"))
        pm = QPixmap(size, size)
        pm.fill(_Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        return QIcon(pm)
    except Exception:
        return None

class OnScreenKeyboard(QWidget):

    closed = Signal()

    def __init__(self, keyboard_repo, language_id: str, session_dir: str = "", parent=None):
        super().__init__(parent)
        self.keyboard_repo = keyboard_repo
        self.language_id = language_id
        self.session_dir = session_dir
        self._key_buttons = {}
        self._mappings = {}
        self._conlang_family = None

        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Digital Keyboard")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._build_ui()
        self.reload_mappings()

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def _build_ui(self):
        self.setObjectName("OSKRoot")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        lbl = QLabel("Digital Keyboard")
        lbl.setObjectName("OSKTitle")
        header.addWidget(lbl)
        header.addStretch()
        btn_close = QToolButton()
        btn_close.setText("✕")
        btn_close.setObjectName("OSKClose")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.close)
        header.addWidget(btn_close)
        root.addLayout(header)

        hint = QLabel("Assign keys in Keyboard → Layout Mapper. Types into the focused field.")
        hint.setObjectName("OSKHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(5)
        grid.setContentsMargins(0, 0, 0, 0)

        row = 0
        for keys in QWERTY_ROWS:
            col = 0
            for key in keys:
                display, span, obj_name = FILTER_KEYS.get(key, (key, 1, "KeyCap"))
                btn = QPushButton(display)
                btn.setObjectName(obj_name)
                btn.setMinimumHeight(34)
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                if obj_name == "Backspace":
                    btn.setToolTip("Backspace")
                elif obj_name == "Tab":
                    btn.setToolTip("Tab")
                elif obj_name == "Space":
                    btn.setToolTip("Space")
                btn.clicked.connect(self._on_key)
                grid.addWidget(btn, row, col, 1, span)
                self._key_buttons[key] = btn
                col += span
            row += 1
        grid.setColumnStretch(6, 1)  # keep layout left-aligned
        root.addLayout(grid)

        self.setStyleSheet(self._qss())

    def _qss(self) -> str:
        return """
        QWidget#OSKRoot {
            background-color: #f7f7f7;
            border: 1px solid #c8c8c8;
            border-radius: 10px;
        }
        QLabel#OSKTitle {
            font-size: 13px;
            font-weight: bold;
            color: #111111;
        }
        QLabel#OSKHint {
            font-size: 10px;
            color: #888888;
        }
        QPushButton#KeyCap {
            background: #ffffff;
            border: 1px solid #c8c8c8;
            border-radius: 5px;
            font-size: 12px;
            color: #333333;
            padding: 2px;
        }
        QPushButton#KeyCap:hover {
            background: #eef4fd;
            border-color: #007acc;
        }
        QPushButton#Backspace, QPushButton#Tab {
            background: #ececec;
            border: 1px solid #d0d0d0;
            border-radius: 5px;
            font-size: 11px;
            color: #666666;
        }
        QPushButton#Space {
            background: #ffffff;
            border: 1px solid #c8c8c8;
            border-radius: 5px;
            font-size: 11px;
            color: #999999;
        }
        QPushButton#Space:hover {
            background: #eef4fd;
        }
        QToolButton#OSKClose {
            border: none;
            background: transparent;
            color: #666666;
            font-size: 14px;
            font-weight: bold;
        }
        QToolButton#OSKClose:hover {
            color: #c0392b;
        }
        """

    def reload_mappings(self):
        self._mappings = {}
        try:
            rows = self.keyboard_repo.all_mappings_for_language(self.language_id)
        except Exception:
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
            self._mappings[key_code] = {
                "char": char,
                "glyph_id": m.get("glyph_id"),
                "ppua": m.get("ppua") or "",
            }
        self._paint_keys()

    def _paint_keys(self):
        for key, btn in self._key_buttons.items():
            if key not in KEY_CODES:
                continue
            m = self._mappings.get(key)
            if m and (m["char"] or m["glyph_id"]):
                if m["glyph_id"] and self.session_dir:
                    svg = ""
                    try:
                        g = self.keyboard_repo.get_glyph(m["glyph_id"])
                        svg = g.get("svg_data", "") if g else ""
                    except Exception:
                        svg = ""
                    icon = _render_glyph_icon(svg, 22) if svg else None
                    if icon:
                        btn.setText("")
                        btn.setIcon(icon)
                        btn.setIconSize(QSize(22, 22))
                        btn.setObjectName("KeyCapGlyph")
                        btn.setStyleSheet("QPushButton#KeyCapGlyph { background: #e3f0ff; border: 1px solid #4a90d9; border-radius: 5px; }\nQPushButton#KeyCapGlyph:hover { background: #d4e6f1; }")
                        continue
                btn.setIcon(QIcon())
                btn.setText(m["char"] if m["char"] else key)
                if m["char"] and any(ord(c) >= 0xE000 for c in m["char"]):
                    btn.setObjectName("KeyCapGlyph")
                    btn.setStyleSheet("QPushButton#KeyCapGlyph { background: #e3f0ff; border: 1px solid #4a90d9; border-radius: 5px; font-size: 18px; }\nQPushButton#KeyCapGlyph:hover { background: #d4e6f1; }")
                    try:
                        btn.setFont(conlang_font(point_size=18))
                    except Exception:
                        pass
                else:
                    btn.setObjectName("KeyCap")
                    btn.setStyleSheet("")
                    btn.setFont(QFont())
                btn.setToolTip(f"{key} → {m['char'] or 'glyph'}")
            else:
                btn.setIcon(QIcon())
                btn.setText(FILTER_KEYS.get(key, (key, 1, "KeyCap"))[0])
                btn.setObjectName("KeyCap")
                btn.setStyleSheet("")
                btn.setFont(QFont())
                btn.setToolTip("")

    def _on_key(self):
        btn = self.sender()
        if not btn:
            return
        key = next((k for k, b in self._key_buttons.items() if b is btn), None)
        if key is None:
            return
        if key == "BS":
            self._send_key(Qt.Key.Key_Backspace)
            return
        if key == "Tab":
            self._send_key(Qt.Key.Key_Tab)
            return
        if key == "Space":
            self._insert(" ")
            return
        m = self._mappings.get(key)
        if m and m["char"]:
            self._insert(m["char"])
        elif m and m["glyph_id"]:
            self._insert(m.get("ppua") or "")

    def _insert(self, text: str):
        w = self._focus_widget()
        if not w:
            win = self.window() if self.window() != self else None
            if win is not None:
                try:
                    w = win.focusWidget()
                except Exception:
                    w = None
        if not w:
            return
        ins = getattr(w, "insert", None)
        if callable(ins):
            try:
                ins(text)
                return
            except Exception:
                pass
        setter = getattr(w, "setText", None)
        getter = getattr(w, "text", None)
        if callable(setter) and callable(getter):
            try:
                setter(str(getter()) + text)
                return
            except Exception:
                pass
        for ch in text:
            if ch.isascii():
                try:
                    self._send_key(Qt.Key.Key_A + (ord(ch.upper()) - ord('A')) if ch.isalpha() else None)
                except Exception:
                    pass

    def _focus_widget(self):
        from PySide6.QtWidgets import QApplication
        w = QApplication.focusWidget()
        if w is not None and hasattr(w, "insert") and not isinstance(w, QPushButton) and not isinstance(w, QToolButton):
            return w
        if w is not None and hasattr(w, "setText") and not isinstance(w, QPushButton) and not isinstance(w, QToolButton):
            return w
        return None

    def _send_key(self, qkey):
        from PySide6.QtWidgets import QApplication
        w = QApplication.focusWidget()
        if not w:
            return
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        press = QKeyEvent(QEvent.Type.KeyPress, qkey, Qt.KeyboardModifier.NoModifier)
        release = QKeyEvent(QEvent.Type.KeyRelease, qkey, Qt.KeyboardModifier.NoModifier)
        try:
            QApplication.sendEvent(w, press)
            QApplication.sendEvent(w, release)
        except Exception:
            pass

    def highlight_key(self, key_code: str):
        btn = self._key_buttons.get(key_code)
        if btn is not None:
            self._highlight_btn(btn)

    def clear_highlight(self):
        for btn in self._key_buttons.values():
            self._unhighlight_btn(btn)

    def _highlight_btn(self, btn):
        try:
            btn.setProperty("pressedX", True)
            btn.setStyleSheet(
                "QPushButton { background:#cfe8ff; border:2px solid #007acc; border-radius:5px; }"
            )
        except Exception:
            pass

    def _unhighlight_btn(self, btn):
        try:
            btn.setProperty("pressedX", False)
        except Exception:
            pass
        self._repaint_key(btn)

    def _repaint_key(self, btn):
        try:
            key = next((k for k, b in self._key_buttons.items() if b is btn), None)
            if key is None:
                return
            m = self._mappings.get(key)
            if m and (m.get("char") or m.get("glyph_id")):
                self._paint_key_btn(btn, key, m)
            else:
                btn.setStyleSheet("")
                btn.setFont(QFont())
        except Exception:
            pass

    def _paint_key_btn(self, btn, key, m):
        if m.get("glyph_id") and self.session_dir:
            svg = ""
            try:
                g = self.keyboard_repo.get_glyph(m["glyph_id"])
                svg = g.get("svg_data", "") if g else ""
            except Exception:
                svg = ""
            icon = _render_glyph_icon(svg, 22) if svg else None
            if icon:
                btn.setText("")
                btn.setIcon(icon)
                btn.setIconSize(QSize(22, 22))
                btn.setObjectName("KeyCapGlyph")
                btn.setStyleSheet("QPushButton#KeyCapGlyph { background: #e3f0ff; border: 1px solid #4a90d9; border-radius: 5px; }\nQPushButton#KeyCapGlyph:hover { background: #d4e6f1; }")
                return
        btn.setIcon(QIcon())
        btn.setText(m["char"] if m["char"] else key)
        if m["char"] and any(ord(c) >= 0xE000 for c in m["char"]):
            btn.setObjectName("KeyCapGlyph")
            btn.setStyleSheet("QPushButton#KeyCapGlyph { background: #e3f0ff; border: 1px solid #4a90d9; border-radius: 5px; font-size: 18px; }\nQPushButton#KeyCapGlyph:hover { background: #d4e6f1; }")
            try:
                btn.setFont(conlang_font(point_size=18))
            except Exception:
                pass
        else:
            btn.setObjectName("KeyCap")
            btn.setStyleSheet("")
            btn.setFont(QFont())
            btn.setStyleSheet("")
            btn.setFont(QFont())