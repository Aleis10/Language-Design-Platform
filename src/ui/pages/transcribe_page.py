"""Transcribe & Translate page.

    speak or type English  ->  (Whisper)  ->  English text  ->  translation engine  ->  conlang words

* Speech to text is optional (needs `pip install faster-whisper`); typing always works.
* The word table shows what each English word matched and how it was inflected. Double-click an
  ambiguous word to pick another entry; double-click an unknown word to add it to the lexicon.
* Words currently come out in English word order (word order is a later engine step).
"""
import importlib.util
import os
import tempfile
import time
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from database.transcribe_db import DEFAULTS
from digital_keyboard import install_conlang_delegate, track_conlang_widget
from translation import SimpleAnalyzer, SpacyAnalyzer, TranslationEngine
from translation.speech import MODEL_CHOICES, WhisperBackend

from .lexicon_page import add_entry_via_dialog

AUDIO_FILTER = "Audio (*.wav *.mp3 *.m4a *.flac *.ogg *.opus *.webm *.aac);;All files (*)"
UNKNOWN_CHOICES = [("Show as [word]", "bracket"), ("Keep the English word", "keep"), ("Leave it out", "skip")]
ANALYZER_CHOICES = [("Automatic (spaCy if installed)", "auto"), ("Built-in (no extra install)", "builtin"),
                    ("spaCy (more accurate)", "spacy")]


class MicRecorder(QObject):
    """Records the microphone to a temporary WAV file (same Qt classes as the glyph audio widget)."""

    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ""
        self._active = False
        self.recorder = None
        self.reason = ""
        try:
            from PySide6.QtMultimedia import QAudioInput, QMediaCaptureSession, QMediaFormat, QMediaRecorder
            self._session = QMediaCaptureSession(self)
            self._input = QAudioInput(self)
            self._session.setAudioInput(self._input)
            self.recorder = QMediaRecorder(self)
            self._session.setRecorder(self.recorder)
            fmt = QMediaFormat()
            fmt.setFileFormat(QMediaFormat.FileFormat.Wave)
            fmt.setAudioCodec(QMediaFormat.AudioCodec.Wave)
            self.recorder.setMediaFormat(fmt)
            self.recorder.recorderStateChanged.connect(self._on_state)
            self.recorder.errorOccurred.connect(self._on_error)
        except Exception as exc:                       # no multimedia backend
            self.recorder = None
            self.reason = str(exc)

    def available(self) -> bool:
        if self.recorder is None:
            return False
        try:
            from PySide6.QtMultimedia import QMediaDevices
            return bool(QMediaDevices.audioInputs())
        except Exception:
            return False

    def start(self) -> None:
        self._path = os.path.join(tempfile.gettempdir(), f"transcribe_{int(time.time())}.wav")
        self.recorder.setOutputLocation(QUrl.fromLocalFile(self._path))
        self._active = True
        self.recorder.record()

    def stop(self) -> None:
        if self.recorder is not None:
            self.recorder.stop()

    def _on_state(self, state) -> None:
        from PySide6.QtMultimedia import QMediaRecorder
        if state == QMediaRecorder.RecorderState.StoppedState and self._active:
            self._active = False
            self.finished.emit(self._path)

    def _on_error(self, _error, message: str) -> None:
        self._active = False
        self.failed.emit(message or "Recording failed.")


