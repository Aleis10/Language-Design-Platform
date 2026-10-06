"""Run from the project root:   python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from translation import Analysis, SimpleAnalyzer, Token, TranslationEngine   # noqa: E402
from translation.inflect import apply_affix                                  # noqa: E402

try:                                                    # optional dependency
    import spacy
    spacy.load("en_core_web_sm")
    HAVE_SPACY = True
except Exception:
    HAVE_SPACY = False


def entry(i, headword, english, pos, meaning=""):
    return {"id": f"e{i}", "headword": headword, "english_translation": english,
            "part_of_speech": pos, "meaning": meaning or f"definition of {headword}", "ipa_reading": ""}


ENTRIES = [
    entry(1, "kor", "dog", "noun"), entry(2, "nim", "cat", "noun"),
    entry(3, "sek", "to chase, chase", "verb"), entry(4, "mal", "big", "adjective"),
    entry(5, "ira", "to go", "verb"), entry(6, "tan", "thank you", "interjection"),
    entry(7, "vok", "to walk", "verb"), entry(8, "tomo", "house", "noun"),
]
CATS = [{"id": "cn", "name": "Noun morphology"}, {"id": "cv", "name": "Verb morphology"},
        {"id": "ca", "name": "Adjective morphology"}]
RULES = [
    {"id": "r1", "name": "Plural", "affix_pattern": "-ya", "affix_type": "suffix", "gloss_tag": "PL", "category_id": "cn", "position": 1},
    {"id": "r2", "name": "Past", "affix_pattern": "-ta", "affix_type": "suffix", "gloss_tag": "PAST", "category_id": "cv", "position": 2},
    {"id": "r3", "name": "Progressive", "affix_pattern": "-no", "affix_type": "suffix", "gloss_tag": "PROG", "category_id": "cv", "position": 3},
    {"id": "r4", "name": "Comparative", "affix_pattern": "mo-", "affix_type": "prefix", "gloss_tag": "CMP", "category_id": "ca", "position": 4},
]
GRIDS = [{"id": "g1", "name": "Verb: to go", "headers": ["Form \\ Feature", "SG", "PL"],
          "rows": [["PST", "ire", "irum"], ["PRS", "ira", "irao"]]}]


def engine(**kw):
    kw.setdefault("ignore", ["the", "a", "an"])
    return TranslationEngine(ENTRIES, RULES, CATS, GRIDS, **kw)


class FakeAnalyzer:
    """Returns a fixed reading per word, to test part-of-speech choices."""
    def __init__(self, readings):
        self.readings = readings

    def analyze(self, text):
        return [Token(w, [Analysis(w.lower(), *self.readings.get(w, ("", {})))]) for w in text.split()]


class Lookup(unittest.TestCase):
    def test_plain_word(self):
        t = engine().translate("dog")
        self.assertEqual((t.conlang_text, t.gloss_text), ("kor", "dog"))

    def test_gloss_list_and_leading_to(self):
        e = engine()
        self.assertEqual(e.translate("chase").conlang_text, "sek")
        self.assertEqual(e.translate("to go").conlang_text, "ira")

    def test_brackets_and_semicolons(self):
        e = TranslationEngine([entry(1, "zup", "stone (rock); pebble", "noun")])
        for w in ("stone", "pebble"):
            self.assertEqual(e.translate(w).conlang_text, "zup")
        self.assertEqual(e.translate("rock").words[0].status, "unknown")

    def test_phrase_longest_match(self):
        t = engine().translate("Thank you, dogs.")
        self.assertEqual(t.conlang_text, "tan, korya.")
        self.assertEqual(t.words[0].span, (0, 2))

    def test_unknown_word_policies(self):
        self.assertEqual(engine().translate("dogs fly").conlang_text, "korya [fly]")
        self.assertEqual(engine(unknown="keep").translate("dogs fly").conlang_text, "korya fly")
        self.assertEqual(engine(unknown="skip").translate("dogs fly").conlang_text, "korya")
        self.assertIn("unknown word: 'fly'", engine().translate("fly").warnings)

    def test_ignore_list_never_beats_a_real_entry(self):
        e = TranslationEngine(ENTRIES + [entry(9, "ta", "the", "determiner")], ignore=["the"])
        self.assertEqual(e.translate("the dog").conlang_text, "ta kor")
        self.assertEqual(engine().translate("the dog").conlang_text, "kor")

    def test_part_of_speech_picks_the_right_entry(self):
        entries = [entry(1, "luma", "light", "noun"), entry(2, "sol", "light", "adjective")]
        noun = TranslationEngine(entries, analyzer=FakeAnalyzer({"light": ("NOUN", {})}))
        adj = TranslationEngine(entries, analyzer=FakeAnalyzer({"light": ("ADJ", {})}))
        self.assertEqual(noun.translate("light").conlang_text, "luma")
        self.assertEqual(adj.translate("light").conlang_text, "sol")

    def test_unresolved_ambiguity_is_flagged_not_hidden(self):
        entries = [entry(1, "luma", "light", "noun"), entry(2, "sol", "light", "adjective")]
        t = TranslationEngine(entries).translate("light")
        w = t.words[0]
        self.assertEqual((w.status, w.form), ("ambiguous", "luma"))
        self.assertEqual([c.entry["headword"] for c in w.alternatives], ["sol"])
        self.assertTrue(any("ambiguous" in x for x in t.warnings))

    def test_english_translation_beats_loose_meaning(self):
        entries = [entry(1, "aaa", "", "noun", meaning="dog"), entry(2, "zzz", "dog", "noun")]
        w = TranslationEngine(entries).translate("dog").words[0]
        self.assertEqual(w.form, "zzz")


class Inflection(unittest.TestCase):
    def test_plural_rule(self):
        w = engine().translate("dogs").words[0]
        self.assertEqual((w.form, w.gloss, w.source, w.status), ("korya", "dog-PL", "rule:Plural", "ok"))

    def test_singular_unmarked(self):
        self.assertEqual(engine().translate("dog").conlang_text, "kor")

    def test_sentence_in_english_order(self):
        t = engine().translate("The big dogs chased the cats.")
        self.assertEqual(t.conlang_text, "mal korya sekta nimya.")
        self.assertEqual(t.gloss_text, "big dog-PL chase-PAST cat-PL")
        self.assertEqual(t.warnings, [])

    def test_progressive_and_comparative(self):
        e = engine()
        self.assertEqual(e.translate("walking").conlang_text, "vokno")
        self.assertEqual(e.translate("bigger").conlang_text, "momal")

    def test_irregular_form_from_grid_beats_rules(self):
        w = engine().translate("went").words[0]
        self.assertEqual((w.form, w.applied), ("ire", ["PST"]))     # the tag the grid itself uses
        self.assertTrue(w.source.startswith("grid:"))
        self.assertEqual(engine().translate("walked").conlang_text, "vokta")   # no grid -> rule

    def test_grid_cell_that_is_an_affix(self):
        grid = {"name": "Noun declension", "headers": ["x", "SG", "PL"], "rows": [["NOM", "", "-yo"]]}
        e = TranslationEngine(ENTRIES, RULES, CATS, [grid])
        self.assertEqual(e.translate("dogs").conlang_text, "korya" if False else "koryo")

    def test_old_format_grid_without_row_labels(self):
        grid = {"name": "Verb: to go", "headers": ["x", "PST", "PRS"], "rows": [["ire", "ira"]]}
        e = TranslationEngine(ENTRIES, RULES, CATS, [grid])
        self.assertEqual(e.translate("went").conlang_text, "ire")

    def test_missing_rule_is_reported_and_stem_kept(self):
        t = TranslationEngine(ENTRIES).translate("dogs")
        self.assertEqual(t.conlang_text, "kor")
        self.assertEqual(t.words[0].missing, ["PL"])
        self.assertTrue(any("PL" in w for w in t.warnings))

    def test_optional_features_stay_silent(self):
        t = engine().translate("she walks")      # 3rd person -> no rule needed in this language
        self.assertEqual(t.words[1].form, "vok")
        self.assertEqual([w for w in t.warnings if "walks" in w], [])
        rules = RULES + [{"id": "r9", "name": "3sg", "affix_pattern": "-s", "gloss_tag": "3SG",
                          "category_id": "cv", "position": 9}]
        self.assertEqual(TranslationEngine(ENTRIES, rules, CATS, GRIDS).translate("walks").conlang_text, "voks")

    def test_category_name_restricts_a_rule_to_its_part_of_speech(self):
        rules = [{"id": "p", "name": "Plural", "affix_pattern": "-ya", "gloss_tag": "PL", "category_id": "cv", "position": 1}]
        t = TranslationEngine(ENTRIES, rules, CATS).translate("dogs")        # rule sits under "Verb morphology"
        self.assertEqual((t.conlang_text, t.words[0].missing), ("kor", ["PL"]))

    def test_two_rules_same_tag_pick_by_part_of_speech(self):
        rules = RULES + [{"id": "p2", "name": "Verb plural", "affix_pattern": "-ra", "gloss_tag": "PL",
                          "category_id": "cv", "position": 5}]
        self.assertEqual(TranslationEngine(ENTRIES, rules, CATS).translate("dogs").conlang_text, "korya")

    def test_several_rules_apply_in_rule_order(self):
        rules = [
            {"id": "a", "name": "Past", "affix_pattern": "-ta", "gloss_tag": "PAST", "category_id": "cv", "position": 2},
            {"id": "b", "name": "3sg", "affix_pattern": "-s", "gloss_tag": "3SG", "category_id": "cv", "position": 1},
        ]
        class Both:
            def analyze(self, text):
                return [Token("x", [Analysis("walk", "VERB", {"Tense": "Past", "VerbForm": "Fin"})])]
        w = TranslationEngine(ENTRIES, rules, CATS, analyzer=Both()).translate("x").words[0]
        self.assertEqual(w.form, "vokta")

    def test_glyph_characters_pass_through(self):
        g = [entry(1, "\ue000\ue001", "dog", "noun")]
        r = [{"id": "r", "name": "Plural", "affix_pattern": "-\ue010", "gloss_tag": "PL", "position": 1}]
        self.assertEqual(TranslationEngine(g, r).translate("dogs").conlang_text, "\ue000\ue001\ue010")


class Choosing(unittest.TestCase):
    def setUp(self):
        entries = [entry(1, "luma", "light", "noun"), entry(2, "sol", "light", "adjective"),
                   entry(3, "kor", "dog", "noun")]
        self.engine = TranslationEngine(entries, RULES, CATS)

    def test_with_choice_swaps_the_entry_and_keeps_the_grammar(self):
        t = self.engine.translate("light dogs")
        self.assertEqual(t.conlang_text, "luma korya")
        alt = t.words[0].alternatives[0]
        t2 = self.engine.with_choice(t, 0, alt)
        self.assertEqual(t2.conlang_text, "sol korya")
        self.assertEqual(t2.words[0].status, "ok")
        self.assertIn("entry chosen manually", t2.words[0].notes)
        self.assertEqual(t2.warnings, [])            # no longer ambiguous

    def test_with_choice_keeps_inflection(self):
        entries = [entry(1, "kor", "dog", "noun"), entry(2, "hund", "dog", "noun")]
        e = TranslationEngine(entries, RULES, CATS)
        t = e.translate("dogs")
        t2 = e.with_choice(t, 0, t.words[0].alternatives[0])
        self.assertEqual((t.conlang_text, t2.conlang_text), ("hundya", "korya"))   # ties: alphabetical first

    def test_can_switch_back(self):
        t = self.engine.translate("light")
        t2 = self.engine.with_choice(t, 0, t.words[0].alternatives[0])
        t3 = self.engine.with_choice(t2, 0, t2.words[0].alternatives[0])
        self.assertEqual((t.conlang_text, t2.conlang_text, t3.conlang_text), ("luma", "sol", "luma"))


class Affixes(unittest.TestCase):
    def check(self, stem, pattern, atype, expect):
        self.assertEqual(apply_affix(stem, pattern, atype)[0], expect, (pattern, atype))

    def test_all_kinds(self):
        self.check("kor", "-ya", "suffix", "korya")
        self.check("kor", "un-", "prefix", "unkor")
        self.check("kor", "-en-", "infix", "kenor")
        self.check("kor", "-en-@2", "infix", "koenr")
        self.check("kor", "-en-@-2", "infix", "kenor")
        self.check("kor", "ge-...-t", "circumfix", "gekort")
        self.check("kor", "ge-*-t", "circumfix", "gekort")
        self.check("kor", "ge- -t", "circumfix", "gekort")
        self.check("kor", "{stem}{stem}", "other", "korkor")
        self.check("kor", "ma{stem}", "other", "makor")

    def test_hyphen_shape_beats_default_type_but_says_so(self):
        form, note = apply_affix("kor", "un-", "suffix")
        self.assertEqual(form, "unkor")
        self.assertIn("looks like a prefix", note)

    def test_cannot_apply_tone_or_stress(self):
        form, note = apply_affix("kor", "high tone", "suprafix")
        self.assertIsNone(form)
        self.assertIn("cannot be applied automatically", note)


class WithDatabase(unittest.TestCase):
    def test_from_repos_reads_the_real_database(self):
        from database.db_Manager import Database_Manager
        from database.grammar_db import GrammarRepository
        from database.lexicon_db import LexiconRepository
        from database.overview_db import LanguageOverviewRepository
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "data"))
        dbm = Database_Manager(os.path.join(tmp, "data", "p.db"))
        lang = LanguageOverviewRepository(dbm).create_initial_language("Test")
        lex, gr = LexiconRepository(dbm), GrammarRepository(dbm)
        lex.add_entry(lang, "kor", "a domestic animal", part_of_speech="Noun", english_translation="dog")
        lex.add_entry(lang, "ira", "to move away", part_of_speech="Verb", english_translation="to go")
        cat = gr.add_category(lang, "Noun morphology")
        gr.add_rule(lang, "Plural", "PL", category_id=cat, affix_pattern="-ya", affix_type="suffix")
        gr.add_paradigm(lang, "Verb: to go", "", ["Form \\ Feature", "SG"], [["PST", "ire"]])
        e = TranslationEngine.from_repos(lex, gr, lang, ignore=["the"])
        self.assertEqual(e.translate("The dogs went.").conlang_text, "korya ire.")
        self.assertEqual(e.translate("dogs went").gloss_text, "dog-PL go-PST")


@unittest.skipUnless(HAVE_SPACY, "spaCy / en_core_web_sm not installed")
class WithSpacy(unittest.TestCase):
    def setUp(self):
        from translation import SpacyAnalyzer
        self.engine = engine(analyzer=SpacyAnalyzer())

    def test_sentence(self):
        t = self.engine.translate("The big dogs chased the cat.")
        self.assertEqual(t.conlang_text, "mal korya sekta nim.")

    def test_progressive_and_irregular(self):
        self.assertEqual(self.engine.translate("The dog is walking.").conlang_text.split()[-1], "vokno.")
        self.assertEqual(self.engine.translate("She went.").conlang_text.endswith("ire."), True)


if __name__ == "__main__":
    unittest.main()
