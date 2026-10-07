"""Transcribe & Translate page.

    type English  ->  translation engine  ->  conlang words

* The word table shows what each English word matched and how it was inflected. Double-click an
  ambiguous word to pick another entry; double-click an unknown word to add it to the lexicon.
* Words currently come out in English word order (word order is a later engine step).
"""
import os
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from database.transcribe_db import DEFAULTS
from digital_keyboard import install_conlang_delegate, track_conlang_widget
from translation import TranslationEngine

from .lexicon_page import add_entry_via_dialog

UNKNOWN_CHOICES = [("Show as [word]", "bracket"), ("Keep the English word", "keep"), ("Leave it out", "skip")]


class _ChooseEntryDialog(QDialog):
    def __init__(self, english: str, candidates, current_entry, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Choose a word for \u201c{english}\u201d")
        self.setMinimumWidth(480)
        self._candidates = list(candidates)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Several lexicon entries match. Pick the one you mean:"))
        self.list = QListWidget()
        install_conlang_delegate(self.list, 16)
        for c in self._candidates:
            e = c.entry
            tag = "   (current)" if e is current_entry else ""
            pos = f"  [{e.get('part_of_speech')}]" if e.get("part_of_speech") else ""
            item = QListWidgetItem(f"{e.get('headword', '')}{pos}   {e.get('meaning', '')}{tag}")
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        layout.addWidget(self.list)
        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Use this word")
        ok.setObjectName("TrPrimary")
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)

    def selected(self):
        row = self.list.currentRow()
        return self._candidates[row] if 0 <= row < len(self._candidates) else None


