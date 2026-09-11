"""
On-screen digital keyboard (OSK) — a compact floating panel that types the
assigned character for each key into whichever text field currently has focus.

Sources:
  keyboard_repo.all_mappings_for_language(language_id)   -> key_code -> char
  font_registry.glyph_character(session_dir, glyph_id)   -> PPUA char

It uses the same row/col grid as the Keyboard Layout Mapper page (including
the wide space-row), so the on-screen layout mirrors what the user designed.
"""

import os
from PySide6.QtWidgets import (
    QWidget, QGridLayout, QPushButton, QLabel, QToolButton,
    QVBoxLayout, QHBoxLayout,
)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap

try:
    from database.keyboard_db import KeyboardRepository
    from font_tools.font_registry import glyph_character, conlang_font
except (ImportError, ValueError):
    from ..database.keyboard_db import KeyboardRepository
    from ...font_tools.font_registry import glyph_character, conlang_font

# Mirrored from keyboard_page.QWERTY_ROWS — physical layout grid.
QWERTY_ROWS = [
    ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "="],
    ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
    ["a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "BS"],
    ["z", "x", "c", "v", "b", "n", "m", ",", ".", "/", "Tab"],
    ["Space"],
]
# key_code -> (display text, span, objectName behaviour)
FILTER_KEYS = {"BS": ("⌫ Backspace", 2, "Backspace"), "Tab": ("⇥ Tab", 2, "Tab"), "Space": ("Space", 8, "Space")}

KEY_CODES = {k for row in QWERTY_ROWS for k in row}


def _render_glyph_icon(svg_data: str, size: int = 24):
    """Render an SVG glyph string into a QIcon for use on key buttons."""
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
    """Compact floating keyboard; types into QApplication.focusWidget()."""

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
        # Show without taking window activation — the user's text field must
        # keep focus while the keyboard floats above it (virtual-keyboard rule).
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # Never steal focus from the user's text field — OSK buttons must be
        # clickable while focusWidget() stays on the target editor.
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
                # NoFocus: clicking must not move focus off the text field
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

    # ---- data ----

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
                # show glyph icon if assigned to one, else the char
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
                        btn.setStyleSheet("QPushButton { background: #e3f0ff; border: 1px solid #4a90d9; border-radius: 5px; }")
                        continue
                btn.setIcon(QIcon())
                btn.setText(m["char"] if m["char"] else key)
                if m["char"] and any(ord(c) >= 0xE000 for c in m["char"]):
                    btn.setStyleSheet("QPushButton { background: #e3f0ff; border: 1px solid #4a90d9; border-radius: 5px; font-size: 18px; }")
                    try:
                        btn.setFont(conlang_font(point_size=18))
                    except Exception:
                        pass
                else:
                    btn.setStyleSheet("")
                    btn.setFont(QFont())
                btn.setToolTip(f"{key} → {m['char'] or 'glyph'}")
            else:
                btn.setIcon(QIcon())
                btn.setText(FILTER_KEYS.get(key, (key, 1, "KeyCap"))[0])
                btn.setStyleSheet("")
                btn.setFont(QFont())
                btn.setToolTip("")

    # ---- input ----

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
            # glyph without font export — fall back to PPUA text if provided
            self._insert(m.get("ppua") or "")

    def _insert(self, text: str):
        # The OSK window never takes activation (WA_ShowWithoutActivating), so
        # focusWidget() is the user's field. In offscreen tests the platform
        # may not honor that — fall back to the main window's focus if needed.
        w = self._focus_widget()
        if not w:
            # Last resort: the main window's active subwidget
            win = self.window() if self.window() != self else None
            if win is not None:
                try:
                    w = win.focusWidget()
                except Exception:
                    w = None
        if not w:
            return
        # QLineEdit/QTextEdit/QPlainTextEdit all expose insert(str)
        ins = getattr(w, "insert", None)
        if callable(ins):
            try:
                ins(text)
                return
            except Exception:
                pass
        # Fallback widgets without insert(): append via setText if available
        setter = getattr(w, "setText", None)
        getter = getattr(w, "text", None)
        if callable(setter) and callable(getter):
            try:
                setter(str(getter()) + text)
                return
            except Exception:
                pass
        # Last resort: simulate keystrokes for ASCII, skip glyphs
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