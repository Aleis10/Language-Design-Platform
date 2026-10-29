import os
import uuid
from typing import Optional, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog, QFormLayout, QLineEdit, QDialogButtonBox, QComboBox, QFrame,
    QMessageBox, QScrollArea, QToolButton, QInputDialog, QApplication, QCheckBox, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter
from digital_keyboard import (
    apply_conlang_to_fields, install_conlang_delegate, track_conlang_widget, track_conlang_combo,
)
from PySide6.QtSvg import QSvgRenderer
from ui.components.typeface_dialog import TypefaceDialog
from database.typeface_db import TypefaceRepository

try:
    from database.keyboard_db import KeyboardRepository
    from database.glyph_db import GlyphRepository
    from digital_keyboard import load_font_mapping
except (ImportError, ValueError):
    from ..database.keyboard_db import KeyboardRepository
    from ..database.glyph_db import GlyphRepository
    from ...font_tools.font_registry import load_font_mapping

QWERTY_ROWS = [
    ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Backspace"],
    ["Tab", "q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "[", "]", "\\"],
    ["Caps", "a", "s", "d", "f", "g", "h", "j", "k", "l", ";", "'", "Enter"],
    ["Shift", "z", "x", "c", "v", "b", "n", "m", ",", ".", "/", "Shift"],
    ["Alt", "      ", "Alt"],  # bottom row: one space bar between the Alt keys
]

# the left and right Shift / Alt share one key code, so they are one key for mapping purposes
NON_ASSIGNABLE = {"Enter", "Backspace", " ", "      "}

def _render_glyph_icon(svg_data: str, size: int = 40) -> Optional[QIcon]:
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

    def __init__(self, parent=None, key_code: str = "", available_glyphs=None, current: Optional[dict] = None,
                 font_mapping: Optional[Dict[str, int]] = None):
        super().__init__(parent)
        self.key_code = key_code
        self.setWindowTitle(f"Assign key: '{key_code}'")
        self.setMinimumWidth(380)
        available_glyphs = available_glyphs or []
        self.font_mapping = font_mapping or {}

        form = QFormLayout(self)

        self.combo_glyph = QComboBox()
        self.combo_glyph.addItem("(none)", None)
        for g in available_glyphs:
            name = g.get("name", "")
            meaning = g.get("meaning", "")
            label = f"{name} — {meaning}" if meaning else name
            icon = _render_glyph_icon(g.get("svg_data", ""), 24)
            self.combo_glyph.addItem(icon if icon else QIcon(), label, g.get("id"))
        form.addRow("Glyph for this key:", self.combo_glyph)
        track_conlang_combo(self.combo_glyph, 12)

        hint = QLabel("Only pick a glyph. Clicking this key will type that glyph "
                      "(after Save rebuilds the language font).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #777; font-size: 11px;")
        form.addRow(hint)

        if current and current.get("glyph_id"):
            idx = self.combo_glyph.findData(current["glyph_id"])
            if idx >= 0:
                self.combo_glyph.setCurrentIndex(idx)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)
        apply_conlang_to_fields(self, 12)

    def get_data(self):
        return {
            "assignment": "",   # glyph-only; no manual character
            "ppua": "",         # filled at font-rebuild time
            "glyph_id": self.combo_glyph.currentData(),
        }

# plain names for what a trigger key does: (stored value, label, explanation)
COMBO_MODE_ITEMS = [
    ("once", "Once (dead key)",
     "Press the trigger, release it, then press the key to combine. Works for that one key only."),
    ("hold", "Hold",
     "Keep the trigger pressed while you type. Every key you press meanwhile uses this layer."),
    ("toggle", "Toggle (lock)",
     "Press the trigger once to switch the layer on and again to switch it off, like Caps Lock."),
]
_MODE_WIDTH = 150
_SYMBOL_WIDTH = 14
_REMOVE_WIDTH = 28


