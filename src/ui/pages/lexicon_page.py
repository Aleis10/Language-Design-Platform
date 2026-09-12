import os
import uuid
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QAbstractItemView, QDialog, QFormLayout, QDialogButtonBox, QComboBox, QLabel,
    QPlainTextEdit, QListWidget, QListWidgetItem, QInputDialog,
)
from PySide6.QtCore import Qt

try:
    from database.lexicon_db import LexiconRepository
    from ui.components.glyph_audio import GlyphAudioWidget
except ImportError:
    from ..database.lexicon_db import LexiconRepository
    from ..components.glyph_audio import GlyphAudioWidget

POS_OPTIONS = ["", "NOUN", "VERB", "ADJ", "ADV", "PRON", "PREP", "CONJ", "DET", "PART", "INTERJ", "NUM"]

class _EntryDialog(QDialog):

    def __init__(self, parent=None, data: Optional[dict] = None, base_audio_dir: str = "", data_dir: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Edit Entry" if data else "Add Entry")
        self.setMinimumWidth(520)
        self.base_audio_dir = base_audio_dir
        self.available_audio = list(data.get("audio_variants", [])) if data else []
        self._is_edit = bool(data)

        if data_dir:
            try:
                from font_tools.font_registry import apply_conlang_font
                self.data_dir = data_dir
            except ImportError:
                pass

        form = QFormLayout(self)

        self.input_headword = QLineEdit()
        self.input_headword.setPlaceholderText("Citation form (e.g. katana)")
        if data_dir:
            try:
                from font_tools.font_registry import apply_conlang_font
                apply_conlang_font(self.input_headword, data_dir, point_size=12)
            except Exception:
                pass
        form.addRow("Headword:", self.input_headword)

        self.input_ipa = QLineEdit()
        self.input_ipa.setPlaceholderText("e.g. /ka.ta.na/")
        form.addRow("Primary IPA:", self.input_ipa)

        self.input_pos = QComboBox()
        self.input_pos.setEditable(True)
        self.input_pos.addItems(POS_OPTIONS)
        form.addRow("Part of Speech:", self.input_pos)

        self.input_meaning = QLineEdit()
        self.input_meaning.setPlaceholderText("Native gloss / citation meaning")
        form.addRow("Meaning:", self.input_meaning)

        self.input_english = QLineEdit()
        self.input_english.setPlaceholderText("Direct English translation")
        form.addRow("English Translation:", self.input_english)

        self.input_description = QPlainTextEdit()
        self.input_description.setPlaceholderText("Multi-line description / usage notes...")
        self.input_description.setFixedHeight(80)
        form.addRow("Description:", self.input_description)

        lbl_audio = QLabel("Pronunciation Audio Variants")
        lbl_audio.setStyleSheet("font-weight: bold;")
        form.addRow(lbl_audio)

        self.audio_list = QListWidget()
        self.audio_list.setObjectName("LexAudioList")
        self.audio_list.setMaximumHeight(120)
        self.audio_list.itemSelectionChanged.connect(self._on_audio_select)
        form.addRow(self.audio_list)

        self.audio_widget = GlyphAudioWidget(base_audio_dir=base_audio_dir)
        self.audio_widget.set_glyph(str(uuid.uuid4()))
        form.addRow("Record new / overwrite selected:", self.audio_widget)

        self.input_variant_label = QLineEdit()
        self.input_variant_label.setPlaceholderText("e.g. Slow, Fast, Female, Formal...")
        form.addRow("Variant label:", self.input_variant_label)

        self.input_audio_ipa = QLineEdit()
        self.input_audio_ipa.setPlaceholderText("IPA for this recording")
        form.addRow("Variant IPA:", self.input_audio_ipa)

        audio_btns = QHBoxLayout()
        btn_add_audio = QPushButton("Add Variant")
        btn_add_audio.setObjectName("LexAudioBtn")
        btn_add_audio.clicked.connect(self._add_variant)
        btn_update_audio = QPushButton("Update Selected")
        btn_update_audio.setObjectName("LexAudioBtn")
        btn_update_audio.clicked.connect(self._update_variant)
        btn_remove_audio = QPushButton("Remove Selected")
        btn_remove_audio.setObjectName("LexAudioBtnRemove")
        btn_remove_audio.clicked.connect(self._remove_variant)
        audio_btns.addWidget(btn_add_audio)
        audio_btns.addWidget(btn_update_audio)
        audio_btns.addWidget(btn_remove_audio)
        audio_btns.addStretch()
        form.addRow(audio_btns)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._validate)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

        self.input_ipa.clearFocus()

        if data:
            self.input_headword.setText(data.get("headword", ""))
            self.input_ipa.setText(data.get("ipa_reading", ""))
            pos_val = data.get("part_of_speech", "")
            idx = self.input_pos.findText(pos_val)
            if idx >= 0:
                self.input_pos.setCurrentIndex(idx)
            else:
                self.input_pos.setEditText(pos_val)
            self.input_meaning.setText(data.get("meaning", ""))
            self.input_english.setText(data.get("english_translation", ""))
            self.input_description.setPlainText(data.get("description", ""))
            for audio in self.available_audio:
                self._append_audio_item(audio)

    def _append_audio_item(self, audio: dict):
        ipa = audio.get("ipa_reading", "")
        label = audio.get("variant_label", "")
        path = audio.get("audio_path", "")
        tag = " / ".join(x for x in [label, ipa] if x)
        item = QListWidgetItem(tag or os.path.basename(path or "(new recording)"))
        item.setData(Qt.ItemDataRole.UserRole, dict(audio))
        self.audio_list.addItem(item)

    def _current_audio_row_data(self) -> Optional[dict]:
        item = self.audio_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_audio_select(self):
        audio = self._current_audio_row_data()
        if not audio:
            return
        self.input_variant_label.setText(audio.get("variant_label", ""))
        self.input_audio_ipa.setText(audio.get("ipa_reading", ""))

    def _add_variant(self):
        rel_path = self.audio_widget.current_audio_rel
        audio_data = {
            "id": None,  # new, will get an id on save
            "variant_label": self.input_variant_label.text().strip(),
            "ipa_reading": self.input_audio_ipa.text().strip(),
            "audio_path": rel_path,
        }
        tag = " / ".join(x for x in [audio_data["variant_label"], audio_data["ipa_reading"]] if x)
        item = QListWidgetItem(tag or os.path.basename(rel_path or "(new recording)"))
        item.setData(Qt.ItemDataRole.UserRole, audio_data)
        self.audio_list.addItem(item)
        self.audio_widget.set_glyph(str(uuid.uuid4()))
        self.input_variant_label.clear()
        self.input_audio_ipa.clear()
        self._mark_changed()

    def _update_variant(self):
        audio = self._current_audio_row_data()
        if not audio:
            QMessageBox.information(self, "No selection", "Select an audio variant to update.")
            return
        rel_path = self.audio_widget.current_audio_rel or audio.get("audio_path", "")
        audio_data = {
            "id": audio.get("id"),
            "variant_label": self.input_variant_label.text().strip(),
            "ipa_reading": self.input_audio_ipa.text().strip(),
            "audio_path": rel_path,
        }
        item = self.audio_list.currentItem()
        tag = " / ".join(x for x in [audio_data["variant_label"], audio_data["ipa_reading"]] if x)
        item.setText(tag or os.path.basename(rel_path or "(no file)"))
        item.setData(Qt.ItemDataRole.UserRole, audio_data)
        self._mark_changed()

    def _remove_variant(self):
        item = self.audio_list.currentItem()
        if not item:
            QMessageBox.information(self, "No selection", "Select an audio variant to remove.")
            return
        idx = self.audio_list.row(item)
        self.audio_list.takeItem(idx)
        self._mark_changed()

    def _mark_changed(self):
        if not hasattr(self, "_variants_dirty"):
            self._variants_dirty = True

    def _get_variants(self) -> list:
        variants = []
        for i in range(self.audio_list.count()):
            item = self.audio_list.item(i)
            variants.append(item.data(Qt.ItemDataRole.UserRole) or {})
        return variants

    def _validate(self):
        if not self.input_headword.text().strip():
            QMessageBox.warning(self, "Missing", "Headword is required.")
            return
        if not self.input_meaning.text().strip():
            QMessageBox.warning(self, "Missing", "Meaning is required.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "headword": self.input_headword.text().strip(),
            "ipa_reading": self.input_ipa.text().strip(),
            "part_of_speech": self.input_pos.currentText().strip(),
            "meaning": self.input_meaning.text().strip(),
            "english_translation": self.input_english.text().strip(),
            "description": self.input_description.toPlainText().strip(),
            "audio_variants": self._get_variants(),
        }

