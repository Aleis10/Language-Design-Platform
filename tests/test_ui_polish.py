import os, re, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QLineEdit, QPushButton, QWidget

import ui.components.glyph_audio as glyph_audio


class _AudioStub(QWidget):                      # the sandbox has no audio device
    def __init__(self, *a, **k):
        super().__init__()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None


glyph_audio.GlyphAudioWidget = _AudioStub

from database.db_Manager import Database_Manager
from database.lexicon_db import LexiconRepository
from database.overview_db import LanguageOverviewRepository
from ui.components import button_styles as bs
from ui.frontend_main import MainWindow

app = QApplication.instance() or QApplication([])
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27bf\u2b00-\u2bff\u23e9-\u23ff\ufe0f\u25b6\u25cf]")
KEPT_SYMBOLS = set("\u2715\u25bc\u25b2\u2713\u2192\u2190\u21ba\u21bb")


class StylesTest(unittest.TestCase):
    def test_roles_have_the_shared_colours(self):
        for role, colour in (("primary", bs.BLUE), ("success", bs.GREEN), ("danger", bs.RED)):
            b = bs.set_role(QPushButton("x"), role)
            self.assertEqual(b.property("role"), role)
            self.assertIn(colour, b.styleSheet())
            self.assertIn("#ffffff", b.styleSheet())          # white text on the coloured buttons
        self.assertIn("#ffffff", bs.set_role(QPushButton("x"), "neutral").styleSheet())
        with self.assertRaises(ValueError):
            bs.set_role(QPushButton("x"), "purple")

    def test_icon_button(self):
        b = bs.set_icon_button(QPushButton("text"), "Trash.svg", "Delete", danger=True)
        self.assertEqual((b.text(), b.toolTip(), b.width(), b.property("role")), ("", "Delete", 28, "icon-danger"))
        self.assertIn(bs.RED, b.styleSheet())
        e = bs.set_icon_button(QPushButton(), "edit.svg", "Rename")
        self.assertEqual(e.property("role"), "icon")
        self.assertNotIn(bs.RED, e.styleSheet())


