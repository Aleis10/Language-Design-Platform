import os
import uuid
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QComboBox, QFrame,
    QMessageBox, QScrollArea, QToolButton, QInputDialog,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

try:
    from database.keyboard_db import KeyboardRepository
    from database.glyph_db import GlyphRepository
    from font_tools.font_registry import load_font_mapping
except (ImportError, ValueError):
    from ..database.keyboard_db import KeyboardRepository
    from ..database.glyph_db import GlyphRepository
    from ...font_tools.font_registry import load_font_mapping


# Standard QWERTY layout (physical -> single-row)
QWERTY_ROWS = [
    ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Backspace"],
    ["Tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
    ["Caps", "a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "Enter"],
    ["Shift", "z", "x", "c", "v", "b", "n", "m", ",", ".", "/", "Shift"],
    ["      ", "      "],  # space row
]

NON_ASSIGNABLE = {"Tab", "Caps", "Shift", "Enter", "Backspace", " ", "      "}


def _render_glyph_icon(svg_data: str, size: int = 40) -> Optional[QIcon]:
    """Render an SVG glyph string into a QIcon for display on key buttons."""
    if not svg_data or not svg_data.strip():
        return None
    try:
        renderer = QSvgRenderer(svg_data.encode("utf-8"))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)
    except Exception:
        return None


class _AssignDialog(QDialog):
    def __init__(self, parent=None, key_code: str = "", available_glyphs=None, current: Optional[dict] = None, font_mapping: Optional[Dict[str, int]] = None):
        super().__init__(parent)
        self.key_code = key_code
        self.setWindowTitle(f"Assign key: '{key_code}'")
        self.setMinimumWidth(380)
        available_glyphs = available_glyphs or []
        # glyph_id -> PPUA codepoint (from the exported font's .mapping.json)
        self.font_mapping = font_mapping or {}

        form = QFormLayout(self)

        self.input_text = QLineEdit()
        self.input_text.setPlaceholderText("Character / text this key outputs")
        form.addRow("Assigned Character:", self.input_text)

        self.input_ppua = QLineEdit()
        self.input_ppua.setPlaceholderText("e.g. U+E000 - U+F8FF (Private Use Area)")
        form.addRow("Unicode PPUA:", self.input_ppua)

        # Glyph picker with previews
        self.combo_glyph = QComboBox()
        self.combo_glyph.addItem("(none)", None)
        for g in available_glyphs:
            name = g.get("name", "")
            meaning = g.get("meaning", "")
            label = f"{name} — {meaning}" if meaning else name
            icon = _render_glyph_icon(g.get("svg_data", ""), 24)
            self.combo_glyph.addItem(icon if icon else QIcon(), label, g.get("id"))
        form.addRow("Link Glyph:", self.combo_glyph)

        if current:
            self.input_text.setText(current.get("assignment", ""))
            self.input_ppua.setText(current.get("ppua", ""))
            if current.get("glyph_id"):
                idx = self.combo_glyph.findData(current["glyph_id"])
                if idx >= 0:
                    self.combo_glyph.setCurrentIndex(idx)

        # Automate PPUA: picking a glyph fills the PPUA box with its codepoint
        self.combo_glyph.currentIndexChanged.connect(self._on_glyph_changed)
        self._sync_ppua_from_glyph()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _on_glyph_changed(self):
        self._sync_ppua_from_glyph()

    def _sync_ppua_from_glyph(self):
        gid = self.combo_glyph.currentData()
        if gid and gid in self.font_mapping:
            cp = self.font_mapping[gid]
            # U+E000 style label; also store raw int for get_data()
            self.input_ppua.setText(f"U+{cp:04X}")

    def get_data(self):
        # Resolve raw codepoint from the PPUA label we auto-filled
        ppua_raw = self.input_ppua.text().strip()
        # Accept either a hex codepoint label or an integer (text like U+E000)
        gid = self.combo_glyph.currentData()
        if gid and gid in self.font_mapping:
            ppua_raw = f"U+{self.font_mapping[gid]:04X}"
        return {
            "assignment": self.input_text.text().strip(),
            "ppua": ppua_raw,
            "glyph_id": gid,
        }


class _PresetDialog(QDialog):
    def __init__(self, parent=None, name: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Name Preset") if not name else self.setWindowTitle("Rename Preset")
        self.setMinimumWidth(280)
        form = QFormLayout(self)
        self.input_name = QLineEdit()
        self.input_name.setText(name)
        self.input_name.setPlaceholderText("e.g. Default, Numeral, Cursive...")
        form.addRow("Preset Name:", self.input_name)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def get_name(self):
        return self.input_name.text().strip()


class KeyboardPage(QWidget):
    def __init__(self, keyboard_repo: KeyboardRepository, glyph_repo: GlyphRepository, language_id: str, parent=None,
                 data_dir: str = ""):
        super().__init__(parent)
        self.keyboard_repo = keyboard_repo
        self.glyph_repo = glyph_repo
        self.language_id = language_id
        self.data_dir = data_dir
        self._font_mapping = {}
        self._key_buttons = {}  # key_code -> QPushButton
        self._current_preset_id: Optional[str] = None
        self._build_ui()
        self.load_presets()
        self._load_font_mapping()

    def _load_font_mapping(self):
        """glyph_id -> PPUA codepoint from the exported font's .mapping.json."""
        self._font_mapping = {}
        if not self.data_dir:
            return
        try:
            self._font_mapping = load_font_mapping(self.data_dir)
        except Exception:
            self._font_mapping = {}

    def _load_stylesheet(self):
        style_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "keyboard_page.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar (white, full width): title + preset controls
        header_bar = QWidget()
        header_bar.setObjectName("KbdTopBar")
        header = QHBoxLayout(header_bar)
        header.setContentsMargins(20, 12, 20, 12)
        header.setSpacing(10)

        lbl = QLabel("Keyboard Layout Mapper")
        lbl.setObjectName("KbdTitle")
        header.addWidget(lbl)

        header.addSpacing(16)
        header.addWidget(QLabel("Preset:"))

        self.combo_presets = QComboBox()
        self.combo_presets.setMinimumWidth(160)
        self.combo_presets.currentIndexChanged.connect(self._on_preset_changed)
        header.addWidget(self.combo_presets)

        btn_add_preset = QPushButton("+ New Preset")
        btn_add_preset.clicked.connect(self._add_preset)
        header.addWidget(btn_add_preset)

        btn_rename_preset = QPushButton("Rename")
        btn_rename_preset.clicked.connect(self._rename_preset)
        header.addWidget(btn_rename_preset)

        btn_delete_preset = QPushButton("Delete")
        btn_delete_preset.setObjectName("KbdDeletePreset")
        btn_delete_preset.clicked.connect(self._delete_preset)
        header.addWidget(btn_delete_preset)

        header.addStretch()
        root.addWidget(header_bar)

        # Body container (padding under the bar)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(10)

        # Second tool row: mapped count + clear all
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.lbl_count = QLabel("0 keys mapped")
        self.lbl_count.setObjectName("KbdCount")
        toolbar.addWidget(self.lbl_count)
        toolbar.addStretch()
        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self._confirm_clear_all)
        toolbar.addWidget(btn_clear)
        body_layout.addLayout(toolbar)

        hint = QLabel("Click a key to assign a character, Unicode PPUA code, or glyph. Create presets for alternate layouts.")
        hint.setObjectName("KbdHint")
        body_layout.addWidget(hint)

        # Keyboard board
        self.board_container = QWidget()
        self.board_container.setObjectName("KbdBoard")
        self.grid = QVBoxLayout(self.board_container)
        self.grid.setSpacing(5)
        for row in QWERTY_ROWS:
            row_layout = QHBoxLayout()
            row_layout.setSpacing(5)
            for key in row:
                btn = QToolButton() if key in NON_ASSIGNABLE else QPushButton()
                btn.setMinimumHeight(44)
                if key in NON_ASSIGNABLE or key in (" ", "      "):
                    btn.setText("SPACE" if key in (" ", "      ") else key)
                    btn.setObjectName("KeyCapStatic")
                    btn.setEnabled(False)
                else:
                    btn.setText(key)
                    btn.setObjectName("KeyCapEmpty")
                    btn.setProperty("keyCode", key)
                    btn.clicked.connect(self._on_key_clicked)
                    self._key_buttons[key] = btn
                row_layout.addWidget(btn)
            self.grid.addLayout(row_layout)
        self.grid.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.board_container)
        scroll.setObjectName("KbdScroll")
        body_layout.addWidget(scroll, stretch=1)
        root.addWidget(body, stretch=1)

        self._load_stylesheet()

    # ---- Presets ----

    def load_presets(self):
        presets = self.keyboard_repo.get_presets(self.language_id)
        if not presets:
            preset_id = self.keyboard_repo.get_or_create_default_preset(self.language_id)
            presets = self.keyboard_repo.get_presets(self.language_id)

        self.combo_presets.blockSignals(True)
        self.combo_presets.clear()
        for p in presets:
            self.combo_presets.addItem(p["name"], p["id"])
        self.combo_presets.blockSignals(False)

        # Select first preset (or keep current if still exists)
        if self._current_preset_id:
            idx = self.combo_presets.findData(self._current_preset_id)
            if idx >= 0:
                self.combo_presets.setCurrentIndex(idx)
                self._switch_preset(self._current_preset_id)
                return
        if self.combo_presets.count() > 0:
            self.combo_presets.setCurrentIndex(0)
            self._switch_preset(self.combo_presets.currentData())

    def _switch_preset(self, preset_id: Optional[str]):
        self._current_preset_id = preset_id
        self.refresh()

    def _on_preset_changed(self):
        preset_id = self.combo_presets.currentData()
        if preset_id:
            self._current_preset_id = preset_id
            self.refresh()

    def _add_preset(self):
        dlg = _PresetDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.get_name()
            if not name:
                return
            new_id = self.keyboard_repo.create_preset(self.language_id, name)
            self._current_preset_id = new_id
            self.load_presets()

    def _rename_preset(self):
        preset_id = self.combo_presets.currentData()
        if not preset_id:
            return
        current_name = self.combo_presets.currentText()
        dlg = _PresetDialog(self, name=current_name)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name = dlg.get_name()
            if name:
                self.keyboard_repo.rename_preset(preset_id, name)
                self.load_presets()

    def _delete_preset(self):
        preset_id = self.combo_presets.currentData()
        if not preset_id:
            return
        res = QMessageBox.question(
            self, "Delete Preset",
            f"Delete preset '{self.combo_presets.currentText()}' and all its mappings?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.keyboard_repo.delete_preset(preset_id)
            self._current_preset_id = None
            self.load_presets()

    # ---- Key mapping ----

    def _on_key_clicked(self):
        btn = self.sender()
        if not btn:
            return
        key_code = btn.property("keyCode")
        if not self._current_preset_id:
            return
        current = self.keyboard_repo.get_mapping(self._current_preset_id, key_code)
        glyphs = self.keyboard_repo.unassigned_glyphs(self.language_id)
        dlg = _AssignDialog(self, key_code=key_code, current=current, available_glyphs=glyphs,
                            font_mapping=self._font_mapping)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data["assignment"] or data["glyph_id"]:
                self.keyboard_repo.set_mapping(
                    language_id=self.language_id,
                    preset_id=self._current_preset_id,
                    key_code=key_code,
                    assignment=data["assignment"],
                    ppua=data["ppua"],
                    glyph_id=data["glyph_id"],
                    key_label=key_code,
                )
            else:
                self.keyboard_repo.clear_mapping(self._current_preset_id, key_code)
            self.refresh()

    def _confirm_clear_all(self):
        if not self._current_preset_id:
            return
        res = QMessageBox.question(
            self, "Clear All Maps",
            "Remove all keyboard mappings in this preset?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.keyboard_repo.clear_all_mappings(self._current_preset_id)
            self.refresh()

    # ---- Refresh ----

    def _set_key_style(self, btn, object_name: str):
        btn.setObjectName(object_name)
        btn.style().unpolish(btn)
        btn.style().polish(btn)

    def refresh(self):
        if not self._current_preset_id:
            return
        mappings = {
            m["key_code"]: m
            for m in self.keyboard_repo.get_all_mappings(self._current_preset_id)
        }
        mapped = 0
        for key_code, btn in self._key_buttons.items():
            m = mappings.get(key_code)
            if m and (m.get("assignment") or m.get("glyph_id")):
                mapped += 1
                self._set_key_style(btn, "KeyCapAssigned")
                # Show glyph icon (preferred) or assigned character
                if m.get("glyph_id"):
                    glyph = self.keyboard_repo.get_glyph(m["glyph_id"])
                    icon = _render_glyph_icon(glyph.get("svg_data", ""), 32) if glyph else None
                    if icon:
                        btn.setIcon(icon)
                        btn.setIconSize(QSize(32, 32))
                        btn.setText("")  # show only the glyph icon
                    else:
                        btn.setText("glyph")
                        btn.setIcon(QIcon())
                elif m.get("assignment"):
                    btn.setText(m["assignment"])
                    btn.setIcon(QIcon())
                btn.setToolTip(
                    f"key '{key_code}' → {m.get('assignment') or 'glyph'}"
                    + (f"  {m.get('ppua')}" if m.get("ppua") else "")
                )
            else:
                self._set_key_style(btn, "KeyCapEmpty")
                btn.setText(key_code)
                btn.setIcon(QIcon())
                btn.setToolTip("")
        self.lbl_count.setText(f"{mapped} keys mapped")