import os
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtMultimedia import (
    QMediaCaptureSession, QAudioInput, QMediaRecorder,
    QAudioOutput, QMediaPlayer, QMediaFormat
)


class GlyphAudioWidget(QWidget):
    # Audio recorder and playback controller for glyphs & vocabulary entries.
    audio_changed = Signal(str)  # Emits relative or absolute path to audio file

    def __init__(self, base_audio_dir: str = "", audio_path: str = "", parent=None):
        super().__init__(parent)
        self.base_audio_dir = base_audio_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
            "data", "audio", "glyphs"
        )
        os.makedirs(self.base_audio_dir, exist_ok=True)

        self.current_audio_rel = audio_path or ""
        self.is_recording = False
        self.glyph_id = None

        # Audio Session & Recorder
        self.capture_session = None
        self.audio_input = None
        self.recorder = None

        # Audio Player
        self.player = None
        self.audio_output = None

        self._init_multimedia()
        self._init_ui()
        self.update_state()

    def _init_multimedia(self):
        try:
            # Playback
            self.player = QMediaPlayer(self)
            self.audio_output = QAudioOutput(self)
            self.player.setAudioOutput(self.audio_output)
            self.player.playbackStateChanged.connect(self._on_playback_state_changed)

            # Recording
            self.capture_session = QMediaCaptureSession(self)
            self.audio_input = QAudioInput(self)
            self.capture_session.setAudioInput(self.audio_input)
            self.recorder = QMediaRecorder(self)
            self.capture_session.setRecorder(self.recorder)

            # Set format to WAV
            fmt = QMediaFormat()
            fmt.setFileFormat(QMediaFormat.FileFormat.Wave)
            fmt.setAudioCodec(QMediaFormat.AudioCodec.Wave)
            self.recorder.setMediaFormat(fmt)
            self.recorder.recorderStateChanged.connect(self._on_recorder_state_changed)
        except Exception as e:
            print(f"[GlyphAudioWidget] Multimedia init notice: {e}")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(6)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        # Record Button
        self.btn_record = QPushButton("⏺ Record Audio")
        self.btn_record.setObjectName("BtnRecordAudio")
        self.btn_record.setStyleSheet("""
            QPushButton#BtnRecordAudio {
                background-color: #d9534f;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 12px;
                border: none;
            }
            QPushButton#BtnRecordAudio:hover { background-color: #c9302c; }
        """)
        self.btn_record.clicked.connect(self.toggle_record)

        # Play Button
        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setObjectName("BtnPlayAudio")
        self.btn_play.setStyleSheet("""
            QPushButton#BtnPlayAudio {
                background-color: #0275d8;
                color: white;
                font-weight: bold;
                border-radius: 4px;
                padding: 6px 12px;
                border: none;
            }
            QPushButton#BtnPlayAudio:hover { background-color: #025aa5; }
            QPushButton#BtnPlayAudio:disabled { background-color: #cccccc; color: #666666; }
        """)
        self.btn_play.clicked.connect(self.play_audio)

        # Delete Button
        self.btn_delete = QPushButton("🗑 Clear")
        self.btn_delete.setObjectName("BtnDeleteAudio")
        self.btn_delete.setStyleSheet("""
            QPushButton#BtnDeleteAudio {
                background-color: #f7f7f7;
                color: #555555;
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QPushButton#BtnDeleteAudio:hover { background-color: #e9e9e9; }
            QPushButton#BtnDeleteAudio:disabled { opacity: 0.5; }
        """)
        self.btn_delete.clicked.connect(self.delete_audio)

        btn_row.addWidget(self.btn_record)
        btn_row.addWidget(self.btn_play)
        btn_row.addWidget(self.btn_delete)
        btn_row.addStretch()

        self.lbl_status = QLabel("No recording")
        self.lbl_status.setStyleSheet("font-size: 11px; color: #777777;")

        layout.addLayout(btn_row)
        layout.addWidget(self.lbl_status)

    def set_glyph(self, glyph_id: str, audio_path: str = ""):
        self.glyph_id = glyph_id
        self.current_audio_rel = audio_path or ""
        self.update_state()

    def _resolve_full_path(self, rel_or_abs: str) -> str:
        if not rel_or_abs:
            return ""
        if os.path.isabs(rel_or_abs):
            return rel_or_abs
        return os.path.join(self.base_audio_dir, rel_or_abs)

    def update_state(self):
        full_path = self._resolve_full_path(self.current_audio_rel)
        has_file = bool(full_path and os.path.exists(full_path))

        self.btn_play.setEnabled(has_file and not self.is_recording)
        self.btn_delete.setEnabled(has_file and not self.is_recording)

        if self.is_recording:
            self.lbl_status.setText("● Recording in progress... Click to stop")
            self.lbl_status.setStyleSheet("font-size: 11px; color: #d9534f; font-weight: bold;")
            self.btn_record.setText("⏹ Stop Recording")
            self.btn_record.setStyleSheet("background-color: #333333; color: white; padding: 6px 12px; border-radius: 4px;")
        elif has_file:
            fname = os.path.basename(full_path)
            self.lbl_status.setText(f"✓ Recorded: {fname}")
            self.lbl_status.setStyleSheet("font-size: 11px; color: #28a745;")
            self.btn_record.setText("⏺ Retake Audio")
            self.btn_record.setStyleSheet("background-color: #d9534f; color: white; padding: 6px 12px; border-radius: 4px;")
        else:
            self.lbl_status.setText("No pronunciation audio recorded")
            self.lbl_status.setStyleSheet("font-size: 11px; color: #888888;")
            self.btn_record.setText("⏺ Record Audio")
            self.btn_record.setStyleSheet("background-color: #d9534f; color: white; padding: 6px 12px; border-radius: 4px;")

    def toggle_record(self):
        if not self.recorder:
            QMessageBox.warning(self, "Audio Error", "Audio recording engine is not initialized.")
            return

        if not self.is_recording:
            # Start recording
            glyph_name = self.glyph_id or "clip"
            target_filename = f"{glyph_name}.wav"
            target_abs = os.path.join(self.base_audio_dir, target_filename)

            try:
                self.recorder.setOutputLocation(QUrl.fromLocalFile(target_abs))
                self.recorder.record()
                self.is_recording = True
                self.current_audio_rel = target_filename
                self.update_state()
            except Exception as e:
                QMessageBox.critical(self, "Recording Failed", f"Could not start audio recorder:\n{e}")
        else:
            # Stop recording
            try:
                self.recorder.stop()
            except Exception as e:
                print(f"[GlyphAudioWidget] Stop recorder notice: {e}")
            self.is_recording = False
            self.update_state()
            self.audio_changed.emit(self.current_audio_rel)

    def play_audio(self):
        if not self.player:
            return
        full_path = self._resolve_full_path(self.current_audio_rel)
        if full_path and os.path.exists(full_path):
            self.player.setSource(QUrl.fromLocalFile(full_path))
            self.player.play()

    def delete_audio(self):
        full_path = self._resolve_full_path(self.current_audio_rel)
        if full_path and os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception as e:
                print(f"[GlyphAudioWidget] File delete warning: {e}")
        self.current_audio_rel = ""
        self.update_state()
        self.audio_changed.emit("")

    def _on_recorder_state_changed(self, state):
        if state == QMediaRecorder.RecorderState.StoppedState:
            self.is_recording = False
            self.update_state()

    def _on_playback_state_changed(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.btn_play.setText("⏸ Playing...")
        else:
            self.btn_play.setText("▶ Play")
