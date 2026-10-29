import os
import shutil
import tempfile
import traceback
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from digital_keyboard import DEFAULT_STYLE, RANGES, build_preview_font, normalize_style, register_preview_font
from .flow_layout import FlowLayout
from .tool_icons import asset_icon

# The Typeface window: change how the language font looks (scale, thickness, gap between glyphs, width of a
# space) and watch a test text change while you drag. Nothing is saved until Save is pressed. The window
# blocks the rest of the app while it is open, which keeps it simple.

PREVIEW_DELAY_MS = 250      # the preview is rebuilt this long after the last slider move
DEFAULT_PREVIEW_SIZE = 32   # points


class TypefaceDialog(QDialog):
    def __init__(self, glyph_rows: List[Dict[str, Any]], fonts_dir: str, style: Optional[Dict[str, Any]] = None,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Typeface")
        self.setModal(True)
        self.resize(780, 700)
        self.glyph_rows = glyph_rows
        self.fonts_dir = fonts_dir
        self._tmp_dir = tempfile.mkdtemp(prefix="typeface_preview_")
        self._build_count = 0
        self._family: Optional[str] = None
        self._mapping: Dict[str, int] = {}
        self._glyph_buttons: List[QPushButton] = []
        self._sliders: Dict[str, QSlider] = {}
        self._value_labels: Dict[str, QLabel] = {}

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PREVIEW_DELAY_MS)
        self._timer.timeout.connect(self._rebuild_preview)

        self._build_ui()
        self._load_style(normalize_style(style))
        self.setStyleSheet(self._qss())
        self._rebuild_preview()

    # ---------------------------------------------------------------- layout
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)

        title = QLabel("Typeface")
        title.setObjectName("TfTitle")
        root.addWidget(title)
        hint = QLabel("Click glyphs or type below to test the text. Move the sliders to change the font; "
                      "nothing is saved until you press Save.")
        hint.setObjectName("TfHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # the test text: three lines
        self.test_text = QPlainTextEdit()
        self.test_text.setObjectName("TfTest")
        self.test_text.setPlaceholderText("Test text: click the glyphs below, or type here.")
        root.addWidget(self.test_text)

        # a row of tools for the test text
        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.btn_all = QPushButton("Insert all glyphs")
        self.btn_all.setToolTip("Adds every glyph, separated by spaces, to check spacing and word gaps")
        self.btn_all.clicked.connect(self._insert_all)
        self.btn_space = QPushButton("Space")
        self.btn_space.clicked.connect(lambda: self._insert(" "))
        self.btn_newline = QPushButton("New line")
        self.btn_newline.clicked.connect(lambda: self._insert("\n"))
        self.btn_back = QPushButton()
        self.btn_back.setIcon(asset_icon("backspace.svg"))
        self.btn_back.setIconSize(QSize(18, 18))
        self.btn_back.setToolTip("Backspace")
        self.btn_back.clicked.connect(self._backspace)
        self.btn_clear = QPushButton("Clear text")
        self.btn_clear.clicked.connect(self.test_text.clear)
        for b in (self.btn_all, self.btn_space, self.btn_newline, self.btn_back, self.btn_clear):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)        # the test text keeps the keyboard focus
            tools.addWidget(b)
        tools.addStretch()
        tools.addWidget(QLabel("Preview size"))
        self.slider_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_size.setRange(14, 72)
        self.slider_size.setValue(DEFAULT_PREVIEW_SIZE)
        self.slider_size.setFixedWidth(120)
        self.slider_size.valueChanged.connect(self._apply_preview_font)
        tools.addWidget(self.slider_size)
        root.addLayout(tools)

        # the glyphs, as buttons that insert themselves
        self.glyph_area = QScrollArea()
        self.glyph_area.setObjectName("TfGlyphArea")
        self.glyph_area.setWidgetResizable(True)
        self.glyph_area.setMinimumHeight(110)
        self.glyph_area.setMaximumHeight(170)
        holder = QWidget()
        holder.setObjectName("TfGlyphHolder")
        self.glyph_flow = FlowLayout(holder, margin=8, h_spacing=6, v_spacing=6)
        self.glyph_area.setWidget(holder)
        root.addWidget(self.glyph_area)

        # the style sliders
        root.addWidget(self._section("Glyphs"))
        self._add_slider(root, "scale", "Scale", "% of the slot", "Size of each glyph inside its slot")
        self._add_slider(root, "thickness", "Thickness", "% of the stroke width",
                         "Makes every stroke thinner or thicker. Imported SVG outlines cannot be thickened.")
        root.addWidget(self._section("Spacing"))
        self._add_slider(root, "glyph_gap", "Gap between glyphs", "font units",
                         "Extra room between typed glyphs. 1000 units is the width of one glyph slot; negative is tighter.")
        word_row = QHBoxLayout()
        self.chk_space = QCheckBox("Use a custom word gap")
        self.chk_space.setToolTip("When on, the space bar uses this width. It also sets the width of spaces in "
                                  "ordinary text inside fields that use the language font.")
        self.chk_space.toggled.connect(self._on_space_toggled)
        word_row.addWidget(self.chk_space)
        word_row.addStretch()
        root.addLayout(word_row)
        self._add_slider(root, "space_width", "Word gap", "font units", "Width of a space")

        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("TfStatus")
        self.lbl_status.setWordWrap(True)
        root.addWidget(self.lbl_status)

        # buttons
        buttons = QHBoxLayout()
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setToolTip("Back to the default look")
        self.btn_reset.clicked.connect(self._reset)
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Save")
        self.btn_save.setObjectName("TfSave")
        self.btn_save.setDefault(False)
        self.btn_save.clicked.connect(self.accept)
        buttons.addWidget(self.btn_reset)
        buttons.addStretch()
        buttons.addWidget(self.btn_cancel)
        buttons.addWidget(self.btn_save)
        root.addLayout(buttons)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("TfSection")
        return lbl

    def _add_slider(self, layout: QVBoxLayout, key: str, label: str, unit: str, tip: str):
        low, high = RANGES[key]
        row = QHBoxLayout()
        row.setSpacing(10)
        name = QLabel(label)
        name.setObjectName("TfRowLabel")
        name.setFixedWidth(150)
        name.setToolTip(tip)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(int(low), int(high))
        slider.setToolTip(tip)
        slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        value = QLabel("")
        value.setObjectName("TfValue")
        value.setFixedWidth(120)
        slider.valueChanged.connect(lambda _v, k=key, u=unit: self._on_slider(k, u))
        row.addWidget(name)
        row.addWidget(slider, 1)
        row.addWidget(value)
        layout.addLayout(row)
        self._sliders[key] = slider
        self._value_labels[key] = value
        self._units = getattr(self, "_units", {})
        self._units[key] = unit

    # ---------------------------------------------------------------- style values
    def _load_style(self, style: Dict[str, Any]):
        for key, slider in self._sliders.items():
            slider.blockSignals(True)
            slider.setValue(int(round(style[key])))
            slider.blockSignals(False)
        self.chk_space.blockSignals(True)
        self.chk_space.setChecked(bool(style["space_enabled"]))
        self.chk_space.blockSignals(False)
        self._sliders["space_width"].setEnabled(self.chk_space.isChecked())
        for key in self._sliders:
            self._update_value_label(key)

    def style(self) -> Dict[str, Any]:
        # the settings as they are now (always complete and in range)
        values = {key: float(slider.value()) for key, slider in self._sliders.items()}
        values["space_enabled"] = self.chk_space.isChecked()
        return normalize_style(values)

    def _update_value_label(self, key: str):
        value = self._sliders[key].value()
        unit = self._units.get(key, "")
        suffix = "%" if unit.startswith("%") else " units"
        self._value_labels[key].setText(f"{value}{suffix}")

    def _on_slider(self, key: str, _unit: str):
        self._update_value_label(key)
        self.lbl_status.setText("Updating preview...")
        self._timer.start()                                  # rebuild once the slider has stopped moving

    def _on_space_toggled(self, checked: bool):
        self._sliders["space_width"].setEnabled(checked)
        self._timer.start()

    def _reset(self):
        self._load_style(dict(DEFAULT_STYLE))
        self._timer.start()

    # ---------------------------------------------------------------- the test text
    def _insert(self, text: str):
        cursor = self.test_text.textCursor()
        cursor.insertText(text)
        self.test_text.setTextCursor(cursor)
        self.test_text.setFocus()

    def _backspace(self):
        cursor = self.test_text.textCursor()
        cursor.deletePreviousChar()
        self.test_text.setTextCursor(cursor)
        self.test_text.setFocus()

    def _insert_all(self):
        chars = [chr(self._mapping[gid]) for gid in self._ordered_ids() if gid in self._mapping]
        if chars:
            self._insert(" ".join(chars) + " ")

    def _ordered_ids(self) -> List[str]:
        return [str(row.get("id") or row.get("name") or "glyph") for row in self.glyph_rows]

    # ---------------------------------------------------------------- the preview font
    def _rebuild_preview(self):
        if not self.glyph_rows:
            self.lbl_status.setText("There are no glyphs yet. Draw some on the Logogram page first.")
            return
        self._build_count += 1
        path = os.path.join(self._tmp_dir, f"preview_{self._build_count}.ttf")
        try:
            mapping = build_preview_font(self.glyph_rows, self.fonts_dir, path, self.style())
            family = register_preview_font(path)
        except Exception as exc:                              # keep the window usable, show what went wrong
            traceback.print_exc()
            self.lbl_status.setText(f"The preview could not be built: {exc}")
            return
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        if not family:
            self.lbl_status.setText("The preview font could not be loaded.")
            return
        self._mapping = mapping
        self._family = family
        if not self._glyph_buttons:
            self._create_glyph_buttons()
        self._apply_preview_font()
        self.lbl_status.setText("")

    def _create_glyph_buttons(self):
        names = {str(row.get("id") or row.get("name") or "glyph"): (row.get("name") or "(unnamed)")
                 for row in self.glyph_rows}
        for gid in self._ordered_ids():
            cp = self._mapping.get(gid)
            if cp is None:
                continue
            button = QPushButton(chr(cp))
            button.setObjectName("TfGlyph")
            button.setFixedSize(56, 56)
            button.setToolTip(names.get(gid, ""))
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.clicked.connect(lambda _=False, c=chr(cp): self._insert(c))
            self.glyph_flow.addWidget(button)
            self._glyph_buttons.append(button)

    def _apply_preview_font(self, *_):
        if not self._family:
            return
        size = self.slider_size.value()
        self.test_text.setFont(QFont(self._family, size))
        self.test_text.setFixedHeight(self.test_text.fontMetrics().lineSpacing() * 3 + 26)   # three lines
        button_font = QFont(self._family, 22)
        for button in self._glyph_buttons:
            button.setFont(button_font)

    # ---------------------------------------------------------------- closing
    def done(self, result: int):
        self._timer.stop()
        shutil.rmtree(self._tmp_dir, ignore_errors=True)
        super().done(result)

    def _qss(self) -> str:
        return """
            QDialog { background-color: #f4f4f4; }
            QLabel { color: #222222; font-size: 12px; }
            QLabel#TfTitle { font-size: 18px; font-weight: bold; color: #111111; }
            QLabel#TfHint { color: #666666; }
            QLabel#TfSection { font-size: 13px; font-weight: bold; color: #111111; margin-top: 4px; }
            QLabel#TfValue { color: #444444; }
            QLabel#TfStatus { color: #b36b00; }
            QPlainTextEdit#TfTest { background-color: #ffffff; color: #111111; border: 1px solid #cccccc;
                                    border-radius: 6px; padding: 6px; }
            QScrollArea#TfGlyphArea { background-color: #ffffff; border: 1px solid #cccccc; border-radius: 6px; }
            QWidget#TfGlyphHolder { background-color: #ffffff; }
            QPushButton { background-color: #ffffff; color: #222222; border: 1px solid #cccccc; border-radius: 4px;
                          padding: 5px 12px; font-size: 12px; }
            QPushButton:hover { background-color: #eef4fd; border-color: #007acc; }
            QPushButton#TfGlyph { padding: 0px; color: #111111; }
            QPushButton#TfSave { background-color: #007acc; color: #ffffff; border-color: #005999; font-weight: bold; }
            QPushButton#TfSave:hover { background-color: #0a8ae0; }
            QCheckBox { color: #222222; font-size: 12px; }
        """
