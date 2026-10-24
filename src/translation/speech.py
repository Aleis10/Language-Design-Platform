"""Speech to text with Whisper (via faster-whisper). No Qt here, so it is easy to test.

faster-whisper is optional: `WhisperTranscriber.available()` says whether it is installed.
The first transcription with a model downloads it (tens to hundreds of MB, depending on size);
after that it works offline.
"""
from __future__ import annotations

import importlib.util
import wave
from typing import Dict, List, Optional

MODEL_CHOICES: List[str] = ["tiny.en", "base.en", "small.en", "medium.en", "tiny", "base", "small"]


def load_wav_audio(path: str, target_rate: int = 16000):
    """Read a plain PCM .wav file as mono float32 at 16 kHz, which is what Whisper wants.

    Doing this ourselves means our own recordings do not depend on PyAV (faster-whisper's audio
    decoder), whose releases have broken faster-whisper before. Returns None when the file is not a
    plain PCM wav (mp3, m4a, float wav ...), and the caller then lets faster-whisper decode it.
    """
    try:
        import numpy as np
        with wave.open(path, "rb") as w:
            channels, width, rate, frames = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
            raw = w.readframes(frames)
        if width == 2:
            data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
        elif width == 4:
            data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
        elif width == 1:
            data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
        elif width == 3:
            b = np.frombuffer(raw, dtype=np.uint8)
            b = b[: (len(b) // 3) * 3].reshape(-1, 3).astype(np.int32)
            value = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            value = np.where(value >= 1 << 23, value - (1 << 24), value)
            data = value.astype(np.float32) / 8388608.0
        else:
            return None
        if channels > 1:
            data = data[: (len(data) // channels) * channels].reshape(-1, channels).mean(axis=1)
        if rate != target_rate and len(data) > 1:
            # straight-line resampling is plenty for speech
            n_out = int(round(len(data) * target_rate / rate))
            data = np.interp(np.linspace(0, len(data) - 1, n_out), np.arange(len(data)), data).astype(np.float32)
        return np.ascontiguousarray(data, dtype=np.float32)
    except Exception:                       # not a wav we can read: let faster-whisper handle the file
        return None


class WhisperTranscriber:
    # device "cpu" is the safe default: "auto" would pick an NVIDIA GPU even when its CUDA libraries
    # (libcublas ...) are not installed, and that only fails later, on the first transcription.
    def __init__(self, model_size: str = "base.en", device: str = "cpu", compute_type: str = "auto"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self.used = None   # (device, compute_type) that actually loaded

    @staticmethod
    def available() -> bool:
        return importlib.util.find_spec("faster_whisper") is not None

    # words that mean "this device / compute type cannot be used", so the next option is worth trying
    _DEVICE_ERRORS = ("compute type", "int8", "int16", "float16", "bfloat16", "efficient", "cuda", "cublas", "cudnn",
                      "device", "gpu")

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel          # imported late: it is slow and optional
            # "auto" lets CTranslate2 pick what this CPU supports. If that still fails (for example int8 or
            # a GPU that is not usable), fall back to plain CPU and finally to float32, which always works.
            attempts = []
            for option in ((self.device, self.compute_type), (self.device, "auto"), (self.device, "int8"),
                           ("cpu", "auto"), ("cpu", "float32")):
                if option not in attempts:
                    attempts.append(option)
            last_error = None
            for device, compute_type in attempts:
                try:
                    self._model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
                    self.used = (device, compute_type)
                    break
                except Exception as exc:
                    last_error = exc
                    if not any(word in str(exc).lower() for word in self._DEVICE_ERRORS):
                        raise                               # a download or file problem: retrying will not help
            if self._model is None:
                raise last_error
        return self._model

    @staticmethod
    def _is_gpu_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(word in text for word in ("cublas", "cudnn", "cuda", "libcu", "gpu"))

    def transcribe(self, audio_path: str, language: str = "en") -> str:
        try:
            return self._run(audio_path, language)
        except Exception as exc:
            # a GPU that loads but cannot run (missing CUDA libraries): redo it on the CPU, and stay there
            if self.device != "cpu" and self._is_gpu_error(exc):
                self._model = None
                self.device = "cpu"
                return self._run(audio_path, language)
            raise

    def _run(self, audio_path: str, language: str) -> str:
        model = self._load()
        audio = load_wav_audio(audio_path)
        if audio is not None and len(audio) < 1600:          # shorter than 0.1 s: nothing to transcribe
            return ""
        source = audio if audio is not None else audio_path
        try:
            segments, _info = model.transcribe(source, language=language, beam_size=5, vad_filter=True)
            parts = [seg.text.strip() for seg in segments]
        except Exception:                                    # VAD needs onnxruntime; retry without it
            segments, _info = model.transcribe(source, language=language, beam_size=5, vad_filter=False)
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
            if "metadata_errors" in text:
                raise RuntimeError(
                    "faster-whisper and the installed version of PyAV (its audio reader) do not match: "
                    "PyAV 19 removed something faster-whisper still uses.\n\n"
                    "Fix it once in the project's environment:\n\n    pip install \"av<19\"\n\n"
                    f"Details: {text}"
                ) from exc
            if any(k in text for k in ("huggingface", "LocalEntryNotFound", "ConnectionError", "offline")):
                first_line = text.strip().splitlines()[0] if text.strip() else "network error"
                raise RuntimeError(
                    f"Could not download the speech model '{model_size}'.\n\n"
                    "The first use of a model needs an internet connection (it is downloaded from huggingface.co "
                    "and then stays on this computer). Check your connection or firewall and try again.\n\n"
                    f"Details: {first_line}"
                ) from exc
            raise