class LexiconPage(QWidget):
    def __init__(self, lexicon_repo: LexiconRepository, language_id: str, session_dir: str = "", parent=None):
        super().__init__(parent)
        self.lexicon_repo = lexicon_repo
        self.language_id = language_id
        self._current_query = ""

        self.session_dir = session_dir
        self.data_dir = session_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "data",
        )
        self.audio_dir = os.path.join(self.data_dir, "audio", "lexicon")
        os.makedirs(self.audio_dir, exist_ok=True)

        self._build_ui()
        self._load_stylesheet()
        self.refresh_table()

    def _load_stylesheet(self):
        style_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "lexicon_page.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("LexTopBar")
        top = QHBoxLayout(top_bar)
        top.setContentsMargins(20, 12, 20, 12)
        top.setSpacing(12)

        lbl = QLabel("Lexicon & Dictionary")
        lbl.setObjectName("LexTitle")
        top.addWidget(lbl)
        top.addSpacing(12)

        btn_add = QPushButton("+ Add Entry")
        btn_add.clicked.connect(self._add_entry)
        top.addWidget(btn_add)

        btn_edit = QPushButton("Edit")
        btn_edit.clicked.connect(self._edit_entry)
        top.addWidget(btn_edit)

        btn_delete = QPushButton("Delete")
        btn_delete.setObjectName("LexDelete")
        btn_delete.clicked.connect(self._delete_entry)
        top.addWidget(btn_delete)

        top.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search headword, meaning, IPA...")
        self.search_input.setFixedWidth(260)
        self.search_input.textChanged.connect(self._on_search)
        top.addWidget(self.search_input)
        root.addWidget(top_bar)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 16, 20, 16)
        body_layout.setSpacing(12)
        self.table = QTableWidget()
        self.table.setObjectName("LexTable")
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(["Headword", "IPA", "POS", "Meaning", "English", "Audio", "Description", "ID"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnHidden(7, True)   # hide ID
        self.table.setWordWrap(True)
        body_layout.addWidget(self.table, stretch=1)

        self.lbl_count = QLabel("0 entries")
        self.lbl_count.setObjectName("LexCount")
        body_layout.addWidget(self.lbl_count)
        root.addWidget(body, stretch=1)

    def refresh_table(self):
        entries = (
            self.lexicon_repo.search(self.language_id, self._current_query)
            if self._current_query
            else self.lexicon_repo.get_all_entries(self.language_id)
        )
        self.table.setRowCount(len(entries))
        verbs = 0
        for row, entry in enumerate(entries):
            hw_item = QTableWidgetItem(entry.get("headword", ""))
            if hasattr(self, "data_dir") and self.data_dir:
                try:
                    from font_tools.font_registry import conlang_font
                    hw_item.setFont(conlang_font(point_size=12))
                except Exception:
                    pass
            self.table.setItem(row, 0, hw_item)
            self.table.setItem(row, 1, QTableWidgetItem(entry.get("ipa_reading", "")))
            self.table.setItem(row, 2, QTableWidgetItem(entry.get("part_of_speech", "")))
            self.table.setItem(row, 3, QTableWidgetItem(entry.get("meaning", "")))
            self.table.setItem(row, 4, QTableWidgetItem(entry.get("english_translation", "")))

            variants = entry.get("audio_variants", [])
            variant_text = f"{len(variants)} recording(s)"
            if variants:
                ipas = [v.get("ipa_reading", "") for v in variants if v.get("ipa_reading")]
                if ipas:
                    variant_text += ": " + " · ".join(ipas)
            self.table.setItem(row, 5, QTableWidgetItem(variant_text))

            self.table.setItem(row, 6, QTableWidgetItem(entry.get("description", "")))
            self.table.setItem(row, 7, QTableWidgetItem(entry.get("id", "")))
            if entry.get("part_of_speech", ""):
                verbs += 1
        self.lbl_count.setText(f"{len(entries)} entries")

    def _on_search(self, text: str):
        self._current_query = text
        self.refresh_table()

    def _selected_id(self) -> Optional[str]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.table.item(rows[0].row(), 7).text()

    def _selected_entry(self) -> Optional[dict]:
        entry_id = self._selected_id()
        if not entry_id:
            return None
        entries = self.lexicon_repo.get_all_entries(self.language_id)
        for e in entries:
            if e["id"] == entry_id:
                return e
        return None

    def _add_entry(self):
        dlg = _EntryDialog(self, base_audio_dir=self.audio_dir, data_dir=self.data_dir)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            entry_id = self.lexicon_repo.add_entry(
                language_id=self.language_id,
                headword=data["headword"],
                meaning=data["meaning"],
                ipa_reading=data["ipa_reading"],
                part_of_speech=data["part_of_speech"],
                english_translation=data.get("english_translation", ""),
                description=data.get("description", ""),
            )
            for variant in data.get("audio_variants", []):
                if variant.get("audio_path"):
                    self.lexicon_repo.add_entry_audio(
                        entry_id,
                        audio_path=variant["audio_path"],
                        ipa_reading=variant.get("ipa_reading", ""),
                        variant_label=variant.get("variant_label", ""),
                    )
            self.refresh_table()

    def _edit_entry(self):
        entry = self._selected_entry()
        if not entry:
            QMessageBox.information(self, "No selection", "Select a row to edit.")
            return
        dlg = _EntryDialog(self, data=entry, base_audio_dir=self.audio_dir, data_dir=self.data_dir)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            self.lexicon_repo.update_entry(
                entry["id"],
                headword=data["headword"],
                meaning=data["meaning"],
                ipa_reading=data["ipa_reading"],
                part_of_speech=data["part_of_speech"],
                english_translation=data.get("english_translation", ""),
                description=data.get("description", ""),
            )
            existing = {v["id"]: v for v in entry.get("audio_variants", []) if v.get("id")}
            kept_ids = set()
            for variant in data.get("audio_variants", []):
                vid = variant.get("id")
                if vid and vid in existing:
                    self.lexicon_repo.update_entry_audio(
                        vid,
                        variant_label=variant.get("variant_label", ""),
                        ipa_reading=variant.get("ipa_reading", ""),
                        audio_path=variant.get("audio_path", ""),
                    )
                    kept_ids.add(vid)
                else:
                    self.lexicon_repo.add_entry_audio(
                        entry["id"],
                        audio_path=variant.get("audio_path", ""),
                        ipa_reading=variant.get("ipa_reading", ""),
                        variant_label=variant.get("variant_label", ""),
                    )
            for vid in existing:
                if vid not in kept_ids:
                    self.lexicon_repo.delete_entry_audio(vid)
            self.refresh_table()

    def _delete_entry(self):
        entry_id = self._selected_id()
        if not entry_id:
            QMessageBox.information(self, "No selection", "Select a row to delete.")
            return
        res = QMessageBox.question(
            self, "Confirm Delete",
            "Delete this lexicon entry? This also removes all its audio.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if res == QMessageBox.StandardButton.Yes:
            self.lexicon_repo.delete_entry(entry_id)
            self.refresh_table()