"""The translation engine: English text in, conlang words (with glosses) out.

Steps implemented so far
    1. Word lookup   English word  -> lexicon entry         (lookup.py)
    2. Inflection    dictionary form -> plural / past / ... (inflect.py)

Words come out in ENGLISH order for now; word order, function words and the settings page
are later steps. Nothing in this file depends on Qt.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .analyzer import SimpleAnalyzer
from .inflect import inflect, prepare_grids, prepare_rules
from .lookup import MAX_PHRASE_WORDS, LexiconIndex
from .models import Analysis, Candidate, Token, Translation, WordResult

_NO_SPACE_BEFORE = set(".,;:!?)]}%\u2026")
_NO_SPACE_AFTER = set("([{")


class TranslationEngine:
    def __init__(
        self,
        entries: Sequence[Dict[str, Any]],
        rules: Sequence[Dict[str, Any]] = (),
        categories: Sequence[Dict[str, Any]] = (),
        paradigms: Sequence[Dict[str, Any]] = (),
        analyzer=None,
        unknown: str = "bracket",          # "bracket" -> [word]   "keep" -> word   "skip" -> omitted
        ignore: Iterable[str] = (),        # English words to drop when the lexicon has no entry for them
    ):
        self.index = LexiconIndex(entries)
        self.rules = prepare_rules(rules, categories)
        self.grids = prepare_grids(paradigms)
        self.analyzer = analyzer or SimpleAnalyzer()
        self.unknown = unknown
        self.ignore = {w.strip().lower() for w in ignore if w.strip()}

    # -- construction from the app's repositories --------------------------
    @classmethod
    def from_repos(cls, lexicon_repo, grammar_repo, language_id: str, **kwargs) -> "TranslationEngine":
        return cls(
            entries=lexicon_repo.get_all_entries(language_id),
            rules=grammar_repo.get_rules(language_id),
            categories=grammar_repo.get_categories(language_id),
            paradigms=grammar_repo.get_paradigms(language_id),
            **kwargs,
        )

    # -- public API ----------------------------------------------------------
    def translate(self, text: str) -> Translation:
        tokens = self.analyzer.analyze(text)
        words: List[WordResult] = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            if tok.is_punct:
                words.append(WordResult(english=tok.text, form=tok.text, status="punct", span=(i, i + 1)))
                i += 1
                continue
            if tok.is_number:
                words.append(WordResult(english=tok.text, form=tok.text, status="number", span=(i, i + 1)))
                i += 1
                continue
            phrase = self._match_phrase(tokens, i)
            if phrase:
                words.append(phrase)
                i = phrase.span[1]
                continue
            words.append(self._translate_token(tok, i))
            i += 1
        return self._assemble(text, words)

    def with_choice(self, translation: Translation, index: int, candidate: Candidate) -> Translation:
        """Redo one word of an existing translation using a different lexicon entry.

        The word is inflected again with the same English features, so a plural stays plural.
        """
        w = translation.words[index]
        if w.entry is None:
            return translation
        hyp = Analysis(w.lemma, w.pos, dict(w.features))
        others = [c for c in ([w.chosen] if w.chosen else []) + list(w.alternatives)
                  if c.entry is not candidate.entry]
        words = list(translation.words)
        words[index] = self._build(w.english, hyp, [candidate] + others, w.span, forced=True)
        return self._assemble(translation.source_text, words)

    # -- internals -------------------------------------------------------------
    def _match_phrase(self, tokens: List[Token], i: int) -> Optional[WordResult]:
        longest = min(self.index.max_phrase_words, MAX_PHRASE_WORDS)
        for n in range(longest, 1, -1):
            span = tokens[i:i + n]
            if len(span) < n or any(t.is_punct or t.is_number for t in span):
                continue
            surface = [t.text.lower() for t in span]
            # the last word may be inflected: try its readings
            for hyp in span[-1].hypotheses:
                phrase = " ".join(surface[:-1] + [hyp.lemma])
                cands = self.index.find(phrase, hyp.pos)
                if cands:
                    return self._build(" ".join(t.text for t in span), hyp, cands, (i, i + n))
        return None

    def _translate_token(self, tok: Token, i: int) -> WordResult:
        best: Optional[Tuple[Tuple[int, int], Analysis, List[Candidate]]] = None
        for rank, hyp in enumerate(tok.hypotheses):
            cands = self.index.find(hyp.lemma, hyp.pos)
            if not cands:
                continue
            pos_rank = 0 if cands[0].pos_match is True else 1 if cands[0].pos_match is None else 2
            key = (pos_rank, rank)
            if best is None or key < best[0]:
                best = (key, hyp, cands)
            if pos_rank == 0:
                break
        if best:
            return self._build(tok.text, best[1], best[2], (i, i + 1))

        lower = tok.text.lower()
        if lower in self.ignore:
            return WordResult(english=tok.text, status="dropped", span=(i, i + 1),
                              notes=["on the ignore list and not in the lexicon"])
        form = {"bracket": f"[{tok.text}]", "keep": tok.text, "skip": ""}.get(self.unknown, f"[{tok.text}]")
        return WordResult(english=tok.text, form=form, status="unknown", span=(i, i + 1),
                          notes=["no lexicon entry has this English meaning"])

    def _build(self, english: str, hyp: Analysis, cands: List[Candidate], span: Tuple[int, int],
               forced: bool = False) -> WordResult:
        top = cands[0]
        ties = [] if forced else [c for c in cands[1:] if (c.pos_match, c.source) == (top.pos_match, top.source)]
        word = WordResult(
            english=english, lemma=hyp.lemma, pos=hyp.pos, entry=top.entry,
            stem=(top.entry.get("headword") or "").strip(), span=span,
            alternatives=cands[1:], chosen=top, features=dict(hyp.features),
        )
        if forced:
            word.notes.append("entry chosen manually")
        if ties:
            word.status = "ambiguous"
            word.notes.append(
                "several entries match: " + ", ".join(c.entry.get("headword", "?") for c in [top] + ties)
            )
        res = inflect(top.entry, hyp.lemma, hyp.pos, hyp.features, self.rules, self.grids)
        word.form, word.applied, word.missing = res.form, res.applied, res.missing
        word.source = res.source
        word.notes.extend(res.notes)
        word.gloss = hyp.lemma.replace(" ", ".") + "".join(f"-{t}" for t in res.applied)
        for m in res.missing:
            word.notes.append(f"no rule or grid for {m}; left as dictionary form")
        return word

    def _assemble(self, source: str, words: List[WordResult]) -> Translation:
        out_parts: List[str] = []
        gloss_parts: List[str] = []
        warnings: List[str] = []
        for w in words:
            if w.status == "dropped" or (w.status == "unknown" and not w.form):
                continue
            if w.status == "punct":
                if out_parts and w.form and w.form[0] in _NO_SPACE_BEFORE:
                    out_parts[-1] += w.form
                else:
                    out_parts.append(w.form)
                continue
            out_parts.append(w.form)
            gloss_parts.append(w.gloss or w.english)
        # join, but keep opening brackets attached to the next word
        text = ""
        for part in out_parts:
            if not text:
                text = part
            elif text[-1] in _NO_SPACE_AFTER:
                text += part
            else:
                text += " " + part
        for w in words:
            if w.status == "unknown":
                warnings.append(f"unknown word: '{w.english}'")
            elif w.status == "ambiguous":
                warnings.append(f"'{w.english}' is ambiguous: " + w.notes[0].split(": ", 1)[-1])
            if w.missing:
                warnings.append(f"'{w.english}': no rule or grid for {', '.join(w.missing)}")
        return Translation(
            source_text=source, words=words, conlang_text=text,
            gloss_text=" ".join(gloss_parts), warnings=list(dict.fromkeys(warnings)),
        )
