"""Run from the project root:   python -m unittest discover -s tests -v"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from translation import TranslationEngine                                          # noqa: E402
from translation.features import (                                                  # noqa: E402
    DEFAULT_FEATURES, TRIGGER_KEYS, WORD_CLASS_KEYS, trigger_for_tag,
)
from translation.inflect import condition_matches                                  # noqa: E402


def entry(i, headword, english, pos):
    return {"id": f"e{i}", "headword": headword, "english_translation": english,
            "part_of_speech": pos, "meaning": f"definition of {headword}", "ipa_reading": ""}


ENTRIES = [
    entry(1, "kor", "dog", "noun"), entry(2, "nim", "cat", "noun"), entry(3, "tomo", "house", "noun"),
    entry(4, "vok", "to walk", "verb"), entry(5, "ira", "to go", "verb"), entry(6, "mal", "big", "adjective"),
]
VOWELS = "a, e, i, o, u"


def value(vid, tag, trigger, feature="Number", classes=("NOUN",)):
    return {"id": vid, "feature_id": "f_" + feature, "feature_name": feature, "word_classes": list(classes),
            "tag": tag, "label": tag, "trigger": trigger}


VALUES = [
    value("v_sg", "SG", "singular"),
    value("v_pl", "PL", "plural"),
    value("v_du", "DU", ""),                                                  # a value nobody can trigger from English
    value("v_pst", "PST", "past", "Tense", ("VERB",)),
    value("v_prog", "PROG", "progressive", "Verb form", ("VERB",)),
    value("v_3sg", "3SG", "3sg", "Person", ("VERB",)),
    value("v_cmp", "CMP", "comparative", "Degree", ("ADJ", "ADV")),
]


def rule(rid, vid, pattern, position=1, **extra):
    r = {"id": rid, "name": rid, "affix_pattern": pattern, "affix_type": "suffix", "gloss_tag": "IGNORED",
         "value_id": vid, "position": position}
    r.update(extra)
    return r


def engine(rules, irregulars=(), values=VALUES, paradigms=(), categories=()):
    return TranslationEngine(ENTRIES, rules, list(categories), paradigms, feature_values=values,
                             irregulars=irregulars, ignore=["the", "a", "an"])


def irregular(iid, entry_id, value_ids, form):
    return {"id": iid, "entry_id": entry_id, "value_ids": value_ids, "form": form}


class FeatureValueRules(unittest.TestCase):
    def test_rule_attached_to_a_value_is_found_by_its_trigger(self):
        t = engine([rule("r1", "v_pl", "-ya")]).translate("dogs")
        self.assertEqual(t.conlang_text, "korya")

    def test_gloss_uses_the_tag_of_the_value_not_of_the_rule(self):
        self.assertEqual(engine([rule("r1", "v_pl", "-ya")]).translate("dogs").gloss_text, "dog-PL")
        renamed = [dict(v, tag="PLU") if v["id"] == "v_pl" else v for v in VALUES]
        self.assertEqual(engine([rule("r1", "v_pl", "-ya")], values=renamed).translate("dogs").gloss_text, "dog-PLU")

    def test_word_class_set_on_the_rule_limits_it(self):
        wrong = engine([rule("r1", "v_pl", "-ya", word_class="VERB")]).translate("dogs")
        self.assertEqual(wrong.conlang_text, "kor")
        self.assertTrue(wrong.warnings)
        right = engine([rule("r1", "v_pl", "-ya", word_class="NOUN")]).translate("dogs")
        self.assertEqual(right.conlang_text, "korya")

    def test_word_classes_of_the_feature_limit_a_rule_without_its_own(self):
        verb_only = [dict(v, word_classes=["VERB"]) if v["id"] == "v_pl" else v for v in VALUES]
        self.assertEqual(engine([rule("r1", "v_pl", "-ya")], values=verb_only).translate("dogs").conlang_text, "kor")

    def test_a_value_without_trigger_is_never_applied_by_itself(self):
        t = engine([rule("r1", "v_du", "-xa")]).translate("dogs")
        self.assertEqual(t.conlang_text, "kor")
        self.assertTrue(t.warnings)

    def test_older_rules_without_a_value_keep_working_beside_new_ones(self):
        legacy = {"id": "old", "name": "Past", "affix_pattern": "-ta", "affix_type": "suffix", "gloss_tag": "PAST",
                  "position": 2}
        t = engine([rule("r1", "v_pl", "-ya"), legacy]).translate("dogs walked")
        self.assertEqual(t.conlang_text, "korya vokta")

    def test_a_linked_rule_wins_over_an_older_one_for_the_same_meaning(self):
        legacy = {"id": "old", "name": "Plural", "affix_pattern": "-zz", "affix_type": "suffix", "gloss_tag": "PL",
                  "position": 1}
        self.assertEqual(engine([legacy, rule("r1", "v_pl", "-ya", position=2)]).translate("dogs").conlang_text, "korya")

    def test_a_rule_pointing_at_a_deleted_value_falls_back_to_its_own_tag(self):
        orphan = {"id": "r1", "name": "Plural", "affix_pattern": "-ya", "affix_type": "suffix", "gloss_tag": "PL",
                  "value_id": "gone", "position": 1}
        self.assertEqual(engine([orphan]).translate("dogs").conlang_text, "korya")


class Conditions(unittest.TestCase):
    def test_condition_matches(self):
        self.assertTrue(condition_matches("tomo", "ends_with", VOWELS))
        self.assertFalse(condition_matches("kor", "ends_with", VOWELS))
        self.assertTrue(condition_matches("kor", "not_ends_with", VOWELS))
        self.assertTrue(condition_matches("Kor", "starts_with", "k"))
        self.assertTrue(condition_matches("kor", "not_starts_with", "m, n"))
        self.assertTrue(condition_matches("ring", "ends_with", "ng"))
        self.assertTrue(condition_matches("TOMO", "ends_with", "o"))            # capitals do not matter
        self.assertTrue(condition_matches("anything", "", "a"))                 # no condition
        self.assertTrue(condition_matches("anything", "ends_with", ""))         # empty list
        self.assertTrue(condition_matches("anything", "nonsense", "a"))         # unknown kind is ignored

    def test_two_endings_chosen_by_how_the_stem_ends(self):
        rules = [rule("after_vowel", "v_pl", "-ya", 1, condition_type="ends_with", condition_value=VOWELS),
                 rule("after_consonant", "v_pl", "-a", 2, condition_type="not_ends_with", condition_value=VOWELS)]
        e = engine(rules)
        self.assertEqual(e.translate("houses").conlang_text, "tomoya")
        self.assertEqual(e.translate("dogs").conlang_text, "kora")

    def test_first_rule_that_fits_wins(self):
        rules = [rule("a", "v_pl", "-ya", 1), rule("b", "v_pl", "-zz", 2)]
        self.assertEqual(engine(rules).translate("dogs").conlang_text, "korya")

    def test_when_no_rule_fits_the_word_stays_and_says_why(self):
        t = engine([rule("only_vowel", "v_pl", "-ya", 1, condition_type="ends_with", condition_value=VOWELS)]).translate("dogs")
        self.assertEqual(t.conlang_text, "kor")
        self.assertTrue(any("fits" in w for w in t.warnings), t.warnings)

    def test_conditions_also_work_on_older_rules(self):
        legacy = {"id": "old", "name": "Plural", "affix_pattern": "-ya", "affix_type": "suffix", "gloss_tag": "PL",
                  "position": 1, "condition_type": "ends_with", "condition_value": VOWELS}
        self.assertEqual(engine([legacy]).translate("houses").conlang_text, "tomoya")
        self.assertEqual(engine([legacy]).translate("dogs").conlang_text, "kor")


class Irregulars(unittest.TestCase):
    PLURAL_RULE = rule("r1", "v_pl", "-ya")

    def test_an_irregular_form_beats_the_rule(self):
        e = engine([self.PLURAL_RULE], [irregular("i1", "e1", ["v_pl"], "kori")])
        t = e.translate("dogs")
        self.assertEqual(t.conlang_text, "kori")
        self.assertEqual(t.words[0].source, "irregular")
        self.assertEqual(t.gloss_text, "dog-PL")

    def test_only_the_word_it_was_made_for_is_affected(self):
        e = engine([self.PLURAL_RULE], [irregular("i1", "e1", ["v_pl"], "kori")])
        self.assertEqual(e.translate("cats").conlang_text, "nimya")

    def test_an_irregular_can_be_an_ending_instead_of_a_whole_word(self):
        e = engine([self.PLURAL_RULE], [irregular("i1", "e1", ["v_pl"], "-xa")])
        self.assertEqual(e.translate("dogs").conlang_text, "korxa")

    def test_it_beats_an_older_paradigm_grid(self):
        grid = [{"id": "g1", "name": "Verb: to go", "headers": ["Form \\ Feature", "SG", "PL"],
                 "rows": [["PST", "ire", "irum"]]}]
        rules = [rule("r2", "v_pst", "-ta")]
        plain = engine(rules, paradigms=grid).translate("went")
        self.assertEqual(plain.conlang_text, "ire")                          # the grid, as before
        irr = engine(rules, [irregular("i1", "e5", ["v_pst"], "irote")], paradigms=grid).translate("went")
        self.assertEqual(irr.conlang_text, "irote")

    def test_an_irregular_for_one_value_also_serves_a_word_that_asks_for_more(self):
        # "walks" asks for 3rd person singular and present; an irregular listed for 3rd person singular is enough
        e = engine([rule("r3", "v_3sg", "-s")], [irregular("i1", "e4", ["v_3sg"], "voke")])
        self.assertEqual(e.translate("walks").conlang_text, "voke")

    def test_the_most_specific_irregular_wins(self):
        irregulars = [irregular("i1", "e4", ["v_3sg"], "voke"), irregular("i2", "e4", ["v_3sg", "v_pst"], "nope")]
        e = engine([rule("r3", "v_3sg", "-s")], irregulars)
        self.assertEqual(e.translate("walks").conlang_text, "voke")           # "walks" never asks for past

    def test_an_irregular_for_a_feature_the_word_does_not_use_is_ignored(self):
        e = engine([self.PLURAL_RULE], [irregular("i1", "e1", ["v_pst"], "korta")])
        self.assertEqual(e.translate("dogs").conlang_text, "korya")

    def test_values_without_a_trigger_cannot_make_an_irregular_apply(self):
        e = engine([self.PLURAL_RULE], [irregular("i1", "e1", ["v_du"], "korxi")])
        self.assertEqual(e.translate("dogs").conlang_text, "korya")

    def test_broken_irregulars_are_skipped_quietly(self):
        junk = [irregular("i1", "", ["v_pl"], "x"), irregular("i2", "e1", ["v_pl"], ""),
                irregular("i3", "e1", "not a list", "y"), irregular("i4", "e1", ["missing"], "z"),
                {"id": "i5", "entry_id": "e1", "value_ids": '["v_pl"]', "form": "kori"}]     # stored as JSON text
        self.assertEqual(engine([self.PLURAL_RULE], junk).translate("dogs").conlang_text, "kori")


class StarterSet(unittest.TestCase):
    def test_every_default_value_listens_for_a_real_trigger(self):
        for feature in DEFAULT_FEATURES:
            self.assertTrue(feature["name"] and feature["values"])
            for cls in feature["word_classes"]:
                self.assertIn(cls, WORD_CLASS_KEYS)
            for v in feature["values"]:
                self.assertIn(v["trigger"], TRIGGER_KEYS, v)

    def test_default_tags_are_unique(self):
        tags = [v["tag"] for f in DEFAULT_FEATURES for v in f["values"]]
        self.assertEqual(len(tags), len(set(tags)))

    def test_every_trigger_the_translator_asks_for_has_a_starter_value(self):
        used = {v["trigger"] for f in DEFAULT_FEATURES for v in f["values"]}
        self.assertEqual(used, set(TRIGGER_KEYS))

    def test_familiar_tags_suggest_their_trigger(self):
        expected = {"PL": "plural", "PLUR": "plural", "plural": "plural", "SG": "singular", "PAST": "past",
                    "PST": "past", "PSTP": "past_participle", "PROG": "progressive", "3SG": "3sg",
                    "CMP": "comparative", "SUP": "superlative", "PRS": "present"}
        for tag, trigger in expected.items():
            self.assertEqual(trigger_for_tag(tag), trigger, tag)
        for tag in ("DU", "ERG", "", None):
            self.assertIsNone(trigger_for_tag(tag), tag)

    def test_the_starter_set_works_end_to_end(self):
        by_trigger = {}
        for position, feature in enumerate(DEFAULT_FEATURES):
            for v in feature["values"]:
                by_trigger[v["trigger"]] = {"id": "id_" + v["tag"], "feature_name": feature["name"],
                                            "word_classes": feature["word_classes"], **v}
        rules = [rule("r1", "id_PL", "-ya"), rule("r2", "id_PST", "-ta", 2), rule("r3", "id_CMP", "mo-", 3)]
        rules[2]["affix_type"] = "prefix"
        e = engine(rules, values=list(by_trigger.values()))
        self.assertEqual(e.translate("dogs walked bigger").conlang_text, "korya vokta momal")


class GrammarDatabase(unittest.TestCase):
    def setUp(self):
        from database.db_Manager import Database_Manager
        from database.grammar_db import GrammarRepository
        from database.lexicon_db import LexiconRepository
        from database.overview_db import LanguageOverviewRepository
        self.tmp = tempfile.mkdtemp()
        self.dbm = Database_Manager(os.path.join(self.tmp, "data", "p.db"))
        self.lang = LanguageOverviewRepository(self.dbm).create_initial_language("Zarin")
        self.other = LanguageOverviewRepository(self.dbm).create_initial_language("Other")
        self.gr = GrammarRepository(self.dbm)
        self.lex = LexiconRepository(self.dbm)

    def test_starter_set_is_added_once(self):
        self.assertTrue(self.gr.ensure_default_features(self.lang))
        self.assertFalse(self.gr.ensure_default_features(self.lang))
        names = [f["name"] for f in self.gr.get_features(self.lang)]
        self.assertEqual(names, [f["name"] for f in DEFAULT_FEATURES])
        values = self.gr.get_feature_values(self.lang)
        self.assertEqual(len(values), sum(len(f["values"]) for f in DEFAULT_FEATURES))
        plural = next(v for v in values if v["tag"] == "PL")
        self.assertEqual((plural["trigger"], plural["feature_name"], plural["word_classes"]),
                         ("plural", "Number", ["NOUN", "PRON"]))
        self.assertEqual(self.gr.get_features(self.other), [])                # per language

    def test_feature_and_value_crud_and_order(self):
        f = self.gr.add_feature(self.lang, "Case", ["noun"])
        a = self.gr.add_feature_value(f, "NOM", "Nominative")
        b = self.gr.add_feature_value(f, "ACC", "Accusative", "")
        self.assertEqual([v["tag"] for v in self.gr.get_feature_values(self.lang)], ["NOM", "ACC"])
        self.gr.update_feature(f, name="Cases", word_classes=["NOUN", "PRON"])
        self.gr.update_feature_value(b, tag="ACC2", trigger="plural")
        got = {v["id"]: v for v in self.gr.get_feature_values(self.lang)}
        self.assertEqual((got[b]["tag"], got[b]["trigger"], got[b]["feature_name"], got[b]["word_classes"]),
                         ("ACC2", "plural", "Cases", ["NOUN", "PRON"]))
        with self.assertRaises(ValueError):
            self.gr.add_feature_value("no-such-feature", "X")

    def test_deleting_a_value_unlinks_rules_and_trims_irregulars(self):
        f = self.gr.add_feature(self.lang, "Number", ["NOUN"])
        pl = self.gr.add_feature_value(f, "PL", "Plural", "plural")
        du = self.gr.add_feature_value(f, "DU", "Dual", "")
        rule_id = self.gr.add_rule(self.lang, "Plural", "PL", affix_pattern="-ya", affix_type="suffix", value_id=pl)
        only = self.gr.add_irregular(self.lang, "e1", [pl], "kori")
        both = self.gr.add_irregular(self.lang, "e2", [pl, du], "nimi")
        self.gr.delete_feature_value(pl)
        rules = {r["id"]: r for r in self.gr.get_rules(self.lang)}
        self.assertFalse(rules[rule_id]["value_id"])                           # back to a plain tagged rule
        left = {i["id"]: i for i in self.gr.get_irregulars(self.lang)}
        self.assertNotIn(only, left)                                           # nothing left of it
        self.assertEqual(left[both]["value_ids"], [du])

    def test_deleting_a_feature_removes_its_values(self):
        f = self.gr.add_feature(self.lang, "Number", ["NOUN"])
        self.gr.add_feature_value(f, "PL", "Plural", "plural")
        self.gr.delete_feature(f)
        self.assertEqual(self.gr.get_features(self.lang), [])
        self.assertEqual(self.gr.get_feature_values(self.lang), [])

    def test_irregular_crud(self):
        i = self.gr.add_irregular(self.lang, "e1", ["b", "a"], " kori ")
        row = self.gr.get_irregulars(self.lang, "e1")[0]
        self.assertEqual((row["form"], row["value_ids"]), ("kori", ["a", "b"]))
        self.assertEqual(self.gr.get_irregulars(self.lang, "e2"), [])
        self.gr.update_irregular(i, ["c"], "kor2")
        row = self.gr.get_irregulars(self.lang)[0]
        self.assertEqual((row["form"], row["value_ids"]), ("kor2", ["c"]))
        self.gr.delete_irregular(i)
        self.assertEqual(self.gr.get_irregulars(self.lang), [])

    def test_rule_gets_the_new_fields(self):
        r = self.gr.add_rule(self.lang, "Plural", "PL", affix_pattern="-ya", affix_type="suffix",
                             word_class="noun", condition_type="ends_with", condition_value="a, e")
        row = next(x for x in self.gr.get_rules(self.lang) if x["id"] == r)
        self.assertEqual((row["word_class"], row["condition_type"], row["condition_value"], row["value_id"]),
                         ("noun", "ends_with", "a, e", None))
        self.gr.update_rule(r, condition_type="starts_with", word_class="VERB")
        row = next(x for x in self.gr.get_rules(self.lang) if x["id"] == r)
        self.assertEqual((row["condition_type"], row["word_class"]), ("starts_with", "VERB"))

    def test_an_older_database_gets_the_new_rule_columns(self):
        import sqlite3
        path = os.path.join(self.tmp, "old.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE languages (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE grammar_rules (id TEXT PRIMARY KEY, language_id TEXT, category_id TEXT, name TEXT, "
                     "affix_pattern TEXT, affix_type TEXT, gloss_tag TEXT, gloss_description TEXT, position INTEGER, "
                     "created_at TIMESTAMP, updated_at TIMESTAMP)")          # a table as the earlier version made it
        conn.execute("INSERT INTO languages VALUES ('L')")
        conn.execute("INSERT INTO grammar_rules VALUES ('r', 'L', NULL, 'Plural', '-ya', 'suffix', 'PL', '', 1, NULL, NULL)")
        conn.commit()
        conn.close()
        from database.db_Manager import Database_Manager
        from database.grammar_db import GrammarRepository
        repo = GrammarRepository(Database_Manager(path))
        row = repo.get_rules("L")[0]
        self.assertEqual((row["gloss_tag"], row["value_id"], row["word_class"], row["condition_type"]), ("PL", None, "", ""))

    def test_the_engine_reads_everything_from_the_real_repositories(self):
        self.gr.ensure_default_features(self.lang)
        values = {v["tag"]: v["id"] for v in self.gr.get_feature_values(self.lang)}
        self.lex.add_entry(self.lang, "kor", "a domestic animal", part_of_speech="Noun", english_translation="dog")
        self.lex.add_entry(self.lang, "tomo", "a building", part_of_speech="Noun", english_translation="house")
        kor = next(e for e in self.lex.get_all_entries(self.lang) if e["headword"] == "kor")
        self.gr.add_rule(self.lang, "Plural after vowel", "PL", affix_pattern="-ya", affix_type="suffix",
                         value_id=values["PL"], condition_type="ends_with", condition_value=VOWELS, position=1)
        self.gr.add_rule(self.lang, "Plural after consonant", "PL", affix_pattern="-a", affix_type="suffix",
                         value_id=values["PL"], condition_type="not_ends_with", condition_value=VOWELS, position=2)
        engine_ = TranslationEngine.from_repos(self.lex, self.gr, self.lang)
        self.assertEqual(engine_.translate("dogs houses").conlang_text, "kora tomoya")
        self.gr.add_irregular(self.lang, kor["id"], [values["PL"]], "kori")
        engine_ = TranslationEngine.from_repos(self.lex, self.gr, self.lang)
        self.assertEqual(engine_.translate("dogs houses").conlang_text, "kori tomoya")

    def test_an_older_repository_object_without_the_new_methods_still_works(self):
        class OldRepo:
            def get_rules(self, _l): return [{"id": "r", "name": "Plural", "affix_pattern": "-ya", "affix_type": "suffix",
                                              "gloss_tag": "PL", "position": 1}]
            def get_categories(self, _l): return []
            def get_paradigms(self, _l): return []

        class Lex:
            def get_all_entries(self, _l): return ENTRIES
        self.assertEqual(TranslationEngine.from_repos(Lex(), OldRepo(), "x").translate("dogs").conlang_text, "korya")


if __name__ == "__main__":
    unittest.main()