class _SpeechWorker(QThread):
    """Runs Whisper off the UI thread."""

    done = Signal(str)
    failed = Signal(str)

    def __init__(self, backend, path: str, model: str, delete_after: bool, parent=None):
        super().__init__(parent)
        self.backend, self.path, self.model, self.delete_after = backend, path, model, delete_after

    def run(self) -> None:
        try:
            self.done.emit(self.backend.transcribe(self.path, self.model))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if self.delete_after:
                try:
                    os.remove(self.path)
                except OSError:
                    pass


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
    def __init__(self, settings: Dict[str, Any], spacy_ok: bool, whisper_ok: bool, parent=None):
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

        self.analyzer = QComboBox()
        for label, value in ANALYZER_CHOICES:
            self.analyzer.addItem(label, value)
        self.analyzer.setCurrentIndex(max(0, self.analyzer.findData(settings.get("analyzer", "auto"))))
        form.addRow("English analysis:", self.analyzer)
        a_note = QLabel("spaCy: installed" if spacy_ok else
                        "spaCy: not installed.  pip install spacy  &&  python -m spacy download en_core_web_sm")
        a_note.setObjectName("TrHint")
        a_note.setWordWrap(True)
        a_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("", a_note)

        self.model = QComboBox()
        self.model.addItems(MODEL_CHOICES)
        idx = self.model.findText(settings.get("whisper_model", "base.en"))
        self.model.setCurrentIndex(max(0, idx))
        form.addRow("Speech model:", self.model)
        w_note = QLabel(
            ("faster-whisper: installed. " if whisper_ok else
             "faster-whisper: not installed.  pip install faster-whisper  ") +
            "Larger models are more accurate but slower. The first use of a model downloads it.")
        w_note.setObjectName("TrHint")
        w_note.setWordWrap(True)
        w_note.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("", w_note)

        self.auto = QCheckBox("Translate automatically after speech is transcribed")
        self.auto.setChecked(bool(settings.get("auto_translate", True)))
        form.addRow("", self.auto)
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
            "analyzer": self.analyzer.currentData(),
            "whisper_model": self.model.currentText(),
            "auto_translate": self.auto.isChecked(),
        }


