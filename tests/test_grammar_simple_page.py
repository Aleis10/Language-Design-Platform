import os, sys, tempfile, unittest
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtWidgets import QApplication, QPushButton
from database.db_Manager import Database_Manager
from database.grammar_db import GrammarRepository
from database.lexicon_db import LexiconRepository
from translation import TranslationEngine
from ui.pages.grammar_simple_page import GrammarSimplePage, _RuleRow, _ExceptionRow

app = QApplication.instance() or QApplication([])
SENTENCE = "the big dog sees the cat in the house"


def make():
    tmp = tempfile.TemporaryDirectory()
    db = Database_Manager(os.path.join(tmp.name, "t.db"))
    with db.get_connection() as c:
        c.execute("INSERT INTO languages (id, name) VALUES ('L','Test');")
    gr, lex = GrammarRepository(db), LexiconRepository(db)
    ids = {}
    for head, eng, pos in [("kor", "dog", "noun"), ("mia", "cat", "noun"), ("ven", "house", "noun"),
                           ("tal", "big", "adjective"), ("sek", "see", "verb"), ("ru", "the", "determiner"),
                           ("ni", "in", "preposition"), ("chil", "child", "noun")]:
        ids[eng] = lex.add_entry("L", head, "", english_translation=eng, part_of_speech=pos)
    return tmp, db, gr, lex, ids


