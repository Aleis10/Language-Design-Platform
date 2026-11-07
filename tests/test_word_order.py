import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from database.db_Manager import Database_Manager
from database.grammar_db import GrammarRepository
from database.lexicon_db import LexiconRepository
from translation import TranslationEngine
from translation.word_order import (DEFAULT_ORDER, is_default, normalize_order, np_choices, np_from_choices,
                                    preset_name, sentence_example)

SOV = {"sentence": ["S", "O", "V"], "np": ["DET", "NOUN", "ADJ"], "adp": "after"}


def entries():
    def e(i, head, eng, pos):
        return {"id": i, "headword": head, "english_translation": eng, "part_of_speech": pos, "meaning": ""}
    return [e("1", "kor", "dog", "noun"), e("2", "mia", "cat", "noun"), e("3", "ven", "house", "noun"),
            e("4", "tal", "big", "adjective"), e("5", "sek", "see", "verb"), e("6", "ru", "the", "determiner"),
            e("7", "ni", "in", "preposition"), e("8", "dor", "sleep", "verb"), e("9", "bak", "bird", "")]


def run(text, order, ents=None):
    return TranslationEngine(ents or entries(), word_order=order, ignore=[]).translate(text).conlang_text


class Order(unittest.TestCase):
    def test_default_changes_nothing(self):
        self.assertEqual(run("the big dog sees the cat in the house", None),
                         "ru tal kor sek ru mia ni ru ven")

    def test_full_sov(self):
        self.assertEqual(run("the big dog sees the cat in the house", SOV),
                         "ru kor tal ru mia ru ven ni sek")

    def test_only_adjectives(self):
        o = {"np": ["DET", "NOUN", "ADJ"]}
        self.assertEqual(run("the big dog sees the cat", o), "ru kor tal sek ru mia")

    def test_only_adposition(self):
        self.assertEqual(run("the dog sleeps in the house", {"adp": "after"}), "ru kor dor ru ven ni")

    def test_vso_and_osv(self):
        self.assertEqual(run("the dog sees the cat", {"sentence": ["V", "S", "O"]}), "sek ru kor ru mia")
        self.assertEqual(run("the dog sees the cat", {"sentence": ["O", "S", "V"]}), "ru mia ru kor sek")

    def test_intransitive_keeps_phrase_with_verb(self):
        self.assertEqual(run("the dog sleeps in the house", {"sentence": ["V", "S", "O"]}),
                         "dor ni ru ven ru kor")

    def test_punctuation_and_conjunction_split_clauses(self):
        out = run("the dog sees the cat, and the cat sees the dog.", {"sentence": ["S", "O", "V"]})
        self.assertEqual(out, "ru kor ru mia sek, [and] ru mia ru kor sek.")

    def test_plural_and_inflected_words_keep_their_form(self):
        out = run("the dogs see the cat", {"sentence": ["S", "O", "V"]})
        self.assertTrue(out.endswith("sek"), out)

    def test_word_without_pos_is_warned(self):
        t = TranslationEngine(entries(), word_order=SOV).translate("the bird sees the cat")
        self.assertTrue(any("bird" in w and "part of speech" in w for w in t.warnings), t.warnings)

    def test_no_warning_in_english_order(self):
        t = TranslationEngine(entries()).translate("the bird sees the cat")
        self.assertFalse(any("part of speech" in w for w in t.warnings))

    def test_unknown_word_stays_in_clause(self):
        out = run("the zebra sees the cat", {"sentence": ["S", "O", "V"]})
        self.assertIn("[zebra]", out)

    def test_words_keep_gloss_in_new_order(self):
        t = TranslationEngine(entries(), word_order={"sentence": ["S", "O", "V"]}).translate("the dog sees the cat")
        self.assertEqual(t.gloss_text.split()[-1], "see")

    def test_with_choice_keeps_order(self):
        eng = TranslationEngine(entries(), word_order={"sentence": ["S", "O", "V"]})
        t = eng.translate("the dog sees the cat")
        again = eng.with_choice(t, 0, t.words[0].chosen) if t.words[0].chosen else t
        self.assertEqual(again.conlang_text, t.conlang_text)


class Settings(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_order(None), DEFAULT_ORDER)
        self.assertEqual(normalize_order({"sentence": ["S", "S", "V"]})["sentence"], ["S", "V", "O"])
        self.assertEqual(normalize_order({"adp": "middle"})["adp"], "before")
        self.assertEqual(normalize_order({"np": ["NOUN", "ADJ", "DET"]})["np"], ["NOUN", "ADJ", "DET"])
        self.assertTrue(is_default({}))
        self.assertFalse(is_default(SOV))

    def test_preset_name(self):
        self.assertEqual(preset_name(["S", "O", "V"]), "SOV")
        self.assertEqual(preset_name(["S", "V", "O"]), "Keep English (SVO)")

    def test_noun_phrase_choices(self):
        self.assertEqual(np_from_choices(True, True), ["DET", "ADJ", "NOUN"])
        self.assertEqual(np_from_choices(True, False), ["DET", "NOUN", "ADJ"])
        self.assertEqual(np_from_choices(False, True), ["ADJ", "NOUN", "DET"])
        self.assertEqual(np_from_choices(False, False), ["NOUN", "ADJ", "DET"])
        for det in (True, False):
            for adj in (True, False):
                self.assertEqual(np_choices(np_from_choices(det, adj)), (det, adj))
        self.assertEqual(np_choices(["NOUN", "DET", "ADJ"]), (False, False))

    def test_choice_orders_translate(self):
        self.assertEqual(run("the big dog", {"np": np_from_choices(True, False)}), "ru kor tal")
        self.assertEqual(run("the big dog", {"np": np_from_choices(False, True)}), "tal kor ru")

    def test_sentence_example(self):
        self.assertEqual(sentence_example(["S", "V", "O"]), "dog sees cat")
        self.assertEqual(sentence_example(["S", "O", "V"]), "dog cat sees")
        self.assertEqual(sentence_example(["V", "S", "O"]), "sees dog cat")


class Database(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database_Manager(os.path.join(self.tmp.name, "t.db"))
        with self.db.get_connection() as c:
            c.execute("INSERT INTO languages (id, name) VALUES ('L','Test');")
        self.repo = GrammarRepository(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_default_then_save_and_load(self):
        self.assertEqual(self.repo.get_word_order("L"), DEFAULT_ORDER)
        self.repo.set_word_order("L", SOV)
        self.assertEqual(self.repo.get_word_order("L"), SOV)
        self.repo.set_word_order("L", {"sentence": ["V", "S", "O"]})
        self.assertEqual(self.repo.get_word_order("L")["sentence"], ["V", "S", "O"])
        self.assertEqual(self.repo.get_word_order("L")["adp"], "before")

    def test_engine_from_repos_reads_it(self):
        lex = LexiconRepository(self.db)
        for e in entries():
            lex.add_entry("L", e["headword"], "", english_translation=e["english_translation"],
                          part_of_speech=e["part_of_speech"])
        self.repo.set_word_order("L", {"sentence": ["S", "O", "V"]})
        eng = TranslationEngine.from_repos(lex, self.repo, "L")
        self.assertEqual(eng.word_order["sentence"], ["S", "O", "V"])


if __name__ == "__main__":
    unittest.main()
