"""Speech to text with Whisper (via faster-whisper). No Qt here, so it is easy to test.

faster-whisper is optional: `WhisperTranscriber.available()` says whether it is installed.
The first transcription with a model downloads it (tens to hundreds of MB, depending on size);
after that it works offline.
"""
from __future__ import annotations

import importlib.util
from typing import Dict, List

MODEL_CHOICES: List[str] = ["tiny.en", "base.en", "small.en", "medium.en", "tiny", "base", "small"]


class WhisperTranscriber:
    def __init__(self, model_size: str = "base.en", device: str = "auto", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel          # imported late: it is slow and optional
            self._model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        return self._model

    def transcribe(self, audio_path: str, language: str = "en") -> str:
        model = self._load()
        try:
            segments, _info = model.transcribe(audio_path, language=language, beam_size=5, vad_filter=True)
            parts = [seg.text.strip() for seg in segments]
        except Exception:                                    # VAD needs onnxruntime; retry without it
            segments, _info = model.transcribe(audio_path, language=language, beam_size=5, vad_filter=False)
            parts = [seg.text.strip() for seg in segments]
        return " ".join(p for p in parts if p).strip()


class WhisperBackend:
    """What the Transcribe page talks to. Keeps one loaded model per size."""

    def __init__(self):
        self._cache: Dict[str, WhisperTranscriber] = {}

    def available(self) -> bool:
        return WhisperTranscriber.available()

    def transcribe(self, audio_path: str, model_size: str = "base.en") -> str:
        t = self._cache.get(model_size)
        if t is None:
            t = self._cache[model_size] = WhisperTranscriber(model_size)
        try:
            return t.transcribe(audio_path)
        except Exception as exc:
            text = str(exc)
            if any(k in text for k in ("huggingface", "LocalEntryNotFound", "ConnectionError", "offline")):
                first_line = text.strip().splitlines()[0] if text.strip() else "network error"
                raise RuntimeError(
                    f"Could not download the speech model '{model_size}'.\n\n"
                    "The first use of a model needs an internet connection (it is downloaded from huggingface.co "
                    "and then stays on this computer). Check your connection or firewall and try again.\n\n"
                    f"Details: {first_line}"
                ) from exc
            raise