class TranscribePage(QWidget):
    COLUMNS = ["English", "Conlang", "Gloss", "Via", "Status"]

    def __init__(self, lexicon_repo, grammar_repo, settings_repo, language_id: str,
                 session_dir: str = "", speech_backend=None, parent=None):
        super().__init__(parent)
        self.lexicon_repo = lexicon_repo
        self.grammar_repo = grammar_repo
        self.settings_repo = settings_repo
        self.language_id = language_id
        self.data_dir = session_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "data")
        self.audio_dir = os.path.join(self.data_dir, "audio", "lexicon")
        self.speech = speech_backend or WhisperBackend()

        self._analyzers: Dict[str, Any] = {}
        self._engine: Optional[TranslationEngine] = None
        self.last_translation = None
        self._row_to_word: List[int] = []
        self._worker: Optional[_SpeechWorker] = None
        self._recording = False
        self._rec_started = 0.0
        self._mic: Optional[MicRecorder] = None
        self._rec_timer = QTimer(self)
        self._rec_timer.setInterval(250)
        self._rec_timer.timeout.connect(self._tick_recording)

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
        self.btn_record = QPushButton("\u23FA Record")
        self.btn_record.setObjectName("TrRecord")
        self.btn_record.clicked.connect(self._toggle_record)
        top.addWidget(self.btn_record)
        self.btn_import = QPushButton("Import audio\u2026")
        self.btn_import.clicked.connect(self._import_audio)
        top.addWidget(self.btn_import)
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
        self.input_text.setPlaceholderText("Type English here, or record / import audio.   Ctrl+Enter translates.")
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

    def _get_analyzer(self, mode: str):
        key = "spacy" if mode in ("auto", "spacy") else "builtin"
        if key in self._analyzers:
            return self._analyzers[key]
        analyzer = None
        if key == "spacy":
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                analyzer = SpacyAnalyzer()
            except Exception as exc:
                if mode == "spacy":
                    self._set_status(f"spaCy is not available ({exc}); using the built-in analyzer.")
            finally:
                QApplication.restoreOverrideCursor()
        analyzer = analyzer or SimpleAnalyzer()
        self._analyzers[key] = analyzer
        return analyzer

    def analyzer_name(self) -> str:
        mode = self._settings().get("analyzer", "auto")
        return "spaCy" if isinstance(self._get_analyzer(mode), SpacyAnalyzer) else "built-in"

    def _make_engine(self) -> TranslationEngine:
        s = self._settings()
        return TranslationEngine.from_repos(
            self.lexicon_repo, self.grammar_repo, self.language_id,
            analyzer=self._get_analyzer(s.get("analyzer", "auto")),
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
        spacy_ok = importlib.util.find_spec("spacy") is not None
        dlg = _SettingsDialog(self._settings(), spacy_ok, self.speech.available(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.settings_repo.set_many(self.language_id, dlg.values())
            self._analyzers.clear()
            if self.last_translation is not None:
                self.translate_text(self.input_text.toPlainText())

    # --------------------------------------------------------------- speech
    def _need_speech(self) -> bool:
        if self.speech.available():
            return True
        QMessageBox.information(
            self, "Speech to text not installed",
            "Speech to text uses Whisper through faster-whisper.\n\nInstall it with:\n\n    pip install faster-whisper\n\n"
            "You can still type English and translate it.")
        return False

    def _toggle_record(self) -> None:
        if self._recording:
            self._mic.stop()
            self.btn_record.setEnabled(False)
            self._set_status("Finishing recording\u2026")
            return
        if not self._need_speech() or self._busy():
            return
        if self._mic is None:
            self._mic = MicRecorder(self)
            self._mic.finished.connect(self._on_recording_finished)
            self._mic.failed.connect(self._on_recording_failed)
        if not self._mic.available():
            QMessageBox.warning(self, "No microphone", "No microphone or audio backend was found." +
                                (f"\n\n{self._mic.reason}" if self._mic.reason else ""))
            return
        self._mic.start()
        self._recording = True
        self._rec_started = time.time()
        self.btn_record.setText("\u25A0 Stop")
        self.btn_import.setEnabled(False)
        self._rec_timer.start()
        self._tick_recording()

    def _tick_recording(self) -> None:
        secs = int(time.time() - self._rec_started)
        self._set_status(f"Recording\u2026 {secs // 60}:{secs % 60:02d}   (click Stop when finished)")

    def _reset_record_button(self) -> None:
        self._recording = False
        self._rec_timer.stop()
        self.btn_record.setText("\u23FA Record")
        self.btn_record.setEnabled(True)
        self.btn_import.setEnabled(True)

    def _on_recording_finished(self, path: str) -> None:
        self._reset_record_button()
        self._start_transcription(path, delete_after=True)

    def _on_recording_failed(self, message: str) -> None:
        self._reset_record_button()
        self._set_status("")
        QMessageBox.warning(self, "Recording failed", message)

    def _import_audio(self) -> None:
        if not self._need_speech() or self._busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import audio", "", AUDIO_FILTER)
        if path:
            self._start_transcription(path, delete_after=False)

    def _busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _start_transcription(self, path: str, delete_after: bool) -> None:
        model = self._settings().get("whisper_model", "base.en")
        self._set_status(f"Transcribing with {model}\u2026 (the first run downloads the model)")
        self.btn_record.setEnabled(False)
        self.btn_import.setEnabled(False)
        self._worker = _SpeechWorker(self.speech, path, model, delete_after, self)
        self._worker.done.connect(self._on_transcribed)
        self._worker.failed.connect(self._on_transcribe_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_finished(self) -> None:
        self.btn_record.setEnabled(True)
        self.btn_import.setEnabled(True)

    def _on_transcribed(self, text: str) -> None:
        if not text.strip():
            self._set_status("No speech was detected.")
            return
        self.input_text.setPlainText(text)
        self._set_status("Transcribed. Check the English, then Translate." if not self._settings().get("auto_translate", True)
                         else "Transcribed and translated.")
        if self._settings().get("auto_translate", True):
            self.translate_text(text)

    def _on_transcribe_failed(self, message: str) -> None:
        self._set_status("")
        QMessageBox.warning(self, "Transcription failed", message)

    def shutdown(self) -> None:
        """Stop background work. Call before the page is destroyed."""
        if self._recording and self._mic is not None:
            self._mic.stop()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(5000)
