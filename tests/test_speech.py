import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from translation import speech   # noqa: E402


class Backend(unittest.TestCase):
    def setUp(self):
        self._orig = speech.WhisperTranscriber.transcribe

    def tearDown(self):
        speech.WhisperTranscriber.transcribe = self._orig

    def test_offline_failure_gets_a_friendly_message(self):
        def boom(self, path, language="en"):
            raise OSError("Got: HfHubHTTPError: 403 Forbidden\nCannot access content at: https://huggingface.co/x")
        speech.WhisperTranscriber.transcribe = boom
        with self.assertRaises(RuntimeError) as ctx:
            speech.WhisperBackend().transcribe("a.wav", "tiny.en")
        msg = str(ctx.exception)
        self.assertIn("Could not download the speech model 'tiny.en'", msg)
        self.assertIn("internet connection", msg)

    def test_other_errors_pass_through_unchanged(self):
        def boom(self, path, language="en"):
            raise ValueError("bad audio file")
        speech.WhisperTranscriber.transcribe = boom
        with self.assertRaises(ValueError):
            speech.WhisperBackend().transcribe("a.wav")

    def test_model_is_loaded_once_per_size(self):
        calls = []
        speech.WhisperTranscriber.transcribe = lambda self, path, language="en": calls.append(self.model_size) or "hi"
        b = speech.WhisperBackend()
        b.transcribe("a.wav", "base.en"); b.transcribe("b.wav", "base.en"); b.transcribe("c.wav", "small.en")
        self.assertEqual(sorted(b._cache), ["base.en", "small.en"])
        self.assertEqual(calls, ["base.en", "base.en", "small.en"])


if __name__ == "__main__":
    unittest.main()
