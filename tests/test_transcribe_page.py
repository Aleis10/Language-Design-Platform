"""Transcribe page tests (offscreen Qt, real repositories, fake speech backend)."""
import os
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication, QMessageBox, QStyleOptionViewItem   # noqa: E402

from database.db_Manager import Database_Manager                                # noqa: E402
from database.grammar_db import GrammarRepository                               # noqa: E402
from database.lexicon_db import LexiconRepository                               # noqa: E402
from database.overview_db import LanguageOverviewRepository                     # noqa: E402
from database.transcribe_db import DEFAULTS, TranscribeSettingsRepository       # noqa: E402
from digital_keyboard import (                                                  # noqa: E402
    export_language_font, get_fonts_dir, glyph_character, has_ppua, register_language_font,
)

app = QApplication.instance() or QApplication([])

SQ = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"><path d="M 50 100 L 250 100 L 250 300 L 50 300 Z"/></svg>'


class FakeSpeech:
    def __init__(self, text="the big dogs chased the cat", ok=True, available=True):
        self.text, self.ok, self._available, self.calls = text, ok, available, []

    def available(self):
        return self._available

    def transcribe(self, path, model="base.en"):
        self.calls.append((path, model))
        if not self.ok:
            raise RuntimeError("model could not be loaded")
        return self.text


def make_project():
    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "data"))
    export_language_font([{"id": "g1", "name": "x", "svg_data": SQ}], get_fonts_dir(tmp))
    fam = register_language_font(tmp)
    glyph = glyph_character(tmp, "g1")
    dbm = Database_Manager(os.path.join(tmp, "data", "p.db"))
    lang = LanguageOverviewRepository(dbm).create_initial_language("Zarin")
    lex, gr = LexiconRepository(dbm), GrammarRepository(dbm)
    lex.add_entry(lang, "kor", "a domestic animal", part_of_speech="Noun", english_translation="dog")
    lex.add_entry(lang, "hund", "a hound", part_of_speech="Noun", english_translation="dog")
    lex.add_entry(lang, "nim" + glyph, "a small feline", part_of_speech="Noun", english_translation="cat")
    lex.add_entry(lang, "sek", "to run after", part_of_speech="Verb", english_translation="to chase")
    lex.add_entry(lang, "mal", "of large size", part_of_speech="Adjective", english_translation="big")
    cn, cv = gr.add_category(lang, "Noun morphology"), gr.add_category(lang, "Verb morphology")
    gr.add_rule(lang, "Plural", "PL", category_id=cn, affix_pattern="-ya", affix_type="suffix")
    gr.add_rule(lang, "Past", "PAST", category_id=cv, affix_pattern="-ta", affix_type="suffix")
    return dict(tmp=tmp, fam=fam, glyph=glyph, dbm=dbm, lang=lang, lex=lex, gr=gr,
                settings=TranscribeSettingsRepository(dbm))


def make_page(p, speech=None):
    from ui.pages.transcribe_page import TranscribePage
    return TranscribePage(p["lex"], p["gr"], p["settings"], p["lang"], session_dir=p["tmp"],
                          speech_backend=speech or FakeSpeech())