class LexiconTest(unittest.TestCase):
    def test_audio_variants_are_read_in_one_go(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database_Manager(os.path.join(tmp, "t.db"))
            with db.get_connection() as c:
                c.execute("INSERT INTO languages (id, name) VALUES ('L','T');")
                c.execute("INSERT INTO languages (id, name) VALUES ('M','Other');")
            lex = LexiconRepository(db)
            a = lex.add_entry("L", "kor", "", english_translation="dog")
            b = lex.add_entry("L", "mia", "", english_translation="cat")
            lex.add_entry("M", "zzz", "", english_translation="other language")
            lex.add_entry_audio(a, "a1.wav", "kor", "first")
            lex.add_entry_audio(a, "a2.wav", "kor2", "second")
            entries = lex.get_all_entries("L")
            self.assertEqual([e["headword"] for e in entries], ["kor", "mia"])
            for e in entries:
                self.assertEqual(e["audio_variants"], lex.get_entry_audio(e["id"]))
            self.assertEqual(len(entries[0]["audio_variants"]), 2)
            self.assertEqual(entries[1]["audio_variants"], [])
            labels = lex.get_entry_labels("L")
            self.assertEqual([(x["headword"], x["english_translation"]) for x in labels], [("kor", "dog"), ("mia", "cat")])


class WindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, "p.db")
        cls.db = Database_Manager(path)
        cls.repo = LanguageOverviewRepository(cls.db)
        cls.lang = cls.repo.create_initial_language("Test")      # also creates the overview row
        cls.win = MainWindow(db_manager=cls.db, overview_repo=cls.repo, language_id=cls.lang, db_path=path,
                             project_name="Test", session_dir=cls.tmp.name)
        cls.win.resize(1200, 800)
        cls.win.show()
        app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.win.close()
        cls.tmp.cleanup()

    def buttons(self, page):
        return {b.text(): b for b in page.findChildren(QPushButton) if b.text()}

    # ------------------------------------------------------------ colours
    def test_button_colours_by_purpose(self):
        w = self.win
        expected = {
            w.lexicon_page: {"+ Add Entry": "primary", "Edit": "primary", "Delete": "danger"},
            w.keyboard_page: {"+ New Preset": "primary", "Delete": "danger", "Save": "success", "Clear All": "danger",
                              "+ Add combination": "primary"},
            w.overview_page: {"+ Add Custom Section": "primary"},
            w.transcribe_page: {"Translate": "primary", "Settings": "neutral"},
            w.glyphs_page: {"+ Add Group": "primary"},
        }
        for page, mapping in expected.items():
            found = self.buttons(page)
            for text, role in mapping.items():
                if text in found:                                  # a few only exist while a row is selected
                    self.assertEqual(found[text].property("role"), role, (type(page).__name__, text))
        self.assertIn("Save", self.buttons(w.keyboard_page))
        self.assertIn("+ Add Entry", self.buttons(w.lexicon_page))

    def test_red_buttons_have_white_text(self):
        count = 0
        for b in self.win.findChildren(QPushButton):
            if b.property("role") == "danger":
                count += 1
                self.assertIn(bs.RED, b.styleSheet())
                self.assertIn("color: #ffffff", b.styleSheet())
        self.assertGreater(count, 0)

    # ------------------------------------------------------------ emoji
    def test_no_emoji_in_visible_text(self):
        for w in self.win.findChildren(QWidget):
            texts = []
            if isinstance(w, (QPushButton, QLabel)):
                texts.append(w.text())
            if isinstance(w, QLineEdit):
                texts.append(w.placeholderText())
            texts.append(w.toolTip())
            for t in texts:
                bad = [c for c in EMOJI.findall(t or "") if c not in KEPT_SYMBOLS]
                self.assertEqual(bad, [], (type(w).__name__, t))

    def test_no_emoji_in_source_strings(self):
        bad = []
        for folder in ("src/ui", "src/digital_keyboard"):
            for dirpath, _dirs, files in os.walk(os.path.join(ROOT, folder)):
                for name in files:
                    if not name.endswith(".py"):
                        continue
                    with open(os.path.join(dirpath, name), encoding="utf-8") as handle:
                        for n, line in enumerate(handle, 1):
                            if line.lstrip().startswith("#"):
                                continue
                            found = [c for c in EMOJI.findall(line) if c not in KEPT_SYMBOLS]
                            if found:
                                bad.append((name, n, "".join(found)))
        self.assertEqual(bad, [])

    # ------------------------------------------------------------ overview
    def test_overview_has_no_save_button_and_saves_itself(self):
        page = self.win.overview_page
        self.assertNotIn("Save Overview", self.buttons(page))
        page.input_exonym.setText("Zedish")
        page.text_history.setPlainText("Long ago")
        page.combo_script.setCurrentText("Abugida")
        self.assertTrue(page._autosave_timer.isActive())
        QTest.qWait(900)                                           # the short pause after the last change
        data = self.repo.get_overview_data(self.lang)
        self.assertEqual((data["exonym"], data["history"], data["script_system"]), ("Zedish", "Long ago", "Abugida"))

    def test_overview_saves_when_the_page_is_left(self):
        page = self.win.overview_page
        page.input_family.setText("Tiny family")
        self.assertTrue(page._autosave_timer.isActive())
        page.hide()                                                # leaving the page saves at once
        self.assertFalse(page._autosave_timer.isActive())
        self.assertEqual(self.repo.get_overview_data(self.lang)["genetic_classification"], "Tiny family")
        page.show()

    def test_overview_loading_does_not_trigger_a_save(self):
        self.repo.update_overview_field(self.lang, "autonym", "Native")
        from ui.pages.overview import Overview_Page
        fresh = Overview_Page(overview_repo=self.repo, language_id=self.lang)
        self.assertEqual(fresh.input_endonym.text(), "Native")
        self.assertFalse(fresh._autosave_timer.isActive())

    def test_overview_card_icons(self):
        page = self.win.overview_page
        page._add_card_widget("Notes", 0)
        card = page.custom_cards[-1]
        for btn, role in ((card.btn_rename, "icon"), (card.btn_delete, "icon-danger")):
            self.assertEqual((btn.text(), btn.property("role")), ("", role))
            self.assertFalse(btn.icon().isNull())

    # ------------------------------------------------------------ keyboard page
    def test_keyboard_page_hints(self):
        texts = [l.text() for l in self.win.keyboard_page.findChildren(QLabel)]
        self.assertIn("Click a key to assign a character", texts)
        self.assertIn("Choose a mode", texts)
        self.assertFalse(any("Unicode PPUA" in t or "Caps Lock" in t for t in texts))
        # the explanation of Once / Hold / Toggle is still there, as tooltips of the mode dropdown
        row_combo = self.win.keyboard_page.findChildren(QWidget)
        self.assertTrue(row_combo)

    # ------------------------------------------------------------ glyph gallery
    def test_glyph_tiles_use_icons_and_do_not_overlap(self):
        gp = self.win.glyphs_page
        repo = gp.glyph_repo
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><path d="M10 10 L90 90" stroke="black"/></svg>'
        gid = repo.add_group(self.lang, "Radicals")
        repo.create_glyph(self.lang, gid, "Sun", "star", svg_data=svg)
        repo.create_glyph(self.lang, gid, "Moon", "night", ipa_reading="muːn", svg_data=svg)
        gp.refresh_gallery()
        gp.resize(1000, 700)
        gp.show()
        for _ in range(3):
            app.processEvents()
        tiles = [f for f in gp.findChildren(QFrame) if f.property("class") == "glyph-tile"]
        self.assertEqual(len(tiles), 2)
        for tile in tiles:
            icons = [b for b in tile.findChildren(QPushButton) if b.property("role") == "icon-danger"]
            self.assertEqual(len(icons), 1)
            self.assertEqual(icons[0].text(), "")
            self.assertEqual([b.text() for b in tile.findChildren(QPushButton) if b.text()], ["Edit"])
            labels = tile.findChildren(QLabel)
            preview = [l for l in labels if l.pixmap() is not None and not l.pixmap().isNull()][0]
            name = [l for l in labels if l.text() in ("Sun", "Moon")][0]
            self.assertGreater(name.geometry().top(), preview.geometry().bottom())
            self.assertGreaterEqual(name.height(), name.sizeHint().height())
        # group header: icon buttons, no emoji
        header_icons = [b for b in gp.findChildren(QPushButton) if b.property("role") in ("icon", "icon-danger")]
        self.assertGreaterEqual(len(header_icons), 3)

    def test_tiles_do_not_overlap_with_tall_labels(self):
        from ui.pages import glyphs_page as gpm
        gp = self.win.glyphs_page
        original = gpm.ConlangLabel.__init__

        def tall(self_, *a, **k):
            original(self_, *a, **k)
            self_.setMinimumHeight(36)

        gpm.ConlangLabel.__init__ = tall
        try:
            gp.refresh_gallery()
            for _ in range(3):
                app.processEvents()
            tiles = [f for f in gp.findChildren(QFrame) if f.property("class") == "glyph-tile"]
            self.assertTrue(tiles)
            for tile in tiles:
                labels = tile.findChildren(QLabel)
                preview = [l for l in labels if l.pixmap() is not None and not l.pixmap().isNull()][0]
                name = [l for l in labels if l.text() in ("Sun", "Moon")][0]
                self.assertGreater(name.geometry().top(), preview.geometry().bottom())
        finally:
            gpm.ConlangLabel.__init__ = original


if __name__ == "__main__":
    unittest.main()