class _SettingsDialog(QDialog):
    def __init__(self, settings: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Transcribe settings")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.ignore = QLineEdit(", ".join(settings.get("ignore_words", [])))
        self.ignore.setPlaceholderText("the, a, an")
        form.addRow("Skip English words:", self.ignore)
        hint = QLabel("Words your language does not have. They are dropped unless the lexicon has an entry for them.")
        hint.setObjectName("TrHint")
        hint.setWordWrap(True)
        form.addRow("", hint)

        self.unknown = QComboBox()
        for label, value in UNKNOWN_CHOICES:
            self.unknown.addItem(label, value)
        self.unknown.setCurrentIndex(max(0, self.unknown.findData(settings.get("unknown", "bracket"))))
        form.addRow("Words not in lexicon:", self.unknown)

        layout.addLayout(form)

        row = QHBoxLayout()
        row.addStretch()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setObjectName("TrPrimary")
        save.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(save)
        layout.addLayout(row)

    def values(self) -> Dict[str, Any]:
        words = [w.strip() for w in self.ignore.text().replace(";", ",").split(",") if w.strip()]
        return {
            "ignore_words": words,
            "unknown": self.unknown.currentData(),
        }


class TranscribePage(QWidget):
    COLUMNS = ["English", "Conlang", "Gloss", "Via", "Status"]

    def __init__(self, lexicon_repo, grammar_repo, settings_repo, language_id: str,
                 session_dir: str = "", parent=None):
        super().__init__(parent)
        self.lexicon_repo = lexicon_repo
        self.grammar_repo = grammar_repo
        self.settings_repo = settings_repo
        self.language_id = language_id
        self.data_dir = session_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")
        self.audio_dir = os.path.join(self.data_dir, "audio", "lexicon")

        self._engine: Optional[TranslationEngine] = None
        self.last_translation = None
        self._row_to_word: List[int] = []

        self._build_ui()
        self._load_stylesheet()
        self._refresh_info()

    # ------------------------------------------------------------------ UI
    def _load_stylesheet(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style", "transcribe_page.qss")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("TrTopBar")
        top = QHBoxLayout(top_bar)
        top.setContentsMargins(20, 12, 20, 12)
        top.setSpacing(12)
        title = QLabel("Transcribe & Translate")
        title.setObjectName("TrTitle")
        top.addWidget(title)
        top.addSpacing(12)
        self.lbl_status = QLabel("")
        self.lbl_status.setObjectName("TrStatus")
        top.addWidget(self.lbl_status, stretch=1)
        btn_settings = QPushButton("Settings")
        btn_settings.clicked.connect(self._open_settings)
        top.addWidget(btn_settings)
        root.addWidget(top_bar)

        body = QWidget()
        lay = QVBoxLayout(body)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        lay.addWidget(self._section("English"))
        self.input_text = QPlainTextEdit()
        self.input_text.setPlaceholderText("Type English here.   Ctrl+Enter translates.")
        self.input_text.setFixedHeight(84)
        lay.addWidget(self.input_text)
        QShortcut(QKeySequence("Ctrl+Return"), self.input_text, activated=self._on_translate_clicked)
        QShortcut(QKeySequence("Ctrl+Enter"), self.input_text, activated=self._on_translate_clicked)

        row = QHBoxLayout()
        self.btn_translate = QPushButton("Translate")
        self.btn_translate.setObjectName("TrPrimary")
        self.btn_translate.clicked.connect(self._on_translate_clicked)
        row.addWidget(self.btn_translate)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self._clear)
        row.addWidget(btn_clear)
        row.addStretch()
        self.lbl_info = QLabel("")
        self.lbl_info.setObjectName("TrHint")
        row.addWidget(self.lbl_info)
        lay.addLayout(row)

        lay.addWidget(self._section("Conlang"))
        self.output_text = QPlainTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setFixedHeight(84)
        track_conlang_widget(self.output_text, 20)
        lay.addWidget(self.output_text)
        self.lbl_gloss = QLabel("")
        self.lbl_gloss.setObjectName("TrGloss")
        self.lbl_gloss.setWordWrap(True)
        self.lbl_gloss.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.lbl_gloss)

        copy_row = QHBoxLayout()
        btn_copy = QPushButton("Copy conlang text")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.output_text.toPlainText()))
        copy_row.addWidget(btn_copy)
        btn_copy_gloss = QPushButton("Copy gloss")
        btn_copy_gloss.clicked.connect(lambda: QApplication.clipboard().setText(self.lbl_gloss.text()))
        copy_row.addWidget(btn_copy_gloss)
        copy_row.addStretch()
        lay.addLayout(copy_row)

        lay.addWidget(self._section("Word by word"))
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setObjectName("TrTable")
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        install_conlang_delegate(self.table, 16)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._act_on_row(r))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._row_menu)
        lay.addWidget(self.table, stretch=1)

        self.lbl_warn = QLabel("")
        self.lbl_warn.setObjectName("TrWarn")
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setVisible(False)
        lay.addWidget(self.lbl_warn)
        hint = QLabel("Double-click an ambiguous word to choose another entry, or an unknown word to add it to the lexicon.")
        hint.setObjectName("TrHint")
        lay.addWidget(hint)
        root.addWidget(body, stretch=1)

    def _section(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("TrSection")
        return lbl

    # ------------------------------------------------------------ helpers
    def _set_status(self, text: str) -> None:
        self.lbl_status.setText(text)

    def _settings(self) -> Dict[str, Any]:
        if self.settings_repo is None:
            return {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
        return self.settings_repo.get_all(self.language_id)

    def _make_engine(self) -> TranslationEngine:
        s = self._settings()
        return TranslationEngine.from_repos(
            self.lexicon_repo, self.grammar_repo, self.language_id,
            unknown=s.get("unknown", "bracket"), ignore=s.get("ignore_words", []),
        )

    def _refresh_info(self) -> None:
        try:
            n_words = len(self.lexicon_repo.get_all_entries(self.language_id))
            n_rules = len(self.grammar_repo.get_rules(self.language_id))
            n_grids = len(self.grammar_repo.get_paradigms(self.language_id))
        except Exception:
            self.lbl_info.setText("")
            return
        self.lbl_info.setText(f"{n_words} lexicon entries \u00B7 {n_rules} rules \u00B7 {n_grids} grids")
        if n_words == 0:
            self._set_status("Your lexicon is empty. Add words on the Lexicon page first.")

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_info()

    # ---------------------------------------------------------- translate
    def _on_translate_clicked(self) -> None:
        self.translate_text(self.input_text.toPlainText())

    def translate_text(self, text: str):
        text = (text or "").strip()
        if not text:
            self._clear_output()
            return None
        try:
            self._engine = self._make_engine()
            self.last_translation = self._engine.translate(text)
        except Exception as exc:
            QMessageBox.warning(self, "Translation failed", str(exc))
            return None
        self._render()
        return self.last_translation

    def _clear(self) -> None:
        self.input_text.clear()
        self._clear_output()

    def _clear_output(self) -> None:
        self.last_translation = None
        self._row_to_word = []
        self.output_text.setPlainText("")
        self.lbl_gloss.setText("")
        self.table.setRowCount(0)
        self.lbl_warn.setVisible(False)

    @staticmethod
    def _via(word) -> str:
        if word.source == "stem":
            return ""
        kind, _, name = word.source.partition(":")
        return f"grid: {name}" if kind == "grid" else name

    @staticmethod
    def _status(word) -> str:
        if word.status == "unknown":
            return "not in lexicon"
        if word.status == "dropped":
            return "skipped"
        parts = []
        if word.status == "ambiguous":
            parts.append(f"ambiguous ({len(word.alternatives) + 1})")
        elif word.alternatives:
            parts.append("other entries")
        if word.missing:
            parts.append("no rule for " + ", ".join(word.missing))
        return "; ".join(parts)

    def _render(self) -> None:
        t = self.last_translation
        self.output_text.setPlainText(t.conlang_text)
        self.lbl_gloss.setText(t.gloss_text)
        self._row_to_word = [i for i, w in enumerate(t.words) if w.status not in ("punct", "number")]
        self.table.setRowCount(len(self._row_to_word))
        for row, wi in enumerate(self._row_to_word):
            w = t.words[wi]
            cells = [w.english, w.form or "\u2014", w.gloss, self._via(w), self._status(w)]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if w.status == "ambiguous" or w.missing:
                    item.setBackground(QBrush(QColor("#fff4d6")))
                elif w.status == "unknown":
                    item.setBackground(QBrush(QColor("#fde2e1")))
                elif w.status == "dropped":
                    item.setForeground(QBrush(QColor("#999999")))
                if w.notes:
                    item.setToolTip("\n".join(w.notes))
                self.table.setItem(row, col, item)
        self.lbl_warn.setText("\n".join("\u2022 " + x for x in t.warnings))
        self.lbl_warn.setVisible(bool(t.warnings))
        self._refresh_info()

    # ---------------------------------------------------- word actions
    def _word_at_row(self, row: int):
        if self.last_translation is None or not (0 <= row < len(self._row_to_word)):
            return None, -1
        wi = self._row_to_word[row]
        return self.last_translation.words[wi], wi

    def _act_on_row(self, row: int) -> None:
        w, wi = self._word_at_row(row)
        if w is None:
            return
        if w.status == "unknown":
            self.add_to_lexicon(wi)
        elif w.entry is not None and w.alternatives:
            self.choose_entry(wi)

    def _row_menu(self, pos) -> None:
        w, wi = self._word_at_row(self.table.rowAt(pos.y()))
        if w is None:
            return
        menu = QMenu(self)
        if w.entry is not None and w.alternatives:
            menu.addAction("Choose another entry\u2026", lambda: self.choose_entry(wi))
        if w.status == "unknown":
            menu.addAction("Add to lexicon\u2026", lambda: self.add_to_lexicon(wi))
        if not menu.isEmpty():
            menu.exec(self.table.viewport().mapToGlobal(pos))

    def choose_entry(self, word_index: int, candidate=None) -> None:
        """Re-do one word with a different lexicon entry (asks the user unless `candidate` is given)."""
        w = self.last_translation.words[word_index]
        if candidate is None:
            cands = ([w.chosen] if w.chosen else []) + list(w.alternatives)
            dlg = _ChooseEntryDialog(w.english, cands, w.entry, self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            candidate = dlg.selected()
        if candidate is None or candidate.entry is w.entry:
            return
        self.last_translation = self._engine.with_choice(self.last_translation, word_index, candidate)
        self._render()

    def add_to_lexicon(self, word_index: int) -> None:
        w = self.last_translation.words[word_index]
        if add_entry_via_dialog(self, self.lexicon_repo, self.language_id, self.audio_dir, self.data_dir,
                                english=w.english.lower()):
            self.translate_text(self.input_text.toPlainText())

    # ------------------------------------------------------------ settings
    def _open_settings(self) -> None:
        if self.settings_repo is None:
            return
        dlg = _SettingsDialog(self._settings(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings_repo.set_many(self.language_id, dlg.values())
            if self.last_translation is not None:
                self.translate_text(self.input_text.toPlainText())