def wait_for(cond, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


class Settings(unittest.TestCase):
    def test_defaults_and_round_trip(self):
        p = make_project()
        s = p["settings"].get_all(p["lang"])
        self.assertEqual(s, DEFAULTS)
        p["settings"].set_many(p["lang"], {"ignore_words": ["the"], "unknown": "keep", "auto_translate": False})
        s = p["settings"].get_all(p["lang"])
        self.assertEqual((s["ignore_words"], s["unknown"], s["auto_translate"], s["whisper_model"]),
                         (["the"], "keep", False, "base.en"))
        p["settings"].set_many(p["lang"], {"unknown": "skip"})            # update, not duplicate
        self.assertEqual(p["settings"].get_all(p["lang"])["unknown"], "skip")

    def test_defaults_are_not_shared_between_calls(self):
        p = make_project()
        p["settings"].get_all(p["lang"])["ignore_words"].append("zzz")
        self.assertNotIn("zzz", p["settings"].get_all(p["lang"])["ignore_words"])

    def test_settings_survive_reopening_the_database(self):
        p = make_project()
        p["settings"].set_many(p["lang"], {"ignore_words": ["the", "this"]})
        again = TranscribeSettingsRepository(Database_Manager(os.path.join(p["tmp"], "data", "p.db")))
        self.assertEqual(again.get_all(p["lang"])["ignore_words"], ["the", "this"])


class Translating(unittest.TestCase):
    def setUp(self):
        self.p = make_project()
        self.page = make_page(self.p)

    def test_typed_english_is_translated(self):
        t = self.page.translate_text("The big dogs chased the cat.")
        g = self.p["glyph"]
        # "kor" and "hund" both mean dog; ties go to the alphabetically first headword
        self.assertEqual(self.page.output_text.toPlainText(), f"mal hundya sekta nim{g}.")
        self.assertEqual(self.page.lbl_gloss.text(), "big dog-PL chase-PAST cat")
        self.assertIsNotNone(t)

    def test_default_ignore_list_drops_articles(self):
        self.page.translate_text("the cat")
        self.assertEqual(self.page.output_text.toPlainText(), "nim" + self.p["glyph"])

    def test_table_rows_and_statuses(self):
        self.page.translate_text("The dogs chased a bird.")
        rows = [[self.page.table.item(r, c).text() for c in range(5)] for r in range(self.page.table.rowCount())]
        by_english = {r[0]: r for r in rows}
        self.assertEqual(by_english["dogs"][2:4], ["dog-PL", "Plural"])
        self.assertIn("ambiguous", by_english["dogs"][4])           # "kor" and "hund" both mean dog
        self.assertEqual(by_english["bird"][4], "not in lexicon")
        self.assertEqual(by_english["The"][4], "skipped")
        self.assertEqual(len(rows), 5)                               # the, dogs, chased, a, bird (no punctuation row)
        self.assertTrue(self.page.lbl_warn.isVisibleTo(self.page))
        self.assertIn("unknown word: 'bird'", self.page.lbl_warn.text())

    def test_empty_input_clears(self):
        self.page.translate_text("dogs")
        self.page.translate_text("   ")
        self.assertEqual((self.page.output_text.toPlainText(), self.page.table.rowCount()), ("", 0))

    def test_conlang_output_uses_conlang_font_and_english_does_not(self):
        self.page.translate_text("cat")
        self.assertIn(self.p["fam"], self.page.output_text.font().families()[0])
        self.assertNotIn(self.p["fam"], self.page.input_text.font().families()[0])
        self.assertTrue(has_ppua(self.page.table.item(0, 1).text()))
        opt = QStyleOptionViewItem()
        self.page.table.itemDelegate().initStyleOption(opt, self.page.table.model().index(0, 1))
        self.assertIn(self.p["fam"], opt.font.families()[0])

    def test_reflects_lexicon_edits_without_reopening(self):
        self.page.translate_text("bird")
        self.assertEqual(self.page.table.item(0, 4).text(), "not in lexicon")
        self.p["lex"].add_entry(self.p["lang"], "avi", "a flying animal", part_of_speech="Noun", english_translation="bird")
        self.page.translate_text("bird")
        self.assertEqual(self.page.output_text.toPlainText(), "avi")

    def test_unknown_policy_setting_is_used(self):
        self.p["settings"].set_many(self.p["lang"], {"unknown": "keep"})
        self.page.translate_text("bird")
        self.assertEqual(self.page.output_text.toPlainText(), "bird")


class WordActions(unittest.TestCase):
    def setUp(self):
        self.p = make_project()
        self.page = make_page(self.p)

    def test_choose_another_entry_keeps_plural(self):
        self.page.translate_text("dogs")
        w = self.page.last_translation.words[0]
        before = self.page.output_text.toPlainText()
        self.page.choose_entry(0, candidate=w.alternatives[0])
        after = self.page.output_text.toPlainText()
        self.assertNotEqual(before, after)
        self.assertTrue(after.endswith("ya"))
        self.assertNotIn("ambiguous", self.page.table.item(0, 4).text())
        self.assertEqual(self.page.table.item(0, 2).text(), "dog-PL")

    def test_add_unknown_word_to_lexicon_then_retranslate(self):
        import ui.pages.transcribe_page as tp
        self.page.input_text.setPlainText("bird")
        self.page.translate_text("bird")
        seen = {}

        def fake_add(parent, repo, language_id, audio_dir, data_dir, english=""):
            seen["english"] = english
            repo.add_entry(language_id, "avi", "a flying animal", part_of_speech="Noun", english_translation=english)
            return True
        original, tp.add_entry_via_dialog = tp.add_entry_via_dialog, fake_add
        try:
            self.page._act_on_row(0)                # what a double-click on the unknown word does
        finally:
            tp.add_entry_via_dialog = original
        self.assertEqual(seen["english"], "bird")
        self.assertEqual(self.page.output_text.toPlainText(), "avi")


class Speech(unittest.TestCase):
    def setUp(self):
        self.p = make_project()
        self.messages = []
        self._orig = (QMessageBox.warning, QMessageBox.information)
        QMessageBox.warning = staticmethod(lambda *a, **k: self.messages.append(("warning", a[1:3])))
        QMessageBox.information = staticmethod(lambda *a, **k: self.messages.append(("info", a[1:3])))

    def tearDown(self):
        QMessageBox.warning, QMessageBox.information = self._orig

    def test_transcribed_audio_is_translated_automatically(self):
        speech = FakeSpeech("the big dogs chased the cat")
        page = make_page(self.p, speech)
        page._start_transcription("/tmp/does-not-matter.wav", delete_after=False)
        self.assertFalse(page.btn_record.isEnabled())                       # busy while Whisper runs
        self.assertTrue(wait_for(lambda: page.last_translation is not None))
        self.assertEqual(page.input_text.toPlainText(), "the big dogs chased the cat")
        self.assertEqual(page.lbl_gloss.text(), "big dog-PL chase-PAST cat")
        self.assertEqual(speech.calls, [("/tmp/does-not-matter.wav", "base.en")])
        self.assertTrue(wait_for(lambda: page.btn_record.isEnabled()))       # buttons come back

    def test_auto_translate_can_be_turned_off(self):
        self.p["settings"].set_many(self.p["lang"], {"auto_translate": False})
        page = make_page(self.p, FakeSpeech("dogs"))
        page._start_transcription("x.wav", delete_after=False)
        self.assertTrue(wait_for(lambda: page.input_text.toPlainText() == "dogs"))
        self.assertIsNone(page.last_translation)

    def test_chosen_model_is_passed_to_whisper(self):
        self.p["settings"].set_many(self.p["lang"], {"whisper_model": "small.en"})
        speech = FakeSpeech("dog")
        page = make_page(self.p, speech)
        page._start_transcription("x.wav", delete_after=False)
        self.assertTrue(wait_for(lambda: speech.calls))
        self.assertEqual(speech.calls[0][1], "small.en")

    def test_failure_is_reported_not_raised(self):
        page = make_page(self.p, FakeSpeech(ok=False))
        page._start_transcription("x.wav", delete_after=False)
        self.assertTrue(wait_for(lambda: self.messages))
        self.assertEqual(self.messages[0][0], "warning")
        self.assertIn("model could not be loaded", self.messages[0][1][1])
        self.assertTrue(wait_for(lambda: page.btn_record.isEnabled()))

    def test_empty_speech_is_reported(self):
        page = make_page(self.p, FakeSpeech(""))
        page._start_transcription("x.wav", delete_after=False)
        self.assertTrue(wait_for(lambda: "No speech" in page.lbl_status.text()))

    def test_recordings_are_deleted_after_use_imports_are_not(self):
        rec = os.path.join(self.p["tmp"], "rec.wav")
        imp = os.path.join(self.p["tmp"], "imp.wav")
        for f in (rec, imp):
            open(f, "wb").write(b"x")
        page = make_page(self.p, FakeSpeech("dog"))
        page._start_transcription(rec, delete_after=True)
        self.assertTrue(wait_for(lambda: not os.path.exists(rec)))
        page._start_transcription(imp, delete_after=False)
        self.assertTrue(wait_for(lambda: page.btn_record.isEnabled() and page.last_translation is not None))
        self.assertTrue(os.path.exists(imp))

    def test_missing_whisper_explains_how_to_install(self):
        page = make_page(self.p, FakeSpeech(available=False))
        page._toggle_record()
        self.assertEqual(self.messages[0][0], "info")
        self.assertIn("pip install faster-whisper", self.messages[0][1][1])
        self.assertFalse(page._recording)
        page.translate_text("cat")                                        # typing still works
        self.assertEqual(page.output_text.toPlainText(), "nim" + self.p["glyph"])


class MainWindowWiring(unittest.TestCase):
    def test_sidebar_and_stack_include_transcribe(self):
        p = make_project()
        from database.glyph_db import GlyphRepository
        from database.keyboard_db import KeyboardRepository
        from ui.frontend_main import MainWindow
        win = MainWindow(
            db_manager=p["dbm"], overview_repo=LanguageOverviewRepository(p["dbm"]),
            glyph_repo=GlyphRepository(p["dbm"]), lexicon_repo=p["lex"],
            keyboard_repo=KeyboardRepository(p["dbm"]), grammar_repo=p["gr"],
            language_id=p["lang"], db_path=os.path.join(p["tmp"], "data", "p.db"),
            project_name="Zarin", session_dir=p["tmp"],
        )
        self.assertEqual(len(win.sidebar.buttons), 6)
        self.assertEqual(win.pages.count(), 6)
        win.sidebar.select_button(5)
        self.assertIs(win.pages.currentWidget(), win.transcribe_page)
        win._rebuild_pages()                                              # what opening another project does
        self.assertEqual(win.pages.count(), 6)
        win.sidebar.select_button(5)
        self.assertIs(win.pages.currentWidget(), win.transcribe_page)
        win.transcribe_page.translate_text("cat")
        self.assertEqual(win.transcribe_page.output_text.toPlainText(), "nim" + p["glyph"])


if __name__ == "__main__":
    unittest.main()
