# translation: English -> conlang engine (steps 1-2)

Words in, words out, **in English word order** for now (word order is step 3).

    from translation import TranslationEngine
    engine = TranslationEngine.from_repos(lexicon_repo, grammar_repo, language_id, ignore=["the", "a"])
    result = engine.translate("The big dogs chased the cat.")
    result.conlang_text   # the sentence
    result.gloss_text     # big dog-PL chase-PAST cat
    result.words          # one WordResult per word: form, gloss, status, alternatives, notes
    result.warnings       # unknown / ambiguous words, missing rules

Try it on a project: `python -m translation.cli MyLanguage.langarc "The dogs chased the cat."` (run from `src`).
Tests: `python -m unittest discover -s tests -v` (from the project root).

## How to fill in your data so the engine can use it

**Lexicon**
- *English Translation*: the English word(s), separated by `,` `;` or `/`. `to eat` and `eat` both work.
  Notes in (brackets) are ignored. Several words in one entry are fine, and a word can appear in several entries.
- *Part of Speech*: Noun, Verb, Adjective, Adverb, Pronoun, ... (abbreviations like `n`, `v`, `adj` work).
  It is used to choose between entries that share an English word ("light" noun vs adjective).
- *Meaning* is only used as a weak fallback, and only when it is 1-2 words long.

**Affix rules** (Grammar > Affix Rules)
- *Gloss tag* is what the engine looks for. These are recognised for each English feature:

  | English | Tags (any one) |
  |---|---|
  | plural | PL, PLUR, PLURAL |
  | past | PST, PAST, PRET |
  | past participle | PSTP, PTCP.PST, ... (falls back to past) |
  | progressive (-ing) | PROG, IPFV, GER, PTCP.PRS, ... |
  | comparative / superlative | CMP, COMP / SUP, SUPL |
  | 3rd person singular (optional) | 3SG |
  | present, singular (optional) | PRS / SG |

  "Optional" means: applied if you have a rule or grid cell for it, silently skipped if not.
  Dots, dashes and case do not matter (`3.sg` = `3SG`).
- *Affix pattern*: `-ya` suffix, `un-` prefix, `-en-` infix (after the 1st character; `-en-@2` = after the 2nd,
  `-en-@-1` = before the last), `ge-...-t` circumfix, `{stem}{stem}` anywhere (reduplication).
  The hyphens decide the kind; the "affix type" dropdown is only used when there are no hyphens.
  Tone/stress (suprafix) cannot be applied automatically; you get a warning.
- *Category name*: name a category "Noun ...", "Verb ..." or "Adjective ..." to restrict its rules to that
  part of speech. This is how two rules can share the tag PL (one for nouns, one for verbs).
- Several rules on one word are applied in the order they are listed.

**Paradigm grids**
- Top row and left column are tags: `NOM`, `SG`, `PST`, `3.SG` ... The corner cell is ignored.
- A cell is either a full form (`ire`) or an affix (`-yo`, `un-`).
- A grid beats the rules. Use it for irregular words.
- A grid applies to ONE word if its name contains that word's English meaning or headword
  ("Verb: to go"). It applies to a WHOLE CLASS only if its name is just the part of speech plus a
  generic word ("Noun declension", "Verb conjugation").

## Not done yet (later steps)
Word order, function words (the, is, will), negation/questions, per-word overrides, and the settings page.
Morphophonology (sound changes at the affix boundary) is not modelled: put irregular results in a grid.
