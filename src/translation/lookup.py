"""Step 1: find lexicon entries for an English word.

The index is built from each entry's `english_translation` field (and, as a weaker
fallback, short `meaning` fields). Glosses can be separated with , ; / or "or", and may
contain notes in (brackets) that are ignored:

    "dog, hound (animal)"      -> dog, hound
    "to eat; to consume"       -> to eat, eat, to consume, consume
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from .models import Candidate

POS_ALIASES = {
    "noun": "NOUN", "n": "NOUN", "nn": "NOUN", "propernoun": "NOUN",
    "verb": "VERB", "v": "VERB", "vt": "VERB", "vi": "VERB", "vb": "VERB",
    "adjective": "ADJ", "adj": "ADJ", "adverb": "ADV", "adv": "ADV",
    "pronoun": "PRON", "pron": "PRON", "pro": "PRON",
    "preposition": "ADP", "prep": "ADP", "postposition": "ADP", "adposition": "ADP", "adp": "ADP",
    "conjunction": "CONJ", "conj": "CONJ",
    "determiner": "DET", "det": "DET", "article": "DET", "art": "DET",
    "numeral": "NUM", "num": "NUM", "number": "NUM",
    "interjection": "INTJ", "intj": "INTJ", "interj": "INTJ",
    "particle": "PART", "part": "PART",
    "auxiliary": "AUX", "aux": "AUX",
}

# English (UD) part of speech -> lexicon part-of-speech class
UD_TO_CLASS = {
    "NOUN": "NOUN", "PROPN": "NOUN", "VERB": "VERB", "AUX": "VERB", "ADJ": "ADJ",
    "ADV": "ADV", "PRON": "PRON", "DET": "DET", "ADP": "ADP", "CCONJ": "CONJ",
    "SCONJ": "CONJ", "NUM": "NUM", "INTJ": "INTJ", "PART": "PART",
}

MAX_PHRASE_WORDS = 4


def pos_class(lexicon_pos: Optional[str]) -> Optional[str]:
    """Map a free-text part of speech ("Noun", "n.", "vt") to a class, or None."""
    if not lexicon_pos:
        return None
    m = re.match(r"[A-Za-z]+", lexicon_pos.strip().lower().replace(".", " "))
    return POS_ALIASES.get(m.group(0)) if m else None


def _clean(gloss: str) -> str:
    gloss = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", gloss)
    gloss = gloss.lower().strip(" \t\"'.!?")
    return re.sub(r"\s+", " ", gloss)


def split_glosses(text: Optional[str]) -> List[str]:
    """Break an english_translation value into normalized match keys."""
    if not text:
        return []
    keys: List[str] = []
    for part in re.split(r"[;,/|]|\bor\b", text):
        g = _clean(part)
        if not g:
            continue
        keys.append(g)
        for lead in ("to ", "a ", "an ", "the "):
            if g.startswith(lead) and len(g) > len(lead):
                keys.append(g[len(lead):])
    return list(dict.fromkeys(keys))


class LexiconIndex:
    def __init__(self, entries: Iterable[Dict[str, Any]], use_meaning_fallback: bool = True):
        self._by_key: Dict[str, List[Candidate]] = {}
        self.max_phrase_words = 1
        for entry in entries:
            self._add(entry, split_glosses(entry.get("english_translation")), "english_translation")
            if use_meaning_fallback:
                # only very short, gloss-like meanings ("dog", "to eat"); definitions are ignored
                meaning = entry.get("meaning") or ""
                if len(_clean(meaning).split()) <= 2:
                    self._add(entry, split_glosses(meaning), "meaning")

    def _add(self, entry: Dict[str, Any], keys: List[str], source: str) -> None:
        for key in keys:
            bucket = self._by_key.setdefault(key, [])
            if any(c.entry.get("id") == entry.get("id") and c.entry is entry for c in bucket):
                continue
            bucket.append(Candidate(entry=entry, gloss=key, source=source))
            self.max_phrase_words = max(self.max_phrase_words, min(len(key.split()), MAX_PHRASE_WORDS))

    def __len__(self) -> int:
        return len(self._by_key)

    def find(self, english: str, ud_pos: str = "") -> List[Candidate]:
        """Candidates for an English word/phrase, best first (part of speech, then source)."""
        key = _clean(english)
        want = UD_TO_CLASS.get(ud_pos) if ud_pos else None
        out: List[Candidate] = []
        seen = set()
        for c in self._by_key.get(key, []):
            ident = id(c.entry)
            if ident in seen:
                continue
            seen.add(ident)
            have = pos_class(c.entry.get("part_of_speech"))
            match: Optional[bool] = None
            if want and have:
                match = have == want
            out.append(Candidate(c.entry, c.gloss, c.source, match))

        def rank(c: Candidate):
            return (
                0 if c.pos_match is True else 1 if c.pos_match is None else 2,
                0 if c.source == "english_translation" else 1,
                str(c.entry.get("headword", "")),
            )
        return sorted(out, key=rank)