class _ComboHeader(QWidget):
    # column titles; same layout as _ComboRow so every title sits above its dropdown

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        def title(text, tip=""):
            lbl = QLabel(text)
            lbl.setObjectName("KbdColTitle")
            lbl.setToolTip(tip)
            return lbl

        mode = title("Mode", "How the trigger key behaves: once, hold or toggle")
        mode.setFixedWidth(_MODE_WIDTH)
        lay.addWidget(mode)
        trigger = title("Trigger key", "The key you press first (dead key, held key or lock key)")
        trigger.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(trigger, 1)
        gap1 = QLabel("")
        gap1.setFixedWidth(_SYMBOL_WIDTH)
        lay.addWidget(gap1)
        combine = title("Combine with", "The key you press together with, or after, the trigger")
        combine.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(combine, 1)
        gap2 = QLabel("")
        gap2.setFixedWidth(_SYMBOL_WIDTH)
        lay.addWidget(gap2)
        result = title("Result", "The glyph that is typed")
        result.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lay.addWidget(result, 2)
        end = QLabel("")
        end.setFixedWidth(_REMOVE_WIDTH)
        lay.addWidget(end)


class _ComboRow(QWidget):
    # one combination: [mode] [trigger key] + [key to combine] = [result glyph]

    def __init__(self, key_items, glyph_items, mode="once", dead=None, base=None, glyph_id=None, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        self.combo_mode = QComboBox()
        self.combo_mode.setFixedWidth(_MODE_WIDTH)
        for i, (value, label, tip) in enumerate(COMBO_MODE_ITEMS):
            self.combo_mode.addItem(label, value)
            self.combo_mode.setItemData(i, tip, Qt.ItemDataRole.ToolTipRole)
        idx = self.combo_mode.findData(mode)
        self.combo_mode.setCurrentIndex(idx if idx >= 0 else 0)

        self.combo_dead = self._make_combo(key_items, "(choose key)", dead)
        self.combo_base = self._make_combo(key_items, "(choose key)", base)
        self.combo_result = self._make_combo(glyph_items, "(choose glyph)", glyph_id)

        lay.addWidget(self.combo_mode)
        lay.addWidget(self.combo_dead, 1)
        lay.addWidget(self._symbol("+"))
        lay.addWidget(self.combo_base, 1)
        lay.addWidget(self._symbol("="))
        lay.addWidget(self.combo_result, 2)
        self.btn_remove = QToolButton()
        self.btn_remove.setText("✕")
        self.btn_remove.setToolTip("Remove this combination")
        self.btn_remove.setFixedWidth(_REMOVE_WIDTH)
        lay.addWidget(self.btn_remove)

    @staticmethod
    def _symbol(text):
        lbl = QLabel(text)
        lbl.setFixedWidth(_SYMBOL_WIDTH)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return lbl

    @staticmethod
    def _make_combo(items, placeholder, selected):
        # items: [(data, text, icon-or-None)]
        combo = QComboBox()
        combo.setIconSize(QSize(24, 24))
        combo.setMinimumWidth(110)
        # width comes only from the stretch factor, so it lines up with the column title above
        combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        combo.addItem(placeholder, None)
        for data, text, icon in items:
            combo.addItem(icon if icon else QIcon(), text, data)
        if selected:
            idx = combo.findData(selected)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        track_conlang_combo(combo, 12)   # conlang characters in names must not use the wrong font
        return combo

    def mode(self):
        return self.combo_mode.currentData() or "once"

    def trigger(self):
        return self.combo_dead.currentData()

    def set_mode(self, mode):
        idx = self.combo_mode.findData(mode)
        if idx >= 0 and idx != self.combo_mode.currentIndex():
            self.combo_mode.blockSignals(True)
            self.combo_mode.setCurrentIndex(idx)
            self.combo_mode.blockSignals(False)

    def values(self):
        return {
            "mode": self.mode(),
            "dead_key_code": self.combo_dead.currentData(),
            "base_key_code": self.combo_base.currentData(),
            "result_glyph_id": self.combo_result.currentData(),
        }

    def connect_changed(self, slot):
        # base key and result: they never affect other rows
        for c in (self.combo_base, self.combo_result):
            c.currentIndexChanged.connect(slot)

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
        apply_conlang_to_fields(self, 12)

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
        self._key_buttons = {}  # key_code -> [QPushButton]  (left and right Shift/Alt share a code)
        self._current_preset_id: Optional[str] = None
        self._combo_rows = []   # _ComboRow widgets for the dead key section
        self._combo_preset_id: Optional[str] = None   # preset the rows currently belong to
        self.on_saved = None  # MainWindow sets this to refresh Conlang mappings
        self._build_ui()
        self.load_presets()
        self._load_font_mapping()
        apply_conlang_to_fields(self, 12)

    def _load_font_mapping(self):
        self._font_mapping = {}
        if not self.data_dir:
            return
        try:
            self._font_mapping = load_font_mapping(self.data_dir)
            if not self._font_mapping:
                print(f"[DEBUG-kbd1] No font mapping found in {self.data_dir}/fonts/")
        except Exception as exc:
            print(f"[DEBUG-kbd1] Font mapping load failed: {exc}")
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
        track_conlang_combo(self.combo_presets, 12)
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

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.lbl_count = QLabel("0 keys mapped")
        self.lbl_count.setObjectName("KbdCount")
        toolbar.addWidget(self.lbl_count)
        toolbar.addStretch()
        btn_typeface = QPushButton("Typeface...")
        btn_typeface.setToolTip("Change how the language font looks: scale, thickness and spacing, "
                                "with a live preview")
        btn_typeface.clicked.connect(self._open_typeface)
        toolbar.addWidget(btn_typeface)
        btn_save = QPushButton("Save")
        btn_save.setObjectName("KbdSave")
        btn_save.setToolTip("Save this preset's mappings and rebuild the language font "
                            "from ALL glyphs, so the assigned glyphs become typeable everywhere.")
        btn_save.clicked.connect(self._save_and_rebuild)
        toolbar.addWidget(btn_save)
        btn_clear = QPushButton("Clear All")
        btn_clear.clicked.connect(self._confirm_clear_all)
        toolbar.addWidget(btn_clear)
        body_layout.addLayout(toolbar)

        hint = QLabel("Click a key to assign a character, Unicode PPUA code, or glyph. Create presets for alternate layouts.")
        hint.setObjectName("KbdHint")
        body_layout.addWidget(hint)

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
                is_space = key in (" ", "      ")
                if key in NON_ASSIGNABLE:
                    btn.setText("SPACE" if is_space else key)
                    btn.setObjectName("KeyCapStatic")
                    btn.setEnabled(False)
                else:
                    btn.setText(key)
                    btn.setObjectName("KeyCapEmpty")
                    btn.setProperty("keyCode", key)
                    btn.clicked.connect(self._on_key_clicked)
                    self._key_buttons.setdefault(key, []).append(btn)
                if row in (QWERTY_ROWS[3], QWERTY_ROWS[4]):
                    # Shift row and bottom row: width comes only from the stretch factors, so
                    # an Alt key is exactly as wide as a Shift key and the space bar fills the gap
                    btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                    btn.setMinimumWidth(48)
                row_layout.addWidget(btn, 10 if is_space else 1)
            self.grid.addLayout(row_layout)
        self.grid.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.board_container)
        scroll.setObjectName("KbdScroll")
        scroll.setMinimumHeight(280)
        body_layout.addWidget(scroll, stretch=1)

        # dead key combinations: dead key + key to combine = result
        combo_head = QHBoxLayout()
        lbl_combo = QLabel("Key combinations")
        lbl_combo.setObjectName("KbdSectionTitle")
        combo_head.addWidget(lbl_combo)
        combo_head.addStretch()
        btn_add_combo = QPushButton("+ Add combination")
        btn_add_combo.clicked.connect(lambda: self._add_combo_row())
        combo_head.addWidget(btn_add_combo)
        body_layout.addLayout(combo_head)

        combo_hint = QLabel("Choose a mode, the trigger key, the key to combine with, and the result.  "
                            "Once: press the trigger, then the key.  Hold: keep the trigger pressed while "
                            "you type.  Toggle: press once to switch on, again to switch off (like Caps Lock).  "
                            "A trigger key can be empty or have its own glyph.")
        combo_hint.setObjectName("KbdHint")
        combo_hint.setWordWrap(True)
        body_layout.addWidget(combo_hint)

        self.combo_container = QWidget()
        self.combo_container.setObjectName("KbdComboList")
        self.combo_layout = QVBoxLayout(self.combo_container)
        self.combo_layout.setContentsMargins(8, 8, 8, 8)
        self.combo_layout.setSpacing(6)
        self.combo_layout.addWidget(_ComboHeader())      # column titles stay above the rows
        self.lbl_combo_empty = QLabel("No combinations yet.")
        self.lbl_combo_empty.setObjectName("KbdHint")
        self.combo_layout.addWidget(self.lbl_combo_empty)
        self.combo_layout.addStretch()
        combo_scroll = QScrollArea()
        combo_scroll.setWidgetResizable(True)
        combo_scroll.setWidget(self.combo_container)
        combo_scroll.setObjectName("KbdComboScroll")
        combo_scroll.setMinimumHeight(200)
        body_layout.addWidget(combo_scroll, stretch=2)
        root.addWidget(body, stretch=1)

        self._load_stylesheet()

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
        if callable(self.on_saved):
            self.on_saved()   # typing and the on-screen keyboard follow the selected preset

    def _on_preset_changed(self):
        preset_id = self.combo_presets.currentData()
        if preset_id:
            self._current_preset_id = preset_id
            self.refresh()
            if callable(self.on_saved):
                self.on_saved()

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
            "Remove all keyboard mappings and dead key combinations in this preset?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.keyboard_repo.clear_all_mappings(self._current_preset_id)
            self._combo_preset_id = None   # reload the (now empty) combination list
            self.refresh()
            if callable(self.on_saved):
                self.on_saved()

    def _save_and_rebuild(self):
        if not self._current_preset_id:
            QMessageBox.information(self, "No Preset", "Select or create a preset first.")
            return

        try:
            glyph_rows = self.glyph_repo.get_all_glyphs(self.language_id)
            if not glyph_rows:
                QMessageBox.warning(
                    self, "No Glyphs",
                    "No glyphs yet — draw some logograms first, then Save to build the font.",
                )
                return
            from digital_keyboard import export_language_font, get_fonts_dir, register_language_font
            fonts_dir = get_fonts_dir(self.data_dir) if self.data_dir else self.data_dir
            
            # Export font
            result = export_language_font(glyph_rows, fonts_dir, style=self._typeface_style())
            print(f"[DEBUG-kbd3] Font exported: {result.ttf_path}")
            
            # Verify TTF was created
            if not os.path.exists(result.ttf_path):
                raise FileNotFoundError(f"Font file not created: {result.ttf_path}")
            
            # Verify mapping was created
            if not os.path.exists(result.mapping_path):
                raise FileNotFoundError(f"Mapping file not created: {result.mapping_path}")
            
            # Register font with Qt
            registered = register_language_font(self.data_dir)
            if not registered:
                print(f"[DEBUG-kbd3] Font registration failed for {result.ttf_path}")
                QMessageBox.warning(
                    self, "Font Registration Failed",
                    f"Font file created but Qt couldn't register it.\n"
                    f"Glyphs may not display correctly.\n\n"
                    f"Path: {result.ttf_path}"
                )
            else:
                print(f"[DEBUG-kbd3] Font registered: {registered}")
            
            # Reload mapping
            self._load_font_mapping()
            if not self._font_mapping:
                raise RuntimeError("Font mapping is empty after rebuild")

            # Update DB with PPUA codes
            updated_count = 0
            for m in self.keyboard_repo.get_all_mappings(self._current_preset_id):
                gid = m.get("glyph_id")
                if gid and gid in self._font_mapping:
                    cp = self._font_mapping[gid]
                    self.keyboard_repo.set_mapping(
                        language_id=self.language_id,
                        preset_id=self._current_preset_id,
                        key_code=m["key_code"],
                        assignment="",           # glyph-only model
                        ppua=f"U+{cp:04X}",       # internal plumbing filled here
                        glyph_id=gid,
                        key_label=m["key_code"],
                    )
                    updated_count += 1

            QMessageBox.information(
                self,
                "Layout Saved",
                f"✓ Font rebuilt: {result.num_glyphs} glyphs\n"
                f"✓ Mappings updated: {updated_count} keys\n"
                f"✓ Font registered: {registered or result.family_name}\n\n"
                f"Click the button on the bottom right to activate Digital Keyboard"
            )
            if callable(self.on_saved):
                self.on_saved()
        except Exception as exc:
            import traceback
            print(f"[DEBUG-kbd3] Rebuild failed: {exc}")
            print(traceback.format_exc())
            QMessageBox.critical(self, "Rebuild Failed", f"Could not rebuild font:\n{exc}")
        self.refresh()

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
        for key_code, btns in self._key_buttons.items():
            m = mappings.get(key_code)
            is_mapped = bool(m and (m.get("assignment") or m.get("glyph_id")))
            if is_mapped:
                mapped += 1
            icon = None
            if is_mapped and m.get("glyph_id"):
                glyph = self.keyboard_repo.get_glyph(m["glyph_id"])
                icon = _render_glyph_icon(glyph.get("svg_data", ""), 32) if glyph else None
            for btn in btns:
                if is_mapped:
                    self._set_key_style(btn, "KeyCapAssigned")
                    if m.get("glyph_id"):
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
        self._rebuild_combo_rows()

    # typeface (how the language font looks)

    def _typeface_repo(self) -> TypefaceRepository:
        if getattr(self, "_typeface_repository", None) is None:
            self._typeface_repository = TypefaceRepository(self.keyboard_repo.db_manager)
        return self._typeface_repository

    def _typeface_style(self) -> Dict[str, Any]:
        from digital_keyboard import normalize_style
        try:
            return normalize_style(self._typeface_repo().get(self.language_id))
        except Exception as exc:
            print(f"[DEBUG-kbd3] Could not read the typeface settings: {exc}")
            return normalize_style(None)

    def _open_typeface(self):
        from digital_keyboard import get_fonts_dir
        try:
            glyph_rows = self.glyph_repo.get_all_glyphs(self.language_id)
        except Exception as exc:
            QMessageBox.warning(self, "Typeface", f"Could not read the glyphs:\n{exc}")
            return
        if not glyph_rows:
            QMessageBox.information(self, "No Glyphs", "Draw some logograms first, then come back to the Typeface.")
            return
        fonts_dir = get_fonts_dir(self.data_dir) if self.data_dir else self.data_dir
        dialog = TypefaceDialog(glyph_rows, fonts_dir, self._typeface_style(), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._typeface_repo().save(self.language_id, dialog.style())
        except Exception as exc:
            QMessageBox.critical(self, "Typeface", f"Could not save the settings:\n{exc}")
            return
        self._rebuild_font_only()

    def _rebuild_font_only(self):
        # rebuild and register the language font with the saved typeface settings (key assignments are not touched)
        try:
            from digital_keyboard import export_language_font, get_fonts_dir, register_language_font
            glyph_rows = self.glyph_repo.get_all_glyphs(self.language_id)
            fonts_dir = get_fonts_dir(self.data_dir) if self.data_dir else self.data_dir
            result = export_language_font(glyph_rows, fonts_dir, style=self._typeface_style())
            registered = register_language_font(self.data_dir)
            if not registered:
                QMessageBox.warning(
                    self, "Font Registration Failed",
                    f"The font was built but Qt could not register it.\n\nPath: {result.ttf_path}")
            self._load_font_mapping()
            QMessageBox.information(
                self, "Typeface Saved",
                f"The language font was rebuilt with the new look ({result.num_glyphs} glyphs).")
            if callable(self.on_saved):
                self.on_saved()
        except Exception as exc:
            import traceback
            print(f"[DEBUG-kbd3] Typeface rebuild failed: {exc}")
            print(traceback.format_exc())
            QMessageBox.critical(self, "Typeface", f"Could not rebuild the font:\n{exc}")
        self.refresh()

    # dead key combinations

    def _combo_key_items(self, mappings):
        # every assignable key: shown with its glyph when it has one, otherwise marked empty
        items = []
        seen = set()
        for row in QWERTY_ROWS:
            for key in row:
                if key in NON_ASSIGNABLE or key.strip() == "" or key in seen:
                    continue
                seen.add(key)
                m = mappings.get(key)
                icon = None
                text = f"{key}  (empty)"
                if m and m.get("glyph_id"):
                    glyph = self.keyboard_repo.get_glyph(m["glyph_id"])
                    icon = _render_glyph_icon(glyph.get("svg_data", ""), 24) if glyph else None
                    text = f"{key}" if icon else f"{key}  (glyph)"
                elif m and m.get("assignment"):
                    text = f"{key}  {m['assignment']}"
                items.append((key, text, icon))
        return items

    def _combo_glyph_items(self):
        items = []
        for g in self.keyboard_repo.unassigned_glyphs(self.language_id):
            name = g.get("name", "")
            meaning = g.get("meaning", "")
            label = f"{name} — {meaning}" if meaning else name
            items.append((g.get("id"), label, _render_glyph_icon(g.get("svg_data", ""), 24)))
        return items

    def _collect_combo_state(self):
        return [r.values() for r in self._combo_rows]

    def _rebuild_combo_rows(self):
        # rebuild from the screen when it is the same preset (keeps half filled rows), else from the DB
        if not self._current_preset_id:
            return
        if self._combo_preset_id == self._current_preset_id:
            state = self._collect_combo_state()
        else:
            state = [
                {"mode": c.get("mode") or "once", "dead_key_code": c["dead_key_code"],
                 "base_key_code": c["base_key_code"], "result_glyph_id": c["result_glyph_id"]}
                for c in self.keyboard_repo.get_dead_combos(self._current_preset_id)
            ]
        mappings = {m["key_code"]: m for m in self.keyboard_repo.get_all_mappings(self._current_preset_id)}
        self._key_items = self._combo_key_items(mappings)
        self._glyph_items = self._combo_glyph_items()
        for r in self._combo_rows:
            self.combo_layout.removeWidget(r)
            r.setParent(None)
            r.deleteLater()
        self._combo_rows = []
        self._combo_preset_id = self._current_preset_id
        for v in state:
            self._add_combo_row(v.get("dead_key_code"), v.get("base_key_code"),
                                v.get("result_glyph_id"), v.get("mode") or "once", save=False)
        self._update_combo_empty_label()

    def _add_combo_row(self, dead=None, base=None, glyph_id=None, mode="once", save=True):
        if not self._current_preset_id:
            return
        if not hasattr(self, "_key_items"):
            self._rebuild_combo_rows()
        row = _ComboRow(self._key_items, self._glyph_items, mode, dead, base, glyph_id)
        row.connect_changed(self._on_combos_changed)
        row.combo_mode.currentIndexChanged.connect(lambda _=0, r=row: self._on_mode_changed(r))
        row.combo_dead.currentIndexChanged.connect(lambda _=0, r=row: self._on_trigger_changed(r))
        row.btn_remove.clicked.connect(lambda _=False, r=row: self._remove_combo_row(r))
        # rows go after the column titles and before the empty label and the stretch
        self.combo_layout.insertWidget(1 + len(self._combo_rows), row)
        self._combo_rows.append(row)
        self._update_combo_empty_label()
        if save:
            self._on_combos_changed()

    def _remove_combo_row(self, row):
        if row in self._combo_rows:
            self._combo_rows.remove(row)
        self.combo_layout.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._update_combo_empty_label()
        self._on_combos_changed()

    def _on_mode_changed(self, row):
        # one trigger key has one mode, so the other rows with the same trigger follow this row
        trigger = row.trigger()
        if trigger:
            for other in self._combo_rows:
                if other is not row and other.trigger() == trigger:
                    other.set_mode(row.mode())
        self._on_combos_changed()

    def _on_trigger_changed(self, row):
        # a trigger that is already used keeps the mode it already has
        trigger = row.trigger()
        if trigger:
            for other in self._combo_rows:
                if other is not row and other.trigger() == trigger:
                    row.set_mode(other.mode())
                    break
        self._on_combos_changed()

    def _update_combo_empty_label(self):
        self.lbl_combo_empty.setVisible(not self._combo_rows)

    def _on_combos_changed(self, *_):
        # only complete rows are stored; half filled rows stay on screen until finished
        if not self._current_preset_id:
            return
        complete = [v for v in self._collect_combo_state()
                    if v["dead_key_code"] and v["base_key_code"] and v["result_glyph_id"]]
        self.keyboard_repo.replace_all_dead_combos(self.language_id, self._current_preset_id, complete)
        if callable(self.on_saved):
            self.on_saved()