class PageTest(unittest.TestCase):
    def setUp(self):
        self.tmp, self.db, self.gr, self.lex, self.ids = make()
        self.page = GrammarSimplePage(self.gr, self.lex, "L")
        self.page.resize(1000, 700)
        self.page.show()

    def tearDown(self):
        self.page.close()
        self.tmp.cleanup()

    def translate(self, text=SENTENCE):
        eng = TranslationEngine.from_repos(self.lex, self.gr, "L", ignore=[])
        return eng.translate(text)

    def rule_rows(self):
        return [self.page.rules_box.itemAt(i).widget() for i in range(self.page.rules_box.count())]

    def test_no_try_it_and_no_advanced(self):
        self.assertFalse(hasattr(self.page, "txt_try"))
        texts = [b.text() for b in self.page.findChildren(QPushButton)]
        self.assertNotIn("Advanced", texts)

    def test_starts_with_starter_features_and_english_order(self):
        self.assertTrue(self.gr.get_features("L"))
        self.assertEqual(self.page.current_order(), {"sentence": ["S", "V", "O"], "np": ["DET", "ADJ", "NOUN"], "adp": "before"})
        self.assertTrue(self.page._order_buttons["SVO"].isChecked())
        self.assertEqual(self.page.lbl_example.text(), "Example:  dog sees cat")
        self.assertEqual(self.translate().conlang_text, "ru tal kor sek ru mia ni ru ven")

    def test_six_order_buttons_each_save_and_apply(self):
        self.assertEqual(sorted(self.page._order_buttons), sorted(["SVO", "SOV", "VSO", "VOS", "OVS", "OSV"]))
        for key in ("SOV", "VSO", "OSV", "SVO"):
            self.page._order_buttons[key].click()
            self.assertEqual(self.gr.get_word_order("L")["sentence"], list(key))
            self.assertEqual(self.page.current_order()["sentence"], list(key))
        self.page._order_buttons["SOV"].click()
        self.assertEqual(self.page.lbl_example.text(), "Example:  dog cat sees")
        self.assertEqual(self.translate().conlang_text, "ru tal kor ru mia ni ru ven sek")
        self.assertTrue(self.page._order_buttons["SOV"].isChecked())
        self.assertFalse(self.page._order_buttons["SVO"].isChecked())

    def test_adjective_determiner_adposition_choices(self):
        self.page.cmb_adj.setCurrentIndex(self.page.cmb_adj.findData(False))
        self.assertEqual(self.gr.get_word_order("L")["np"], ["DET", "NOUN", "ADJ"])
        self.assertEqual(self.translate("the big dog").conlang_text, "ru kor tal")
        self.page.cmb_det.setCurrentIndex(self.page.cmb_det.findData(False))
        self.assertEqual(self.gr.get_word_order("L")["np"], ["NOUN", "ADJ", "DET"])
        self.assertEqual(self.translate("the big dog").conlang_text, "kor tal ru")
        self.page.cmb_adp.setCurrentIndex(1)
        self.assertEqual(self.gr.get_word_order("L")["adp"], "after")
        self.assertIn("ven ru ni", self.translate().conlang_text)      # determiner after the noun too

    def test_reset_to_english(self):
        self.page._order_buttons["VOS"].click()
        self.page.cmb_adj.setCurrentIndex(1)
        self.page.cmb_adp.setCurrentIndex(1)
        self.page._reset_order()
        self.assertEqual(self.gr.get_word_order("L"), {"sentence": ["S", "V", "O"], "np": ["DET", "ADJ", "NOUN"], "adp": "before"})
        self.assertTrue(self.page._order_buttons["SVO"].isChecked())
        self.assertEqual(self.page.cmb_adp.currentData(), "before")
        self.assertEqual(self.page.cmb_adj.currentData(), True)

    def test_settings_reload_when_project_reopened(self):
        self.page._order_buttons["OVS"].click()
        self.page.cmb_adp.setCurrentIndex(1)
        again = GrammarSimplePage(self.gr, self.lex, "L")
        self.assertTrue(again._order_buttons["OVS"].isChecked())
        self.assertEqual(again.cmb_adp.currentData(), "after")

    def test_rule_header_and_columns_line_up(self):
        self.assertFalse(self.page.rules_header.isVisibleTo(self.page))      # no rules: no header
        self.page._add_rule()
        self.assertTrue(self.page.rules_header.isVisibleTo(self.page))
        app.processEvents()
        row = self.rule_rows()[0]
        labels = [self.page.rules_header.layout().itemAt(i).widget() for i in range(4)]
        widgets = [row.cmb_value, row.cmb_class, row.txt_affix, row.cmb_cond]
        for lbl, w in zip(labels, widgets):
            self.assertEqual(lbl.width(), w.width())
            self.assertAlmostEqual(lbl.mapTo(self.page, lbl.rect().topLeft()).x(),
                                   w.mapTo(self.page, w.rect().topLeft()).x(), delta=2)

    def test_rule_rows_do_not_overlap(self):
        for _ in range(3):
            self.page._add_rule()
        for _ in range(4):
            app.processEvents()
        rows = self.rule_rows()
        for a, b in zip(rows, rows[1:]):
            self.assertLess(a.geometry().bottom(), b.geometry().top())
        for r in rows:
            self.assertGreaterEqual(r.height(), r.minimumSizeHint().height())

    def test_add_rule_saves_and_applies(self):
        self.page._add_rule()
        row = self.rule_rows()[0]
        self.assertIsInstance(row, _RuleRow)
        self.assertEqual(row.cmb_value.currentText(), "Singular")
        row.cmb_value.setCurrentIndex(row.cmb_value.findText("Plural"))
        self.assertEqual(row.cmb_class.currentData(), "NOUN")
        self.assertEqual(self.gr.get_rules("L"), [])                      # no affix yet: not stored
        row.txt_affix.setText("-ya")
        row.txt_affix.editingFinished.emit()
        rules = self.gr.get_rules("L")
        self.assertEqual(len(rules), 1)
        self.assertEqual((rules[0]["affix_pattern"], rules[0]["word_class"], rules[0]["gloss_tag"]), ("-ya", "NOUN", "PL"))
        self.assertTrue(rules[0]["value_id"])
        self.assertEqual(self.translate("the dogs").conlang_text, "ru korya")
        # only if the word ends with a vowel: 'kor' does not
        self.assertFalse(row.txt_cond.isEnabled())
        row.cmb_cond.setCurrentIndex(row.cmb_cond.findData("ends_with"))
        self.assertTrue(row.txt_cond.isEnabled())
        row.txt_cond.setText("a e i o u")
        row.txt_cond.editingFinished.emit()
        self.assertEqual(self.gr.get_rules("L")[0]["condition_type"], "ends_with")
        self.assertEqual(self.translate("the dogs").conlang_text, "ru kor")
        row.cmb_cond.setCurrentIndex(0)
        self.assertEqual(self.gr.get_rules("L")[0]["condition_type"], "")
        self.assertEqual(self.translate("the dogs").conlang_text, "ru korya")
        row.btn_remove.click()
        self.assertEqual(self.gr.get_rules("L"), [])
        self.assertTrue(self.page.lbl_no_rules.isVisibleTo(self.page))
        self.assertFalse(self.page.rules_header.isVisibleTo(self.page))

    def test_word_type_follows_form_until_chosen_by_hand(self):
        self.page._add_rule()
        row = self.rule_rows()[0]
        row.cmb_value.setCurrentIndex(row.cmb_value.findText("Past"))
        self.assertEqual(row.cmb_class.currentData(), "VERB")
        row.cmb_class.setCurrentIndex(row.cmb_class.findData("NOUN"))        # chosen by hand
        row.cmb_value.setCurrentIndex(row.cmb_value.findText("Plural"))
        self.assertEqual(row.cmb_class.currentData(), "NOUN")
        row.cmb_class.setCurrentIndex(row.cmb_class.findData("ADJ"))
        row.cmb_value.setCurrentIndex(row.cmb_value.findText("Past"))
        self.assertEqual(row.cmb_class.currentData(), "ADJ")

    def test_rules_reload_after_refresh(self):
        self.page._add_rule()
        row = self.rule_rows()[0]
        row.cmb_value.setCurrentIndex(row.cmb_value.findText("Past"))
        row.txt_affix.setText("-ta")
        row.txt_affix.editingFinished.emit()
        self.page.refresh()
        rows = self.rule_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].cmb_value.currentText(), "Past")
        self.assertEqual(rows[0].cmb_class.currentData(), "VERB")
        self.assertEqual(rows[0].txt_affix.text(), "-ta")

    def test_old_rule_without_value_is_shown_and_kept(self):
        self.gr.add_rule("L", "Plural Marker", "PLUR", affix_pattern="-ya")
        self.gr.add_rule("L", "Weird", "ZZZ", affix_pattern="-zz")
        self.page.refresh()
        a, b = self.rule_rows()
        self.assertEqual(a.cmb_value.currentText(), "Plural")
        self.assertIn("older rule", b.cmb_value.currentText())
        b.txt_affix.setText("-zy")
        b.txt_affix.editingFinished.emit()
        r = [x for x in self.gr.get_rules("L") if x["gloss_tag"] == "ZZZ"][0]
        self.assertEqual((r["gloss_tag"], r["affix_pattern"]), ("ZZZ", "-zy"))

    def test_exception_saves_and_wins(self):
        self.page._add_rule()
        rr = self.rule_rows()[0]
        rr.cmb_value.setCurrentIndex(rr.cmb_value.findText("Plural"))
        rr.txt_affix.setText("-ya")
        rr.txt_affix.editingFinished.emit()
        self.assertEqual(self.translate("the children").conlang_text, "ru chilya")
        self.page._add_exception()
        row = self.page.exc_box.itemAt(0).widget()
        self.assertIsInstance(row, _ExceptionRow)
        row.cmb_word.showPopup()                    # the list of words is read when the dropdown opens
        row.cmb_word.hidePopup()
        row.cmb_word.setCurrentIndex(row.cmb_word.findData(self.ids["child"]))
        row.cmb_value.setCurrentIndex(row.cmb_value.findText("Plural"))
        self.assertEqual(self.gr.get_irregulars("L"), [])                 # no form yet
        row.txt_form.setText("chile")
        row.txt_form.editingFinished.emit()
        self.assertEqual([i["form"] for i in self.gr.get_irregulars("L")], ["chile"])
        self.assertEqual(self.translate("the children").conlang_text, "ru chile")
        row.txt_form.setText("chilo")
        row.txt_form.editingFinished.emit()
        self.assertEqual([i["form"] for i in self.gr.get_irregulars("L")], ["chilo"])
        self.page.refresh()
        again = self.page.exc_box.itemAt(0).widget()
        self.assertEqual((again.cmb_value.currentText(), again.txt_form.text()), ("Plural", "chilo"))
        again.btn_remove.click()
        self.assertEqual(self.gr.get_irregulars("L"), [])

    def test_word_dropdown_is_lazy_and_follows_the_lexicon(self):
        self.page._add_exception()
        row = self.page.exc_box.itemAt(0).widget()
        self.assertEqual(row.cmb_word.count(), 1)                         # only "(choose a word)" until opened
        row.cmb_word.showPopup()
        row.cmb_word.hidePopup()
        self.assertEqual(row.cmb_word.count(), 1 + 8)
        row.cmb_word.setCurrentIndex(row.cmb_word.findData(self.ids["child"]))
        row.cmb_value.setCurrentIndex(row.cmb_value.findText("Plural"))
        row.txt_form.setText("chile")
        row.txt_form.editingFinished.emit()
        self.page.refresh()
        again = self.page.exc_box.itemAt(0).widget()
        self.assertEqual(again.cmb_word.count(), 2)                       # the chosen word only
        self.assertIn("chil", again.cmb_word.currentText())
        # the word is renamed on the Lexicon page; coming back to the page shows the new name
        self.lex.update_entry(self.ids["child"], headword="kinda")
        self.page.hide()
        self.page.show()
        again = self.page.exc_box.itemAt(0).widget()
        self.assertIn("kinda", again.cmb_word.currentText())
        self.assertEqual(again.cmb_word.currentData(), self.ids["child"])

    def test_coming_back_to_the_page_keeps_its_rows(self):
        self.page._add_rule()
        row = self.rule_rows()[0]
        row.txt_affix.setText("-ya")
        row.txt_affix.editingFinished.emit()
        self.page.hide()
        self.page.show()
        self.assertIs(self.rule_rows()[0], row)

    def test_on_saved_is_called(self):
        calls = []
        self.page.on_saved = lambda: calls.append(1)
        self.page._order_buttons["SOV"].click()
        self.page._add_rule()
        row = self.rule_rows()[0]
        row.txt_affix.setText("-ya")
        row.txt_affix.editingFinished.emit()
        self.assertGreaterEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
